/*
 * view-live.js — 玄衡原生 view「實盤 / Live Trading」(Phase 2 iframe→原生遷移,交易關鍵四者**最後**一個)
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:把 legacy `tab-live.html`(iframe 後備)遷成玄衡殼內的**原生 view**。
 *   live = **實盤交易面**(真金/LiveDemo 雙態儀表板 · 帳戶餘額 · PnL 概覽+時序 · 持倉/掛單/塵埃 ·
 *   性能指標 · Pre-Live gate 趨勢 · 成交記錄 · Earned-Trust 授權狀態欄);**交易關鍵四者之一**,
 *   §3 硬化面最重者——含 4 個破壞性寫(session start/stop·emergency-stop·close-all·個別平倉)全走
 *   typed-confirm(START LIVE / STOP LIVE / EMERGENCY STOP / CLOSE ALL)+ 五閘 signed authorization.json gate。
 *   策略=**復用遷移**:fetch tab-live.html → 注入其 <body> DOM(byte-parity clone)→ fetch tab-live.js text
 *   → 串接成**單一共享 IIFE 重跑**。**tab-live.html / tab-live.js 零修改(reuse 正本 + rollback 錨)。**
 *
 * ★ skin-only 只換皮不改邏輯(§3 硬化逐字保留零弱化,operator §0.2 硬邊界):
 *   view-live.js **零自建寫路徑**——只 fetch + clone DOM + 重跑既有 tab-live.js text。§3 硬化面全在復用的未改
 *   text 內 byte-parity 續生效,經 Rust authority IPC;IIFE-wrap 不觸碰任何 confirm / 寫 / diff:
 *   ① typed-confirm phrase 逐字保留零弱化:START LIVE(liveStart)、STOP LIVE(doLiveStop)、
 *      EMERGENCY STOP(doEmergencyStop)、CLOSE ALL(doLiveCloseAll),全走 openTypedConfirmModal;個別平倉
 *      closeLivePosition 走 openConfirmModal(1-click,dust/一般兩態),保「單倉=1-click / 全域破壞性=typed」分級;
 *   ② 三態防 fake-success:classifyLiveMutation 判 success/未確認(非 if(d) 假成功);
 *   ③ 五閘 / signed authorization.json gate / execution_authority guard / 緊急停止·平倉·停止三者分離
 *      (doLiveStop·doEmergencyStop 同 session/stop 端點但互動層分離;doLiveCloseAll 走 close-all-positions,
 *      session 不停)/ REAL FUNDS 常駐標識 / --live 熱紅 / live_halt·drawdown / canon-7 三態
 *      (integrity-fail·phantom-view·unconfigured)文案逐字保留;
 *   ④ --live 熱紅主題(真金 salience,canon-6)由 view-live.css verbatim 承載,view-live.js 不改寫任何 §3 邏輯。
 *   **本檔不得繞過 / 短路 / 改任何 confirm 或寫。**寫全走 Rust 引擎 IPC。
 *
 * ★★ 共享 IIFE 如何串接(本遷關鍵手法,比 risk/governance 都簡):
 *   tab-live.html body 唯一內聯 <script>= ocAuthCheck()+ocInjectBaseCSS()(**跳過**:殼已 auth;ocInjectBaseCSS
 *   注 body 內距+`*` reset 破殼 chrome,禁呼)。故 combined = **只 tab-live.js text**,無 inline 塊要併入
 *   (governance 需 4 路串接序+TDZ,live 全不觸)。外層 (function(){ <combined>; <re-export>; })();。
 *   IIFE 內 tab-live.js self-init(refreshPage({force:true})+startLiveRefreshLoop())append 當下同步跑=首拉全頁 +
 *   啟 15s 輪詢;visibility listener(收 openclaw-tab-visibility tab==='live')註冊於**殼 window**(§9 pause/resume 之核心)。
 *
 * ★★★ 跨-view 全域詞法隔離(paper ↔ settings ↔ overview ↔ risk ↔ governance ↔ demo ↔ live 共存;R71 guard 非協商):
 *   tab-live.js 頂層宣告大量 const/let(TRUST_TIER_* / LIVE_* / _live* 等)+ function。classic script raw 重跑=進
 *   同一 Realm 共享 global lexical → 頂層 const/let 跨 script 重宣告 SyntaxError,整段死。**處置**:串接後包 IIFE →
 *   頂層全部成 IIFE-local → 不進 global lexical → 過 R71 guard(live 判 isolated,貢獻空集,同 view-risk.js)。
 *   實測 live 頂層唯一「泛名」= refreshPage;whole-word grep 其他 view/tab JS 零定義/零消費(common.js 僅註解),
 *   re-export 至 window.refreshPage 安全,無跨-view 消費者。其餘全 live/Live/_live 前綴或 live 專屬,無跨-view 重名。
 *   onclick 函式(13 名)由 fetched html∪combined **強化自動發現**(見 ★★★★)後 re-export 至 window;此 13 名與
 *   paper/settings/overview/risk/governance/demo 的 onclick 集**無交集**(spec §3.C 實測),re-export 無 last-writer-win。
 *   **live 無 loadAll**(§5):self-init 即首拉+啟輪詢,不需 __ocLiveLoadAll 命名空間暴露、不寫 window.loadAll
 *   (paper 恆安全),亦無 governance 的 onclick 重綁——**live 是交易關鍵四者中 loadAll/onclick-重綁 最乾淨者**。
 *
 * ★★★★ 強化 handler 發現(復用 view-governance.js 強化版 verbatim;PM 裁 OPEN-5)——必改硬核 closeLivePosition:
 *   view-risk.js 的 discoverOnHandlerNames 只掃 htmlText;但 live 有一個 on* handler **只在 tab-live.js 模板字串**——
 *   closeLivePosition(tab-live.js:837,倉位表 row template 由 loadDashboardData innerHTML 動態注入,**不在** html)。
 *   只掃 html 會**漏** → 個別倉位平倉鈕 onclick 在殼 global 域 closeLivePosition is not defined → 平倉鈕全死
 *   (**安全關鍵寫**,不可靜默死)。**處置**:掃 html ∪ combined、抓 on* 值內所有非 member ident(、交集頂層宣告名
 *   (含 function)、濾 JS 保留字、排除 loadAll。掃 combined 額外命中 js:422 `button[onclick="doLiveCloseAll()"]`
 *   捕 doLiveCloseAll(已是真 handler,重複無害);js:440 `button[onclick^="closeLivePosition"]` 因 `^=` 破
 *   `on[a-z]+\s*=` 不中,無誤。實測 exportNames = 恰 13 名(含 closeLivePosition),零漏零餘。
 *
 * ★★★★★ F1-class 裸賦值風險 = 空集(brief「頭號風險」REFUTE;PM 獨立核驗):
 *   live 的 typed-confirm 全走 `const ok = await openTypedConfirmModal({...}).catch(()=>false); if(!ok) return;`,
 *   closeLivePosition 走 `if(!await openConfirmModal({...})) return;`;confirm 結果由 SDK 回傳 Promise 承載,
 *   **無**risk 那種「取消鈕 inline _liveRiskSavePendingCallback=null」的殼 global 域裸賦值 → F1 proxy 集 = ∅。
 *   本檔仍保留 onAttrBareAssignTargets ∩ topLevelDeclaredNames 檢查作 born-safety,**掃 html∪combined**(§11 對齊
 *   discoverer 掃描域,不留 template-injected 盲區),對 live 產空集,不生成 proxy 碼(比 risk 簡:risk 有 1 proxy)。
 *
 * ★★★★★★ pause/resume 15s 輪詢暫停 — postMessage 復用既有 visibility listener(§9,零源修改):
 *   shell.js notifyViewVisibility 對原生 view 呼 api.pause()/api.resume(),**不** postMessage;但 tab-live.js 已內建
 *   openclaw-tab-visibility listener(收 tab==='live')。故 view-live.js 的 pause/resume 自行 window.postMessage 該訊息
 *   → 觸 tab-live.js listener 復用其 start/stop 邏輯:pause(visible:false)→ stopLiveRefreshLoop(清唯一 15s
 *   _liveRefreshTimer);resume(visible:true)→ startLiveRefreshLoop + refreshPage({force:true})(首拉+啟輪詢)。
 *   listener 恰在殼 window(合併 script 跑於殼 realm),同 window postMessage 可收 + origin 相符(location.origin)。
 *   live listener 已含 start+首拉(比 governance 完整,resume 純 postMessage,不需另呼 refresh/loadAll)。
 *   sub-refresh(dashboard 30s/metrics 30s/edge 120s/pnl 60s)是 refreshPage 內時戳節流非獨立 interval,掛單一
 *   15s master tick → pause 只需停一個 timer。雙保險:tab-live.js 另含 document visibilitychange(殼 document)。
 *
 * 注入 / 重跑:render → 建 `.live-view` 宿主 → 併發 fetch tab-live.html + tab-live.js → DOMParser 解析 html →
 *   <body> DOM 逐節點 clone 進宿主(byte-parity id/class/onclick;integrity-fail view + dashboard view 全部)→
 *   tab-live.js text 以全新 <script> 節點 IIFE-wrap 重跑(built guard 只首渲一次,防雙 fetch/雙 setInterval/雙 listener)。
 *   **跳過**:①外部 <script src>(common* 殼已載;tab-live.js 的 text 另 fetch 併入 IIFE,不作 <script src> 重載
 *   避免其 self-init 在無 DOM 的殼 boot 期跑);②首個內聯 <script>=ocAuthCheck()+ocInjectBaseCSS()(殼已 auth;
 *   ocInjectBaseCSS 破殼 chrome,禁呼);③頁內樣式塊(→ view-live.css,`.live-view` scope)。
 * visibility 語義:pause=postMessage visible:false(觸 listener stopLiveRefreshLoop,隱藏不續打後端=freshness/safety);
 *   resume=postMessage visible:true(觸 listener startLiveRefreshLoop + refreshPage force 首拉)。built/wired guard:
 *   pause/resume 在 !built||!wired 時 no-op;built guard 防 resume 重跑 IIFE(不重註冊 listener/不雙 setInterval)。
 * 依賴(全復用,不重造):common.js($ / ocApi / ocPost / ocToast / ocMiniTrendSvg / classifyLiveMutation /
 *   ocResidualRiskBanner / ocReadCachedDevelopmentSupportMode / ocListen·ocFetchDevelopmentSupportMode)、
 *   common-formatters.js(ocPerformanceMetricsFromPayload / ocStrategyChip / ocPnlSeriesFromFills / ocSetPnlRangeButtons)、
 *   common-modals.js(openTypedConfirmModal / openConfirmModal)、fetch_with_csrf.js;view-live.css 供 `.live-view` scope 樣式。
 * 誠實邊界:靜態(node --check + ratchet 0/0/0 新檔 + 5b + 註冊 smoke + R71 空集 + F1 空集)只證 source 事實;
 *   **真渲染 / 4 寫真行為 / typed-confirm 真閘 / 五閘真 enforced / 三態(integrity-fail·phantom-view)/ REAL FUNDS·
 *   --live 真配色 / body.live-mode-* 真切換 / 15s 輪詢 pause = NEEDS-LINUX runtime + operator**,不由本刀 attest。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  // ── 模塊級狀態 ──
  var host = null;              // 原生 <section> 宿主(shell 注入)
  var root = null;              // `.live-view` 內層宿主(view-live.css scope root)
  var built = false;            // rendered guard(只首渲一次;防雙 fetch / 雙重跑 / 雙啟 setInterval / 雙註冊 listener)
  var wired = false;            // 共享 IIFE 已重跑並定義全域函式 + 啟輪詢(併發 fetch 完成後轉真)
  var TAB_LIVE_URL = '/static/tab-live.html';   // DOM 來源 + registry 完整性 + 回滾錨
  var TAB_LIVE_JS_URL = '/static/tab-live.js';  // tab-live.js text 另 fetch,併入共享 IIFE(不作 <script src> 重載)

  function warn(msg, e) { try { console.warn('[view-live] ' + msg, e || ''); } catch (_) {} }

  // fail-closed 可見化:fetch / 解析失敗 → 顯錯不崩(對齊殼 iframe 載入失敗語義,不留空白)。
  function showLoadError(e) {
    warn('tab-live.html / tab-live.js 載入失敗 — Live view inactive', e);
    if (root) {
      root.innerHTML =
        '<div class="oc-subtab-placeholder">實盤載入失敗 — 可切其他視圖或返回舊版 Console(詳見瀏覽器 console)</div>';
    }
  }

  // ── JS 保留字(強化 handler 發現的濾集;冗餘保險——交集頂層函式本已濾掉,但明列擋保留字→window[reserved]=reserved blocker)──
  var JS_RESERVED = {
    'if': 1, 'else': 1, 'for': 1, 'while': 1, 'do': 1, 'switch': 1, 'case': 1, 'default': 1,
    'break': 1, 'continue': 1, 'return': 1, 'function': 1, 'var': 1, 'let': 1, 'const': 1,
    'new': 1, 'delete': 1, 'typeof': 1, 'instanceof': 1, 'void': 1, 'in': 1, 'of': 1,
    'this': 1, 'super': 1, 'class': 1, 'extends': 1, 'try': 1, 'catch': 1, 'finally': 1,
    'throw': 1, 'true': 1, 'false': 1, 'null': 1, 'undefined': 1, 'with': 1, 'yield': 1,
    'await': 1, 'async': 1, 'debugger': 1, 'export': 1, 'import': 1, 'from': 1, 'as': 1
  };

  // ── 掃 script text 的**深度 0(頂層)** let/const/var **與 function** 宣告名(復用 view-governance.js verbatim)。──
  //   字元級掃描(跳 字串/樣板/行·塊註釋/regex 字面,追蹤 (){}[] 深度,只在深度 0 捕關鍵字後識別字)。
  //   捕頂層 function 宣告名(含 async function → closeLivePosition 是 async function,def 於 tab-live.js:1177,
  //   須被捕方能交集出 export)。用途:① handler 發現交集;② F1 born-safety 交集。
  function topLevelDeclaredNames(text) {
    var names = {};
    var i = 0, n = text.length, depth = 0, prev = '';
    var idStart = /[A-Za-z_$]/, idCont = /[\w$]/, ws = /\s/;
    var regexPrev = '(,=:[!&|?{;}+-*%<>~^';
    // kwRegex:這些關鍵字後的 `/` 是 regex 非除號;**含 async** → 令 `async function foo` 的 prev 成分隔符,
    //   否則 prev='c'(async 末字)會令下步 `!idCont.test(prev)` 誤擋 → 漏捕所有 async function(closeLivePosition 是)。
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
          // function 後可能有 `*`(generator);tab-live.js 無 generator,但跳過保險。
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

  // ── 強化版 handler 發現(復用 view-governance.js verbatim;§3.A / PM 裁 OPEN-5)。────────────────────────
  //   掃 scanText(= html ∪ combined script);對每個 on* 屬性值抓**所有非 member** ident( 的 identifier,
  //   再交集 topFnNames(頂層宣告名)+ 濾 JS 保留字 + 排除 loadAll(live 無 loadAll,§5)。
  //   有界取值:on<event>= 後接引號,取至「同型未轉義引號 / 換行」——換行有界防模板字串內未閉合引號貪婪吞噬跨行;
  //   handler 恆在 on* 值首,newline 界內可捕。**必改硬核**:捕 tab-live.js:837 模板注入的 closeLivePosition。
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
      if (nm === 'loadAll') return;         // live 無 loadAll,不寫 window.loadAll(隔離 paper);冗餘保險
      if (JS_RESERVED[nm]) return;          // 濾保留字(擋 window[reserved]=reserved parse-error blocker)
      if (topFnNames[nm]) out.push(nm);     // 只 re-export 真頂層可呼叫(天然濾 this.dataset 等 member 讀)
    });
    return out;
  }

  // ── F1 born-safety(復用 view-governance.js verbatim):掃 scanText 所有 on* 屬性值,抓**裸賦值目標**(IDENT=…);──
  //   與頂層宣告名交集才建 proxy。前置 (^|[^.\w$]) 排屬性賦值(this.x= / el.value=);`=` 後 [^=] 排 ==/===。
  //   §11:掃 html∪combined(對齊 discoverer 掃描域,不留 template-injected 盲區)。live 實測交集=∅
  //   (§4:全 on* 皆函式呼叫或 member 讀;closeLivePosition 的 this.dataset.* 是 member 讀非賦值)→ 不生成 proxy 碼。
  function onAttrBareAssignTargets(scanText) {
    var found = {};
    var attrRe = /on[a-z]+\s*=\s*("([^"]*)"|'([^']*)')/g;
    var m;
    while ((m = attrRe.exec(scanText)) !== null) {
      var val = (m[2] !== undefined) ? m[2] : (m[3] || '');
      var asgn = /(^|[^.\w$])([A-Za-z_$][\w$]*)\s*=\s*[^=]/g;
      var a;
      while ((a = asgn.exec(val)) !== null) { found[a[2]] = true; }
    }
    return Object.keys(found);
  }

  // 重跑共享 script(combined = tab-live.js text,IIFE 包裹隔離頂層 const/let/function 防跨-view 詞法重宣告
  //   SyntaxError——見 ★★★)。tab-live.js 無 DOMContentLoaded;self-init(refreshPage({force:true})+
  //   startLiveRefreshLoop(),js:1923-1924)在 append 當下同步跑=首拉+啟 15s 輪詢,故直接重跑。
  function rerunSharedScript(inlineScriptTexts, liveTabJsText, htmlText) {
    // combined:tab-live.js text(唯一段;body 唯一內聯塊=ocInjectBaseCSS 已跳過,無 inline 塊前綴,§A.1)。
    //   若未來 html 新增非-skip 內聯塊,inlineScriptTexts 非空則前綴之(原頁載入序:inline 早於 <script src>)。
    var combined = inlineScriptTexts.length
      ? (inlineScriptTexts.join('\n;\n') + '\n;\n' + liveTabJsText)
      : liveTabJsText;

    // 頂層宣告名(含 function)——① handler 發現交集;② F1 born-safety 交集。
    var topNames = topLevelDeclaredNames(combined);

    // 強化 handler 發現:掃 html ∪ combined(後者含模板字串內 closeLivePosition onclick),交集頂層函式 + 濾保留字。
    //   identifier 由正則限定合法識別字(無注入);key 走 JSON.stringify;逐名 try/catch 兜底(非真頂層函式→跳過)。
    var exportNames = discoverOnHandlerNames(htmlText + '\n' + combined, topNames);
    var reexport = '';
    exportNames.forEach(function (nmx) {
      reexport += 'try{window[' + JSON.stringify(nmx) + ']=' + nmx + ';}catch(_e){}\n';
    });

    // F1 born-safety(§11 掃 html∪combined;live 產空集,不生成 proxy 碼;保留檢查對齊手法擋未來裸賦值弱化)。
    var proxyNames = onAttrBareAssignTargets(htmlText + '\n' + combined).filter(function (nm) { return topNames[nm]; });
    var proxyCode = '';
    proxyNames.forEach(function (nm) {
      proxyCode +=
        'try{Object.defineProperty(window,' + JSON.stringify(nm) + ',{' +
        'get:function(){return ' + nm + ';},set:function(_v){' + nm + '=_v;},configurable:true});}catch(_e){}\n';
    });

    // IIFE 包裹:頂層 const/let/function(TRUST_TIER_* / LIVE_* / _live* / refreshPage 等)成 IIFE-local → 不進
    //   global lexical → 過 R71 guard(live 判 isolated,貢獻空集);其後 re-export 13 onclick 函式至 window
    //   (含 closeLivePosition,否則個別平倉鈕破)。**無 __ocLiveLoadAll**(live 無 loadAll)、**無 F1 proxy**(空集)。
    //   §3:IIFE-wrap 純作用域橋接,不觸碰 confirm / typed-confirm / 寫 的任何字節。
    var wrapped =
      '(function(){\n' + combined + '\n;\n' +
      reexport +
      proxyCode +
      '})();';
    // 內聯 classic script 以全新 <script> 節點重跑(cloneNode 注入的 script 不自動執行);appendChild 當下同步執行。
    var s = document.createElement('script');
    s.textContent = wrapped;
    root.appendChild(s);
    wired = true;
  }

  // 注入 tab-live.html <body> DOM(byte-parity clone)+ 串接 tab-live.js text 重跑。
  function injectAndRun(html, liveTabJsText) {
    if (!root) return;
    var doc;
    try { doc = new DOMParser().parseFromString(html, 'text/html'); }
    catch (e) { showLoadError(e); return; }
    if (!doc || !doc.body) { showLoadError(new Error('no body')); return; }

    root.innerHTML = '';        // 清 loading 佔位
    var inlineScripts = [];
    Array.prototype.forEach.call(doc.body.childNodes, function (node) {
      if (node.nodeType === 1 && node.tagName === 'SCRIPT') {
        // 外部 <script src>(含 tab-live.js):不 clone、不作 <script src> 重載——tab-live.js 的 text 由 render
        //   併發 fetch 併入共享 IIFE(見 ★★);其餘外部 src(common*)殼已載入,略過。
        if (node.src) return;
        var txt = node.textContent || '';
        // 首個內聯:ocAuthCheck()+ocInjectBaseCSS();殼已 auth,且 ocInjectBaseCSS 破殼 chrome → 跳過。
        if (txt.indexOf('ocInjectBaseCSS') !== -1) return;
        inlineScripts.push(txt);  // live 現況無其他非-skip 內聯塊;防禦性收集(未來若有則併入 IIFE)
        return;
      }
      if (node.nodeType === 1 && node.tagName === 'STYLE') return;  // 頁內樣式塊 → view-live.css 供
      // 其餘 body 節點(integrity-fail view / 儀表板 header / 餘額·PnL 卡 / 持倉·塵埃·掛單表 / 性能·edge gate /
      //   成交記錄 / trust-status 欄 / 註釋)→ clone byte-parity id/class/onclick
      root.appendChild(node.cloneNode(true));
    });

    // DOM 就位後串接重跑(此時 getElementById 皆可解;IIFE-wrap 後 re-export 使 onclick 函式全域可達)。
    //   傳 html 供 on* 事件屬性自動發現(靜態 + 模板注入超集,捕 closeLivePosition)。
    rerunSharedScript(inlineScripts, liveTabJsText, html);
  }

  // ═══ shell router 契約:render / resume / pause ═══
  // render:建 `.live-view` 宿主 + 併發 fetch tab-live.html + tab-live.js + 注入/重跑(built guard 只首渲一次);
  //   首拉 + 啟 15s 輪詢 + 註冊 visibility listener 由重跑的 tab-live.js self-init 自帶(js:1902-1924),非本函式。
  function renderLiveView(hostEl) {
    if (hostEl) host = hostEl;
    if (!host || built) return;
    built = true;
    root = document.createElement('div');
    root.className = 'live-view';
    host.appendChild(root);
    root.innerHTML = '<div class="oc-subtab-placeholder">載入實盤… / Loading…</div>';
    // 併發 fetch:tab-live.html(DOM)+ tab-live.js(text,併入共享 IIFE)。任一失敗 → showLoadError。
    Promise.all([
      fetch(TAB_LIVE_URL, { credentials: 'same-origin' })
        .then(function (r) { if (!r.ok) throw new Error('tab-live HTTP ' + r.status); return r.text(); }),
      fetch(TAB_LIVE_JS_URL, { credentials: 'same-origin' })
        .then(function (r) { if (!r.ok) throw new Error('tab-live.js HTTP ' + r.status); return r.text(); })
    ]).then(function (arr) { injectAndRun(arr[0], arr[1]); }).catch(showLoadError);
  }

  // resume:view 顯示 → postMessage visible:true → tab-live.js listener startLiveRefreshLoop + refreshPage({force:true})
  //   (首拉 + 啟 15s 輪詢)。fetch 未完成(!wired)時 no-op:重跑本身即會首拉 + 啟輪詢 + 註冊 listener。
  //   純 postMessage(live listener 已含 start+首拉,不需另呼 refresh/loadAll,比 governance 省)。
  function resumeLiveView() {
    if (!built || !wired) return;
    try {
      window.postMessage({ type: 'openclaw-tab-visibility', tab: 'live', visible: true }, window.location.origin);
    } catch (e) { warn('resume postMessage(啟輪詢)失敗', e); }
  }

  // pause:view 隱藏 → postMessage visible:false → tab-live.js listener stopLiveRefreshLoop(清唯一 15s
  //   _liveRefreshTimer;隱藏不續打後端=freshness/safety,鏡像 iframe 暫停語義)。!built||!wired 時 no-op。
  function pauseLiveView() {
    if (!built || !wired) return;
    try {
      window.postMessage({ type: 'openclaw-tab-visibility', tab: 'live', visible: false }, window.location.origin);
    } catch (e) { warn('pause postMessage(停輪詢)失敗', e); }
  }

  // 註冊進殼可見的原生 view 表(router 以 v.iframe===false 查此;key=VIEWS 的 id 'live')。
  window.OC_NATIVE_VIEWS = window.OC_NATIVE_VIEWS || {};
  window.OC_NATIVE_VIEWS['live'] = { render: renderLiveView, resume: resumeLiveView, pause: pauseLiveView };
  // 具名導出(task 契約:renderLiveView / pauseLiveView / resumeLiveView 可被引用)。
  window.renderLiveView = renderLiveView;
  window.resumeLiveView = resumeLiveView;
  window.pauseLiveView = pauseLiveView;
})();
