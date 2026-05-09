/**
 * 玄衡 · Arcane Equilibrium Control Center — GUI JavaScript
 * 玄衡控制台前端脚本
 *
 * 功能概述 / Feature overview:
 * - 通过 HttpOnly Cookie 认证调用 Control API（已从 Bearer Token 迁移）
 *   Authenticates via HttpOnly cookie to call the Control API (migrated from Bearer Token)
 * - 展示系统运行态、健康、审计、产品族状态
 *   Displays system runtime state, health, audit trail, product family status
 * - 产品族配置设置台：可交互修改 enabled/visible/mode/action_permissions
 *   Product family config console: interactive controls for enabled/visible/mode/action_permissions
 * - 经营摘要面板：展示每日 PnL + 历史条目，支持手动录入成本和 PnL
 *   Business summary panel: daily PnL + history entries, supports manual cost/PnL entry
 * - 系统设置台：风险策略、Demo Ack、学习审批等开关
 *   Settings console: risk policy, demo ack, learning approval toggles
 * - 所有关键动作需要二次确认弹窗
 *   All critical actions require a second-confirmation modal
 *
 * 安全原则 / Safety principle:
 * 看得见 ≠ 被允许；被允许继续判断 ≠ 能执行；demo ≠ live。
 * Visible ≠ allowed; allowed to continue ≠ executable; demo ≠ live.
 */

"use strict";

// ── 全局状态 / Global state ──────────────────────────────────────────────────

let inMemoryToken = "";

// 当前状态修订版本号，用于构建 envelope / Current state revision for envelope construction
let currentStateRevision = 0;

// ── 常量：关键动作元数据 / Constants: critical action metadata ────────────────

/**
 * 需要二次确认的关键动作及其风险说明。
 * Critical actions requiring second confirmation, with risk descriptions.
 */
const CRITICAL_ACTIONS = {
  "set-demo-mode": {
    title: "切换到 Demo Reserved",
    subtitle: "Set global execution mode to demo_reserved",
    risk: "这一步只是把系统从「完全不走 demo 流程」改成「允许继续做 demo 相关判断」。它不是下单，不是开启 live，也不是马上获得执行权。",
    consequence: "点完后，系统只会进入「可以继续做 demo 检查」的状态。你之后仍然还要 validate、arm，甚至 future enable；所以这一步只是打开下一道门，不是直接放权。"
  },
  "enable-spot": {
    title: "开启 Spot / 现货产品配置",
    subtitle: "Enable spot family in shadow mode",
    risk: "这一步只影响现货产品族。它会让 spot/现货从「关闭/仅展示」进入 shadow 控制状态。shadow 的意思是：用于观察、验证、看控制结果，不是实际成交。",
    consequence: "点完后，只会改变现货这一类产品的控制展示和 gate 结果，不会影响其它产品族，也不会直接让账户获得真实现货下单权限。"
  },
  validate: {
    title: "验证 Demo 前提",
    subtitle: "Validate demo prerequisites and gates",
    risk: "这一步只是做检查。它会重新判断系统现在是否满足 demo 的前置条件。它不会切模式，也不会推进 demo 主状态。",
    consequence: "点完后，你主要会看到 gate 结果变了，比如「可以继续」还是「还不满足条件」。它不会直接提高执行权限。"
  },
  "arm-demo": {
    title: "执行 Demo Arm",
    subtitle: "Move demo state to armed_but_closed",
    risk: "这是 demo 流程里更关键的一步。它表示系统已经通过前置检查，进入「已准备好下一步，但仍然封闭」的状态。",
    consequence: "点完后，demo 会更接近后续 enable，但仍然不能直接执行。你可以把它理解成「已经准备好了，但保险还没真正打开」。"
  },
  bundle: {
    title: "执行安全复核打包",
    subtitle: "Run safe recheck bundle",
    risk: "这一步会把多项检查和刷新一起跑一遍。它适合在你想让整页判断一起更新时使用。",
    consequence: "点完后，readiness、gate、audit 等多个区域可能一起刷新。它本身不是切模式，也不是直接放权。"
  },
  "pf-config": {
    title: "修改产品族配置",
    subtitle: "Update product family control switches",
    risk: "这一步会修改指定产品族的 enabled/visible/mode 等控制开关。它不等于获得执行权，但会改变系统控制判断的输入。",
    consequence: "点完后，相应产品族的 capability 和 execution authority 会重新计算。这一步本身不直接开放 live 权限。"
  },
  "settings-change": {
    title: "修改系统设置",
    subtitle: "Apply system-level configuration change",
    risk: "这一步会修改全局系统设置，如风险策略或 Demo Ack 开关。这些设置影响整个控制判断链路。",
    consequence: "设置变更后立即生效。请确认你理解修改后的效果，特别是风险策略相关的变更。"
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

// ── 常量：产品族标签 / Constants: product family labels ──────────────────────

const PRODUCT_FAMILY_LABELS = {
  spot: "spot / 现货",
  margin: "margin / 保证金",
  perp_linear: "perp_linear / 线性永续",
  perp_inverse: "perp_inverse / 反向永续",
  options: "options / 期权",
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

// 动作权限名称映射 / Action permission name mappings
const ACTION_NAME_LABELS = {
  new_order: "新建订单 / new_order",
  cancel: "撤销 / cancel",
  amend: "改单 / amend",
  reduce_only: "只减仓 / reduce_only",
  increase_position: "加仓 / increase_position",
  close_position: "平仓 / close_position"
};

const ACTION_NAMES = Object.keys(ACTION_NAME_LABELS);

// 长期开关预留区 / Long-term switch preset area
const LONG_TERM_SWITCHES = [
  ["仅观察", "Observe Only", "当前只做展示位", "locked"],
  ["Demo Reserved", "Demo Reserved", "允许继续做 demo 判断", "preset"],
  ["Demo Enabled", "Demo Enabled", "后续阶段预留，当前不开放", "locked"],
  ["Live Locked", "Live Locked", "真实执行长期锁定", "locked"],
  ["紧急回锁", "Emergency Relock", "高优先级安全开关，当前只预留", "locked"],
  ["自动化锁定", "Automation Locked", "自动化真实执行暂不开放", "locked"],
  ["只读维护", "Readonly Maintenance", "维护模式后续接入", "locked"],
  ["审计增强", "Audit Enhanced", "长期审计扩展位", "planned"]
];

// ── 基础工具函数 / Basic utility functions ───────────────────────────────────

function headers() {
  // APR01-MEDIUM-13: Token is in HttpOnly cookie, sent automatically.
  // Authorization header kept only if inMemoryToken was manually set (legacy/API mode).
  // APR01-MEDIUM-13：Token 在 HttpOnly cookie 中，自动发送。
  // 仅在手动设置 inMemoryToken 时保留 Authorization header（旧版/API 模式）。
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
 * 根据状态值返回 CSS variant 名。
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
  // 格式化 PnL 数字为带正负号的字符串 / Format PnL number with sign
  const n = parseFloat(value);
  if (isNaN(n)) return "-";
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(4)} USDT`;
}

function fmtTs(tsMs) {
  // 将时间戳转为本地时间字符串 / Convert timestamp to local time string
  if (!tsMs) return "-";
  return new Date(tsMs).toLocaleString();
}

// ── UI 状态更新辅助 / UI state update helpers ─────────────────────────────────

/**
 * 安全设置元素文本 / Safely set element text by ID.
 * 如果元素不存在则静默忽略。
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
    validate: "验证 Demo",
    bundle: "安全复核打包",
    "set-demo-mode": "切到 Demo Reserved",
    "enable-spot": "开启 Spot / 现货产品配置",
    "arm-demo": "执行 Demo Arm",
    "pf-config": "产品族配置变更",
    "settings-change": "系统设置变更",
    "cost-entry": "费用录入",
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
  let hint = "动作执行完成。";
  let helper = "Action completed.";

  if (actionName === "validate") {
    hint = `系统刚完成一次检查：前提 gate = ${safeText(data.demo_prerequisites_gate_state)}；Arm gate = ${safeText(data.demo_arm_gate_state)}。`;
    helper = `This checked whether demo can continue, not whether execution is already open.`;
  } else if (actionName === "arm-demo") {
    hint = `Demo 状态现在是：${safeText(data.demo_state_switch)}。系统已更接近下一步，但仍未放开执行。`;
    helper = `The system moved closer to the next step, but execution is still not open.`;
  } else if (actionName === "set-demo-mode") {
    hint = `已接受"进入 Demo Reserved"配置。后续仍需 validate → arm → enable 才能获得执行权。`;
    helper = `Demo evaluation path is now allowed to continue, but no execution authority was opened.`;
  } else if (actionName === "enable-spot") {
    hint = `现货产品配置已修改。现货进入 shadow 控制展示，但不等于账户已能真实现货下单。`;
    helper = `Spot moved into shadow control display, but real spot trading authority is still separate.`;
  } else if (actionName === "bundle") {
    hint = `系统刚完成一轮统一复核刷新。多个判断结果可能已更新，但本步骤不直接放权。`;
    helper = `Multiple checks were refreshed together, but no authority was directly opened.`;
  } else if (actionName === "refresh") {
    hint = "界面已刷新。"; helper = "Dashboard refreshed.";
  } else if (actionName === "pf-config") {
    const applied = Object.keys(data.applied_changes || {});
    hint = `产品族 ${safeText(data.family)} 配置已更新，变更字段：${applied.join(", ") || "无"}。`;
    helper = `Product family ${safeText(data.family)} config updated.`;
  } else if (actionName === "settings-change") {
    hint = `系统设置已更新：${safeText((data.accepted_paths || []).join(", "))}。`;
    helper = `System settings updated.`;
  } else if (actionName === "cost-entry") {
    hint = `费用条目已录入，金额：${safeText(result?.data?.record_count_delta)} 条。`;
    helper = `Cost entry recorded.`;
  } else if (actionName === "pnl-entry") {
    hint = `PnL 条目已录入，类型：${safeText(data.entry_type)}。`;
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

// ── 双语标签辅助 / Bilingual label helpers ────────────────────────────────────

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

// ── KV 网格渲染 / KV grid rendering ──────────────────────────────────────────

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

// ── 确认弹窗 / Confirm modal ──────────────────────────────────────────────────

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

// ── API 调用 / API calls ──────────────────────────────────────────────────────

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
  // 构建标准请求 envelope / Build standard request envelope
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

// ── 渲染函数 / Render functions ───────────────────────────────────────────────

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

  // 更新历史条目列表 / Update recent entry lists
  renderCostEntries(businessData.cost_entries_recent || []);
  renderPnlEntries(businessData.pnl_entries_recent || []);

  // 更新成本分解 / Update cost breakdown
  renderCostBreakdown(businessData.cost_breakdown || {});

  // 更新条目总数 / Update entry totals
  const totals = businessData.entry_totals || {};
  if (el("bizCostCount")) el("bizCostCount").textContent = safeText(totals.total_cost_entries);
  if (el("bizPnlCount")) el("bizPnlCount").textContent = safeText(totals.total_pnl_entries);
  if (el("bizEvtCount")) el("bizEvtCount").textContent = safeText(totals.total_event_entries);
}

function renderCostEntries(entries) {
  const node = document.getElementById("costEntriesList");
  if (!node) return;
  if (!entries || entries.length === 0) {
    node.innerHTML = '<div class="entry-row muted-row">暂无费用记录 / No cost entries yet.</div>';
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
    node.innerHTML = '<div class="entry-row muted-row">暂无 PnL 记录 / No PnL entries yet.</div>';
    return;
  }
  node.innerHTML = entries.map((e) =>
    `<div class="entry-row">
       <span class="entry-ts">${fmtTs(e.recorded_ts_ms)}</span>
       <span class="entry-cat">${safeText(e.entry_type)}</span>
       <span class="entry-amt ${parseFloat(e.realized_pnl || 0) >= 0 ? "good" : "bad"}">已实现:${fmtPnl(e.realized_pnl)}</span>
       <span class="entry-note muted">未实现:${fmtPnl(e.unrealized_pnl)} ${safeText(e.note || "")}</span>
     </div>`
  ).join("");
}

function renderCostBreakdown(breakdown) {
  const node = document.getElementById("costBreakdownGrid");
  if (!node) return;
  const keys = Object.keys(breakdown);
  if (keys.length === 0) {
    node.innerHTML = '<span class="muted">暂无分类 / No categories yet.</span>';
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
  // 渲染每个产品族的配置卡片摘要 / Render config summary for each product family card
  Object.entries(PRODUCT_FAMILY_CONFIG_IDS).forEach(([family, ids]) => {
    const data = productFamilies[family];
    const summaryNode = document.getElementById(ids.summary);
    const metaNode = document.getElementById(ids.meta);
    if (!summaryNode || !metaNode) return;
    if (!data) {
      summaryNode.textContent = "-";
      metaNode.textContent = "暂无数据 / No data.";
      return;
    }
    const enabledText = booleanZh(data.controls.enabled_switch, "已启用 ✓", "未启用 ✗");
    const visibleText = booleanZh(data.controls.visibility_switch, "可见", "隐藏");
    summaryNode.textContent = `${enabledText} · ${visibleText} · ${safeText(data.controls.mode_switch)}`;
    metaNode.textContent =
      `交易所事实: ${safeText(data.facts.exchange_permission_fact)} | ` +
      `账户事实: ${safeText(data.facts.account_permission_fact)} | ` +
      `能力: ${safeText(data.derived.capability_state)}`;
  });
}

/**
 * 渲染产品族配置设置台的交互控件。
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

    // 动作权限格子 / Action permissions grid
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

    // 能力/执行状态徽章 / Capability/execution status badges
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
          <span class="switch-label">启用 / Enabled</span>
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
          应用配置 / Apply Config
          <span class="button-sub">sends to /control/product-family/{family}/config</span>
        </button>
      </div>
      <details class="perm-details">
        <summary class="perm-summary">动作权限 / Action Permissions</summary>
        <div class="perm-grid">${permRows}</div>
        <button class="pf-perm-apply-btn" data-family="${family}">
          应用权限变更 / Apply Permission Changes
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
         <button class="button-muted" disabled>长期预留（未开放）<span class="button-sub">preset only</span></button>
       </div>
     </div>`
  ).join("");
}

function renderSourceContext(sourceContext) {
  renderKvGrid("sourceContextGrid", [
    [zhEnPrimary("只读连接器", "Readonly Connector"), sourceContext.readonly_connector_name],
    [zhEnPrimary("执行连接器", "Execution Connector"), sourceContext.execution_connector_name || "not_attached"],
    [zhEnPrimary("私有 REST", "REST Private"), sourceContext.rest_private_connection_state],
    [zhEnPrimary("私有 WS", "WS Private"), sourceContext.ws_private_connection_state],
    [zhEnPrimary("Runtime 连接", "Runtime Connection"), sourceContext.runtime_connection_state],
    [zhEnPrimary("账户完整性", "Account Completeness"), sourceContext.account_fact_completeness_state],
    [zhEnPrimary("快照完整性", "Snapshot Completeness"), sourceContext.source_snapshot_completeness_state],
    [zhEnPrimary("角色分离", "Role Separation"), sourceContext.connector_role_separation_ok],
    [zhEnPrimary("Runtime 快照", "Runtime Snapshot"), sourceContext.pinned_runtime_snapshot_id]
  ]);
}

function renderHealth(overview) {
  const health = overview.data.health_summary;
  renderKvGrid("healthGrid", [
    [zhEnPrimary("总健康分", "Overall Health Score"), health.scores.overall_health_score],
    [zhEnPrimary("AI 健康分", "AI Health Score"), health.scores.ai_health_score],
    [zhEnPrimary("交易所健康分", "Exchange Health Score"), health.scores.exchange_health_score],
    [zhEnPrimary("新鲜度分", "Data Freshness Score"), health.scores.data_freshness_score],
    [zhEnPrimary("总 Gate", "Health Gates Overall"), health.gates.health_gates_overall_state],
    [zhEnPrimary("Timeout Gate", "Exchange Timeout Gate"), health.gates.exchange_timeout_gate_state],
    [zhEnPrimary("WS 断连 Gate", "WS Disconnect Gate"), health.gates.ws_disconnect_gate_state],
    [zhEnPrimary("延迟 Gate", "Latency Gate"), health.gates.latency_gate_state],
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
  body.innerHTML = rows || '<tr><td colspan="8" class="muted-cell">无数据 / No data</td></tr>';
}

/**
 * 渲染系统设置台 / Render the system settings console.
 * @param {Object} snapshot - the full state snapshot from overview or control-plane
 */
function renderSettingsConsole(snapshot) {
  const cpData = snapshot?.data?.demo_control_summary || {};
  const globalRuntime = snapshot?.data?.global_runtime || {};

  const riskSwitch = document.getElementById("settingsRiskSwitch");
  const demoAckSwitch = document.getElementById("settingsDemoAck");
  const learningApproval = document.getElementById("settingsLearningApproval");

  // 从 API 返回数据中无法直接获得这些字段的当前值——它们嵌在 control_plane 内层
  // These fields are not directly in overview; we display placeholder state from what we know.
  // Full value will be populated after /system/control-plane fetch in loadDashboard.
  if (riskSwitch) riskSwitch.value = "default_guarded"; // default; will be updated
  if (demoAckSwitch) demoAckSwitch.checked = true; // default; will be updated
  if (learningApproval) learningApproval.checked = true; // default; will be updated
}

/**
 * 用 /system/control-plane 的真实数据更新设置台 / Update settings console with real control-plane data.
 */
function updateSettingsConsoleFromControlPlane(controlPlane) {
  const cpData = controlPlane?.data || {};
  const riskEnvelope = cpData.risk_envelope || {};
  const demoCtrl = cpData.demo_control || {};

  const riskSwitch = document.getElementById("settingsRiskSwitch");
  const demoAckSwitch = document.getElementById("settingsDemoAck");

  if (riskSwitch) riskSwitch.value = riskEnvelope.risk_policy_switch || "default_guarded";
  if (demoAckSwitch) demoAckSwitch.checked = demoCtrl.demo_operator_ack_required !== false;

  // 显示当前风险状态 / Show current risk envelope state
  const riskStateEl = document.getElementById("settingsRiskEnvelopeState");
  if (riskStateEl) {
    const effectiveState = riskEnvelope.effective_risk_envelope_state || "-";
    riskStateEl.innerHTML = `<span class="status-chip ${variantForState(effectiveState)}">${ocEsc(effectiveState)}</span>`;
  }
}
