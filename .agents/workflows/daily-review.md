---
description: 每日盤後深度檢視（市場狀態 → 讀 log → 資金桶稽核 → 預警建議 → 建日誌）
---

## 步驟

1. 決定本次盤後歸屬日期（格式：YYYY-MM-DD），以下以 `{REVIEW_DATE}` 代稱。
   - 正常當日執行：`{REVIEW_DATE}` = 今天。
   - 午夜後或隔日補執行：必須指定實際盤後日期，例如 `2026-05-04`，不得直接使用系統日期。
   - 執行腳本前先設定：
     ```powershell
     $env:REVIEW_DATE = "{REVIEW_DATE}"
     ```
   - 若要重建 scan.log：
     ```powershell
     .\scripts\daily_scan.bat {REVIEW_DATE}
     ```

2. **MD 讀取規則**：
   - `持倉健診_{REVIEW_DATE}.md`、`journals/logs/{REVIEW_DATE}_scan.log` 屬於腳本輸出的短報告，可直接讀取。
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
   - 優先讀取 `持倉健診_{REVIEW_DATE}.md`
   - 若不存在，判斷原因：
     - **今日為週末或國定假日（休市）** → 輸出：`今日休市，daily-review 無需執行。下次執行日：{下一個交易日}。` 並**中止**
     - **今日為交易日但健診未產生** →
       1. 詢問用戶：「今日現金增減多少元？（正數 = 增加，負數 = 減少，0 = 不變；例如賣股後 +174563、買股後 -50000）」
       2. 以 PowerShell 執行：
          ```powershell
          .\.venv\Scripts\python.exe scripts/portfolio_report.py --date={REVIEW_DATE} --cash-delta={用戶輸入增減量}
          ```
          腳本會自動讀取前次現金餘額並加減計算。
       3. 執行完成後，讀取新產生的 `持倉健診_{REVIEW_DATE}.md`，繼續後續步驟（不中止）
       4. 若用戶回答「不知道」或「0」，以 `--cash-delta=0` 執行並在日誌加上 ⚠️ 現金未確認，沿用前次值

6. 依 `capital_config.md` 第 0 節的桶別歸屬表，計算目前 Core / Tactical 市值佔比。
   - 對照步驟 3 的**建議配置**，輸出偏離說明：
     ```
     目前 Core XX% vs 建議 XX%（{市場狀態}下）
     目前 Tactical XX% vs 建議 XX%
     ```
   - 若 Tactical 佔比 > 35%，在回覆**首行**輸出：`⚠️ 資金越權警告：Tactical 超過 35% 上限`

7. **核對法人籌碼觸發條件**（若戰術指南內有「📡 法人籌碼觸發條件」表）：
   執行：
   ```powershell
   .\.venv\Scripts\python.exe scripts\chip_check.py --date={REVIEW_DATE}
   ```
   - 腳本自動抓取 TWSE 當日三大法人買賣超金額，並對照 A/B/C/D 情境
   - 若命中任一情境：
     - 在盤後日誌 `## 待辦事項` 加入對應操作的 `- [ ]`
     - 同步更新戰術指南 P1/P2 的相關標的動作說明
     - 更新戰術指南觸發表「觸發日」欄位為 `{REVIEW_DATE}`
   - 若腳本執行失敗（TWSE API 異常）：記錄 `⚠️ 籌碼資料未取得，核對跳過`，不中止流程
   - 將腳本輸出的 Markdown 段落附加至盤後日誌 `## 總經與產業訊號` → `### 三大法人籌碼` 子區塊

7.5. **Hook 統一執行（hook_runner.py）**：
    執行 hook 引擎，自動判斷哪些 hook 今日到期、執行腳本、收集結構化結果：
    ```powershell
    .\.venv\Scripts\python.exe scripts/hook_runner.py
    ```
    hook_runner.py 會：
    - 讀取 `.agents/hooks/post-daily-review/hooks.yaml` 取得所有 hook 定義
    - 讀取 `.agents/hooks/post-daily-review/hooks_state.json` 判斷排程到期與生命週期
    - 執行到期 hook 的腳本、解析 JSON stdout
    - 更新 hooks_state.json（last_run, status, lifecycle changes）
    - 將結果輸出到 `journals/logs/{REVIEW_DATE}_hooks.json`

    讀取 `journals/logs/{REVIEW_DATE}_hooks.json`，取得本日觸發結果。

    高嚴重度判斷（以下任一，供步驟 8 的來源 D①）：
    - `severity: high` 且 `status: alert` 的 hook 結果
    - 連 3 次失敗的 hook（hooks_state.json 中 `consecutive_failures >= 3`）
    - 論點到期（thesis-expiry 輸出 overdue 項目）
    - 資金越權（Tactical > 35%）/ 硬死線到期

8. **整體研判（四源合議）**：
   在處理任何個股之前，先綜合以下四個來源，**用一段結構化文字形成今日整體判斷**：
   - **來源 A**：步驟 3 的市場狀態（多頭確立 / 震盪 / 空頭…）
   - **來源 B**：步驟 7 的法人籌碼（外資方向、法人一致性、命中情境）
   - **來源 C**：步驟 5 健診檔 / scan.log 中的訊號診斷分布（策略類型 / 趨勢 / 位置 / 動能 / 品質）
   - **來源 D**：今日事件彙整，從以下位置收集：
     - 步驟 7.5 的 **Hook 高嚴重度警示**（論點到期 / 資金越權 / 硬死線）
     - 當日盤後日誌的 `## 總經與產業訊號` 區塊（用戶或 Agent 輸入的財經新聞）
     - 受影響標的的 `## 重要事件與催化劑` 最新一列
     - 若當日日誌尚未建立，詢問用戶：「今日有無重要財經消息？」（可直接貼文字）

   輸出格式（寫入盤後日誌 `## 整體研判` 區塊，置於預警標的之前）：

   ```markdown
   ## 整體研判

   **今日市場定性**：（一句話，例如：外資連買 + 大盤多頭確立，高位強籌碼格局）

   **四源一致性**：
   - 大盤：🚀 多頭確立（均線分數 5/5）
   - 籌碼：🟢 外資 +60 億，法人共買；情境 A 接近觸發（連 2 日）
   - Wave：🟡 多數標的在賣出區趨勢延伸，動能仍強但需等爆量收黑
   - 新聞事件：🟢 / 🟡 / 🔴（一句話：關鍵事件 + 對整體方向的影響評估）

   **整體操作方向**：攻 / 守 / 觀察（三選一，加一句理由）

   **今日決策框架**：
   > 根據以上研判，本日個股操作應以「…」為主軸。
   > 重點觀察順序：①… ②… ③…
   ```

   研判規則（Agent 應遵循）：
   - **四源一致看多** → 整體方向「攻」，波段倉抱住，停利不提前
   - **大盤多頭 + 籌碼賣超** → 整體方向「觀察」，不加倉，等籌碼回穩
   - **大盤震盪 + 法人分歧** → 整體方向「守」，優先處理 P1/預警標的
   - **任一來源出現危機訊號（如外資大賣超 ≥ 30 億 + 收黑）** → 整體方向強制切「守」，不論其他訊號
   - **來源 D 出現重大負面事件**（Fed 意外升息、地緣衝突升級、重要客戶砍單）→ 整體方向強制切「守」，Wave/籌碼看多不抵銷
   - **來源 D 出現重大正面催化**（法說上修、法人升評、政策利多）→ 可在整體方向上加一級（觀察→攻、守→觀察），但需說明理由
   - 整體方向確定後，步驟 10 的個股建議**必須符合整體方向**；若有衝突，以整體方向為優先，並說明原因

9. 取得預警標的（依序嘗試）：
   - **前置：讀取 `scripts/_entry_alerts.json`（N 計畫未處理警示）**：
     - 若檔案存在，讀取 `alerts` 陣列，篩選出 `triggered_at` 在過去 7 天內的項目
     - 在預警清單**最前面**插入（每個 alert 一行）：
       ```
       📌 N計畫未處理警示（{triggered_at}）：[{code}] {name} {plan}-{condition_label} → {action}
       ```
     - 同一天、同代號、同 label 的警示只顯示一次
   - **優先**：讀取 `journals/logs/{REVIEW_DATE}_scan.log`，提取 ⚠️ 預警行
   - **若 log 不存在**：直接使用步驟 5 健診檔的「需要注意的標的」表格，標注 `（來源：健診檔，無 scan.log）`
   - 所有來源均無預警標的時，輸出：`今日無預警標的`

10. 針對每個預警標的，給出以下格式的操作建議，並**結合步驟 8 的整體研判方向調整力道**：
   ```
   ### [{代號}] {名稱}
   - 現況：現價 vs 月線、損益%
   - 桶別：Core / Tactical
   - 整體研判一致性：（本標的建議是否符合整體方向？若衝突說明原因）
   - 建議：減碼 / 觀察 / 停損（說明理由）
   ```

11. 建立或更新 `journals/{REVIEW_DATE}_盤後日誌.md`，格式如下：
   ```markdown
   # {REVIEW_DATE} 盤後日誌
   ## 大盤狀態
   （貼入步驟 3 的 Markdown 段落）
   ## 總經與產業訊號
   ### 三大法人籌碼
   （貼入步驟 7 的 chip_check Markdown 段落）
   ## 整體研判
   （貼入步驟 8 的三源合議結論）
   ## 資金配置偏離
   （步驟 6 的偏離說明）
   ## 預警標的處置
   （貼入步驟 10 的個股建議）
   ## 待辦事項
   - [ ]（依整體研判 + 個股建議自動生成）
   ```

12. 輸出摘要：市場狀態、整體操作方向、今日預警數量、命中籌碼情境、資金桶狀態、已建日誌路徑。

13. **Hook 結果落地**：
    讀取 `journals/logs/{REVIEW_DATE}_hooks.json`，取得步驟 7.5 彙整的結構化 hook 結果：

    a. **寫入日誌**：將 `summary_md` 區塊內容寫入日誌 `## Hooks` 區塊（表格格式已由 hook_runner 預生成）

    b. **逐一確認 target action**（依 severity 排序：high → medium → low）：
       對每個 triggered hook 中的每個 target：
       - `action: p1_upgrade` → Agent 確認是否同意升級。若是，更新戰術指南 P1 對應條目
       - `action: p1_observe` → Agent 確認是否同意觀察。若是，更新戰術指南 P1 觀察注記
       - `action: p2_observe` → Agent 確認後更新戰術指南 P2 對應條目
       - `action: todo_add` → 寫入日誌 `## 待辦事項`
       - `action: no_action` → 僅記錄，不動作

    c. **生命週期事件**：`lifecycle_events` 陣列中的項目已由 hook_runner 自動執行（status 變更、auto_disable 等），Agent 只需確認並記錄

    d. **失敗 hook**：`failed` 陣列中若有項目，記錄到日誌 `## Hooks → ❌ 執行失敗`，並在待辦事項加入 `- [ ] 人工檢查 {hook_name} 腳本`

    落地完成後，Agent 在日誌中勾選確認。若高嚴重度項目全部確認完畢，輸出摘要。
    在步驟 12 的摘要末尾追加：`Hooks: 已觸發 N 個` 或 `Hooks: 無觸發`
