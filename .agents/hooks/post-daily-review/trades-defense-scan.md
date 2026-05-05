---
name: 持倉防守掃描（全倉）
trigger:
  type: every_n_trading_days
  n: 1
script: .venv/Scripts/python.exe scripts/trades_defense_scan.py --json
output_to: journal
alert_prefix: "🛡️ 持倉防守"
---

## 用途

每個交易日自動掃描所有 `trades/` 持倉（含 ETF），檢查以下防守條件：

| 條件 | 觸發門檻 | 嚴重度 |
|------|---------|--------|
| 停損接近 | 現價距硬停損 < 3% | 🔴 高 |
| 月線跌破 | 現價 < MA20 | 🟡 中 |
| 訊號政策防守 | `signal_policy.py` 確認為防守訊號 | 🟡 中 |
| 損益告急 | 損益 ≤ -8% | 🔴 高 |

ETF 類（代號以 0 開頭）降級為純損益監控（不計 Wave Score）。

## 設計意圖

此 hook 提供**全倉通用防守掃描**，補足個股專屬 hook（`ma-breach-1210`、`wave-decay-6239` 等）的覆蓋缺口。
兩者互補：專屬 hook 做更深層的業務邏輯分析，此 hook 確保每個持倉至少有基礎防守訊號。

## 結構化落地

daily-review 步驟 13 只讀 `journals/logs/{REVIEW_DATE}_hooks.json`：

- `status: alert` / `severity: high` → 檢查是否需升 P1 或加入緊急待辦
- `status: warning` / `severity: medium` → 更新戰術指南 P2 或日誌待辦
- `status: ok` → 只保留 hook summary，不更新戰術指南

持續性必須讀 `journals/logs/signal_state.json` 的 `action_tag` / `quality`，不得解析 stdout 或 `_state.json.last_output`。

### Agent 執行指令

> **v2 結構化輸出**：此 hook 腳本現在輸出 JSON `{hook, status, severity, targets[{code, name, action, summary, detail}]}`。
> Agent 應讀取 `journals/logs/{REVIEW_DATE}_hooks.json` 中的結構化結果，而非解析 stdout 文字。
> `action` 欄位：`p1_upgrade` | `p1_observe` | `p2_observe` | `todo_add` | `no_action`

當 target `action` 為 `p1_upgrade`、`p1_observe`、`p2_observe` 或 `todo_add` 時：

1. 判斷警示嚴重度：
   - 「停損接近」或「損益告急」→ 在戰術指南 P1 加入 `- [ ] 緊急：[code] {name} {警示}，確認是否執行停損`
   - 「訊號政策防守」→ 在戰術指南 P2 加入 `- [ ] 觀察：[code] {name} {警示}，下一個交易日確認方向`
2. 在日誌 `## 待辦事項` 加入對應 `- [ ]` 行
