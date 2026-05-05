# 戰術指南過期條件檢查

## 目的

每日盤後檢查 `journals/戰術指南.md` 是否殘留已完成、已全清、已失效或與來源檔不一致的條件。

戰術指南只應保留當週 dashboard：
- P1：今日優先處理或高風險監控
- P2：非 P1 持倉摘要
- 建倉候補摘要
- 價格警示清單

完整 SOP、歷史原因、已完成交易應寫回 `trades/`、`watchlist/` 或當日盤後日誌。

## 腳本

```powershell
.venv/Scripts/python.exe scripts/check_tactical_guide_stale.py --json
```

## 觸發後處理

若輸出 `status: alert` 或 `status: warning`：
1. 先讀 `targets[].detail.evidence` 確認是哪一列過期。
2. 檢查對應 `trades/` 或 `watchlist/` 是否為最新 source of truth。
3. 修正 `journals/戰術指南.md`：
   - P1 完成或失效：移出 P1。
   - P2 完成語氣：改寫成目前有效監控條件。
   - 價格警示過期：刪除或改成底倉防守。
4. 修正後重新執行本腳本，確認無高嚴重度警示。

## 常見警示

- P1 待執行數量與 P1 表格列數不一致
- 同一標的同時出現在 P1 與 P2
- 來源檔顯示操作倉已全清，但戰術指南仍要求賣出操作倉
- 價格警示表保留已失效的反彈出場價
- 總經/產業舊訊息被留在戰術指南
