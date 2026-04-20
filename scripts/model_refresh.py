"""
model_refresh.py — Layer 2 模型區塊重算
==========================================
重算指定標的的 GBM 預估、物理診斷、分位數區間三個 MD section，
並就地更新 trades/ 對應的 MD 檔。

觸發時機：
  - event_detector.py 偵測到 Layer 3 事件後，由 hook 呼叫
  - 每 10~15 個交易日定期刷新（另一個 hook）
  - 手動：python scripts/model_refresh.py --code 2546

更新的 MD 區塊：
  1. ## 基本資訊   ← 僅更新量化屬性行的 μ 值與日期
  2. ## GBM 預估   ← μ/σ、60 日期望價、各目標/停損到達機率
  3. ## 物理診斷   ← 動量 p、溫度 T、流體狀態 + 分位數區間子表

資料來源：
  優先：journals/logs/{TODAY}_wave_scores.json（wave cache，避免重抓）
  回退：yfinance 現場抓取

用法：
  python scripts/model_refresh.py --code 2546
  python scripts/model_refresh.py --code 2546 --dry-run
  python scripts/model_refresh.py --from-events          # 讀今日 scan.log 的 EVENT 行
  python scripts/model_refresh.py --from-events --date 2026-04-17
"""

import sys
import os
import re
import json
import glob
import argparse
import math
from datetime import date

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADES_DIR = os.path.join(BASE_DIR, 'trades')
LOGS_DIR   = os.path.join(BASE_DIR, 'journals', 'logs')

TODAY = date.today().isoformat()


# ── 資料抓取（與 wave_score_scan 相同邏輯）────────────────────────────────────

def fetch_ohlcv(ticker, period='1y'):
    try:
        from curl_cffi import requests as creq
        import yfinance as yf
        session = creq.Session(verify=False, impersonate='chrome')
        df = yf.Ticker(ticker, session=session).history(period=period)
        if df.empty:
            return None
        df.index = df.index.tz_localize(None) if df.index.tzinfo else df.index
        return df.dropna()
    except Exception:
        return None


def load_ticker_map():
    path = os.path.join(BASE_DIR, 'stocks.csv')
    try:
        import pandas as pd
        return pd.read_csv(path, dtype=str).set_index('code')['ticker'].to_dict()
    except Exception:
        return {}


def load_wave_cache(today_str):
    path = os.path.join(LOGS_DIR, f'{today_str}_wave_scores.json')
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


# ── 從 trades MD 提取閾值（與 event_detector 相同）────────────────────────────

def extract_thresholds(content):
    targets = []
    for m in re.finditer(
            r'\|\s*(第\S+批[^|]*)\|[^|]*站上\s+\*\*([\d,\.]+)\s*元\*\*', content):
        try:
            targets.append((float(m.group(2).replace(',', '')), m.group(1).strip()))
        except ValueError:
            pass
    if not targets:
        for m in re.finditer(r'站上\s+\*\*([\d,\.]+)\s*元\*\*', content):
            try:
                targets.append((float(m.group(1).replace(',', '')), '目標'))
            except ValueError:
                pass

    stop, pause = None, None
    m = re.search(r'波段停損[^\n]*?跌破\s+\*\*([\d,\.]+)\s*元\*\*', content)
    if m:
        try:
            stop = float(m.group(1).replace(',', ''))
        except ValueError:
            pass
    m = re.search(r'暫停線[^\n]*?跌破\s+\*\*([\d,\.]+)\s*元\*\*', content)
    if m:
        try:
            pause = float(m.group(1).replace(',', ''))
        except ValueError:
            pass

    return targets, stop, pause


# ── GBM 計算 ──────────────────────────────────────────────────────────────────

def estimate_gbm(prices):
    """年化 μ / σ"""
    try:
        import arch
        lr   = np.log(prices / prices.shift(1)).dropna()
        res  = arch.arch_model(lr * 100, vol='GARCH', p=1, q=1,
                               dist='normal').fit(disp='off')
        sigma = (res.conditional_volatility[-1] / 100) * np.sqrt(252)
    except Exception:
        lr    = np.log(prices / prices.shift(1)).dropna()
        sigma = np.std(lr, ddof=1) * np.sqrt(252)
    lr    = np.log(prices / prices.shift(1)).dropna()
    mu    = (np.mean(lr) + 0.5 * (sigma / np.sqrt(252)) ** 2) * 252
    return mu, sigma


def lognormal_prob_above(S0, K, mu, sigma, T_days):
    """P(S_T >= K) under GBM"""
    T = T_days / 252
    if T <= 0 or sigma <= 0:
        return 0.0
    d2 = (math.log(S0 / K) + (mu - 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    from scipy.stats import norm
    return float(norm.cdf(d2))


def lognormal_prob_below(S0, K, mu, sigma, T_days):
    """P(S_T <= K) under GBM"""
    return 1.0 - lognormal_prob_above(S0, K, mu, sigma, T_days)


# ── section 生成 ──────────────────────────────────────────────────────────────

def build_gbm_section(today_str, current, mu, sigma, targets, stop, pause):
    T_days = 60
    T      = T_days / 252
    exp_price = current * math.exp(mu * T)
    exp_pct   = (exp_price / current - 1) * 100

    lines = [
        f'## GBM 預估（{today_str} 重算）',
        '',
        '| 指標 | 數值 |',
        '|------|------|',
        f'| μ / σ | **{mu*100:+.1f}% / {sigma*100:.1f}%**（年化） |',
        f'| {T_days} 日期望價 | **{exp_price:.1f} 元**（{exp_pct:+.1f}%） |',
    ]

    # 到達目標價的機率（取第一批和最後一批）
    shown = []
    if targets:
        first_t  = targets[0]
        last_t   = targets[-1] if len(targets) > 1 else None
        for price, label in ([first_t] + ([last_t] if last_t else [])):
            if price not in shown:
                prob = lognormal_prob_above(current, price, mu, sigma, T_days)
                lines.append(
                    f'| {T_days} 日到達 {price:.0f}（{label}）機率 '
                    f'| {prob*100:.1f}% |'
                )
                shown.append(price)

    # 跌破暫停線的機率
    barrier = pause if pause else stop
    if barrier:
        prob = lognormal_prob_below(current, barrier, mu, sigma, T_days)
        lines.append(
            f'| {T_days} 日跌破 {barrier:.1f}（{"暫停線" if pause else "停損"}）機率 '
            f'| {prob*100:.1f}% |'
        )

    lines.append('')
    return '\n'.join(lines)


def build_physics_section(today_str, df, current, q_data):
    from physics_engine import compute_physics, diagnose_fluid_state

    phys = compute_physics(df)
    row  = phys.iloc[-1]

    mom  = row.get('momentum', 0) or 0
    temp = row.get('temperature', 0) or 0
    temp_pct = temp * 100

    mom_dir   = '↑' if mom > 0 else '↓'
    mom_state = '正向加速' if mom > 0 else '負向減速' if mom < 0 else '中性'
    if abs(mom) > 1e6:
        mom_str = f'{mom/1e6:.0f}M'
    elif abs(mom) > 1e3:
        mom_str = f'{mom/1e3:.0f}K'
    else:
        mom_str = f'{mom:.0f}'

    temp_status = '🟢 正常' if temp_pct < 3 else ('🟡 偏高' if temp_pct < 5 else '🔴 過熱')
    fluid_state = diagnose_fluid_state(row)

    atr14     = q_data.get('atr14', 0) or 0
    sell_low  = q_data.get('sell_low', 0)
    sell_high = q_data.get('sell_high', 0)
    buy_low   = q_data.get('buy_low', 0)
    buy_high  = q_data.get('buy_high', 0)
    deep_low  = q_data.get('deep_low', 0)
    stop_lvl  = q_data.get('stop_level', 0)

    # 現價相對賣出區的描述
    if current >= sell_high:
        price_desc = f'超越賣出區上緣 {sell_high:.1f}'
    elif current >= sell_low:
        price_desc = f'在賣出區 {sell_low:.1f}~{sell_high:.1f} 內'
    elif current >= buy_high:
        price_desc = f'已脫離賣出區下緣 {sell_low:.1f}'
    else:
        price_desc = f'在買回區附近'

    lines = [
        f'## 物理診斷（{today_str}）',
        '',
        '| 指標 | 數值 | 狀態 |',
        '|------|------|------|',
        f'| 動量 p | {mom_str} {mom_dir} | {mom_state} |',
        f'| 溫度 T | {temp_pct:.2f}% | {temp_status} |',
        f'| 流體狀態 | {fluid_state} | — |',
        '',
        f'### 歷史分位數決策區間（{today_str}）',
        '',
        '| 區域 | 價格 |',
        '|------|------|',
        f'| 現價 | **{current:.1f}**（{price_desc}）|',
        f'| 賣出區 | {sell_low:.2f} ~ {sell_high:.2f} |',
        f'| 常規買回區 | {buy_low:.2f} ~ {buy_high:.2f} |',
        f'| 深度買回區 | {deep_low:.2f} ~ {buy_low:.2f} |',
    ]
    if stop_lvl:
        lines.append(f'| 暫停線 | {stop_lvl:.2f} |')

    lines.append('')
    atr_comment = '低波動，適合底倉長持' if atr14 < 3 else ('中等波動' if atr14 < 8 else '高波動，謹慎管理部位')
    lines.append(f'> ATR14 = {atr14:.2f} 元；{atr_comment}。')
    lines.append('')
    return '\n'.join(lines)


# ── MD 更新 ───────────────────────────────────────────────────────────────────

def update_mu_in_basic_info(content, mu, today_str):
    """只更新量化屬性行裡的 μ 值與日期，不動其他內容。"""
    return re.sub(
        r'(量化屬性[^\n]*漂移率 \$\\mu\$ = )[+\-][\d\.]+%(，\d{4}-\d{2}-\d{2} 重算)',
        lambda m: f'{m.group(1)}{mu*100:+.1f}%，{today_str} 重算',
        content
    )


def replace_md_section(content, heading_pattern, new_section_text):
    """
    找到第一個符合 heading_pattern 的 ## 標題，
    取代到下一個同層（或更高層）## 標題前。
    回傳 (updated_content, replaced: bool)
    """
    lines = content.splitlines(keepends=True)
    start_idx = None
    level     = None

    for i, line in enumerate(lines):
        m = re.match(r'^(#{1,6})\s+' + heading_pattern, line)
        if m:
            start_idx = i
            level     = len(m.group(1))
            break

    if start_idx is None:
        return content, False

    # 找下一個同層或更高層的標題
    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        m = re.match(r'^(#{1,6})\s+', lines[i])
        if m and len(m.group(1)) <= level:
            end_idx = i
            break

    new_lines = (new_section_text.rstrip('\n') + '\n\n').splitlines(keepends=True)
    updated   = ''.join(lines[:start_idx] + new_lines + lines[end_idx:])
    return updated, True


# ── 從 scan.log 提取命中事件的股票代號 ───────────────────────────────────────

def load_event_codes(today_str):
    log_path = os.path.join(LOGS_DIR, f'{today_str}_scan.log')
    if not os.path.exists(log_path):
        return []
    codes = []
    with open(log_path, encoding='utf-8', errors='replace') as f:
        for line in f:
            m = re.search(r'🔔 EVENT \[(\d+)', line)
            if m:
                code = m.group(1)
                if code not in codes:
                    codes.append(code)
    return codes


# ── 主流程 ────────────────────────────────────────────────────────────────────

def refresh_one(code, today_str, dry_run=False):
    """重算並更新單一標的的模型區塊。回傳 (success: bool, summary: str)"""
    # 找 trades MD
    pattern = os.path.join(TRADES_DIR, f'{code}_*.md')
    matches = glob.glob(pattern)
    if not matches:
        return False, f'{code}: 找不到 trades MD'
    fpath = matches[0]

    with open(fpath, encoding='utf-8') as f:
        content = f.read()

    # 載入資料（優先 wave cache）
    wave_cache = load_wave_cache(today_str)
    cached     = wave_cache.get(code)

    if cached:
        import pandas as pd
        # 從 cache 取 GBM 參數（仍需原始資料做物理計算）
        mu    = cached['mu']
        sigma = cached['sigma']
        current = cached['current']
        q_data  = cached.get('q_data', {})
    else:
        mu, sigma, current, q_data = None, None, None, {}

    # 物理診斷需要原始 OHLCV
    ticker_map = load_ticker_map()
    ticker     = ticker_map.get(code, f'{code}.TW')
    df         = fetch_ohlcv(ticker)

    if df is None or df.empty:
        return False, f'{code}: 無法取得行情資料'

    prices  = df['Close']
    current = float(prices.iloc[-1])

    if mu is None:
        mu, sigma = estimate_gbm(prices)

    if not q_data:
        from quantile_engine import compute_quantile_metrics
        q_data = compute_quantile_metrics(df)

    # 提取 MD 內的目標價 / 停損 / 暫停線
    targets, stop, pause = extract_thresholds(content)

    # 生成新的 section 文字
    gbm_section  = build_gbm_section(today_str, current, mu, sigma,
                                     targets, stop, pause)
    phys_section = build_physics_section(today_str, df, current, q_data)

    # 更新 content
    updated = content
    updated = update_mu_in_basic_info(updated, mu, today_str)
    updated, ok1 = replace_md_section(updated, 'GBM 預估', gbm_section)
    updated, ok2 = replace_md_section(updated, '物理診斷', phys_section)

    changed = updated != content
    if not changed:
        return True, f'{code}: 無異動（section 未找到或內容相同）'

    if not dry_run:
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(updated)

    sections_updated = []
    if ok1: sections_updated.append('GBM 預估')
    if ok2: sections_updated.append('物理診斷')
    tag = '[dry-run] ' if dry_run else ''
    return True, f'{tag}{code}: 已更新 {" + ".join(sections_updated)}（μ={mu*100:+.1f}%，ATR={q_data.get("atr14", 0):.2f}）'


def main():
    ap = argparse.ArgumentParser(description='模型區塊重算')
    ap.add_argument('--code', help='股票代號（單一）')
    ap.add_argument('--from-events', action='store_true',
                    help='從今日 scan.log 讀取 EVENT 代號批次處理')
    ap.add_argument('--dry-run', action='store_true', help='只顯示，不寫入')
    ap.add_argument('--date', default=TODAY)
    args = ap.parse_args()

    today_str = args.date

    if args.from_events:
        codes = load_event_codes(today_str)
        if not codes:
            print(f'[model-refresh] {today_str} — scan.log 無 EVENT 紀錄，略過')
            return
        print(f'[model-refresh] {today_str} — 從 EVENT 取得 {len(codes)} 個標的：{", ".join(codes)}')
    elif args.code:
        codes = [args.code]
    else:
        ap.error('請指定 --code 或 --from-events')

    results = []
    for code in codes:
        ok, msg = refresh_one(code, today_str, dry_run=args.dry_run)
        status  = '✅' if ok else '❌'
        print(f'  {status} {msg}')
        results.append(msg)

    if results:
        print(f'\n共處理 {len(results)} 檔')


if __name__ == '__main__':
    main()
