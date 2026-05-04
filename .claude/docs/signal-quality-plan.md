# 訊號品質與 Wave 決策政策 — v0.2

**日期**：2026-05-04  
**狀態**：v0.2 已實作，並依 2026-05-05 review 補齊落差  
**核心修正**：Wave total 只保留為摘要，不再直接觸發加碼、減碼、P1/P2。

---

## 一、背景問題

原系統將 `MA + GBM + 分位 + 物理 = Wave Score` 後，直接用總分連動決策。這造成兩類錯誤：

1. **不同語義被互相抵銷**
   - `MA +2`、`分位 -2` 加總為 0，但實際意思是「趨勢強、位置偏高」，不是中性。
   - `GBM +2`、`MA -2` 加總為 0，但實際意思是「模型低估、趨勢轉弱」，不是中性。

2. **不同持倉邏輯被混用**
   - 成長波段股可以用動能追蹤。
   - 殖利率錨定股不能因月線或 Wave 轉弱就賣底倉。
   - 區間滾動股應以分位數買回/賣出區為主，MA/物理只做確認。

代表案例：

| 標的 | 原問題 | v0.2 修正 |
|------|--------|-----------|
| 6239 力成 | 單日 Wave 轉弱容易中段賣出 | 需政策確認防守訊號與持續性 |
| 2317 鴻海 | 趨勢仍強時固定梯次過早賣 | 賣出區但未轉弱 → 抱住不追高 |
| 2546 根基 | Wave -1 在賣出區被升級減碼 | 未見足夠轉弱確認 → 觀察 |
| 1215 卜蜂 / 1210 大成 | 月線失守可能誤傷底倉 | 底倉只看殖利率/配息/硬停損 |

---

## 二、v0.2 決策原則

### 1. Wave total 降級為摘要

Wave total 仍可用於 dashboard 排序與快速掃描，但不得直接產生「強力加碼」、「部分減持」、「強力減持」等交易動作。

禁止規則：

```text
Wave >= 3  → 加碼
Wave <= -2 → 減碼
Wave <= 0  → P1/P2
```

正確流程：

```text
四維診斷 → 策略路由 → 訊號品質 → 政策建議
```

### 2. 決策順序固定

```text
硬規則
  ↓
策略類型
  ↓
四維診斷
  ↓
訊號品質
  ↓
Wave total 摘要
```

硬規則優先於所有技術訊號：

| 硬規則 | 動作 |
|--------|------|
| 硬停損跌破 | 防守處理 |
| 論點失效 | 防守處理 |
| 配息削減 / 殖利率邏輯失效 | 重新評估底倉 |
| Tactical 越權 / Cash 過低 | 限制新增部位 |

### 3. 四維診斷不可互相抵銷

| 維度 | 回答的問題 | 決策用途 |
|------|------------|----------|
| MA | 趨勢結構有沒有壞 | 趨勢濾網 |
| GBM | 相對模型期望偏便宜或偏熱 | 價格期望參考 |
| 分位 | 在買回區、合理區、賣出區或暫停線 | 位置主訊號 |
| 物理 | 動能與量價狀態是否健康 | 確認/降級訊號 |
| 量能 | 今日移動是否有成交量確認 | 品質加權 |
| 持續性 | 訊號是否連續出現 | 品質加權 |

---

## 三、策略路由

策略分類來源優先順序：

1. `capital/position_policy.csv`
2. trades MD 內文推斷
3. 預設 `growth_trend`

目前支援三類：

| strategy_class | 適用 | 主訊號 |
|----------------|------|--------|
| `growth_trend` | 台積電波段、力成波段、緯創、南亞科等 | 趨勢 + 位置 + 動能 |
| `dividend_anchor` | 大成、卜蜂、東和鋼、華碩等 | 殖利率 / 配息 / 硬停損 |
| `reversion_rolling` | 環球晶、中美晶等區間滾動 | 分位數買回/賣出區 |

### growth_trend 規則

| 條件 | 政策建議 |
|------|----------|
| 賣出區，但 MA/物理未轉弱 | 抱住不追高 |
| 賣出區 + 物理轉弱 | 依 SOP 減碼 |
| 賣出區 + 跌破 MA20 + MA 轉弱 | 依 SOP 減碼 |
| 跌破暫停線 | 防守處理 |
| 買回區 + 趨勢未壞 + 動能未壞 | 可依計畫加碼 |
| GBM 低估但 MA 壞 | 等趨勢修復 |

### dividend_anchor 規則

| 條件 | 政策建議 |
|------|----------|
| 月線失守但殖利率仍合理 | 底倉不動；波段倉觀察 |
| Wave 轉弱 | 不影響底倉賣出，只影響波段倉節奏 |
| 價格下跌且殖利率達加碼門檻 | 檢查 Core 配置後才加碼 |
| 配息削減 / 基本面破壞 | 重新評估底倉 |
| 硬停損接近或跌破 | 檢查硬停損 |

### reversion_rolling 規則

| 條件 | 政策建議 |
|------|----------|
| 進入買回區 | 依回測區評估買回 |
| 進入賣出區但動能健康 | 賣出區觀察 |
| 進入賣出區且動能轉弱 | 賣出區處理 |
| 跌破暫停線 | 暫停滾動 / 檢查停損 |

---

## 四、訊號品質

訊號品質用於判斷「今天的政策訊號是否可信」，不是直接決定買賣。

目前實作位置：`scripts/signal_policy.py`

| 因子 | 說明 |
|------|------|
| 方向一致性 | 下跌訊號需位置、MA、物理至少部分確認 |
| 量能 | `volume_ratio >= 1.5` 提高可信度 |
| 持續性 | 最近結構化紀錄連續同向時提高可信度 |
| 策略類型 | 同一組 Wave 分項在不同策略下有不同含義 |

品質標籤：

| 品質 | 用途 |
|------|------|
| 🟢 高 | 可升級為行動，但仍需符合個股 SOP |
| 🟡 中 | 觀察或輕量處理 |
| 🔴 低 | 視為噪音或只列觀察 |

---

## 五、結構化持續性

舊做法：

```text
讀 `_state.json.last_output` 字串，看上次是否也有 ⚠️
```

問題：

- stdout 文字改版會破壞判斷。
- 只存一筆，不知道訊號方向與品質。
- 門檻調整後容易誤判連續性。

新做法：

```text
journals/logs/signal_state.json
```

每筆紀錄保存：

```json
{
  "date": "2026-05-04",
  "source": "wave_score_scan",
  "strategy_class": "growth_trend",
  "wave_components": {
    "ma": 1,
    "gbm": 0,
    "quantile": -2,
    "physics": 2,
    "total": 1
  },
  "quality": "low",
  "action_tag": "upside_growth_extension"
}
```

Agent 判斷持續性時應看 `action_tag` 與 `quality`，不要解析 hook stdout。`⚠️` 可作為 daily-review 的落地觸發格式，但不能作為「連續幾日」的資料來源。

---

## 六、已實作範圍

| 檔案 | 狀態 | 說明 |
|------|------|------|
| `scripts/signal_policy.py` | ✅ 已新增 | 統一策略路由與訊號品質 |
| `capital/position_policy.csv` | ✅ 已新增 | 明確標的策略分類；已補 `2002`、`2886`、`8069` |
| `journals/logs/signal_state.json` | ✅ 已新增 | 結構化持續性狀態檔，初始為空 `signals` |
| `scripts/wave_score_scan.py` | ✅ 已改造 | 戰術指南改輸出「訊號診斷日更新」 |
| `scripts/trades_defense_scan.py` | ✅ 已改造 | Wave 不再直接產生全倉防守警示 |
| `scripts/wave_decay_alert.py` | ✅ 已改造 | Wave 門檻命中但政策未確認時降級觀察 |
| `scripts/watchlist_scan.py` | ✅ 已改造 | N 計畫進場需通過政策確認 |
| `scripts/wave_position.py` | ✅ 已改造 | 單股波段位置分析改輸出政策建議，不再用總分產生加減碼 |
| `scripts/vol_check.py` | ✅ 已升級 | 支援 `--daily` 今日量比，並從 `stocks.csv` 解析 ticker |
| `scripts/daily_scan.bat` | ✅ 已改造 | 支援 `REVIEW_DATE` / 日期參數，避免補執行污染隔日 scan.log |
| `scripts/portfolio_log.py` | ✅ 已改造 | 支援 `--date` / `REVIEW_DATE`，市場資料日期不一致時不寫入歷史 |
| `.agents/hooks/post-daily-review/*.md` | ✅ 已更新 | 持續性不解析 `_state.json.last_output`；stdout `⚠️` 只保留為 daily-review 落地傳輸格式 |
| `.agents/workflows/daily-review.md` | ✅ 已更新 | 來源 C 改為訊號診斷分布，並支援 `{REVIEW_DATE}` 補執行 |
| `tests/test_signal_policy.py` | ✅ 已擴充 | 覆蓋三類策略、硬規則、配息底倉、趨勢破壞與持續性 |

驗證結果：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m py_compile scripts\signal_policy.py scripts\wave_score_scan.py scripts\trades_defense_scan.py scripts\wave_decay_alert.py scripts\watchlist_scan.py scripts\wave_position.py
.\.venv\Scripts\python.exe scripts\wave_score_scan.py --dry-run
.\.venv\Scripts\python.exe scripts\wave_score_scan.py --date 2026-05-04 --dry-run
.\.venv\Scripts\python.exe scripts\vol_check.py --daily --ticker 1215 6239 6488
```

已確認：

- `2546 根基`：Wave -1 且賣出區 → 觀察，不直接減碼。
- `1215 卜蜂`：技術轉弱 → 底倉不因 Wave 賣出。
- `2002`、`2886`、`8069`：已補入 `position_policy.csv`，避免 fallback 誤判。
- `0xxx`：不再用代號開頭推斷 `dividend_anchor`；ETF/配息分類需來自 policy 或文字語義。
- 多數賣出區但趨勢健康標的 → 抱住不追高。

---

## 七、維護事項 / 後續改善

### 1. `vol_check.py` 已升級（階段 1 完成）

目前量能計算已內建在 `signal_policy.compute_volume_metrics()`，`vol_check.py` 也已新增 `--daily` 模式，可獨立檢查今日量比。舊的 3 個月靜態統計模式保留。

使用方式：

```powershell
.\.venv\Scripts\python.exe scripts\vol_check.py --daily --ticker 6239
```

輸出：

```text
6239 力成：
  今日量：1,234,567 股
  5日均量：1,508,234 股
  量比：0.82x → 🔵 縮量
  20日均量：1,389,000 股
  長量比：0.89x
```

已用 trades 內三檔測試：

| 標的 | ticker | 測試結果 |
|------|--------|----------|
| 1215 卜蜂 | `1215.TW` | ✅ daily 模式可輸出量比 |
| 6239 力成 | `6239.TW` | ✅ daily 模式可輸出量比 |
| 6488 環球晶 | `6488.TWO` | ✅ daily 模式可輸出量比，上櫃 ticker 正確 |

### 2. `position_policy.csv` 需定期校正

若標的從波段倉改成底倉，或新增操作倉，需同步更新策略分類。

### 3. 個股 SOP 仍是最終落地條件

`signal_policy.py` 只輸出政策建議，不應覆蓋個股 SOP：

- 力成仍需看批次二/批次三條件。
- 台積電仍需看價格線與三大觸發訊號。
- 卜蜂/大成仍需看殖利率與配息。

### 4. 補執行日期治理

若 daily-review 延後到隔日才做，必須先指定盤後歸屬日期：

```powershell
$env:REVIEW_DATE = "2026-05-04"
.\scripts\daily_scan.bat 2026-05-04
```

原則：

- `scan.log`、`wave_scores.json`、`持倉健診`、`盤後日誌` 都用同一個 `REVIEW_DATE`。
- Hook state 的 `last_run` 寫 `REVIEW_DATE`，不是系統日期。
- 若市場資料日期與 `REVIEW_DATE` 不一致，不應寫入會污染歷史的檔案。

---

## 八、設計底線

1. 不再用 Wave total 直接觸發買賣。
2. 不再讓不同維度互相抵銷成「中性」。
3. 不再讓配息底倉吃成長股的 Wave 減碼規則。
4. 不再解析 stdout 判斷持續性。
5. 所有產生買賣建議的腳本都必須先通過 `signal_policy.py`。
