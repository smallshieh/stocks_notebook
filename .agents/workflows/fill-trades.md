---
description: 填入 trades/ 下基本資訊空白欄位（目前價格 / 月線 / 殖利率）
---

## 前提
- 今日 `持倉健診_{TODAY}.md` 必須已存在（14:35 自動執行或手動執行 portfolio_report.py）

## 步驟

1. 取得今天日期（格式：YYYY-MM-DD），以下以 `{TODAY}` 代稱。

2. 讀取 `持倉健診_{TODAY}.md`，建立以下對照表：
   `{ 代號 → { price, ma20, dy } }`

3. 掃描 `trades/` 目錄下所有 `.md` 檔（排除 `template.md`）。

4. 對每個 trades MD 檔：
   - 不要直接讀完整檔案；先用 outline 確認結構，再讀 `基本資訊` 區塊：
     ```powershell
     .\.venv\Scripts\python.exe scripts\md_outline.py trades\{檔名}.md
     .\.venv\Scripts\python.exe scripts\md_section.py trades\{檔名}.md "基本資訊"
     ```
   - 在 `基本資訊` 區塊檢查 `**目前價格**:`、`**月線 (20MA) 位置**:`、`**預估殖利率**:` 三行是否為空值
   - **若有值則跳過，不覆蓋**
   - 若為空，從步驟 2 的對照表找對應代號，填入數值（格式：`XX.XX 元 ({TODAY})`）
   - 更新時優先只替換 `基本資訊` 區塊，先 dry-run 再寫入：
     ```powershell
     .\.venv\Scripts\python.exe scripts\md_update_section.py trades\{檔名}.md "基本資訊" --from {暫存區塊檔} --dry-run
     .\.venv\Scripts\python.exe scripts\md_update_section.py trades\{檔名}.md "基本資訊" --from {暫存區塊檔}
     ```
   - 只有在 `基本資訊` 區塊不存在、標題歧義、格式損壞時，才讀完整 MD。

5. 輸出摘要：
   - 共更新幾個檔案、哪些代號
   - 哪些代號在健診報告中找不到對應數據（需手動補充）
