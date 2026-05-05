# Hook v2 機制說明

**版本**：v2
**日期**：2026-05-05
**取代**：舊 `.md` frontmatter + `_state.json` + stdout `⚠️` 解析機制

---

## 一、架構總覽

```
┌──────────────────────────────────────────────────────────┐
│                    設置層 (Design Time)                    │
│  hooks.yaml      ← 中央註冊表（觸發規則/生命週期/重試）     │
│  hooks_state.json ← 統一狀態（排程歷史 + 診斷數據）        │
│  *.md            ← 人類可讀文件（背景 + Agent 操作指南）    │
├──────────────────────────────────────────────────────────┤
│                    觸發層 (Runtime)                        │
│  hook_runner.py  ← 執行引擎（讀 registry → 判斷到期/復活  │
│                    → 傳入 REVIEW_DATE → 收集 JSON →       │
│                    更新 state，保留同日既有 log）          │
│  hook_output.py  ← 共用輸出模組（HookResult + HookTarget） │
├──────────────────────────────────────────────────────────┤
│                    處理層 (Post-Trigger)                   │
│  {DATE}_hooks.json ← 盤後日誌用的結構化摘要                │
│  Agent           ← 讀取 JSON → 依 severity 確認 action    │
│                     → 更新戰術指南 P1/P2 → 寫入日誌        │
└──────────────────────────────────────────────────────────┘
```

---

## 二、Hook 定義：`hooks.yaml`

### 完整欄位

```yaml
hooks:
  ma-breach-1210:                    # hook 唯一識別碼
    name: "大成月線跌破計數"           # 顯示名稱
    script: ".venv/Scripts/python.exe scripts/ma_breach_counter.py --code 1210 --ma 20 --alert-days 3 --name 大成 --json"
    targets: ["1210"]                # 影響的股票代號（* = 通用）
    strategy_class: "dividend_anchor" # 策略類型（供訊號品質參考）
    severity_default: "high"         # 預設嚴重度 (high/medium/low)

    trigger:                         # 觸發條件
      type: schedule                 # schedule | condition | on_event
      every_n_trading_days: 1        # 每 N 個交易日執行一次

    lifecycle:                       # 生命週期自動管理
      auto_disable_on: "ma20_recovered"      # 月線收復 → 自動停用
      auto_reenable_on: "ma20_breached"      # 再次跌破 → 自動啟用
      permanent_disable_on: null             # 何時永久停用

    retry:                           # 失敗重試
      max_consecutive_failures: 2    # 連續失敗 N 次後降級
      fallback_frequency_days: 1     # 降級後的檢查頻率

    doc: "ma-breach-1210.md"         # 對應的人類可讀文件
```

### 觸發類型

| type | 說明 | 適用場景 |
|------|------|---------|
| `schedule` | 定時排程（`every_n_trading_days`） | 每日檢查：Wave 衰退、月線跌破、硬死線倒數 |
| `condition` | 條件觸發（檢查 `hooks_state.json` 欄位） | 價格達標、μ 轉負、殖利率跌破門檻 |
| `on_event` | 事件驅動（由其他腳本寫入 flag） | 模型刷新需要、N 計畫觸發 |

> 目前全部使用 `schedule`，`condition` 和 `on_event` 為預留介面。

---

## 三、狀態管理：`hooks_state.json`

```json
{
  "meta": {
    "last_run": "2026-05-05",
    "migrated_from": { ... }
  },
  "hooks": {
    "ma-breach-1210": {
      "status": "active",           // active | disabled
      "last_run": "2026-05-04",     // 上次執行日期
      "run_count": 8,               // 累計執行次數
      "consecutive_failures": 0,    // 連續失敗次數
      "disabled_reason": null,      // 若 disabled，記錄原因
      "last_result": {              // 上次執行結果摘要
        "status": "alert",
        "severity": "high",
        "summary": "月線下方連續第 8 日"
      }
    }
  },
  "stocks": {
    "1210": {
      "ma20_status": "below",       // above | below
      "ma20_breach_days": 8,
      "wave_score": 1,
      "signal_quality": "medium",
      "position_status": "holding"
    }
  }
}
```

**與舊系統的差異**：
- 舊：`_state.json`（排程） + `signal_state.json`（診斷）分開存，互不參考
- 新：合併為單一 `hooks_state.json`，hook 可直接讀取 stocks 診斷數據判斷是否需要觸發

---

## 四、腳本輸出格式（`hook_output.py`）

所有 hook 腳本在 `--json` 模式下輸出以下結構：

```json
{
  "hook": "ma-breach-1210",
  "timestamp": "2026-05-05",
  "status": "alert",                // ok | alert | warning | error
  "severity": "high",               // high | medium | low
  "targets": [
    {
      "code": "1210",
      "name": "大成",
      "action": "p1_observe",       // p1_upgrade | p1_resolved | p2_observe | todo_add | no_action
      "summary": "月線下方連續第 9 日",
      "detail": {
        "breach_days": 9,
        "ma20": 53.80,
        "current_price": 52.30,
        "dividend_yield": 5.41
      }
    }
  ],
  "lifecycle_event": null,          // auto_disable | auto_enable | null
  "error_message": null
}
```

**與舊系統的差異**：
- 舊：Agent 解析 stdout 中的 `⚠️` 關鍵字 → 容易因輸出格式變動而漏訊號
- 新：結構化 JSON，每個欄位有明確定義 → `severity` 決定優先級，`action` 決定落地動作

### action 欄位說明

| action | 含義 | Agent 應做的動作 |
|--------|------|-----------------|
| `p1_upgrade` | 需升級到 P1 | 更新戰術指南 P1 對應條目 |
| `p1_observe` | P1 觀察（不立即動作） | 更新戰術指南 P1 觀察注記 |
| `p1_resolved` | P1 條件已解除 | 從 P1 移除，移回 P2 |
| `p2_observe` | P2 監控 | 更新戰術指南 P2 對應條目 |
| `todo_add` | 加入待辦 | 寫入盤後日誌 `## 待辦事項` |
| `no_action` | 純記錄 | 不動作，僅保留記錄 |

---

## 五、執行流程

### daily-review 中的位置

```
daily_scan.bat
  └→ [1/5] portfolio_report.py  → 持倉健診
  └→ [2/5] portfolio_log.py     → 歷史記錄
  └→ [3/5] watchlist_scan.py    → 候補股掃描 (寫入 scan.log)
  └→ [4/5] wave_score_scan.py   → Wave Score (寫入戰術指南 + scan.log)
  └→ [5/5] event_detector.py    → 事件偵測 (寫入 scan.log)

daily-review (Agent 驅動)
  ├→ 步驟 3: market_state.py     → 來源 A
  ├→ 步驟 5: portfolio_report    → 來源 C
  ├→ 步驟 7: chip_check.py       → 來源 B
  ├→ 步驟 7.5: hook_runner.py    → 來源 D① ← 新架構
  │   ├─ 讀取 hooks.yaml
  │   ├─ 讀取 hooks_state.json
  │   ├─ 判斷哪些 hook 排程到期，或 disabled hook 是否需 auto-reenable 檢查
  │   ├─ subprocess 執行腳本，並傳入 REVIEW_DATE 環境變數
  │   ├─ 解析 JSON stdout
  │   ├─ 更新 hooks_state.json（排程 + 生命週期）
  │   └─ 寫入 journals/logs/{REVIEW_DATE}_hooks.json（同日重跑保留既有觸發結果）
  ├→ 步驟 8: 四源合議
  ├→ 步驟 13: Hook 結果落地     ← 改為結構化
  │   ├─ 讀取 {REVIEW_DATE}_hooks.json
  │   ├─ 按 severity 排序
  │   ├─ Agent 逐項確認 action
  │   └─ 更新戰術指南 P1/P2 + 日誌
  └→ 步驟 12: 輸出摘要
```

### 重試機制

```
腳本執行成功 → last_run 更新 → 等 n 個交易日後再跑

腳本執行失敗：
  consecutive_failures += 1
  last_run 不更新（保留下次重試機會）

  if consecutive_failures >= max_consecutive_failures:
      降級為 fallback_frequency_days（預設每日重試一次）
      不再等原本的 n 天週期
```

例如 `regime-6488` (n=10)：連續失敗 2 次後，改為每天重試，不會因一次網路問題等 2 週。

---

## 六、生命週期自動管理

不再靠人手改檔名（`_ma-breach-1210.md`）來暫停/啟用 hook。

### 自動轉換規則

| 事件 | 觸發來源 | 效果 |
|------|---------|------|
| `auto_disable_on: "ma20_recovered"` | 腳本偵測月線收復 → 輸出 `lifecycle_event: "auto_disable"` | `status` → `disabled` |
| `auto_reenable_on: "ma20_breached"` | runner 對因月線收復而 disabled 的 MA hook 做輕量檢查；腳本回報 `breach_days >= 1` | `status` → `active` |
| `permanent_disable_on: "deadline_passed"` | 硬死線已過 | `status` → `disabled`，不再排程 |
| `permanent_disable_on: "position_liquidated"` | 持倉已清空 | `status` → `disabled` |

### 狀態機

```
  [defined] ─→ [active] ─→ [triggered] ─→ [processing]
                   ↑  │                        │
                   │  └→ [disabled] ←──────────┘
                   │        │
                   └────────┘  (auto_reenable)
```

---

## 七、18 個 Hook 清單

### 月線跌破監控 (n=1)

| Hook | 標的 | 策略 | 腳本 |
|------|------|------|------|
| `ma-breach-1210` | 1210 大成 | dividend_anchor | ma_breach_counter.py |
| `ma-breach-1215` | 1215 卜蜂 | dividend_anchor | ma_breach_counter.py |
| `ma-breach-2317` | 2317 鴻海 | growth_trend | ma_breach_counter.py |
| `ma-breach-2006` | 2006 東和鋼 | dividend_anchor | ma_breach_counter.py |

### 硬死線倒計時

| Hook | 標的 | n | 腳本 |
|------|------|---|------|
| `deadline-2449` | 2449 京元電 | 1 (05-12) | deadline_counter.py |
| `deadline-8069` | 8069 元太 | 5 (06-30) | deadline_counter.py |

### Wave 動能衰退 (n=1)

| Hook | 標的 | 策略 | 警示門檻 |
|------|------|------|---------|
| `wave-decay-2330` | 2330 台積電 | growth_trend | Wave ≤ 0 |
| `wave-decay-6239` | 6239 力成 | growth_trend | Wave ≤ -2 |
| `wave-decay-5483` | 5483 中美晶 | reversion_rolling | Wave ≤ 0 |

### 區間觀察（雙週）

| Hook | 標的 | n | 腳本 |
|------|------|---|------|
| `regime-6488` | 6488 環球晶 | 10 | regime_tracker.py |
| `regime-8069` | 8069 元太 | 10 | regime_tracker.py |

### 通用掃描 (n=1)

| Hook | 範圍 | 腳本 |
|------|------|------|
| `trades-defense-scan` | 全持倉防守 | trades_defense_scan.py |
| `watchlist-entry-scan` | 候補股 N 計畫 | watchlist_scan.py --from-log |
| `model-refresh-on-event` | 事件驅動模型刷新 | model_refresh.py --from-events |
| `thesis-expiry` | 前瞻觀點到期 | thesis_expiry.py (n=5) |

### 特殊條件

| Hook | 標的 | 用途 |
|------|------|------|
| `reentry-1210` | 1210 大成 | 已減碼後的回補提醒 |
| `price-alert-2002` | 2002 中鋼 | 反彈賣點 20.5/21/21.5 + 硬止損 17.5 |
| `vol-spike-2454` | 2454 聯發科 | 爆量 ≥ 1.5x + 收黑 K 偵測 |

---

## 八、如何新增一個 Hook

### Step 1：建立腳本（或複用既有腳本）

確保腳本支援 `--json` 模式：

```python
# 在 script.py 結尾
if args.json:
    from hook_output import HookResult, HookTarget, output, today_str
    result = HookResult(
        hook="my-new-hook",
        timestamp=today_str(),
        status="alert" if triggered else "ok",
        severity="high",
        targets=[HookTarget(code=code, name=name, action="p1_upgrade", summary="...", detail={})],
    )
    output(result)
```

### Step 2：寫入 `hooks.yaml`

```yaml
hooks:
  my-new-hook:
    name: "新 Hook 顯示名稱"
    script: ".venv/Scripts/python.exe scripts/my_script.py --code XXXX --json"
    targets: ["XXXX"]
    severity_default: "high"
    trigger:
      type: schedule
      every_n_trading_days: 1
    lifecycle:
      permanent_disable_on: null
    retry:
      max_consecutive_failures: 2
      fallback_frequency_days: 1
    doc: "my-new-hook.md"
```

### Step 3：建立 `.md` 文件

```markdown
---
name: 新 Hook 顯示名稱
trigger:
  type: schedule
  n: 1
script: .venv/Scripts/python.exe scripts/my_script.py --code XXXX --json
output_to: journal
alert_prefix: "🔔 新 Hook"
---

## 背景
說明這個 hook 監控什麼、為什麼需要。

### Agent 執行指令

> **v2 結構化輸出**：此 hook 腳本現在輸出 JSON `{hook, status, severity, targets[{code, name, action, summary, detail}]}`。
> Agent 應讀取 `journals/logs/{REVIEW_DATE}_hooks.json` 中的結構化結果，而非解析 stdout 文字。

當 `status: alert` 時：
1. 檢查 `detail` 欄位中的具體資訊
2. 依 `action` 欄位決定落地動作
3. 更新戰術指南對應區塊
```

### Step 4：Dry-run 驗證

```powershell
.\.venv\Scripts\python.exe scripts/hook_runner.py --dry-run
```

---

## 九、常用指令

```powershell
# Dry-run（預覽哪些 hook 會觸發，不執行、不寫 state、不寫 hooks.json）
.\.venv\Scripts\python.exe scripts/hook_runner.py --dry-run

# 指定日期執行（補執行、測試用）
.\.venv\Scripts\python.exe scripts/hook_runner.py --date 2026-05-04

# 或由 daily-review 先設定 REVIEW_DATE，hook_runner 會自動讀取並傳給子腳本
$env:REVIEW_DATE = "2026-05-04"
.\.venv\Scripts\python.exe scripts/hook_runner.py

# 測試單一 hook 的 JSON 輸出
.\.venv\Scripts\python.exe scripts/ma_breach_counter.py --code 1210 --ma 20 --alert-days 3 --name 大成 --json

# 查看當前 hook 狀態
.\.venv\Scripts\python.exe -c "import json; s=json.load(open('.agents/hooks/post-daily-review/hooks_state.json')); print(json.dumps({k:{'status':v['status'],'last_run':v['last_run']} for k,v in s['hooks'].items()}, indent=2, ensure_ascii=False))"

# 手動重設 hook 狀態（如需要強制重跑）
# 編輯 hooks_state.json，將 target hook 的 last_run 設為 null
```
