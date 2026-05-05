---
name: 旺宏時間停損倒計時
trigger:
  type: every_n_trading_days
  n: 1
script: .venv/Scripts/python.exe scripts/deadline_counter.py --code 2337 --name 旺宏 --deadline 2026-05-12 --alert-days 3 --json
output_to: journal
alert_prefix: "⏰ 旺宏時間停損"
---

## 背景

監控 2337 旺宏動能波段倉（80 股）的時間停損死線（2026-05-12）。

**背景**：2026-05-05 A 條件建倉 80 股 @158 元。動能波段 SOP 規定：**持有 5 個交易日（≈ 05-12）未創新高 → 全出**。

- 每日提示剩餘交易日數
- 剩餘 ≤ 3 交易日時輸出警示
- 到期日當天若現價 > 進場均價（158 元）且移動停利未觸發 → 評估是否延期

**平行監控**：`wave-decay-2337`（Wave ≤ 0 出場）+ 移動停利（-5% from 最高點，人工執行）。

### Agent 執行指令（警示觸發時）

> **v2 結構化輸出**：此 hook 腳本現在輸出 JSON `{hook, status, severity, targets[{code, name, action, summary, detail}]}`。
> Agent 應讀取 `journals/logs/{REVIEW_DATE}_hooks.json` 中的結構化結果，而非解析 stdout 文字。
> `action` 欄位：`p1_upgrade` | `p1_observe` | `p2_observe` | `todo_add` | `no_action`

當 `status: alert` 且 `action: p1_upgrade` 時（剩餘 ≤ 3 交易日）：
1. 在盤後日誌 `## 待辦事項` 加入：
   `- [ ] 【2337 旺宏】時間停損倒計時：剩 {remaining} 交易日，現價 vs 158 元，確認是否繼續持有`
2. 若剩餘 ≤ 1 交易日且 Wave ≤ 0：升入戰術指南 P1，動作填「時間停損到期，今日全出 80 股 @市價」

**預計存續**：2026-05-12 後由 `deadline_passed` lifecycle 自動停用。
