/*
 * view-paper.js — 玄衡原生 view「Legacy Paper / 舊 Paper 引擎」(Phase 2 第 11 個 iframe→原生遷移)
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:把 legacy `tab-paper.html`(iframe 後備)遷成玄衡殼內的**原生 view**。
 *   paper = **模擬紙上交易**(真實市場價、零真錢;預設關);session 寫(start/pause/resume/
 *   stop/stop-all/close)經 Rust 引擎 IPC,手動下單(submitPaperOrder)後端已 HTTP 410 停用。
 *   策略=**復用遷移(fetch tab-paper.html → 注入其 <body> paper DOM(byte-parity)→ 重跑其內聯
 *   <script>)**。**tab-paper.html / app-paper.js 零修改(reuse 正本 + rollback 錨)。**
 *
 * ★ 與 brief 的關鍵出入(以源碼為準,已於回報指出):
 *   brief 假設 paper session 邏輯在 app-paper.js(handlePaperAction/renderPaperSession,靠
 *   `[data-paper-action=start|pause|resume|stop]` DOM 綁定)。**源碼實測:tab-paper.html <body>
 *   零 `data-paper-action`**;session 控制是 `onclick="sessionAction('start')"`,而 sessionAction /
 *   loadSession / loadAll / closeAllPositions / 平倉 modal / 分頁成交 等**全部函式定義在
 *   tab-paper.html 自己的內聯 <script>(行 355-1030),非 app-paper.js**。app-paper.js 的
 *   handlePaperAction/renderPaperSession(帶 data-paper-action)是 **legacy index.html 舊路徑**,
 *   對 tab-paper.html 為死碼;tab-paper.html 只從 app-paper.js 復用 `ocPaperSubtabInit`(子標籤導航)。
 *   故忠實遷移 = 復用 tab-paper.html 的內聯 script(fetch + 重跑),非復用 app-paper.js 的 session fn。
 *   此為比 brief 更 byte-parity 的「reuse verbatim」(整檔字節,零複製 675 行內聯邏輯入本檔)。
 *
 * 注入 / 重跑(phase4 「注入片段 + 重跑內聯 script」pattern,套用於 tab-paper.html 整檔):
 *   render → fetch /static/tab-paper.html → DOMParser 解析 → 把 <body> 的 paper DOM 逐節點
 *   clone 進 `.paper-view` 宿主(byte-parity id/class/onclick;subtab nav、Session 內容[控制列 +
 *   餘額/PnL/持倉/訂單/成交/影子/性能 card 與表]、Compare disabled-card 掛點、Handoff 掛點、平倉
 *   modal)→ 再把其大內聯 <script> 以全新 <script> 節點重跑(定義全域 sessionAction/loadAll/… +
 *   首拉 loadAll() + ocStartRefresh(15s) + ocPaperSubtabInit())。
 *   **跳過**:①外部 <script src>(common / i18n / app-paper / handoff_helper 殼已載入,勿重複);
 *   ②首個內聯 <script>=`ocAuthCheck(); ocInjectBaseCSS();`(殼 boot 已 ocAuthCheck;ocInjectBaseCSS
 *   會注入 body{padding}+`*` reset 破殼 chrome,禁呼——見 view-earn.css MODULE_NOTE);
 *   ③頁內樣式塊(由 view-paper.css 以 `.paper-view` scope 供給,ratchet born-clean)。
 * DOMContentLoaded 依賴(殼內已過 → 手動觸發):tab-paper.html 內聯 script 尾端三個
 *   `document.addEventListener('DOMContentLoaded', …)`(mode-badge / Compare disabled-card /
 *   Handoff render)在殼 realm 永不 fire(DCL 早已觸發)。處置=**捕獲重跑**:重跑期間暫接管
 *   document.addEventListener 收下 DCL handler(其餘型別透傳),重跑後**逐一手動呼**——verbatim
 *   復用內聯 handler,零複製、零漂移(相對「港 40 行雙語 gate 字串入本檔」的漂移風險更安全)。
 *   接管窗口僅同步一瞬(內聯 classic script append 即同步執行),try/finally 保證復原,
 *   不觸 window.addEventListener('occurrencychange',…)(非 document,不攔)。
 * canon-7(預設關 → 停用態,非假 active):Compare 子標籤走 OpenClawDisabledStateCard(🔒 P3
 *   校準未上線);mode-badge 全 unknown/none(執行信心=none → ⚠ 紅外框防認知欺詐);Session 狀態
 *   徽由 loadSession 依真值三態(active/starting/其餘中性;連接失敗顯「連接失敗」不假綠)。皆由
 *   復用的內聯 script + helper 原樣渲染,本檔零 fake。
 * 硬邊界(canon / LOOP §6):
 *   ① session 寫(start/pause/resume/stop/stop-all、close/close-all、單倉 close)= 既有
 *      /api/v1/paper/session/* 與 positions close 端點,經 Rust 引擎 IPC,**byte-parity 復用**
 *      (重跑內聯 script,零新寫路徑);confirm 全保留(dual-stop=openConfirmModal('paper-stop-all')、
 *      平倉=paper-confirm-modal),response-gated(stop/close-all 走 classifyLiveMutation,殘留風險
 *      顯常駐紅橫幅,不一律顯綠)。**start 為 1-click 直送無 confirm(源碼實測,brief 稱「1-click
 *      confirm」不符,以源碼為準)**。
 *   ② submitPaperOrder 保持 HTTP 410 停用態:手動下單表單已於 P1 下架(DOM 僅存 disabled-state
 *      說明卡,無 submit 按鈕接線);app-paper.js submitPaperOrder 為防禦兜底(呼即 toast「已停用」),
 *      本遷不復活、不觸發。
 *   ③ visibility 語義:pause=ocStopRefresh()(停 15s 輪詢,隱藏不續打後端=freshness/safety);
 *      resume=首拉 + ocStartRefresh(loadAll,15s) 重啟(鏡像 iframe openclaw-tab-visibility 暫停)。
 *      ocStartRefresh 用 common.js 全域單例 `_ocRefreshTimer`;殼內無其他 native view 呼 ocStartRefresh
 *      (實測 view-*.js 皆自管 setInterval),故 paper 獨佔此單例、零 timer 爭用。
 * 依賴(全復用,不重造):app-paper.js(ocPaperSubtabInit,殼已載 R68 for replay)、common.js
 *   ($ / ocApi / ocPost / ocStartRefresh / ocStopRefresh / ocInitFx / classifyLiveMutation /
 *   ocResidualRiskBanner / OpenClawDisabledStateCard)、common-formatters.js(ocMoney/ocSide/…)、
 *   common-mode-badge.js(OpenClawModeBadge)、common-modals.js(openConfirmModal)、
 *   handoff_helper.js(OpenClawHandoff,殼此遷新增);view-paper.css 供 `.paper-view` scope 樣式。
 * 誠實邊界:靜態(node --check + ratchet + 註冊 smoke)只證 source 事實;**真渲染 / session 寫真行為 /
 *   confirm 真閘 / 三態徽 / 輪詢 = NEEDS-LINUX runtime + operator**,不由本刀 attest。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  // ── 模塊級狀態 ──
  var host = null;           // 原生 <section> 宿主(shell 注入)
  var root = null;           // `.paper-view` 內層宿主(view-paper.css scope root)
  var built = false;         // rendered guard(只首渲一次;防雙 fetch / 雙重跑內聯 script)
  var wired = false;         // 內聯 script 已重跑並定義全域函式 + 啟輪詢(async fetch 完成後轉真)
  var POLL_MS = 15000;       // 輪詢間隔(byte-parity tab-paper.html ocStartRefresh(loadAll,15000))
  var TAB_PAPER_URL = '/static/tab-paper.html';  // src 保留=registry 完整性 + 回滾錨,同時作復用來源

  function warn(msg, e) { try { console.warn('[view-paper] ' + msg, e || ''); } catch (_) {} }

  // fail-closed 可見化:fetch / 解析失敗 → 顯錯不崩(對齊殼 iframe 載入失敗語義,不留空白)。
  function showLoadError(e) {
    warn('tab-paper.html 載入失敗 — Legacy Paper view inactive', e);
    if (root) {
      root.innerHTML =
        '<div class="oc-subtab-placeholder">Legacy Paper 載入失敗 — 可切其他視圖或返回舊版 Console(詳見瀏覽器 console)</div>';
    }
  }

  // 重跑內聯 script + 捕獲/手動觸發其 DOMContentLoaded handler(殼內 DCL 已過)。
  function rerunInlineScripts(scriptTexts) {
    // 暫接管 document.addEventListener:收下 DCL handler,其餘型別透傳(fail-safe 復原)。
    var captured = [];
    var origAdd = document.addEventListener;
    document.addEventListener = function (type, fn, opts) {
      if (type === 'DOMContentLoaded') { if (typeof fn === 'function') captured.push(fn); return; }
      return origAdd.call(document, type, fn, opts);
    };
    try {
      scriptTexts.forEach(function (txt) {
        // 內聯 classic script 以全新 <script> 節點重跑(innerHTML/cloneNode 注入的 script 不自動執行);
        //   appendChild 當下同步執行 → 定義全域 fn + 首拉 loadAll() + ocStartRefresh + ocPaperSubtabInit()。
        var s = document.createElement('script');
        s.textContent = txt;
        root.appendChild(s);
      });
    } finally {
      document.addEventListener = origAdd;   // 無論成敗必復原(防全域殘留破 app)
    }
    // 手動觸發被捕獲的 DCL init(mode-badge / Compare disabled-card / Handoff)—— verbatim 復用內聯 handler。
    captured.forEach(function (fn) {
      try { fn(); } catch (e) { warn('inline DOMContentLoaded init 失敗', e); }
    });
  }

  // 注入 tab-paper.html <body> 的 paper DOM(byte-parity clone)+ 重跑其內聯 script。
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
        inlineScripts.push(txt);  // 大 inline paper 邏輯 → 收集待重跑
        return;
      }
      if (node.nodeType === 1 && node.tagName === 'STYLE') return;  // 頁內樣式塊 → view-paper.css 供
      // 其餘 body 節點(subtab nav / Session 內容 / Compare / Handoff mount / 平倉 modal / 註釋)→ clone byte-parity
      root.appendChild(node.cloneNode(true));
    });

    // DOM 就位後重跑內聯 script(此時 $('explain-paper') 等 getElementById 皆可解;fn 成全域,onclick 可達)。
    rerunInlineScripts(inlineScripts);
    wired = true;
  }

  // ═══ shell router 契約:render / resume / pause ═══
  // render:建 `.paper-view` 宿主 + fetch tab-paper.html + 注入/重跑(built guard 只首渲一次);
  //   首拉 + 啟輪詢由重跑的內聯 script 自帶(ocStartRefresh),非本函式——尊重 async fetch 完成時序。
  function renderPaperView(hostEl) {
    if (hostEl) host = hostEl;
    if (!host || built) return;
    built = true;
    root = document.createElement('div');
    root.className = 'paper-view';
    host.appendChild(root);
    root.innerHTML = '<div class="oc-subtab-placeholder">載入 Legacy Paper… / Loading…</div>';
    fetch(TAB_PAPER_URL, { credentials: 'same-origin' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); })
      .then(injectAndRun)
      .catch(showLoadError);
  }

  // resume:view 顯示 → 首拉一次(鏡像「顯示即刷新」)+ 重啟 15s 輪詢。fetch 未完成(!wired)時 no-op:
  //   重跑本身即會首拉 + 啟輪詢,無需在此重入。ocStartRefresh 冪等(clear 後重設單例 timer)。
  function resumePaperView() {
    if (!built || !wired) return;
    try { if (typeof window.loadAll === 'function') window.loadAll(); }
    catch (e) { warn('resume loadAll 失敗', e); }
    try {
      if (typeof window.ocStartRefresh === 'function' && typeof window.loadAll === 'function') {
        window.ocStartRefresh(window.loadAll, POLL_MS);
      }
    } catch (e) { warn('resume 重啟輪詢失敗', e); }
  }

  // pause:view 隱藏 → 停 15s 輪詢(freshness/safety:隱藏不得續打後端,鏡像 iframe 暫停語義)。
  //   ocStopRefresh 清 common.js 全域單例 timer;未啟輪詢時安全 no-op。
  function pausePaperView() {
    try { if (typeof window.ocStopRefresh === 'function') window.ocStopRefresh(); }
    catch (e) { warn('pause 停輪詢失敗', e); }
  }

  // 註冊進殼可見的原生 view 表(router 以 v.iframe===false 查此;key=VIEWS 的 id 'paper')。
  window.OC_NATIVE_VIEWS = window.OC_NATIVE_VIEWS || {};
  window.OC_NATIVE_VIEWS['paper'] = { render: renderPaperView, resume: resumePaperView, pause: pausePaperView };
  // 具名導出(task 契約:renderPaperView / pausePaperView / resumePaperView 可被引用)。
  window.renderPaperView = renderPaperView;
  window.resumePaperView = resumePaperView;
  window.pausePaperView = pausePaperView;
})();
