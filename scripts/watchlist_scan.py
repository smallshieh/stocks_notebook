"""
watchlist_scan.py — 候補股自動掃描
每次執行會：
  1. 讀取 /watchlist 下所有 MD 檔
  2. 抓取現價、20MA（月線）、60MA（季線）
  3. 評估可量化的買入觸發條件
  4. 若今天尚未記錄，自動在 MD 的「每月更新紀錄」新增一行
  5. 輸出總覽報告

用法：
  python scripts/watchlist_scan.py
"""

import os
import re
import sys
import time
import datetime
import yfinance as yf
import pandas as pd
from curl_cffi import requests as creq

_CURL_SESSION = creq.Session(verify=False, impersonate='chrome')

import warnings, logging
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)

WATCHLIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'watchlist')
TODAY = datetime.date.today().strftime("%Y-%m-%d")

# ── 可量化的觸發條件定義 ──────────────────────────────────────────────────────
# 每個條件是一個 lambda，接收 (price, ma20, ma60)，回傳 (bool觸發, str說明)
QUANT_TRIGGERS = [
    (
        "股價回測月線支撐",
        lambda p, m20, m60: (
            1.0 <= p / m20 <= 1.03,
            f"現價 {p:.1f} 距月線 {m20:.1f} 僅 {(p/m20-1)*100:.1f}%（月線回測中）"
        )
    ),
    (
        "股價跌至月線下方",
        lambda p, m20, m60: (
            p < m20,
            f"現價 {p:.1f} 跌破月線 {m20:.1f}（需觀察是否企穩）"
        )
    ),
    (
        "股價突破季線",
        lambda p, m20, m60: (
            p > m60,
            f"現價 {p:.1f} 站上季線 {m60:.1f}（+{(p/m60-1)*100:.1f}%）"
        )
    ),
    (
        "股價跌近季線支撐",
        lambda p, m20, m60: (
            1.0 <= p / m60 <= 1.05,
            f"現價 {p:.1f} 距季線 {m60:.1f} 僅 {(p/m60-1)*100:.1f}%（季線回測）"
        )
    ),
]


def get_market_data(code: str, retries=3, delay=5):
    """取得現價、20MA、60MA；TW/TWO 自動切換，含重試。"""
    for suffix in ['.TW', '.TWO']:
        for attempt in range(retries):
            try:
                hist = yf.Ticker(f"{code}{suffix}", session=_CURL_SESSION).history(period="6mo", auto_adjust=False)
                if hist is not None and not hist.empty:
                    close = hist['Close'].dropna()
                    price = float(close.iloc[-1])
                    ma20  = float(close.rolling(20, min_periods=1).mean().iloc[-1])
                    ma60  = float(close.rolling(60, min_periods=1).mean().iloc[-1])
                    return price, ma20, ma60
            except Exception:
                pass
            if attempt < retries - 1:
                time.sleep(delay)
    return None, None, None


def evaluate_triggers(price, ma20, ma60):
    """跑所有可量化條件，回傳觸發清單。"""
    fired = []
    for name, fn in QUANT_TRIGGERS:
        triggered, detail = fn(price, ma20, ma60)
        if triggered:
            fired.append(f"{name}：{detail}")
    return fired


def build_status_text(price, ma20, ma60, fired_triggers):
    """產生寫入 MD 的狀態更新文字。"""
    ma20_pct = (price / ma20 - 1) * 100
    ma60_pct = (price / ma60 - 1) * 100
    base = (f"現價 {price:.1f}，月線 {ma20:.1f}（{ma20_pct:+.1f}%），"
            f"季線 {ma60:.1f}（{ma60_pct:+.1f}%）")
    if fired_triggers:
        trigger_str = "；".join(fired_triggers)
        return f"{base}。⚡ 觸發：{trigger_str}"
    return f"{base}。無量化觸發訊號"


def append_today_record(filepath: str, price: float, ma20: float, ma60: float,
                        fired_triggers: list):
    """若今天尚未記錄，在 MD 的每月更新紀錄 table 末尾插入新行。"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 若今天已記錄則跳過
    if TODAY in content:
        return False

    status = build_status_text(price, ma20, ma60, fired_triggers)
    new_row = f"| {TODAY} | **{price:.2f}** 元 | {status} |"

    # 在「每月更新紀錄」表格的最後一行後面插入
    table_pattern = re.compile(
        r'(## 每月更新紀錄.*?(?:\n\|[^\n]+)+)',
        re.DOTALL
    )
    match = table_pattern.search(content)
    if match:
        updated = content[:match.end()] + '\n' + new_row + content[match.end():]
    else:
        # fallback：直接附加在檔尾
        updated = content.rstrip() + '\n' + new_row + '\n'

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(updated)
    return True


def scan():
    if not os.path.exists(WATCHLIST_DIR):
        print("watchlist 目錄不存在！")
        return

    files = [f for f in sorted(os.listdir(WATCHLIST_DIR))
             if f.endswith('.md') and f != 'template.md']
    if not files:
        print("watchlist 目錄內無追蹤標的。")
        return

    print(f"== Watchlist 掃描 {TODAY} ==\n")
    alert_stocks = []

    for fname in files:
        code_match = re.match(r'(\d{4,6})', fname)
        if not code_match:
            continue
        code = code_match.group(1)
        filepath = os.path.join(WATCHLIST_DIR, fname)

        # 讀取標的名稱
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        name_match = re.search(r'^#\s+(.+)', content, re.MULTILINE)
        name = name_match.group(1).strip() if name_match else fname

        print(f"[{code}] {name}")

        price, ma20, ma60 = get_market_data(code)
        if price is None:
            print(f"  無法取得市場資料，跳過。\n")
            continue

        ma20_pct = (price / ma20 - 1) * 100
        ma60_pct = (price / ma60 - 1) * 100
        print(f"  現價: {price:.2f}  |  月線(20MA): {ma20:.2f} ({ma20_pct:+.1f}%)  |  季線(60MA): {ma60:.2f} ({ma60_pct:+.1f}%)")

        fired = evaluate_triggers(price, ma20, ma60)
        if fired:
            print(f"  ⚡ 量化觸發：")
            for t in fired:
                print(f"     • {t}")
            alert_stocks.append((code, name, fired))
        else:
            print(f"  目前無量化觸發訊號")

        # 更新 MD
        updated = append_today_record(filepath, price, ma20, ma60, fired)
        print(f"  MD 更新：{'已新增今日紀錄' if updated else '今日已有紀錄，跳過'}\n")

    # 總覽
    print("=" * 50)
    if alert_stocks:
        print(f"!! 本次掃描共 {len(alert_stocks)} 檔觸發量化訊號，建議啟動研究：")
        for code, name, triggers in alert_stocks:
            print(f"  [{code}] {name}")
            for t in triggers:
                print(f"    -> {t}")
    else:
        print("本次掃描無量化觸發訊號，候補股持續觀察中。")
    print()
    print("注意：法人調升評等、外資加碼、供需報告等質化條件仍需人工確認。")


if __name__ == '__main__':
    scan()
