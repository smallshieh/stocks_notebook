---
name: 大成月線跌破計數
trigger:
  type: every_n_trading_days
  n: 1
script: .venv/Scripts/python.exe scripts/ma_breach_counter.py --code 1210 --ma 20 --alert-days 3 --name 大成 --json
output_to: journal
alert_prefix: "📉 大成月線觀察"
---

## 說明

追蹤 1210 大成收盤價是否連續跌破月線（20MA），達 3 日時觸發警示。

**背景**：大成為配息防禦型底倉，殖利率錨定策略。月線短暫失守屬正常震盪，**不等同動能背離**。

**判定門檻**：

| 狀況 | 動作 |
|------|------|
| 月線下方 < 3 日 | 觀察，不動作 |
| 月線下方 ≥ 3 日 | ⚠️ 升入 P1 觀察，但動作依殖利率判斷（見下方執行指令）|
| 回到月線上方 | 計數歸零，持有不動 |

### Agent 執行指令（達門檻時強制執行）

> **v2 結構化輸出**：此 hook 腳本現在輸出 JSON `{hook, status, severity, targets[{code, name, action, summary, detail}]}`。
> Agent 應讀取 `journals/logs/{REVIEW_DATE}_hooks.json` 中的結構化結果，而非解析 stdout 文字。
> `action` 欄位：`p1_upgrade` | `p1_observe` | `p2_observe` | `todo_add` | `no_action`

> ⚠️ **配息防禦股特別規則**：大成為殖利率錨定型底倉，月線跌破≠動能背離，須先確認殖利率再決定動作。

當 `journals/logs/{REVIEW_DATE}_hooks.json` 中此 hook 為 `status: alert` 且 target `action: p1_observe` 時，daily-review agent 必須：
1. **先確認現價殖利率**（股利 2.83 元 ÷ 現價）：
   - 若殖利率 **≥ 5.0%**（現價 ≤ 56.6 元）：P1 動作填「再觀察 N 日；殖利率仍合理，真正觸發：跌破 48.93 元或配息削減」，**不執行減碼**
   - 若殖利率 **< 5.0%**（現價 > 56.6 元）且月線持續失守：才評估先減 1/3
2. 將 1210 大成移入戰術指南 `## P1`，動作欄依上方殖利率判斷填入對應文字
3. 在日誌 `## Hooks` 區塊標記「→ 已更新 P1」

當此 hook 產生 `lifecycle_event: auto_disable` 或 hooks_state 顯示月線收復時：
1. 若 1210 在 P1，移回 P2 觀察
2. 確認 `hooks_state.json` 中此 hook 已由 runner 自動轉為 disabled

**預計存續**：短期 hook，待大成月線情況明朗後由 `hooks_state.json` lifecycle 自動停用；再次跌破時由 runner 自動 re-enable。
