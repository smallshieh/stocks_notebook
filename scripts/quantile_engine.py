"""
歷史分位數引擎 (Quantile Engine)
=================================
以歷史價格資料估計回檔分位數，並輸出滾動決策區間：
  - 賣出區 (sell_low ~ sell_high)
  - 常規買回區 (buy_low ~ buy_high)
  - 深回檔區 (deep_low ~ deep_high)
  - 暫停線 (stop_level)

用途：作為「輔助決策計算」模組，和 physics_engine 並列使用。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_quantile_metrics(df: pd.DataFrame) -> dict[str, float | str]:
    """
    由 OHLC 歷史資料計算分位數決策參數。

    參數:
        df: 包含 'High', 'Low', 'Close' 欄位的 DataFrame

    回傳:
        包含 as_of、均線、ATR、回檔分位數與價位區間的 dict
    """
    result = df.copy()
    result.index = pd.to_datetime(result.index).tz_localize(None)

    close = result["Close"]
    high = result["High"]
    low = result["Low"]

    last_close = float(close.iloc[-1])
    mean20 = float(close.tail(20).mean())
    std20 = float(close.tail(20).std(ddof=0))

    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr14 = float(tr.rolling(14).mean().iloc[-1])

    ret = close.pct_change().dropna()
    vol20 = float(ret.tail(20).std(ddof=0))

    # 局部高點：以 5 日 centered rolling max 近似峰值。
    roll_max = close.rolling(5, center=True).max()
    peaks = close[close.eq(roll_max)].dropna()

    drawdowns: list[float] = []
    for dt, px in peaks.items():
        loc = close.index.get_loc(dt)
        if isinstance(loc, slice):
            continue
        future = close.iloc[loc + 1 : loc + 11]
        if len(future) < 5:
            continue
        dd = (float(px) - float(future.min())) / float(px)
        if dd > 0:
            drawdowns.append(dd)

    if drawdowns:
        arr = np.array(drawdowns, dtype=float)
        dd50 = float(np.quantile(arr, 0.50))
        dd70 = float(np.quantile(arr, 0.70))
        dd85 = float(np.quantile(arr, 0.85))
    else:
        dd50, dd70, dd85 = 0.04, 0.08, 0.11

    sell_center = mean20
    sell_low = sell_center - 0.5 * atr14
    sell_high = sell_center + 0.5 * atr14

    buy_high = sell_center * (1 - dd50)
    buy_low = sell_center * (1 - dd70)
    deep_low = sell_center * (1 - dd85)
    deep_high = buy_low

    stop_level = buy_low - 0.8 * atr14

    return {
        "as_of": str(close.index[-1].date()),
        "last_close": last_close,
        "mean20": mean20,
        "std20": std20,
        "atr14": atr14,
        "vol20_pct": vol20 * 100,
        "dd50_pct": dd50 * 100,
        "dd70_pct": dd70 * 100,
        "dd85_pct": dd85 * 100,
        "sell_low": sell_low,
        "sell_high": sell_high,
        "buy_low": buy_low,
        "buy_high": buy_high,
        "deep_low": deep_low,
        "deep_high": deep_high,
        "stop_level": stop_level,
    }


def generate_quantile_report(df: pd.DataFrame, ticker: str) -> str:
    """
    生成分位數決策報告文字，供 CLI 或日誌輸出。
    """
    if df is None or df.empty:
        return f"[{ticker}] 無法生成分位數診斷：資料不足"

    m = compute_quantile_metrics(df)
    lines = []
    lines.append(f"\n[{ticker}] 歷史分位數決策診斷")
    lines.append("─" * 40)
    lines.append(f"➤ 參數日期: {m['as_of']}")
    lines.append(f"➤ 現價: {float(m['last_close']):.2f}")
    lines.append(f"➤ 20MA: {float(m['mean20']):.2f}")
    lines.append(f"➤ ATR14: {float(m['atr14']):.2f}")
    lines.append(
        f"➤ 回檔分位: dd50={float(m['dd50_pct']):.2f}% / "
        f"dd70={float(m['dd70_pct']):.2f}% / dd85={float(m['dd85_pct']):.2f}%"
    )
    lines.append(
        f"➤ 賣出區: {float(m['sell_low']):.2f} ~ {float(m['sell_high']):.2f}"
    )
    lines.append(
        f"➤ 常規買回區: {float(m['buy_low']):.2f} ~ {float(m['buy_high']):.2f}"
    )
    lines.append(
        f"➤ 深回檔區: {float(m['deep_low']):.2f} ~ {float(m['deep_high']):.2f}"
    )
    lines.append(f"➤ 暫停線: {float(m['stop_level']):.2f}")
    lines.append("")
    return "\n".join(lines)
