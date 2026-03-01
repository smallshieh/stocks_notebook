"""
performance_report.py — 投資績效評估報告

計算：
  1. Modified Dietz 月報酬率（正確處理現金流入）
  2. 時間加權報酬率 TWR（連鎖相乘）
  3. 資金加權報酬率 MWR（IRR，反映實際財富增長）
  4. 基準比較（0050.TW）與 Alpha

執行方式：
  python scripts/performance_report.py

portfolio_history.csv 欄位說明：
  date                  — 紀錄日期
  total_stock_value     — 股票持倉市值（由 portfolio_report.py 自動填入）
  cash_balance          — 現金餘額（手動填入，或 --cash= 參數）
  total_portfolio_value — 股票 + 現金合計（= 兩者之和）
  cash_inflow           — 當日從外部新注入的資金（薪資/儲蓄）；0 表示無流入
  notes                 — 備註
"""

import os
import sys
import datetime
import warnings
import pandas as pd
import numpy as np
import yfinance as yf

warnings.filterwarnings('ignore')

BASE_DIR     = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
HISTORY_PATH = os.path.join(BASE_DIR, 'portfolio_history.csv')
BENCHMARK    = '0050.TW'   # 比較基準


# ── 讀取歷史數據 ────────────────────────────────────────────────────────────

def load_history() -> pd.DataFrame:
    if not os.path.exists(HISTORY_PATH):
        print(f"[錯誤] 找不到 {HISTORY_PATH}")
        sys.exit(1)
    df = pd.read_csv(HISTORY_PATH, parse_dates=['date'])
    df = df.sort_values('date').reset_index(drop=True)
    df['total_portfolio_value'] = pd.to_numeric(df['total_portfolio_value'], errors='coerce')
    df['cash_inflow']           = pd.to_numeric(df['cash_inflow'], errors='coerce').fillna(0)
    df = df.dropna(subset=['total_portfolio_value'])
    return df


# ── Modified Dietz 月報酬率 ─────────────────────────────────────────────────

def modified_dietz(v0: float, v1: float, flows: list) -> float:
    """
    flows: list of (day_index, amount) — day_index 從 0 開始（0 = 月初第一天）
    回傳：單月報酬率（小數），資料不足回傳 None
    """
    if v0 <= 0 and not flows:
        return None
    total_days = 30  # 近似月份天數（簡化）
    total_cf   = sum(amt for _, amt in flows)
    weighted   = sum(amt * (total_days - d) / total_days for d, amt in flows)
    denom      = v0 + weighted
    if denom == 0:
        return None
    return (v1 - v0 - total_cf) / denom


def calc_monthly_returns(df: pd.DataFrame) -> pd.DataFrame:
    """
    依月份計算 Modified Dietz 報酬率。
    假設：每個月的「月初值」= 上月底的 total_portfolio_value
    """
    df = df.copy()
    df['ym'] = df['date'].dt.to_period('M')
    records   = []

    months = df['ym'].unique()
    for i, ym in enumerate(months):
        m_df = df[df['ym'] == ym].copy()
        # 月初值：上月底最後一筆；若無則用本月第一筆 - 當日流入
        if i == 0:
            first_row = m_df.iloc[0]
            v0 = first_row['total_portfolio_value'] - first_row['cash_inflow']
        else:
            prev_ym = months[i - 1]
            prev_df = df[df['ym'] == prev_ym]
            v0 = prev_df.iloc[-1]['total_portfolio_value']

        v1 = m_df.iloc[-1]['total_portfolio_value']

        # 月內現金流入（排除月初第一天，因已反映在 v0 基礎上）
        flows_df = m_df[m_df['cash_inflow'] > 0].copy()
        flows_df['day_idx'] = (flows_df['date'] - m_df.iloc[0]['date']).dt.days
        flows = list(zip(flows_df['day_idx'], flows_df['cash_inflow']))

        r = modified_dietz(v0, v1, flows)
        records.append({'month': str(ym), 'v0': v0, 'v1': v1,
                        'cash_inflow': flows_df['cash_inflow'].sum(),
                        'return': r})

    return pd.DataFrame(records)


# ── TWR（時間加權報酬率）──────────────────────────────────────────────────

def calc_twr(monthly_returns: pd.DataFrame) -> float:
    """連鎖各月報酬率"""
    valid = monthly_returns['return'].dropna()
    if valid.empty:
        return None
    twr = 1.0
    for r in valid:
        twr *= (1 + r)
    return twr - 1


# ── MWR（資金加權報酬率 / IRR）──────────────────────────────────────────────

def calc_mwr(df: pd.DataFrame) -> float:
    """
    用 numpy IRR 近似法。
    現金流序列：注入為負（你付出），最終值為正（你拿回）。
    簡化：以月為間隔
    """
    try:
        import numpy_financial as npf
    except ImportError:
        return None

    df = df.copy().sort_values('date')
    flows = []
    # 初始投資（負值）
    first = df.iloc[0]
    flows.append(-first['total_portfolio_value'])
    # 後續現金流入（負值）
    for _, row in df.iloc[1:].iterrows():
        if row['cash_inflow'] > 0:
            flows.append(-row['cash_inflow'])
        else:
            flows.append(0)
    # 最終市值（正值，替換最後一個）
    flows[-1] += df.iloc[-1]['total_portfolio_value']
    irr = npf.irr(flows)
    if irr is None or np.isnan(irr):
        return None
    # 轉換為年化（簡化：假設每格為 1 個月）
    n_months = len(flows) - 1
    if n_months <= 0:
        return None
    annualized = (1 + irr) ** 12 - 1
    return annualized


# ── 基準報酬率（0050.TW）───────────────────────────────────────────────────

def calc_benchmark_return(start_date, end_date) -> float:
    """計算 0050.TW 在同期間的累積報酬率"""
    try:
        hist = yf.Ticker(BENCHMARK).history(
            start=start_date.strftime('%Y-%m-%d'),
            end=(end_date + datetime.timedelta(days=1)).strftime('%Y-%m-%d'),
            auto_adjust=True
        )
        if hist is None or len(hist) < 2:
            return None
        r = (hist['Close'].iloc[-1] - hist['Close'].iloc[0]) / hist['Close'].iloc[0]
        return r
    except Exception:
        return None


# ── 報告輸出 ────────────────────────────────────────────────────────────────

def fmt_pct(v, decimals=2):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return 'N/A'
    return f"{v*100:+.{decimals}f}%"


def generate_report():
    df = load_history()

    if len(df) < 2:
        print("=" * 60)
        print("資料不足（需至少 2 筆不同日期的紀錄才能計算報酬率）")
        print(f"目前只有 {len(df)} 筆，請繼續執行 portfolio_report.py 累積數據")
        print("=" * 60)
        _print_current_snapshot(df)
        return

    monthly = calc_monthly_returns(df)
    twr     = calc_twr(monthly)
    mwr     = calc_mwr(df)
    start   = df['date'].min()
    end     = df['date'].max()
    bench   = calc_benchmark_return(start, end)
    alpha   = (twr - bench) if (twr is not None and bench is not None) else None
    n_days  = (end - start).days

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    lines = []
    lines.append(f"# 投資績效報告 ({today_str})")
    lines.append(f"\n追蹤期間：{start.date()} → {end.date()}（{n_days} 天）\n")

    # ── 快照 ──
    latest = df.iloc[-1]
    lines.append("## 最新資產快照")
    lines.append("| 項目 | 金額 |")
    lines.append("|------|------|")
    lines.append(f"| 股票市值 | {latest['total_stock_value']:>12,.0f} 元 |" if pd.notna(latest.get('total_stock_value')) else "| 股票市值 | — |")
    lines.append(f"| 現金餘額 | {latest['cash_balance']:>12,.0f} 元 |" if pd.notna(latest.get('cash_balance')) else "| 現金餘額 | （未填） |")
    lines.append(f"| **總資產** | **{latest['total_portfolio_value']:>12,.0f} 元** |")
    lines.append(f"| 初始基準日資產 | {df.iloc[0]['total_portfolio_value']:>12,.0f} 元 |")

    total_injected = df['cash_inflow'].sum()
    lines.append(f"| 累計注入資金 | {total_injected:>12,.0f} 元 |")
    lines.append("")

    # ── 月度報酬 ──
    lines.append("## 月度 Modified Dietz 報酬率")
    lines.append("| 月份 | 月初值 | 月底值 | 當月流入 | 月報酬率 |")
    lines.append("|------|--------|--------|---------|---------|")
    for _, row in monthly.iterrows():
        r_str = fmt_pct(row['return'])
        trend = "📈" if row['return'] and row['return'] > 0 else ("📉" if row['return'] and row['return'] < 0 else "—")
        lines.append(
            f"| {row['month']} "
            f"| {row['v0']:>10,.0f} "
            f"| {row['v1']:>10,.0f} "
            f"| {row['cash_inflow']:>8,.0f} "
            f"| {trend} {r_str} |"
        )
    lines.append("")

    # ── 績效總覽 ──
    lines.append("## 績效總覽")
    lines.append("| 指標 | 數值 | 說明 |")
    lines.append("|------|------|------|")
    lines.append(f"| 時間加權報酬 TWR | {fmt_pct(twr)} | 策略品質，排除現金流時機 |")
    lines.append(f"| 資金加權報酬 MWR | {fmt_pct(mwr)} *(年化)* | 實際財富增長，含進場時機 |")
    lines.append(f"| 基準（0050 同期）| {fmt_pct(bench)} | 定期定額買 0050 的報酬 |")

    if alpha is not None:
        alpha_icon = "✅" if alpha >= 0 else "❌"
        lines.append(f"| Alpha（超額報酬）| {alpha_icon} {fmt_pct(alpha)} | TWR − 0050，正值代表跑贏大盤 |")
    else:
        lines.append(f"| Alpha | N/A | 基準數據不足 |")
    lines.append("")

    # ── 解讀提示 ──
    lines.append("## 解讀指引")
    if twr is not None and bench is not None:
        if twr > bench:
            lines.append(f"> ✅ **TWR {fmt_pct(twr)} > 0050 {fmt_pct(bench)}**：策略跑贏大盤 {fmt_pct(alpha)}，選股有附加價值。")
        else:
            lines.append(f"> ❌ **TWR {fmt_pct(twr)} < 0050 {fmt_pct(bench)}**：策略跑輸大盤 {fmt_pct(alpha)}，考慮是否調整策略或轉向 ETF。")
    if twr is not None and mwr is not None:
        diff = mwr - twr
        if diff < -0.02:
            lines.append(f"> ⚠️ **MWR 低於 TWR {fmt_pct(diff)}**：現金進場時機拖累實際報酬（高點注入較多資金）。")
        elif diff > 0.02:
            lines.append(f"> 💡 **MWR 高於 TWR {fmt_pct(diff)}**：你的進場時機幫助了實際財富增長。")

    lines.append("")
    lines.append("---")
    lines.append("*TWR = 時間加權報酬（評估策略）；MWR = 資金加權報酬（評估實際財富）*")
    lines.append("*Alpha = TWR − 同期 0050 報酬；正值代表主動選股有意義*")

    report = "\n".join(lines)
    out_path = os.path.join(BASE_DIR, f'績效報告_{today_str}.md')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(report)
    print(f"\n報告已儲存：{os.path.abspath(out_path)}")


def _print_current_snapshot(df):
    if df.empty:
        return
    row = df.iloc[-1]
    total = row['total_portfolio_value']
    total_injected = df['cash_inflow'].sum()
    simple_pnl = total - total_injected
    print(f"\n【快照】{row['date'].date()}")
    print(f"  總資產：{total:,.0f} 元")
    print(f"  累計注入：{total_injected:,.0f} 元")
    print(f"  帳面損益：{simple_pnl:+,.0f} 元（{simple_pnl/total_injected*100:+.2f}%）")
    print("（報酬率計算需累積更多資料點）")


if __name__ == '__main__':
    generate_report()
