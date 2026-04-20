"""
regime_tracker.py — 價格區間遷移追蹤器
=======================================
追蹤個股的價格區間是否發生結構性變化，產出三個指標：
  1. OU 均衡價 θ（90日窗口）
  2. 關鍵支撐價位守住率（60日）
  3. 最近一次顯著回測的低點

用法：
  # 基本（自動從 stocks.csv 查 ticker）
  python scripts/regime_tracker.py --code 6488

  # 自訂支撐價位（預設從 CSV 歷史紀錄推算）
  python scripts/regime_tracker.py --code 6488 --support 430

  # 查看歷史紀錄
  python scripts/regime_tracker.py --code 6488 --history

  # 靜默模式（供 hook 呼叫，只輸出摘要行）
  python scripts/regime_tracker.py --code 6488 --quiet

輸出：
  - 一行摘要（供 daily-review hook 使用）
  - CSV 追蹤行追加至 journals/regime_tracking_{code}.csv
"""

import sys
import os
import argparse
import json
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')

import numpy as np
import pandas as pd


# ── 路徑 ───────────────────────────────────────────────────────────────────

PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STOCKS_CSV = os.path.join(PROJ_ROOT, 'stocks.csv')
JOURNALS_DIR = os.path.join(PROJ_ROOT, 'journals')


# ── 資料取得 ─────────────────────────────────────────────────────────────────

def resolve_ticker(code: str) -> str:
    """從 stocks.csv 解析 ticker，fallback 暴力嘗試"""
    if os.path.exists(STOCKS_CSV):
        try:
            df = pd.read_csv(STOCKS_CSV, dtype=str).set_index('code')
            if code in df.index and 'ticker' in df.columns:
                return df.loc[code, 'ticker']
        except Exception:
            pass
    return f'{code}.TW'


def fetch_prices(ticker: str, period: str = '2y') -> pd.DataFrame | None:
    try:
        from curl_cffi import requests as creq
        import yfinance as yf
        session = creq.Session(verify=False, impersonate='chrome')
        df = yf.Ticker(ticker, session=session).history(period=period)
        df.index = df.index.tz_localize(None)
        return df
    except Exception as e:
        print(f'⚠️  無法下載 {ticker}：{e}', file=sys.stderr)
        return None


# ── 指標 1：OU 均衡價 θ ────────────────────────────────────────────────────

def estimate_ou_theta(prices: pd.Series, window: int = 90) -> dict:
    """估算 OU 模型的均衡價 θ 與半衰期"""
    p = prices[-window:]
    X = p.values
    dt = 1 / 252

    dX = np.diff(X)
    X_lag = X[:-1]
    A = np.vstack([np.ones_like(X_lag), X_lag]).T
    result = np.linalg.lstsq(A, dX, rcond=None)
    a, b = result[0]

    kappa = -b / dt
    theta = -a / b if b != 0 else np.nan
    half_life = np.log(2) / kappa * 252 if kappa > 0 else np.inf

    return {
        'theta': round(theta, 0),
        'kappa': round(kappa, 2),
        'half_life_days': round(half_life, 0),
    }


# ── 指標 2：支撐守住率 ──────────────────────────────────────────────────────

def support_holding(prices: pd.Series, support: float, window: int = 60) -> dict:
    """計算近 window 日站穩 support 的比率與最長連續天數"""
    recent = prices[-window:]
    above = recent >= support

    total_above = int(above.sum())
    hold_rate = round(total_above / len(recent) * 100, 0)

    # 最長連續站穩
    max_streak = 0
    streak = 0
    for v in above:
        if v:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0

    return {
        'support': support,
        'hold_rate_pct': hold_rate,
        'max_streak_days': max_streak,
        'total_above': total_above,
        'window': len(recent),
    }


# ── 指標 3：最近回測深度 ─────────────────────────────────────────────────────

def recent_drawdown(prices: pd.Series, lookback: int = 120) -> dict:
    """找近 lookback 日內最顯著的一次高點→回測"""
    recent = prices[-lookback:]

    # 滾動20日高點
    rolling_max = recent.rolling(20).max()
    # 找最高的那個峰
    peak_idx = rolling_max.idxmax()
    peak_val = recent.loc[peak_idx]

    # 峰之後的最低點
    after_peak = recent[peak_idx:]
    if len(after_peak) < 2:
        return {'peak': float(peak_val), 'peak_date': str(peak_idx.date()),
                'trough': float(peak_val), 'trough_date': str(peak_idx.date()),
                'drawdown_pct': 0.0}

    trough_idx = after_peak.idxmin()
    trough_val = after_peak.loc[trough_idx]
    dd_pct = round((trough_val - peak_val) / peak_val * 100, 1)

    return {
        'peak': float(peak_val),
        'peak_date': str(peak_idx.date()),
        'trough': float(trough_val),
        'trough_date': str(trough_idx.date()),
        'drawdown_pct': dd_pct,
    }


# ── 支撐價位自動推算 ────────────────────────────────────────────────────────

def auto_support(prices: pd.Series, csv_path: str | None = None) -> float:
    """
    自動推算關鍵支撐價位。
    策略：取近 120 日的 25th percentile，四捨五入到 10 元。
    """
    recent = prices[-120:]
    p25 = np.percentile(recent.values, 25)
    return round(p25 / 10) * 10


# ── CSV 追蹤 ─────────────────────────────────────────────────────────────────

def csv_path(code: str) -> str:
    return os.path.join(JOURNALS_DIR, f'regime_tracking_{code}.csv')


def append_csv(code: str, row: dict):
    path = csv_path(code)
    df_new = pd.DataFrame([row])
    if os.path.exists(path):
        df_old = pd.read_csv(path)
        df = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df = df_new
    df.to_csv(path, index=False)


def read_csv(code: str) -> pd.DataFrame | None:
    path = csv_path(code)
    if os.path.exists(path):
        return pd.read_csv(path)
    return None


# ── 判定門檻評估 ─────────────────────────────────────────────────────────────

def evaluate_thresholds(code: str, current: dict) -> list[str]:
    """讀取歷史 CSV，評估三個維度的確認狀態"""
    notes = []
    history = read_csv(code)

    # 維度一：OU θ 連續 3 次 ≥ 450
    if history is not None and len(history) >= 3:
        last3_theta = history['ou_theta'].tail(3).tolist()
        if all(t >= 450 for t in last3_theta):
            notes.append('✅ OU θ 連續3次 ≥ 450（中樞上移確認）')
        else:
            notes.append(f'⏳ OU θ 近3次: {last3_theta}（需全部 ≥ 450）')
    else:
        notes.append(f'⏳ OU θ 資料不足（需累積 3 筆）')

    # 維度二：支撐守住率
    rate = current['support_hold_rate_pct']
    streak = current['support_max_streak']
    if rate >= 90 and streak >= 30:
        notes.append(f'✅ 支撐守住率 {rate}% / 連續 {streak} 日（新底確立）')
    else:
        notes.append(f'⏳ 支撐守住率 {rate}% / 連續 {streak} 日（需 ≥90% + 30日）')

    # 維度三：回測深度（需要人工判斷下一次回測）
    dd = current['drawdown_pct']
    trough = current['drawdown_trough']
    notes.append(f'📊 最近回測低點 {trough:.0f}（跌幅 {dd}%，需觀察下次回測是否守住更高位）')

    return notes


# ── 主程式 ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='價格區間遷移追蹤器')
    parser.add_argument('--code', required=True, help='股票代號')
    parser.add_argument('--support', type=float, default=None,
                        help='關鍵支撐價位（未填則自動推算）')
    parser.add_argument('--history', action='store_true',
                        help='顯示歷史追蹤紀錄')
    parser.add_argument('--quiet', action='store_true',
                        help='靜默模式，只輸出摘要行')
    args = parser.parse_args()

    code = args.code

    # 顯示歷史
    if args.history:
        df = read_csv(code)
        if df is None:
            print(f'尚無 {code} 的追蹤紀錄')
        else:
            print(df.to_string(index=False))
        return

    # 取得價格
    ticker = resolve_ticker(code)
    df = fetch_prices(ticker)
    if df is None or df.empty:
        print(f'❌ 無法取得 {code} 價格資料', file=sys.stderr)
        sys.exit(1)

    prices = df['Close']
    current_price = prices.iloc[-1]
    today = prices.index[-1].strftime('%Y-%m-%d')

    # 支撐價位
    support = args.support if args.support else auto_support(prices)

    # 計算三指標
    ou = estimate_ou_theta(prices, window=90)
    sh = support_holding(prices, support, window=60)
    dd = recent_drawdown(prices, lookback=120)

    # 組裝 CSV 行
    row = {
        'date': today,
        'price': current_price,
        'ou_theta': ou['theta'],
        'ou_half_life': ou['half_life_days'],
        'support_level': support,
        'support_hold_rate_pct': sh['hold_rate_pct'],
        'support_max_streak': sh['max_streak_days'],
        'drawdown_peak': dd['peak'],
        'drawdown_trough': dd['trough'],
        'drawdown_pct': dd['drawdown_pct'],
    }

    # 摘要行
    summary = (
        f"θ={ou['theta']:.0f}, "
        f"{support:.0f}守住率={sh['hold_rate_pct']:.0f}%/{sh['max_streak_days']}日, "
        f"回測低點={dd['trough']:.0f}({dd['drawdown_pct']:+.1f}%)"
    )

    if args.quiet:
        print(summary)
        append_csv(code, row)
        return

    # 完整輸出
    print(f'=== {code} 區間遷移追蹤 ({today}) ===')
    print(f'現價: {current_price:.0f}')
    print()
    print(f'【指標1】OU 均衡價 θ = {ou["theta"]:.0f}（半衰期 {ou["half_life_days"]:.0f} 日）')
    print(f'【指標2】{support:.0f} 元支撐：守住率 {sh["hold_rate_pct"]:.0f}%（{sh["total_above"]}/{sh["window"]} 日），最長連續 {sh["max_streak_days"]} 日')
    print(f'【指標3】最近回測：{dd["peak_date"]} 高點 {dd["peak"]:.0f} → {dd["trough_date"]} 低點 {dd["trough"]:.0f}（{dd["drawdown_pct"]:+.1f}%）')
    print()

    # 判定門檻
    notes = evaluate_thresholds(code, row)
    print('--- 判定門檻狀態 ---')
    for n in notes:
        print(f'  {n}')
    print()
    print(f'📐 摘要: {summary}')

    # 寫入 CSV
    append_csv(code, row)
    print(f'✅ 已追加至 {csv_path(code)}')


if __name__ == '__main__':
    main()
