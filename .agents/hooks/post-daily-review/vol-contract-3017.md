---
name: 奇鋐量縮承接監控
trigger:
  type: schedule
  n: 1
script: .venv/Scripts/python.exe scripts/hook_vol_spike.py --code 3017 --name 奇鋐 --vol-contract 0.8 --json
output_to: journal
alert_prefix: "📉 奇鋐量縮監控"
---

## 背景

監控 3017 奇鋐是否出現量縮承接訊號。目前量能仍偏高（1.91x），等賣壓釋放。

**狀態**：候補追蹤，高檔獲利了結賣壓中。
**量縮門檻**：日量 ≤ 20MA × 0.8（≈ 349 萬股）。
**搭配條件**：需同時滿足價格守月線 2,534（另由 price-alert-3017 監控）。
**SOP**：量縮達標時交叉比對 price-alert-3017 是否也觸及月線；兩者同時成立 = 進場窗。

### Agent 執行指令

當 `status: alert`（量縮達標，vol ≤ 0.8x）：
1. 升入戰術指南 P1：「奇鋐量縮達標 {vol_ratio}x ≤ 0.8x，交叉比對 price-alert-3017 月線狀態」
2. 日誌待辦：`- [ ] 【3017 奇鋐】量縮達標，確認價格是否守月線 → 若守則進場試單`

當 `status: ok`（量能尚未達標）：
- 記錄即可

**預計存續**：建倉後由 `position_entered` 永久停用。
