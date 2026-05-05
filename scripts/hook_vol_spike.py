"""
hook_vol_spike.py — Volume spike + black candle detector.
==========================================================
Checks if a stock has today's volume >= vol_ratio * 5-day average AND close < open.

Usage:
    python scripts/hook_vol_spike.py --code 2454 --name 聯發科 --vol-ratio 1.5
    python scripts/hook_vol_spike.py --code 2454 --name 聯發科 --vol-ratio 1.5 --json
"""

import argparse
import os
import sys
from datetime import date

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

import warnings
import logging
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)

from curl_cffi import requests as creq
import yfinance as yf
import pandas as pd

SESSION = creq.Session(verify=False, impersonate='chrome')


def review_date() -> str:
    return os.environ.get('REVIEW_DATE') or date.today().isoformat()


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


def get_ohlcv(code: str) -> pd.DataFrame | None:
    ticker = resolve_ticker(code)
    try:
        df = yf.Ticker(ticker, session=SESSION).history(period='1mo')
        if df is not None and not df.empty:
            return df
    except Exception:
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description='Volume spike detector')
    parser.add_argument('--code', required=True)
    parser.add_argument('--name', default='')
    parser.add_argument('--vol-ratio', type=float, default=1.5)
    parser.add_argument('--json', action='store_true', help='Output structured JSON for hook_runner')
    args = parser.parse_args()

    label = args.name or args.code
    as_of = review_date()
    df = get_ohlcv(args.code)

    if df is None or df.empty:
        msg = f"{label}：無法取得市場資料"
        if args.json:
            from hook_output import HookResult, output
            result = HookResult(
                hook=f"vol-spike-{args.code}", timestamp=as_of,
                status="error", severity="high", error_message=msg,
            )
            output(result)
            return
        print(msg)
        return

    today_vol = float(df['Volume'].iloc[-1])
    today_open = float(df['Open'].iloc[-1])
    today_close = float(df['Close'].iloc[-1])
    avg5_vol = float(df['Volume'].tail(6).iloc[:-1].mean()) if len(df) >= 6 else float(df['Volume'].tail(5).mean())
    vol_ratio = today_vol / avg5_vol if avg5_vol else 0.0
    is_black = today_close < today_open
    spike_triggered = vol_ratio >= args.vol_ratio

    detail = {
        "current_price": round(today_close, 2),
        "open": round(today_open, 2),
        "today_volume": int(today_vol),
        "avg5_volume": round(avg5_vol, 0),
        "volume_ratio": round(vol_ratio, 2),
        "is_black_candle": is_black,
        "spike_threshold": args.vol_ratio,
    }

    if spike_triggered and is_black:
        summary = f"爆量 {vol_ratio:.1f}x + 收黑 K（{today_open:.0f}→{today_close:.0f}）"
        severity = "high"
        status = "alert"
        action = "p1_upgrade"
    elif spike_triggered:
        summary = f"爆量 {vol_ratio:.1f}x 但未收黑"
        severity = "medium"
        status = "warning"
        action = "p2_observe"
    elif is_black:
        summary = f"收黑 K（量比 {vol_ratio:.1f}x，未達 {args.vol_ratio}）"
        severity = "low"
        status = "warning"
        action = "p2_observe"
    else:
        summary = f"正常（量比 {vol_ratio:.1f}x，非黑K）"
        severity = "low"
        status = "ok"
        action = "no_action"

    if args.json:
        from hook_output import HookResult, HookTarget, output
        targets = [HookTarget(
            code=args.code, name=label, action=action,
            summary=summary, detail=detail,
        )] if status != "ok" else []
        result = HookResult(
            hook=f"vol-spike-{args.code}", timestamp=as_of,
            status=status, severity=severity, targets=targets,
        )
        output(result)
        return

    print(f"{label}：{summary}")
    if spike_triggered and is_black:
        print(f"  ⚠️  爆量收黑：量比 {vol_ratio:.1f}x ≥ {args.vol_ratio}，{today_open:.0f}→{today_close:.0f}，建議評估減持")


if __name__ == '__main__':
    main()
