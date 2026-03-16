---
description: 新標的進場前分析（查現價月線 → 資金桶容量確認 → 風險計算 → 建檔）
---

## 使用方式
呼叫時請提供：`/new-position {股票代號}`

## 步驟

1. 讀取 `capital/capital_config.md` 第 0 節，確認目前 Tactical_Bucket 使用量。
   - 若 Tactical 已達 35% 上限，輸出警告並**暫停流程**，提示用戶先出清現有 Tactical 部位。

2. 執行：`python scripts/stock_analyzer.py --ticker {代號}`
   取得現價、20MA、殖利率。

3. 搜尋該標的近期資訊：法人評等、外資買賣超、近期重大公告。

4. 依 `capital_config.md` 第 2 節計算建議買入股數：
   ```
   應買入股數 = (投資組合總資產 × 風險率 1%) / (買入價 - 停損價)
   ```
   停損價預設為買入價 × 0.9（-10% 首波停損）。

5. 輸出分析摘要：
   - 現價 / 月線 / 殖利率
   - 法人目標價 / 本益比概況
   - 建議買入股數與最大風險金額
   - 歸屬桶別建議（Core or Tactical）

6. 若用戶確認進場，依 `trades/template.md` 建立新持倉筆記至 `trades/{代號}_{名稱}.md`，填入：
   - 買進價格、停損線、目標價
   - 桶別標籤（Source: Core / Tactical）
