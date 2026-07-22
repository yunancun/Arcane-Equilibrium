/*
 * view-ai-cost.js — 玄衡原生 view「AI 狀態」成本面 companion(Phase 2 第 6 遷;拆檔)
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:tab-ai 遷移的**成本面拆檔**(檔案 <2000 硬性;主檔 view-ai.js 已承狀態/歷史/Phase3)。
 *   本檔不註冊 OC_NATIVE_VIEWS(非獨立 view),而註冊 window.OC_AI_COST = {render, load},
 *   由主檔 view-ai.js 於 render/loadAll 驅動(companion 缺席時主面照常降級)。**純唯讀,零寫路徑**。
 *   內容逐節守恆(對 legacy tab-ai 成本 4 節,零丟失):
 *     ③全供應商 AI 成本 Dashboard(今日/30 天/日預算/推理次數/平均/剩餘 6 KPI);
 *     ④自適應預算 Adaptive Budget(預算倍數/AI ROI/有效預算/調整原因);
 *     ⑤AI Cost ROI Monitor(7d spend / 7d paper PnL / cost-edge ratio / budget remaining + verdict + 日表);
 *     定價表 Pricing Table(collapsible;input/output $/1M + 刷新)。
 *   刻意變更(canon 守恆):legacy `.oc-card/.oc-metric`(ocInjectBaseCSS,殼不呼叫)不可用,
 *     改殼組件庫(.panel/.kpi/.tbl/.tag/.note);legacy `?? 0` fallback 升級為 null→EMPTY
 *     (canon 7 誠實:絕不假 cost / 假 0),對齊 learning/agents 遷移。
 * 主要函數:render(建成本面板骨架,冪等)、load(4 唯讀 GET 渲染)、
 *   loadCost / loadAdaptive / loadCostRoiMonitor / loadPricing。
 * 依賴(全復用):common.js ocApi;common-formatters.js ocEsc / ocBalance / ocNum / ocPct / OC_EMPTY;
 *   組件庫 shell-components.css + tokens.css(.silk/.num)+ oc-utilities.css(t-* / flex / 間距)。
 * 硬邊界(canon / LOOP §6):
 *   ① **零寫路徑**——成本面全唯讀:GET /paper/layer2/cost · /paper/ai-cost · /paper/layer2/cost/adaptive ·
 *      /paper/layer2/cost/pricing(皆 ∈ 5b 對齊 authoritative,與 legacy tab-ai 同端點)。
 *   ② canon 7 三態:loading=「—/Loading…」;無真值=「—」(絕不假 0.00 / 假 cost);
 *      error(ocApi 回 null)=顯錯不崩,保守標 warn/bad;ROI verdict 資料不足→中性,不假綠燈。
 *   ③ visibility 由主檔統籌(load 僅在主檔 loadAll 觸發,主檔 pause 時不再呼 load)。
 *   ④ ratchet 0/0/0:零裸 hex、零 inline 樣式屬性、零內聯樣式塊;tone 走 .style.setProperty scoped-var。
 * 誠實邊界:靜態只證 source/路徑;真渲染/三態/真 cost 值 = NEEDS-LINUX runtime + operator 視覺。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  var host = null;                 // 主檔 <section> 宿主(view-ai.js render 傳入)
  var built = false;               // 面板骨架是否已建(render 冪等)

  // ── 小工具(拆檔各自持最小副本;與主檔同構)──
  function root() { return host ? host.querySelector('.ai-cost-slot') : null; }
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
  function toneTextClass(tone) {
    if (tone === 'good') return 't-pos';
    if (tone === 'bad') return 't-neg';
    if (tone === 'warn') return 't-warn';
    if (tone === 'muted') return 't-muted';
    return '';
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
  function balance(v, dp) {
    return (typeof window.ocBalance === 'function' && v != null) ? window.ocBalance(v, dp != null ? dp : 4) : EMPTY;
  }
  function num2(v, dp) {
    return (typeof window.ocNum === 'function' && v != null) ? window.ocNum(v, dp != null ? dp : 2) : EMPTY;
  }
  // 取第一個非空值(保 0 為有效值);全空回 null(canon 7:交呼叫端顯 EMPTY,不假 0)。
  function pick() {
    for (var i = 0; i < arguments.length; i++) { if (arguments[i] != null) return arguments[i]; }
    return null;
  }

  // ═══ 成本面骨架(canon 7:首渲 loading 態「—」)═══
  var PANEL =
    // ═ 節③:全供應商 AI 成本 Dashboard ═
    '<div class="panel">' +
      '<div class="panel-t"><span class="zh">全供應商 AI 成本</span><span class="code">ALL-PROVIDER COST DASHBOARD</span></div>' +
      '<div class="note mb-2">彙總所有 AI 供應商的成本(不僅限於 Claude);系統嚴格「看 net 不看 gross」。</div>' +
      '<div class="kpis">' +
        '<div class="kpi c-today"><div class="silk">TODAY · 今日總成本</div><div class="v num">' + EMPTY + '</div></div>' +
        '<div class="kpi c-total"><div class="silk">30D · 30 天累計</div><div class="v num">' + EMPTY + '</div></div>' +
        '<div class="kpi c-budget"><div class="silk">DAILY CAP · 日預算上限</div><div class="v num">' + EMPTY + '</div></div>' +
        '<div class="kpi c-sessions"><div class="silk">SESSIONS · 今日推理次數</div><div class="v num">' + EMPTY + '</div></div>' +
        '<div class="kpi c-avg"><div class="silk">AVG · 平均成本/推理</div><div class="v num">' + EMPTY + '</div></div>' +
        '<div class="kpi c-remaining"><div class="silk">REMAINING · 預算剩餘</div><div class="v num">' + EMPTY + '</div></div>' +
      '</div>' +
    '</div>' +

    // ═ 節④:自適應預算 Adaptive Budget ═
    '<div class="panel">' +
      '<div class="panel-t"><span class="zh">自適應預算</span><span class="code">ADAPTIVE BUDGET</span></div>' +
      '<div class="note mb-2">自適應預算依 AI 投資回報率自動調整:賺錢時預算增加,虧損時縮減。AI ROI = AI 建議產生的淨利潤 / AI 成本;根原則 13:cost_edge_ratio ≥ 0.8 才建議持倉。</div>' +
      '<div class="kpis">' +
        '<div class="kpi ab-mult"><div class="silk">MULTIPLIER · 預算倍數</div><div class="v num">' + EMPTY + '</div><div class="d note">1.0 = 標準</div></div>' +
        '<div class="kpi ab-roi"><div class="silk">AI ROI · 投資回報率</div><div class="v num">' + EMPTY + '</div><div class="d note">收益 / AI 成本</div></div>' +
        '<div class="kpi ab-effective"><div class="silk">EFFECTIVE · 有效預算</div><div class="v num">' + EMPTY + '</div></div>' +
        '<div class="kpi ab-reason"><div class="silk">REASON · 調整原因</div><div class="v num fs-dense">' + EMPTY + '</div></div>' +
      '</div>' +
    '</div>' +

    // ═ 節⑤:AI Cost ROI Monitor ═
    '<div class="panel">' +
      '<div class="panel-t"><span class="zh">AI Cost ROI Monitor</span><span class="code">COST-EDGE RATIO · PAPER</span></div>' +
      '<div class="kpis">' +
        '<div class="kpi roi-spend"><div class="silk">7D AI SPEND</div><div class="v num">' + EMPTY + '</div><div class="d note roi-spend-sub">' + EMPTY + '</div></div>' +
        '<div class="kpi roi-pnl"><div class="silk">7D PAPER PNL</div><div class="v num">' + EMPTY + '</div><div class="d note">paper only</div></div>' +
        '<div class="kpi roi-ratio"><div class="silk">COST-EDGE RATIO</div><div class="v num">' + EMPTY + '</div><div class="d note roi-ratio-sub">min 3 data days</div></div>' +
        '<div class="kpi roi-remaining"><div class="silk">BUDGET REMAINING</div><div class="v num">' + EMPTY + '</div><div class="d note roi-remaining-sub">today</div></div>' +
      '</div>' +
      '<div class="row wrap gap-2 mt-2">' +
        '<span class="roi-verdict tag" data-tone="muted">checking…</span>' +
        '<span class="roi-basis note">paper_simulation_only</span>' +
      '</div>' +
      '<table class="tbl mt-3">' +
        '<thead><tr><th>Day</th><th>Cost</th><th>Tokens</th></tr></thead>' +
        '<tbody class="roi-daily-body"><tr><td colspan="3" class="note">Loading…</td></tr></tbody>' +
      '</table>' +
    '</div>' +

    // ═ 定價表 Pricing Table(collapsible)═
    '<div class="panel">' +
      '<div class="row-between wrap gap-2">' +
        '<div class="panel-t"><span class="zh">定價表</span><span class="code">PRICING TABLE</span></div>' +
        '<button type="button" class="tag pointer pricing-refresh" data-tone="muted">刷新 / Pricing</button>' +
      '</div>' +
      '<div class="note mb-2 pricing-status">定價刷新:載入中</div>' +
      '<div class="note mb-2">各 AI 模型的 input tokens(送模型文本)/ output tokens(模型回復)價差巨大:DeepSeek V4 Flash 明顯低於 Claude Opus。</div>' +
      '<details><summary class="note pointer">展開定價明細 / Expand pricing detail</summary>' +
        '<table class="tbl mt-2">' +
          '<thead><tr><th>模型</th><th>供應商</th><th>Input $/1M</th><th>Output $/1M</th></tr></thead>' +
          '<tbody class="pricing-body"><tr><td colspan="4" class="note">Loading…</td></tr></tbody>' +
        '</table>' +
      '</details>' +
    '</div>';

  // ═══ 值設定器 ═══
  function setKpi(cls, value, tone) {
    var v = q('.' + cls + ' .v');
    if (!v) return;
    var base = (v.className.indexOf('fs-dense') >= 0) ? 'v num fs-dense ' : 'v num ';
    v.className = (base + toneTextClass(tone)).trim();
    v.textContent = (value == null || value === '') ? EMPTY : String(value);
  }
  function setSub(cls, text) { var el = q('.' + cls); if (el) el.textContent = text; }
  function setBadge(cls, text, tone) {
    var el = q('.' + cls);
    if (!el) return;
    el.textContent = text;
    el.setAttribute('data-tone', tone || 'muted');
    el.style.setProperty('--tag-tone', toneVar(tone || 'muted'));
  }

  // ═══ 節③:成本 Dashboard(port legacy loadCost;/paper/layer2/cost fallback /paper/ai-cost)═══
  async function loadCost() {
    var d = await ocApi('/api/v1/paper/layer2/cost');
    if (!d || !d.data) d = await ocApi('/api/v1/paper/ai-cost');
    if (!built) return;
    if (!d || !d.data) { setKpi('c-today', '失敗 / Failed', 'bad'); return; }
    var c = d.data;
    // canon 7:全 null → EMPTY(升級 legacy `?? 0` fake 0);真 0 才顯 0。
    var todayCost = pick(c.today && c.today.total_usd, c.today_cost, c.cost_today);
    var totalCost = pick(c.cumulative && c.cumulative.total_usd, c.total_cost, c.cost_total, c.total_cost_30d);
    var budget = pick(c.budget && c.budget.daily_hard_cap_usd, c.daily_budget, c.budget_limit);
    var sessions = pick(c.today && c.today.session_count, c.sessions_today, c.session_count, c.cumulative && c.cumulative.total_sessions);
    setKpi('c-today', todayCost != null ? balance(todayCost, 4) : EMPTY);
    setKpi('c-total', totalCost != null ? balance(totalCost, 2) : EMPTY);
    setKpi('c-budget', budget != null ? balance(budget, 2) : EMPTY);
    setKpi('c-sessions', sessions != null ? sessions : EMPTY);
    var avg = pick(c.avg_cost_per_session, (sessions && todayCost != null && sessions > 0) ? todayCost / sessions : null);
    setKpi('c-avg', avg != null ? balance(avg, 4) : EMPTY);
    var remaining = pick(c.budget && c.budget.remaining_usd, (budget != null && todayCost != null) ? (budget - todayCost) : null);
    setKpi('c-remaining', remaining != null ? balance(remaining, 4) : EMPTY, remaining == null ? undefined : (remaining > 0 ? 'good' : 'bad'));
  }

  // ═══ 節④:自適應預算(port legacy loadAdaptive;/paper/layer2/cost/adaptive)═══
  async function loadAdaptive() {
    var d = await ocApi('/api/v1/paper/layer2/cost/adaptive');
    if (!built) return;
    if (!d || !d.data) { setKpi('ab-mult', '⚠', 'warn'); setKpi('ab-reason', '連線失敗 / Failed', 'warn'); return; }
    var a = d.data;
    var mult = pick(a.multiplier, a.budget_multiplier);
    setKpi('ab-mult', mult != null ? (num2(mult, 2) + 'x') : EMPTY);
    // FA-8:?? 空值合併確保 cost_edge_ratio=0 不被跳過;根原則 13 字段優先。
    var roi = pick(a.cost_edge_ratio, a.roi_7d, a.roi, a.ai_roi);
    if (roi != null) setKpi('ab-roi', num2(roi, 2) + 'x', roi >= 0.8 ? 'good' : 'bad');
    else setKpi('ab-roi', 'N/A(數據不足)', 'muted');
    var eff = pick(a.effective_budget, a.adjusted_budget);
    setKpi('ab-effective', eff != null ? balance(eff, 2) : EMPTY);
    setKpi('ab-reason', pick(a.reason, a.adjustment_reason) || EMPTY);
  }

  // ═══ 節⑤:ROI verdict(port legacy roiVerdict)═══
  function roiVerdict(ratio, dataDays) {
    if (dataDays < 3 || ratio == null) return { cls: 'muted', text: 'Insufficient ROI sample' };
    if (ratio < 0) return { cls: 'bad', text: 'AI cost has negative paper ROI' };
    if (ratio < 0.8) return { cls: 'warn', text: 'AI ROI below cost-edge target' };
    return { cls: 'good', text: 'AI ROI is above cost-edge target' };
  }
  function renderRoiDaily(gateway) {
    var body = q('.roi-daily-body');
    if (!body) return;
    var daily = (gateway && Array.isArray(gateway.daily)) ? gateway.daily.slice(-7).reverse() : [];
    if (!daily.length) { body.innerHTML = '<tr><td colspan="3" class="note">No gateway daily cost data</td></tr>'; return; }
    body.innerHTML = daily.map(function (day) {
      var label = pick(day.date, day.day, day.timestamp) || EMPTY;
      var dayCost = pick(day.totalCost, day.total_cost, day.cost);
      var tokens = pick(day.totalTokens, day.total_tokens);
      return '<tr><td class="mono fs-micro">' + esc(String(label)) + '</td>' +
        '<td class="num">' + (dayCost != null ? balance(dayCost, 4) : EMPTY) + '</td>' +
        '<td class="num">' + esc(tokens != null ? String(tokens) : EMPTY) + '</td></tr>';
    }).join('');
  }
  // ═══ 節⑤:Cost ROI Monitor(port legacy loadCostRoiMonitor;adaptive + cost + ai-cost)═══
  async function loadCostRoiMonitor() {
    var res = await Promise.allSettled([
      ocApi('/api/v1/paper/layer2/cost/adaptive'),
      ocApi('/api/v1/paper/layer2/cost'),
      ocApi('/api/v1/paper/ai-cost'),
    ]);
    if (!built) return;
    var adaptiveOk = res[0].status === 'fulfilled' && res[0].value && res[0].value.data;
    var costOk = res[1].status === 'fulfilled' && res[1].value && res[1].value.data;
    var adaptive = adaptiveOk ? res[0].value.data : {};
    var cost = costOk ? res[1].value.data : {};
    var gateway = (res[2].status === 'fulfilled' && res[2].value && res[2].value.data) ? res[2].value.data : {};

    if (!adaptiveOk) {
      // adaptive 端點不可用:誠實顯無 ROI 樣本(不假綠燈),仍嘗試顯 remaining 與日表。
      setKpi('roi-spend', EMPTY); setSub('roi-spend-sub', 'adaptive endpoint unavailable');
      setKpi('roi-pnl', EMPTY); setKpi('roi-ratio', 'N/A'); setSub('roi-ratio-sub', 'no backend ROI sample');
      var remA = costOk && cost.budget ? cost.budget.remaining_usd : null;
      setKpi('roi-remaining', remA != null ? balance(remA, 4) : EMPTY);
      setSub('roi-remaining-sub', (costOk && cost.budget && cost.budget.daily_hard_cap_usd != null) ? ('cap ' + balance(cost.budget.daily_hard_cap_usd, 2)) : 'budget unavailable');
      setBadge('roi-verdict', 'ROI data unavailable', 'muted');
      setSub('roi-basis', 'not evaluated without backend adaptive data');
      renderRoiDaily(gateway);
      return;
    }

    var spend = adaptive.ai_spend_7d_usd != null ? adaptive.ai_spend_7d_usd : null;
    var pnl = adaptive.paper_pnl_7d_usd != null ? adaptive.paper_pnl_7d_usd : null;
    var dataDays = adaptive.data_days != null ? adaptive.data_days : 0;
    var ratio = pick(adaptive.cost_edge_ratio, adaptive.roi_7d, adaptive.roi, adaptive.ai_roi);
    var remaining = (cost.budget && cost.budget.remaining_usd != null) ? cost.budget.remaining_usd : null;
    var hardCap = (cost.budget && cost.budget.daily_hard_cap_usd != null) ? cost.budget.daily_hard_cap_usd : null;
    var verdict = roiVerdict(ratio, dataDays);

    setKpi('roi-spend', spend != null ? balance(spend, 4) : EMPTY);
    setSub('roi-spend-sub', dataDays + ' data days');
    setKpi('roi-pnl', pnl != null ? balance(pnl, 4) : EMPTY, pnl == null ? undefined : (pnl >= 0 ? 'good' : 'bad'));
    setKpi('roi-ratio', ratio == null ? 'N/A' : (num2(ratio, 2) + 'x'), verdict.cls === 'good' ? 'good' : verdict.cls === 'bad' ? 'bad' : undefined);
    setSub('roi-ratio-sub', dataDays < 3 ? 'waiting for 3 days' : 'paper PnL / AI spend');
    setKpi('roi-remaining', remaining != null ? balance(remaining, 4) : EMPTY);
    setSub('roi-remaining-sub', hardCap != null ? ('cap ' + balance(hardCap, 2)) : 'budget unavailable');
    setBadge('roi-verdict', verdict.text, verdict.cls);
    setSub('roi-basis', pick(cost.roi_basis, gateway.source) || 'paper_simulation_only');
    renderRoiDaily(gateway);
  }

  // ═══ 定價表(port legacy loadPricing;/paper/layer2/cost/pricing)═══
  function mtokPrice(row, side) {
    if (!row || typeof row !== 'object') return null;
    var mtokKey = side + '_per_mtok', mKey = side + '_cost_per_1m', kKey = side + '_cost_per_1k';
    if (row[mtokKey] != null) return Number(row[mtokKey]) || 0;
    if (row[mKey] != null) return Number(row[mKey]) || 0;
    if (row[kKey] != null) return (Number(row[kKey]) || 0) * 1000;
    if (row[side] != null) return Number(row[side]) || 0;
    return null;
  }
  function renderPricingStatus(data) {
    var meta = (data && data.source_meta) || {};
    var status = (data && data.refresh_status) || 'unknown';
    var last = meta.last_refresh_date || EMPTY;
    var changed = meta.source_changed ? ' · 官方頁面有變化,需復核' : '';
    var reasons = ((data && data.refresh_reasons) || meta.refresh_reasons || []).join(',');
    setSub('pricing-status', '定價刷新:' + status + ' · last=' + last + (reasons ? (' · ' + reasons) : '') + changed);
  }
  async function loadPricing(forceRefresh) {
    var d = await ocApi('/api/v1/paper/layer2/cost/pricing' + (forceRefresh ? '?force_refresh=true' : ''));
    if (!built) return;
    var body = q('.pricing-body');
    if (!d || !d.data) { if (body) body.innerHTML = '<tr><td colspan="4" class="note t-warn">No pricing data</td></tr>'; return; }
    renderPricingStatus(d.data);
    var pricing = d.data.models || d.data;
    var rows = [];
    if (Array.isArray(pricing)) {
      pricing.forEach(function (p) {
        var inp = mtokPrice(p, 'input'), out = mtokPrice(p, 'output');
        rows.push('<tr><td>' + esc(pick(p.model, p.name, p.model_id) || EMPTY) + '</td><td>' + esc(p.provider || EMPTY) +
          '</td><td class="num">' + (inp != null ? ('$' + num2(inp, 3)) : EMPTY) + '</td><td class="num">' + (out != null ? ('$' + num2(out, 3)) : EMPTY) + '</td></tr>');
      });
    } else if (pricing && typeof pricing === 'object') {
      Object.keys(pricing).forEach(function (model) {
        var costs = pricing[model];
        var inp = mtokPrice(costs, 'input'), out = mtokPrice(costs, 'output');
        rows.push('<tr><td>' + esc(model) + '</td><td>' + EMPTY + '</td><td class="num">' + (inp != null ? ('$' + num2(inp, 3)) : EMPTY) +
          '</td><td class="num">' + (out != null ? ('$' + num2(out, 3)) : EMPTY) + '</td></tr>');
      });
    }
    if (body) body.innerHTML = rows.length ? rows.join('') : '<tr><td colspan="4" class="note">No pricing rows</td></tr>';
  }
  async function refreshPricing() {
    await loadPricing(true);
    if (typeof window.ocToast === 'function') window.ocToast('定價表已刷新 / Pricing refreshed', 'success');
  }

  // ═══ 主檔掛鉤:render(建骨架)+ load(4 GET 渲染)═══
  function render(hostEl) {
    if (hostEl) host = hostEl;
    var slot = root();
    if (!slot || built) return;
    slot.innerHTML = PANEL;
    built = true;
    applyTagTones(slot);
    var pr = q('.pricing-refresh');
    if (pr) pr.addEventListener('click', function () { refreshPricing(); });
  }
  async function load() {
    if (!built) return;
    await Promise.allSettled([loadCost(), loadAdaptive(), loadCostRoiMonitor(), loadPricing(false)]);
  }

  // 註冊 companion hook(主檔 view-ai.js 於 render/loadAll 驅動;非獨立 OC_NATIVE_VIEWS)。
  window.OC_AI_COST = { render: render, load: load };
})();
