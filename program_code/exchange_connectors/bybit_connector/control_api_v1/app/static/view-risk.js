/*
 * view-risk.js — 玄衡原生 view「風控 / Risk & Stops」(Phase 2 第 15 個 iframe→原生遷移)
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:把 legacy `tab-risk.html`(iframe 後備)遷成玄衡殼內的**原生 view**。
 *   risk = **風控中樞**(風險總覽 / 引擎風控配置 Paper·Demo·Live / P0·P1·P2 三層 / 止損 · 倉位 ·
 *   冷卻 · H0 門控 · 自動調整 · AI 止損建議 · AI 預算 · Danger Zone);**交易關鍵四者之一**——
 *   含 **risk_config TOML 寫**(每引擎 global config)+ **LIVE engine risk save confirm**(§3 硬化)。
 *   策略=**復用遷移**:fetch tab-risk.html → 注入其 <body> risk DOM(byte-parity)→ 把其內聯
 *   <script>(switchRiskTab + 2 IIFE)**與外部 `risk-tab.js` 的 text 串接進「同一個共享 IIFE」重跑**。
 *   **tab-risk.html / risk-tab.js / governance.js 零修改(reuse 正本 + rollback 錨)。**
 *
 * ★ skin-only 只換皮不改邏輯(§3 硬化逐字保留零弱化,本遷最高關注):
 *   view-risk.js **零自建寫路徑**——只 fetch + clone DOM + 重跑既有內聯 script + risk-tab.js text。
 *   §3 硬化面全在復用的 script 內 byte-parity 續生效,IIFE-wrap **不觸碰**任何 confirm / 寫 / diff 邏輯:
 *   ① **confirmLiveEngineRiskSave**(risk-tab.js:254)+ `_wrapLiveSave`/`_liveRiskSavePendingCallback`:
 *      _selectedRiskEngine==='live' 的 save 全走 dlg-engine-live-confirm 對話框 gate,verbatim 保留;
 *      **F1(E2 MED)修復**:tab-risk.html:244 取消鈕 inline `onclick="…;_liveRiskSavePendingCallback=null"` 在殼
 *      **global 域**執行,IIFE-wrap 後裸賦值只會建無關 window 屬性、不清 IIFE-local pending → cancel 未真 cancel。
 *      view-risk.js 於 IIFE 末尾對「on* 裸賦值 ∩ 頂層宣告名」(=_liveRiskSavePendingCallback)建 window↔IIFE-local
 *      getter/setter proxy → cancel 賦值觸 setter 清 IIFE-local → cancel 語義**逐字還原**(arming/寫/read 路徑不變);
 *   ② **diff preview**(`_DIFF_MAP` / `_updateDiffHighlights` / `_resetDiffHighlights`,risk-tab.js:298-353):
 *      輸入值 ≠ 已載入 dataset.original 時右側顯示格 .oc-diff-changed 高亮 + 「← was: X」標籤,verbatim;
 *   ③ **reset-cooldown / unhalt-session** 前置 `openConfirmModal(...)` gate(risk-tab.js:603-604 / 610-611),verbatim;
 *   ④ **_riskFormDirty**(risk-tab.js:280):有未保存編輯時 15s loadAll 跳過輸入框填充(防覆寫 in-flight),verbatim;
 *   ⑤ **REAL FUNDS 常駐標識**(engine-risk-live-warn / dlg-engine-live-confirm 的「真實資金」文案,tab-risk.html:229/239)
 *      + **`--live` 熱紅**(.etab-btn.is-active-live / .rc-live-warn / .rc-dlg-danger / .rc-btn-live-confirm,view-risk.css 逐字)
 *      → live 引擎態不稀釋。**本檔不得繞過 / 短路 / 改任何 confirm 或寫。**寫全走 Rust 引擎 IPC。
 *
 * ★★ 共享 IIFE 如何串接 inline + risk-tab.js(本遷關鍵手法):
 *   tab-risk.html 的內聯 <script>(頂層 `function switchRiskTab` + hoistRiskEngineSelector / dirty-bar 兩 IIFE)
 *   與外部 `risk-tab.js`(頂層 const/let/function 全域詞法 + 底部自初始化 loadAll+ocStartRefresh+loadAiBudget)
 *   **原皆全域、互相引用**(risk-tab.js:267 的 message handler 呼 inline 定義的 switchRiskTab;onclick 反向呼
 *   risk-tab.js 的函式)。若各自 raw 重跑則跨-script 見不到彼此。**處置**:fetch tab-risk.html 的 inline text
 *   **+** fetch /static/risk-tab.js 的 text,**依原頁載入序(inline 先,risk-tab.js 後)串接**成單一大 text,
 *   再包進**單一** `(function(){ <inline + risk-tab.js>; <re-export onclick>; window.__ocRiskLoadAll=…; })();`。
 *   IIFE 內兩段共享同一詞法環境 → switchRiskTab 與 risk-tab.js 函式互見(如原全域),confirm/寫/diff 全 verbatim。
 *
 * ★★★ 跨-view 全域詞法隔離(paper ↔ settings ↔ overview ↔ risk 共存;R71 guard 非協商):
 *   risk-tab.js 頂層宣告大量 `const/let`(RISK_LEVEL_NAMES / RISK_LEVEL_COLORS / _AI_BUDGET_SCOPES / _DIFF_MAP /
 *   _RISK_INPUT_IDS / _tpEl、`let _currentRiskLevel / _selectedRiskEngine / _liveRiskSavePendingCallback /
 *   _paperRiskEngineEnabled / _riskFormDirty / _lastAIAdvice`)+ 頂層 `async function loadAll`。classic script 經
 *   raw `appendChild(<script>)` 重跑=進**同一 Realm 共享 global lexical**;頂層 `const/let/class` 跨 script 重宣告
 *   → SyntaxError,整段不執行 → view 靜默功能死。且 risk 的 `loadAll` 若 raw 重跑會**撞 paper 的 window.loadAll**
 *   (paper.resume 讀之)。
 *   **處置**:串接後的大 text 包進 IIFE → 頂層 const/let/class 成 IIFE-local → 不進 global lexical → 過 R71 guard
 *   (risk 判 isolated,貢獻空集)。onclick 函式(switchRiskTab / submitRiskOverride / selectRiskEngine /
 *   confirmLiveEngineRiskSave / saveStopSettings / savePositionSettings / saveCooldownSettings / saveH0ShadowMode /
 *   toggleDynamicRisk / toggleTPInputs / askAIStopLoss / applyAIAdvice / showRiskOverrideModal / closeRiskOverrideModal /
 *   resetCooldown / unhaltSession / saveAiBudget)由 fetched html **自動發現**(掃全文 `on*="ident("` 超集,非硬編)
 *   後 re-export 至 window,onclick 屬性可達;此 17 名與 paper(sessionAction / closePosition / …)、settings
 *   (demoAction / configAction / …)、overview(confirmAction / confirmMode / …)onclick 集**無交集**(實測 grep),
 *   re-export 無 last-writer-win 破壞。`loadAll` **不**在 on* 集、**不寫 window.loadAll**(避免撞 paper),改暴露
 *   `window.__ocRiskLoadAll` 供 pause/resume。eval 當下 risk-tab.js 尾端 selectRiskEngine()+loadPaperRiskAvailability()+
 *   loadAll()+ocStartRefresh(loadAll,15000)+loadAiBudget()+setInterval 用 IIFE 內詞法 binding,首拉 + 啟輪詢照常。
 *
 * ★★★★ 與 brief 的關鍵出入(以源碼為準,已於回報指出):
 *   ① brief 稱「9 inline script」;源碼實測 tab-risk.html <body> 只有 **2 個內聯 <script>**:行 19
 *      (`ocAuthCheck(); ocInjectBaseCSS();`,跳過)+ 行 643-681(switchRiskTab + hoistRiskEngineSelector /
 *      dirty-bar 兩 IIFE,**單一塊**),外加行 683 外部 `<script src="/static/risk-tab.js">`(承全部 risk 邏輯)。
 *      故「重跑內聯 script」= 重跑這唯一 inline 塊 + 併入 risk-tab.js text。
 *   ② brief 稱「2 style 塊」;源碼實測 tab-risk.html body 只有 **1 個頁內 style 塊**(行 21-104,id=rc-page-style);
 *      另一「命中」是 risk-tab.js:10-18 於 eval 當下**動態注入** head 的 oc-modal CSS(id 守衛,byte-parity 復用,
 *      非 tab-risk.html 的頁內塊)。頁內塊搬入 view-risk.css;oc-modal 由 risk-tab.js 執行期自注入,不重複。
 *   ③ **pf-toggle 開關**:tab-risk.html 頁內 style 塊 **未**定義 .pf-toggle/.slider,且 ocInjectBaseCSS 亦無 →
 *      legacy iframe 內該 toggle 本就渲染為**原生 checkbox**(空 slider span)。故 view-risk.css **刻意不 port**
 *      pf-toggle/slider(port 之即 skin 變更,違 byte-parity)——原生 checkbox 與 legacy 一致。此為源碼事實非缺陷。
 *
 * 注入 / 重跑(phase4「注入片段 + 重跑內聯 script」pattern,套用於 tab-risk.html + risk-tab.js):
 *   render → 併發 fetch /static/tab-risk.html + /static/risk-tab.js → DOMParser 解析 html → 把 <body> risk DOM
 *   逐節點 clone 進 `.risk-view` 宿主(byte-parity id/class/onclick;子分頁 nav + 引擎選擇器 + P0/P1/P2 +
 *   止損 / 倉位 / 冷卻 / H0 / 自動調整 / AI 建議 / AI 預算 / Danger Zone + risk-dirty-bar + live-confirm 對話框)
 *   → 再把 inline 塊 + risk-tab.js text 串接後以全新 <script> 節點 IIFE-wrap 重跑。
 *   **跳過**:①外部 <script src>(common* / governance.js 殼已載入,勿重複;**risk-tab.js 的 text 另 fetch 併入 IIFE**,
 *   不作 <script src> 重載——避免其底部自初始化在無 DOM 的殼 boot 期跑);②首個內聯 <script>=`ocAuthCheck();
 *   ocInjectBaseCSS();`(殼 boot 已 ocAuthCheck;ocInjectBaseCSS 注入 body{padding}+`*` reset 破殼 chrome,禁呼);
 *   ③頁內 style 塊(由 view-risk.css 以 `.risk-view` scope 供給,含 --live 熱紅 / rc-dirty-bar / danger-zone,ratchet born-clean)。
 * 寫面(byte-parity 復用,零新寫路徑,全在 risk-tab.js 未改的 text 內,經 Rust 引擎 IPC):
 *   governance/risk/override(83)、paper/risk/config/global + /engine/{engine}/global(save config,241-242)、
 *   paper/layer2/trigger(AI 諮詢,564)、**paper/risk/reset-cooldown 前置 openConfirmModal**(603-604)、
 *   **paper/risk/unhalt-session 前置 openConfirmModal**(610-611)、ai_budget/config(POST,1125)、
 *   strategy/dynamic-risk/toggle(987)、settings/paper-engine(187,GET)。confirm 全保留,response-gated 非 fake。
 * canon-7(未接數據三態,非假 active):r-engine-status 讀取失敗顯「✗ 未連接」非假「運行中」;risk API 不可達顯「⚠」;
 *   governor 源不可得顯「—」;--live 熱紅在 live 引擎態顯示不稀釋。皆由復用 script 原樣渲染,本檔零 fake。
 * visibility 語義:pause=ocStopRefresh()(停 15s loadAll 輪詢,隱藏不續打後端=freshness/safety);
 *   resume=首拉 __ocRiskLoadAll() + ocStartRefresh(__ocRiskLoadAll, 15s) 重啟。ocStartRefresh 用 common.js 全域
 *   單例 `_ocRefreshTimer`(殼內呼者僅 paper / settings / overview / risk,同時只一 view active,pause 清 timer,單例零爭用)。
 *   **行為守恆限制**:risk-tab.js 尾端 `setInterval(loadAiBudget, 30000)` 是 IIFE-local,pause **無法**外清 →
 *   隱藏後續跑(唯讀 GET /api/v1/ai_budget/status,無害,無寫);built guard 防 resume 重跑 IIFE 避免雙 setInterval(同 earn/linucb 先例)。
 * 依賴(全復用,不重造):common.js($ / ocApi / ocPost / ocStartRefresh / ocStopRefresh / ocExplain / ocToast /
 *   ocSetText / ocSetHtml / ocEsc / ocChip / ocPct / ocPctVal / ocBalance / ocInitFx)、common-formatters.js、
 *   common-modals.js(openConfirmModal)、fetch_with_csrf.js(ocCsrfHeaders);governance.js(殼已於 overview 遷移載入,
 *   勿重複;risk-tab.js 實測**不呼** governance.js 全域,故此依賴 nominal)。view-risk.css 供 `.risk-view` scope 樣式。
 * 誠實邊界:靜態(node --check + ratchet + 註冊 smoke + R71 guard)只證 source 事實;**真渲染 / risk_config 真寫行為 /
 *   confirmLiveEngineRiskSave 真閘 / diff 真預覽 / reset-cooldown·unhalt 真 confirm / REAL FUNDS·--live 真配色 /
 *   三態徽 / 15s 輪詢 = NEEDS-LINUX runtime + operator**,不由本刀 attest。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  // ── 模塊級狀態 ──
  var host = null;              // 原生 <section> 宿主(shell 注入)
  var root = null;              // `.risk-view` 內層宿主(view-risk.css scope root)
  var built = false;            // rendered guard(只首渲一次;防雙 fetch / 雙重跑 / 雙啟 setInterval(loadAiBudget))
  var wired = false;            // 共享 IIFE 已重跑並定義全域函式 + 啟輪詢(併發 fetch 完成後轉真)
  var POLL_MS = 15000;          // 輪詢間隔(byte-parity risk-tab.js ocStartRefresh(loadAll, 15000))
  var TAB_RISK_URL = '/static/tab-risk.html';   // src 保留=registry 完整性 + 回滾錨,同時作 DOM + inline 復用來源
  var RISK_TAB_JS_URL = '/static/risk-tab.js';  // risk-tab.js text 另 fetch,併入共享 IIFE(不作 <script src> 重載)

  function warn(msg, e) { try { console.warn('[view-risk] ' + msg, e || ''); } catch (_) {} }

  // fail-closed 可見化:fetch / 解析失敗 → 顯錯不崩(對齊殼 iframe 載入失敗語義,不留空白)。
  function showLoadError(e) {
    warn('tab-risk.html / risk-tab.js 載入失敗 — Risk view inactive', e);
    if (root) {
      root.innerHTML =
        '<div class="oc-subtab-placeholder">風控載入失敗 — 可切其他視圖或返回舊版 Console(詳見瀏覽器 console)</div>';
    }
  }

  // 自動發現 fetched html 內所有 on* 事件屬性(onclick/onchange/…)引用的頂層函式名。
  //   非硬編(隨錨新增函式自動涵蓋);掃 html 全文=DOM 靜態屬性 ∪ 內聯 script 模板字串產出的 on* 的超集。
  //   捕 `on<event>="<identifier>(` 的 identifier。risk 現況集(17)={switchRiskTab, showRiskOverrideModal,
  //   closeRiskOverrideModal, submitRiskOverride, selectRiskEngine, confirmLiveEngineRiskSave, toggleTPInputs,
  //   saveStopSettings, savePositionSettings, saveCooldownSettings, saveH0ShadowMode, toggleDynamicRisk,
  //   askAIStopLoss, applyAIAdvice, resetCooldown, unhaltSession, saveAiBudget}(全與 paper/settings/overview 無交集)。
  function discoverOnHandlerNames(htmlText) {
    var names = {};
    var re = /on[a-z]+\s*=\s*["']\s*([A-Za-z_$][\w$]*)\s*\(/g;
    var m;
    while ((m = re.exec(htmlText)) !== null) { names[m[1]] = true; }
    return Object.keys(names);
  }

  // ── F1(E2 MED)修復輔助 1:掃 script text 的**深度 0(頂層)** let/const/var 宣告名。────────────
  //   字元級掃描(跳 字串/樣板/行·塊註釋/regex 字面,追蹤 (){}[] 深度,只在深度 0 捕關鍵字後識別字);
  //   移植自 R71 guard 的 Python 掃描器語義。用途:交集 on* 裸賦值目標,找出 onclick 可能誤中的 IIFE-local binding。
  function topLevelDeclaredNames(text) {
    var names = {};
    var i = 0, n = text.length, depth = 0, prev = '';
    var idStart = /[A-Za-z_$]/, idCont = /[\w$]/, ws = /\s/;
    var regexPrev = '(,=:[!&|?{;}+-*%<>~^';
    var kwRegex = { 'return': 1, 'typeof': 1, 'instanceof': 1, 'in': 1, 'of': 1, 'new': 1, 'delete': 1, 'void': 1, 'do': 1, 'else': 1, 'yield': 1, 'case': 1, 'throw': 1 };
    while (i < n) {
      var c = text[i];
      if (c === '/' && text[i + 1] === '/') { var j = text.indexOf('\n', i); i = (j === -1) ? n : j; continue; }
      if (c === '/' && text[i + 1] === '*') { var k = text.indexOf('*/', i + 2); i = (k === -1) ? n : k + 2; continue; }
      if (c === '"' || c === "'") { var q = c; i++; while (i < n) { if (text[i] === '\\') { i += 2; continue; } if (text[i] === q) { i++; break; } i++; } prev = q; continue; }
      if (c === '`') { i++; var td = 0; while (i < n) { var ch = text[i]; if (ch === '\\') { i += 2; continue; } if (ch === '`' && td === 0) { i++; break; } if (ch === '$' && text[i + 1] === '{') { td++; i += 2; continue; } if (ch === '}' && td > 0) { td--; i++; continue; } i++; } prev = '`'; continue; }
      if (c === '/' && (prev === '' || regexPrev.indexOf(prev) !== -1)) { i++; var inCls = false; while (i < n) { var r = text[i]; if (r === '\\') { i += 2; continue; } if (r === '[') inCls = true; else if (r === ']') inCls = false; else if (r === '/' && !inCls) { i++; break; } else if (r === '\n') break; i++; } prev = '/'; continue; }
      if (c === '(' || c === '[' || c === '{') { depth++; prev = c; i++; continue; }
      if (c === ')' || c === ']' || c === '}') { depth--; prev = c; i++; continue; }
      if (idStart.test(c)) {
        var s = i; while (i < n && idCont.test(text[i])) i++;
        var word = text.slice(s, i);
        if ((word === 'let' || word === 'const' || word === 'var') && depth === 0 && !idCont.test(prev) && prev !== '.') {
          var mm = i; while (mm < n && ws.test(text[mm])) mm++;
          if (mm < n && idStart.test(text[mm])) { var e = mm; while (e < n && idCont.test(text[e])) e++; names[text.slice(mm, e)] = true; }
        }
        prev = kwRegex[word] ? ':' : word.slice(-1);
        continue;
      }
      if (!ws.test(c)) prev = c;
      i++;
    }
    return names;
  }

  // ── F1 修復輔助 2:掃 fetched html 所有 on* 屬性值,抓**裸賦值目標**(IDENT=…)。─────────────────
  //   前置 (^|[^.\w$]) 排屬性賦值(this.x= / el.value=);`=` 後 [^=] 排 ==/===;運算子致 >=/<=/!= 因
  //   ident 後非 `\s*=` 自然不中。回傳去重名陣列;與 topLevelDeclaredNames 交集後才建 proxy(只對真 IIFE-local binding)。
  function onAttrBareAssignTargets(htmlText) {
    var found = {};
    var attrRe = /on[a-z]+\s*=\s*("([^"]*)"|'([^']*)')/g;
    var m;
    while ((m = attrRe.exec(htmlText)) !== null) {
      var val = (m[2] !== undefined) ? m[2] : (m[3] || '');
      var asgn = /(^|[^.\w$])([A-Za-z_$][\w$]*)\s*=\s*[^=]/g;
      var a;
      while ((a = asgn.exec(val)) !== null) { found[a[2]] = true; }
    }
    return Object.keys(found);
  }

  // 重跑共享 script(inline 塊 + risk-tab.js text,IIFE 包裹隔離頂層 const/let/class 防跨-view 詞法重宣告
  //   SyntaxError + 撞 paper 的 window.loadAll——見 ★★★)。tab-risk.html 無 DOMContentLoaded,append 當下
  //   同步自呼 init(risk-tab.js 尾端 selectRiskEngine/loadAll/ocStartRefresh/loadAiBudget/setInterval),故直接重跑。
  function rerunSharedScript(inlineScriptTexts, riskTabJsText, htmlText) {
    // 自動發現 → 生成 re-export 碼:IIFE 內函式提升可見,逐名 try/catch 兜底(某名非真頂層函式→ReferenceError→跳過)。
    //   identifier 由正則限定 [A-Za-z_$][\w$]*(合法識別字,無注入風險);key 走 JSON.stringify。
    var exportNames = discoverOnHandlerNames(htmlText);
    var reexport = '';
    exportNames.forEach(function (n) {
      reexport += 'try{window[' + JSON.stringify(n) + ']=' + n + ';}catch(_e){}\n';
    });
    // 串接:inline 塊(定義 switchRiskTab 等)在前 + risk-tab.js text 在後(原頁載入序:inline <script> 早於
    //   <script src=risk-tab.js>)→ 兩段共享同一 IIFE 詞法環境,互見對方頂層函式(如原全域)。
    var combined = inlineScriptTexts.join('\n;\n') + '\n;\n' + riskTabJsText;
    // F1(E2 MED)修復:auto-discover on* 屬性中的**裸頂層變數賦值**(IDENT=…,非函式呼叫/比較),對每個「是
    //   combined 頂層 let/const/var 名」的 IDENT(現況=[_liveRiskSavePendingCallback])建 window↔IIFE-local
    //   getter/setter proxy。緣由:onclick handler 在殼 **global 域**執行,IIFE-wrap 後 tab-risk.html:244 取消鈕的
    //   裸 `_liveRiskSavePendingCallback=null` 會建**無關的 window._liveRiskSavePendingCallback=null**、**不清**
    //   confirmLiveEngineRiskSave 讀的 IIFE-local binding → 事後 window.confirmLiveEngineRiskSave() 會執行**已取消的
    //   live save**(§3 live confirm cancel 語義弱化)。proxy 後:①IIFE 內直存不變(_wrapLiveSave 寫 / confirm 讀走
    //   IIFE-local direct);②cancel onclick 的 global 賦值 → 觸 setter → 清 IIFE-local → **cancel 語義逐字還原**。
    //   此通用擋未來其他 onclick 裸賦值到 IIFE-local 的同類弱化;交集 topLevelDeclaredNames 確保只對真 IIFE-local
    //   binding 建 proxy(不誤中 DOM `.value=` / `this.x=`,那些被 (^|[^.\w$]) 前置排除且非頂層宣告名)。
    var topNames = topLevelDeclaredNames(combined);
    var proxyNames = onAttrBareAssignTargets(htmlText).filter(function (nm) { return topNames[nm]; });
    var proxyCode = '';
    proxyNames.forEach(function (nm) {
      // nm 由 [A-Za-z_$][\w$]* 限定(合法識別字,無注入);window key 走 JSON.stringify,IIFE-local 存取用裸名。
      proxyCode +=
        'try{Object.defineProperty(window,' + JSON.stringify(nm) + ',{' +
        'get:function(){return ' + nm + ';},set:function(_v){' + nm + '=_v;},configurable:true});}catch(_e){}\n';
    });
    // IIFE 包裹:頂層 const/let/class(RISK_LEVEL_* / _DIFF_MAP / _riskFormDirty / … + switchRiskTab)成 IIFE-local
    //   → 不進 global lexical → 不與 paper/settings/overview 頂層跨-script 重宣告(否則 SyntaxError 整段不執行,
    //   view 靜默死),過 R71 guard(risk 判 isolated,貢獻空集)。其後 re-export onclick 函式至 window(否則
    //   IIFE-local 令 onclick 破)+ F1 proxy(cancel 裸賦值還原清 IIFE-local)+ 暴露 loadAll 至命名空間 __ocRiskLoadAll
    //   (供 pause/resume;**不寫 window.loadAll** 避免撞 paper.resume 所讀的 window.loadAll)。§3 保證:IIFE-wrap +
    //   proxy 純作用域橋接,不觸碰 confirm / diff / 寫的任何字節,cancel 語義還原而非弱化。
    var wrapped =
      '(function(){\n' + combined + '\n;\n' +
      reexport +
      proxyCode +
      'try{window.__ocRiskLoadAll=(typeof loadAll===\'function\'?loadAll:null);}catch(_e){}\n' +
      '})();';
    // 內聯 classic script 以全新 <script> 節點重跑(innerHTML/cloneNode 注入的 script 不自動執行);
    //   appendChild 當下同步執行。
    var s = document.createElement('script');
    s.textContent = wrapped;
    root.appendChild(s);
    wired = true;
  }

  // 注入 tab-risk.html <body> 的 risk DOM(byte-parity clone)+ 串接 inline 塊 + risk-tab.js text 重跑。
  function injectAndRun(html, riskTabJsText) {
    if (!root) return;
    var doc;
    try { doc = new DOMParser().parseFromString(html, 'text/html'); }
    catch (e) { showLoadError(e); return; }
    if (!doc || !doc.body) { showLoadError(new Error('no body')); return; }

    root.innerHTML = '';        // 清 loading 佔位
    var inlineScripts = [];
    Array.prototype.forEach.call(doc.body.childNodes, function (node) {
      if (node.nodeType === 1 && node.tagName === 'SCRIPT') {
        // 外部 <script src>(含 risk-tab.js):不 clone、不作 <script src> 重載——risk-tab.js 的 text 由 render
        //   併發 fetch 併入共享 IIFE(見 ★★);其餘外部 src(common* / governance.js)殼已載入,略過。
        if (node.src) return;
        var txt = node.textContent || '';
        // 首個內聯:ocAuthCheck()+ocInjectBaseCSS();殼已 auth,且 ocInjectBaseCSS 破殼 chrome → 跳過。
        if (txt.indexOf('ocInjectBaseCSS') !== -1) return;
        inlineScripts.push(txt);  // switchRiskTab + hoistRiskEngineSelector / dirty-bar 兩 IIFE → 收集待重跑
        return;
      }
      if (node.nodeType === 1 && node.tagName === 'STYLE') return;  // 頁內樣式塊 → view-risk.css 供
      // 其餘 body 節點(nav / 引擎選擇器 / P0·P1·P2 / 止損·倉位·冷卻·H0·自動調整 / AI 建議·預算 / Danger Zone /
      //   risk-dirty-bar / live-confirm 對話框 / 註釋)→ clone byte-parity
      root.appendChild(node.cloneNode(true));
    });

    // DOM 就位後串接重跑(此時 $('rg-explainer') / $('r-engine-status') 等 getElementById 皆可解;IIFE-wrap
    //   後 re-export 使 onclick 函式仍全域可達)。傳 html 供 on* 事件屬性自動發現(靜態 + 模板注入超集)。
    rerunSharedScript(inlineScripts, riskTabJsText, html);
  }

  // ═══ shell router 契約:render / resume / pause ═══
  // render:建 `.risk-view` 宿主 + 併發 fetch tab-risk.html + risk-tab.js + 注入/重跑(built guard 只首渲一次);
  //   首拉 + 啟輪詢 + setInterval(loadAiBudget) 由重跑的共享 script 自帶(risk-tab.js 尾端),非本函式——尊重 async fetch 完成時序。
  function renderRiskView(hostEl) {
    if (hostEl) host = hostEl;
    if (!host || built) return;
    built = true;
    root = document.createElement('div');
    root.className = 'risk-view';
    host.appendChild(root);
    root.innerHTML = '<div class="oc-subtab-placeholder">載入風控… / Loading…</div>';
    // 併發 fetch:tab-risk.html(DOM + inline)+ risk-tab.js(text,併入共享 IIFE)。任一失敗 → showLoadError。
    Promise.all([
      fetch(TAB_RISK_URL, { credentials: 'same-origin' })
        .then(function (r) { if (!r.ok) throw new Error('tab-risk HTTP ' + r.status); return r.text(); }),
      fetch(RISK_TAB_JS_URL, { credentials: 'same-origin' })
        .then(function (r) { if (!r.ok) throw new Error('risk-tab.js HTTP ' + r.status); return r.text(); })
    ]).then(function (arr) { injectAndRun(arr[0], arr[1]); }).catch(showLoadError);
  }

  // resume:view 顯示 → 首拉一次(鏡像「顯示即刷新」)+ 重啟 15s 輪詢。fetch 未完成(!wired)時 no-op:
  //   重跑本身即會首拉 + 啟輪詢,無需在此重入。用 window.__ocRiskLoadAll(IIFE 內暴露的 risk 自有 loadAll;
  //   不用 window.loadAll,隔離 paper——見 ★★★)。resume 不重跑 script,故不會重啟 setInterval(loadAiBudget)。
  function resumeRiskView() {
    if (!built || !wired) return;
    var fn = window.__ocRiskLoadAll;
    try { if (typeof fn === 'function') fn(); }
    catch (e) { warn('resume loadAll 失敗', e); }
    try {
      if (typeof window.ocStartRefresh === 'function' && typeof fn === 'function') {
        window.ocStartRefresh(fn, POLL_MS);
      }
    } catch (e) { warn('resume 重啟輪詢失敗', e); }
  }

  // pause:view 隱藏 → 停 15s loadAll 輪詢(freshness/safety:隱藏不得續打後端,鏡像 iframe 暫停語義)。
  //   ocStopRefresh 清 common.js 全域單例 timer;未啟輪詢時安全 no-op。
  //   註:setInterval(loadAiBudget,30000) 是共享 IIFE-local,pause 無法外清 → 隱藏後續跑(唯讀 GET,無害;見 MODULE_NOTE 行為守恆)。
  function pauseRiskView() {
    try { if (typeof window.ocStopRefresh === 'function') window.ocStopRefresh(); }
    catch (e) { warn('pause 停輪詢失敗', e); }
  }

  // 註冊進殼可見的原生 view 表(router 以 v.iframe===false 查此;key=VIEWS 的 id 'risk')。
  window.OC_NATIVE_VIEWS = window.OC_NATIVE_VIEWS || {};
  window.OC_NATIVE_VIEWS['risk'] = { render: renderRiskView, resume: resumeRiskView, pause: pauseRiskView };
  // 具名導出(task 契約:renderRiskView / pauseRiskView / resumeRiskView 可被引用)。
  window.renderRiskView = renderRiskView;
  window.resumeRiskView = resumeRiskView;
  window.pauseRiskView = pauseRiskView;
})();
