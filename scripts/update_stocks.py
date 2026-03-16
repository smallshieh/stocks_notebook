"""
update_stocks.py — stocks.csv 新增維護工具
==========================================
只新增，不刪除（除非手動處理下市標的）。

用法：
  # 新增單一標的（自動偵測上市/上櫃、抓取名稱）
  python scripts/update_stocks.py --code 2454

  # 指定市場與名稱（跳過自動查詢，速度更快）
  python scripts/update_stocks.py --code 2454 --market TWO --name 聯發科 --type 股票

  # 批次新增
  python scripts/update_stocks.py --code 2454,3481,4991

  # 僅顯示，不寫入（預覽）
  python scripts/update_stocks.py --code 2454 --dry-run
"""

import sys
import os
import argparse
import csv

sys.stdout.reconfigure(encoding='utf-8')

CSV_PATH = os.path.join(os.path.dirname(__file__), '..', 'stocks.csv')
FIELDNAMES = ['code', 'exchange', 'ticker', 'name', 'type']

# SSL 修正
try:
    import shutil, certifi
    os.makedirs('C:/Temp', exist_ok=True)
    shutil.copy2(certifi.where(), 'C:/Temp/cacert.pem')
except Exception:
    pass


def load_csv() -> dict:
    """讀取 stocks.csv，回傳 {code: row} dict"""
    if not os.path.exists(CSV_PATH):
        return {}
    with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        return {row['code']: row for row in reader}


def save_csv(records: dict):
    """將 records dict 寫回 stocks.csv（依 code 排序）"""
    with open(CSV_PATH, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for code in sorted(records.keys()):
            writer.writerow(records[code])


def detect_market(code: str) -> tuple[str, str, str]:
    """
    自動偵測上市/上櫃，並抓取股票名稱。
    回傳：(exchange, ticker, name)
    """
    try:
        from curl_cffi import requests as creq
        import yfinance as yf

        session = creq.Session(verify=False, impersonate='chrome')

        for suffix, exchange in [('.TWO', 'TWO'), ('.TW', 'TW')]:
            ticker_str = f'{code}{suffix}'
            try:
                t = yf.Ticker(ticker_str, session=session)
                h = t.history(period='5d')
                if h is not None and not h.empty:
                    # 取得名稱
                    try:
                        info = t.info
                        name = info.get('longName') or info.get('shortName') or '（待填）'
                        # 簡化名稱：去掉 Co., Ltd. 等英文後綴
                        for suffix_str in [' Co., Ltd.', ' Corp.', ' Inc.', ' Holdings']:
                            name = name.replace(suffix_str, '')
                        name = name.strip()
                    except Exception:
                        name = '（待填）'

                    return exchange, ticker_str, name
            except Exception:
                continue

    except ImportError:
        pass

    return 'TW', f'{code}.TW', '（待填）'


def add_stock(code: str, records: dict, market: str = 'auto',
              name: str = None, stock_type: str = '股票',
              dry_run: bool = False) -> bool:
    """
    新增單一標的至 records。
    回傳：True=已新增, False=已存在跳過
    """
    if code in records:
        print(f'  [{code}] 已存在 → {records[code]["ticker"]} ({records[code]["name"]})，跳過')
        return False

    if market == 'auto':
        print(f'  [{code}] 偵測市場中...', end=' ', flush=True)
        exchange, ticker, fetched_name = detect_market(code)
        final_name = name or fetched_name
        print(f'→ {exchange} ({ticker})')
    else:
        exchange = market
        ticker = f'{code}.{market}'
        final_name = name or '（待填）'

    row = {
        'code': code,
        'exchange': exchange,
        'ticker': ticker,
        'name': final_name,
        'type': stock_type,
    }

    if dry_run:
        print(f'  [預覽] {row}')
    else:
        records[code] = row
        print(f'  [{code}] ✅ 新增：{ticker} — {final_name}（{stock_type}）')

    return True


def main():
    parser = argparse.ArgumentParser(
        description='stocks.csv 新增維護工具（只新增，不刪除）',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--code', required=True,
                        help='股票代號，可用逗號分隔批次新增，如 2454,3481,4991')
    parser.add_argument('--market', default='auto', choices=['auto', 'TW', 'TWO'],
                        help='市場：auto=自動偵測（預設），TW=上市，TWO=上櫃')
    parser.add_argument('--name', default=None,
                        help='股票名稱（選填，若不填則自動抓取）')
    parser.add_argument('--type', default='股票',
                        help='類型：股票 / ETF（預設：股票）')
    parser.add_argument('--dry-run', action='store_true',
                        help='預覽模式，不寫入 CSV')
    args = parser.parse_args()

    records = load_csv()
    codes = [c.strip() for c in args.code.split(',') if c.strip()]

    print(f'=== stocks.csv 維護工具 ===')
    print(f'現有記錄：{len(records)} 筆\n')

    added = 0
    for code in codes:
        if add_stock(code, records, market=args.market,
                     name=args.name, stock_type=args.type,
                     dry_run=args.dry_run):
            added += 1

    print()
    if args.dry_run:
        print(f'[預覽模式] 共 {added} 筆將新增，未寫入。去掉 --dry-run 以正式執行。')
    else:
        if added > 0:
            save_csv(records)
            print(f'✅ 已新增 {added} 筆，stocks.csv 現有 {len(records)} 筆記錄')
        else:
            print('無新增，stocks.csv 未變動')


if __name__ == '__main__':
    main()
