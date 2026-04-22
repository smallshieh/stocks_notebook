# 股票筆記本｜Scripts 工具手冊

> 適用：任何 AI Agent 或操作者，快速掌握本系統所有分析工具的用途與指令  
> Python 環境：**永遠使用 `.venv`** → `S:\股票筆記\.venv\Scripts\python.exe`  
> 工作目錄：`S:\股票筆記\`（所有指令請在此處執行）

---

## 工具總覽

| 腳本 | 類型 | 功能摘要 |
|------|------|---------|
| **`market_state.py`** | **決策架構（來源A）** | **大盤狀態判斷（多頭/震盪/空頭）+ 建議資產配置** |
| **`chip_check.py`** | **決策架構（來源B）** | **TWSE 三大法人籌碼抓取 + A/B/C/D 情境觸發核對** |
| **`wave_score_scan.py`** | **決策架構（來源C）** | **全持倉 Wave Score 掃描（加碼/減碼/觀察訊號）** |
| `stock_analyzer.py` | 資料查詢 | 即時股價、月線、停損預警 |
| `physics_engine.py` | 物理模型 | 動量、動能、雷諾數診斷（模組）|
| `quantile_engine.py` | 統計模型 | 回檔分位數決策（賣出/買回/暫停區）|
| `ou_analysis_6488.py` | 機率模型 | OU 均值回歸 + 蒙地卡羅機率預測 |
| `recalc_rolling_ranges.py` | 策略工具 | 批次重算零股滾動法價格區間 |
| `portfolio_report.py` | 報告工具 | 持倉健診報告（盤後全倉掃描）|
| `portfolio_log.py` | 紀錄工具 | 資金 / 持倉快照存檔 |
| `performance_report.py` | 報告工具 | 績效報告（含計算資金輪轉效益）|
| `sync_to_notion.py` | 同步工具 | 將 MD 檔同步至 Notion |
| `update_trade_prices.py` | MD 更新 | 從持倉健診刷新 trades/ 的目前價格、20MA、殖利率 |
| `watchlist_scan.py` | 監控工具 | 觀察清單標的掃描與警示 |
| `update_stocks.py` | 資料維護 | 新增 / 查詢 stocks.csv 標的清單 |
| `vol_check.py` | 工具 | 個股波動率快速查詢 |
| `md_outline.py` | MD 工具 | 列出 Markdown 標題結構與行號 |
| `md_section.py` | MD 工具 | 只讀指定 Markdown 區塊 |
| `md_update_section.py` | MD 工具 | 安全替換指定 Markdown 區塊 |
| `regime_tracker.py` | ��控工具 | 價格區間遷移追蹤（OU θ、支撐守住率、回測深度）|
| `thesis_expiry.py` | 監控工具 | 前瞻觀點與催化劑到期提醒 |
| `daily_scan.bat` | 排程 | 每日自動執行盤後掃描 |

---

## 零、每日決策架構工具（daily-review 四源合議）

> 這三個腳本是 `/daily-review` workflow 的核心數據來源，輸出「訊號」供 Agent 合議成整體操作方向。

### `market_state.py` — 大盤狀態（來源 A）

```powershell
.venv\Scripts\python.exe scripts/market_state.py
.venv\Scripts\python.exe scripts/market_state.py --quiet   # 只輸出 Markdown 段落
```

**輸出**：市場狀態（多頭確立/震盪/空頭/危機）、建議 Core:Tactical:Cash 比例、操作指引

---

### `chip_check.py` — 三大法人籌碼（來源 B）

```powershell
# 當日籌碼（自動日期）
.venv\Scripts\python.exe scripts/chip_check.py

# 指定日期（補歷史快取）
.venv\Scripts\python.exe scripts/chip_check.py --date 20260421

# 只輸出 Markdown 段落（供日誌貼入）
.venv\Scripts\python.exe scripts/chip_check.py --quiet

# 單行摘要（供 daily-review 整合）
.venv\Scripts\python.exe scripts/chip_check.py --summary
```

**資料來源**：TWSE BFI82U API（無需帳號，自動抓取）  
**快取位置**：`journals/logs/_chip_history.json`（保留近 10 日）  
**觸發情境**：

| 情境 | 名稱 | 觸發條件 | 對應操作 |
|------|------|---------|----------|
| A | 多頭鞏固 | 外資連三日買超 ≥ 30 億 | 波段倉持有，停利不提前 |
| B | 高檔出貨 | 外資單日轉賣超 ≥ 30 億 + 爆量收黑 | 波段倉減碼（2330/2454/2382 優先）|
| C | 短線退潮 | 投信翻買後連兩日撤退 | 觀察，不加碼 |
| D | 對沖解除 | 自營商避險部位由負轉正 | 可輕倉跟進 |

---

### `wave_score_scan.py` — Wave Score 全倉掃描（來源 C）

```powershell
.venv\Scripts\python.exe scripts/wave_score_scan.py
```

**輸出位置**：`journals/logs/{TODAY}_scan.log`、覆寫戰術指南 `## Wave Score 日更新` 區塊  
**訊號分類**：🔴 需即時處理（動能背離）/ 🟢 加碼機會 / 🟡 觀察

---

## 一、資料查詢

### `stock_analyzer.py` — 股價 / 月線 / 停損

```powershell
# 查詢單一股票（現價、月線、殖利率）
.venv\Scripts\python.exe scripts/stock_analyzer.py --ticker 6488

# 同時查詢多個
.venv\Scripts\python.exe scripts/stock_analyzer.py --ticker 6488 2330 8069

# 帶成本查停損
.venv\Scripts\python.exe scripts/stock_analyzer.py --ticker 6488 --cost 603.27

# 掃描所有 trades/ 下的持倉
.venv\Scripts\python.exe scripts/stock_analyzer.py --scan-trades
```

---

## 二、物理模型診斷（動量 / 動能 / 雷諾數）

### `physics_engine.py` — 核心物理模型（模組，不直接執行）

透過 `stock_analyzer.py --physics` 呼叫：

```powershell
.venv\Scripts\python.exe scripts/stock_analyzer.py --ticker 6488 --physics
```

**輸出解讀**：
| 指標 | 對應物理量 | 意涵 |
|------|----------|------|
| 動量 p | 成交量 × 日報酬率 | 正值表示資金流入推升 |
| 動能 KE | ½ × 量 × 報酬率² | 波動劇烈程度 |
| 雷諾數 Re | 慣性 / 黏性比 | >1 趨勢穩定；<1 震盪多 |

---

## 三、統計分位數決策

### `quantile_engine.py` — 歷史回檔分位診斷（模組）

透過 `stock_analyzer.py --quantile` 或 `recalc_rolling_ranges.py` 呼叫：

```powershell
.venv\Scripts\python.exe scripts/stock_analyzer.py --ticker 5483 --quantile
```

**輸出**：賣出區 / 常規買回區 / 深回檔區 / 暫停線（依 dd50, dd70, dd85 分位）

---

## 四、均值回歸機率預測（OU 模型）

### `ou_analysis.py` — 通用 OU + 蒙地卡羅機率預測

> 任何標的皆可使用，## 五、趨勢股機率預測（GBM 模型）

### `gbm_analysis.py` — 幾何布朗運動機率預測

> 適用於具備「長期向上漂移（Drift）」特性的標的（如台積電 2330、大盤 0050）。
> 不適用於景氣循環股或區間震盪股（請改用 `ou_analysis.py`）。

```powershell
# 基本使用（自動推算 10, 20, 60 日目標與機率）
.venv\Scripts\python.exe scripts/gbm_analysis.py --code 2330

# 自訂查特定天數
.venv\Scripts\python.exe scripts/gbm_analysis.py --code 0050 --days 20,40,60
```

**輸出重點**：
- 趨勢漂移率 μ（年化，正值代表長期看漲）
- 期望價（Expected Value）、向上突破與向下跌破的機率
- **注意**：GBM 機率具備不對稱性，只要 μ > 0，長期向上突破的機率會顯著高於向下跌破。

---

## 六、零股滾動法價格區間重算

### `recalc_rolling_ranges.py` — 批次重算策略檔

```powershell
# 預覽單一標的（不寫入）
.venv\Scripts\python.exe scripts/recalc_rolling_ranges.py --code 5483

# 重算並寫入策略檔
.venv\Scripts\python.exe scripts/recalc_rolling_ranges.py --code 5483 --write

# 一次重算多檔
.venv\Scripts\python.exe scripts/recalc_rolling_ranges.py --code 5483,6488 --write

# 全部標的批次
.venv\Scripts\python.exe scripts/recalc_rolling_ranges.py --all --write
```

**輸出位置**：`strategies/零股滾動法_實戰_{code}{name}.md`  
**詳細說明**：`scripts/零股滾動法區間重算_使用說明.md`

---

## 七、持倉報告

### `portfolio_report.py` — 盤後持倉健診

```powershell
.venv\Scripts\python.exe scripts/portfolio_report.py
```

**輸出**：`journals/持倉健診_{TODAY}.md`（停損預警、月線狀態、損益）

### `portfolio_log.py` — 持倉快照存檔

```powershell
.venv\Scripts\python.exe scripts/portfolio_log.py
```

### `performance_report.py` — 績效報告

```powershell
.venv\Scripts\python.exe scripts/performance_report.py
```

---

## 七、持倉筆記價格刷新

### `update_trade_prices.py` — 從持倉健診更新 trades 市場欄位

> 與 `/fill-trades` 不同：`fill-trades` 只補空白；本工具會刷新既有市場欄位。  
> 只更新 `目前價格`、`月線 (20MA) 位置`、`預估殖利率 / 現價殖利率 / 殖利率`。

```powershell
# 預覽所有會更新的欄位（不寫入）
.venv\Scripts\python.exe scripts/update_trade_prices.py

# 確認 dry-run 無誤後寫入
.venv\Scripts\python.exe scripts/update_trade_prices.py --write

# 只更新單一代號
.venv\Scripts\python.exe scripts/update_trade_prices.py --code 1210
.venv\Scripts\python.exe scripts/update_trade_prices.py --code 1210 --write

# 指定健診報告
.venv\Scripts\python.exe scripts/update_trade_prices.py --report 持倉健診_2026-04-16.md --write
```

**安全邊界**：
- 只改 `## 基本資訊` 區塊；舊格式檔案只改檔案開頭 metadata 區。
- 不改買進均價、集保股數、總成本、交易紀錄、停損預警、策略規劃。
- 預設 dry-run；必須加 `--write` 才會寫檔。

---

## 八、Notion 同步

### `sync_to_notion.py` — 同步 MD 至 Notion

```powershell
# 同步單一檔案
.venv\Scripts\python.exe scripts/sync_to_notion.py journals/戰術指南.md

# 同步多檔
.venv\Scripts\python.exe scripts/sync_to_notion.py journals/戰術指南.md trades/6488_環球晶.md
```

**憑證位置**：`scripts/notion_creds.py`（已 gitignore，不可提交）  
**詳細說明**：`/sync-notion` workflow

---


## 九、stocks.csv 維護

### `update_stocks.py` — 新增標的清單

> 只新增，不刪除（下市須手動清除）

```powershell
# 新增單一標的（自動偵測上市/上櫃 + 抓名稱）
.venv\Scripts\python.exe scripts/update_stocks.py --code 2454

# 批次新增
.venv\Scripts\python.exe scripts/update_stocks.py --code 2454,3481,4991

# 手動指定市場與名稱（跳過自動查詢，速度更快）
.venv\Scripts\python.exe scripts/update_stocks.py --code 2454 --market TWO --name 聯發科 --type 股票

# 預覽模式（不寫入）
.venv\Scripts\python.exe scripts/update_stocks.py --code 2454 --dry-run
```

**判斷邏輯**：先查 `stocks.csv`（已存在則跳過），再自動試 `.TWO` / `.TW` 取得 ticker 與名稱。

---

## 十、Markdown 結構化讀寫

> Agent 讀 `trades/`、`watchlist/`、`journals/` 長篇 MD 時，先用 outline 找區塊，再用 section 讀必要內容，避免整檔讀取。
> 詳細規則見：`scripts/MD_TOOLS_FOR_AGENTS.md`

### `md_outline.py` — 列出標題與行號

```powershell
.venv\Scripts\python.exe scripts/md_outline.py trades/00919_群益台灣精選高息.md
.venv\Scripts\python.exe scripts/md_outline.py trades/00919_群益台灣精選高息.md --json
```

### `md_section.py` — 讀指定區塊

```powershell
.venv\Scripts\python.exe scripts/md_section.py trades/00919_群益台灣精選高息.md "基本資訊"
.venv\Scripts\python.exe scripts/md_section.py trades/00919_群益台灣精選高息.md --section "基本資訊" --section "交易紀錄"
```

### `md_update_section.py` — 替換指定區塊

```powershell
# 先 dry-run
.venv\Scripts\python.exe scripts/md_update_section.py trades/00919_群益台灣精選高息.md "停損預警區" --from tmp_section.md --dry-run

# 確認後寫入
.venv\Scripts\python.exe scripts/md_update_section.py trades/00919_群益台灣精選高息.md "停損預警區" --from tmp_section.md
```

---

## 十一、價格區間遷移追蹤

### `regime_tracker.py` — 結構性區間變化監控

> 用於判斷個股的價格中樞是否發生永久性遷移（而非暫時波動）。
> 通常由 daily-review hook 自動觸發（每 10 個交易日），也可手動執行。

```powershell
# 完整報告（含判定門檻評估）
.venv\Scripts\python.exe scripts/regime_tracker.py --code 6488 --support 430

# 靜默模式（供 hook 呼叫，只輸出一行摘要）
.venv\Scripts\python.exe scripts/regime_tracker.py --code 6488 --support 430 --quiet

# 查看歷史追蹤紀錄
.venv\Scripts\python.exe scripts/regime_tracker.py --code 6488 --history

# 不指定 support（自動推算為近 120 日 P25，四捨五入到 10 元）
.venv\Scripts\python.exe scripts/regime_tracker.py --code 6488
```

**三個追蹤指標**：

| 指標 | 計算方式 | 意義 |
|------|---------|------|
| OU 均衡價 θ | 90日窗口 OLS 估算 | 均值回歸模型認為的「公允中心」|
| 支撐守住率 | 近 60 日站穩指定支撐的比率 + 最長連續天數 | 新底部是否確立 |
| 最近回測深度 | 近 120 日內最大峰→谷跌幅 | 買盤承接位是否上移 |

**輸出位置**：`journals/regime_tracking_{code}.csv`（每次執行追加一行）

**與 hook 系統的關係**：本腳本是 `.agents/hooks/post-daily-review/regime-6488.md` 的執行標的，由 daily-review 步驟 13 自動門控觸發。詳見 `.agents/hooks/README.md`。

---

## 十二、前瞻觀點到期提醒

### `thesis_expiry.py` — 觀點與催化劑到期掃描

> 掃描 `strategies/thesis_tracking.md` Active 區 + `trades/*.md` 催化劑表中帶有未來日期的項目。
> 通常由 daily-review hook 自動��發（每 5 個交易日），也可手動執行。

```powershell
# 完整報告
.venv\Scripts\python.exe scripts/thesis_expiry.py

# 靜默模式（供 hook 呼叫）
.venv\Scripts\python.exe scripts/thesis_expiry.py --quiet

# 自訂提醒天數（即將到期 14 天、預覽 60 天）
.venv\Scripts\python.exe scripts/thesis_expiry.py --warn-days 14 --preview-days 60
```

**掃描來源與條件**：

| 來源 | 解析內容 | 收錄條件 |
|------|---------|---------|
| `strategies/thesis_tracking.md` Active 區 | 每個 `### T-NNN` entry 的 `驗證時點` | 所有 Active 狀態的 entry |
| `trades/*.md` 催化劑表 | 表格中 `日期` 欄位 | 僅收錄日期 > 今天的項目（過去事件忽略）|

**提醒分類**：

| 類別 | 條件 | 圖示 |
|------|------|------|
| 已過期未驗 | 驗證時點已過，仍在 Active 區 | 🚨 |
| 即將到期 | 驗證時點在未來 7 天內（可調） | ⏰ |
| 預覽 | 驗證時點在未來 30 天內（可調） | 📅 |

**與 hook 系統的關係**：本腳本是 `.agents/hooks/post-daily-review/thesis-expiry.md` 的執行標的，由 daily-review 步驟 13 自動門控觸發。詳見 `.agents/hooks/README.md`。

---

## 十三、規劃中但尚未實作的量化方法

> 這些方法曾在策略設計中提及，待需求成熟時實作。  
> **與現有工具的差異**：現有工具回答「現在發生什麼」，以下方法回答「未來風險有多大、精確度有多高」。

| 方法 | 用途 | 優先度 | 現有替代 |
|------|------|--------|---------|
| **CVaR**（條件風險值）/ Power Law | 極端下跌的尾端機率。讓停損線設定有統計依據而非拍腦袋 | 🟡 中 | 固定 -10% 停損（粗略）|
| **HMM**（隱馬可夫模型）| 市場狀態偵測（趨勢 / 震盪 / 崩跌），比雷諾數更嚴謹 | 🟠 低 | 雷諾數 Re（已夠用）|

*(註：GARCH 波動率與 GBM 趨勢模型已實作於 `ou_analysis.py` 與 `gbm_analysis.py`)*

---

## 十四、注意事項

1. **SSL 問題**：yfinance 有時因 SSL 失敗，程式碼會自動 fallback 至 curl_cffi 或 TWSE/TPEX 直連 API
2. **ticker 格式**：上市用 `.TW`，上櫃用 `.TWO`，不確定時查 `stocks.csv`
3. **stocks.csv**：存放 `code → ticker` 對應，所有腳本從此讀取，**不硬編碼 ticker**；新增用 `update_stocks.py`
4. **編碼問題**：輸出中文時，若亂碼請加 `sys.stdout.reconfigure(encoding='utf-8')`
