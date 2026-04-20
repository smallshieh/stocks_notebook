---
description: 從持倉健診報告刷新 trades/ 下目前價格、20MA、殖利率
---

## 使用方式

```powershell
/update-trade-prices
/update-trade-prices --code 1210
```

---

## 步驟

1. 確認今日或最近一份 `持倉健診_{YYYY-MM-DD}.md` 已存在。
   - 若不存在，先執行：
     ```powershell
     .\.venv\Scripts\python.exe scripts\portfolio_report.py
     ```

2. 先 dry-run，檢查會改哪些檔案與欄位：
   ```powershell
   .\.venv\Scripts\python.exe scripts\update_trade_prices.py
   ```

3. 檢查輸出清單，只允許更新以下欄位：
   - `目前價格`
   - `月線 (20MA) 位置`
   - `預估殖利率` / `現價殖利率` / `殖利率`

4. 確認沒有改到買進均價、集保股數、總成本、交易紀錄、停損預警、策略規劃後，才正式寫入：
   ```powershell
   .\.venv\Scripts\python.exe scripts\update_trade_prices.py --write
   ```

5. 若只更新單一代號：
   ```powershell
   .\.venv\Scripts\python.exe scripts\update_trade_prices.py --code 1210
   .\.venv\Scripts\python.exe scripts\update_trade_prices.py --code 1210 --write
   ```

6. 輸出摘要：
   - 更新幾個檔案
   - 跳過哪些檔案與原因
   - 是否需要同步 Notion

---

## 注意事項

- 這個 workflow 會覆蓋市場欄位；若只是補空白，請改用 `/fill-trades`。
- 腳本只改 `## 基本資訊` 區塊；舊格式沒有 `## 基本資訊` 但開頭 metadata 有欄位者，只改檔案開頭到第一個 H2 前的區塊。
- 此 workflow 是「機械欄位更新」例外；一般 section 內容仍由 LLM 判斷與撰寫，scripts 只負責定位、讀取、dry-run 與安全替換。
- 結構化讀寫原則見 `scripts/MD_TOOLS_FOR_AGENTS.md`。
- `2379` 這類已清倉或不在健診報告的標的會跳過。
- 修改 `trades/*.md` 後，詢問用戶是否同步 Notion。
