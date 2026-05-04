---
name: 前瞻觀點到期提醒
trigger:
  type: every_n_trading_days
  n: 5
script: .venv/Scripts/python.exe scripts/thesis_expiry.py --quiet
output_to: journal
alert_prefix: "⏰ 觀點到期追蹤"
---

## 說明

掃描兩個來源，提醒即將到期或已過期未驗證的前瞻觀點：

1. **`strategies/thesis_tracking.md`** Active 區 — 第三方前瞻觀點，有明確「驗證時點」
2. **`trades/*.md`** 催化劑表 — 帶有**未來日期**的項目（過去事件不會出現）

### 提醒分類

| 類別 | 條件 | 圖示 |
|------|------|------|
| 已過期未驗 | 驗證時點已過，狀態仍為 🟡 | 🚨 |
| 即將到期 | 驗證時點在未來 7 天內 | ⏰ |
| 預覽 | 驗證時點在未來 30 天內 | 📅 |

### 收到提醒後的動作

- **已過期**：立即驗證，將 thesis_tracking 中對應項目移到 Resolved 區並打分
- **即將到期**：準備驗證所需數據（拉行情、比對條件）
- **預覽**：僅供知悉，不需行動

### 手動執行（完整報告）

```powershell
.venv\Scripts\python.exe scripts/thesis_expiry.py
```

### Agent 執行指令

> **v2 結構化輸出**：此 hook 腳本現在輸出 JSON `{hook, status, severity, targets[{code, name, action, summary, detail}]}`。
> Agent 應讀取 `journals/logs/{REVIEW_DATE}_hooks.json` 中的結構化結果，而非解析 stdout 文字。
> `action` 欄位：`p1_upgrade` | `p1_observe` | `p2_observe` | `todo_add` | `no_action`
