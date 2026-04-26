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
| 2026-04-26 | F5 GUI Live tab anti-human-design 修復（5 findings + 11 pytest） | `workspace/reports/2026-04-26--f5_gui_live_anti_human_design.md` |

## F5 教訓（2026-04-26）

### Multi-session race condition 應對
當主 srv 工作樹（branch e1-f3 / e1-f6 等）頻繁被別 session reset 時，改用 `git worktree add -b <new-branch> ../worktree-<topic> main` 隔離工作流是穩定方案。本任務前 2 次嘗試 srv 工作樹被別人切分支兩次，改用 worktree 後穩定完成 + commit + push。

### LiveDemo 不被當「未配置」處理
per CLAUDE.md memory `feedback_live_no_degradation_by_endpoint`，LiveDemo 是 design intent；只在視覺差異（橙 vs 紫紅），不在後端 guard 擋。phantom-view guard 只擋 `engine_kind != "live" AND endpoint == "unconfigured"` 的雙重失效。

### Mac dev → SSH bridge 強制
Mac 沒裝 fastapi → pytest 必走 `ssh trade-core "python3 -m pytest ..."`。Mac 端只能 `python3 -m ast.parse` syntax check。任何 GUI 後端改動必須 SSH bridge 驗證。

### HTML 1659 行接近上限
tab-live.html 1281 → 1659 行（+378 行）。靜態資源不受 §九 1200 硬上限，但下次再加應拆 JS 成 sibling 檔（`tab-live-handlers.js`）。

### 後端結構化 error envelope vs 422
GUI `ocApi` 對 non-200 顯通用 toast，page-load 流程讀不到 markers swap views。改回 HTTP 200 + `{error: "live_slot_not_configured", actual_engine_kind, actual_endpoint, ...}` envelope 讓前端能結構化 short-circuit。**規律**：當需要前端依 error type 做 view-swap 而非單純 toast 時，用 200 envelope 而非 4xx HTTPException。
