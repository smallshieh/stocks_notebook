---
name: 力成 Wave 衰退警示
trigger:
  type: every_n_trading_days
  n: 1
script: .venv/Scripts/python.exe scripts/wave_decay_alert.py --code 6239 --name 力成 --alert-wave -2 --context "批次二：Wave ≤ -2 連 2 日 → 賣波段 60 股" --json
output_to: journal
alert_prefix: "⚠️ 力成 Wave 衰退"
---

## 背景

監控 6239 力成波段倉的動能狀態。Wave ≤ -2 只是觀察門檻；是否升級為動作，須由 `signal_policy.py` 確認為防守訊號，且參考 `journals/logs/signal_state.json` 的結構化持續性紀錄。

**持倉**：底倉 350 股（長線不動）+ 波段倉 150 股（待分批減持）。

**SOP 減持層級**：
- 批次一（手動）：單日量 ≥ 均量 1.5 倍 + 收黑 K → 賣波段 60 股（盤中手動執行）
- 批次二（此 hook）：Wave ≤ -2 且政策確認防守訊號連 2 日 → 賣波段 60 股
- 批次三：跌破月線 + Wave ≤ -1 → 賣剩餘 45 股波段倉

**Wave 觀察門檻**：`--alert-wave -2`。門檻命中但政策品質不足時，腳本輸出 `status: warning` / `action: p2_observe`，不升級為 P1。

### Agent 執行指令

> **v2 結構化輸出**：此 hook 腳本現在輸出 JSON `{hook, status, severity, targets[{code, name, action, summary, detail}]}`。
> Agent 應讀取 `journals/logs/{REVIEW_DATE}_hooks.json` 中的結構化結果，而非解析 stdout 文字。
> `action` 欄位：`p1_upgrade` | `p1_observe` | `p2_observe` | `todo_add` | `no_action`

**收到 `status: alert` / `action: p1_upgrade` 時（Wave ≤ -2 且政策確認防守）：**
1. 讀取 `journals/logs/signal_state.json` 中 `6239` 最近紀錄，確認 `action_tag` 是否連續為 `downside_*` 且 `quality` 非 `low`：
   - **若是（連續 2 日）**：升入戰術指南 P1，動作填「政策確認 Wave 防守訊號連 2 日，批次二：賣波段 60 股 @市價」；並在盤後日誌 `## 待辦事項` 新增 `- [ ] 【6239 力成】政策確認防守訊號連 2 日，批次二賣波段 60 股`
   - **若否（第 1 日）**：在日誌 Hook 區記錄「力成政策確認防守第 1 日，明日若持續 → 升 P1 執行批次二」，不升 P1

**Wave 回升至 ≥ +2 時：**
1. 若已升入 P1，確認批次執行後移回 P2
2. 若波段倉已清空，將 `hooks_state.json` 中此 hook 設為 `disabled`

**預計存續**：波段倉 150 股清空後停用。
