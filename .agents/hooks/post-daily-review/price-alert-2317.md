---
name: 鴻海移動停利監控
trigger:
  type: schedule
  n: 1
script: .venv/Scripts/python.exe scripts/hook_price_alert.py --code 2317 --name 鴻海 --targets 215.0 --hard-stop 190.0 --json
output_to: journal
alert_prefix: "🎯 鴻海移動停利"
---

## 背景

監控 2317 鴻海波段倉（70 股）的移動停利線與硬停損。

**持倉**：底倉 40 股（長線不動）+ 波段倉 70 股（移動停利管理）。
**建倉均價**：204.16 元。
**移動停利狀態**：✅ 已啟動（2026-05-05，現價 239.5 突破 230 觸發線）。

**停利/停損層級**：

| 層級 | 條件 | 動作 |
|------|------|------|
| 移動停利（主軸）| 現價跌破 **215 元** | 波段倉全出（70 股）|
| 移動停利升段 | 現價站上 **250 元** → 停利線升至 235 | 跌破 235 全出 |
| L3 硬停損 | 跌破 **190 元** | 波段倉全出（70 股）|
| L2 停損 | 連 2 日 < 200 | 追賣 35 股（部分波段）|

本 hook 監控：**215 元停利線** + **190 元硬停損**。

### Agent 執行指令

> **v2 結構化輸出**：此 hook 腳本現在輸出 JSON `{hook, status, severity, targets[{code, name, action, summary, detail}]}`。
> Agent 應讀取 `journals/logs/{REVIEW_DATE}_hooks.json` 中的結構化結果，而非解析 stdout 文字。
> `action` 欄位：`p1_upgrade` | `p1_observe` | `p2_observe` | `todo_add` | `no_action`

當 `status: alert` / `action: p1_upgrade` 時：

1. **現價跌破 215**（`closest_target_gap_pct = 0`）：
   - 升入戰術指南 P1：「鴻海移動停利觸發，波段倉 70 股全出 @市價」
   - 日誌待辦：`- [ ] 【2317 鴻海】移動停利 215 跌破，今日執行波段倉 70 股全出`

2. **距 215 < 5%**（`status: warning`）：
   - P2 觀察：「鴻海接近停利線 215（距 {gap}%），留意明日收盤」

3. **距硬停損 190 < 5%**（`near_hard_stop: true`）：
   - P1：「鴻海距 L3 硬停損 190 僅 {gap}%，波段倉全出警戒」

**移動停利升段觸發後（現價站上 250）**：
- 人工更新此 hook 的 script 參數，將 `--targets 215.0` 改為 `--targets 235.0`
- 在 `hooks.yaml` 中修改對應 script 命令

**預計存續**：波段倉 70 股全出後，`hooks_state.json` 設為 disabled；底倉 40 股不受此 hook 管控。
