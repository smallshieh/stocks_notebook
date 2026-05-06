"""
date_utils.py — 共用日期工具（slice history to review date, trading day helpers）
"""
from __future__ import annotations

import os
import datetime
from datetime import date, timedelta
import pandas as pd


def resolve_review_date(cli_date: str | None = None) -> str:
    """優先級：CLI > REVIEW_DATE env > today"""
    if cli_date:
        return cli_date
    env = os.environ.get("REVIEW_DATE")
    if env:
        return env
    return date.today().isoformat()


def resolve_effective_date(
    cli_date: str | None = None,
    hist: pd.DataFrame | None = None,
    *,
    allow_future: bool = False,
) -> str:
    """
    決定本次執行的有效日期。
    優先級：CLI > REVIEW_DATE env > hist 最後一列日期 > today

    若 cli_date/env_date 指定了日期且 hist 包含該日期 → 切片到該日期
    若未指定 → 使用 hist 最後一列或 today
    """
    target = resolve_review_date(cli_date)
    if hist is not None and not hist.empty:
        data_dates = pd.to_datetime(hist.index).date
        latest = data_dates[-1]
        latest_str = latest.isoformat()
        target_date = date.fromisoformat(target)
        if target_date in data_dates.values:
            return target
        if not allow_future and target_date > latest:
            return latest_str
    return target


def slice_history_to_date(hist: pd.DataFrame, target_date: str) -> pd.DataFrame:
    """裁切 yfinance history 到指定日期（含），回傳該時間點的快照。
    若 target_date 不是交易日（週末/假日），自動取之前最近一個交易日。"""
    if hist is None or hist.empty:
        return hist
    cutoff = pd.Timestamp(target_date)
    idx = pd.to_datetime(hist.index)
    if hasattr(idx, 'tz') and idx.tz is not None:
        cutoff = cutoff.tz_localize(idx.tz)
    mask = idx <= cutoff
    if not mask.any():
        return hist.iloc[:0].copy()
    sliced = hist.loc[mask].copy()
    return sliced


def trading_days_between(from_date: str, to_date: str) -> int:
    """計算兩個日期之間的交易日數（不含起日，含迄日）"""
    try:
        f = date.fromisoformat(from_date)
        t = date.fromisoformat(to_date)
    except (ValueError, TypeError):
        return 0
    count = 0
    d = f + timedelta(days=1)
    while d <= t:
        if d.weekday() < 5:
            count += 1
        d += timedelta(days=1)
    return count


def latest_market_date(hist: pd.DataFrame | None) -> str | None:
    """從 yfinance history 取最新交易日"""
    if hist is not None and not hist.empty:
        return pd.to_datetime(hist.index[-1]).date().isoformat()
    return None
