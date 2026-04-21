---
description: 每日盤後深度檢視（市場狀態 → 讀 log → 資金桶稽核 → 預警建議 → 建日誌）
---

## 步驟

1. 取得今天日期（格式：YYYY-MM-DD），以下以 `{TODAY}` 代稱。

2. **MD 讀取規則**：
   - `持倉健診_{TODAY}.md`、`journals/logs/{TODAY}_scan.log` 屬於腳本輸出的短報告，可直接讀取。
   - 若流程中需要讀 `journals/戰術指南.md`、`trades/*.md`、`watchlist/*.md`，必須先用結構化工具列 outline，再只讀相關 section：
     ```powershell
     .\.venv\Scripts\python.exe scripts\md_outline.py trades\{檔名}.md
     .\.venv\Scripts\python.exe scripts\md_section.py trades\{檔名}.md "基本資訊"
     ```
   - 只有在 outline 缺失、標題歧義、格式損壞，或必要資訊無法定位時，才讀完整 MD。
   - 工具完整說明見 `scripts/MD_TOOLS_FOR_AGENTS.md`。

3. **確認大盤狀態**（所有個股決策的上下文）：
   執行：
   ```powershell
   .\.venv\Scripts\python.exe scripts/market_state.py
   ```
   記錄以下三項，供後續步驟使用：
   - **市場狀態**（多頭確立 / 多頭震盪 / 盤整 / 空頭初期 / 空頭確立 / 危機）
   - **建議配置**（Core % / Tactical % / Cash %）
   - **操作指引**（攻擊 / 平衡 / 防禦）

   > 若腳本執行失敗（網路問題），以最近一次已知狀態繼續，並在日誌加上 ⚠️ 大盤狀態未更新。

4. 讀取 `.brain/capital_management_rules.md`，載入三桶定義與稽核規則（第 1 節）及 AI 執行指令（第 5 節）。

5. 確認健診檔案並自動產生（若尚未產生）：
   - 優先讀取 `持倉健診_{TODAY}.md`
   - 若不存在，判斷原因：
     - **今日為週末或國定假日（休市）** → 輸出：`今日休市，daily-review 無需執行。下次執行日：{下一個交易日}。` 並**中止**
     - **今日為交易日但健診未產生** →
       1. 詢問用戶：「今日現金增減多少元？（正數 = 增加，負數 = 減少，0 = 不變；例如賣股後 +174563、買股後 -50000）」
       2. 以 PowerShell 執行：
          ```powershell
          .\.venv\Scripts\python.exe scripts/portfolio_report.py --cash-delta={用戶輸入增減量}
          ```
          腳本會自動讀取前次現金餘額並加減計算。
       3. 執行完成後，讀取新產生的 `持倉健診_{TODAY}.md`，繼續後續步驟（不中止）
       4. 若用戶回答「不知道」或「0」，以 `--cash-delta=0` 執行並在日誌加上 ⚠️ 現金未確認，沿用前次值

6. 依 `capital_config.md` 第 0 節的桶別歸屬表，計算目前 Core / Tactical 市值佔比。
   - 對照步驟 3 的**建議配置**，輸出偏離說明：
     ```
     目前 Core XX% vs 建議 XX%（{市場狀態}下）
     目前 Tactical XX% vs 建議 XX%
     ```
   - 若 Tactical 佔比 > 35%，在回覆**首行**輸出：`⚠️ 資金越權警告：Tactical 超過 35% 上限`

7. 取得預警標的（依序嘗試）：
   - **優先**：讀取 `journals/logs/{TODAY}_scan.log`，提取 ⚠️ 預警行
   - **若 log 不存在**：直接使用步驟 5 健診檔的「需要注意的標的」表格，標注 `（來源：健診檔，無 scan.log）`
   - 兩者均無預警標的時，輸出：`今日無預警標的`

8. 針對每個預警標的，給出以下格式的操作建議，並**結合步驟 3 的市場狀態調整力道**：
   ```
   ### [{代號}] {名稱}
   - 現況：現價 vs 月線、損益%
   - 桶別：Core / Tactical
   - 市場狀態調整：（例如：空頭初期 → 建議保守，不加碼）
   - 建議：減碼 / 觀察 / 停損（說明理由）
   ```

9. 建立或更新 `journals/{TODAY}_盤後日誌.md`，格式如下：
   ```markdown
   # {TODAY} 盤後日誌
   ## 大盤狀態
   （貼入步驟 3 的 Markdown 段落）
   ## 資金配置偏離
   （步驟 6 的偏離說明）
   ## 預警標的處置
   （貼入步驟 8 的建議）
   ## 待辦事項
   - [ ]（依建議自動生成）
   ```

10. 輸出摘要：市場狀態、建議配置、今日預警數量、資金桶狀態、已建日誌路徑。

11. **執行 post-daily-review hooks**：
    - 掃描 `.agents/hooks/post-daily-review/` 目錄下所有 `.md` 檔（**跳過**底線 `_` 開頭的檔案）
    - 讀取 `.agents/hooks/post-daily-review/_state.json`，取得每個 hook 的 `last_run` 日期
    - 對每個 hook `.md` 檔：
      a. 解析 frontmatter 的 `trigger` 欄位
      b. **判斷是否觸發**：
         - `every_n_trading_days`：計算 `{TODAY}` 與 `last_run` 之間的**交易日數**（排除週末；若無 last_run 視為已到期）
         - 若交易日數 < `n` → 跳過此 hook
      c. **執行**：以 PowerShell 執行 frontmatter `script` 欄位的指令，擷取 stdout 輸出
      d. **寫入日誌**：將 `alert_prefix` + 輸出追加至步驟 9 日誌的 `## 待辦事項` 之前，格式：
         ```markdown
         ## Hooks
         - {alert_prefix} #{run_count}: {script stdout}
         ```
      e. **更新 state**：寫入 `_state.json`：
         ```json
         { "hook-name": { "last_run": "{TODAY}", "run_count": N, "last_output": "..." } }
         ```
      f. **警示落地（強制）**：檢查 script stdout 是否包含警示關鍵字（`⚠️`、`已達.*門檻`、`建議評估`）：
         - **有警示** → 讀取該 hook `.md` 的 `### Agent 執行指令` 區塊（若存在），**依指令更新 `journals/戰術指南.md`**（P1 / P2），並在日誌該 hook 行末追加 `→ 已更新戰術指南`
         - **無 Agent 執行指令區塊** → 在日誌標記 `→ 需人工確認`，提醒用戶
         - **無警示** → 不動作，只保留日誌紀錄
    - 若無任何 hook 觸發 → 不輸出、不修改日誌
    - 若某 hook 腳本執行失敗 → 在日誌記錄 `⚠️ {hook name} 執行失敗：{error}`，繼續處理下一個 hook
    - 在步驟 10 的摘要末尾追加：`Hooks: 已觸發 N 個` 或 `Hooks: 無觸發`
