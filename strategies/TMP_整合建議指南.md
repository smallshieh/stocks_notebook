# Tradememory Protocol (TMP) v0.3.0 整合建議指南

> **目標**：借鑒 TMP v0.3.0 的結構化優化框架，強化 Antigravity 系統從「質化心得」到「量化決策」的轉化能力。
> **參考文檔**：[mnemox-ai/tradememory-protocol v0.3.0](https://github.com/mnemox-ai/tradememory-protocol)

---

## 1. 核心概念對比 (Antigravity vs. TMP)

| 維度 | Antigravity (現況) | TMP v0.3.0 (建議方向) |
| :--- | :--- | :--- |
| **數據層次** | 交易日誌 + 四階段審計 | L1 (Entry/Exit) -> L2 (Patterns) -> L3 (Adjustments) |
| **優化邏輯** | AI 覆盤 + 感性心得 (10日戰術) | 置信度門檻 (>0.7) + 樣本數 (>10/50) |
| **觸發機制** | 時間週期 (定時更新) | 數據觸發 (Data-Driven Trigger) |
| **決策方式** | 專家直覺 (由你判斷) | 確定性規則 (Deterministic Rules) |

---

## 2. TMP v0.3.0 關鍵機制摘要

### L1: 原始紀錄層 (Immutable Record)
*   記錄每一筆交易的進場、出場、預期 R/R。
*   *Antigravity 對應：`trades/*.md` 的審計 ① ② ③。*

### L2: 模式識別層 (Pattern Identification)
*   **關鍵概念**：標記該交易屬於哪種「模式」(如：Fomo, Breakout, Mean Reversion)。
*   **置信度計算**：統計該模式在特定樣本數下的表現。

### L3: 策略調整層 (Strategy Adjustments) - **v0.3.0 重點**
*   **不輕易修改策略**：只有當 L2 模式顯示某種參數（如停損距離、持有時間）有明顯優化空間時，才提出 `Adjustment`。
*   **調整生命週期**：`Proposed` (提議) -> `Approved` (驗證) -> `Applied` (正式實施)。

---

## 3. 建議優化方向 (分階段實施)

為了不破壞目前的專案運行，建議依序執行：

### 第一階段：標籤標準化 (不改程式，只改習慣)
*   在 `trades/template.md` 增加 **「模式標籤 (L2 Tag)」**。
*   常見標籤建議：`#Strategy-Sync` (符合規則), `#Market-Noise` (大盤干擾), `#Emotional-Exit` (情緒出場)。
*   **目的**：為未來的量化統計累積結構化數據。

### 第二階段：策略進化表 (修改策略模板)
*   在 `strategies/template.md` 加入 **L3 策略調整表**。
*   當你在「10日戰術指南」想改參數時，先寫入此表並標註為 `Proposed`。
*   **目的**：強迫自己追蹤「修改策略」的效果，避免隨機改動。

### 第三階段：量化審計腳本 (新增獨立腳本)
*   開發 `scripts/strategy_audit.py`。
*   讀取所有 `trades/*.md`，統計：
    *   各策略的真實期望值。
    *   「紀律分」與「獲利」的相關性。
*   **目的**：提供客觀數據，告訴你「目前的戰術是否真的失效」。

---

## 4. 未來實施紅線 (Red Lines)

1.  **樣本不足不調整**：單一策略樣本數未達 10 筆前，不將 `Proposed` 轉為 `Applied`。
2.  **紀律分優先**：如果紀律分（Audit ①）持續低於「嚴守」，則應處理「心態問題」而非「策略調整」。
3.  **AI 的角色**：AI 應用於「質化原因分析」，而「參數調整」應優先參考量化統計數據。

---
*編製日期：2026-03-01*
*版本：v1.0 (Draft)*
