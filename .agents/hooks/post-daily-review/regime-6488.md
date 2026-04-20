---
name: 環球晶區間觀察
trigger:
  type: every_n_trading_days
  n: 10
script: .venv/Scripts/python.exe scripts/regime_tracker.py --code 6488 --support 430 --quiet
output_to: journal
alert_prefix: "📐 環球晶區間觀察"
---

## 說明

追蹤 6488 環球晶的價格區間是否發生結構性遷移。

腳本 `scripts/regime_tracker.py` 計算三個指標：
1. **OU 均衡價 θ**（90日窗口）— 均值回歸模型認為的「公允中心」
2. **430 元支撐守住率**（60日）— 新底部是否確立
3. **最近回測深度** — 買盤承接位是否上移

追蹤結果寫入 `journals/regime_tracking_6488.csv`。

## 判定門檻（僅供人類參考，腳本不自動執行策略調整）

需至少兩項通過才可調整 Phase 0 觸發價：

| 維度 | 確認門檻 | 目前狀態 |
|------|---------|---------|
| OU θ 穩定 | 連續 3 次 θ ≥ 450 | ⏳ 待累積 |
| 支撐守住 | 430 守住率 ≥ 90% + 連續 30 日 | ⏳ 88%/23日 |
| 回測變淺 | 下一次回測低點 ≥ 440 | ⏳ 上次低點 410 |

## 注意事項

- `--support 430` 是固定值，代表舊區間上緣 / 新區間下緣的關鍵位
- 若未來確認中樞上移，應同步更新此 hook 的 support 參數
- 完整報告可手動執行（不帶 --quiet）：
  ```
  .venv/Scripts/python.exe scripts/regime_tracker.py --code 6488 --support 430
  ```
- 查看歷史紀錄：
  ```
  .venv/Scripts/python.exe scripts/regime_tracker.py --code 6488 --history
  ```
