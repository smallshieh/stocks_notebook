---
name: 京元電 Wave 停利/退場監控
trigger:
  type: every_n_trading_days
  n: 1
script: .venv/Scripts/python.exe scripts/wave_decay_alert.py --code 2449 --name 京元電 --alert-wave 1 --context 停利2檢查：Wave<=+1且未創新高賣4股；Wave<=0或跌破月線全清 --json
output_to: journal
alert_prefix: "📉 京元電 Wave 停利/退場"
---

## 背景

監控 2449 京元電剩餘 8 股的動能衰退與停利/退場條件。

**2026-05-05 狀態**：停利 1 已執行（@353 賣 4 股），剩 8 股 @均 273.25。現價 354，Wave +3，月線 289.43，原 05-12 時間停損已廢止。

**攻守退重點**：

| 條件 | 動作 |
|------|------|
| Wave ≥ +2 且站穩月線 | 持有 8 股 |
| Wave 降至 +1 | 暫停第三批加碼，檢查是否滯漲未創新高 |
| Wave ≤ +1 且現價未創新高 | 停利 2：賣 4 股（剩 4 股） |
| Wave ≤ 0 或跌破月線 289 | 停利 3：全清剩餘 4 股 |
| 跌破 246 | 硬停損：全清，不等其他訊號 |

**觀察門檻**：`--alert-wave 1`。Wave 降至 +1 即要求 Agent 檢查是否符合停利 2，而不是等到負值。

### Agent 執行指令

> **v2 結構化輸出**：此 hook 腳本現在輸出 JSON `{hook, status, severity, targets[{code, name, action, summary, detail}]}`。
> Agent 應讀取 `journals/logs/{REVIEW_DATE}_hooks.json` 中的結構化結果，而非解析 stdout 文字。
> `action` 欄位：`p1_upgrade` | `p1_observe` | `p2_observe` | `todo_add` | `no_action`

當 `status: alert` 或 `status: warning` 且 target 為 2449：

1. 讀取 `detail.wave_total`、`detail.current_price`、`detail.ma20`。
2. 若 Wave ≤ +1 且現價未創新高：升入戰術指南 P1，動作填「京元電停利 2：賣 4 股」。
3. 若 Wave ≤ 0 或現價跌破月線 289：升入 P1，動作填「京元電停利 3：剩餘股數全清」。
4. 若僅 Wave +1 但仍創新高：P2 觀察，暫停第三批加碼。

**平行監控**：`trades-defense-scan` 仍負責硬停損 246；05/10 月營收 MoM ≥ 0 由 Agent 在 daily-review/事件輸入時確認第三批加碼是否開放。

**預計存續**：2449 完全出場後，在 `hooks_state.json` 設為 disabled（`position_liquidated`）。
