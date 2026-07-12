# 11 · Governance view 遷移規格(iframe → 原生玄衡 view)

> PA-design-writer(2026-07-12)。承 design/10 recipe + view-risk.js pattern 正本。
> **靶**:`governance`(§0.1 交易關鍵四者之一,定序最後遷)。**手法**:共享 IIFE 復用(fetch DOM + fetch 各 JS text → 串接單一 IIFE 重跑),鏡像 view-risk.js。
> **產出物**:`view-governance.js`(thin wrapper,類比 view-risk.js)+ `view-governance.css`。`tab-governance.html / governance-tab.js / canary-tab.js / autonomy-posture.js / governance.js` **零修改**(reuse 正本 + rollback 錨)。
> **驗收**:交易關鍵 → E2 + E3 雙審 + operator Linux 批驗才 cutover。Mac 靜態只證 source 事實。
>
> ⚠ **本遷比 risk 多三個 pattern 正本未覆蓋的新風險**,全部在 §A / §3 / §4 / §9 給出處置;E1a 必須逐項照做,不得直接複製 view-risk.js。三新風險摘要:
> - **(N1)** 四路 script 併入同一 IIFE(inline 塊 + autonomy-posture.js + governance-tab.js + canary-tab.js),非 risk 的「inline + 單一 tab.js」二路。
> - **(N2)** `onclick="loadAll()"`(html:407)硬編於不可改的 HTML → 與 paper 的 `window.loadAll` 衝突;risk 因 loadAll 不在 on* 集而迴避,governance **無法迴避** → 必須用「clone 節點 onclick 重綁 + __ocGovLoadAll」處置(§3.B / §9)。
> - **(N3)** risk 的 `discoverOnHandlerNames`(只取 on* 屬性**首個** token)在 governance 會 ① 誤取保留字 `if`(html:937)→ 生成 `window["if"]=if` **解析錯誤 → 整段 IIFE 死**(設計 blocker);② 漏掉 `loadAuditTrail`(html:1091 `event.stopPropagation();loadAuditTrail()` 的非首 token)+ 漏掉 JS 模板注入的 `auditApprove/auditReject/confirmApproveRecovery`。**必須換用強化版 handler 發現**(§3.A)。

---

## 0 · 事實核實結論(相對 brief)

| brief 敘述 | 源碼實測 | 依據 |
|---|---|---|
| tab-governance.html 9 個 `<script src>` | ✅ 正確:common-formatters / common-mode-badge / common-modals / fetch_with_csrf / common.js / **governance.js** / **canary-tab.js**(`defer`) / …末尾 **autonomy-posture.js** / **governance-tab.js** | html:11-19, 1718-1719 |
| inline `<script>`:378 skip + 1250 真塊 | ✅ 正確。378=`ocAuthCheck();ocInjectBaseCSS();`(skip)。1250-1716=Live Auth 大內聯塊(**併入 IIFE**) | html:378, 1250-1716 |
| `<style>` 塊 2 個(20-375 + 1230-1247) | ✅ 正確 → view-governance.css | html:20-375, 1230-1247 |
| governance-tab.js 頂層 `loadAll`(:1796)撞 window.loadAll | ✅ 正確。**且 html:407 `onclick="loadAll()"` 直接呼之** → 比 risk 更嚴(risk 的 loadAll 不在 on* 集) | gov-tab:1796, html:407 |
| 三 JS 可能互引對方頂層符號 | ✅ 部分:governance-tab.js `loadAll` 呼 `loadAutonomyPosture`(autonomy-posture.js);inline 塊 `updateQuickStatus` 被 governance-tab.js 以 `window.updateQuickStatus` 讀;autonomy-posture.js 呼 governance.js 全域 `govGetAutonomyLevelState / govSwitchAutonomyLevel`。canary-tab.js **自成 IIFE**,不與他者共享詞法(只經 window.loadCanaryCohorts) | gov-tab:1855;html:1278,72,560;autonomy:163,225;canary:37,446 |
| 「6 寫(含 risk-escalate/auth-freeze)」 | ⚠ **undercount**:實測活躍寫 **12 個 endpoint**(見 §5)。「auth-freeze」**無對應 GUI 寫**(freeze 是後端 SM 轉移,GUI 無 freeze 端點)。另有 2 個 defined-but-unwired(govPostHealthCheck / govDismissAllAudit,零 caller) | §5 |

---

## A · script 併入清單、串接序、skip(item 1)

### A.1 fetch 併入共享 IIFE(4 路 text,串接序固定)

render 時**併發 fetch** 5 個資源(1 HTML + 3 JS text;canary-tab.js 亦 fetch text),依下列**串接序**組單一 combined text,再包單一外層 IIFE 重跑:

| 序 | 來源 | 取得方式 | 原頁載入序依據 |
|---|---|---|---|
| 1 | tab-governance.html 的 **inline 塊**(html:1250-1716) | fetch html → DOMParser → 收集非-src、非-ocInjectBaseCSS 的 inline `<script>` text | inline `<script>` 在 body 中隨解析同步執行,早於 autonomy/gov-tab |
| 2 | **autonomy-posture.js** text | fetch `/static/autonomy-posture.js` | html:1718(gov-tab 之前) |
| 3 | **governance-tab.js** text | fetch `/static/governance-tab.js` | html:1719 |
| 4 | **canary-tab.js** text | fetch `/static/canary-tab.js` | html:19 `defer` → 實際在 parse 完後、DCL 前執行(最後);canary 自成 IIFE,置末即可 |

**串接**:`combined = [inline, autonomy, govtab, canary].join('\n;\n')`(`;` 分隔防 ASI)。外層再 `(function(){ 'use strict'; <combined>; <re-export>; <expose __ocGovLoadAll>; })();`。

**為何序 2 早於序 3(TDZ 硬約束)**:governance-tab.js 尾端 self-init `loadAll()` 會呼 `loadAutonomyPosture()`,後者讀 autonomy-posture.js 的頂層 `const AUTONOMY_*`。函式宣告雖 hoist,但 `const/let` 有 TDZ——若 autonomy text 排在 gov-tab 的 self-init **之後**,`loadAll()→loadAutonomyPosture()` 執行當下 `AUTONOMY_*` 未初始化 → ReferenceError。故 **autonomy 必在 gov-tab 之前**(= 原頁序)。inline 塊置首(其 self-init 只呼自身段內函式/常數,安全)。

### A.2 skip(不併入)

| 資源 | 處置 | 理由 |
|---|---|---|
| common-formatters / common-mode-badge / common-modals / fetch_with_csrf / common.js | skip(殼已載) | 外部 `<script src>`,shell boot 已載入 |
| **governance.js**(html:16) | **skip 併入,保持殼載** | 殼已載(overview/risk 遷移時已進殼);提供 `govGetStatus / govGet*/ govPost* / gov*Badge / GOV_*` 等全域,autonomy-posture.js + governance-tab.js 於 IIFE 內以**上層作用域**引用(free var → 解析到 global)。**不可併入**(併入會令其全域被 IIFE 圍住,gov-tab/autonomy 就找不到——實測 gov-tab 用裸名 `govGetStatus()` 依賴其為全域) |
| 首個 inline `<script>`(html:378 `ocAuthCheck();ocInjectBaseCSS();`) | skip | 殼 boot 已 ocAuthCheck;`ocInjectBaseCSS` 注 `body{padding}`+`*` reset **破殼 chrome**,禁呼(同 risk/paper) |
| 兩 `<style>` 塊(20-375 / 1230-1247) | skip(不進 IIFE) | → view-governance.css,`.governance-view` scope 供給(§8) |

### A.3 各段 self-init / DOMContentLoaded / setInterval 行為(重跑當下)

| 段 | 尾端自初始化 | 重跑當下行為 |
|---|---|---|
| inline 塊 | `govLoadLiveAuthStatus({force:true})`(html:1714)+ `startGovLiveAuthLoop()`(1715);另註冊 `window.addEventListener('message',…)`(1677)+ `document.addEventListener('visibilitychange',…)`(1704) | append 同步執行:首拉 live-auth 狀態 + 啟 **30s `_govLiveAuthTimer` setInterval**(§9 第二輪詢)。兩監聽器註冊一次(built guard 防重跑) |
| autonomy-posture.js | **無**(純定義,`loadAutonomyPosture` 由 gov-tab `loadAll` 呼) | 只定義函式/常數,不主動跑 |
| governance-tab.js | `loadAll()`(gov-tab:1865)+ `ocStartRefresh(loadAll,10000)`(1866)+ 5 modal 背景點擊關閉 listener(1869-1877) | append 同步:首拉全頁 + 啟 **10s 主輪詢**(common.js 全域單例 `_ocRefreshTimer`,同 risk) |
| canary-tab.js | `if(readyState==='loading'){DCL…}else{ if(_el('canary-stage-ladder')) loadCanaryCohorts() }`(canary:455-467) | 殼內 `readyState==='complete'` → **else 分支** → 元素已注入 → 直接 `loadCanaryCohorts()`。**故不需 DCL-capture hack**(見下) |

**★ 關鍵:governance 不需 view-paper.js 的 `document.addEventListener` DCL-capture 劫持。** 唯一含 `DOMContentLoaded` 的是 canary-tab.js,且其 else 分支已處理「DCL 已過」的殼情境;其餘三段皆 eval-time 直接 self-init。E1a 用 view-risk.js 的直接 append 重跑即可,勿引入 paper 的 DCL 捕獲。

---

## 2 · 頂層宣告名總表 + IIFE 隔離論證(item 2)

**canary-tab.js 已自成 IIFE**(`(function(){ 'use strict'; … })();`,canary:37/468)→ 其頂層 `const CANARY_PROMOTE_PHRASE / STAGE_*` 等**本就 IIFE-local**,**零**貢獻外層/全域詞法。以下只列會進外層 IIFE 頂層的三段(inline / autonomy / gov-tab):

**inline 塊**(html:1250-1716)
- `let`:`_govLiveAuthVisible, _govLiveAuthTimer, _govLiveAuthInFlight, _govLiveAuthRefreshPending, _govLastLiveAuthStatus, _govLastLiveAuthHalt`
- `const`:`GOV_TRUST_TIER_LABELS, GOV_TRUST_TIER_COLORS, GOV_LIVE_AUTH_REFRESH_MS`
- `function`:`toggleDL, toggleRecon, updateQuickStatus, _govLiveAuthRefreshVisible, _govSignedAuthDisplayState, _govLiveAuthHaltText, _govApplyRenewHint, govLoadLiveAuthStatus, govRenewLiveAuth, govRenewReview, startGovLiveAuthLoop, stopGovLiveAuthLoop`

**autonomy-posture.js**
- `let`:`_currentAutonomyState`
- `const`:`AUTONOMY_LEVEL_LABELS, AUTONOMY_GATE_LABELS, AUTONOMY_ESCALATION_LABELS, AUTONOMY_NOTIF_LABELS`
- `function`:`autonomyPlainLabel, autonomyPlainWithRaw, autonomySetNotifChannel, autonomyChipForLevel, autonomyFmtTime, autonomyRenderEligibility, autonomyRenderMatrix, autonomyRenderPosture, loadAutonomyPosture, autonomyOpenSwitchModal`

**governance-tab.js**
- `let`:`_currentStatus, _currentAuthState, **_currentRiskLevel**, _currentLeaseActive, _lastPendingRecovery, _lastPendingAudit, _govEventLog, _prevStatus`
- `const`:`MAX_EVENTS, _CHANGE_TYPE_LABELS, _APPROVAL_STATUS_CN, _AUTH_STATE_CN, _RISK_LEVEL_CN, _OMS_STATE_CN, _LEASE_STATE_CN, _COMP_CN, _WHAT_RULES`
- `function`(節選關鍵):`updateOmsCard, updateDemoProbeAdmissionCard, toggleAuthScope, toggleIncidentLog, toggleAuditTrail, togglePendingApprovals, toggleLeaseList, togglePLGCriteria, toggleEventsFeed, detectChanges, renderIncidentLog, renderAuditTrail, loadAuditTrail, showRequestAuthModal, hideRequestAuthModal, submitRequestAuth, showApprovalModal, hideApprovalModal, showOverrideModal, hideOverrideModal, showReconcileModal, hideReconcileModal, submitApproval, submitOverride, submitReconcile, renderAuthScope, loadAuthScope, renderAuthCard, renderRiskCard, renderLeaseList, renderLeaseCard, renderReconCard, renderSummary, loadPaperLiveGate, evaluatePaperLiveGate, loadLearningTier, showPromoteModal, hidePromoteModal, submitPromotion, loadEventsFeed, showUnavailable, renderPendingRecovery, renderPendingAudit, auditApprove, auditReject, bulkAudit, loadPendingApprovals, confirmApproveRecovery, **loadAll**`

**撞已遷頂層名者(若 raw 重跑會 SyntaxError / 破 paper)**:
- `loadAll`——撞 **paper 的 `window.loadAll`**(paper raw 全域)+ 撞 risk/overview/settings 各自 IIFE 內的 `loadAll`(它們 IIFE-local,互不干涉)。
- `_currentRiskLevel`——撞 **risk-tab.js 頂層 `let _currentRiskLevel`**(view-risk.js MODULE_NOTE 列出)。

**隔離論證**:外層 IIFE-wrap 後,上述**全部**頂層 `const/let/class/function` 成 **IIFE-local**,不進 global lexical → ① 不與 paper 的 raw 全域(loadAll 等)在 global lexical 重宣告(paper 是 raw,governance 是 IIFE,兩者只可能在 `window.*` 層相撞,非詞法層——見 §3.B);② 不與 risk/overview/settings 各自 IIFE 的頂層重宣告(彼此 isolated)。**過 R71 跨-view 詞法 guard,governance 判 isolated,貢獻空集**。canary 段亦 isolated(自 IIFE)。**結論:R71 貢獻空集,與 view-risk.js 同。**

---

## 3 · onclick/on* handler 集 + 交集比對 + handler 發現強化(item 3)

### 3.A 強化版 handler 發現(必須,取代 view-risk.js 的 `discoverOnHandlerNames`)

**問題**:view-risk.js 的 `discoverOnHandlerNames` regex `on[a-z]+\s*=\s*["']\s*([A-Za-z_$][\w$]*)\s*\(` 只捕**屬性值首個** token,在 governance 會:
- **(blocker)** html:937 `onclick="if (typeof loadCanaryCohorts === 'function') loadCanaryCohorts();"` → 捕到保留字 **`if`** → re-export 生成 `try{window["if"]=if;}catch(_e){}`。`=if` 是**解析錯誤**(keyword 作表達式);try/catch 擋不住 parse error → **整段 IIFE 不執行 → governance view 靜默全死**。
- **(miss)** html:1091 `onclick="event.stopPropagation();loadAuditTrail()"` → 捕到 `event`(非首 token 的 `loadAuditTrail` 被漏)→ `loadAuditTrail`(IIFE-local)未 re-export → 審計軌跡刷新鈕 onclick ReferenceError。
- **(miss)** JS 模板注入的 on*:`auditApprove / auditReject`(gov-tab:1521/1523)、`confirmApproveRecovery`(gov-tab:1090)——這些在 governance-tab.js **模板字串**內,不在 tab-governance.html,view-risk.js 只掃 html 會全漏。

**處置(E1a 實作)**——`view-governance.js` 用強化發現:
1. **掃描範圍** = `htmlText`(tab-governance.html) **∪** `combined`(4 段串接 script text)。後者含 JS 模板字串裡的 `onclick="…"` → 捕到 auditApprove/auditReject/confirmApproveRecovery。
2. **抓每個 on* 屬性值內所有** `(^|[^.\w$])([A-Za-z_$][\w$]*)\s*\(` 的 identifier(非只首 token;`(^|[^.\w$])` 前置排除 member 存取如 `.stopPropagation`)。→ 從 html:1091 得 `loadAuditTrail`;從 html:937 得 `loadCanaryCohorts`(+ `if`,下步濾掉)。
3. **交集** `topLevelDeclaredFnNames(combined)`(擴充 view-risk.js 的 `topLevelDeclaredNames` 使其亦捕頂層 `function` 宣告名,非只 let/const/var)。→ 自然濾掉 `if`(非頂層函式)、`event`/`stopPropagation`(非頂層函式)、`loadCanaryCohorts`(非 gov 頂層——它是 canary window 匯出,html:937 已自帶 `typeof …==='function'` 守衛且 canary 自曝 window,gov **不需** re-export)。**同時避開 `window["if"]=if` blocker**。
4. **顯式排除 `loadAll`**(§3.B 另行處置,不寫 window.loadAll)。

> 產物 = 需 re-export 至 window 的 gov 頂層函式集(下 §3.B 清單)。此為 governance **相對 view-risk.js 的第一個必改點**。

### 3.B governance 完整 on* handler 集(超集)

**靜態 tab-governance.html on***(行號):loadAll(407,**排除**)、toggleAuthScope(439)、showRequestAuthModal(461)、showApprovalModal(465)、toggleDL(472)、toggleLeaseList(508)、showOverrideModal(589)、toggleRecon(648)、showReconcileModal(678)、govRenewLiveAuth(710)、govRenewReview(713)、govLoadLiveAuthStatus(716)、autonomyOpenSwitchModal(782)、evaluatePaperLiveGate(865)、togglePLGCriteria(871)、showPromoteModal(913)、`if`+loadCanaryCohorts(937,見 §3.A)、togglePendingApprovals(999)、bulkAudit(1017/1018)、toggleEventsFeed(1030)、loadEventsFeed(1039)、toggleIncidentLog(1075)、toggleAuditTrail(1088)、`event`+loadAuditTrail(1091)、hideRequestAuthModal(1138)、submitRequestAuth(1139)、hideApprovalModal(1154)、submitApproval(1155)、hideOverrideModal(1179)、submitOverride(1180)、hideReconcileModal(1195)、submitReconcile(1196)、hidePromoteModal(1223)、submitPromotion(1224)

**JS 模板注入 on***:confirmApproveRecovery(gov-tab:1090)、auditApprove(gov-tab:1521)、auditReject(gov-tab:1523)

**re-export 目標集(交集頂層函式後、去 loadAll/保留字)= 35 名**:
`toggleAuthScope, showRequestAuthModal, showApprovalModal, toggleDL, toggleLeaseList, showOverrideModal, toggleRecon, showReconcileModal, govRenewLiveAuth, govRenewReview, govLoadLiveAuthStatus, autonomyOpenSwitchModal, evaluatePaperLiveGate, togglePLGCriteria, showPromoteModal, togglePendingApprovals, bulkAudit, toggleEventsFeed, loadEventsFeed, toggleIncidentLog, toggleAuditTrail, loadAuditTrail, hideRequestAuthModal, submitRequestAuth, hideApprovalModal, submitApproval, hideOverrideModal, submitOverride, hideReconcileModal, submitReconcile, hidePromoteModal, submitPromotion, confirmApproveRecovery, auditApprove, auditReject`
（另:`updateQuickStatus` 由 inline 塊 html:1278 **顯式** `window.updateQuickStatus=…` 自曝,不靠 re-export;`loadCanaryCohorts` 由 canary IIFE canary:446 自曝 window——皆不需 gov re-export。）

### 3.C 逐一與 paper/settings/overview/risk onclick 集交集比對(re-export 安全硬前提)

| 已遷 view onclick 集 | 與 gov 35 名交集 |
|---|---|
| paper(sessionAction, closePosition, …;`loadAll`=raw 全域) | **∅**(gov 名皆 toggle*/show*/hide*/submit*/audit*/gov*/autonomy* 專屬;`loadAll` 已排除不 re-export) |
| settings(demoAction, configAction, …) | **∅** |
| overview(confirmAction, confirmMode, …) | **∅**(gov 的 confirmApproveRecovery ≠ confirmAction/confirmMode) |
| risk(switchRiskTab, submitRiskOverride, selectRiskEngine, confirmLiveEngineRiskSave, saveStopSettings, savePositionSettings, saveCooldownSettings, saveH0ShadowMode, toggleDynamicRisk, toggleTPInputs, askAIStopLoss, applyAIAdvice, showRiskOverrideModal, closeRiskOverrideModal, resetCooldown, unhaltSession, saveAiBudget) | **∅**(gov `submitOverride`≠risk `submitRiskOverride`;gov `showOverrideModal`≠risk `showRiskOverrideModal`;gov `toggleDL/toggleRecon`≠risk `toggleDynamicRisk/toggleTPInputs`) |

**結論:re-export 交集 = ∅(唯一潛在交集 `loadAll` 已排除)→ 無 last-writer-win 破壞。**

### 3.B′ `loadAll` 衝突處置(N2,governance 相對 view-risk.js 的第二個必改點)

**問題**:html:407 `onclick="loadAll()"`(Quick Status 刷新鈕)硬編呼全域 `loadAll`。governance `loadAll` IIFE-wrap 後為 IIFE-local。若:
- **不** re-export loadAll → 該鈕呼到 **paper 的 `window.loadAll`**(或 undefined)→ 對 governance 為誤呼/no-op。
- **re-export** `window.loadAll=govLoadAll` → 覆蓋 paper 的 window.loadAll → paper.resume(view-paper.js:164 讀 `window.loadAll`)後續會呼 governance 的 loadAll → **破 paper**。

**拒絕的替代(save/restore-on-pause)**:實測 shell.js `notifyViewVisibility`(shell.js:170-181)以 `VIEWS.forEach` 序 resume(active)/pause(others)。VIEWS 序中 `paper`(idx 1)< `governance`(idx 13)。**governance→paper 導覽時 `paper.resume()`(idx1)在 `governance.pause()`(idx13)之前執行** → 若靠 governance.pause 還原 window.loadAll,paper.resume 讀取時 window.loadAll 仍是 governance 的 → 仍破 paper。**故 save/restore-on-pause 不可靠,拒絕。**

**PRIMARY 處置(推薦)**:**clone 後 onclick 重綁 + __ocGovLoadAll**,governance **永不寫 `window.loadAll`**——
1. `loadAll` 排除於 re-export(§3.A 步 4)。
2. IIFE 尾曝 `window.__ocGovLoadAll = (typeof loadAll==='function'?loadAll:null)`(鏡像 view-risk.js `__ocRiskLoadAll`)。
3. 注入 DOM(byte-parity clone)後,view-governance.js 在**已 clone 進宿主的節點**上,把該唯一 `onclick="loadAll()"` 節點(Quick Status 刷新鈕)重綁:`el.setAttribute('onclick','__ocGovLoadAll()')`(僅此一處;`root.querySelectorAll('[onclick]')` 掃出 onclick 值 `=== 'loadAll()'` 者)。
   - 此為**執行期對 view 自有 clone DOM 的 seam 調整**,非改 tab-governance.html **檔**(rollback 錨完好)——與 view-paper.js 執行期劫持 `document.addEventListener`、view-risk.js F1 window↔IIFE-local proxy 同類手法。
4. 效果:paper 的 `window.loadAll` **從不被 governance 觸碰**(paper 恆安全),governance 刷新鈕呼自身 loadAll。維持 risk/overview/settings 的「不寫 window.loadAll」隔離不變式。

**FALLBACK(若 E2/E3 否決任何 clone-DOM 變更)**:不重綁,html:407 鈕呼環境 `window.loadAll`(paper 的/undefined)→ 該鈕降級為 no-op;governance 仍由內部 10s `ocStartRefresh(loadAll,…)` 自動刷新(loadAll 走 IIFE-local reference,不受影響)。**永不寫 window.loadAll → paper 恆安全**,代價僅該手動鈕失效。

> **OPEN-1(PM/E2/E3 裁)**:PRIMARY 的「clone 節點 onclick 重綁」是否可接受為 seam 調整,抑或採 FALLBACK 接受手動鈕降級。PA 傾向 PRIMARY(功能守恆 + paper 安全兼得)。

---

## 4 · F1-class 裸賦值風險(item 4)

掃 tab-governance.html 全部 on* 屬性值,尋「裸 `IDENT=…` ∩ 頂層宣告名」(risk `_liveRiskSavePendingCallback` 先例):
- 全部 on* 皆函式呼叫(`foo(...)`)或 member 呼叫(`event.stopPropagation();loadAuditTrail()`);html:937 的 `=== 'function'` 是**比較非賦值**(`onAttrBareAssignTargets` 的 `=\s*[^=]` 對 `===` 不中)。
- **無**任何 `IDENT=value` 裸賦值到頂層 binding。

**結論:F1 proxy 集 = ∅,governance 不需 window↔IIFE-local getter/setter proxy。** E1a 仍應保留 `onAttrBareAssignTargets ∩ topLevelDeclaredNames` 檢查作 born-safety(對 governance 產空集),但不會生成 proxy 碼。此比 risk 簡單(risk 有 1 個)。§3 confirm/cancel 語義不因缺 proxy 而弱化(governance 的 confirm 全走 openConfirmModal/openTypedConfirmModal/openPromptModal 的 async await,非 risk 那種 inline 裸賦值 pending callback)。

---

## 5 · 寫面完整清單(item 5,**12 活躍 endpoint**,brief 的「6」undercount)

全部寫**走既有 Rust authority IPC**,復用未改 JS text,零自建寫路徑。confirm 全 response-gated 非 fake。

| # | endpoint | method | 觸發函式(檔:行) | payload | confirm gate | gov-critical |
|---|---|---|---|---|---|---|
| 1 | `/api/v1/governance/auth/request` | POST | `submitRequestAuth`(gov-tab:361)→`govRequestAuthorization`(governance.js:64) | `{scope:{}, ttl_hours, reason}` | modal-request-auth 表單(reason 非空驗證) | 授權申請 |
| 2 | `/api/v1/governance/auth/approve` | POST | `submitApproval`(gov-tab:407)→`govPostApprove`(governance.js:58) | `{approval_note}` | modal-approve 表單(note 非空) | **auth 審批** |
| 3 | `/api/v1/governance/risk/override` | POST | `submitOverride`(gov-tab:424)→`govPostOverride`(governance.js:78) | `{target_level, reason}` | modal-override 表單(level+reason);**三態防 fake-success**(applied/pending/unconfirmed,gov-tab:442-456) | **risk 降級(SM-04 de-escalate)** |
| 4 | `/api/v1/governance/reconcile` | POST | `submitReconcile`(gov-tab:459)→`govPostReconcile`(governance.js:88) | `{reason}` | modal-reconcile 表單(reason 非空) | 對賬觸發 |
| 5 | `/api/v1/governance/learning-tier/promote` | POST | `submitPromotion`(gov-tab:964)→`govPromoteLearningTier`(governance.js:140) | `{target_tier, reason, approved_by:'operator'}` | modal-promote 表單;**三態防 fake**(promoted true/false/unconfirmed,gov-tab:983-996) | 學習層級晉升 |
| 6 | `/api/v1/governance/audit/approve/{change_id}` | POST | `auditApprove`(gov-tab:1534)→`govApproveAuditChange`(governance.js:164) | `{reason}`(選填) | openPromptModal(reason 選填) | 變更批准 |
| 7 | `/api/v1/governance/audit/reject/{change_id}` | POST | `auditReject`(gov-tab:1551)→`govRejectAuditChange`(governance.js:169) | `{reason}` | openPromptModal(reason **required**) | 變更拒絕 |
| 8 | `/api/v1/governance/audit/approve|reject/{change_id}`(逐筆迴圈) | POST | `bulkAudit`(gov-tab:1569) | 逐筆 `{reason}` | **openTypedConfirmModal phrase=`CONFIRM`**(gov-tab:1614)+ reject 另需 openPromptModal reason | **批量審批(critical-grade)** |
| 9 | `/api/v1/governance/recovery/{request_id}/approve` | POST | `confirmApproveRecovery`(gov-tab:1706)→`govApprovePendingRecovery`(governance.js:154) | `{}` | **openTypedConfirmModal phrase=`CONFIRM`**(gov-tab:1764,放寬風控邊界) | **recovery 批准(放寬 SM-04/Lease 邊界)** |
| 10 | `/api/v1/live/auth/renew` | POST | `govRenewLiveAuth`(inline html:1540) | `{accepted_tier, reason}` | halt 態先 openConfirmModal(html:1546)+ openPromptModal reason(1556)+ openPromptModal tier(1568) | **§3 Live 授權續期** |
| 11 | `/api/v1/live/auth/renew-review` | POST | `govRenewReview`(inline html:1610) | `{review_notes, confirmed_tier}` | openPromptModal notes(≥10 字,1611)+ openPromptModal tier(1625) | **§3 T3 Full Review** |
| 12 | `/api/v1/governance/canary/manual_promote` | **POST via `ocApi(url,{method:'POST'})`** | `_onPromoteClick`(canary:319,addEventListener 綁定非 onclick) | `{cohort_id, from_stage, to_stage, reason}` | **openTypedConfirmModal phrase=`PROMOTE`**(canary:334)+ openPromptModal reason | **canary stage 晉升(LeaseScope)** |
| 13 | `/api/v1/governance/autonomy-level/switch` | POST | `autonomyOpenSwitchModal`(autonomy:181)→`govSwitchAutonomyLevel`(governance.js:128) | `{target_level, reason, typed_confirm_phrase, totp_code}` | openPromptModal reason(≥30 字)+ openPromptModal TOTP + **openTypedConfirmModal phrase=`CONFIRM SWITCH`**(autonomy:216,confirmClass danger) | **autonomy 姿態切換(system-wide)** |

> **grep 盲點**:#12 `canary/manual_promote` 用 `ocApi(url,{method:'POST'})`(canary:388)**非** `ocPost` → `grep ocPost` 會漏。E1a 驗寫面守恆時必含此路徑。
> **defined-but-unwired(零 caller,非活躍寫,不列上表)**:`govPostHealthCheck`(governance.js:98,POST `/governance/health-check`)、`govDismissAllAudit`(governance.js:174,POST `/governance/audit/dismiss-all`)——保留於 governance.js 未改 text,dormant。
> **「auth-freeze」**:governance GUI **無** freeze 寫端點(FROZEN 是後端 SM 轉移態,GUI 只顯示)。brief 的「auth-freeze」無對應寫面。

**5b 對齊 ratchet**:上 13 endpoint(+2 dormant)全在既有未改 JS text 內,E1a 不新增 call-site;新 `view-governance.js` 自身只 `fetch('/static/tab-governance.html')` + `fetch('/static/*.js')`(GET,registry 完整性 src)——需確認此 4 個 static GET ∈ authoritative/allowlist,否則 5b 紅。

---

## 6 · §3 硬化面 byte-parity 清單(item 6,E1a 零弱化)

governance 的 §3 硬化**不同於 risk**(risk 有 REAL FUNDS/`--live` 熱紅類;governance **無** `--live` CSS 類,live 態配色由 reused JS 執行期 `.style` 設)。逐字保留清單:

**typed-confirm phrase(逐字,禁弱化/短路)**:
- `CONFIRM`——bulkAudit(gov-tab:1614)、confirmApproveRecovery(gov-tab:1764)
- `PROMOTE`——canary manual_promote(canary:41/334,case-sensitive)
- `CONFIRM SWITCH`——autonomy switch(autonomy:216/228)

**五閘 / Live boundary 文案(逐字)**:html:805(`5-gate 5 + protected 6 + opt-in 8 + venue 1`)、html:946(`Stage 4 = LIVE_PENDING(不自動晉升,必走 5-gate live boundary)`)、html:956(`Live boundary 5-gate`)、canary:166/224(`Stage 4 走 5-gate live boundary`)、autonomy learn-body(html:753-760,「5 道安全閘門 + 換交易所永遠上鎖」)。

**緊急停止 / 熔斷分離(逐字)**:governance-tab.js `_WHAT_RULES` 的「緊急熔斷」條(gov-tab:1300-1323,`熔斷不可通過拒絕取消`/`熔斷後系統不會再開任何新倉`)、`CIRCUIT_BREAKER 熔斷(全部凍結)` / `DEFENSIVE 防御(只許平倉)`(gov-tab:1141)、SM-04 abbr(html:563)。

**Live 授權硬化(逐字)**:inline 塊 `Signed auth: MISSING - auto-revoked after Live halt`(html:1353)、`Rust deletes authorization.json while the Live session remains halted`(html:1355/1548)、Trust TTL EXPIRED/`<2h` 配色邏輯(html:1458-1470)、T3 `印` 朱印方印形制(html:1437-1445,canon 9,`seal-mark` 用 tokens.css 原子)。

**REAL FUNDS 對應**:governance 用 `Paper 模擬(無真實資金)…每次授權都需要你親自審批`(gov-tab:1255)——逐字保留。

**落 view-governance.css 的部分**:**無**。governance 無 `--live`/`.is-active-live` 專屬熱紅類;live/halt/circuit 態配色全由 **reused JS 執行期** `element.style.*` 設(inline 塊 `row.style.borderColor='rgba(239,68,68,0.5)'` html:1514、`expiresEl.style.color='var(--neg)'` html:1460;governance.js `GOV_TRUST_TIER_COLORS`;autonomy `gov-autonomy-banner`)。**此屬未改 JS 的 byte-parity 執行期行為,非 view-governance.js/css 的新 inline-style ratchet 違規**(§8 說明)。

> **live-hardening snapshot 守衛(R53)**:cutover 前跑,確認上列文案/phrase/熔斷分離 diff=0,不稀釋。

---

## 7 · canon-7 三態(item 7,復用 script 原樣,view 零 fake)

governance 的三態渲染點**全在 reused JS**,view-governance.js 零 fake:
- **未接數據 `—`/`--`**:全 card 初值 `--`(html 各 id 預設);`_formatObservationProgress` total=0 → `—`(canary:80);metric threshold null → `—`(canary:276)。
- **blocked/degraded**:`showUnavailable()`(gov-tab:1052,governance_hub_unavailable);autonomy degraded → `連線降級 / Degraded` + 保守 Level 1 fallback(autonomy:154-157/171-178);canary 後端不可用 → fallback empty state 不破畫面(canary:110/143/256)。
- **anti-fake 三態分流**:submitOverride(applied/pending/unconfirmed,gov-tab:442-456)、submitPromotion(promoted true/false/unconfirmed,gov-tab:983-996)——**不把 pending 誤顯綠**。
- **stale/fresh**:live-auth TTL `<2h` 黃 / EXPIRED 紅(html:1458-1470)。

E1a:注入即渲,三態由 reused loadAll/render* 原樣產出;view-governance.js 不改任何顯示分支。

---

## 8 · view-governance.css scope(item 8)

- **來源**:兩 `<style>` 塊(html:20-375 主塊 + html:1230-1247 oc-modal 塊)→ 全搬入 `view-governance.css`,**外層 `.governance-view` scope**(鏡像 view-risk.css `.risk-view`)。
- **born-clean ratchet**:view-governance.js/css(E1a 新檔)**零 inline style、零新裸 `#hex`、零新框架**;動態值走 `setProperty` scoped-var(既有 `--canary-fill-w` html:222 / `--lt-progress-w` html:294 已是此模式,原樣保留)。
- **既有 `rgba()` 色字面 = pre-existing,逐字搬(byte-parity)**:主塊含多處 `rgba(…)` 色字面(canary stage chip `rgba(56,139,253,…)`/`rgba(248,81,73,…)`/`rgba(100,116,139,…)` html:140-206、tint 背景 html:27/80/315 等),源註明「palette 外色 verbatim,P0.4 複審」(html:257/313/319)。**搬入時逐字保留,不 re-tokenize**(改之即 skin 變更,違 byte-parity);標為 P0.2/P0.4 pre-existing 債,不計入 E1a 新違規。oc-modal 塊(1230-1247)`rgba(0,0,0,0.6)` 遮罩同理逐字。
- **reused JS 執行期 `.style` inline 不入 css、不算 E1a inline 違規**(§6):在未改的 governance.js / inline 塊 / autonomy-posture.js text 內,非 E1a 新碼。
- **「未定義 toggle 類刻意不 port」陷阱核查**:risk 有 pf-toggle/slider(頁內未定義 → 原生 checkbox → 不 port)。governance 對應 = html:696 `class="trust-tier-badge gov-trust-tier-badge"` 的裸 **`.trust-tier-badge`** —— 全 `.css` **無定義**(僅 `.gov-trust-tier-badge` html:327 有定義並承載樣式)。裸 `.trust-tier-badge` 為冗餘類,**無樣式可 port**(JS 另以 `.style` 覆蓋 bg/color,html:1434)。**刻意不新增 `.trust-tier-badge` 定義**(port 之即 skin 變更)——與 legacy 一致,源碼事實非缺陷。

---

## 9 · registry / router 接線(item 9)

- **VIEWS entry**(shell.js:119):現 `{ id:'governance', lane:'cross', hash:'#/cross/governance', src:'/static/tab-governance.html', visId:'governance', label:'治理 Governance', flag:true }`(**無 `iframe:` 鍵 → 預設 iframe:true**)。E1a **加 `iframe:false`**(保留 `flag:true`,同 risk entry shell.js:128)。
- **`view-governance.js` 加 `<script src>`** 於 **shell.html:225**(view-risk.js 註冊點旁,shell.js 前載以註冊 OC_NATIVE_VIEWS['governance'])。
- **governance.js 已於 shell.html:215 `<script src>` 殼載**(提供 govGetStatus/govPost*/gov*Badge/GOV_* 全域,§5 全寫路徑依賴)→ view-governance.js **勿重載**、勿併入 IIFE(§A.2)。canary-tab.js / autonomy-posture.js **未**殼載(僅在 tab-governance.html)→ 由 render fetch-text 併入(§A.1)。
- **OC_NATIVE_VIEWS 註冊**:`window.OC_NATIVE_VIEWS['governance'] = { render:renderGovernanceView, resume:resumeGovernanceView, pause:pauseGovernanceView }`(+ 具名 window 導出)。
- **render**:建 `.governance-view` 宿主 → 併發 fetch tab-governance.html + autonomy-posture.js + governance-tab.js + canary-tab.js → DOMParser 注入 body DOM(byte-parity clone,skip script/style)→ §3.B′ onclick 重綁 → 串接 4 段 + re-export + 曝 `__ocGovLoadAll` → 全新 `<script>` 節點重跑(built guard 只首渲)。首拉 + 啟輪詢由重跑段自帶(gov-tab `loadAll()`+`ocStartRefresh(loadAll,10000)`;inline `govLoadLiveAuthStatus`+`startGovLiveAuthLoop`;canary else-分支)。
- **pause**(view 隱藏)——需停**兩**輪詢:
  1. 主 10s:`ocStopRefresh()`(清 common.js 全域單例 `_ocRefreshTimer`,同 risk/paper)。
  2. live-auth 30s `_govLiveAuthTimer`(IIFE-local,ocStopRefresh 清不到)——**postMessage 復用**:`window.postMessage({type:'openclaw-tab-visibility', tab:'governance', visible:false}, location.origin)`。inline 塊的 message listener(html:1677,跑在殼 window)收到 → `_govLiveAuthVisible=false` → `stopGovLiveAuthLoop()`。**零修改復用既有 visibility 語義**(§9-★)。
- **resume**(view 顯示):
  1. postMessage `visible:true` → inline listener 啟 `startGovLiveAuthLoop()` + `govLoadLiveAuthStatus({force:true})`。
  2. 首拉主頁 `window.__ocGovLoadAll()` + `ocStartRefresh(window.__ocGovLoadAll, 10000)`(鏡像 risk;用命名空間非 window.loadAll)。`!built||!wired` 時 no-op(重跑本身已首拉+啟輪詢)。
- **★ 為何 postMessage 復用**:inline 塊的 `message` listener 註冊在**殼 window**(合併 script 跑於殼 realm,非 iframe)→ 殼內 `window.postMessage(...)` 同 window 可收。native view 無 iframe 可 postMessage,但此 listener 恰在殼 window → 直接 reuse,無需曝 start/stop 到 window,byte-parity 最佳。(替代:另曝 `__ocGovLiveAuthStop/Start`,較繁,不採。)
- **IIFE-local setInterval 的 pause 限制**:live-auth `_govLiveAuthTimer` 經 postMessage→stopGovLiveAuthLoop **可**外停(優於 risk 的 `setInterval(loadAiBudget)` 無法外清)。另 inline 塊自帶 `document.visibilitychange` listener(html:1704)——瀏覽器層 tab 隱藏亦會停 live-auth loop(雙保險)。built guard 防 resume 重跑 IIFE → 不重註冊 listener/不雙 setInterval。

---

## 10 · E1a 交付物(item 10)

**新增**:
- `view-governance.js`(thin wrapper,類比 view-risk.js;含強化 handler 發現 §3.A + onclick 重綁 §3.B′ + 雙輪詢 pause/resume §9)
- `view-governance.css`(兩 style 塊 → `.governance-view` scope,§8)
- shell index 加 `<script src="/static/view-governance.js">`

**改**:
- shell.js:119 VIEWS governance entry 加 `iframe:false`(僅此一鍵)

**零修改(reuse 正本 + rollback 錨)**:
- `tab-governance.html`、`governance-tab.js`、`canary-tab.js`、`autonomy-posture.js`、`governance.js`

---

## 硬約束(E1a 遵行)

- 零自建寫路徑;§5 全 12 寫走既有 Rust IPC(復用未改 JS text);typed-confirm(`CONFIRM`/`PROMOTE`/`CONFIRM SWITCH`)逐字保留不弱化。
- 零 inline style / 裸 hex / 新框架(view-governance.js/css 新碼);動態值走 setProperty scoped-var。既有 rgba 色字面逐字搬(pre-existing,§8)。
- §3(五閘 / typed-confirm / 緊急停止·熔斷分離 / signed-auth·authorization.json / Paper 無真實資金)+ live-hardening snapshot 守衛不稀釋(§6)。
- E2 + E3 雙審(交易關鍵)+ operator Linux 批驗才 cutover。Mac 靜態(node --check + ratchet 0/0/0 新檔 + 5b + 註冊 smoke + R71 guard = 空集)只證 source 事實;真渲染 / 12 寫真行為 / typed-confirm 真閘 / 三態 / 雙輪詢 = **NEEDS-LINUX runtime + operator**。

---

## OPEN(供 PM 裁)

- **OPEN-1(HIGH,§3.B′)**:`loadAll` 衝突處置 —— PRIMARY(clone 節點 onclick 重綁 `loadAll()`→`__ocGovLoadAll()`,永不寫 window.loadAll)vs FALLBACK(不重綁,手動刷新鈕降級 no-op)。PA 傾向 PRIMARY。涉及「clone DOM 執行期調整是否算 seam 手法 / 破 byte-parity」的界定 → E2/E3 裁。
- **OPEN-2(MED,§3.A)**:強化版 `discoverOnHandlerNames`(掃 html∪script、抓非首 token、交集頂層函式、濾保留字)是 governance 相對 view-risk.js 的**必改**(否則 html:937 `if` 致 `window["if"]=if` parse error 全死 blocker)。確認 E1a 不得原樣複製 view-risk.js 的 handler 發現。
- **OPEN-3(LOW,§9)**:live-auth 30s loop 的 pause 採 postMessage 復用 inline listener(零修改)vs 另曝 `__ocGovLiveAuthStop/Start`。PA 傾向 postMessage 復用。

---

## PM 裁決(R76,2026-07-12)

三 OPEN 皆屬遷移 seam 設計選擇(非 operator/治理裁量),PM/Conductor 逕裁如下;E1a 照此實作,E2/E3 據此核。

- **OPEN-1 → 採 PRIMARY(clone 節點 onclick 重綁 `loadAll()`→`__ocGovLoadAll()`,governance 永不寫 window.loadAll)。** 理由:①**源檔 tab-governance.html 零修改**(byte-parity/rollback 錨保全)——重綁發生在 view-governance.js **執行期對 cloned 節點**,是遷移 seam 的職責本身(把 global 域引用適配到 IIFE-isolated 等價),與 risk 的 `__ocRiskLoadAll` 隔離 + onclick re-export 機制**同類**,在既定 seam 手法範圍內,非對 governance 行為的 skin/邏輯改動;②FALLBACK(刷新鈕 no-op)=功能靜默丟失,違「遷移零丟失」。**E2 硬核**:(a) 源 html 未觸;(b) 此為**唯一** onclick 重綁(其餘 handler 全走標準 re-export);(c) `__ocGovLoadAll` 呼叫的 loadAll 與源 byte-identical;(d) governance 全程不寫 window.loadAll(paper 恆安全)。MODULE_NOTE 須明記此唯一重綁及理由。
- **OPEN-2 → 確認為必改(非選擇)。** E1a **不得**原樣複製 view-risk.js 的 `discoverOnHandlerNames`,**必須**實作 §3.A 強化版(掃 html∪script、抓非首 token、交集頂層函式名、濾 JS 保留字)。**E2 硬核**:保留字濾除(尤 `if`,否則 `window["if"]=if` parse error 整段 IIFE 死=blocker)+ `loadAuditTrail`(html:1091 非首 token)/`auditApprove`/`auditReject`/`confirmApproveRecovery`(模板注入)確被捕獲且 re-export。
- **OPEN-3 → 採 postMessage 復用 inline listener(零源修改)。** 比另曝 stop/start API 面更小、與既有 `openclaw-tab-visibility` 機制一致。E1a 照 §9 實作;IIFE-local `_govLiveAuthTimer` 於 pause 經 postMessage 停、resume 起。

**E1a 交付即照本規格(§A-§10 + 硬約束 + 上述三裁)實作 view-governance.js + view-governance.css;五源檔(tab-governance.html/governance-tab.js/canary-tab.js/autonomy-posture.js/governance.js)零修改。** 交易關鍵=E1a→E2→E3→E4 全鏈,operator Linux 批驗才 cutover。
- **無循環依賴 / 無 canary 自初始化衝突**:canary 自成 IIFE + else-分支 self-init,與其餘三段僅經 window.loadCanaryCohorts 交互;autonomy↔gov-tab 經同 IIFE 詞法 + governance.js 上層全域,序 [inline,autonomy,govtab,canary] 滿足 const TDZ。三 JS **無**互引對方 IIFE-local 而失敗的循環。
