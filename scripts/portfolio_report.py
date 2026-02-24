"""
portfolio_report.py — 一鍵產生持倉健診報告
自動檢查所有 /trades 下的持股，比對現價 vs 月線、停損線後，
輸出一份乾淨的 Markdown 格式報告。
"""
import os
import re
import sys
import time
import warnings
import yfinance as yf
import pandas as pd
import datetime

warnings.filterwarnings('ignore')   # 抑制 yfinance 的 404 警告訊息

import logging
logging.disable(logging.CRITICAL)   # 抑制 yfinance HTTP 404 log 輸出

TRADES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'trades')


def get_tw_ticker(code, retries=3, delay=5):
    """Try both .TW and .TWO formats with retry; return (ticker, history)."""
    for suffix in ['.TW', '.TWO']:
        for attempt in range(retries):
            try:
                ticker = yf.Ticker(f"{code}{suffix}")
                hist = ticker.history(period="3mo", auto_adjust=False)
                if hist is not None and not hist.empty:
                    return ticker, hist
            except Exception:
                pass
            if attempt < retries - 1:
                time.sleep(delay)
    return None, None


def analyze(code, cost):
    ticker, hist = get_tw_ticker(code)
    if ticker is None:
        return None
    current_price = hist['Close'].iloc[-1]
    ma20 = hist['Close'].rolling(window=min(20, len(hist))).mean().iloc[-1]
    info = ticker.info
    dy = info.get('dividendYield')
    if dy and dy < 1.0:
        dy_str = f"{dy*100:.2f}%"
    elif dy:
        dy_str = f"{dy:.2f}%"
    else:
        dy_str = "N/A"
    loss_pct = (current_price - cost) / cost * 100
    alerts = []
    if current_price < ma20:
        alerts.append("跌破月線")
    if loss_pct <= -10:
        alerts.append(f"觸及-10%停損 ({loss_pct:.1f}%)")
    return {
        'price': current_price,
        'ma20': ma20,
        'dy': dy_str,
        'loss_pct': loss_pct,
        'alerts': alerts,
    }


def scan():
    rows_normal = []
    rows_alert = []

    for fname in sorted(os.listdir(TRADES_DIR)):
        if not fname.endswith('.md') or fname == 'template.md':
            continue
        fpath = os.path.join(TRADES_DIR, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        ticker_match = re.search(r'\[標的\].*?(\d{4,6})', content)
        cost_match   = re.search(r'買進(?:均)?價[^\d]*([\d,\.]+)', content)
        name_match   = re.search(r'\[標的\].*?\d{4,6}\s+(.+)', content)

        if not ticker_match or not cost_match:
            continue

        code = ticker_match.group(1)
        cost = float(cost_match.group(1).replace(',', ''))
        name = name_match.group(1).strip() if name_match else code

        result = analyze(code, cost)
        if result is None:
            rows_alert.append(f"| {code} | {name} | ❌ 無法取得資料 | — | — | — |")
            continue

        status = "⚠️ " + " / ".join(result['alerts']) if result['alerts'] else "✅ 正常"
        row = (
            f"| `{code}` | {name} "
            f"| {result['price']:.2f} "
            f"| {result['ma20']:.2f} "
            f"| {result['loss_pct']:+.1f}% "
            f"| {result['dy']} "
            f"| {status} |"
        )
        if result['alerts']:
            rows_alert.append(row)
        else:
            rows_normal.append(row)

    today = datetime.date.today().strftime("%Y-%m-%d")
    header = (
        f"# 📊 持倉健診報告 ({today})\n\n"
        f"## ⚠️ 需要注意的標的\n"
        "| 代碼 | 名稱 | 現價 | 20MA | 損益% | 殖利率 | 狀態 |\n"
        "|------|------|------|------|-------|--------|------|\n"
    )
    alert_section = "\n".join(rows_alert) if rows_alert else "| — | 目前無預警標的 | — | — | — | — | — |"
    normal_section_header = (
        "\n\n## ✅ 正常持倉\n"
        "| 代碼 | 名稱 | 現價 | 20MA | 損益% | 殖利率 | 狀態 |\n"
        "|------|------|------|------|-------|--------|------|\n"
    )
    normal_section = "\n".join(rows_normal)
    report = header + alert_section + normal_section_header + normal_section
    out_path = os.path.join(TRADES_DIR, '..', f'持倉健診_{today}.md')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"報告已產生：{os.path.abspath(out_path)}")
    print(report)


if __name__ == '__main__':
    scan()
