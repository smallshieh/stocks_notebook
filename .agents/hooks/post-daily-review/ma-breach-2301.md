---
name: 光寶科月線跌破監控
trigger:
  type: every_n_trading_days
  n: 1
script: .venv/Scripts/python.exe scripts/ma_breach_counter.py --code 2301 --ma 20 --alert-days 2 --name 光寶科 --json
output_to: journal
alert_prefix: "📉 光寶科月線觀察"
---

## 背景

追蹤 2301 光寶科收盤價是否連續跌破月線（20MA），達 2 日時觸發警示。

**持倉**：50 股 @均 161.44 元（Tactical Tier C，2026-05-05 第二批完成）。
**出場條件**：跌破月線 + Wave ≤ -2 → 全出；硬停損 145.30 元（成本 × 0.9）。

**判定門檻**：

| 狀況 | 動作 |
|------|------|
| 月線下方 < 2 日 | 觀察，不動作 |
| 月線下方 ≥ 2 日 | ⚠️ 升入 P1 觀察，確認 Wave 是否 ≤ -2 |
| 月線下方 ≥ 2 日 + Wave ≤ -2 | 全出 50 股 |
| 回到月線上方 | 計數歸零，持有不動 |

> ⚠️ **動能成長股規則**：光寶科是 Tactical 波段倉（非殖利率底倉），月線跌破 + Wave ≤ -2 = 動能背離，直接全出，不考慮殖利率護底。

### Agent 執行指令（達門檻時）

> **v2 結構化輸出**：此 hook 腳本現在輸出 JSON `{hook, status, severity, targets[{code, name, action, summary, detail}]}`。
> Agent 應讀取 `journals/logs/{REVIEW_DATE}_hooks.json` 中的結構化結果，而非解析 stdout 文字。
> `action` 欄位：`p1_upgrade` | `p1_observe` | `p2_observe` | `todo_add` | `no_action`

當 `status: alert` 且 `action: p1_observe` 時（月線下方 ≥ 2 日）：
1. 查詢當日 Wave Score（從 scan.log 或戰術指南）：
   - **Wave ≤ -2**：升入戰術指南 P1，動作填「光寶科月線跌破 + Wave ≤ -2，全出 50 股 @市價」；日誌待辦加入 `- [ ] 【2301 光寶科】月線跌破+Wave≤-2，全出 50 股`
   - **Wave > -2**：P2 觀察，「月線跌破第 {N} 日，Wave 尚未惡化，等 Wave ≤ -2 確認」

當此 hook 產生 `lifecycle_event: auto_disable`（月線收復）：
1. 若在 P1，移回 P2 觀察
2. 確認 `hooks_state.json` 中此 hook 已由 runner 轉為 disabled

**預計存續**：50 股全出後由 `position_liquidated` 永久停用。
