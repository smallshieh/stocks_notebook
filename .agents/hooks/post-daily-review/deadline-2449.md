---
name: 京元電時間停損倒計時
trigger:
  type: every_n_trading_days
  n: 1
script: .venv/Scripts/python.exe scripts/deadline_counter.py --code 2449 --name 京元電 --deadline 2026-05-12 --alert-days 5
output_to: journal
alert_prefix: "⏰ 京元電時間停損"
---

## 背景

監控 2449 京元電的時間停損死線（2026-05-12）。

**背景**：04-20 重新建倉 12 股 @均 273.25，SOP 設定「15 個交易日內（≈ 05/12）未突破 300 元，需檢討是否繼續持有」。

- 突破 300 前：每日提示剩餘天數
- 剩餘 ≤ 5 交易日時輸出警示

**另一個關鍵日期**：05/10 月營收公告（加碼第三批的基本面條件之一），若 MoM 為負，時間停損提前執行。

### Agent 執行指令（警示觸發時）

> **v2 結構化輸出**：此 hook 腳本現在輸出 JSON `{hook, status, severity, targets[{code, name, action, summary, detail}]}`。
> Agent 應讀取 `journals/logs/{REVIEW_DATE}_hooks.json` 中的結構化結果，而非解析 stdout 文字。
> `action` 欄位：`p1_upgrade` | `p1_observe` | `p2_observe` | `todo_add` | `no_action`

當輸出包含「⚠️」或「警戒」時：
1. 在盤後日誌 `## 待辦事項` 加入 `- [ ] 【2449 京元電】時間停損倒計時警示：{日期}，現價 vs 300 元，評估是否繼續持有`
2. 若剩餘 ≤ 3 交易日且現價 < 300：升入戰術指南 P1，動作填「時間停損評估，05/12 決定」

**預計存續**：2026-05-12 後可停用（加底線前綴 `_deadline-2449.md`）。
