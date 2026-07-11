/*
 * shell.js — 玄衡新殼 view-router + iframe host(P1.1-a strangler-fig 起步)
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:玄衡儀單文檔殼的行為層。承載 (1) hash view-router(#/<lane>/<view>);
 *   (2) iframe host 管理(iframe view 直接移植 legacy console.html 機制)+ 原生 view hook
 *       (Phase 2 strangler-fig:iframe:false 的 view 走 window.OC_NATIVE_VIEWS 的 render/pause/resume,
 *        gates=首個;router 為穩定宿主,原生 render 為唯一擴充點,其餘 view 維持 iframe:true 不動);
 *   (3) lane segmented 切換 + rail 導航渲染;(4) density toggle(上線);
 *   (5) theme toggle(渲染但 P1.3-gated,不切換);(6) 衡樑 blocked 渲染;(7) clock 真值。
 * 主要函數:buildViews / navigate / onHashChange(router)、withBuildVersion /
 *   notifyViewVisibility / flushPendingFrameMessages / postToTabFrame(iframe host,verbatim 移植)、
 *   buildRailEnvs / buildRailCross / updateRailActive、switchLane、setBeam(P1.2 seam)。
 * 依賴:common.js(ocAuthCheck / ocLogout / ocEsc);tokens.css / oc-utilities.css / shell.css。
 *   不重造 auth / formatter / CSRF。
 * 硬邊界(canon / LOOP §6):
 *   ① 殼零寫路徑——無 POST、無 order、無 activation;交易/寫面全在 iframe 內既有 tab-*.html
 *      (五閘 / REAL FUNDS / typed-confirm / --live 熱紅 byte-identical 續生效)。
 *   ② 衡樑無真值 → blocked 態(canon 7),絕不 fake 傾角;setBeam 形制保留,P1.1-a 不呼叫,
 *      真接線=P1.2 shared WS。
 *   ③ topbar / status 遙測 P1.1-a 為 canon-7 blocked 佔位,零新 fetch;clock 是唯一 client 真值。
 *   ④ openclaw-tab-visibility 廣播=safety-critical,以 tab 既有消費形狀(ev.data.tab=legacy id)
 *      逐字移植;shape drift=隱藏 iframe WS 不暫停=freshness/safety 退步,非協商。
 *   ⑤ 原生 view visibility:隱藏時呼其 pause(停輪詢/停 fetch),鏡像 iframe postMessage 暫停語義;
 *      iframe view 的 postMessage 廣播(④)verbatim 不動——原生分支只是併行擴充,不改 iframe 面。
 * 誠實邊界:靜態 node --check + ratchet + smoke 只證 source 事實;router runtime 行為 /
 *   衡樑真傾角 / 帛晝 AA = NEEDS-LINUX,不由本刀 attest。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  // ── 殼靜態 build 版號(mirror console.html BUILD_TS 機制)──
  // 來源:靜態注入常量(非 runtime git SHA;誠實標記=殼 build tag,每次殼部署更新);
  // 用途:iframe cache-bust(withBuildVersion)+ status strip 顯示。
  var BUILD_TS = '20260711.shell-p11a';
  var USER_KEY = 'oc_username';
  // 預設 landing(PM 裁決 3:legacy parity=console 現行預設 view=tab-system=總覽)。
  var DEFAULT_HASH = '#/crypto/overview';

  // ═══ VIEWS 註冊表(18 tab → lane×view;P1.1-a 全 iframe:true)═══
  // 內容守恆(working doc §5:零靜默丟失)——18 全在,映射對 design/09 §3 表。
  // 欄位:id=內部/router id(frame 元素 f-<id>、rail data-view);lane∈{crypto,stock,cross};
  //       hash=深連結字串;src=既有 tab-*.html(legacy 與殼共用同一批檔);
  //       visId=visibility 廣播 tab 欄位(=legacy tab id;verbatim 消費契約,勿改);
  //       label/badge=rail 顯示;flag=⚑ 交易關鍵(P2 最後遷移);live=Live rung 視覺 gate。
  var VIEWS = [
    // ── crypto lane:environment ladder(scoped 於 active lane)──
    { id: 'overview', lane: 'crypto', hash: '#/crypto/overview', src: '/static/tab-system.html',     visId: 'system',      label: '總覽 Overview',   badge: 'overview' },
    { id: 'paper',    lane: 'crypto', hash: '#/crypto/paper',    src: '/static/tab-paper.html',       visId: 'paper',       label: 'Legacy Paper',    badge: 'paper' },
    { id: 'replay',   lane: 'crypto', hash: '#/crypto/replay',   src: '/static/tab-replay.html',      visId: 'replay',      label: '回放 Replay',     badge: 'replay' },
    { id: 'strategy', lane: 'crypto', hash: '#/crypto/strategy', src: '/static/tab-strategy.html',    visId: 'strategy',    label: '策略 Strategy',   badge: 'strategy' },
    { id: 'earn',     lane: 'crypto', hash: '#/crypto/earn',     src: '/static/tab-earn.html',        visId: 'earn',        label: 'Earn 理財',       badge: 'earn' },
    { id: 'demo',     lane: 'crypto', hash: '#/crypto/demo',     src: '/static/tab-demo.html',        visId: 'demo',        label: '演示 Demo',       badge: 'demo', flag: true },
    { id: 'live',     lane: 'crypto', hash: '#/crypto/live',     src: '/static/tab-live.html',        visId: 'live',        label: '實盤 Live',       badge: 'live', flag: true, live: true },
    // ── stock lane(IBKR read-only;殼不新增任何 IBKR 寫/激活 UI)──
    { id: 'stock',    lane: 'stock',  hash: '#/stock/overview',  src: '/static/tab-stock-etf.html',   visId: 'stock-etf',   label: '總覽 Overview',   badge: 'read-only' },
    // ── cross-cutting(lane/env 正交;釘 rail 底)──
    // monitor:Phase 2 第 2 個原生遷移(iframe:false)——render/pause/resume 由 view-monitor.js 註冊於
    //   window.OC_NATIVE_VIEWS(id=monitor);src 保留 legacy tab-monitoring 作 registry 完整性 + 回滾錨,原生渲染接管。
    { id: 'monitor',    lane: 'cross', hash: '#/cross/monitor',    src: '/static/tab-monitoring.html', visId: 'monitoring',  label: '監控 Monitor', iframe: false },
    { id: 'ai',         lane: 'cross', hash: '#/cross/ai',         src: '/static/tab-ai.html',         visId: 'ai',          label: 'AI 狀態' },
    { id: 'agents',     lane: 'cross', hash: '#/cross/agents',     src: '/static/tab-agents.html',     visId: 'agents',      label: 'Agent 團隊' },
    { id: 'learning',   lane: 'cross', hash: '#/cross/learning',   src: '/static/tab-learning.html',   visId: 'learning',    label: '學習 Learning' },
    { id: 'development', lane: 'cross', hash: '#/cross/development', src: '/static/tab-development.html', visId: 'development', label: '開發 Support' },
    { id: 'phase4',     lane: 'cross', hash: '#/cross/phase4',     src: '/static/tab-phase4.html',     visId: 'phase4',      label: 'Phase 4' },
    // gates:Phase 2 首個原生遷移(iframe:false)——render/pause/resume 由 view-gates.js 註冊於
    //   window.OC_NATIVE_VIEWS(id=gates);src 保留 legacy 檔作 registry 完整性 + 回滾錨,原生渲染接管。
    { id: 'gates',      lane: 'cross', hash: '#/cross/gates',      src: '/static/tab-edge-gates.html', visId: 'edge-gates',  label: '封驗 Gates', iframe: false },
    // charts:legacy `edge` 組 K線圖表(trading.html;內容守恆——design/09 §3 漏列,R51 補回 legacy parity,零靜默丟失)
    { id: 'charts',     lane: 'cross', hash: '#/cross/charts',     src: '/trading?embed=1',            visId: 'charts',      label: 'K線 Charts' },
    { id: 'governance', lane: 'cross', hash: '#/cross/governance', src: '/static/tab-governance.html', visId: 'governance',  label: '治理 Governance', flag: true },
    { id: 'risk',       lane: 'cross', hash: '#/cross/risk',       src: '/static/tab-risk.html',       visId: 'risk',        label: '風控 Risk', flag: true },
    { id: 'settings',   lane: 'cross', hash: '#/cross/settings',   src: '/static/tab-settings.html',   visId: 'settings',    label: '設置 Settings' }
  ];

  var VIEW_BY_ID = {};
  var VIEW_BY_HASH = {};
  VIEWS.forEach(function (v) { VIEW_BY_ID[v.id] = v; VIEW_BY_HASH[v.hash] = v; });
  var DEFAULT_VIEW = VIEW_BY_HASH[DEFAULT_HASH] || VIEWS[0];

  // 執行期狀態
  var currentViewId = null;
  var activeLane = 'crypto';
  var railEnvsLane = null;            // rail-envs 已渲染的 lane(避免無謂重繪)
  var failedViews = {};              // iframe 載入失敗集(view 顯錯不崩)
  var pendingFrameMessages = {};     // iframe 未載完前的訊息佇列(verbatim 移植)

  // 小工具:安全轉義(復用 common.js ocEsc;缺席時 fail-safe 退回原文)
  function esc(s) {
    return (typeof window.ocEsc === 'function') ? window.ocEsc(String(s)) : String(s);
  }
  function byId(id) { return document.getElementById(id); }

  // ═══ iframe host 機制(直接移植 legacy console.html;design §5.2)═══

  // withBuildVersion — verbatim(console.html L464–468):cache-bust 版號,tab 更新才傳播。
  function withBuildVersion(src) {
    if (src.includes('v=')) return src;
    var sep = src.includes('?') ? '&' : '?';
    return src + sep + 'v=' + BUILD_TS;
  }

  // notifyViewVisibility — 訊息形狀 verbatim(console.html L595–608)。
  // safety-critical(PM 裁決 6 非協商):每 frame 收 {type,tab,visible};tab=legacy id(visId),
  // 隱藏 iframe 據此暫停 WS/輪詢。漏發=隱藏 iframe WS 續跑=freshness/safety 退步。
  function notifyViewVisibility(activeViewId) {
    var browserVisible = document.visibilityState !== 'hidden';
    VIEWS.forEach(function (v) {
      if (isNative(v)) {
        // 原生 view 無 iframe/postMessage:可見→resume(啟輪詢)、隱藏/瀏覽器不可見→pause(停 fetch)。
        // 鏡像 iframe visibility 語義(隱藏續輪詢=freshness/safety 退步,非協商)。
        var api = nativeApi(v.id);
        if (!api) return;
        var on = browserVisible && v.id === activeViewId;
        try {
          if (on) { if (typeof api.resume === 'function') api.resume(); }
          else { if (typeof api.pause === 'function') api.pause(); }
        } catch (_) {}
        return;
      }
      var frame = byId('f-' + v.id);
      if (!frame || frame.dataset.loaded !== 'true' || !frame.contentWindow) return;
      try {
        frame.contentWindow.postMessage({
          type: 'openclaw-tab-visibility',
          tab: v.visId,
          visible: browserVisible && v.id === activeViewId
        }, window.location.origin);
      } catch (_) {}
    });
  }

  document.addEventListener('visibilitychange', function () {
    notifyViewVisibility(currentViewId);
  });

  // flushPendingFrameMessages / postToTabFrame — verbatim(console.html L614–639)。
  // 佇列機制:frame 未載完前的訊息暫存,load 後 flush。P1.1-a 唯一生產者(跨 tab 深連結
  // openclaw-risk-select / openclaw-governance-scroll)是 deferred delta(§5.3),故佇列常空;
  // 機制原樣移植作 P1.2 / 跨 tab 恢復的 ready seam,不重造。
  function flushPendingFrameMessages(viewId) {
    var frame = byId('f-' + viewId);
    var queue = pendingFrameMessages[viewId] || [];
    if (!frame || !queue.length) return;
    pendingFrameMessages[viewId] = [];
    queue.forEach(function (message) {
      try { frame.contentWindow.postMessage(message, window.location.origin); } catch (_) {}
    });
  }

  function postToTabFrame(viewId, message) {
    var frame = byId('f-' + viewId);
    if (!frame) return;
    if (frame.dataset.loaded === 'true') {
      setTimeout(function () {
        try { frame.contentWindow.postMessage(message, window.location.origin); } catch (_) {}
      }, 0);
      return;
    }
    if (!pendingFrameMessages[viewId]) pendingFrameMessages[viewId] = [];
    pendingFrameMessages[viewId].push(message);
  }

  // ═══ 原生 view hook(Phase 2 strangler-fig;iframe:false 的 view 走 render/pause/resume)═══
  // 殼 router 為穩定宿主;每個原生 view 於 window.OC_NATIVE_VIEWS[id] 註冊 {render,pause,resume}
  //   (view-gates.js = 首個)。iframe view 機制 verbatim 不動(R51 safety 面經 iframe 保全)。
  var nativeRendered = {};             // 原生 view 是否已首渲(render 冪等)

  function isNative(v) { return !!(v && v.iframe === false); }
  function nativeApi(id) { return (window.OC_NATIVE_VIEWS || {})[id] || null; }

  // 原生 view 宿主:建 <section>(非 iframe),沿用 .view-frame 顯隱機制 + --native 滾動修飾。
  function buildNativeHost(host, v) {
    var sec = document.createElement('section');
    sec.id = 'n-' + v.id;
    sec.className = 'view-frame view-frame--native';
    sec.setAttribute('role', 'region');
    sec.setAttribute('aria-label', v.label);
    host.appendChild(sec);
  }

  // 首渲(冪等):原生 view 首次 navigate 到才呼 render(v 對應 section);之後只切顯隱。
  function ensureNativeRendered(v, sec) {
    if (nativeRendered[v.id]) return;
    var api = nativeApi(v.id);
    if (api && typeof api.render === 'function') {
      try { api.render(sec); nativeRendered[v.id] = true; failedViews[v.id] = false; }
      catch (e) {
        // render 拋錯 → 可見化(對齊 iframe error 語義:標 failedViews,navigate 顯 .view-error 佔位,不留空白)。
        console.warn('[shell] 原生 view render 失敗:', v.id, e);
        failedViews[v.id] = true;
        if (v.id === currentViewId) showErrorOverlay(true);
      }
    } else {
      // 原生模組未註冊(view-*.js script 載入失敗 / OC_NATIVE_VIEWS 缺)→ fail-closed 可見化
      // (E2 R56 nit:對齊 iframe 載入失敗的 .view-error 佔位,避免空白 view 無提示)。
      console.warn('[shell] 原生 view 模組未註冊:', v.id);
      failedViews[v.id] = true;
      if (v.id === currentViewId) showErrorOverlay(true);
    }
  }

  // 建 view host(iframe view lazy iframe;原生 view 建 <section> 容器)。
  function buildViews() {
    var host = byId('oc-view-host');
    VIEWS.forEach(function (v) {
      if (isNative(v)) { buildNativeHost(host, v); return; }   // 原生 view:不建 iframe
      var frame = document.createElement('iframe');
      frame.id = 'f-' + v.id;
      frame.className = 'view-frame';
      frame.title = v.label;                 // a11y:iframe 需可辨識名
      frame.setAttribute('loading', 'lazy');
      frame.addEventListener('load', function () {
        frame.dataset.loaded = 'true';
        flushPendingFrameMessages(v.id);
        notifyViewVisibility(currentViewId);
      });
      // 網絡層載入失敗 → 標記 + 若當前則顯錯誤佔位(design §5.4:不崩,其他 view 續切)。
      frame.addEventListener('error', function () {
        failedViews[v.id] = true;
        if (v.id === currentViewId) showErrorOverlay(true);
      });
      frame.dataset.src = withBuildVersion(v.src);
      host.appendChild(frame);
    });
  }

  // ═══ rail 導航渲染(env ladder scoped active lane + cross-cutting 釘底)═══

  function railItem(v) {
    var a = document.createElement('a');
    a.className = 'rail-item' + (v.live ? ' rail-item--live' : '');
    a.href = v.hash;
    a.dataset.view = v.id;
    var label = document.createElement('span');
    label.textContent = v.label;
    if (v.flag) {
      var flag = document.createElement('span');
      flag.className = 'flag';
      flag.title = '交易關鍵 · P2 最後遷移(P1.1-a 仍 iframe 後備)';
      flag.textContent = '⚑';
      label.appendChild(flag);
    }
    a.appendChild(label);
    if (v.badge) {
      var badge = document.createElement('span');
      badge.className = 'env-badge';
      badge.textContent = v.badge;
      a.appendChild(badge);
    }
    return a;
  }

  function buildRailEnvs(lane) {
    if (railEnvsLane === lane) return;      // 已渲染此 lane,免重繪
    railEnvsLane = lane;
    var box = byId('oc-rail-envs');
    box.textContent = '';
    var t = document.createElement('div');
    t.className = 'rail-grp-t silk';
    t.textContent = 'Environment';
    box.appendChild(t);
    VIEWS.filter(function (v) { return v.lane === lane; })
      .forEach(function (v) { box.appendChild(railItem(v)); });
  }

  function buildRailCross() {
    var box = byId('oc-rail-cross');
    box.textContent = '';
    var t = document.createElement('div');
    t.className = 'rail-grp-t silk';
    t.textContent = 'Cross-cutting';
    box.appendChild(t);
    VIEWS.filter(function (v) { return v.lane === 'cross'; })
      .forEach(function (v) { box.appendChild(railItem(v)); });
  }

  function updateRailActive() {
    var items = document.querySelectorAll('.rail-item');
    for (var i = 0; i < items.length; i++) {
      var on = items[i].dataset.view === currentViewId;
      if (on) items[i].setAttribute('aria-current', 'page');
      else items[i].removeAttribute('aria-current');
    }
  }

  function updateLaneButtons() {
    var btns = document.querySelectorAll('.lane button[data-lane]');
    for (var i = 0; i < btns.length; i++) {
      btns[i].setAttribute('aria-pressed', btns[i].dataset.lane === activeLane ? 'true' : 'false');
    }
  }

  // ═══ 錯誤佔位 + drawer ═══
  function showErrorOverlay(show) {
    var el = byId('oc-view-error');
    if (!el) return;
    el.classList.toggle('is-active', !!show);
  }

  function closeRailDrawer() {
    document.documentElement.removeAttribute('data-rail-open');
  }

  // ═══ 核心:navigate(顯 target iframe、隱其餘、更新 rail、發 visibility)═══
  function navigate(viewId) {
    var v = VIEW_BY_ID[viewId];
    if (!v) return;                          // 防禦:未知 view 不崩
    currentViewId = viewId;
    if (v.lane !== 'cross') activeLane = v.lane;   // cross view 不改 active lane
    VIEWS.forEach(function (o) {
      if (isNative(o)) {
        // 原生 view:切 <section> 顯隱 + 首渲(resume/pause 由末尾 notifyViewVisibility 統一驅動)。
        var sec = byId('n-' + o.id);
        if (!sec) return;
        if (o.id === viewId) { sec.classList.add('is-active'); ensureNativeRendered(o, sec); }
        else { sec.classList.remove('is-active'); }
        return;
      }
      var frame = byId('f-' + o.id);
      if (!frame) return;
      if (o.id === viewId) {
        frame.classList.add('is-active');
        if (!frame.src) frame.src = frame.dataset.src;   // lazy load 首切
      } else {
        frame.classList.remove('is-active');
      }
    });
    showErrorOverlay(!!failedViews[viewId]);
    buildRailEnvs(activeLane);
    updateRailActive();
    updateLaneButtons();
    closeRailDrawer();
    notifyViewVisibility(viewId);
  }

  // ═══ hash router(深連結 / 刷新 / back-forward 保持;未知→預設 landing)═══
  function onHashChange() {
    var v = VIEW_BY_HASH[location.hash];
    if (v) { navigate(v.id); return; }
    // 未知/空/非法 hash → 回落預設 landing(不崩)
    if (location.hash && location.hash !== DEFAULT_HASH) {
      console.warn('[shell] 未知 hash,回落預設 landing:', location.hash);
    }
    if (location.hash !== DEFAULT_HASH) {
      location.hash = DEFAULT_HASH;          // 觸發再一次 hashchange → navigate
      return;
    }
    navigate(DEFAULT_VIEW.id);
  }

  // ═══ lane segmented 切換(頂欄;PM 裁決 A)═══
  function switchLane(lane) {
    activeLane = lane;
    updateLaneButtons();
    var first = VIEWS.filter(function (v) { return v.lane === lane; })[0];
    if (first) location.hash = first.hash;   // 導向該 lane 首個 env view(觸發 navigate)
  }

  // ═══ 衡樑(canon 7:P1.1-a blocked;setBeam 形制保留,不呼叫)═══
  // setBeam 真接線=P1.2 shared WS(訂閱風控包絡)。scoped-var 寫法(ratchet 正法,非 style=)。
  // 樣品 setBeam(31) 是假數據演示,shipped shell P1.1-a 不呼叫——秤樑水平靜置顯 blocked。
  function setBeam(usedPct) {
    var beam = byId('oc-beam');
    if (!beam) return;
    var angle = ((100 - usedPct) - usedPct) / 100 * -6;   // 50/50 水平,滿載 −6°(已用端沉)
    beam.style.setProperty('--beam-angle', angle.toFixed(2) + 'deg');
    beam.classList.toggle('beam--warn', usedPct >= 80);
    beam.classList.remove('beam--blocked');
    var used = byId('oc-beam-used'); if (used) used.textContent = usedPct + '%';
    var left = byId('oc-beam-left'); if (left) left.textContent = (100 - usedPct) + '%';
  }
  void setBeam;   // P1.1-a 不呼叫;顯式標記保留為 P1.2 接線 seam(canon 7)

  function renderBeamBlocked() {
    var beam = byId('oc-beam');
    if (beam) {
      beam.classList.add('beam--blocked');
      beam.style.setProperty('--beam-angle', '0deg');   // 水平靜置,絕不 fake 傾角
    }
    var used = byId('oc-beam-used'); if (used) used.textContent = '—';
    var left = byId('oc-beam-left'); if (left) left.textContent = '—';
  }

  // ═══ clock(唯一 client 真值;UTC 上 / local 下,mono tabular)═══
  function updateClock() {
    var d = new Date();
    var utc = byId('oc-clock-utc');
    var local = byId('oc-clock-local');
    if (utc) utc.textContent = d.toISOString().slice(11, 19) + ' UTC';
    if (local) local.textContent = d.toLocaleTimeString('zh-CN', { hour12: false });
  }

  // ═══ density toggle(上線,session-only;localStorage 持久化=P1.3,本刀不做)═══
  function wireDensityToggle() {
    var btn = byId('oc-density-btn');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var root = document.documentElement;
      var compact = root.getAttribute('data-density') === 'compact';
      if (compact) root.removeAttribute('data-density');
      else root.setAttribute('data-density', 'compact');
      btn.textContent = compact ? '舒適' : '緊湊';
    });
  }

  // ═══ theme toggle(渲染但 P1.3-gated;帛晝 AA 三綠前 data-theme 釘死玄夜,不宣稱雙主題)═══
  // 按鈕 inert(aria-disabled);不切換 data-theme。真雙主題=P1.3(LOOP §6 硬 gate)。
  function wireThemeToggle() {
    var btn = byId('oc-theme-btn');
    if (!btn) return;
    btn.addEventListener('click', function (ev) {
      ev.preventDefault();                   // P1.3-gated:不切換,僅提示
      console.info('[shell] 帛晝主題待 P1.3(AA 三綠)才上線;P1.1-a data-theme 釘死玄夜。');
    });
  }

  // ═══ rail 漢堡(≤960 drawer;完整動效 P1.1-b,本刀最小 toggle 不破版)═══
  function wireRailToggle() {
    var btn = byId('oc-rail-toggle');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var root = document.documentElement;
      var open = root.getAttribute('data-rail-open') === 'true';
      if (open) root.removeAttribute('data-rail-open');
      else root.setAttribute('data-rail-open', 'true');
    });
  }

  // ═══ 帳號 + 登出(復用 common.js;殼零新寫路徑)═══
  function wireAccount() {
    var actor = byId('oc-account-actor');
    try {
      var user = localStorage.getItem(USER_KEY);
      if (user && actor) actor.textContent = esc(user);
    } catch (_) {}
    var logout = byId('oc-logout');
    if (logout) {
      logout.addEventListener('click', function () {
        if (typeof window.ocLogout === 'function') window.ocLogout();
        else window.location.href = '/login';
      });
    }
  }

  // ═══ lane 按鈕接線 ═══
  function wireLaneButtons() {
    var btns = document.querySelectorAll('.lane button[data-lane]');
    for (var i = 0; i < btns.length; i++) {
      (function (btn) {
        btn.addEventListener('click', function () { switchLane(btn.dataset.lane); });
      })(btns[i]);
    }
  }

  // ═══ 啟動 ═══
  function boot() {
    // client-side auth 補轉址(與 tab 一致;真守衛=server static_auth_guard,C2)。
    if (typeof window.ocAuthCheck === 'function') window.ocAuthCheck();

    var build = byId('oc-build');
    if (build) build.textContent = 'build ' + BUILD_TS;

    buildViews();
    buildRailCross();
    renderBeamBlocked();
    wireLaneButtons();
    wireDensityToggle();
    wireThemeToggle();
    wireRailToggle();
    wireAccount();

    updateClock();
    setInterval(updateClock, 1000);

    window.addEventListener('hashchange', onHashChange);
    onHashChange();          // 首載:parse 現行 hash → 定位 view(深連結 / 刷新保持)
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
