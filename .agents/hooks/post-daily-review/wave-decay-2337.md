---
name: 旺宏 Wave 衰退警示
trigger:
  type: every_n_trading_days
  n: 1
script: .venv/Scripts/python.exe scripts/wave_decay_alert.py --code 2337 --name 旺宏 --alert-wave 0 --context 動能波段Wave<=0全出 --json
output_to: journal
alert_prefix: "⚠️ 旺宏 Wave 衰退"
---

## 背景

監控 2337 旺宏動能波段倉（80 股）的 Wave Score 衰退。動能波段策略中，Wave 是最主要的出場依據。

**持倉**：80 股 @158 元（2026-05-05 建倉），Tactical Tier C。

**出場 SOP（Wave 相關）**：

| Wave 狀況 | 動作 |
|-----------|------|
| Wave ≤ 0 | ⚠️ 警示，搭配其他出場條件確認 |
| Wave ≤ 0 + 量能衰竭（< 60% 均量）| 全出 80 股 |
| Wave ≤ 0 + 開高收低 | 全出 80 股 |
| Wave ≤ 0 + 時間停損（05-12）| 全出 80 股 |

**觀察門檻**：`--alert-wave 0`（Wave 跌至 0 即觸發警示，而非等到負值）。

**平行監控**：`deadline-2337`（時間停損 05-12）+ 人工移動停利（-5% from 最高點）。

### Agent 執行指令

> **v2 結構化輸出**：此 hook 腳本現在輸出 JSON `{hook, status, severity, targets[{code, name, action, summary, detail}]}`。
> Agent 應讀取 `journals/logs/{REVIEW_DATE}_hooks.json` 中的結構化結果，而非解析 stdout 文字。
> `action` 欄位：`p1_upgrade` | `p1_observe` | `p2_observe` | `todo_add` | `no_action`

**收到 `status: alert` / `action: p1_upgrade` 時（Wave ≤ 0）：**
1. 確認當日量能狀況（日誌中 vol_check 結果）：
   - **量縮 < 60% 或開高收低**：升入戰術指南 P1，動作填「旺宏 Wave ≤ 0 + 出場訊號，全出 80 股 @市價」
   - **量能正常**：P2 觀察，「旺宏 Wave 衰退至 {wave}，留意明日是否有量縮確認」

2. 在日誌待辦加入：
   `- [ ] 【2337 旺宏】Wave {wave}，確認量能是否觸發出場條件`

**Wave 回升至 ≥ +2 後**：若持倉繼續，維持 hook active。

**預計存續**：80 股全出後在 `hooks_state.json` 設為 disabled（`position_liquidated`）。
