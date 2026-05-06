"""
trades_defense_scan.py — 全持倉防守掃描
每次執行會：
  1. 掃描 trades/ 下所有 MD 檔，解析持倉資訊（成本、股數、硬停損）
  2. 取得現價，計算損益%、距停損%
  3. 計算 Wave Score（靜默模式）
  4. 對每個持倉輸出狀態，遇到防守訊號輸出 ⚠️ 關鍵字
  5. ETF 類（代號 5 碼含英文或 0 開頭）降級為「僅顯示損益，不計 Wave Score」

輸出格式供 daily-review step 13 解析：
  ⚠️ [code] name：{警示原因}

用法：
  python scripts/trades_defense_scan.py
  python scripts/trades_defense_scan.py --date 2026-05-04
"""

import os
import re
import sys
import time
import datetime
import yfinance as yf
import pandas as pd
import numpy as np
from curl_cffi import requests as creq

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from quantile_engine import compute_quantile_metrics
    from physics_engine import compute_physics, detect_antigravity, detect_energy_dissipation
    from signal_policy import (
        compute_volume_metrics,
        evaluate_signal,
        load_position_policies,
        load_signal_state,
        recent_entries,
        record_signal_state,
        resolve_review_date,
        save_signal_state,
    )
    _ENGINES_AVAILABLE = True
except ImportError:
    _ENGINES_AVAILABLE = False

_CURL_SESSION = creq.Session(verify=False, impersonate='chrome')

import warnings, logging
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)

TRADES_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'trades')
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
TODAY = resolve_review_date() if _ENGINES_AVAILABLE else datetime.date.today().strftime("%Y-%m-%d")

# ETF 判定：代號以 0 開頭，或含英文字母（00919, 009816, 0050 等）
def is_etf(code: str) -> bool:
    return code.startswith('0') or bool(re.search(r'[A-Za-z]', code))


def parse_trades_md(filepath: str) -> dict | None:
    """
    解析 trades MD，回傳：
    {code, name, cost, shares, stop_loss_price}
    解析失敗回傳 None。stop_loss_price 可為 None（找不到時）。
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    fname = os.path.basename(filepath)
    code_match = re.match(r'(\d[\dA-Za-z]{3,5})', fname)
    if not code_match:
        return None
    code = code_match.group(1)

    # 標的名稱
    name_match = re.search(r'^#\s+(\S+)\s+(?:交易紀錄|候補追蹤)?', content, re.MULTILINE)
    name = name_match.group(1) if name_match else fname

    # 買進均價（支援千分位逗號，支援多種格式）
    cost = None
    for pattern in [
        r'\*\*買進均價\*\*[：:]\s*\**\s*([\d,]+\.?\d*)\s*元',
        r'買進均價[：:]\s*([\d,]+\.?\d*)\s*元',
    ]:
        m = re.search(pattern, content)
        if m:
            cost = float(m.group(1).replace(',', ''))
            break

    # 集保股數（取第一個數字）
    shares = None
    for pattern in [
        r'\*\*集保股數\*\*[：:]\s*\**\s*([\d,]+)',
        r'集保股數[：:]\s*([\d,]+)',
    ]:
        m = re.search(pattern, content)
        if m:
            shares = int(m.group(1).replace(',', ''))
            break

    if cost is None or shares is None:
        return None

    # 硬停損（多種格式）
    stop_loss = None
    patterns = [
        r'硬停損[^\d\n]{0,10}([\d,]+\.?\d*)\s*元',   # 硬停損 | **200 元** 或 硬停損：195 元
        r'🔴\s*硬停損[^\d\n]{0,20}([\d,]+\.?\d*)\s*元',
        r'停損.*?([\d,]+\.?\d*)\s*元\b',
    ]
    for pat in patterns:
        m = re.search(pat, content)
        if m:
            candidate = float(m.group(1).replace(',', ''))
            # 排除明顯不合理的值（> 成本 * 2 或 < 成本 * 0.3）
            if cost and 0.3 <= candidate / cost <= 2.0:
                stop_loss = candidate
                break

    return {
        'code': code,
        'name': name,
        'cost': cost,
        'shares': shares,
        'stop_loss': stop_loss,
        'content': content,
    }


def get_market_data(code: str, retries=3, delay=5):
    """取得現價、20MA 及完整 hist；TW/TWO 自動切換。
    若 REVIEW_DATE env 已設定，自動將 history 切片到該日期。"""
    from date_utils import slice_history_to_date, resolve_review_date
    review = resolve_review_date()
    # 先從 stocks.csv 取 ticker
    stocks_csv = os.path.join(SCRIPTS_DIR, '..', 'stocks.csv')
    ticker_override = None
    try:
        import csv
        with open(stocks_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('code') == code:
                    ticker_override = row.get('ticker')
                    break
    except Exception:
        pass

    suffixes = [ticker_override] if ticker_override else [f'{code}.TW', f'{code}.TWO']
    for ticker in suffixes:
        for attempt in range(retries):
            try:
                hist = yf.Ticker(ticker, session=_CURL_SESSION).history(period="6mo", auto_adjust=False)
                if hist is not None and not hist.empty:
                    if review:
                        hist = slice_history_to_date(hist, review)
                    if hist is None or hist.empty:
                        continue
                    hist.columns = [c.title() for c in hist.columns]
                    close = hist['Close'].dropna()
                    price = float(close.iloc[-1])
                    ma20  = float(close.rolling(20, min_periods=1).mean().iloc[-1])
                    return price, ma20, hist
            except Exception:
                pass
            if attempt < retries - 1:
                time.sleep(delay)
    return None, None, None


def compute_wave_snapshot_silent(code: str, hist: pd.DataFrame) -> dict | None:
    """靜默計算 Wave 四維診斷資料，失敗回傳 None。"""
    if not _ENGINES_AVAILABLE:
        return None
    try:
        prices  = hist['Close'].dropna()
        current = float(prices.iloc[-1])

        ma5  = float(prices.tail(5).mean())
        ma10 = float(prices.tail(10).mean())
        ma20 = float(prices.tail(20).mean())
        ma60 = float(prices.tail(60).mean())
        ma_raw   = sum([current > ma5, ma5 > ma10, ma10 > ma20, ma20 > ma60])
        ma_score = ma_raw - 2

        log_returns = np.diff(np.log(prices.values))
        try:
            from arch import arch_model
            am  = arch_model(log_returns * 100, vol='Garch', p=1, o=0, q=1, dist='Normal')
            res = am.fit(disp='off')
            sigma = (res.conditional_volatility[-1] / 100) * np.sqrt(252)
        except Exception:
            sigma = float(np.std(log_returns, ddof=1)) * np.sqrt(252)
        mu_daily = float(np.mean(log_returns))
        mu = (mu_daily + 0.5 * (sigma / np.sqrt(252)) ** 2) * 252

        T   = 20 / 252
        E   = current * np.exp(mu * T)
        std = sigma * np.sqrt(T) * current
        if current < E - 0.5 * std:
            gbm_score = 2
        elif current <= E + 0.5 * std:
            gbm_score = 0
        elif current <= E + std:
            gbm_score = -1
        else:
            gbm_score = -2

        q = compute_quantile_metrics(hist)
        if current >= q['sell_low']:
            q_score = -2
        elif current >= q['buy_high']:
            q_score = 0
        elif current >= q['buy_low']:
            q_score = 2
        elif current >= q['deep_low']:
            q_score = 3
        else:
            q_score = -3

        phys_df   = compute_physics(hist)
        latest    = phys_df.iloc[-1]
        momentum  = latest.get('momentum', 0) or 0
        reynolds  = latest.get('reynolds', 0) or 0
        antigrav  = detect_antigravity(phys_df)
        ener_diss = detect_energy_dissipation(phys_df)
        phys_raw  = sum([momentum > 0, reynolds < 2000, not antigrav, not ener_diss])
        phys_score = phys_raw - 2

        volume = compute_volume_metrics(hist)
        return {
            'code': code,
            'current': current,
            'ma20': ma20,
            'ma_s': ma_score,
            'gbm_s': gbm_score,
            'q_s': q_score,
            'phys_s': phys_score,
            'total': ma_score + gbm_score + q_score + phys_score,
            **volume,
        }
    except Exception:
        return None


def scan():
    import argparse as _ap
    _parser = _ap.ArgumentParser()
    _parser.add_argument('--json', action='store_true', help='Output structured JSON for hook_runner')
    _args, _ = _parser.parse_known_args()
    use_json = _args.json

    if not os.path.exists(TRADES_DIR):
        print("trades 目錄不存在！")
        return

    files = sorted([
        f for f in os.listdir(TRADES_DIR)
        if f.endswith('.md') and f != 'template.md'
    ])
    if not files:
        print("trades 目錄內無持倉。")
        return

    print(f"== 持倉防守掃描 {TODAY} ==\n")
    alert_lines = []
    policies = load_position_policies() if _ENGINES_AVAILABLE else {}
    signal_state = load_signal_state() if _ENGINES_AVAILABLE else {"signals": {}}

    for fname in files:
        filepath = os.path.join(TRADES_DIR, fname)
        info = parse_trades_md(filepath)
        if info is None:
            continue

        code   = info['code']
        name   = info['name']
        cost   = info['cost']
        shares = info['shares']
        sl     = info['stop_loss']
        etf    = is_etf(code)

        price, ma20, hist = get_market_data(code)
        if price is None:
            print(f"  [{code}] {name}：無法取得市場資料，跳過")
            continue
        data_date = hist.index[-1].date().isoformat() if hist is not None and not hist.empty else ""
        if data_date and data_date < TODAY:
            print(f"  [{code}] {name}：市場資料日期 {data_date} < REVIEW_DATE {TODAY}，資料不足，跳過")
            continue

        pnl_pct = (price / cost - 1) * 100
        sl_gap  = ((price / sl - 1) * 100) if sl else None

        if etf:
            # ETF：只顯示損益，不計 Wave Score
            tag = "正常" if pnl_pct >= -5 else "⚠️ 損益偏低"
            line = (f"  [{code}] {name}（ETF）: 現價 {price:.2f} | "
                    f"損益 {pnl_pct:+.1f}% — {tag}")
            print(line)
            if pnl_pct <= -8:
                alert_lines.append(f"⚠️ [{code}] {name}（ETF）損益告急：{pnl_pct:+.1f}%，低於 -8% 警戒線")
            continue

        # 一般股：計算四維診斷，交由 signal_policy 決定是否升級為防守警示
        snapshot = compute_wave_snapshot_silent(code, hist) if hist is not None else None
        wave = snapshot['total'] if snapshot is not None else 0
        decision = None
        hard_stop_hit = sl_gap is not None and sl_gap < 0
        stop_near = sl_gap is not None and 0 <= sl_gap < 3
        if snapshot is not None:
            decision = evaluate_signal(
                snapshot,
                code=code,
                strategy_class=policies.get(code, {}).get('strategy_class'),
                policies=policies,
                trade_text=info.get('content', ''),
                history=recent_entries(signal_state, code),
                hard_stop_triggered=hard_stop_hit,
                stop_loss_near=stop_near,
            )
            record_signal_state(
                signal_state,
                code=code,
                as_of=TODAY,
                source='trades_defense_scan',
                metrics=snapshot,
                decision=decision,
            )

        alerts = []
        if hard_stop_hit:
            alerts.append(f"已跌破停損 {sl:.1f}（現價在停損下方 {abs(sl_gap):.1f}%）")
        elif stop_near:
            alerts.append(f"停損接近（距停損 {sl:.1f} 僅 {sl_gap:.1f}%）")
        if pnl_pct <= -8:
            alerts.append(f"損益告急（{pnl_pct:+.1f}%）")
        if decision and decision.action_group == 'defensive' and decision.action_tag != 'downside_hard_rule':
            alerts.append(f"{decision.recommendation}（{decision.reason}，品質 {decision.signal_quality_label}）")

        sl_info = f"停損 {sl:.0f}（{sl_gap:+.1f}%）" if sl_gap is not None else "停損未設"
        policy_info = (
            f"{decision.strategy_label} | {decision.recommendation} | {decision.signal_quality_label}"
            if decision else "訊號政策未取得"
        )

        if alerts:
            alert_str = "、".join(alerts)
            line = (f"  ⚠️ [{code}] {name}: 現價 {price:.2f} | Wave {wave:+d} | "
                    f"損益 {pnl_pct:+.1f}% | {sl_info} | {policy_info} — {alert_str}")
            alert_lines.append(
                f"⚠️ [{code}] {name}：{alert_str}"
                f"（現價 {price:.2f}，Wave摘要 {wave:+d}，損益 {pnl_pct:+.1f}%，{policy_info}）"
            )
        else:
            line = (f"  [{code}] {name}: 現價 {price:.2f} | Wave {wave:+d} | "
                    f"損益 {pnl_pct:+.1f}% | {sl_info} | {policy_info} — 正常")

        print(line)

    # ── 總覽 ─────────────────────────────────────────────
    print()
    print("=" * 50)
    if alert_lines:
        print(f"\n⚠️ 持倉防守警示 — 共 {len(alert_lines)} 項需注意：\n")
        for line in alert_lines:
            print(f"  {line}")
    else:
        print("本次掃描所有持倉均在正常範圍，無防守警示。")
    print()

    if use_json:
        from hook_output import HookResult, HookTarget, output, today_str

        targets = []
        for al in alert_lines:
            m = re.match(r'⚠️\s*\[(\d+)\]\s*(\S+)[：:](.*)', al)
            if m:
                code, name, desc = m.group(1), m.group(2), m.group(3).strip()
                action = "p1_upgrade" if ("停損接近" in desc or "損益告急" in desc or "跌破" in desc) else "p2_observe"
                targets.append(HookTarget(
                    code=code, name=name, action=action,
                    summary=desc[:60],
                    detail={"raw_alert": al},
                ))
            else:
                targets.append(HookTarget(
                    code="*", name="defense", action="no_action",
                    summary=al[:60], detail={"raw_alert": al},
                ))

        if targets:
            result = HookResult(
                hook="trades-defense-scan", timestamp=today_str(),
                status="alert", severity="medium", targets=targets,
            )
        else:
            result = HookResult(
                hook="trades-defense-scan", timestamp=today_str(),
                status="ok", severity="low",
            )
        output(result)

    if _ENGINES_AVAILABLE:
        save_signal_state(signal_state)


if __name__ == '__main__':
    scan()
