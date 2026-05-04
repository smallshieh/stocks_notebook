# Markdown 工具給 Agents 的使用規則

> 目的：降低讀寫 `trades/`、`watchlist/`、`journals/` 長篇 Markdown 的 token 成本，避免整檔讀取與誤改。

## 核心原則

1. **scripts 負責結構與安全，LLM 負責內容判斷。**
2. 讀長 MD 前，先跑 `md_outline.py` 看標題與行號。
3. 只讀任務需要的區塊，使用 `md_section.py`。
4. 只有在區塊邊界不清、格式破損、或任務需要全文時，才讀完整 MD。
5. 修改整個區塊時，LLM 先產生新的 section 內容，再用 `md_update_section.py --dry-run` 檢查，確認後寫入。
6. 交易股數、成本、均價等數字不可猜；從 MD、CSV 或使用者提供資料取得。

## 職責邊界

### scripts 做什麼

- 找檔案、列標題、回報行號。
- 讀取指定 section，避免整檔讀取。
- 替換指定 section，避免誤改其他區塊。
- 做 dry-run、拒絕歧義匹配、保留區塊邊界。
- 做明確限制欄位的機械更新，例如價格、20MA、殖利率、日期、表格格式。

### LLM 做什麼

- 判斷任務需要讀哪些 section。
- 理解 section 內容與上下文。
- 產生新的 section 內容。
- 決定哪些資訊該保留、改寫、補充或刪除。
- 做投資邏輯、風險判斷、紀律檢查與文字整理。

### scripts 不應做什麼

- 不自動推論停損、停利或加碼條件。
- 不自動改策略與交易邏輯。
- 不自動刪除 LLM 未明確要求刪除的文字。
- 不把投資判斷寫死在工具中。
- 不把整份 MD 當成黑盒重排或重寫。

## 標準讀寫流程

### 讀取

```text
1. md_outline.py <file>
2. 依 outline 判斷需要哪些 section
3. md_section.py <file> "<section>"
4. LLM 理解內容並做判斷
```

### 寫入

```text
1. LLM 產生完整的新 section 內容
2. 將新 section 存成暫存檔
3. md_update_section.py <file> "<section>" --from <tmp> --dry-run
4. 檢查 dry-run 只影響目標 section
5. md_update_section.py <file> "<section>" --from <tmp>
```

### 例外：機械欄位更新

像 `update_trade_prices.py` 這類腳本可以直接更新欄位，但必須同時滿足：

- 欄位範圍明確，例如只更新 `目前價格`、`月線 (20MA) 位置`、`預估殖利率`。
- 區塊範圍明確，例如只改 `## 基本資訊` 或舊格式開頭 metadata。
- 預設 dry-run，必須明確加 `--write` 才寫檔。
- 不改交易紀錄、停損預警、倉位規劃、操作策略。

## 指令

所有指令都在專案根目錄執行：

```powershell
Set-Location -LiteralPath 'S:\股票筆記'
.\.venv\Scripts\python.exe scripts\md_outline.py trades\00919_群益台灣精選高息.md
```

## 1. 列出 MD 結構

```powershell
.\.venv\Scripts\python.exe scripts\md_outline.py trades\00919_群益台灣精選高息.md
```

輸出範例：

```text
trades\00919_群益台灣精選高息.md
L001 H1 00919_群益台灣精選高息 交易紀錄 [1-95]
L003 H2 基本資訊 [3-10]
L020 H2 交易紀錄 [20-29]
L048 H2 停損預警區 (由 AI 或腳本自動核對) [48-55]
```

JSON 模式：

```powershell
.\.venv\Scripts\python.exe scripts\md_outline.py trades\00919_群益台灣精選高息.md --json
```

## 2. 讀取指定區塊

```powershell
.\.venv\Scripts\python.exe scripts\md_section.py trades\00919_群益台灣精選高息.md "基本資訊"
```

讀多個區塊：

```powershell
.\.venv\Scripts\python.exe scripts\md_section.py trades\00919_群益台灣精選高息.md --section "基本資訊" --section "交易紀錄"
```

遇到多個同名或模糊匹配時，工具會列出候選區塊。此時用 `--exact` 或 `--level` 限縮：

```powershell
.\.venv\Scripts\python.exe scripts\md_section.py trades\00919_群益台灣精選高息.md "交易紀錄" --exact --level 2
```

## 3. 更新指定區塊

先準備一個 replacement 檔，例如 `tmp_section.md`，內容包含整個 section：

```markdown
## 停損預警區 (由 AI 或腳本自動核對)
- [ ] 是否觸及 -10% 首波停損點？
- [ ] 是否跌破月線？
- **預警狀態**: ✅ 正常
```

先 dry-run：

```powershell
.\.venv\Scripts\python.exe scripts\md_update_section.py trades\00919_群益台灣精選高息.md "停損預警區" --from tmp_section.md --dry-run
```

確認後寫入：

```powershell
.\.venv\Scripts\python.exe scripts\md_update_section.py trades\00919_群益台灣精選高息.md "停損預警區" --from tmp_section.md
```

若 replacement 只有 body、不含標題，使用 `--body-only`，工具會保留原標題：

```powershell
.\.venv\Scripts\python.exe scripts\md_update_section.py trades\00919_群益台灣精選高息.md "停損預警區" --from tmp_body.md --body-only
```

## Agent 建議流程

### 查單檔基本資料

```text
1. md_outline.py <file>
2. md_section.py <file> "基本資訊"
3. 需要交易流水時，再讀 "交易紀錄" 或 "買賣執行紀錄"
```

### 校正交易紀錄

```text
1. md_outline.py <trade file>
2. md_section.py <trade file> "基本資訊"
3. md_section.py <trade file> "交易紀錄" 或 "買賣執行紀錄"
4. 只在必要時讀 "倉位規劃"、"停損預警區"
5. 不讀全文，除非找不到區塊或格式破損
```

### daily-review

```text
1. 健診檔可直接讀，因為它本身是摘要
2. 戰術指南先 md_outline.py
3. 只讀 "儀表板"、"P1"、"P2"、"訊號診斷日更新"
4. 不要整檔讀戰術指南
```

## 注意事項

- 這些工具只解析 ATX 標題：`#` 到 `######`。
- fenced code block 內的 `#` 不會被當成標題。
- 行號是 1-based，方便 agent 精準讀取與回報。
- `md_update_section.py` 只替換單一匹配區塊；若匹配多個，會拒絕寫入。
- 修改 `trades/`、`journals/` 重要 MD 後，仍需詢問是否同步 Notion。
