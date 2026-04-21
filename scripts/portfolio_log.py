"""
portfolio_log.py — 每日投資組合淨值記錄
每次執行會：
  1. 讀取 /trades 下所有 MD 檔（股數 × 現價 = 當日市值）
  2. 計算整體總市值、總成本、損益
  3. 若今天尚未記錄，追加一行至 portfolio_history.csv
  4. 印出最近 10 筆記錄，顯示淨值趨勢

用法：
  python scripts/portfolio_log.py
"""

import os
import re
import sys
import csv
import time
import warnings
import logging
import datetime
import yfinance as yf
from curl_cffi import requests as creq

warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)

_SESSION = creq.Session(verify=False, impersonate='chrome')

TRADES_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'trades')
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'portfolio_history.csv')
TODAY        = datetime.date.today().strftime("%Y-%m-%d")

FIELDNAMES = ['date', 'total_value', 'total_cost', 'total_pnl', 'total_pnl_pct']


# ── 重試工具 ──────────────────────────────────────────────────────────────────
def _fetch_hist(code, period="5d", retries=3, delay=5):
    """帶重試的 yfinance 歷史資料抓取（.TW → .TWO fallback）。"""
    for suffix in ['.TW', '.TWO']:
        for attempt in range(retries):
            try:
                h = yf.Ticker(f"{code}{suffix}", session=_SESSION).history(period=period, auto_adjust=False)
                if h is not None and not h.empty:
                    return h
            except Exception:
                pass
            if attempt < retries - 1:
                time.sleep(delay)
    return None


# ── 假日偵測 ──────────────────────────────────────────────────────────────────
def is_trading_day():
    """確認今天是否為台股交易日（以 0050 最新資料日期比對今天）。"""
    hist = _fetch_hist("0050", period="5d")
    if hist is None or hist.empty:
        return True   # 無法確認時，保守假設為交易日
    last_date = hist.index[-1].date()
    return last_date == datetime.date.today()


# ── 市場資料 ──────────────────────────────────────────────────────────────────
def get_price(code: str):
    hist = _fetch_hist(code, period="5d")
    if hist is not None and not hist.empty:
        return float(hist['Close'].dropna().iloc[-1])
    return None


# ── 解析 MD ──────────────────────────────────────────────────────────────────
def parse_trade_file(filepath: str):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    ticker_m = re.search(r'\[標的\].*?(\d{4,6})', content)
    shares_m = re.search(r'集保股數[^\d]*([\d,]+)', content)
    cost_m   = re.search(r'買進(?:均)?價[^\d]*([\d,\.]+)', content)
    name_m   = re.search(r'\[標的\].*?\d{4,6}\s+(.+)', content)

    if not (ticker_m and shares_m and cost_m):
        return None

    return {
        'code':   ticker_m.group(1),
        'name':   name_m.group(1).strip() if name_m else ticker_m.group(1),
        'shares': int(shares_m.group(1).replace(',', '')),
        'cost':   float(cost_m.group(1).replace(',', '')),
    }


# ── 主流程 ────────────────────────────────────────────────────────────────────
def load_history() -> list[dict]:
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, 'r', encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def append_record(record: dict):
    file_exists = os.path.exists(HISTORY_FILE)
    with open(HISTORY_FILE, 'a', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow(record)


def _row_val(row: dict) -> float:
    """相容新舊 CSV 格式，回傳市值欄位數值。"""
    for k in ('total_value', 'total_portfolio_value', 'total_stock_value'):
        if k in row and row[k]:
            return float(row[k])
    return 0.0


def print_trend(history: list[dict], new_record: dict):
    recent = (history + [new_record])[-10:]   # 最近 10 筆
    print(f"\n{'日期':<12} {'總市值':>14} {'損益':>10} {'損益%':>8}")
    print("-" * 50)
    for i, row in enumerate(recent):
        val    = int(_row_val(row))
        marker = " ← 今日" if i == len(recent) - 1 else ""
        # 新格式才有 total_pnl / total_pnl_pct
        if 'total_pnl' in row and row['total_pnl']:
            pnl = int(float(row['total_pnl']))
            pct = float(row['total_pnl_pct'])
            print(f"{row['date']:<12} {val:>14,} {pnl:>+10,}  {pct:>+6.2f}%{marker}")
        else:
            print(f"{row['date']:<12} {val:>14,}{'':>10}{'':>8}{marker}")

    # 若有 2 筆以上，顯示與上次的變化
    if len(recent) >= 2:
        prev_val = _row_val(recent[-2])
        curr_val = _row_val(recent[-1])
        delta    = curr_val - prev_val
        if prev_val:
            print(f"\n  vs 上次：{delta:+,.0f} 元  ({delta/prev_val*100:+.2f}%)")


def run():
    files = [f for f in sorted(os.listdir(TRADES_DIR))
             if f.endswith('.md') and f != 'template.md']

    holdings, errors = [], []
    print(f"解析 {len(files)} 個持股檔案...")

    for fname in files:
        parsed = parse_trade_file(os.path.join(TRADES_DIR, fname))
        if parsed is None:
            errors.append(fname)
            continue

        price = get_price(parsed['code'])
        if price is None:
            errors.append(f"{fname} (無法取得現價)")
            continue

        parsed['price']        = price
        parsed['market_value'] = parsed['shares'] * price
        parsed['book_cost']    = parsed['shares'] * parsed['cost']
        holdings.append(parsed)

    # ── 假日偵測：非交易日不寫入 CSV ──────────────────────────────────────────
    if not is_trading_day():
        print(f"  今天（{TODAY}）非台股交易日，略過 CSV 記錄。")
        return

    total_files = len(files)
    incomplete = len(errors) > 0

    if errors:
        print(f"  警告：跳過 {len(errors)} 檔（共 {total_files} 檔）：{', '.join(errors)}")

    if not holdings:
        print("無法取得任何持股資料，中止。")
        return

    total_value = sum(h['market_value'] for h in holdings)
    total_cost  = sum(h['book_cost']    for h in holdings)
    total_pnl   = total_value - total_cost
    pnl_pct     = total_pnl / total_cost * 100 if total_cost else 0

    completeness = f"{len(holdings)}/{total_files} 檔"
    print(f"\n[{TODAY}] 結算完成（{completeness}{'，資料不完整' if incomplete else ''}）")
    print(f"  總市值：{total_value:>12,.0f} 元")
    print(f"  總成本：{total_cost:>12,.0f} 元")
    print(f"  總損益：{total_pnl:>+12,.0f} 元  ({pnl_pct:+.2f}%)")
    if incomplete:
        print(f"  ** 本次資料不完整，缺少 {len(errors)} 檔，數字偏低，不寫入歷史記錄 **")

    today_rec = {
        'date': TODAY,
        'total_value': f"{total_value:.0f}",
        'total_cost':  f"{total_cost:.0f}",
        'total_pnl':   f"{total_pnl:.0f}",
        'total_pnl_pct': f"{pnl_pct:.4f}",
    }

    # 資料不完整時不寫入，避免污染歷史記錄
    if incomplete:
        return

    history = load_history()
    if history and history[-1]['date'] == TODAY:
        print(f"\n  今日已有記錄（{TODAY}），不重複寫入。")
        print_trend(history[:-1], history[-1])
    else:
        append_record(today_rec)
        print(f"  已寫入 portfolio_history.csv")
        print_trend(history, today_rec)


if __name__ == '__main__':
    run()
