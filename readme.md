# 📈 股票筆記本 — 操作速查表

> 忘了怎麼用？從這裡找答案。詳細 SOP 見 `AI_Workflow_SOP.md`。

---

## ⚡ 每日例行（14:35 已自動執行，不用管）

| 腳本自動做的事 | 產生的檔案 |
|--------------|-----------|
| 所有持倉健診（現價 / 月線 / 損益 / 三桶佔比）| `持倉健診_YYYY-MM-DD.md` |
| 淨值快照寫入歷史 | `portfolio_history.csv` |
| Watchlist 觸發訊號掃描 | `journals/logs/YYYY-MM-DD_scan.log` |

**每天只需要做一件事**：打開 `持倉健診_YYYY-MM-DD.md` 看一眼有無 ⚠️ 預警。

---

## 🤖 AI 協作 Slash 指令

| 指令 | 使用時機 |
|------|---------|
| `/daily-review` | 有預警標的、想寫盤後日誌時 |
| `/fill-trades` | 新建持倉後，基本資訊欄位空白時 |
| `/new-position {代號}` | 想買新標的，進場前做完整分析 |

---

## 🛠️ 手動執行腳本（需要時才跑）

```bash
# 手動觸發持倉健診
python scripts/portfolio_report.py

# 手動觸發淨值快照
python scripts/portfolio_log.py

# 手動觸發 Watchlist 掃描
python scripts/watchlist_scan.py

# 查單一股票現價 / 月線 / 殖利率
python scripts/stock_analyzer.py --ticker 2330

# 查多檔成交量（評估流動性）
python scripts/vol_check.py --ticker 2002 6488
```

---

## 📁 目錄地圖

| 目錄 / 檔案 | 用途 |
|------------|------|
| `trades/` | 每筆持倉的策略與停損記錄 |
| `trades/template.md` | 新倉建檔範本 |
| `watchlist/` | 候補股追蹤（量化觸發條件） |
| `journals/` | 盤後日誌 |
| `journals/logs/` | 腳本每日執行 log |
| `strategies/` | 交易策略文件 |
| `capital/capital_config.md` | 三桶資金快照（需定期手動更新） |
| `.brain/rules.md` | AI 行為準則（停損規則 / 分析風格） |
| `.brain/capital_management_rules.md` | 三桶定義 / 風險計算公式 / AI 執行指令 |
| `portfolio_history.csv` | 每日淨值歷史記錄 |
| `持倉健診_YYYY-MM-DD.md` | 每日持倉看板（最常開的檔案） |

---

## 💼 資金桶快速回憶

| 桶別 | 目標佔比 | 上限 | 內容 |
|------|---------|------|------|
| Core（底倉水庫）| 50% | — | ETF、高殖利率存股 |
| Tactical（戰術水管）| 30% | **35%** | 波段操作、零股滾動 |
| Cash（銀彈消防栓）| 20% | 下限 10% | 恐慌備用金 |

> 詳細規則見 `.brain/capital_management_rules.md`

---

## 📋 什麼時候要更新哪個檔案

| 情境 | 要更新的檔案 |
|------|------------|
| 買進 / 賣出 | `trades/{代號}.md` — 記錄操作與損益 |
| 看法改變 / 停損線修正 | `trades/{代號}.md` — 更新策略區塊 |
| 月底資金盤點 | `capital/capital_config.md` — 更新 Section 0 快照 |
| 投資邏輯出現新規則 | `.brain/rules.md` |
| 三桶比例或風險公式要調整 | `.brain/capital_management_rules.md` |