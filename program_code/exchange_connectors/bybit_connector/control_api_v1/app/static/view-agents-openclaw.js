/*
 * view-agents-openclaw.js — 玄衡「Agent 團隊」view 的 OpenClaw 控制面 companion(Phase 2 第 5 遷拆檔;read-only)
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:承接 view-agents.js 主檔(Phase 2 第 5 遷)拆出的 **OpenClaw Agent Control 只讀面**——
 *   本地 5-Agent / Gateway / Rust engine / event-store row proof 的**唯讀總覽**(authority lockdown /
 *   gateway·channel posture / topology / degraded·error state 四面板)。拆檔理由:主檔逼近 800 硬性
 *   上限,openclaw 面自成一塊(獨立 read-only header fetch 契約),拆出使兩檔各 <800 且職責分明。
 *   本檔不註冊 OC_NATIVE_VIEWS(非獨立 view),而註冊 window.OC_AGENTS_OPENCLAW = {render, load},
 *   由主檔於 renderAgentsView 掛鉤(render 建面板骨架進主檔的 .ag-openclaw 宿主)+ loadAll 驅動(load)。
 *   內容逐元素守恆(對 legacy openclaw-agent-control.js,零丟失):
 *     ①狀態總 chip(PASS/FAIL/DEGRADED/WARN/DISABLED/UNKNOWN);②Authority Lockdown(trading
 *       authority / gateway role / event rows 30m msg·state·ai / row proof / 4 capability:submit
 *       orders·mutate live config·read secrets·proposal endpoints,皆 safe-when-false=不可寫才 good);
 *     ③Gateway · Channel Posture(gateway status / runtime connection / engine alive / cloud
 *       supervisor / channels);④Topology(agents + gateway + rust_engine 節點,tone by runtime_state);
 *     ⑤Degraded / Error State(open_blockers 或「無阻塞」)。
 *   刻意變更(canon 守恆非逐像素):legacy 頁內 `.agent-control-*` class(tab-agents 頁內樣式區塊,
 *     iframe 作用域,殼不載)不可用,改以殼原生組件庫(.tbl kv 行 / .tag tone / .logblock 節點)重渲。
 *     裝飾去除;capability/authority/health 語義完整保留。
 * 硬邊界(canon / LOOP §6):
 *   ① **零寫路徑**——read-only 前端,只發 2 GET(/openclaw/status · /openclaw/self-state,皆 ∈ 後端
 *      authoritative:openclaw_routes.py:947 / :986)。**絕不發 POST/PUT/PATCH/DELETE、無 control 動作**。
 *   ② **必送 read-only header**(openclawGet;非可省):後端 _build_request_context 若缺
 *      x-openclaw-* header → 標 request_context_inferred → status **誤判 degraded**(openclaw_routes.py
 *      :358)。故保留 legacy MAG-018 read-only header 契約(x-openclaw-source/channel/sender/
 *      auth-profile=read_only/request-id),否則會**假降級**真健康(canon 7:不 fake health,兩向皆禁)。
 *      注:此 2 GET 走裸 fetch(path,…) header helper(同 legacy),5b 對齊視為 dynamic-base(不入靜態
 *      check,與 legacy 一致=非回歸);路由已人工核對 ∈ authoritative。
 *   ③ canon 7 三態:loading=「讀取中…」;error(2 GET 皆 null)=顯錯不崩「暫時不可用;交易 runtime
 *      不受影響」;無真值 → 「—」/保守 tone。**絕不假 authority/capability/health**。
 *   ④ ratchet 0/0/0:零裸 hex、零 inline style 屬性、零內聯樣式區塊;tone 走 --tag-tone scoped-var。
 * 誠實邊界:靜態只證 source/路徑;**真渲染 / OpenClaw 真健康 / capability 真值 = NEEDS-LINUX
 *   runtime + operator 視覺**,不由本刀 attest。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  var host = null;                 // 主檔傳入的 view 宿主(openclaw 面渲進其 .ag-openclaw)
  var built = false;               // 面板骨架是否已建(render 冪等)

  // ── 小工具(復用 window.ocEsc / OC_EMPTY;tone/tag 與主檔同構,拆檔各自持有最小副本)──
  function root() { return host ? host.querySelector('.ag-openclaw') : null; }
  function q(sel) { var r = root(); return r ? r.querySelector(sel) : null; }
  function esc(s) { return (typeof window.ocEsc === 'function') ? window.ocEsc(s) : String(s == null ? '' : s); }
  var EMPTY = (typeof window.OC_EMPTY === 'string') ? window.OC_EMPTY : '—';

  function toneVar(tone) {
    if (tone === 'good') return 'var(--pos)';
    if (tone === 'bad') return 'var(--neg)';
    if (tone === 'muted') return 'var(--text-muted)';
    if (tone === 'accent') return 'var(--accent)';
    return 'var(--warn)';
  }
  function tagHtml(text, tone) {
    return '<span class="tag" data-tone="' + esc(tone || 'muted') + '">' + esc(text) + '</span>';
  }
  function applyTagTones(el) {
    if (!el) return;
    var tags = el.querySelectorAll('.tag[data-tone]');
    for (var i = 0; i < tags.length; i++) {
      tags[i].style.setProperty('--tag-tone', toneVar(tags[i].getAttribute('data-tone')));
    }
  }
  function num(v) { return (v == null || !isFinite(Number(v))) ? '--' : String(Number(v)); }

  // ═══ read-only header fetch(port legacy _openclawApi;header 非可省——見 MODULE_NOTE 硬邊界②)═══
  function sender() { try { return localStorage.getItem('oc_username') || 'console'; } catch (_) { return 'console'; } }
  function requestId() {
    try { if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID(); } catch (_) {}
    return 'openclaw-' + Date.now() + '-' + Math.random().toString(16).slice(2);
  }
  // GET only,永不寫。path 為變數 → 5b 對齊視為 dynamic(同 legacy);路由已人工核 ∈ authoritative。
  function openclawGet(path) {
    var headers = {
      'x-openclaw-source': 'tradebot-console',
      'x-openclaw-channel': 'console',
      'x-openclaw-sender': sender(),
      'x-openclaw-auth-profile': 'read_only',
      'x-openclaw-request-id': requestId()
    };
    return fetch(path, { method: 'GET', headers: headers, credentials: 'same-origin', signal: AbortSignal.timeout(8000) })
      .then(function (r) {
        if (!r.ok) {
          if (typeof window.ocHandleUnauthenticatedResponse === 'function') { try { window.ocHandleUnauthenticatedResponse(r); } catch (_) {} }
          console.warn('[view-agents-openclaw] GET ' + path + ' -> ' + r.status);
          return null;
        }
        return r.json();
      })
      .catch(function (e) { console.warn('[view-agents-openclaw] network error: ' + path, e); return null; });
  }

  // ═══ 值→tone 映射(port legacy _openclawStatusChip;回 {text,tone} 直設 .oc-status pill)═══
  function statusMeta(status, degraded) {
    var s = String(status || 'unknown').toLowerCase();
    if (s === 'pass' && !degraded) return { text: 'PASS', tone: 'good' };
    if (s === 'fail') return { text: 'FAIL', tone: 'bad' };
    if (s === 'degraded' || degraded) return { text: 'DEGRADED', tone: 'warn' };
    if (s === 'warn') return { text: 'WARN', tone: 'warn' };
    if (s === 'disabled') return { text: 'DISABLED', tone: 'muted' };
    return { text: 'UNKNOWN', tone: 'bad' };
  }
  // capability 行:safeWhenFalse=true 代表「不可(false)才安全→good」;yes/no + tone。
  function capRow(label, allowed, safeWhenFalse) {
    var ok = safeWhenFalse ? allowed === false : allowed === true;
    return '<tr><td class="t-muted">' + esc(label) + '</td><td class="t-right">' + tagHtml(allowed ? 'yes' : 'no', ok ? 'good' : 'bad') + '</td></tr>';
  }
  function kvRow(label, valueHtml) {
    return '<tr><td class="t-muted">' + esc(label) + '</td><td class="t-right">' + valueHtml + '</td></tr>';
  }
  function nodeTone(state) {
    var s = String(state || '').toLowerCase();
    if (s === 'running' || s === 'available' || s === 'healthy') return 'good';
    if (s === 'offline' || s === 'failed' || s === 'error') return 'bad';
    return 'warn';   // disabled / not_configured / unknown → 保守 warn(canon 7)
  }

  // ═══ 四面板渲染(from status/self payload)═══
  function renderAuthority(statusPayload) {
    var data = (statusPayload && statusPayload.data) || {};
    var authority = data.authority || {};
    var es = data.agent_event_store || {};
    var rows = es.recent_rows || {};
    var html = '<table class="tbl"><tbody>';
    html += kvRow('Trading authority', '<span class="mono">' + esc(authority.trading_authority || '--') + '</span>');
    html += kvRow('Gateway role', esc(authority.gateway_role || '--'));
    html += kvRow('Event rows 30m', '<span class="mono fs-micro">msg ' + num(rows.messages) + ' / state ' + num(rows.state_changes) + ' / ai ' + num(rows.ai_invocations) + '</span>');
    html += kvRow('Row proof', tagHtml(es.row_proof ? 'complete' : 'incomplete', es.row_proof ? 'good' : 'warn'));
    html += capRow('Submit orders', authority.can_submit_orders, true);
    html += capRow('Mutate live config', authority.can_mutate_live_config, true);
    html += capRow('Read secrets', authority.can_read_secrets, true);
    html += capRow('Proposal endpoints', authority.deferred_workflows_enabled, true);
    html += '</tbody></table>';
    var el = q('.oc-authority');
    if (el) { el.innerHTML = html; applyTagTones(el); }
  }
  function renderGateway(statusPayload) {
    var data = (statusPayload && statusPayload.data) || {};
    var gateway = data.gateway || {}, runtime = data.runtime || {}, budget = data.model_budget || {};
    var channels = gateway.channels || {};
    var html = '<table class="tbl"><tbody>';
    html += kvRow('Gateway', tagHtml(gateway.status || 'unknown', gateway.configured ? 'good' : 'muted'));
    html += kvRow('Runtime connection', tagHtml(runtime.runtime_connection_state || 'unknown', runtime.runtime_connection_state === 'healthy' ? 'good' : 'warn'));
    html += kvRow('Engine alive', tagHtml(String(runtime.engine_alive), runtime.engine_alive === true ? 'good' : 'warn'));
    html += kvRow('Cloud supervisor', tagHtml(budget.cloud_enabled ? 'enabled' : 'disabled', budget.cloud_enabled ? 'warn' : 'muted'));
    html += '</tbody></table>';
    var chanKeys = Object.keys(channels);
    if (chanKeys.length) {
      html += '<div class="row wrap gap-2 mt-2">';
      chanKeys.forEach(function (name) {
        html += tagHtml(name + ': ' + channels[name], channels[name] === 'available' ? 'good' : 'muted');
      });
      html += '</div>';
    }
    var el = q('.oc-gateway');
    if (el) { el.innerHTML = html; applyTagTones(el); }
  }
  function renderTopology(selfPayload) {
    var data = (selfPayload && selfPayload.data) || {};
    var agents = data.agents || [], gateway = data.gateway || {}, runtime = data.runtime || {};
    var nodes = agents.slice();
    nodes.push({ role: 'gateway', runtime_state: gateway.status || 'unknown', source: gateway.configured ? 'configured' : 'not_configured' });
    nodes.push({ role: 'rust_engine', runtime_state: runtime.runtime_connection_state || 'unknown', source: runtime.engine_alive === true ? 'engine_alive' : 'runtime_summary' });
    var html = nodes.map(function (r) {
      var state = r.runtime_state || 'unknown';
      return '<div class="logblock"><div class="w-full">' +
        '<div class="row-between gap-2"><strong class="t-primary">' + esc(r.role || 'unknown') + '</strong>' + tagHtml(state, nodeTone(state)) + '</div>' +
        (r.source ? '<div class="t-muted fs-micro mt-1">' + esc(r.source) + '</div>' : '') +
      '</div></div>';
    }).join('');
    var el = q('.oc-topology');
    if (el) { el.innerHTML = html || '<div class="note">無節點資料 / No nodes</div>'; applyTagTones(el); }
  }
  function renderBlockers(selfPayload) {
    var data = (selfPayload && selfPayload.data) || {};
    var blockers = data.open_blockers || [];
    var el = q('.oc-blockers');
    if (!el) return;
    if (!blockers.length) { el.innerHTML = '<div class="note t-pos">無只讀阻塞 / No active MAG-018 read-only blockers</div>'; return; }
    el.innerHTML = blockers.map(function (b) {
      var sev = b.severity || 'warn';
      return '<div class="logblock"><div class="w-full">' +
        '<div class="row-between gap-2"><strong class="t-primary">' + esc(b.code || 'blocker') + '</strong>' + tagHtml(sev, sev === 'fail' ? 'bad' : 'warn') + '</div>' +
        '<div class="t-muted fs-micro mt-1">' + esc(b.summary || '') + '</div>' +
      '</div></div>';
    }).join('');
    applyTagTones(el);
  }

  // ═══ 面板骨架(render 冪等;建進主檔 .ag-openclaw 宿主)═══
  var PANEL =
    '<div class="panel">' +
      '<div class="row-between wrap gap-3">' +
        '<div>' +
          '<div class="panel-t"><span class="zh">OpenClaw 控制面</span><span class="code">OPENCLAW AGENT CONTROL · READ-ONLY</span></div>' +
          '<div class="note">本地 5-Agent、Gateway、Rust engine、event-store row proof 的只讀總覽。此面板不受交易 runtime 影響,亦不能在此改變 authority。</div>' +
        '</div>' +
        '<span class="oc-status tag" data-tone="muted">loading…</span>' +
      '</div>' +
      '<div class="oc-error panel note t-warn hidden">OpenClaw self-state 暫時不可用;交易 runtime 不受此面板影響。</div>' +
      '<div class="oc-body">' +
        '<div class="row wrap gap-3">' +
          '<div class="col flex-1"><div class="silk">AUTHORITY LOCKDOWN</div><div class="oc-authority mt-1"><div class="note">Loading…</div></div></div>' +
          '<div class="col flex-1"><div class="silk">GATEWAY · CHANNEL</div><div class="oc-gateway mt-1"><div class="note">Loading…</div></div></div>' +
        '</div>' +
        '<div class="row wrap gap-3 mt-3">' +
          '<div class="col flex-1"><div class="silk">TOPOLOGY</div><div class="oc-topology logs mt-1"><div class="note">Loading…</div></div></div>' +
          '<div class="col flex-1"><div class="silk">DEGRADED / ERROR STATE</div><div class="oc-blockers logs mt-1"><div class="note">Loading…</div></div></div>' +
        '</div>' +
      '</div>' +
    '</div>';

  function setStatus(text, tone) {
    var el = q('.oc-status');
    if (!el) return;
    el.textContent = text;
    el.setAttribute('data-tone', tone || 'muted');
    el.style.setProperty('--tag-tone', toneVar(tone || 'muted'));
  }
  function showError(on) {
    var err = q('.oc-error'), body = q('.oc-body');
    if (err) err.classList.toggle('hidden', !on);
    if (body) body.classList.toggle('hidden', !!on);
  }

  // ═══ 主檔掛鉤:render(建骨架)+ load(拉 2 GET 渲四面板)═══
  function render(hostEl) {
    if (hostEl) host = hostEl;
    var slot = root();
    if (!slot) return;
    if (built) return;
    slot.innerHTML = PANEL;
    built = true;
    setStatus('loading…', 'muted');
  }
  async function load() {
    if (!built) return;
    var res = await Promise.allSettled([
      openclawGet('/api/v1/openclaw/status'),
      openclawGet('/api/v1/openclaw/self-state')
    ]);
    if (!built) return;
    var statusPayload = res[0].status === 'fulfilled' ? res[0].value : null;
    var selfPayload = res[1].status === 'fulfilled' ? res[1].value : null;
    if (!statusPayload && !selfPayload) {
      setStatus('不可用', 'bad');
      showError(true);
      return;
    }
    showError(false);
    var primary = statusPayload || selfPayload;
    if (primary) { var meta = statusMeta(primary.status, primary.degraded); setStatus(meta.text, meta.tone); }
    renderAuthority(statusPayload || selfPayload);
    renderGateway(statusPayload || selfPayload);
    renderTopology(selfPayload || statusPayload);
    renderBlockers(selfPayload || statusPayload);
  }

  // 註冊 companion hook(主檔 view-agents.js 於 render/loadAll 驅動;非獨立 OC_NATIVE_VIEWS)。
  window.OC_AGENTS_OPENCLAW = { render: render, load: load };
})();
