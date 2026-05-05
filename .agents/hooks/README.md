# Post-Daily-Review Hook 系統

> 適用：任何 AI Agent 執行 `/daily-review` 時，步驟 7.5 用 `hook_runner.py` 執行 hook，步驟 13 讀取結構化 JSON 結果並落地到日誌與戰術指南。

---

## v2 運作原理

Hook v2 不再掃描 `.md` frontmatter，也不再用 `_state.json.last_output` 或 stdout `⚠️` 判斷結果。

```
步驟 7.5
  ├── 讀取 .agents/hooks/post-daily-review/hooks.yaml
  ├── 讀取 .agents/hooks/post-daily-review/hooks_state.json
  ├── 判斷到期 hook 或需 auto-reenable 檢查的 disabled hook
  ├── 執行 hook script --json
  ├── 解析 JSON stdout
  ├── 更新 hooks_state.json
  └── 寫入 journals/logs/{REVIEW_DATE}_hooks.json

步驟 13
  ├── 讀取 journals/logs/{REVIEW_DATE}_hooks.json
  ├── 將 summary_md 寫入盤後日誌 ## Hooks
  ├── 依 severity high -> medium -> low 檢查 targets
  └── 依 action 更新戰術指南 P1/P2 或待辦事項
```

同日重跑 `/daily-review` 時，`hook_runner.py` 會保留同一個 `{REVIEW_DATE}_hooks.json` 中較早已觸發的結果，避免第二次全數 skipped 時覆蓋掉第一次的有效訊號。

---

## 目錄結構

```
.agents/hooks/post-daily-review/
├── hooks.yaml          # 中央註冊表：hook 名稱、script、targets、trigger、lifecycle、retry
├── hooks_state.json    # 統一狀態：last_run、run_count、failures、last_result、stocks 診斷
├── *.md                # 人類可讀背景與 Agent 落地指引
└── _state.json         # 舊制備份/遷移來源，不再作為執行依據
```

詳細 schema 見 `.claude/docs/hook-v2-guide.md`。

---

## 常用指令

```powershell
# 正常執行，使用今天或 REVIEW_DATE
.\.venv\Scripts\python.exe scripts\hook_runner.py

# 指定盤後歸屬日期
.\.venv\Scripts\python.exe scripts\hook_runner.py --date 2026-05-04

# 預覽哪些 hook 會執行，不執行腳本、不寫 state、不寫 hooks.json
.\.venv\Scripts\python.exe scripts\hook_runner.py --dry-run

# 測試單一 hook 的 JSON 輸出
.\.venv\Scripts\python.exe scripts\ma_breach_counter.py --code 1210 --ma 20 --alert-days 3 --name 大成 --json
```

`hook_runner.py --date` 會把同一日期寫入子程序的 `REVIEW_DATE` 環境變數，避免補執行時 state/log 與腳本內部日期不一致。

---

## 新增 Hook

1. 確認腳本支援 `--json`，輸出 `HookResult`：
   ```json
   {
     "hook": "my-hook",
     "timestamp": "2026-05-05",
     "status": "alert",
     "severity": "high",
     "targets": [
       {
         "code": "1210",
         "name": "大成",
         "action": "p1_observe",
         "summary": "月線下方連續第 9 日",
         "detail": {}
       }
     ],
     "lifecycle_event": null,
     "error_message": null
   }
   ```
2. 在 `.agents/hooks/post-daily-review/hooks.yaml` 新增 hook 定義。
3. 新增或更新同名 `.md` 文件，說明背景與 action 落地方式。
4. 用 `hook_runner.py --dry-run` 與單一腳本 `--json` 驗證。

---

## 暫停、恢復、強制重跑

- 暫停：將 `hooks_state.json.hooks.{hook}.status` 改為 `disabled`，並填 `disabled_reason`。
- 恢復：將 `status` 改回 `active`，移除 `disabled_reason`。
- 強制下次重跑：將該 hook 的 `last_run` 設為 `null`。
- MA20 類 hook 若因月線收復自動 disabled，runner 仍會做 re-enable 檢查；再次跌破時會自動轉回 active。

不要再用「檔名前加底線」作為 v2 暫停方式；那只適用舊制 md 掃描。

---

## 錯誤處理

- script exit code 非 0 或 JSON 無法解析：`consecutive_failures += 1`，不更新 `last_run`，下次仍會重試。
- 達 `retry.max_consecutive_failures` 後，runner 使用 `fallback_frequency_days` 作為重試頻率。
- 失敗項目會寫入 `journals/logs/{REVIEW_DATE}_hooks.json.failed`，步驟 13 應在日誌 `## Hooks` 和 `## 待辦事項` 記錄人工檢查。
