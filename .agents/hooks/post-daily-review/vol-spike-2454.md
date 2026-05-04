---
name: 聯發科爆量監控
trigger:
  type: schedule
  n: 1
script: .venv/Scripts/python.exe scripts/hook_vol_spike.py --code 2454 --name 聯發科 --vol-ratio 1.5 --json
output_to: journal
alert_prefix: "📊 聯發科爆量監控"
---

## 背景

監控 2454 聯發科是否出現「爆量收黑」訊號。

**持倉**：28 股 @1,551.21 元。
**SOP**：聯發科在賣出區趨勢延伸（+46.9%），唯一觸發條件是「爆量收黑」。
**本 hook**：每日檢查今日量比是否 ≥ 1.5 倍，並判斷是否收黑 K。

### Agent 執行指令

> **v2 結構化輸出**：此 hook 腳本現在輸出 JSON `{hook, status, severity, targets[{code, name, action, summary, detail}]}`。
> Agent 應讀取 `journals/logs/{REVIEW_DATE}_hooks.json` 中的結構化結果，而非解析 stdout 文字。
> `action` 欄位：`p1_upgrade` | `p1_observe` | `p2_observe` | `todo_add` | `no_action`

當 `status: alert`（爆量 ≥ 1.5x 且收黑 K）：
1. 升入戰術指南 P1，動作填「聯發科爆量收黑，評估減持波段倉」
2. 在待辦事項加入 `- [ ] 【2454 聯發科】爆量收黑，確認減持時機`

當 `status: warning`（爆量但未收黑，或收黑但量未達）：
- 在 P2 加注觀察

當 `status: ok`：
- 記錄即可

**預計存續**：長期（聯發科為長期持有標的）。
