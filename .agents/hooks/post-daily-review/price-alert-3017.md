---
name: 奇鋐月線回測放棄線監控
trigger:
  type: schedule
  n: 1
script: .venv/Scripts/python.exe scripts/hook_price_alert.py --code 3017 --name 奇鋐 --targets 2535 --hard-stop 2405 --json
output_to: journal
alert_prefix: "🛑 奇鋐月線監控"
---

## 背景

監控 3017 奇鋐月線回測與放棄線。現價 2,705，月線 2,534（距 +6.7%）。

**狀態**：候補追蹤，高檔獲利了結賣壓中，等量縮。
**進場條件**：月線 2,535 + 量縮 ≤ 20MA ×0.8（另由 vol-contract-3017 監控）。
**放棄線**：2,405（月線 -5%），跌破即放棄本輪。
**SOP**：價格觸及 2,535 時手動確認量能；若量縮達標且守月線 → 進場試單。

### Agent 執行指令

當 `status: alert` 且觸及 targets（現價 ≥ 2,535 或 near_hard_stop）：
1. 若觸及 2,535：升入戰術指南 P1「奇鋐觸及月線 2,535，交叉比對 vol-contract-3017 量縮狀態」
2. 若距 2,405 < 5%：升入 P1「奇鋐距放棄線 2,405 僅 {gap_pct}%，準備放棄」

**預計存續**：建倉後由 `position_entered` 永久停用。
