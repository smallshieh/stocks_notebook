"""
vol_check.py — 個股成交量與波動分析

用法：
  python scripts/vol_check.py --ticker 2002 1503
  python scripts/vol_check.py --ticker 6488
"""
import sys
import argparse
import warnings
import logging
import time
import yfinance as yf

sys.stdout.reconfigure(encoding='utf-8')

warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)


def fetch_hist(code, period='3mo', retries=3, delay=5):
    for suffix in ['.TW', '.TWO']:
        for attempt in range(retries):
            try:
                h = yf.Ticker(f"{code}{suffix}").history(period=period)
                if h is not None and not h.empty:
                    return h
            except Exception:
                pass
            if attempt < retries - 1:
                time.sleep(delay)
    return None


def analyze(code):
    hist = fetch_hist(code)
    if hist is None or hist.empty:
        print(f'{code}: 無法取得資料\n')
        return

    avg_vol   = hist['Volume'].mean()
    avg_price = hist['Close'].mean()
    hi        = hist['Close'].max()
    lo        = hist['Close'].min()
    swing     = (hi - lo) / lo * 100

    print(f'{code}:')
    print(f'  日均成交量：{avg_vol:>12,.0f} 股  ({avg_vol/1000:.0f} 千股)')
    print(f'  日均成交值：{avg_vol * avg_price / 1e8:>10.2f} 億元')
    print(f'  近3月最高：{hi:.2f}  最低：{lo:.2f}  波動幅度：{swing:.1f}%')
    print()


def main():
    parser = argparse.ArgumentParser(description='個股成交量與波動分析')
    parser.add_argument('--ticker', nargs='+', required=True,
                        metavar='CODE', help='股票代號，可一次輸入多個（如 2002 1503）')
    args = parser.parse_args()
    for code in args.ticker:
        analyze(code)


if __name__ == '__main__':
    main()
