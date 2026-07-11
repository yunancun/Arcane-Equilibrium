/*
 * view-learning.js — 玄衡原生 view「學習 Learning」(Phase 2 第 4 個 iframe→原生遷移;首個含寫)
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:把 legacy `tab-learning.html`(iframe 後備)遷成玄衡殼內的**原生 view**,
 *   延續 gates(首遷)/monitor(二遷)/development(三遷)所建的 strangler-fig pattern
 *   (design/10 recipe §1)。**本 view 是 Phase 2 首個含寫的原生 view**:除唯讀學習儀表盤外,
 *   還承載 3 項**學習治理寫**(審核決策 approve/reject/ask_ai + 觸發 auto-scan)——這些是
 *   既有 learning 治理端點,**原生 view preserve 呼叫(同端點、同 payload),絕不新增寫路徑、
 *   絕不改端點**。殼 router 為穩定宿主,本檔提供 render/pause/resume 為唯一新增擴充點
 *   (second-adapter),與 gates/monitor/development 同構。
 *   內容逐節守恆(對 legacy 7 節,零丟失):
 *     ①學習系統 Overview(header + Refresh + 6 摘要:觀察/教訓/假設/活躍實驗/待審核/淨 PnL 評分——
 *       淨 PnL 評分升為 hero,canon 6/9 PnL 領銜);②待審核佇列(表 + 每列 3 寫動作:批准/駁回/AI 諮詢);
 *     ③學習動態 Feed(觀察 + 教訓);④淨 PnL 儀表盤(Gross/Fees/AI Costs/Net 分解);
 *     ⑤自動掃描 Auto-Scan(3 觸發按鈕 + 結果,含寫);⑥實驗列表;⑦假設列表。
 *   刻意變更(canon 守恆非逐像素):
 *     ①legacy「AI 團隊工作台已搬遷」redirect banner(90d auto-dismiss + `window.parent.switchTo`
 *       跨-iframe 導航)**不遷**——玄衡殼已把 Agent 團隊(agents view)提為 rail 一級項,
 *       redirect 過渡輔助已過時,且 `window.parent.switchTo` 對原生 view(與殼同文檔、非 iframe)不適用;
 *       porting 破碎的跨-iframe 邏輯無益。此為 obsolete 過渡 chrome 之刻意省略。
 *     ②legacy 裝飾 emoji(📖📥📋💵…)不遷(canon 1 非數據 chrome 從簡,對齊 gates/monitor/development)。
 *     ③legacy ocExplain(short/deep 展開說明)+ `.oc-*` class(styles.css,iframe 作用域,殼不載)不可用,
 *       其操作教育文以殼原生 `.note` 內聯說明承載(資訊守恆,版式改玄衡組件)。
 * 主要函數:renderLearningView(建骨架,冪等)、resumeLearningView(顯示→拉真值+啟輪詢)、
 *   pauseLearningView(隱藏→停輪詢/停 fetch)、loadAll / loadOverview / loadReviewQueue / loadFeed /
 *   loadNetPnl / loadExperiments / loadHypotheses(6 唯讀 GET,7 call-site)、
 *   reviewAction / aiConsult(POST /learning/review/{}/decide)、autoScan(POST /learning/auto/{})。
 * 依賴(全復用,不重造):common.js ocApi / ocPost / ocToast($ 系;POST/CSRF/timeout 由 ocApi 統一);
 *   common-formatters.js ocEsc / ocMoney / ocBalance / OC_EMPTY;組件庫 shell-components.css
 *   (.panel/.panel-t/.kpis/.kpi/.tbl/.tag/.logs/.logblock/.note/.code)+ tokens.css(.silk/.num)
 *   + oc-utilities.css(flex/間距/t-* 色階/.hidden/.mono/.pointer)。
 * 硬邊界(canon / LOOP §6):
 *   ① 寫面走既有 Rust/API authority——3 寫 preserve 既有端點:
 *      · POST /api/v1/learning/review/{packet_id}/decide(approve/reject/ask_ai;payload {decision})
 *      · POST /api/v1/learning/auto/{scan}(scan-observations/scan-lessons/scan-hypotheses)
 *      皆 ∈ 5b 對齊(review/decide ∈ authoritative RESOLVED_CONCAT_SEEDS;auto/{} ∈ DYNAMIC_DEBT)。
 *      **絕不新增寫路徑、絕不改端點/payload**;學習治理是非交易面,經後端授權/審計。
 *   ② **response-gated 成功,絕不 fake-success**:ocApi/ocPost 契約(common.js:225-279)=任何
 *      非-2xx / 網路 / timeout / CSRF 失敗回 **null**,僅真 2xx 回 parsed JSON。故成功 toast +
 *      樂觀重載**只在 d 為真(後端真成功回應)才觸發**;d 為 null → 顯錯不冒充成功。絕不在回應前假成功。
 *   ③ canon 7 三態:loading=骨架「—/Loading…」;無真值=「—」/空節提示(絕不假值/假 0);
 *      error(ocApi 回 null)=顯錯不崩,保守標 warn/bad。淨 PnL 無值顯 EMPTY,絕不假 0.00。
 *   ④ visibility 語義(非協商):隱藏時 pauseLearningView 停輪詢/停後端抓取(鏡像 iframe
 *      openclaw-tab-visibility 暫停),否則隱藏續打後端=freshness/safety 退步。
 *   ⑤ ratchet 0/0/0:零裸 hex、零 inline style 屬性、零內聯樣式區塊;動態 tone 走
 *      .style.setProperty('--tag-tone', var(...)) scoped-var 正法(非樣式屬性字面)。
 * 誠實邊界:靜態(node --check + ratchet + 5b 對齊 + registry/asset smoke)只證 source/路徑事實;
 *   **真渲染正確性 / 三態版式 / 真值 / 3 寫真行為(真送達後端·真授權·真審計)= NEEDS-LINUX runtime
 *   + operator 視覺**,不由本刀 attest。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  // ── 常量 ──
  var POLL_MS = 30000;             // 輪詢間隔(鏡像 legacy ocStartRefresh 30s;僅可見時運行)
  var STALE_MS = 90000;            // 新鮮度門檻:client 拉取時刻逾 90s → 更新徽 STALE(刷新為 30s)

  // ── 執行期狀態 ──
  var host = null;                 // 原生 <section> 宿主(shell 注入)
  var built = false;               // 骨架是否已建(render 冪等)
  var timer = null;                // 輪詢 interval id(null=停;pause 必清)
  var loading = false;             // loadAll 去重(不重入整輪刷新)
  var visible = false;             // view 是否可見(resume=true / pause=false;守 visibility 語義)

  // ── 小工具 ──
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
  // tone → 文字色 utility class(oc-utilities .t-*;數值/KPI 值用)。
  // 註:不用 ocPnlClass(回傳 green/red 是 styles.css 舊 class,殼作用域無定義);
  //     殼內盈虧色走 .t-pos/.t-neg(oc-utilities,tokens 語義 var)。
  function toneTextClass(tone) {
    if (tone === 'good') return 't-pos';
    if (tone === 'bad') return 't-neg';
    if (tone === 'warn') return 't-warn';
    if (tone === 'muted') return 't-muted';
    return '';
  }

  // 產出 .tag pill 的 HTML(帶 data-tone;真正 tone 由 applyTagTones 以 scoped-var 上色,
  // 避免 innerHTML 內寫死 style=/hex —— ratchet 正法)。
  function tagHtml(text, tone) {
    return '<span class="tag" data-tone="' + esc(tone || 'muted') + '">' + esc(text) + '</span>';
  }
  // 掃 root 內所有 .tag[data-tone],逐一寫 --tag-tone scoped-var(component .tag 消費之)。
  // 註:含 .tag 態的 <button>(掃描 / 審核按鈕)亦被 shell.css button 重置去掉預設底/框,
  //     只留 .tag 的 border/color = 乾淨的 pill 按鈕,tone 由此上色。
  function applyTagTones(root) {
    if (!root) return;
    var tags = root.querySelectorAll('.tag[data-tone]');
    for (var i = 0; i < tags.length; i++) {
      tags[i].style.setProperty('--tag-tone', toneVar(tags[i].getAttribute('data-tone')));
    }
  }

  // 淨 PnL 金額格(復用 common-formatters ocMoney;+/− 帶 U+2212,tabular)。無值回 EMPTY(canon 7 禁假 0)。
  function money(v) {
    return (typeof window.ocMoney === 'function' && v != null) ? window.ocMoney(v) : EMPTY;
  }
  // 成本/餘額格(ocBalance 4dp sub-cent;非 PnL 無 +/−)。無值回 EMPTY。
  function balance(v) {
    return (typeof window.ocBalance === 'function' && v != null) ? window.ocBalance(v, 4) : EMPTY;
  }

  // ═══ 骨架(canon 7:首渲即 loading 態「—/Loading…」,絕不假值)═══
  var SKELETON =
    '<div class="p-4">' +

      // ═ 節①:學習系統 Overview(header + Refresh + 6 KPI 摘要)═
      '<div class="panel">' +
        '<div class="row-between wrap gap-3">' +
          '<div>' +
            '<div class="panel-t"><span class="zh">學習系統</span><span class="code">LEARNING SYSTEM</span></div>' +
            '<div class="note">觀察 → 教訓 → 假設 → 實驗 → 改進:先觀察市場現象,提煉教訓,形成假設,設計實驗驗證,將驗證過的知識應用到策略。唯讀儀表盤 + 三項學習治理寫(審核決策 / 自動掃描),不影響交易、風控、live 授權或 engine runtime。</div>' +
          '</div>' +
          '<div class="row wrap gap-2">' +
            '<span class="tag" data-tone="muted">auto refresh 30s</span>' +
            '<button type="button" class="lg-refresh mono fs-dense t-accent pointer">刷新 / Refresh</button>' +
            '<span class="lg-updated tag" data-tone="muted">loading…</span>' +
          '</div>' +
        '</div>' +
        // 錯誤橫幅(canon 7:error 顯錯不崩;預設隱藏)
        '<div class="lg-error panel note t-warn hidden"></div>' +
        // KPI 行(1 hero + 5):淨 PnL 評分升為 hero(最終指標,canon 6/9);其餘為學習計數
        '<div class="kpis">' +
          '<div class="kpi hero lg-kpi-score"><div class="silk">NET PNL SCORE</div><div class="v num">' + EMPTY + '</div><div class="d note">扣除全部成本後淨收益 / Net after all costs</div></div>' +
          '<div class="kpi lg-kpi-obs"><div class="silk">OBSERVATIONS</div><div class="v num">' + EMPTY + '</div><div class="d note">觀察記錄</div></div>' +
          '<div class="kpi lg-kpi-lessons"><div class="silk">LESSONS</div><div class="v num">' + EMPTY + '</div><div class="d note">教訓</div></div>' +
          '<div class="kpi lg-kpi-hyp"><div class="silk">HYPOTHESES</div><div class="v num">' + EMPTY + '</div><div class="d note">假設</div></div>' +
          '<div class="kpi lg-kpi-exp"><div class="silk">EXPERIMENTS</div><div class="v num">' + EMPTY + '</div><div class="d note">活躍實驗</div></div>' +
          '<div class="kpi lg-kpi-queue"><div class="silk">REVIEW QUEUE</div><div class="v num">' + EMPTY + '</div><div class="d note">待審核</div></div>' +
        '</div>' +
      '</div>' +

      // ═ 節②:待審核佇列(表 + 每列 3 寫動作)═
      '<div class="panel">' +
        '<div class="panel-t"><span class="zh">待審核佇列</span><span class="code">REVIEW QUEUE</span></div>' +
        '<div class="note mb-2">需人工確認的學習成果:自動發現的市場模式 / 策略參數調整建議 / 風控閾值修改建議。批准 · 駁回 · 或請 AI 分析——人類 Operator 始終保持對學習方向的控制權。</div>' +
        '<table class="tbl">' +
          '<thead><tr><th>ID</th><th>類型 / Type</th><th>摘要 / Summary</th><th>優先級</th><th>建立時間</th><th>操作</th></tr></thead>' +
          '<tbody class="lg-review-body"><tr><td colspan="6" class="note">Loading…</td></tr></tbody>' +
        '</table>' +
      '</div>' +

      // ═ 節③④:學習動態 Feed + 淨 PnL 儀表盤(兩面板)═
      '<div class="row wrap gap-3">' +
        '<div class="panel flex-1">' +
          '<div class="panel-t"><span class="zh">學習動態</span><span class="code">LEARNING FEED</span></div>' +
          '<div class="note mb-2">最近的觀察和教訓</div>' +
          '<div class="lg-feed logs"><div class="note">Loading…</div></div>' +
        '</div>' +
        '<div class="panel flex-1">' +
          '<div class="panel-t"><span class="zh">淨 PnL 儀表盤</span><span class="code">NET PNL DASHBOARD</span></div>' +
          '<div class="note mb-2">Net PnL = Gross − Trading Fees − AI Costs − Infra Costs;系統嚴格「看 net 不看 gross」。</div>' +
          '<div class="lg-netpnl"><div class="note">Loading…</div></div>' +
        '</div>' +
      '</div>' +

      // ═ 節⑤:自動掃描 Auto-Scan(3 觸發按鈕 + 結果;含寫)═
      '<div class="panel">' +
        '<div class="panel-t"><span class="zh">自動掃描</span><span class="code">AUTO-SCAN CONTROLS</span></div>' +
        '<div class="note mb-2">讓 AI 分析最近交易資料,自動發現值得關注的觀察 / 教訓 / 假設。發現的內容進入審核佇列,待人工確認後才納入知識庫——確保自動發現的品質。</div>' +
        '<div class="row wrap gap-3 mb-2">' +
          '<button type="button" class="tag pointer lg-scan" data-tone="accent" data-scan="scan-observations">掃描觀察記錄</button>' +
          '<button type="button" class="tag pointer lg-scan" data-tone="accent" data-scan="scan-lessons">掃描教訓</button>' +
          '<button type="button" class="tag pointer lg-scan" data-tone="accent" data-scan="scan-hypotheses">掃描假設</button>' +
        '</div>' +
        '<div class="lg-scan-result"></div>' +
      '</div>' +

      // ═ 節⑥:實驗列表 Experiments ═
      '<div class="panel">' +
        '<div class="panel-t"><span class="zh">實驗列表</span><span class="code">EXPERIMENTS</span></div>' +
        '<table class="tbl">' +
          '<thead><tr><th>ID</th><th>假設 / Hypothesis</th><th>狀態</th><th>開始時間</th><th>結果 / Result</th></tr></thead>' +
          '<tbody class="lg-exp-body"><tr><td colspan="5" class="note">Loading…</td></tr></tbody>' +
        '</table>' +
      '</div>' +

      // ═ 節⑦:假設列表 Hypotheses ═
      '<div class="panel">' +
        '<div class="panel-t"><span class="zh">假設列表</span><span class="code">HYPOTHESES</span></div>' +
        '<table class="tbl">' +
          '<thead><tr><th>ID</th><th>預測 / Prediction</th><th>狀態</th><th>裁決 / Verdict</th><th>建立時間</th></tr></thead>' +
          '<tbody class="lg-hyp-body"><tr><td colspan="5" class="note">Loading…</td></tr></tbody>' +
        '</table>' +
      '</div>' +
    '</div>';

  // ═══ 值設定器(canon 7:無真值 → EMPTY,絕不假 0)═══
  function setKpi(cls, value, tone) {
    var v = q('.' + cls + ' .v');
    if (!v) return;
    v.className = ('v num ' + toneTextClass(tone)).trim();
    v.textContent = (value == null || value === '') ? EMPTY : String(value);
  }
  // hero:淨 PnL 評分(ocMoney;>=0 綠 / <0 紅;無值 EMPTY,絕不假 0.00)。
  function setScore(score) {
    var v = q('.lg-kpi-score .v');
    if (!v) return;
    if (score == null) { v.className = 'v num'; v.textContent = EMPTY; return; }
    v.className = 'v num ' + (Number(score) >= 0 ? 't-pos' : 't-neg');
    v.textContent = money(score);
  }
  // 更新徽:顯 client 拉取時刻(誠實=前端最後成功拉取時間,非後端 generated_at;canon 7 staleness)。
  function setUpdated(text, tone) {
    var el = q('.lg-updated');
    if (!el) return;
    el.textContent = text;
    el.setAttribute('data-tone', tone || 'muted');
    el.style.setProperty('--tag-tone', toneVar(tone || 'muted'));
  }
  function stampUpdated(ok) {
    if (!ok) { setUpdated('拉取失敗', 'bad'); return; }
    var t = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    setUpdated('更新 ' + t, 'good');
  }
  function showError(msg) {
    var el = q('.lg-error');
    if (!el) return;
    if (msg) { el.textContent = msg; el.classList.remove('hidden'); }
    else { el.textContent = ''; el.classList.add('hidden'); }
  }

  // ═══ 節①:摘要(port legacy loadOverview;totals 來自 /feed、活躍實驗來自 /overview)═══
  async function loadOverview() {
    var res = await Promise.allSettled([
      ocApi('/api/v1/learning/feed'),
      ocApi('/api/v1/learning/overview'),
    ]);
    if (!built) return;
    var feedD = res[0], ovD = res[1];
    if (feedD.status === 'fulfilled' && feedD.value && feedD.value.data) {
      var totals = feedD.value.data.totals || {};
      setKpi('lg-kpi-obs', totals.total_observations != null ? totals.total_observations : 0);
      setKpi('lg-kpi-lessons', totals.total_lessons != null ? totals.total_lessons : 0);
      setKpi('lg-kpi-hyp', totals.total_hypotheses != null ? totals.total_hypotheses : 0);
    }
    if (ovD.status === 'fulfilled' && ovD.value && ovD.value.data) {
      var o = ovD.value.data;
      var expCount = (o.experiments && o.experiments.active_experiment_count) || o.active_experiment_count || 0;
      setKpi('lg-kpi-exp', expCount);
    }
  }

  // ═══ 節②:待審核佇列(port legacy loadReviewQueue;含 3 寫動作按鈕)═══
  function priorityTone(p) { return p === 'high' ? 'bad' : 'muted'; }
  function renderReviewRows(items) {
    var body = q('.lg-review-body');
    if (!body) return;
    if (!items.length) {
      body.innerHTML = '<tr><td colspan="6" class="note">審核佇列為空 / Queue is empty</td></tr>';
      return;
    }
    var html = items.map(function (item) {
      var id = String(item.id == null ? '' : item.id);
      // 3 寫動作:批准 / 駁回 走 review/decide(decision=approve|reject);AI 諮詢走同端點(decision=ask_ai)。
      // 按鈕帶 data-id/data-act,由 tbody 事件委派(wireReviewDelegation)分派——避免每次重渲重接線。
      var actions =
        '<button type="button" class="tag pointer" data-tone="good" data-id="' + esc(id) + '" data-act="approve">批准</button> ' +
        '<button type="button" class="tag pointer" data-tone="bad" data-id="' + esc(id) + '" data-act="reject">駁回</button> ' +
        '<button type="button" class="tag pointer" data-tone="accent" data-id="' + esc(id) + '" data-act="ask_ai">AI 諮詢</button>';
      return '<tr>' +
        '<td class="mono fs-micro">' + shortId(id) + '</td>' +
        '<td>' + tagHtml(item.type || EMPTY, 'muted') + '</td>' +
        '<td class="clip">' + esc(item.summary || item.title || EMPTY) + '</td>' +
        '<td>' + tagHtml(item.priority || 'normal', priorityTone(item.priority)) + '</td>' +
        '<td class="mono fs-micro t-muted">' + esc(timeShort(item.created_at)) + '</td>' +
        '<td class="nowrap">' + actions + '</td>' +
      '</tr>';
    }).join('');
    body.innerHTML = html;
    applyTagTones(body);
  }
  async function loadReviewQueue() {
    var d = await ocApi('/api/v1/learning/review-queue');
    if (!built) return;
    var body = q('.lg-review-body');
    if (!d || !d.data) {
      setKpi('lg-kpi-queue', EMPTY, 'warn');
      if (body) body.innerHTML = '<tr><td colspan="6" class="note t-warn">無法載入 / Failed to load review queue</td></tr>';
      return;
    }
    var items = d.data.items || d.data.queue || (Array.isArray(d.data) ? d.data : []) || [];
    setKpi('lg-kpi-queue', items.length);
    renderReviewRows(items);
  }

  // ═══ 節③:學習動態 Feed(port legacy loadFeed;觀察 + 教訓合流)═══
  async function loadFeed() {
    var d = await ocApi('/api/v1/learning/feed');
    if (!built) return;
    var box = q('.lg-feed');
    if (!box) return;
    if (!d || !d.data) { box.innerHTML = '<div class="note t-warn">無法載入 / Failed to load feed</div>'; return; }
    var observations = (d.data.observations_recent || []).map(function (o) { o._feedType = 'observation'; return o; });
    var lessons = (d.data.lessons_recent || []).map(function (l) { l._feedType = 'lesson'; return l; });
    var feed = observations.concat(lessons);
    var totals = d.data.totals || {};
    if (!feed.length) {
      box.innerHTML =
        '<div class="note">暫無學習動態 / No feed items yet' +
        '<div class="mono fs-micro t-muted mt-1">Total observations: ' + (totals.total_observations || 0) +
        ' · lessons: ' + (totals.total_lessons || 0) + '</div></div>';
      return;
    }
    var html = feed.slice(0, 15).map(function (f) {
      var typeLabel = f._feedType || f.observation_type || f.type || EMPTY;
      var ts = f.recorded_at || f.created_at || f.timestamp;
      var detail = f.detail || f.outcome_summary || f.content || f.title || EMPTY;
      var symbol = f.symbol ? ' · ' + f.symbol : '';
      return '<div class="logblock"><div class="w-full">' +
          '<div class="row-between wrap gap-2">' +
            '<span>' + tagHtml(typeLabel, f._feedType === 'lesson' ? 'good' : 'accent') + '<span class="t-muted">' + esc(symbol) + '</span></span>' +
            '<span class="ts">' + esc(timeShort(ts)) + '</span>' +
          '</div>' +
          '<div class="mt-1 t-primary">' + esc(detail) + '</div>' +
        '</div></div>';
    }).join('');
    box.innerHTML = html;
    applyTagTones(box);
  }

  // ═══ 節④:淨 PnL 儀表盤(port legacy loadNetPnl;Gross/Fees/AI/Net + hero 評分)═══
  async function loadNetPnl() {
    var d = await ocApi('/api/v1/learning/net-pnl');
    if (!built) return;
    var box = q('.lg-netpnl');
    if (!box) return;
    if (!d || !d.data) { box.innerHTML = '<div class="note t-warn">無法載入 / Failed to load PnL</div>'; return; }
    var pnl = d.data;
    // isPnl 欄用 ocMoney(+/−);非 PnL(費用/成本)用 ocBalance 4dp;盈虧色走 .t-pos/.t-neg。
    var fields = [
      { label: 'Gross Revenue', val: pick(pnl.gross_revenue, pnl.gross_pnl), isPnl: true },
      { label: 'Trading Fees',  val: pick(pnl.trading_fees, pnl.fees),       isPnl: false },
      { label: 'AI Costs',      val: pick(pnl.ai_costs, pnl.ai_cost),         isPnl: false },
      { label: 'Net Revenue',   val: pick(pnl.net_revenue, pnl.net_pnl),      isPnl: true },
    ];
    var rows = fields.map(function (f) {
      var cls = f.isPnl && f.val != null ? (Number(f.val) >= 0 ? 't-pos' : 't-neg') : '';
      var txt = f.val == null ? EMPTY : (f.isPnl ? money(f.val) : balance(f.val));
      return '<tr><td class="t-muted">' + esc(f.label) + '</td>' +
        '<td class="num t-right ' + cls + '">' + esc(txt) + '</td></tr>';
    }).join('');
    box.innerHTML = '<table class="tbl"><tbody>' + rows + '</tbody></table>';
    // hero 評分 = net_revenue / net_pnl(canon 7:無值 EMPTY 不假 0)
    setScore(pick(pnl.net_revenue, pnl.net_pnl));
  }

  // ═══ 節⑥:實驗列表(port legacy loadExperiments)═══
  function experimentTone(s) { return s === 'completed' ? 'good' : s === 'active' ? 'accent' : 'muted'; }
  async function loadExperiments() {
    var d = await ocApi('/api/v1/learning/experiments');
    if (!built) return;
    var body = q('.lg-exp-body');
    if (!body) return;
    if (!d || !d.data) { body.innerHTML = '<tr><td colspan="5" class="note t-warn">無法載入 / Load failed</td></tr>'; return; }
    var exps = d.data.experiments || (Array.isArray(d.data) ? d.data : []) || [];
    if (!exps.length) { body.innerHTML = '<tr><td colspan="5" class="note">暫無實驗 / No experiments</td></tr>'; return; }
    body.innerHTML = exps.map(function (e) {
      return '<tr>' +
        '<td class="mono fs-micro">' + shortId(e.id) + '</td>' +
        '<td class="clip">' + esc(e.hypothesis || e.title || EMPTY) + '</td>' +
        '<td>' + tagHtml(e.status || EMPTY, experimentTone(e.status)) + '</td>' +
        '<td class="mono fs-micro t-muted">' + esc(timeShort(e.started_at || e.created_at)) + '</td>' +
        '<td class="fs-micro">' + esc(e.result || EMPTY) + '</td>' +
      '</tr>';
    }).join('');
    applyTagTones(body);
  }

  // ═══ 節⑦:假設列表(port legacy loadHypotheses)═══
  function hypothesisTone(s) { return s === 'validated' ? 'good' : s === 'rejected' ? 'bad' : 'muted'; }
  async function loadHypotheses() {
    var d = await ocApi('/api/v1/learning/hypotheses');
    if (!built) return;
    var body = q('.lg-hyp-body');
    if (!body) return;
    if (!d || !d.data) { body.innerHTML = '<tr><td colspan="5" class="note t-warn">無法載入 / Load failed</td></tr>'; return; }
    var hyps = d.data.hypotheses || (Array.isArray(d.data) ? d.data : []) || [];
    if (!hyps.length) { body.innerHTML = '<tr><td colspan="5" class="note">暫無假設 / No hypotheses</td></tr>'; return; }
    body.innerHTML = hyps.map(function (h) {
      return '<tr>' +
        '<td class="mono fs-micro">' + shortId(h.id) + '</td>' +
        '<td class="clip">' + esc(h.prediction || h.title || EMPTY) + '</td>' +
        '<td>' + tagHtml(h.status || EMPTY, hypothesisTone(h.status)) + '</td>' +
        '<td>' + esc(h.verdict || EMPTY) + '</td>' +
        '<td class="mono fs-micro t-muted">' + esc(timeShort(h.created_at)) + '</td>' +
      '</tr>';
    }).join('');
    applyTagTones(body);
  }

  // 小工具:取第一個非空值(port legacy `a || b` 模式,但保 0 為有效值)。
  function pick(a, b) { return a != null ? a : (b != null ? b : null); }
  // 時間短格式(復用 common-formatters ocTimeShort;缺席回退)。
  function timeShort(ts) {
    if (typeof window.ocTimeShort === 'function') return window.ocTimeShort(ts);
    return ts ? String(ts) : '--';
  }

  // ═══ 全節載入(6 GET / 7 call-site;Promise.allSettled 併發,任一失敗不拖垮其餘)═══
  async function loadAll() {
    if (!built || loading) return;
    loading = true;
    showError('');
    try {
      var res = await Promise.allSettled([
        loadOverview(), loadReviewQueue(), loadFeed(), loadNetPnl(), loadExperiments(), loadHypotheses(),
      ]);
      if (!built) return;
      // 只要有一節 rejected(非預期例外),標更新徽 warn;各節內部已各自顯錯(canon 7)。
      var anyRejected = res.some(function (r) { return r.status === 'rejected'; });
      stampUpdated(!anyRejected);
    } finally {
      loading = false;
    }
  }

  // ═══ 學習治理寫(3 寫;preserve 既有端點/payload;response-gated,絕不 fake-success)═══
  // ★ 反 fake-success 契約(硬邊界②):ocApi/ocPost 於任何非-2xx / 網路 / timeout / CSRF 失敗
  //   回 null,僅真 2xx 成功回 parsed JSON(common.js:225-279)。故下列成功 toast + 樂觀重載
  //   **只在 d 為真(後端真成功回應)時觸發**;d 為 null → 顯錯,絕不冒充成功。

  // 審核決策:批准 / 駁回(POST /learning/review/{packet_id}/decide;payload {decision})。
  async function reviewAction(id, action) {
    if (!id) return;
    var d = await ocPost('/api/v1/learning/review/' + id + '/decide', { decision: action });
    if (d) {
      ocToast('審核 ' + action + ' 完成', 'success');
      loadReviewQueue();   // 樂觀重載:僅在真成功後刷新佇列
    } else {
      ocToast('審核操作失敗', 'error');
    }
  }
  // AI 諮詢:同 review/decide 端點,decision=ask_ai(preserve legacy aiConsult)。
  async function aiConsult(id) {
    if (!id) return;
    var d = await ocPost('/api/v1/learning/review/' + id + '/decide', { decision: 'ask_ai' });
    if (d) {
      ocToast('AI 諮詢已提交', 'success');
      loadReviewQueue();
    } else {
      ocToast('AI 諮詢失敗', 'error');
    }
  }
  // 觸發 auto-scan(POST /learning/auto/{scan};scan ∈ scan-observations|scan-lessons|scan-hypotheses)。
  async function autoScan(type) {
    if (!type) return;
    var box = q('.lg-scan-result');
    var d = await ocPost('/api/v1/learning/auto/' + type);
    if (d) {
      ocToast('掃描完成', 'success');
      var count = d.data ? (d.data.count || d.data.discovered || 0) : 0;
      if (box) { box.innerHTML = tagHtml('發現 ' + count + ' 條記錄', 'good'); applyTagTones(box); }
      loadAll();           // 掃描可能新增觀察/教訓/假設 → 整輪重載(僅真成功後)
    } else {
      ocToast('掃描失敗', 'error');
      if (box) { box.innerHTML = tagHtml('掃描失敗', 'bad'); applyTagTones(box); }
    }
  }

  // ═══ 控件接線(刷新 / 掃描 / 審核動作;審核走事件委派)═══
  function wireControls() {
    var refresh = q('.lg-refresh');
    if (refresh) refresh.addEventListener('click', function () { loadAll(); });

    // auto-scan 按鈕(骨架靜態存在,直接接)
    var scans = host ? host.querySelectorAll('.lg-scan') : [];
    for (var i = 0; i < scans.length; i++) {
      (function (btn) {
        btn.addEventListener('click', function () { autoScan(btn.getAttribute('data-scan')); });
      })(scans[i]);
    }

    // 審核動作:tbody 事件委派(列動態重渲,委派避免每渲重接線)。
    var body = q('.lg-review-body');
    if (body) {
      body.addEventListener('click', function (ev) {
        var t = ev.target;
        var btn = (t && typeof t.closest === 'function') ? t.closest('button[data-act]') : null;
        if (!btn) return;
        var id = btn.getAttribute('data-id');
        var act = btn.getAttribute('data-act');
        if (!id) return;
        if (act === 'ask_ai') aiConsult(id);
        else reviewAction(id, act);
      });
    }
  }

  // ═══ 輪詢生命週期(僅可見時運行;pause 必清 → 隱藏不 fetch)═══
  function startPolling() {
    stopPolling();
    timer = setInterval(loadAll, POLL_MS);
  }
  function stopPolling() {
    if (timer) { clearInterval(timer); timer = null; }
  }

  // ═══ shell router 契約:render / resume / pause(second-adapter 擴充點)═══
  // render:建骨架(冪等,只首渲一次);接線;不啟輪詢(屬 resume)。
  function renderLearningView(hostEl) {
    if (hostEl) host = hostEl;
    if (!host || built) return;
    host.innerHTML = SKELETON;
    built = true;
    wireControls();
    applyTagTones(host);              // 骨架內 .tag(refresh 徽 / 掃描按鈕)首次上色
    setUpdated('loading…', 'muted');
  }
  // resume:view 顯示 → 拉真值 + 啟輪詢。
  function resumeLearningView() {
    if (!built) return;
    visible = true;
    loadAll();
    startPolling();
  }
  // pause:view 隱藏 → 停輪詢/停後續抓取(freshness/safety:隱藏不得續打後端,
  // 鏡像 iframe openclaw-tab-visibility 暫停語義,非協商)。
  function pauseLearningView() {
    visible = false;
    stopPolling();
  }

  // 註冊進殼可見的原生 view 表(router 以 v.iframe===false 查此;stable host / 唯一擴充點)。
  window.OC_NATIVE_VIEWS = window.OC_NATIVE_VIEWS || {};
  window.OC_NATIVE_VIEWS['learning'] = { render: renderLearningView, resume: resumeLearningView, pause: pauseLearningView };
  // 具名導出(task 契約:renderLearningView / pauseLearningView / resumeLearningView 可被引用)。
  window.renderLearningView = renderLearningView;
  window.resumeLearningView = resumeLearningView;
  window.pauseLearningView = pauseLearningView;
})();
