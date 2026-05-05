---
name: 台積電減持監控
trigger:
  type: every_n_trading_days
  n: 1
script: .venv/Scripts/python.exe scripts/wave_decay_alert.py --code 2330 --name 台積電 --alert-wave 0 --context "第一波減持待命（≥ 2,297 元）：三大訊號確認 → 賣 3 股波段倉" --json
output_to: journal
alert_prefix: "📉 台積電減持警示"
---

## 背景

監控 2330 台積電波段倉在高檔區的動能狀態。現價 2,275 接近第一波減持觸發價 2,297（距差 1%）。

**持倉**：底倉 43 股（永不出售）+ 波段調節倉 7 股（等觸發條件執行減持）。

**SOP 減持層級**：

| 波次 | 價格條件 | 觸發訊號（擇一）| 動作 |
|------|---------|----------------|------|
| 第一波 | ≥ **2,297 元** | 見下 | 賣 3 股 → 剩 48 股 |
| 第二波 | ≥ **2,331 元** | 見下 | 再賣 3 股 → 剩 45 股 |
| 第三波 | ≥ **2,606 元** | 見下 | 再賣 2 股 → 剩 43 股（底倉） |

**三大觸發訊號（任一即可）：**
1. 連續 2 日收盤跌破 10MA 或 20MA 且無法站回
2. 單日爆量（近期均量 3~4 倍）但收長上影線或黑 K
3. P/E 超過 37.5 倍（2026E EPS 84.92 元對應股價 3,185 元）

**Wave 作為代理訊號**：Wave ≤ 0 只代表需要檢查動能；是否升級為警示，須由 `signal_policy.py` 確認為防守訊號。門檻命中但品質不足時，只列觀察。

### Agent 執行指令

> **v2 結構化輸出**：此 hook 腳本現在輸出 JSON `{hook, status, severity, targets[{code, name, action, summary, detail}]}`。
> Agent 應讀取 `journals/logs/{REVIEW_DATE}_hooks.json` 中的結構化結果，而非解析 stdout 文字。
> `action` 欄位：`p1_upgrade` | `p1_observe` | `p2_observe` | `todo_add` | `no_action`

**收到 `status: alert` / `action: p1_upgrade` 時（Wave ≤ 0 且政策確認防守）：**
1. 確認當日現價是否 ≥ 2,297：
   - **若是**：升入戰術指南 P1，動作填「台積電第一波減持條件：波段倉接近出場，人工確認三大訊號」；盯盤確認是否有爆量收黑或 MA 跌破
   - **若否（< 2,297）**：在日誌 Hook 區記錄「台積電政策防守訊號成立，但現價未達 2,297 減持觸發價，觀察中」，不升 P1
2. 在盤後日誌 `## 待辦事項` 加入 `- [ ] 【2330 台積電】政策防守訊號成立，確認三大訊號，現價 vs 2,297 元`

**Wave 維持 ≥ +2 且現價 < 2,297：**
- 記錄正常觀察行，不做動作

**預計存續**：波段倉 7 股清空後，在 `hooks_state.json` 將此 hook 設為 disabled。
