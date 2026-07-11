/*
 * view-development.js — 玄衡原生 view「開发 Support」(Phase 2 第 3 個 iframe→原生遷移)
 * ═══════════════════════════════════════════════════════════════════
 * MODULE_NOTE
 * 模塊用途:把 legacy `tab-development.html`(iframe 後備)遷成玄衡殼內的**原生 view**,
 *   延續首遷(view-gates.js status/table 形)+ 二遷(view-monitor.js dashboard 形)所建的
 *   strangler-fig pattern(design/10 recipe §1)——本 view 是**唯讀開发診斷儀表盤**:掃 repo
 *   的 migration / git / TODO / PM handoff / 文档庫存,純狀態展示,零交易/風控關聯。殼 router
 *   為穩定宿主,本檔提供 render/pause/resume 為唯一新增擴充點(second-adapter),與 gates/monitor 同構。
 *   內容逐節守恆(對 legacy 8 節 + disabled 態,零丟失):
 *     ①全局開发状态(header + 5 摘要:Latest Migration / Next Slot / Repo Head / Dirty Files /
 *       Last Scan——前 4 走 KPI,Last Scan 折成頂欄 scan 新鮮度徽,語義即「server-side scan 時刻」);
 *     ②開发焦点(TODO / AgentTodo 摘錄);③最近 PM Handoff;④Migration Intelligence(migrations_dir +
 *       All/Landed/Gaps/Future 篩選 + 表格,landed 列可展開 detail);⑤文档智能(index 層 / markdown
 *       計數 / 最大 cluster / reorg phases);⑥GUI 热交互候選;⑦Useful Commands;⑧Git Context。
 *   刻意變更(canon 守恆非逐像素):legacy 裝飾 emoji(🛠🧭📝🗺…)不遷(canon 1 非數據 chrome 從簡,
 *     對齊 gates/monitor austere 版式);legacy `.dev-migration-card` 展開卡格 + 自帶頁內樣式塊 class
 *     在殼文檔不可用(殼只載 tokens/oc-utilities/shell/shell-components),故 landed detail 改由
 *     **表格內可展開 detail 列**承載(同資料、companions/size/action_counts/header_excerpt/objects
 *     全保留=內容超集不丟失),非沿用 legacy class。
 * 主要函數:renderDevelopmentView(建骨架,冪等)、resumeDevelopmentView(顯示→重讀開发支持態+
 *   拉真值+啟輪詢)、pauseDevelopmentView(隱藏→停輪詢/停 fetch)、applyDevEnabled(disabled/enabled
 *   分支切換)、load(唯一 GET)、renderAll / renderSummary / renderFocus / renderReports /
 *   renderMigrations / renderDocumentation / renderRunbook / renderGit。
 * 依賴(全復用,不重造):common.js ocApi + 開发支持態三 helper(ocReadCachedDevelopmentSupportMode /
 *   ocListenDevelopmentSupportMode——browser-local 設定,非後端寫);common-formatters.js ocEsc /
 *   OC_EMPTY;組件庫 shell-components.css(.panel/.panel-t/.kpis/.kpi/.tbl/.tag/.logs/.logblock/
 *   .note/.code)+ tokens.css(.silk)+ oc-utilities.css(flex/間距/t-* 色階/.hidden/.mono/.pointer)。
 * 硬邊界(canon / LOOP §6):
 *   ① 零寫路徑——development 唯讀:1 個 ocApi GET(/settings/development-status,∈ 5b authoritative,
 *      與 legacy tab-development 同路由),0 POST/order。開发支持 enabled/disabled 是 browser-local
 *      localStorage 設定(common.js),非後端寫。
 *   ② canon 7 三態:loading=骨架「—/loading…」;無真值=「—」/空節提示(絕不假值/假成功);
 *      error(ocApi 回 null)=顯錯不崩,保守標 warn/bad,絕不冒充成功。**disabled 態誠實顯
 *      「開发状态支持未啟用」**(保 legacy dev-locked 分支),不 fake dashboard。
 *   ③ visibility 語義(非協商):隱藏時 pauseDevelopmentView 停輪詢/停後端抓取(鏡像 iframe
 *      openclaw-tab-visibility 暫停),否則隱藏續打後端=freshness/safety 退步。disabled 態亦不 fetch
 *      (dashboard 隱藏,拉真值無意義且徒增後端負載)。
 *   ④ ratchet 0/0/0:零裸 hex、零 inline style 屬性、零內聯樣式區塊;動態 tone 走
 *      .style.setProperty('--tag-tone', var(...)) scoped-var 正法(非樣式屬性字面)。
 * 誠實邊界:靜態(node --check + ratchet + 5b 對齊 + registry/asset smoke)只證 source/路徑事實;
 *   **真渲染正確性 / 三態版式 / 真值 / disabled 分支視覺 = NEEDS-LINUX runtime + operator 視覺**,
 *   不由本刀 attest。
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  // ── 常量 ──
  var POLL_MS = 60000;             // 輪詢間隔(鏡像 legacy ocStartRefresh 60s;僅可見+啟用時運行)
  var STALE_MS = 180000;           // 新鮮度門檻:scan 時刻逾 3min → scan 徽 STALE(canon 7;刷新為 60s)

  // ── 執行期狀態 ──
  var host = null;                 // 原生 <section> 宿主(shell 注入)
  var built = false;               // 骨架是否已建(render 冪等)
  var timer = null;                // 輪詢 interval id(null=停;pause 必清)
  var loading = false;             // fetch 去重(不重入)
  var visible = false;             // view 是否可見(resume=true / pause=false;守 visibility 語義)
  var devEnabled = false;          // 開发支持態(disabled/enabled 分支;browser-local 設定)
  var _payload = null;             // 最近一次 development-status payload(篩選/展開重渲用)
  var _migFilter = 'all';          // migration 篩選(all/landed/gap/future;鏡像 legacy)
  var _expanded = {};              // landed migration 展開集(id→true;鏡像 legacy _expandedMigrations)

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
  // 'plain'/預設回空 class:KPI 值多為中性事實(migration id / sha),用 .v 預設 text-primary,不強上色。
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
  function applyTagTones(root) {
    if (!root) return;
    var tags = root.querySelectorAll('.tag[data-tone]');
    for (var i = 0; i < tags.length; i++) {
      tags[i].style.setProperty('--tag-tone', toneVar(tags[i].getAttribute('data-tone')));
    }
  }

  // 位元組人類可讀(port legacy formatBytes)。
  function formatBytes(n) {
    var value = Number(n || 0);
    if (!value) return '0 B';
    if (value < 1024) return value + ' B';
    return (value / 1024).toFixed(1) + ' KB';
  }

  // ═══ 骨架(canon 7:首渲即 loading 態「—/loading…」,絕不假值)═══
  // 兩大分支容器:.dv-locked-note(disabled 提示,預設 hidden)/ .dv-body(dashboard);
  // 由 applyDevEnabled 依 browser-local 開发支持態切 .hidden(canon 7 誠實 disabled 分支)。
  var SKELETON =
    '<div class="p-4">' +
      // disabled 態誠實提示(未啟用時顯;不 fake dashboard)
      '<div class="dv-locked-note panel note t-warn hidden">' +
        '<div class="fw-semi t-primary">開发状态支持未啟用 / Development Support Disabled</div>' +
        '<div class="note mt-1">請在 Settings 中啟用 Development Support。此页面只顯示全局開发過程状态,不影响交易、風控、live 授權或 engine runtime。</div>' +
      '</div>' +

      '<div class="dv-body">' +
        // ═ 節①:全局開发状态(header + 摘要)═
        '<div class="panel">' +
          '<div class="row-between wrap gap-3">' +
            '<div>' +
              '<div class="panel-t"><span class="zh">全局開发状态</span><span class="code">GLOBAL DEVELOPMENT STATUS</span></div>' +
              '<div class="note">動態掃描 repo 的 migrations、git、TODO、AgentTodo 与 PM handoff;每次刷新重新掃描,新增 migration 自動出現。唯讀,不影响 runtime。</div>' +
            '</div>' +
            '<div class="row wrap gap-2">' +
              '<span class="dv-support tag" data-tone="muted">loading…</span>' +
              '<span class="tag" data-tone="muted">auto refresh 60s</span>' +
              '<button type="button" class="dv-refresh mono fs-dense t-accent pointer">刷新 / Refresh</button>' +
              '<span class="dv-updated tag" data-tone="muted">loading…</span>' +
            '</div>' +
          '</div>' +
        '</div>' +
        // 錯誤橫幅(canon 7:error 顯錯不崩;預設隱藏)
        '<div class="dv-error panel note t-warn hidden"></div>' +
        // KPI 行(1 hero + 3):Latest Migration / Next Slot / Repo Head / Dirty Files
        '<div class="kpis">' +
          '<div class="kpi hero dv-kpi-latest"><div class="silk">LATEST MIGRATION</div><div class="v">' + EMPTY + '</div><div class="d note dv-sub">' + EMPTY + '</div></div>' +
          '<div class="kpi dv-kpi-next"><div class="silk">NEXT SLOT</div><div class="v">' + EMPTY + '</div><div class="d note dv-sub">' + EMPTY + '</div></div>' +
          '<div class="kpi dv-kpi-head"><div class="silk">REPO HEAD</div><div class="v">' + EMPTY + '</div><div class="d note dv-sub">' + EMPTY + '</div></div>' +
          '<div class="kpi dv-kpi-dirty"><div class="silk">DIRTY FILES</div><div class="v">' + EMPTY + '</div><div class="d note dv-sub">' + EMPTY + '</div></div>' +
        '</div>' +

        // ═ 節②③:開发焦点 + 最近 PM Handoff(兩面板)═
        '<div class="row wrap gap-3">' +
          '<div class="panel flex-1">' +
            '<div class="panel-t"><span class="zh">開发焦点</span><span class="code">DEVELOPMENT FOCUS</span></div>' +
            '<div class="dv-focus logs"><div class="note">Loading…</div></div>' +
          '</div>' +
          '<div class="panel flex-1">' +
            '<div class="panel-t"><span class="zh">最近 PM Handoff</span><span class="code">RECENT PM REPORTS</span></div>' +
            '<div class="dv-reports logs"><div class="note">Loading…</div></div>' +
          '</div>' +
        '</div>' +

        // ═ 節④:Migration Intelligence(篩選 + 表格 + 展開 detail)═
        '<div class="panel">' +
          '<div class="row-between wrap gap-2">' +
            '<div class="panel-t"><span class="zh">Migration Intelligence</span><span class="code">MIGRATION INTELLIGENCE</span></div>' +
            '<span class="dv-mig-dir mono fs-micro t-muted">sql/migrations</span>' +
          '</div>' +
          '<div class="dv-mig-filters row wrap gap-3 mb-2">' +
            '<button type="button" class="dv-filter mono fs-dense pointer t-accent" data-filter="all">All</button>' +
            '<button type="button" class="dv-filter mono fs-dense pointer t-muted" data-filter="landed">Landed</button>' +
            '<button type="button" class="dv-filter mono fs-dense pointer t-muted" data-filter="gap">Gaps</button>' +
            '<button type="button" class="dv-filter mono fs-dense pointer t-muted" data-filter="future">Future</button>' +
          '</div>' +
          '<table class="tbl">' +
            '<thead><tr>' +
              '<th>V</th><th>Status</th><th>做了什么 / Purpose</th><th>Phase</th><th>Key Objects</th><th>File</th>' +
            '</tr></thead>' +
            '<tbody class="dv-mig-body"><tr><td colspan="6" class="note">Loading…</td></tr></tbody>' +
          '</table>' +
        '</div>' +

        // ═ 節⑤⑥:文档智能 + GUI 热交互候選(兩面板)═
        '<div class="row wrap gap-3">' +
          '<div class="panel flex-1">' +
            '<div class="panel-t"><span class="zh">文档智能</span><span class="code">DOCUMENTATION INTELLIGENCE</span></div>' +
            '<div class="dv-doc-summary logs"><div class="note">Loading…</div></div>' +
          '</div>' +
          '<div class="panel flex-1">' +
            '<div class="panel-t"><span class="zh">GUI 热交互候選</span><span class="code">HOT GUI CANDIDATES</span></div>' +
            '<div class="dv-doc-hot logs"><div class="note">Loading…</div></div>' +
          '</div>' +
        '</div>' +

        // ═ 節⑦⑧:Useful Commands + Git Context(兩面板)═
        '<div class="row wrap gap-3">' +
          '<div class="panel flex-1">' +
            '<div class="panel-t"><span class="zh">Useful Commands</span><span class="code">USEFUL DEVELOPMENT COMMANDS</span></div>' +
            '<div class="dv-runbook logs"><div class="note">—</div></div>' +
          '</div>' +
          '<div class="panel flex-1">' +
            '<div class="panel-t"><span class="zh">Git Context</span><span class="code">GIT CONTEXT</span></div>' +
            '<div class="dv-git logs"><div class="note">—</div></div>' +
          '</div>' +
        '</div>' +
      '</div>' +
    '</div>';

  // ═══ 值設定器(canon 7:無真值 → EMPTY / 保守 tone,絕不假值)═══
  function setKpi(prefix, value, tone, sub) {
    var v = q('.' + prefix + ' .v');
    if (v) { v.className = ('v ' + toneTextClass(tone)).trim(); v.textContent = (value == null || value === '') ? EMPTY : String(value); }
    var d = q('.' + prefix + ' .dv-sub');
    if (d) { d.textContent = sub || ''; }
  }
  // scan 新鮮度徽(good=已掃 / warn=STALE·無時間 / bad=錯誤);承載 legacy「Last Scan」節。
  function setUpdated(text, tone) {
    var el = q('.dv-updated');
    if (!el) return;
    el.textContent = text;
    el.setAttribute('data-tone', tone || 'muted');
    el.style.setProperty('--tag-tone', toneVar(tone || 'muted'));
  }
  function setUpdatedFrom(epochSec) {
    if (!epochSec) { setUpdated('無掃描時間', 'warn'); return; }
    var ms = Number(epochSec) * 1000;
    if (!Number.isFinite(ms)) { setUpdated('無掃描時間', 'warn'); return; }
    var stale = (Date.now() - ms) > STALE_MS;
    var t = new Date(ms).toLocaleTimeString('zh-CN', { hour12: false });
    setUpdated('scan ' + t + (stale ? ' · STALE' : ''), stale ? 'warn' : 'good');
  }
  function showError(msg) {
    var el = q('.dv-error');
    if (!el) return;
    if (msg) { el.textContent = msg; el.classList.remove('hidden'); }
    else { el.textContent = ''; el.classList.add('hidden'); }
  }

  // ═══ 節①:摘要(port legacy renderSummary;Last Scan 折成 scan 徽)═══
  function renderSummary(payload) {
    var migrations = payload.migrations || {};
    var latest = migrations.latest || {};
    var git = payload.git || {};
    setKpi('dv-kpi-latest', latest.id, 'plain', latest.title || '');
    setKpi('dv-kpi-next', migrations.next_version, 'plain', 'auto-discovered from sql/migrations');
    setKpi('dv-kpi-head', git.sha, 'plain', (git.branch || 'unknown') + ' · ' + (git.subject || ''));
    var dirty = git.dirty_paths || [];
    setKpi('dv-kpi-dirty', (git.dirty_count == null ? EMPTY : git.dirty_count), 'plain',
      dirty.length ? dirty.slice(0, 3).join(', ') : 'clean');
    var dir = q('.dv-mig-dir');
    if (dir) dir.textContent = payload.migrations_dir || 'sql/migrations';
    setUpdatedFrom(payload.generated_at_epoch);
  }

  // 小工具:單條 logblock 事件塊(唯一子節點=內容,不觸發 flex gap;bordered 列表項)。
  function logItem(inner) { return '<div class="logblock"><div>' + inner + '</div></div>'; }
  function emptyNote(msg) { return '<div class="note">' + esc(msg) + '</div>'; }

  // ═══ 節②:開发焦点(port legacy renderFocus;todo 7 + agenttodo 5)═══
  function renderFocus(payload) {
    var ctx = payload.development_context || {};
    var rows = [];
    (ctx.todo_excerpt || []).slice(0, 7).forEach(function (line) {
      rows.push(logItem(esc(line)));
    });
    (ctx.agenttodo_excerpt || []).slice(0, 5).forEach(function (line) {
      rows.push(logItem('<strong class="t-primary">AgentTodo</strong><br>' + esc(line)));
    });
    var box = q('.dv-focus');
    if (box) box.innerHTML = rows.length ? rows.join('') : emptyNote('No development focus docs found');
  }

  // ═══ 節③:最近 PM Handoff(port legacy renderReports)═══
  function renderReports(payload) {
    var reports = ((payload.development_context || {}).recent_pm_reports) || [];
    var box = q('.dv-reports');
    if (!box) return;
    box.innerHTML = reports.length
      ? reports.map(function (r) {
          return logItem('<div class="t-primary">' + esc(r.title || r.file) + '</div>' +
            '<div class="t-muted fs-micro">' + esc(r.file || '') + '</div>');
        }).join('')
      : emptyNote('No PM reports found');
  }

  // ═══ 節④:Migration Intelligence(port legacy renderMigrations;表格 + landed 展開 detail)═══
  // migration 狀態 → tone(landed=good / gap=warn / future=muted;canon 7 中性未達=保守)。
  function migTone(status) {
    if (status === 'landed') return 'good';
    if (status === 'gap') return 'warn';
    return 'muted';
  }
  // SQL 動作計數(port legacy renderActionCounts)→ 中性 tag。
  function actionCountTags(item) {
    var counts = item.action_counts || {};
    var keys = Object.keys(counts);
    if (!keys.length) return '<span class="t-muted">' + EMPTY + '</span>';
    return keys.map(function (k) {
      return tagHtml(k.replace(/_/g, ' ') + ': ' + counts[k], 'muted');
    }).join(' ');
  }
  // 頭部/工作註記摘錄(port legacy renderHeaderExcerpt)。
  function headerExcerpt(item) {
    var rows = item.header_excerpt || [];
    if (!rows.length) return '<div class="t-muted fs-micro">No header comments found</div>';
    return rows.slice(0, 6).map(function (line) {
      return '<div class="mono fs-micro t-muted">' + esc(line) + '</div>';
    }).join('');
  }
  // companion 檔(migration 伴生檔)→ warn tag,無則 EMPTY。
  function companionTags(item) {
    var companions = item.companions || [];
    return companions.length
      ? companions.map(function (c) { return tagHtml(c, 'warn'); }).join(' ')
      : '<span class="t-muted">' + EMPTY + '</span>';
  }
  // landed 列展開 detail(承 legacy 卡展開內容:Source File / Size / Companions / SQL Actions /
  //   Key Objects / Header 全保留=內容超集不丟失)。以 .col + .silk 版式重建,免 legacy card class。
  function migDetailRow(item) {
    var objects = (item.objects || []).slice(0, 8);
    var objectText = objects.length ? objects.join(', ') : EMPTY;
    return '<tr class="dv-mig-detail"><td colspan="6">' +
      '<div class="row wrap gap-3">' +
        '<div class="col"><div class="silk">SOURCE FILE</div><div class="mono fs-micro t-muted">' + esc(item.file || 'no source file') + '</div></div>' +
        '<div class="col"><div class="silk">SIZE</div><div class="note">' + esc(formatBytes(item.size_bytes)) + '</div></div>' +
        '<div class="col"><div class="silk">COMPANIONS</div><div>' + companionTags(item) + '</div></div>' +
        '<div class="col"><div class="silk">SQL ACTIONS</div><div>' + actionCountTags(item) + '</div></div>' +
      '</div>' +
      '<div class="col mt-2"><div class="silk">KEY OBJECTS</div><div class="mono fs-micro t-muted">' + esc(objectText) + '</div></div>' +
      '<div class="col mt-2"><div class="silk">HEADER / WORK NOTES</div><div>' + headerExcerpt(item) + '</div></div>' +
    '</td></tr>';
  }
  function migSummaryRow(item) {
    var isLanded = item.status === 'landed';
    var expanded = !!_expanded[item.id];
    var objects = (item.objects || []).slice(0, 6).join(', ');
    var companions = (item.companions || []).length
      ? '<div class="mt-1">' + (item.companions || []).map(function (c) { return tagHtml(c, 'warn'); }).join(' ') + '</div>'
      : '';
    // landed 列可展開(role=button + tabindex + aria-expanded;caret 提示);非 landed 無 detail。
    var rowAttrs = isLanded
      ? ' class="dv-mig-row pointer" role="button" tabindex="0" data-mig-id="' + esc(item.id || '') + '" aria-expanded="' + (expanded ? 'true' : 'false') + '"'
      : '';
    var caret = isLanded ? (expanded ? '▾ ' : '▸ ') : '';
    return '<tr' + rowAttrs + '>' +
      '<td><span class="mono fw-semi t-accent">' + caret + esc(item.id || '') + '</span></td>' +
      '<td>' + tagHtml(item.status, migTone(item.status)) + '</td>' +
      '<td><div><strong class="t-primary">' + esc(item.title || '') + '</strong></div>' +
        '<div class="note">' + esc(item.purpose || '') + '</div></td>' +
      '<td>' + tagHtml(item.phase || EMPTY, 'muted') + '</td>' +
      '<td><div class="mono fs-micro t-muted">' + esc(objects || EMPTY) + '</div>' + companions + '</td>' +
      '<td><div class="mono fs-micro t-muted">' + esc(item.file || 'no source file') + '</div></td>' +
    '</tr>';
  }
  function renderMigrations(payload) {
    var all = ((payload.migrations || {}).items) || [];
    var items = all.filter(function (item) {
      return _migFilter === 'all' || item.status === _migFilter;
    });
    var body = q('.dv-mig-body');
    if (!body) return;
    if (!items.length) { body.innerHTML = '<tr><td colspan="6" class="note">No rows</td></tr>'; return; }
    var html = items.map(function (item) {
      var row = migSummaryRow(item);
      if (item.status === 'landed' && _expanded[item.id]) row += migDetailRow(item);
      return row;
    }).join('');
    body.innerHTML = html;
    applyTagTones(body);
    wireMigrationRows();
  }
  // landed 列展開/收合(鏡像 legacy toggleMigrationCard;Set 態驅動重渲)。
  function toggleMigration(id) {
    if (_expanded[id]) delete _expanded[id];
    else _expanded[id] = true;
    if (_payload) renderMigrations(_payload);
  }
  function wireMigrationRows() {
    var rows = host ? host.querySelectorAll('.dv-mig-row[data-mig-id]') : [];
    for (var i = 0; i < rows.length; i++) {
      (function (row) {
        var id = row.getAttribute('data-mig-id');
        row.onclick = function () { toggleMigration(id); };
        row.onkeydown = function (ev) {
          if (ev.key !== 'Enter' && ev.key !== ' ') return;
          ev.preventDefault();
          toggleMigration(id);
        };
      })(rows[i]);
    }
  }
  function setMigrationFilter(filter) {
    _migFilter = filter;
    var btns = host ? host.querySelectorAll('.dv-filter') : [];
    for (var i = 0; i < btns.length; i++) {
      var active = btns[i].getAttribute('data-filter') === filter;
      btns[i].classList.toggle('t-accent', active);
      btns[i].classList.toggle('t-muted', !active);
    }
    if (_payload) renderMigrations(_payload);
  }

  // ═══ 節⑤:文档智能(port legacy renderDocumentation 之 summary 半)═══
  function renderDocumentation(payload) {
    var docs = payload.documentation || {};
    var inventory = docs.inventory || {};
    var indexFiles = docs.index_files || {};
    var counts = docs.live_counts || {};
    var clusters = docs.live_clusters || [];
    var phases = inventory.phased_execution || [];
    var rows = [];
    // Index 層:inventory / redirects 存在性 tag + 路徑
    rows.push(logItem(
      '<strong class="t-primary">Index Layer</strong><br>' +
      tagHtml('inventory', indexFiles.document_inventory_present ? 'good' : 'warn') + ' ' +
      tagHtml('redirects', indexFiles.path_redirects_present ? 'good' : 'warn') +
      '<div class="mono fs-micro t-muted">' + esc(indexFiles.document_inventory || 'docs/_indexes/document_inventory.json pending') + '</div>' +
      '<div class="mono fs-micro t-muted">' + esc(indexFiles.path_redirects || 'docs/_indexes/path_redirects.md pending') + '</div>'
    ));
    // Live markdown 計數
    rows.push(logItem(
      '<strong class="t-primary">Live Markdown Counts</strong><br>' +
      tagHtml('docs ' + (counts.docs_markdown || 0), 'muted') + ' ' +
      tagHtml('memory ' + (counts.memory_markdown || 0), 'muted') + ' ' +
      tagHtml('.codex ' + (counts.codex_markdown || 0), 'muted') + ' ' +
      tagHtml('.claude_reports ' + (counts.claude_reports_markdown || 0), 'muted')
    ));
    // 最大 cluster(top 6,按 markdown_count 降序)
    if (clusters.length) {
      var top = clusters.slice().sort(function (a, b) {
        return (b.markdown_count || 0) - (a.markdown_count || 0);
      }).slice(0, 6);
      rows.push(logItem(
        '<strong class="t-primary">Largest Clusters</strong><br>' +
        top.map(function (c) {
          return '<div class="mono fs-micro t-muted">' + esc(c.path || '') + ' · ' + esc(String(c.markdown_count || 0)) + '</div>';
        }).join('')
      ));
    }
    // reorg phases(top 4)
    if (phases.length) {
      rows.push(logItem(
        '<strong class="t-primary">Reorg Phases</strong><br>' +
        phases.slice(0, 4).map(function (p) { return '<div>' + esc(p) + '</div>'; }).join('')
      ));
    }
    var box = q('.dv-doc-summary');
    if (box) { box.innerHTML = rows.join(''); applyTagTones(box); }

    // ═══ 節⑥:GUI 热交互候選(gui_hot_candidates.high)═══
    var hot = ((inventory.gui_hot_candidates || {}).high) || [];
    var hotBox = q('.dv-doc-hot');
    if (hotBox) {
      hotBox.innerHTML = hot.length
        ? hot.map(function (item) {
            return logItem('<strong class="t-primary">' + esc(item.path || '') + '</strong>' +
              '<div class="note">' + esc(item.surface || '') + '</div>' +
              '<div class="mono fs-micro t-muted">' + esc(item.integration || '') + '</div>');
          }).join('')
        : emptyNote('No hot candidates indexed');
    }
  }

  // ═══ 節⑦:Useful Commands(port legacy renderRunbook)═══
  function renderRunbook(payload) {
    var box = q('.dv-runbook');
    if (!box) return;
    var rows = (payload.runbook || []).map(function (item) {
      return logItem('<strong class="t-primary">' + esc(item.label || '') + '</strong>' +
        '<div class="mono fs-micro t-muted">' + esc(item.command || '') + '</div>');
    });
    box.innerHTML = rows.length ? rows.join('') : emptyNote('No runbook commands');
  }

  // ═══ 節⑧:Git Context(port legacy renderGit;recent_commits + dirty_paths)═══
  function renderGit(payload) {
    var git = payload.git || {};
    var rows = [];
    (git.recent_commits || []).forEach(function (c) {
      rows.push(logItem('<span class="mono fs-micro t-accent">' + esc(c.sha || '') + '</span> ' + esc(c.subject || '')));
    });
    if (git.dirty_paths && git.dirty_paths.length) {
      rows.push(logItem('<strong class="t-primary">Dirty paths</strong>' +
        '<div class="mono fs-micro t-muted pre-line">' + esc(git.dirty_paths.join('\n')) + '</div>'));
    }
    var box = q('.dv-git');
    if (box) box.innerHTML = rows.length ? rows.join('') : emptyNote('No git context available');
  }

  // ═══ 全節渲染 ═══
  function renderAll(payload) {
    showError('');
    renderSummary(payload);
    renderFocus(payload);
    renderReports(payload);
    renderMigrations(payload);
    renderDocumentation(payload);
    renderRunbook(payload);
    renderGit(payload);
    applyTagTones(host);
  }

  // 無真值(payload 缺)→ 一律 —/空節提示,絕不假值(canon 7)。
  function renderEmpty() {
    setKpi('dv-kpi-latest', EMPTY, 'warn', 'development status 無資料');
    setKpi('dv-kpi-next', EMPTY, 'warn', EMPTY);
    setKpi('dv-kpi-head', EMPTY, 'warn', EMPTY);
    setKpi('dv-kpi-dirty', EMPTY, 'warn', EMPTY);
    var body = q('.dv-mig-body');
    if (body) body.innerHTML = '<tr><td colspan="6" class="note">Unable to load development status</td></tr>';
    setUpdated('無資料', 'warn');
  }
  // error(ocApi 回 null)→ 顯錯不崩,保守標 warn/bad,絕不冒充成功(canon 7)。
  function renderError(msg) {
    setKpi('dv-kpi-latest', '錯誤', 'warn', msg);
    var body = q('.dv-mig-body');
    if (body) body.innerHTML = '<tr><td colspan="6" class="note t-warn">' + esc(msg) + '</td></tr>';
    setUpdated('錯誤', 'bad');
    showError(msg);
  }

  // ═══ 資料抓取(per-view;唯一 GET,∈ 5b 對齊 authoritative;與 legacy 同路由)═══
  // 用裸名 ocApi 而非 window.ocApi:①common.js 先於本檔載入,ocApi 為 global,裸引安全;
  //   ②5b 對齊 ratchet 的 wrapper 偵測器有 (?<![.\w]) 前瞻,裸名才被抽取驗證路由 ∈ authoritative。
  async function load() {
    if (!built || loading || !devEnabled) return;   // disabled 態不 fetch(dashboard 隱藏,拉真值無意義)
    loading = true;
    try {
      var d = await ocApi('/api/v1/settings/development-status');
      if (!built) return;                            // 已卸載/未建 → 不寫 DOM
      if (d == null) { renderError('開发状态載入失敗(HTTP / 網路)'); return; }
      var payload = (d && d.data) ? d.data : d;      // legacy:d.data || d(payload 可能未包 data)
      if (!payload) { renderEmpty(); return; }
      _payload = payload;
      renderAll(payload);
    } finally {
      loading = false;
    }
  }

  // ═══ 開发支持 disabled/enabled 分支(browser-local 設定;非後端寫)═══
  // 誠實 disabled:未啟用時顯提示、隱 dashboard、停輪詢/不 fetch(canon 7 不 fake dashboard)。
  function applyDevEnabled(enabled) {
    devEnabled = !!enabled;
    var note = q('.dv-locked-note');
    var body = q('.dv-body');
    if (note) note.classList.toggle('hidden', devEnabled);
    if (body) body.classList.toggle('hidden', !devEnabled);
    var chip = q('.dv-support');
    if (chip) {
      chip.textContent = devEnabled ? 'Development Support Enabled' : 'Development Support Disabled';
      chip.setAttribute('data-tone', devEnabled ? 'good' : 'muted');
      chip.style.setProperty('--tag-tone', toneVar(devEnabled ? 'good' : 'muted'));
    }
    // 啟用 + 可見 → 拉真值 + 啟輪詢;否則停輪詢(disabled 或隱藏皆不打後端)。
    if (devEnabled && visible) { load(); startPolling(); }
    else { stopPolling(); }
  }
  function readCachedMode() {
    return (typeof window.ocReadCachedDevelopmentSupportMode === 'function')
      ? window.ocReadCachedDevelopmentSupportMode() : false;
  }

  // ═══ 控件接線(刷新 / 篩選;皆唯讀,無寫路徑)═══
  function wireControls() {
    var btn = q('.dv-refresh');
    if (btn) btn.addEventListener('click', function () { load(); });
    var filters = host ? host.querySelectorAll('.dv-filter') : [];
    for (var i = 0; i < filters.length; i++) {
      (function (f) {
        f.addEventListener('click', function () { setMigrationFilter(f.getAttribute('data-filter')); });
      })(filters[i]);
    }
  }

  // ═══ 輪詢生命週期(僅可見+啟用時運行;pause 必清 → 隱藏不 fetch)═══
  function startPolling() {
    stopPolling();
    timer = setInterval(load, POLL_MS);
  }
  function stopPolling() {
    if (timer) { clearInterval(timer); timer = null; }
  }

  // ═══ shell router 契約:render / resume / pause(second-adapter 擴充點)═══
  // render:建骨架(冪等,只首渲一次);讀 browser-local 開发支持態設初始分支;不啟輪詢(屬 resume)。
  function renderDevelopmentView(hostEl) {
    if (hostEl) host = hostEl;
    if (!host || built) return;
    host.innerHTML = SKELETON;
    built = true;
    wireControls();
    // 監聽開发支持態切換(Settings 端經 postMessage / CustomEvent 廣播;browser-local)。
    if (typeof window.ocListenDevelopmentSupportMode === 'function') {
      window.ocListenDevelopmentSupportMode(applyDevEnabled);
    }
    applyDevEnabled(readCachedMode());     // 初始分支(此時 visible=false → 不啟輪詢)
    setUpdated('loading…', 'warn');
  }
  // resume:view 顯示 → 重讀開发支持態(暫停期間可能被切換)+(若啟用)拉真值 + 啟輪詢。
  function resumeDevelopmentView() {
    if (!built) return;
    visible = true;
    applyDevEnabled(readCachedMode());     // enabled+visible → load + startPolling
  }
  // pause:view 隱藏 → 停輪詢/停後續抓取(freshness/safety:隱藏不得續打後端,
  // 鏡像 iframe openclaw-tab-visibility 暫停語義,非協商)。
  function pauseDevelopmentView() {
    visible = false;
    stopPolling();
  }

  // 註冊進殼可見的原生 view 表(router 以 v.iframe===false 查此;stable host / 唯一擴充點)。
  window.OC_NATIVE_VIEWS = window.OC_NATIVE_VIEWS || {};
  window.OC_NATIVE_VIEWS['development'] = { render: renderDevelopmentView, resume: resumeDevelopmentView, pause: pauseDevelopmentView };
  // 具名導出(task 契約:renderDevelopmentView / pauseDevelopmentView / resumeDevelopmentView 可被引用)。
  window.renderDevelopmentView = renderDevelopmentView;
  window.resumeDevelopmentView = resumeDevelopmentView;
  window.pauseDevelopmentView = pauseDevelopmentView;
})();
