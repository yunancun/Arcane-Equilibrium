/*
 * view-demo.js — 玄衡原生 view「演示 / Demo」(Phase 2 交易關鍵 view 遷移;iframe→原生)
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:把 legacy `tab-demo.html`(iframe 後備)遷成玄衡殼內的**原生 view**。
 *   demo = **Demo 演示**(Bybit 沙盒環境,真實市場數據 + **虛擬資金**;帳戶餘額 / 盈虧概覽 /
 *   持倉 + 塵埃匯總 / 活躍訂單 / 性能指標 / 成交歷史分頁 / Paper↔Demo 對比 / Demo 會話控制)。
 *   **交易關鍵**——含 4 個 demo 虛擬資金寫(session 動作 / 全平 / 單倉平倉 ×2),經 Rust 引擎 IPC。
 *   策略=**復用遷移(fetch tab-demo.html → 注入其 <body> demo DOM(byte-parity)→ IIFE-wrap 重跑其
 *   唯一大內聯 script)**,同 settings / overview 的「單一 inline 塊復用」pattern。
 *   **tab-demo.html 零修改(唯一 reuse 正本 + rollback 錨)。**
 *
 * ★ 只換皮不改邏輯(§3 破壞性確認逐字保留零弱化):
 *   view-demo.js **零自建寫路徑**——只 fetch + clone DOM + 重跑既有內聯 script。4 寫全在復用的未改
 *   script 內 byte-parity 續生效,IIFE-wrap 不觸碰任何 confirm / 寫:
 *   ① demoSessionAction → ocPost('/api/v1/strategy/demo/session/'+action);
 *   ② doDemoCloseAll → ocPost('/api/v1/strategy/demo/close-all-positions')(前置 #dlg-demo-close-all 確認框 +
 *      classifyLiveMutation / ocResidualRiskBanner 防 fake-success);
 *   ③④ closeDemoPosition → ocPost('.../positions/{symbol}/close')(前置 openConfirmModal;dust / 一般各一路)。
 *   canon-6 政策:demo=虛擬資金,破壞性確認框用**琥珀(--warn)**警示語義,**非** live 熱紅(--live);
 *   本檔絕不把 demo 誤升 --live,confirm gate 逐字保留不短路。
 *
 * ★★ 跨-view 全域詞法隔離(paper ↔ settings ↔ overview ↔ risk ↔ governance ↔ demo 共存;R71 guard 非協商):
 *   tab-demo.html 頂層宣告大量 `let/const`(_demoFillsCache / _demoPnlRange / _demoRefreshInFlight /
 *   _demoTabVisible / _demoCloseAllSummary / DEMO_FILL_PAGE_SIZE / DEMO_FILL_TABS / _demoFillState /
 *   DEMO_PNL_PRELOAD_SIZE / _demoPnlHistoryState 等)+ **頂層 `async function loadAll`(撞 paper 的
 *   window.loadAll,paper.resume 讀之)**。classic script 經 raw appendChild(<script>) 重跑=進**同一 Realm
 *   共享 global lexical**;頂層 `let/const/class` 跨 script 重宣告 → SyntaxError,整段不執行 → view 靜默功能死。
 *   **處置**:把重跑的內聯 script **IIFE 包裹**,頂層全部成 IIFE-local → 不進 global lexical → 過 R71 guard
 *   (demo 判 isolated,貢獻空集)。onclick 函式由 fetched html ∪ script text **強化自動發現**(見 ★★★)後
 *   re-export 至 window;`loadAll` **不**在 on* 集、**不寫 window.loadAll**(避免撞 paper),改暴露
 *   `window.__ocDemoLoadAll` 供 demo 自身 pause/resume。demo onclick 集與 paper/settings/overview/risk/governance
 *   的 onclick 集**無交集**(實測 grep 12 名全零交集),re-export 無 last-writer-win 破壞。
 *
 * ★★★ 強化 handler 發現(參 view-governance.js,即使 demo handler 集簡單也用穩健版):
 *   舊版(view-settings/overview)只取 on* 值**首 token**——雖 demo 現況全部 handler 皆在值首,穩健版仍改用
 *   governance 手法:掃 html ∪ combined、抓 on* 值內**所有非 member** `ident(`、**交集頂層宣告名(含 function)**、
 *   **濾 JS 保留字**、排除 loadAll。好處:① 未來錨新增非首 token handler 自動涵蓋;② 天然濾掉 `if`/`event` 等
 *   保留字/非函式,不生成 window["if"]=if 的 parse-error blocker。demo 現況發現集 = 12 名 on* handler:
 *   closeDemoDialog / closeDemoPosition / demoFillNext / demoFillPrev / demoSessionAction / doDemoCloseAll /
 *   openDemoCloseAllDialog / openDemoRisk / refreshDemoFillsNow / setDemoFillView / setDemoPnlRange +
 *   **onDemoFillsToggle**(ontoggle=,非 onclick——brief 只列 11 onclick,穩健掃 on* 全類即涵蓋此第 12 名)。
 *
 * ★★★★ 與 brief / 事實的出入(以源碼為準,誠實指出):
 *   ① brief 稱「11 onclick handler」;源碼實測 on* handler 集 = **12**(第 12 = ontoggle="onDemoFillsToggle(this)"
 *      html:190,onDemoFillsToggle 為頂層 function html:972)。強化掃 on* 全類自動涵蓋,無需硬編。
 *   ② 自初始化尾巴(IIFE 重跑當下同步跑)brief 列 loadAll({force:true}) + ocStartRefresh + occurrencychange;
 *      源碼另有 **`ocInitFx()`**(html:1352,FX 匯率初始化,byte-parity 保留無害)。occurrencychange(html:1353)
 *      為拼錯的 dead 事件,無害保留。
 *   ③ demo 的 loadAll **不在** onclick 集(實測零 `onclick="loadAll()"`),故**不需** governance 的 clone-rebind;
 *      loadAll 只由自初始化 / 15s timer / 內聯事件監聽器內部呼(全 IIFE 內詞法 binding)。
 *   ④ oc-btn-warn(closeDemoPosition dust 確認的 confirmClass)全域未定義(ocInjectBaseCSS 只有 oc-btn-warning);
 *      該按鈕在 common-modals.js 掛於 document.body(.demo-view 外),此為**既有源碼債**(pre-existing),
 *      byte-parity 不動、不在本檔修——退回 .oc-btn 基樣式,功能不受影響。
 *
 * 注入 / 重跑:render → fetch /static/tab-demo.html → DOMParser 解析 → 把 <body> demo DOM 逐節點 clone 進
 *   `.demo-view` 宿主(byte-parity id/class/onclick;控制欄 + explain + stale banner + demo-content 各卡 +
 *   demo-offline + close-all 確認框)→ 再把大內聯 script 以全新 <script> 節點 IIFE-wrap 重跑。
 *   **跳過**:①外部 <script src>(common-formatters / mode-badge / modals / csrf / common 殼已載入,勿重複);
 *   ②首個內聯 <script>=`ocAuthCheck(); ocInjectBaseCSS();`(殼 boot 已 ocAuthCheck;ocInjectBaseCSS 注入
 *   body{padding}+`*` reset 破殼 chrome,禁呼——見四姊妹 view CSS MODULE_NOTE);
 *   ③頁內樣式塊(由 view-demo.css 以 `.demo-view` scope 供給,含 demo 琥珀確認框樣式,ratchet born-clean)。
 * canon-7(未接數據三態,非假 active):demo-badge 依真值顯「已连接/連線逾時/未连接」;balance 逾時保最後快照 +
 *   stale banner;metrics/fills 空顯「暫無/無法載入」;皆由復用內聯 script 原樣渲染,本檔零 fake。
 * visibility 語義:pause=ocStopRefresh()(停 15s 輪詢,隱藏不續打後端=freshness/safety);
 *   resume=首拉 __ocDemoLoadAll() + ocStartRefresh(__ocDemoLoadAll, 15s) 重啟(鏡像 iframe 暫停)。
 *   ⚠ 行為守恆限制:內聯自帶 `document.addEventListener('visibilitychange',…)`(html:1346)為 IIFE-local,
 *   本檔無法外清——瀏覽器分頁重獲焦點時它會再呼 loadAll(受 loadAll 內 `_demoRefreshInFlight` 重入閘 +
 *   `_isDemoTabRefreshVisible()` 節流,且全為唯讀 GET)。同 risk setInterval 先例;built guard 防 resume 重跑內聯。
 *   ocStartRefresh 用 common.js 全域單例 `_ocRefreshTimer`;殼內呼 ocStartRefresh 者僅 paper/settings/overview/demo,
 *   且同時只一 view active(pause 清 timer),故單例零爭用。
 * 依賴(全復用,不重造):common.js($ / ocApi / ocPost / ocStartRefresh / ocStopRefresh / ocExplain /
 *   ocToast / ocSetText / ocSetHtml / ocEsc / ocMoney / ocBalance / ocSignParts / classifyLiveMutation /
 *   ocResidualRiskBanner / ocInitFx / …)、common-formatters.js、common-mode-badge.js、common-modals.js
 *   (openConfirmModal)、fetch_with_csrf.js;view-demo.css 供 `.demo-view` scope 樣式。
 * 誠實邊界:靜態(node --check + ratchet + 註冊 smoke + R71 空集)只證 source 事實;**真渲染 / 4 寫真行為 /
 *   confirm 真閘 / 三態徽 / 15s 輪詢 / 琥珀不升 live = NEEDS-LINUX runtime + operator**,不由本刀 attest。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  // ── 模塊級狀態 ──
  var host = null;              // 原生 <section> 宿主(shell 注入)
  var root = null;              // `.demo-view` 內層宿主(view-demo.css scope root)
  var built = false;            // rendered guard(只首渲一次;防雙 fetch / 雙重跑內聯 script)
  var wired = false;            // 內聯 script 已重跑並定義全域函式 + 啟輪詢(async fetch 完成後轉真)
  var POLL_MS = 15000;          // 輪詢間隔(byte-parity tab-demo.html ocStartRefresh(loadAll, 15000))
  var TAB_DEMO_URL = '/static/tab-demo.html';  // src 保留=registry 完整性 + 回滾錨,同時作復用來源

  function warn(msg, e) { try { console.warn('[view-demo] ' + msg, e || ''); } catch (_) {} }

  // fail-closed 可見化:fetch / 解析失敗 → 顯錯不崩(對齊殼 iframe 載入失敗語義,不留空白)。
  function showLoadError(e) {
    warn('tab-demo.html 載入失敗 — Demo view inactive', e);
    if (root) {
      root.innerHTML =
        '<div class="oc-subtab-placeholder">Demo 載入失敗 — 可切其他視圖或返回舊版 Console(詳見瀏覽器 console)</div>';
    }
  }

  // ── JS 保留字(強化 handler 發現的濾集;交集頂層函式本已濾掉,明列作冗餘保險擋 window["if"]=if 之類 blocker)──
  var JS_RESERVED = {
    'if': 1, 'else': 1, 'for': 1, 'while': 1, 'do': 1, 'switch': 1, 'case': 1, 'default': 1,
    'break': 1, 'continue': 1, 'return': 1, 'function': 1, 'var': 1, 'let': 1, 'const': 1,
    'new': 1, 'delete': 1, 'typeof': 1, 'instanceof': 1, 'void': 1, 'in': 1, 'of': 1,
    'this': 1, 'super': 1, 'class': 1, 'extends': 1, 'try': 1, 'catch': 1, 'finally': 1,
    'throw': 1, 'true': 1, 'false': 1, 'null': 1, 'undefined': 1, 'with': 1, 'yield': 1,
    'await': 1, 'async': 1, 'debugger': 1, 'export': 1, 'import': 1, 'from': 1, 'as': 1
  };

  // ── 掃 script text 的**深度 0(頂層)** let/const/var **與 function** 宣告名(移植 view-governance.js)。──────
  //   字元級掃描(跳 字串/樣板/行·塊註釋/regex 字面,追蹤 (){}[] 深度,只在深度 0 捕關鍵字後識別字)。
  //   用途:handler 發現交集(只 re-export 真頂層可呼叫函式)。
  function topLevelDeclaredNames(text) {
    var names = {};
    var i = 0, n = text.length, depth = 0, prev = '';
    var idStart = /[A-Za-z_$]/, idCont = /[\w$]/, ws = /\s/;
    var regexPrev = '(,=:[!&|?{;}+-*%<>~^';
    // kwRegex:這些關鍵字後的 `/` 是 regex 非除號;**含 `async`** → 令 `async function foo` 的 prev 成分隔符,
    //   否則 prev='c'(async 末字)會令下步 `!idCont.test(prev)` 誤擋 → 漏捕所有 async function(demo 大量用)。
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
          // function 後可能有 `*`(generator);demo 無 generator,但跳過保險。
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

  // ── 強化版 handler 發現(移植 view-governance.js;取代 view-settings/overview 只取首 token 的舊版)。────────
  //   掃 scanText(= html ∪ combined script);對每個 on* 屬性值抓**所有非 member** `ident(` 的 identifier,
  //   再交集 topFnNames(頂層宣告名)+ 濾 JS 保留字 + 排除 loadAll(demo loadAll 只走 __ocDemoLoadAll)。
  //   有界取值:on<event>= 後接引號,取至「同型未轉義引號 / 換行」——換行有界防模板字串內未閉合引號貪婪吞噬跨行。
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
      if (nm === 'loadAll') return;         // demo 永不寫 window.loadAll(隔離 paper),改走 __ocDemoLoadAll
      if (JS_RESERVED[nm]) return;          // 濾保留字(冗餘保險)
      if (topFnNames[nm]) out.push(nm);     // 只 re-export 真頂層可呼叫(天然濾 event/非函式)
    });
    return out;
  }

  // 重跑內聯 script(demo 無 DOMContentLoaded handler,append 當下同步自呼 init,故直接重跑;
  //   IIFE 包裹隔離頂層 let/const/function 防跨-view 詞法重宣告 SyntaxError + 撞 paper 的 window.loadAll——見 ★★)。
  function rerunInlineScripts(scriptTexts, htmlText) {
    // 頂層宣告名(含 function)——供強化 handler 發現交集(只 re-export 真頂層函式)。
    var combined = scriptTexts.join('\n;\n');
    var topNames = topLevelDeclaredNames(combined);
    // 強化 handler 發現:掃 html ∪ combined(後者含模板字串內 onclick),交集頂層函式 + 濾保留字 + 排 loadAll。
    var exportNames = discoverOnHandlerNames(htmlText + '\n' + combined, topNames);
    var reexport = '';
    exportNames.forEach(function (nmx) {
      // identifier 由正則限定 [A-Za-z_$][\w$]*(合法識別字,無注入);key 走 JSON.stringify;逐名 try/catch 兜底。
      reexport += 'try{window[' + JSON.stringify(nmx) + ']=' + nmx + ';}catch(_e){}\n';
    });
    scriptTexts.forEach(function (txt) {
      // IIFE 包裹:頂層 let/const/function(含 loadAll / _demoTabVisible / DEMO_FILL_TABS 等)成 IIFE-local →
      //   不進 global lexical → 不與 paper/settings/overview/risk/governance 頂層跨-script 重宣告(否則 SyntaxError
      //   整段不執行,view 靜默死),過 R71 guard(demo 判 isolated,貢獻空集)。原 text 尾端自帶
      //   loadAll({force:true})+ocStartRefresh(loadAll,15000)+ocInitFx()(IIFE 內詞法 binding,首拉+啟輪詢+FX 初始化照常);
      //   其後 re-export 12 onclick 函式至 window(否則 IIFE-local 令 onclick 破)+ 暴露 loadAll 至命名空間
      //   __ocDemoLoadAll(供 pause/resume;不寫 window.loadAll 避免撞 paper.resume 所讀的 window.loadAll)。
      //   §3 保證:IIFE-wrap 純作用域收束,不觸碰 4 寫 / confirm gate / 琥珀警示 的任何字節。
      var wrapped =
        '(function(){\n' + txt + '\n;\n' +
        reexport +
        'try{window.__ocDemoLoadAll=(typeof loadAll===\'function\'?loadAll:null);}catch(_e){}\n' +
        '})();';
      // 內聯 classic script 以全新 <script> 節點重跑(innerHTML/cloneNode 注入的 script 不自動執行);
      //   appendChild 當下同步執行。
      var s = document.createElement('script');
      s.textContent = wrapped;
      root.appendChild(s);
    });
    wired = true;
  }

  // 注入 tab-demo.html <body> 的 demo DOM(byte-parity clone)+ 重跑其內聯 script。
  function injectAndRun(html) {
    if (!root) return;
    var doc;
    try { doc = new DOMParser().parseFromString(html, 'text/html'); }
    catch (e) { showLoadError(e); return; }
    if (!doc || !doc.body) { showLoadError(new Error('no body')); return; }

    root.innerHTML = '';        // 清 loading 佔位
    var inlineScripts = [];
    Array.prototype.forEach.call(doc.body.childNodes, function (node) {
      if (node.nodeType === 1 && node.tagName === 'SCRIPT') {
        if (node.src) return;   // 外部 script(殼已載入)略過
        var txt = node.textContent || '';
        // 首個內聯:ocAuthCheck()+ocInjectBaseCSS();殼已 auth,且 ocInjectBaseCSS 破殼 chrome → 跳過。
        if (txt.indexOf('ocInjectBaseCSS') !== -1) return;
        inlineScripts.push(txt);  // 唯一大 inline demo 邏輯(html:263-1443)→ 收集待重跑
        return;
      }
      if (node.nodeType === 1 && node.tagName === 'STYLE') return;  // 頁內樣式塊 → view-demo.css 供
      // 其餘 body 節點(控制欄 / explain / stale banner / demo-content 各卡 / demo-offline / close-all 確認框 / 註釋)
      //   → clone byte-parity(含 close-all 確認框 #dlg-demo-close-all,位於 script 之後仍被逐節點 clone)
      root.appendChild(node.cloneNode(true));
    });

    // DOM 就位後重跑內聯 script(此時 $('demo-badge') / $('demo-content') 等 getElementById 皆可解;IIFE-wrap
    //   後 re-export 使 onclick 函式仍全域可達)。傳 html 供 on* 事件屬性自動發現(靜態 + 模板注入超集)。
    rerunInlineScripts(inlineScripts, html);
  }

  // ═══ shell router 契約:render / resume / pause ═══
  // render:建 `.demo-view` 宿主 + fetch tab-demo.html + 注入/重跑(built guard 只首渲一次);
  //   首拉 + 啟輪詢 + FX 初始化由重跑的內聯 script 自帶(尾端),非本函式——尊重 async fetch 完成時序。
  function renderDemoView(hostEl) {
    if (hostEl) host = hostEl;
    if (!host || built) return;
    built = true;
    root = document.createElement('div');
    root.className = 'demo-view';
    host.appendChild(root);
    root.innerHTML = '<div class="oc-subtab-placeholder">載入 Demo… / Loading…</div>';
    fetch(TAB_DEMO_URL, { credentials: 'same-origin' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); })
      .then(injectAndRun)
      .catch(showLoadError);
  }

  // resume:view 顯示 → 首拉一次(鏡像「顯示即刷新」)+ 重啟 15s 輪詢。fetch 未完成(!wired)時 no-op:
  //   重跑本身即會首拉 + 啟輪詢,無需在此重入。用 window.__ocDemoLoadAll(IIFE 內暴露的 demo 自有 loadAll;
  //   不用 window.loadAll,隔離 paper——見 ★★)。resume 不重跑 script,故不重複註冊內聯監聽器 / 不重啟 FX。
  function resumeDemoView() {
    if (!built || !wired) return;
    // 通知內聯 visibilitychange 節流器 demo 已可見(_demoTabVisible=true):refocus 時允許刷新。
    //   復用 tab-demo.html:1337 既有 message listener(origin-checked),零源改;targetOrigin 綁 same-origin。
    try { window.postMessage({ type: 'openclaw-tab-visibility', tab: 'demo', visible: true }, window.location.origin); } catch (e) {}
    var fn = window.__ocDemoLoadAll;
    try { if (typeof fn === 'function') fn(); }
    catch (e) { warn('resume loadAll 失敗', e); }
    try {
      if (typeof window.ocStartRefresh === 'function' && typeof fn === 'function') {
        window.ocStartRefresh(fn, POLL_MS);
      }
    } catch (e) { warn('resume 重啟輪詢失敗', e); }
  }

  // pause:view 隱藏 → 停 15s 輪詢(freshness/safety:隱藏不得續打後端,鏡像 iframe 暫停語義)。
  //   ocStopRefresh 清 common.js 全域單例 timer;未啟輪詢時安全 no-op。
  //   內聯自帶 visibilitychange 監聽器為 IIFE-local 無法外清,但**經 postMessage 令內聯 _demoTabVisible=false**
  //   即抑制其 refocus 時觸發 loadAll(_isDemoTabRefreshVisible() 讀 _demoTabVisible)——消除 demo 非 active 時
  //   瀏覽器重獲焦點的多餘唯讀 GET(R78 E2 LOW-1 修;同 governance OPEN-3 手法,復用既有 message listener 零源改)。
  function pauseDemoView() {
    try { if (typeof window.ocStopRefresh === 'function') window.ocStopRefresh(); }
    catch (e) { warn('pause 停輪詢失敗', e); }
    // 通知內聯節流器 demo 已隱藏 → refocus 不再刷新(抑制多餘唯讀 loadAll GET)。
    try { window.postMessage({ type: 'openclaw-tab-visibility', tab: 'demo', visible: false }, window.location.origin); } catch (e) {}
  }

  // 註冊進殼可見的原生 view 表(router 以 v.iframe===false 查此;key=VIEWS 的 id 'demo')。
  window.OC_NATIVE_VIEWS = window.OC_NATIVE_VIEWS || {};
  window.OC_NATIVE_VIEWS['demo'] = { render: renderDemoView, resume: resumeDemoView, pause: pauseDemoView };
  // 具名導出(task 契約:renderDemoView / pauseDemoView / resumeDemoView 可被引用)。
  window.renderDemoView = renderDemoView;
  window.resumeDemoView = resumeDemoView;
  window.pauseDemoView = pauseDemoView;
})();
