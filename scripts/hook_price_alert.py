"""
hook_price_alert.py — Price target and hard-stop alert.
========================================================
Monitors a stock's current price against specified targets and hard-stop.

Usage:
    python scripts/hook_price_alert.py --code 2002 --targets 20.5,21.0,21.5 --hard-stop 17.5
    python scripts/hook_price_alert.py --code 2002 --targets 20.5,21.0,21.5 --hard-stop 17.5 --json
"""

import argparse
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

import warnings
import logging
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)

from curl_cffi import requests as creq
import yfinance as yf

SESSION = creq.Session(verify=False, impersonate='chrome')


def resolve_ticker(code: str) -> str:
    import csv
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'stocks.csv')
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row['code'] == code:
                    return row['ticker']
    except Exception:
        pass
    return f'{code}.TW'


def get_price(code: str) -> float | None:
    ticker = resolve_ticker(code)
    try:
        df = yf.Ticker(ticker, session=SESSION).history(period='5d')
        if df is not None and not df.empty:
            return float(df['Close'].dropna().iloc[-1])
    except Exception:
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description='Price target and hard-stop alert')
    parser.add_argument('--code', required=True)
    parser.add_argument('--targets', required=True, help='Comma-separated price targets')
    parser.add_argument('--hard-stop', type=float, required=True)
    parser.add_argument('--json', action='store_true', help='Output structured JSON for hook_runner')
    args = parser.parse_args()

    try:
        targets = [float(x.strip()) for x in args.targets.split(',')]
    except ValueError:
        print(f"ERROR: invalid targets format: {args.targets}", file=sys.stderr)
        sys.exit(1)

    price = get_price(args.code)
    if price is None:
        msg = f"中鋼 ({args.code})：無法取得市場資料"
        if args.json:
            from hook_output import HookResult, output, today_str
            result = HookResult(
                hook=f"price-alert-{args.code}", timestamp=today_str(),
                status="error", severity="high", error_message=msg,
            )
            output(result)
            return
        print(msg)
        return

    closest = None
    closest_gap = float('inf')
    for t in targets:
        if price >= t:
            closest = t
            closest_gap = 0
            break
        gap = (t / price - 1) * 100
        if gap < closest_gap:
            closest_gap = gap
            closest = t

    hard_stop_gap = (price / args.hard_stop - 1) * 100
    near_hard_stop = 0 <= hard_stop_gap < 5

    label = f"中鋼 ({args.code})"
    detail = {
        "current_price": round(price, 2),
        "targets": targets,
        "hard_stop": args.hard_stop,
        "closest_target": closest,
        "closest_target_gap_pct": round(closest_gap, 1),
        "hard_stop_gap_pct": round(hard_stop_gap, 1),
        "near_hard_stop": near_hard_stop,
    }

    if price >= min(targets):
        summary = f"現價 {price:.2f} ≥ {closest}，反彈賣點觸發"
        severity = "high"
        status = "alert"
        action = "p1_upgrade"
    elif near_hard_stop:
        summary = f"距硬止損 {args.hard_stop} 僅 {hard_stop_gap:.1f}%"
        severity = "high"
        status = "alert"
        action = "p1_upgrade"
    elif closest_gap < 5:
        summary = f"距最近目標 {closest} 僅 {closest_gap:.1f}%"
        severity = "medium"
        status = "warning"
        action = "p2_observe"
    else:
        summary = f"現價 {price:.2f}，最近目標 {closest}（距 {closest_gap:.1f}%）"
        severity = "low"
        status = "ok"
        action = "no_action"

    if args.json:
        from hook_output import HookResult, HookTarget, output, today_str
        targets_list = [HookTarget(
            code=args.code, name=label, action=action,
            summary=summary, detail=detail,
        )] if status != "ok" else []
        result = HookResult(
            hook=f"price-alert-{args.code}", timestamp=today_str(),
            status=status, severity=severity, targets=targets_list,
        )
        output(result)
        return

    print(f"{label}：{summary}")
    if price >= min(targets):
        print(f"  賣出 {1000 if closest <= 20.5 else (1000 if closest <= 21.0 else 1100)} 股 @市價")


if __name__ == '__main__':
    main()
