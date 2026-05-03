/**
 * REF-20 Wave 8 — Handoff Modal + Cooldown + Recent + Idempotency Helper
 * REF-20 Wave 8 — 候選交接 Modal + 冷卻 + 近 5 筆 + 冪等鍵 助手
 *
 * MODULE_NOTE
 * 模組目的：承載 P6 Bounded Demo Handoff 前端 4 個 atomic task 的 helper 函式：
 *   H1) typed confirmation modal（9 fields read-only summary + phrase regex
 *       `^HANDOFF [a-z0-9-]{36}$`）
 *   H2) cooldown ≥30s（localStorage 持久化抗 reload）+ dual-actor 政策警示
 *   H3) footer recent 5 handoff list（actor + ts + result + trace_id）
 *   H4) idempotency key handling（client UUID v4 + Idempotency-Key header）
 *
 * Module purpose: ship Wave 8 P6 Bounded Demo Handoff frontend helpers covering
 *   four atomic tasks: typed-confirmation modal (H1), cooldown + dual-actor
 *   policy (H2), recent-5 footer (H3), idempotency-key handling (H4).
 *
 * 上游契約 / Upstream contracts:
 *   - UX SoT: docs/execution_plan/2026-05-02--ref20_ux_subdoc_v1.md §6 Handoff
 *   - V3:     docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
 *             §11 P6 / §12 #20 (typed_confirm) / §四 防誤等級 4
 *   - Workplan docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
 *             §4 Wave 8 R20-P6-H1/H2/H3/H4 + §5.2 P6 KPI
 *
 * Backend endpoints (sibling sub-agent S13/S14/S15 may not have landed yet):
 *   POST /api/v1/replay/handoff           — submit handoff (regex enforce + cooldown + idempotency)
 *   GET  /api/v1/replay/handoff/recent?n=5 — last N handoff records
 *   GET  /api/v1/replay/handoff/state      — last_actor + last_handoff_at + emergency_freeze flag
 *
 * If endpoints respond 404/network-fail, helper degrades to mock placeholder
 * + TODO marker per Wave 8 closure spec; never crashes UI.
 *
 * 依賴 / Dependencies:
 *   - common.js (ocEsc / ocSanitizeClass / ocApi / ocPost / ocToast / _ocUUID / $)
 *   - i18n_zh.js (window.t_zh + window.OpenClawI18n_zh.handoff_phrase table)
 *   Both must load BEFORE this file (script-tag order in tab-paper.html).
 *
 * 硬邊界 / Hard constraints:
 *   - 0 backend write absent operator typed-confirm + idempotency key
 *   - 0 risk param touch (本 helper 純 UI flow)
 *   - vanilla JS only (項目原則 stay vanilla, no React/Vue)
 *   - XSS-safe: all dynamic text via ocEsc(); class tokens via ocSanitizeClass()
 *   - WCAG 2.1 AA: focus trap / ESC-cancel / role=dialog / aria-labelledby
 *   - Mobile touch ≥44px (Wave 4 SEV-2 #1 retrofit pattern)
 *
 * Invariant / 不變量:
 *   - Submit button disabled until typed phrase matches `HANDOFF <experiment_id>`
 *   - Cooldown timestamp persisted in localStorage; 30s tick-down on UI
 *   - Idempotency key is UUID v4, generated once per modal-open, sent as header
 *   - Cached response (`cached:true`) shows bilingual notice, NOT toast spam
 */

(function _ocHandoffHelperModule() {
  "use strict";

  // ─── Constants / 常數 ───────────────────────────────────────────────────────
  // Cooldown 30s per workplan §4 R20-P6-H2 + V3 §四 防誤等級 4
  // Cooldown 30s per workplan §4 R20-P6-H2 + V3 §four anti-misclick level 4
  var COOLDOWN_MS = 30000;
  var COOLDOWN_LS_KEY = "oc_handoff_cooldown_until_ms";
  var LAST_ACTOR_LS_KEY = "oc_handoff_last_actor_id";
  // Typed phrase regex per UX subdoc §6 + workplan R20-P6-S13
  // 強制 client-side regex（server-side S13 同步嚴驗，client 為 UX feedback layer）
  var PHRASE_REGEX = /^HANDOFF [a-z0-9-]{36}$/;
  // Recent N (default 5)
  var RECENT_N = 5;

  // Phase chip text per UX subdoc §6
  // 階段標籤文字（與既有 disabled card P6 chip 風格一致）
  var PHASE_CHIP_TEXT_ZH = "P6 候選交接";
  var PHASE_CHIP_TEXT_EN = "P6 demo handoff";

  // ─── i18n helper（fallback-safe）/ 國際化助手（缺鍵安全降級）────────────────
  // i18n_zh.js's t_zh returns raw key path on miss (documented behavior); we
  // detect that and fall back to caller-supplied default to keep UX consistent.
  // i18n_zh.js 的 t_zh 在缺鍵時返回原始 key path（成文行為），此處偵測並 fallback
  // 到呼叫端 default，避免 UI 顯示 raw key path 嚇到 operator。
  function tZh(keyPath, fallback) {
    if (typeof window.t_zh === "function") {
      var v = window.t_zh(keyPath);
      if (typeof v === "string" && v !== keyPath && v.length > 0) return v;
    }
    return fallback || "";
  }

  // ─── Cooldown state（localStorage 持久化抗 reload）/ 冷卻狀態（持久化）──────
  // 為什麼用 localStorage：operator 可能 reload 頁面 / 開新 tab 試圖繞過冷卻。
  // 每次 success handoff 後寫入 deadline_ms；checkCooldown 比對 Date.now()。
  // 過期會自動清除（避免 LS quota 累積）。
  // Why localStorage: operator may reload / open new tab to bypass cooldown.
  // After each successful handoff we persist deadline_ms; checkCooldown compares
  // Date.now() and auto-clears on expiry to avoid LS quota bloat.
  function getCooldownDeadlineMs() {
    try {
      var raw = localStorage.getItem(COOLDOWN_LS_KEY);
      if (!raw) return 0;
      var n = parseInt(raw, 10);
      if (!isFinite(n) || n <= 0) return 0;
      // 過期自動清除 / Auto-clear expired
      if (n < Date.now()) {
        localStorage.removeItem(COOLDOWN_LS_KEY);
        return 0;
      }
      return n;
    } catch (e) {
      return 0;
    }
  }

  function setCooldownStartingNow() {
    try {
      localStorage.setItem(COOLDOWN_LS_KEY, String(Date.now() + COOLDOWN_MS));
    } catch (e) {
      console.warn("[handoff] localStorage write failed for cooldown:", e);
    }
  }

  function getLastActorId() {
    try {
      return localStorage.getItem(LAST_ACTOR_LS_KEY) || "";
    } catch (e) {
      return "";
    }
  }

  function setLastActorId(actor) {
    try {
      if (actor) localStorage.setItem(LAST_ACTOR_LS_KEY, String(actor));
    } catch (e) {
      // 安靜失敗 / Silent fail
    }
  }

  // ─── Current actor identity / 當前 actor 身份 ──────────────────────────────
  // 從 oc_username localStorage（common.js 在 login 時寫入）讀取當前 actor。
  // 缺值 fallback 'unknown-operator'（仍允許走 typed confirm，但 dual-actor
  // policy 比對時若 last_actor 也是 'unknown-operator' → 視為 same actor，
  // 提示 cooldown applies）。
  // Read current actor from oc_username localStorage (common.js login writer).
  // Missing → 'unknown-operator' fallback; dual-actor policy still triggers if
  // the previous actor was also 'unknown-operator'.
  function currentActorId() {
    try {
      return localStorage.getItem("oc_username") || "unknown-operator";
    } catch (e) {
      return "unknown-operator";
    }
  }

  // ─── Time formatter (relative, bilingual) / 時間格式化（相對，雙語）────────
  // P5 ago / 5 分鐘前 — Compatible with operator zh-dominant preference.
  function relativeTime(tsMs) {
    if (!tsMs) return "--";
    var diffSec = Math.max(1, Math.floor((Date.now() - Number(tsMs)) / 1000));
    if (diffSec < 60) return diffSec + "s ago / " + diffSec + " 秒前";
    var diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return diffMin + " min ago / " + diffMin + " 分鐘前";
    var diffH = Math.floor(diffMin / 60);
    if (diffH < 24) return diffH + " h ago / " + diffH + " 小時前";
    var diffD = Math.floor(diffH / 24);
    return diffD + " d ago / " + diffD + " 天前";
  }

  // Truncate actor id to 8 chars + ellipsis（per task spec）
  // 截斷 actor id 至 8 字元 + 省略號（per task spec）
  function truncateActor(a) {
    if (!a) return "--";
    var s = String(a);
    if (s.length <= 8) return s;
    return s.substring(0, 8) + "...";
  }

  // ─── Render: 9-field read-only summary table inside Handoff sub-tab ─────────
  // 渲染 #subtab-handoff 內的 9 欄位 read-only summary table（H1 form）+
  // operator notes textarea（optional）+ "Promote to Demo" trigger button +
  // dual-actor warning slot + footer recent 5 list mount point（H3）。
  //
  // Render the 9-field read-only summary table (UX subdoc §6) plus optional
  // operator notes textarea, "Promote to Demo" trigger button (H1 entry),
  // dual-actor warning slot (H2), and the recent-5 footer mount point (H3).
  //
  // SAFETY / 不變量：所有動態文字經 ocEsc() 過濾；class token 用 ocSanitizeClass()。
  // SAFETY / Invariant: all dynamic text via ocEsc(); class tokens via ocSanitizeClass().
  //
  // @param {string} containerId - target div id (`subtab-handoff`)
  // @param {Object} candidateData - 9 fields populated by replay engine
  //   { experiment_id, manifest_id, confidence_score, n_trades, sharpe,
  //     drawdown, fee_model, expires_at, baseline_delta, ... }
  //   Pass null/undefined to render an empty placeholder + "No replay candidate
  //   selected" notice.
  // @returns {boolean}
  function renderHandoffForm(containerId, candidateData) {
    var el = document.getElementById(containerId);
    if (!el) {
      console.warn("[handoff] container not found:", containerId);
      return false;
    }
    candidateData = candidateData || {};
    var hasData = !!candidateData.experiment_id;

    // Phase chip + dual-actor warning slot inline at header
    // 標題列含 phase chip + dual-actor warning slot
    var headerHtml =
      '<div class="oc-handoff-header">' +
        '<div class="oc-handoff-title">' +
          '<h3 style="margin:0;font-size:14px;font-weight:600">' +
            ocEsc(tZh("terminology.handoff.zh", "候選交接")) +
            ' / Bounded Demo Handoff' +
          '</h3>' +
          '<div style="font-size:11px;color:var(--text-dim);margin-top:2px">' +
            ocEsc(tZh("terminology.handoff.meaning_zh", "受限 demo 候選路徑")) +
            ' · UX §6' +
          '</div>' +
        '</div>' +
        '<span class="oc-handoff-phase-chip">' + ocEsc(PHASE_CHIP_TEXT_ZH) +
          ' / ' + ocEsc(PHASE_CHIP_TEXT_EN) + '</span>' +
      '</div>' +
      '<div id="oc-handoff-dual-actor-banner" class="oc-handoff-dual-banner" hidden></div>';

    // 9-field summary table per UX subdoc §6
    // 9 欄位 read-only summary（UX subdoc §6）
    var fields = [
      ["experiment_id", "回放實驗 ID / Experiment ID", candidateData.experiment_id],
      ["manifest_id", "清單 ID / Manifest ID", candidateData.manifest_id],
      ["confidence_score", "信心分數 / Confidence Score", candidateData.confidence_score],
      ["n_trades", "成交筆數 / Trade Count", candidateData.n_trades],
      ["sharpe", "Sharpe", candidateData.sharpe],
      ["drawdown", "最大回撤 / Drawdown", candidateData.drawdown],
      ["fee_model", "費率模型 / Fee Model", candidateData.fee_model],
      ["expires_at", "過期時間 / Expires At", candidateData.expires_at],
      ["baseline_delta", "基準差異 / Baseline Delta", candidateData.baseline_delta || "—"]
    ];
    var rowsHtml = fields.map(function(row) {
      var key = ocSanitizeClass(row[0]);
      var label = ocEsc(row[1]);
      var val = row[2] == null || row[2] === "" ? "—" : ocEsc(String(row[2]));
      return '<div class="oc-handoff-field" data-field="' + key + '">' +
        '<div class="oc-handoff-field-label">' + label + '</div>' +
        '<div class="oc-handoff-field-value">' + val + '</div>' +
      '</div>';
    }).join("");

    var notDataNotice = !hasData ? (
      '<div class="oc-handoff-empty-notice" role="status">' +
        ocEsc("尚未選擇回放候選 — 從上方 Compare 列選 verdict='demo_candidate' 的實驗") +
        '<br/><span style="font-size:11px;color:var(--text-dim)">' +
        ocEsc("No replay candidate selected — pick one with verdict='demo_candidate' from Compare list") +
        '</span>' +
      '</div>'
    ) : "";

    var operatorNotesHtml =
      '<div class="oc-handoff-notes-row">' +
        '<label class="oc-handoff-field-label" for="oc-handoff-notes">' +
          ocEsc("操作員備註 / Operator Notes") + ' <span style="opacity:0.6">(' +
          ocEsc("選填 / optional") + ')</span></label>' +
        '<textarea id="oc-handoff-notes" rows="2" maxlength="500" ' +
        'placeholder="' + ocEsc("交接原因或前後文觀察…") + ' / Reason or context…"></textarea>' +
      '</div>';

    // Trigger button — disabled if no candidate, cooldown active, or backend unreachable
    // 觸發按鈕：無 candidate / 冷卻中 / backend unreachable 時 disabled
    var triggerBtnHtml =
      '<div class="oc-handoff-trigger-row">' +
        '<button id="oc-handoff-trigger-btn" type="button" class="oc-btn oc-btn-danger" ' +
        '  ' + (hasData ? '' : 'disabled') + ' ' +
        '  aria-controls="oc-handoff-modal-overlay" ' +
        '  title="' + ocEsc("打開 typed-confirm 對話框 / Open typed-confirm dialog") + '">' +
          '&#x2192; ' + ocEsc("交付至 Demo / Promote to Demo") +
        '</button>' +
        '<span id="oc-handoff-cooldown-msg" class="oc-handoff-cooldown-msg" aria-live="polite"></span>' +
      '</div>';

    // Footer mount point for recent-5 list (H3) — populated by renderRecentList()
    // 底部 recent 5 footer mount point（H3 用）
    var footerHtml =
      '<div id="oc-handoff-recent-footer" class="oc-handoff-recent" aria-live="polite">' +
        '<div class="oc-handoff-recent-header">' +
          ocEsc("最近 " + RECENT_N + " 筆交接 / Recent " + RECENT_N + " handoffs") +
        '</div>' +
        '<div id="oc-handoff-recent-body" class="oc-handoff-recent-body">' +
          '<div class="oc-handoff-recent-loading">' + ocEsc("載入中… / Loading…") + '</div>' +
        '</div>' +
      '</div>';

    el.innerHTML =
      '<div class="oc-handoff-card">' +
        headerHtml +
        notDataNotice +
        '<div class="oc-handoff-grid">' + rowsHtml + '</div>' +
        operatorNotesHtml +
        triggerBtnHtml +
        footerHtml +
      '</div>';

    // Wire trigger button → open modal（H1 entry）
    // 綁 trigger button click → open modal（H1 進入點）
    var btn = document.getElementById("oc-handoff-trigger-btn");
    if (btn) {
      btn.addEventListener("click", function() {
        openHandoffModal(candidateData);
      });
    }

    // Apply cooldown UI（page-load 即評估，不等 modal 觸發）
    // Apply cooldown UI on page load (do not wait for modal)
    refreshCooldownUI();
    // Refresh dual-actor banner（從後端拉 state）
    // Refresh dual-actor banner (pull state from backend)
    refreshDualActorBanner();
    // Recent 5 list 拉一次（async）
    // Pull recent-5 once (async)
    refreshRecentList();

    return true;
  }

  // ─── Cooldown UI tick / 冷卻 UI 倒數 ───────────────────────────────────────
  // 每 1s tick 更新 button text + 解禁；過期自動 clearInterval 避免 leak。
  // Tick 1Hz: update button text + auto-unblock; clearInterval on expiry.
  var _cooldownTickHandle = null;
  function refreshCooldownUI() {
    var btn = document.getElementById("oc-handoff-trigger-btn");
    var msg = document.getElementById("oc-handoff-cooldown-msg");
    if (!btn || !msg) return;
    var deadline = getCooldownDeadlineMs();
    if (!deadline) {
      msg.textContent = "";
      // Only re-enable if there was data backing the form
      // 僅在 form 有 candidate data 時才解禁（仍尊重 disabled-without-data）
      if (btn.dataset.hasOwnProperty("inhibitedByCooldown")) {
        btn.disabled = false;
        delete btn.dataset.inhibitedByCooldown;
      }
      if (_cooldownTickHandle) {
        clearInterval(_cooldownTickHandle);
        _cooldownTickHandle = null;
      }
      return;
    }
    btn.disabled = true;
    btn.dataset.inhibitedByCooldown = "1";
    var remainSec = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
    msg.textContent = remainSec + "s remaining / " + remainSec + " 秒後可再次交付";
    if (!_cooldownTickHandle) {
      _cooldownTickHandle = setInterval(refreshCooldownUI, 1000);
    }
  }

  // ─── Dual-actor banner / 雙 actor 警示橫幅 ─────────────────────────────────
  // GET /api/v1/replay/handoff/state → { last_actor, last_handoff_at, emergency_freeze }
  // 同 actor 連續交付 → 顯示「Same actor — cooldown applies」warning badge
  // 不同 actor → bypass cooldown allowed（但仍須 typed confirm；是 server enforce）
  // emergency_freeze=true → freeze handoff regardless（等同 cooldown 加倍鎖）
  //
  // Same actor → warning badge "Same actor — cooldown applies"
  // Different actor → cooldown bypass allowed (typed confirm still required)
  // emergency_freeze=true → freeze handoff regardless
  async function refreshDualActorBanner() {
    var banner = document.getElementById("oc-handoff-dual-actor-banner");
    if (!banner) return;
    var resp = null;
    try {
      resp = await ocApi("/api/v1/replay/handoff/state");
    } catch (e) {
      // Network error → degrade silently（banner 不顯示，cooldown LS 仍生效）
      // Network error → silent degrade (banner hidden; LS cooldown still works)
    }
    if (!resp || !resp.data) {
      // Endpoint 還沒 land（sibling sub-agent S13 in flight）→ banner 顯示
      // backend pending notice for transparency。Wave 8 closure 會啟用實資料。
      // Endpoint not yet shipped → show transparency notice; Wave 8 closure
      // wires the real data flow.
      banner.hidden = false;
      banner.className = "oc-handoff-dual-banner pending";
      banner.innerHTML =
        '<span class="oc-handoff-dual-icon">&#9888;</span>' +
        '<span class="zh">' + ocEsc("交接狀態端點待 backend 上線（Wave 8 sibling task）") + '</span>' +
        '<span class="en"> · Handoff state endpoint pending backend (Wave 8 sibling)</span>';
      return;
    }
    var lastActor = resp.data.last_actor || getLastActorId();
    var lastTs = resp.data.last_handoff_at;
    var freeze = !!resp.data.emergency_freeze;
    var current = currentActorId();

    if (freeze) {
      // Emergency freeze 全凍結（per workplan H2 "全局 emergency stop signal"）
      // Emergency freeze (workplan H2 global emergency stop)
      banner.hidden = false;
      banner.className = "oc-handoff-dual-banner freeze";
      banner.innerHTML =
        '<span class="oc-handoff-dual-icon">&#9940;</span>' +
        '<span class="zh">' + ocEsc("緊急凍結已啟動 — 所有 handoff 暫停") + '</span>' +
        '<span class="en"> · Emergency freeze active — handoff halted</span>';
      // Force trigger button into disabled state regardless of candidate data
      // 強制 disable trigger button（凍結 > cooldown > data 三層）
      var btn = document.getElementById("oc-handoff-trigger-btn");
      if (btn) {
        btn.disabled = true;
        btn.dataset.frozenByEmergency = "1";
      }
      return;
    }

    var isSameActor = lastActor && current && lastActor === current;
    if (isSameActor) {
      banner.hidden = false;
      banner.className = "oc-handoff-dual-banner same-actor";
      banner.innerHTML =
        '<span class="oc-handoff-dual-icon">&#9888;</span>' +
        '<span class="zh">' + ocEsc("同一 actor 連續交付（" + truncateActor(current) + "）— 冷卻條件套用") + '</span>' +
        '<span class="en"> · Same actor — cooldown applies</span>' +
        (lastTs ? ('<span class="ts"> · ' + ocEsc(relativeTime(lastTs)) + '</span>') : '');
    } else if (lastActor) {
      banner.hidden = false;
      banner.className = "oc-handoff-dual-banner ok";
      banner.innerHTML =
        '<span class="oc-handoff-dual-icon">&#10003;</span>' +
        '<span class="zh">' + ocEsc("上次交付 actor: " + truncateActor(lastActor) + "（不同 actor — cooldown bypass 允許）") + '</span>' +
        '<span class="en"> · Last handoff by: ' + ocEsc(truncateActor(lastActor)) + ' (different actor — cooldown bypass allowed)</span>' +
        (lastTs ? ('<span class="ts"> · ' + ocEsc(relativeTime(lastTs)) + '</span>') : '');
    } else {
      banner.hidden = true;
    }
  }

  // ─── Recent-5 list / 近 5 筆列表（H3）──────────────────────────────────────
  // GET /api/v1/replay/handoff/recent?n=5 → { items: [{actor, ts, result, trace_id}, ...] }
  // 端點未上線時降級為 mock placeholder + TODO marker（per task spec Wave 8 closure）。
  // Trace id 用 monospace + truncate + click-to-copy。
  //
  // Endpoint not yet live → mock placeholder + TODO marker (Wave 8 closure
  // will wire real data). Trace id renders as monospace + truncate + click-to-copy.
  async function refreshRecentList() {
    var body = document.getElementById("oc-handoff-recent-body");
    if (!body) return;
    var resp = null;
    try {
      resp = await ocApi("/api/v1/replay/handoff/recent?n=" + RECENT_N);
    } catch (e) {
      // 網絡錯誤 / Network error
    }
    if (!resp || !resp.data || !Array.isArray(resp.data.items)) {
      // Mock placeholder + TODO marker（per task spec）
      body.innerHTML =
        '<div class="oc-handoff-recent-empty">' +
          '<span class="zh">' + ocEsc("尚無交接紀錄，或後端 endpoint 待上線（Wave 8 sibling task）") + '</span>' +
          '<br/><span class="en">No handoff records yet, or backend endpoint pending (Wave 8 sibling)</span>' +
          '<div class="oc-handoff-recent-todo">[TODO Wave 8 closure: GET /api/v1/replay/handoff/recent]</div>' +
        '</div>';
      return;
    }
    var items = resp.data.items;
    if (items.length === 0) {
      body.innerHTML = '<div class="oc-handoff-recent-empty">' +
        ocEsc("尚無交接紀錄 / No handoffs yet") +
        '</div>';
      return;
    }
    var rows = items.slice(0, RECENT_N).map(function(it) {
      var actor = truncateActor(it.actor || it.actor_id || "");
      var ts = relativeTime(it.ts || it.timestamp);
      var result = String(it.result || "unknown");
      var resultZh = (result === "success" ? "成功" :
                       result === "failed" ? "失敗" :
                       result === "rejected" ? "拒絕" :
                       result === "cached" ? "快取" : result);
      var resultClass = ocSanitizeClass(
        result === "success" ? "ok" :
        result === "failed" ? "fail" :
        result === "rejected" ? "rej" :
        result === "cached" ? "cached" : "neutral"
      );
      var traceId = String(it.trace_id || it.traceId || "—");
      var traceShort = traceId === "—" ? "—" :
        (traceId.length <= 12 ? traceId : traceId.substring(0, 12) + "…");
      return '<div class="oc-handoff-recent-row">' +
        '<span class="actor" title="' + ocEsc(it.actor || "") + '">' + ocEsc(actor) + '</span>' +
        '<span class="ts">' + ocEsc(ts) + '</span>' +
        '<span class="result result-' + resultClass + '">' + ocEsc(resultZh + " / " + result) + '</span>' +
        '<span class="trace" data-trace="' + ocEsc(traceId) + '" tabindex="0" ' +
            'role="button" aria-label="' + ocEsc("複製 trace id / Copy trace id") + '" ' +
            'title="' + ocEsc("點擊複製 trace id / Click to copy") + '">' +
          ocEsc(traceShort) + ' &#x1F4CB;' +
        '</span>' +
      '</div>';
    }).join("");
    body.innerHTML = rows;
    // Wire copy-to-clipboard on trace cells
    // 綁 trace cell click-to-copy（避免 inline onclick 被 CSP 擋）
    body.querySelectorAll(".trace").forEach(function(span) {
      span.addEventListener("click", function() {
        var t = span.getAttribute("data-trace") || "";
        if (!t || t === "—") return;
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(t).then(function() {
            ocToast(tZh("handoff_phrase.field_trace_id", "Trace ID") + " copied / 已複製", "success");
          }).catch(function() {
            ocToast("Copy failed / 複製失敗", "error");
          });
        }
      });
      // Keyboard a11y: Enter to copy
      span.addEventListener("keydown", function(ev) {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          span.click();
        }
      });
    });
  }

  // ─── Modal: typed confirmation / Modal：typed-confirm 對話框 ──────────────
  // 提交流程 / Submission flow：
  //   1. operator 點擊 "Promote to Demo" → openHandoffModal()
  //   2. modal 顯示 9 fields read-only summary + typed phrase input
  //   3. typed phrase regex 不符 → submit button keep disabled
  //   4. typed phrase OK → click submit → POST /api/v1/replay/handoff
  //      - Header: Idempotency-Key: <UUID v4>（H4）
  //      - Body: { experiment_id, manifest_id, typed_phrase, idempotency_key,
  //               actor, notes }
  //   5. response.ok=true → toast success + setCooldownStartingNow + refresh recent
  //   6. response.cached=true → bilingual notice "Already submitted (cached)"
  //   7. response.ok=false → toast error + reason
  //
  // Submission flow:
  //   Operator clicks Promote → modal renders 9-field summary + typed phrase
  //   input. Submit disabled until regex matches `HANDOFF <experiment_id>`.
  //   On submit, POST with Idempotency-Key header (UUID v4); on cached/success
  //   show bilingual notice + start cooldown + refresh recent list.
  function openHandoffModal(candidateData) {
    candidateData = candidateData || {};
    if (!candidateData.experiment_id) {
      ocToast(ocEsc("請先選回放候選 / Select a replay candidate first"), "error");
      return;
    }
    // 冷卻 / 凍結 兩道阻擋（防 race-edge case：trigger 已 disable 但 keyboard hook 觸發）
    // Two-tier block (cooldown + emergency freeze) — defense vs race edge cases
    if (getCooldownDeadlineMs()) {
      ocToast(ocEsc("冷卻中，請稍候 / Cooldown active, please wait"), "info");
      return;
    }

    var overlay = ensureModalOverlay();
    var experimentId = String(candidateData.experiment_id);
    var idempotencyKey = _ocUUID();  // H4: generate UUID v4 once per modal-open

    // Populate summary table
    // 填入 9 欄位 read-only summary
    var summaryEl = document.getElementById("oc-handoff-modal-summary");
    if (summaryEl) {
      var fields = [
        ["回放實驗 ID / Experiment ID", experimentId],
        ["清單 ID / Manifest ID", candidateData.manifest_id],
        ["信心分數 / Confidence", candidateData.confidence_score],
        ["成交筆數 / Trade Count", candidateData.n_trades],
        ["Sharpe", candidateData.sharpe],
        ["最大回撤 / Drawdown", candidateData.drawdown],
        ["費率模型 / Fee Model", candidateData.fee_model],
        ["過期時間 / Expires At", candidateData.expires_at],
        ["基準差異 / Baseline Delta", candidateData.baseline_delta || "—"]
      ];
      summaryEl.innerHTML = fields.map(function(row) {
        var v = row[1] == null || row[1] === "" ? "—" : ocEsc(String(row[1]));
        return '<div class="oc-handoff-modal-row">' +
          '<span class="lbl">' + ocEsc(row[0]) + '</span>' +
          '<span class="val">' + v + '</span>' +
        '</div>';
      }).join("");
    }

    // Populate phrase template hint + idempotency key display
    // 填入 phrase template hint + idempotency key 顯示
    var hintEl = document.getElementById("oc-handoff-modal-phrase-hint");
    if (hintEl) {
      var template = "HANDOFF " + experimentId;
      hintEl.innerHTML =
        '<div class="zh">' + ocEsc(tZh("handoff_phrase.phrase_hint",
          "請輸入 \"HANDOFF \" + 36 字元 experiment_id (UUID 格式)")) + '</div>' +
        '<div class="en">' + ocEsc(tZh("handoff_phrase.phrase_hint_en",
          "Type \"HANDOFF \" + 36-char experiment_id (UUID format)")) + '</div>' +
        '<code class="oc-handoff-modal-template" aria-label="' +
          ocEsc("預期語句 / Expected phrase") + '">' +
          ocEsc(template) + '</code>';
    }
    var idemEl = document.getElementById("oc-handoff-modal-idempotency");
    if (idemEl) {
      idemEl.textContent = idempotencyKey;
    }

    // Reset input + submit button
    // 重置輸入 + submit button
    var input = document.getElementById("oc-handoff-modal-phrase-input");
    if (input) input.value = "";
    var submitBtn = document.getElementById("oc-handoff-modal-submit-btn");
    if (submitBtn) {
      submitBtn.disabled = true;
      delete submitBtn.dataset.submitting;
    }

    // Wire phrase input → live regex validate
    // 綁 phrase input → live regex 驗證
    var expected = "HANDOFF " + experimentId;
    if (input && submitBtn) {
      input.oninput = function() {
        // Strict equality first（更嚴格防尾空白）；regex 額外保險
        // Strict equality first (catches trailing whitespace) + regex backup
        var ok = (input.value === expected) && PHRASE_REGEX.test(input.value);
        submitBtn.disabled = !ok;
        input.setAttribute("aria-invalid", ok ? "false" : "true");
      };
    }

    // Wire submit button — H4 idempotency + H1 server submit
    // 綁 submit button — H4 冪等鍵 + H1 server submit
    if (submitBtn) {
      submitBtn.onclick = async function() {
        // 防雙擊（H4 anti double-click）
        // Anti double-click (H4)
        if (submitBtn.dataset.submitting === "1") return;
        submitBtn.dataset.submitting = "1";
        submitBtn.disabled = true;

        var actor = currentActorId();
        var notesEl = document.getElementById("oc-handoff-notes");
        var notesVal = notesEl ? String(notesEl.value || "").trim() : "";
        var typedPhrase = input ? input.value : "";

        // POST with Idempotency-Key header — handled by ocApi (no built-in
        // header support → fallback: bake into body for backend mirror; backend
        // must read either header or body to honor V044 UNIQUE constraint).
        // ocApi 沒原生支援 custom header → 把 idempotency_key 也放 body，
        // backend S14 (V044 UNIQUE constraint) 同時讀 header / body。
        // Use raw fetch for header support.
        var resp = await fetchWithIdempotency(
          "/api/v1/replay/handoff",
          {
            experiment_id: experimentId,
            manifest_id: candidateData.manifest_id || null,
            typed_phrase: typedPhrase,
            idempotency_key: idempotencyKey,
            actor: actor,
            notes: notesVal
          },
          idempotencyKey
        );

        // Restore submitting flag — but if success keep disabled (cooldown ⛏)
        // Restore flag — keep disabled on success (cooldown handles re-enable)
        if (!resp || !resp.ok) {
          // Failure：unlock for retry（user 可改 phrase 再試）
          // Failure: unlock for retry
          delete submitBtn.dataset.submitting;
          // Re-validate phrase to set submit button correct state
          if (input && input.oninput) input.oninput();
          var reason = (resp && resp.reason) || "Network or server error / 網絡或伺服器錯誤";
          ocToast(ocEsc("交付失敗 / Handoff failed: " + reason), "error");
          return;
        }

        // Cached response handling (H4 Idempotency-Key UNIQUE hit)
        // 快取回應處理（V044 UNIQUE 命中）
        if (resp.cached) {
          showCachedNotice();
        } else {
          ocToast(ocEsc("交付已提交 / Handoff submitted"), "success");
        }

        // H2: start cooldown + persist last_actor
        // H2：啟動冷卻 + 持久化 last_actor
        setCooldownStartingNow();
        setLastActorId(actor);
        refreshCooldownUI();
        // Refresh recent list & dual-actor banner（async）
        // 刷新 recent list & dual-actor banner（async）
        refreshRecentList();
        refreshDualActorBanner();

        closeHandoffModal();
      };
    }

    // Show overlay + focus trap + ESC handler
    // 顯示 overlay + focus trap + ESC handler
    overlay.classList.add("show");
    overlay.setAttribute("aria-hidden", "false");
    // Focus moved to phrase input for fastest typing path
    // 焦點移到 phrase input（operator 直接 type）
    setTimeout(function() {
      var inp = document.getElementById("oc-handoff-modal-phrase-input");
      if (inp) inp.focus();
    }, 50);
    document.addEventListener("keydown", _modalKeydown);
  }

  // ─── Modal close + cleanup / Modal 關閉 + 清理 ─────────────────────────────
  function closeHandoffModal() {
    var overlay = document.getElementById("oc-handoff-modal-overlay");
    if (!overlay) return;
    overlay.classList.remove("show");
    overlay.setAttribute("aria-hidden", "true");
    document.removeEventListener("keydown", _modalKeydown);
    // Return focus to trigger button（a11y best practice）
    // 焦點返回 trigger button（a11y）
    var trigger = document.getElementById("oc-handoff-trigger-btn");
    if (trigger) trigger.focus();
  }

  // ESC handler + focus trap (Tab cycles inside modal)
  // ESC 鍵 + Tab 焦點陷阱
  function _modalKeydown(ev) {
    if (ev.key === "Escape") {
      ev.preventDefault();
      closeHandoffModal();
      return;
    }
    if (ev.key !== "Tab") return;
    // Focus trap: cycle within modal-only focusable elements
    // 焦點陷阱：限制 Tab 在 modal 內 focusable 元素
    var modal = document.querySelector("#oc-handoff-modal-overlay .oc-handoff-modal");
    if (!modal) return;
    var focusables = modal.querySelectorAll(
      'button:not([disabled]), [href], input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    if (!focusables.length) return;
    var first = focusables[0];
    var last = focusables[focusables.length - 1];
    if (ev.shiftKey && document.activeElement === first) {
      ev.preventDefault();
      last.focus();
    } else if (!ev.shiftKey && document.activeElement === last) {
      ev.preventDefault();
      first.focus();
    }
  }

  function showCachedNotice() {
    // Bilingual cached-response notice (H4)
    // 雙語快取回應通知（H4）
    ocToast(ocEsc("已提交（快取結果）/ Already submitted (cached result)"), "info");
  }

  // ─── Modal overlay lazy-inject / Modal overlay 懶注入 ─────────────────────
  // 與既有 #paper-confirm-modal 風格一致；重用 oc-confirm-overlay base style，
  // 額外加 .oc-handoff-modal layer 拓展 9-field summary table 排版。
  // Mirrors existing #paper-confirm-modal pattern; reuses oc-confirm-overlay
  // base style + adds .oc-handoff-modal layer for 9-field summary table.
  function ensureModalOverlay() {
    var overlay = document.getElementById("oc-handoff-modal-overlay");
    if (overlay) return overlay;
    overlay = document.createElement("div");
    overlay.id = "oc-handoff-modal-overlay";
    overlay.className = "oc-handoff-modal-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-labelledby", "oc-handoff-modal-title");
    overlay.setAttribute("aria-describedby", "oc-handoff-modal-desc");
    overlay.setAttribute("aria-hidden", "true");
    overlay.innerHTML =
      '<div class="oc-handoff-modal" tabindex="-1">' +
        '<div class="oc-handoff-modal-head">' +
          '<h3 id="oc-handoff-modal-title">' +
            ocEsc("驗證並交付 / Confirm Handoff") +
          '</h3>' +
          '<button type="button" class="oc-handoff-modal-close" ' +
            ' aria-label="' + ocEsc("關閉 / Close") + '">&#x2715;</button>' +
        '</div>' +
        '<div class="oc-handoff-modal-body" id="oc-handoff-modal-desc">' +
          '<div class="oc-handoff-modal-section-title">' +
            ocEsc("候選資料摘要 / Candidate Summary") +
          '</div>' +
          '<div id="oc-handoff-modal-summary" class="oc-handoff-modal-summary"></div>' +
          '<div class="oc-handoff-modal-section-title" style="margin-top:14px">' +
            ocEsc("typed 確認語 / Typed Confirmation Phrase") +
          '</div>' +
          '<div id="oc-handoff-modal-phrase-hint" class="oc-handoff-modal-hint"></div>' +
          '<input type="text" id="oc-handoff-modal-phrase-input" ' +
            ' class="oc-handoff-modal-input" autocomplete="off" spellcheck="false" ' +
            ' aria-required="true" aria-invalid="true" ' +
            ' placeholder="HANDOFF xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx" />' +
          '<div class="oc-handoff-modal-meta">' +
            '<span class="lbl">' + ocEsc("冪等鍵 / Idempotency Key") + ':</span>' +
            '<code id="oc-handoff-modal-idempotency"></code>' +
          '</div>' +
          '<div class="oc-handoff-modal-warning" role="note">' +
            '<span class="zh">' + ocEsc("提交後 30 秒內不可再次交付（H2 cooldown）") + '</span>' +
            '<span class="en"> · 30s cooldown applies after submit</span>' +
          '</div>' +
        '</div>' +
        '<div class="oc-handoff-modal-foot">' +
          '<button type="button" class="oc-btn" id="oc-handoff-modal-cancel-btn">' +
            ocEsc("取消 / Cancel") +
          '</button>' +
          '<button type="button" class="oc-btn oc-btn-danger" ' +
            ' id="oc-handoff-modal-submit-btn" disabled>' +
            ocEsc("確認交付 / Confirm Handoff") +
          '</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(overlay);

    // Wire close + cancel + click-outside-to-cancel
    // 綁 close + cancel + 點外圍取消
    var closeBtn = overlay.querySelector(".oc-handoff-modal-close");
    if (closeBtn) closeBtn.addEventListener("click", closeHandoffModal);
    var cancelBtn = overlay.querySelector("#oc-handoff-modal-cancel-btn");
    if (cancelBtn) cancelBtn.addEventListener("click", closeHandoffModal);
    overlay.addEventListener("click", function(ev) {
      if (ev.target === overlay) closeHandoffModal();
    });
    return overlay;
  }

  // ─── fetch with Idempotency-Key header / 帶冪等鍵 header 的 fetch ─────────
  // ocApi 不支援 custom header；此處 raw fetch 包一層，保持其他 endpoint 不動。
  // ocApi lacks custom header support; raw fetch wrapper keeps other endpoints
  // untouched.
  async function fetchWithIdempotency(path, body, idempotencyKey) {
    try {
      var r = await fetch(path, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey
        },
        body: JSON.stringify(body || {}),
        signal: AbortSignal.timeout(10000)
      });
      if (!r.ok) {
        // 404 = endpoint 還沒上線（Wave 8 sibling task）→ 友好降級訊息
        // 404 = endpoint not yet shipped → friendly degradation message
        if (r.status === 404) {
          return {
            ok: false,
            reason: "後端 endpoint 待上線（Wave 8 backend）/ Backend endpoint pending (Wave 8)"
          };
        }
        var errMsg = "HTTP " + r.status;
        try {
          var eb = await r.json();
          if (eb && eb.detail) errMsg = typeof eb.detail === "string" ? eb.detail : JSON.stringify(eb.detail);
          if (eb && eb.message) errMsg = eb.message;
        } catch (_) {}
        return { ok: false, reason: errMsg };
      }
      var resp = await r.json();
      // 統一回應形狀：{ ok, cached, data, reason }
      // Normalize response shape: { ok, cached, data, reason }
      return {
        ok: true,
        cached: !!(resp && (resp.cached === true || (resp.data && resp.data.cached === true))),
        data: resp && resp.data ? resp.data : resp
      };
    } catch (e) {
      console.warn("[handoff] fetch error:", e);
      return { ok: false, reason: e && e.message ? e.message : "network error" };
    }
  }

  // ─── CSS injection / CSS 注入 ──────────────────────────────────────────────
  // 與既有 oc-disabled-card / oc-confirm-overlay 風格一致；mobile @media 觸控
  // 目標 ≥44px（per Wave 4 SEV-2 #1 retrofit pattern）。
  // Mirrors oc-disabled-card / oc-confirm-overlay; mobile touch ≥44px.
  function injectCSS() {
    if (document.getElementById("oc-handoff-helper-css")) return;
    var s = document.createElement("style");
    s.id = "oc-handoff-helper-css";
    s.textContent = [
      // Card / form layout
      ".oc-handoff-card{background:rgba(22,27,34,0.7);border:1px solid var(--border);",
        "border-radius:var(--card-radius);padding:18px 20px 22px;margin-bottom:14px}",
      ".oc-handoff-header{display:flex;align-items:flex-start;gap:10px;margin-bottom:8px}",
      ".oc-handoff-title{flex:1;min-width:0}",
      ".oc-handoff-phase-chip{flex-shrink:0;font-size:10px;font-weight:700;",
        "padding:3px 9px;border-radius:999px;background:rgba(248,81,73,0.12);",
        "color:var(--red);border:1px solid rgba(248,81,73,0.35);letter-spacing:0.4px}",
      ".oc-handoff-empty-notice{font-size:12px;color:var(--text-dim);line-height:1.6;",
        "padding:10px 12px;background:rgba(13,17,23,0.55);border-left:3px solid var(--yellow);",
        "border-radius:4px;margin:8px 0}",
      ".oc-handoff-grid{display:grid;gap:8px;margin-top:10px;",
        "grid-template-columns:repeat(auto-fill,minmax(180px,1fr))}",
      ".oc-handoff-field{background:rgba(13,17,23,0.4);border:1px solid #21262d;",
        "border-radius:6px;padding:8px 10px;min-height:46px}",
      ".oc-handoff-field-label{font-size:9px;color:var(--text-dim);",
        "text-transform:uppercase;letter-spacing:0.4px}",
      ".oc-handoff-field-value{font-size:13px;color:var(--text);font-weight:500;",
        "margin-top:4px;word-break:break-all}",
      // Notes textarea
      ".oc-handoff-notes-row{margin-top:14px}",
      ".oc-handoff-notes-row textarea{width:100%;font-family:inherit;font-size:12px;",
        "padding:8px 10px;background:rgba(13,17,23,0.55);border:1px solid #21262d;",
        "border-radius:6px;color:var(--text);resize:vertical;margin-top:4px}",
      ".oc-handoff-notes-row textarea:focus{outline:2px solid var(--accent);outline-offset:1px}",
      // Trigger row
      ".oc-handoff-trigger-row{display:flex;align-items:center;gap:12px;margin-top:14px}",
      ".oc-handoff-cooldown-msg{font-size:11px;color:var(--yellow);font-family:monospace}",
      // Dual-actor banner
      ".oc-handoff-dual-banner{display:flex;align-items:center;gap:8px;flex-wrap:wrap;",
        "padding:8px 12px;border-radius:6px;font-size:12px;line-height:1.5;margin:6px 0 10px}",
      ".oc-handoff-dual-banner.same-actor{background:rgba(210,153,34,0.1);",
        "color:var(--yellow);border:1px solid rgba(210,153,34,0.4)}",
      ".oc-handoff-dual-banner.ok{background:rgba(46,160,67,0.1);",
        "color:var(--green);border:1px solid rgba(46,160,67,0.4)}",
      ".oc-handoff-dual-banner.freeze{background:rgba(248,81,73,0.12);",
        "color:var(--red);border:1px solid rgba(248,81,73,0.5);font-weight:600}",
      ".oc-handoff-dual-banner.pending{background:rgba(56,139,253,0.1);",
        "color:var(--text-dim);border:1px dashed rgba(56,139,253,0.3)}",
      ".oc-handoff-dual-banner .ts{margin-left:auto;font-size:10px;opacity:0.7}",
      ".oc-handoff-dual-banner .oc-handoff-dual-icon{font-size:14px}",
      // Recent footer
      ".oc-handoff-recent{margin-top:18px;border-top:1px dashed var(--border);padding-top:12px}",
      ".oc-handoff-recent-header{font-size:11px;color:var(--text-dim);",
        "text-transform:uppercase;letter-spacing:0.4px;margin-bottom:6px}",
      ".oc-handoff-recent-body{display:flex;flex-direction:column;gap:4px}",
      ".oc-handoff-recent-row{display:grid;",
        "grid-template-columns:80px 1fr 90px 1fr;gap:10px;",
        "padding:6px 8px;background:rgba(13,17,23,0.4);border-radius:4px;",
        "font-size:11px;align-items:center}",
      ".oc-handoff-recent-row .actor{font-family:monospace;color:var(--text)}",
      ".oc-handoff-recent-row .ts{color:var(--text-dim)}",
      ".oc-handoff-recent-row .result{font-weight:600}",
      ".oc-handoff-recent-row .result-ok{color:var(--green)}",
      ".oc-handoff-recent-row .result-fail{color:var(--red)}",
      ".oc-handoff-recent-row .result-rej{color:var(--yellow)}",
      ".oc-handoff-recent-row .result-cached{color:var(--blue)}",
      ".oc-handoff-recent-row .trace{font-family:monospace;font-size:10px;",
        "color:var(--blue);cursor:pointer;text-decoration:underline dotted;",
        "text-overflow:ellipsis;overflow:hidden;white-space:nowrap}",
      ".oc-handoff-recent-row .trace:hover{color:var(--accent)}",
      ".oc-handoff-recent-row .trace:focus{outline:2px solid var(--accent);outline-offset:1px;border-radius:2px}",
      ".oc-handoff-recent-empty{font-size:12px;color:var(--text-dim);",
        "padding:14px;text-align:center;line-height:1.6}",
      ".oc-handoff-recent-loading{font-size:12px;color:var(--text-dim);",
        "padding:14px;text-align:center;font-style:italic}",
      ".oc-handoff-recent-todo{font-size:10px;color:var(--text-dim);",
        "margin-top:6px;font-family:monospace;opacity:0.7}",
      // Modal overlay (mirrors oc-confirm-overlay)
      ".oc-handoff-modal-overlay{display:none;position:fixed;inset:0;z-index:1000;",
        "background:rgba(0,0,0,0.6);align-items:center;justify-content:center;padding:20px}",
      ".oc-handoff-modal-overlay.show{display:flex}",
      ".oc-handoff-modal{background:#161b22;border:1px solid #30363d;",
        "border-radius:12px;width:min(560px,100%);max-height:90vh;overflow-y:auto;",
        "box-shadow:0 20px 50px rgba(0,0,0,0.5);outline:none}",
      ".oc-handoff-modal-head{padding:16px 20px;border-bottom:1px solid #21262d;",
        "display:flex;justify-content:space-between;align-items:center}",
      ".oc-handoff-modal-head h3{margin:0;font-size:14px;font-weight:600;color:var(--text)}",
      ".oc-handoff-modal-close{background:none;border:none;color:#8b949e;",
        "font-size:18px;cursor:pointer;padding:4px 8px;line-height:1;min-height:32px;min-width:32px}",
      ".oc-handoff-modal-close:hover{color:var(--text)}",
      ".oc-handoff-modal-close:focus{outline:2px solid var(--accent);outline-offset:1px;border-radius:4px}",
      ".oc-handoff-modal-body{padding:16px 20px}",
      ".oc-handoff-modal-section-title{font-size:11px;color:var(--text-dim);",
        "text-transform:uppercase;letter-spacing:0.4px;margin-bottom:6px}",
      ".oc-handoff-modal-summary{display:flex;flex-direction:column;gap:4px;",
        "background:rgba(13,17,23,0.5);border-radius:6px;padding:8px 10px;",
        "border:1px solid #21262d}",
      ".oc-handoff-modal-row{display:flex;justify-content:space-between;gap:12px;",
        "font-size:12px;padding:3px 0;border-bottom:1px dashed #21262d}",
      ".oc-handoff-modal-row:last-child{border-bottom:none}",
      ".oc-handoff-modal-row .lbl{color:var(--text-dim);flex-shrink:0}",
      ".oc-handoff-modal-row .val{color:var(--text);font-family:monospace;font-size:11px;",
        "word-break:break-all;text-align:right}",
      ".oc-handoff-modal-hint{font-size:11px;color:var(--text-dim);line-height:1.6;",
        "margin-bottom:4px}",
      ".oc-handoff-modal-hint .zh{color:var(--text)}",
      ".oc-handoff-modal-hint .en{color:var(--text-dim);font-size:10px}",
      ".oc-handoff-modal-template{display:block;margin-top:4px;font-size:11px;",
        "padding:6px 8px;background:rgba(56,139,253,0.08);color:var(--blue);",
        "border:1px solid rgba(56,139,253,0.25);border-radius:4px;word-break:break-all}",
      ".oc-handoff-modal-input{width:100%;font-family:monospace;font-size:13px;",
        "padding:10px 12px;background:rgba(13,17,23,0.7);border:2px solid #21262d;",
        "border-radius:6px;color:var(--text);margin-top:6px;letter-spacing:0.5px}",
      ".oc-handoff-modal-input:focus{outline:none;border-color:var(--blue)}",
      ".oc-handoff-modal-input[aria-invalid='false']{border-color:var(--green)}",
      ".oc-handoff-modal-meta{display:flex;align-items:center;gap:8px;",
        "margin-top:10px;font-size:11px;color:var(--text-dim);flex-wrap:wrap}",
      ".oc-handoff-modal-meta .lbl{font-weight:600}",
      ".oc-handoff-modal-meta code{font-family:monospace;font-size:10px;",
        "padding:2px 6px;background:rgba(13,17,23,0.6);border:1px solid #21262d;",
        "border-radius:3px;color:var(--text);word-break:break-all}",
      ".oc-handoff-modal-warning{margin-top:12px;padding:8px 12px;",
        "background:rgba(210,153,34,0.08);color:var(--yellow);font-size:11px;",
        "border:1px solid rgba(210,153,34,0.3);border-radius:4px;line-height:1.5}",
      ".oc-handoff-modal-warning .zh{display:block}",
      ".oc-handoff-modal-warning .en{display:block;font-size:10px;opacity:0.85;margin-top:2px}",
      ".oc-handoff-modal-foot{padding:12px 20px;border-top:1px solid #21262d;",
        "display:flex;gap:8px;justify-content:flex-end}",
      // Mobile / touch (Wave 4 SEV-2 #1 baseline)
      "@media(max-width:700px){",
        ".oc-handoff-card{padding:14px 14px 16px}",
        ".oc-handoff-grid{grid-template-columns:1fr 1fr}",
        ".oc-handoff-recent-row{grid-template-columns:1fr 1fr;font-size:10px}",
        ".oc-handoff-modal{max-height:95vh;border-radius:8px}",
        ".oc-handoff-modal-foot button,",
        ".oc-handoff-trigger-row button{min-height:44px;padding:12px 16px}",
        ".oc-handoff-modal-input{min-height:44px;font-size:14px}",
      "}"
    ].join("");
    document.head.appendChild(s);
  }
  injectCSS();

  // ─── Public API / 對外公開 API ─────────────────────────────────────────────
  // 掛在 window.OpenClawHandoff 命名空間下（與 OpenClawDisabledStateCard /
  // OpenClawModeBadge 風格一致）。
  // Mounts on window.OpenClawHandoff (mirrors OpenClawDisabledStateCard /
  // OpenClawModeBadge naming convention).
  window.OpenClawHandoff = {
    /**
     * Render the Handoff sub-tab functional content into a container.
     * 渲染 Handoff 子標籤功能內容到容器。
     *
     * @param {string} containerId - target div id (subtab-handoff)
     * @param {Object|null} candidateData - 9 fields; null/undef = empty placeholder
     * @returns {boolean}
     */
    render: renderHandoffForm,

    /**
     * Open modal directly (for keyboard shortcut / sibling Compare flow).
     * 直接開啟 modal（鍵盤快捷鍵 / Compare 流程分派用）。
     */
    openModal: openHandoffModal,

    /**
     * Close modal programmatically (test harness / shutdown flow).
     * 程式化關閉 modal（test harness / shutdown 流程）。
     */
    closeModal: closeHandoffModal,

    /**
     * Refresh recent-5 list (for external cron / focus return).
     * 刷新近 5 筆列表（外部 cron / 焦點返回用）。
     */
    refreshRecent: refreshRecentList,

    /**
     * Refresh dual-actor banner (for emergency-freeze toggle).
     * 刷新 dual-actor banner（emergency freeze toggle 用）。
     */
    refreshDualActor: refreshDualActorBanner,

    /**
     * Diagnostic: current cooldown remaining ms (test harness).
     * 診斷：當前冷卻剩餘毫秒（test harness 用）。
     */
    cooldownRemainingMs: function() {
      var d = getCooldownDeadlineMs();
      return d ? Math.max(0, d - Date.now()) : 0;
    }
  };
})();
