# 股票筆記本 — Codex 專案指令

## Python 環境
- **永遠使用 `.venv`**：`S:\股票筆記\.venv\Scripts\python.exe`
- `.venv` 已安裝：yfinance、notion-client、curl_cffi、pandas、numpy
- Anaconda 僅備用，不主動使用

## Yahoo Finance 資料抓取
- yfinance 可用，但需注入 curl_cffi session 繞過 SSL 問題：
  ```python
  from curl_cffi import requests as creq
  import yfinance as yf
  session = creq.Session(verify=False, impersonate='chrome')
  df = yf.Ticker('6488.TWO', session=session).history(period='6mo')
  ```
- ticker 格式：上市（TSE）用 `.TW`，上櫃（OTC）用 `.TWO`
- **不要硬編碼 ticker**，從 `stocks.csv` 讀取：
  ```python
  import pandas as pd
  stocks = pd.read_csv('stocks.csv', dtype=str).set_index('code')
  ticker = stocks.loc['6488', 'ticker']  # → '6488.TWO'
  ```

## Notion 同步
- 同步指令：`.venv/Scripts/python.exe scripts/sync_to_notion.py <檔案路徑>`
- 每次修改重要 MD 檔後，詢問用戶是否同步 Notion
- 憑證在 `scripts/notion_creds.py`（已 gitignore）

## 個股基本資料
- **6488 環球晶**：上櫃股（OTC），ticker `6488.TWO`

## 戰術指南
- 當週戰術指南：`journals/戰術指南.md`（固定檔名，每週覆寫）
- 備份命名：`journals/戰術指南_{YYYY-MM-DD}.md`

## 新聞與資訊消化規範

當用戶提供財經新聞、網路資訊、或由 agent 主動抓取資訊時，依以下規則處理：

### 分類與寫入位置

| 類型 | 寫入位置 | 區塊名稱 |
|------|---------|---------|
| 個股相關（財報、法說、產品、人事） | 對應 `trades/` 或 `watchlist/` 的 .md | `## 重要事件與催化劑` |
| 總經 / 產業面（央行、匯率、產業趨勢） | `journals/YYYY-MM-DD_盤後日誌.md` | `## 總經與產業訊號` |
| 足以改變操作方向的重大事件 | `journals/戰術指南.md` 對應標的處加註 | 直接修改觸發條件或備註 |

### 個股催化劑表格格式

在 `## 重要事件與催化劑` 區塊下，使用四欄表格：

```markdown
| 日期 | 事件 | 影響評估 | 行動 |
|------|------|---------|------|
| 2026-03-14 | Q1 營收 MoM +12% | 🟢 優於預期 | 維持持有 |
```

- 若該 .md 尚無此區塊，在 `## 倉位規劃` 之前插入
- 影響評估用 🔴🟡🟢 標示嚴重程度

### 總經訊號格式

```markdown
## 總經與產業訊號
- **Fed**: 鮑威爾暗示年中降息，美債殖利率回落 → 利多成長股
- **半導體**: ASML 訂單指引上修 → 設備股留意
```

### 禁止事項
- **不存原文**：只記消化後的摘要與影響評估
- **不存來源連結**：關鍵字句足以回查，不需要 URL
- **不做無結論的剪報**：每則資訊必須回答「對持倉有什麼影響？需要什麼行動？」
- **不另開 news/ 資料夾**：所有資訊歸入現有結構

### 資訊→決策閉環（來源 D 路徑）

歸檔只是第一步。寫入後，資訊如何影響決策：

```
用戶輸入新聞 / Hook 高嚴重度警示（論點到期、硬死線）
      ↓
分類（個股 / 總經 / 重大事件 / 系統警示）
      ↓
寫入正確位置（trades/ / 日誌 / 戰術指南）
      ↓
daily-review 步驟 7.5「Hook 前置掃描」
　→ 收集高嚴重度 Hook 警示（暫不寫檔）
      ↓
daily-review 步驟 8「整體研判（四源合議）」
　→ 來源 D 收集：
　    ① 步驟 7.5 的 Hook 高嚴重度警示
　    ② 盤後日誌的 ## 總經與產業訊號
　    ③ 受影響標的的 ## 重要事件與催化劑 最新列
　→ Agent 評估對整體操作方向的影響
      ↓
若為重大負面事件 / 高嚴重度 Hook → 整體方向強制切「守」
若為重大正面催化              → 整體方向可上調一級（需說明理由）
```

**即時處理路徑（daily-review 之外）**：
若用戶在非 daily-review 時間輸入重大事件（如法說當下、突發消息），Agent 應：
1. 立即依分類寫入正確位置
2. 若事件等級「足以改變操作方向」（🔴），**同步更新戰術指南的觸發條件或 P1/P2 動作說明**，不等到 daily-review
3. 告知用戶：「已更新戰術指南，明日 daily-review 將納入四源合議」

## 每日決策架構腳本（daily-review 四源合議）

| 步驟 | 腳本 | 提供訊號 | 性質 |
|------|------|---------|------|
| 3 | `market_state.py` | 來源 A：大盤狀態 | 自動執行 |
| 7 | `chip_check.py` | 來源 B：法人籌碼 + A/B/C/D 情境 | 自動執行（TWSE API）|
| 5 / scan.log | `wave_score_scan.py` | 來源 C：Wave Score 分布 | 自動執行 |
| 7.5 | Hook 前置掃描 | 來源 D①：高嚴重度系統警示 | Agent 執行 |
| 日誌/trades | 用戶輸入 | 來源 D②③：新聞事件 / 催化劑 | 手動輸入 |

> 步驟 8 Agent 把以上五路輸入合議成**整體操作方向（攻/守/觀察）**，再驅動個股決策。

## 工作流程
- 修改 trades/ 或 journals/ 重要檔案後，主動提示同步 Notion
- 執行腳本前先確認使用 `.venv`
- 不要自行猜測數字（股數、均價、資金）— 從 MD 檔讀取或詢問用戶
