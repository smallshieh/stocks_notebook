---
name: 京元電時間停損倒計時
trigger:
  type: every_n_trading_days
  n: 1
script: .venv/Scripts/python.exe scripts/deadline_counter.py --code 2449 --name 京元電 --deadline 2026-05-12 --alert-days 5 --json
output_to: journal
alert_prefix: "⏰ 京元電時間停損"
---

## 背景

監控 2449 京元電的時間停損死線（2026-05-12）。

> **2026-05-05 更新**：京元電已突破 300，時間停損前提已兌現；此 hook 已在 `hooks_state.json` 停用。後續改由 `wave-decay-2449` 監控剩餘 8 股的停利/退場。

**背景**：04-20 重新建倉 12 股 @均 273.25，SOP 設定「15 個交易日內（≈ 05/12）未突破 300 元，需檢討是否繼續持有」。

- 突破 300 前：每日提示剩餘天數
- 剩餘 ≤ 5 交易日時輸出警示

**另一個關鍵日期**：05/10 月營收公告仍是第三批加碼的基本面條件；若 MoM 為負，第三批凍結，不再追高。

### Agent 執行指令（警示觸發時）

> **v2 結構化輸出**：此 hook 腳本現在輸出 JSON `{hook, status, severity, targets[{code, name, action, summary, detail}]}`。
> Agent 應讀取 `journals/logs/{REVIEW_DATE}_hooks.json` 中的結構化結果，而非解析 stdout 文字。
> `action` 欄位：`p1_upgrade` | `p1_observe` | `p2_observe` | `todo_add` | `no_action`

此 hook 目前 disabled；若未來被誤啟用且輸出 `status: alert`，應先確認是否仍有時間停損前提。以 2026-05-05 更新後的 SOP 為準，2449 後續主要由 `wave-decay-2449` 與 `trades-defense-scan` 監控。

**目前狀態**：disabled。保留此文件作為舊時間停損紀錄，不再作為 2449 主要 hook。
