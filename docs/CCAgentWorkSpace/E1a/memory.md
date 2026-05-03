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
