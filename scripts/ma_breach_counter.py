"""
ma_breach_counter.py — 月線跌破連日計數器（v2：資料驅動，無狀態檔）
================================================================
從 yfinance 歷史日線直接計算收盤連續低於 MA 的天數，
不再依賴 _ma_breach_state.json。補跑安全，無儲存風險。

用法：
  python scripts/ma_breach_counter.py --code 1210 --ma 20 --alert-days 3
  python scripts/ma_breach_counter.py --code 1210 --ma 20 --alert-days 3 --json
"""

import os
import sys
import argparse
import datetime
import warnings
import logging

warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
sys.stdout.reconfigure(encoding='utf-8')

from curl_cffi import requests as creq
import yfinance as yf
import pandas as pd
import numpy as np

STOCKS_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'stocks.csv')
_SESSION = creq.Session(verify=False, impersonate='chrome')

try:
    from date_utils import resolve_review_date, slice_history_to_date
except ImportError:
    def resolve_review_date(cli_date=None):
        return cli_date or os.environ.get('REVIEW_DATE') or datetime.date.today().isoformat()

    def slice_history_to_date(hist, target_date):
        if hist is None or hist.empty:
            return hist
        cutoff = pd.Timestamp(target_date)
        idx = pd.to_datetime(hist.index)
        if hasattr(idx, 'tz') and idx.tz is not None:
            cutoff = cutoff.tz_localize(idx.tz)
        mask = idx <= cutoff
        if not mask.any():
            return hist.iloc[:0].copy()
        return hist.loc[mask].copy()


def resolve_ticker(code: str) -> str:
    try:
        import csv
        with open(STOCKS_CSV, 'r', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                if row['code'] == code:
                    return row['ticker']
    except Exception:
        pass
    return ''


def get_history(code: str, period='3mo'):
    ticker = resolve_ticker(code)
    if not ticker:
        return None
    try:
        hist = yf.Ticker(ticker, session=_SESSION).history(period=period, auto_adjust=False)
        if hist is not None and not hist.empty:
            hist.columns = [c.title() for c in hist.columns]
            return hist
    except Exception:
        pass
    return None


def compute_consecutive_breach(hist: pd.DataFrame, ma_period: int) -> dict:
    """從歷史資料直接計算連續跌破天數。回傳 {count, streak_start, below_today, price, ma}。"""
    if hist is None or hist.empty:
        return {'count': 0, 'streak_start': '', 'below_today': False, 'price': None, 'ma': None}

    closes = hist['Close'].dropna()
    if len(closes) < 2:
        return {'count': 0, 'streak_start': '', 'below_today': False, 'price': None, 'ma': None}

    ma_series = closes.rolling(ma_period, min_periods=ma_period).mean()
    valid_idx = ma_series.notna()
    closes_valid = closes[valid_idx]
    ma_valid = ma_series[valid_idx]

    if closes_valid.empty:
        return {'count': 0, 'streak_start': '', 'below_today': False, 'price': None, 'ma': None}

    price = float(closes_valid.iloc[-1])
    ma_val = float(ma_valid.iloc[-1])
    below_today = price < ma_val

    count = 0
    streak_start = ''
    for i in range(len(closes_valid) - 1, -1, -1):
        c = float(closes_valid.iloc[i])
        m = float(ma_valid.iloc[i])
        if c < m:
            count += 1
            streak_start = closes_valid.index[i].strftime('%Y-%m-%d')
        else:
            break

    return {
        'count': count,
        'streak_start': streak_start,
        'below_today': below_today,
        'price': price,
        'ma': ma_val,
    }


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--code', required=True)
    parser.add_argument('--ma', type=int, default=20)
    parser.add_argument('--alert-days', type=int, default=3)
    parser.add_argument('--name', default='')
    parser.add_argument('--json', action='store_true', help='Output structured JSON for hook_runner')
    args = parser.parse_args()

    today = resolve_review_date()
    label = args.name or args.code

    hist = get_history(args.code, period='3mo')
    if hist is None or hist.empty:
        msg = f"{label}：無法取得市場資料"
        if args.json:
            from hook_output import HookResult, output
            result = HookResult(
                hook=f"ma-breach-{args.code}", timestamp=today,
                status="error", severity="high", error_message=msg,
            )
            output(result)
            return
        print(msg)
        return

    # 若指定了複查日期，切片到該日
    if os.environ.get('REVIEW_DATE'):
        hist = slice_history_to_date(hist, today)

    result = compute_consecutive_breach(hist, args.ma)
    price = result['price']
    ma_val = result['ma']
    count = result['count']
    below = result['below_today']
    streak_start = result['streak_start']

    if price is None:
        msg = f"{label}：無法計算 MA"
        if args.json:
            from hook_output import HookResult, output
            result = HookResult(
                hook=f"ma-breach-{args.code}", timestamp=today,
                status="error", severity="high", error_message=msg,
            )
            output(result)
            return
        print(msg)
        return

    pct = (price / ma_val - 1) * 100

    status = f"{'🔴' if below else '🟢'} 現價 {price:.2f}，MA{args.ma} {ma_val:.2f}（{pct:+.1f}%）"
    if below:
        status += f"，月線下方連續第 **{count} 日**（自 {streak_start}）"
        if count >= args.alert_days:
            status += f"\n⚠️ 已達 {args.alert_days} 日門檻 → 建議評估減碼"
    else:
        status += "，月線之上，無需動作"

    if args.json:
        from hook_output import HookResult, HookTarget, output

        hook_name = f"ma-breach-{args.code}"
        detail = {
            "breach_days": count if below else 0,
            "ma_period": args.ma,
            "ma20": round(ma_val, 2),
            "current_price": round(price, 2),
            "pct_from_ma": round(pct, 1),
            "ma20_recovered": not below and count == 0,
            "streak_start": streak_start,
        }
        if below and count >= args.alert_days:
            targets = [HookTarget(
                code=args.code, name=label, action="p1_observe",
                summary=f"月線下方連續第 {count} 日",
                detail=detail,
            )]
            result = HookResult(
                hook=hook_name, timestamp=today, status="alert",
                severity="high", targets=targets,
                lifecycle_event=None,
            )
        elif not below:
            result = HookResult(
                hook=hook_name, timestamp=today, status="ok",
                severity="low", lifecycle_event="auto_disable",
            )
        else:
            result = HookResult(
                hook=hook_name, timestamp=today, status="ok",
                severity="low",
                targets=[HookTarget(
                    code=args.code, name=label, action="no_action",
                    summary=f"月線下方第 {count} 日（未達 {args.alert_days} 日門檻）",
                    detail=detail,
                )],
            )
        output(result)
        return

    print(f"{label} MA{args.ma} 觀察：{status}")


if __name__ == '__main__':
    run()
