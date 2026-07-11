/*
 * view-ai.js — 玄衡原生 view「AI 狀態」(Phase 2 第 6 個 iframe→原生遷移;含寫 + typed-confirm)主檔
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:把 legacy `tab-ai.html`(1489L,iframe 後備)遷成玄衡殼內的**原生 view**,
 *   延續 gates(首遷)/monitor(二遷)/development(三遷)/learning(四遷/首含寫)/agents(五遷)
 *   所建的 strangler-fig pattern(design/10 recipe §1)。**本 view 是 Phase 2 第 6 遷,含寫 +
 *   typed-confirm**:除唯讀 Layer2 advisory-mesh 儀表盤外,還承載多項既有 layer2 寫端點——
 *   原生 view **preserve 呼叫(同端點、同 payload),絕不新增寫路徑、絕不改端點/payload**。
 *   殼 router 為穩定宿主,本檔提供 render/pause/resume 為唯一新增擴充點(second-adapter)。
 *   **拆檔**(檔案 <800 硬性;tab-ai 內容極多):本檔=主(狀態列 + 諮詢/推理歷史 + Phase3 儀表盤
 *   假設實驗/Kelly/策略進化 + trigger 寫 + evolution/run 寫 + 骨架宿主 + 生命週期);成本面拆出
 *   `view-ai-cost.js`(掛 window.OC_AI_COST);供應商 + 引擎設置面拆出 `view-ai-providers.js`
 *   (掛 window.OC_AI_PROVIDERS,承 3 config/DELETE 寫 + typed-confirm)。三檔各 <800,companion
 *   缺席時本 view 誠實降級(該面顯提示,主面照常)。
 *   內容逐節守恆(對 legacy tab-ai,零丟失):本檔承 legacy 之
 *     ①AI 推理引擎狀態列(badge + Trigger Session + Refresh);⑨諮詢狀態(enabled/running/queries/last);
 *     ⑩AI 推理歷史(sessions 表);⑫假設實驗狀態(active/confirmed/refuted/expired);
 *     ⑬Kelly 資本配置(策略數/平均 Kelly%/總樣本 + 表);⑭策略參數進化(累計次數/組合上限 + 手動觸發表)。
 *   成本 4 節(③④⑤定價)在 view-ai-cost.js;供應商 + 引擎設置 2 節在 view-ai-providers.js。
 *   刻意變更(canon 守恆非逐像素):
 *     ①legacy 裝飾 emoji(🤖⚡💰🧪📊…)不遷(canon 1 非數據 chrome 從簡,對齊前五遷 austere 版式);
 *     ②legacy `.oc-card`/`.oc-metric`/`.oc-chip`/`.oc-table`(ocInjectBaseCSS 運行時注入樣式,殼不呼叫)
 *       不可用,改以殼組件庫(.panel/.kpi/.tag/.tbl/.note + oc-utilities t-* 色階)重渲;
 *     ③legacy ocExplain(short/deep 展開)以殼原生 .note 內聯承載(資訊守恆,版式改玄衡);
 *     ④legacy 進化引擎「狀態色點」(頁內 style + JS 設 background)改以 .tag 狀態 pill 承載
 *       (資訊守恆:last_run_ts 非空=已執行 → good,空=尚未執行 → muted,不可達=bad;免 inline);
 *     ⑤legacy 每塊獨立 30/60/120s 輪詢改為單輪 30s 且僅可見時運行(對齊 agents 遷移;
 *       隱藏續輪詢=freshness/safety 退步);⑥legacy `occurrencychange` 監聽(拼錯的無效事件,dead)
 *       + ocInitFx/ocStartRefresh(iframe-era chrome)不遷。
 * 主要函數:renderAiView(建骨架,冪等;掛 2 companion)、resumeAiView(顯示→拉真值+啟輪詢)、
 *   pauseAiView(隱藏→停輪詢/停 fetch)、loadAll(5 主 GET + 2 companion load)、
 *   loadConsult / loadSessions / loadExperiments / loadEvolution / loadKelly、
 *   doTriggerSession(POST paper/layer2/trigger)、runEvolution(POST evolution/run)。
 * 依賴(全復用,不重造):common.js ocApi / ocPost / ocFetch / ocToast;common-modals.js
 *   openConfirmModal(trigger 確認);common-formatters.js ocEsc / ocBalance / ocNum / ocPct / ocQty /
 *   ocTimeShort / OC_EMPTY;組件庫 shell-components.css(.panel/.panel-t/.kpi/.tbl/.tag/.note/.logblock)
 *   + tokens.css(.silk/.num)+ oc-utilities.css(flex/間距/t-* 色階/.hidden/.mono/.pointer)。
 * 硬邊界(canon / LOOP §6):
 *   ① 寫面走既有 Rust/API authority——本檔 2 寫 preserve 既有端點,payload byte-parity:
 *      · POST /api/v1/paper/layer2/trigger(payload {reason:'manual_gui_trigger'};trigger 前經
 *        openConfirmModal 成本預估確認,鏡像 legacy trigger-confirm 單擊確認,不弱化);
 *      · POST /api/v1/evolution/run(payload {strategy_name,symbol,timeframe,parameter_grids,min_sharpe};
 *        server-side 強制 Operator 角色 403 gate)。**絕不新增寫路徑、絕不改端點/payload**。
 *      (另 3 config/DELETE 寫 + typed-confirm CLEAR 在 view-ai-providers.js。)
 *   ② **response-gated 成功,絕不 fake-success**:ocApi/ocPost 契約(common.js:225-279)=任何
 *      非-2xx / 網路 / timeout / CSRF 失敗回 **null**,僅真 2xx 回 parsed JSON。故成功 toast +
 *      樂觀重載**只在後端真成功回應才觸發**;失敗顯錯不冒充成功。絕不在回應前假成功。
 *   ③ canon 7 三態:loading=骨架「—/Loading…」;無真值=「—」/空節提示(**絕不假 provider 狀態 /
 *      假 cost / 假 0 / 假成功**;legacy `?? 0` fallback 升級為 null→EMPTY,對齊 learning/agents 誠實);
 *      error(ocApi 回 null)=顯錯不崩,保守標 warn/bad。
 *   ④ visibility 語義(非協商):隱藏時 pauseAiView 停輪詢/停後端抓取(鏡像 iframe
 *      openclaw-tab-visibility 暫停),否則隱藏續打後端=freshness/safety 退步。
 *   ⑤ ratchet 0/0/0:零裸 hex、零 inline 樣式屬性、零內聯樣式塊;動態 tone 走
 *      .style.setProperty('--tag-tone', var(...)) scoped-var 正法(非樣式屬性字面)。
 * 誠實邊界:靜態(node --check + ratchet + 5b 對齊 + registry/asset smoke)只證 source/路徑事實;
 *   **真渲染正確性 / 三態版式 / 真值 / 2 寫真行為(真送達後端·真授權·真審計)= NEEDS-LINUX runtime
 *   + operator 視覺**,不由本刀 attest。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  // ── 常量 ──
  var POLL_MS = 30000;             // 輪詢間隔(統一 30s loadAll;鏡像 agents 遷移;僅可見時運行。
                                   //   刻意簡化 legacy 每塊獨立 30/60/120s → 單輪 30s,只在可見時打後端,誠實)

  // ── 執行期狀態 ──
  var host = null;                 // 原生 <section> 宿主(shell 注入)
  var built = false;               // 骨架是否已建(render 冪等)
  var timer = null;                // 輪詢 interval id(null=停;pause 必清)
  var loading = false;             // loadAll 去重(不重入整輪刷新)
  var visible = false;             // view 是否可見(resume=true / pause=false;守 visibility 語義)

  // ── 小工具(復用 window.ocEsc / OC_EMPTY;tone/tag 與 companion 同構,拆檔各自持最小副本)──
  function q(sel) { return host ? host.querySelector(sel) : null; }
  function esc(s) { return (typeof window.ocEsc === 'function') ? window.ocEsc(s) : String(s == null ? '' : s); }
  var EMPTY = (typeof window.OC_EMPTY === 'string') ? window.OC_EMPTY : '—';
  function shortId(v) { return esc(String(v == null ? '' : v).slice(0, 8)); }

  // tone → tokens.css 語義色 var(給 .tag 的 scoped-var --tag-tone)。
  // 未知/中性一律 warn 調(canon 7:不確定 → 保守標注,絕不綠燈)。
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
    if (tone === 'accent') return 't-accent';
    return '';
  }

  // 產出 .tag pill 的 HTML(帶 data-tone;真正 tone 由 applyTagTones 以 scoped-var 上色,
  // 避免 innerHTML 內寫死 style=/hex —— ratchet 正法)。
  function tagHtml(text, tone) {
    return '<span class="tag" data-tone="' + esc(tone || 'muted') + '">' + esc(text) + '</span>';
  }
  function applyTagTones(root) {
    if (!root) return;
    var tags = root.querySelectorAll('.tag[data-tone]');
    for (var i = 0; i < tags.length; i++) {
      tags[i].style.setProperty('--tag-tone', toneVar(tags[i].getAttribute('data-tone')));
    }
  }
  function paint() { applyTagTones(host); }

  // 成本/餘額格(ocBalance;無值回 EMPTY,canon 7 禁假 0)。
  function balance(v, dp) {
    return (typeof window.ocBalance === 'function' && v != null) ? window.ocBalance(v, dp != null ? dp : 4) : EMPTY;
  }
  function num2(v, dp) {
    return (typeof window.ocNum === 'function' && v != null) ? window.ocNum(v, dp != null ? dp : 2) : EMPTY;
  }
  function timeShort(ts) {
    if (typeof window.ocTimeShort === 'function') return window.ocTimeShort(ts);
    return ts ? String(ts) : EMPTY;
  }
  // 取第一個非空值(保 0 為有效值);全空回 null(canon 7:交由呼叫端顯 EMPTY,不假 0)。
  function pick() {
    for (var i = 0; i < arguments.length; i++) { if (arguments[i] != null) return arguments[i]; }
    return null;
  }

  // ═══ companion 掛鉤(view-ai-cost.js / view-ai-providers.js 註冊)═══
  function aiCost() { return window.OC_AI_COST || null; }
  function aiProviders() { return window.OC_AI_PROVIDERS || null; }

  // ═══ 骨架(canon 7:首渲即 loading 態「—/Loading…」,絕不假值)═══
  var SKELETON =
    '<div class="p-4">' +

      // ═ 節①:AI 推理引擎狀態列(header + Trigger + Refresh)═
      '<div class="panel">' +
        '<div class="row-between wrap gap-3">' +
          '<div>' +
            '<div class="panel-t"><span class="zh">AI 推理引擎</span><span class="code">LAYER 2 AI ENGINE</span></div>' +
            '<div class="note">Layer 2 三層架構:L0(確定性規則,零成本)→ L1(輕量模型快速篩選)→ L2(高級模型深度分析)。多供應商 advisory,每次查詢產生 API 費用;所有 AI 建議須經 Decision Lease + 本地檢查,非即時命令(唯讀儀表盤 + 既有 layer2 寫,不繞交易/風控/live 授權)。</div>' +
          '</div>' +
          '<div class="row wrap gap-2">' +
            '<span class="ai-badge tag" data-tone="muted">checking…</span>' +
            '<button type="button" class="tag pointer ai-trigger" data-tone="accent">Trigger Session</button>' +
            '<button type="button" class="tag pointer ai-refresh" data-tone="muted">刷新 / Refresh</button>' +
            '<span class="ai-updated tag" data-tone="muted">loading…</span>' +
          '</div>' +
        '</div>' +
        '<div class="ai-error panel note t-warn hidden"></div>' +
      '</div>' +

      // ═ 成本面(companion view-ai-cost.js 填充;缺席顯降級提示)═
      '<div class="ai-cost-slot"><div class="panel note t-muted">AI 成本面模組載入中… / AI cost module loading…</div></div>' +

      // ═ 供應商 + 引擎設置面(companion view-ai-providers.js 填充;缺席顯降級提示)═
      '<div class="ai-providers-slot"><div class="panel note t-muted">AI 供應商/設置面模組載入中… / AI providers module loading…</div></div>' +

      // ═ 節⑨:諮詢狀態 Consultation Status ═
      '<div class="panel">' +
        '<div class="panel-t"><span class="zh">諮詢狀態</span><span class="code">CONSULTATION STATUS</span></div>' +
        '<div class="kpis">' +
          '<div class="kpi cs-enabled"><div class="silk">ENABLED · 已啟用</div><div class="v num">' + EMPTY + '</div></div>' +
          '<div class="kpi cs-running"><div class="silk">RUNNING · 運行中</div><div class="v num">' + EMPTY + '</div></div>' +
          '<div class="kpi cs-queries"><div class="silk">TOTAL QUERIES · 總查詢</div><div class="v num">' + EMPTY + '</div></div>' +
          '<div class="kpi cs-last"><div class="silk">LAST QUERY · 最後查詢</div><div class="v num fs-dense">' + EMPTY + '</div></div>' +
        '</div>' +
      '</div>' +

      // ═ 節⑩:AI 推理歷史 Inference History ═
      '<div class="panel">' +
        '<div class="panel-t"><span class="zh">AI 推理歷史</span><span class="code">AI INFERENCE HISTORY</span></div>' +
        '<table class="tbl">' +
          '<thead><tr><th>ID</th><th>Time</th><th>Trigger</th><th>Symbol</th><th>Status</th><th>Cost</th><th>Result</th></tr></thead>' +
          '<tbody class="ai-sessions-body"><tr><td colspan="7" class="note">Loading…</td></tr></tbody>' +
        '</table>' +
      '</div>' +

      // ═ 節⑫:假設實驗狀態 Experiment Status ═
      '<div class="panel">' +
        '<div class="row-between wrap gap-2">' +
          '<div class="panel-t"><span class="zh">假設實驗狀態</span><span class="code">EXPERIMENT STATUS</span></div>' +
          '<span class="exp-badge tag" data-tone="muted">載入中</span>' +
        '</div>' +
        '<div class="kpis">' +
          '<div class="kpi exp-active"><div class="silk">ACTIVE · 活躍假設</div><div class="v num">' + EMPTY + '</div><div class="d note">pending + running</div></div>' +
          '<div class="kpi exp-confirmed"><div class="silk">CONFIRMED · 已確認</div><div class="v num">' + EMPTY + '</div></div>' +
          '<div class="kpi exp-refuted"><div class="silk">REFUTED · 已反駁</div><div class="v num">' + EMPTY + '</div></div>' +
          '<div class="kpi exp-expired"><div class="silk">EXPIRED · 已過期</div><div class="v num">' + EMPTY + '</div></div>' +
        '</div>' +
      '</div>' +

      // ═ 節⑬:Kelly 資本配置 Kelly Capital Allocation ═
      '<div class="panel">' +
        '<div class="panel-t"><span class="zh">Kelly 資本配置</span><span class="code">KELLY CAPITAL ALLOCATION</span></div>' +
        '<div class="kpis">' +
          '<div class="kpi kelly-count"><div class="silk">STRATEGIES · 策略數</div><div class="v num">' + EMPTY + '</div></div>' +
          '<div class="kpi kelly-avg"><div class="silk">AVG KELLY% · 平均</div><div class="v num">' + EMPTY + '</div></div>' +
          '<div class="kpi kelly-samples"><div class="silk">TOTAL SAMPLES · 總樣本</div><div class="v num">' + EMPTY + '</div></div>' +
        '</div>' +
        '<table class="tbl mt-3">' +
          '<thead><tr><th>策略 / Strategy</th><th>Kelly%</th><th>建議 Qty</th><th>勝率</th><th>樣本</th><th>層級</th></tr></thead>' +
          '<tbody class="kelly-body"><tr><td colspan="6" class="note">Loading…</td></tr></tbody>' +
        '</table>' +
      '</div>' +

      // ═ 節⑭:策略參數進化 Strategy Evolution(含 evolution/run 寫)═
      '<div class="panel">' +
        '<div class="row-between wrap gap-2">' +
          '<div class="panel-t"><span class="zh">策略參數進化</span><span class="code">STRATEGY EVOLUTION</span></div>' +
          '<span class="evo-state tag" data-tone="muted">—</span>' +
        '</div>' +
        '<div class="kpis">' +
          '<div class="kpi evo-runs"><div class="silk">TOTAL RUNS · 累計進化</div><div class="v num">' + EMPTY + '</div></div>' +
          '<div class="kpi evo-combos"><div class="silk">MAX COMBOS · 組合上限</div><div class="v num">' + EMPTY + '</div></div>' +
        '</div>' +
        '<div class="note mt-2 mb-2">自動排程:每週日 UTC 00:30 · Operator 認證後可手動觸發(server-side 強制 Operator 角色 403 gate)。</div>' +
        '<div class="row wrap gap-2">' +
          '<input type="text" class="evo-strategy mono" placeholder="策略名 (e.g. ma_crossover)" />' +
          '<input type="text" class="evo-symbol mono" placeholder="Symbol (e.g. BTCUSDT)" value="BTCUSDT" />' +
          '<button type="button" class="tag pointer evo-run" data-tone="accent">執行進化</button>' +
        '</div>' +
        '<div class="evo-result note mt-2"></div>' +
      '</div>' +
    '</div>';

  // ═══ 值設定器(canon 7:無真值 → EMPTY,絕不假 0)═══
  function setKpi(cls, value, tone) {
    var v = q('.' + cls + ' .v');
    if (!v) return;
    var base = (v.className.indexOf('fs-dense') >= 0) ? 'v num fs-dense ' : 'v num ';
    v.className = (base + toneTextClass(tone)).trim();
    v.textContent = (value == null || value === '') ? EMPTY : String(value);
  }
  function setBadge(cls, text, tone) {
    var el = q('.' + cls);
    if (!el) return;
    el.textContent = text;
    el.setAttribute('data-tone', tone || 'muted');
    el.style.setProperty('--tag-tone', toneVar(tone || 'muted'));
  }
  function stampUpdated(ok) {
    if (!ok) { setBadge('ai-updated', '拉取失敗', 'bad'); return; }
    var t = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    setBadge('ai-updated', '更新 ' + t, 'good');
  }
  function showError(msg) {
    var el = q('.ai-error');
    if (!el) return;
    if (msg) { el.textContent = msg; el.classList.remove('hidden'); }
    else { el.textContent = ''; el.classList.add('hidden'); }
  }

  // ═══ 節⑨:諮詢狀態(port legacy loadConsult;/strategy/ai/status)═══
  async function loadConsult() {
    var d = await ocApi('/api/v1/strategy/ai/status');
    if (!built) return;
    if (!d || !d.data) {
      setBadge('ai-badge', 'API 失敗 / Failed', 'bad');
      setKpi('cs-enabled', EMPTY, 'warn');
      return;
    }
    var s = d.data;
    setKpi('cs-enabled', s.enabled ? '是' : '否', s.enabled ? 'good' : 'muted');
    setKpi('cs-running', (s.running || s.is_running) ? '是' : '否');
    setKpi('cs-queries', pick(s.total_queries, s.query_count));
    setKpi('cs-last', s.last_query_at ? timeShort(s.last_query_at) : EMPTY);
    if (s.enabled) setBadge('ai-badge', '已啟用', 'good');
    else setBadge('ai-badge', '已禁用', 'muted');
  }

  // ═══ 節⑩:AI 推理歷史(port legacy loadSessions;/paper/layer2/sessions?limit=20)═══
  function sessionTone(st) { return st === 'completed' ? 'good' : st === 'failed' ? 'bad' : 'muted'; }
  async function loadSessions() {
    var d = await ocApi('/api/v1/paper/layer2/sessions?limit=20');
    if (!built) return;
    var body = q('.ai-sessions-body');
    if (!body) return;
    if (!d || !d.data) { body.innerHTML = '<tr><td colspan="7" class="note t-warn">連線失敗 / Connection failed</td></tr>'; return; }
    var sessions = d.data.sessions || (Array.isArray(d.data) ? d.data : []) || [];
    if (!sessions.length) { body.innerHTML = '<tr><td colspan="7" class="note">暫無 AI 推理記錄 / No sessions</td></tr>'; return; }
    body.innerHTML = sessions.slice(0, 20).map(function (s) {
      return '<tr>' +
        '<td class="mono fs-micro">' + shortId(pick(s.session_id, s.id)) + '</td>' +
        '<td class="mono fs-micro t-muted">' + esc(timeShort(pick(s.created_at, s.timestamp))) + '</td>' +
        '<td>' + esc(pick(s.trigger, s.reason) || EMPTY) + '</td>' +
        '<td>' + esc(s.symbol || EMPTY) + '</td>' +
        '<td>' + tagHtml(pick(s.status, s.state) || EMPTY, sessionTone(s.status)) + '</td>' +
        '<td class="num">' + (s.cost != null ? balance(s.cost, 4) : EMPTY) + '</td>' +
        '<td class="fs-micro clip">' + esc(pick(s.result, s.recommendation) || EMPTY) + '</td>' +
      '</tr>';
    }).join('');
    applyTagTones(body);
  }

  // ═══ 節⑫:假設實驗狀態(port legacy refreshExperimentStatus;/experiments/status)═══
  async function loadExperiments() {
    var d = await ocApi('/api/v1/experiments/status');
    if (!built) return;
    // 註:此端點回頂層計數(非 {data:{}} 封套),legacy 直接讀 d.pending 等。
    if (!d) {
      setBadge('exp-badge', '錯誤', 'bad');
      return;
    }
    var active = (d.pending != null ? d.pending : 0) + (d.running != null ? d.running : 0);
    setKpi('exp-active', active);
    setKpi('exp-confirmed', d.confirmed != null ? d.confirmed : EMPTY, 'good');
    setKpi('exp-refuted', d.refuted != null ? d.refuted : EMPTY, 'bad');
    setKpi('exp-expired', d.expired != null ? d.expired : EMPTY, 'muted');
    setBadge('exp-badge', '共 ' + (d.total != null ? d.total : 0) + ' 個', 'good');
  }

  // ═══ 節⑬:Kelly 資本配置(port legacy refreshKellyData;/strategy/kelly-recommendations)═══
  function kellyTierTone(t) { return t === 'normal' ? 'good' : t === 'moderate' ? 'accent' : 'muted'; }
  async function loadKelly() {
    var body = q('.kelly-body');
    var r;
    try { r = await ocFetch('/api/v1/strategy/kelly-recommendations'); }
    catch (e) { if (body) body.innerHTML = '<tr><td colspan="6" class="note t-warn">連線失敗 / Load failed</td></tr>'; return; }
    if (!r || !r.ok) { if (body) body.innerHTML = '<tr><td colspan="6" class="note t-warn">無法載入 / Load failed</td></tr>'; return; }
    var data = await r.json();
    if (!built) return;
    var strategies = (data && data.strategies) || {};
    var keys = Object.keys(strategies);
    setKpi('kelly-count', keys.length);
    var totalFrac = 0, totalSamples = 0;
    keys.forEach(function (k) {
      totalFrac += (strategies[k].kelly_fraction || 0);
      totalSamples += (strategies[k].sample_size || 0);
    });
    // kelly_fraction 為 fraction(0-1),平均後 ×100 → ocPct(2dp);無數據回 EMPTY。
    setKpi('kelly-avg', keys.length > 0 ? (typeof window.ocPct === 'function' ? window.ocPct(totalFrac / keys.length) : num2(totalFrac / keys.length)) : EMPTY);
    setKpi('kelly-samples', totalSamples);
    if (!body) return;
    if (!keys.length) { body.innerHTML = '<tr><td colspan="6" class="note">無策略數據 / No strategy data</td></tr>'; return; }
    body.innerHTML = keys.map(function (k) {
      var s = strategies[k];
      // kelly_fraction / win_rate 皆 fraction(0-1,顯示 ×100)→ ocPct;recommended_qty 為 base-asset 量 → ocQty(6dp)。
      var pctFn = (typeof window.ocPct === 'function') ? window.ocPct : function (v) { return num2(v); };
      var qtyFn = (typeof window.ocQty === 'function') ? window.ocQty : function (v) { return num2(v, 6); };
      return '<tr>' +
        '<td>' + esc(k) + '</td>' +
        '<td class="num">' + esc(pctFn(s.kelly_fraction)) + '</td>' +
        '<td class="num">' + esc(qtyFn(s.recommended_qty)) + '</td>' +
        '<td class="num">' + esc(pctFn(s.win_rate)) + '</td>' +
        '<td class="num">' + esc(s.sample_size == null ? EMPTY : s.sample_size) + '</td>' +
        '<td>' + tagHtml(s.kelly_tier || EMPTY, kellyTierTone(s.kelly_tier)) + '</td>' +
      '</tr>';
    }).join('');
    applyTagTones(body);
  }

  // ═══ 節⑭:策略進化狀態(port legacy refreshEvolutionStatus;/evolution/status)═══
  async function loadEvolution() {
    var d = await ocApi('/api/v1/evolution/status');
    if (!built) return;
    if (!d) { setBadge('evo-state', '狀態不可用', 'bad'); return; }
    setKpi('evo-runs', d.total_runs != null ? d.total_runs : EMPTY);
    setKpi('evo-combos', d.max_combinations != null ? d.max_combinations : EMPTY);
    // last_run_ts 非空 → 已執行(good);空 → 尚未執行(muted)。承 legacy 狀態點語義,改 .tag pill。
    if (d.last_run_ts != null) {
      var when = new Date(d.last_run_ts * 1000).toLocaleString('zh-CN', { hour12: false });
      setBadge('evo-state', '已執行 · ' + when, 'good');
    } else {
      setBadge('evo-state', '尚未執行', 'muted');
    }
  }

  // ═══ 寫①:Trigger Session(POST /paper/layer2/trigger;openConfirmModal 成本預估確認)═══
  // ★ 反 fake-success(硬邊界②):ocPost 失敗回 null → 顯錯不假成功;僅真 2xx 才 toast 成功 + 重載。
  // 確認流程 port legacy trigger-confirm(單擊確認 + 成本預估),用既有 common-modals openConfirmModal
  //   承載(殼不載 legacy 頁內 .confirm-overlay 樣式塊);不弱化——money-spending POST 前必經確認 gate。
  async function doTriggerSession() {
    var confirmFn = window.openConfirmModal;
    // fail-closed(硬邊界/survival-first,E2 R61 LOW-2):確認 gate 不可用時**不**觸發 money-spending POST,
    //   對齊 clear-key 的 fail-closed posture(勿因 modal 缺席而繞過成本確認)。
    if (typeof confirmFn !== 'function') {
      ocToast('確認對話框不可用,已取消觸發 / Confirm unavailable, trigger cancelled', 'error');
      return;
    }
    var proceed = false;
    {
      try {
        proceed = await confirmFn({
          title: '觸發 AI 推理 / Trigger L2 Inference',
          body: '即將觸發一次 AI 深度分析。\nAI 會分析當前市場狀況、持倉情況和歷史表現,然後給出交易建議。\n\n預估成本 / Estimated cost:\n  默認模型 (Sonnet): ~$0.02 - $0.08\n  如升級到 Opus: ~$0.10 - $0.50\n  如使用 Haiku: ~$0.002 - $0.01\n  如使用 DeepSeek: ~$0.001 - $0.005\n實際成本取決於分析復雜度和 token 用量。',
          confirmLabel: '確認觸發 / Confirm',
          confirmClass: 'oc-btn-danger'
        });
      } catch (err) {
        ocToast('開啟確認對話框失敗 / Open confirm dialog failed', 'error');
        return;
      }
    }
    if (!proceed) { ocToast('已取消觸發 / Trigger cancelled', 'neutral'); return; }
    var d = await ocPost('/api/v1/paper/layer2/trigger', { reason: 'manual_gui_trigger' });
    if (d) { ocToast('AI 推理已觸發', 'success'); loadSessions(); }
    else ocToast('觸發失敗 / Trigger failed', 'error');
  }

  // ═══ 寫②:手動觸發進化(POST /evolution/run;server-side Operator 角色 403 gate)═══
  // ★ 反 fake-success:ocApi 失敗回 null → 顯錯不假成功;payload byte-parity(parameter_grids/min_sharpe 同 legacy)。
  async function runEvolution() {
    var stratEl = q('.evo-strategy'), symEl = q('.evo-symbol'), resEl = q('.evo-result'), btn = q('.evo-run');
    var strategy = stratEl ? stratEl.value.trim() : '';
    var symbol = (symEl ? symEl.value.trim() : '') || 'BTCUSDT';
    if (!strategy) {
      if (resEl) { resEl.textContent = '請輸入策略名稱'; resEl.className = 'evo-result note t-warn mt-2'; }
      return;
    }
    if (btn) btn.setAttribute('aria-disabled', 'true');
    if (resEl) { resEl.textContent = '執行中…'; resEl.className = 'evo-result note t-muted mt-2'; }
    try {
      var d = await ocApi('/api/v1/evolution/run', {
        method: 'POST',
        body: {
          strategy_name: strategy,
          symbol: symbol,
          timeframe: '1h',
          parameter_grids: [
            { name: 'stop_loss_pct', values: [0.02, 0.03, 0.05] },
            { name: 'position_size_pct', values: [0.1, 0.2] }
          ],
          min_sharpe: 1.0
        }
      });
      if (!d) throw new Error('request failed');
      var sharpe = d.best_sharpe !== undefined ? 'Sharpe=' + num2(d.best_sharpe, 2) : '完成';
      if (resEl) {
        resEl.textContent = '進化完成 ' + sharpe + ' · 評估=' + (d.evaluated_combinations != null ? d.evaluated_combinations : EMPTY);
        resEl.className = 'evo-result note t-pos mt-2';
      }
      loadEvolution();
    } catch (e) {
      if (resEl) { resEl.textContent = '執行失敗:' + esc(String(e && e.message || e)); resEl.className = 'evo-result note t-neg mt-2'; }
    } finally {
      if (btn) btn.removeAttribute('aria-disabled');
    }
  }

  // ═══ 全節載入(5 主 GET + 2 companion load;Promise.allSettled,任一失敗不拖垮其餘)═══
  async function loadAll() {
    if (!built || loading) return;
    loading = true;
    showError('');
    try {
      var cost = aiCost(), prov = aiProviders();
      var tasks = [loadConsult(), loadSessions(), loadExperiments(), loadKelly(), loadEvolution()];
      if (cost && typeof cost.load === 'function') tasks.push(Promise.resolve(cost.load()));
      if (prov && typeof prov.load === 'function') tasks.push(Promise.resolve(prov.load()));
      var res = await Promise.allSettled(tasks);
      if (!built) return;
      stampUpdated(!res.some(function (x) { return x.status === 'rejected'; }));
    } finally {
      loading = false;
    }
  }

  // ═══ 控件接線(刷新 / trigger / evolution run)═══
  function wireControls() {
    var refresh = q('.ai-refresh');
    if (refresh) refresh.addEventListener('click', function () { loadAll(); });
    var trigger = q('.ai-trigger');
    if (trigger) trigger.addEventListener('click', function () { doTriggerSession(); });
    var evoRun = q('.evo-run');
    if (evoRun) evoRun.addEventListener('click', function () { runEvolution(); });
  }

  // ═══ 輪詢生命週期(僅可見時運行;pause 必清 → 隱藏不 fetch)═══
  function startPolling() { stopPolling(); timer = setInterval(loadAll, POLL_MS); }
  function stopPolling() { if (timer) { clearInterval(timer); timer = null; } }

  // ═══ shell router 契約:render / resume / pause(second-adapter 擴充點)═══
  // render:建骨架(冪等,只首渲一次);掛 2 companion;接線;不啟輪詢(屬 resume)。
  function renderAiView(hostEl) {
    if (hostEl) host = hostEl;
    if (!host || built) return;
    host.innerHTML = SKELETON;
    built = true;
    wireControls();
    // 掛成本面 companion(缺席則保留骨架降級提示,主面照常)。
    var cost = aiCost();
    if (cost && typeof cost.render === 'function') {
      try { cost.render(host); }
      catch (e) { console.warn('[view-ai] cost companion render 失敗:', e); }
    } else {
      var cs = q('.ai-cost-slot');
      if (cs) cs.innerHTML = '<div class="panel note t-warn">AI 成本面模組未載入;主面不受影響 / cost module not loaded.</div>';
    }
    // 掛供應商/設置面 companion(缺席則保留骨架降級提示,主面照常)。
    var prov = aiProviders();
    if (prov && typeof prov.render === 'function') {
      try { prov.render(host); }
      catch (e) { console.warn('[view-ai] providers companion render 失敗:', e); }
    } else {
      var ps = q('.ai-providers-slot');
      if (ps) ps.innerHTML = '<div class="panel note t-warn">AI 供應商/設置面模組未載入;主面不受影響 / providers module not loaded.</div>';
    }
    paint();                          // 骨架內 .tag(badge / 按鈕)首次上色
    setBadge('ai-updated', 'loading…', 'muted');
  }
  // resume:view 顯示 → 拉真值 + 啟輪詢。
  function resumeAiView() {
    if (!built) return;
    visible = true;
    loadAll();
    startPolling();
  }
  // pause:view 隱藏 → 停輪詢/停後續抓取(freshness/safety:隱藏不得續打後端,
  // 鏡像 iframe openclaw-tab-visibility 暫停語義,非協商)。
  function pauseAiView() {
    visible = false;
    stopPolling();
  }

  // 註冊進殼可見的原生 view 表(router 以 v.iframe===false 查此;stable host / 唯一擴充點)。
  window.OC_NATIVE_VIEWS = window.OC_NATIVE_VIEWS || {};
  window.OC_NATIVE_VIEWS['ai'] = { render: renderAiView, resume: resumeAiView, pause: pauseAiView };
  // 具名導出(task 契約:renderAiView / pauseAiView / resumeAiView 可被引用)。
  window.renderAiView = renderAiView;
  window.resumeAiView = resumeAiView;
  window.pauseAiView = pauseAiView;
})();
