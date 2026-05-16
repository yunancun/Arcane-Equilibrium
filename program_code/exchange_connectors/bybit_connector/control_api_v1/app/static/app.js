/**
 * 玄衡 · Arcane Equilibrium Control Center — GUI JavaScript
 * 玄衡控制台前端脚本
 *
 * 功能概述 / Feature overview:
 * - 通過 HttpOnly Cookie 認證調用 Control API（已从 Bearer Token 迁移）
 *   Authenticates via HttpOnly cookie to call the Control API (migrated from Bearer Token)
 * - 展示系統運行态、健康、審計、產品族状态
 *   Displays system runtime state, health, audit trail, product family status
 * - 產品族配置設置台：可交互修改 enabled/visible/mode/action_permissions
 *   Product family config console: interactive controls for enabled/visible/mode/action_permissions
 * - 經营摘要面板：展示每日 PnL + 歷史條目，支持手動录入成本和 PnL
 *   Business summary panel: daily PnL + history entries, supports manual cost/PnL entry
 * - 系統設置台：風險策略、Demo Ack、學習審批等開關
 *   Settings console: risk policy, demo ack, learning approval toggles
 * - 所有關键動作需要二次确認弹窗
 *   All critical actions require a second-confirmation modal
 *
 * 安全原則 / Safety principle:
 * 看得见 ≠ 被允許；被允許繼續判斷 ≠ 能執行；demo ≠ live。
 * Visible ≠ allowed; allowed to continue ≠ executable; demo ≠ live.
 */

"use strict";

// ── 全局状态 / Global state ──────────────────────────────────────────────────

let inMemoryToken = "";

// 當前状态修订版本號，用于構建 envelope / Current state revision for envelope construction
let currentStateRevision = 0;

// ── 常量：關键動作元數據 / Constants: critical action metadata ────────────────

/**
 * 需要二次确認的關键動作及其風險說明。
 * Critical actions requiring second confirmation, with risk descriptions.
 */
const CRITICAL_ACTIONS = {
  "set-demo-mode": {
    title: "切换到 Demo Reserved",
    subtitle: "Set global execution mode to demo_reserved",
    risk: "這一步只是把系統从「完全不走 demo 流程」改成「允許繼續做 demo 相關判斷」。它不是下單，不是開啟 live，也不是马上获得執行權。",
    consequence: "点完后，系統只会進入「可以繼續做 demo 檢查」的状态。你之后仍然還要 validate、arm，甚至 future enable；所以這一步只是打開下一道门，不是直接放權。"
  },
  "enable-spot": {
    title: "開啟 Spot / 現货產品配置",
    subtitle: "Enable spot family in shadow mode",
    risk: "這一步只影响現货產品族。它会讓 spot/現货从「關閉/仅展示」進入 shadow 控制状态。shadow 的意思是：用于觀察、驗證、看控制結果，不是實際成交。",
    consequence: "点完后，只会改变現货這一類產品的控制展示和 gate 結果，不會影响其它產品族，也不會直接讓賬户获得真實現货下單權限。"
  },
  validate: {
    title: "驗證 Demo 前提",
    subtitle: "Validate demo prerequisites and gates",
    risk: "這一步只是做檢查。它会重新判斷系統現在是否滿足 demo 的前置條件。它不會切模式，也不會推進 demo 主状态。",
    consequence: "点完后，你主要会看到 gate 結果变了，比如「可以繼續」還是「還不滿足條件」。它不會直接提高執行權限。"
  },
  "arm-demo": {
    title: "執行 Demo Arm",
    subtitle: "Move demo state to armed_but_closed",
    risk: "這是 demo 流程里更關键的一步。它表示系統已經通過前置檢查，進入「已準備好下一步，但仍然封閉」的状态。",
    consequence: "点完后，demo 会更接近后續 enable，但仍然不能直接執行。你可以把它理解成「已經準備好了，但保險還没真正打開」。"
  },
  bundle: {
    title: "執行安全復核打包",
    subtitle: "Run safe recheck bundle",
    risk: "這一步会把多项檢查和刷新一起跑一遍。它適合在你想讓整页判斷一起更新時使用。",
    consequence: "点完后，readiness、gate、audit 等多個區域可能一起刷新。它本身不是切模式，也不是直接放權。"
  },
  "pf-config": {
    title: "修改產品族配置",
    subtitle: "Update product family control switches",
    risk: "這一步会修改指定產品族的 enabled/visible/mode 等控制開關。它不等于获得執行權，但会改变系統控制判斷的輸入。",
    consequence: "点完后，相應產品族的 capability 和 execution authority 会重新計算。這一步本身不直接開放 live 權限。"
  },
  "settings-change": {
    title: "修改系統設置",
    subtitle: "Apply system-level configuration change",
    risk: "這一步会修改全局系統設置，如風險策略或 Demo Ack 開關。這些設置影响整個控制判斷链路。",
    consequence: "設置变更后立即生效。請确認你理解修改后的效果，特别是風險策略相關的变更。"
  },
  // FIX-39/40: Danger Zone operations + strategy deletion — replaced native confirm()
  "delete-strategy": {
    title: "刪除策略 / Delete Strategy",
    subtitle: "Permanently remove this strategy configuration",
    risk: "此操作無法撤銷。策略的所有參數、狀態將被永久刪除。",
    consequence: "策略刪除後立即生效，已開倉位不受影響但不再被該策略管理。"
  },
  "reset-cooldown": {
    title: "重置冷卻期 / Reset Loss Cooldown",
    subtitle: "Re-enable new order placement immediately",
    risk: "連續虧損冷卻期是風控保護機制。重置後系統將立即恢復開倉。",
    consequence: "請確認當前市況適合繼續交易，否則可能加速虧損。"
  },
  "unhalt-session": {
    title: "解除熔斷 / Resume Trading",
    subtitle: "Resume trading after circuit-breaker halt",
    risk: "熔斷保護在回撤嚴重時觸發。解除後所有交易功能恢復。",
    consequence: "請確認回撤已受控、市場條件改善後再操作。錯誤解除可能導致進一步虧損。"
  }
};

// ── 常量：產品族標簽 / Constants: product family labels ──────────────────────

const PRODUCT_FAMILY_LABELS = {
  spot: "spot / 現货",
  margin: "margin / 保證金",
  perp_linear: "perp_linear / 線性永續",
  perp_inverse: "perp_inverse / 反向永續",
  options: "options / 期權",
  other_derivatives_reserved: "other_derivatives_reserved / 其他衍生品（预留）"
};

const PRODUCT_FAMILY_CONFIG_IDS = {
  spot: { summary: "cfgSpotSummary", meta: "cfgSpotMeta" },
  margin: { summary: "cfgMarginSummary", meta: "cfgMarginMeta" },
  perp_linear: { summary: "cfgLinearPerpSummary", meta: "cfgLinearPerpMeta" },
  perp_inverse: { summary: "cfgInversePerpSummary", meta: "cfgInversePerpMeta" },
  options: { summary: "cfgOptionsSummary", meta: "cfgOptionsMeta" },
  other_derivatives_reserved: { summary: "cfgOtherDerivativesSummary", meta: "cfgOtherDerivativesMeta" }
};

// 動作權限名稱映射 / Action permission name mappings
const ACTION_NAME_LABELS = {
  new_order: "新建訂單 / new_order",
  cancel: "撤銷 / cancel",
  amend: "改單 / amend",
  reduce_only: "只减倉 / reduce_only",
  increase_position: "加倉 / increase_position",
  close_position: "平倉 / close_position"
};

const ACTION_NAMES = Object.keys(ACTION_NAME_LABELS);

// 長期開關预留區 / Long-term switch preset area
const LONG_TERM_SWITCHES = [
  ["仅觀察", "Observe Only", "當前只做展示位", "locked"],
  ["Demo Reserved", "Demo Reserved", "允許繼續做 demo 判斷", "preset"],
  ["Demo Enabled", "Demo Enabled", "后續階段预留，當前不開放", "locked"],
  ["Live Locked", "Live Locked", "真實執行長期锁定", "locked"],
  ["紧急回锁", "Emergency Relock", "高優先级安全開關，當前只预留", "locked"],
  ["自動化锁定", "Automation Locked", "自動化真實執行暂不開放", "locked"],
  ["只读維護", "Readonly Maintenance", "維護模式后續接入", "locked"],
  ["審計增强", "Audit Enhanced", "長期審計擴展位", "planned"]
];

// ── 基礎工具函數 / Basic utility functions ───────────────────────────────────

function headers() {
  // APR01-MEDIUM-13: Token is in HttpOnly cookie, sent automatically.
  // Authorization header kept only if inMemoryToken was manually set (legacy/API mode).
  // APR01-MEDIUM-13：Token 在 HttpOnly cookie 中，自動發送。
  // 仅在手動設置 inMemoryToken 時保留 Authorization header（旧版/API 模式）。
  const h = { "Content-Type": "application/json" };
  if (inMemoryToken) {
    h.Authorization = `Bearer ${inMemoryToken}`;
  }
  return h;
}

function pretty(value) { return JSON.stringify(value, null, 2); }
// SEC-05: safeText now HTML-escapes to prevent XSS when used in innerHTML templates.
// SEC-05：safeText 現在做 HTML 轉義，防止 innerHTML 模板中的 XSS。
function safeText(value) { return value === undefined || value === null ? "-" : ocEsc(String(value)); }

/**
 * 根據状态值返回 CSS variant 名。
 * Returns CSS variant name based on state value.
 */
function variantForState(value) {
  const normalized = String(value || "").toLowerCase();
  if (["passed", "healthy", "ready", "fresh", "complete", "shadow_only", "shadow_control_ready",
       "success", "true", "allowed", "preset", "observe_only"].includes(normalized)) return "good";
  if (["blocked", "disabled", "down", "missing", "failed", "unavailable",
       "unknown", "false", "locked"].includes(normalized)) return "bad";
  if (["partial", "degraded", "demo_reserved", "demo_blocked", "armed_but_closed",
       "visible_only", "shadow_visible", "planned"].includes(normalized)) return "warn";
  return "neutral";
}

function booleanZh(value, trueText, falseText) { return value ? trueText : falseText; }

function fmtPnl(value) {
  // 格式化 PnL 數字为带正負號的字符串 / Format PnL number with sign
  const n = parseFloat(value);
  if (isNaN(n)) return "-";
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(4)} USDT`;
}

function fmtTs(tsMs) {
  // 将時間戳转为本地時間字符串 / Convert timestamp to local time string
  if (!tsMs) return "-";
  return new Date(tsMs).toLocaleString();
}

// ── UI 状态更新辅助 / UI state update helpers ─────────────────────────────────

/**
 * 安全設置元素文本 / Safely set element text by ID.
 * 如果元素不存在則靜默忽略。
 * Silently ignored if element does not exist.
 */
function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = String(text);
}

function setConnectionStatus(text, variant = "neutral") {
  const node = document.getElementById("connectionStatus");
  node.textContent = text;
  node.className = `status-chip ${variant}`;
}

function setRuntimeModeBadge(text, variant = "neutral") {
  const node = document.getElementById("runtimeModeBadge");
  node.textContent = text;
  node.className = `status-chip ${variant}`;
}

function setActionSummary(name, result, revision, auditRef, hint, raw) {
  document.getElementById("actionSummaryName").textContent = safeText(name);
  const resultNode = document.getElementById("actionSummaryResult");
  resultNode.textContent = safeText(result);
  resultNode.className = `action-result-value ${variantForState(result)}`;
  document.getElementById("actionSummaryRevision").textContent = safeText(revision);
  document.getElementById("actionSummaryAudit").textContent = safeText(auditRef);
  document.getElementById("actionSummaryHint").textContent = safeText(hint);
  document.getElementById("actionResultBox").textContent = typeof raw === "string" ? raw : pretty(raw);
}

function summarizeActionResult(actionName, result) {
  const actionMap = {
    refresh: "刷新概览",
    validate: "驗證 Demo",
    bundle: "安全復核打包",
    "set-demo-mode": "切到 Demo Reserved",
    "enable-spot": "開啟 Spot / 現货產品配置",
    "arm-demo": "執行 Demo Arm",
    "pf-config": "產品族配置变更",
    "settings-change": "系統設置变更",
    "cost-entry": "費用录入",
    "pnl-entry": "PnL 录入"
  };
  const actionEnMap = {
    refresh: "refresh overview",
    validate: "validate demo",
    bundle: "safe recheck bundle",
    "set-demo-mode": "set demo reserved",
    "enable-spot": "enable spot config",
    "arm-demo": "arm demo",
    "pf-config": "product family config update",
    "settings-change": "system settings change",
    "cost-entry": "cost entry recorded",
    "pnl-entry": "PnL entry recorded"
  };

  const data = result?.data || {};
  let hint = "動作執行完成。";
  let helper = "Action completed.";

  if (actionName === "validate") {
    hint = `系統刚完成一次檢查：前提 gate = ${safeText(data.demo_prerequisites_gate_state)}；Arm gate = ${safeText(data.demo_arm_gate_state)}。`;
    helper = `This checked whether demo can continue, not whether execution is already open.`;
  } else if (actionName === "arm-demo") {
    hint = `Demo 状态現在是：${safeText(data.demo_state_switch)}。系統已更接近下一步，但仍未放開執行。`;
    helper = `The system moved closer to the next step, but execution is still not open.`;
  } else if (actionName === "set-demo-mode") {
    hint = `已接受"進入 Demo Reserved"配置。后續仍需 validate → arm → enable 才能获得執行權。`;
    helper = `Demo evaluation path is now allowed to continue, but no execution authority was opened.`;
  } else if (actionName === "enable-spot") {
    hint = `現货產品配置已修改。現货進入 shadow 控制展示，但不等于賬户已能真實現货下單。`;
    helper = `Spot moved into shadow control display, but real spot trading authority is still separate.`;
  } else if (actionName === "bundle") {
    hint = `系統刚完成一轮統一復核刷新。多個判斷結果可能已更新，但本步驟不直接放權。`;
    helper = `Multiple checks were refreshed together, but no authority was directly opened.`;
  } else if (actionName === "refresh") {
    hint = "界面已刷新。"; helper = "Dashboard refreshed.";
  } else if (actionName === "pf-config") {
    const applied = Object.keys(data.applied_changes || {});
    hint = `產品族 ${safeText(data.family)} 配置已更新，变更字段：${applied.join(", ") || "無"}。`;
    helper = `Product family ${safeText(data.family)} config updated.`;
  } else if (actionName === "settings-change") {
    hint = `系統設置已更新：${safeText((data.accepted_paths || []).join(", "))}。`;
    helper = `System settings updated.`;
  } else if (actionName === "cost-entry") {
    hint = `費用條目已录入，金额：${safeText(result?.data?.record_count_delta)} 條。`;
    helper = `Cost entry recorded.`;
  } else if (actionName === "pnl-entry") {
    hint = `PnL 條目已录入，類型：${safeText(data.entry_type)}。`;
    helper = `PnL entry recorded.`;
  }

  setActionSummary(
    `${actionMap[actionName] || actionName} / ${actionEnMap[actionName] || actionName}`,
    safeText(result.action_result),
    safeText(result.state_revision),
    safeText(result.audit_ref),
    `${hint} ${helper}`,
    result
  );
}

// ── 双語標簽辅助 / Bilingual label helpers ────────────────────────────────────

function zhEnPrimary(zh, en) {
  return `<span class="label-zh">${zh}</span><span class="label-en">${en}</span>`;
}

function annotateGlossary(termZh, termEn, noteZh, noteEn) {
  return `<div class="glossary-pill">
    <span class="glossary-term">${termZh}</span>
    <span class="glossary-term-en">${termEn}</span>
    <span class="glossary-note">${noteZh} / ${noteEn}</span>
  </div>`;
}

// ── KV 網格渲染 / KV grid rendering ──────────────────────────────────────────

function renderKvGrid(nodeId, items) {
  const node = document.getElementById(nodeId);
  if (!node) return;
  node.innerHTML = items.map(([labelHtml, value]) =>
    `<div class="kv-item">
       <dt>${labelHtml}</dt>
       <dd><span class="status-chip ${variantForState(value)}">${safeText(value)}</span></dd>
     </div>`
  ).join("");
}

// ── 确認弹窗 / Confirm modal ──────────────────────────────────────────────────

function openConfirmModal(actionName) {
  const meta = CRITICAL_ACTIONS[actionName];
  if (!meta) return Promise.resolve(true);
  const modal = document.getElementById("confirmModal");
  const dialog = modal.querySelector(".confirm-modal-dialog");
  if (dialog) {
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-labelledby", "confirmModalTitle");
    dialog.setAttribute("tabindex", "-1");
  }
  modal.classList.remove("hidden");
  document.getElementById("confirmModalTitle").textContent = meta.title;
  document.getElementById("confirmModalSubtitle").textContent = meta.subtitle;
  document.getElementById("confirmModalRisk").textContent = meta.risk;
  document.getElementById("confirmModalConsequence").textContent = meta.consequence;
  return new Promise((resolve) => {
    const previousActive = document.activeElement;
    const focusableNodes = () => Array.from(
      modal.querySelectorAll("button,[href],input,select,textarea,[tabindex]:not([tabindex='-1'])")
    ).filter((node) => !node.disabled && node.offsetParent !== null);
    const cleanup = () => {
      modal.classList.add("hidden");
      modal.onkeydown = null;
      document.querySelectorAll("[data-close-modal='true']").forEach((node) =>
        node.replaceWith(node.cloneNode(true))
      );
      const proceed = document.getElementById("confirmModalProceed");
      proceed.replaceWith(proceed.cloneNode(true));
      if (previousActive && typeof previousActive.focus === "function") previousActive.focus();
    };
    modal.onkeydown = (ev) => {
      if (ev.key === "Escape") {
        ev.preventDefault();
        cleanup();
        resolve(false);
        return;
      }
      if (ev.key !== "Tab") return;
      const nodes = focusableNodes();
      if (!nodes.length) {
        ev.preventDefault();
        return;
      }
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (ev.shiftKey && document.activeElement === first) {
        ev.preventDefault();
        last.focus();
      } else if (!ev.shiftKey && document.activeElement === last) {
        ev.preventDefault();
        first.focus();
      }
    };
    modal.querySelectorAll("[data-close-modal='true']").forEach((node) =>
      (node.onclick = () => { cleanup(); resolve(false); })
    );
    document.getElementById("confirmModalProceed").onclick = () => { cleanup(); resolve(true); };
    setTimeout(() => {
      const cancel = modal.querySelector(".confirm-cancel");
      if (cancel) cancel.focus();
    }, 0);
  });
}

// ── API 調用 / API calls ──────────────────────────────────────────────────────

async function apiGet(path) {
  const response = await fetch(path, { headers: headers(), credentials: 'same-origin' });
  const data = await response.json();
  if (!response.ok) throw new Error(pretty(data));
  return data;
}

async function apiPost(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: headers(),
    credentials: 'same-origin',
    body: JSON.stringify(payload)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(pretty(data));
  return data;
}

function baseEnvelope(extra = {}) {
  // 構建標准請求 envelope / Build standard request envelope
  return {
    request_id: _ocUUID(),
    idempotency_key: _ocUUID(),
    operator_id: "demo-operator",
    reason: "gui-triggered action",
    client_ts_ms: Date.now(),
    expected_state_revision: currentStateRevision,
    expected_previous_state: null,
    payload: {},
    ...extra
  };
}

// ── 渲染函數 / Render functions ───────────────────────────────────────────────

function renderSummary(overview) {
  const runtime = overview.data.global_runtime;
  const demo = overview.data.demo_control_summary;
  const sourceContext = overview.source_context;
  currentStateRevision = overview.state_revision;

  document.getElementById("summaryGlobalMode").textContent = runtime.global_mode_state;
  document.getElementById("summaryExecutionAuthority").textContent = runtime.global_execution_authority_state;
  document.getElementById("summaryDemoState").textContent = demo.demo_state_switch;
  document.getElementById("summarySnapshot").textContent = `${overview.state_revision} / ${overview.snapshot_id}`;
  document.getElementById("summaryRuntimeSnapshot").textContent = sourceContext.pinned_runtime_snapshot_id;
  document.getElementById("summaryProtected").textContent = String(runtime.runtime_still_protected);
  setRuntimeModeBadge(
    `${runtime.global_mode_state} · ${demo.demo_state_switch}`,
    variantForState(runtime.global_execution_authority_state)
  );
}

function renderModeControl(overview) {
  const runtime = overview.data.global_runtime;
  const demo = overview.data.demo_control_summary;
  const el = (id) => document.getElementById(id);
  if (el("modeStageLabel")) el("modeStageLabel").textContent = safeText(runtime.global_stage_label);
  if (el("modeCapabilityState")) el("modeCapabilityState").textContent = safeText(runtime.global_capability_state);
  if (el("modeDemoArmGate")) el("modeDemoArmGate").textContent = safeText(demo.demo_arm_gate_state);
  if (el("modeDemoEnableGate")) el("modeDemoEnableGate").textContent = safeText(demo.demo_enable_gate_state);
}

function renderBusinessSummary(businessData) {
  // businessData 可能来自 overview.data.daily_business_summary 或 summary endpoint
  // businessData may come from overview.data.daily_business_summary or the summary endpoint
  const daily = businessData.daily || businessData;
  const el = (id) => document.getElementById(id);

  if (el("bizRealizedPnl")) el("bizRealizedPnl").textContent = fmtPnl(daily.realized_pnl);
  if (el("bizUnrealizedPnl")) el("bizUnrealizedPnl").textContent = fmtPnl(daily.unrealized_pnl);
  if (el("bizGrossPnl")) el("bizGrossPnl").textContent = fmtPnl(daily.gross_pnl);
  if (el("bizTotalCost")) el("bizTotalCost").textContent = fmtPnl(daily.total_cost);
  if (el("bizNetOperatingPnl")) el("bizNetOperatingPnl").textContent = fmtPnl(daily.net_operating_pnl);
  if (el("bizEventCount")) el("bizEventCount").textContent = safeText(daily.business_event_count);

  // 更新歷史條目列表 / Update recent entry lists
  renderCostEntries(businessData.cost_entries_recent || []);
  renderPnlEntries(businessData.pnl_entries_recent || []);

  // 更新成本分解 / Update cost breakdown
  renderCostBreakdown(businessData.cost_breakdown || {});

  // 更新條目總數 / Update entry totals
  const totals = businessData.entry_totals || {};
  if (el("bizCostCount")) el("bizCostCount").textContent = safeText(totals.total_cost_entries);
  if (el("bizPnlCount")) el("bizPnlCount").textContent = safeText(totals.total_pnl_entries);
  if (el("bizEvtCount")) el("bizEvtCount").textContent = safeText(totals.total_event_entries);
}

function renderCostEntries(entries) {
  const node = document.getElementById("costEntriesList");
  if (!node) return;
  if (!entries || entries.length === 0) {
    node.innerHTML = '<div class="entry-row muted-row">暂無費用記錄 / No cost entries yet.</div>';
    return;
  }
  node.innerHTML = entries.map((e) =>
    `<div class="entry-row">
       <span class="entry-ts">${fmtTs(e.recorded_ts_ms)}</span>
       <span class="entry-cat">${safeText(e.category || "manual")}</span>
       <span class="entry-amt bad">${fmtPnl(e.amount)}</span>
       <span class="entry-note muted">${safeText(e.note || "")}</span>
     </div>`
  ).join("");
}

function renderPnlEntries(entries) {
  const node = document.getElementById("pnlEntriesList");
  if (!node) return;
  if (!entries || entries.length === 0) {
    node.innerHTML = '<div class="entry-row muted-row">暂無 PnL 記錄 / No PnL entries yet.</div>';
    return;
  }
  node.innerHTML = entries.map((e) =>
    `<div class="entry-row">
       <span class="entry-ts">${fmtTs(e.recorded_ts_ms)}</span>
       <span class="entry-cat">${safeText(e.entry_type)}</span>
       <span class="entry-amt ${parseFloat(e.realized_pnl || 0) >= 0 ? "good" : "bad"}">已實現:${fmtPnl(e.realized_pnl)}</span>
       <span class="entry-note muted">未實現:${fmtPnl(e.unrealized_pnl)} ${safeText(e.note || "")}</span>
     </div>`
  ).join("");
}

function renderCostBreakdown(breakdown) {
  const node = document.getElementById("costBreakdownGrid");
  if (!node) return;
  const keys = Object.keys(breakdown);
  if (keys.length === 0) {
    node.innerHTML = '<span class="muted">暂無分類 / No categories yet.</span>';
    return;
  }
  node.innerHTML = keys.map((k) =>
    `<div class="breakdown-item">
       <span class="breakdown-cat">${ocEsc(k)}</span>
       <span class="breakdown-amt bad">${fmtPnl(breakdown[k])}</span>
     </div>`
  ).join("");
}

function renderProductFamilyConfig(productFamilies) {
  // 渲染每個產品族的配置卡片摘要 / Render config summary for each product family card
  Object.entries(PRODUCT_FAMILY_CONFIG_IDS).forEach(([family, ids]) => {
    const data = productFamilies[family];
    const summaryNode = document.getElementById(ids.summary);
    const metaNode = document.getElementById(ids.meta);
    if (!summaryNode || !metaNode) return;
    if (!data) {
      summaryNode.textContent = "-";
      metaNode.textContent = "暂無數據 / No data.";
      return;
    }
    const enabledText = booleanZh(data.controls.enabled_switch, "已啟用 ✓", "未啟用 ✗");
    const visibleText = booleanZh(data.controls.visibility_switch, "可见", "隐藏");
    summaryNode.textContent = `${enabledText} · ${visibleText} · ${safeText(data.controls.mode_switch)}`;
    metaNode.textContent =
      `交易所事實: ${safeText(data.facts.exchange_permission_fact)} | ` +
      `賬户事實: ${safeText(data.facts.account_permission_fact)} | ` +
      `能力: ${safeText(data.derived.capability_state)}`;
  });
}

/**
 * 渲染產品族配置設置台的交互控件。
 * Render interactive controls in the product family config settings console.
 *
 * @param {Object} productFamilies - product_family_status from API
 * @param {Object} controlPlane - control_plane from API (for action_permissions)
 */
function renderProductFamilyEditor(productFamilies, controlPlane) {
  const container = document.getElementById("pfEditorContainer");
  if (!container) return;

  container.innerHTML = Object.entries(productFamilies).map(([family, data]) => {
    const ctrl = data.controls;
    const derived = data.derived;
    const perms = (controlPlane?.action_permissions?.by_product_family?.[family]) || {};
    const label = PRODUCT_FAMILY_LABELS[family] || family;

    // 動作權限格子 / Action permissions grid
    const permRows = ACTION_NAMES.map((action) => {
      const switchKey = `configured_${action}_allowed_switch`;
      const checked = perms[switchKey] === true ? "checked" : "";
      const effectiveKey = `effective_${action}_allowed_state`;
      const effective = perms[effectiveKey] || "disabled";
      return `<label class="perm-row">
        <input type="checkbox" class="perm-check" data-family="${family}" data-action="${action}" ${checked}>
        <span class="perm-label">${ACTION_NAME_LABELS[action]}</span>
        <span class="status-chip ${variantForState(effective)} perm-effective">${effective}</span>
      </label>`;
    }).join("");

    // 能力/執行状态徽章 / Capability/execution status badges
    const capBadge = `<span class="status-chip ${variantForState(derived.capability_state)}">${derived.capability_state}</span>`;
    const execBadge = `<span class="status-chip ${variantForState(derived.execution_authority_state)}">${derived.execution_authority_state}</span>`;

    return `
    <div class="pf-editor-card" id="pfe-${family}">
      <div class="pf-editor-header">
        <strong>${label}</strong>
        <div class="pf-editor-badges">${capBadge}${execBadge}</div>
      </div>
      <div class="pf-editor-controls">
        <label class="switch-row">
          <span class="switch-label">啟用 / Enabled</span>
          <input type="checkbox" class="pf-toggle" id="pf-enabled-${family}" data-family="${family}" data-field="enabled_switch" ${ctrl.enabled_switch ? "checked" : ""}>
        </label>
        <label class="switch-row">
          <span class="switch-label">可见 / Visible</span>
          <input type="checkbox" class="pf-toggle" id="pf-visible-${family}" data-family="${family}" data-field="visibility_switch" ${ctrl.visibility_switch ? "checked" : ""}>
        </label>
        <div class="switch-row">
          <span class="switch-label">模式 / Mode</span>
          <select class="pf-mode-select" id="pf-mode-${family}" data-family="${family}">
            <option value="disabled" ${ctrl.mode_switch === "disabled" ? "selected" : ""}>disabled</option>
            <option value="observe_only" ${ctrl.mode_switch === "observe_only" ? "selected" : ""}>observe_only</option>
            <option value="shadow_only" ${ctrl.mode_switch === "shadow_only" ? "selected" : ""}>shadow_only</option>
          </select>
        </div>
        <button class="pf-apply-btn" data-family="${family}">
          應用配置 / Apply Config
          <span class="button-sub">sends to /control/product-family/{family}/config</span>
        </button>
      </div>
      <details class="perm-details">
        <summary class="perm-summary">動作權限 / Action Permissions</summary>
        <div class="perm-grid">${permRows}</div>
        <button class="pf-perm-apply-btn" data-family="${family}">
          應用權限变更 / Apply Permission Changes
          <span class="button-sub">updates action permission switches</span>
        </button>
      </details>
    </div>`;
  }).join("");
}

function renderLongTermSwitches() {
  const grid = document.getElementById("longTermSwitchGrid");
  if (!grid) return;
  grid.innerHTML = LONG_TERM_SWITCHES.map(([zh, en, desc, state]) =>
    `<div class="summary-item config-family-card">
       <span class="summary-label">${zhEnPrimary(zh, en)}</span>
       <strong><span class="status-chip ${variantForState(state)}">${safeText(state)}</span></strong>
       <div class="family-card-meta">${desc}</div>
       <div class="family-actions">
         <button class="button-muted" disabled>長期预留（未開放）<span class="button-sub">preset only</span></button>
       </div>
     </div>`
  ).join("");
}

function renderSourceContext(sourceContext) {
  renderKvGrid("sourceContextGrid", [
    [zhEnPrimary("只读连接器", "Readonly Connector"), sourceContext.readonly_connector_name],
    [zhEnPrimary("執行连接器", "Execution Connector"), sourceContext.execution_connector_name || "not_attached"],
    [zhEnPrimary("私有 REST", "REST Private"), sourceContext.rest_private_connection_state],
    [zhEnPrimary("私有 WS", "WS Private"), sourceContext.ws_private_connection_state],
    [zhEnPrimary("Runtime 连接", "Runtime Connection"), sourceContext.runtime_connection_state],
    [zhEnPrimary("賬户完整性", "Account Completeness"), sourceContext.account_fact_completeness_state],
    [zhEnPrimary("快照完整性", "Snapshot Completeness"), sourceContext.source_snapshot_completeness_state],
    [zhEnPrimary("角色分离", "Role Separation"), sourceContext.connector_role_separation_ok],
    [zhEnPrimary("Runtime 快照", "Runtime Snapshot"), sourceContext.pinned_runtime_snapshot_id]
  ]);
}

function renderHealth(overview) {
  const health = overview.data.health_summary;
  renderKvGrid("healthGrid", [
    [zhEnPrimary("總健康分", "Overall Health Score"), health.scores.overall_health_score],
    [zhEnPrimary("AI 健康分", "AI Health Score"), health.scores.ai_health_score],
    [zhEnPrimary("交易所健康分", "Exchange Health Score"), health.scores.exchange_health_score],
    [zhEnPrimary("新鲜度分", "Data Freshness Score"), health.scores.data_freshness_score],
    [zhEnPrimary("總 Gate", "Health Gates Overall"), health.gates.health_gates_overall_state],
    [zhEnPrimary("Timeout Gate", "Exchange Timeout Gate"), health.gates.exchange_timeout_gate_state],
    [zhEnPrimary("WS 斷连 Gate", "WS Disconnect Gate"), health.gates.ws_disconnect_gate_state],
    [zhEnPrimary("延遲 Gate", "Latency Gate"), health.gates.latency_gate_state],
    [zhEnPrimary("新鲜度 Gate", "Freshness Gate"), health.gates.freshness_gate_state]
  ]);
}

function renderProductFamilies(productFamilies) {
  const body = document.getElementById("productFamilyTableBody");
  const rows = Object.entries(productFamilies).map(([name, data]) =>
    `<tr>
       <td>${PRODUCT_FAMILY_LABELS[name] || name}</td>
       <td><span class="status-chip ${variantForState(data.facts.exchange_permission_fact)}">${data.facts.exchange_permission_fact}</span></td>
       <td><span class="status-chip ${variantForState(data.facts.account_permission_fact)}">${data.facts.account_permission_fact}</span></td>
       <td>${String(data.controls.enabled_switch)}</td>
       <td>${String(data.controls.visibility_switch)}</td>
       <td>${data.controls.mode_switch}</td>
       <td><span class="status-chip ${variantForState(data.derived.capability_state)}">${data.derived.capability_state}</span></td>
       <td><span class="status-chip ${variantForState(data.derived.execution_authority_state)}">${data.derived.execution_authority_state}</span></td>
     </tr>`
  ).join("");
  body.innerHTML = rows || '<tr><td colspan="8" class="muted-cell">無數據 / No data</td></tr>';
}

/**
 * 渲染系統設置台 / Render the system settings console.
 * @param {Object} snapshot - the full state snapshot from overview or control-plane
 */
function renderSettingsConsole(snapshot) {
  const cpData = snapshot?.data?.demo_control_summary || {};
  const globalRuntime = snapshot?.data?.global_runtime || {};

  const riskSwitch = document.getElementById("settingsRiskSwitch");
  const demoAckSwitch = document.getElementById("settingsDemoAck");
  const learningApproval = document.getElementById("settingsLearningApproval");

  // 从 API 返回數據中無法直接获得這些字段的當前值——它们嵌在 control_plane 內層
  // These fields are not directly in overview; we display placeholder state from what we know.
  // Full value will be populated after /system/control-plane fetch in loadDashboard.
  if (riskSwitch) riskSwitch.value = "default_guarded"; // default; will be updated
  if (demoAckSwitch) demoAckSwitch.checked = true; // default; will be updated
  if (learningApproval) learningApproval.checked = true; // default; will be updated
}

/**
 * 用 /system/control-plane 的真實數據更新設置台 / Update settings console with real control-plane data.
 */
function updateSettingsConsoleFromControlPlane(controlPlane) {
  const cpData = controlPlane?.data || {};
  const riskEnvelope = cpData.risk_envelope || {};
  const demoCtrl = cpData.demo_control || {};

  const riskSwitch = document.getElementById("settingsRiskSwitch");
  const demoAckSwitch = document.getElementById("settingsDemoAck");

  if (riskSwitch) riskSwitch.value = riskEnvelope.risk_policy_switch || "default_guarded";
  if (demoAckSwitch) demoAckSwitch.checked = demoCtrl.demo_operator_ack_required !== false;

  // 顯示當前風險状态 / Show current risk envelope state
  const riskStateEl = document.getElementById("settingsRiskEnvelopeState");
  if (riskStateEl) {
    const effectiveState = riskEnvelope.effective_risk_envelope_state || "-";
    riskStateEl.innerHTML = `<span class="status-chip ${variantForState(effectiveState)}">${ocEsc(effectiveState)}</span>`;
  }
}
