"""
ma_breach_counter.py — 月線跌破連日計數器

用法：
  python scripts/ma_breach_counter.py --code 1210 --ma 20 --alert-days 3

每次執行：
  1. 抓取最新收盤價與 MA
  2. 判斷今日是否在 MA 下方
  3. 累計連跌天數（狀態存 scripts/_ma_breach_state.json）
  4. 達 alert-days 時輸出 ⚠️ 警示
"""

import os
import sys
import json
import argparse
import datetime
import warnings
import logging

warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
sys.stdout.reconfigure(encoding='utf-8')

from curl_cffi import requests as creq
import yfinance as yf

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_ma_breach_state.json')
STOCKS_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'stocks.csv')

_SESSION = creq.Session(verify=False, impersonate='chrome')


def resolve_ticker(code: str) -> str:
    """從 stocks.csv 取得完整 ticker（含交易所 suffix）。找不到則回傳空字串。"""
    try:
        import csv
        with open(STOCKS_CSV, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row['code'] == code:
                    return row['ticker']
    except Exception:
        pass
    return ''


def get_price_and_ma(code: str, ma_period: int):
    ticker = resolve_ticker(code)
    if not ticker:
        return None, None
    try:
        hist = yf.Ticker(ticker, session=_SESSION).history(period="3mo", auto_adjust=False)
        if hist is not None and not hist.empty:
            close = hist['Close'].dropna()
            price = float(close.iloc[-1])
            ma = float(close.rolling(ma_period, min_periods=1).mean().iloc[-1])
            return price, ma
    except Exception:
        pass
    return None, None


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--code', required=True)
    parser.add_argument('--ma', type=int, default=20)
    parser.add_argument('--alert-days', type=int, default=3)
    parser.add_argument('--name', default='')
    args = parser.parse_args()

    today = datetime.date.today().strftime('%Y-%m-%d')
    label = args.name or args.code

    price, ma = get_price_and_ma(args.code, args.ma)
    if price is None:
        print(f"{label}：無法取得市場資料")
        return

    state = load_state()
    key = f"{args.code}_ma{args.ma}"
    entry = state.get(key, {'count': 0, 'last_date': '', 'streak_start': ''})

    below = price < ma
    pct = (price / ma - 1) * 100

    if below:
        if entry['last_date'] != today:
            entry['count'] += 1
            if entry['count'] == 1:
                entry['streak_start'] = today
            entry['last_date'] = today
    else:
        entry['count'] = 0
        entry['streak_start'] = ''
        entry['last_date'] = today

    state[key] = entry
    save_state(state)

    status = f"{'🔴' if below else '🟢'} 現價 {price:.2f}，MA{args.ma} {ma:.2f}（{pct:+.1f}%）"
    if below:
        status += f"，月線下方連續第 **{entry['count']} 日**（自 {entry['streak_start']}）"
        if entry['count'] >= args.alert_days:
            status += f"\n⚠️ 已達 {args.alert_days} 日門檻 → 建議評估減碼"
    else:
        status += "，月線之上，無需動作"

    print(f"{label} MA{args.ma} 觀察：{status}")


if __name__ == '__main__':
    run()
