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
from curl_cffi import requests as creq
import yfinance as yf

_CURL_SESSION = creq.Session(verify=False, impersonate='chrome')
import pandas as pd
import datetime

warnings.filterwarnings('ignore')   # 抑制 yfinance 的 404 警告訊息

import logging
logging.disable(logging.CRITICAL)   # 抑制 yfinance HTTP 404 log 輸出

TRADES_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'trades')
BUDGET_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'capital', 'single_position_budget.md')

# ── 資金桶歸屬表 (依 capital/capital_config.md 定義) ──────────────────────────
# 不在表中的代碼預設歸 Tactical
CORE_CODES = {
    '0050', '0056', '00878', '00919', '00921', '00929', '00940', '00946', '009816',
    '1210', '1215', '2493', '2546', '2886', '6115', '6239', '8069',
}
TACTICAL_CODES = {
    '1503', '2002', '2317', '2330', '2357', '2376', '2377',
    '2379', '2382', '2454', '3034', '3231', '3455', '4938',
    '5483', '6488',
}

def get_bucket(code: str) -> str:
    if code in CORE_CODES:
        return 'Core'
    if code in TACTICAL_CODES:
        return 'Tactical'
    return 'Tactical'  # 預設


def parse_single_position_budget():
    """解析 capital/single_position_budget.md 的預算表。
    回傳 dict: {code: {'name', 'tier', 'basis', 'override', 'cap'}}。
    找不到檔案 / 無表格時回傳空 dict。"""
    if not os.path.exists(BUDGET_PATH):
        return {}
    try:
        with open(BUDGET_PATH, 'r', encoding='utf-8') as f:
            text = f.read()
    except Exception:
        return {}
    budgets = {}
    # 僅解析「## 📊 預算使用一覽」區段
    m = re.search(r'##\s*📊[^\n]*預算使用一覽[^\n]*\n(.*?)(?:\n##\s|\Z)', text, re.DOTALL)
    if not m:
        return {}
    block = m.group(1)
    for line in block.splitlines():
        # 跳過表頭 / 分隔線 / 空行 / 非表格行
        if not line.startswith('|'):
            continue
        if '---' in line:
            continue
        if '代碼' in line or '總計' in line:
            continue
        parts = [p.strip() for p in line.split('|')]
        # parts 第 0 / 末尾因首尾 | 會有空字串，有效欄位從 parts[1] 起
        if len(parts) < 10:
            continue
        code_cell = parts[1]
        if not re.match(r'^\d{4,6}$', code_cell):
            continue
        try:
            basis    = int(parts[4].replace(',', ''))
            override = int(parts[5].replace(',', ''))
            cap      = int(parts[6].replace(',', ''))
        except ValueError:
            continue
        budgets[code_cell] = {
            'name':     parts[2],
            'tier':     parts[3],
            'basis':    basis,
            'override': override,
            'cap':      cap,
        }
    return budgets


def get_tw_ticker(code, retries=3, delay=5):
    """Try both .TW and .TWO formats with retry; return (ticker, history)."""
    for suffix in ['.TW', '.TWO']:
        for attempt in range(retries):
            try:
                ticker = yf.Ticker(f"{code}{suffix}", session=_CURL_SESSION)
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
    bucket_values = {'Core': 0.0, 'Tactical': 0.0}  # 現價市值加總
    bucket_costs  = {'Core': 0.0, 'Tactical': 0.0}  # 成本基礎加總
    position_costs = {}  # {code: {'name', 'cost', 'bucket'}}  用於單檔預算檢查

    for fname in sorted(os.listdir(TRADES_DIR)):
        if not fname.endswith('.md') or fname == 'template.md':
            continue
        fpath = os.path.join(TRADES_DIR, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        ticker_match = re.search(r'\[標的\].*?(\d{4,6})', content)
        cost_match   = re.search(r'買進(?:均)?價[^\d]*([\d,\.]+)', content)
        shares_match = re.search(r'集保股數[^\d]*([\d,]+)', content)
        total_cost_match = re.search(r'總成本[^\d]*([\d,\.]+)', content)
        name_match   = re.search(r'\[標的\].*?\d{4,6}\s+(.+)', content)

        if not ticker_match or not cost_match:
            continue

        code = ticker_match.group(1)
        cost = float(cost_match.group(1).replace(',', ''))
        name = name_match.group(1).strip() if name_match else code

        # 跳過已全數出清的標的（shares=0）
        if shares_match:
            _shares_check = int(shares_match.group(1).replace(',', ''))
            if _shares_check == 0:
                continue

        result = analyze(code, cost)
        if result is None:
            rows_alert.append(f"| {code} | {name} | ❌ 無法取得資料 | — | — | — |")
            continue

        # 累計桶別市值 + 成本基礎
        if shares_match:
            shares = int(shares_match.group(1).replace(',', ''))
            market_val = shares * result['price']
            # 成本基礎：優先讀 `總成本` 欄位，fallback 為 股數 × 買進均價
            if total_cost_match:
                total_cost = float(total_cost_match.group(1).replace(',', ''))
            else:
                total_cost = shares * cost
            bucket = get_bucket(code)
            bucket_values[bucket] = bucket_values.get(bucket, 0.0) + market_val
            bucket_costs[bucket]  = bucket_costs.get(bucket, 0.0) + total_cost
            position_costs[code] = {'name': name, 'cost': total_cost, 'bucket': bucket}

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

    # ── 資金桶佔比摘要（雙口徑：現價 + 成本）────────────────────────────────
    total_invested = sum(bucket_values.values())
    total_cost_sum = sum(bucket_costs.values())

    def pct(v, base): return v / base * 100 if base else 0

    # 現價口徑（風險 / 曝險視角）
    core_val     = bucket_values.get('Core', 0)
    tact_val     = bucket_values.get('Tactical', 0)
    core_pct     = pct(core_val, total_invested)
    tactical_pct = pct(tact_val, total_invested)

    # 成本口徑（預算 / 投入視角）
    core_cost    = bucket_costs.get('Core', 0)
    tact_cost    = bucket_costs.get('Tactical', 0)
    core_cpct    = pct(core_cost, total_cost_sum)
    tact_cpct    = pct(tact_cost, total_cost_sum)

    # 帳面損益
    core_pnl     = core_val - core_cost
    tact_pnl     = tact_val - tact_cost
    core_pnl_pct = pct(core_pnl, core_cost)
    tact_pnl_pct = pct(tact_pnl, tact_cost)

    tactical_warn = ' ⚠️ 超出上限 (35%)' if tactical_pct > 35 else ''
    core_note    = ' 📌 偏高，長線防禦性強' if core_pct > 60 else ''

    # 提前讀取現金餘額（讓 bucket_section 可填入）
    _history_path_early = os.path.join(TRADES_DIR, '..', 'portfolio_history.csv')
    _cash_bal_early = None
    if os.path.exists(_history_path_early):
        import csv as _csv_e, io as _io_e
        with open(_history_path_early, 'r', encoding='utf-8') as _fe:
            _lines_e = _fe.readlines()
        for _le in reversed(_lines_e[1:]):
            _pe = _le.strip().split(',')
            if len(_pe) >= 3 and _pe[2]:
                try:
                    _c = float(_pe[2])
                    if _c > 0:
                        _cash_bal_early = _c
                        break
                except ValueError:
                    pass
    # argv 覆寫：--cash= 或 --cash-delta=
    for _arg in sys.argv[1:]:
        if _arg.startswith('--cash='):
            try: _cash_bal_early = float(_arg.split('=', 1)[1].replace(',', ''))
            except ValueError: pass
        elif _arg.startswith('--cash-delta='):
            try: _cash_bal_early = (_cash_bal_early or 0.0) + float(_arg.split('=', 1)[1].replace(',', ''))
            except ValueError: pass

    if _cash_bal_early is not None:
        _cash_str = f"{_cash_bal_early:,.0f}"
        _total_pv = total_invested + _cash_bal_early
        _cash_pct = _cash_bal_early / _total_pv * 100
        _cash_status = '🔴 嚴重不足' if _cash_pct < 10 else ('🟡 低配' if _cash_pct < 15 else ('✅' if _cash_pct <= 25 else '🟡 高配'))
        _cash_row = f"| Cash（銀彈消防栓）| {_cash_str} | {_cash_pct:.1f}% | 20% | {_cash_status} |\n"
    else:
        _cash_row = "| Cash（銀彈消防栓）| （請手動填入）| — | 20% | — |\n"

    bucket_section = (
        "\n\n## 💼 資金桶檢查 (依 capital/capital_config.md)\n"
        "\n### 現價口徑（風險 / 曝險視角）\n"
        "| 桶別 | 現價市值 | 佔比 | 目標 | 狀態 |\n"
        "|------|---------:|-----:|-----:|------|\n"
        f"| Core（底倉水庫）| {core_val:,.0f} | {core_pct:.1f}% | 50% | {'✅' if 40<=core_pct<=60 else '📌'}{core_note} |\n"
        f"| Tactical（戰術水管）| {tact_val:,.0f} | {tactical_pct:.1f}% | 30% | {'✅' if tactical_pct<=35 else '⚠️'}{tactical_warn} |\n"
        + _cash_row +
        f"| **已投資合計** | **{total_invested:,.0f}** | 100% | | |\n"
        "\n### 成本口徑（預算 / 投入視角）\n"
        "| 桶別 | 成本基礎 | 佔比 | 現價市值 | 帳面損益 |\n"
        "|------|---------:|-----:|---------:|---------:|\n"
        f"| Core | {core_cost:,.0f} | {core_cpct:.1f}% | {core_val:,.0f} | {core_pnl:+,.0f} ({core_pnl_pct:+.1f}%) |\n"
        f"| Tactical | {tact_cost:,.0f} | {tact_cpct:.1f}% | {tact_val:,.0f} | {tact_pnl:+,.0f} ({tact_pnl_pct:+.1f}%) |\n"
        f"| **合計** | **{total_cost_sum:,.0f}** | 100% | **{total_invested:,.0f}** | **{total_invested-total_cost_sum:+,.0f}** ({pct(total_invested-total_cost_sum, total_cost_sum):+.1f}%) |\n"
        "\n> 💡 **雙口徑解讀**：現價口徑用於觸發「桶別佔比」警戒線（配置偏離）；成本口徑用於判斷「預算投入」是否超限（單一標的／單桶是否過度押注）。兩者可能差距很大：Tactical 帳面虧損會讓現價佔比「看起來」變小，但實際投入本金沒變。\n"
    )
    if tactical_pct > 35:
        bucket_section = "\n> ⚠️ **資金越權警告**：Tactical 佔比（現價）超過 35% 上限！\n" + bucket_section
    if tact_cpct > 35:
        bucket_section = f"\n> ⚠️ **預算越權警告**：Tactical 成本佔比 {tact_cpct:.1f}% 超過 35% 上限（投入本金過重）\n" + bucket_section

    # ── 單檔預算檢查（Phase 4，依 capital/single_position_budget.md）────────
    budgets = parse_single_position_budget()
    if budgets:
        budget_rows_over = []
        budget_rows_ok   = []
        budget_rows_miss = []  # 表內有登記但持倉已清
        total_basis    = 0
        total_override = 0
        total_actual   = 0
        for code, b in budgets.items():
            total_basis    += b['basis']
            total_override += b['override']
            cap = b['cap']
            if code in position_costs:
                actual = position_costs[code]['cost']
                total_actual += actual
                usage = (actual / cap * 100) if cap > 0 else float('inf')
                if cap == 0:
                    status = '🟡 Exit（預算已鎖 0）' if actual > 0 else '✅ 已清'
                elif actual > cap:
                    over = actual - cap
                    status = f'🔴 超支 {over:,.0f}'
                elif usage >= 80:
                    status = f'⚠️ 使用率 {usage:.0f}%'
                else:
                    status = f'✅ {usage:.0f}%'
                row = (
                    f"| `{code}` | {b['name']} | {b['tier']} "
                    f"| {b['basis']:,} | {b['override']:,} | {cap:,} "
                    f"| {actual:,.0f} | {status} |"
                )
                if cap > 0 and actual > cap:
                    budget_rows_over.append(row)
                elif cap == 0 and actual > 0:
                    budget_rows_over.append(row)
                else:
                    budget_rows_ok.append(row)
            else:
                # 表中有登記但 position_costs 沒有 → 已清倉
                budget_rows_miss.append(
                    f"| `{code}` | {b['name']} | {b['tier']} "
                    f"| {b['basis']:,} | {b['override']:,} | {cap:,} | 0 | ✅ 已清倉 |"
                )

        budget_header = (
            "\n\n## 🎯 單檔預算檢查 (依 capital/single_position_budget.md)\n"
            "| 代碼 | 名稱 | Tier | 基準預算 | Override | 總上限 | 實際本金 | 狀態 |\n"
            "|------|------|:----:|---------:|---------:|-------:|---------:|------|\n"
        )
        budget_body = ""
        if budget_rows_over:
            budget_body += "\n".join(budget_rows_over) + "\n"
        if budget_rows_ok:
            budget_body += "\n".join(budget_rows_ok) + "\n"
        if budget_rows_miss:
            budget_body += "\n".join(budget_rows_miss) + "\n"

        budget_summary = (
            f"\n**預算匯總**：基準 {total_basis:,} ／ Override {total_override:,} "
            f"／ 實際投入 {total_actual:,.0f}\n"
        )
        if budget_rows_over:
            budget_warn = (
                f"\n> 🔴 **單檔預算越權警告**：{len(budget_rows_over)} 檔超出總預算上限，"
                "詳見 `capital/single_position_budget.md` § 🚫 超支既有部位\n"
            )
        else:
            budget_warn = "\n> ✅ 所有持倉均在預算範圍內\n"

        budget_section = budget_header + budget_body + budget_summary + budget_warn
        bucket_section = bucket_section + budget_section

    # ── 追加今日數據到 portfolio_history.csv ─────────────────────────────────
    history_path = os.path.join(TRADES_DIR, '..', 'portfolio_history.csv')
    cash_arg = None
    cash_delta_arg = None
    for arg in sys.argv[1:]:
        if arg.startswith('--cash='):
            try:
                cash_arg = float(arg.split('=', 1)[1].replace(',', ''))
            except ValueError:
                pass
        if arg.startswith('--cash-delta='):
            try:
                cash_delta_arg = float(arg.split('=', 1)[1].replace(',', ''))
            except ValueError:
                pass
    cash_inflow_arg = 0.0
    for arg in sys.argv[1:]:
        if arg.startswith('--inflow='):
            try:
                cash_inflow_arg = float(arg.split('=', 1)[1].replace(',', ''))
            except ValueError:
                pass
    notes_arg = ''
    for arg in sys.argv[1:]:
        if arg.startswith('--notes='):
            notes_arg = arg.split('=', 1)[1]

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    for arg in sys.argv[1:]:
        if arg.startswith('--date='):
            today_str = arg.split('=', 1)[1]

    if os.path.exists(history_path):
        with open(history_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        # 移除今日舊紀錄（若存在），保留其 cash_balance + notes 作為預設值
        prev_cash = None
        prev_notes = None
        new_lines = []
        import csv as _csv, io as _io
        for l in lines:
            if l.startswith(today_str + ','):
                # 用 csv module 解析，能正確處理引號包裝的 notes
                try:
                    parts = next(_csv.reader(_io.StringIO(l.strip())))
                except Exception:
                    parts = l.strip().split(',')
                if len(parts) >= 3 and parts[2]:
                    try:
                        prev_cash = float(parts[2])
                    except ValueError:
                        pass
                if len(parts) >= 6 and parts[5]:
                    prev_notes = parts[5]
            else:
                new_lines.append(l)
        lines = new_lines
        # 若今日無舊記錄，往回找最近一筆有效現金餘額（昨天或更早）
        if prev_cash is None:
            for l in reversed(new_lines[1:]):  # 跳過 header
                parts = l.strip().split(',')
                if len(parts) >= 3 and parts[2]:
                    try:
                        candidate = float(parts[2])
                        if candidate > 0:   # 排除異常負值
                            prev_cash = candidate
                            break
                    except ValueError:
                        pass
    else:
        lines = ['date,total_stock_value,cash_balance,total_portfolio_value,cash_inflow,notes\n']
        prev_cash = None
        prev_notes = None

    # cash 優先順序：--cash-delta（加減前次值）> --cash（直接覆寫）> 最近一筆餘額 > 空白
    if cash_delta_arg is not None:
        base = prev_cash if prev_cash is not None else 0.0
        cash_bal = base + cash_delta_arg
    elif cash_arg is not None:
        cash_bal = cash_arg
    elif prev_cash is not None:
        cash_bal = prev_cash
    else:
        cash_bal = ''

    total_pv = (total_invested + cash_bal) if cash_bal != '' else ''

    # notes 優先順序：--notes=（新值）> 舊列 notes（保留）> 空字串
    if notes_arg:
        final_notes = notes_arg
    elif prev_notes:
        final_notes = prev_notes
    else:
        final_notes = ''

    # 用 csv 模組寫入，正確處理含逗號的 notes 欄位
    import csv as _csv
    new_row_buf = _io.StringIO()
    _csv.writer(new_row_buf, lineterminator='\n').writerow([
        today_str,
        f"{total_invested:.0f}",
        cash_bal,
        total_pv,
        cash_inflow_arg,
        final_notes,
    ])
    lines.append(new_row_buf.getvalue())
    with open(history_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    cash_note = f"（現金 {cash_bal:,.0f} 元）" if cash_bal != '' else "（現金未提供，請加 --cash=金額）"
    print(f"[history] 已更新 {today_str}：股票市值 {total_invested:,.0f}{cash_note}")

    today = today_str
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
