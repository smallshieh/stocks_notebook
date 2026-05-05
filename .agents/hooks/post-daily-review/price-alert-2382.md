---
name: 廣達月線回測進場監控
trigger:
  type: schedule
  n: 1
script: .venv/Scripts/python.exe scripts/hook_price_alert.py --code 2382 --name 廣達 --hard-stop 304 --json
output_to: journal
alert_prefix: "🛑 廣達進場監控"
---

## 背景

監控 2382 廣達月線回測進場機會。現價 321，月線 320（距 +0.4%），月線回測已觸發。

**狀態**：候補追蹤，尚未建倉。
**進場區**：310~329（月線 ±3%），首單 15 股 @~320（~4,800 元）。
**放棄線**：304（月線 -5%），跌破即放棄本輪。
**SOP**：等回測月線區間量穩 + Wave ≤ 0 時試單。

### Agent 執行指令

當 `status: alert` 且 `near_hard_stop: true`（距 304 < 5%）：
1. 升入戰術指南 P1：「廣達距放棄線 304 僅 {gap_pct}%，準備判斷是否放棄本輪」
2. 日誌待辦：`- [ ] 【2382 廣達】距放棄線 304 僅 {gap_pct}%，確認是否觸發停止條件`

當 `status: ok`（現價 > 304 且安全距離足夠）：
- 記錄即可，由 watchlist_scan 每日更新月線回測狀態

**預計存續**：建倉後由 `position_entered` 永久停用。
