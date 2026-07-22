/*
 * view-agents.js — 玄衡原生 view「Agent 團隊」(Phase 2 第 5 個 iframe→原生遷移;read-only)
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:把 legacy `tab-agents.html`(iframe 後備)遷成玄衡殼內的**原生 view**,
 *   延續 gates(首遷)/monitor(二遷)/development(三遷)/learning(四遷)所建的
 *   strangler-fig pattern(design/10 recipe §1)。**本 view 純唯讀**:5-Agent 團隊追蹤
 *   (Scout/Strategist/Guardian/Analyst/Executor 各自狀態/任務/成本/歷史)+ OpenClaw 控制面
 *   authority/capability/gateway/topology/blockers 唯讀展示。**零寫路徑**(0 POST/PUT/PATCH/
 *   DELETE、0 order、0 control 動作)。殼 router 為穩定宿主,本檔提供 render/pause/resume 為唯一
 *   新增擴充點(second-adapter),與前四遷同構。
 *   **拆檔**(檔案 <2000 硬性;agents 內容多):本檔=主(Agent 團隊面 + 生命週期 + 骨架宿主);
 *   OpenClaw 控制面拆出 `view-agents-openclaw.js`(companion,自帶 read-only header fetch),
 *   由本檔於 window.OC_AGENTS_OPENCLAW 掛鉤驅動(render/load);companion 缺席時本 view 誠實降級
 *   (openclaw 面顯提示,團隊面照常)。兩檔各 <2000。
 *   內容逐節守恆(對 legacy tab-agents,零丟失):
 *     ①phase/契約列(P5 抽出 read-only never-emit + 4 維 mode:data_tier=mixed / output_policy=
 *       advisory / calibration=unknown / execution_confidence=none——none 為 anti-cognitive-fraud
 *       SENTINEL,以 bad 調紅標,強化「不可作實盤決策依據」)+ AI 團隊 explainer 文;
 *     ②OpenClaw 控制面(companion,見 view-agents-openclaw.js);③5-Agent Roster 卡;
 *     ④思考预算(spent/cap/pct + 告警文);⑤Demo 引擎 vs LiveDemo 引擎成交對比(2 欄 + diff);
 *     ⑥最近活動 feed(strategist history + shadow fills 合流);⑦治理租約 & 拒單(2 欄)。
 *   刻意變更(canon 守恆非逐像素):①legacy 裝飾 emoji(🤖👥🧠🟦…)不遷(canon 1 非數據 chrome
 *     從簡,對齊前四遷 austere 版式);②legacy 頁內 `.agent-card`/`.at-*`/`.exec-banner*`/
 *     `.agent-control-*` class(tab-agents 頁內樣式區塊,iframe 作用域,殼不載)不可用,改以殼原生
 *     組件庫(.panel/.tag/.tbl/.logblock/.note + oc-utilities t-* 色階)重渲(資訊守恆,版式改玄衡);
 *     ③Executor 真倉「呼吸動畫」是裝飾,不遷——真倉/影子的**安全語義**以 note + tone 保留
 *     (真倉=t-neg 紅警「用真钱下單」/ 影子=t-accent「仅模擬不送真單」);④思考预算「圖形進度條」
 *     (legacy 頁內樣式 + JS 設寬)改以「$spent / $cap + 已用 pct% tone tag + 告警文」承載
 *     (資訊守恆:數值/百分比/告警全在,免頁內 CSS,守 ratchet 0/0/0);⑤legacy ocExplain(short/deep
 *     展開)+ OpenClawModeBadge(styles.css/共用 badge CSS,殼作用域無定義)不復用,其資訊以殼原生
 *     .note + .tag 內聯承載。
 *   canon 7 誠實升級(不 fake):legacy roster 卡對 today_decisions/today_cost_usd 缺值 `?? 0`;
 *     本 view **null → EMPTY(—),絕不假 0**(真 0 事件才顯 0)——task 硬紀律「絕不假 agent 狀態/
 *     capability/authority/健康/假 0」。
 * 主要函數:renderAgentsView(建骨架,冪等;掛 openclaw companion)、resumeAgentsView(顯示→拉真值+
 *   啟輪詢)、pauseAgentsView(隱藏→停輪詢/停 fetch)、loadAll(5 團隊 GET + openclaw load hook)、
 *   loadRoster / loadFeed / loadFills / loadGovernance / loadBudget。
 * 依賴(全復用,不重造):common.js ocApi(GET;auth 由 HttpOnly cookie);common-formatters.js
 *   ocEsc / ocMoney / ocBalance / ocTimeShort / OC_EMPTY;組件庫 shell-components.css
 *   (.panel/.panel-t/.tbl/.tag/.logs/.logblock/.note/.code)+ tokens.css(.silk/.num)
 *   + oc-utilities.css(flex/間距/t-* 色階/.hidden/.mono/.pointer)。
 * 硬邊界(canon / LOOP §6):
 *   ① **零寫路徑**——agents 全唯讀:7 團隊 GET(∈ 5b 對齊 authoritative)+ 2 openclaw GET
 *      (companion,同 legacy read-only 契約);**絕不引入任何寫/control 動作**。7 團隊 GET:
 *      /agents/roster · /strategist/history · /edge/shadow_fills · /agents/shadow_vs_live_summary ·
 *      /governance/leases · /agents/recent_rejects · /paper/layer2/cost(皆 ∈ authoritative)。
 *   ② canon 7 三態:loading=骨架「Loading…」;無真值=「—」/空節提示(絕不假值/假 0/假狀態);
 *      error(ocApi 回 null)=顯錯不崩,保守標 warn/bad,絕不冒充健康。
 *   ③ visibility 語義(非協商):隱藏時 pauseAgentsView 停輪詢/停後端抓取(鏡像 iframe
 *      openclaw-tab-visibility 暫停),否則隱藏續打後端=freshness/safety 退步。
 *   ④ ratchet 0/0/0:零裸 hex、零 inline style 屬性、零內聯樣式區塊;動態 tone 走
 *      .style.setProperty('--tag-tone', var(...)) scoped-var 正法(非樣式屬性字面)。
 * 誠實邊界:靜態(node --check + ratchet + 5b 對齊 + registry/asset smoke)只證 source/路徑事實;
 *   **真渲染正確性 / 三態版式 / 真值 / Agent 真狀態 / OpenClaw 真健康 = NEEDS-LINUX runtime
 *   + operator 視覺**,不由本刀 attest。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  // ── 常量 ──
  var POLL_MS = 30000;             // 輪詢間隔(統一 30s loadAll;鏡像 learning 遷移;僅可見時運行。
                                   //   刻意簡化 legacy 每塊獨立 30/60/120s → 單輪 30s,只在可見時打後端,誠實)

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
  // tone → 文字色 utility class(oc-utilities .t-*;數值/警語用)。
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
  // 掃 root 內所有 .tag[data-tone],逐一寫 --tag-tone scoped-var(component .tag 消費之)。
  function applyTagTones(root) {
    if (!root) return;
    var tags = root.querySelectorAll('.tag[data-tone]');
    for (var i = 0; i < tags.length; i++) {
      tags[i].style.setProperty('--tag-tone', toneVar(tags[i].getAttribute('data-tone')));
    }
  }
  // 全域上色(重渲後統一刷新 host 內所有 .tag)。
  function paint() { applyTagTones(host); }

  // PnL 金額格(ocMoney;+/− 帶 U+2212,tabular)。無值回 EMPTY(canon 7 禁假 0)。
  function money(v) {
    return (typeof window.ocMoney === 'function' && v != null) ? window.ocMoney(v) : EMPTY;
  }
  // 成本/餘額格(ocBalance;非 PnL 無 +/−)。無值回 EMPTY。
  function balance(v) {
    return (typeof window.ocBalance === 'function' && v != null) ? window.ocBalance(v, 2) : EMPTY;
  }

  // 相對時間(port legacy _agentRelTime;空/非法回 '--')。
  function relTime(isoTs) {
    if (!isoTs) return '--';
    var t = new Date(isoTs).getTime();
    if (!isFinite(t)) return '--';
    var dMs = Date.now() - t;
    if (dMs < 0) return '刚刚';
    var sec = Math.floor(dMs / 1000);
    if (sec < 60) return sec + ' 秒前';
    var min = Math.floor(sec / 60);
    if (min < 60) return min + ' 分鐘前';
    var hr = Math.floor(min / 60);
    if (hr < 24) return hr + ' 小時前';
    return Math.floor(hr / 24) + ' 天前';
  }
  // 短時間(復用 common-formatters ocTimeShort;缺席回退)。
  function timeShort(ts) {
    if (typeof window.ocTimeShort === 'function') return window.ocTimeShort(ts);
    return ts ? String(ts) : '--';
  }
  // 心跳新鮮度 tag:<2min good / 2-5min warn / >5min bad(port legacy _heartbeatChip)。
  function heartbeatTag(ts) {
    if (!ts) return tagHtml('無心跳', 'bad');
    var min = (Date.now() - new Date(ts).getTime()) / 60000;
    var tone = min > 5 ? 'bad' : (min > 2 ? 'warn' : 'good');
    return tagHtml('心跳 ' + relTime(ts), tone);
  }

  // Agent 狀態 → { zh, tone }(port legacy _AGENT_STATE_MAP;去 emoji,tone 對映 canon 語義色。
  // 未知/live 一律 bad 紅——canon 7 不確定保守 + live=真钱風險紅)。
  var STATE_MAP = {
    active:      { zh: '活跃中',       tone: 'good'   },
    idle:        { zh: '待命',         tone: 'muted'  },
    slow:        { zh: '反應慢',       tone: 'warn'   },
    offline:     { zh: '已离線',       tone: 'bad'    },
    thinking:    { zh: '思考中',       tone: 'accent' },
    watching:    { zh: '盯盤中',       tone: 'accent' },
    budget_low:  { zh: '预算告急',     tone: 'warn'   },
    rejecting:   { zh: '拒單中',       tone: 'warn'   },
    guarding:    { zh: '守门中',       tone: 'good'   },
    tightening:  { zh: '收紧门槛',     tone: 'warn'   },
    frozen:      { zh: '冻結',         tone: 'bad'    },
    shadow:      { zh: '影子模式',     tone: 'accent' },
    live:        { zh: '真倉執行',     tone: 'bad'    },
    reviewing:   { zh: '審核中',       tone: 'accent' },
    waiting:     { zh: '等待數據',     tone: 'muted'  },
    unknown:     { zh: '状态未确認',   tone: 'bad'    }
  };
  function stateBadge(state, labelZh) {
    var cfg = STATE_MAP[state] || STATE_MAP.unknown;
    return tagHtml(labelZh || cfg.zh, cfg.tone);
  }

  // ═══ 骨架(canon 7:首渲即 loading 態,絕不假值)═══
  // 各塊用單一 body 容器(loading/empty/error/data 由 loader 換 innerHTML;鏡像前四遷)。
  var SKELETON =
    '<div class="p-4">' +

      // ═ 節①:phase/契約列 + AI 團隊 explainer(read-only never-emit + 4 維 mode)═
      '<div class="panel">' +
        '<div class="row-between wrap gap-3">' +
          '<div>' +
            '<div class="panel-t"><span class="zh">Agent 團隊</span><span class="code">AI TEAM · READ-ONLY</span></div>' +
            '<div class="note">你的 5 位 AI 員工今天在干什么、花了多少钱、谁進入執行链路。Scout 巡逻找機會 · Strategist 評估策略 · Guardian 守门控風險 · Analyst 復盤歸因 · Executor 負責執行入口。執行權限由 engine_mode、RiskConfig、Decision Lease 与 live 授權门控共同決定;LiveDemo 是 demo endpoint 上的 live-grade 管線,不等于真實主網資金。本視圖純只读,不能在此切换執行權限。</div>' +
          '</div>' +
          '<div class="row wrap gap-2">' +
            '<span class="tag" data-tone="muted">auto refresh 30s</span>' +
            '<button type="button" class="ag-refresh mono fs-dense t-accent pointer">刷新 / Refresh</button>' +
            '<span class="ag-updated tag" data-tone="muted">loading…</span>' +
          '</div>' +
        '</div>' +
        // 4 維 mode 徽(read-only baseline;execution_confidence=none 為 SENTINEL,bad 紅標)
        '<div class="row wrap gap-2 mt-2">' +
          '<span class="tag" data-tone="muted">read-only · 永不送單</span>' +
          '<span class="tag" data-tone="muted">data_tier: mixed</span>' +
          '<span class="tag" data-tone="accent">output_policy: advisory</span>' +
          '<span class="tag" data-tone="warn">calibration: unknown</span>' +
          '<span class="tag" data-tone="bad">execution_confidence: none</span>' +
        '</div>' +
      '</div>' +

      // ═ 節②:OpenClaw 控制面宿主(companion view-agents-openclaw.js 填充;缺席顯降級提示)═
      '<div class="ag-openclaw"><div class="panel note t-muted">OpenClaw 控制面模組載入中… / OpenClaw control module loading…</div></div>' +

      // ═ 節③:5-Agent Roster ═
      '<div class="panel">' +
        '<div class="panel-t"><span class="zh">5 位 Agent 現況</span><span class="code">5-AGENT ROSTER</span></div>' +
        '<div class="ag-roster"><div class="note">Loading…</div></div>' +
      '</div>' +

      // ═ 節④⑤:思考预算 + Demo/LiveDemo 引擎成交(兩面板)═
      '<div class="row wrap gap-3">' +
        '<div class="panel flex-1">' +
          '<div class="panel-t"><span class="zh">今日思考预算</span><span class="code">THINKING BUDGET</span></div>' +
          '<div class="note mb-2">每天給 AI 的思考費用上限,用完就停主動思考(仅 fallback 決策)。</div>' +
          '<div class="ag-budget"><div class="note">Loading…</div></div>' +
        '</div>' +
        '<div class="panel flex-1">' +
          '<div class="panel-t"><span class="zh">Demo vs LiveDemo 引擎成交</span><span class="code">ENGINE MODE FILLS</span></div>' +
          '<div class="note mb-2">兩边皆真送單到 Bybit demo endpoint;差别在 risk_config 引擎(demo.toml vs live.toml)。非 ExecutorAgent _shadow_mode。</div>' +
          '<div class="ag-fills"><div class="note">Loading…</div></div>' +
        '</div>' +
      '</div>' +

      // ═ 節⑥⑦:最近活動 feed + 治理租約 & 拒單(兩面板)═
      '<div class="row wrap gap-3">' +
        '<div class="panel flex-1">' +
          '<div class="panel-t"><span class="zh">最近活動</span><span class="code">RECENT ACTIVITY</span></div>' +
          '<div class="ag-feed logs"><div class="note">Loading…</div></div>' +
        '</div>' +
        '<div class="panel flex-1">' +
          '<div class="panel-t"><span class="zh">治理租約 &amp; 拒單</span><span class="code">GOVERNANCE &amp; REJECTS</span></div>' +
          '<div class="ag-gov"><div class="note">Loading…</div></div>' +
        '</div>' +
      '</div>' +
    '</div>';

  // ═══ 更新徽(誠實=前端最後成功拉取時間,非後端 generated_at;canon 7 staleness)═══
  function setUpdated(text, tone) {
    var el = q('.ag-updated');
    if (!el) return;
    el.textContent = text;
    el.setAttribute('data-tone', tone || 'muted');
    el.style.setProperty('--tag-tone', toneVar(tone || 'muted'));
  }
  function stampUpdated(ok) {
    if (!ok) { setUpdated('拉取失敗', 'bad'); return; }
    setUpdated('更新 ' + new Date().toLocaleTimeString('zh-CN', { hour12: false }), 'good');
  }

  // 小工具:單條 note(帶 tone 文字色);警語橫幅用。
  function noteLine(text, tone) {
    return '<div class="note ' + toneTextClass(tone) + '">' + esc(text) + '</div>';
  }
  function pick(a, b) { return a != null ? a : (b != null ? b : null); }

  // ═══ 節③:5-Agent Roster(port legacy renderAgentCard + loadAgentRoster)═══
  // Executor 真倉/影子視覺隔離:真倉=t-neg 紅警(用真钱)/ 影子=t-accent(仅模擬)。
  // canon 7:shadow_mode null/undefined → 強制 unknown + 暂停接單警語(fail-loud,信任後端字段)。
  function renderCard(agent) {
    var role = agent.role || 'unknown';
    var state = agent.state || 'unknown';
    var isExecutor = role === 'executor';
    var isLive = false, executorUnclear = false;
    if (isExecutor) {
      if (agent.shadow_mode === false) isLive = true;
      else if (agent.shadow_mode === true) isLive = false;
      else { executorUnclear = true; state = 'unknown'; }   // 契約缺失 → fail-loud
    }
    var isUnknown = state === 'unknown';

    var banner = '';
    if (isExecutor && !executorUnclear) {
      banner = isLive
        ? noteLine('真倉執行中 — 這位 Agent 正在用真钱下單 / Live execution — real funds', 'bad')
        : noteLine('影子模式 — 所有動作仅模擬,不送真單到交易所 / Shadow mode — simulated only', 'accent');
    }
    var unknownBanner = '';
    if (isUnknown) {
      unknownBanner = noteLine(executorUnclear
        ? '后端未回報 shadow_mode 字段,已暂停接單 / Backend missing shadow_mode, intake paused'
        : '状态未确認,已暂停接單 / State unknown, intake paused', 'bad');
    }

    var labelZh = esc(agent.label_zh || role);
    var labelEn = esc(agent.label_en || role);
    var summary = esc(agent.summary_zh || '（暂無概述）');
    var runtimeState = String(agent.runtime_state || '--');
    var runtimeTag = tagHtml('程序 ' + runtimeState, runtimeState === 'running' ? 'good' : 'bad');
    var badge = stateBadge(state, agent.state_label_zh);
    // canon 7:decisions/cost null → EMPTY,絕不假 0(真 0 事件才顯 0)。
    var decisions;
    if (isExecutor) decisions = agent.today_orders != null ? esc(String(agent.today_orders)) : EMPTY;
    else decisions = agent.today_decisions != null ? esc(String(agent.today_decisions)) : EMPTY;
    var decisionLabel = isExecutor ? (executorUnclear ? '今日下單' : (isLive ? '真實成單' : '模擬成單')) : '今日決策';
    var costTxt = balance(agent.today_cost_usd);

    var html = '<div class="panel flex-1">';
    html += banner + unknownBanner;
    html += '<div class="row-between wrap gap-2">' +
      '<div><div class="fs-title fw-semi">' + labelZh + '</div><div class="fs-micro t-muted">' + labelEn + '</div></div>' +
      '<div class="t-right">' + badge + '</div>' +
    '</div>';
    html += '<div class="note mt-2"><span class="t-muted">現在在做:</span>' + summary + '</div>';
    if (agent.state_reason_zh) {
      html += '<div class="note fs-micro t-warn mt-1">状态依據:' + esc(agent.state_reason_zh) + '</div>';
    }
    html += '<div class="row wrap gap-2 fs-micro t-muted mt-2">' +
      '<span>' + runtimeTag + '</span>' +
      '<span>' + heartbeatTag(agent.last_heartbeat_ts) + '</span>' +
      '<span>' + esc(decisionLabel) + ':<strong class="t-primary">' + decisions + '</strong> 笔</span>' +
      '<span>今日成本:<strong class="t-primary">' + costTxt + '</strong></span>' +
    '</div>';
    html += '</div>';
    return html;
  }
  async function loadRoster() {
    var d = await ocApi('/api/v1/agents/roster');
    if (!built) return;
    var box = q('.ag-roster');
    if (!box) return;
    if (!d) { box.innerHTML = noteLine('连不上引擎 — 仪表板迷路了,30 秒后再試 / Failed to load roster', 'warn'); return; }
    var payload = d.data || d;
    var agents = payload.agents || [];
    if (!agents.length) { box.innerHTML = '<div class="note">今天還没有 Agent 開始工作(系統刚啟動)/ No agents active yet</div>'; return; }
    box.innerHTML = '<div class="row wrap gap-3">' + agents.map(renderCard).join('') + '</div>';
    applyTagTones(box);
  }

  // ═══ 節④:思考预算(port legacy loadAgentBudget;圖形進度條 → 文字 + tone tag,守 ratchet)═══
  async function loadBudget() {
    var d = await ocApi('/api/v1/paper/layer2/cost');
    if (!built) return;
    var box = q('.ag-budget');
    if (!box) return;
    if (!d) { box.innerHTML = noteLine('无法載入预算 / Failed to load budget', 'warn'); return; }
    var c = d.data || d;
    var today = c.today || {}, budget = c.budget || {};
    var spent = today.total_usd != null ? Number(today.total_usd) : null;
    var cap = budget.daily_hard_cap_usd != null ? Number(budget.daily_hard_cap_usd) : null;
    var remaining = budget.remaining_usd != null ? Number(budget.remaining_usd) : null;
    if (spent == null && cap == null) { box.innerHTML = '<div class="note">尚未有思考預算資料 / No budget data yet</div>'; return; }

    var spentTxt = spent != null ? balance(spent) : EMPTY;
    var capTxt = cap != null ? balance(cap) : EMPTY;
    var pct = (cap != null && cap > 0 && spent != null) ? Math.min(100, (spent / cap) * 100) : null;
    var tone = 'good';
    if (pct != null) { if (pct >= 90) tone = 'bad'; else if (pct >= 70) tone = 'warn'; }

    var note;
    if (cap === 0) note = '尚未設定每日预算上限';
    else if (pct != null && pct >= 90) note = '预算告急 — Agent 即将停止主動思考(仅 fallback 決策)';
    else if (pct != null && pct >= 70) note = '已用 ' + pct.toFixed(0) + '%,注意節流';
    else if (pct != null) { var rem = remaining != null ? remaining : (cap - spent); note = '剩余 ' + balance(rem) + ' 可供今日思考'; }
    else note = '預算使用率待完整資料 / Usage pending complete data';

    var pctTag = pct != null ? tagHtml('已用 ' + pct.toFixed(0) + '%', tone) : tagHtml('用量未知', 'muted');
    box.innerHTML =
      '<div class="row-between wrap gap-2">' +
        '<span class="fs-dense t-muted">已用 / 上限</span>' +
        '<span class="fs-base fw-semi num">' + spentTxt + ' / ' + capTxt + '</span>' +
      '</div>' +
      '<div class="mt-2">' + pctTag + '</div>' +
      '<div class="note fs-micro ' + toneTextClass(tone) + ' mt-1">' + esc(note) + '</div>';
    applyTagTones(box);
  }

  // ═══ 節⑤:Demo 引擎 vs LiveDemo 引擎成交(port legacy loadShadowLiveDiff)═══
  async function loadFills() {
    var d = await ocApi('/api/v1/agents/shadow_vs_live_summary?since=24h');
    if (!built) return;
    var box = q('.ag-fills');
    if (!box) return;
    if (!d) { box.innerHTML = noteLine('无法載入成交對比 / Failed to load fills', 'warn'); return; }
    var r = d.data || d;
    var demo = r.demo || {}, liveDemo = r.live_demo || {}, diff = r.diff || {};
    var demoCount = demo.count != null ? Number(demo.count) : 0;
    var liveCount = liveDemo.count != null ? Number(liveDemo.count) : 0;
    if (demoCount === 0 && liveCount === 0) { box.innerHTML = '<div class="note">此時段無成交 / No fills in window</div>'; return; }

    // Demo 引擎欄(engine_mode=demo,risk_config_demo.toml)
    var demoCol = '<div class="col gap-1">' +
      '<div class="fs-dense fw-semi">Demo 引擎成交</div>' +
      '<div class="fs-micro t-muted">Bybit demo endpoint · risk_config_demo.toml</div>' +
      '<div class="fs-title fw-semi">' + demoCount + ' 笔</div>';
    if (demo.total_pnl_usd != null) {
      var dCls = Number(demo.total_pnl_usd) >= 0 ? 't-pos' : 't-neg';
      demoCol += '<div class="fs-md ' + dCls + '">PnL ' + money(demo.total_pnl_usd) + '</div>';
    }
    if (demo.avg_slippage_bps != null) demoCol += '<div class="fs-micro t-muted">平均滑点 ' + Number(demo.avg_slippage_bps).toFixed(2) + ' bps</div>';
    demoCol += '</div>';

    // LiveDemo 引擎欄(engine_mode=live_demo,Live 管線走 demo endpoint,risk_config_live.toml)
    var liveCol = '<div class="col gap-1">' +
      '<div class="fs-dense fw-semi t-neg">LiveDemo 引擎成交</div>' +
      '<div class="fs-micro t-muted">Live 管線 · demo endpoint · risk_config_live.toml</div>';
    if (liveCount > 0) {
      liveCol += '<div class="fs-title fw-semi">' + liveCount + ' 笔</div>';
      if (liveDemo.total_pnl_usd != null) {
        var lCls = Number(liveDemo.total_pnl_usd) >= 0 ? 't-pos' : 't-neg';
        liveCol += '<div class="fs-md ' + lCls + '">PnL ' + money(liveDemo.total_pnl_usd) + '</div>';
      }
      if (liveDemo.avg_slippage_bps != null) liveCol += '<div class="fs-micro t-muted">平均滑点 ' + Number(liveDemo.avg_slippage_bps).toFixed(2) + ' bps</div>';
    } else {
      liveCol += '<div class="fs-md t-muted">— 此時段無 LiveDemo 成交 —</div>' +
        '<div class="fs-micro t-muted">流量稀疏 / 引擎運行中(pipeline 状态見 Overview)</div>';
    }
    liveCol += '</div>';

    var html = '<div class="row wrap gap-3">' + demoCol + liveCol + '</div>';

    // 中央 diff 行:fill_rate_delta_pct(≥10% 紅)+ slippage_delta_bps
    var fillDelta = diff.fill_rate_delta_pct, slipDelta = diff.slippage_delta_bps;
    if (fillDelta != null || slipDelta != null) {
      html += '<div class="row wrap gap-3 fs-dense mt-2">';
      if (fillDelta != null) {
        var fillRed = Math.abs(Number(fillDelta)) >= 10;
        var sign = Number(fillDelta) >= 0 ? '+' : '';
        html += '<div>成交率差異(Demo vs LiveDemo):<strong class="' + (fillRed ? 't-neg' : 't-muted') + '">' +
          sign + Number(fillDelta).toFixed(1) + '%</strong>' + (fillRed ? ' <span class="t-neg fs-micro">偏离 ≥10%</span>' : '') + '</div>';
      }
      if (slipDelta != null) {
        var s2 = Number(slipDelta) >= 0 ? '+' : '';
        html += '<div>滑点差異:<strong class="t-primary">' + s2 + Number(slipDelta).toFixed(2) + ' bps</strong></div>';
      }
      html += '</div>';
    }
    box.innerHTML = html;
    applyTagTones(box);
  }

  // ═══ 節⑥:最近活動 feed(port legacy loadAgentFeed;strategist history + shadow fills 合流)═══
  var SOURCE_ZH = {
    manual_promote: '手動晋升', shadow_to_live: '影子→真倉晋升', auto_apply: '自動套用',
    rust_apply: 'Rust 引擎套用', hot_reload: '热重載', rollback: '回滚'
  };
  async function loadFeed() {
    var res = await Promise.allSettled([
      ocApi('/api/v1/strategist/history?engine=demo&limit=10'),
      ocApi('/api/v1/edge/shadow_fills?engine=demo&limit=10')
    ]);
    if (!built) return;
    var box = q('.ag-feed');
    if (!box) return;
    var histR = res[0], fillsR = res[1];
    var histOk = histR.status === 'fulfilled' && histR.value;
    var fillsOk = fillsR.status === 'fulfilled' && fillsR.value;
    if (!histOk && !fillsOk) { box.innerHTML = noteLine('无法載入活動 feed / Failed to load feed', 'warn'); return; }

    var entries = [];
    if (histOk) {
      var histPayload = histR.value.data || histR.value;
      (histPayload.rows || []).forEach(function (h) {
        var strat = h.strategy_name || '?';
        entries.push({
          type: '策略师', tone: 'accent', ts: h.applied_at,
          outcome: SOURCE_ZH[h.source] || h.source || '應用参數', symbol: strat,
          summary: '套用参數: ' + strat + (h.reason ? ' · ' + h.reason : '')
        });
      });
    }
    if (fillsOk) {
      var fillsPayload = fillsR.value.data || fillsR.value;
      (fillsPayload.rows || []).forEach(function (f) {
        var stratLabel = f.strategy_name || f.strategy || '';
        var exitReason = f.exit_reason || '';
        entries.push({
          type: '影子成交', tone: 'accent', ts: f.ts || f.created_at,
          outcome: '影子成交', symbol: f.symbol || '',
          summary: (exitReason ? stratLabel + ' (' + exitReason + ')' : stratLabel) + ' · ' + (f.side || '') + ' · qty ' + (f.qty != null ? f.qty : '--')
        });
      });
    }
    entries.sort(function (a, b) { return new Date(b.ts || 0).getTime() - new Date(a.ts || 0).getTime(); });
    if (!entries.length) { box.innerHTML = '<div class="note">今天還没有活動 / No activity yet</div>'; return; }

    box.innerHTML = entries.slice(0, 15).map(function (e) {
      return '<div class="logblock"><div class="w-full">' +
        '<div class="row-between wrap gap-2">' +
          '<span>' + tagHtml(e.type, e.tone) + ' ' + tagHtml(e.outcome || '--', 'muted') +
            (e.symbol ? ' <strong class="t-primary">' + esc(e.symbol) + '</strong>' : '') + '</span>' +
          '<span class="ts">' + esc(relTime(e.ts)) + '</span>' +
        '</div>' +
        (e.summary ? '<div class="mt-1 t-muted fs-micro lh-cjk">' + esc(e.summary) + '</div>' : '') +
      '</div></div>';
    }).join('');
    applyTagTones(box);
  }

  // ═══ 節⑦:治理租約 & 拒單(port legacy loadAgentGovernance)═══
  function riskLevelTag(level) {
    if (!level) return tagHtml('?', 'muted');
    var lvl = String(level).toUpperCase();
    var tone = lvl === 'P0' ? 'bad' : lvl === 'P1' ? 'warn' : lvl === 'P2' ? 'accent' : 'muted';
    return tagHtml(lvl, tone);
  }
  async function loadGovernance() {
    var res = await Promise.allSettled([
      ocApi('/api/v1/governance/leases'),
      ocApi('/api/v1/agents/recent_rejects?limit=5')
    ]);
    if (!built) return;
    var box = q('.ag-gov');
    if (!box) return;
    var leasesR = res[0], rejectsR = res[1];
    var leasesOk = leasesR.status === 'fulfilled' && leasesR.value;
    var rejectsOk = rejectsR.status === 'fulfilled' && rejectsR.value;
    if (!leasesOk && !rejectsOk) { box.innerHTML = noteLine('无法載入治理資料 / Failed to load governance', 'warn'); return; }

    var leases = leasesOk ? ((leasesR.value.data && (leasesR.value.data.leases || leasesR.value.data.active)) || leasesR.value.data || []) : [];
    var rejects = rejectsOk ? ((rejectsR.value.data && rejectsR.value.data.rows) || rejectsR.value.rows || []) : [];
    if ((!leases || !leases.length) && (!rejects || !rejects.length)) { box.innerHTML = '<div class="note">當前無租約,近期無拒單 / No leases or rejects</div>'; return; }

    var html = '<div class="row wrap gap-3">';
    // 活跃決策租約
    html += '<div class="col flex-1 gap-1"><div class="fs-dense fw-semi">活跃決策租約</div>';
    if (leases && leases.length) {
      html += leases.slice(0, 6).map(function (l) {
        var id = shortId(l.lease_id || l.id || '--');
        return '<div class="logblock"><div class="w-full"><div class="row-between gap-2 fs-micro">' +
          '<span><span class="mono t-accent">' + id + '</span> · ' + esc(l.symbol || '--') + '</span>' +
          '<span class="t-muted">到期 ' + esc(relTime(l.expires_at || l.expiry || l.expires_ts)) + '</span>' +
        '</div></div></div>';
      }).join('');
    } else html += '<div class="note fs-micro">當前没有活跃租約</div>';
    html += '</div>';
    // 守门員拒單(最近 5 條)
    html += '<div class="col flex-1 gap-1"><div class="fs-dense fw-semi">守门員拒單(最近 5 條)</div>';
    if (rejects && rejects.length) {
      html += rejects.slice(0, 5).map(function (rj) {
        return '<div class="logblock"><div class="w-full">' +
          '<div class="row-between gap-2 fs-micro">' +
            '<span><span class="mono t-muted">' + esc(timeShort(rj.ts)) + '</span>｜<strong class="t-primary">' + esc(rj.symbol || '?') + '</strong></span>' +
            riskLevelTag(rj.risk_level) +
          '</div>' +
          '<div class="t-muted fs-micro mt-1">被守门員擋下:' + esc(rj.reason || '--') + '</div>' +
        '</div></div>';
      }).join('');
    } else html += '<div class="note fs-micro">近期無拒單</div>';
    html += '</div></div>';
    box.innerHTML = html;
    applyTagTones(box);
  }

  // ═══ OpenClaw companion hook(view-agents-openclaw.js 註冊 window.OC_AGENTS_OPENCLAW)═══
  function ocCompanion() { return window.OC_AGENTS_OPENCLAW || null; }

  // ═══ 全節載入(5 團隊 GET + openclaw load;Promise.allSettled,任一失敗不拖垮其餘)═══
  async function loadAll() {
    if (!built || loading) return;
    loading = true;
    try {
      var comp = ocCompanion();
      var tasks = [loadRoster(), loadBudget(), loadFills(), loadFeed(), loadGovernance()];
      if (comp && typeof comp.load === 'function') tasks.push(Promise.resolve(comp.load()));
      var res = await Promise.allSettled(tasks);
      if (!built) return;
      stampUpdated(!res.some(function (x) { return x.status === 'rejected'; }));
    } finally {
      loading = false;
    }
  }

  // ═══ 控件接線(僅刷新;純唯讀,無寫路徑)═══
  function wireControls() {
    var btn = q('.ag-refresh');
    if (btn) btn.addEventListener('click', function () { loadAll(); });
  }

  // ═══ 輪詢生命週期(僅可見時運行;pause 必清 → 隱藏不 fetch)═══
  function startPolling() { stopPolling(); timer = setInterval(loadAll, POLL_MS); }
  function stopPolling() { if (timer) { clearInterval(timer); timer = null; } }

  // ═══ shell router 契約:render / resume / pause(second-adapter 擴充點)═══
  // render:建骨架(冪等,只首渲一次);掛 openclaw companion;接線;不啟輪詢(屬 resume)。
  function renderAgentsView(hostEl) {
    if (hostEl) host = hostEl;
    if (!host || built) return;
    host.innerHTML = SKELETON;
    built = true;
    wireControls();
    // 掛 OpenClaw 控制面 companion(缺席則保留骨架降級提示,團隊面照常)。
    var comp = ocCompanion();
    if (comp && typeof comp.render === 'function') {
      try { comp.render(host); }
      catch (e) { console.warn('[view-agents] openclaw companion render 失敗:', e); }
    } else {
      var slot = q('.ag-openclaw');
      if (slot) slot.innerHTML = '<div class="panel note t-warn">OpenClaw 控制面模組未載入;團隊面不受影響 / OpenClaw module not loaded; team view unaffected.</div>';
    }
    paint();                          // 骨架內 .tag(mode 徽 / refresh 徽)首次上色
    setUpdated('loading…', 'muted');
  }
  // resume:view 顯示 → 拉真值 + 啟輪詢。
  function resumeAgentsView() {
    if (!built) return;
    visible = true;
    loadAll();
    startPolling();
  }
  // pause:view 隱藏 → 停輪詢/停後續抓取(freshness/safety:隱藏不得續打後端,
  // 鏡像 iframe openclaw-tab-visibility 暫停語義,非協商)。
  function pauseAgentsView() {
    visible = false;
    stopPolling();
  }

  // 註冊進殼可見的原生 view 表(router 以 v.iframe===false 查此;stable host / 唯一擴充點)。
  window.OC_NATIVE_VIEWS = window.OC_NATIVE_VIEWS || {};
  window.OC_NATIVE_VIEWS['agents'] = { render: renderAgentsView, resume: resumeAgentsView, pause: pauseAgentsView };
  // 具名導出(task 契約:renderAgentsView / pauseAgentsView / resumeAgentsView 可被引用)。
  window.renderAgentsView = renderAgentsView;
  window.resumeAgentsView = resumeAgentsView;
  window.pauseAgentsView = pauseAgentsView;
})();
