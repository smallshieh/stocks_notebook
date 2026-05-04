---
name: 中美晶區間監控
trigger:
  type: schedule
  n: 1
script: .venv/Scripts/python.exe scripts/wave_decay_alert.py --code 5483 --name 中美晶 --alert-wave 0 --json
output_to: journal
alert_prefix: "📐 中美晶區間監控"
---

## 背景

監控 5483 中美晶（reversion_rolling 策略）的區間位置與動能。

**持倉**：底倉 140 股，操作倉 0 股。
**策略**：回測 120~125 且 Wave ≤ 0 → 建 30 股操作倉。

**本 hook 提供**：Wave 衰退警示。當 Wave ≤ 0 且政策確認防守時輸出 alert。

### Agent 執行指令

> **v2 結構化輸出**：此 hook 腳本現在輸出 JSON `{hook, status, severity, targets[{code, name, action, summary, detail}]}`。
> Agent 應讀取 `journals/logs/{REVIEW_DATE}_hooks.json` 中的結構化結果，而非解析 stdout 文字。
> `action` 欄位：`p1_upgrade` | `p1_observe` | `p2_observe` | `todo_add` | `no_action`

當 `status: alert`（Wave ≤ 0 且政策確認防守）：
1. 檢查 `detail.current_price`：
   - 若在 120~125 區間：升入戰術指南 P1，動作填「中美晶回測買回區，Wave ≤ 0，評估建操作倉」
   - 若不在買回區：在 P2 加注「Wave ≤ 0 警戒，等回測買回區」

當 `status: ok`：
- 記錄即可，不動作
