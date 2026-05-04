---
name: 東和鋼月線跌破監控
trigger:
  type: schedule
  n: 1
script: .venv/Scripts/python.exe scripts/ma_breach_counter.py --code 2006 --ma 20 --alert-days 3 --name 東和鋼 --json
output_to: journal
alert_prefix: "📉 東和鋼月線觀察"
---

## 說明

追蹤 2006 東和鋼收盤價是否連續跌破月線（20MA），達 3 日時觸發警示。

**背景**：東和鋼為配息防禦型底倉，殖利率錨定策略。月線短暫失守屬正常震盪。

**持倉**：870 股 @均 67.32 元。
**硬停損**：60.6 元。

**判定門檻**：

| 狀況 | 動作 |
|------|------|
| 月線下方 < 3 日 | 觀察，不動作 |
| 月線下方 ≥ 3 日 | ⚠️ 升入 P1 觀察，但動作依殖利率判斷 |
| 回到月線上方 | 計數歸零，持有不動 |

### Agent 執行指令

> **v2 結構化輸出**：此 hook 腳本現在輸出 JSON `{hook, status, severity, targets[{code, name, action, summary, detail}]}`。
> Agent 應讀取 `journals/logs/{REVIEW_DATE}_hooks.json` 中的結構化結果，而非解析 stdout 文字。
> `action` 欄位：`p1_upgrade` | `p1_observe` | `p2_observe` | `todo_add` | `no_action`

當 `status: alert`（月線下方 ≥ 3 日）：
1. 先確認現價殖利率（股利 4.24 元 ÷ 現價）：
   - 若殖利率 ≥ 5.0%：P1 動作填「殖利率仍合理，不減碼。真正觸發：跌破 60.6 元」
   - 若殖利率 < 5.0%：才評估減碼
2. 將東和鋼移入戰術指南 P1 觀察

當 `lifecycle_event: auto_disable`（月線收復）：
- 若已在 P1，移回 P2

**預計存續**：東和鋼月線情況明朗或出清後停用。
