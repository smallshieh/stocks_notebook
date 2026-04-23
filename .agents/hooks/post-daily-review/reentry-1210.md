---
name: 大成回補提醒
trigger:
  type: every_n_trading_days
  n: 1
script: .venv/Scripts/python.exe scripts/reentry_signal.py --code 1210 --name 大成 --armed-max-shares 1500 --min-wave 2 --reentry-shares 100
output_to: journal
alert_prefix: "🔁 大成回補提醒"
---

## 說明

這個 hook 只做提醒，不直接替代決策。

用途：
- 先確認 1210 是否已從 2,240 股減碼到 **1,500 股或以下**
- 只有在「已減碼」狀態下，才檢查是否滿足回補條件：
  - **收復 20MA**
  - **Wave ≥ +2**

### 預期行為

| 情況 | 輸出 |
|------|------|
| 尚未減碼 | 提醒「未啟用，尚未進入先減碼後回補狀態」 |
| 已減碼但條件未達 | 提醒「尚未達回補條件」 |
| 已減碼且條件達成 | 提醒「評估回補 100 股試單」 |

### Agent 操作建議

1. 只把結果寫進盤後日誌 `## Hooks`
2. 若條件達成，於 daily-review 的整體研判或 1210 區塊標示「可評估回補 100 股」
3. **不要**由 hook 直接把 1210 自動移回 P2，也不要自動改成「一定買回」
