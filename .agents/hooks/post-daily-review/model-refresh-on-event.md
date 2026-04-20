---
name: 事件驅動模型刷新
trigger:
  type: every_n_trading_days
  n: 1
script: .venv/Scripts/python.exe scripts/model_refresh.py --from-events
output_to: journal
alert_prefix: "🔄 模型刷新"
---

## 說明

讀取當日 `scan.log` 中由 `event_detector.py` 寫入的 `🔔 EVENT` 行，
對命中事件的標的重算並更新以下兩個 MD section：

- `## GBM 預估` — μ/σ、60 日期望價、各目標 / 停損到達機率
- `## 物理診斷` — 動量 p、溫度 T、流體狀態、分位數區間

### 觸發條件

由 `event_detector.py`（`daily_scan.bat` 第 5 步）負責偵測，
本 hook 只負責「對命中事件的股票執行 Layer 2 模型刷新」。

若當日 scan.log 無 EVENT 紀錄，本 hook 輸出提示後靜默結束（不更新任何檔案）。

### 輸出格式

```
[model-refresh] 2026-04-20 — 從 EVENT 取得 N 個標的：XXXX, YYYY
  ✅ XXXX: 已更新 GBM 預估 + 物理診斷（μ=+24.8%，ATR=1.86）
  ✅ YYYY: 已更新 物理診斷（μ=+52.4%，ATR=6.07）
```

### 不更新的情況

- 該標的 MD 中找不到對應 section（例如 ETF、配息股通常無 GBM 預估區塊）→ 跳過，不報錯
- 行情資料抓取失敗 → 標記 ❌，不更新，下次 daily-review 重試
