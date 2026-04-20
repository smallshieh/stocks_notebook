# Post-Daily-Review Hook 系統

> 適用：任何 AI Agent 執行 `/daily-review` 時，步驟 11 會自動掃描並觸發此目錄下的 hooks。

---

## 運作原理

```
/daily-review
  ├── 步驟 1~10（核心流程：大盤狀態 → 健診 → 預警 → 日誌）
  └── 步驟 11：掃描 .agents/hooks/post-daily-review/
        ├── 讀取 _state.json（各 hook 的上次執行日期）
        ├── 對每個 .md hook 檔：
        │     ├── 解析 frontmatter 的 trigger 條件
        │     ├── 距上次執行 < n 個交易日？→ 跳過
        │     └── 已到期？→ 執行 script → 寫入日誌 → 更新 _state.json
        └── 摘要：「Hooks: 已觸發 N 個」或「Hooks: 無觸發」
```

---

## 目錄結構

```
.agents/hooks/post-daily-review/
├── README.md           ← 你正在讀的這份文件
├── _state.json         ← hook 執行狀態追蹤（自動維護，勿手動編輯）
├── regime-6488.md      ← 環球晶區間遷移觀察（每 10 個交易日）
└── (未來的其他 hook)
```

---

## Hook 檔案格式

每個 hook 是一個 `.md` 檔，frontmatter 定義觸發條件與執行指令：

```yaml
---
name: 顯示名稱（用於日誌和摘要）
trigger:
  type: every_n_trading_days    # 目前唯一支援的觸發類型
  n: 10                         # 每 N 個交易日觸發一次
script: .venv/Scripts/python.exe scripts/some_script.py --args  # 要執行的指令
output_to: journal              # 輸出寫入位置：journal = 當日盤後日誌
alert_prefix: "📐 顯示前綴"     # 日誌中的摘要行前綴
---

## 說明
（Markdown 正文，供人類和 agent 理解此 hook 的用途與判讀方式）
```

### frontmatter 欄位說明

| 欄位 | 必填 | 說明 |
|------|------|------|
| `name` | 是 | hook 的顯示名稱 |
| `trigger.type` | 是 | 觸發類型，目前支援 `every_n_trading_days` |
| `trigger.n` | 是 | 觸發頻率（交易日數，排除週末） |
| `script` | 是 | 要執行的 PowerShell 指令（工作目錄為專案根目錄）|
| `output_to` | 是 | `journal`：輸出追加至當日盤後日誌的 `## Hooks` 區塊 |
| `alert_prefix` | 是 | 日誌摘要行的前綴文字 |

---

## _state.json 格式

```json
{
  "regime-6488": {
    "last_run": "2026-04-17",
    "run_count": 1,
    "last_output": "θ=467, 430守住率=88%/23日, 回測低點=519(-3.9%)"
  }
}
```

- **key**：hook 檔名（不含 `.md`）
- **last_run**：上次執行日期（YYYY-MM-DD）
- **run_count**：累計執行次數
- **last_output**：上次 script stdout 輸出

Agent 在步驟 11 執行後自動更新此檔案。

---

## 觸發條件判斷邏輯

`every_n_trading_days` 的計算方式：

1. 取 `{TODAY}` 與 `_state.json` 中該 hook 的 `last_run` 日期
2. 計算兩者之間的**交易日數**（排除週六、週日；不排除國定假日，因為國定假日 daily-review 本身會在步驟 5 中止）
3. 若交易日數 ≥ `n` → 觸發
4. 若 `_state.json` 中無此 hook 的紀錄 → 視為已到期，立即觸發

---

## 常見操作

### 新增一個 hook

1. 在 `.agents/hooks/post-daily-review/` 建立一個 `.md` 檔
2. 填寫 frontmatter（參考上方格式）
3. 確保 `script` 欄位的腳本可獨立執行
4. 完成。下次 `/daily-review` 會自動偵測到新 hook

### 暫停一個 hook

將檔名加底線前綴：

```
regime-6488.md  →  _regime-6488.md
```

步驟 11 會跳過所有底線開頭的檔案。恢復時移除前綴即可。

### 手動觸發（不等 daily-review）

直接執行 hook 的 `script` 欄位指令：

```powershell
# 例如手動跑環球晶區間觀察（完整報告）
.venv\Scripts\python.exe scripts/regime_tracker.py --code 6488 --support 430
```

注意：手動執行不會更新 `_state.json`，下次 daily-review 仍會按排程觸發。

### 強制下次 daily-review 觸發特定 hook

編輯 `_state.json`，將該 hook 的 `last_run` 改為較早的日期即可。

### 刪除一個 hook

刪除 `.md` 檔。可選擇性清理 `_state.json` 中對應的 key（不清也無害）。

---

## 錯誤處理

- 若某 hook 的 script 執行失敗（非零 exit code 或 exception），agent 會：
  1. 在日誌記錄 `⚠️ {hook name} 執行失敗：{error message}`
  2. **不更新** `_state.json` 的 `last_run`（下次 daily-review 會重試）
  3. 繼續處理其他 hooks（不中斷整個流程）

---

## 目前已啟用的 hooks

| Hook 檔案 | 名稱 | 頻率 | 用途 |
|-----------|------|------|------|
| `regime-6488.md` | 環球晶區間觀察 | 每 10 個交易日 | 追蹤 6488 價格中樞是否遷移（OU θ、支撐守住率、回測深度）|
| `regime-8069.md` | 元太均值錨定觀察 | 每 10 個交易日 | 追蹤 8069 的 θ 是否止穩、mean reversion 錨是否還在 |
| `thesis-expiry.md` | 前瞻觀點到期提醒 | 每 5 個交易日 | 掃描 thesis_tracking Active 區 + trades 催化劑表的未來日期項目 |
