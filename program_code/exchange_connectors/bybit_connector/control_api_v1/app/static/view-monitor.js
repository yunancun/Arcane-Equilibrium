/*
 * view-monitor.js — 玄衡原生 view「系統監控」(Phase 2 第 2 個 iframe→原生遷移)
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:把 legacy `tab-monitoring.html`(iframe 後備)遷成玄衡殼內的**原生 view**,
 *   證明首遷(view-gates.js)所建的 strangler-fig pattern **泛化到 dashboard 形狀**
 *   ——多面板健康儀表盤(design/10 recipe §1)。殼 router 為穩定宿主,本檔提供
 *   render/pause/resume 為唯一新增擴充點(second-adapter),與 gates 同構。
 *   內容逐元素守恆:①Grafana 面板(健康徽章 + 嵌入面板 + 離線配置指南);②服務狀態卡
 *   ×3(Pipeline Bridge / Telegram Alerter / OpenClaw Gateway);③系統健康詳情(平展
 *   healthcheck)——與 legacy 同資料、同讀取路由,只換玄衡組件庫版式 + 補一列 KPI 彙總。
 *   刻意變更:legacy 裝飾 emoji(📊🌐📨🧠🏥)不遷(canon 1 非數據 chrome 從簡,對齊 gates
 *   austere 版式);legacy oc-card/oc-metric/oc-explain 等 class 在殼文檔不可用(殼只載
 *   tokens/oc-utilities/shell/shell-components),故用玄衡組件庫重建,非沿用 legacy class。
 * 主要函數:renderMonitorView(建骨架,冪等)、resumeMonitorView(顯示→拉真值+啟輪詢)、
 *   pauseMonitorView(隱藏→停輪詢/停 fetch)、load / loadGrafana / loadPipeline /
 *   loadTelegram / loadGateway / loadHealth(per-view fetch)、renderHealth / flatEntries。
 * 依賴(全復用,不重造):common.js ocApi;common-formatters.js ocEsc / ocTimeShort /
 *   OC_EMPTY;組件庫 shell-components.css(.panel/.panel-t/.kpis/.kpi/.tbl/.tag/.note/.code)
 *   + tokens.css(.num/.silk)+ oc-utilities.css(flex/間距/t-* 色階)。
 * 硬邊界(canon / LOOP §6):
 *   ① 零寫路徑——monitor 唯讀:5 個 ocApi GET(grafana-health / paper session status /
 *      strategy status / telegram status / system health)+ 1 個 same-origin raw GET
 *      (/openclaw/health,∈ 5b authoritative 的 /openclaw catch-all),無 POST/order。
 *   ② canon 7 三態:loading=骨架「—/loading…」;無真值=「—」/UNKNOWN/未配置(絕不假
 *      healthy/假 0/假 Online);error(ocApi 回 null / fetch throw)=顯錯不崩,保守標
 *      warn/bad,絕不冒充 Connected/Online/PASS。
 *   ③ visibility 語義(非協商):隱藏時 pauseMonitorView 停輪詢/停後端抓取(鏡像 iframe
 *      openclaw-tab-visibility 暫停),否則隱藏續打後端=freshness/safety 退步。
 *   ④ ratchet 0/0/0:零裸 hex、零 inline style 屬性、零內聯樣式區塊;動態 tone 走
 *      .style.setProperty('--tag-tone', var(...)) scoped-var 正法。Grafana 嵌入框以
 *      iframe 的 width/height **HTML 屬性**定尺寸(非 style=),故無需新增殼作用域 CSS。
 * 誠實邊界:靜態(node --check + ratchet + 5b 對齊 + registry/asset smoke)只證 source/路徑
 *   事實;**真渲染正確性 / 三態版式 / 真值 / Grafana 嵌入 = NEEDS-LINUX runtime + operator
 *   視覺**,不由本刀 attest。Grafana / Gateway 主機 URL(trade-core:3000、/openclaw)為
 *   legacy 內容守恆逐字沿用,非本刀新增依賴。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  // ── 常量 ──
  var POLL_MS = 15000;             // 輪詢間隔(鏡像 legacy ocStartRefresh 15s;僅可見時運行)
  // Grafana 嵌入 / 開啟目標(legacy 逐字守恆:tab-monitoring 硬編 trade-core:3000)。
  var GRAFANA_BASE = 'http://trade-core:3000';
  var GRAFANA_EMBED = GRAFANA_BASE + '/d/openclaw-trading-pnl?orgId=1&kiosk';

  // ── 執行期狀態 ──
  var host = null;                 // 原生 <section> 宿主(shell 注入)
  var built = false;               // 骨架是否已建(render 冪等)
  var timer = null;                // 輪詢 interval id(null=停;pause 必清)
  var loading = false;             // fetch 去重(單次 load 內多 GET 並行,不重入)

  // ── 小工具 ──
  function q(sel) { return host ? host.querySelector(sel) : null; }
  function esc(s) { return (typeof window.ocEsc === 'function') ? window.ocEsc(s) : String(s == null ? '' : s); }
  var EMPTY = (typeof window.OC_EMPTY === 'string') ? window.OC_EMPTY : '—';

  // tone → tokens.css 語義色 var(給 .tag 的 scoped-var --tag-tone)。
  // 未知/中性一律 warn 調(canon 7:不確定 → 保守標注,絕不綠燈)。
  function toneVar(tone) {
    if (tone === 'good') return 'var(--pos)';
    if (tone === 'bad') return 'var(--neg)';
    if (tone === 'muted') return 'var(--text-muted)';
    return 'var(--warn)';
  }
  // tone → 文字色 utility class(oc-utilities .t-*;KPI 值用)。
  function toneTextClass(tone) {
    if (tone === 'good') return 't-pos';
    if (tone === 'bad') return 't-neg';
    if (tone === 'muted') return 't-muted';
    return 't-warn';
  }

  // ═══ 值設定器(canon 7:無真值 → EMPTY / 保守 tone,絕不假值)═══
  // 註:骨架內 .tag 首渲即 data-tone="warn",CSS 以 var(--tag-tone, var(--warn)) 回落 warn 色
  //   (canon 7 loading=保守);真值到達後由 setTag 逐一寫 scoped-var,無需批量 applyTagTones。
  // 狀態徽章:文字 + data-tone + scoped-var 上色(不寫 style= 字面,ratchet 正法)。
  function setTag(sel, text, tone) {
    var el = q(sel);
    if (!el) return;
    el.textContent = text;
    el.setAttribute('data-tone', tone || 'warn');
    el.style.setProperty('--tag-tone', toneVar(tone || 'warn'));
  }
  // 純文字值(count / 時間);null/空 → EMPTY(禁假零)。
  function setText(sel, val) {
    var el = q(sel);
    if (!el) return;
    el.textContent = (val == null || val === '') ? EMPTY : String(val);
  }
  // KPI 設值(值 tone 走文字色 class;sub 為 note 文字)。
  function setKpi(prefix, value, tone, sub) {
    var v = q('.' + prefix + ' .v');
    if (v) { v.className = 'v ' + toneTextClass(tone); v.textContent = value; }
    var d = q('.' + prefix + ' .mon-sub');
    if (d) { d.textContent = sub || ''; }
  }
  // 更新徽(good=已刷新於本地時刻 / warn=有面板載入異常)。誠實:此為 client 刷新時刻,非 server 產出時。
  function setUpdated(text, tone) {
    var el = q('.mon-updated');
    if (!el) return;
    el.textContent = text;
    el.setAttribute('data-tone', tone || 'warn');
    el.style.setProperty('--tag-tone', toneVar(tone || 'warn'));
  }
  function showError(msg) {
    var el = q('.mon-error');
    if (!el) return;
    if (msg) { el.textContent = msg; el.classList.remove('hidden'); }
    else { el.textContent = ''; el.classList.add('hidden'); }
  }

  // ═══ 骨架(canon 7:首渲即 loading 態「—/loading…/checking…」,絕不假值)═══
  var SKELETON =
    '<div class="p-4">' +
      // 標頭面板:題 + 說明 + 工具列(刷新 / 更新狀態徽)
      '<div class="panel">' +
        '<div class="row-between wrap gap-3">' +
          '<div>' +
            '<div class="panel-t"><span class="zh">系統監控</span><span class="code">SYSTEM MONITORING</span></div>' +
            '<div class="note">Grafana 面板、管線 / 告警 / Gateway 服務健康與系統 healthcheck 彙總(唯讀)。</div>' +
          '</div>' +
          '<div class="row wrap gap-2">' +
            '<button type="button" class="mon-refresh mono fs-dense t-accent pointer">刷新 / Refresh</button>' +
            '<span class="mon-updated tag" data-tone="warn">loading…</span>' +
          '</div>' +
        '</div>' +
      '</div>' +
      // KPI 行(1 hero + 3):system health / grafana / pipeline / gateway
      '<div class="kpis">' +
        '<div class="kpi hero mon-kpi-health"><div class="silk">SYSTEM HEALTH</div><div class="v">' + EMPTY + '</div><div class="d note mon-sub">' + EMPTY + '</div></div>' +
        '<div class="kpi mon-kpi-grafana"><div class="silk">GRAFANA</div><div class="v">' + EMPTY + '</div><div class="d note mon-sub">' + EMPTY + '</div></div>' +
        '<div class="kpi mon-kpi-pipeline"><div class="silk">PIPELINE BRIDGE</div><div class="v">' + EMPTY + '</div><div class="d note mon-sub">' + EMPTY + '</div></div>' +
        '<div class="kpi mon-kpi-gateway"><div class="silk">OPENCLAW GATEWAY</div><div class="v">' + EMPTY + '</div><div class="d note mon-sub">' + EMPTY + '</div></div>' +
      '</div>' +
      // 錯誤橫幅(canon 7:error 顯錯不崩;預設隱藏)
      '<div class="mon-error panel note t-warn hidden"></div>' +
      // Grafana 監控面板(健康徽 + 開啟鈕 + 嵌入/離線指南)
      '<div class="panel">' +
        '<div class="row-between wrap gap-2">' +
          '<div class="panel-t"><span class="zh">Grafana 監控面板</span><span class="code">GRAFANA DASHBOARD</span></div>' +
          '<div class="row gap-2">' +
            '<span class="mon-grafana-badge tag" data-tone="warn">checking…</span>' +
            '<button type="button" class="mon-grafana-open mono fs-dense t-accent pointer">在 Grafana 開啟 ↗</button>' +
          '</div>' +
        '</div>' +
        '<div class="note mb-2">Grafana 連 Prometheus 時序庫,顯 API 延遲 / 訂單延遲 / WebSocket 狀態 / 資源使用;預配玄衡 Trading PnL 看板。</div>' +
        '<div class="mon-grafana-wrap"><div class="note">Grafana 連接中…</div></div>' +
      '</div>' +
      // 服務狀態卡 ×3(Pipeline / Telegram / Gateway)
      '<div class="row wrap gap-3">' +
        // Pipeline Bridge
        '<div class="panel flex-1">' +
          '<div class="row-between gap-2 mb-2">' +
            '<div><div class="fw-medium">Pipeline Bridge</div><div class="code">PIPELINE BRIDGE</div></div>' +
            '<span class="mon-pipe-status tag" data-tone="warn">—</span>' +
          '</div>' +
          '<div class="note mb-2">接 WS tick,fan-out 給各策略;OrderIntent 過風控後轉 Paper/Demo 單;含 K 線聚合與成交量追蹤。</div>' +
          '<div class="row wrap gap-3">' +
            '<div class="col"><div class="silk">Tick Count</div><div class="num fs-md mon-pipe-ticks">' + EMPTY + '</div></div>' +
            '<div class="col"><div class="silk">Intent Count</div><div class="num fs-md mon-pipe-intents">' + EMPTY + '</div></div>' +
            '<div class="col"><div class="silk">Last Tick</div><div class="num fs-md mon-pipe-last">' + EMPTY + '</div></div>' +
          '</div>' +
        '</div>' +
        // Telegram Alerter
        '<div class="panel flex-1">' +
          '<div class="row-between gap-2 mb-2">' +
            '<div><div class="fw-medium">Telegram Alerter</div><div class="code">TELEGRAM ALERTER</div></div>' +
            '<span class="mon-tg-status tag" data-tone="warn">—</span>' +
          '</div>' +
          '<div class="note mb-2">重要事件經 Telegram Bot 推送:INFO(信號 / 成交)、WARNING(異常 / 風控)、CRITICAL(系統錯 / 熔斷)。</div>' +
          '<div class="row wrap gap-3">' +
            '<div class="col"><div class="silk">Messages Sent</div><div class="num fs-md mon-tg-sent">' + EMPTY + '</div></div>' +
            '<div class="col"><div class="silk">Failed</div><div class="num fs-md mon-tg-failed">' + EMPTY + '</div></div>' +
            '<div class="col"><div class="silk">Last Sent</div><div class="num fs-md mon-tg-last">' + EMPTY + '</div></div>' +
          '</div>' +
        '</div>' +
        // OpenClaw Gateway
        '<div class="panel flex-1">' +
          '<div class="row-between gap-2 mb-2">' +
            '<div><div class="fw-medium">OpenClaw Gateway</div><div class="code">OPENCLAW GATEWAY</div></div>' +
            '<span class="mon-gw-status tag" data-tone="warn">—</span>' +
          '</div>' +
          '<div class="note mb-2">AI 通信層:管理 agent 實例與 channel,多模型路由 / 故障降級;獨立於交易邏輯,不可用不影響核心交易。</div>' +
          '<div class="row wrap gap-3">' +
            '<div class="col"><div class="silk">Agents</div><div class="fs-md mon-gw-agents">' + EMPTY + '</div></div>' +
            '<div class="col"><div class="silk">Channels</div><div class="fs-md mon-gw-channels">' + EMPTY + '</div></div>' +
          '</div>' +
          '<div class="mt-2"><button type="button" class="mon-gw-open mono fs-dense t-accent pointer">開啟 Gateway ↗</button></div>' +
        '</div>' +
      '</div>' +
      // 系統健康詳情(平展 healthcheck;預設收合)
      '<div class="panel">' +
        '<div class="panel-t"><span class="zh">系統健康詳情</span><span class="code">SYSTEM HEALTH DETAIL</span></div>' +
        '<details><summary class="note pointer">展開 / Expand</summary>' +
          '<div class="mon-health-body note mt-2">Loading…</div>' +
        '</details>' +
      '</div>' +
    '</div>';

  // ═══ Grafana 面板 ═══
  function renderGrafana(ok) {
    setTag('.mon-grafana-badge', ok ? 'Connected' : 'Not Connected', ok ? 'good' : 'warn');
    setKpi('mon-kpi-grafana', ok ? 'CONNECTED' : 'OFFLINE', ok ? 'good' : 'warn',
      ok ? 'Grafana 服務可用' : 'Grafana 未連接 / 未啟動');
    var wrap = q('.mon-grafana-wrap');
    if (!wrap) return;
    if (ok) {
      // 嵌入框尺寸走 iframe 的 width/height **HTML 屬性**(非 style=),ratchet 安全,免殼作用域 CSS。
      wrap.innerHTML = '<iframe src="' + esc(GRAFANA_EMBED) + '" width="100%" height="520" ' +
        'loading="lazy" title="Grafana 監控面板 / Grafana Dashboard"></iframe>';
    } else {
      // 離線態:配置指南(canon 7 不假 Connected;內容守恆自 legacy showGrafanaOffline)。
      wrap.innerHTML =
        '<div class="col gap-2">' +
          '<div class="fw-medium">Grafana 未連接 / Not Connected</div>' +
          '<div class="note">Grafana 監控服務未啟動或不可訪問。</div>' +
          '<details><summary class="t-accent pointer fs-dense">如何配置 Grafana / Setup Guide</summary>' +
            '<div class="note mt-2 lh-cjk">' +
              '<p>1. 安裝 Grafana:<code>sudo apt install grafana</code></p>' +
              '<p>2. 安裝 Prometheus:<code>sudo apt install prometheus</code></p>' +
              '<p>3. 配置 Prometheus 抓取 Trading API 的 /metrics 端點</p>' +
              '<p>4. 在 Grafana 添加 Prometheus 數據源</p>' +
              '<p>5. 導入玄衡 Trading PnL 看板</p>' +
              '<p>6. 確保 Grafana 運行在 trade-core:3000</p>' +
            '</div>' +
          '</details>' +
        '</div>';
    }
  }

  async function loadGrafana() {
    // 代理健康檢查(避免瀏覽器 CORS);回 {data:{ok}}(legacy checkGrafana 同路由)。
    var d = await ocApi('/api/v1/system/grafana-health');
    if (!built) return;
    if (d == null) {
      // error:顯錯不崩,保守標離線(絕不假 Connected)。
      setTag('.mon-grafana-badge', '檢查失敗', 'warn');
      setKpi('mon-kpi-grafana', '錯誤', 'warn', 'Grafana 健康檢查失敗(HTTP / 網路)');
      return;
    }
    renderGrafana(!!(d.data && d.data.ok));
  }

  // ═══ Pipeline Bridge(paper session status + orchestrator strategy status)═══
  async function loadPipeline() {
    // 管線統計在 paper session(pipeline_bridge stats 存於此)。
    var d = await ocApi('/api/v1/paper/session/status');
    if (!built) return;
    var sess = (d && d.data && (d.data.session || d.data)) || null;
    if (!sess) {
      setTag('.mon-pipe-status', '載入失敗', 'warn');
      setKpi('mon-kpi-pipeline', EMPTY, 'warn', 'paper session 載入失敗');
    } else {
      var active = sess.session_state === 'active';
      var label = active ? 'Active' : (sess.session_state || 'Inactive');
      setTag('.mon-pipe-status', label, active ? 'good' : 'warn');
      setKpi('mon-kpi-pipeline', active ? 'ACTIVE' : String(label).toUpperCase(), active ? 'good' : 'warn',
        active ? '管線活躍' : '管線非活躍');
    }
    // orchestrator:tick / intent 統計。
    var d2 = await ocApi('/api/v1/strategy/status');
    if (!built) return;
    if (d2 && d2.data) {
      var stats = d2.data.stats || {};
      var km = (d2.data.kline_manager_status || {}).stats || {};
      setText('.mon-pipe-ticks', km.total_ticks_processed != null ? km.total_ticks_processed : EMPTY);
      setText('.mon-pipe-intents', stats.intents_collected != null ? stats.intents_collected : EMPTY);
      setText('.mon-pipe-last', km.last_tick_ts_ms ? window.ocTimeShort(km.last_tick_ts_ms) : EMPTY);
    } else {
      setText('.mon-pipe-ticks', EMPTY);
      setText('.mon-pipe-intents', EMPTY);
      setText('.mon-pipe-last', EMPTY);
    }
  }

  // ═══ Telegram Alerter ═══
  async function loadTelegram() {
    var d = await ocApi('/api/v1/strategy/telegram/status');
    if (!built) return;
    var t = d && d.data;
    if (!t) {
      setTag('.mon-tg-status', '未配置', 'warn');
      setText('.mon-tg-sent', EMPTY);
      setText('.mon-tg-failed', EMPTY);
      setText('.mon-tg-last', EMPTY);
      return;
    }
    var enabled = t.enabled || t.configured;
    setTag('.mon-tg-status', enabled ? 'Enabled' : 'Disabled', enabled ? 'good' : 'warn');
    setText('.mon-tg-sent', t.messages_sent != null ? t.messages_sent : (t.sent_count != null ? t.sent_count : EMPTY));
    setText('.mon-tg-failed', t.messages_failed != null ? t.messages_failed : (t.error_count != null ? t.error_count : EMPTY));
    setText('.mon-tg-last', t.last_sent_at ? window.ocTimeShort(t.last_sent_at) : EMPTY);
  }

  // ═══ OpenClaw Gateway(same-origin raw GET;∈ 5b authoritative 的 /openclaw catch-all)═══
  async function loadGateway() {
    var h = null;
    try {
      var r = await fetch('/openclaw/health', { credentials: 'same-origin' });  // HttpOnly cookie 自動附
      h = await r.json();
    } catch (e) {
      h = null;
    }
    if (!built) return;
    if (!h) {
      // 不可達(網路 / throw):保守標 warn(canon 7 不確定;非假 Online 亦非武斷判死)。
      setTag('.mon-gw-status', 'Offline', 'warn');
      setKpi('mon-kpi-gateway', 'OFFLINE', 'warn', 'Gateway 不可訪問');
      setText('.mon-gw-agents', EMPTY);
      setText('.mon-gw-channels', EMPTY);
      return;
    }
    var ok = !!h.ok;
    setTag('.mon-gw-status', ok ? 'Online' : 'Down', ok ? 'good' : 'bad');
    setKpi('mon-kpi-gateway', ok ? 'ONLINE' : 'DOWN', ok ? 'good' : 'bad', ok ? 'Gateway 在線' : 'Gateway 回報異常');
    setText('.mon-gw-agents', (h.agents || []).length + ' agent(s)');
    setText('.mon-gw-channels', (h.channels || []).length + ' channel(s)');
  }

  // ═══ 系統健康詳情(平展 nested dict → 表;port legacy flatEntries + loadHealthDetail)═══
  function flatEntries(obj, prefix) {
    var entries = [];
    Object.keys(obj || {}).forEach(function (key) {
      var val = obj[key];
      var fullKey = prefix ? prefix + '.' + key : key;
      if (val != null && typeof val === 'object' && !Array.isArray(val)) {
        entries = entries.concat(flatEntries(val, fullKey));
      } else {
        entries.push([fullKey, val]);
      }
    });
    return entries;
  }

  // 健康總態(hero KPI):沿用 gates healthToneFrom 的 scores/gates 判定;無此結構 → UNKNOWN
  // (canon 7:不臆測平展布林的健康語義,不假 PASS)。
  function healthState(h) {
    if (!h || typeof h !== 'object') return { status: 'UNKNOWN', tone: 'warn', reason: 'health API 無資料' };
    var scores = h.scores || {};
    var gates = h.gates || {};
    var scoreVals = Object.keys(scores).map(function (k) { return Number(scores[k]); }).filter(Number.isFinite);
    var failedGates = Object.keys(gates).filter(function (k) {
      var v = String(gates[k]).toLowerCase();
      return v !== 'passed' && v !== 'true';
    });
    if (failedGates.length || scoreVals.some(function (v) { return v < 50; })) {
      return { status: 'FAIL', tone: 'bad', reason: failedGates.length + ' failed gate(s)' };
    }
    if (scoreVals.some(function (v) { return v < 80; })) return { status: 'WARN', tone: 'warn', reason: 'score below 80' };
    if (scoreVals.length || Object.keys(gates).length) return { status: 'PASS', tone: 'good', reason: 'scores and gates pass' };
    return { status: 'UNKNOWN', tone: 'warn', reason: '無 scores/gates 欄位' };
  }

  // 值 → 語義 tone class(true/passed/healthy=正;false/failed/fail=負;其餘中性)。
  function healthValueClass(v) {
    var s = String(v).toLowerCase();
    if (s === 'true' || s === 'passed' || s === 'healthy') return 't-pos';
    if (s === 'false' || s === 'failed' || s === 'fail') return 't-neg';
    return '';
  }

  function renderHealth(h) {
    var state = healthState(h);
    setKpi('mon-kpi-health', state.status, state.tone, state.reason);
    var body = q('.mon-health-body');
    if (!body) return;
    var entries = flatEntries(h, '');
    if (!entries.length) { body.innerHTML = '<div class="note">Healthcheck 無資料</div>'; return; }
    var rows = entries.map(function (pair) {
      var key = pair[0];
      var v = pair[1] != null ? String(pair[1]) : EMPTY;
      var label = key.replace(/_/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); });
      return '<tr><td>' + esc(label) + '</td>' +
        '<td class="mono ' + healthValueClass(pair[1]) + '">' + esc(v) + '</td></tr>';
    }).join('');
    body.innerHTML = '<table class="tbl"><thead><tr><th>Key</th><th>Value</th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table>';
  }

  async function loadHealth() {
    var d = await ocApi('/api/v1/system/health');
    if (!built) return;
    if (d == null) {
      setKpi('mon-kpi-health', '錯誤', 'warn', '健康檢查載入失敗(HTTP / 網路)');
      var body = q('.mon-health-body');
      if (body) body.innerHTML = '<div class="note t-warn">健康檢查載入失敗</div>';
      return;
    }
    renderHealth(d.data || d);       // legacy:d.data || d(payload 可能未包 data)
  }

  // ═══ 統一載入(per-view;全唯讀 GET,並行 allSettled;顯 refresh 時刻徽)═══
  async function load() {
    if (!built || loading) return;
    loading = true;
    showError('');
    try {
      await Promise.allSettled([loadGrafana(), loadPipeline(), loadTelegram(), loadGateway(), loadHealth()]);
    } finally {
      loading = false;
    }
    if (!built) return;
    // 誠實:此為 client 端最近刷新時刻(非 server 產出時);多面板各自標狀態,此徽僅示已刷新。
    var now = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    setUpdated('refreshed ' + now, 'good');
  }

  // ═══ 控件接線(刷新 / Grafana 開啟 / Gateway 開啟;皆唯讀,無寫路徑)═══
  function wireControls() {
    var btn = q('.mon-refresh');
    if (btn) btn.addEventListener('click', function () { load(); });
    var gopen = q('.mon-grafana-open');
    if (gopen) gopen.addEventListener('click', function () { window.open(GRAFANA_BASE, '_blank'); });
    var gwopen = q('.mon-gw-open');
    if (gwopen) gwopen.addEventListener('click', function () { window.open(window.location.origin + '/openclaw/', '_blank'); });
  }

  // ═══ 輪詢生命週期(僅可見時運行;pause 必清 → 隱藏不 fetch)═══
  function startPolling() {
    stopPolling();
    timer = setInterval(load, POLL_MS);
  }
  function stopPolling() {
    if (timer) { clearInterval(timer); timer = null; }
  }

  // ═══ shell router 契約:render / resume / pause(second-adapter 擴充點)═══
  // render:建骨架(冪等,只首渲一次);不啟輪詢——輪詢屬 resume(visibility 語義)。
  function renderMonitorView(hostEl) {
    if (hostEl) host = hostEl;
    if (!host || built) return;
    host.innerHTML = SKELETON;
    built = true;
    wireControls();
    setUpdated('loading…', 'warn');
  }
  // resume:view 顯示 → 立即拉一次真值(鏡像 iframe「顯示即刷新」)+ 啟輪詢。
  function resumeMonitorView() {
    if (!built) return;
    load();
    startPolling();
  }
  // pause:view 隱藏 → 停輪詢/停後續抓取(freshness/safety:隱藏不得續打後端,
  // 鏡像 iframe openclaw-tab-visibility 暫停語義,非協商)。
  function pauseMonitorView() {
    stopPolling();
  }

  // 註冊進殼可見的原生 view 表(router 以 v.iframe===false 查此;stable host / 唯一擴充點)。
  window.OC_NATIVE_VIEWS = window.OC_NATIVE_VIEWS || {};
  window.OC_NATIVE_VIEWS['monitor'] = { render: renderMonitorView, resume: resumeMonitorView, pause: pauseMonitorView };
  // 具名導出(task 契約:renderMonitorView / pauseMonitorView / resumeMonitorView 可被引用)。
  window.renderMonitorView = renderMonitorView;
  window.resumeMonitorView = resumeMonitorView;
  window.pauseMonitorView = pauseMonitorView;
})();
