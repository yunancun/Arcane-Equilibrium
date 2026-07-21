/*
 * view-strategy-history.js — 玄衡原生 view「策略中心」觀測面 companion(Phase 2 第 8 遷;全唯讀)
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:tab-strategy 遷移的**觀測面拆檔**(檔案 <2000 硬性;主檔 view-strategy.js 已承
 *   狀態/健康/策略列表/3 寫/掃描/编排器详情)。本檔不註冊 OC_NATIVE_VIEWS(非獨立 view),
 *   而註冊 window.OC_STRATEGY_HISTORY = {render, load},由主檔 view-strategy.js 於 render/loadAll 驅動
 *   (companion 缺席時主面照常降級)。**本檔全唯讀:零寫路徑**。
 *   內容逐節守恆(對 legacy tab-strategy 觀測 2 節,零丟失):
 *     ⑧近期交易意圖 Recent Order Intents(最近 30 條;/strategy/intents);
 *     ⑨策略师变更歷史 Strategist Apply History(summary + 篩選 + 列表 + Diff + 7d Effect + cycle metrics;
 *       /strategist/history/summary · /strategist/history · /strategist/history/{id}/effect ·
 *       /strategist/history/cycle_metrics)。
 * 刻意變更(canon 守恆,對齊主檔 austere):legacy .oc-card/.oc-chip/.oc-table/.oc-metric/.oc-collapse
 *   (ocInjectBaseCSS,殼不注入)不可用,改殼組件庫(.panel/.tag/.tbl/.note/.kpi);legacy 頁內 id
 *   改殼作用域 class 選擇器;裝飾 emoji 不遷;legacy .oc-diff-changed 改 .t-warn/.fw-semi 標注變更格。
 * 主要函數:render(建 意圖 + 歷史骨架,冪等)、load(唯讀 GET 渲染)、
 *   loadIntents / loadStrategistSummary / loadStrategistHistory / showStratHistDiff / showStratHistEffect /
 *   loadStrategistCycleMetrics。
 * 依賴(全復用,不重造):common.js ocApi;common-formatters.js ocEsc / ocSide / ocPct / ocQty /
 *   ocTimeShort / ocMoney / ocSignParts / OC_EMPTY;組件庫 shell-components.css + oc-utilities.css。
 * 硬邊界(canon / LOOP §6):
 *   ① 零寫路徑(全 GET;唯讀觀測面)。
 *   ② response-gated:ocApi 非-2xx/網路/timeout/CSRF 回 null → 顯錯不崩,不假數據。
 *   ③ canon 7 三態:loading=「Loading…」;無真值=「—」/空態提示(絕不假 0);degraded 顯後端 reason。
 *   ④ visibility 由主檔統籌;ratchet 0/0/0:零裸 hex、零 inline 樣式屬性、零內聯樣式塊;tone 走 scoped-var。
 * 誠實邊界:靜態只證 source/路徑/端點對齊;**真渲染/三態/真值 = NEEDS-LINUX runtime + operator 視覺**,不由本刀 attest。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  var host = null;
  var built = false;
  var _shRows = [];   // 策略师歷史列快取(供 Diff 由快取取值,免二次抓取)

  // ── 小工具(拆檔各持最小副本)──
  function root() { return host ? host.querySelector('.strategy-history-slot') : null; }
  function q(sel) { var r = root(); return r ? r.querySelector(sel) : null; }
  function esc(s) { return (typeof window.ocEsc === 'function') ? window.ocEsc(s) : String(s == null ? '' : s); }
  var EMPTY = (typeof window.OC_EMPTY === 'string') ? window.OC_EMPTY : '—';
  function timeShort(ts) { return (typeof window.ocTimeShort === 'function') ? window.ocTimeShort(ts) : (ts ? String(ts) : EMPTY); }

  function toneVar(tone) {
    if (tone === 'good') return 'var(--pos)';
    if (tone === 'bad') return 'var(--neg)';
    if (tone === 'muted') return 'var(--text-muted)';
    if (tone === 'accent') return 'var(--accent)';
    if (tone === 'info') return 'var(--accent)';
    return 'var(--warn)';
  }
  function applyTagTones(el) {
    if (!el) return;
    var tags = el.querySelectorAll('.tag[data-tone]');
    for (var i = 0; i < tags.length; i++) {
      tags[i].style.setProperty('--tag-tone', toneVar(tags[i].getAttribute('data-tone')));
    }
  }
  function tagHtml(text, tone) {
    return '<span class="tag" data-tone="' + esc(tone || 'muted') + '">' + esc(text) + '</span>';
  }
  function setText(cls, v) { var el = q('.' + cls); if (el) el.textContent = (v == null || v === '') ? EMPTY : String(v); }
  function setHtml(cls, html) { var el = q('.' + cls); if (el) el.innerHTML = html; }

  // ═══ 骨架 ═══
  var PANEL =
    // ═ 節⑧:近期交易意圖(默認收合)═
    '<details class="panel">' +
      '<summary class="fw-semi pointer">近期交易意圖 / Recent Order Intents(最近 30 條)</summary>' +
      '<div class="note mt-2 mb-2">交易意圖是策略產生的下單指令,經風控檢查(cost_gate / StopManager)後才轉為訂單。</div>' +
      '<table class="tbl">' +
        '<thead><tr><th>Time</th><th>Symbol</th><th>Side</th><th>Type</th><th>Qty</th><th>Conf</th><th>Source</th><th>Status</th></tr></thead>' +
        '<tbody class="sh-intents-body"><tr><td colspan="8" class="note">Loading…</td></tr></tbody>' +
      '</table>' +
    '</details>' +

    // ═ 節⑨:策略师变更歷史 ═
    '<details class="panel">' +
      '<summary class="fw-semi pointer">策略师变更歷史 / Strategist Apply History</summary>' +
      '<div class="note mt-2 mb-2">Strategist 5-min 自動 tune 与 Operator 手動 promote 審計轨跡(learning.strategist_applied_params,V019+V020)。全為成功 apply。</div>' +
      '<div class="kpis">' +
        '<div class="kpi"><div class="silk">TOTAL APPLIES · 總應用</div><div class="v num sh-total">' + EMPTY + '</div></div>' +
        '<div class="kpi"><div class="silk">AUTO-TUNE · 自動</div><div class="v num sh-auto">' + EMPTY + '</div></div>' +
        '<div class="kpi"><div class="silk">MANUAL PROMOTE · 手動</div><div class="v num sh-manual">' + EMPTY + '</div></div>' +
        '<div class="kpi"><div class="silk">OPERATOR OVERRIDE · 覆蓋</div><div class="v num sh-override">' + EMPTY + '</div></div>' +
      '</div>' +
      '<div class="row wrap gap-2 mt-2 mb-3">' +
        '<div><label class="fs-micro t-dim block">Engine Mode</label>' +
          '<select class="sh-mode oc-select"><option value="">All / 全部</option><option value="paper">paper</option><option value="demo">demo</option><option value="live">live</option><option value="live_demo">live_demo</option><option value="live_testnet">live_testnet</option></select></div>' +
        '<div><label class="fs-micro t-dim block">Strategy</label>' +
          '<select class="sh-strat oc-select"><option value="">All / 全部</option><option value="ma_crossover">ma_crossover</option><option value="bb_reversion">bb_reversion</option><option value="bb_breakout">bb_breakout</option><option value="grid_trading">grid_trading</option><option value="funding_arb">funding_arb</option></select></div>' +
        '<div><label class="fs-micro t-dim block">Source</label>' +
          '<select class="sh-source oc-select"><option value="">All / 全部</option><option value="strategist_scheduler">strategist_scheduler</option><option value="manual_promote">manual_promote</option><option value="operator_override">operator_override</option></select></div>' +
        '<button type="button" class="sh-apply tag pointer" data-tone="accent">Apply / 應用</button>' +
      '</div>' +
      '<table class="tbl">' +
        '<thead><tr><th>Time</th><th>Engine</th><th>Strategy</th><th>Source</th><th>Reason</th><th>Action</th></tr></thead>' +
        '<tbody class="sh-tbody"><tr><td colspan="6" class="note">Loading…</td></tr></tbody>' +
      '</table>' +
      '<div class="sh-detail-box mt-3"></div>' +
      // cycle metrics footer:解釋空表原因
      '<div class="panel mt-3 fs-micro t-dim">' +
        '<span class="fw-semi t-accent">近 scheduler cycle 健康度 / Recent cycle health:</span>' +
        '<span class="ml-2">rejects <strong class="sh-cyc-rejects t-warn">' + EMPTY + '</strong></span>' +
        '<span class="ml-2">applies <strong class="sh-cyc-applies t-pos">' + EMPTY + '</strong></span>' +
        '<span class="ml-2 sh-cyc-last">last: —</span>' +
        '<div class="mt-1 sh-cyc-hint"></div>' +
      '</div>' +
    '</details>';

  // ═══ 節⑧:近期交易意圖(port legacy loadIntents;/strategy/intents)═══
  async function loadIntents() {
    var d;
    try { d = await ocApi('/api/v1/strategy/intents'); } catch (e) { d = null; }
    if (!built) return;
    var body = q('.sh-intents-body');
    if (!body) return;
    if (!d || !d.data) { body.innerHTML = '<tr><td colspan="8" class="note t-warn">無法載入 / Load failed</td></tr>'; return; }
    var intents = d.data.intents || d.data || [];
    if (!intents.length) { body.innerHTML = '<tr><td colspan="8" class="note">暂無交易意圖 / No intents</td></tr>'; return; }
    var sideFn = (typeof window.ocSide === 'function') ? window.ocSide : function (s) { return esc(s); };
    var pctFn = (typeof window.ocPct === 'function') ? window.ocPct : function (v) { return v == null ? EMPTY : String(v); };
    var qtyFn = (typeof window.ocQty === 'function') ? window.ocQty : function (v) { return v == null ? EMPTY : String(v); };
    body.innerHTML = intents.slice(0, 30).map(function (i) {
      var status = i.status || 'pending';
      var tone = status === 'submitted' ? 'good'
        : (status.indexOf('rejected') === 0 || status.indexOf('blocked') === 0) ? 'bad'
        : status === 'pending' ? 'warn' : 'muted';
      return '<tr>' +
        '<td class="fs-micro">' + esc(timeShort(i.collected_ts_ms)) + '</td>' +
        '<td>' + esc(i.symbol) + '</td>' +
        '<td>' + sideFn(i.side) + '</td>' +
        '<td>' + esc(i.order_type || 'market') + '</td>' +
        '<td class="num">' + qtyFn(i.qty) + '</td>' +
        '<td class="num fs-micro">' + pctFn(i.confidence) + '</td>' +
        '<td class="fs-micro">' + esc(i.source || i.strategy_name || EMPTY) + '</td>' +
        '<td>' + tagHtml(status, tone) + '</td>' +
      '</tr>';
    }).join('');
    applyTagTones(body);
  }

  // ═══ 節⑨-a:歷史 summary(port legacy loadStrategistSummary;/strategist/history/summary)═══
  async function loadStrategistSummary() {
    var d;
    try { d = await ocApi('/api/v1/strategist/history/summary'); } catch (e) { d = null; }
    if (!built) return;
    if (!d || !d.data) {
      setText('sh-total', EMPTY); setText('sh-auto', EMPTY); setText('sh-manual', EMPTY); setText('sh-override', EMPTY);
      return;
    }
    setText('sh-total', d.data.total || 0);
    var bySrc = {};
    (d.data.by_source || []).forEach(function (r) { bySrc[r.source] = r.n; });
    setText('sh-auto', bySrc['strategist_scheduler'] || 0);
    setText('sh-manual', bySrc['manual_promote'] || 0);
    setText('sh-override', bySrc['operator_override'] || 0);
  }

  // ═══ 節⑨-b:歷史列表 + 篩選(port legacy loadStrategistHistory;/strategist/history?…)═══
  async function loadStrategistHistory() {
    var modeEl = q('.sh-mode'), stratEl = q('.sh-strat'), srcEl = q('.sh-source');
    var params = new URLSearchParams();
    if (modeEl && modeEl.value) params.set('engine_mode', modeEl.value);
    if (stratEl && stratEl.value) params.set('strategy_name', stratEl.value);
    if (srcEl && srcEl.value) params.set('source', srcEl.value);
    params.set('limit', '50');
    var qs = params.toString();
    var d;
    try { d = await ocApi('/api/v1/strategist/history' + (qs ? '?' + qs : '')); } catch (e) { d = null; }
    if (!built) return;
    var body = q('.sh-tbody');
    if (!body) return;
    if (!d || !d.data) { body.innerHTML = '<tr><td colspan="6" class="note t-warn">無法載入 / Failed to load</td></tr>'; _shRows = []; return; }
    if (d.data.degraded) { body.innerHTML = '<tr><td colspan="6" class="note t-warn">Degraded: ' + esc(d.data.reason || 'unknown') + '</td></tr>'; _shRows = []; return; }
    var rows = d.data.rows || [];
    _shRows = rows;
    if (!rows.length) { body.innerHTML = '<tr><td colspan="6" class="note">暂無記錄 / No history yet</td></tr>'; return; }
    body.innerHTML = rows.map(function (r) {
      var srcTone = r.source === 'manual_promote' ? 'warn' : r.source === 'operator_override' ? 'info' : 'muted';
      return '<tr>' +
        '<td class="fs-micro nowrap">' + esc(timeShort(r.applied_at)) + '</td>' +
        '<td>' + tagHtml(r.engine_mode || EMPTY, 'muted') + '</td>' +
        '<td>' + esc(r.strategy_name || EMPTY) + '</td>' +
        '<td>' + tagHtml(r.source || EMPTY, srcTone) + '</td>' +
        '<td class="fs-micro clip" title="' + esc(r.reason || '') + '">' + esc(r.reason || '') + '</td>' +
        '<td class="nowrap">' +
          '<button type="button" class="tag pointer" data-tone="muted" data-sh-kind="diff" data-sh-id="' + esc(r.id) + '">Diff</button> ' +
          '<button type="button" class="tag pointer" data-tone="muted" data-sh-kind="effect" data-sh-id="' + esc(r.id) + '">7d Effect</button>' +
        '</td>' +
      '</tr>';
    }).join('');
    applyTagTones(body);
  }

  // ═══ 節⑨-c:Diff(port legacy showStratHistDiff;由快取取值)═══
  function showStratHistDiff(rowId) {
    var row = _shRows.filter(function (r) { return String(r.id) === String(rowId); })[0];
    if (!row) { setHtml('sh-detail-box', '<div class="tag" data-tone="bad">Row not in cache — refresh first</div>'); applyTagTones(q('.sh-detail-box')); return; }
    var prev = row.prev_params_json || {};
    var cur = row.params_json || {};
    var keys = Array.from(new Set(Object.keys(prev).concat(Object.keys(cur)))).sort();
    var html = '<div class="panel">';
    html += '<div class="fw-semi mb-2">Diff: ' + esc(row.strategy_name) + ' (' + esc(row.engine_mode) + ') @ ' + esc(timeShort(row.applied_at)) + '</div>';
    html += '<div class="note mb-2">Reason: ' + esc(row.reason || '-') + ' · Source: ' + esc(row.source || '-') + '</div>';
    if (!keys.length) {
      html += '<div class="note">No params recorded</div>';
    } else {
      html += '<table class="tbl"><thead><tr><th>Param</th><th>Prev</th><th>Current</th></tr></thead><tbody>';
      keys.forEach(function (k) {
        var a = JSON.stringify(prev[k]);
        var b = JSON.stringify(cur[k]);
        var changed = a !== b;
        html += '<tr>';
        html += '<td class="fs-micro">' + esc(k) + '</td>';
        html += '<td class="mono fs-micro">' + esc(a != null ? a : '-') + '</td>';
        html += '<td class="mono fs-micro' + (changed ? ' t-warn fw-semi' : '') + '">' + esc(b != null ? b : '-') + '</td>';
        html += '</tr>';
      });
      html += '</tbody></table>';
    }
    html += '</div>';
    setHtml('sh-detail-box', html);
  }

  // ═══ 節⑨-d:7d Effect(port legacy showStratHistEffect;/strategist/history/{id}/effect)═══
  async function showStratHistEffect(rowId) {
    setHtml('sh-detail-box', '<div class="note">Loading 7d effect…</div>');
    var d;
    try { d = await ocApi('/api/v1/strategist/history/' + rowId + '/effect'); } catch (e) { d = null; }
    if (!built) return;
    var boxSel = q('.sh-detail-box');
    if (!d || !d.data) { if (boxSel) { boxSel.innerHTML = '<div class="tag" data-tone="bad">Failed to load effect</div>'; applyTagTones(boxSel); } return; }
    if (d.data.degraded) { if (boxSel) { boxSel.innerHTML = '<div class="tag" data-tone="warn">Degraded: ' + esc(d.data.reason || 'unknown') + '</div>'; applyTagTones(boxSel); } return; }
    var row = d.data.row || {};
    var eff = d.data.effect || {};
    // Net PnL 帶方向 → 態 class 走 ocSignParts;值 ocMoney 自帶 U+2212 號。
    var signFn = (typeof window.ocSignParts === 'function') ? window.ocSignParts : function () { return { cls: '' }; };
    var moneyFn = (typeof window.ocMoney === 'function') ? window.ocMoney : function (v) { return v == null ? EMPTY : String(v); };
    var pctFn = (typeof window.ocPct === 'function') ? window.ocPct : function (v) { return v == null ? EMPTY : String(v); };
    var pnlParts = signFn(eff.net_pnl);
    var html = '<div class="panel">';
    html += '<div class="fw-semi mb-2">7-day Effect: ' + esc(row.strategy_name || '-') + ' (' + esc(row.engine_mode || '-') + ')</div>';
    html += '<div class="note mb-2">Since apply @ ' + esc(timeShort(row.applied_at)) + '</div>';
    html += '<div class="kpis">';
    html += '<div class="kpi"><div class="silk">FILLS</div><div class="v num">' + (eff.fill_count || 0) + '</div></div>';
    html += '<div class="kpi"><div class="silk">NET PNL</div><div class="v num ' + pnlParts.cls + '">' + moneyFn(eff.net_pnl, 4) + '</div></div>';
    html += '<div class="kpi"><div class="silk">WIN RATE</div><div class="v num">' + pctFn(eff.win_rate) + '</div></div>';
    html += '</div>';
    html += '<div class="note mt-2">Window: ' + esc(timeShort(eff.window_start_ms)) + ' → ' + esc(timeShort(eff.window_end_ms));
    if (eff.first_fill_ts) html += ' · first fill ' + esc(timeShort(eff.first_fill_ts));
    if (eff.last_fill_ts) html += ' · last fill ' + esc(timeShort(eff.last_fill_ts));
    html += '</div></div>';
    setHtml('sh-detail-box', html);
  }

  // ═══ 節⑨-e:cycle metrics(port legacy loadStrategistCycleMetrics;/strategist/history/cycle_metrics)═══
  async function loadStrategistCycleMetrics() {
    var d;
    try { d = await ocApi('/api/v1/strategist/history/cycle_metrics'); } catch (e) { d = null; }
    if (!built) return;
    if (!d || !d.data) {
      setText('sh-cyc-rejects', EMPTY); setText('sh-cyc-applies', EMPTY); setText('sh-cyc-last', 'last: —');
      setHtml('sh-cyc-hint', '<span class="t-neg">端點不可用(uvicorn 需 restart 帶入新 route)</span>');
      return;
    }
    var r = d.data.rejects || 0;
    var a = d.data.applies || 0;
    setText('sh-cyc-rejects', String(r));
    setText('sh-cyc-applies', String(a));
    var lastStr;
    if (d.data.last_apply && d.data.last_apply.ts) {
      lastStr = 'last apply: ' + timeShort(d.data.last_apply.ts);
    } else if (d.data.last_reject && d.data.last_reject.ts) {
      var lr = d.data.last_reject;
      lastStr = 'last reject: ' + timeShort(lr.ts) + (lr.param ? ' · ' + lr.param + ' ' + lr.current + '→' + lr.proposed + ' (' + lr.delta_pct + ')' : '');
    } else {
      lastStr = 'last: (none in ' + (d.data.scan_window || 'recent log') + ')';
    }
    setText('sh-cyc-last', lastStr);
    var hint;
    if (d.data.degraded) {
      hint = '<span class="t-warn">log 檔不可讀(' + esc(d.data.log_path || '?') + '),計數未必完整</span>';
    } else if (a === 0 && r > 0) {
      hint = '<span class="t-warn">所有 propose 被 ±30% cap 拒絕(LLM 產出超邊界)→ 表永遠空 ≠ GUI 壞</span>';
    } else if (a === 0 && r === 0) {
      hint = '近 ' + esc(d.data.scan_window || '?') + ' 內無 strategist cycle 活動(scheduler 可能停滯或未啟動)';
    } else {
      hint = '掃描範圍:' + esc(d.data.scan_window || '?') + ' · log ' + esc(d.data.log_path || '?');
    }
    setHtml('sh-cyc-hint', hint);
  }

  // ═══ 控件接線(事件委派:Apply 篩選 / Diff / 7d Effect)═══
  function wire() {
    var slot = root();
    if (!slot) return;
    slot.addEventListener('click', function (ev) {
      var t = ev.target;
      var btn = (t && typeof t.closest === 'function') ? t.closest('button.sh-apply, button[data-sh-kind]') : null;
      if (!btn) return;
      if (btn.classList.contains('sh-apply')) { loadStrategistHistory(); return; }
      var kind = btn.getAttribute('data-sh-kind');
      var id = btn.getAttribute('data-sh-id');
      if (kind === 'diff') showStratHistDiff(id);
      else if (kind === 'effect') showStratHistEffect(id);
    });
  }

  // ═══ 主檔掛鉤:render(建骨架)+ load(唯讀 GET 渲染)═══
  function render(hostEl) {
    if (hostEl) host = hostEl;
    var slot = root();
    if (!slot || built) return;
    slot.innerHTML = PANEL;
    built = true;
    applyTagTones(slot);
    wire();
  }
  async function load() {
    if (!built) return;
    await Promise.allSettled([
      loadIntents(), loadStrategistSummary(), loadStrategistHistory(), loadStrategistCycleMetrics()
    ]);
  }

  // 註冊 companion hook(主檔 view-strategy.js 於 render/loadAll 驅動;非獨立 OC_NATIVE_VIEWS)。
  window.OC_STRATEGY_HISTORY = { render: render, load: load };
})();
