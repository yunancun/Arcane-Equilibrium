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
| 2026-05-09 | W-AUDIT-7c GUI 三項修復（typed-confirm modal + Settings sub-tab + 2 governance confirm replace） | `workspace/reports/2026-05-09--w_audit_7c_gui_three_fix.md` · commit 9e265ba9 |
| 2026-05-09 | W-AUDIT-7c **Round 2** fix（A3 verdict FALSE_CLOSED 後 9 項缺陷修補）— SyntaxError 整檔 parse fail / fixture garbage / button race / cancel toast / pending list 細節展示 | `workspace/reports/2026-05-09--w_audit_7c_round2_fix.md` · commit `0fbed710` |
| 2026-05-09 | W-AUDIT-7c **Round 3** fix（E2 RETURN HIGH-1 silent unhandled rejection + 2 cosmetic）— 3 處 await openTypedConfirmModal 包 try/catch + ok→proceed rename + 英文 case-sensitive 注釋刪 + Case 7 singleton race fixture | `workspace/reports/2026-05-09--w_audit_7c_round3_fix.md` |

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

## REF-20 Wave 2 Batch 1 MED-5 retrofit — mode badge i18n hook 实装 (2026-05-03)

### Task：把 stale `// REF-20 R20-P1-U9 i18n hook` comment 实装为真 t_zh() lookup
E2 review (`docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-03--ref20_wave2_batch1_design_impl_review.md`) MED-5：U9 (commit 9879eeb) 已 land `i18n_zh.js` + `window.t_zh()` helper，但 `common.js:1184-1189` 的 mode badge factory 仍直接用 `meta.dim_label_en` / `meta.label_en` 显 EN-only label，与 operator 中文 dominant 偏好冲突。E2 二选一：(A) 实装 i18n lookup / (B) 移 comment + 改 commit message。PM 选 (A)。

### 修改实做 — 加一个 helper `_ocLookupModeBadgeStateLabel(meta)`
为啥不 inline `window.t_zh(...)` 调用：(1) 4 维要重复同样的 fallback chain 逻辑 (2) miss/缺载入两种 fail mode 都要 defensive 处理 (3) helper 有清楚的 SAFETY 注释更好维护。Helper 内三层 fallback：`t_zh(mode_badge.<dim>.<state>)` (miss != raw key signal) → `meta.label_zh` → `meta.label_en`。**规律**：当一个 cross-cutting concern (i18n lookup / safety check) 要在 N 个调用点重复时，抽 helper 比 inline 干净 — 尤其当 fallback chain 多层时。

### t_zh miss 用 strict !== 比 raw key 判定真 hit
i18n_zh.js 的 t_zh() docstring 明示「缺鍵時返回 raw key path（fail-loud，方便 dev 抓 typo）」。Helper 写 `if (looked === keyPath) return fallback`：用 strict !== 比对原 key path 字符串、再加 length > 0 双保险。**规律**：consumer 端用 i18n helper 时必读 helper 的 miss 行为契约 — 有的 lib miss 返 null/empty/undef/raw-key，处理方式完全不同。

### dim label 不走 t_zh — i18n_zh schema 没 dim 级条目
i18n_zh.js 的 `mode_badge` table schema 是 `mode_badge.<dim>.<state>` 二级，只有 state 文案；`dim` 级 label「资料层级 / 输出策略 / 校准新鲜度 / 执行可信度」是直接挂在 common.js `_OC_MODE_BADGE_DEFS` 的 def.label_zh。所以 dim label 直接用 `meta.dim_label_zh` 不需 lookup。这避免重复 sync schema（i18n_zh 加一个 dim_labels 表 = 2 处 source of truth = 漂移风险）。**规律**：跨 module schema 要 stay 单一 SoT — 哪边已经有合适字段直接复用，不要「为了走 i18n 流程」强行加层。

### bilingual aria-label 保 EN-only screen reader 友好
之前 aria-label 是「Exec Confidence: None (warning, not actionable)」纯 EN，screen reader 读出来是英文。retrofit 后改并列「Exec Confidence: None / 执行可信度: 无 (warning, not actionable / 警告，不可作为实盘依据)」中英都念得到。EN baseline 不破，中文 operator + 中文屏幕阅读器双友好。**规律**：a11y label 改文案时不能 silent 替换 EN→zh — screen reader 用户的语言设置可能是 EN，drop EN baseline 等于 break a11y baseline；改成中英并列才安全。

### tooltip 反过来 zh-dom + EN fallback (operator 中文偏好)
之前 title 是「EN / zh」(EN 在前)，retrofit 改「zh / EN」(zh 在前)。鼠标 hover 弹的 tooltip 是 operator 直接看的，operator 中文偏好下 zh 应该在前。aria-label 走 a11y 路径保 EN 在前，tooltip 走 hover 路径改 zh 在前 — 同一组数据两条 channel 用不同优先序。**规律**：i18n 顺序不只看「哪个语言重要」，要看「这条 string 哪个 channel 用、谁是真消费者」。

### File size cap 1500 行管理 — 1413 → 1466（+53 行）
现在 1466，距 cap 1500 还 34 行 buffer。新加 helper 27 行 + 改 docstring 24 行 + bilingual aria-label 6 行 = 53 行新增。**规律**：1500 行 cap 是硬上限，每次 retrofit 必算预算；这次 53 / 87 buffer = 61% 占用率，下次 Wave 2 closure 同档加新功能要先看还有多少空间，不够要 (a) split 文件 (b) push back 到 PM。

### Defensive `typeof window.t_zh === 'function'` 检查必加
理论上 console.html / tab-paper.html 的 script load order 已确保 i18n_zh.js 在 common.js 之后载入，DOMContentLoaded 触发时 t_zh 必已定义。但实战中 (a) 未来其他 tab 可能 reuse mode badge factory 但不载 i18n_zh.js (b) script 加载失败 / network error (c) 测试 stub 替换 — 任一情况 t_zh undefined 时 helper 必须 fallback 不 throw。**规律**：consumer 端用第三方 module export 时必加 typeof check + fallback，永不假定 module 一定 loaded — 这是 vanilla JS 项目（无 import resolver / no module bundler）的硬要求。

### 验证手段：node 不可用时用 python 静态结构 + i18n schema 模拟
Mac 环境无 node / esprima JS parser，没法 `node --check` 跑 syntax。改用 (1) python brace/paren balance 计数确认 379/379 平衡 (2) grep 确认 stale comment 已清 + helper wired (3) python 模拟 t_zh schema lookup 4 维 mock seed 全 hit 中文 label。**规律**：开发机环境受限时，结构性 grep + 字符 balance + schema 模拟可代替 syntax parser；但完整验证仍需 Linux trade-core 跑 console.html 实际渲染（E4 smoke test 范围）。

## REF-20 Wave 2 Batch 2 — U2/U4/U5/U6/U8 (2026-05-03)

### File size cap 1500 行硬上限管理 — common.js 1468→1490 (+22)
U8 Disabled State Card factory 第一次写 264 行（含完整 MODULE_NOTE + 二次拆分 helper + 双 metrics 渲染 fn），编译完发现 common.js 1732 = 1500 cap 远超。三轮压缩：(a) MODULE_NOTE 30 行 → 4 行 (b) CSS textContent multi-line array → 单行 string concat (c) metrics 双 helper fn → 单 const + map → 内联到 render fn 内 (d) var 多行 → comma chain 单行 var (e) IIFE 内 helper i18n → 内联 closure 一行。最终 1490 = +22 行 / 50% buffer 利用率。**规律**：(1) 先写「正常注释 + 拆分 helper」版本验证逻辑通，再压缩到 cap 内 (2) 压缩优先级 = 注释 > CSS array > 拆分 helper > var 声明 (3) 永远保留 ocEsc / ocSanitizeClass / role / aria 关键属性，不为压缩牺牲 XSS / a11y。

### Disabled State Card 三 sub-tab 复用模式（U4/U5/U6 共用 U8 helper）
3 个 disabled sub-tab（Replay P2 / Compare P3 / Handoff P6）原可各自手写 placeholder div，但每个都有：(a) phase chip color variant (b) icon + bilingual gate label (c) optional bilingual banner (d) 12-cell metrics grid placeholder (Compare/Replay) (e) a11y baseline (role/aria-disabled/tabindex) (f) i18n hook + fallback。9 重写 → 1 helper + 3 caller config object。**规律**：sub-tab disabled state 是典型 cross-cutting concern，第一次见到第 2 个就要抽 factory；不要等第 3 个出现才抽（已晚）。同样地，未来 P2-T2 / P4-Q5 上线后也用同一 helper 显示 phase 上线进度通知（switch render config，不重写）。

### Mount point pattern：HTML 占位 + JS 注入，分离结构与渲染逻辑
`#subtab-replay-disabled-card` / `-compare-` / `-handoff-` 三个 mount div 在 HTML 中只是空 div，所有 disabled card HTML 由 inline script 末段的 DOMContentLoaded listener 透过 `OpenClawDisabledStateCard.render(id, opts)` 渲染。优点：(a) HTML 静态部分仅 ~3 行 mount div，结构清晰 (b) 渲染逻辑集中在 JS init block，方便后续 P2/P3/P6 deploy 时 swap render → API state 推真实数据 (c) defensive guard：helper 未载入 fallback 显示 "helper not loaded — see console" inline notice，避免空白画面。**规律**：复杂 component 用 mount-point + JS render 分离；简单静态 element（如 nav button）保留 inline HTML。

### Session 内容 cut-paste 必须验证「无外部残留」+「内部完整」
U2 Session 内容遷入 #subtab-session 时分两步：(1) Edit 把所有 cards / details 复制进 #subtab-session（content 9 sections）(2) Edit 删原位 cards / details。第 2 步后必跑 grep 验证：(a) `positions-tbody` / `btn-stop-all` / `Submit Order` 现在只 inside session div 而非 outside (b) inline script 结尾 `<script>` 之前的 HTML 段无残留任何 `oc-card` / `oc-control-bar` / `details`。**规律**：cut-paste 类操作必跑 leakage check，否则原内容被复制 2 份导致 DOM ID collision（hardest debug type — JS 找到第一个 ID 渲染，第二个孤儿不刷新）。leakage check pattern: `grep` between two known anchor sentinels，确认 segment 干净。

### Self-closing void element 在 Python HTMLParser 误报
HTML5 `<input>` / `<meta>` / `<br>` / `<hr>` 是 void element 不需 close。Python `html.parser.HTMLParser` 默认严格模式下会把 `<input ...>` 当作 unclosed tag 报错。验证 HTML 时（Mac 没 W3C validator）需要：(a) `unclosed at end: []` 检查 stack 最终空 = 真实 OK (b) 出现的 mismatch errors 全部是 void elements (`</input>` / `</meta>`) = 误报忽略。**规律**：Python HTMLParser 适合做 brace-balance + 整体 wellformed sanity check，不适合做 strict spec compliance。这次 6 errors 全是 void element 误报，文件结构实际 healthy。

### tab-paper.html 结构稳定 ~830 行 (U2 后 829)
原 778 行 (U1 land 后) → +51 (U2 移入 + 删原位实际几乎抵消 + 3 disabled mount div + JS init 块) = 829。3 sub-tab 内容只新增 ~3 行 mount + JS 在 inline script 末段加 ~52 行 init listener。distance to 1500 cap 还剩 671 行，buffer 充足。**规律**：tab-paper.html 是单一档完整页，必须时刻关注 cap，每次 wave 加新功能必算预算；当前 wave 只占 cap 的 55%，但 P3a Compare 真渲染 / P6 Handoff modal 真上线还会再加 200-400 行，要预留。

## REF-20 Wave 4 P1-U3 + SEV-2 #1 mobile touch retrofit (2026-05-03)

### V3 §12 acceptance grep target 与 comment 文字冲突 — 必避免在注释中出现 raw token
PM 派发 brief 给的 V3 §12 #19 acceptance check：`grep submitOrder|cancelOrder` in tab-paper.html + app-paper.js → 0 hit (post-U3)。第一版 retirement comment 写「`submitOrder()` / `cancelOrder()` JS 全部移除」直接 leak raw token 进 comment → grep 仍命中 2 行。改用「manual order JS handlers retired (3 fns: togglePrice + 2 order handlers)」绕开 raw token，保留语义。**规律**：当 acceptance check 是 raw token grep（不是 function-call AST grep）时，retirement comment 必须 paraphrase 原 token；否则「retired in code 但 reactivated in comment」。下次 retire framework / function 时，先想清楚 acceptance grep 的 token 边界。

### `<details>` 殼保留 vs body replace 决策 — preserve IA + explain gate
PM brief 写「preserve any Submit Order details `<details>` block but remove inner submit button if exists」表面与 V3 §12 #19 「无 submit/cancel controls」矛盾。最终方案：保留 `<details>` 外殼 + summary chip「P1 已下架」+ body 替换为 disabled-state placeholder（UX subdoc §8 phase/gate language: 「P1 retired · UX subdoc §3 paper_replay_lab_no_order_submit」）。优点：(a) operator 看到熟悉的「手动下单 / Submit Order」入口但点进去明确是 disabled state，不会觉得功能消失了；(b) 殼里讲清楚 blocking gate「P1 已下架 · UX subdoc §3」，operator 知道为啥 + 什么 phase 重新评估；(c) gate-label CSS class 复用既有 disabled-state visual idiom。**规律**：retire 既有 UI 入口时不要直接删 `<details>` 外殼 — 改成 disabled-state placeholder 更友好 + 保 IA 銜接 + 可 grep 知道「曾经有过这个功能」。仅当殼本身已无意义（如只剩内部 hidden div）才整块删。

### Active Orders 操作欄 9→8 column delete — 必同步 thead + colspan + render fn 三处
原 thead 9 列含「操作」(cancel button)；retire 时必同步：(a) `<thead><tr>` 删「操作」th (b) 3 处 `colspan="9"` → `"8"`（empty-row × 1, 错误重试 × 1, 暂无活跃订单 × 1）(c) `loadOrders()` render forEach 内删 `'<td><button ...cancelOrder()>取消</button></td>'`。漏一个就 break — colspan 不对 empty row 排版崩；render fn 不对 button reference dead fn → console error。第一次只删 button line + thead 漏 colspan，被自己 grep 抓到。**规律**：删表格 column 时三处必须同步检查清单：thead × 1 + colspan-occurrences × N + render-loop × 1。可用 `grep -nE 'colspan="<old>"' <file>` 一次抓所有 occurrence 避免漏。

### `@media (max-width: 700px)` 在 page-scoped style 覆盖 common.js mobile shrink rules
A3 SEV-2 #1: 行动装置 `.oc-subtab-btn` 6px 14px / 12px font + `.oc-mode-badge` 3px 9px / 11px font 都 < 44px touch target (WCAG 2.1 AA 2.5.5 Target Size)。修法：在 tab-paper.html 加 page-scoped `@media (max-width: 700px)` 重定义 min-height + 较大 padding + 较大 font-size。共存性：common.js 1394-1396 行已有自己的 `.oc-mode-badge` mobile shrink rule (font-size 10px / padding 2px 7px) — 我们的 page-scoped rule 因 cascade 顺序后入栈 + selector specificity 相同 (1 element) 自然覆盖（CSS later-wins-on-tie）。验证：`@media (max-width: 700px)` block 数 = 1（仅这次新增），`min-height: 44px` + `min-height: 32px` 各 1 处。**规律**：当 common.js 已有 mobile media query 与 page UX 要求冲突时，page-scoped @media 覆盖比改 common.js 安全（不影响其他 11 tab + console.html）。

### Mac 环境 HTML smoke test = python HTMLParser stack depth 0 + 字符 balance + grep
没装 W3C validator / chrome devtools / playwright —用 (1) custom HTMLParser 子类追踪 push/pop tag stack，最终 stack 深度必 0 + errors 必 0 (2) `{}/()/[]` count 平衡 (3) acceptance grep 0 hit。本次 result: stack=0 / errors=0 / 105:105 / 383:383 / 22:22 全 OK + grep 0 hit。**规律**：Mac dev 环境 HTML 验证必跑这三套 + 同步 push 进 Linux 由 E4 跑 console.html 真实渲染 / a11y axe-core / mobile viewport DevTools test。结构性验证不能替代 visual / a11y / interaction 验证，但可以阻止 80% 的 「HTML 不 wellformed」level bug 进入 review。

## REF-20 Wave 7 P5 R20-P5-A1/A2/A3/A4 — Agents Monitor 抽出 (2026-05-03)

### Wave 7 hard prereq bypass (operator override)
PM brief 明示「LG-2/3/4 stable 7d 是 Wave 7 entry hard prereq，但 operator 全自主模式 + 「全部做完然後 deploy」覆寫」。E1a IMPL 範圍接受此 bypass，sibling LG-2/3/4 frontend race risk = accept-and-flag for deploy time consideration。

### 「11→12 Tab」brief 與真實 codebase drift
PM brief 寫「11-Tab nav → 12-Tab nav」+ V3 §11 P5「12-Tab top-level」。實測 console.html 原本就是 12 tabs（system / live / demo / paper / charts / strategy / risk / ai / learning / governance / monitoring / settings），加 agents 後變 13。CLAUDE.md §五 也寫「11-Tab」是 outdated count。意圖明確「+1 tab 抽出 Agents Monitor」，IMPL 按意圖走。**規律**：brief 引用「N-Tab」字面值時，必須先 grep `const TABS = [` 確認真實 count，避免 silent drift；如有偏差 IMPL 報告中明文標出，不靜默修正 brief 數字。

### Mount target swap pattern — 既有 JS 0 mutation，純 HTML 容器遷移
agent-tracker.js（997 行）整段 0 邏輯改動；只是 mount target 從 tab-learning.html → tab-agents.html。HTML scaffold（5 區塊 × 4 state IDs = 20 IDs + explain-agent-tracker）整段複製到新檔，原檔整段刪除（含 5 oc-card section + style 區塊 + ocExplain 內聯 + script load + boot block）。Cross-check：`grep id="agent-..."` 確認 tab-agents.html 全 20 IDs PRESENT + tab-learning.html 0 leakage。**規律**：當「extraction」task 是 mount target swap 而非 logic refactor 時，先 audit JS 引用的全部 DOM ID（用 setLoadingState prefix pattern 推算），確保新容器有，舊容器 0 leakage。

### Banner dismiss 90d auto-reset 雙鍵設計
單純 `localStorage.setItem(dismiss_flag, '1')` 永久 dismiss → operator 90d 後完全忘記遷移事實。改成雙鍵：dismiss_flag + dismiss_ts（ISO 字符串），讀取時計算 elapsed_days，超 90d → clearItem 兩個鍵 → banner 重新顯示。trade-off：operator 在同 browser 90d 內看不到 banner（合理）；90d 後再次提醒（避免長期失憶）。**規律**：「auto-dismiss N d」UX 約定不能 implement 為「永久 dismiss」— 必須有 timestamp 機制 + 過期 reset，否則違反 UX 合約。

### 跨 iframe switchTo 透過 window.parent
tab-learning.html 在 console.html 內 iframe 中跑；redirect banner link 點擊要切到 12th tab，必須 cross iframe 呼叫 parent window 的 switchTo()。實作 `window.parent.switchTo('agents')`；defensive 檢查 `typeof === 'function'` + try/catch 避免 cross-origin error / parent 直接打開非 iframe 場景。**規律**：iframe-based tab system 中，sub-iframe 內的 navigation 必須透過 parent window；不能用 `window.location.hash = '#tab-agents'`（hash 在 sub-iframe scope 不會觸發 parent switchTo）。

### Mode badge slot baseline = "P5 抽出 read-only never-emit" 視覺合約
4 維 mode badge（data_tier / output_policy / calibration_freshness / execution_confidence）對齊 paper tab pattern。Agents Monitor 是 read-only 永不送單 surface，所以 execution_confidence='none'（紅外框 + ⚠️ icon）= anti-cognitive-fraud SENTINEL。data_tier='mixed'（demo + live_demo 兩種 fills 都顯示）；output_policy='advisory'（只觀察不下單）。**規律**：read-only never-emit surface 的 mode badge baseline 必選 execution_confidence='none' 強化「不可作為實盤決策依據」視覺合約 — 不能省略 mode badge 槽位（即使內容空也保留 slot 待 future 動態狀態接線）。

### tab-agents.html 290 LOC = 新檔，A11y baseline retrofit + bilingual comment
新檔 290 行（cap 1500，buffer 1210，未來 dynamic mode badge update / per-card refresh state 加可繼續疊）。A11y 自帶：5 個 region role + 5 個 aria-label + 5 個 tabindex（5 卡的 data div 提供 keyboard reach）+ 1 個 phase row role status + 1 個 section role region。CSS @media (max-width: 700px) 重定義 .oc-mode-badge min-height:32px + .agents-phase-chip min-height:32px，page-scoped 覆蓋 common.js mobile shrink rules（與 tab-paper.html SEV-2 #1 retrofit 同 pattern）。**規律**：抽出 task 新建檔必須帶 A11y baseline + mobile touch retrofit，不能等 SEV-2 audit 再補 — 因為新檔 audit 觸發點通常是 deploy 後操作上，cost 高於 IMPL 期一次補完。

### 三檔同 commit 修改 LOC budget
console.html: 579→586 (+7) / tab-learning.html: 502→491 (-11 净；移除 100+ 行 section + 增加 banner CSS/HTML/JS handler) / tab-agents.html: 0→290 (+290 新檔)。三檔總 LOC 變化 +286 行，但無單一檔超 1500 cap。**規律**：抽出 task 是 zero-sum 重分配（A 檔 -X 行 + B 檔 +X 行 + 少量新基建 banner/CSS）；不會 net 增加多少；如出現 net 暴增 = scope creep 訊號（多寫了不在 task 範圍的功能）。本次 +286 行主要來自新增 mode badge slot 基建（35 行）+ banner CSS+HTML+JS handler（85 行）+ phase chip row（25 行）+ MODULE_NOTE 雙語注釋擴充（80 行）+ A11y attributes（30 行）+ 既有 section 整段移植（30 行净）。

### tab-paper.html 829→847 (+18 LOC) — Wave 4 P1-U3 + SEV-2 #1 同 commit retrofit
size 详细：(a) U3 删除 = `.order-form` CSS 4 行 + `<details>` 内 12 行 form + `explain-order` ocExplain 4 行 + 3 fns 14 行 + cancel button render 1 行 = -35 行；(b) U3 加入 = retirement comments 7 行 + `<details>` placeholder body 16 行 + colspan/thead 同步 0 行 (replace) = +23 行；(c) SEV-2 #1 加入 = `@media` block + bilingual comments = +18 行；(d) order-form CSS 注释保留 1 行 + 其他 retire comments = +12 行。净 +18。distance to 1500 cap = 653 行 buffer，仍充足。**规律**：retire 操作不必然净减少 LOC — 替换 disabled-state body / 加 retire 注释 / 同 commit 含 SEV-2 retrofit 都会拉回；但替换 + 注释 buyback 比保留 dead code 长期 maintenance 友好。

## REF-20 Sprint B1 R4 — Paper Replay Lab UI Enablement (2026-05-05)

### 任務範圍：4 task (R4-T1/T2/T3/T4)，純 frontend，0 backend 改動
- **R4-T1**：tab-paper.html replay 按鈕移除靜態 `aria-disabled="true"` / `data-disabled="true"` (~10 LOC)
- **R4-T2**：app-paper.js 新加 `OpenClawReplaySubtab` namespace + readiness probe + 5-state machine + 30s 週期輪詢 (~410 LOC)
- **R4-T3**：app-paper.js renderReadyState 4 cell + 載入 experiment_id 按鈕 + CSS injection helper (~120 LOC)
- **R4-T4**：tests/static/ 新加 1 browser HTML mock-fetch fixture + 1 pytest sibling (~860 LOC)

LOC delta：tab-paper.html 909→928 (+19) / app-paper.js 447→956 (+509) / tests/static/ 0→862 新加。

### 設計決定：Sprint A baseline 4 cell 視覺合約 — execution_confidence='none' 是 anti-cognitive-fraud SENTINEL
PA brief §3 R4-T3 + CLAUDE.md §九 已登記：`evidence_source_tier='synthetic_replay'` 是 Sprint A 唯一上線 tier，**不可作 ML training data**。所以 4 baseline cell 必須：
  - `execution_confidence`: 「無 / NONE」紅外框 + ⚠ 警示
  - `data_tier`: 「S3（合成 / Synthetic）」中性
  - `fee_model`: 「尚未校準 / NOT CALIBRATED」紅外框
  - `calibration_status`: 「PENDING R6」紅外框
即使後端未來在 `/replay/report/{id}` envelope 加欄位，前端 baseline 仍維持 — 待 Sprint C R6 fee calibration ship 才升級為 'CALIBRATED' / 'LOW' / 'MEDIUM' tier。**規律**：anti-cognitive-fraud baseline UX 必獨立於 backend 動態欄位；backend 沒回的欄位前端 must NOT silently 升級為「樂觀」標籤。

### 5 態狀態機 + last-active=replay 必先 probe（禁直接 active）
PA brief §3 R4-T2 invariant：「即使 last-active=replay localStorage，下次 load 仍須先 probe；禁直接 active without /health probe」。實作做法 = `ocPaperSubtabShow(name)` 對 `name === 'replay'` 觸發 `OpenClawReplaySubtab.onTabActivate()`，後者先 fetch `/api/v1/replay/health` → 解析 `wiring_status` → `ready` render ready / `degraded`+`binary_missing` render disabled card via U8 helper。
**規律**：localStorage persistence + 動態 backend gating 共存時，persistence 是「讀回 last name」，gating 永遠在 render 階段做（不在 read 階段短路）；persistence 不可承擔 readiness assertion 責任。

### 30s 週期輪詢 deactivate 必 clearInterval（iframe 內背景燒 timer 反模式）
console.html iframe 內 setInterval 在 user 切走 tab 時不卸載；不 clear 會 30s 燒 fetch 一輩子。`onTabDeactivate` 必 `clearInterval(_pollIntervalId)` + `_pollIntervalId = null`。同時 `startPolling` 內 `if (_pollIntervalId !== null) return` 防重複註冊。test fixture `case_deactivate.polling_cleared_post` 直接讀 `_isPolling()` 驗證。
**規律**：iframe-based GUI 任何 setInterval 必有對應 onDeactivate clearInterval；不 clear = 30s 燒一輩子；test fixture 必有「pre/post deactivate polling state」斷言。

### Backend endpoint URL 不返 4 cell 數據 — fallback 到 baseline + 仍呼 endpoint 確認 health
`/api/v1/replay/report/{id}` 當前 schema 只回 `experiment_id / manifest_id / run / artifacts / wiring_status`，**不**返 `data_tier / evidence_source_tier / fee_model / execution_confidence`。R4-T3 設計 = 載入按鈕 fetch endpoint → 顯示 `run.status` + `artifact_count` + 「evidence_source_tier=synthetic_replay (Sprint A baseline)」status 文字；4 cell 內容仍維持 baseline（不 silent 升級）。**規律**：當後端 endpoint schema 還沒實作 GUI 需要的欄位時，**呼 endpoint 當 health probe + 顯示 baseline** 比「假裝有真實數據」乾淨；user 看到 status 文字明確知道「現在是 Sprint A baseline」。

### test fixture 沿用 `test_agent_tracker_contract.html` 純瀏覽器 mock-fetch pattern（避免 push back PM）
PA brief §R4-T4 寫「~150 LOC pytest 或 playwright」。專案無 jsdom / vitest / playwright 框架；現有 frontend test fixture 唯一是 `test_agent_tracker_contract.html`（純瀏覽器 mock-fetch + record/assertContains 手寫斷言）。我選用同 pattern 加 1 browser HTML test（423 行，6 case 覆蓋 ready/degraded/binary_missing/fetch_failed/deactivate/probe schema）+ 1 pytest sibling（439 行，28 個 structural assertion，CI 可跑無 browser 依賴）。**規律**：當既有 codebase 已有「最低線交付」test pattern 時，沿用比 push back PM 改更高層 test 框架快；但 pytest sibling 必加（確保結構 invariants 進 CI grep 防線，browser 端只是 runtime 視覺驗證）。

### Mac dev workflow：scp 同步 + ssh 跑 pytest，無 git commit（PM 後續審完才 commit）
brief 明示「禁止 commit」。Mac CC IMPL 結束後：
  1. `scp` 4 個檔案到 Linux trade-core 對應路徑（不過 git）
  2. `ssh trade-core "python3 -m pytest ..."` 跑新 test
  3. 同時 git status 確認 Mac local 還是 modified/untracked 狀態，不 git add
這流程繞開 multi-session race（隔壁 sub-agent 可能在 main branch 推他自己的 R0-T0 work，不應被 R4 frontend 改動覆蓋）。**規律**：跨 sub-agent 並行 IMPL 期 + PM 規定 not-yet-commit 時，scp 跑驗證比 commit-then-revert 安全；commit 留給 PM 統合 sign-off。

## W-AUDIT-7c 三項 GUI 修復（2026-05-09）

### Sub-tab 拆分時 modal overlay 必抽出 sub-tab content
`<div [hidden]>` 套用 `display: none` 給整顆 subtree（含 fixed/absolute 後代）— 這是 CSS 規範，無法繞開。所以 sub-tab 內含 modal overlay 時，當 sub-tab 被切走，modal `.show` 也不會渲染（即使 fixed position）。**規律**：Sub-tab 拆分前必先 `grep` 該 tab 內所有 fixed-position `<div>` modal/dialog/overlay；全部抽到 sub-tab content **之外**（檔尾 `</script>` 之前），不影響 visual layout（fixed position 不依賴 DOM 位置），同時保證 sub-tab 切換不影響 modal 可用性。本任務抽出 2 個（restartModal + dlg-apikey）。

### 高摩擦 typed-confirm 替代單擊 yes/no — phrase case-sensitive
A3 v2 audit 抓出 governance-tab.js 兩個 native `confirm()` 是 critical 寫操作（bulk approve/reject + recovery approve），用 native `confirm()` UX 反人類且無 audit 證據鏈。新建 `openTypedConfirmModal(options)` helper 要求 user 鍵入 phrase（預設 'CONFIRM'，case-sensitive）才啟用「確認」按鈕。共用既有 `.oc-confirm-overlay` CSS，加 actor / impact / rollback metadata 槽位（CLAUDE.md §五 audit-aware 三原則第 2 條）。**規律**：Critical-grade governance 寫操作（system_mode 切換 / live_execution_allowed / bulk approve / recovery override）一律 typed-confirm，不能單擊 yes/no — 額外打字成本是 cognitive friction 防誤觸的設計，不是 UX 摩擦。

### Settings sub-tab namespace 隔離（localStorage key + show fn）
不重用 `ocPaperSubtabShow` 因為 Paper 與 Settings 是兩個不同 tab、不同 sub-tab 名單；硬塞同一 helper 會在 Paper 沒此 sub-tab 時走 fallback 路徑誤導。改成獨立 `ocSettingsSubtabShow` + `_OC_SETTINGS_SUBTAB_LS_KEY = 'settings_active_subtab'`（與 paper 的 `paper_active_subtab` 隔離）。**規律**：Sub-tab 系統 namespace 隔離 = `(LS key) × (function name) × (DOM ID prefix)` 三層全隔離；不要共享 helper 跨 tab 否則 fallback / restore 邏輯會互相污染。

### 多 session race 守則：staged 只加自己改的檔
派任務時 git status 已有別 session 的 modified（adr + ml_training + cron）+ untracked（execution_plan 3 檔）。`git add` 必須 explicit 列檔名，**禁** `git add .` / `git add -A`，否則吸收他人 WIP 變成不知情共 commit。本任務只 stage 5 個 W-AUDIT-7c 相關檔（4 修改 + 1 新增 fixture），其他 7 個改動完全保留 unstaged 給該 session 自己 commit。**規律**：multi-session 同工作樹下 `git add` 必 explicit；commit message 只描述自己改的。

### Fixture 沿用 tests/static/ pattern + browser mock-fetch（無 jsdom/jest）
專案無 jsdom / jest / vitest / playwright；既有 `tests/static/test_agent_tracker_contract.html` + `test_replay_subtab_readiness.html` 已是「最低線交付」pattern（純瀏覽器 mock-fetch + record/assertContains 手寫斷言）。本任務沿用同 pattern 加 `test_typed_confirm_modal.html`（5 case 覆蓋正確 phrase / 錯 phrase / 取消 / Esc / case-sensitive）。**規律**：當 codebase 已有最低線 fixture pattern 時沿用比 push back PM 改更高層 test 框架快；fixture 至少能讓 reviewer 用 browser 一鍵驗證 modal 行為。

### Mac dev 環境 HTML/JS 驗證 = HTMLParser stack + grep + brace count
Mac 沒裝 W3C validator / esprima / node JS parser；用 (1) Python `html.parser.HTMLParser` 子類追 push/pop tag stack，最終 stack residue 0 + errors 0 (2) `{}/()/[]` count 平衡 (3) 結構性 grep（function name + DOM ID + key string literals）。本任務 4 個改動檔 stack 全平衡，2 個 JS 檔 brace 全 0 diff。Production smoke test 仍由 E4 在 Linux 跑 console.html 真實渲染。**規律**：Mac dev 環境用結構性 grep + 字符 balance 不是「真 syntax check」，但能擋 80% 「不 wellformed」level bug；剩 20% 由 Linux runtime 抓。

### 28/28 pytest PASS + 169/169 sibling regression unchanged（3 pre-existing fails 不歸 R4）
新加 28 個 R4 test 全 PASS（覆蓋 R4-T1/T2/T3/T4 + Sprint A invariants + 跨平台 sanity）。sibling regression 169 PASS / 3 FAIL — 3 FAIL 是 Linux HEAD `6e39c51d` 上 `test_replay_routes_auth.py::test_authenticated_*_post_run` 系列（POST /run active_run cap 邏輯），與我 frontend 改動 0 重疊。透過 `git stash --include-untracked` + 重跑驗證 3 fail 在我改動前已存在 → 不歸 R4 責任。
**規律**：sibling regression 報出 FAIL 必先「stash --include-untracked + 重跑」確認是否 pre-existing；只有 「stash 後 PASS / unstash 後 FAIL」才是真退化；同 stash 兩邊都 fail 屬於 pre-existing baseline，IMPL 報告必明文標出避免 reviewer 誤解為 IMPL 引入退化。

## W-AUDIT-7c Round 2 fix 教訓（2026-05-09，A3 verdict FALSE_CLOSED 修補）

### Brace/paren/bracket diff = 0 對 lexical-scope shadow 無效
上輪 sign-off 自評「JS brace=0 parens=0 brackets=0」字符 balance check **完全無法捕捉** same-scope `const ok` + `let ok` 重複宣告的 SyntaxError。governance-tab.js 整檔 parse fail，user 一進 governance tab 所有 fn ReferenceError。**規律**：GUI E1a 任務 sign-off 必跑 `node --check <file>` 真實 V8 parser；character balance 是輔助，不能替代 syntax check。Mac 開發環境裝 `node` (homebrew) 即可，不需 jsdom。

### Fixture 結尾殘留 `</content></invoke>` 是「沒真開瀏覽器」鐵證
上輪 fixture 結尾 line 125-126 是 Write 工具 XML payload 殘留（`</content></invoke>` 是 tool call closing tag）。如果上輪真在瀏覽器打開過，瀏覽器會視這 2 行為 invalid HTML 並 console error；事實是寫完就放著沒驗證。**規律**：Write tool 用於寫整檔時若 prompt 內 XML payload 殘留，必須回頭 grep `</content>` / `</invoke>` 字面值清掉；fixture sign-off 必有「真開瀏覽器跑」或「裝 jsdom 跑 headless runner」的證據（screenshot / stdout / DOM dump）。

### Cancel path 靜默 return 是 anti-UX
modal 取消後純 `return` 沒任何 toast → user 沒得到反饋以為按錯了會再點一次。本輪 4 cancel path 全加 `ocToast('已取消...', 'neutral')`。**規律**：governance ux-checklist §5「audit-aware: 最近 5 次 actor + ts + 結果」原則延伸 — cancel 也算結果，必須 surface visible feedback。所有 modal-based critical 寫操作 cancel path 都加 cancel toast。

### 「事先 fetch list 才開 modal」是 audit-aware UX 準則
governance critical 寫操作 modal body 不能只給通用 phrase（「即將批准全部待審」），必須含具體影響：N 筆、change_id 樣本、strategy/symbol/freeze reason/age 等。本輪 [#5] bulkAudit 改先 fetch 再開 modal、[#6] confirmApproveRecovery 從 cache `_lastPendingRecovery` 找 detail 顯示。**規律**：bulk 操作 modal 必含「N 筆 + 前 5 筆 ID + overflow `... 及其他 M 筆`」；single 操作 modal 必含 cache lookup 取得 entity detail（無需新 API call，從 list cache `find()`）；cache 過期則強制 reload 一次再顯。

### Modal singleton 防雙開 + button disable 雙道防線
critical 寫操作 race protection：
1. trigger button 在 await modal **前** `disabled = true`（try/finally 復位）— 第一道
2. `openTypedConfirmModal` 內 detect overlay 已 `.show` 狀態時 `console.error` + `Promise.reject('modal already open')`— 第二道
兩道並用避免 fast 連點覆蓋第一個 Promise resolver。**規律**：singleton modal helper（如 openTypedConfirmModal / openPromptModal / openConfirmModal）必有「already open」guard；caller 也必有 button disable + finally 復位；兩者協作不可省略其中一個。

### bulk 部分失敗必收 failedChangeIds + toast 帶 detail
for-loop 內 `okCount++` / `failCount++` 之外，必收 `failedChangeIds.push(change_id)`，最終 toast 在 base counter 訊息後追加「失敗：[id1, id2, ...(+N)]」（≤ 10 直顯，> 10 截斷）。toast type 改三態：全成功 success / 部分失敗 warn / 全失敗 error。**規律**：所有「one user action 觸發 N backend write」的 bulk 操作必有 partial-fail visibility — operator 看到「7 項已同意」但實際 5 成功 2 失敗時必須能立刻看到哪 2 個失敗，否則 audit trail 斷層。

### jsdom 裝起來跑 fixture > Mac 純結構驗證
上輪用 Python HTMLParser stack + brace count 是 80% bug 防線，但漏了 same-scope shadow（lexical layer）。本輪改裝 jsdom (`npm install jsdom` 在 /tmp/jsdom-runner)，跑 5 case fixture + 2 e2e（bulkAudit/confirmApproveRecovery modal real flow）。jsdom 完整支援 input/dispatchEvent/click/KeyboardEvent/Promise/setTimeout/classList，行為與 Chrome V8 + Blink 等價（V8 同源），唯一差異 layout/paint 不影響 GUI logic test。**規律**：Mac 環境一次性 `npm install jsdom` 是值得的工作流投資；下次 GUI E1a 任務若涉及 modal / event / async UX 路徑，先 jsdom headless 驗一次，再 push back 給 E4 在 Linux real-browser 跑 visual + a11y。

### `event.currentTarget` 在 inline `onclick="bulkAudit('approve')"` 模式下 reachable
HTML 內 `<button onclick="bulkAudit('approve')">` 點擊時，`bulkAudit` 函數體內 `event` global ref 仍指向 click event；`event.currentTarget` 是觸發 button DOM。**規律**：inline onclick handler 內呼叫的 fn 可直接用 `typeof event !== 'undefined' && event && event.currentTarget` 三層 guard 拿 trigger button，不需修 HTML 改傳 `this` 參數（會破壞 caller 兼容）；jsdom 測試時 `w.event = { currentTarget: btn }` mock 即可。

## W-AUDIT-7c Round 3 fix 教訓（2026-05-09，E2 senior catch HIGH-1）

### Singleton guard reject 必由 caller 接，否則「不靜默」初衷被 finally 反噬
Round 2 [#7] 在 `openTypedConfirmModal` 加 singleton guard `Promise.reject(new Error('modal already open'))`，立意是「不允許併發雙開」；但 caller 端 3 個 `await openTypedConfirmModal(...)` 寫法是 `try { await ... } finally { btn.disabled = false }` 不接 catch — 結果是：(1) JS unhandled promise rejection → console error user 看不到 (2) finally 仍跑 → trigger button 重新可點 → user 誤判「按了沒反應，再點一次」 → 違背 round 2 [#7] 設計初衷。**規律**：singleton helper 加 reject 路徑時，必同時 retrofit 所有 caller 用 try/catch 包 await；單方面在 helper 加防護 + caller 不接 = 設計矛盾，比沒防護還糟（user 行為更難預測）。E2 senior view catch 出 A3 (focus on UX flow) 漏的 lexical-scope contradiction。

### `try { let proceed; ...; } catch { ... }` 兩段式 await 處理
原本 `const proceed = await modalCall;` 一行寫法是「成功路徑 + cancel false 路徑」二態；加 try/catch 後變三態：(a) reject (singleton/unexpected) → toast warn/error + return (b) resolve(false) cancel → toast neutral + return (c) resolve(true) proceed → 後續業務。寫法：先 `let proceed;` 再 `try { proceed = await modal; } catch (err) { ... return; }` 然後 `if (!proceed) { ... return; }` 最後業務。三段都加 `return; // finally 會 re-enable button`。**規律**：async modal call 必三態完整收口；catch 與 cancel 不可合併（cancel 是有意 user choice，singleton reject 是 race condition / unexpected error），UX feedback 用不同 toast type（neutral vs warn/error）反映語意差異。

### `const ok` vs `const proceed` rename = future-proofing footgun 預防
Round 2 bulkAudit rename `const ok` → `const proceed` 因為 outer `const ok` + inner counter `let ok = 0` 衝突；confirmApproveRecovery / clearProviderKey 沒 rename 因為 outer `const ok` + 沒衝突的 inner var。E2 round 2 + A3 round 2 都點到「兩處不一致 = future-proofing footgun」。雖然不同 function scope 不衝突，但下次 maintainer 從 bulkAudit copy-paste 到別處 refactor 出 inner counter `ok` 就立刻爆 SyntaxError。round 3 統一全部 rename 成 `proceed`。**規律**：同 module 內 modal-await 結果變數命名要求 100% consistency（`proceed`），即使單獨看不衝突；naming consistency 是低成本 future-proofing。

### 英文 inline 注釋預設刪（2026-05-05 governance change）
common.js 1919 殘留 `// case-sensitive match; trim trailing whitespace to avoid false-negative` 是 round 2 修改時忘清的英文重複注釋；中文版 1918 行已自存。E2 + A3 都點到。**規律**：2026-05-05 廢除 bilingual mandate 後，新代碼僅中文；既有中英對照不主動清，但**「修改既有 block 時移除英文只保留中文」** 是 governance rule。round 3 修法：直接 Edit 刪英文行不留 placeholder。

### jsdom Case 7 fixture 模擬 caller 包 try/catch 才能驗 'modal already open' 路徑
直接 await 第二次 modal 在 jsdom 跑出 unhandled rejection；Case 7 設計 = `try { await second } catch (err) { secondError = err; }` 模擬正確 caller 行為，斷言 `secondError.message === 'modal already open'`。如果直接 await 不接 catch，jsdom 會 emit unhandledrejection event，測試 framework 看不出對錯。**規律**：jsdom singleton race smoke 必模擬「正確包 try/catch 的 caller」，這也順便驗證了 caller 端 3 個 callsite 的 try/catch pattern 能正確接 reject。

### A3 漏 HIGH-1 vs E2 catch HIGH-1 — multi-reviewer 不同視角互補
A3 round 2 verdict TRUE_CLOSED 8.4/10（B+）9/9 brief 項全 PASS — A3 從 user-facing UX flow 看（「modal 打開了 / cancel 了 / typed correct phrase 了 / button race fixed 了」），4 個 happy path 角度都 PASS 不疑。E2 senior view 從 promise lifecycle + lexical scope 看 — 看出 caller 端 await 沒 catch + helper reject + finally re-enable 三個 trace 合起來 = silent bug。**規律**：A3 (UX-focused review) 與 E2 (senior code review) 同 round 都跑必要；A3 verdict TRUE_CLOSED 不是 commit 終點，E2 verdict 才是 RETURN/APPROVED 二選一的 gate；多 reviewer 不同視角互補才能 catch lexical-level 矛盾。
