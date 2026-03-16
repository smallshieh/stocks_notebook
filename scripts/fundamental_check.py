#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fundamental_check.py — 財報狗場景 A/C/D 自動化（資料來源：FinMind / 公開資訊觀測站）

功能：
  - 月營收趨勢（近 6 個月 YoY）
  - 近 4 季毛利率、EPS
  - 近 4 季 ROE（單季淨利 / 淨值）
  - 資產負債結構（負債比、流動比）
  - 輸出 Core 入選標準評估結論

用法：
  .venv/Scripts/python.exe scripts/fundamental_check.py --code 6115
  .venv/Scripts/python.exe scripts/fundamental_check.py --code 2330 2317
"""

import sys
import os
import warnings
import argparse
import datetime

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

import logging
logging.disable(logging.CRITICAL)

from curl_cffi import requests as creq
import pandas as pd

API_URL = 'https://api.finmindtrade.com/api/v4/data'

# 載入 FinMind token（選用，有 token 可提高 API 限制）
try:
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(__file__))
    from notion_creds import FINMIND_TOKEN as _FM_TOKEN
    FINMIND_TOKEN = _FM_TOKEN if _FM_TOKEN else None
except Exception:
    FINMIND_TOKEN = None


# ─────────────────────────────────────────────────────────────────────────────
# API 工具
# ─────────────────────────────────────────────────────────────────────────────

def _session():
    return creq.Session(impersonate='chrome', verify=False)


def fetch(session, dataset, code, start_date) -> pd.DataFrame:
    params = {
        'dataset': dataset,
        'data_id': str(code),
        'start_date': start_date,
    }
    if FINMIND_TOKEN:
        params['token'] = FINMIND_TOKEN
    r = session.get(API_URL, params=params)
    d = r.json()
    if d.get('status') != 200 or not d.get('data'):
        return pd.DataFrame()
    return pd.DataFrame(d['data'])


# ─────────────────────────────────────────────────────────────────────────────
# 月營收
# ─────────────────────────────────────────────────────────────────────────────

def get_revenue(session, code) -> pd.DataFrame:
    # 抓 2 年資料以便計算 YoY
    start = (datetime.date.today() - datetime.timedelta(days=730)).strftime('%Y-%m-%d')
    df = fetch(session, 'TaiwanStockMonthRevenue', code, start)
    if df.empty:
        return df
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    df['revenue'] = pd.to_numeric(df['revenue'], errors='coerce')

    # 計算 YoY
    rev_map = dict(zip(df['date'], df['revenue']))
    yoy_list = []
    for d, rev in zip(df['date'], df['revenue']):
        prev = d - pd.DateOffset(years=1)
        # 找最近一個月的去年同期
        candidates = [v for k, v in rev_map.items() if abs((k - prev).days) <= 31]
        if candidates and rev is not None:
            prev_rev = candidates[0]
            yoy = (rev - prev_rev) / prev_rev * 100 if prev_rev else None
        else:
            yoy = None
        yoy_list.append(yoy)
    df['yoy'] = yoy_list
    return df.tail(6)


# ─────────────────────────────────────────────────────────────────────────────
# 財務報表（毛利率、EPS）
# ─────────────────────────────────────────────────────────────────────────────

def get_income(session, code) -> pd.DataFrame:
    start = (datetime.date.today() - datetime.timedelta(days=540)).strftime('%Y-%m-%d')
    df = fetch(session, 'TaiwanStockFinancialStatements', code, start)
    if df.empty:
        return pd.DataFrame()
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    pivot = df.pivot_table(index='date', columns='type', values='value', aggfunc='first').reset_index()
    pivot['date'] = pd.to_datetime(pivot['date'])
    pivot = pivot.sort_values('date').tail(4)

    # 毛利率 = GrossProfit / Revenue
    if 'GrossProfit' in pivot.columns and 'Revenue' in pivot.columns:
        pivot['gross_margin'] = pivot['GrossProfit'] / pivot['Revenue'] * 100
    else:
        pivot['gross_margin'] = None

    return pivot


# ─────────────────────────────────────────────────────────────────────────────
# 資產負債表（負債比、流動比）
# ─────────────────────────────────────────────────────────────────────────────

def get_balance(session, code) -> pd.DataFrame:
    start = (datetime.date.today() - datetime.timedelta(days=540)).strftime('%Y-%m-%d')
    df = fetch(session, 'TaiwanStockBalanceSheet', code, start)
    if df.empty:
        return pd.DataFrame()
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    pivot = df.pivot_table(index='date', columns='type', values='value', aggfunc='first').reset_index()
    pivot['date'] = pd.to_datetime(pivot['date'])
    pivot = pivot.sort_values('date').tail(4)

    # 負債比 = Liabilities / TotalAssets（FinMind 欄位名）
    if 'Liabilities' in pivot.columns and 'TotalAssets' in pivot.columns:
        pivot['debt_ratio'] = pivot['Liabilities'] / pivot['TotalAssets'] * 100
    else:
        pivot['debt_ratio'] = None

    # 流動比 = CurrentAssets / CurrentLiabilities
    ca_col = next((c for c in pivot.columns if c == 'CurrentAssets'), None)
    cl_col = next((c for c in pivot.columns if c == 'CurrentLiabilities'), None)
    if ca_col and cl_col:
        pivot['current_ratio'] = pivot[ca_col] / pivot[cl_col]
    else:
        pivot['current_ratio'] = None

    return pivot


# ─────────────────────────────────────────────────────────────────────────────
# ROE（單季淨利 / 季末淨值，需合併損益表 + 資產負債表）
# ─────────────────────────────────────────────────────────────────────────────

def get_roe(session, code, inc: pd.DataFrame, bal: pd.DataFrame) -> list:
    """回傳 [(date_str, roe%), ...] 近 4 季"""
    if inc.empty or bal.empty:
        return []
    # 損益表取 IncomeFromContinuingOperations（稅後淨利）
    ni_col = 'IncomeFromContinuingOperations'
    eq_col = next((c for c in bal.columns if c in ('EquityAttributableToOwnersOfParent', 'Equity')), None)
    if ni_col not in inc.columns or eq_col is None:
        return []
    merged = pd.merge(
        inc[['date', ni_col]].rename(columns={ni_col: 'net_income'}),
        bal[['date', eq_col]].rename(columns={eq_col: 'equity'}),
        on='date', how='inner'
    )
    result = []
    for _, row in merged.iterrows():
        if pd.notna(row['net_income']) and pd.notna(row['equity']) and row['equity'] != 0:
            result.append((str(row['date'])[:10], row['net_income'] / row['equity'] * 100))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Core 評估
# ─────────────────────────────────────────────────────────────────────────────

def core_verdict(gross_margin_trend, roe_avg, eps_stable, debt_ok, current_ok) -> str:
    failures = []
    if roe_avg is not None and roe_avg < 3.5:  # 單季 3.5% ≈ 年化 14%
        failures.append('ROE 偏低')
    if not gross_margin_trend:
        failures.append('毛利率下滑')
    if not eps_stable:
        failures.append('EPS 不穩定')
    if debt_ok is False:
        failures.append('負債偏高')

    if not failures:
        return '✅ 初步符合 Core 標準（需搭配 GBM μ 確認）'
    return f'❌ 不符合 Core 標準：{" / ".join(failures)}'


# ─────────────────────────────────────────────────────────────────────────────
# 主分析
# ─────────────────────────────────────────────────────────────────────────────

def analyze(code: str):
    session = _session()
    today = datetime.date.today().strftime('%Y-%m-%d')
    print(f"\n{'='*55}")
    print(f"📊 基本面審查：{code}　（{today}）")
    print(f"{'='*55}")

    # ── 月營收 ──────────────────────────────────────────────
    print("\n### 月營收趨勢（近 6 個月）")
    rev = get_revenue(session, code)
    if rev.empty:
        print("  ❌ 無法取得月營收資料")
    else:
        print(f"  {'月份':<12} {'營收（億元）':>10} {'YoY%':>8}")
        for _, row in rev.iterrows():
            yoy_str = f"{row['yoy']:+.1f}%" if pd.notna(row['yoy']) else "  N/A"
            flag = '🔴' if pd.notna(row['yoy']) and row['yoy'] < -15 else ('🚀' if pd.notna(row['yoy']) and row['yoy'] > 20 else '  ')
            print(f"  {str(row['date'])[:7]:<12} {row['revenue']/1e8:>10.2f}  {yoy_str:>8} {flag}")

    # ── 損益表 ──────────────────────────────────────────────
    print("\n### 獲利能力（近 4 季）")
    inc = get_income(session, code)
    gross_margins = []
    eps_list = []
    if inc.empty:
        print("  ❌ 無法取得損益資料")
    else:
        print(f"  {'季度':<14} {'毛利率':>8} {'EPS':>8}")
        for _, row in inc.iterrows():
            gm = f"{row['gross_margin']:.1f}%" if pd.notna(row.get('gross_margin')) else "N/A"
            eps = f"{row['EPS']:.2f}" if 'EPS' in row and pd.notna(row['EPS']) else "N/A"
            print(f"  {str(row['date'])[:10]:<14} {gm:>8} {eps:>8}")
            if pd.notna(row.get('gross_margin')):
                gross_margins.append(row['gross_margin'])
            if 'EPS' in row and pd.notna(row['EPS']):
                eps_list.append(row['EPS'])

    # ── 資產負債表 ──────────────────────────────────────────
    print("\n### 財務結構（近 4 季）")
    bal = get_balance(session, code)
    debt_ratios = []
    roe_pairs = []
    if bal.empty:
        print("  ❌ 無法取得資產負債資料")
    else:
        # ROE 合併計算
        roe_pairs = get_roe(session, code, inc, bal)
        roe_map = dict(roe_pairs)

        print(f"  {'季度':<14} {'負債比':>8} {'流動比':>8} {'ROE(季)':>9}")
        for _, row in bal.iterrows():
            dr = f"{row['debt_ratio']:.1f}%" if pd.notna(row.get('debt_ratio')) else "N/A"
            cr = f"{row['current_ratio']:.2f}x" if pd.notna(row.get('current_ratio')) else "N/A"
            date_key = str(row['date'])[:10]
            roe_val = roe_map.get(date_key)
            roe = f"{roe_val:.2f}%" if roe_val is not None else "N/A"
            print(f"  {date_key:<14} {dr:>8} {cr:>8} {roe:>9}")
            if pd.notna(row.get('debt_ratio')):
                debt_ratios.append(row['debt_ratio'])

    roe_list = [v for _, v in roe_pairs] if not bal.empty else []

    # ── Core 評估 ───────────────────────────────────────────
    print("\n### Core 入選標準評估")
    gm_trend = len(gross_margins) >= 2 and gross_margins[-1] >= gross_margins[0]
    roe_avg = sum(roe_list) / len(roe_list) if roe_list else None
    eps_stable = len(eps_list) >= 3 and min(eps_list) > 0 and (max(eps_list) - min(eps_list)) / max(eps_list) < 0.8 if eps_list else False
    debt_ok = all(d < 50 for d in debt_ratios) if debt_ratios else None

    gm_str = f"{gross_margins[-1]:.1f}%（{'↑改善' if gm_trend else '↓下滑'}）" if gross_margins else "N/A"
    roe_str = f"{roe_avg:.2f}% 季均（≈年化 {roe_avg*4:.1f}%）" if roe_avg is not None else "N/A"

    print(f"  毛利率趨勢：{gm_str}")
    print(f"  ROE 季均：{roe_str}")
    print(f"  EPS 穩定性：{'✅ 穩定' if eps_stable else '⚠️ 波動'}")
    print(f"  財務結構：{'✅ 健康' if debt_ok else ('⚠️ 偏高' if debt_ok is False else 'N/A')}")
    verdict = core_verdict(gm_trend, roe_avg, eps_stable, debt_ok, None)
    print(f"\n  結論：{verdict}")
    print(f"  （μ 需另查 GBM 分析腳本確認長期漂移方向）")


# ─────────────────────────────────────────────────────────────────────────────
# 主程式
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='基本面審查（FinMind）')
    parser.add_argument('--code', nargs='+', required=True, help='股票代號，可多檔')
    args = parser.parse_args()

    for code in args.code:
        analyze(code)


if __name__ == '__main__':
    main()
