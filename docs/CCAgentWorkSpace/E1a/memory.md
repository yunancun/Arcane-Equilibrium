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
| 2026-04-27 | Live Auth Renew 控制項移至 Governance Hub，打破 locked tab 死鎖 | 主會話直接報告（無單獨 .md） |
| 2026-04-28 | Agent Tracker MVP（AI 团队工作台）— tab-learning.html 加 5 区块 + agent-tracker.js 722 行 | 主會話直接報告（無單獨 .md） |
| 2026-04-29 | Learning tab 区块 E「影子 vs 真仓」误导文案修正 → 「Demo 引擎 vs LiveDemo 引擎成交」 | `.claude_reports/20260429_191942_e1a_gui_shadow_vs_live_text_fix.md` |

## F5 教訓（2026-04-26）

### Multi-session race condition 應對
當主 srv 工作樹（branch e1-f3 / e1-f6 等）頻繁被別 session reset 時，改用 `git worktree add -b <new-branch> ../worktree-<topic> main` 隔離工作流是穩定方案。本任務前 2 次嘗試 srv 工作樹被別人切分支兩次，改用 worktree 後穩定完成 + commit + push。

### LiveDemo 不被當「未配置」處理
per CLAUDE.md memory `feedback_live_no_degradation_by_endpoint`，LiveDemo 是 design intent；只在視覺差異（橙 vs 紫紅），不在後端 guard 擋。phantom-view guard 只擋 `engine_kind != "live" AND endpoint == "unconfigured"` 的雙重失效。

### Mac dev → SSH bridge 強制
Mac 沒裝 fastapi → pytest 必走 `ssh trade-core "python3 -m pytest ..."`。Mac 端只能 `python3 -m ast.parse` syntax check。任何 GUI 後端改動必須 SSH bridge 驗證。

### HTML 1659 行接近上限
tab-live.html 1281 → 1659 行（+378 行）。靜態資源不受 §九 1200 硬上限，但下次再加應拆 JS 成 sibling 檔（`tab-live-handlers.js`）。

### Live Auth 控制項搬移教訓（2026-04-27）

**死鎖模式**：任何「只能在 X 操作，但 X 被鎖定後才需要操作」的設計都是 anti-human。解法永遠是把操作移到「永遠可達」的地方（本例：Governance Hub）。

**兩個 trust-status-bar 的 ID 管理**：同一頁面存在兩個語意相同但位置不同的元素（integrity-fail view + dashboard view），必須用不同 ID 防止 `getElementById` 只取第一個。本例用 `trust-status-bar`（locked view）和 `trust-status-bar-dashboard`（dashboard view）區分，並透過 `_applyToBar(barId, ...)` helper 統一套用邏輯。

**refreshPage() early return 陷阱**：engine 未啟動時 refreshPage() 會 early return，任何放在 early return 後面的 `loadXxx()` 都不會執行。需要「即使 engine 不在線也更新」的 UI 元素，必須在 early return **之前**呼叫其 load function。

**Governance Hub 的 CSS class 借用**：`trust-tier-badge` CSS class 定義在 tab-live.html 的 `<style>` 區塊，tab-governance.html 用 `id="gov-trust-tier-badge"` 的元素借用此 class 會在 include 場景失效。本任務直接在 HTML 元素上用 inline style 複製視覺效果（padding/border-radius/font-size/font-weight），不依賴跨 tab CSS。

## Agent Tracker 教訓（2026-04-28 MVP）

### tab-learning.html 是 inline `<script>`，不走 app-learning.js
`app-learning.js` 屬於 console.html，但 tab-learning.html 自帶完整 inline `<script>` 區塊。新功能直接在 tab-learning.html 內或新建 sibling JS 檔案載入即可，**不要動 app-learning.js**（它服務 console.html 的不同職能）。

### 外部 JS 載入順序陷阱
inline `<script>` 內呼叫外部 JS 定義的 function 必先確保 `<script src="...">` 在 inline `<script>` 之前。本任務首版 `startAgentTracker()` boot 寫在外部 script 之上，會直接 `typeof === 'function'` 失敗。修正：把 boot 移到外部 src 之後的另一個 inline `<script>` 區塊。

### iframe 內 setInterval 必須監聽 visibilitychange + pagehide
console.html 的 tab 是 iframe；user 切換 tab 時 iframe 不卸載只 hide，setInterval 仍燒。本任務在 `agent-tracker.js` 接 `pagehide` + `visibilitychange` 雙事件，hidden 時 clearInterval、visible 回來再 startAgentTracker()。注意要用 `Object.keys(_AGENT_TIMERS)` 一次清光所有 timer slot，不要漏。

### 視覺強隔離 = 多通道冗餘
Executor shadow vs live 隔離靠 3 通道：(1) 卡片底色 gradient (2) 頂部 banner 文案 + emoji (3) 數字單位語意（「模擬成單」vs「真實成單 · 真實 PnL」）。任一通道 user 沒看到都還剩 2 個冗餘提示。`unknown` 狀態額外加紅警語「狀態未確認，已暫停接單」確保永遠不留灰色，符合 plan「永遠不留灰色」。

### 三態文案核心：失敗訊息要明說「Agent 還活著」
普通 user 看到 GUI 紅字失敗會以為交易系統掛了去亂按。本任務 error 文案：「连不上引擎 — 不代表 Agent 出问题，是仪表板自己迷路了，30 秒后再试」— 把責任歸給仪表板自己，避免 panic。三個狀態的中文必對齊 plan T5 規範：⏳/💤/⚠️ 三 emoji 各對應載入/空/失敗。

### 後端契約兼容防禦寫法
endpoint 回傳格式現實中經常多套 envelope（`{data: {...}}` 或直接 `{...}`）。本檔對 6 個 endpoint 都做 `d.data || d` fallback + 多 field 名 fallback（`shadow_count || count || n`）。後端契約即使後續微調或不同 layer 包裝，前端不爆。

### 後端結構化 error envelope vs 422
GUI `ocApi` 對 non-200 顯通用 toast，page-load 流程讀不到 markers swap views。改回 HTTP 200 + `{error: "live_slot_not_configured", actual_engine_kind, actual_endpoint, ...}` envelope 讓前端能結構化 short-circuit。**規律**：當需要前端依 error type 做 view-swap 而非單純 toast 時，用 200 envelope 而非 4xx HTTPException。

## Agent Tracker Round 2 教訓（2026-04-28 retro fix）

### Round 1 fallback chain 是 contract drift 隱身披風
Round 1 對所有 endpoint 寫 `data.x || data.y || data.z` fallback chain（sticker：`shadow_count || count || n`、`spent_usd || total_cost_usd || cap_usd`）。表面友好「容錯」、實際是把後端 schema 不一致 silent 吞掉 → operator 永遠看不到「後端真的回了什麼/該回什麼」。E2 retro 抓出：fallback 一個都沒對上真 schema，5 個 block 全部資料 silent empty。**規律**：endpoint 第一版可加 1 層 envelope fallback (`data.x || .x`)，但 field-level fallback chain 是 anti-pattern — 直接信 schema，找不到就 fail-loud 顯空態 + 寫 console.warn，逼 operator/E2 在 round 1 抓 contract drift。

### Round 2 contract change 用獨立 endpoint，不擴 legacy schema
原本想法：在 `/strategist/history` 加 `?outcome=reject` query 服務 Block F；後端不接受 silent ignore。E1-A round 2 給的方案 = 新開 `/api/v1/agents/recent_rejects` + `/api/v1/agents/shadow_vs_live_summary` 兩個 GUI-purpose-built endpoint，schema 跟 GUI 用法 1:1 對齊（`{rows:[{ts, symbol, reason, risk_level}]}` / `{demo, live_demo, diff}`）。**規律**：當 GUI 要 cross-table 聚合 + 後端既有 endpoint 用法不對齊時，後端為 GUI 開新 endpoint 比 GUI 自己 query-string-hack 既有 endpoint 乾淨；schema 只服務一個用途 → 不會有第二個 caller pull schema drift。

### `oc-chip-live` 在 common.js 已存在但顏色不對 — page-scoped specificity override 比改 common.js 安全
Common.js 默認 `oc-chip-live` 紫（LiveDemo flavor），Agent 工作台需要紅色「真錢」緊迫感。直接改 common.js 會牽動所有用紫色的 LiveDemo banner（tab-live.html 等）。Page-scoped 用 `.oc-chip.oc-chip-live` 雙 class selector specificity (1,0,0) 覆蓋 common.js `.oc-chip-live` (0,1,0) → 只 tab-learning 變紅，其他頁面不動。**規律**：CSS class collision 時，page-local specificity boost 比改 global 安全；但要在 comment 裡標清楚為什麼要 override（避免下次 maintainer 把 page-local rule 移走）。

### Stale-bail 比 AbortController 更普適（共享 ocApi 不接受 signal 場景）
M-2 finding：fast 連點 / refresh 重疊發 race 寫舊 response 進 DOM。AbortController 需要 fetch 接 signal，但這專案的 `ocApi` 是固定簽名不接 signal。改用 module-level `_pollSeq[key]++` ID + .then 開頭比對：每次 loader 進入 ++myseq，await 後 `if (mySeq !== _pollSeq[key]) return;` bail render。零侵入 + 不依賴 ocApi 改動 + 符合 Anthropic「最小變更」原則。

### 後端字段 null/undefined 必 fail-loud
`shadow_mode` 是這專案最危險的字段（決定真錢與否）。Round 1 寫 `shadow_mode === false` 判 isLive 看似嚴格，但 `agent.shadow_mode === undefined` 時 isLive 變 false → silent 顯「影子模式」橘 banner，掩蓋 contract drift。Round 2 改三分支：`=== false → live (red breathing)` / `=== true → shadow (blue)` / `null/undefined/non-bool → state=unknown + 紅色「後端未回報 shadow_mode 字段」warning`。**規律**：危險決策字段必三分支 — 真 / 假 / 不知道；不知道一律走最保守警示路徑（不能默認任何一邊）。

### L-3 contract test fixture 用純瀏覽器可跑的 mock-fetch
專案無前端測試框架 (vitest/jest/jsdom)；E2 round 2 retro 容許「跳 L-3 但留 TODO」。我選最低線交付：`tests/static/test_agent_tracker_contract.html` 純 mock window.fetch + 手寫 record/assertContains，瀏覽器打開即跑、無依賴。比 0 fixture 強，比 jest 弱；TODO 註明未來若上 jest/vitest 應升級。

## Shadow-vs-Live 文案误导修正教训（2026-04-29）

### Endpoint URL ≠ semantic accuracy
`/api/v1/agents/shadow_vs_live_summary` URL 用「shadow」「live」字眼，但后端 SQL 实际抓 `engine_mode IN ('demo','live','live_demo')` — 两边都是真实 fills，差别只在 risk_config TOML 引擎。Round 2 endpoint 命名时若选 `engine_mode_fills_summary` 就不会有此误导；但既然已上 endpoint 不可改 URL，**前端必须靠文案 + docstring + HTML 注释三层冗余把语义说清楚**，不依赖 URL/字段名 self-documenting。**规律**：endpoint URL 用了易误导的 metaphor（shadow/live/dark/light）时，GUI 文案必加 explicit 解释「这里说的 X 是 Y 概念，不是 Z 概念」，否则下次 maintainer / operator 又会被字面意思误导。

### 不动 endpoint URL 也能彻底修文案
Task 边界明确「不动 endpoint URL，等 E1 backend alias 解耦」。前端文案修正零依赖后端，这是好的解耦设计 — GUI 文案治理可独立 ship，不被 backend 部署排程卡。本次修改：(a) HTML 区块标题 (b) HTML 注释扩展（解释 engine_mode 概念）(c) JS docstring 重写 (d) Demo column 4 处文案 (e) LiveDemo column 5 处文案 (f) 中央 diff 2 处文案 — 全部静态字符串字面值替换，无控制流变更，retro break risk 极低。**规律**：当后端 endpoint URL 误导但已 ship，前端文案修正可作为「先治标」短期手段，让 user 立即免误导；后端 alias 是「再治本」的中期工程。

### ExecutorAgent shadow ≠ engine_mode shadow
Block E 卡和 Roster A 卡两个「shadow」概念完全不同：(1) Roster A 的 ExecutorAgent `_shadow_mode=True` — Python 进程内决策只 log 不发 SubmitOrder IPC 到 Rust（设计避免 Path A/B 双发倉位冲突，executor_agent.py:382）。(2) Block E 的「shadow」其实是 demo engine_mode 标签，跟 Python ExecutorAgent 完全无关。误用同一个词「shadow」是 round 1 命名失败遗留 — Round 2 修正只能从 Block E 这边拆分（Roster A 仍叫 shadow_mode 因为代码字段就叫这个）。**规律**：同一 GUI 页面同时显示两个不同概念但都用「shadow」时，必须至少一边换名字消除冲突（本次：Block E 「shadow」→「Demo 引擎」） + 在两边的注释/tooltip 显式说明「这里的 shadow 不是另一个 shadow」。

### Tip / Tooltip 跨区块作用域要 grep 验证
Task brief 提到 line 259-260 的 explain-agent-tracker tip 描述「5 位 AI 员工... 谁还在影子模式」— 看起来像描述 Block E 的 shadow，实际通过 grep `$('explain-agent-tracker')` 的元素位置验证：tip 挂在 `<section id="agent-tracker">` 顶部「AI 团队工作台」标题下方，作用域是整个 section（覆盖 Roster A + 4 个其他卡），主要描述 Roster A 的 ExecutorAgent shadow 概念（「谁还在影子模式（只观察）、谁开始动真钱」对应 Roster 卡的 isExecutor isLive 分支）。**规律**：改文案前必须 `grep '$(\'explain-X\')'` 找到该 explainer 的渲染位置 + 上下文卡片，确认作用域；不能光看 tip 内容字面就断定它服务哪个卡。本次按 task brief 不改 line 259-260 是正确决策。
