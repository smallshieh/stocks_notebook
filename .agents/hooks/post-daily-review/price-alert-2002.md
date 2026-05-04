---
name: 中鋼反彈賣點監控
trigger:
  type: schedule
  n: 1
script: .venv/Scripts/python.exe scripts/hook_price_alert.py --code 2002 --targets 20.5,21.0,21.5 --hard-stop 17.5 --json
output_to: journal
alert_prefix: "📈 中鋼反彈賣點"
---

## 背景

監控 2002 中鋼操作倉（3,000 股）的反彈賣點與硬止損接近度。

**持倉**：操作倉 3,000 股，底倉 10,000 股不動。
**成本**：約 26.15 元（高成本位，μ = -13.3%，不具殖利率邏輯）。

**SOP 減持計畫（2026-04-21 下修）**：
- 反彈 20.5 元 → 賣 1,000 股
- 反彈 21.0 元 → 賣 1,000 股  
- 反彈 21.5 元 → 賣 1,100 股（操作倉清空）
- 硬止損：跌破 17.5 元 → 操作倉全數市價出清

**本 hook 提供**：現價接近任一反彈目標或硬止損時觸發警示。

### Agent 執行指令

> **v2 結構化輸出**：此 hook 腳本現在輸出 JSON `{hook, status, severity, targets[{code, name, action, summary, detail}]}`。
> Agent 應讀取 `journals/logs/{REVIEW_DATE}_hooks.json` 中的結構化結果，而非解析 stdout 文字。
> `action` 欄位：`p1_upgrade` | `p1_observe` | `p2_observe` | `todo_add` | `no_action`

當 `status: alert` 時（現價接近反彈目標或硬止損）：
1. 檢查 `detail` 中 `closest_target` 欄位：
   - 若為反彈目標價（20.5/21.0/21.5）：在戰術指南 P1 加入「中鋼操作倉反彈至 {price}，執行減碼 {shares} 股」
   - 若 `near_hard_stop: true`：在戰術指南 P1 加入「中鋼距硬止損 17.5 僅 {gap_pct}%，準備操作倉全出」
2. 在日誌待辦事項加入對應 `- [ ]`

**預計存續**：操作倉全數出清後停用。
