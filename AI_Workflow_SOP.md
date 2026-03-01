# 🤖 AI 協作最佳實踐 (股票筆記本 SOP)

> ⚡ **重要前提**：持倉健診、淨值記錄、watchlist 掃描已在每個工作日 14:35 **全自動執行**。
> 請先查看當天的 `持倉健診_YYYY-MM-DD.md` 與 `journals/logs/` 的 log，
> 再決定是否需要 AI 介入，避免浪費 tokens。

---

## 📅 情境一：每日盤後深度檢視

**觸發時機**：自動掃描有預警標的，或想撰寫盤後日誌時。

> **Prompt 範本：**
> 「請依序讀取：
> 1. `capital/capital_config.md`（資金桶定義與稽核規則）
> 2. `持倉健診_今日.md`（現價 / 月線 / 損益）
> 3. `journals/logs/今日_scan.log`（原始掃描紀錄）
>
> 依 capital_config.md 第 5 節執行資金桶稽核，再針對预警標的給出操作建議，
> 最後建立今天的盤後日誌 `journals/YYYY-MM-DD_盤後日誌.md`。」

**💡 AI 會做什麼：**
1. 讀取 `capital_config.md`，核算三桶佔比是否偏離 10 個百分點以上，若有則首行發出 ⚠️ 資金越權警告。
2. 讀取掃描結果，不重複抓取已有的數據。
3. 針對 ⚠️ 停損 / 跌破月線標的給出操作建議（減碼 / 觀察 / 停損）。
4. 建立盤後日誌，填入大盤數據與待辦事項。

---

## 🔎 情境二：買進前標的分析

**觸發時機**：有感興趣的新標的，想在進場前做完整評估。

> **Prompt 範本：**
> 「我想分析 [股票代號]，請執行 `stock_analyzer.py --ticker [代號]` 取得現價與月線，
> 再幫我查近期法人籌碼動態。若評估偏向進場，請草擬一份 `/trades` 筆記。」

**💡 AI 會做什麼：**
1. 執行腳本取得現價、月線、殖利率（不需 AI 自己搜尋）。
2. 搜尋法人買賣超、外資評等等質化資訊。
3. 使用 `trades/template.md` 建檔，填入原因、停損參考價。

---

## 🛠️ 情境三：策略設計

**觸發時機**：想把交易心得量化成可重複執行的策略。

> **Prompt 範本：**
> 「我想建立名為『[策略名稱]』的策略，核心邏輯是 [你的想法]。
> 請用 `/strategies` 模板建立文件，並試寫一段回測腳本放入 `/scripts`。」

**💡 AI 會做什麼：**
1. 將感性想法轉成明確的進出場規則，存入 `strategies/`。
2. 產出 `backtest_[策略名稱].py` 供歷史驗證。

---

## 📉 情境四：個股成交量查詢

**觸發時機**：評估流動性、決定能否快速出場時。

直接自己執行，不需 AI：
```bash
python scripts/vol_check.py --ticker 2002 6488
```

輸出：日均成交量、日均成交值（億元）、近 3 月最高 / 最低 / 波動幅度。

---

## 📋 情境五：更新 trades 基本資訊空欄位

**觸發時機**：新建持倉筆記後，`目前價格`、`月線 (20MA) 位置`、`預估殖利率` 等欄位仍是空白時。

> **前提**：先確認今日 `journals/logs/YYYY-MM-DD_scan.log` 或 `持倉健診_YYYY-MM-DD.md` 已產生。

> **Prompt 範本：**
> 「請讀取 `持倉健診_今日.md`，將裡面的現價、20MA、殖利率，
> 填進 `trades/` 下各個基本資訊欄位**仍為空白**的 MD 檔。
> 已有數值的欄位不要覆蓋。」

**💡 AI 會做什麼：**
1. 讀取 `持倉健診_YYYY-MM-DD.md`（數字來源，不再重複呼叫 API）。
2. 逐一比對 `trades/*.md`，只更新「目前價格 / 月線 / 殖利率」三個空欄位。
3. 已有值的欄位、策略分析、操作紀錄等內容**完全不動**。

> ⚠️ **注意**：此動作建議每次只在新建持倉後執行一次，後續日常數據以
> `持倉健診_YYYY-MM-DD.md` 為主要看板，不需每日回寫 trades MD。

---

## 🤖 AI Workflow 速查（`/` 指令）

| 指令 | 用途 | Workflow 定義 |
|------|------|--------------|
| `/daily-review` | 每日盤後深度檢視（資金稽核 + 日誌） | `.agents/workflows/daily-review.md` |
| `/new-position` | 新標的建倉分析 + trades 筆記建檔 | `.agents/workflows/new-position.md` |
| `/fill-trades` | 補填 trades MD 的空白欄位 | `.agents/workflows/fill-trades.md` |
| `/new-tactical` | 建立 10 日戰術指南（備份 → 分析 → 同步 Notion） | `.agents/workflows/new-tactical.md` |

---

## ⌨️ 腳本速查

| 指令 | 用途 |
|------|------|
| `python scripts/stock_analyzer.py --ticker 2330` | 🔎 查單一股票現價 / 月線 / 殖利率 |
| `python scripts/stock_analyzer.py --scan-trades` | ⚠️ 掃描全部持股停損狀態 |
| `python scripts/vol_check.py --ticker 代號 [代號...]` | 📉 查成交量與波動（可多檔） |
| `python scripts/portfolio_report.py` | 🏥 手動觸發持倉健診（平日 14:35 已自動） |
| `python scripts/portfolio_log.py` | 📊 手動觸發淨值快照（平日 14:35 已自動） |
| `python scripts/watchlist_scan.py` | 🔍 手動觸發 watchlist 掃描（平日 14:35 已自動） |
| `python scripts/sync_to_notion.py` | ☁️ 手動同步 10日戰術指南至 Notion |
