---
name: 鴻海月線停損監控
trigger:
  type: every_n_trading_days
  n: 1
script: .venv/Scripts/python.exe scripts/ma_breach_counter.py --code 2317 --ma 20 --alert-days 2 --name 鴻海
output_to: journal
alert_prefix: "⚠️ 鴻海月線停損"
---

## 背景

監控 2317 鴻海波段倉的 L2 停損條件（連 2 日收盤 < 200 元）。

**持倉**：底倉 40 + 波段倉 95 股，合計 135 股 @均成本待確認。

**SOP 停損層級**：
- L2：連 2 日 < 200 → 追賣 50 股波段倉
- L3：跌破 190 → 清空剩餘 95 股波段倉
- 移動停利（若站上 230）：停利線移至 215，跌破全出

**20MA 目前約 206，與 200 停損線接近，用月線跌破代理 L2 條件。**

### Agent 執行指令（達門檻時強制執行）

> **v2 結構化輸出**：此 hook 腳本現在輸出 JSON `{hook, status, severity, targets[{code, name, action, summary, detail}]}`。
> Agent 應讀取 `journals/logs/{REVIEW_DATE}_hooks.json` 中的結構化結果，而非解析 stdout 文字。
> `action` 欄位：`p1_upgrade` | `p1_observe` | `p2_observe` | `todo_add` | `no_action`

當輸出包含「已達 2 日門檻」時：
1. 在戰術指南 `## P1` 新增（或更新）鴻海條目：動作填「L2 停損觸發：追賣 50 股波段倉 @市價」
2. 在盤後日誌 `## 待辦事項` 加入 `- [ ] 【2317 鴻海】L2 停損觸發，追賣波段 50 股`
3. 在日誌標記「→ 已更新 P1」

當輸出包含「月線之上」（計數歸零）時：
1. 若已在 P1，確認停損已解除後移回 P2
2. 加底線前綴暫停此 hook（`_ma-breach-2317.md`）

**預計存續**：短期，待鴻海月線情況明朗後暫停。
