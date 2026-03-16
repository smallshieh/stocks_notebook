#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd
import yfinance as yf
from curl_cffi import requests as creq

from quantile_engine import compute_quantile_metrics


@dataclass
class TradeInfo:
    shares: int | None
    avg_cost: float | None


def read_stocks_csv(path: Path) -> pd.DataFrame:
    last_err = None
    for enc in ("utf-8-sig", "utf-8", "cp950"):
        try:
            return pd.read_csv(path, dtype=str, encoding=enc).set_index("code")
        except Exception as err:  # pragma: no cover
            last_err = err
    raise RuntimeError(f"無法讀取 {path}: {last_err}")


def parse_codes(raw_codes: Iterable[str] | None) -> list[str]:
    if not raw_codes:
        return []
    result: list[str] = []
    for raw in raw_codes:
        for part in raw.split(","):
            code = part.strip()
            if code:
                result.append(code)
    return sorted(set(result))


def find_trade_file(trades_dir: Path, code: str) -> Path | None:
    files = sorted(trades_dir.glob(f"{code}_*.md"))
    return files[0] if files else None


def read_text_with_fallback(path: Path) -> str:
    last_err = None
    for enc in ("utf-8-sig", "utf-8", "cp950"):
        try:
            return path.read_text(encoding=enc)
        except Exception as err:
            last_err = err
    raise RuntimeError(f"無法讀取 {path}: {last_err}")


def parse_trade_info(path: Path | None) -> TradeInfo:
    if path is None:
        return TradeInfo(None, None)

    text = read_text_with_fallback(path)

    shares = None
    avg_cost = None

    m_shares = re.search(r"集保股數\*\*:\s*([0-9,]+)", text)
    if m_shares:
        shares = int(m_shares.group(1).replace(",", ""))

    m_cost = re.search(r"買進價格\*\*:\s*([0-9]+(?:\.[0-9]+)?)", text)
    if m_cost:
        avg_cost = float(m_cost.group(1))

    if avg_cost is None:
        m_cost2 = re.search(r"均價\*\*:\s*([0-9]+(?:\.[0-9]+)?)", text)
        if m_cost2:
            avg_cost = float(m_cost2.group(1))

    return TradeInfo(shares=shares, avg_cost=avg_cost)


def to_zone(v: float) -> int:
    return int(round(v))


def split_position(shares: int | None) -> tuple[str, str]:
    if shares is None:
        return "（待填）", "（待填）"

    base = int(round(shares * 0.6 / 10.0) * 10)
    base = max(0, min(base, shares))
    op = shares - base
    return str(base), str(op)


def safe_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "", name)


def build_markdown(code: str, ticker: str, name: str, metrics: dict[str, float | str], trade: TradeInfo) -> str:
    base_pos, op_pos = split_position(trade.shares)

    avg_cost_text = f"{trade.avg_cost:.2f} 元" if trade.avg_cost is not None else "（待填）"
    shares_text = f"{trade.shares} 股" if trade.shares is not None else "（待填）"

    m = metrics
    sell_low = to_zone(float(m["sell_low"]))
    sell_high = to_zone(float(m["sell_high"]))
    buy_low = to_zone(float(m["buy_low"]))
    buy_high = to_zone(float(m["buy_high"]))
    deep_low = to_zone(float(m["deep_low"]))
    deep_high = to_zone(float(m["deep_high"]))
    stop = to_zone(float(m["stop_level"]))

    return f"""# {code} {name}｜零股滾動法實戰手冊（歷史分位數版）

> **更新日期**：{date.today().isoformat()}  
> **資料來源**：Yahoo Finance（`{ticker}`）  
> **參數日期**：{m['as_of']}  
> **目標**：用可重算波動參數定義賣買區，不靠主觀猜測

---

## 一、目前持倉（依交易紀錄）

| 項目 | 數值 |
|------|------|
| 標的 | {code} {name} |
| 總持股 | {shares_text} |
| 均價 | {avg_cost_text} |
| 現價（{m['as_of']}） | {float(m['last_close']):.2f} 元 |

---

## 二、模型輸入參數（{m['as_of']}）

| 參數 | 數值 | 說明 |
|------|------|------|
| 20MA（μ20） | {float(m['mean20']):.2f} | 近 20 日均衡價 |
| σ20 | {float(m['std20']):.2f} | 近 20 日波動標準差 |
| ATR14 | {float(m['atr14']):.2f} | 近 14 日平均真實波幅 |
| 日報酬波動率（20D） | {float(m['vol20_pct']):.2f}% | 近 20 日日報酬標準差 |
| 回檔中位數（dd50） | {float(m['dd50_pct']):.2f}% | 局部高點後 10 日回檔分位 |
| 回檔 70 分位（dd70） | {float(m['dd70_pct']):.2f}% | 常規回檔幅度 |
| 回檔 85 分位（dd85） | {float(m['dd85_pct']):.2f}% | 深回檔幅度 |

---

## 三、價位區間如何算

1. 賣出中心：`SellCenter = μ20 = {float(m['mean20']):.2f}`
2. 賣出區：`SellCenter ± 0.5*ATR14`  
   -> **{float(m['sell_low']):.2f} ~ {float(m['sell_high']):.2f}**
3. 買回區：以賣出中心乘上歷史回檔分位
   - 常規上緣（dd50）：**{float(m['buy_high']):.2f}**
   - 常規下緣（dd70）：**{float(m['buy_low']):.2f}**
4. 暫停位：`BuyLow - 0.8*ATR14`  
   -> **{float(m['stop_level']):.2f}**

> 實務掛單採整數價位：賣出 `{sell_low}~{sell_high}`、常規買回 `{buy_low}~{buy_high}`、深回檔 `{deep_low}~{deep_high}`、暫停 `{stop}`。

---

## 四、執行區間（本期）

### 1. 倉位拆分
- 底倉：{base_pos}（不動）
- 操作倉：{op_pos}（滾動）

### 2. 賣出操作倉
- **賣出區間（模型）**：**{sell_low} ~ {sell_high} 元**
- 觸發方式：收盤進入區間，隔日分批掛零股賣單

### 3. 買回操作倉
- **常規買回區**：**{buy_low} ~ {buy_high} 元**
- **深回檔加碼區**：**{deep_low} ~ {deep_high} 元**
- 目標：同筆資金買回股數 > 賣出股數

### 4. 停手與風控
- **暫停線**：**{stop} 元**（模型值 {float(m['stop_level']):.2f}）
- 若放量跌破暫停線，停止本輪滾動，保留現金等待下一次均值回歸

---

## 五、每輪結算模板

- 賣出：`__` 股，均價 `__` 元，淨回收 `__` 元  
- 買回：`__` 股，均價 `__` 元，總支出 `__` 元  
- 本輪股數變化：`__` 股  
- 本輪均價變化：`__` -> `__` 元  
- 是否達成「買回股數 > 賣出股數」：`是 / 否`
"""


def get_history(ticker: str, period: str, session: creq.Session) -> pd.DataFrame:
    df = yf.Ticker(ticker, session=session).history(period=period)
    if df is None or df.empty:
        raise RuntimeError(f"抓不到 {ticker} 的歷史資料")
    return df


def main() -> int:
    parser = argparse.ArgumentParser(description="重算零股滾動法的波動區間並輸出策略檔")
    parser.add_argument("--code", action="append", help="股票代碼，可重複或逗號分隔，例如 --code 5483,6488")
    parser.add_argument("--all", action="store_true", help="對 stocks.csv 全部代碼重算")
    parser.add_argument("--period", default="6mo", help="歷史區間，預設 6mo")
    parser.add_argument("--write", action="store_true", help="寫入 strategies/零股滾動法_實戰_{code}{name}.md")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    stocks_path = project_root / "stocks.csv"
    trades_dir = project_root / "trades"
    strategies_dir = project_root / "strategies"

    stocks = read_stocks_csv(stocks_path)

    if args.all:
        codes = list(stocks.index)
    else:
        codes = parse_codes(args.code)
        if not codes:
            raise SystemExit("請提供 --code 代碼，或使用 --all")

    session = creq.Session(verify=False, impersonate="chrome")

    ok = 0
    fail = 0

    for code in codes:
        if code not in stocks.index:
            print(f"[SKIP] {code}: stocks.csv 找不到")
            fail += 1
            continue

        row = stocks.loc[code]
        ticker = row["ticker"]
        name = str(row.get("name", code))

        try:
            df = get_history(ticker=ticker, period=args.period, session=session)
            metrics = compute_quantile_metrics(df)
            trade = parse_trade_info(find_trade_file(trades_dir, code))

            print(
                f"[{code}] as_of={metrics['as_of']} sell={to_zone(float(metrics['sell_low']))}-{to_zone(float(metrics['sell_high']))} "
                f"buy={to_zone(float(metrics['buy_low']))}-{to_zone(float(metrics['buy_high']))} stop={to_zone(float(metrics['stop_level']))}"
            )

            if args.write:
                md = build_markdown(code=code, ticker=ticker, name=name, metrics=metrics, trade=trade)
                filename = f"零股滾動法_實戰_{code}{safe_name(name)}.md"
                out = strategies_dir / filename
                out.write_text(md, encoding="utf-8")
                print(f"  -> 已寫入: {out}")

            ok += 1
        except Exception as err:
            print(f"[FAIL] {code}: {err}")
            fail += 1

    print(f"\n完成: success={ok}, fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())


