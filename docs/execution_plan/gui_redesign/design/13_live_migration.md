# 13 · Live view 遷移規格(iframe → 原生玄衡 view)

> PA-design-writer(2026-07-12,R85)。承 design/10 recipe + design/11 governance 遷移正本 + view-risk.js/view-demo.js pattern。
> **靶**:`live`(§0.1 交易關鍵四者**最後**一個,operator 2026-07-12 §0.2 授權 **skin-only 重宿** GO)。
> **手法**:共享 IIFE 復用(fetch tab-live.html DOM byte-parity clone + fetch tab-live.js text → 串接單一 IIFE 重跑),鏡像 view-risk.js/view-demo.js。
> **產出物**:`view-live.js`(thin wrapper,類比 view-risk.js)+ `view-live.css`(`.live-view` scope)。`tab-live.html / tab-live.js` **零修改**(reuse 正本 + rollback 錨)。
> **驗收**:交易關鍵 → E1a → **E2 + E3 雙審(硬邊界)** → E4 → operator Linux 批驗才 cutover。Mac 靜態只證 source 事實。
> **本輪只做調查 + 寫本規格**(read-only 源碼 + 只寫 design/13);實作留下一輪 E1a,不改任何 app/static 源碼。
>
> ⚠ **live 是交易關鍵四者中結構最簡單、§3 硬化面最重的一個。** 相對 governance 的三新風險(4 路 script / loadAll 硬編 / `if` blocker),live **全部不觸**;但 live 有 governance/risk 沒有的**兩個新處置點**:
> - **(L1 · §10/§12 最高關注)** tab-live.html 的 **`body.live-mode-*` 主題類**(mainnet 熱紅 / livedemo 橙 / unconfigured):reused JS 於 `document.body`(**殼 body**)加 class,view-live.css 的 mode override 規則**不能**天真地 scope 進 `.live-view`(class 在祖先 body 上,非後代)→ 必須 body-anchored port。這是 risk/governance 未覆蓋的新形。
> - **(L2 · §3.A/§10)** 唯一模板注入 on* handler **`closeLivePosition`**(tab-live.js:837,倉位表 row template,**不在** tab-live.html)→ view-risk.js 只掃 htmlText 的 `discoverOnHandlerNames` 會**漏**它 → onclick ReferenceError。必須掃 **html ∪ combined**(governance §3.A 強化版恰覆蓋此,理由不同但形同)。
>
> **F1-class 反而是空集**(brief 稱「頭號風險」,實測 refute,見 §4):live 的 typed-confirm pending callback **不存在**——全走 `openTypedConfirmModal({...}).catch(...)` async/await 回傳 Promise,**無**risk 那種 `_liveRiskSavePendingCallback` 全域裸賦值 pending → 不需 F1 window↔IIFE-local proxy。

---

## 0 · 事實核實結論(相對 brief)

| brief 敘述 | 源碼實測 | 依據 |
|---|---|---|
| tab-live.html 另有 inline `<script>` 塊(如 governance) | ❌ **無**。body 內唯一 inline `<script>`=html:18 `ocAuthCheck(); ocInjectBaseCSS();`(**skip**);其餘全 external `<script src>`(head 的 common*,殼已載;body 末 html:593 `tab-live.js`)。故 combined = **只 tab-live.js text**,無 inline 塊要併入(比 risk/governance 都簡) | html:18, 593;`<style>` 僅 1 塊 html:20-285 |
| onclick handler 有截斷的 `do…` 未查全 | ✅ 補全:三個 `do*` = doLiveStop(381)/doEmergencyStop(382)/doLiveCloseAll(468);全集 12 靜態 + 1 模板注入,見 §3.B | 見 §3.B |
| tab-live.js **無 loadAll** | ✅ **確認無 loadAll**。self-init = `refreshPage({force:true})`(js:1923)+ `startLiveRefreshLoop()`(js:1924)。**不需** `__ocLiveLoadAll` 重綁(比 governance 簡);resume 走 postMessage 復用(§9) | js:1923-1924 全文無 `loadAll` |
| F1-class(typed-confirm pending callback)是頭號風險 | ⚠ **REFUTE**:live 無 pending-callback 裸賦值。所有 do* 走 `await openTypedConfirmModal(...).catch(()=>false)`(js:1047/1086/1119/1149),confirm 語義自封閉於 SDK Promise → **F1 proxy 集 = ∅**(§4) | js:1047,1086,1119,1149 |
| refreshPage 可能 `location.reload()` 重載整殼 | ⚠ **REFUTE**:`refreshPage(options)`(js:462)是**純資料刷新** async fn(重拉 engine status + trust + dashboard),**非** page reload。全檔**零** `location.reload/href=/window.location=`(僅 3 處唯讀 `location.origin`);html:317 `refreshPage({force:true})` 鈕 byte-parity 保留即可,不需原生覆蓋(§8) | js:462-512;grep `location.` = 273/284/1903 唯讀 |
| 寫面「所有 /api/v1/live/* 寫」 | ✅ 4 distinct endpoint / 6 call-site(§7);**live 無 auth/renew 寫**(Renew 已移至 Governance Hub,js:116/527 註;那是 governance §5 #10/#11 的職責) | §7 |
| 輪詢多迴圈 | ⚠ 實際 **單一 setInterval** `_liveRefreshTimer`(15s,js:1893);sub-refresh(dashboard 30s/metrics 30s/edge 120s/pnl 60s)是 `refreshPage` 內**時戳節流**非獨立 interval → pause 只需停一個 timer(§9) | js:1891-1900 |

---

## A · script 併入清單、串接序、skip(item 1)

### A.1 fetch 併入共享 IIFE(**單路 text**,無串接序問題)

render 時**併發 fetch** 2 個資源(1 HTML + 1 JS text):

| 序 | 來源 | 取得方式 | 說明 |
|---|---|---|---|
| — | tab-live.html 的 **body DOM** | fetch html → DOMParser → clone `<body>` 非-script/style 節點進 `.live-view`(byte-parity) | 提供 live DOM(integrity-fail view + dashboard view 全部 id/class/onclick) |
| 1 | **tab-live.js** text | fetch `/static/tab-live.js` | **唯一** JS 段。IIFE-wrap 後重跑 |

**combined = tab-live.js text**(無 inline 塊前綴——tab-live.html 唯一 inline `<script>`=skip 塊)。外層 `(function(){ <combined>; <re-export>; })();`。**無 governance 的 4 路串接序 / TDZ 約束問題**(單段)。

**★ 為何不需 `__ocLiveLoadAll`**:live 無 loadAll;tab-live.js self-init(`refreshPage({force:true})` + `startLiveRefreshLoop()`,js:1923-1924)在 append 當下同步跑=首拉 + 啟 15s 輪詢。resume 由 postMessage 復用既有 visibility listener(§9),不需暴露 loadAll/refresh 到 window 命名空間(比 risk 的 `__ocRiskLoadAll` 更省——live 的 visibility listener 已內建 start+refresh)。

### A.2 skip(不併入 / 不 clone)

| 資源 | 處置 | 理由 |
|---|---|---|
| head 的 `common-formatters / common-mode-badge / common-modals / fetch_with_csrf / common.js`(html:11-15) | skip(殼已載) | external `<script src>`,shell boot 已載入;提供 tab-live.js 全部 free var(**已核實**:classifyLiveMutation/ocResidualRiskBanner/ocReadCachedDevelopmentSupportMode/ocListenDevelopmentSupportMode/ocFetchDevelopmentSupportMode 於 common.js;openTypedConfirmModal/openConfirmModal 於 common-modals.js;ocPerformanceMetricsFromPayload/ocStrategyChip/ocPnlSeriesFromFills/ocSetPnlRangeButtons 於 common-formatters.js;ocPost/ocApi/ocToast/ocMiniTrendSvg 於 common.js) |
| inline `<script>`(html:18 `ocAuthCheck(); ocInjectBaseCSS();`) | skip | 殼 boot 已 ocAuthCheck;`ocInjectBaseCSS` 注 `body{padding}`+`*` reset **破殼 chrome**,禁呼(同 risk/governance/demo) |
| `<style>` 塊(html:20-285) | skip(不進 IIFE) | → view-live.css,`.live-view` scope(§10/§12) |
| external `<script src="/static/tab-live.js">`(html:593) | 不作 `<script src>` 重載;其 **text 另 fetch** 併入 IIFE | 避免其 self-init 在無 DOM 的殼 boot 期跑(同 risk 對 risk-tab.js 的手法) |

### A.3 tab-live.js self-init / listener 行為(重跑當下)

| 段 | eval-time 自初始化 | 重跑當下行為 |
|---|---|---|
| dev-support 可見性(js:294-304) | `applyDevelopmentSupportVisibility(...)` + 註冊 `ocListenDevelopmentSupportMode` + `ocFetchDevelopmentSupportMode().then(...)` | 同步:對 `[data-dev-mode-only="global-mode-control"]` 元素(在 .live-view 內)toggle hidden。querySelector 掃殼 doc,元素 live-unique,byte-parity 無害 |
| visibility listener(js:1902-1912) | `window.addEventListener('message', …)`(收 `openclaw-tab-visibility` tab==='live') | 註冊於**殼 window**——§9 pause/resume 復用之核心 seam |
| browser visibility(js:1914-1921) | `document.addEventListener('visibilitychange', …)` | 註冊於**殼 document**;瀏覽器隱藏時 `_isLiveTabRefreshVisible()` 判 false → stopLiveRefreshLoop(雙保險) |
| self-init(js:1923-1924) | `refreshPage({force:true})` + `startLiveRefreshLoop()` | 同步:首拉全頁 + 啟 **15s `_liveRefreshTimer`**(§9 唯一輪詢) |

**★ 關鍵:live 不需 view-paper.js 的 DCL-capture 劫持。** tab-live.js **無** `DOMContentLoaded` 監聽;self-init 在 eval-time 直接跑。E1a 用 view-risk.js 的直接 append 重跑即可。built guard 只首渲一次(防雙 fetch/雙 setInterval/雙 listener 註冊)。

---

## 2 · 頂層宣告名總表 + IIFE 隔離論證(item 2)

tab-live.js 頂層(深度 0)宣告(raw 重跑會進殼 global lexical,IIFE-wrap 後全 IIFE-local):

**`const`**:`TRUST_TIER_LABELS, TRUST_TIER_COLORS, LIVE_REFRESH_MS, LIVE_DASHBOARD_REFRESH_MS, LIVE_PNL_REFRESH_MS, LIVE_EDGE_REFRESH_MS, _liveModeState, LIVE_FILL_PAGE_SIZE, LIVE_FILL_TABS, LIVE_PNL_PRELOAD_SIZE`

**`let`**:`_livePnlRange, _liveMetricsLoadedOnce, _liveFillsLoadedOnce, _liveRefreshTimer, _liveRefreshInFlight, _liveTabVisible, _lastDashboardRefreshMs, _lastMetricsRefreshMs, _lastPnlRefreshMs, _lastEdgeRefreshMs, _liveStatusLoadedOnce, _liveStratMap, _fillsLoaded, _liveFillState, _livePnlHistoryState`

**`function`(節選關鍵)**:`_isLiveTabRefreshVisible, _livePriceCell, _signedAuthDisplayState, loadTrustStatus, openLiveRisk, openLiveAuth, applyDevelopmentSupportVisibility, _applyLiveModeUI, _applyLiveActionGuards, refreshPage, _ocRenderOwnerStrategy, _renderLiveDustPanel, _buildLiveStratMap, _isPhantomViewError, _livePerformanceMetrics, _liveMetricValue, _applyLiveTodayPnl, loadDashboardData, checkLiveEngineStatus, liveStart, doLiveStop, doEmergencyStop, doLiveCloseAll, closeLivePosition, loadLiveMetrics, setLivePnlRange, loadLivePnlSeries, _edgeGateTone, _edgeGateChip, _edgeMetricValue, _edgeGateTrendValues, _edgeGateValueCells, _renderEdgeGateCard, _readinessValue, _renderReadiness, loadPreLiveEdgeGates, toggleFills, _liveFillTs/_liveFillQty/_liveFillPrice/_liveFillFee/_liveFillPnl, _liveFillHead, _liveFillRow, _liveBuildProfitRows, _liveProfitRow, _liveStrategySourceLabel, _liveClosedPnlRow, _liveUpdateFillControls, _liveResetPnlHistory, _liveCurrentPnlRows, _liveRenderPnlHistory, _liveLoadPnlBatch, _liveMaybePreloadNextPnlPage, setLiveFillView, liveFillPrev, liveFillNext, loadFills, startLiveRefreshLoop, stopLiveRefreshLoop`

**撞已遷頂層名者(若 raw 重跑會 SyntaxError / last-writer-win)**:
- **`refreshPage`**——唯一「泛名」。實測(whole-word grep)其他 view/tab JS **零定義/零消費** `refreshPage`;common.js 僅**註解**(common.js:599/601/903,描述殘留風險橫幅語義,非定義)。故無跨-view window.refreshPage 消費者,re-export 安全(§3.C)。
- 其餘全 `live`/`Live`/`_live` 前綴或 live 專屬,**無**與 paper/settings/overview/risk/governance/demo 頂層重名。

**隔離論證**:外層 IIFE-wrap 後,上述**全部**頂層 `const/let/function` 成 **IIFE-local**,不進 global lexical → ① 不與 paper 的 raw 全域(loadAll 等)在 global lexical 重宣告(paper=raw,live=IIFE,只可能在 `window.*` 層相撞,見 §3.C);② 不與 risk/overview/settings/governance/demo 各自 IIFE 的頂層重宣告(彼此 isolated)。**過 R71 跨-view 詞法 guard,live 判 isolated,貢獻空集**(與 view-risk.js 同)。

---

## 3 · onclick/on* handler 集 + 交集比對 + handler 發現強化(item 2/4)

### 3.A 強化版 handler 發現(**必改**,取代 view-risk.js 的 `discoverOnHandlerNames` 只掃 htmlText)

**問題**:view-risk.js 的 `discoverOnHandlerNames(htmlText)`(view-risk.js:128)只掃 **tab-live.html**;但 live 有一個 on* handler **只在 tab-live.js 模板字串**:
- **(L2 miss)** `closeLivePosition('${sym}', this.dataset.ownerStrategy, this.dataset.frozenReason)`(tab-live.js:837,倉位表 row template 由 `loadDashboardData` innerHTML 動態注入)。此 handler **不在** tab-live.html;只掃 html 會**漏** → 個別倉位平倉鈕 onclick 在殼 global 域 `closeLivePosition is not defined` → 平倉鈕全死(F5-RETURN/Issue-2 的個別倉位平倉 = **安全關鍵寫**,不可靜默死)。

**處置(E1a 實作)**——`view-live.js` 用強化發現(**掃 html ∪ combined**):
1. **掃描範圍** = `htmlText`(tab-live.html) **∪** `combined`(tab-live.js text)。後者含 `onclick="closeLivePosition(…"` 模板字串 → 捕到 closeLivePosition。
2. 沿用 first-token regex `on[a-z]+\s*=\s*["']\s*([A-Za-z_$][\w$]*)\s*\(` 即足(live **無** governance 的多語句 handler,無需非首 token 提取)。掃 combined 額外命中 `_applyLiveActionGuards` 內 querySelector 字串 `button[onclick="doLiveCloseAll()"]`(js:422)→ 捕 `doLiveCloseAll`(**已是**真 handler,重複無害);`button[onclick^="closeLivePosition"]`(js:440)因 `^=` 破 `on[a-z]+\s*=` **不中**,無誤。
3. **re-export**:`try{window[name]=name;}catch(_e){}` 逐名(IIFE 內函式 hoist 可見;非真頂層函式→ReferenceError→try/catch 跳過)。

**⚠ live 相對 governance §3.A 的差異(不同理由,同結論「必掃 combined」)**:
- live **無**保留字 blocker(governance 的 html:937 `if` → `window["if"]=if` parse 死)。live 全 on* 名皆合法識別字。
- live **無**非首 token miss(governance 的 `event.stopPropagation();loadAuditTrail()`)。live on* 皆單一函式呼叫。
- live 的**唯一**必掃-combined 理由 = 模板注入的 `closeLivePosition`。

> **推薦(§9 OPEN-5)**:E1a **直接復用 view-governance.js 的強化 `discoverOnHandlerNames`**(已含掃 html∪combined + 保留字濾 + 頂層函式交集)——雖 live 現況只需「掃 combined」一項,復用 governance 版=跨兩交易關鍵遷移一致 + 未來若模板新增保留字/多語句 handler 免再回改。**必改硬核**:closeLivePosition 確被捕獲且 re-export(否則個別平倉鈕死)。

### 3.B live 完整 on* handler 集(超集)

**靜態 tab-live.html on***(行號):liveStart(314)、refreshPage(317,arg=`{force:true}`)、openLiveAuth(320)、openLiveRisk(378)、liveStart(379)、doLiveStop(381)、doEmergencyStop(382)、setLivePnlRange(442/443/444/445/446,五按鈕 1h/6h/24h/7d/30d)、doLiveCloseAll(468)、toggleFills(551)、setLiveFillView(559/560/561/562,aggregate/buy/sell/profit)、liveFillPrev(565)、liveFillNext(567)

**JS 模板注入 on***:closeLivePosition(tab-live.js:837)

**exportNames(去重、含模板注入)= 13 名**:
`liveStart, refreshPage, openLiveAuth, openLiveRisk, doLiveStop, doEmergencyStop, setLivePnlRange, doLiveCloseAll, toggleFills, setLiveFillView, liveFillPrev, liveFillNext, closeLivePosition`

(全 13 皆 tab-live.js 頂層 `function`(§2)→ IIFE-wrap 後 IIFE-local → 全部**須** re-export 至 window,否則對應 onclick 破。**無** loadAll 例外(live 無 loadAll,§5)。)

### 3.C 逐一與 paper/settings/overview/risk/governance/demo onclick 集交集比對(re-export 安全硬前提)

實測(whole-word grep,view-*.js + tab-*.js,排除 tab-live.*):13 名中 **12 名** 完全 live-unique;**`refreshPage`** 另現於 common.js **但僅註解**(非定義/非消費)。

| 已遷 view onclick 集(依 shell.js MODULE_NOTE / 前遷 spec) | 與 live 13 名交集 |
|---|---|
| paper(sessionAction, closePosition, …;`loadAll`=raw 全域) | **∅**(live 名皆 live*/Live*/do*Live*/openLive*/closeLivePosition 專屬) |
| settings(demoAction, configAction, …) | **∅** |
| overview(confirmAction, confirmMode, …) | **∅** |
| risk(switchRiskTab, submitRiskOverride, …, unhaltSession, saveAiBudget — 17 名) | **∅** |
| governance(toggleAuthScope, …, auditApprove, auditReject — 35 名) | **∅** |
| demo(sessionAction, …, onDemoFillsToggle — 12 名) | **∅**(demo `onDemoFillsToggle` ≠ live `toggleFills`) |

**結論:re-export 交集 = ∅ → 無 last-writer-win 破壞。** `refreshPage` re-export 至 `window.refreshPage` 安全(無跨-view 消費者;common.js 註解不衝突)。live **不寫** `window.loadAll`(live 無 loadAll),paper 恆安全,無 governance §3.B′ 的 loadAll 衝突處置需求(**live 比 governance 簡:無 onclick 重綁**)。

---

## 4 · F1-class 裸賦值風險(item 5)——**空集(brief「頭號風險」REFUTE)**

掃 tab-live.html **全部** on* 屬性值 **∪** tab-live.js 模板注入 on*,尋「裸 `IDENT=…` ∩ 頂層宣告名」(risk `_liveRiskSavePendingCallback` 先例):
- 全部 on* 皆函式呼叫:`foo()` / `setLivePnlRange('1h')` / `refreshPage({force:true})`(`force:true` 是**物件屬性冒號**非賦值)/ `closeLivePosition('${sym}', this.dataset.ownerStrategy, this.dataset.frozenReason)`(`this.dataset.*` 是 member 讀非賦值)。
- **無**任何 `IDENT=value` 裸賦值到頂層 binding。實測 `grep -E "on[a-z]+=\"[^\"]*[^=!<>]=[^=]"` 於兩檔:唯一命中=html:5 `<meta … content="width=device-width, initial-scale=1">`(**假陽性**:單字「c**ontent**=」被 `on[a-z]+=` 誤中;其內 `width`/`scale` 與頂層宣告名交集=∅ → 被 `onAttrBareAssignTargets ∩ topLevelDeclaredNames` 濾除,不生 proxy;此與 risk 對同型 `<meta>` 假陽性的處理一致,證交集是 load-bearing safety)。

**為何 live 無 pending-callback(結構論證)**:live 的 typed-confirm **全走** `const ok = await openTypedConfirmModal({...}).catch(()=>false); if(!ok) return;`(liveStart js:1047 / doLiveStop js:1086 / doEmergencyStop js:1119 / doLiveCloseAll js:1149);closeLivePosition 走 `if(!await openConfirmModal({...})) return;`(js:1195/1210)。confirm 結果由 **SDK 回傳 Promise** 承載,**無**risk 那種「取消鈕 inline `_liveRiskSavePendingCallback=null`」的殼 global 域裸賦值 → **無** IIFE-local pending 被殼域清不到的問題。

**結論:F1 proxy 集 = ∅,live 不需 window↔IIFE-local getter/setter proxy。** E1a 仍應保留 `onAttrBareAssignTargets ∩ topLevelDeclaredNames` 檢查作 born-safety(對 live 產空集,且應掃 html∪combined 見 §11),但不生成 proxy 碼。**§3 confirm/cancel 語義不因缺 proxy 而弱化**(live 的 confirm 是 async Promise-gated,非 inline 裸賦值 pending)。比 risk 簡單(risk 有 1 個 proxy)。

---

## 5 · loadAll(item 3)——**確認無**

tab-live.js **全文無** `loadAll`(grep 確認)。self-init = `refreshPage({force:true})` + `startLiveRefreshLoop()`(js:1923-1924)。故:
- **不需** governance/risk 的 `__ocGovLoadAll`/`__ocRiskLoadAll` 命名空間暴露。
- **不需** governance §3.B′ 的 `onclick="loadAll()"` clone-節點重綁(live 無此 onclick)。
- **不寫** `window.loadAll`,paper 的 `window.loadAll` 恆不被 live 觸碰(paper 恆安全)。
- resume 首拉走 postMessage 復用既有 visibility listener(§9),非 loadAll 呼叫。

**live 是交易關鍵四者中 loadAll/onclick-重綁 最乾淨者。**

---

## 6 · §3 硬化面 byte-parity 清單(item 6,E1a 零弱化;live=§3 硬化最重)

live 的 §3 硬化面**橫跨 tab-live.js(執行期 `.style`/文案/typed-confirm)+ tab-live.html `<style>`(`--live` 熱紅 CSS)**。逐字保留清單(源檔零改=回滾錨;cutover 前 live-hardening snapshot 守衛 R53 跑,diff=0):

### 6.1 五閘顯示 / signed-auth gate(逐字,禁弱化/短路)
- **`_signedAuthDisplayState`**(tab-live.js:66-102):signed authorization.json = Rust engine gate 的顯示;逐字文案 `'Signed auth: MISSING - auto-revoked after Live halt'`(js:89)+ title `'Renew can be accepted, then Rust deletes authorization.json while the Live session remains halted. Clear/reset the risk halt before renewing again.'`(js:91)+ `'Signed auth: ' + status + ' - Renew required'`(js:98)+ `'Signed auth: valid'`(js:72)。
- **五閘文案**:`'（請確認 5 道 live gate 與 authorization.json）'`(js:1070)、`'重新啟動 Live（重新走 5 道 gate 授權）'`(js:1085/1094/1127)、`'需重新啟動 Live 交易（重走 5 道 gate 授權）才能恢復'`(js:1128);html:361 `'全局模式門禁 / 二次確認 / 完整風控棧'` + `'Risk controls remain at strict Live standards regardless'`(html:365)。
- **execution_authority guard**:`_applyLiveActionGuards`(js:406-456)`execution_authority !== 'granted'` → disable 寫鈕 + tooltip(js:449);btn-start-locked 文案 `'Live engine 未啟動；點擊後仍需通過後端 Operator + live_reserved + Rust 授權門控'`(js:971)。**client-side guard,後端仍真權威**——逐字保留,不弱化。

### 6.2 typed-confirm phrase(逐字,case-sensitive,禁弱化/短路)
- **`START LIVE`**——liveStart(js:1050)
- **`STOP LIVE`**——doLiveStop(js:1089)
- **`EMERGENCY STOP`**——doEmergencyStop(js:1122)
- **`CLOSE ALL`**——doLiveCloseAll(js:1152)
- 全走 `openTypedConfirmModal({..., confirmClass:'oc-btn-danger', actor:'Operator', impact, rollback})`;phrase/body/impact/rollback 逐字。closeLivePosition 走 **openConfirmModal**(1-click,非 typed;dust 態 js:1195 / 一般 js:1210,`confirmClass:'oc-btn-critical'`)——保留原「單倉平倉=1-click / 全域破壞性=typed」分級。

### 6.3 緊急停止 · 平倉 · 停止 三者分離(逐字,**operator §0.2 硬邊界**)
- **doLiveStop**(js:1075)→ `POST /session/stop`:撤單 + 市價平倉 + **撤授權持久化** + session 停 + tier 重置 T0(body 逐字 js:1088)。
- **doEmergencyStop**(js:1111)→ `POST /session/stop`(**同端點**,差異僅互動層:跳過逐步、引擎在線始終可按;body 逐字誠實揭同一後端動作 js:1114-1118/1121)。
- **doLiveCloseAll**(js:1146)→ `POST /close-all-positions`(**session 不停**,引擎續跑;body 逐字 js:1151)。
- HTML 佈局分離:`live-shutdown-zone`(html:380-383,data-danger-zone)群組 btn-live-stop + btn-emergency-stop;`全部平倉`鈕(html:468)在 Positions header **獨立**。三者語義/端點/確認 phrase 各異,**逐字保留,不合併**。

### 6.4 REAL FUNDS 常駐標識 + `--live` 熱紅(canon 6,byte-parity,兩主題不稀釋)
- **REAL FUNDS badge**:`.real-funds-badge` CSS(html:194-200,`rgba(239,68,68,0.18)` 底 + `rgba(239,68,68,0.6)` 框 + `var(--neg)` 字);JS 於 mainnet 態 innerHTML `'REAL FUNDS · Mainnet'`(js:363)+ epBadge `real-funds-badge`(js:386-387)。`body.live-mode-mainnet` 由 `_applyLiveModeUI`(js:349-350)加。
- **`--live` 熱紅主題**(canon 6,**逐字 port 至 view-live.css**,§12 標為不可動):`.live-warn-bar`(html:37 `var(--live-bg)`+`var(--live)`)、`.live-control-bar`(html:47 `var(--live)` 框)、`.live-card-group.live-accent`(html:76 `var(--live)`)、`.live-fills-toggle:hover`(html:120 `var(--live)`)。
- **`.live-mode-mainnet` 真金 override**(html:173-179):`rgba(239,68,68,0.6)` 上緣紅框 + `var(--live-bg)` 熱紅底 + **`border-bottom: 3px double var(--neg)`** 下緣雙線(REAL-FUNDS 身分承載)。`.live-mode-mainnet .live-warn-bar strong { color: var(--neg) }`(html:191)。
- **`.live-mode-livedemo` 橙 override**(html:180-190,`rgba(249,115,22,*)`):LiveDemo=橙**非**真金熱紅(不誤升 canon 6);badge `.live-demo-badge`(html:201-207)。JS badge `oc-chip-warn`(橙)vs `oc-chip-live`(熱紅)分流(js:999)。
- **`.btn-emergency`**(html:126-141,`rgba(239,68,68,*)` 紅,危險操作按鈕保紅)。

### 6.5 live_halt / drawdown(逐字)
- signed-auth halt 明細:`liveHalt.session_halted` + `session_drawdown_pct` + `drawdown_threshold_pct`(js:76-92,`' (snapshot DD X% / limit Y%)'`)。
- contraction badge(js:1010-1021):`halted` → `oc-chip-bad` `'🚨 自動停止 (回撤X)'`;`warned` → `oc-chip-warn` `'⚠ 回撤警告 X'`。btn-emergency disabled = `!data.engine_available`(js:1033)。

### 6.6 canon-7 三態(phantom-view 防假 live,逐字,**reused JS 原樣,view 零 fake**)
- **integrity-fail view**(engine_kind != 'live'):`_applyLiveModeUI`(js:326-342)切 fail view,**刻意不渲染資料**(防 paper/demo 數字套 Live 皮=幽靈視圖);ifv-debug 顯 actual_engine_kind/endpoint/session。
- **phantom-view error**:`_isPhantomViewError`(js:645,`error==='live_slot_not_configured'`)→ metric card 顯 `'N/A'` + title 非 `'--'` 假裝有資料(js:665-675/724-730/775-778/873-877/1238-1243)。
- **unconfigured banner**:Live 槽空 → `'Live 槽未配置 — 顯示資料來自 demo 槽'`(js:375)。
- transient status timeout **不降級**已渲 Live view(js:930-933 保 last-known)。

> **live-hardening snapshot 守衛(R53)**:cutover 前跑,確認上列文案/phrase(4 typed + START/STOP/EMERGENCY/CLOSE ALL)/熔斷·平倉·停止分離 / REAL FUNDS / signed-auth 文案 / `--live` 熱紅 CSS diff=0,不稀釋。

---

## 7 · 寫面完整清單(item 7,**4 distinct endpoint / 6 call-site**)

全部寫**走既有 Rust authority IPC**(`ocPost` → ocApi 寫路徑 → Rust 引擎),復用未改 tab-live.js text,**零自建寫路徑、零改道、零 fake-success**。confirm 全 response-gated(`classifyLiveMutation` 三態判讀,非 `if(d)` 假成功)。

| # | endpoint | method | 觸發函式(js:行) | confirm gate | 未改 JS text |
|---|---|---|---|---|---|
| 1 | `/api/v1/live/session/start` | POST | `liveStart`(js:1058) | typed `START LIVE`(js:1050);`classifyLiveMutation` 判 success/未確認(js:1062,防 fake) | ✅ |
| 2 | `/api/v1/live/session/stop` | POST | `doLiveStop`(js:1097) | typed `STOP LIVE`(js:1089);殘留→`ocResidualRiskBanner`常駐橫幅(js:1106) | ✅ |
| 2′ | `/api/v1/live/session/stop`(**同端點**) | POST | `doEmergencyStop`(js:1130) | typed `EMERGENCY STOP`(js:1122);殘留→常駐橫幅(js:1138) | ✅ |
| 3 | `/api/v1/live/close-all-positions` | POST | `doLiveCloseAll`(js:1160) | typed `CLOSE ALL`(js:1152);殘留→常駐橫幅(js:1172) | ✅ |
| 4 | `/api/v1/live/positions/{symbol}/close` | POST | `closeLivePosition`(js:1201 dust / js:1216 一般) | 1-click `openConfirmModal`(dust 態警告交易所拒單 js:1195;一般 js:1210) | ✅ |

> **live 無 auth/renew 寫**:Renew 已移至 Governance Hub → Live Auth(js:116/527 註;對應 governance §5 #10 `/api/v1/live/auth/renew`、#11 `/api/v1/live/auth/renew-review`)。live view 只顯示 trust/signed-auth 狀態(唯讀 `/api/v1/live/auth/trust-status`),**不**含 renew 寫面。
> **讀端點(GET via ocApi,10 個)**:`/api/v1/live/auth/trust-status`、`/session/status`、`/balance?fast=1`、`/positions?fast=1`、`/orders`、`/metrics`、`/pnl-series?range=`、`/fills`、`/closed-pnl`、`/strategy/prelive/edge-gates?window_days=7`。
> **5b 對齊 ratchet**:上 4 寫 + 10 讀全在既有未改 tab-live.js text,E1a **不新增 call-site**;新 `view-live.js` 自身只 `fetch('/static/tab-live.html')` + `fetch('/static/tab-live.js')`(GET,registry 完整性 src)——**須確認此 2 個 static GET ∈ authoritative/allowlist**(risk 的 `/static/tab-risk.html`+`/static/risk-tab.js` 已過 5b,同型應通過;E1a/E2 核)。

---

## 8 · refreshPage 危害核查(item 8)——**REFUTE,byte-parity 保留**

brief 疑 `onclick="refreshPage({ force: true })"`(html:317)做 `location.reload()` 重載整殼(原生 view 回歸)。**源碼實測 REFUTE**:
- `refreshPage(options)`(js:462-512)是 **async 資料刷新** fn:`Promise.allSettled([checkLiveEngineStatus(), loadTrustStatus()])` → 若 engine==live 再節流拉 dashboard/metrics/edge/pnl。**無** page reload。
- 全檔 grep `location.(reload|href|assign|replace)|window.location=|document.location` = **0 命中**;`location.` 僅 3 處**唯讀** `location.origin`(js:273/284 postMessage 目標 origin、js:1903 message origin 驗證)。

**處置**:html:317 `refreshPage({force:true})` 鈕**byte-parity 保留**(clone 進 .live-view,onclick re-export window.refreshPage);其行為=資料重刷,**不**重載殼、**不**回歸原生 view。**不需**原生安全覆蓋、不需裁決。item 8 clean。

**附帶(§9 OPEN-3 相關,非 full-reload)**:`openLiveRisk`(js:265,`window.parent.postMessage('openclaw-console-switch-tab', tab:'risk')`)+ `openLiveAuth`(js:277,tab:'governance')= 跨-tab 深連結跳轉。實測**新 shell.js 不監聽** `openclaw-console-switch-tab`(僅 legacy console.html 監聽;tab-demo.html 亦用之=**已遷 demo 共享的既有 gap**)→ 在原生殼此二鈕 **no-op**(便利跳轉失效,**非**安全/寫回歸;operator 可手動點 Risk/Governance tab)。見 §9 OPEN-3。

---

## 9 · pause/resume 輪詢暫停(item 9)

### 9.1 輪詢盤點
- **唯一 setInterval**:`_liveRefreshTimer = setInterval(() => refreshPage({fromTimer:true}), LIVE_REFRESH_MS=15000)`(js:1893),由 `startLiveRefreshLoop`(js:1891)/`stopLiveRefreshLoop`(js:1896)管理。
- **sub-refresh 非獨立 interval**:dashboard 30s / metrics 30s / edge 120s / pnl 60s 是 `refreshPage` 內 `now - _lastXxxRefreshMs >= …` **時戳節流**(js:492-508),掛在單一 15s master tick → **pause 只需停 `_liveRefreshTimer` 一個**。

### 9.2 pause/resume 手法——**postMessage 復用既有 visibility listener(零源修改)**

**★ 關鍵:shell.js `notifyViewVisibility` 對原生 view 呼 `api.pause()`/`api.resume()`(shell.js:194-201),不 postMessage**(iframe view 才 postMessage `openclaw-tab-visibility`,shell.js:206-210)。但 tab-live.js **已內建** `openclaw-tab-visibility` listener(js:1902-1912,收 tab==='live')。故 view-live.js 的 pause/resume 自行 `window.postMessage` 該訊息 → 觸 tab-live.js listener → 復用其 start/stop 邏輯(governance §9 同型)。

- **pause**(view 隱藏 / 瀏覽器不可見):
  `window.postMessage({type:'openclaw-tab-visibility', tab:'live', visible:false}, location.origin)`
  → tab-live.js listener(js:1904 檢 `tab!=='live'` return;`ev.origin` 檢 js:1903)設 `_liveTabVisible=false` → `stopLiveRefreshLoop()`(清 `_liveRefreshTimer`,js:1910)。**隱藏不續打後端=freshness/safety,鏡像 iframe 暫停語義。**
- **resume**(view 顯示):
  `window.postMessage({type:'openclaw-tab-visibility', tab:'live', visible:true}, location.origin)`
  → listener 設 `_liveTabVisible=true` → `startLiveRefreshLoop()` + `refreshPage({force:true})`(js:1906-1908,首拉 + 啟輪詢)。

**★ 為何 postMessage 復用最佳(vs 暴露 start/stop 到 window)**:tab-live.js 的 listener **恰在殼 window**(合併 script 跑於殼 realm,非 iframe);殼內 `window.postMessage(...)` 同 window 可收 + origin 相符(`location.origin`)。且 live 的 listener **已含 start+首拉**(比 governance 更完整——governance 需另呼 `__ocGovLoadAll`),故 view-live.js resume **不需**額外呼 refresh/loadAll,純 postMessage。`tab:'live'` 對齊 shell.js visibility 用 `tab:v.visId`(live 的 visId='live',shell.js:90)+ listener 檢 `tab==='live'`(js:1904)。

**★ 雙保險(byte-parity 附帶)**:tab-live.js 另含 `document.addEventListener('visibilitychange',…)`(js:1914)——跑於殼 document,瀏覽器 tab 真隱藏時 `_isLiveTabRefreshVisible()`(`_liveTabVisible && visibilityState!=='hidden'`)判 false → stopLiveRefreshLoop。與 shell.js:215 的 visibilitychange 冪等收斂(startLiveRefreshLoop 有 `if(_liveRefreshTimer) return` guard,js:1892)。當 operator 在他 view 時 `_liveTabVisible=false`(pause 已設)→ 瀏覽器可見性切換不誤啟 live 輪詢。

- **built/wired guard**:pause/resume 在 `!built||!wired` 時 no-op(postMessage 前置檢查);built guard 防 resume 重跑 IIFE(不重註冊 listener/不雙 setInterval)。

---

## 10 · 殼接線(item 10)

### 10.1 shell.js VIEWS entry
現 `{ id:'live', lane:'crypto', hash:'#/crypto/live', src:'/static/tab-live.html', visId:'live', label:'實盤 Live', badge:'live', flag:true, live:true }`(shell.js:90,**無 `iframe:` 鍵 → 預設 iframe:true**)。E1a **加 `iframe:false`**(保留 `flag:true` + `live:true` + `badge:'live'`;`live:true` 供 §0.2 熱紅 lane 標識,router 零改其他)。

### 10.2 shell.html `<link>` + `<script>` 接線
- **`view-live.css`**:加 `<link rel="stylesheet" href="/static/view-live.css?v=…">` 於 shell.html **~line 74 後**(view-governance.css 旁),附 MODULE_NOTE 註釋(比照 view-risk.css/view-governance.css 兩段)。
- **`view-live.js`**:加 `<script src="/static/view-live.js?v=…">` 於 shell.html **~line 260 後**(view-demo.js 旁),**於 shell.js 前載**以註冊 `window.OC_NATIVE_VIEWS['live']`。附 MODULE_NOTE(§3 硬化 / 4 寫 / postMessage pause / body.live-mode-* 提示)。
- common* 殼已載(§A.2),live 無其他外部 JS 依賴 → view-live.js 只 fetch tab-live.html + tab-live.js。

### 10.3 OC_NATIVE_VIEWS 註冊
`window.OC_NATIVE_VIEWS['live'] = { render:renderLiveView, resume:resumeLiveView, pause:pauseLiveView }`(+ 具名 `window.renderLiveView/resumeLiveView/pauseLiveView` 導出)。render:建 `.live-view` 宿主 → 併發 fetch tab-live.html + tab-live.js → DOMParser 注入 body DOM(byte-parity clone,skip script/style/ocInjectBaseCSS)→ 串接 tab-live.js text + re-export(§3.A 強化發現)→ 全新 `<script>` 節點 IIFE-wrap 重跑(built guard 只首渲)。首拉 + 啟 15s 輪詢由重跑段自帶(js:1923-1924)。

### 10.4 view-live.css port + born-clean + **body.live-mode-* 新形(L1,§9 OPEN-1)**
`<style>` 塊(html:20-285)搬入 view-live.css,**外層 `.live-view` scope**(鏡像 view-risk.css `.risk-view`),但**三處 port 分歧須 E1a 精確處理**:

1. **`html, body {…}`(html:23-29)→ DROP,不 port**。此塊在 legacy iframe styled iframe 自身 html/body(margin:0/overflow/background/color);原生 port 會**覆蓋殼 html/body 破 chrome**(同 ocInjectBaseCSS 危害)。殼已 own html/body。**丟棄**(非 byte-parity 例外,理由=殼 chrome 所有權,同 risk/governance skip ocInjectBaseCSS 的 `body{padding}`)。→ **OPEN-2**。

2. **`body.live-mode-*` 主題 override 規則(html:173-191)→ body-anchored port(不天真 scope 進 `.live-view`)**。reused JS `_applyLiveModeUI` 於 **`document.body`(殼 body)** 加/移 `live-mode-mainnet`/`live-mode-livedemo`/`live-mode-unconfigured`(js:316/317/350/352/354)。CSS 選擇器 `.live-mode-mainnet .live-warn-bar` 需 `.live-warn-bar`(在 .live-view 內,body 後代)可達。若前綴成 `.live-view .live-mode-mainnet .live-warn-bar` → **永不匹配**(mode class 在 .live-view 的**祖先** body 上)。**推薦(OPEN-1)**:port 成 `.live-mode-mainnet .live-view .live-warn-bar {…!important}`(在選擇器鏈保留 .live-view 作 scope 紀律,同時尊重 body-anchored class;computed byte-parity 保全——所有 `.live-warn-bar` 皆在 .live-view 內,cascade 結果同 legacy)。**fallback**:`.live-mode-mainnet .live-warn-bar`(不含 .live-view,靠 class 名 live-unique 免碰撞;逐字 byte-identical)。E2/E3 裁。
   - 附:reused JS 於殼 body 留 `live-mode-*` class(導覽離開 live 後不清)**無害**(.live-warn-bar 等隨 view hidden;class live-unique,他 view 無匹配後代);view-live.js pause() **不**移除(移除=JS 行為新增,違 byte-parity)。文檔記之。

3. **其餘規則(base .live-*/.trust-*/.oc-dialog*/.integrity-fail-view/.real-funds-badge/.btn-emergency 等)→ `.live-view` scope 前綴**。**⚠ `.oc-dialog` / `.oc-dialog-overlay`(html:144-162)**:WP-01 Wave 1 已拆舊雙層 dialog(html:587-591 註;do* 改走 openTypedConfirmModal SDK)→ 此二規則為**死 CSS**(無 live 元素用);但 SDK typed-confirm modal 於殼**可能**用同名 `.oc-dialog` → **必須 `.live-view` scope**(不可 unscoped,否則污染殼 SDK modal skin)。scope 後為無害死規則(byte-parity 保留,不刪=不改檔語義)。

**born-clean ratchet(0/0/0,R77)**:view-live.js/css 新檔**零 inline style 屬性、零裸 `#hex`、零新框架、零 `<style>` 字面於註釋**;動態值走既有 `.style`(在 reused tab-live.js text,非 E1a 新碼,同 governance §6/§8)。既有 rgba 色字面 byte-parity 搬(§12)。

---

## 11 · born-safety discover guard 對齊(item 11,E3 R77 LOW-1)

**現況**:view-governance.js/view-risk.js 的 `onAttrBareAssignTargets(htmlText)`(view-risk.js:173,line 210 `onAttrBareAssignTargets(htmlText).filter(...)`)**只掃 htmlText,不掃 combined** → 模板注入的裸賦值是盲區。

**live 規劃**:view-live.js 的 F1 born-safety guard **掃 html ∪ combined**(對齊 §3.A 的 discoverOnHandlerNames 掃描域),使模板注入的任何 `onclick="IDENT=…"`(未來若有)亦被 `∩ topLevelDeclaredNames` 檢出。**live 現況此集 = ∅**(§4,closeLivePosition 是呼叫非賦值;`this.dataset.*` 是 member 讀)——但 guard 掃描域對齊是 born-safety 紀律(不留 template-injected 盲區),E1a 照此實作。

**coverage-debt 建議(§9 OPEN-4)**:是否**本輪一併回改** view-governance.js/view-risk.js 的 `onAttrBareAssignTargets` 使掃 html∪combined(消 E3 R77 LOW-1 的既有盲區)——標為 **coverage-debt**,由 PM 裁本輪隨 live 做(觸 2 個已審交易關鍵檔,須各自 E2 byte-parity 復審)或獨立輪。PA 傾向**獨立 coverage-debt 輪**(不擴 live 遷移 blast radius;live 自身 guard 已對齊)。

---

## 12 · 雙主題(item 12,承 design/12 P1.3)

view-live.css 冷家族 rgba(design/12 §2 四 `--ov-*-rgb` 三元組)+ `--live` 熱紅 canon-6 兩主題不稀釋:

### 12.1 冷家族 rgba(design/12 inventory,view-live.css born-clean 應直接 token 化)
tab-live.html `<style>` 塊的 design/12 冷家族(近黑 13,17,23 / 冷灰 139,148,158)= **3 spot / 4 literal**:
| html:行 | 現值 | design/12 family | born-clean 目標 |
|---|---|---|---|
| html:211 | `rgba(139,148,158,0.05)` | 冷灰 → `--ov-muted-rgb` | `rgba(var(--ov-muted-rgb),0.05)`(integrity-fail-view 底) |
| html:212 | `rgba(139,148,158,0.4)` | 冷灰 → `--ov-muted-rgb` | `rgba(var(--ov-muted-rgb),0.4)`(integrity-fail-view dashed 框) |
| html:275 | `rgba(13,17,23,0.5)` | 近黑 → `--ov-panel-rgb` | `rgba(var(--ov-panel-rgb),0.5)`(live-pnl-sparkline 底) |
| html:282 | `rgba(13,17,23,0.5)` | 近黑 → `--ov-panel-rgb` | `rgba(var(--ov-panel-rgb),0.5)`(live-dust-details 底) |

**推薦**:view-live.css **born-clean 直接 token 化**上 4 處(玄夜展開 = 原字面 byte-identical;帛晝自動暖化),對齊 view-risk.css:158 已用 `--ov-accent-rgb` 的既定慣例——view-live.css 生而 dual-theme-aligned,**免**未來 P1.3-c 對 live 的回改。`--ov-*-rgb` token 由 design/12 P1.3-a 已定義入 tokens.css(E1a 核實已 land;若未 land 則此 4 處暫留 rgba 字面 byte-parity + 標 P1.3 follow-up)。

### 12.2 **不可動**清單(canon-6 / 非冷家族 identity,byte-parity verbatim)
- **`--live` 熱紅**(html:37/47/76/120 `var(--live)`/`var(--live-bg)`)= canon-6,兩主題由 tokens.css `--live` 帛晝加深 #BE1E27(design/12 §3 retune)承載;view-live.css **只用 `var(--live)` verbatim,禁改/禁 tokenize**。
- **紅家族 `rgba(239,68,68,*)`**(html:127/128/137/174/197 emergency/mainnet/real-funds)= --neg 系身分,**非冷家族**,verbatim(design/12 §2.3 規則 6 DEFER)。
- **橙家族 `rgba(249,115,22,*)`**(html:181/182/185/188/190/204 livedemo)= 橙身分(不誤升熱紅),**非冷家族**,verbatim。
- **綠/琥珀 `rgba(34,197,94,*)`/`rgba(210,153,34,*)`**(html:235/236 trust-bar ok/warn)= --pos/--warn 系,**非冷家族**,verbatim。
- **scrim `rgba(0,0,0,*)`**(html:147/157 dialog overlay/box-shadow)= 主題中性,**不遷、不 tokenize**(design/12 §2.3 規則 5)。
- **白 overlay `rgba(255,255,255,0.04)`**(html:100 live-table td 底線)= 白非冷家族;design/12 未覆蓋白 overlay,verbatim(pre-existing,P0.4 記錄)。
- **reused JS `.style`/TRUST_TIER_COLORS rgba**(tab-live.js:33-36 `rgba(100,116,139,.2)`/`rgba(34,197,94,.15)`/`rgba(59,130,246,.15)`;js:184/193/221 執行期 `.style`)= **未改 tab-live.js text 的 byte-parity 執行期行為**,非 view-live.css/js 新碼,不入 css、不算 E1a inline 違規(同 governance §6/§8)。

---

## 13 · E1a 交付物

**新增**:
- `view-live.js`(thin wrapper,類比 view-risk.js;含 §3.A 強化 handler 發現[掃 html∪combined,捕 closeLivePosition]+ §9 postMessage pause/resume + §4 born-safety guard 掃 html∪combined 產空集)
- `view-live.css`(html:20-285 `<style>` → `.live-view` scope;§10.4 三處 port 分歧[drop html,body / body-anchored mode 規則 / scope 死 .oc-dialog]+ §12 冷家族 token 化)
- shell.html 加 `<link view-live.css>` + `<script src=view-live.js>`(§10.2)

**改**:
- shell.js:90 VIEWS live entry 加 `iframe:false`(僅此一鍵;保 flag:true+live:true+badge:'live')

**零修改(reuse 正本 + rollback 錨)**:
- `tab-live.html`、`tab-live.js`

---

## 硬約束(E1a 遵行,operator §0.2 skin-only 重宿)

- **零自建寫路徑、零改道、零 fake-success**;§7 全 4 寫走既有 ocPost→Rust IPC(復用未改 tab-live.js text);typed-confirm(`START LIVE`/`STOP LIVE`/`EMERGENCY STOP`/`CLOSE ALL`)逐字保留不弱化。
- **五閘 / signed authorization.json gate / typed-confirm / 緊急停止·平倉·停止分離 / REAL FUNDS 常駐標識 / `--live` 熱紅 byte-parity**(§6)零弱化;live-hardening snapshot 守衛(R53)cutover 前 diff=0。
- **不放寬任何硬邊界、不觸交易邏輯、不授權任何 live 下單**(CLAUDE.md §四全數不變);opt-in 殼(flag:true 保留)+ flag 後備;寫仍走 Rust authority。
- 零 inline style / 裸 hex / 新框架(view-live.js/css 新碼);動態值走既有 reused `.style`(非新碼)。既有 rgba 色字面 byte-parity 搬(§12);冷家族 born-clean token 化。
- **E2 + E3 雙審(交易關鍵硬邊界)+ E4 回歸 + operator Linux 批驗才 cutover。** Mac 靜態(node --check + ratchet 0/0/0 新檔 + 5b + 註冊 smoke + R71 guard = 空集 + F1 guard = 空集)只證 source 事實;真渲染 / 4 寫真行為 / typed-confirm 真閘 / 五閘真 enforced / 三態(integrity-fail·phantom-view)/ REAL FUNDS·`--live` 真配色 / body.live-mode-* 真切換 / 15s 輪詢 pause = **NEEDS-LINUX runtime + operator**。

---

## OPEN(供 PM 裁,R85 候選)

- **OPEN-1(HIGH,§10.4-2)**:view-live.css 的 `body.live-mode-*` 主題 override 規則 port 形——reused JS 於**殼 body** 加 mode class,不能天真 scope 進 `.live-view`。**PRIMARY**=`.live-mode-mainnet .live-view .live-warn-bar {…!important}`(選擇器鏈保 .live-view 紀律 + 尊重 body-anchored;computed byte-parity)。**FALLBACK**=`.live-mode-mainnet .live-warn-bar`(逐字 byte-identical,靠 class live-unique)。PA 傾向 PRIMARY。涉「原生殼內 body-level mode class 是否算 seam 手法」界定 → E2/E3 裁。**這是 live 相對 risk/governance 的唯一 CSS 新形。**
- **OPEN-2(LOW,§10.4-1)**:`html, body {…}`(html:23-29)DROP 不 port(殼 chrome 所有權,同 skip ocInjectBaseCSS `body{padding}`)。PA 傾向 DROP;E2 確認殼 html/body 不受影響。
- **OPEN-3(LOW,§8)**:`openLiveRisk`/`openLiveAuth`(`openclaw-console-switch-tab` 深連結)在原生殼 **no-op**(shell.js 不監聽此訊息;**與已遷 demo 共享的既有 shell-level gap**,tab-demo.html 亦用)。**PA 傾向 accept**(byte-parity JS 未改;便利跳轉失效,**非**安全/寫回歸,operator 可手動點 tab)+ 標 **shell coverage-debt**(未來 shell.js 增 `openclaw-console-switch-tab` handler,影響所有 view,**出 live 遷移範圍**)。
- **OPEN-4(LOW,§11)**:是否**本輪一併**回改 view-governance.js/view-risk.js 的 `onAttrBareAssignTargets` 掃 html∪combined(消 E3 R77 LOW-1 template-injected 盲區,coverage-debt)。PA 傾向**獨立 coverage-debt 輪**(不擴 live blast radius;live 自身 guard 已對齊掃 html∪combined)。由 PM 裁。
- **OPEN-5(LOW,§3.A)**:E1a 的 `discoverOnHandlerNames` 用 governance 強化版 verbatim(掃 html∪combined + 保留字濾 + 頂層函式交集)vs live-minimal(僅掃 combined,first-token)。**PA 傾向復用 governance 強化版**(跨兩交易關鍵遷移一致 + 未來免回改;必改硬核=掃 combined 捕 closeLivePosition,否則個別平倉鈕死)。

---

## PM 裁決(R85,PM/Conductor 定案)

五 OPEN 皆屬遷移 seam 設計選擇(非 operator/治理裁量,§0.2 skin-only 重宿範圍內),逕裁如 governance R76 先例。PM 另獨立核驗三安全關鍵宣稱屬實(源碼實測):**F1 空集**(js:1047/1086/1119/1149 全 `await openTypedConfirmModal(...)` Promise 式,全檔零 `window.X=`/`_*Pending=`/`_*Callback=` 裸賦值)、**closeLivePosition 模板注入**(def js:1177,注入 js:837 innerHTML,不在 html;既有 discoverer 靠 `button[onclick^="closeLivePosition"]` js:440 捕,遷移必掃 combined 否則個別平倉鈕死)、**寫全走 Rust IPC**(6 call-site 全 `ocPost('/api/v1/live/...')`,零裸 `fetch`/`XHR`)。裁決:

- **OPEN-1 → PRIMARY(採 PA)**:`.live-mode-mainnet .live-view .live-warn-bar {…!important}`。理由:`.live-view` scope 前綴是全遷移一致的隔離紀律(防 mode-override CSS 洩漏至未來任何 `.live-warn-bar`-名元素);因所有 `.live-warn-bar` 皆在 `.live-view` 內,computed 結果與 legacy byte-identical。**E2/E3 硬核驗**:mainnet 態 `--live` 熱紅**真的**套用(canon-6 salience 不弱化)+ computed-equivalence。FALLBACK(無 `.live-view`)僅 E2 判 PRIMARY 有具體 cascade 反例時啟用。
- **OPEN-2 → DROP(採 PA)**:`html, body {…}`(html:23-29)不 port。殼 own html/body;port 會覆蓋殼 chrome(同 risk/governance skip ocInjectBaseCSS `body{padding}` 先例)。E2 確認殼 html/body 不受影響。
- **OPEN-3 → ACCEPT + shell coverage-debt(採 PA)**:`openLiveRisk`/`openLiveAuth` 深連結在原生殼 no-op=byte-parity JS 未改,便利跳轉失效**非**安全/寫回歸(operator 可手動點 Risk/Governance tab),與已遷 demo 共享既有 gap。標 **shell coverage-debt**(未來 shell.js 增 `openclaw-console-switch-tab` handler,影響所有 view,**出 live 遷移範圍**)。
- **OPEN-4 → 本輪 in-arc 隨遷(PM 逆 PA 傾向;依 operator §0.2 item-1)**:operator §0.2 item-1 明文「並批 born-safety discover guard 對齊(E3 R77 LOW-1)**隨 live 遷移一併處理**」——故**不**deferred 到獨立 operator-gated 輪(R84 Fix 2 曾誤 SKIP)。**分兩層**:①**live 自身** guard(`onAttrBareAssignTargets`)掃 html∪combined=E1a live impl **強制內含**(§11,捕 closeLivePosition 的裸賦值形);②**回改 view-governance.js/view-risk.js** 的 guard 消 E3 R77 LOW-1 既有盲區=**live impl 落地後同弧的獨立窄 checkpoint**(各觸 1 已審交易關鍵檔,各自 E2 byte-parity 復審;不擴 live 本身 blast radius)。即「一併處理」=同一 live 遷移弧內完成、不無限期 defer,但各 commit 窄化。序:live impl(R86+)→ governance/risk guard back-fix(緊隨)。
- **OPEN-5 → 復用 governance 強化 discoverer(採 PA)**:E1a 的 `discoverOnHandlerNames` 用 view-governance.js 強化版 verbatim(掃 html∪combined + 保留字濾 + 頂層函式交集)。跨兩交易關鍵遷移一致 + 未來免回改;**必改硬核**=掃 combined 捕 closeLivePosition,否則個別平倉鈕 ReferenceError。

**E1a 交付即照本規格(§A-§13 + 硬約束 + OPEN 裁決)實作 view-live.js + view-live.css;二源檔(tab-live.html/tab-live.js)零修改(= reuse 正本 + 回滾錨)。** 交易關鍵=E1a→E2→E3→E4 全鏈(E2+E3 雙審為 operator §0.2 硬邊界),operator Linux 批驗才 cutover。**實作留 R86**(交易關鍵全鏈太大,避同輪 context 耗盡於最關鍵 view 中途——承 governance R76→R77 先例)。
