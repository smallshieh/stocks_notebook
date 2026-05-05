---
name: 元太硬死線倒計時
trigger:
  type: every_n_trading_days
  n: 5
script: .venv/Scripts/python.exe scripts/deadline_counter.py --code 8069 --name 元太 --deadline 2026-06-30 --alert-days 20 --json
output_to: journal
alert_prefix: "⏳ 元太硬死線"
---

## 說明

追蹤 8069 元太硬死線（2026-06-30）的剩餘交易日數。

**背景**：元太退場 SOP 情境 B，持倉 231 股 @均 154.71。
- 主要出場線：165 元（自動觸發）
- 硬死線：2026-06-30（無論股價，強制清倉）
- 緊急停損：130 元（全出）

**每 5 個交易日檢查一次**（週一、週三或週五附近）：

| 剩餘交易日 | 狀態 | 行動 |
|-----------|------|------|
| > 20 日 | 🟢 安全 | 靜默記錄 |
| ≤ 20 日 | ⚠️ **警示觸發** | 強制寫入 P1，加注出場計畫 |
| ≤ 5 日 | 🚨 緊急 | 同上 + 提示明確出場時間窗口 |
| 0 日（當天）| ⛔ | 今日必須清倉 |

### Agent 執行指令（達門檻時強制執行）

> **v2 結構化輸出**：此 hook 腳本現在輸出 JSON `{hook, status, severity, targets[{code, name, action, summary, detail}]}`。
> Agent 應讀取 `journals/logs/{REVIEW_DATE}_hooks.json` 中的結構化結果，而非解析 stdout 文字。
> `action` 欄位：`p1_upgrade` | `p1_observe` | `p2_observe` | `todo_add` | `no_action`

當此 hook 輸出 `status: alert` 且 target `action: p1_upgrade` 時，daily-review agent 必須：
1. 將 8069 元太移入戰術指南 `## P1`，備注「硬死線 ≤ 20 交易日，不論股價必須在 06-30 前完成清倉」
2. 在 P1 動作欄加入具體出場窗口（例如：「若不到 165 元，於 06-25 前市價清出」）
3. 在日誌 `## Hooks` 標記「→ 已更新 P1 元太硬死線」

**預計存續**：至 2026-06-30 出場完成後，由 `deadline_passed` lifecycle 停用，或手動在 `hooks_state.json` 設為 disabled。
