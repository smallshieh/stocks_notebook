---
name: 中鋼底倉硬止損監控
trigger:
  type: schedule
  n: 1
script: .venv/Scripts/python.exe scripts/hook_price_alert.py --code 2002 --name 中鋼 --hard-stop 17.5 --json
output_to: journal
alert_prefix: "🛑 中鋼硬止損"
---

## 背景

監控 2002 中鋼底倉（10,000 股）的硬止損接近度。

**持倉**：底倉 10,000 股（景氣循環倉），操作倉已於 2026-05-05 全清（換倉東和鋼鐵）。
**成本**：約 26.15 元（μ = -13.3%，景氣底部持倉，非殖利率倉）。
**硬止損**：17.5 元（現價 18.6，餘裕僅 6.3%）。

> ⚠️ **底倉性質**：10,000 股為景氣復甦等待倉，正常情況不動；唯跌破硬止損 17.5 時才觸發退場。

**原 SOP 三段賣點（20.5/21.0/21.5）已廢止**：操作倉 3,000 股已於 05-05 全清，減碼任務完成。

### Agent 執行指令

> **v2 結構化輸出**：此 hook 腳本現在輸出 JSON `{hook, status, severity, targets[{code, name, action, summary, detail}]}`。
> Agent 應讀取 `journals/logs/{REVIEW_DATE}_hooks.json` 中的結構化結果，而非解析 stdout 文字。
> `action` 欄位：`p1_upgrade` | `p1_observe` | `p2_observe` | `todo_add` | `no_action`

當 `status: alert` 且 `near_hard_stop: true`（距 17.5 < 5%）時：
1. 升入戰術指南 P1：「中鋼底倉距硬止損 17.5 僅 {gap_pct}%，準備 10,000 股市價退場」
2. 日誌待辦：`- [ ] 【2002 中鋼】距硬止損 17.5 僅 {gap_pct}%，確認退場決策`

**預計存續**：底倉清空後由 `position_liquidated` 永久停用；若景氣回升、底倉出清前無需修改。
