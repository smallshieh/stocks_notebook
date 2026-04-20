---
description: 將 MD 檔同步到 Notion（支援單檔、多檔、自動偵測近期修改）
---

## 使用方式

```
/sync-notion                    # 自動偵測 git 修改過的 MD 檔，逐一確認後同步
/sync-notion journals/戰術指南.md          # 同步指定檔案
/sync-notion trades/6488_環球晶.md trades/8069_元太.md   # 同步多檔
/sync-notion --all              # 同步所有支援類型的重要 MD 檔
```

---

## 步驟

### Step 1｜確認執行環境

執行以下指令，確認 .venv 可用且 notion-client 已安裝：

```bash
.venv/Scripts/python.exe -c "import notion_client; print('OK')"
```

- 若輸出 `OK`：繼續
- 若失敗：輸出 `❌ notion-client 未安裝，請執行：.venv/Scripts/pip install notion-client`，**中止流程**

---

### Step 2｜決定同步清單

依使用方式不同，建立「待同步清單」：

**情況 A：有指定檔案（命令列參數）**
- 直接使用指定的檔案路徑作為待同步清單
- 確認每個路徑存在，若不存在輸出 `❌ 找不到：{路徑}` 並跳過

**情況 B：無參數（自動偵測）**

執行以下指令取得近期修改的 MD 檔：

```bash
git -C "S:/股票筆記" status --short
```

- 篩選條件：`.md` 副檔名、狀態為 `M`（已修改）或 `??`（未追蹤）
- 排除路徑：`.agents/`、`memory/`、`CLAUDE.md`
- 若無符合檔案：輸出 `✅ 無需同步的修改檔案` 並中止

列出偵測結果，逐一詢問用戶：
```
偵測到以下修改的 MD 檔，請確認要同步的項目：
[1] journals/戰術指南.md
[2] trades/6488_環球晶.md
[3] trades/8069_元太.md
輸入編號（逗號分隔，例：1,3）或 all / skip：
```

**情況 C：`--all`**

固定同步清單（依優先序）：
1. `journals/戰術指南.md`（若存在）
2. 今日或最近一份 `持倉健診_{YYYY-MM-DD}.md`
3. 今日或最近一份 `journals/{YYYY-MM-DD}_盤後日誌.md`
4. `trades/` 目錄下所有 `.md`

---

### Step 3｜執行同步

對清單中每個檔案，執行：

```bash
.venv/Scripts/python.exe scripts/sync_to_notion.py "{檔案路徑}"
```

輸出格式：
```
同步中 [1/3]：journals/戰術指南.md
  → 目標頁面：「戰術指南」
  → ✅ 完成（61 blocks）

同步中 [2/3]：trades/6488_環球晶.md
  → 目標頁面：「6488 環球晶」
  → ✅ 完成（70 blocks）

同步中 [3/3]：trades/8069_元太.md
  → 目標頁面：「8069 元太」
  → ✅ 完成（78 blocks）
```

**錯誤處理：**
- 單檔失敗（憑證錯誤、網路逾時等）→ 輸出 `❌ 失敗：{錯誤訊息}`，繼續下一檔，**不中止整體流程**
- 全部失敗 → 最後輸出 `❌ 所有檔案同步失敗，請確認 NOTION_TOKEN 設定是否正確（scripts/notion_creds.py）`

---

### Step 4｜輸出摘要

```
=== /sync-notion 完成 ===
同步結果：✅ {n} 成功 / ❌ {n} 失敗
成功：
  - journals/戰術指南.md → 「戰術指南」（61 blocks）
  - trades/6488_環球晶.md → 「6488 環球晶」（70 blocks）
失敗（若有）：
  - trades/XXX.md → {錯誤原因}
```

---

## 注意事項

- 同步為**單向覆寫**：Notion 端舊內容會被清除，以 MD 檔為準
- Notion 同步內容必須使用完整 MD；不要用 `md_section.py` 或局部 section 內容作為同步 payload
- `md_outline.py` 僅可用於同步前檢查檔案結構或除錯，不可取代完整檔案同步
- 同步指令固定使用 `.venv/Scripts/python.exe`，不使用系統 python
- Notion 頁面標題由 MD 檔名推斷（第一個底線替換為空格）：
  - `戰術指南.md` → 「戰術指南」
  - `2026-03-10_盤後日誌.md` → 「2026-03-10 盤後日誌」
  - `持倉健診_2026-03-10.md` → 「持倉健診 2026-03-10」
  - `6488_環球晶.md` → 「6488 環球晶」
