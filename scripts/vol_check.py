"""
vol_check.py — 個股成交量與波動分析

用法：
  python scripts/vol_check.py --ticker 2002 1503
  python scripts/vol_check.py --ticker 6488
  python scripts/vol_check.py --daily --ticker 6239 1215 6488
"""
import argparse
import csv
import os
import warnings
import logging
import time

import yfinance as yf
from curl_cffi import requests as creq



warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOCKS_CSV = os.path.join(BASE_DIR, 'stocks.csv')
_CURL_SESSION = creq.Session(verify=False, impersonate='chrome')


def load_stock_map():
    try:
        with open(STOCKS_CSV, 'r', encoding='utf-8-sig', newline='') as f:
            return {
                row['code']: row
                for row in csv.DictReader(f)
                if row.get('code') and row.get('ticker')
            }
    except Exception:
        return {}


def resolve_stock(code, stock_map):
    row = stock_map.get(str(code), {})
    ticker = row.get('ticker') or f'{code}.TW'
    name = row.get('name') or ''
    return ticker, name


def fetch_hist(ticker, period='3mo', retries=3, delay=5):
    for attempt in range(retries):
        try:
            h = yf.Ticker(ticker, session=_CURL_SESSION).history(period=period, auto_adjust=False)
            if h is not None and not h.empty:
                h.columns = [c.title() for c in h.columns]
                return h.dropna()
        except Exception:
            pass
        if attempt < retries - 1:
            time.sleep(delay)
    return None


def volume_label(ratio):
    if ratio is None:
        return '⚪ 量能未知'
    if ratio < 0.8:
        return '🔵 縮量'
    if ratio >= 1.5:
        return '🔴 爆量'
    return '⚪ 平量'


def fmt_ratio(value):
    return 'N/A' if value is None else f'{value:.2f}x'


def analyze(code, stock_map, period='3mo'):
    ticker, name = resolve_stock(code, stock_map)
    hist = fetch_hist(ticker, period=period)
    if hist is None or hist.empty:
        print(f'{code}: 無法取得資料（ticker={ticker}）\n')
        return

    avg_vol   = hist['Volume'].mean()
    avg_price = hist['Close'].mean()
    hi        = hist['Close'].max()
    lo        = hist['Close'].min()
    swing     = (hi - lo) / lo * 100

    label = f'{code} {name}' if name else code
    print(f'{label} [{ticker}]:')
    print(f'  日均成交量：{avg_vol:>12,.0f} 股  ({avg_vol/1000:.0f} 千股)')
    print(f'  日均成交值：{avg_vol * avg_price / 1e8:>10.2f} 億元')
    print(f'  近3月最高：{hi:.2f}  最低：{lo:.2f}  波動幅度：{swing:.1f}%')
    print()


def analyze_daily(code, stock_map, period='2mo'):
    ticker, name = resolve_stock(code, stock_map)
    hist = fetch_hist(ticker, period=period)
    if hist is None or hist.empty or 'Volume' not in hist:
        print(f'{code}: 無法取得資料（ticker={ticker}）\n')
        return

    volume = hist['Volume'].dropna()
    close = hist['Close'].dropna()
    if len(volume) < 2 or close.empty:
        print(f'{code}: 成交量資料不足（ticker={ticker}）\n')
        return

    as_of = volume.index[-1].date()
    today_vol = float(volume.iloc[-1])
    prev = volume.iloc[:-1]
    avg5 = float(prev.tail(5).mean()) if len(prev) else None
    avg20 = float(prev.tail(20).mean()) if len(prev) else None
    ratio5 = today_vol / avg5 if avg5 else None
    ratio20 = today_vol / avg20 if avg20 else None
    current = float(close.iloc[-1])

    label = f'{code} {name}' if name else code
    print(f'{label} [{ticker}]（{as_of}）:')
    print(f'  收盤價：  {current:>12,.2f} 元')
    print(f'  今日量：  {today_vol:>12,.0f} 股  ({today_vol/1000:.0f} 千股)')
    print(f'  5日均量： {avg5:>12,.0f} 股  ({avg5/1000:.0f} 千股)' if avg5 else '  5日均量： N/A')
    print(f'  量比：    {fmt_ratio(ratio5):>12} → {volume_label(ratio5)}')
    print(f'  20日均量：{avg20:>12,.0f} 股  ({avg20/1000:.0f} 千股)' if avg20 else '  20日均量：N/A')
    print(f'  長量比：  {fmt_ratio(ratio20):>12}')
    print()


def main():
    parser = argparse.ArgumentParser(description='個股成交量與波動分析')
    parser.add_argument('--ticker', nargs='+', required=True,
                        metavar='CODE', help='股票代號，可一次輸入多個（如 2002 1503）')
    parser.add_argument('--daily', action='store_true',
                        help='輸出今日量比：今日量 / 前5日均量，並附 20 日長量比')
    parser.add_argument('--period', default=None,
                        help='資料期間；靜態模式預設 3mo，daily 模式預設 2mo')
    args = parser.parse_args()
    stock_map = load_stock_map()
    period = args.period or ('2mo' if args.daily else '3mo')
    for code in args.ticker:
        if args.daily:
            analyze_daily(code, stock_map, period=period)
        else:
            analyze(code, stock_map, period=period)


if __name__ == '__main__':
    main()
