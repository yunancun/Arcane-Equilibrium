/*
 * view-gates.js — 玄衡原生 view「封驗 Gates」(Phase 2 首個 iframe→原生遷移)
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:把 legacy `tab-edge-gates.html`(iframe 後備)遷成玄衡殼內的**原生 view**,
 *   證明 strangler-fig 遷移 pattern(design/10 recipe §0-§1):殼 router 為穩定宿主,
 *   本檔提供 render/pause/resume 為唯一新增擴充點(second-adapter)。內容逐元素守恆:
 *   4 KPI(readiness / crisis / passing / healthcheck)、全局 healthcheck 面板、
 *   Live readiness checklist、關鍵 Gate 卡([33] maker / [38] grid lifecycle / [40] realized edge)、
 *   策略達標矩陣——與 legacy 同資料、同 2 個 GET,只換玄衡組件庫版式。
 * 主要函數:renderGatesView(建骨架,冪等)、resumeGatesView(顯示→拉真值+啟輪詢)、
 *   pauseGatesView(隱藏→停輪詢/停 fetch)、load / loadEdge / loadHealth(per-view fetch)、
 *   renderEdge / renderGateCards / renderReadiness / renderStrategies / renderHealth(組件渲染)。
 * 依賴(全復用,不重造):common.js ocApi;common-formatters.js ocEsc / ocBps / ocPctVal /
 *   ocNum / ocSigned / ocSignParts / ocMiniTrendSvg / ocTimeShort / ocDate / OC_EMPTY;
 *   組件庫 shell-components.css(.panel/.panel-t/.tbl/.tag/.kpis/.kpi/.note/.code)+
 *   tokens.css(.num/.silk)+ oc-utilities.css(flex/間距/val-* 第二通道)。
 * 硬邊界(canon / LOOP §6):
 *   ① 零寫路徑——只 2 個唯讀 GET(/strategy/prelive/edge-gates、/system/health),無 POST/order。
 *   ② canon 7 三態:loading=骨架「—/loading…」;無真值=「—」/UNKNOWN(絕不假 pass/假 0);
 *      error(ocApi 回 null)=顯錯不崩,保守標 warn/bad,絕不冒充 PASS。
 *   ③ visibility 語義(非協商):隱藏時 pauseGatesView 停輪詢/停後端抓取(鏡像 iframe
 *      openclaw-tab-visibility 暫停),否則隱藏續打後端=freshness/safety 退步。
 *   ④ ratchet 0/0/0:零裸 hex、零 inline style 屬性、零內聯樣式區塊;動態 tone 走
 *      .style.setProperty('--tag-tone', var(...)) scoped-var 正法(非樣式屬性字面)。
 * 誠實邊界:靜態(node --check + ratchet + 5b 對齊 + registry smoke)只證 source/路徑事實;
 *   **真渲染正確性 / 三態版式 / 真值 = NEEDS-LINUX runtime + operator 視覺**,不由本刀 attest。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  // ── 常量 ──
  var POLL_MS = 30000;             // 輪詢間隔(鏡像 legacy setInterval 30s;僅可見時運行)
  var STALE_MS = 180000;           // 新鮮度門檻:generated_at 逾 3min → fresh-badge STALE(canon 7)
  var KNOWN_STRATEGIES = ['grid_trading', 'ma_crossover', 'funding_arb', 'bb_breakout', 'bb_reversion'];

  // ── 執行期狀態 ──
  var host = null;                 // 原生 <section> 宿主(shell 注入)
  var built = false;               // 骨架是否已建(render 冪等)
  var timer = null;                // 輪詢 interval id(null=停;pause 必清)
  var loading = false;             // fetch 去重(單次 load 內兩 GET 並行,不重入)
  var windowDays = '7';            // 視窗選擇(7/14/30;鏡像 legacy select 預設 7d)

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
  // tone → 文字色 utility class(oc-utilities .t-*;KPI 值 / 分數用)。
  function toneTextClass(tone) {
    if (tone === 'good') return 't-pos';
    if (tone === 'bad') return 't-neg';
    if (tone === 'muted') return 't-muted';
    return 't-warn';
  }

  // 狀態 → tone(port legacy toneFor;中性未知回 warn = 保守)。
  function toneFor(status) {
    var s = String(status || '').toLowerCase();
    if (s === 'pass' || s === 'ready') return 'good';
    if (s === 'warn' || s === 'not_ready' || s === 'unknown') return 'warn';
    if (s === 'fail' || s === 'crisis') return 'bad';
    return 'warn';
  }
  // 狀態 → 顯示標籤(port legacy chipFor 的 label 對照)。
  function chipLabel(status, label) {
    var s = String(status || 'unknown').toLowerCase();
    return label || (
      s === 'pass' ? 'PASS' :
      s === 'ready' ? 'READY' :
      s === 'warn' ? 'WARN' :
      s === 'fail' ? 'FAIL' :
      s === 'crisis' ? 'CRISIS' :
      s === 'not_ready' ? 'NOT READY' : 'UNKNOWN'
    );
  }

  // 產出 .tag pill 的 HTML(帶 data-tone;真正 tone 由 applyTagTones 以 scoped-var 上色,
  // 避免 innerHTML 內寫死 style=/hex —— ratchet 正法)。
  function tagHtml(text, tone) {
    return '<span class="tag" data-tone="' + esc(tone || 'warn') + '">' + esc(text) + '</span>';
  }
  // 掃 root 內所有 .tag[data-tone],逐一寫 --tag-tone scoped-var(component .tag 消費之)。
  function applyTagTones(root) {
    if (!root) return;
    var tags = root.querySelectorAll('.tag[data-tone]');
    for (var i = 0; i < tags.length; i++) {
      tags[i].style.setProperty('--tag-tone', toneVar(tags[i].getAttribute('data-tone')));
    }
  }

  // 泛型 value+suffix(port legacy metricValue):非契約型別 count/ratio/'x'/'m';無值回 EMPTY(禁假零)。
  function metricValue(value, suffix, decimals) {
    if (value == null || value === '') return EMPTY;
    var n = Number(value);
    if (!Number.isFinite(n)) return esc(value);
    var d = decimals == null ? 1 : decimals;
    return window.ocNum(n, d) + (suffix || '');
  }

  // ═══ 骨架(canon 7:首渲即 loading 態「—/loading…」,絕不假值)═══
  var SKELETON =
    '<div class="p-4">' +
      // 標頭面板:題 + 說明 + 工具列(視窗選擇 / 刷新 / 更新狀態徽)
      '<div class="panel">' +
        '<div class="row-between wrap gap-3">' +
          '<div>' +
            '<div class="panel-t"><span class="zh">封驗 Gates</span><span class="code">PRE-LIVE EDGE GATES</span></div>' +
            '<div class="note">策略達標、crisis、Edge gates 與全局 healthcheck fail/warn 彙總。</div>' +
          '</div>' +
          '<div class="row wrap gap-2">' +
            '<select class="gv-window mono fs-dense" aria-label="視窗天數">' +
              '<option value="7">7d</option><option value="14">14d</option><option value="30">30d</option>' +
            '</select>' +
            '<button type="button" class="gv-refresh mono fs-dense t-accent pointer">刷新 / Refresh</button>' +
            '<span class="gv-updated tag" data-tone="warn">loading…</span>' +
          '</div>' +
        '</div>' +
      '</div>' +
      // KPI 行(1 hero + 3):readiness / crisis / passing / healthcheck
      '<div class="kpis">' +
        '<div class="kpi hero gv-kpi-readiness"><div class="silk">LIVE READINESS</div><div class="v">' + EMPTY + '</div><div class="d note gv-sub">' + EMPTY + '</div></div>' +
        '<div class="kpi gv-kpi-crisis"><div class="silk">STRATEGY CRISIS</div><div class="v">' + EMPTY + '</div><div class="d note gv-sub">' + EMPTY + '</div></div>' +
        '<div class="kpi gv-kpi-pass"><div class="silk">STRATEGIES PASSING</div><div class="v">' + EMPTY + '</div><div class="d note gv-sub">' + EMPTY + '</div></div>' +
        '<div class="kpi gv-kpi-health"><div class="silk">GLOBAL HEALTHCHECK</div><div class="v">' + EMPTY + '</div><div class="d note gv-sub">' + EMPTY + '</div></div>' +
      '</div>' +
      // 錯誤橫幅(canon 7:error 顯錯不崩;預設隱藏)
      '<div class="gv-error panel note t-warn hidden"></div>' +
      // 全局 healthcheck + Live readiness checklist(兩面板)
      '<div class="row wrap gap-3">' +
        '<div class="panel flex-1">' +
          '<div class="panel-t"><span class="zh">全局 Healthcheck</span><span class="code">GLOBAL HEALTHCHECK</span></div>' +
          '<div class="gv-health-body note">Loading…</div>' +
        '</div>' +
        '<div class="panel flex-1">' +
          '<div class="panel-t"><span class="zh">Live Readiness</span><span class="code">READINESS CHECKLIST</span></div>' +
          '<div class="gv-readiness note">Loading…</div>' +
        '</div>' +
      '</div>' +
      // 關鍵 Gate 卡([33]/[38]/[40])
      '<div class="panel">' +
        '<div class="panel-t"><span class="zh">關鍵 Gate</span><span class="code">GATE CARDS · [33] MAKER · [38] LIFECYCLE · [40] REALIZED EDGE</span></div>' +
        '<div class="gv-gates row wrap gap-3"><div class="note">Loading…</div></div>' +
      '</div>' +
      // 策略達標矩陣
      '<div class="panel">' +
        '<div class="panel-t"><span class="zh">策略達標矩陣</span><span class="code">STRATEGY GATE MATRIX</span><span class="gv-strat-src code"></span></div>' +
        '<table class="tbl">' +
          '<thead><tr>' +
            '<th>Strategy</th><th>Status</th><th>24h Avg Net</th><th>24h Rows</th>' +
            '<th>Win Rate</th><th>Window Avg</th><th>Reason / Crisis Cells</th>' +
          '</tr></thead>' +
          '<tbody class="gv-strat-body"><tr><td colspan="7" class="note">Loading…</td></tr></tbody>' +
        '</table>' +
      '</div>' +
    '</div>';

  function emptyRow(msg) {
    return '<tr><td colspan="7" class="note">' + esc(msg) + '</td></tr>';
  }

  // ═══ KPI 設值(值 tone 走文字色 class;sub 為 note 文字)═══
  function setKpi(prefix, value, tone, sub) {
    var v = q('.' + prefix + ' .v');
    if (v) { v.className = 'v ' + toneTextClass(tone); v.textContent = value; }
    var d = q('.' + prefix + ' .gv-sub');
    if (d) { d.textContent = sub || ''; }
  }

  // ═══ 更新徽(new fresh-badge 語義:good=已更新 / warn=STALE·無資料 / bad=錯誤)═══
  function setUpdated(text, tone) {
    var el = q('.gv-updated');
    if (!el) return;
    el.textContent = text;
    el.setAttribute('data-tone', tone || 'warn');
    el.style.setProperty('--tag-tone', toneVar(tone || 'warn'));
  }
  function setUpdatedFrom(generatedAt) {
    var d = (typeof window.ocDate === 'function') ? window.ocDate(generatedAt) : null;
    if (!d) { setUpdated('updated', 'good'); return; }
    var stale = (Date.now() - d.getTime()) > STALE_MS;
    setUpdated('updated ' + window.ocTimeShort(generatedAt) + (stale ? ' · STALE' : ''), stale ? 'warn' : 'good');
  }

  function showError(msg) {
    var el = q('.gv-error');
    if (!el) return;
    if (msg) { el.textContent = msg; el.classList.remove('hidden'); }
    else { el.textContent = ''; el.classList.add('hidden'); }
  }

  // ═══ Gate 卡:值格(port legacy gateValueCells;型別正確 formatter)═══
  function gateValueCells(gate) {
    var c = (gate && gate.current) || {};
    if (!gate) return [];
    if (gate.gate_id === '33') {
      // fee_drop_pct / maker_like_pct 皆 already-percent(producer *100)→ ocPctVal(2dp)。
      return [
        ['Fee drop', window.ocPctVal(c.fee_drop_pct)],
        ['Maker-like', window.ocPctVal(c.maker_like_pct)],
        ['Entry fills', metricValue(c.entry_fills, '', 0)],
      ];
    }
    if (gate.gate_id === '38') {
      // lifetime_ratio(倍率 x)/ p50(分鐘 m)/ reentry_rate(比率)非契約型別 → metricValue。
      return [
        ['Lifetime', metricValue(c.lifetime_ratio, 'x', 2)],
        ['Live p50', metricValue(c.live_demo_p50_min, 'm', 1)],
        ['Re-entry', metricValue(c.live_demo_reentry_rate, '', 2)],
      ];
    }
    if (gate.gate_id === '40') {
      // avg_net_bps 帶方向淨邊際(可正負)→ ocSigned + 第二通道 sign/色。
      return [
        ['Avg net', window.ocSigned(c.avg_net_bps, window.ocBps)],
        ['Rows', metricValue(c.rows, '', 0)],
        ['Bad cells', metricValue((c.bad_cells || []).length, '', 0)],
      ];
    }
    return [];
  }

  // Gate 卡趨勢序列(port legacy trendValues;餵 ocMiniTrendSvg)。
  function trendValues(gate) {
    var rows = Array.isArray(gate && gate.series) ? gate.series : [];
    if (!gate) return [];
    if (gate.gate_id === '33') return rows.map(function (r) { return r.fee_drop_pct; });
    if (gate.gate_id === '38') return rows.map(function (r) { return r.lifetime_ratio; });
    if (gate.gate_id === '40') return rows.map(function (r) { return r.avg_net_bps; });
    return [];
  }

  function renderGateCard(gate) {
    var tone = toneFor(gate.status);
    var cells = gateValueCells(gate).map(function (pair) {
      return '<div class="col"><div class="silk">' + esc(pair[0]) + '</div>' +
             '<div class="num fs-md">' + pair[1] + '</div></div>';
    }).join('');
    // ocMiniTrendSvg:復用 authoritative helper(stroke 走 var(--pos/--neg/--warn),ratchet 安全);
    // 尺寸由 shell-components.css .gv-spark svg 給(legacy .oc-mini-trend CSS 不在殼作用域)。
    var spark = (typeof window.ocMiniTrendSvg === 'function')
      ? window.ocMiniTrendSvg(trendValues(gate), { tone: tone, includeZero: gate.gate_id === '40' })
      : '';
    return '<div class="panel flex-1">' +
      '<div class="row-between gap-2 mb-2">' +
        '<div><div class="fw-medium">[' + esc(gate.gate_id) + '] ' + esc(gate.label || gate.key) + '</div>' +
        '<div class="code">' + esc(gate.key || '') + '</div></div>' +
        tagHtml(chipLabel(gate.status), tone) +
      '</div>' +
      '<div class="row wrap gap-3 mb-2">' + cells + '</div>' +
      '<div class="gv-spark">' + spark + '</div>' +
      '<div class="note mt-2">' + esc(gate.summary || '') + '</div>' +
    '</div>';
  }

  function renderGateCards(payload) {
    var box = q('.gv-gates');
    if (!box) return;
    var gates = ['33', '38', '40'].map(function (id) { return payload.gates[id]; }).filter(Boolean);
    box.innerHTML = gates.length ? gates.map(renderGateCard).join('') : '<div class="note">無 gate payload</div>';
    applyTagTones(box);
  }

  // ═══ Live readiness checklist(port legacy renderReadiness;摘要行 + .tbl)═══
  function readinessValue(item) {
    var key = item && item.key ? String(item.key) : '';
    if (key.indexOf('fee_drop') >= 0 || key.indexOf('maker_like') >= 0) return window.ocPctVal(item.value);
    if (key.indexOf('avg_net') >= 0) return window.ocBps(item.value, true);
    if (key.indexOf('ratio') >= 0 || key.indexOf('rate') >= 0) return metricValue(item.value, '', 2);
    return metricValue(item.value, '', 0);
  }

  function renderReadiness(payload) {
    var box = q('.gv-readiness');
    if (!box) return;
    var readiness = payload && payload.readiness;
    var items = readiness && Array.isArray(readiness.items) ? readiness.items : [];
    if (!items.length) { box.innerHTML = '<div class="note">無 readiness checklist</div>'; return; }
    var rStatus = readiness.status || (readiness.ready ? 'ready' : 'not_ready');
    var head = '<div class="row-between wrap gap-2 mb-3">' +
      '<div><div class="fw-medium">Live readiness</div>' +
      '<div class="note">' + esc(String(readiness.passed || 0)) + '/' + esc(String(readiness.total || items.length)) +
      ' passed · unknown ' + esc(String(readiness.unknown || 0)) + '</div></div>' +
      tagHtml(chipLabel(rStatus), toneFor(rStatus)) +
      '<div class="code">[33] [38] [40]</div></div>';
    var rows = items.map(function (item) {
      var iStatus = item.status || (item.passed ? 'pass' : 'fail');
      return '<tr>' +
        '<td>[' + esc(item.gate || '') + '] ' + esc(item.label || item.key || '') +
          '<div class="note">' + esc(item.detail || '') + '</div></td>' +
        '<td>' + tagHtml(chipLabel(iStatus), toneFor(iStatus)) + '</td>' +
        '<td class="num">' + readinessValue(item) + ' / ' + esc(item.target || '') + '</td>' +
      '</tr>';
    }).join('');
    box.innerHTML = head +
      '<table class="tbl"><thead><tr><th>Gate</th><th>Status</th><th>Value / Target</th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table>';
    applyTagTones(box);
  }

  // ═══ 策略達標矩陣(port legacy renderStrategies + fallbackStrategyStatus)═══
  function fallbackStrategyStatus(payload) {
    var gate38 = payload && payload.gates && payload.gates['38'];
    var gate40 = payload && payload.gates && payload.gates['40'];
    var badCells = ((gate40 && gate40.current && gate40.current.bad_cells) || []);
    var byStrategy = {};
    badCells.forEach(function (cell) {
      var name = cell.strategy_name || '';
      if (!name) return;
      if (!byStrategy[name]) byStrategy[name] = [];
      byStrategy[name].push(cell);
    });
    return KNOWN_STRATEGIES.map(function (name) {
      var bad = byStrategy[name] || [];
      var status = 'unknown';
      var summary = 'strategy_status field not available from backend';
      if (bad.length) {
        status = 'crisis';
        summary = bad.length + ' active negative cell(s)';
      } else if (name === 'grid_trading' && gate38 && ['warn', 'fail'].indexOf(String(gate38.status)) >= 0) {
        status = gate38.status === 'fail' ? 'fail' : 'warn';
        summary = 'grid lifecycle gate ' + gate38.status;
      } else if (gate40 && gate40.status === 'pass') {
        status = 'pass';
        summary = 'no active 24h negative cell in current payload';
      }
      return { strategy_name: name, status: status, summary: summary, rows_24h: null, avg_net_24h_bps: null,
        win_rate_24h_pct: null, rows_window: null, avg_net_window_bps: null, bad_cells: bad };
    });
  }

  function renderStrategies(payload) {
    var hasStatus = Array.isArray(payload && payload.strategy_status) && payload.strategy_status.length;
    var rows = hasStatus ? payload.strategy_status : fallbackStrategyStatus(payload);
    var srcEl = q('.gv-strat-src');
    if (srcEl) srcEl.textContent = hasStatus ? 'source=strategy_status' : 'source=fallback_from_bad_cells';

    var crisis = rows.filter(function (r) { return String(r.status).toLowerCase() === 'crisis'; });
    var passing = rows.filter(function (r) { return String(r.status).toLowerCase() === 'pass'; });
    setKpi('gv-kpi-crisis', String(crisis.length), crisis.length ? 'bad' : 'good',
      crisis.length ? crisis.map(function (r) { return r.strategy_name; }).join(', ') : '無 crisis 策略');
    setKpi('gv-kpi-pass', String(passing.length) + '/' + String(rows.length || KNOWN_STRATEGIES.length),
      passing.length === rows.length ? 'good' : 'warn',
      rows.filter(function (r) { return String(r.status).toLowerCase() !== 'pass'; })
        .map(function (r) { return r.strategy_name + ':' + r.status; }).join(', ') || '全數達標');

    var body = q('.gv-strat-body');
    if (!body) return;
    var html = rows.map(function (row) {
      var bad = Array.isArray(row.bad_cells) ? row.bad_cells : [];
      // bad-cell 為 ocEsc 純字串脈絡:avg 走 ocBps(帶 U+2212),不掛色 span。
      var badHtml = bad.length
        ? '<div class="note">' + bad.map(function (c) {
            return esc((c.engine_mode || '') + ' ' + (c.symbol || '') + ' n=' + (c.rows || 0) + ' avg=' + window.ocBps(c.avg_net_bps));
          }).join('<br>') + '</div>'
        : '';
      // avg_net_*_bps 帶方向 → 態 class 掛 <td>(第二通道);win_rate_24h_pct already-percent → ocPctVal。
      var p24 = window.ocSignParts(row.avg_net_24h_bps);
      var pWin = window.ocSignParts(row.avg_net_window_bps);
      return '<tr>' +
        '<td class="fw-medium">' + esc(row.strategy_name || EMPTY) + '</td>' +
        '<td>' + tagHtml(chipLabel(row.status), toneFor(row.status)) + '</td>' +
        '<td class="num ' + p24.cls + '">' + window.ocBps(row.avg_net_24h_bps, true) + '</td>' +
        '<td class="num">' + metricValue(row.rows_24h, '', 0) + '</td>' +
        '<td class="num">' + window.ocPctVal(row.win_rate_24h_pct) + '</td>' +
        '<td class="num ' + pWin.cls + '">' + window.ocBps(row.avg_net_window_bps, true) +
          '<div class="note">n=' + metricValue(row.rows_window, '', 0) + '</div></td>' +
        '<td>' + esc(row.summary || '') + badHtml + '</td>' +
      '</tr>';
    }).join('');
    body.innerHTML = html || emptyRow('無策略達標資料');
    applyTagTones(body);
  }

  // ═══ 全局 healthcheck(port legacy healthToneFrom + loadSystemHealth 渲染)═══
  function healthToneFrom(h) {
    if (!h) return { status: 'UNKNOWN', tone: 'warn', reason: 'health API 無資料' };
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
    return { status: 'PASS', tone: 'good', reason: 'scores and gates pass' };
  }

  function renderHealth(h) {
    var state = healthToneFrom(h);
    setKpi('gv-kpi-health', state.status, state.tone, state.reason);
    var body = q('.gv-health-body');
    if (!body) return;
    if (!h) { body.innerHTML = '<div class="note">Healthcheck 無資料</div>'; return; }
    var scores = h.scores || {};
    var gates = h.gates || {};
    var html = '<div>' + tagHtml('HEALTH ' + state.status, state.tone) + '</div>';
    html += '<div class="row wrap gap-3 mt-3">';
    Object.keys(scores).forEach(function (key) {
      var n = Number(scores[key]);
      var cls = n >= 80 ? 't-pos' : n >= 50 ? 't-warn' : 't-neg';
      html += '<div class="col"><div class="silk">' + esc(key.replace(/_/g, ' ')) + '</div>' +
        '<div class="num fs-title ' + cls + '">' + esc(String(scores[key])) + '</div></div>';
    });
    html += '</div><div class="row wrap gap-2 mt-3">';
    Object.keys(gates).forEach(function (key) {
      var ok = String(gates[key]).toLowerCase() === 'passed' || String(gates[key]).toLowerCase() === 'true';
      html += tagHtml((ok ? 'PASS ' : 'FAIL ') + key.replace(/_gate_state|_state/g, '').replace(/_/g, ' '), ok ? 'good' : 'bad');
    });
    html += '</div>';
    body.innerHTML = html;
    applyTagTones(body);
  }

  // ═══ edge-gates payload 三態渲染 ═══
  function renderEdge(payload) {
    showError('');
    var readiness = payload.readiness || {};
    var ready = !!readiness.ready;
    setKpi('gv-kpi-readiness', ready ? 'READY' : 'NOT READY', ready ? 'good' : 'warn',
      String(readiness.passed || 0) + '/' + String(readiness.total || 0) + ' passed · unknown ' + String(readiness.unknown || 0));
    renderGateCards(payload);
    renderReadiness(payload);
    renderStrategies(payload);
    setUpdatedFrom(payload.generated_at);
  }

  function renderEdgeEmpty() {
    // 無真值(payload 無 gates)→ 一律 —/UNKNOWN,絕不假 pass/假 0(canon 7)。
    setKpi('gv-kpi-readiness', 'UNKNOWN', 'warn', 'edge gate API 無資料');
    setKpi('gv-kpi-crisis', EMPTY, 'warn', EMPTY);
    setKpi('gv-kpi-pass', EMPTY, 'warn', EMPTY);
    var g = q('.gv-gates'); if (g) g.innerHTML = '<div class="note">無 edge gate 趨勢資料</div>';
    var r = q('.gv-readiness'); if (r) r.innerHTML = '<div class="note">無 readiness checklist</div>';
    var b = q('.gv-strat-body'); if (b) b.innerHTML = emptyRow('無策略達標資料');
    setUpdated('無資料', 'warn');
  }

  function renderEdgeError(msg) {
    // error(ocApi 回 null)→ 顯錯不崩,保守標 warn/bad,絕不冒充 PASS(canon 7)。
    setKpi('gv-kpi-readiness', '錯誤', 'warn', msg);
    var g = q('.gv-gates'); if (g) g.innerHTML = '<div class="note t-warn">' + esc(msg) + '</div>';
    setUpdated('錯誤', 'bad');
    showError(msg);
  }

  // ═══ 資料抓取(per-view;復用 ocApi + 既有 GET 路由,∈ 5b 對齊 authoritative)═══
  // 用裸名 ocApi 而非 window.ocApi:①common.js 先於本檔載入,ocApi 為 global,裸引安全;
  //   ②5b 對齊 ratchet 的 wrapper 偵測器有 (?<![.\w]) 前瞻,裸名才被抽取驗證路由 ∈ authoritative。
  async function loadEdge() {
    var d = await ocApi('/api/v1/strategy/prelive/edge-gates?window_days=' + encodeURIComponent(windowDays));
    if (!built) return;                      // 已卸載/未建 → 不寫 DOM
    if (d == null) { renderEdgeError('封驗資料載入失敗(HTTP / 網路)'); return; }
    var payload = d.data;
    if (!payload || !payload.gates) { renderEdgeEmpty(); return; }
    renderEdge(payload);
  }

  async function loadHealth() {
    var d = await ocApi('/api/v1/system/health');
    if (!built) return;
    if (d == null) {
      setKpi('gv-kpi-health', '錯誤', 'warn', '健康檢查載入失敗(HTTP / 網路)');
      var body = q('.gv-health-body');
      if (body) body.innerHTML = '<div class="note t-warn">健康檢查載入失敗</div>';
      return;
    }
    renderHealth(d.data);                     // d.data 可能 null → renderHealth 顯無資料(不假 pass)
  }

  async function load() {
    if (!built || loading) return;
    loading = true;
    try {
      await Promise.allSettled([loadEdge(), loadHealth()]);
    } finally {
      loading = false;
    }
  }

  // ═══ 控件接線(視窗選擇 / 刷新;皆唯讀,無寫路徑)═══
  function wireControls() {
    var sel = q('.gv-window');
    if (sel) {
      sel.value = windowDays;
      sel.addEventListener('change', function () { windowDays = sel.value || '7'; load(); });
    }
    var btn = q('.gv-refresh');
    if (btn) btn.addEventListener('click', function () { load(); });
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
  function renderGatesView(hostEl) {
    if (hostEl) host = hostEl;
    if (!host || built) return;
    host.innerHTML = SKELETON;
    built = true;
    wireControls();
    setUpdated('loading…', 'warn');
  }
  // resume:view 顯示 → 立即拉一次真值(鏡像 iframe「顯示即刷新」)+ 啟輪詢。
  function resumeGatesView() {
    if (!built) return;
    load();
    startPolling();
  }
  // pause:view 隱藏 → 停輪詢/停後續抓取(freshness/safety:隱藏不得續打後端,
  // 鏡像 iframe openclaw-tab-visibility 暫停語義,非協商)。
  function pauseGatesView() {
    stopPolling();
  }

  // 註冊進殼可見的原生 view 表(router 以 v.iframe===false 查此;stable host / 唯一擴充點)。
  window.OC_NATIVE_VIEWS = window.OC_NATIVE_VIEWS || {};
  window.OC_NATIVE_VIEWS['gates'] = { render: renderGatesView, resume: resumeGatesView, pause: pauseGatesView };
  // 具名導出(task 契約:renderGatesView / pauseGatesView / resumeGatesView 可被引用)。
  window.renderGatesView = renderGatesView;
  window.resumeGatesView = resumeGatesView;
  window.pauseGatesView = pauseGatesView;
})();
