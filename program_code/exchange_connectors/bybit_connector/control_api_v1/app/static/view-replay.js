/*
 * view-replay.js — 玄衡原生 view「回放 / 回測 Replay」(Phase 2 第 10 個 iframe→原生遷移)
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:把 legacy `tab-replay.html`(iframe 後備)遷成玄衡殼內的**原生 view**。
 *   策略=**復用遷移(thin-DOM + reuse 外部 JS)**:view-replay.js 只復現 tab-replay.html
 *   <body> 的 replay DOM(replay-head 標題 + Replay Engine chip + Refresh、replay-note 說明、
 *   `#subtab-replay` > `#subtab-replay-disabled-card`),再把生命週期交回 app-paper.js 既有的
 *   `window.OpenClawReplaySubtab`(readiness probe + 5 態狀態機 + full-chain/run/register/report
 *   等 replay 寫端點)。**OpenClawReplaySubtab 與其所依附的 app-paper.js 零修改,byte-parity 復用。**
 * DOM 保真(硬紀律):OpenClawReplaySubtab 的 renderReadyState / renderDegradedState 皆以
 *   `getElementById('subtab-replay-disabled-card')` 掛載,故該 id(連同 `#subtab-replay`
 *   容器 class `oc-subtab-content active`)必 byte-parity;`.oc-replay-*` ready-card class 由
 *   app-paper.js 的 `_injectReplayReadyCss()` 執行期自注入、disabled-card 由 OpenClawDisabledStateCard
 *   自帶樣式,故本檔 CSS 只需補 replay-head/replay-note + `.oc-chip*` 短名 shim(見 view-replay.css)。
 * paper 寫面 dormant(親證):本檔復現的 replay DOM **不含任何 `[data-paper-action]` 元素**。
 *   app-paper.js 的 paper 寫按鈕綁定(renderPaperSession 的 querySelector("[data-paper-action=…]"))
 *   只在 refreshPaperTrading→handlePaperAction 鏈觸發,replay view 無此 DOM、也不呼那些 fn →
 *   paper 寫路徑不可達(且 submitPaperOrder 後端已 HTTP 410 停用)。故 reuse app-paper.js 安全。
 * app-paper.js load-safe(親證):其 module-level 副作用僅 = 兩個 var 初值 + `_wireReplaySubtabNamespace`
 *   IIFE(只 define 函數並賦值 window.OpenClawReplaySubtab,零 fetch / 零 DOM query / 零 paper 寫);
 *   無 module-level DOMContentLoaded / 無自動 onTabActivate。載入不觸發任何寫面。
 * 生命週期(house pattern,對齊 view-gates.js / view-strategy.js,非 view-earn 的 no-op resume):
 *   replay 的 onTabActivate / onTabDeactivate 是乾淨且冪等的 hook,正好一一映射殼 router 的
 *   resume / pause(visibility 語義)。故:
 *     · render = 只建骨架 + 綁 Refresh,**不**在此呼 onTabActivate ——「啟動屬 resume」是殼慣例
 *       (view-gates.js L514「不啟輪詢——輪詢屬 resume」)。殼 navigate() 於末尾必呼
 *       notifyViewVisibility→resume(),故首 navigate 即由 resume 驅動一次 probe;render 不呼可
 *       ①免與 resume 重複探針(brief 直述「render 後呼 onTabActivate」會造成首 navigate 雙 probe,
 *       雖因冪等無害但多餘)②尊重「navigate 時瀏覽器隱藏」→ 不啟輪詢(resume 不觸發)。
 *       **此為與 brief 出入處,以源碼(house pattern)為準,已於回報指出。**
 *     · resume = onTabActivate():probe /replay/health → render ready/degraded → 啟 30s 輪詢。
 *       冪等(源碼實測):startPolling 有 `if(_pollIntervalId!==null)return` 防重輪詢;renderReadyState
 *       以 innerHTML 整塊重寫掛載點(全新元素、全新 listener,不累積)。故每次 resume 安全重入。
 *     · pause = onTabDeactivate():stopPolling(clearInterval)——隱藏即停後端探針,鏡像 iframe
 *       openclaw-tab-visibility 暫停語義(freshness/safety,非協商)。此為 replay 勝過 earn 之處:
 *       earn 的輪詢 timer 是 closure 私有清不到故 pause=no-op;replay 有真 deactivate hook,可乾淨停。
 * 依賴(全復用,不重造):app-paper.js(window.OpenClawReplaySubtab,須先於本檔載入)、
 *   OpenClawDisabledStateCard(common.js)、_injectReplayReadyCss(app-paper.js 自注入);
 *   view-replay.css 供 .replay-head / .replay-note + `.replay-view` scope 的 .oc-chip* shim。
 * 硬邊界(canon / LOOP §6):
 *   ① replay 寫(full-chain/coverage、full-chain/run、experiments/register、run、run/{id} finalize、
 *      report/{id})= subprocess spawn 的**研究回測**,非交易寫;全在 OpenClawReplaySubtab 內 byte-parity
 *      復用,response-gated 由 app-paper.js 既有邏輯,本檔零新寫路徑、零觸碰。
 *   ② paper 寫面(§上)保持 dormant/不可達。
 * 誠實邊界:靜態(node --check + ratchet + 註冊 smoke)只證 source 事實;**真渲染 / readiness 真態 /
 *   replay 寫真行為 = NEEDS-LINUX runtime + operator**,不由本刀 attest。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  // ── 模塊級狀態 ──
  var host = null;    // 原生 <section> 宿主(shell 注入)
  var built = false;  // rendered guard(骨架只首建一次;啟動/停止由 resume/pause 驅動)

  // ═══ 骨架(byte-parity 對齊 tab-replay.html <body>;OpenClawReplaySubtab 靠
  //   #subtab-replay-disabled-card 掛載 ready/degraded 卡,故該 id 集必齊)═══
  // .replay-view root 讓 view-replay.css 得以 scope legacy 短名 .oc-chip*(殼不呼 ocInjectBaseCSS)。
  var SKELETON =
    '<div class="replay-view">' +

      // ── replay-head:標題 + Replay Engine chip + Refresh 按鈕 ──
      '<div class="replay-head">' +
        '<span class="replay-head-title">&#x23F1; Reality-Calibrated Fast Replay / 真實校準快速回測</span>' +
        '<span class="oc-chip oc-chip-info">Replay Engine</span>' +
        '<span class="flex-1"></span>' +
        // Refresh:事件委派等價(addEventListener,見 wireRefresh)取代 legacy inline onclick,
        //   語義相同=手動 re-trigger onTabActivate;避免 inline onclick(CSP / ratchet 潔淨)。
        '<button type="button" class="oc-btn replay-refresh" aria-label="重新整理 / Refresh">Refresh / 刷新</button>' +
      '</div>' +

      // ── replay-note:雙語說明(verbatim tab-replay.html)──
      '<div class="replay-note">' +
        '<strong>Replay 是策略/風控修改後的快速驗證入口。</strong>' +
        'One-Click Replay 選擇區間後，用 fixture 重建 historical scanner timeline，再多幣種、多策略啟動 replay_runner。' +
        'Advanced 保留 manifest、fixture、experiment 級工具。' +
        '<br>' +
        '<strong>Replay is the fast validation path after strategy/risk edits.</strong>' +
        'One-Click Replay starts multi-symbol, multi-strategy subprocess runs; Advanced keeps the full manifest workflow.' +
      '</div>' +

      // ── subtab mount(byte-parity id/class;disabled-card 由 OpenClawReplaySubtab 渲染)──
      '<div id="subtab-replay" class="oc-subtab-content active" role="tabpanel">' +
        '<div id="subtab-replay-disabled-card"></div>' +
      '</div>' +

    '</div>';

  // OpenClawReplaySubtab 存取器(app-paper.js 須先載;缺席則 fail-closed 可見化)。
  function replayNs() {
    return (typeof window !== 'undefined') ? window.OpenClawReplaySubtab : null;
  }

  // activate:呼 onTabActivate(probe + render + 啟輪詢);冪等(源碼實測,見 MODULE_NOTE)。
  function activate() {
    var ns = replayNs();
    if (ns && typeof ns.onTabActivate === 'function') {
      try { ns.onTabActivate(); }
      catch (e) { console.warn('[view-replay] onTabActivate 失敗:', e); }
    } else {
      console.warn('[view-replay] app-paper.js 未載入(window.OpenClawReplaySubtab 缺席)— Replay view inactive');
    }
  }

  // deactivate:呼 onTabDeactivate(stopPolling);缺席/未啟輪詢皆安全 no-op。
  function deactivate() {
    var ns = replayNs();
    if (ns && typeof ns.onTabDeactivate === 'function') {
      try { ns.onTabDeactivate(); }
      catch (e) { /* fail-soft:停輪詢失敗不阻斷切換 */ }
    }
  }

  // Refresh 按鈕:手動 re-trigger onTabActivate(等價 legacy inline onclick)。
  function wireRefresh() {
    if (!host) return;
    var btn = host.querySelector('.replay-refresh');
    if (btn) btn.addEventListener('click', activate);
  }

  // ═══ shell router 契約:render / resume / pause ═══
  // render:建骨架 + 綁 Refresh(冪等,只首渲一次);**不**在此啟動——啟動屬 resume(house pattern,
  //   view-gates.js L514「輪詢屬 resume」)。殼 navigate() 末尾必呼 resume,故首 navigate 即被驅動。
  function renderReplayView(hostEl) {
    if (hostEl) host = hostEl;
    if (!host || built) return;
    host.innerHTML = SKELETON;
    built = true;
    wireRefresh();
  }

  // resume:view 顯示 → onTabActivate(probe + render ready/degraded + 啟 30s 輪詢)。
  //   冪等重入安全(startPolling 防重 + renderReadyState 整塊重寫);鏡像 iframe「顯示即刷新」。
  function resumeReplayView() {
    if (!built) return;
    activate();
  }

  // pause:view 隱藏 → onTabDeactivate(停輪詢/停探針)。隱藏不得續打後端(freshness/safety,非協商)。
  function pauseReplayView() {
    deactivate();
  }

  // 註冊進殼可見的原生 view 表(router 以 v.iframe===false 查此;key=VIEWS 的 id 'replay')。
  window.OC_NATIVE_VIEWS = window.OC_NATIVE_VIEWS || {};
  window.OC_NATIVE_VIEWS['replay'] = { render: renderReplayView, resume: resumeReplayView, pause: pauseReplayView };
  // 具名導出(task 契約:renderReplayView / pauseReplayView / resumeReplayView 可被引用)。
  window.renderReplayView = renderReplayView;
  window.resumeReplayView = resumeReplayView;
  window.pauseReplayView = pauseReplayView;
})();
