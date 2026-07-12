/*
 * view-governance.js — 玄衡原生 view「治理 / Governance Control Center」(Phase 2 iframe→原生遷移)
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:把 legacy `tab-governance.html`(iframe 後備)遷成玄衡殼內的**原生 view**。
 *   governance = **治理中樞**(SM-01 授權 / SM-02 決策租約 / SM-03 OMS / SM-04 風控 / EX-04 對賬 /
 *   Live Auth Earned-Trust 階梯 / Autonomy Posture 自主程度 / Paper→Live Gate / Learning Tier /
 *   Graduated Canary / Pending Approvals / Audit Trail);**交易關鍵四者之一**——含 12 個活躍治理寫
 *   (auth request/approve、risk override(SM-04 降級)、reconcile、learning-tier promote、audit approve/reject、
 *   bulkAudit(critical typed-confirm)、recovery approve、live/auth renew·renew-review、canary manual_promote、
 *   autonomy switch)。策略=**復用遷移**:fetch tab-governance.html → 注入其 <body> DOM(byte-parity)→
 *   把 4 路 script text(inline Live-Auth 塊 + autonomy-posture.js + governance-tab.js + canary-tab.js)
 *   **串接進同一個共享 IIFE 重跑**。
 *   **tab-governance.html / governance-tab.js / canary-tab.js / autonomy-posture.js / governance.js 零修改
 *   (reuse 正本 + rollback 錨)。**
 *
 * ★ skin-only 只換皮不改邏輯(§3 硬化逐字保留零弱化):
 *   view-governance.js **零自建寫路徑**——只 fetch + clone DOM + 重跑既有 script text。12 寫全在復用的未改
 *   script 內 byte-parity 續生效,經 Rust authority IPC;IIFE-wrap 不觸碰任何 confirm / 寫 / diff:
 *   ① typed-confirm phrase 逐字保留零弱化:`CONFIRM`(bulkAudit / confirmApproveRecovery)、`PROMOTE`
 *      (canary manual_promote,case-sensitive)、`CONFIRM SWITCH`(autonomy switch);
 *   ② 三態防 fake-success:submitOverride(applied/pending/unconfirmed)、submitPromotion(promoted true/false/
 *      unconfirmed)——pending 不誤顯綠,全 response-gated;
 *   ③ 五閘 / Live boundary / 緊急熔斷·防禦分離 / signed-auth·authorization.json / Paper 無真實資金 文案逐字保留;
 *   ④ Live Auth Trust TTL <2h 黃 / EXPIRED 紅 / T3 朱印(seal-mark)形制由 reused inline 塊執行期 `.style` 設,
 *      屬未改 JS 的 byte-parity 執行期行為,**非** view-governance.js/css 的新 inline-style ratchet 違規。
 *   **本檔不得繞過 / 短路 / 改任何 confirm 或寫。**
 *
 * ★★ 共享 IIFE 如何串接 4 路 script(本遷關鍵手法,比 risk 的「inline+單一 tab.js」多兩路):
 *   render 併發 fetch tab-governance.html(DOM + inline 塊)+ /static/autonomy-posture.js + /static/governance-tab.js
 *   + /static/canary-tab.js 的 text,依**固定串接序** [inline, autonomy, govtab, canary].join('\n;\n') 組單一大 text,
 *   再包進**單一** `(function(){ <combined>; <re-export>; <F1 proxy(gov=空)>; window.__ocGovLoadAll=…; })();`。
 *   為何序 autonomy 早於 govtab(TDZ 硬約束):governance-tab.js 尾端 self-init `loadAll()` 呼
 *   `loadAutonomyPosture()`,後者讀 autonomy-posture.js 頂層 `const AUTONOMY_*`;const 有 TDZ,若 autonomy 排在
 *   gov-tab self-init 之後則 ReferenceError。inline 塊置首(self-init 只呼自身段內函式/常數,安全)。canary 自成
 *   IIFE,只經 window.loadCanaryCohorts 與他段互動,置末(defer 語義)。**governance.js 不併入**——殼 shell.html
 *   已 <script src> 載入(提供 govGetStatus / govPost* / gov*Badge / GOV_* 全域),autonomy/gov-tab 於 IIFE 內以**上層
 *   作用域**(free var → global)引用其裸名;若併入會被 IIFE 圍住令 gov-tab 找不到。
 *
 * ★★★ 跨-view 全域詞法隔離(paper ↔ settings ↔ overview ↔ risk ↔ governance 共存;R71 guard 非協商):
 *   inline/autonomy/gov-tab 頂層宣告大量 const/let + function(gov-tab `async function loadAll` 撞 **paper 的
 *   window.loadAll**;gov-tab `let _currentRiskLevel` 撞 risk-tab.js 頂層 `let _currentRiskLevel`)。classic script
 *   raw 重跑=進同一 Realm 共享 global lexical → 頂層 const/let 跨 script 重宣告 SyntaxError,整段死。
 *   **處置**:串接後包 IIFE → 頂層全部成 IIFE-local → 不進 global lexical → 過 R71 guard(governance 判 isolated,
 *   貢獻空集,同 view-risk.js)。canary 自成 IIFE,亦貢獻空集。onclick 函式(35 名)由 fetched html∪script text
 *   **強化自動發現**(見 ★★★★)後 re-export 至 window;此 35 名與 paper/settings/overview/risk 的 onclick 集**無交集**
 *   (spec §3.C grep 證),re-export 無 last-writer-win 破壞。
 *
 * ★★★★ governance 相對 view-risk.js 的兩個**必改點**(不得原樣複製 view-risk.js):
 *   **(N2)loadAll 衝突 — clone 節點 onclick 重綁(PM 裁 OPEN-1 = PRIMARY)**:
 *     html:407 `onclick="loadAll()"`(Quick Status 刷新鈕)硬編呼全域 loadAll。governance loadAll IIFE-wrap 後為
 *     IIFE-local。若 re-export `window.loadAll` 會覆蓋 **paper 的 window.loadAll**(paper.resume 讀之)→ 破 paper;
 *     若不 re-export 則該鈕誤呼 paper 的 loadAll。save/restore-on-pause 亦不可靠(shell VIEWS 序 paper(idx1) resume
 *     早於 governance(idx13) pause)。**處置**:governance **永不寫 window.loadAll**;IIFE 尾曝 `window.__ocGovLoadAll
 *     = loadAll`;注入 DOM 後在**已 clone 進宿主的節點**上,把該唯一 `onclick="loadAll()"` 節點重綁為
 *     `__ocGovLoadAll()`(**僅此一處** onclick 重綁,其餘 34 名走標準 re-export)。此為執行期對 view 自有 clone DOM 的
 *     seam 調整,**源 tab-governance.html 檔零改**(rollback 錨完好),與 view-risk.js F1 window↔IIFE-local proxy 同類。
 *     效果:paper 的 window.loadAll 從不被 governance 觸碰(paper 恆安全),governance 刷新鈕呼自身 loadAll。
 *   **(N3)強化 handler 發現 — 不得原樣複製 view-risk.js 的 discoverOnHandlerNames(PM 裁 OPEN-2 = 必改)**:
 *     view-risk.js 只取 on* 屬性值**首 token**,在 governance 會 ① html:937 `onclick="if (typeof loadCanaryCohorts…"`
 *     捕到保留字 **`if`** → 生成 `window["if"]=if` **parse error → 整段 IIFE 死(blocker)**;② html:1091
 *     `onclick="event.stopPropagation();loadAuditTrail()"` 漏非首 token `loadAuditTrail`;③ 漏 governance-tab.js 模板
 *     字串注入的 `auditApprove/auditReject/confirmApproveRecovery`。**處置**:掃 html∪combined、抓 on* 值內**所有非
 *     member** `ident(`、**交集頂層宣告名(含 function)**、**濾 JS 保留字**、排除 loadAll。交集頂層函式天然濾掉
 *     `if`/`event`/`loadCanaryCohorts`(canary IIFE-local,自曝 window,不需 gov re-export);保留字濾除為冗餘保險。
 *
 * ★★★★★ live-auth 30s loop 的 pause/resume — postMessage 復用(PM 裁 OPEN-3):
 *   inline 塊自帶 `_govLiveAuthTimer` 30s setInterval(IIFE-local,ocStopRefresh 清不到)。inline 塊亦註冊
 *   `window.addEventListener('message', …)`(html:1677,跑於殼 window),收 `{type:'openclaw-tab-visibility',
 *   tab:'governance', visible}` → visible=false 呼 stopGovLiveAuthLoop、visible=true 呼 startGovLiveAuthLoop +
 *   force load。**pause/resume 經 window.postMessage 復用此既有 listener**(native view 無 iframe,但 listener 恰在
 *   殼 window → 直接同 window 收);零源修改,byte-parity 最佳,優於另曝 start/stop API。
 *
 * ★★★★★★ 與 spec design/11 的出入(以源碼為準,誠實指出,同 risk 遷移):
 *   ① **spec §8「2 style 塊 → view-governance.css」為必要但不充分**:結構類 oc-card / oc-metric* / oc-chip* /
 *      oc-table* / oc-explain* / oc-grid-2 / subtitle / oc-subtab-placeholder 在殼全域 CSS(shell-components /
 *      oc-utilities / shell / tokens)**零定義**——它們原只在 common.js `ocInjectBaseCSS()`,而殼**刻意不呼**
 *      ocInjectBaseCSS(其 body{padding}+`*` reset 破殼 chrome)。**所有 4 個已遷 view CSS(view-risk/overview/
 *      settings/paper.css)各自 port `.{view}-view` scoped oc-* shim**,否則卡片全裸。view-governance.css 照
 *      「類比 view-risk.css」補同款 shim(§8 ratchet 慣例:色字面→語義 token、暗底 rgba→--bg-sunken、無 token
 *      tint 保 rgba)。此為 spec §8 undercount,非缺陷。
 *   ② **spec §5「12 活躍寫」核實成立**(brief「6」undercount);#12 canary manual_promote 走
 *      `ocApi(url,{method:'POST'})` 非 ocPost(grep ocPost 會漏)。全走既有未改 script text,本檔零新增 call-site。
 *   ③ **shell.js:119 governance entry 加 `iframe:false` + shell.html 加 `<script src=view-governance.js>`** 是
 *      cutover wiring(spec §9/§10)。本任務 scope=**只新建 view-governance.js/css 兩檔**(並發安全:governance.js
 *      被他 session 編輯,五源檔零改);registry 接線由後續 cutover 步(E2+E3+operator Linux 批驗後)接手,不在本刀。
 *
 * 注入 / 重跑:render → 併發 fetch tab-governance.html + autonomy-posture.js + governance-tab.js + canary-tab.js →
 *   DOMParser 解析 html → <body> DOM 逐節點 clone 進 `.governance-view` 宿主(byte-parity id/class/onclick)→
 *   §3.B′ loadAll 節點 onclick 重綁 → 4 段 text 串接後以全新 <script> 節點 IIFE-wrap 重跑。
 *   **跳過**:①外部 <script src>(common* / governance.js 殼已載;autonomy/govtab/canary 的 text 另 fetch 併入 IIFE,
 *   不作 <script src> 重載,避免其自初始化在無 DOM 的殼 boot 期跑);②首個內聯 <script>=`ocAuthCheck();
 *   ocInjectBaseCSS();`(殼已 auth;ocInjectBaseCSS 破殼 chrome,禁呼);③兩樣式塊(→ view-governance.css)。
 *   首拉 + 啟輪詢由重跑段自帶(gov-tab `loadAll()`+`ocStartRefresh(loadAll,10000)`;inline `govLoadLiveAuthStatus`
 *   +`startGovLiveAuthLoop`;canary else-分支 `loadCanaryCohorts()`)——不需 view-paper.js 的 DCL-capture hack。
 * visibility 語義:pause=停**兩**輪詢——① ocStopRefresh()(清 common.js 全域單例 10s `_ocRefreshTimer`);
 *   ② postMessage visible:false → inline listener stopGovLiveAuthLoop(清 30s IIFE-local timer)。
 *   resume=① postMessage visible:true(inline listener 啟 30s loop + force load);② __ocGovLoadAll() +
 *   ocStartRefresh(__ocGovLoadAll, 10000)(重啟 10s 主輪詢;用命名空間非 window.loadAll,隔離 paper)。
 * 依賴(全復用,不重造):common.js($ / ocApi / ocPost / ocNum / ocPctVal / ocStartRefresh / ocStopRefresh /
 *   ocToast / ocEsc / …)、common-formatters.js、common-modals.js(openConfirmModal / openPromptModal /
 *   openTypedConfirmModal)、fetch_with_csrf.js;**governance.js**(殼已於 overview 遷移載入,提供 govGet* /
 *   govPost* / gov*Badge / GOV_*,§5 全寫依賴)。view-governance.css 供 `.governance-view` scope 樣式。
 * 誠實邊界:靜態(node --check + ratchet 0/0 新檔 + 5b + 註冊 smoke + R71 空集)只證 source 事實;**真渲染 /
 *   12 寫真行為 / typed-confirm 真閘 / 三態徽 / 雙輪詢 / clone-rebind 真效果 = NEEDS-LINUX runtime + operator**。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  // ── 模塊級狀態 ──
  var host = null;              // 原生 <section> 宿主(shell 注入)
  var root = null;              // `.governance-view` 內層宿主(view-governance.css scope root)
  var built = false;            // rendered guard(只首渲一次;防雙 fetch / 雙重跑 / 雙啟 setInterval)
  var wired = false;            // 共享 IIFE 已重跑並定義全域函式 + 啟輪詢(併發 fetch 完成後轉真)
  var POLL_MS = 10000;          // 主輪詢間隔(byte-parity governance-tab.js ocStartRefresh(loadAll, 10000))
  var TAB_GOV_URL = '/static/tab-governance.html';   // DOM + inline 塊來源 + registry 完整性/回滾錨
  var AUTONOMY_JS_URL = '/static/autonomy-posture.js'; // text 併入共享 IIFE(不作 <script src> 重載)
  var GOVTAB_JS_URL = '/static/governance-tab.js';     // text 併入共享 IIFE
  var CANARY_JS_URL = '/static/canary-tab.js';         // text 併入共享 IIFE(自成 IIFE,置末)

  function warn(msg, e) { try { console.warn('[view-governance] ' + msg, e || ''); } catch (_) {} }

  // fail-closed 可見化:fetch / 解析失敗 → 顯錯不崩(對齊殼 iframe 載入失敗語義,不留空白)。
  function showLoadError(e) {
    warn('tab-governance.html / *.js 載入失敗 — Governance view inactive', e);
    if (root) {
      root.innerHTML =
        '<div class="oc-subtab-placeholder">治理載入失敗 — 可切其他視圖或返回舊版 Console(詳見瀏覽器 console)</div>';
    }
  }

  // ── JS 保留字(強化 handler 發現的濾集;冗餘保險——交集頂層函式本已濾掉,但明列擋 `if`→window["if"]=if blocker)──
  var JS_RESERVED = {
    'if': 1, 'else': 1, 'for': 1, 'while': 1, 'do': 1, 'switch': 1, 'case': 1, 'default': 1,
    'break': 1, 'continue': 1, 'return': 1, 'function': 1, 'var': 1, 'let': 1, 'const': 1,
    'new': 1, 'delete': 1, 'typeof': 1, 'instanceof': 1, 'void': 1, 'in': 1, 'of': 1,
    'this': 1, 'super': 1, 'class': 1, 'extends': 1, 'try': 1, 'catch': 1, 'finally': 1,
    'throw': 1, 'true': 1, 'false': 1, 'null': 1, 'undefined': 1, 'with': 1, 'yield': 1,
    'await': 1, 'async': 1, 'debugger': 1, 'export': 1, 'import': 1, 'from': 1, 'as': 1
  };

  // ── 掃 script text 的**深度 0(頂層)** let/const/var **與 function** 宣告名。──────────────────────
  //   字元級掃描(跳 字串/樣板/行·塊註釋/regex 字面,追蹤 (){}[] 深度,只在深度 0 捕關鍵字後識別字)。
  //   移植 view-risk.js topLevelDeclaredNames + **擴充捕頂層 `function` 宣告名**(§3.A 步 3);canary 自成 IIFE →
  //   其 `(function(){` 令內部 depth≥1,天然不被捕(貢獻空集)。用途:① handler 發現交集;② F1 born-safety 交集。
  function topLevelDeclaredNames(text) {
    var names = {};
    var i = 0, n = text.length, depth = 0, prev = '';
    var idStart = /[A-Za-z_$]/, idCont = /[\w$]/, ws = /\s/;
    var regexPrev = '(,=:[!&|?{;}+-*%<>~^';
    // kwRegex:這些關鍵字後的 `/` 是 regex 非除號;**含 `async`** → 令 `async function foo` 的 prev 成分隔符,
    //   否則 prev='c'(async 末字)會令下步 `!idCont.test(prev)` 誤擋 → 漏捕所有 async function(gov 大量用)。
    var kwRegex = { 'return': 1, 'typeof': 1, 'instanceof': 1, 'in': 1, 'of': 1, 'new': 1, 'delete': 1, 'void': 1, 'do': 1, 'else': 1, 'yield': 1, 'case': 1, 'throw': 1, 'await': 1, 'async': 1 };
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
        if ((word === 'let' || word === 'const' || word === 'var' || word === 'function') && depth === 0 && !idCont.test(prev) && prev !== '.') {
          var mm = i; while (mm < n && ws.test(text[mm])) mm++;
          // function 後可能有 `*`(generator);gov 無 generator,但跳過保險。
          if (mm < n && text[mm] === '*') { mm++; while (mm < n && ws.test(text[mm])) mm++; }
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

  // ── 強化版 handler 發現(取代 view-risk.js 的 discoverOnHandlerNames;§3.A / PM 裁 OPEN-2 必改)。────────
  //   掃 scanText(= html ∪ combined script);對每個 on* 屬性值抓**所有非 member** `ident(` 的 identifier,
  //   再交集 topFnNames(頂層宣告名)+ 濾 JS 保留字 + 排除 loadAll(§3.B′ 另行 clone-rebind)。
  //   有界取值:on<event>= 後接引號,取至「同型未轉義引號 / 換行」——換行有界防模板字串內未閉合引號
  //   (如 governance-tab.js `onclick="auditApprove(\'`)貪婪吞噬跨行;handler 恆在 on* 值首,newline 界內可捕。
  function discoverOnHandlerNames(scanText, topFnNames) {
    var names = {};
    var attrOpen = /\bon[a-z]+\s*=\s*(["'])/g;
    var m;
    while ((m = attrOpen.exec(scanText)) !== null) {
      var quote = m[1];
      var vStart = attrOpen.lastIndex;
      var i = vStart, nn = scanText.length;
      while (i < nn) {
        var chc = scanText[i];
        if (chc === '\\') { i += 2; continue; }               // 跳轉義字元
        if (chc === quote || chc === '\n' || chc === '\r') break; // 同型引號或換行=值邊界
        i++;
      }
      var val = scanText.slice(vStart, i);
      var idRe = /(^|[^.\w$])([A-Za-z_$][\w$]*)\s*\(/g;        // 抓 ident(;前置排 member 存取(.foo)
      var a;
      while ((a = idRe.exec(val)) !== null) { names[a[2]] = true; }
    }
    var out = [];
    Object.keys(names).forEach(function (nm) {
      if (nm === 'loadAll') return;         // §3.B′:governance 永不寫 window.loadAll(隔離 paper),另行 clone-rebind
      if (JS_RESERVED[nm]) return;          // 濾保留字(擋 html:937 `if`→window["if"]=if parse-error blocker)
      if (topFnNames[nm]) out.push(nm);     // 只 re-export 真頂層可呼叫(天然濾 event/stopPropagation/loadCanaryCohorts)
    });
    return out;
  }

  // ── F1 born-safety:掃 fetched html 所有 on* 屬性值,抓**裸賦值目標**(IDENT=…);與頂層宣告名交集才建 proxy。──
  //   前置 (^|[^.\w$]) 排屬性賦值(this.x= / el.value=);`=` 後 [^=] 排 ==/===。governance 實測交集=∅
  //   (§4:全 on* 皆函式呼叫或 member 呼叫,html:937 的 `===` 是比較非賦值)→ proxyCode 空,不生成 proxy 碼。
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

  // 重跑共享 script(4 路 text 串接 → 單一 IIFE)。
  function rerunSharedScript(inlineScriptTexts, autonomyText, govtabText, canaryText, htmlText) {
    // 串接序固定(§A.1):[inline, autonomy, govtab, canary].join('\n;\n')(`;` 分隔防 ASI;autonomy 早於 govtab
    //   滿足 const AUTONOMY_* 的 TDZ;canary 自 IIFE 置末)。
    var segs = inlineScriptTexts.slice();
    segs.push(autonomyText);
    segs.push(govtabText);
    segs.push(canaryText);
    var combined = segs.join('\n;\n');

    // 頂層宣告名(含 function)——① handler 發現交集;② F1 born-safety 交集。
    var topNames = topLevelDeclaredNames(combined);

    // 強化 handler 發現:掃 html ∪ combined(後者含模板字串內 onclick),交集頂層函式 + 濾保留字 + 排 loadAll。
    var exportNames = discoverOnHandlerNames(htmlText + '\n' + combined, topNames);
    var reexport = '';
    exportNames.forEach(function (nmx) {
      // identifier 由正則限定 [A-Za-z_$][\w$]*(合法識別字,無注入);key 走 JSON.stringify;逐名 try/catch 兜底。
      reexport += 'try{window[' + JSON.stringify(nmx) + ']=' + nmx + ';}catch(_e){}\n';
    });

    // F1 born-safety(governance 產空集,不生成 proxy;保留檢查對齊 view-risk.js 手法,擋未來裸賦值弱化)。
    var proxyNames = onAttrBareAssignTargets(htmlText).filter(function (nm) { return topNames[nm]; });
    var proxyCode = '';
    proxyNames.forEach(function (nm) {
      proxyCode +=
        'try{Object.defineProperty(window,' + JSON.stringify(nm) + ',{' +
        'get:function(){return ' + nm + ';},set:function(_v){' + nm + '=_v;},configurable:true});}catch(_e){}\n';
    });

    // IIFE 包裹:頂層 const/let/function 成 IIFE-local → 過 R71 guard(governance 判 isolated,貢獻空集);其後
    //   re-export 35 onclick 函式至 window;曝 loadAll 至命名空間 __ocGovLoadAll(供 pause/resume;**不寫
    //   window.loadAll**,隔離 paper)。§3:IIFE-wrap 純作用域橋接,不觸碰 confirm / typed-confirm / 寫 的任何字節。
    var wrapped =
      '(function(){\n' + combined + '\n;\n' +
      reexport +
      proxyCode +
      'try{window.__ocGovLoadAll=(typeof loadAll===\'function\'?loadAll:null);}catch(_e){}\n' +
      '})();';
    // 內聯 classic script 以全新 <script> 節點重跑(cloneNode 注入的 script 不自動執行);appendChild 當下同步執行。
    var s = document.createElement('script');
    s.textContent = wrapped;
    root.appendChild(s);
    wired = true;
  }

  // 注入 tab-governance.html <body> DOM(byte-parity clone)+ loadAll 節點 onclick 重綁 + 串接 4 路 text 重跑。
  function injectAndRun(html, autonomyText, govtabText, canaryText) {
    if (!root) return;
    var doc;
    try { doc = new DOMParser().parseFromString(html, 'text/html'); }
    catch (e) { showLoadError(e); return; }
    if (!doc || !doc.body) { showLoadError(new Error('no body')); return; }

    root.innerHTML = '';        // 清 loading 佔位
    var inlineScripts = [];
    Array.prototype.forEach.call(doc.body.childNodes, function (node) {
      if (node.nodeType === 1 && node.tagName === 'SCRIPT') {
        // 外部 <script src>(common* / governance.js / autonomy / govtab / canary):不 clone、不作 <script src> 重載
        //   ——autonomy/govtab/canary 的 text 由 render 併發 fetch 併入共享 IIFE;common*/governance.js 殼已載。
        if (node.src) return;
        var txt = node.textContent || '';
        // 首個內聯:ocAuthCheck()+ocInjectBaseCSS();殼已 auth,且 ocInjectBaseCSS 破殼 chrome → 跳過。
        if (txt.indexOf('ocInjectBaseCSS') !== -1) return;
        inlineScripts.push(txt);  // Live-Auth 大內聯塊(html:1250-1716)→ 收集待併入 IIFE
        return;
      }
      if (node.nodeType === 1 && node.tagName === 'STYLE') return;  // 兩頁內樣式塊 → view-governance.css 供
      // 其餘 body 節點(header / SM 四卡 / demo-admission / recon / live-auth / autonomy / PLG / learning-tier /
      //   canary / approvals / events / summary / incident / audit / 5 modal / 註釋)→ clone byte-parity
      root.appendChild(node.cloneNode(true));
    });

    // §3.B′(N2 / PM 裁 OPEN-1 = PRIMARY)loadAll 唯一 onclick 重綁:在**已 clone 進宿主**的節點上,把唯一
    //   `onclick="loadAll()"`(html:407 Quick Status 刷新鈕)重綁為 `__ocGovLoadAll()`。governance 永不寫
    //   window.loadAll(paper 恆安全);源 tab-governance.html 檔零改(rollback 錨完好)。此為**唯一** onclick 重綁。
    try {
      var rebound = 0;
      var nodes = root.querySelectorAll('[onclick]');
      Array.prototype.forEach.call(nodes, function (el) {
        var v = (el.getAttribute('onclick') || '').replace(/\s+/g, '');
        if (v === 'loadAll()') { el.setAttribute('onclick', '__ocGovLoadAll()'); rebound++; }
      });
      if (rebound !== 1) warn('loadAll onclick 重綁筆數異常(預期 1,實得 ' + rebound + ')');
    } catch (e) { warn('loadAll onclick 重綁失敗', e); }

    // DOM 就位後串接重跑(此時 getElementById 皆可解;IIFE-wrap 後 re-export 使 onclick 函式全域可達)。
    rerunSharedScript(inlineScripts, autonomyText, govtabText, canaryText, html);
  }

  // ═══ shell router 契約:render / resume / pause ═══
  // render:建 `.governance-view` 宿主 + 併發 fetch 4 資源 + 注入/重跑(built guard 只首渲一次);首拉 + 啟輪詢
  //   由重跑的共享 script 自帶(gov-tab loadAll+ocStartRefresh、inline live-auth self-init、canary else-分支)。
  function renderGovernanceView(hostEl) {
    if (hostEl) host = hostEl;
    if (!host || built) return;
    built = true;
    root = document.createElement('div');
    root.className = 'governance-view';
    host.appendChild(root);
    root.innerHTML = '<div class="oc-subtab-placeholder">載入治理… / Loading…</div>';
    // 併發 fetch:tab-governance.html(DOM + inline)+ 3 路 JS text(併入共享 IIFE)。任一失敗 → showLoadError。
    Promise.all([
      fetch(TAB_GOV_URL, { credentials: 'same-origin' })
        .then(function (r) { if (!r.ok) throw new Error('tab-governance HTTP ' + r.status); return r.text(); }),
      fetch(AUTONOMY_JS_URL, { credentials: 'same-origin' })
        .then(function (r) { if (!r.ok) throw new Error('autonomy-posture.js HTTP ' + r.status); return r.text(); }),
      fetch(GOVTAB_JS_URL, { credentials: 'same-origin' })
        .then(function (r) { if (!r.ok) throw new Error('governance-tab.js HTTP ' + r.status); return r.text(); }),
      fetch(CANARY_JS_URL, { credentials: 'same-origin' })
        .then(function (r) { if (!r.ok) throw new Error('canary-tab.js HTTP ' + r.status); return r.text(); })
    ]).then(function (arr) { injectAndRun(arr[0], arr[1], arr[2], arr[3]); }).catch(showLoadError);
  }

  // resume:view 顯示 → ① postMessage visible:true(inline listener 啟 30s live-auth loop + force load);
  //   ② 首拉主頁 __ocGovLoadAll() + 重啟 10s 主輪詢(用命名空間非 window.loadAll,隔離 paper)。
  //   fetch 未完成(!wired)時 no-op:重跑本身即會首拉 + 啟輪詢。
  function resumeGovernanceView() {
    if (!built || !wired) return;
    try {
      window.postMessage({ type: 'openclaw-tab-visibility', tab: 'governance', visible: true }, window.location.origin);
    } catch (e) { warn('resume postMessage(live-auth 啟)失敗', e); }
    var fn = window.__ocGovLoadAll;
    try { if (typeof fn === 'function') fn(); }
    catch (e) { warn('resume loadAll 失敗', e); }
    try {
      if (typeof window.ocStartRefresh === 'function' && typeof fn === 'function') {
        window.ocStartRefresh(fn, POLL_MS);
      }
    } catch (e) { warn('resume 重啟輪詢失敗', e); }
  }

  // pause:view 隱藏 → 停**兩**輪詢:① ocStopRefresh()(清 common.js 全域單例 10s timer);② postMessage
  //   visible:false → inline listener stopGovLiveAuthLoop(清 30s IIFE-local `_govLiveAuthTimer`,ocStopRefresh 清不到)。
  function pauseGovernanceView() {
    try { if (typeof window.ocStopRefresh === 'function') window.ocStopRefresh(); }
    catch (e) { warn('pause 停主輪詢失敗', e); }
    try {
      window.postMessage({ type: 'openclaw-tab-visibility', tab: 'governance', visible: false }, window.location.origin);
    } catch (e) { warn('pause postMessage(live-auth 停)失敗', e); }
  }

  // 註冊進殼可見的原生 view 表(router 以 v.iframe===false 查此;key=VIEWS 的 id 'governance')。
  window.OC_NATIVE_VIEWS = window.OC_NATIVE_VIEWS || {};
  window.OC_NATIVE_VIEWS['governance'] = { render: renderGovernanceView, resume: resumeGovernanceView, pause: pauseGovernanceView };
  // 具名導出(task 契約:renderGovernanceView / pauseGovernanceView / resumeGovernanceView 可被引用)。
  window.renderGovernanceView = renderGovernanceView;
  window.resumeGovernanceView = resumeGovernanceView;
  window.pauseGovernanceView = pauseGovernanceView;
})();
