"""
wave_score_scan.py — 每日成長趨勢股 Wave Score 掃描器
=====================================================
收盤後執行，自動：
  1. 掃描 trades/ 下所有成長趨勢股（🚀 / 📈）
  2. 計算最新 Wave Score（均線 + GBM + 分位數 + 物理引擎）
  3. 寫回各 MD 的 Wave Score 歷史表（若無則自動建立）
  4. 更新基本資訊的現價 / 月線欄位
  5. 覆寫 journals/戰術指南.md 末尾的「📊 Wave Score 日更新」區塊

行動優先級：
  🔴 動能背離 / 波段破壞  — 進入賣出區且 Wave ≤ 0，或低於暫停線
  🟢 加碼機會            — 解凍 / 觸發門檻 / 買回區
  🟡 觀察               — 賣出區趨勢延伸、跌破月線、接近賣出區
  ✅ 無需行動

用法：
  python scripts/wave_score_scan.py
  python scripts/wave_score_scan.py --dry-run   # 僅顯示，不寫入
"""

import sys
import os
import re
import glob
import json
import argparse
from datetime import date

sys.stdout.reconfigure(encoding='utf-8')

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADES_DIR   = os.path.join(BASE_DIR, 'trades')
JOURNALS_DIR = os.path.join(BASE_DIR, 'journals')
TACTICAL_MD  = os.path.join(JOURNALS_DIR, '戰術指南.md')
LOGS_DIR     = os.path.join(JOURNALS_DIR, 'logs')

# 區塊標記（用於在戰術指南末尾找到並覆寫）
WAVE_SECTION_MARKER = '## 📊 Wave Score 日更新'


# ── 基礎工具 ─────────────────────────────────────────────────────────────────

def load_ticker_map():
    path = os.path.join(BASE_DIR, 'stocks.csv')
    try:
        return pd.read_csv(path, dtype=str).set_index('code')['ticker'].to_dict()
    except Exception:
        return {}


def fetch_ohlcv(ticker, period='1y'):
    try:
        from curl_cffi import requests as creq
        import yfinance as yf
        session = creq.Session(verify=False, impersonate='chrome')
        df = yf.Ticker(ticker, session=session).history(period=period)
        df.columns = [c.title() for c in df.columns]
        return df.dropna()
    except Exception as e:
        print(f'    ⚠️  無法下載 {ticker}：{e}')
        return None


def load_checkup_dy(today_str):
    """從今日健診 MD 讀殖利率對照表 {code: dy_str}"""
    path = os.path.join(BASE_DIR, f'持倉健診_{today_str}.md')
    dy_map = {}
    if not os.path.exists(path):
        return dy_map
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.startswith('|') or '---' in line:
                continue
            cells = [c.strip() for c in line.split('|') if c.strip()]
            if len(cells) >= 6:
                code = cells[0].strip('`')
                dy_val = cells[5]
                if re.match(r'[\d\.]+%', dy_val):
                    dy_map[code] = dy_val
    return dy_map


def find_growth_stocks():
    """回傳 [(code, filepath, name)] — 🚀 趨勢股 + 📈 穩健走升股"""
    results = []
    for fpath in sorted(glob.glob(os.path.join(TRADES_DIR, '*.md'))):
        fname = os.path.basename(fpath)
        if fname == 'template.md':
            continue
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                head = f.read(400)
        except Exception:
            continue
        if '🚀' in head or '📈' in head:
            m = re.match(r'^(\d+)_(.+)\.md$', fname)
            if m:
                results.append((m.group(1), fpath, m.group(2)))
    return results


# ── Wave Score 計算 ───────────────────────────────────────────────────────────

def estimate_gbm(prices):
    lr = np.diff(np.log(prices.values))
    try:
        from arch import arch_model
        res = arch_model(lr * 100, vol='Garch', p=1, o=0, q=1).fit(disp='off')
        sigma = (res.conditional_volatility[-1] / 100) * np.sqrt(252)
    except Exception:
        sigma = np.std(lr, ddof=1) * np.sqrt(252)
    mu = (np.mean(lr) + 0.5 * (sigma / np.sqrt(252)) ** 2) * 252
    return mu, sigma


def calc_ma_score(prices):
    cur  = float(prices.iloc[-1])
    ma5  = float(prices.tail(5).mean())
    ma10 = float(prices.tail(10).mean())
    ma20 = float(prices.tail(20).mean())
    ma60 = float(prices.tail(60).mean())
    raw  = sum([cur > ma5, ma5 > ma10, ma10 > ma20, ma20 > ma60])
    return raw - 2, raw, ma20


def calc_gbm_score(current, mu, sigma, days=20):
    T   = days / 252
    E   = current * np.exp(mu * T)
    std = sigma * np.sqrt(T) * current
    if current < E - 0.5 * std:  return 2
    if current <= E + 0.5 * std: return 0
    if current <= E + std:       return -1
    return -2


def calc_quantile_score(df, current):
    from quantile_engine import compute_quantile_metrics
    q = compute_quantile_metrics(df)
    if current >= q['sell_low']:   return -2, q
    if current >= q['buy_high']:   return  0, q
    if current >= q['buy_low']:    return  2, q
    if current >= q['deep_low']:   return  3, q
    return -3, q


def calc_physics_score(df):
    from physics_engine import (compute_physics, detect_antigravity,
                                detect_energy_dissipation)
    phys = compute_physics(df)
    row  = phys.iloc[-1]
    mom  = row.get('momentum', 0) or 0
    re_n = row.get('reynolds', 0) or 0
    raw  = sum([
        mom > 0,
        re_n < 2000,
        not detect_antigravity(phys),
        not detect_energy_dissipation(phys),
    ])
    return raw - 2, mom


def analyze(code, ticker, period='1y'):
    df = fetch_ohlcv(ticker, period)
    if df is None or df.empty:
        return None
    prices  = df['Close']
    current = float(prices.iloc[-1])
    as_of   = df.index[-1].date()

    mu, sigma          = estimate_gbm(prices)
    ma_s, ma_raw, ma20 = calc_ma_score(prices)
    gbm_s              = calc_gbm_score(current, mu, sigma)
    q_s, q_data        = calc_quantile_score(df, current)
    phys_s, mom        = calc_physics_score(df)
    total              = ma_s + gbm_s + q_s + phys_s

    return dict(
        code=code, current=current, as_of=as_of,
        ma20=ma20, mu=mu, sigma=sigma,
        ma_s=ma_s, ma_raw=ma_raw, gbm_s=gbm_s,
        q_s=q_s, q_data=q_data,
        phys_s=phys_s, mom=mom,
        total=total,
        sell_low=q_data['sell_low'],
        buy_high=q_data['buy_high'],
        buy_low=q_data['buy_low'],
    )


# ── 行動偵測 ──────────────────────────────────────────────────────────────────

def detect_actions(r, last_score):
    """
    回傳 [(priority, tag, msg)]
    priority: 0=🔴  1=🟢  2=🟡

    核心原則：
      進入賣出區 + Wave > 0  → 趨勢延伸（🟡）
      進入賣出區 + Wave <= 0 → 動能背離（🔴）
      跌破月線              → 🟡（Wave <= -3 升級為 🔴）
      低於暫停線            → 🔴
    """
    t       = r['total']
    current = r['current']
    actions = []

    # ── 🔴 動能背離 / 波段破壞 ───────────────────────────────────────────────
    if r['q_s'] == -2 and t <= 0:
        dist = (current - r['sell_low']) / r['sell_low'] * 100
        actions.append((0, '🔴 減持訊號',
                        f'進入賣出區(+{dist:.1f}%) 且 Wave {t:+d}，動能背離'))

    if r['q_s'] <= -3:
        actions.append((0, '🔴 波段破壞',
                        f'現價 {current:.1f} 低於歷史暫停線'))

    if current < r['ma20'] and t <= -3:
        dist = (r['ma20'] - current) / r['ma20'] * 100
        actions.append((0, '🔴 月線深度失守',
                        f'{current:.1f} < MA20 {r["ma20"]:.1f}(-{dist:.1f}%) Wave {t:+d}'))

    # ── 🟢 加碼機會 ──────────────────────────────────────────────────────────
    if last_score is not None and last_score <= -2 and t >= -1:
        actions.append((1, '🟢 解凍',
                        f'Wave {last_score:+d} → {t:+d}，加碼條件成立'))
    elif t >= 3:
        actions.append((1, '🟢 強力加碼', f'Wave {t:+d}'))
    elif t >= 1 and (last_score is None or last_score < 1):
        last_str = f'{last_score:+d}' if last_score is not None else '無'
        actions.append((1, '🟢 輕倉加碼', f'Wave {t:+d}（上次 {last_str}）'))

    if r['q_s'] >= 2:
        actions.append((1, '🟢 買回區',
                        f'進入回測買點 {r["buy_low"]:.1f}～{r["buy_high"]:.1f}'))

    # ── 🟡 觀察 ──────────────────────────────────────────────────────────────
    if r['q_s'] == -2 and t > 0:
        dist = (current - r['sell_low']) / r['sell_low'] * 100
        actions.append((2, '🟡 賣出區（趨勢延伸）',
                        f'超賣出下緣 +{dist:.1f}%，Wave {t:+d} 仍強，等爆量收黑訊號'))

    if current < r['ma20'] and t > -3:
        dist = (r['ma20'] - current) / r['ma20'] * 100
        actions.append((2, '🟡 跌破月線',
                        f'{current:.1f} < MA20 {r["ma20"]:.1f}(-{dist:.1f}%)'))

    if r['q_s'] == 0 and r['sell_low'] > 0 and t >= 0:
        dist = (r['sell_low'] - current) / r['sell_low'] * 100
        if dist < 2:
            actions.append((2, '🟡 接近賣出區',
                            f'距賣出下緣 {r["sell_low"]:.1f} 僅 {dist:.1f}%'))

    if last_score is not None and last_score >= 0 and t <= -2:
        actions.append((2, '🟡 惡化', f'Wave {last_score:+d} → {t:+d}'))

    return sorted(actions, key=lambda x: x[0])


# ── trades/ MD 讀寫 ───────────────────────────────────────────────────────────

def get_last_wave_score(content):
    rows, in_table = [], False
    for line in content.splitlines():
        if '| 日期 |' in line and '總分' in line:
            in_table = True
            continue
        if in_table:
            if line.strip().startswith('|') and '---' not in line:
                rows.append(line)
            elif not line.strip().startswith('|') and rows:
                break
    if not rows:
        return None
    m = re.search(r'\*\*([+-]?\d+)\*\*', rows[-1])
    return int(m.group(1)) if m else None


def rec_label(total):
    if total >= 5:   return '強力加碼'
    if total >= 3:   return '加碼'
    if total >= 1:   return '輕倉加碼/觀察'
    if total >= -1:  return '持有不動'
    if total >= -3:  return '部分減持'
    return '強力減持'


WAVE_TABLE_HEADER = (
    '\n### Wave Score 歷史紀錄\n'
    '| 日期 | 現價 | MA | GBM | 分位 | 物理 | 總分 | 建議 |\n'
    '|------|------|----|----|------|------|------|------|\n'
)


def make_wave_row(r, today_str):
    rec = rec_label(r['total'])
    return (f'| {today_str} | {r["current"]:.1f} | {r["ma_s"]:+d} | '
            f'{r["gbm_s"]:+d} | {r["q_s"]:+d} | {r["phys_s"]:+d} | '
            f'**{r["total"]:+d}** | {rec} |')


def already_recorded_today(content, today_str):
    """只在 Wave Score 歷史紀錄表格段落中檢查今日是否已記錄，
    避免 減持執行紀錄 等其他表格的日期欄干擾判斷。"""
    in_wave_table = False
    for line in content.splitlines():
        if '| 日期 |' in line and '總分' in line:
            in_wave_table = True
            continue
        if in_wave_table:
            if line.strip().startswith('|') and '---' not in line:
                if today_str in line:
                    return True
            elif not line.strip().startswith('|'):
                in_wave_table = False
    return False


# ── Wave Score cache（盤後結果固定，避免重複抓資料）────────────────────────────

def _cache_path(today_str):
    return os.path.join(LOGS_DIR, f'{today_str}_wave_scores.json')


def load_wave_cache(today_str):
    path = _cache_path(today_str)
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_wave_cache(today_str, raw_results):
    os.makedirs(LOGS_DIR, exist_ok=True)
    cache = {}
    for r in raw_results:
        if r is None:
            continue
        code = r['code']
        cache[code] = {
            'current':  float(r['current']),
            'as_of':    str(r['as_of']),
            'ma20':     float(r['ma20']),
            'mu':       float(r['mu']),
            'sigma':    float(r['sigma']),
            'ma_s':     int(r['ma_s']),
            'ma_raw':   int(r['ma_raw']),
            'gbm_s':    int(r['gbm_s']),
            'q_s':      int(r['q_s']),
            'phys_s':   int(r['phys_s']),
            'total':    int(r['total']),
            'sell_low': float(r['sell_low']),
            'buy_high': float(r['buy_high']),
            'buy_low':  float(r['buy_low']),
            'q_data':   {k: (float(v) if isinstance(v, (int, float, np.integer, np.floating)) else str(v))
                         for k, v in r['q_data'].items()},
        }
    with open(_cache_path(today_str), 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def restore_from_cache(code, cache):
    from datetime import date as _date
    c = dict(cache[code])
    c['as_of'] = _date.fromisoformat(c['as_of'])
    c['mom']   = 0.0   # 物理引擎動量，僅 display 用，cache 不儲存
    c['code']  = code  # cache JSON 以 code 為 key，value 本身不含 code，補回
    return c


def update_trades_md(content, r, new_row, today_str, dy_str=None):
    """更新 trades/ MD：現價欄 + MA 欄 + Wave Score 表"""
    updated = content

    # 現價
    updated = re.sub(
        r'(\*\*目前價格\*\*:\s*)[\d,\.]+\s*元\s*\(\d{4}-\d{2}-\d{2}\)',
        lambda m: f'{m.group(1)}{r["current"]:,.2f} 元 ({today_str})',
        updated
    )
    updated = re.sub(
        r'(\*\*目前價格\*\*:\s*)\(待更新\)',
        f'\\g<1>{r["current"]:,.2f} 元 ({today_str})',
        updated
    )

    # MA20
    updated = re.sub(
        r'(\*\*月線 \(20MA\) 位置\*\*:\s*)[\d,\.]+\s*元(?:\s*\(\d{4}-\d{2}-\d{2}\))?',
        lambda m: f'{m.group(1)}{r["ma20"]:,.2f} 元 ({today_str})',
        updated
    )
    updated = re.sub(
        r'(\*\*月線 \(20MA\) 位置\*\*:\s*)\(待更新\)',
        f'\\g<1>{r["ma20"]:,.2f} 元 ({today_str})',
        updated
    )

    # 殖利率（健診數據，選填）
    if dy_str:
        updated = re.sub(
            r'(\*\*預估殖利率\*\*:\s*)[\d\.]+%',
            f'\\g<1>{dy_str}',
            updated
        )
        updated = re.sub(
            r'(\*\*預估殖利率\*\*:\s*)\(待更新\)',
            f'\\g<1>{dy_str}',
            updated
        )

    # Wave Score 表
    if already_recorded_today(updated, today_str):
        return updated

    if 'Wave Score 歷史紀錄' not in updated:
        anchor = '## 停損預警區'
        if anchor not in updated:
            anchor = '## AI 客觀評估'
        if anchor in updated:
            updated = updated.replace(
                anchor,
                WAVE_TABLE_HEADER + new_row + '\n\n---\n\n' + anchor,
                1
            )
        else:
            updated += WAVE_TABLE_HEADER + new_row + '\n'
    else:
        lines = updated.splitlines()
        last_idx, in_table = -1, False
        for i, line in enumerate(lines):
            if '| 日期 |' in line and '總分' in line:
                in_table = True
            if in_table and line.strip().startswith('|') and '---' not in line and '| 日期 |' not in line:
                last_idx = i
            elif in_table and last_idx >= 0 and not line.strip().startswith('|'):
                break
        if last_idx >= 0:
            lines.insert(last_idx + 1, new_row)
            updated = '\n'.join(lines)

    return updated


# ── 戰術指南.md 更新 ──────────────────────────────────────────────────────────

def build_wave_section(today_str, results, action_items):
    """建立要寫入戰術指南.md 的 Wave Score 區塊"""

    p0 = [(c, n, r, a) for c, n, r, a in action_items if any(x[0] == 0 for x in a)]
    p1 = [(c, n, r, a) for c, n, r, a in action_items
          if not any(x[0] == 0 for x in a) and any(x[0] == 1 for x in a)]
    p2 = [(c, n, r, a) for c, n, r, a in action_items if all(x[0] == 2 for x in a)]

    lines = [
        f'{WAVE_SECTION_MARKER} ({today_str} 自動更新)',
        '',
        '> `wave_score_scan.py` 每日收盤後覆寫此區塊。P0 / P1 / P2 / 執行紀錄由人工維護。',
        '',
    ]

    def section(title, items, priority):
        if not items:
            return []
        out = [f'### {title}', '',
               '| 代號 | 名稱 | 現價 | Wave | 訊號 |',
               '|------|------|------|------|------|']
        for c, n, r, a in items:
            for pri, tag, msg in a:
                if pri == priority:
                    out.append(f'| {c} | {n} | {r["current"]:.1f} | {r["total"]:+d} | {tag}：{msg} |')
        return out + ['']

    lines += section('🔴 需即時處理（動能背離 / 波段破壞）', p0, 0)
    lines += section('🟢 加碼機會', p1, 1)
    lines += section('🟡 觀察', p2, 2)

    # Wave Score 總覽表
    lines += [
        '### 📈 Wave Score 總覽',
        '',
        '| 代號 | 名稱 | 現價 | MA20 | MA | GBM | 分位 | 物理 | Wave | 建議 |',
        '|------|------|------|------|----|----|------|------|------|------|',
    ]
    for r in sorted(results, key=lambda x: x['total'], reverse=True):
        icon = '🟢' if r['total'] >= 1 else ('🔴' if r['total'] <= -2 else '🟡')
        lines.append(
            f'| {r["code"]} | {r["name"]} | {r["current"]:.1f} | {r["ma20"]:.1f} | '
            f'{r["ma_s"]:+d} | {r["gbm_s"]:+d} | {r["q_s"]:+d} | {r["phys_s"]:+d} | '
            f'{icon} **{r["total"]:+d}** | {r["rec"]} |'
        )
    lines.append('')

    return '\n'.join(lines)


def update_tactical_md(today_str, results, action_items, dry_run=False):
    """覆寫戰術指南.md 末尾的 Wave Score 區塊"""
    if not os.path.exists(TACTICAL_MD):
        print(f'  ⚠️  找不到 {TACTICAL_MD}，跳過')
        return

    with open(TACTICAL_MD, 'r', encoding='utf-8') as f:
        content = f.read()

    new_section = build_wave_section(today_str, results, action_items)

    # 找到舊區塊並截斷，或直接追加
    marker_idx = content.find(WAVE_SECTION_MARKER)
    if marker_idx >= 0:
        # 保留 marker 之前的內容（含前一個 --- 分隔線）
        before = content[:marker_idx].rstrip()
        # 確保有分隔線
        if not before.endswith('---'):
            before = before.rstrip('\n') + '\n\n---\n'
        updated = before + '\n\n' + new_section
    else:
        updated = content.rstrip('\n') + '\n\n---\n\n' + new_section

    if not dry_run:
        with open(TACTICAL_MD, 'w', encoding='utf-8') as f:
            f.write(updated)
        print(f'  ✅ 戰術指南.md Wave Score 區塊已更新')
    else:
        print(f'  [dry-run] 戰術指南.md 會新增 {len(new_section.splitlines())} 行 Wave Score 區塊')


# ── 主程式 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='每日 Wave Score 掃描')
    parser.add_argument('--dry-run', action='store_true', help='僅顯示，不寫入')
    parser.add_argument('--period', default='1y')
    args = parser.parse_args()

    today_str  = str(date.today())
    ticker_map = load_ticker_map()
    stocks     = find_growth_stocks()
    dy_map     = load_checkup_dy(today_str)

    print(f'\n{"=" * 60}')
    print(f'  Wave Score 掃描  [{today_str}]  共 {len(stocks)} 檔成長趨勢股')
    if args.dry_run:
        print('  ⚠️  Dry-run 模式，不寫入任何檔案')
    print(f'{"=" * 60}')

    cache      = load_wave_cache(today_str)
    from_cache = cache is not None
    if from_cache:
        print(f'  📦 載入快取 {_cache_path(today_str)}（跳過 yfinance 抓取）')

    results, action_items, failed, raw_results = [], [], [], []

    for code, fpath, name in stocks:
        ticker = ticker_map.get(code, f'{code}.TW')
        print(f'\n  [{code} {name}]', end='  ', flush=True)

        if from_cache and code in cache:
            r = restore_from_cache(code, cache)
            print('(快取)', end='  ', flush=True)
        else:
            r = analyze(code, ticker, args.period)
        if r is None:
            print('❌ 資料取得失敗')
            failed.append(f'{code} {name}')
            continue
        raw_results.append(r)

        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        last  = get_last_wave_score(content)
        rec   = rec_label(r['total'])
        chg   = f' (from {last:+d})' if last is not None and last != r['total'] else ''
        print(f'Wave {r["total"]:+d}{chg}  {rec}')

        new_row = make_wave_row(r, today_str)
        actions = detect_actions(r, last)
        if actions:
            action_items.append((code, name, r, actions))

        results.append({**r, 'name': name, 'last': last, 'rec': rec})

        if not args.dry_run:
            dy_str      = dy_map.get(code)
            new_content = update_trades_md(content, r, new_row, today_str, dy_str)
            if new_content != content:
                with open(fpath, 'w', encoding='utf-8') as f:
                    f.write(new_content)

    # ── 儲存 cache（盤後固定，僅在非 dry-run 且非從 cache 讀入時儲存）──────────
    if not args.dry_run and not from_cache and raw_results:
        save_wave_cache(today_str, raw_results)
        print(f'\n  💾 Wave Score 已快取至 {_cache_path(today_str)}')

    # ── 行動清單輸出（console）────────────────────────────────────────────────
    print(f'\n{"=" * 60}')
    p0 = [(c, n, r, a) for c, n, r, a in action_items if any(x[0] == 0 for x in a)]
    p1 = [(c, n, r, a) for c, n, r, a in action_items
          if not any(x[0] == 0 for x in a) and any(x[0] == 1 for x in a)]
    p2 = [(c, n, r, a) for c, n, r, a in action_items if all(x[0] == 2 for x in a)]

    if not action_items:
        print('  ✅ 今日無特殊行動')
    if p0:
        print('  🔴 需即時處理：')
        for c, n, r, a in p0:
            for pri, tag, msg in a:
                if pri == 0:
                    print(f'    {tag}  {c} {n}  現價 {r["current"]:.1f}  |  {msg}')
    if p1:
        print('  🟢 加碼機會：')
        for c, n, r, a in p1:
            for pri, tag, msg in a:
                if pri == 1:
                    print(f'    {tag}  {c} {n}  現價 {r["current"]:.1f}  |  {msg}')
    if p2:
        print('  🟡 觀察：')
        for c, n, r, a in p2:
            for pri, tag, msg in a:
                print(f'    {tag}  {c} {n}  現價 {r["current"]:.1f}  |  {msg}')

    # ── 更新戰術指南.md ───────────────────────────────────────────────────────
    print()
    update_tactical_md(today_str, results, action_items, dry_run=args.dry_run)

    if failed:
        print(f'\n  ⚠️  資料取得失敗：{", ".join(failed)}')
    print()


if __name__ == '__main__':
    main()
