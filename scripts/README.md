# 股票筆記本｜Scripts 工具手冊

> 適用：任何 AI Agent 或操作者，快速掌握本系統所有分析工具的用途與指令  
> Python 環境：**永遠使用 `.venv`** → `S:\股票筆記\.venv\Scripts\python.exe`  
> 工作目錄：`S:\股票筆記\`（所有指令請在此處執行）

---

## 工具總覽

| 腳本 | 類型 | 功能摘要 |
|------|------|---------|
| `stock_analyzer.py` | 資料查詢 | 即時股價、月線、停損預警 |
| `physics_engine.py` | 物理模型 | 動量、動能、雷諾數診斷（模組）|
| `quantile_engine.py` | 統計模型 | 回檔分位數決策（賣出/買回/暫停區）|
| `ou_analysis_6488.py` | 機率模型 | OU 均值回歸 + 蒙地卡羅機率預測 |
| `recalc_rolling_ranges.py` | 策略工具 | 批次重算零股滾動法價格區間 |
| `portfolio_report.py` | 報告工具 | 持倉健診報告（盤後全倉掃描）|
| `portfolio_log.py` | 紀錄工具 | 資金 / 持倉快照存檔 |
| `performance_report.py` | 報告工具 | 績效報告（含計算資金輪轉效益）|
| `sync_to_notion.py` | 同步工具 | 將 MD 檔同步至 Notion |
| `watchlist_scan.py` | 監控工具 | 觀察清單標的掃描與警示 |
| `update_stocks.py` | 資料維護 | 新增 / 查詢 stocks.csv 標的清單 |
| `vol_check.py` | 工具 | 個股波動率快速查詢 |
| `daily_scan.bat` | 排程 | 每日自動執行盤後掃描 |

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

## 十、規劃中但尚未實作的量化方法

> 這些方法曾在策略設計中提及，待需求成熟時實作。  
> **與現有工具的差異**：現有工具回答「現在發生什麼」，以下方法回答「未來風險有多大、精確度有多高」。

| 方法 | 用途 | 優先度 | 現有替代 |
|------|------|--------|---------|
| **CVaR**（條件風險值）/ Power Law | 極端下跌的尾端機率。讓停損線設定有統計依據而非拍腦袋 | 🟡 中 | 固定 -10% 停損（粗略）|
| **HMM**（隱馬可夫模型）| 市場狀態偵測（趨勢 / 震盪 / 崩跌），比雷諾數更嚴謹 | 🟠 低 | 雷諾數 Re（已夠用）|

*(註：GARCH 波動率與 GBM 趨勢模型已實作於 `ou_analysis.py` 與 `gbm_analysis.py`)*venv\Scripts\python.exe scripts/performance_report.py
```

---

## 七、Notion 同步

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

## 八、stocks.csv 維護

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

## 九、規劃中但尚未實作的量化方法

> 這些方法曾在策略設計中提及，待需求成熟時實作。  
> **與現有工具的差異**：現有工具回答「現在發生什麼」，以下方法回答「未來風險有多大、精確度有多高」。

| 方法 | 用途 | 優先度 | 現有替代 |
|------|------|--------|---------|
| **GARCH**（廣義自迴歸條件異方差）| 動態波動率估算。OU 模型的 σ 目前假設固定，GARCH 讓 σ 隨時間變動，黑天鵝環境下更準確 | ⭐ 高 | rolling std（不夠準）|
| **CVaR**（條件風險值）/ Power Law | 極端下跌的尾端機率。讓停損線設定有統計依據而非拍腦袋 | 🟡 中 | 固定 -10% 停損（粗略）|
| **GBM + drift**（幾何布朗運動）| 趨勢型股票的走勢機率模擬（非均值回歸型）| 🟠 低 | — |
| **HMM**（隱馬可夫模型）| 市場狀態偵測（趨勢 / 震盪 / 崩跌），比雷諾數更嚴謹 | 🟠 低 | 雷諾數 Re（已夠用）|

### 建議優先實作：GARCH 波動率修正

**問題**：`ou_analysis.py` 目前的 σ 由 OLS 殘差估算，假設波動率固定。  
**現象**：黑天鵝期間 σ 會突然放大，導致機率預測偏保守（低估下跌速度）。  
**解法**：在 `estimate_ou_params()` 中加入 `arch` 套件的 GARCH(1,1) 修正：

```python
# 需先安裝：pip install arch
from arch import arch_model
garch = arch_model(returns * 100, vol='Garch', p=1, q=1)
res = garch.fit(disp='off')
sigma_garch = res.conditional_volatility[-1] / 100 * np.sqrt(252)
```

---

## 十、注意事項

1. **SSL 問題**：yfinance 有時因 SSL 失敗，程式碼會自動 fallback 至 curl_cffi 或 TWSE/TPEX 直連 API
2. **ticker 格式**：上市用 `.TW`，上櫃用 `.TWO`，不確定時查 `stocks.csv`
3. **stocks.csv**：存放 `code → ticker` 對應，所有腳本從此讀取，**不硬編碼 ticker**；新增用 `update_stocks.py`
4. **編碼問題**：輸出中文時，若亂碼請加 `sys.stdout.reconfigure(encoding='utf-8')`
