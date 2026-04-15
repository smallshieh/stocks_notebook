# 股票筆記本 — Claude 專案指令

## Python 環境
- **一律使用 `.venv`**：`S:\股票筆記\.venv\Scripts\python.exe`（已裝 yfinance、notion-client、curl_cffi、pandas、numpy）
- Anaconda 備用、不主動切換

## Yahoo Finance
- yfinance 必須注入 curl_cffi session 繞過 SSL：
  ```python
  from curl_cffi import requests as creq
  import yfinance as yf
  session = creq.Session(verify=False, impersonate='chrome')
  df = yf.Ticker('6488.TWO', session=session).history(period='6mo')
  ```
- ticker：TSE 用 `.TW`，OTC 用 `.TWO`；**不要硬編碼**，從 `stocks.csv` 讀取（`set_index('code')`）

## 關鍵路徑
- 當週戰術指南：`journals/戰術指南.md`（固定檔名，備份為 `戰術指南_{YYYY-MM-DD}.md`）
- Notion 同步：`.venv/Scripts/python.exe scripts/sync_to_notion.py <檔案路徑>`（憑證 `scripts/notion_creds.py`，已 gitignore）

## 工作流程
- 修改 `trades/` 或 `journals/` 重要檔案後，主動提示同步 Notion
- 不自行猜測數字（股數、均價、資金）— 從 MD 檔讀取或詢問用戶
- 收到新聞/財經資訊 → 依 [.claude/docs/news-routing.md](.claude/docs/news-routing.md) 路由，勿自行決定寫入位置
- 評估減持配息股前 → 先跑 [.claude/docs/divest-checklist.md](.claude/docs/divest-checklist.md) 三行計算
- 標的完全出場後 → 依 [strategies/trade_lessons.md](strategies/trade_lessons.md) 開頭 SOP 萃取 lesson 並刪除 trades 檔，不保留歸檔資料夾
