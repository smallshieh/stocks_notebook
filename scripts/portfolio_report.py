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

TRADES_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'trades')

# ── 資金桶歸屬表 (依 capital/capital_config.md 定義) ──────────────────────────
# 不在表中的代碼預設歸 Tactical
CORE_CODES = {
    '0050', '0056', '00878', '00919', '00921', '00929', '00940', '00946', '009816',
    '1210', '1215', '2493', '2546', '2886', '6115', '6239', '8069',
}
TACTICAL_CODES = {
    '1503', '2002', '2317', '2330', '2357', '2376', '2377',
    '3034', '3231', '4938', '5483', '6488',
}

def get_bucket(code: str) -> str:
    if code in CORE_CODES:
        return 'Core'
    if code in TACTICAL_CODES:
        return 'Tactical'
    return 'Tactical'  # 預設


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
    rows_alert  = []
    bucket_values = {'Core': 0.0, 'Tactical': 0.0}  # 市值加總

    for fname in sorted(os.listdir(TRADES_DIR)):
        if not fname.endswith('.md') or fname == 'template.md':
            continue
        fpath = os.path.join(TRADES_DIR, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        ticker_match = re.search(r'\[標的\].*?(\d{4,6})', content)
        cost_match   = re.search(r'買進(?:均)?價[^\d]*([\d,\.]+)', content)
        shares_match = re.search(r'集保股數[^\d]*([\d,]+)', content)
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

        # 累計桶別市值
        if shares_match:
            shares = int(shares_match.group(1).replace(',', ''))
            market_val = shares * result['price']
            bucket = get_bucket(code)
            bucket_values[bucket] = bucket_values.get(bucket, 0.0) + market_val

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

    # ── 資金桶佔比摘要 ────────────────────────────────────────────────────────
    total_invested = sum(bucket_values.values())
    def pct(v): return v / total_invested * 100 if total_invested else 0

    core_pct     = pct(bucket_values.get('Core', 0))
    tactical_pct = pct(bucket_values.get('Tactical', 0))

    tactical_warn = ' ⚠️ 超出上限 (35%)' if tactical_pct > 35 else ''
    core_note    = ' 📌 偏高，長線防禦性強' if core_pct > 60 else ''

    bucket_section = (
        "\n\n## 💼 資金桶檢查 (依 capital/capital_config.md)\n"
        "| 桶別 | 市值 | 佔比 | 目標 | 狀態 |\n"
        "|------|------|------|------|------|\n"
        f"| Core（底倉水庫）| {bucket_values.get('Core',0):,.0f} | {core_pct:.1f}% | 50% | {'✅' if 40<=core_pct<=60 else '📌'}{core_note} |\n"
        f"| Tactical（戰術水管）| {bucket_values.get('Tactical',0):,.0f} | {tactical_pct:.1f}% | 30% | {'✅' if tactical_pct<=35 else '⚠️'}{tactical_warn} |\n"
        f"| Cash（銀彈消防栓）| （請手動填入）| — | 20% | — |\n"
        f"| **已投資合計** | **{total_invested:,.0f}** | 100% | | |\n"
    )
    if tactical_pct > 35:
        bucket_section = "\n> ⚠️ **資金越權警告**：Tactical 佔比超過 35% 上限！\n" + bucket_section

    today = datetime.date.today().strftime("%Y-%m-%d")
    header = (
        f"# 📊 持倉健診報告 ({today})\n\n"
        "## ⚠️ 需要注意的標的\n"
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
    report = header + alert_section + normal_section_header + normal_section + bucket_section
    out_path = os.path.join(TRADES_DIR, '..', f'持倉健診_{today}.md')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"報告已產生：{os.path.abspath(out_path)}")
    print(report)


if __name__ == '__main__':
    scan()
