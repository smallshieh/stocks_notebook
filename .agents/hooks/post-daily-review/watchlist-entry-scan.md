---
name: Watchlist N計畫進場掃描
trigger:
  type: every_n_trading_days
  n: 1
script: .venv/Scripts/python.exe scripts/watchlist_scan.py --json --from-log
output_to: journal
alert_prefix: "📋 候補股 N計畫"
---

## 用途

每個交易日自動掃描所有 `watchlist/` 候補股，執行兩層檢查：

1. **通用觸發**：月線回測、月線跌破、季線突破、季線回測
2. **N 計畫進場條件**（`scripts/watchlist_entry_plans.json`）：
   - `zone` 型：現價落在 `[price_min, price_max]` 且 Wave 摘要 ≥ `wave_min`
   - `above_consec` 型：連續 N 日收盤站穩門檻且 Wave 摘要 ≥ `wave_min`
   - 以上兩者都必須再通過 `signal_policy.py` 的進場政策確認；政策品質為低或方向不符時不輸出可落地 action

### 結構化落地

daily-review 步驟 13 只讀 `journals/logs/{REVIEW_DATE}_hooks.json`：

- `status: alert` / `action: p1_upgrade` → 更新戰術指南 P1（加入進場動作待辦）
- `status: warning` / `action: p2_observe` 或 `todo_add` → 寫入 P2 觀察或待辦事項

### Agent 執行指令

> **v2 結構化輸出**：此 hook 腳本現在輸出 JSON `{hook, status, severity, targets[{code, name, action, summary, detail}]}`。
> Agent 應讀取 `journals/logs/{REVIEW_DATE}_hooks.json` 中的結構化結果，而非解析 stdout 文字。
> `action` 欄位：`p1_upgrade` | `p1_observe` | `p2_observe` | `todo_add` | `no_action`

當 target `action` 為 `p1_upgrade` 或 `todo_add` 時：

1. 找到對應 `[code]` 標的
2. 在 `journals/戰術指南.md` 的 P1 區塊加入：
   ```
   - [ ] [{code}] {name} {plan}-{label} 進場條件成立（{TODAY}）：{action}
   ```
3. 在日誌 `## 待辦事項` 加入同樣的 `- [ ]` 行

### 持久化

觸發的 N 計畫警示會寫入 `scripts/_entry_alerts.json`（7 天滾動視窗）。
即使當日未跑 daily-review，次日步驟 9 仍會讀取並補顯示。
