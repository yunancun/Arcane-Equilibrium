# E1a Memory — 工作記憶

## 項目上下文（2026-03-31）

- 當前 Wave：Wave 4 完成，Wave 5 規劃中
- 測試基準：2555 passed
- 系統模式：demo_only

## 強制編碼規範（每次寫/改前端代碼必須遵守）

### 雙語注釋（最高優先，不可省略）
每個新建或修改的 JS 函數、HTML 組件區塊、CSS 模塊，必須包含中英對照注釋：

```javascript
/**
 * Update the AI budget display after each API call.
 * 每次 AI API 調用後更新預算顯示，反映當日剩餘額度。
 *
 * @param {number} remaining - Remaining daily budget in USD / 當日剩餘預算（美元）
 */
function updateBudgetDisplay(remaining) { ... }
```

```html
<!-- AI Budget Control Section / AI 預算控制區塊 -->
<!-- Shows real-time daily cap and current spend / 顯示每日硬上限與當前花費 -->
<div id="ai-budget-panel">
```

規則：
- **JS 函數**：JSDoc 格式，含中英兩段說明 + 參數/返回值雙語
- **HTML 區塊**：每個功能區塊前加中英說明注釋
- **複雜 CSS**：選擇器旁加中文說明用途（英文 class 名不夠直觀時）
- **安全相關**（XSS 防護、ocEsc）：必須注釋說明為什麼在這裡加，而非只是加了

### GUI 規範
- 面向 Operator 的文字一律中文
- 工程術語（SM-01、Decision Lease 等）需配括號中文解釋
- 確認彈窗不可省略（破壞性操作）

### 其他強制規則
- E2+E4 通過前不算完成
- innerHTML 賦值必須用 ocEsc() 包裝（防 XSS）

## 報告索引

| 日期 | 任務 | 文件位置 |
|------|------|---------|
| — | — | — |
