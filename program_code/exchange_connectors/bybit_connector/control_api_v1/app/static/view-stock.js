/*
 * view-stock.js — 玄衡原生 view「Stock/ETF · IBKR Readiness」(Phase 2 第 13 個 iframe→原生遷移)
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:把 legacy `tab-stock-etf.html`(iframe 後備)遷成玄衡殼內的**原生 view**。
 *   stock = **IBKR stock_etf_cash 通道就緒度儀表板**(ADR-0048;paper/shadow/Phase 2 首接觸閘)。
 *   **純唯讀**:全樹 16 個 `/api/v1/stock-etf/*-status` GET 快照(lane/readiness/policy/authorization/
 *   account/evidence/universe/shadow/paper/reconciliation/scorecard/launch/data-foundation/phase0/
 *   release-packet/disable-cleanup),**零寫**(親證:11 JS + HTML 無 ocPost/ocDelete/method:POST)。
 *   **復用遷移**:11 個外部 JS 模組逐字復用,tab-stock-etf.html / 11 JS **零修改**(reuse 正本 + 回滾錨)。
 *
 * 遷移機制(三段;比 paper/settings「fetch+重跑內聯 script」再乾淨,因 stock 的編排邏輯本就在外部 JS):
 *   ① DOM 復用(byte-parity):render fetch /static/tab-stock-etf.html → DOMParser → 逐節點 clone
 *      其 <body> 的 stock DOM(唯一頂層子節點=`div.se-wrap`,含全部 `se-*-panel` 掛載點)進
 *      `.stock-view` 宿主。**跳過** 11 個外部 script(含 bootstrap)與頁內樣式塊。
 *      clone 保 id/class/onclick byte-parity —— 編排器靠 getElementById('se-*-panel/-body/-status/…')
 *      掛載,id 缺 → render no-op/拋,故 byte-parity 是硬需求(以 fetch 活檔 clone 保證,零複製漂移)。
 *   ② 10 純渲染模組於**殼 boot** 載入(shell.html;phase0/release-packet/disable-cleanup/reconciliation/
 *      readiness/data-policy/fallbacks/auth-account/evidence-paper/scorecard-launch)。它們 load-safe:
 *      定義 window.render* / window.*Fallback / window.STOCK_ETF_*_ENDPOINT 與若干全域函式,**load 時零
 *      DOM 存取、零副作用**(僅定義),故先於 DOM 存在也安全。
 *   ③ 編排器 tab-stock-etf.js 於 render **動態注入**(classic `<script src>`):其底部 module-level
 *      `waitForServerUp(loadReadiness)` 自跑 —— DOM 已就位 → fetch 全狀態 → 呼 window.render* 渲染進
 *      各 se-*-panel。**用 `.src`(非 `.textContent`)注入**:①R71 inline-reuse 詞法 guard 只掃
 *      「createElement('script')+.textContent+append」形狀,本 view 用 .src → **不被歸類 inline-reuse**
 *      → 其頂層 const 不被納入跨檔詞法碰撞掃描;②`injected` guard 保只注入一次(見下 ★)。
 *
 * ★ built / injected 雙 guard(防雙跑):
 *   - built:render 冪等(殼 ensureNativeRendered 本已冪等,再加一層防 async fetch 期間重入)。
 *   - injected:tab-stock-etf.js **頂層有 `const LANE_STATUS_ENDPOINT`…13 個 const + loadReadiness/
 *     renderFallback**;classic script 二次注入會「Identifier already declared」SyntaxError → 靜默死。
 *     injected guard 確保**只注入一次** → 單次頂層宣告,無重宣告。
 *
 * ★ 與架構地圖的出入(以源碼實測為準,已於回報指出):
 *   1) 地圖稱「10 純渲染模組各 IIFE」——**實測 5 個非 IIFE**(release-packet/disable-cleanup=window.*
 *      賦值;reconciliation/data-policy/fallbacks=頂層 `function` 宣告)。但**全 load-safe**(無頂層
 *      let/const/class → 殼 boot 零詞法碰撞;無頂層 DOM 存取)。generic 全域名(toneFor/setChip/textChip/
 *      boolChip/kvRow/chipList,由 data-policy.js 洩漏至全域;IIFE 模組與 view-gates.js 的同名版本皆
 *      IIFE-local 不外洩)在殼 boot 無他檔以 let/const/class 撞、亦無他檔同名 function 覆寫 → 與 production
 *      tab-stock-etf.html realm 行為**逐位一致**(親證:grep 全 boot 全域檔)。
 *   2) 地圖稱「loadReadiness 是 tab-stock-etf.js 內部 local,未暴露」——**實測 loadReadiness 是頂層
 *      `async function` = 全域(window.loadReadiness)**;refresh 鈕 onclick="loadReadiness()" 靠此,
 *      注入後可達。故 resume **可**呼 window.loadReadiness() 重 fetch —— 但仍選 no-op(理由見下)。
 *
 * pause/resume no-op(誠實註明):stock = **一次性 readiness 快照**(無 setInterval、無輪詢)。
 *   - pause:無 timer 需停(隱藏不會有背景輪詢續打後端 → 無 freshness/safety 退步問題,不同於 paper)。
 *   - resume:readiness **非即時流**(非 live PnL);首載已由注入的編排器 waitForServerUp(loadReadiness)
 *     快照一次,operator 用頁內「刷新 / Refresh」鈕(onclick=window.loadReadiness)手動更新即可。resume
 *     重 fetch 會與首載自初始化**雙 fetch**且無實益 → 故 no-op。此為最小且誠實的選擇。
 *
 * canon-7(未接/server-down → fallback / blocked 態,非假 ready):編排器 loadReadiness 內建 fallback
 *   邏輯 —— readiness payload 缺 → renderFallback()(readiness_state='degraded'、phase2_gate='BLOCKED'、
 *   live_denied=true、各面 *Fallback('api_unavailable'));個別面缺 data 亦逐一退 *Fallback。**復用逐字
 *   保留**,本檔零 fake。憑證零明文:readiness 只顯狀態旗標(accepted/blockers/…),不顯任何 key。
 * 硬邊界:**零寫**(本檔不引入任何寫路徑;stock 全 GET);IBKR 寫/激活 UI 不在此(殼不新增)。
 * 依賴(全復用,不重造):common.js(ocApi / waitForServerUp);10 純渲染模組(殼 boot 載);
 *   tab-stock-etf.js(render 動態注入);view-stock.css 供 `.stock-view` scope 樣式。
 * 誠實邊界:靜態(node --check + ratchet + 註冊 + inline-reuse guard)只證 source 事實;**真渲染 /
 *   真 16-GET fetch / readiness 真態 / fallback 真觸發 = NEEDS-LINUX runtime + operator**,不由本刀 attest。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  // ── 模塊級狀態 ──
  var host = null;           // 原生 <section> 宿主(shell 注入)
  var root = null;           // `.stock-view` 內層宿主(view-stock.css scope root)
  var built = false;         // render 冪等 guard(只首渲一次;防 async fetch 期間重入)
  var injected = false;      // 編排器只注入一次 guard(防頂層 const 二次宣告 SyntaxError)
  var TAB_STOCK_HTML = '/static/tab-stock-etf.html';  // DOM 復用來源 + 回滾錨
  var TAB_STOCK_JS = '/static/tab-stock-etf.js';      // 編排器(loadReadiness/waitForServerUp),render 動態注入

  function warn(msg, e) { try { console.warn('[view-stock] ' + msg, e || ''); } catch (_) {} }

  // fail-closed 可見化:fetch / 解析失敗 → 顯錯不崩(對齊殼 iframe 載入失敗語義,不留空白)。
  function showLoadError(e) {
    warn('tab-stock-etf.html 載入失敗 — Stock/ETF Readiness view inactive', e);
    if (root) {
      root.innerHTML =
        '<div class="stock-note">Stock/ETF Readiness 載入失敗 — 可切其他視圖或返回舊版 Console(詳見瀏覽器 console)</div>';
    }
  }

  // 動態注入編排器 tab-stock-etf.js(classic <script src>):DOM 已就位 → 其底部
  //   waitForServerUp(loadReadiness) 自跑,fetch 全狀態並渲染進各 se-*-panel。
  // 用 .src(非 .textContent):R71 inline-reuse 詞法 guard 不歸類本 view(見 MODULE_NOTE ③)。
  // injected guard:只注入一次(頂層 const 二次宣告會 SyntaxError → 靜默死)。
  function injectOrchestrator() {
    if (injected || !root) return;
    injected = true;
    var s = document.createElement('script');
    s.src = TAB_STOCK_JS;
    s.async = false;   // 確定性執行(單一注入,順序無他依賴,顯式標明)
    s.onerror = function () { warn('tab-stock-etf.js 載入失敗 — readiness 不會渲染'); };
    root.appendChild(s);
  }

  // 注入 tab-stock-etf.html <body> 的 stock DOM(byte-parity clone)+ 觸發編排器。
  function injectDom(html) {
    if (!root) return;
    var doc;
    try { doc = new DOMParser().parseFromString(html, 'text/html'); }
    catch (e) { showLoadError(e); return; }
    if (!doc || !doc.body) { showLoadError(new Error('no body')); return; }

    root.innerHTML = '';   // 清 loading 佔位
    Array.prototype.forEach.call(doc.body.childNodes, function (node) {
      // 跳過 script 節點(11 外部 src + ocAuthCheck/ocInjectBaseCSS bootstrap)與頁內樣式塊(style 節點,
      //   由 view-stock.css 以 `.stock-view` scope 供給)。其餘(div.se-wrap 及空白/註釋)→ byte-parity clone。
      if (node.nodeType === 1 && (node.tagName === 'SCRIPT' || node.tagName === 'STYLE')) return;
      root.appendChild(node.cloneNode(true));
    });

    // DOM 就位後注入編排器(此時 getElementById('se-*-panel') 皆可解;onclick=loadReadiness 可達)。
    injectOrchestrator();
  }

  // ═══ shell router 契約:render / resume / pause ═══
  // render:建 `.stock-view` 宿主 + fetch tab-stock-etf.html + 注入 DOM/編排器(built guard 只首渲一次);
  //   首拉由編排器自帶 waitForServerUp(loadReadiness),非本函式——尊重 async fetch 完成時序。
  function renderStockView(hostEl) {
    if (hostEl) host = hostEl;
    if (!host || built) return;
    built = true;
    root = document.createElement('div');
    root.className = 'stock-view';
    host.appendChild(root);
    root.innerHTML = '<div class="stock-note">載入 Stock/ETF Readiness… / Loading…</div>';
    fetch(TAB_STOCK_HTML, { credentials: 'same-origin' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); })
      .then(injectDom)
      .catch(showLoadError);
  }

  // pause:no-op —— stock 無輪詢 timer 需停(一次性快照,隱藏不會有背景 fetch 續打後端)。
  function pauseStockView() { /* no-op:無 setInterval / 無輪詢,無 timer 需清 */ }

  // resume:no-op —— readiness 非即時流;首載已快照一次,operator 用頁內「刷新」鈕手動更新(見 MODULE_NOTE)。
  //   不重呼 window.loadReadiness:避免與首載自初始化雙 fetch 且無實益。
  function resumeStockView() { /* no-op:靜態快照 view,顯示不重 fetch */ }

  // 註冊進殼可見的原生 view 表(router 以 v.iframe===false 查此;key=VIEWS 的 id 'stock')。
  window.OC_NATIVE_VIEWS = window.OC_NATIVE_VIEWS || {};
  window.OC_NATIVE_VIEWS['stock'] = { render: renderStockView, resume: resumeStockView, pause: pauseStockView };
  // 具名導出(task 契約:renderStockView / pauseStockView / resumeStockView 可被引用)。
  window.renderStockView = renderStockView;
  window.pauseStockView = pauseStockView;
  window.resumeStockView = resumeStockView;
})();
