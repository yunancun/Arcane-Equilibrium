/*
 * view-strategy.js — 玄衡原生 view「策略中心」(Phase 2 第 8 個 iframe→原生遷移;含寫)主檔
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:把 legacy `tab-strategy.html`(857L,iframe 後備)遷成玄衡殼內的**原生 view**,
 *   延續 gates/monitor/development/learning/agents/ai/phase4 所建 strangler-fig pattern。
 *   本 view **含 3 寫**(策略 create / pause·stop / delete);skin-only 只換渲染殼,
 *   **絕不新增寫路徑、絕不改端點/payload/confirm 流程**(寫走既有 Rust strategy-config authority)。
 *   殼 router 為穩定宿主,本檔提供 render/pause/resume 為唯一擴充點。
 *   **拆檔**(檔案 <2000 硬性;tab-strategy 內容多):本檔=主(狀態列 + 健康彙總 + 策略列表 + 建立表單
 *     + 3 寫 + 市场掃描 + 活跃交易對 + 编排器/引擎详情);觀測面拆出 `view-strategy-history.js`
 *     (掛 window.OC_STRATEGY_HISTORY,承 近期交易意圖 + 策略师变更歷史,全唯讀)。companion 缺席
 *     時本 view 誠實降級(該區顯提示,主面照常)。
 * 內容守恆(對 legacy tab-strategy,零丟失):承 ①编排器狀態列(regime/active·total/refresh)
 *   ②策略健康彙總 ③策略列表 Registered Strategies + 建立表單(create) + 卡動作(pause/stop/delete)
 *   ④市场掃描 Scanner Opportunities ⑤活跃交易對 Active Symbols ⑥编排器详情 ⑦指標/信號引擎详情;
 *   ⑧近期意圖 + ⑨策略师变更歷史在 companion。
 * 刻意變更(canon 守恆非逐像素,對齊前七遷 austere 版式):①legacy 裝飾 emoji 不遷;
 *   ②legacy ocInjectBaseCSS class(.oc-card · .oc-chip · .oc-strat 家族 · .oc-table · .oc-metric,殼不注入)不可用,
 *     改殼組件庫(.panel/.tag/.tbl/.note + oc-utilities t-* 色階);③legacy ocExplain 以 .note 內聯承載;
 *   ④legacy 迷你分布條(.sh-dist-bar 需 iframe 作用域 CSS)不遷,健康以 Active/Paused/Stopped 三 .tag
 *     計數 + 文字彙總承載(資訊守恆:計數為真值);⑤legacy 策略卡 grid 改垂直 .panel 列(austere);
 *   ⑥legacy 15s ocStartRefresh 改單輪 30s 且僅可見時運行(對齊前遷;隱藏續輪詢=freshness/safety 退步);
 *   ⑦legacy inline onclick 改事件委派 + data-* 屬性(IIFE 私有函數不掛 global)。
 * ★ 對 brief 的源碼校正(以源碼為準):brief 稱「3 寫=create/activate/deactivate」與源碼不符——
 *   源碼實測 3 寫 = createStrategy(POST /strategy/create)、strategyAction(POST /strategy/{name}/{action},
 *   action∈{pause,stop})、deleteStrategy(DELETE /strategy/{name});**openConfirmModal 前置的是 delete**
 *   (preset key "delete-strategy",源 L359),非 activate/deactivate。源無 activate/deactivate 端點。
 * 硬邊界(canon / LOOP §6):
 *   ① 寫走既有 Rust strategy-config authority——3 寫 preserve 既有端點 + body byte-parity,零新寫路徑。
 *   ② response-gated 成功,絕不 fake-success:ocApi/ocPost 契約=非-2xx/網路/timeout/CSRF 回 null,
 *      僅真 2xx 回 parsed JSON;成功 toast + 樂觀重載只在後端真成功才觸發。
 *   ③ delete 的 openConfirmModal("delete-strategy") 逐字保留(文案由 common-modals preset 供,不弱化);
 *      R61 fail-closed 硬化:confirm 不可用/reject → **不送 DELETE**(源無 try/catch,此為安全加固非弱化)。
 *   ④ canon 7 三態:loading=「Loading…」;無真值=「—」/空態提示(絕不假 0/假 Active/假成功);
 *      error(回 null)=顯錯不崩,保守 warn/bad。
 *   ⑤ visibility 語義:隱藏時 pause 停輪詢/停 fetch(鏡像 iframe openclaw-tab-visibility 暫停)。
 *   ⑥ ratchet 0/0/0:零裸 hex、零 inline 樣式屬性、零內聯樣式塊;動態 tone 走 .style.setProperty
 *      ('--tag-tone', …) scoped-var 正法。
 * 誠實邊界:靜態(node --check + ratchet + registry smoke)只證 source/路徑事實;
 *   **真渲染 / 三態 / 真值 / 3 寫真行為(真送達·真授權·真審計)/ confirm 真 DOM 閘 = NEEDS-LINUX runtime
 *   + operator 視覺**,不由本刀 attest。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  // ── 常量 ──
  var POLL_MS = 30000;             // 輪詢間隔(統一 30s loadAll;僅可見時運行,鏡像前遷)

  // ── 執行期狀態 ──
  var host = null;                 // 原生 <section> 宿主(shell 注入)
  var built = false;               // 骨架是否已建(render 冪等)
  var timer = null;                // 輪詢 interval id(null=停;pause 必清)
  var loading = false;             // loadAll 去重
  var visible = false;             // view 是否可見
  var _createSubmitting = false;   // 建策略防雙提交(port legacy isSubmitting)

  // ── 小工具(復用 window.ocEsc / OC_EMPTY;與 companion 同構,拆檔各持最小副本)──
  function q(sel) { return host ? host.querySelector(sel) : null; }
  function esc(s) { return (typeof window.ocEsc === 'function') ? window.ocEsc(s) : String(s == null ? '' : s); }
  var EMPTY = (typeof window.OC_EMPTY === 'string') ? window.OC_EMPTY : '—';
  function toast(msg, type) { if (typeof window.ocToast === 'function') window.ocToast(msg, type); }
  function timeShort(ts) { return (typeof window.ocTimeShort === 'function') ? window.ocTimeShort(ts) : (ts ? String(ts) : EMPTY); }

  // tone → tokens.css 語義色 var(給 .tag 的 scoped-var --tag-tone;未知/中性回 warn,canon 7 保守)。
  function toneVar(tone) {
    if (tone === 'good') return 'var(--pos)';
    if (tone === 'bad') return 'var(--neg)';
    if (tone === 'muted') return 'var(--text-muted)';
    if (tone === 'accent') return 'var(--accent)';
    if (tone === 'info') return 'var(--accent)';
    return 'var(--warn)';
  }
  function applyTagTones(root_) {
    if (!root_) return;
    var tags = root_.querySelectorAll('.tag[data-tone]');
    for (var i = 0; i < tags.length; i++) {
      tags[i].style.setProperty('--tag-tone', toneVar(tags[i].getAttribute('data-tone')));
    }
  }
  function tagHtml(text, tone) {
    return '<span class="tag" data-tone="' + esc(tone || 'muted') + '">' + esc(text) + '</span>';
  }
  // 設 badge/文字(canon 7:無值 → EMPTY;真計數 0 仍顯 "0",非假零)。
  function setBadge(cls, text, tone) {
    var el = q('.' + cls);
    if (!el) return;
    el.textContent = text;
    el.setAttribute('data-tone', tone || 'muted');
    el.style.setProperty('--tag-tone', toneVar(tone || 'muted'));
  }
  function setText(cls, v) {
    var el = q('.' + cls);
    if (!el) return;
    el.textContent = (v == null || v === '') ? EMPTY : String(v);
  }

  // companion 掛鉤(view-strategy-history.js 註冊)。
  function historyApi() { return window.OC_STRATEGY_HISTORY || null; }

  // ═══ 策略中文名 + label(port legacy STRAT_CN/stratLabel)═══
  var STRAT_CN = {
    'MA_Crossover': '均線交叉',
    'BB_Reversion': '布林回歸',
    'FundingRate_Arb': '資金費率套利',
    'Grid_Trading': '網格交易',
    'BB_Breakout': '布林突破',
    'RSI_Divergence': 'RSI 背离',
    'MACD_Trend': 'MACD 趋势',
    'Volume_Spike': '量價突破'
  };
  function stratLabel(name) {
    if (typeof window.ocStrategyLabel === 'function') {
      var shared = window.ocStrategyLabel(name);
      if (shared) return shared;
    }
    var base = Object.keys(STRAT_CN).find(function (k) { return name === k || name.indexOf(k + '_') === 0; });
    var cn = base ? STRAT_CN[base] : null;
    return cn ? name + ' / ' + cn : name;
  }

  // ═══ V2 参數渲染(port legacy stratV2Params;返回 HTML 片段,無值回 '')═══
  function stratV2Params(s) {
    var strat = s.strategy || s.name || '';
    var sharedKey = (typeof window.ocStrategyKey === 'function') ? window.ocStrategyKey(strat) : '';
    var base = sharedKey || Object.keys(STRAT_CN).find(function (k) { return strat === k || strat.indexOf(k + '_') === 0; }) || strat;
    var rows = [];
    var bps = (typeof window.ocBps === 'function') ? window.ocBps : function (v) { return String(v); };
    var money = (typeof window.ocMoney === 'function') ? window.ocMoney : function (v) { return String(v); };
    if (base === 'ma_crossover' || base === 'MA_Crossover') {
      if (s.adx_threshold != null) rows.push('ADX&gt;' + s.adx_threshold);
      if (s.use_kama) rows.push('KAMA ✓');
      if (s.multi_tf_confirm) rows.push('Multi-TF ✓');
      if (s.min_confidence != null) rows.push('MinConf=' + s.min_confidence);
    } else if (base === 'bb_reversion' || base === 'BB_Reversion') {
      if (s.rsi_threshold != null) rows.push('RSI&lt;' + s.rsi_threshold);
      if (s.rsi_short_threshold != null) rows.push('RSI&gt;' + s.rsi_short_threshold);
      if (s.regime_aware) rows.push('Regime ✓');
      if (s.use_limit_orders != null) rows.push(s.use_limit_orders ? 'Limit ✓' : 'Market');
    } else if (base === 'funding_arb' || base === 'FundingRate_Arb') {
      // funding_threshold 為 fraction ×10000 轉 bps;total_fee_bps 已是 bps。皆走 ocBps。
      if (s.funding_threshold != null) rows.push('FundThr=' + bps(s.funding_threshold * 10000));
      if (s.total_fee_bps != null) rows.push('TotalFee=' + bps(s.total_fee_bps));
      if (s.delta_neutral) rows.push('ΔNeutral ✓');
      if (s.cost_summary && s.cost_summary.net_funding_pnl != null) rows.push('NetPnL=' + money(s.cost_summary.net_funding_pnl, 4));
    } else if (base === 'grid_trading' || base === 'Grid_Trading' || base === 'grid') {
      if (s.upper_price != null) rows.push('U=' + s.upper_price);
      if (s.lower_price != null) rows.push('L=' + s.lower_price);
      if (s.grid_count != null) rows.push('N=' + s.grid_count);
      if (s.grid_step != null) rows.push('Step=' + s.grid_step);
    } else if (base === 'bb_breakout' || base === 'BB_Breakout') {
      if (s.min_confidence != null) rows.push('MinConf=' + s.min_confidence);
      if (s.use_volume_filter) rows.push('VolFlt ✓');
      if (s.use_donchian) rows.push('Donchian ✓');
    }
    if (!rows.length) return '';
    return '<div class="fs-micro t-dim mt-1">' + rows.join(' · ') + '</div>';
  }

  // ═══ 骨架(canon 7:首渲即 loading 態,絕不假值)═══
  var SKELETON =
    '<div class="p-4">' +

      // ═ 節①:编排器狀態列 ═
      '<div class="panel">' +
        '<div class="row-between wrap gap-3">' +
          '<div>' +
            '<div class="panel-t"><span class="zh">策略编排器</span><span class="code">STRATEGY ORCHESTRATOR</span></div>' +
            '<div class="note">策略中心管理所有交易策略。AI Agent 自主決定啟動哪些策略(上限 100 個),人類只通過手動開關硬關閉。编排器根據市场状态协調所有策略運行。</div>' +
          '</div>' +
          '<div class="row wrap gap-2">' +
            '<span class="st-regime tag" data-tone="muted">—</span>' +
            '<span class="fs-dense t-dim">Active <strong class="st-active">' + EMPTY + '</strong> / Total <strong class="st-total">' + EMPTY + '</strong> (上限 100)</span>' +
            '<button type="button" class="st-refresh tag pointer" data-tone="muted">刷新 / Refresh</button>' +
          '</div>' +
        '</div>' +
      '</div>' +

      // ═ 節②:策略健康彙總 ═
      '<div class="panel">' +
        '<div class="row wrap gap-2">' +
          '<span class="fs-dense t-dim fw-semi">策略分布 / Health:</span>' +
          '<span class="st-sh-active tag" data-tone="muted">Active ' + EMPTY + '</span>' +
          '<span class="st-sh-paused tag" data-tone="muted">Paused ' + EMPTY + '</span>' +
          '<span class="st-sh-stopped tag" data-tone="muted">Stopped ' + EMPTY + '</span>' +
          '<span class="st-sh-summary fs-micro t-dim"></span>' +
        '</div>' +
      '</div>' +

      // ═ 節③:策略列表 + 建立表單 ═
      '<div class="panel">' +
        '<div class="row-between wrap gap-2">' +
          '<div class="panel-t"><span class="zh">策略列表</span><span class="code">REGISTERED STRATEGIES</span></div>' +
          '<button type="button" class="st-create-toggle tag pointer" data-tone="accent">建立策略 / Create</button>' +
        '</div>' +
        '<div class="st-create-form hidden panel mt-2">' +
          '<div class="fs-dense fw-semi mb-2">新建策略 / Create New Strategy</div>' +
          '<div class="row wrap gap-2">' +
            '<div><label class="fs-micro t-dim block">Type / 類型</label>' +
              '<select class="st-new-type oc-select">' +
                '<option value="ma_crossover">MA Crossover / 均線交叉</option>' +
                '<option value="bb_reversion">BB Reversion / 布林回歸</option>' +
                '<option value="funding_arb">Funding Arb / 資金費率套利</option>' +
                '<option value="grid">Grid / 網格交易</option>' +
                '<option value="bb_breakout">BB Breakout / 布林突破</option>' +
              '</select></div>' +
            '<div><label class="fs-micro t-dim block">Symbol / 币種</label>' +
              '<input class="st-new-symbol oc-input mono" value="BTCUSDT" /></div>' +
            '<div><label class="fs-micro t-dim block">Qty/Trade</label>' +
              '<input class="st-new-qty oc-input oc-input--num mono" type="number" value="0.001" step="0.001" /></div>' +
            '<button type="button" class="st-create-btn tag pointer" data-tone="good">Create</button>' +
            '<button type="button" class="st-create-cancel tag pointer" data-tone="muted">Cancel</button>' +
          '</div>' +
        '</div>' +
        '<div class="st-grid mt-3"><div class="note">Loading strategies…</div></div>' +
      '</div>' +

      // ═ 節④⑤:市场掃描 + 活跃交易對 ═
      '<div class="row wrap gap-3">' +
        '<div class="panel flex-1">' +
          '<div class="panel-t"><span class="zh">市场掃描</span><span class="code">SCANNER OPPORTUNITIES</span></div>' +
          '<div class="note mb-2">掃描器每 5 分鐘分析 650+ 交易對,自動發現交易機會並部署策略。</div>' +
          '<table class="tbl">' +
            '<thead><tr><th>Symbol</th><th>Type</th><th>Score</th><th>Reason</th></tr></thead>' +
            '<tbody class="st-scanner-body"><tr><td colspan="4" class="note">Loading…</td></tr></tbody>' +
          '</table>' +
        '</div>' +
        '<div class="panel flex-1">' +
          '<div class="panel-t"><span class="zh">活跃交易對</span><span class="code">ACTIVE SYMBOLS</span></div>' +
          '<div class="note mb-1">Rust ScannerRunner 管理的活跃交易對(固定 + 動態掃描)。</div>' +
          '<div class="st-deployed-meta fs-micro t-dim mb-2"></div>' +
          '<table class="tbl">' +
            '<thead><tr><th>Symbol</th><th>Type</th><th>Strategies</th><th>State</th></tr></thead>' +
            '<tbody class="st-deployed-body"><tr><td colspan="4" class="note">Loading…</td></tr></tbody>' +
          '</table>' +
        '</div>' +
      '</div>' +

      // ═ 節⑥:编排器详情(默認收合)═
      '<details class="panel">' +
        '<summary class="fw-semi pointer">编排器详情 / Orchestrator Details</summary>' +
        '<div class="st-orch-details mt-2"><div class="note">Loading…</div></div>' +
      '</details>' +

      // ═ 節⑦:指標 & 信號引擎(默認收合)═
      '<details class="panel">' +
        '<summary class="fw-semi pointer">指標 &amp; 信號引擎 / Indicator &amp; Signal Engine</summary>' +
        '<div class="st-engine-details mt-2"><div class="note">Loading…</div></div>' +
      '</details>' +

      // ═ 觀測面 companion 掛載槽(view-strategy-history.js;缺席顯降級提示)═
      '<div class="strategy-history-slot"><div class="panel note t-muted">觀測面模組載入中… / Observability module loading…</div></div>' +
    '</div>';

  // ═══ 值渲染小工具 ═══
  function metricTable(fields) {
    var rows = fields.filter(function (f) { return f[1] != null; });
    if (!rows.length) return '<div class="note">無详情 / No details</div>';
    return '<table class="tbl"><tbody>' + rows.map(function (f) {
      return '<tr><td class="t-muted">' + esc(f[0]) + '</td><td class="num t-right">' + esc(String(f[1])) + '</td></tr>';
    }).join('') + '</tbody></table>';
  }

  // ═══ 節③:策略列表(port legacy loadStrategies;/strategy/list)═══
  function renderStrategyCard(s) {
    var state = s.state || 'unknown';
    var tone = state === 'active' ? 'good' : state === 'stopped' ? 'bad' : state === 'paused' ? 'warn' : 'muted';
    var stratName = s.strategy || s.name || s.strategy_name || '?';
    var sid = s.strategy_id || 0;
    var nameAttr = esc(stratName);
    var html = '<div class="panel">';
    html += '<div class="row-between wrap gap-2">';
    html += '<div class="row wrap gap-2">';
    html += '<span class="fs-micro t-dim mono">#' + sid + '</span>';
    html += '<span class="fw-semi">' + esc(stratLabel(stratName)) + '</span>';
    html += '</div>';
    html += tagHtml(state, tone);
    html += '</div>';
    var meta = [];
    if (s.symbol) meta.push('Symbol: ' + esc(s.symbol));
    if (s.qty_per_trade != null) meta.push('Qty/Trade: ' + s.qty_per_trade);
    if (s.trade_count != null) meta.push('Trades: ' + s.trade_count);
    if (s.current_position) meta.push('Pos: ' + esc(s.current_position));
    if (s.cooldown_ms != null) meta.push('CD: ' + (s.cooldown_ms / 1000) + 's');
    if (meta.length) html += '<div class="note mt-1">' + meta.join(' · ') + '</div>';
    html += stratV2Params(s);
    // 動作:pause(非 active 禁)/stop(已 stopped 禁)/delete。native disabled → 禁態不 emit click。
    html += '<div class="row wrap gap-2 mt-2">';
    html += '<button type="button" class="tag pointer" data-tone="warn" data-st-action="pause" data-st-name="' + nameAttr + '"' + (state !== 'active' ? ' disabled' : '') + '>暫停 / Pause</button>';
    html += '<button type="button" class="tag pointer" data-tone="bad" data-st-action="stop" data-st-name="' + nameAttr + '"' + (state === 'stopped' ? ' disabled' : '') + '>停止 / Stop</button>';
    html += '<button type="button" class="tag pointer" data-tone="bad" data-st-action="delete" data-st-name="' + nameAttr + '" title="永久删除(不可撤銷)">刪除 / Delete</button>';
    html += '</div>';
    html += '</div>';
    return html;
  }
  async function loadStrategies() {
    var d;
    try { d = await ocApi('/api/v1/strategy/list'); } catch (e) { d = null; }
    if (!built) return;
    var grid = q('.st-grid');
    if (!d || !d.data) {
      if (grid) grid.innerHTML = '<div class="note t-warn">無法載入策略 / Failed to load strategies</div>';
      return;
    }
    var strategies = d.data.strategies || [];
    var active = strategies.filter(function (s) { return s.state === 'active'; }).length;
    var paused = strategies.filter(function (s) { return s.state === 'paused'; }).length;
    var stopped = strategies.filter(function (s) { return s.state === 'stopped' || s.state === 'error'; }).length;
    var total = strategies.length;
    // 計數為真值(0 也顯 "0",非假零);active/total 隨後可被 loadOrchestrator 覆蓋(更權威)。
    setText('st-active', active);
    setText('st-total', total);
    setBadge('st-sh-active', 'Active ' + active, active > 0 ? 'good' : 'muted');
    setBadge('st-sh-paused', 'Paused ' + paused, paused > 0 ? 'warn' : 'muted');
    setBadge('st-sh-stopped', 'Stopped ' + stopped, stopped > 0 ? 'bad' : 'muted');
    setText('st-sh-summary', total ? (active + '/' + total + ' running') : EMPTY);
    if (!grid) return;
    if (!strategies.length) {
      grid.innerHTML = '<div class="note">没有注册的策略 / No registered strategies</div>';
      return;
    }
    grid.innerHTML = strategies.map(renderStrategyCard).join('');
    applyTagTones(grid);
  }

  // ═══ 節⑥⑦:编排器详情 + 引擎详情(port legacy loadOrchestrator/renderEngineDetails;/strategy/status)═══
  async function loadOrchestrator() {
    var d;
    try { d = await ocApi('/api/v1/strategy/status'); } catch (e) { d = null; }
    if (!built) return;
    if (!d || !d.data) {
      setBadge('st-regime', '無法載入', 'bad');
      var od = q('.st-orch-details');
      if (od) od.innerHTML = '<div class="note t-warn">無法載入 / Load failed</div>';
      return;
    }
    var orch = d.data;
    // regime badge 來自 signal_engine 的 Regime_Detector 規則輸出(canon 7:無數據 → muted,不假 Active)。
    var sigStats = (orch.signal_engine_status || {}).stats || {};
    var sigBySrc = sigStats.signals_by_source || {};
    var hasRegime = (sigBySrc['Regime_Detector'] || 0) > 0;
    setBadge('st-regime', hasRegime ? 'Regime Active' : 'No Regime Data', hasRegime ? 'info' : 'muted');
    // active/total 以编排器狀態覆蓋(比 list 過濾更權威)。
    if (orch.active_count != null) setText('st-active', orch.active_count);
    if (orch.total_registered != null) setText('st-total', orch.total_registered);
    // 详情(欄位路徑對齊實際 API 響應)。
    var stats = orch.stats || {};
    var klMgr = orch.kline_manager_status || {};
    var klStats = klMgr.stats || {};
    var sigEngine = orch.signal_engine_status || {};
    var fields = [
      ['Pipeline Active', orch.active_count > 0 ? 'Yes' : 'No'],
      ['Active Strategies', orch.active_count],
      ['Total Registered', orch.total_registered],
      ['Signals Dispatched', stats.signals_dispatched],
      ['Intents Collected', stats.intents_collected],
      ['Strategies Activated', stats.strategies_activated],
      ['Ticks Processed', klStats.total_ticks_processed],
      ['Klines Closed', klStats.total_klines_closed],
      ['Symbols Tracked', (klMgr.symbols || []).length || null],
      ['Timeframes', (klMgr.timeframes || []).join(', ') || null],
      ['Last Tick', klStats.last_tick_ts_ms ? timeShort(klStats.last_tick_ts_ms) : null],
      ['Signal Rules', sigEngine.rule_count],
      ['Signal History', sigEngine.history_size]
    ];
    var od2 = q('.st-orch-details');
    if (od2) od2.innerHTML = metricTable(fields);
    renderEngineDetails(orch);
  }
  function renderEngineDetails(orch) {
    var box = q('.st-engine-details');
    if (!box) return;
    var indEng = orch.indicator_engine_status || {};
    var sigEng = orch.signal_engine_status || {};
    var sigStats = sigEng.stats || {};
    var sigBySrc = sigStats.signals_by_source || {};
    var sigByDir = sigStats.signals_by_direction || {};
    var indStats = indEng.stats || {};
    var html = '<div class="row wrap gap-4">';
    // 指標引擎
    html += '<div class="flex-1">';
    html += '<div class="fs-dense fw-semi mb-2">指標引擎 / Indicator Engine</div>';
    html += '<div class="note mb-1">共 ' + (indEng.indicator_count || 0) + ' 個指標</div>';
    html += '<div class="note mb-2">Computations: ' + (indStats.total_computations || 0) + ' · Errors: ' + (indStats.computation_errors || 0) + ' · Cache Hits: ' + (indStats.cache_hits || 0) + '</div>';
    var indicators = indEng.indicators_registered || [];
    if (indicators.length) {
      html += '<div class="row wrap gap-1">';
      indicators.forEach(function (ind) { html += tagHtml(ind, 'muted'); });
      html += '</div>';
    }
    html += '</div>';
    // 信號引擎
    html += '<div class="flex-1">';
    html += '<div class="fs-dense fw-semi mb-2">信號引擎 / Signal Engine</div>';
    html += '<div class="note mb-1">共 ' + (sigEng.rule_count || 0) + ' 條規則 · ' + (sigEng.history_size || 0) + ' 條歷史</div>';
    html += '<div class="note mb-1">Evals: ' + (sigStats.total_evaluations || 0) + ' · Generated: ' + (sigStats.signals_generated || 0) + ' · Errors: ' + (sigStats.rule_errors || 0) + '</div>';
    if (Object.keys(sigByDir).length) {
      html += '<div class="row wrap gap-1 mb-2">';
      ['long', 'short', 'close_long', 'close_short', 'neutral'].forEach(function (dir) {
        if (sigByDir[dir] != null) {
          var t = dir === 'long' ? 'good' : dir === 'short' ? 'bad' : dir.indexOf('close') === 0 ? 'warn' : 'muted';
          html += tagHtml(dir + ':' + sigByDir[dir], t);
        }
      });
      html += '</div>';
    }
    if (Object.keys(sigBySrc).length) {
      html += '<div class="row wrap gap-1">';
      Object.keys(sigBySrc).sort(function (a, b) { return sigBySrc[b] - sigBySrc[a]; }).forEach(function (src) {
        html += tagHtml(src + ':' + sigBySrc[src], 'info');
      });
      html += '</div>';
    }
    html += '</div>';
    html += '</div>';
    box.innerHTML = html;
    applyTagTones(box);
  }

  // ═══ 節④:市场掃描(port legacy loadScanner;/strategy/scanner/opportunities)═══
  async function loadScanner() {
    var d = await ocApi('/api/v1/strategy/scanner/opportunities');
    if (!built) return;
    var body = q('.st-scanner-body');
    if (!body) return;
    if (!d || !d.data) { body.innerHTML = '<tr><td colspan="4" class="note t-warn">掃描器未運行 / Scanner not running</td></tr>'; return; }
    var opps = d.data.opportunities || d.data || [];
    if (!opps.length) { body.innerHTML = '<tr><td colspan="4" class="note">暂無機會 / No opportunities</td></tr>'; return; }
    var numFn = (typeof window.ocNum === 'function') ? window.ocNum : function (v) { return String(v); };
    body.innerHTML = opps.slice(0, 20).map(function (o) {
      return '<tr>' +
        '<td><strong>' + esc(o.symbol) + '</strong></td>' +
        '<td>' + esc(o.strategy_type || o.type || EMPTY) + '</td>' +
        '<td class="num">' + numFn(o.score, 2) + '</td>' +
        '<td class="fs-micro t-dim">' + esc(o.reason || EMPTY) + '</td>' +
      '</tr>';
    }).join('');
  }

  // ═══ 節⑤:活跃交易對(port legacy loadDeployed;/strategy/scanner/deployed)═══
  async function loadDeployed() {
    var d = await ocApi('/api/v1/strategy/scanner/deployed');
    if (!built) return;
    var body = q('.st-deployed-body');
    var meta = q('.st-deployed-meta');
    var emptyRow = '<tr><td colspan="4" class="note">No active symbols</td></tr>';
    if (!body) return;
    if (!d || !d.data) { body.innerHTML = emptyRow; return; }
    var deployed = d.data.deployed || [];
    var src = d.data.source || 'unknown';
    var cnt = d.data.symbol_count != null ? d.data.symbol_count : deployed.length;
    if (meta) {
      var srcLabel = src === 'rust_scanner' ? 'Rust ScannerRunner' : (src === 'python_deployer' ? 'Python Deployer (legacy)' : src);
      meta.textContent = srcLabel + ' · ' + cnt + ' symbol(s) active';
    }
    if (!deployed.length) { body.innerHTML = emptyRow; return; }
    body.innerHTML = deployed.map(function (dd) {
      var kind = dd.kind || '';
      var kindTone = kind === 'pinned' ? 'warn' : 'muted';
      // Rust scanner 每 symbol 跑全 4 策略;legacy deployer 顯具體策略名。
      var stratTxt = src === 'rust_scanner' ? 'MA · BB · Grid · BBBreakout' : esc(dd.strategy_name || dd.name || EMPTY);
      var stTone = dd.state === 'active' ? 'good' : 'muted';
      return '<tr>' +
        '<td><strong>' + esc(dd.symbol) + '</strong></td>' +
        '<td>' + tagHtml(kind || EMPTY, kindTone) + '</td>' +
        '<td class="fs-micro t-dim">' + stratTxt + '</td>' +
        '<td>' + tagHtml(dd.state || 'active', stTone) + '</td>' +
      '</tr>';
    }).join('');
    applyTagTones(body);
  }

  // ═══════════════════════════════════════════════════════════════════
  // 3 寫(byte-parity;response-gated;走既有 Rust strategy-config authority)
  // ═══════════════════════════════════════════════════════════════════
  function toggleCreateForm() {
    var f = q('.st-create-form');
    if (f) f.classList.toggle('hidden');
  }

  // ═══ 寫①:建立策略(POST /api/v1/strategy/create;body byte-parity;response-gated)═══
  // ★ 反 fake-success:ocPost 失敗回 null → 顯 'Create failed' 不假成功;僅真 2xx 才 toast + 重載。
  async function createStrategy() {
    if (_createSubmitting) return;
    _createSubmitting = true;
    var btn = q('.st-create-btn');
    var origText = btn ? btn.textContent : null;
    if (btn) { btn.setAttribute('aria-disabled', 'true'); btn.textContent = '建立中...'; }
    try {
      var typeEl = q('.st-new-type'), symEl = q('.st-new-symbol'), qtyEl = q('.st-new-qty');
      // body 構造與源 L339-343 逐值 byte-parity:strategy_type / symbol(.trim().toUpperCase()) / qty_per_trade(parseFloat || 0.001)。
      var body = {
        strategy_type: typeEl ? typeEl.value : '',
        symbol: symEl ? symEl.value.trim().toUpperCase() : '',
        qty_per_trade: (qtyEl ? parseFloat(qtyEl.value) : NaN) || 0.001
      };
      var d = await ocPost('/api/v1/strategy/create', body);
      if (d) {
        toast('Strategy created: ' + (d.data ? d.data.strategy : ''), 'success');
        toggleCreateForm();
        loadStrategies();
      } else {
        toast('Create failed', 'error');
      }
    } finally {
      _createSubmitting = false;
      if (btn) { btn.removeAttribute('aria-disabled'); btn.textContent = origText; }
    }
  }

  // ═══ 寫②:策略動作 pause/stop(POST /api/v1/strategy/{name}/{action};byte-parity;response-gated)═══
  async function strategyAction(name, action) {
    var d = await ocPost('/api/v1/strategy/' + encodeURIComponent(name) + '/' + action);
    if (d) {
      toast(name + ' → ' + action + ' OK', 'success');
      loadStrategies();
    } else {
      toast(action + ' failed for ' + name, 'error');
    }
  }

  // ═══ 寫③:刪除策略(DELETE /api/v1/strategy/{name};openConfirmModal("delete-strategy") 前置)═══
  // ★ confirm byte-parity:preset key "delete-strategy" 逐字保留(title/body/confirmLabel 由 common-modals
  //   _OC_CONFIRM_ACTIONS 供,不弱化);R61 fail-closed 硬化:confirm 不可用 / reject(modal 鎖) → **不送 DELETE**
  //   (源 L359 無 try/catch,rejected promise 會 throw;此加固=安全增強,非弱化)。cancel 靜默 return(對齊源)。
  // ★ 反 fake-success:ocApi 失敗回 null → 顯 'Delete failed' 不假成功。
  async function deleteStrategy(name) {
    var confirmFn = window.openConfirmModal;
    if (typeof confirmFn !== 'function') {
      toast('確認對話框不可用,已取消刪除 / Confirm unavailable, delete cancelled', 'error');
      return;
    }
    var proceed = false;
    try {
      proceed = await confirmFn('delete-strategy');
    } catch (err) {
      toast('開啟確認對話框失敗 / Open confirm dialog failed', 'error');
      return;
    }
    if (!proceed) return;
    var d = await ocApi('/api/v1/strategy/' + encodeURIComponent(name), { method: 'DELETE' });
    if (d) {
      toast(name + ' deleted', 'success');
      loadStrategies();
    } else {
      toast('Delete failed', 'error');
    }
  }

  // ═══ 全節載入(4 主 GET + companion load;Promise.allSettled)═══
  async function loadAll() {
    if (!built || loading) return;
    loading = true;
    try {
      var hist = historyApi();
      var tasks = [loadStrategies(), loadOrchestrator(), loadScanner(), loadDeployed()];
      if (hist && typeof hist.load === 'function') tasks.push(Promise.resolve(hist.load()));
      await Promise.allSettled(tasks);
    } finally {
      loading = false;
    }
  }

  // ═══ 控件接線(事件委派:刷新 / 建表切換 / 建立 / 卡動作;禁態 native disabled 不 emit click)═══
  function wireControls() {
    if (!host) return;
    host.addEventListener('click', function (ev) {
      var t = ev.target;
      var btn = (t && typeof t.closest === 'function')
        ? t.closest('button.st-refresh, button.st-create-toggle, button.st-create-cancel, button.st-create-btn, button[data-st-action]')
        : null;
      if (!btn) return;
      if (btn.classList.contains('st-refresh')) { loadAll(); return; }
      if (btn.classList.contains('st-create-toggle') || btn.classList.contains('st-create-cancel')) { toggleCreateForm(); return; }
      if (btn.classList.contains('st-create-btn')) { createStrategy(); return; }
      var action = btn.getAttribute('data-st-action');
      var name = btn.getAttribute('data-st-name');
      if (!action || name == null) return;
      if (action === 'delete') deleteStrategy(name);
      else strategyAction(name, action);
    });
  }

  // ═══ 輪詢生命週期(僅可見時運行;pause 必清)═══
  function startPolling() { stopPolling(); timer = setInterval(loadAll, POLL_MS); }
  function stopPolling() { if (timer) { clearInterval(timer); timer = null; } }

  // ═══ shell router 契約:render / resume / pause ═══
  function renderStrategyView(hostEl) {
    if (hostEl) host = hostEl;
    if (!host || built) return;
    host.innerHTML = SKELETON;
    built = true;
    wireControls();
    // 掛觀測面 companion(缺席則保留骨架降級提示,主面照常)。
    var hist = historyApi();
    if (hist && typeof hist.render === 'function') {
      try { hist.render(host); }
      catch (e) { console.warn('[view-strategy] history companion render 失敗:', e); }
    } else {
      var slot = q('.strategy-history-slot');
      if (slot) slot.innerHTML = '<div class="panel note t-warn">觀測面模組未載入;主面不受影響 / observability module not loaded.</div>';
    }
    applyTagTones(host);   // 骨架內 .tag(badge / 按鈕)首次上色
  }
  function resumeStrategyView() {
    if (!built) return;
    visible = true;
    loadAll();
    startPolling();
  }
  function pauseStrategyView() {
    visible = false;
    stopPolling();
  }

  // 註冊進殼可見的原生 view 表(router 以 v.iframe===false 查此)。
  window.OC_NATIVE_VIEWS = window.OC_NATIVE_VIEWS || {};
  window.OC_NATIVE_VIEWS['strategy'] = { render: renderStrategyView, resume: resumeStrategyView, pause: pauseStrategyView };
  // 具名導出。
  window.renderStrategyView = renderStrategyView;
  window.resumeStrategyView = resumeStrategyView;
  window.pauseStrategyView = pauseStrategyView;
})();
