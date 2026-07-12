/*
 * view-overview.js — 玄衡原生 view「總覽 / Overview」(Phase 2 第 14 個 iframe→原生遷移)
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:把 legacy `tab-system.html`(iframe 後備)遷成玄衡殼內的**原生 view**。
 *   overview = **總覽儀表板**(運行態摘要 / 全局模式控制 / 治理狀態 / 業務概覽 / 來源上下文 /
 *   健康摘要 / 產品族 / 確認 modal);**交易關鍵**——含 **LIVE session stop 寫**與 §3 LIVE 硬化面。
 *   策略=**復用遷移(fetch tab-system.html → 注入其 <body> overview DOM(byte-parity)→ 重跑其
 *   內聯 <script>)**,同 settings R70 pattern。**tab-system.html / governance.js 零修改(reuse 正本 + rollback 錨)。**
 *
 * ★ skin-only 只換皮不改邏輯(§3 逐字保留零弱化,本遷最高關注):
 *   view-overview.js **零自建寫路徑**——只 fetch + clone DOM + 重跑既有內聯 script。§3 LIVE 硬化面
 *   全在復用的內聯 script 內 byte-parity 續生效,IIFE-wrap **不觸碰** confirm 流程 / 延遲值 / hold 邏輯:
 *   ① 切到 live_reserved 受 **5000ms 倒計時(LIVE_RESERVED_CONFIRM_DELAY_MS)+ 1200ms 按住
 *      (LIVE_RESERVED_HOLD_MS)confirm guard**(startLiveReservedConfirmGuard / setLiveConfirmReady /
 *      beginLiveReservedConfirmHold / countdown·hold timers)—— 常數與 hold 邏輯 verbatim,單擊不切換;
 *   ② 切離 live_reserved **自動 live-stop**(executeModeChange 內 `ocPost('/api/v1/live/session/stop')`)verbatim;
 *   ③ `--live` 熱紅主題 class(.purple / .mode-btn--live / .warn-box--live / .confirm-live-guard /
 *      .oc-chip-live / .live-hold-*)由 view-overview.css 逐字保留,live_reserved 態不稀釋;
 *   ④ 五閘語義(mode/auth/cap 顯真態)、confirmAction / confirmMode 二次確認、REAL FUNDS 常駐標識全 verbatim。
 *   LiveDemo 不因 endpoint 降級。**本檔不得繞過 / 短路 / 改任何 confirm 或寫。**
 *
 * ★★ 與 brief 的關鍵出入(以源碼為準,已於回報指出):
 *   ① brief 稱「8 inline script + 2 style 塊」;源碼實測 tab-system.html <body> 只有 **2 個內聯
 *      <script>**:行 19(`ocAuthCheck(); ocInjectBaseCSS();`,跳過)+ 行 297-1116(**單一大內聯
 *      script**,承全部 overview 邏輯);且只有 **1 個真 style 塊**(行 21-94)。ratchet 記 style_block=2
 *      是因註釋文字(行 72)提及 style 標籤字面被計數,非真標籤。「重跑內聯 script」= 重跑這唯一大塊。
 *   ② brief 查 DOMContentLoaded;源碼實測 tab-system.html **零 DOMContentLoaded handler**——內聯 script
 *      於 eval 當下自呼 init(頂層 `$('explain-runtime').innerHTML=…` / applyDevelopmentSupportVisibility /
 *      尾端 setupLiveReservedConfirmButton() + loadAll() + ocStartRefresh(loadAll,15000))。故**直接重跑即可**,
 *      無需 paper 的 DCL 捕獲 shim(同 settings,比 paper 更簡)。
 *
 * ★★★ 跨-view 全域詞法隔離(paper ↔ settings ↔ overview 共存;R71 guard 非協商,本檔 IIFE-wrap 特別處置):
 *   tab-system.html 頂層宣告大量 `let/const`(MODE_CN/AUTH_CN/CAP_CN/MODE_TO_SWITCH[實為函式內]、
 *   LIVE_RESERVED_CONFIRM_DELAY_MS/LIVE_RESERVED_HOLD_MS、`let _liveConfirm*` timers、`let _stateRevision`、
 *   `let _paperActive/…`、MODE_CONFIRM、CONFIRM_MSGS 等)+ `async function loadAll`。classic script 經 raw
 *   `appendChild(<script>)` 重跑=進**同一 Realm 共享 global lexical**;頂層 `let/const/class` 跨 script 重宣告
 *   → SyntaxError,整段不執行 → view 靜默功能死。且 overview 的 `async function loadAll` 若 raw 重跑會**撞 paper
 *   的 window.loadAll**(paper.resume 讀之)。
 *   **處置**:把重跑的內聯 script **IIFE 包裹**,頂層 `let/const/class`(含 _stateRevision / _liveConfirm* timers /
 *   LIVE_RESERVED_* 常數)成 IIFE-local → 不進 global lexical → 過 R71 guard(overview 判 isolated,貢獻空集)。
 *   `_liveConfirm* timers`(頂層 let)IIFE-local,由 confirm 函式閉包照常用;confirm 函式(confirmAction /
 *   confirmMode / closeConfirm / handleConfirmOkClick)re-export 至 window,onclick 屬性可達;beginLiveReservedConfirmHold /
 *   cancelLiveReservedConfirmHold 由 setupLiveReservedConfirmButton 內 addEventListener 綁定(IIFE-local 詞法,無需 window)。`loadAll` **不**在
 *   on* 集、**不寫 window.loadAll**(避免撞 paper),改暴露 `window.__ocOverviewLoadAll` 供 pause/resume。
 *   overview onclick 集(confirmAction / confirmMode / closeConfirm / handleConfirmOkClick)與 paper
 *   (sessionAction / closeAllPositions / …)、settings(demoAction / configAction / …)**無交集**(實測 grep),
 *   re-export 無 last-writer-win 破壞。eval 當下 setupLiveReservedConfirmButton()+loadAll()+ocStartRefresh 用
 *   IIFE 內詞法 binding,首綁 confirm 按鈕 + 首拉 + 啟輪詢照常。
 *
 * 注入 / 重跑(phase4「注入片段 + 重跑內聯 script」pattern,套用於 tab-system.html):
 *   render → fetch /static/tab-system.html → DOMParser 解析 → 把 <body> overview DOM 逐節點 clone 進
 *   `.overview-view` 宿主(byte-parity id/class/onclick;運行態摘要 + 快捷操作 + 全局模式控制 + 治理狀態 +
 *   業務概覽 + 來源/健康雙欄 + 產品族 collapse + **確認 modal 含 live-confirm-guard**)→ 再把大內聯 <script>
 *   以全新 <script> 節點 IIFE-wrap 重跑。
 *   **跳過**:①外部 <script src>(common-formatters / mode-badge / modals / csrf / common / **governance.js** 殼已載入,勿重複);
 *   ②首個內聯 <script>=`ocAuthCheck(); ocInjectBaseCSS();`(殼 boot 已 ocAuthCheck;ocInjectBaseCSS 注入
 *   body{padding}+`*` reset 破殼 chrome,禁呼——見 view-earn/paper.css MODULE_NOTE);
 *   ③頁內 style 塊(由 view-overview.css 以 `.overview-view` scope 供給,含 --live 熱紅主題 class,ratchet born-clean)。
 * 寫面(byte-parity 復用,零新寫路徑):paper session start/stop(/api/v1/paper/session/{start,stop})、
 *   **LIVE session stop(/api/v1/live/session/stop)**、mode 切換 config-change(ocEnvelope→/api/v1/input/config-change)
 *   全在復用的內聯 script,經 Rust 引擎 IPC;confirm 全保留,response-gated(classifyLiveMutation / ocResidualRiskBanner)。
 * canon-7(未接數據三態,非假 active):mode/auth/cap 由 loadOverview 依真值渲染;engine_alive 讀取失敗顯「未知 ?」
 *   (yellow)非假「運行中」;governance badge 源不可得顯 N/A;--live 熱紅在 live_reserved 態顯示不稀釋。皆由復用
 *   內聯 script 原樣渲染,本檔零 fake。
 * visibility 語義:pause=ocStopRefresh()(停 15s 輪詢,隱藏不續打後端=freshness/safety);
 *   resume=首拉 __ocOverviewLoadAll() + ocStartRefresh(__ocOverviewLoadAll, 15s) 重啟(鏡像 iframe 暫停)。
 *   ocStartRefresh 用 common.js 全域單例 `_ocRefreshTimer`;殼內呼 ocStartRefresh 者僅 paper / settings / overview,
 *   且同時只一 view active(pause 清 timer),故單例零爭用。
 * 依賴(全復用,不重造):common.js($ / ocApi / ocPost / ocStartRefresh / ocStopRefresh / ocExplain /
 *   ocEnvelope / ocToast / ocSetText / ocSetHtml / ocEsc / ocChip / ocMoney / ocPnlClass / ocBalance /
 *   classifyLiveMutation / ocResidualRiskBanner)、common-formatters.js、common-mode-badge.js、
 *   common-modals.js、fetch_with_csrf.js(ocCsrfHeaders)、**governance.js**(govAuthBadge / govRiskBadge / …,
 *   loadGovernanceStatus 用;殼已於 shell.html 載入);view-overview.css 供 `.overview-view` scope 樣式。
 * 誠實邊界:靜態(node --check + ratchet + 註冊 smoke + R71 guard)只證 source 事實;**真渲染 / LIVE-stop 真行為 /
 *   5s+1.2s confirm guard 真閘 / --live 真渲染 / mode/auth/cap 三態 / 輪詢 = NEEDS-LINUX runtime + operator**,
 *   不由本刀 attest。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  // ── 模塊級狀態 ──
  var host = null;              // 原生 <section> 宿主(shell 注入)
  var root = null;              // `.overview-view` 內層宿主(view-overview.css scope root)
  var built = false;            // rendered guard(只首渲一次;防雙 fetch / 雙重跑內聯 script / live confirm 雙綁)
  var wired = false;            // 內聯 script 已重跑並定義全域函式 + 啟輪詢(async fetch 完成後轉真)
  var POLL_MS = 15000;          // 輪詢間隔(byte-parity tab-system.html ocStartRefresh(loadAll, 15000))
  var TAB_SYSTEM_URL = '/static/tab-system.html';  // src 保留=registry 完整性 + 回滾錨,同時作復用來源

  function warn(msg, e) { try { console.warn('[view-overview] ' + msg, e || ''); } catch (_) {} }

  // fail-closed 可見化:fetch / 解析失敗 → 顯錯不崩(對齊殼 iframe 載入失敗語義,不留空白)。
  function showLoadError(e) {
    warn('tab-system.html 載入失敗 — Overview view inactive', e);
    if (root) {
      root.innerHTML =
        '<div class="oc-subtab-placeholder">總覽載入失敗 — 可切其他視圖或返回舊版 Console(詳見瀏覽器 console)</div>';
    }
  }

  // 自動發現 fetched html 內所有 on* 事件屬性(onclick/onchange/…)引用的頂層函式名。
  //   非硬編(隨錨新增函式自動涵蓋);掃 html 全文=DOM 靜態屬性 ∪ 內聯 script 模板字串產出的 on* 的超集。
  //   捕 `on<event>="<identifier>(` 的 identifier。overview 現況集={confirmAction, confirmMode, closeConfirm,
  //   handleConfirmOkClick}(全與 paper / settings onclick 集無交集)。
  function discoverOnHandlerNames(htmlText) {
    var names = {};
    var re = /on[a-z]+\s*=\s*["']\s*([A-Za-z_$][\w$]*)\s*\(/g;
    var m;
    while ((m = re.exec(htmlText)) !== null) { names[m[1]] = true; }
    return Object.keys(names);
  }

  // 重跑內聯 script(overview 無 DOMContentLoaded handler,append 當下同步自呼 init,故直接重跑;
  //   IIFE 包裹隔離頂層 let/const/class 防跨-view 詞法重宣告 SyntaxError + 撞 paper 的 window.loadAll——見 ★★★)。
  function rerunInlineScripts(scriptTexts, htmlText) {
    // 自動發現 → 生成 re-export 碼:IIFE 內函式提升可見,逐名 try/catch 兜底(某名非真頂層函式→ReferenceError→跳過)。
    //   identifier 由正則限定 [A-Za-z_$][\w$]*(合法識別字,無注入風險);key 走 JSON.stringify。
    var exportNames = discoverOnHandlerNames(htmlText);
    var reexport = '';
    exportNames.forEach(function (n) {
      reexport += 'try{window[' + JSON.stringify(n) + ']=' + n + ';}catch(_e){}\n';
    });
    scriptTexts.forEach(function (txt) {
      // IIFE 包裹:頂層 let/const/class(含 _stateRevision / _liveConfirm* timers / LIVE_RESERVED_* 常數)成
      //   IIFE-local → 不進 global lexical → 不與 paper/settings 頂層跨-script 重宣告(否則 SyntaxError 整段不執行,
      //   view 靜默死),過 R71 guard(overview 判 isolated,貢獻空集)。原 text 尾端自帶
      //   setupLiveReservedConfirmButton()+loadAll()+ocStartRefresh(loadAll,15000)(IIFE 內詞法 binding,首綁 confirm
      //   按鈕 + 首拉 + 啟輪詢照常);其後 re-export onclick 函式至 window(否則 IIFE-local 令 onclick 破)+ 暴露 loadAll
      //   至命名空間 __ocOverviewLoadAll(供 pause/resume;不寫 window.loadAll 避免撞 paper.resume 所讀的 window.loadAll)。
      //   §3 保證:IIFE-wrap 純作用域收束,不觸碰 confirm 流程 / 5000·1200 常數 / hold 邏輯 / live-stop 寫的任何字節。
      var wrapped =
        '(function(){\n' + txt + '\n;\n' +
        reexport +
        'try{window.__ocOverviewLoadAll=(typeof loadAll===\'function\'?loadAll:null);}catch(_e){}\n' +
        '})();';
      // 內聯 classic script 以全新 <script> 節點重跑(innerHTML/cloneNode 注入的 script 不自動執行);
      //   appendChild 當下同步執行。
      var s = document.createElement('script');
      s.textContent = wrapped;
      root.appendChild(s);
    });
    wired = true;
  }

  // 注入 tab-system.html <body> 的 overview DOM(byte-parity clone)+ 重跑其內聯 script。
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
        inlineScripts.push(txt);  // 大 inline overview 邏輯 → 收集待重跑
        return;
      }
      if (node.nodeType === 1 && node.tagName === 'STYLE') return;  // 頁內樣式塊 → view-overview.css 供
      // 其餘 body 節點(運行態摘要 / 快捷操作 / 全局模式控制 / 治理狀態 / 業務概覽 / 雙欄 / 產品族 / 確認 modal / 註釋)→ clone byte-parity
      root.appendChild(node.cloneNode(true));
    });

    // DOM 就位後重跑內聯 script(此時 $('explain-runtime') / $('confirm-ok') 等 getElementById 皆可解;IIFE-wrap
    //   後 re-export 使 onclick 函式仍全域可達)。傳 html 供 on* 事件屬性自動發現(靜態 + 模板注入超集)。
    rerunInlineScripts(inlineScripts, html);
  }

  // ═══ shell router 契約:render / resume / pause ═══
  // render:建 `.overview-view` 宿主 + fetch tab-system.html + 注入/重跑(built guard 只首渲一次);
  //   首拉 + 啟輪詢 + live confirm 綁定由重跑的內聯 script 自帶(尾端),非本函式——尊重 async fetch 完成時序。
  function renderOverviewView(hostEl) {
    if (hostEl) host = hostEl;
    if (!host || built) return;
    built = true;
    root = document.createElement('div');
    root.className = 'overview-view';
    host.appendChild(root);
    root.innerHTML = '<div class="oc-subtab-placeholder">載入總覽… / Loading…</div>';
    fetch(TAB_SYSTEM_URL, { credentials: 'same-origin' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); })
      .then(injectAndRun)
      .catch(showLoadError);
  }

  // resume:view 顯示 → 首拉一次(鏡像「顯示即刷新」)+ 重啟 15s 輪詢。fetch 未完成(!wired)時 no-op:
  //   重跑本身即會首拉 + 啟輪詢,無需在此重入。用 window.__ocOverviewLoadAll(IIFE 內暴露的 overview 自有
  //   loadAll;不用 window.loadAll,隔離 paper——見 ★★★)。resume 不重跑 script,故不會重綁 live confirm timers。
  function resumeOverviewView() {
    if (!built || !wired) return;
    var fn = window.__ocOverviewLoadAll;
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
  function pauseOverviewView() {
    try { if (typeof window.ocStopRefresh === 'function') window.ocStopRefresh(); }
    catch (e) { warn('pause 停輪詢失敗', e); }
  }

  // 註冊進殼可見的原生 view 表(router 以 v.iframe===false 查此;key=VIEWS 的 id 'overview')。
  window.OC_NATIVE_VIEWS = window.OC_NATIVE_VIEWS || {};
  window.OC_NATIVE_VIEWS['overview'] = { render: renderOverviewView, resume: resumeOverviewView, pause: pauseOverviewView };
  // 具名導出(task 契約:renderOverviewView / pauseOverviewView / resumeOverviewView 可被引用)。
  window.renderOverviewView = renderOverviewView;
  window.resumeOverviewView = resumeOverviewView;
  window.pauseOverviewView = pauseOverviewView;
})();
