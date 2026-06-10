# E1a Memory — 工作記憶

> 本檔=長期教訓+近期記錄；超 300 行由 R4 巡檢標記、PM 派工壓實，舊條目原文遷 memory-archive.md（append-only）；agent 完成序列照常追加於檔尾。

## 長期教訓（2026-06-10 壓實蒸餾；原文與脈絡見 memory-archive.md）

- 本檔定位=歷史教訓+角色偏好，非 active state/TODO/runtime ledger；與 TODO/README/CLAUDE/代碼/runtime 證據衝突時信較新有證據來源並顯式說明；長報告放 workspace/reports/。
- 注釋語言：2026-05-05 起新注釋只寫中文，修改既有 block 時移英文留中文；operator-facing 文字一律中文，工程術語配括號中文解釋；破壞性操作確認彈窗不可省略。
- XSS 鐵則：innerHTML/insertAdjacentHTML 拼字串必 ocEsc；.placeholder/.textContent/.value 屬性賦值天然安全；審 `innerHTML = var` 須向前同 fn body trace var 來源；動態字串禁入 onclick= 字面注入 — 用 data-* attribute（ocEsc）+addEventListener。
- GUI sign-off 必跑 node --check（真 V8 parser）：brace/paren balance 抓不到 same-scope shadow SyntaxError；HTML inline-JS 用 regex 抽 `<script>`（排除 src=）join 後寫 tempfile node --check。
- Mac dev 驗證鏈=HTMLParser stack+brace balance+結構 grep+node --check+jsdom（涉 modal/event/async 必跑）；Mac 無 fastapi，pytest/runtime 渲染/a11y 必 ssh trade-core；fixture sign-off 必有真跑證據，Write 工具殘留 `</content></invoke>` 必 grep 清。
- E2+E4 通過前不算完成；A3（UX 視角）與 E2（senior promise/lexical 視角）互補，A3 TRUE_CLOSED 不是 gate，E2 verdict 才是；lesson 必內化進下一個 IMPL baseline 不重犯。
- 危險決策字段（如 shadow_mode）必三分支 true/false/unknown，unknown 走最保守警示；禁 field-level fallback chain（吞 contract drift），欄位缺失 fail-loud 顯空態+console.warn；backend 未回欄位前端禁 silent 樂觀升級。
- Critical governance 寫操作一律 typed-confirm（case-sensitive phrase+actor/impact/rollback metadata），先 fetch detail 再開 modal；cancel path 必 toast 反饋；bulk 操作必收 failedChangeIds 顯部分失敗明細。
- Modal singleton reject 必由全部 caller try/catch 三態收口（reject→warn／cancel→neutral／proceed→業務）；多 modal SDK 共用 module-level lock 且 close/cleanup（含 reject 路徑）必清 lock；trigger button disable+finally 復位。
- fixed/absolute modal overlay 必抽出 sub-tab content 外（sub-tab [hidden] 連帶 display:none 整顆 subtree）；純表單卡片可留 sub-tab 內。
- iframe tab 內 setInterval 必接 pagehide/visibilitychange/onDeactivate clearInterval（切走不清=燒一輩子）；跨 iframe 導航走 window.parent.switchTo()+typeof guard+try/catch。
- 殘留風險/不可逆失敗警示必常駐 dismiss-on-click 橫幅（append document.body survive 局部重繪+actionKey dedupe），禁自動消失 toast；live 寫操作 caller 一律 classifyLiveMutation 禁 `if (d)` 報成功；新增 toast type 必同步加 .oc-toast-<type> CSS。
- FastAPI router 拆檔：sibling route 檔必在 main.py explicit import 觸發 decorator 註冊（只 include_router 不夠）；GUI 需依 error type 做 view-swap 時用 200+結構化 error envelope 而非 4xx toast。
- CSS 衝突用 page-scoped specificity/@media 覆蓋並注釋原因，不改 common.js global；mobile <700px touch target ≥44px（WCAG 2.1 AA），N-col grid 行動版必 wrap。
- 檔案 LOC 治理看 per-file 非 net delta：>800 行需 review，1500/2000 硬上限，超限需 PM exception 明文簽；每次改動先算預算，不夠先 split 或 push back。
- 刪表格 column 三處同步（thead+全部 colspan+render loop）；cut-paste 遷移必跑 leakage grep 防 DOM ID collision；同語意雙元素必不同 ID+helper 統一套邏輯。
- 敏感欄位三鐵律：value 永遠空、狀態走 placeholder/hint；提交後（成敗皆）立即清 DOM；成功後 re-render 用後端回的遮罩；clear sentinel（__CLEAR__）走獨立旁路標記不混 input.value。
- multi-session 同工作樹：git add 必 explicit 列檔名禁 -A/.；不認識的改動禁 revert；branch race 用獨立 git worktree；PM 未授權 commit 時 scp+ssh 驗證代替 commit。
- sibling regression FAIL 必 `git stash --include-untracked`+重跑判 pre-existing；只有 stash 後 PASS/unstash 後 FAIL 才是自己引入退化，IMPL 報告必明文標示。
- localStorage persistence 不承擔 readiness assertion（gating 永遠在 render 階段 probe）；auto-dismiss N 天必雙鍵 flag+timestamp 過期 reset；read-only never-emit surface 的 mode badge 必 execution_confidence='none' anti-cognitive-fraud sentinel；誤導命名（shadow/live）靠文案+注釋多層冗餘消歧。

## 近期記錄

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

## W-AUDIT-9 T5 Graduated Canary GUI surface（2026-05-09 Sprint N+0 W2）

### Tab 選擇：governance > settings — namespace 對齊比 historic placement 重要
AMD-2026-05-09-03 §4.3 給的選擇：「Settings tab 或 Governance tab subsection，由 W-AUDIT-7 GUI implementer 拍板」。tab-settings.html 已有 4 sub-tab（engines/system/connection/debug）+ restart modal + apikey dialog，再塞 5-stage cohort 顯示 + manual promote 邏輯不對齊；tab-governance.html 已含 SM-01..04 + Decision Lease + EX-04 + Live Auth + Paper→Live Gate + Learning Tier — Graduated Canary 與這些治理元件天然同 namespace（cohort lineage / lease 走 LeaseScope::CanaryStagePromotion / observation gate / promotion semantics）。**規律**：新 governance 機制的 GUI placement 不是「找空位」，是「找 namespace」— 同 tab 內 cross-reference 才能讓 operator 在一頁看完整 治理 picture，不需 jump tab 拼湊。

### 後端路由用既有 governance_router prefix，不新建 prefix
governance_extended_routes.py / governance_promotion_routes.py 都 import `governance_router`（prefix=/api/v1/governance）並 attach decorator（@governance_router.get/post），檔案職能拆但 URL prefix 共享。新 `governance_canary_routes.py` 沿用此 pattern：兩個 endpoint `/canary/cohorts` + `/canary/manual_promote` 都 mount 在 `governance_router` 上。**main.py 必加 `from . import governance_canary_routes` 觸發 decorator 註冊**（不 import 則 endpoint 不存在；本 task land main.py 順帶加 governance_extended / governance_promotion 兩個既有 mock import，明確 documentation 觸發機制；本 commit 也修了 governance_promotion_routes 的隱性依賴）。**規律**：FastAPI router 拆檔時，sibling routes 必須在 main.py 側 explicit import 觸發 decorator 註冊；只 include_router(governance_router) 不夠（router 是 mutable container；decorator 只有 import 才執行）。

### LeaseScope::CanaryStagePromotion 走字符串 facade，不擴 enum signature
T6（E1-D 隔壁 sibling）已 IMPL `LeaseScope::CanaryStagePromotion` Rust enum + 專用 `acquire_canary_stage_promotion_lease()` 但保留既有 `acquire_lease(scope: &str, ...)` 不動 signature（避免撞 W-AUDIT-8a Phase A trait 升級時序）。**T5 後端 IMPL 的選擇**：直接呼 `governance_hub.acquire_lease(scope='CanaryStagePromotion', ttl_seconds=60.0)` — 字符串對齊 `LeaseScope::as_audit_str()`，TTL 60s strict per AMD §4.5。這保「最小影響」+ 不破隔壁 E1 sprint。**規律**：跨 wave / 跨 agent IMPL 時，downstream 用 upstream API 採「最小調用面」原則（既有 generic facade 字符串接口 > 新 typed enum 簽名）— 即使 typed enum 已存在；除非 upstream 明示 deprecate string facade。

### SHADOW_BYPASS sentinel 拒寫 audit row 是 invariant 防線
governance_hub.acquire_lease 在 `_shadow_mode_provider() == True` 時走 PA push back #2 short-circuit，回 `SHADOW_BYPASS:<intent_id>` sentinel。canary_stage_log 的 `decision_lease_id` 是 PG `UUID` type + `manual_promote` rows NOT NULL（V080 CHECK constraint）。SHADOW_BYPASS 字符串是合法 lease_id 字面值但**不是合法 UUID**，又**不是真授權鏈**（per AMD §4.5）。**雙層防線**：(1) 路由層 `_is_shadow_bypass_lease()` 顯式判斷拒 409；(2) `_write_canary_stage_log_manual_promote()` 內 `uuid.UUID(decision_lease_id)` 校驗 fail-closed 回 None。應用層 + DB 層雙鎖避免 SHADOW_BYPASS 進 audit chain。**規律**：sentinel value 不能進 audit DB（即使應用層忘 filter，PG type / CHECK 必擋）；雙鎖比單鎖好過 audit-replay correctness 邊界。

### typed-confirm phrase 'PROMOTE' + window.prompt reason 雙模式分工
governance critical 寫操作（per W-AUDIT-7c lessons）必走 `openTypedConfirmModal` typed-confirm；但 reason 不是 critical phrase（可任意字串），用 native window.prompt 可 — 對齊 settings tab restart modal 的 simple-step pattern。**分工**：phrase = 'PROMOTE' 走 typed-confirm 防誤觸；reason 走 native prompt 收上下文（用於 audit log 補充）。**規律**：UX 摩擦設計 = critical decision 走高摩擦（typed-confirm + actor/impact/rollback metadata）；audit context 走低摩擦（prompt or simple input）— 不必為了 audit 完整性把每個欄位都升級為 typed-confirm（會疲勞使 operator 簡化 input → 治理失效）。

### caller try/catch 包 await openTypedConfirmModal（W-AUDIT-7c Round 3 lesson 內化）
本檔 _onPromoteClick 直接學 W-AUDIT-7c Round 3：`let proceed; try { proceed = await openTypedConfirmModal(...); } catch (err) { ocToast warn; return; }`。三態完整收口：(a) reject (singleton/unexpected) → toast warn + return (b) resolve(false) cancel → toast neutral + return (c) resolve(true) proceed → 業務。新代碼從一開始就帶這個 pattern，避免 Round 3 retrofit 工。**規律**：lesson learned 應內化到下一個 IMPL 的 baseline；不應重犯一次再修一次（Round 3 fix 同 lesson 在新代碼可零成本套用）。

### data-* attributes + addEventListener 取代 onclick="fn(...)" 字面注入
inline `<button onclick="fn('${cohort_id}', ...)">` 在 cohort_id 含 quote / backslash 時會 break HTML parsing 或 XSS 注入。改用 `<button data-cohort-id="${ocEsc(cohort_id)}" ...>` + JS 端 `btn.addEventListener('click', ev => { const id = ev.currentTarget.dataset.cohortId; ... })`。**規律**：dynamic 字串進 attribute 必過 ocEsc + addEventListener > onclick=；onclick= 只適合純靜態無 user input 字面值。inline `<button onclick="canaryRefresh()">` OK；inline `<button onclick="canaryPromote('${id}')">` 必拒。

### 5-stage 視覺合約：grid 5-col + 行動版 wrap 為 2 col
desktop 1366x768 / 1920x1080 都 5 欄並排清晰；行動版 < 700px 5 欄太擠（11px font 仍不夠），page-scoped `@media (max-width: 700px)` 改 grid-template-columns 為 2 欄 wrap（per 之前 SEV-2 #1 retrofit 同 pattern）。Stage 0 / 1-3 / 4 三色變體（neutral / blue active / red warn）對齊 governance 顏色語義（red = LIVE_PENDING 必慎，blue = 觀察期中，gray = shadow）。**規律**：N-stage ladder 顯示在 desktop 用 grid 平鋪；mobile 必 wrap，wrap 條件 = card 最小寬 < `100vw / N`（5 stage 約 2-2.5 col 為臨界）。

### test fixture 用 lenient HTMLParser + py_compile + node --check 三層
Mac 端：`python3 -c "html.parser"` lenient 跑 stack residue + py_compile + node --check 三套（node 可能未裝；條件跳過）。Linux 端 ssh bridge 跑真 pytest（後端 25 case + GUI static 12 case 共 37 PASS）+ sibling 13 case regression（governance_routes_auth + W-AUDIT-7c）共 60 PASS。**規律**：Mac 開發只能驗 syntax + structural；Linux 必 ssh 跑 import-time + runtime business logic。後端 unit test 用 patch.object(GOV_HUB, ...) mock 即可，不需開 FastAPI app（避免 db_pool / IPC singleton 撞 Mac import-time side effect）。

### XSS 防護 fixture：innerHTML 賦值點向前 1500 char 找 ocEsc
原本想法：每個 `innerHTML =` 點向後 200 char 視窗找 ocEsc（看 RHS 是 placeholder string literal 直接通過）。實測失敗：`el.innerHTML = html;` 是 already-built var，向後找不到 ocEsc 但 html var 是同 fn body 用 ocEsc 拼出來的。改向前 1500 char 視窗（同 fn body）找 ocEsc 或 placeholder pattern。**規律**：fixture 對 `innerHTML = var` pattern 必查同 function body upstream 證據；單看 RHS 200 char 是字面字串賦值才有效；變數賦值要 trace var 來源。

### 後端 25 case + GUI 12 case + sibling 13 case = 60 PASS
後端覆蓋：payload validation 跳階 / Stage 4 / 反向 / 相鄰；SHADOW_BYPASS sentinel 4 case；DB write UUID + DB unavailable 3 case；query active cohorts / metric registry pg_unavailable 3 case；POST handler full flow 7 case（acquire fail / shadow / non-operator / skip / happy / db fail / hub unavailable）；constants 3 case。GUI 覆蓋：HTML structure / JS balance / node check / DOM IDs / function exposure / CSS / XSS / lease constants / main.py registration / a11y / typed-confirm phrase / no-native-confirm 12 case。**規律**：新 endpoint 配套 fixture 必涵蓋：(1) 路由 sad path 覆蓋 (2) DB layer fail-soft (3) auth gate (4) constants invariant (5) GUI structural / a11y / XSS / lesson learned grep — 五層全跑齊才能在 sign-off 階段守住「無 silent runtime regression」。

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

## WP-01 Wave 1 GUI Safety follow-up（2026-05-16，5 gap closure）

### 雙層 modal 拆除 = button onclick + handler 整體重構，光改 1 處不夠
WP-01 主修在 `doLiveStop()` / `doEmergencyStop()` / `doLiveCloseAll()` 內加 typed-phrase modal，但**忘刪舊三個 1-click dialog overlay**（L527-575） + 三個 `open*Dialog` wrapper + button onclick 還是指向 wrapper → 雙層 modal（1-click → typed-phrase）。光看 handler 改了會覺得完成；真的修需 (1) button onclick → 直呼 handler (2) dialog DOM block 刪 (3) wrapper helper 刪 (4) handler 內 closeDialog 呼叫刪 (5) **隱藏盲區 action-guard selector**（L905 `button[onclick="openCloseAllDialog()"]`）也得同步更新，否則 disabled-state 失效。**規律**：UI helper 重構必 grep 全 file 找所有引用，含 onclick string selector + class queries，不只看 main flow。

### Module-level modal lock 共用 = 3 個 SDK 同一 flag
原 A3-HIGH-3 是 DOM-state guard `overlay.classList.contains('show')`，微 task race window 存在；改 module-level `_OC_MODAL_OPEN_LOCK` 必須**3 個 modal SDK 共用同一 flag**（不是 per-modal lock），否則 typed-confirm 開啟時 prompt-modal 仍能開 → onclick handler 互相覆蓋。close()/cleanup() 必清 lock 否則永久 deadlock（含 reject 路徑！）。**規律**：multi-helper concurrent guard 設計，共享 lock 是 trade-off：(a) 共享 = 嚴格序列化，UX 弱（user 不能 stack modal）但 race-safe (b) per-helper = 寬鬆 UX 但需處理 modal 互相覆蓋。共用較安全，配合 try/catch caller pattern。

### openPromptModal SDK 增強取代 ad-hoc overlay = 共享基礎設施投資
canary-tab.js manual_promote 自製 `oc-promote-reason` overlay（自製 textarea + counter + Esc handler）是第 5 個 ad-hoc modal pattern；改用 SDK 需先**增強 SDK 支援 placeholder + maxlength + char-counter**（+10 LOC SDK），然後 caller 變 -27 LOC（自製 overlay → SDK 呼叫）。淨節省 -13 LOC + 統一 UX + 取代 5 個 ad-hoc → 3 個 shared SDK + 1 module lock。**規律**：發現 ad-hoc 重複實作時，先升 SDK 再 migrate caller，不要直接複製。SDK 增強 option 必設 default value 不破既有 caller。

### 繁簡 replace_all 安全前提 = grep JS string 比對零命中
tab-live.html 18 處 `实盘` + tab-demo.html 6 處 `平仓` 全 replace_all，前提是 `grep -nE "=== ['\"]实盘['\"]|== ['\"]实盘['\"]"` 零命中。若有 `if (mode === '实盘')` 之類 logic 比對，replace_all 立刻爆。**規律**：繁簡統一前必跑 JS string equality grep；只動 user-facing text vs class name / data-attribute / JS string literal 是兩層判斷，混 = 邏輯破。

### HTML inline-JS node --check = python regex extract → temp file → node
HTML 不能直接 node --check；用 `re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)` + `'\n;\n'.join(scripts)` 後寫 tempfile node --check。覆蓋率約 95%（漏 onclick="..." inline expression），但 catch 大多數 syntax 錯。**規律**：HTML inline-JS sign-off 必跑 extract + node --check（per `feedback_gui_node_check_sop.md`）；標準 .js 額外做 brace-balance 仍是盲區（W-AUDIT-7c lexical scope shadow），需 A3+E2 對抗性 review 補。

### LOC delta net=0 ≠ governance free pass
本次 -50 (tab-live) -13 (canary) +63 (common) = net 0，但 common.js 2135 → 2198 觸發 §九 governance：pre-existing baseline 已超 2000 硬上限，exception clause 允許「baseline + 5 LOC」寬容，**+63 超寬容**。需 PM Sign-off 明文記錄 exception 理由（SDK consolidation > 多 ad-hoc）+ 同時開 P2 ticket 處理 common.js 拆檔。**規律**：governance LOC 不看 net delta 看 per-file；SDK 增強雖然抵消多檔成本，per-file 仍要 PM exception 簽。

## v80 cold audit Wave 1 PkgA — A3 condition-clear（殘留風險常駐橫幅）(2026-05-29)

### 殘留風險警示禁用 3.5s auto-dismiss toast → 常駐橫幅（dismiss-on-click）
A3 HIGH：不可逆 live 寫操作（doLiveStop / doEmergencyStop / doLiveCloseAll / switchSystemMode / liveStart）部分失敗時，「倉位/掛單可能殘留，請手動確認 Bybit」若用 `ocToast(..., 'error')`（3.5s 自動消失）呈現，受壓操作員會錯過，然後 refreshPage() 重繪畫面顯「一切就緒」掩蓋殘留。解法 = common.js 新 helper `ocResidualRiskBanner(actionKey, msg)`：fixed 置頂常駐橫幅，只能點「我已確認 · 關閉」按鈕關閉。**規律**：殘留風險/不可逆失敗的警示必須是 persistent dismiss-on-click，不能是定時消失的 toast；toast 只配「成功/一般資訊/可重試錯誤」。

### 常駐橫幅必 append 到 document.body 才能 survive refreshPage / loadAll 重繪
refreshPage()（tab-live）與 setTimeout(loadAll)（tab-system）只重繪特定容器 ID 的內容；橫幅 append 到 `document.body` 而非任何被重繪的容器 → 重繪不會清掉它。同 actionKey 重複呼叫時 `_ocResidualBanners[key]` 更新文字而非堆疊，避免連點產生多條殘留橫幅；多 actionKey 則垂直堆疊置頂。**規律**：要 survive 局部重繪的 UI 元素必掛在重繪範圍之外（body 直屬），並用 key-dedupe map 防連點堆疊（同 Agent Tracker 90d banner、F5 trust-status-bar 雙 ID 教訓一脈）。

### liveStart fake-success：`if (d)` 顯「已啟動」是 pre-fix 反模式
liveStart 舊碼 `if (d) ocToast('已啟動','warn')` 完全沒讀 P1-02 後端回的 partial_failure / rust_synced:false → live gate 未滿足仍顯善意「已啟動」。修法同 doLiveStop：先 `classifyLiveMutation(d)`，residual 時常駐橫幅「啟動未確認 — 引擎未授權」。**規律**：所有 live 寫操作 caller 一律走 classifyLiveMutation，禁 `if (d)` 直接報成功；新增 live 寫操作時 grep `if (d)` 確認沒漏網。

### 'warn' toast type 缺 CSS class → 退回無樣式（透明背景無邊框）
common.js toast 只有 info/success/error 三 class；多處 `ocToast(..., 'warn')`（liveStart / P1-05 manual-mark）渲染成 `oc-toast-warn` 但無對應 CSS rule → 透明無邊框幾乎看不見。補 `.oc-toast-warn` = `--yellow` (#d29922) rgba 背景 + 邊框，與綠/紅/灰區分。**規律**：新增 toast type 字串時必同步加對應 `.oc-toast-<type>` CSS；grep `ocToast(.*'<type>')` 確認所有用到的 type 都有 class。

## 告警通知卡片（Telegram + Webhook）對 LOCKED 後端契約（2026-06-05）

### partial-safe secret 欄位：空=不變 / "__CLEAR__"=清除，用「clear 標記」而非把 sentinel 塞進 input
後端契約 `POST /api/v1/settings/alerts` 對 token/secret 採三態：送輸入值=更新、送 ""=不變、送 "__CLEAR__"=移除。前端不能用 input.value 直接承載 sentinel（password input 應保持空 + 遮罩看不出狀態 + 操作員可能誤把 "__CLEAR__" 當成真 token）。解法 = module-level `_ocAlertClearMarks = {field: bool}` 標記哪些欄位按過「清除」，提交時 helper `_alertSensitiveValue(inputId, clearKey)`：有輸入→輸入值；無輸入但標記清除→sentinel；都沒有→""。任何重新輸入自然覆蓋（先檢查 typed）。每次 renderAlertConfig 重置標記（剛取得最新 server 狀態）。**規律**：partial-safe 「空=不變」語義的敏感欄位，sentinel 走獨立旁路狀態（clear 標記 + 顯式按鈕），不混進 input.value；提交計算「輸入優先 > clear 標記 > 不變」三態。

### masked-render：password 欄位永遠空 + placeholder 帶 *_configured 遮罩 hint，明文欄位才預填
對齊 doSaveApiKey/loadApiKeyStatus pattern。後端永不回明文（只回 `bot_token_configured` + `bot_token_hint` 如 "••••1234"）。渲染：chat_id / urls 是明文 → 直接 `.value=` 預填；bot_token / secret 是敏感 → `.value=''` 永遠空，`.placeholder=` 反映狀態（configured 顯 `已設定 ••••1234，留空不變`，否則 `未設定`）。提交後（不論成功失敗）立即 `.value=''` 清 DOM 敏感欄位 + 重置 clear 標記，成功則用回應（GET 同 shape + saved:true）直接 renderAlertConfig 顯新遮罩。**規律**：敏感欄位 GUI 三條鐵律 = (1) value 永遠空、狀態走 placeholder/hint (2) 提交後立即清 DOM（即使失敗，避免明文殘留） (3) 成功後 re-render 顯後端回的新遮罩，不本地猜。

### placeholder/.textContent 屬性賦值是 XSS-safe，innerHTML 才需 ocEsc
本卡片把後端 hint 放進 `input.placeholder = '已設定 ' + hint + ...`（DOM 屬性賦值，text-only 不解析 HTML）→ 不需 ocEsc 也安全；但 note 區用 `el.textContent` 同樣安全。只有 status 行用 `innerHTML` 顯後端 error 時才必 `ocEsc(errMsg)`。toast 走 `.textContent`（common.js ocToast 內部）天然安全。**規律**：server value 進 `.placeholder` / `.textContent` / `.value` 屬性賦值天然 XSS-safe（不需 ocEsc）；只有 `innerHTML` / `insertAdjacentHTML` 拼字串才必 ocEsc。但寧可一致用 ocEsc 包（本卡片 innerHTML error 路徑都包了）。

### 卡片內無 fixed-position modal → 不受 sub-tab [hidden] 影響（W-AUDIT-7c 教訓的反向適用）
W-AUDIT-7c 教訓：sub-tab 內含 fixed/absolute modal overlay 時，sub-tab `[hidden]` 會連帶 `display:none` 整顆 subtree 害 modal 不渲染，故 modal 須抽到 sub-tab 外。本告警卡片是純 `oc-card`（checkbox / input / textarea / button，無 modal overlay），放在 `#subtab-connection` 內完全 OK — sub-tab 切走時整卡 hide 是預期行為（卡片不需在 hidden 時可見）。**規律**：判斷元件能否留在 sub-tab 內 = 看它有沒有 fixed/absolute 後代需在 sub-tab hidden 時仍渲染；純表單卡片可留，fixed modal/overlay 必抽出。

### HTML inline-JS 驗證 = python regex 抽 <script>（排除 src=）→ node --check tempfile
Mac 端 sign-off：`re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', html, re.DOTALL)` 抽所有非外部 inline script，`\n;\n` join 寫 tempfile，`node --check`。本任務 2 個 inline block、40741 chars、node v26 exit 0。額外用 node 跑純邏輯 mock 驗 partial-safe 三態 + masked placeholder + urls split/filter 11/11 PASS（無 jsdom 也能驗 contract 語義）。**規律**：per feedback_gui_node_check_sop，inline-JS 必 extract + node --check（brace count 是盲區）；contract 語義可抽純函數在 node mock 驗，不必開瀏覽器。runtime 渲染/a11y 仍留 E4 Linux。
