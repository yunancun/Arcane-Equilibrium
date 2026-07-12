/*
 * view-settings.js — 玄衡原生 view「設置中樞 / Settings & Control」(Phase 2 第 12 個 iframe→原生遷移)
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:把 legacy `tab-settings.html`(iframe 後備)遷成玄衡殼內的**原生 view**。
 *   settings = **設置中樞**(4 子標籤:引擎控制 / 系統運維 / 連線與憑證 / 調試);寫面涵蓋
 *   demo control / 全局模式 / 產品族 / 成本·盈虧錄入 / config-change / paper-engine toggle /
 *   development-support(browser-local)/ **Bybit API-key 管理** / **告警通知(Telegram+Webhook)**。
 *   策略=**復用遷移(fetch tab-settings.html → 注入其 <body> settings DOM(byte-parity)→ 重跑其
 *   內聯 <script>)**,同 paper R69 pattern。**tab-settings.html 零修改(reuse 正本 + rollback 錨)。**
 *
 * ★ 與 brief 的關鍵出入(以源碼為準,已於回報指出):
 *   ① brief 稱「7 inline script,全內嵌」;源碼實測 tab-settings.html <body> 只有 **2 個內聯
 *      <script>**:行 18(`ocAuthCheck(); ocInjectBaseCSS();`,跳過)+ 行 661-1897(**單一大內聯
 *      script**,承全部 settings 邏輯)。故「重跑內聯 script」= 重跑這唯一大塊。
 *   ② brief 稱「3 個 style 塊」;源碼實測只有 **2 個頁內 style 塊**(行 37-47 + 行 186-340;
 *      第三個「命中」是行 286 註釋文字裡的 style 標籤字面,非真標籤)。兩塊全搬入 view-settings.css。
 *   ③ brief 稱查 DOMContentLoaded;源碼實測 tab-settings.html **零 DOMContentLoaded handler**——
 *      內聯 script 於 eval 當下自呼 init(subtab IIFE `_ocSettingsSubtabInit` + explainer 賦值 +
 *      尾端 `loadAll()` + `ocStartRefresh(loadAll, 30000)`)。故**直接重跑即可**,無需 paper 的
 *      DCL 捕獲/手動觸發 shim(此為比 paper 更簡:settings 無延後 DCL 依賴)。
 *
 * ★★ 跨-view 全域詞法隔離(paper ↔ settings 共存;E2 HIGH 修復,本檔 IIFE-wrap 特別處置):
 *   tab-settings.html:837 與 tab-paper.html:366 都在**頂層**宣告 `let stateRevision = 0`(settings 另有
 *   13 個頂層 let/const)+ `function loadAll()`。兩者皆 native view,內聯 script 經 raw `appendChild(
 *   <script>)` 重跑=進**同一 Realm 共享 global lexical 環境**。classic script 頂層 `let/const/class`
 *   跨 script **重宣告 → SyntaxError,整段 script 不執行**(inserted-script parse error 是 window
 *   uncaught,shell.js / 本檔 try/catch 都捕不到)→ 第二個被 navigate 的 view **功能性死**(所有 onclick
 *   函式未定義 / 無 init / 無輪詢),且靜默。(function 重宣告只重賦值不拋,故舊版 window.loadAll save/restore
 *   漏了 let/const 這條——已由本修復取代。)
 *   **處置**:把 settings 重跑的內聯 script **IIFE 包裹**,使頂層 `let/const/class`(含 stateRevision)成
 *   IIFE-local→不進 global lexical→不與 paper 的頂層 `let stateRevision` 衝突。IIFE 內函式亦變 local,故
 *   尾端**自動發現**(掃 fetched html 的 on* 屬性引用的頂層 identifier,非硬編——隨錨新增函式自動涵蓋;
 *   掃 html 全文為 DOM 掃描的**超集**,兼收運行時模板注入的 handler:pfToggle / openApikeyDialog / peekApiKey)
 *   並 re-export 這批 onclick 函式至 window(demoAction / configAction / doSaveApiKey / saveAlertConfig / …);
 *   `loadAll` **不**在 on* 集內、**不寫 window.loadAll**(避免撞 paper 的 window.loadAll——只 paper.resume 讀之),
 *   改暴露至命名空間 `window.__ocSettingsLoadAll` 供 settings 自身 pause/resume。
 *   paper 保持 raw(其頂層 let 進 global lexical,settings IIFE 不觸→無重宣告);settings onclick 函式名與已遷
 *   native view(paper 等)**無交集**(實測 grep),re-export 無 last-writer-win 破壞。settings 頂層 let/const
 *   僅 script 內閉包用,**無被 onclick / DOM 當值外引**(實測:所有 on* 皆函式呼叫形,不讀狀態變數),故 IIFE-wrap
 *   對狀態變數安全。eval 當下的 `loadAll()`/`ocStartRefresh(loadAll,…)`(尾端自帶)用 IIFE 內**詞法** binding,
 *   首拉+啟輪詢照常。此為 isolate-settings-only 修復(通用「共享 inline 隔離 helper + 跨檔頂層詞法重名 guard 測試」
 *   記為 follow-up 下輪;本輪先讓 settings + paper 正確共存)。
 *
 * 注入 / 重跑(phase4「注入片段 + 重跑內聯 script」pattern,套用於 tab-settings.html):
 *   render → fetch /static/tab-settings.html → DOMParser 解析 → 把 <body> settings DOM 逐節點 clone
 *   進 `.settings-view` 宿主(byte-parity id/class/onclick/type=password;subtab nav + 4 pane +
 *   restart modal + API-key replace dialog + rst-banner)→ 再把大內聯 <script> 以全新 <script> 節點重跑。
 *   **跳過**:①外部 <script src>(common / formatters / mode-badge / modals / csrf 殼已載入,勿重複);
 *   ②首個內聯 <script>=`ocAuthCheck(); ocInjectBaseCSS();`(殼 boot 已 ocAuthCheck;ocInjectBaseCSS
 *   注入 body{padding}+`*` reset 破殼 chrome,禁呼——見 view-earn/paper.css MODULE_NOTE);
 *   ③頁內 style 塊(由 view-settings.css 以 `.settings-view` scope 供給,ratchet born-clean)。
 *
 * §3 憑證鐵則(本遷最重):**API-key / token / secret 明文永不暴露**。復用 verbatim 保既有三條合規:
 *   (a) GUI 只顯後端遮罩 hint(key_hint / bot_token_hint / secret_hint,如 ••••1234);
 *   (b) 敏感輸入框 type=password(dlg-apikey-secret / alert-tg-token / alert-wh-secret),
 *       placeholder 反映 *_configured 狀態(未設定顯「未設定」,已設定顯遮罩 hint);
 *   (c) 提交後**立即清 DOM**(doSaveApiKey / saveAlertConfig 於 POST 後即 value=''、closeApikeyDialog 亦清)。
 *   **本檔零新增讀取/顯示/log/回顯 key 明文的碼**——只 fetch+clone+重跑既有內聯 script,不觸憑證值。
 * canon-7(未接數據三態):api-key slot 未配置顯「未設定」(apiKeyStatusView has_key=false 分支),
 *   非假 active;告警 chip「已啟用但未完成設定 — 不會送出告警」防 soft fake-success;Decision Lease
 *   源不可得顯 unknown/yellow。皆由復用內聯 script 原樣渲染,本檔零 fake。
 * scheduled-restart:後端已 HTTP 410 停用(P2-14)。DOM 保留 disabled-state 佔位 + 停用按鈕;
 *   openRestartModal 首行 `return`(守衛防復活)。**本遷不復活、不接線**——保持後端停用態。
 * visibility 語義:pause=ocStopRefresh()(停 30s 輪詢,隱藏不續打後端=freshness/safety);
 *   resume=首拉 settingsLoadAll() + ocStartRefresh(settingsLoadAll, 30s) 重啟(鏡像 iframe 暫停)。
 *   ocStartRefresh 用 common.js 全域單例 `_ocRefreshTimer`;殼內實際呼 ocStartRefresh 者僅 paper 與
 *   settings(其餘 native view 自管 setInterval),且同時只一 view active(pause 清 timer),故單例零爭用。
 * 依賴(全復用,不重造):common.js($ / ocApi / ocPost / ocStartRefresh / ocStopRefresh / ocExplain /
 *   ocEnvelope / ocToast / ocSetText / ocSetHtml / ocEsc / classifyLiveMutation / ocResidualRiskBanner)、
 *   common-formatters.js、common-mode-badge.js、common-modals.js、fetch_with_csrf.js(ocCsrfHeaders);
 *   view-settings.css 供 `.settings-view` scope 樣式。
 * 誠實邊界:靜態(node --check + ratchet + 註冊 smoke)只證 source 事實;**真渲染 / API-key 真遮罩 /
 *   寫真行為 / confirm 真閘 / 三態徽 / 輪詢 = NEEDS-LINUX runtime + operator**,不由本刀 attest。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  // ── 模塊級狀態 ──
  var host = null;              // 原生 <section> 宿主(shell 注入)
  var root = null;              // `.settings-view` 內層宿主(view-settings.css scope root)
  var built = false;            // rendered guard(只首渲一次;防雙 fetch / 雙重跑內聯 script)
  var wired = false;            // 內聯 script 已重跑並定義全域函式 + 啟輪詢(async fetch 完成後轉真)
  var POLL_MS = 30000;          // 輪詢間隔(byte-parity tab-settings.html ocStartRefresh(loadAll, 30000))
  var TAB_SETTINGS_URL = '/static/tab-settings.html';  // src 保留=registry 完整性 + 回滾錨,同時作復用來源

  function warn(msg, e) { try { console.warn('[view-settings] ' + msg, e || ''); } catch (_) {} }

  // fail-closed 可見化:fetch / 解析失敗 → 顯錯不崩(對齊殼 iframe 載入失敗語義,不留空白)。
  function showLoadError(e) {
    warn('tab-settings.html 載入失敗 — Settings view inactive', e);
    if (root) {
      root.innerHTML =
        '<div class="oc-subtab-placeholder">設置載入失敗 — 可切其他視圖或返回舊版 Console(詳見瀏覽器 console)</div>';
    }
  }

  // 自動發現 fetched html 內所有 on* 事件屬性(onclick/onchange/oninput/…)引用的頂層函式名。
  //   非硬編(隨錨新增函式自動涵蓋);掃 html 全文=DOM 靜態屬性 ∪ 內聯 script 模板字串產出的 on*
  //   (如 pfToggle / openApikeyDialog / peekApiKey——純 clone-DOM 掃描漏這批運行時注入的 handler,
  //   故掃全文為其超集)。捕 `on<event>="<identifier>(` 的 identifier。
  function discoverOnHandlerNames(htmlText) {
    var names = {};
    var re = /on[a-z]+\s*=\s*["']\s*([A-Za-z_$][\w$]*)\s*\(/g;
    var m;
    while ((m = re.exec(htmlText)) !== null) { names[m[1]] = true; }
    return Object.keys(names);
  }

  // 重跑內聯 script(settings 無 DOMContentLoaded handler,append 當下同步自呼 init,故直接重跑;
  //   IIFE 包裹隔離頂層 let/const/class 防跨-view 詞法重宣告 SyntaxError——見 MODULE_NOTE ★★)。
  function rerunInlineScripts(scriptTexts, htmlText) {
    // 自動發現 → 生成 re-export 碼:IIFE 內函式提升可見,逐名 try/catch 兜底(某名非真頂層函式→ReferenceError→跳過)。
    //   identifier 由正則限定 [A-Za-z_$][\w$]*(合法識別字,無注入風險);key 走 JSON.stringify。
    var exportNames = discoverOnHandlerNames(htmlText);
    var reexport = '';
    exportNames.forEach(function (n) {
      reexport += 'try{window[' + JSON.stringify(n) + ']=' + n + ';}catch(_e){}\n';
    });
    scriptTexts.forEach(function (txt) {
      // IIFE 包裹:頂層 let/const/class(含 stateRevision)成 IIFE-local→不進 global lexical→不與 paper
      //   的頂層 `let stateRevision` 跨-script 重宣告(否則 SyntaxError 整段不執行,view 靜默死)。
      //   原 text 尾端自帶 loadAll()+ocStartRefresh(loadAll,30000)(IIFE 內詞法 binding,首拉+啟輪詢照常);
      //   其後 re-export onclick 函式至 window(否則 IIFE-local 令 onclick 破)+ 暴露 loadAll 至命名空間
      //   __ocSettingsLoadAll(供 pause/resume;不寫 window.loadAll 避免撞 paper.resume 所讀的 window.loadAll)。
      var wrapped =
        '(function(){\n' + txt + '\n;\n' +
        reexport +
        'try{window.__ocSettingsLoadAll=(typeof loadAll===\'function\'?loadAll:null);}catch(_e){}\n' +
        '})();';
      // 內聯 classic script 以全新 <script> 節點重跑(innerHTML/cloneNode 注入的 script 不自動執行);
      //   appendChild 當下同步執行。
      var s = document.createElement('script');
      s.textContent = wrapped;
      root.appendChild(s);
    });
    wired = true;
  }

  // 注入 tab-settings.html <body> 的 settings DOM(byte-parity clone)+ 重跑其內聯 script。
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
        inlineScripts.push(txt);  // 大 inline settings 邏輯 → 收集待重跑
        return;
      }
      if (node.nodeType === 1 && node.tagName === 'STYLE') return;  // 頁內樣式塊 → view-settings.css 供
      // 其餘 body 節點(rst-banner / subtab nav / 4 pane / restart modal / API-key dialog / 註釋)→ clone byte-parity
      root.appendChild(node.cloneNode(true));
    });

    // DOM 就位後重跑內聯 script(此時 $('explain-demo-control') 等 getElementById 皆可解;IIFE-wrap
    //   後 re-export 使 onclick 函式仍全域可達)。傳 html 供 on* 事件屬性自動發現(靜態 + 模板注入超集)。
    rerunInlineScripts(inlineScripts, html);
  }

  // ═══ shell router 契約:render / resume / pause ═══
  // render:建 `.settings-view` 宿主 + fetch tab-settings.html + 注入/重跑(built guard 只首渲一次);
  //   首拉 + 啟輪詢由重跑的內聯 script 自帶(尾端 loadAll()+ocStartRefresh),非本函式——尊重 async fetch 完成時序。
  function renderSettingsView(hostEl) {
    if (hostEl) host = hostEl;
    if (!host || built) return;
    built = true;
    root = document.createElement('div');
    root.className = 'settings-view';
    host.appendChild(root);
    root.innerHTML = '<div class="oc-subtab-placeholder">載入設置… / Loading…</div>';
    fetch(TAB_SETTINGS_URL, { credentials: 'same-origin' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); })
      .then(injectAndRun)
      .catch(showLoadError);
  }

  // resume:view 顯示 → 首拉一次(鏡像「顯示即刷新」)+ 重啟 30s 輪詢。fetch 未完成(!wired)時 no-op:
  //   重跑本身即會首拉 + 啟輪詢,無需在此重入。用 window.__ocSettingsLoadAll(IIFE 內暴露的 settings 自有
  //   loadAll;不用 window.loadAll,隔離 paper——見 MODULE_NOTE ★★)。
  function resumeSettingsView() {
    if (!built || !wired) return;
    var fn = window.__ocSettingsLoadAll;
    try { if (typeof fn === 'function') fn(); }
    catch (e) { warn('resume loadAll 失敗', e); }
    try {
      if (typeof window.ocStartRefresh === 'function' && typeof fn === 'function') {
        window.ocStartRefresh(fn, POLL_MS);
      }
    } catch (e) { warn('resume 重啟輪詢失敗', e); }
  }

  // pause:view 隱藏 → 停 30s 輪詢(freshness/safety:隱藏不得續打後端,鏡像 iframe 暫停語義)。
  //   ocStopRefresh 清 common.js 全域單例 timer;未啟輪詢時安全 no-op。
  function pauseSettingsView() {
    try { if (typeof window.ocStopRefresh === 'function') window.ocStopRefresh(); }
    catch (e) { warn('pause 停輪詢失敗', e); }
  }

  // 註冊進殼可見的原生 view 表(router 以 v.iframe===false 查此;key=VIEWS 的 id 'settings')。
  window.OC_NATIVE_VIEWS = window.OC_NATIVE_VIEWS || {};
  window.OC_NATIVE_VIEWS['settings'] = { render: renderSettingsView, resume: resumeSettingsView, pause: pauseSettingsView };
  // 具名導出(task 契約:renderSettingsView / pauseSettingsView / resumeSettingsView 可被引用)。
  window.renderSettingsView = renderSettingsView;
  window.resumeSettingsView = resumeSettingsView;
  window.pauseSettingsView = pauseSettingsView;
})();
