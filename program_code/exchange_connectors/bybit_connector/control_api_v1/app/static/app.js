/**
 * OpenClaw / Bybit Control Center — GUI JavaScript
 * OpenClaw / Bybit 控制台前端脚本
 *
 * 功能概述 / Feature overview:
 * - 通过 Bearer Token 认证调用 Control API
 *   Authenticates via Bearer Token to call the Control API
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
  modal.classList.remove("hidden");
  document.getElementById("confirmModalTitle").textContent = meta.title;
  document.getElementById("confirmModalSubtitle").textContent = meta.subtitle;
  document.getElementById("confirmModalRisk").textContent = meta.risk;
  document.getElementById("confirmModalConsequence").textContent = meta.consequence;
  return new Promise((resolve) => {
    const cleanup = () => {
      modal.classList.add("hidden");
      document.querySelectorAll("[data-close-modal='true']").forEach((node) =>
        node.replaceWith(node.cloneNode(true))
      );
      const proceed = document.getElementById("confirmModalProceed");
      proceed.replaceWith(proceed.cloneNode(true));
    };
    modal.querySelectorAll("[data-close-modal='true']").forEach((node) =>
      (node.onclick = () => { cleanup(); resolve(false); })
    );
    document.getElementById("confirmModalProceed").onclick = () => { cleanup(); resolve(true); };
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

// ── DOM 注入：动态创建 GUI 各区块 / DOM injection: dynamically create GUI sections ──

function ensureGuiEnhancements() {
  const pageShell = document.querySelector(".page-shell");
  if (!pageShell) return;

  // 修正顶栏文字 / Fix topbar text
  document.querySelector("label[for='tokenInput']")?.replaceChildren("访问令牌 / Bearer Token");
  document.getElementById("connectButton").textContent = "连接 / Connect";

  const topbarSubtle = document.querySelector(".topbar p");
  if (topbarSubtle) topbarSubtle.textContent = "RC2 控制台 · OpenClaw/Bybit 受保护控制面 / RC2 control console for guarded operations";

  // 更新表格头 / Update table headers
  const tableHeaders = [
    zhEnPrimary("产品族", "Product Family"),
    zhEnPrimary("交易所事实", "Exchange Fact"),
    zhEnPrimary("账户事实", "Account Fact"),
    zhEnPrimary("已启用", "Enabled"),
    zhEnPrimary("可见", "Visible"),
    zhEnPrimary("模式", "Mode"),
    zhEnPrimary("能力", "Capability"),
    zhEnPrimary("执行", "Execution")
  ];
  document.querySelectorAll("table thead th").forEach((th, idx) => {
    if (tableHeaders[idx]) th.innerHTML = tableHeaders[idx];
  });

  // 更新 summary grid 标签 / Update summary grid labels
  const summaryTexts = [
    zhEnPrimary("全局模式", "Global Mode"),
    zhEnPrimary("执行权限", "Execution Authority"),
    zhEnPrimary("Demo 状态", "Demo State"),
    zhEnPrimary("快照", "Snapshot"),
    zhEnPrimary("Runtime 快照", "Runtime Snapshot"),
    zhEnPrimary("仍受保护", "Runtime Protected")
  ];
  document.querySelectorAll("#summaryGrid .summary-label").forEach((node, index) => {
    if (summaryTexts[index]) node.innerHTML = summaryTexts[index];
  });

  // 更新快捷动作按钮 / Update quick action buttons
  const actionButtonLabels = {
    refresh: ["刷新概览", "refresh overview"],
    validate: ["验证 Demo 前提", "validate demo gates"],
    "set-demo-mode": ["切到 Demo Reserved", "global demo mode"],
    "enable-spot": ["开启 Spot / 现货产品配置", "spot product config"],
    "arm-demo": ["执行 Demo Arm", "move to armed_but_closed"],
    bundle: ["安全复核打包", "multi-step guarded recheck"]
  };
  document.querySelectorAll("[data-action]").forEach((btn) => {
    const name = btn.dataset.action;
    if (actionButtonLabels[name]) {
      btn.innerHTML = `${actionButtonLabels[name][0]}<span class="button-sub">${actionButtonLabels[name][1]}</span>`;
    }
  });

  // 更新动作摘要 / Update action summary labels
  const actionTexts = [
    zhEnPrimary("最近动作", "Last Action"),
    zhEnPrimary("结果", "Result"),
    zhEnPrimary("状态版本", "State Revision"),
    zhEnPrimary("审计引用", "Audit Ref")
  ];
  document.querySelectorAll("#actionSummaryGrid .summary-label").forEach((node, index) => {
    if (actionTexts[index]) node.innerHTML = actionTexts[index];
  });

  // ── 注入：关键概念提示 / Inject: key concept hints ─────────────────────────
  if (!document.getElementById("guiConceptHints")) {
    const hintCard = document.createElement("section");
    hintCard.className = "card glossary-card";
    hintCard.id = "guiConceptHints";
    hintCard.innerHTML = `
      <details class="raw-toggle">
        <summary>${zhEnPrimary("关键概念提示（按需展开）", "Key Concept Hints")}</summary>
        <div class="glossary-wrap" style="padding:16px;">
          ${annotateGlossary("事实", "Facts", "先看交易所、账户、runtime 实际返回了什么。事实是「真实情况」，不是你点按钮点出来的权限。", "Facts are the actual returned conditions, not permissions granted by a button.")}
          ${annotateGlossary("权限配置", "Control Permission", "再看你在控制面配置了什么，例如 demo reserved、spot shadow。这些是「允许系统往下判断」，不是「马上能执行」。", "Control permissions allow the system to continue guarded evaluation; they are not immediate execution authority.")}
          ${annotateGlossary("状态推进", "State Progress", "最后看 demo validate、demo arm 这类步骤。它们表示系统流程往前走了，但仍可能保持封闭。", "State progress means the workflow moved forward, but it can still remain closed.")}
          ${annotateGlossary("最重要的一句", "Most Important Rule", "看得见 ≠ 被允许；被允许继续判断 ≠ 能执行；demo ≠ live。", "Visible is not allowed; allowed to continue is not executable; demo is not live.")}
        </div>
      </details>`;
    const hero = document.querySelector(".hero-card");
    if (hero) hero.after(hintCard);
  }

  // ── 注入：运行模式控制 + 经营摘要（双列）/ Inject: runtime mode control + business summary ──
  if (!document.getElementById("runtimeModeSection")) {
    const grid = document.createElement("section");
    grid.className = "grid two-up injected-grid";
    grid.id = "modeBizGrid";
    grid.innerHTML = `
      <section class="card" id="runtimeModeSection">
        <div class="card-header-row">
          <div>
            <h2>${zhEnPrimary("运行模式控制", "Runtime Mode Control")}</h2>
            <p class="subtle">受保护模式切换骨架；当前只开放低风险 guarded 动作，live 仍锁定。</p>
          </div>
        </div>
        <div class="mode-grid">
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("阶段标签", "Stage Label")}</span><strong id="modeStageLabel">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("能力状态", "Capability State")}</span><strong id="modeCapabilityState">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("Demo Arm Gate", "Demo Arm Gate")}</span><strong id="modeDemoArmGate">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("Demo Enable Gate", "Demo Enable Gate")}</span><strong id="modeDemoEnableGate">-</strong></div>
        </div>
        <div class="mode-actions">
          <button data-action="set-demo-mode">切到 Demo Reserved<span class="button-sub">global demo mode</span></button>
          <button data-action="enable-spot">开启 Spot<span class="button-sub">spot product config</span></button>
          <button data-action="validate">验证 Demo 前提<span class="button-sub">validate demo gates</span></button>
          <button data-action="arm-demo">执行 Demo Arm<span class="button-sub">move to armed_but_closed</span></button>
          <button class="button-muted" disabled>观测模式<span class="button-sub">Observe Only · later</span></button>
          <button class="button-muted" disabled>Live 模式<span class="button-sub">Live Mode · locked</span></button>
        </div>
        <div class="mode-note">先决定"系统要不要进入 demo/spot 的受保护流程"，再决定"现在是否满足继续前进的条件"。这不是真实执行权限开关区。</div>
      </section>

      <section class="card" id="businessSummarySection">
        <div class="card-header-row">
          <div>
            <h2>${zhEnPrimary("经营与收益摘要", "Business & Income Summary")}</h2>
            <p class="subtle">每日 PnL 指标 + 历史条目。来自 /system/business/summary。</p>
          </div>
        </div>
        <div class="summary-grid business-grid">
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("已实现盈亏", "Realized PnL")}</span><strong id="bizRealizedPnl">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("未实现盈亏", "Unrealized PnL")}</span><strong id="bizUnrealizedPnl">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("毛盈亏", "Gross PnL")}</span><strong id="bizGrossPnl">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("总成本", "Total Cost")}</span><strong id="bizTotalCost">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("净经营盈亏", "Net Operating PnL")}</span><strong id="bizNetOperatingPnl">-</strong></div>
          <div class="summary-item"><span class="summary-label">${zhEnPrimary("业务事件数", "Business Event Count")}</span><strong id="bizEventCount">-</strong></div>
        </div>
        <div class="biz-totals">
          <span>${zhEnPrimary("费用条目", "Cost entries")}: <strong id="bizCostCount">-</strong></span>
          <span>${zhEnPrimary("PnL 条目", "PnL entries")}: <strong id="bizPnlCount">-</strong></span>
          <span>${zhEnPrimary("业务事件", "Event entries")}: <strong id="bizEvtCount">-</strong></span>
        </div>
        <div class="mode-note">当前来自 /system/business/summary，包含每日 PnL 快照 + 最近历史条目。</div>
      </section>`;
    const firstGrid = document.querySelector(".page-shell > .grid.two-up");
    if (firstGrid) firstGrid.before(grid);
  }

  // ── 注入：产品族配置区（只读摘要卡片）/ Inject: product family config summary cards ──
  if (!document.getElementById("productFamilyConfigSection")) {
    const card = document.createElement("section");
    card.className = "card";
    card.id = "productFamilyConfigSection";
    card.innerHTML = `
      <div class="card-header-row">
        <div>
          <h2>${zhEnPrimary("产品族配置", "Product Family Configuration")}</h2>
          <p class="subtle">当前状态快照。点击下方设置台可修改。/ Current state snapshot. Use the config console below to modify.</p>
        </div>
      </div>
      <div class="summary-grid business-grid config-family-grid">
        ${Object.entries(PRODUCT_FAMILY_CONFIG_IDS).map(([family, ids]) => `
          <div class="summary-item config-family-card">
            <span class="summary-label">${zhEnPrimary(PRODUCT_FAMILY_LABELS[family] || family, family)}</span>
            <strong id="${ids.summary}">-</strong>
            <div id="${ids.meta}" class="family-card-meta">-</div>
          </div>`).join("")}
      </div>`;
    const productFactsCard = Array.from(document.querySelectorAll(".page-shell > .card"))
      .find((node) => node.querySelector("h2")?.textContent.includes("产品族事实"));
    if (productFactsCard) productFactsCard.before(card);
  }

  // ── 注入：产品族配置设置台（可交互）/ Inject: product family config console (interactive) ──
  if (!document.getElementById("pfEditorSection")) {
    const card = document.createElement("section");
    card.className = "card";
    card.id = "pfEditorSection";
    card.innerHTML = `
      <div class="card-header-row">
        <div>
          <h2>${zhEnPrimary("产品族配置设置台", "Product Family Config Console")}</h2>
          <p class="subtle">交互式配置每个产品族的控制开关。变更会调用 /control/product-family/{family}/config。
            / Interactive controls for each product family. Changes call /control/product-family/{family}/config.</p>
        </div>
      </div>
      <div id="pfEditorContainer" class="pf-editor-grid">
        <div class="muted-row">等待加载 / Loading...</div>
      </div>
      <div class="mode-note">
        <strong>安全提示 / Safety:</strong> mode_switch 只允许 disabled / observe_only / shadow_only。
        live 相关模式不在当前阶段开放。/ live-related modes are NOT available at this stage.
      </div>`;
    const configCard = document.getElementById("productFamilyConfigSection");
    if (configCard) configCard.after(card);
  }

  // ── 注入：长期开关预留 / Inject: long-term switch preset ───────────────────
  if (!document.getElementById("longTermSwitchSection")) {
    const card = document.createElement("section");
    card.className = "card";
    card.id = "longTermSwitchSection";
    card.innerHTML = `
      <div class="card-header-row">
        <div>
          <h2>${zhEnPrimary("长期开关预留", "Long-Term Switch Preset")}</h2>
          <p class="subtle">这里只预留长期会用到的结构和名字，不在当前章节开放真实高权限能力。</p>
        </div>
      </div>
      <div class="summary-grid switch-grid" id="longTermSwitchGrid"></div>
      <div class="mode-note">当前这一块的定位是：先把未来一定会出现的总开关和安全开关位置固定下来，避免后面临时加入口。现在全部只做展示、锁定或预留。</div>`;
    const pfEditor = document.getElementById("pfEditorSection");
    if (pfEditor) pfEditor.after(card);
  }

  // ── 注入：收益录入面板 / Inject: income & cost entry panel ─────────────────
  if (!document.getElementById("incomeEntrySection")) {
    const card = document.createElement("section");
    card.className = "card";
    card.id = "incomeEntrySection";
    card.innerHTML = `
      <div class="card-header-row">
        <div>
          <h2>${zhEnPrimary("收益与成本录入", "Income & Cost Entry")}</h2>
          <p class="subtle">手动录入费用条目和 PnL 更新。数据会累计到每日经营摘要。
            / Manually record cost entries and PnL updates. Data accumulates in the daily business summary.</p>
        </div>
      </div>
      <div class="grid two-up entry-grid">
        <div class="entry-form-card">
          <h3 class="entry-form-title">${zhEnPrimary("费用录入", "Cost Entry")}</h3>
          <div class="form-row">
            <label class="form-label">金额 / Amount (USDT)</label>
            <input type="number" id="costAmount" step="0.0001" placeholder="0.0000" class="form-input">
          </div>
          <div class="form-row">
            <label class="form-label">类别 / Category</label>
            <select id="costCategory" class="form-input">
              <option value="manual">manual（手动）</option>
              <option value="ai_api">ai_api（AI API 费用）</option>
              <option value="exchange_fee">exchange_fee（交易所手续费）</option>
              <option value="slippage">slippage（滑点）</option>
              <option value="infra">infra（基础设施）</option>
            </select>
          </div>
          <div class="form-row">
            <label class="form-label">备注 / Note</label>
            <input type="text" id="costNote" placeholder="可选 / optional" class="form-input">
          </div>
          <button id="submitCostEntry" class="entry-submit-btn">
            录入费用 / Record Cost
            <span class="button-sub">POST /input/cost</span>
          </button>
        </div>

        <div class="entry-form-card">
          <h3 class="entry-form-title">${zhEnPrimary("PnL 录入", "PnL Entry")}</h3>
          <div class="form-row">
            <label class="form-label">类型 / Type</label>
            <select id="pnlType" class="form-input">
              <option value="realized">realized（已实现）</option>
              <option value="unrealized">unrealized（未实现）</option>
              <option value="manual_adjustment">manual_adjustment（手动调整）</option>
            </select>
          </div>
          <div class="form-row">
            <label class="form-label">已实现盈亏增量 / Realized PnL delta (USDT)</label>
            <input type="number" id="pnlRealized" step="0.0001" placeholder="0.0000" class="form-input">
          </div>
          <div class="form-row">
            <label class="form-label">未实现盈亏（快照）/ Unrealized PnL snapshot (USDT)</label>
            <input type="number" id="pnlUnrealized" step="0.0001" placeholder="0.0000" class="form-input">
          </div>
          <div class="form-row">
            <label class="form-label">标的 / Symbol (可选)</label>
            <input type="text" id="pnlSymbol" placeholder="e.g. BTCUSDT" class="form-input">
          </div>
          <button id="submitPnlEntry" class="entry-submit-btn">
            录入 PnL / Record PnL
            <span class="button-sub">POST /input/pnl-entry</span>
          </button>
        </div>
      </div>

      <div class="entries-history">
        <div class="entries-col">
          <h4 class="entries-col-title">${zhEnPrimary("最近费用记录", "Recent Cost Entries")}</h4>
          <div id="costEntriesList" class="entry-list">等待加载 / Loading...</div>
        </div>
        <div class="breakdown-col">
          <h4 class="entries-col-title">${zhEnPrimary("成本分解", "Cost Breakdown")}</h4>
          <div id="costBreakdownGrid" class="breakdown-grid">-</div>
        </div>
      </div>

      <div class="entries-history">
        <div class="entries-col full-width">
          <h4 class="entries-col-title">${zhEnPrimary("最近 PnL 记录", "Recent PnL Entries")}</h4>
          <div id="pnlEntriesList" class="entry-list">等待加载 / Loading...</div>
        </div>
      </div>`;

    const longTermSection = document.getElementById("longTermSwitchSection");
    if (longTermSection) longTermSection.after(card);
  }

  // ── 注入：系统设置台 / Inject: system settings console ─────────────────────
  if (!document.getElementById("settingsConsoleSection")) {
    const card = document.createElement("section");
    card.className = "card";
    card.id = "settingsConsoleSection";
    card.innerHTML = `
      <div class="card-header-row">
        <div>
          <h2>${zhEnPrimary("系统设置台", "System Settings Console")}</h2>
          <p class="subtle">调整全局风险策略、Demo 确认要求等系统级开关。所有变更有二次确认保护。
            / Adjust global risk policy, demo confirmation requirement, etc. All changes require second confirmation.</p>
        </div>
      </div>
      <div class="settings-grid">
        <div class="settings-block">
          <h4 class="settings-block-title">${zhEnPrimary("风险策略", "Risk Policy")}</h4>
          <div class="settings-row">
            <label class="settings-label">风险策略开关 / Risk Policy Switch</label>
            <select id="settingsRiskSwitch" class="form-input settings-select">
              <option value="default_guarded">default_guarded（默认受保护）</option>
              <option value="manual_blocked">manual_blocked（手动阻断）</option>
            </select>
          </div>
          <div class="settings-row">
            <label class="settings-label">当前风险包络状态 / Current Risk Envelope State</label>
            <span id="settingsRiskEnvelopeState">-</span>
          </div>
          <button id="applyRiskSwitch" class="settings-apply-btn">
            应用风险策略 / Apply Risk Policy
            <span class="button-sub">PUT control_plane.risk_envelope.risk_policy_switch</span>
          </button>
        </div>

        <div class="settings-block">
          <h4 class="settings-block-title">${zhEnPrimary("Demo 与学习开关", "Demo & Learning Switches")}</h4>
          <div class="settings-row">
            <label class="settings-label">Demo 操作员确认要求 / Demo Operator Ack Required</label>
            <input type="checkbox" id="settingsDemoAck" class="settings-checkbox" checked>
          </div>
          <div class="settings-row">
            <label class="settings-label">学习实验需人工审批 / Learning Experiments Require Approval</label>
            <input type="checkbox" id="settingsLearningApproval" class="settings-checkbox" checked>
          </div>
          <button id="applyDemoLearningSettings" class="settings-apply-btn">
            应用 Demo/Learning 设置 / Apply Demo/Learning Settings
            <span class="button-sub">PUT control_plane.demo_control + learning_state</span>
          </button>
        </div>
      </div>
      <div class="mode-note">
        ⚠️ 风险策略 manual_blocked 会立即阻断所有执行权限判断。生产环境慎用。
        / ⚠️ Risk policy manual_blocked immediately blocks all execution authority. Use carefully in production.
      </div>`;

    const incomeSection = document.getElementById("incomeEntrySection");
    if (incomeSection) incomeSection.after(card);
  }

  // ── 注入：学习驾驶舱 / Inject: Learning Cockpit ─────────────────────────────
  // L 章核心 GUI 区域：四标签页（观察 / 经验 / 假设 / 实验）+ 录入表单 + 审批按钮。
  // L-chapter core GUI section: four tabs (observations / lessons / hypotheses / experiments)
  // + input forms + approval buttons.
  if (!document.getElementById("learningCockpitSection")) {
    const card = document.createElement("section");
    card.className = "card";
    card.id = "learningCockpitSection";
    card.innerHTML = `
      <div class="card-header-row">
        <div>
          <h2>${zhEnPrimary("学习驾驶舱", "Learning Cockpit")}</h2>
          <p class="subtle">L 章：观察流 / 经验记忆 / 假设队列 / 实验队列。所有记录区分事实、推断、假设（原则 8）。
            / L-Chapter: Observation Feed / Lessons Memory / Hypothesis Queue / Experiment Queue. All entries tagged with fact/inference/hypothesis (Principle 8).</p>
        </div>
      </div>
      <div class="learning-tabs">
        <button class="learning-tab active" data-tab="observations">${zhEnPrimary("观察流", "Observations")}</button>
        <button class="learning-tab" data-tab="lessons">${zhEnPrimary("经验记忆", "Lessons")}</button>
        <button class="learning-tab" data-tab="hypotheses">${zhEnPrimary("假设队列", "Hypotheses")}</button>
        <button class="learning-tab" data-tab="experiments">${zhEnPrimary("实验队列", "Experiments")}</button>
        <button class="learning-tab" data-tab="reviewQueue">${zhEnPrimary("审核队列", "Review Queue")}</button>
      </div>

      <div class="learning-tab-content active" id="tabObservations">
        <div class="entry-form-card learning-form">
          <h4 class="entry-form-title">${zhEnPrimary("录入观察", "Record Observation")}</h4>
          <div class="form-row">
            <label class="form-label">标题 / Title</label>
            <input type="text" id="obsTitle" placeholder="简要描述 / Brief description" class="form-input">
          </div>
          <div class="form-row">
            <label class="form-label">详情 / Detail</label>
            <textarea id="obsDetail" rows="2" placeholder="完整观察内容 / Full observation" class="form-input form-textarea"></textarea>
          </div>
          <div class="form-row form-row-inline">
            <div>
              <label class="form-label">类别 / Category</label>
              <select id="obsCategory" class="form-input">
                <option value="market">market（市场）</option>
                <option value="execution">execution（执行）</option>
                <option value="cost">cost（成本）</option>
                <option value="system">system（系统）</option>
                <option value="strategy">strategy（策略）</option>
                <option value="other">other（其他）</option>
              </select>
            </div>
            <div>
              <label class="form-label">置信度 / Confidence</label>
              <select id="obsConfidence" class="form-input">
                <option value="fact">fact（事实）</option>
                <option value="inference">inference（推断）</option>
                <option value="hypothesis">hypothesis（假设）</option>
              </select>
            </div>
          </div>
          <button id="submitObservation" class="entry-submit-btn">
            录入观察 / Record Observation
            <span class="button-sub">POST /input/observation</span>
          </button>
        </div>
        <div id="observationsList" class="learning-records-list">等待加载 / Loading...</div>
      </div>

      <div class="learning-tab-content" id="tabLessons">
        <div class="entry-form-card learning-form">
          <h4 class="entry-form-title">${zhEnPrimary("录入经验", "Record Lesson")}</h4>
          <div class="form-row">
            <label class="form-label">标题 / Title</label>
            <input type="text" id="lessonTitle" placeholder="经验概要 / Lesson summary" class="form-input">
          </div>
          <div class="form-row">
            <label class="form-label">详情 / Detail</label>
            <textarea id="lessonDetail" rows="2" placeholder="经验详情 / Full lesson" class="form-input form-textarea"></textarea>
          </div>
          <div class="form-row form-row-inline">
            <div>
              <label class="form-label">类别 / Category</label>
              <select id="lessonCategory" class="form-input">
                <option value="market_pattern">market_pattern（市场规律）</option>
                <option value="cost_insight">cost_insight（成本洞察）</option>
                <option value="execution_quality">execution_quality（执行质量）</option>
                <option value="strategy">strategy（策略）</option>
                <option value="system">system（系统）</option>
                <option value="other">other（其他）</option>
              </select>
            </div>
            <div>
              <label class="form-label">置信度 / Confidence</label>
              <select id="lessonConfidence" class="form-input">
                <option value="fact">fact（事实）</option>
                <option value="inference">inference（推断）</option>
                <option value="hypothesis">hypothesis（假设）</option>
              </select>
            </div>
          </div>
          <button id="submitLesson" class="entry-submit-btn">
            录入经验 / Record Lesson
            <span class="button-sub">POST /input/lesson</span>
          </button>
        </div>
        <div id="lessonsList" class="learning-records-list">等待加载 / Loading...</div>
      </div>

      <div class="learning-tab-content" id="tabHypotheses">
        <div class="entry-form-card learning-form">
          <h4 class="entry-form-title">${zhEnPrimary("提出假设", "Propose Hypothesis")}</h4>
          <div class="form-row">
            <label class="form-label">标题 / Title</label>
            <input type="text" id="hypTitle" placeholder="假设名称 / Hypothesis name" class="form-input">
          </div>
          <div class="form-row">
            <label class="form-label">描述 / Description</label>
            <textarea id="hypDescription" rows="2" placeholder="假设描述 / Description" class="form-input form-textarea"></textarea>
          </div>
          <div class="form-row">
            <label class="form-label">可检验预测 / Testable Prediction</label>
            <textarea id="hypPrediction" rows="2" placeholder="什么结果能证实或否定这个假设 / What outcome confirms or denies" class="form-input form-textarea"></textarea>
          </div>
          <button id="submitHypothesis" class="entry-submit-btn">
            提出假设 / Propose Hypothesis
            <span class="button-sub">POST /input/hypothesis (confidence_level = hypothesis)</span>
          </button>
        </div>
        <div id="hypothesesList" class="learning-records-list">等待加载 / Loading...</div>
      </div>

      <div class="learning-tab-content" id="tabExperiments">
        <div class="entry-form-card learning-form">
          <h4 class="entry-form-title">${zhEnPrimary("提出实验", "Propose Experiment")}</h4>
          <div class="form-row">
            <label class="form-label">关联假设 ID / Hypothesis ID</label>
            <input type="text" id="expHypothesisId" placeholder="hyp:..." class="form-input">
          </div>
          <div class="form-row">
            <label class="form-label">标题 / Title</label>
            <input type="text" id="expTitle" placeholder="实验名称 / Experiment name" class="form-input">
          </div>
          <div class="form-row">
            <label class="form-label">描述 / Description</label>
            <textarea id="expDescription" rows="2" placeholder="实验描述 / Description" class="form-input form-textarea"></textarea>
          </div>
          <div class="form-row">
            <label class="form-label">方法 / Method</label>
            <textarea id="expMethod" rows="2" placeholder="如何验证 / How to test" class="form-input form-textarea"></textarea>
          </div>
          <div class="form-row">
            <label class="form-label">成功标准 / Success Criteria</label>
            <input type="text" id="expSuccessCriteria" placeholder="什么结果算成功 / What counts as success" class="form-input">
          </div>
          <button id="submitExperiment" class="entry-submit-btn">
            提出实验 / Propose Experiment
            <span class="button-sub">POST /input/experiment</span>
          </button>
        </div>
        <div id="experimentsList" class="learning-records-list">等待加载 / Loading...</div>
      </div>

      <div class="learning-tab-content" id="tabReviewQueue">
        <div class="review-scan-bar">
          <button class="auto-scan-btn" data-scan="observations">
            扫描观察 / Scan Observations
            <span class="button-sub">POST /learning/auto/scan-observations</span>
          </button>
          <button class="auto-scan-btn" data-scan="lessons">
            扫描经验 / Scan Lessons
            <span class="button-sub">POST /learning/auto/scan-lessons</span>
          </button>
          <button class="auto-scan-btn" data-scan="hypotheses">
            扫描假设 / Scan Hypotheses
            <span class="button-sub">POST /learning/auto/scan-hypotheses</span>
          </button>
        </div>
        <div id="reviewQueueList" class="learning-records-list">等待加载 / Loading...</div>
        <div id="reviewRecentDecided" class="learning-records-list"></div>
      </div>

      <div class="learning-stats" id="learningStats">
        <span>${zhEnPrimary("观察", "Obs")}: <strong id="lrnObsCount">0</strong></span>
        <span>${zhEnPrimary("经验", "Lessons")}: <strong id="lrnLesCount">0</strong></span>
        <span>${zhEnPrimary("假设", "Hyp")}: <strong id="lrnHypCount">0</strong></span>
        <span>${zhEnPrimary("实验", "Exp")}: <strong id="lrnExpCount">0</strong></span>
        <span>${zhEnPrimary("待审批", "Pending")}: <strong id="lrnPendingCount">0</strong></span>
      </div>`;

    const settingsSection = document.getElementById("settingsConsoleSection");
    if (settingsSection) settingsSection.after(card);
  }

  // ── 注入：净 PnL 仪表盘 / Inject: Net PnL Dashboard ────────────────────────
  // L 章 Net PnL 模块：周期趋势、成本分解、快照保存。
  // L-chapter Net PnL module: period trends, cost breakdown, snapshot saving.
  if (!document.getElementById("netPnlDashboardSection")) {
    const card = document.createElement("section");
    card.className = "card";
    card.id = "netPnlDashboardSection";
    card.innerHTML = `
      <div class="card-header-row">
        <div>
          <h2>${zhEnPrimary("净 PnL 仪表盘", "Net PnL Dashboard")}</h2>
          <p class="subtle">含所有成本分解的盈亏趋势追踪。来自 /learning/net-pnl。
            / PnL trend tracking with full cost breakdown. From /learning/net-pnl.</p>
        </div>
      </div>
      <div class="summary-grid business-grid">
        <div class="summary-item"><span class="summary-label">${zhEnPrimary("已实现盈亏", "Realized PnL")}</span><strong id="npRealizedPnl">-</strong></div>
        <div class="summary-item"><span class="summary-label">${zhEnPrimary("未实现盈亏", "Unrealized PnL")}</span><strong id="npUnrealizedPnl">-</strong></div>
        <div class="summary-item"><span class="summary-label">${zhEnPrimary("毛盈亏", "Gross PnL")}</span><strong id="npGrossPnl">-</strong></div>
        <div class="summary-item"><span class="summary-label">${zhEnPrimary("总成本", "Total Cost")}</span><strong id="npTotalCost">-</strong></div>
        <div class="summary-item"><span class="summary-label">${zhEnPrimary("净经营盈亏", "Net Operating PnL")}</span><strong id="npNetPnl" class="pnl-highlight">-</strong></div>
        <div class="summary-item"><span class="summary-label">${zhEnPrimary("周期快照数", "Period Snapshots")}</span><strong id="npSnapshotCount">-</strong></div>
      </div>
      <div class="net-pnl-actions">
        <div class="form-row form-row-inline">
          <div>
            <label class="form-label">周期标签 / Period Label</label>
            <input type="text" id="periodLabel" placeholder="e.g. 2026-03-26" class="form-input">
          </div>
          <button id="savePeriodSnapshot" class="entry-submit-btn">
            保存快照 / Save Period Snapshot
            <span class="button-sub">POST /input/pnl-period-snapshot</span>
          </button>
        </div>
      </div>
      <div class="entries-history">
        <div class="entries-col">
          <h4 class="entries-col-title">${zhEnPrimary("成本分解", "Cost Breakdown")}</h4>
          <div id="npCostBreakdown" class="breakdown-grid">-</div>
        </div>
        <div class="entries-col">
          <h4 class="entries-col-title">${zhEnPrimary("周期趋势", "Period Trend")}</h4>
          <div id="npTrendList" class="entry-list">-</div>
        </div>
      </div>`;

    const learningSection = document.getElementById("learningCockpitSection");
    if (learningSection) learningSection.after(card);
  }

  // ── 注入：确认弹窗 / Inject: confirmation modal ─────────────────────────────
  if (!document.getElementById("confirmModal")) {
    const modal = document.createElement("div");
    modal.id = "confirmModal";
    modal.className = "confirm-modal hidden";
    modal.innerHTML = `
      <div class="confirm-modal-backdrop" data-close-modal="true"></div>
      <div class="confirm-modal-dialog" role="dialog" aria-modal="true" aria-labelledby="confirmModalTitle">
        <div class="confirm-modal-header">
          <h3 id="confirmModalTitle">关键动作确认</h3>
          <button class="confirm-close" data-close-modal="true">×</button>
        </div>
        <div class="confirm-modal-body">
          <div id="confirmModalSubtitle" class="confirm-subtitle">-</div>
          <div class="confirm-block">
            <div class="confirm-label">风险说明 / Risk</div>
            <div id="confirmModalRisk">-</div>
          </div>
          <div class="confirm-block">
            <div class="confirm-label">后果说明 / Consequence</div>
            <div id="confirmModalConsequence">-</div>
          </div>
          <div class="confirm-note">请确认你理解该动作不会直接开放真实 live execution，但会推进控制状态或影响可见控制结果。</div>
        </div>
        <div class="confirm-modal-footer">
          <button class="button-muted confirm-cancel" data-close-modal="true">取消 / Cancel</button>
          <button id="confirmModalProceed">确认执行 / Confirm</button>
        </div>
      </div>`;
    document.body.appendChild(modal);
  }
}

// ── 主数据加载 / Main data loading ───────────────────────────────────────────

async function loadDashboard() {
  ensureGuiEnhancements();

  // 并发加载所有数据（含 L 章学习 + 净 PnL 端点）
  // Load all data concurrently (including L-chapter learning + net PnL endpoints)
  const [overview, controlPlane, sourceContext, audit, productFamilies, businessSummary,
         learningFeed, learningExperiments, netPnlDashboard, reviewQueue] = await Promise.all([
    apiGet("/api/v1/system/overview"),
    apiGet("/api/v1/system/control-plane"),
    apiGet("/api/v1/system/source-context"),
    apiGet("/api/v1/system/audit-summary"),
    apiGet("/api/v1/system/product-families"),
    apiGet("/api/v1/system/business/summary"),
    apiGet("/api/v1/learning/feed"),
    apiGet("/api/v1/learning/experiments"),
    apiGet("/api/v1/learning/net-pnl"),
    apiGet("/api/v1/learning/review-queue")
  ]);

  // 渲染各区块 / Render each section
  renderSummary(overview);
  renderModeControl(overview);
  renderBusinessSummary(businessSummary.data);
  renderProductFamilyConfig(productFamilies.data);
  renderProductFamilyEditor(productFamilies.data, controlPlane.data);
  renderLongTermSwitches();
  renderSourceContext(sourceContext.data);
  renderHealth(overview);
  renderProductFamilies(productFamilies.data);
  updateSettingsConsoleFromControlPlane(controlPlane);

  // L 章渲染 / L-chapter rendering
  renderLearningFeed(learningFeed.data);
  renderLearningExperiments(learningExperiments.data);
  renderNetPnlDashboard(netPnlDashboard.data);
  renderReviewQueue(reviewQueue.data);

  // 调试原文 / Debug raw JSON
  document.getElementById("overviewBox").textContent = pretty(overview);
  document.getElementById("controlPlaneBox").textContent = pretty(controlPlane);
  document.getElementById("auditBox").textContent = pretty(audit);

  // Paper Trading 加载 / Load paper trading data
  refreshPaperTrading().catch(() => {});
}

// ── 动作处理：快捷动作 / Action handler: quick actions ───────────────────────

async function runQuickAction(actionName) {
  try {
    if (actionName !== "refresh") {
      const confirmed = await openConfirmModal(actionName);
      if (!confirmed) {
        setActionSummary(
          "已取消 / Cancelled", "blocked", "-", "-",
          "用户取消了关键动作确认。 / User cancelled.", { cancelled: true, action: actionName }
        );
        return;
      }
    }

    if (actionName === "refresh") {
      await loadDashboard();
      setActionSummary(
        "刷新概览 / refresh overview", "success", currentStateRevision, "-",
        "界面已刷新。 / Dashboard refreshed.", { message: "Refresh completed." }
      );
      return;
    }

    const env = baseEnvelope();
    let result;

    if (actionName === "validate")
      result = await apiPost("/api/v1/control/demo/validate", env);
    else if (actionName === "bundle")
      result = await apiPost("/api/v1/control/safe-recheck-bundle", env);
    else if (actionName === "set-demo-mode")
      result = await apiPost("/api/v1/input/config-change", {
        ...env,
        payload: { changes: [{ path: "global_runtime.controls.global_execution_mode_switch", value: "demo_reserved" }] }
      });
    else if (actionName === "enable-spot")
      result = await apiPost("/api/v1/input/config-change", {
        ...env,
        payload: { changes: [
          { path: "product_family_status.spot.controls.enabled_switch", value: true },
          { path: "product_family_status.spot.controls.mode_switch", value: "shadow_only" }
        ]}
      });
    else if (actionName === "arm-demo")
      result = await apiPost("/api/v1/control/demo/arm", {
        ...env,
        payload: { acknowledged: true }
      });

    summarizeActionResult(actionName, result);
    await loadDashboard();
  } catch (error) {
    setActionSummary("动作失败 / Action Failed", "failed", "-", "-", String(error), String(error));
  }
}

// ── 动作处理：产品族配置应用 / Action handler: product family config apply ──────

async function applyProductFamilyConfig(family) {
  const enabledEl = document.getElementById(`pf-enabled-${family}`);
  const visibleEl = document.getElementById(`pf-visible-${family}`);
  const modeEl = document.getElementById(`pf-mode-${family}`);
  if (!enabledEl || !visibleEl || !modeEl) return;

  const payload = {
    enabled_switch: enabledEl.checked,
    visibility_switch: visibleEl.checked,
    mode_switch: modeEl.value
  };

  const confirmed = await openConfirmModal("pf-config");
  if (!confirmed) return;

  try {
    const result = await apiPost(
      `/api/v1/control/product-family/${family}/config`,
      baseEnvelope({ payload })
    );
    summarizeActionResult("pf-config", result);
    await loadDashboard();
  } catch (error) {
    setActionSummary(`产品族配置失败 / PF Config Failed (${family})`, "failed", "-", "-", String(error), String(error));
  }
}

// ── 动作处理：产品族动作权限变更 / Action handler: product family action permissions ──

async function applyProductFamilyPermissions(family) {
  const permChecks = document.querySelectorAll(`.perm-check[data-family="${family}"]`);
  const action_permissions = {};
  permChecks.forEach((el) => {
    action_permissions[el.dataset.action] = el.checked;
  });

  const confirmed = await openConfirmModal("pf-config");
  if (!confirmed) return;

  try {
    const result = await apiPost(
      `/api/v1/control/product-family/${family}/config`,
      baseEnvelope({ payload: { action_permissions } })
    );
    summarizeActionResult("pf-config", result);
    await loadDashboard();
  } catch (error) {
    setActionSummary(`权限变更失败 / Perm Change Failed (${family})`, "failed", "-", "-", String(error), String(error));
  }
}

// ── 动作处理：费用录入 / Action handler: cost entry ──────────────────────────

async function submitCostEntry() {
  const amount = parseFloat(document.getElementById("costAmount")?.value || "0");
  const category = document.getElementById("costCategory")?.value || "manual";
  const note = document.getElementById("costNote")?.value || "";

  if (isNaN(amount) || amount <= 0) {
    setActionSummary("录入失败", "failed", "-", "-", "请输入有效的正数金额 / Please enter a valid positive amount.", {});
    return;
  }

  try {
    const result = await apiPost("/api/v1/input/cost", baseEnvelope({
      payload: { amount, category, note }
    }));
    summarizeActionResult("cost-entry", result);
    // 清空表单 / Clear form
    document.getElementById("costAmount").value = "";
    document.getElementById("costNote").value = "";
    await loadDashboard();
  } catch (error) {
    setActionSummary("费用录入失败 / Cost Entry Failed", "failed", "-", "-", String(error), String(error));
  }
}

// ── 动作处理：PnL 录入 / Action handler: PnL entry ───────────────────────────

async function submitPnlEntry() {
  const entryType = document.getElementById("pnlType")?.value || "manual_adjustment";
  const realizedVal = document.getElementById("pnlRealized")?.value;
  const unrealizedVal = document.getElementById("pnlUnrealized")?.value;
  const symbol = document.getElementById("pnlSymbol")?.value || "";

  const payload = { entry_type: entryType };
  if (realizedVal !== "") payload.realized_pnl = parseFloat(realizedVal) || 0;
  if (unrealizedVal !== "") payload.unrealized_pnl = parseFloat(unrealizedVal) || 0;
  if (symbol) payload.symbol = symbol;

  try {
    const result = await apiPost("/api/v1/input/pnl-entry", baseEnvelope({ payload }));
    summarizeActionResult("pnl-entry", result);
    // 清空表单 / Clear form
    document.getElementById("pnlRealized").value = "";
    document.getElementById("pnlUnrealized").value = "";
    document.getElementById("pnlSymbol").value = "";
    await loadDashboard();
  } catch (error) {
    setActionSummary("PnL 录入失败 / PnL Entry Failed", "failed", "-", "-", String(error), String(error));
  }
}

// ── 动作处理：系统设置应用 / Action handler: system settings apply ─────────────

async function applyRiskPolicySetting() {
  const riskSwitchEl = document.getElementById("settingsRiskSwitch");
  if (!riskSwitchEl) return;
  const value = riskSwitchEl.value;

  const confirmed = await openConfirmModal("settings-change");
  if (!confirmed) return;

  try {
    const result = await apiPost("/api/v1/input/config-change", baseEnvelope({
      payload: { changes: [{ path: "control_plane.risk_envelope.risk_policy_switch", value }] }
    }));
    summarizeActionResult("settings-change", result);
    await loadDashboard();
  } catch (error) {
    setActionSummary("设置失败 / Settings Failed", "failed", "-", "-", String(error), String(error));
  }
}

async function applyDemoLearningSettings() {
  const demoAck = document.getElementById("settingsDemoAck")?.checked ?? true;
  const learningApproval = document.getElementById("settingsLearningApproval")?.checked ?? true;

  const confirmed = await openConfirmModal("settings-change");
  if (!confirmed) return;

  try {
    const result = await apiPost("/api/v1/input/config-change", baseEnvelope({
      payload: {
        changes: [
          { path: "control_plane.demo_control.demo_operator_ack_required", value: demoAck },
          { path: "learning_state.experiments.approval_required", value: learningApproval }
        ]
      }
    }));
    summarizeActionResult("settings-change", result);
    await loadDashboard();
  } catch (error) {
    setActionSummary("设置失败 / Settings Failed", "failed", "-", "-", String(error), String(error));
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// L 章渲染函数 / L-Chapter Render Functions
//
// 渲染学习驾驶舱各标签页内容和净 PnL 仪表盘。
// Render learning cockpit tab contents and Net PnL dashboard.
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 置信度级别徽章 / Confidence level badge.
 * 根据置信度级别返回对应颜色的标记 / Returns colored badge based on confidence level.
 */
function confidenceBadge(level) {
  const colors = { fact: "#27ae60", inference: "#f39c12", hypothesis: "#3498db" };
  const labels = { fact: "事实/fact", inference: "推断/inference", hypothesis: "假设/hypothesis" };
  const color = colors[level] || "#999";
  return `<span class="confidence-badge" style="background:${color}">${labels[level] || ocEsc(level)}</span>`;
}

/**
 * 状态徽章 / Status badge for hypotheses and experiments.
 */
function statusBadge(status) {
  const colors = {
    proposed: "#3498db", under_review: "#f39c12", testing: "#9b59b6",
    validated: "#27ae60", invalidated: "#e74c3c", archived: "#95a5a6",
    pending_approval: "#f39c12", approved: "#27ae60", rejected: "#e74c3c",
    in_progress: "#9b59b6", completed: "#2ecc71"
  };
  const color = colors[status] || "#999";
  return `<span class="status-badge" style="background:${color}">${ocEsc(status)}</span>`;
}

/**
 * 渲染学习观察流和经验记忆 / Render learning feed (observations + lessons).
 */
function renderLearningFeed(feedData) {
  if (!feedData) return;

  // 渲染观察列表 / Render observations list
  const obsList = document.getElementById("observationsList");
  if (obsList) {
    const obs = feedData.observations_recent || [];
    obsList.innerHTML = obs.length === 0
      ? '<div class="muted-row">暂无观察记录 / No observations yet</div>'
      : obs.map(o => `
        <div class="learning-record-item">
          <div class="learning-record-header">
            ${confidenceBadge(o.confidence_level)}
            <span class="learning-record-category">${ocEsc(o.category)}</span>
            <span class="learning-record-ts">${fmtTs(o.recorded_ts_ms)}</span>
          </div>
          <div class="learning-record-title">${escHtml(o.title)}</div>
          <div class="learning-record-detail">${escHtml(o.detail)}</div>
          <div class="learning-record-id">${ocEsc(o.observation_id)}</div>
        </div>`).join("");
  }

  // 渲染经验列表 / Render lessons list
  const lesList = document.getElementById("lessonsList");
  if (lesList) {
    const les = feedData.lessons_recent || [];
    lesList.innerHTML = les.length === 0
      ? '<div class="muted-row">暂无经验记录 / No lessons yet</div>'
      : les.map(l => `
        <div class="learning-record-item">
          <div class="learning-record-header">
            ${confidenceBadge(l.confidence_level)}
            <span class="learning-record-category">${ocEsc(l.category)}</span>
            <span class="learning-record-ts">${fmtTs(l.recorded_ts_ms)}</span>
          </div>
          <div class="learning-record-title">${escHtml(l.title)}</div>
          <div class="learning-record-detail">${escHtml(l.detail)}</div>
          <div class="learning-record-id">${ocEsc(l.lesson_id)}</div>
        </div>`).join("");
  }

  // 更新统计 / Update stats
  const totals = feedData.totals || {};
  setText("lrnObsCount", totals.total_observations ?? 0);
  setText("lrnLesCount", totals.total_lessons ?? 0);
  setText("lrnHypCount", totals.total_hypotheses ?? 0);
  setText("lrnExpCount", totals.total_experiments ?? 0);
}

/**
 * 渲染假设和实验队列 / Render hypotheses and experiments queue.
 */
function renderLearningExperiments(expData) {
  if (!expData) return;

  // 渲染假设列表 / Render hypotheses list
  const hypList = document.getElementById("hypothesesList");
  if (hypList) {
    const hyps = expData.hypotheses || [];
    hypList.innerHTML = hyps.length === 0
      ? '<div class="muted-row">暂无假设 / No hypotheses yet</div>'
      : hyps.map(h => `
        <div class="learning-record-item">
          <div class="learning-record-header">
            ${statusBadge(h.status)}
            ${confidenceBadge(h.confidence_level || "hypothesis")}
            <span class="learning-record-ts">${fmtTs(h.recorded_ts_ms)}</span>
          </div>
          <div class="learning-record-title">${escHtml(h.title)}</div>
          <div class="learning-record-detail">${escHtml(h.description || "")}</div>
          <div class="learning-record-prediction"><strong>预测 / Prediction:</strong> ${escHtml(h.testable_prediction || "")}</div>
          <div class="learning-record-id">${ocEsc(h.hypothesis_id)}</div>
          ${h.status === "proposed" || h.status === "under_review" ? `
            <div class="learning-record-actions">
              <button class="hyp-verdict-btn" data-hyp-id="${ocEsc(h.hypothesis_id)}" data-verdict="approved">批准 / Approve</button>
              <button class="hyp-verdict-btn btn-danger" data-hyp-id="${ocEsc(h.hypothesis_id)}" data-verdict="rejected">拒绝 / Reject</button>
              <button class="hyp-verdict-btn btn-muted" data-hyp-id="${ocEsc(h.hypothesis_id)}" data-verdict="archived">归档 / Archive</button>
            </div>` : ""}
          ${h.operator_verdict ? `<div class="learning-record-verdict">判定 / Verdict: ${ocEsc(h.operator_verdict)} (${ocEsc(h.operator_verdict_reason || "-")})</div>` : ""}
        </div>`).join("");
  }

  // 渲染实验列表 / Render experiments list
  const expList = document.getElementById("experimentsList");
  if (expList) {
    const exps = expData.experiments || [];
    expList.innerHTML = exps.length === 0
      ? '<div class="muted-row">暂无实验 / No experiments yet</div>'
      : exps.map(e => `
        <div class="learning-record-item">
          <div class="learning-record-header">
            ${statusBadge(e.status)}
            <span class="learning-record-category">hyp: ${ocEsc(e.hypothesis_id)}</span>
            <span class="learning-record-ts">${fmtTs(e.recorded_ts_ms)}</span>
          </div>
          <div class="learning-record-title">${escHtml(e.title)}</div>
          <div class="learning-record-detail">${escHtml(e.description || "")}</div>
          <div class="learning-record-id">${ocEsc(e.experiment_id)}</div>
          ${e.status === "pending_approval" ? `
            <div class="learning-record-actions">
              <button class="exp-approve-btn" data-exp-id="${ocEsc(e.experiment_id)}" data-action="approved">批准 / Approve</button>
              <button class="exp-approve-btn btn-danger" data-exp-id="${ocEsc(e.experiment_id)}" data-action="rejected">拒绝 / Reject</button>
            </div>` : ""}
          ${e.status === "approved" ? `
            <div class="learning-record-actions">
              <button class="exp-complete-btn" data-exp-id="${ocEsc(e.experiment_id)}">标记完成 / Mark Complete</button>
            </div>` : ""}
          ${e.result_summary ? `<div class="learning-record-verdict">结论 / Result: ${escHtml(e.result_summary)} ${confidenceBadge(e.result_confidence_level || "inference")}</div>` : ""}
        </div>`).join("");
  }

  // 更新待审批计数 / Update pending count
  setText("lrnPendingCount", expData.pending_approval_count ?? 0);
}

/**
 * 渲染净 PnL 仪表盘 / Render Net PnL Dashboard.
 */
function renderNetPnlDashboard(dashData) {
  if (!dashData) return;
  const daily = dashData.daily || {};

  setText("npRealizedPnl", fmtPnl(daily.realized_pnl));
  setText("npUnrealizedPnl", fmtPnl(daily.unrealized_pnl));
  setText("npGrossPnl", fmtPnl(daily.gross_pnl));
  setText("npTotalCost", fmtPnl(daily.total_cost));
  setText("npNetPnl", fmtPnl(daily.net_operating_pnl));
  setText("npSnapshotCount", (dashData.entry_totals || {}).total_period_snapshots ?? 0);

  // 成本分解 / Cost breakdown
  const brkEl = document.getElementById("npCostBreakdown");
  if (brkEl) {
    const brk = dashData.cost_breakdown || {};
    const keys = Object.keys(brk);
    brkEl.innerHTML = keys.length === 0
      ? '<div class="muted-row">暂无成本 / No costs yet</div>'
      : keys.map(k => `<div class="breakdown-item"><span>${ocEsc(k)}</span><strong>${fmtPnl(brk[k])}</strong></div>`).join("");
  }

  // 趋势列表 / Trend list
  const trendEl = document.getElementById("npTrendList");
  if (trendEl) {
    const trend = dashData.net_pnl_trend || [];
    trendEl.innerHTML = trend.length === 0
      ? '<div class="muted-row">暂无周期快照 / No period snapshots</div>'
      : trend.map(t => `
        <div class="entry-item">
          <span class="entry-item-label">${escHtml(t.period_label)}</span>
          <span>净 PnL: <strong>${fmtPnl(t.net_operating_pnl)}</strong></span>
          <span>毛 PnL: ${fmtPnl(t.gross_pnl)}</span>
          <span>成本: ${fmtPnl(t.total_cost)}</span>
        </div>`).join("");
  }
}

/**
 * HTML 转义 / Simple HTML escape to prevent XSS.
 */
function escHtml(str) {
  const div = document.createElement("div");
  div.textContent = String(str);
  return div.innerHTML;
}

// ═══════════════════════════════════════════════════════════════════════════════
// L 章动作处理器 / L-Chapter Action Handlers
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 提交观察记录 / Submit an observation record.
 */
async function submitObservation() {
  const title = document.getElementById("obsTitle")?.value?.trim();
  const detail = document.getElementById("obsDetail")?.value?.trim();
  const category = document.getElementById("obsCategory")?.value;
  const confidence = document.getElementById("obsConfidence")?.value;

  if (!title || !detail) {
    setActionSummary("录入失败", "failed", "-", "-", "请填写标题和详情 / Title and detail are required.", {});
    return;
  }

  try {
    const result = await apiPost("/api/v1/input/observation", baseEnvelope({
      payload: { title, detail, category, confidence_level: confidence }
    }));
    summarizeActionResult("learning-observation", result);
    document.getElementById("obsTitle").value = "";
    document.getElementById("obsDetail").value = "";
    await loadDashboard();
  } catch (error) {
    setActionSummary("观察录入失败 / Observation Failed", "failed", "-", "-", String(error), String(error));
  }
}

/**
 * 提交经验教训 / Submit a lesson.
 */
async function submitLesson() {
  const title = document.getElementById("lessonTitle")?.value?.trim();
  const detail = document.getElementById("lessonDetail")?.value?.trim();
  const category = document.getElementById("lessonCategory")?.value;
  const confidence = document.getElementById("lessonConfidence")?.value;

  if (!title || !detail) {
    setActionSummary("录入失败", "failed", "-", "-", "请填写标题和详情 / Title and detail are required.", {});
    return;
  }

  try {
    const result = await apiPost("/api/v1/input/lesson", baseEnvelope({
      payload: { title, detail, category, confidence_level: confidence }
    }));
    summarizeActionResult("learning-lesson", result);
    document.getElementById("lessonTitle").value = "";
    document.getElementById("lessonDetail").value = "";
    await loadDashboard();
  } catch (error) {
    setActionSummary("经验录入失败 / Lesson Failed", "failed", "-", "-", String(error), String(error));
  }
}

/**
 * 提交假设 / Submit a hypothesis.
 */
async function submitHypothesis() {
  const title = document.getElementById("hypTitle")?.value?.trim();
  const description = document.getElementById("hypDescription")?.value?.trim();
  const prediction = document.getElementById("hypPrediction")?.value?.trim();

  if (!title || !description || !prediction) {
    setActionSummary("录入失败", "failed", "-", "-", "请填写标题、描述和可检验预测 / Title, description and prediction required.", {});
    return;
  }

  try {
    const result = await apiPost("/api/v1/input/hypothesis", baseEnvelope({
      payload: { title, description, testable_prediction: prediction }
    }));
    summarizeActionResult("learning-hypothesis", result);
    document.getElementById("hypTitle").value = "";
    document.getElementById("hypDescription").value = "";
    document.getElementById("hypPrediction").value = "";
    await loadDashboard();
  } catch (error) {
    setActionSummary("假设录入失败 / Hypothesis Failed", "failed", "-", "-", String(error), String(error));
  }
}

/**
 * 提交实验 / Submit an experiment.
 */
async function submitExperiment() {
  const hypothesisId = document.getElementById("expHypothesisId")?.value?.trim();
  const title = document.getElementById("expTitle")?.value?.trim();
  const description = document.getElementById("expDescription")?.value?.trim();
  const method = document.getElementById("expMethod")?.value?.trim();
  const criteria = document.getElementById("expSuccessCriteria")?.value?.trim();

  if (!hypothesisId || !title || !description || !method || !criteria) {
    setActionSummary("录入失败", "failed", "-", "-", "请填写所有必填字段 / All required fields must be filled.", {});
    return;
  }

  try {
    const result = await apiPost("/api/v1/input/experiment", baseEnvelope({
      payload: { hypothesis_id: hypothesisId, title, description, method, success_criteria: criteria }
    }));
    summarizeActionResult("learning-experiment", result);
    document.getElementById("expTitle").value = "";
    document.getElementById("expDescription").value = "";
    document.getElementById("expMethod").value = "";
    document.getElementById("expSuccessCriteria").value = "";
    await loadDashboard();
  } catch (error) {
    setActionSummary("实验录入失败 / Experiment Failed", "failed", "-", "-", String(error), String(error));
  }
}

/**
 * 假设审批 / Hypothesis verdict.
 */
async function applyHypothesisVerdict(hypothesisId, verdict) {
  try {
    const result = await apiPost(`/api/v1/learning/hypothesis/${hypothesisId}/verdict`, baseEnvelope({
      payload: { verdict, reason: "operator decision via GUI" }
    }));
    summarizeActionResult("hypothesis-verdict", result);
    await loadDashboard();
  } catch (error) {
    setActionSummary("假设审批失败 / Verdict Failed", "failed", "-", "-", String(error), String(error));
  }
}

/**
 * 实验审批 / Experiment approval.
 */
async function applyExperimentApproval(experimentId, action) {
  try {
    const result = await apiPost(`/api/v1/learning/experiment/${experimentId}/approve`, baseEnvelope({
      payload: { action, reason: "operator decision via GUI" }
    }));
    summarizeActionResult("experiment-approval", result);
    await loadDashboard();
  } catch (error) {
    setActionSummary("实验审批失败 / Approval Failed", "failed", "-", "-", String(error), String(error));
  }
}

/**
 * 实验完成 / Experiment completion.
 */
async function applyExperimentCompletion(experimentId) {
  const summary = prompt("请输入实验结论摘要 / Enter experiment result summary:");
  if (!summary) return;
  const confidence = prompt("置信度级别 / Confidence level (fact/inference/hypothesis):", "inference");
  if (!confidence) return;

  try {
    const result = await apiPost(`/api/v1/learning/experiment/${experimentId}/complete`, baseEnvelope({
      payload: { result_summary: summary, result_confidence_level: confidence }
    }));
    summarizeActionResult("experiment-completion", result);
    await loadDashboard();
  } catch (error) {
    setActionSummary("实验完成失败 / Completion Failed", "failed", "-", "-", String(error), String(error));
  }
}

/**
 * 保存周期快照 / Save period snapshot.
 */
async function savePeriodSnapshot() {
  const label = document.getElementById("periodLabel")?.value?.trim();
  if (!label) {
    setActionSummary("失败", "failed", "-", "-", "请输入周期标签 / Period label is required.", {});
    return;
  }

  try {
    const result = await apiPost("/api/v1/input/pnl-period-snapshot", baseEnvelope({
      payload: { period_label: label }
    }));
    summarizeActionResult("period-snapshot", result);
    document.getElementById("periodLabel").value = "";
    await loadDashboard();
  } catch (error) {
    setActionSummary("快照保存失败 / Snapshot Failed", "failed", "-", "-", String(error), String(error));
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// L 章自动学习：审核队列渲染 + 动作处理 / Auto Learning: Review Queue Render + Actions
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 审核包状态标签 / Review packet status badge.
 */
function reviewStatusBadge(status) {
  const map = {
    pending_review: '<span class="badge badge-warning">待审核 / Pending</span>',
    approved: '<span class="badge badge-success">已批准 / Approved</span>',
    rejected: '<span class="badge badge-danger">已拒绝 / Rejected</span>',
    deferred: '<span class="badge badge-muted">已搁置 / Deferred</span>',
    ai_consulted: '<span class="badge badge-info">已咨询AI / AI Consulted</span>'
  };
  return map[status] || `<span class="badge">${ocEsc(status)}</span>`;
}

/**
 * 审核包类型标签 / Review packet type label.
 */
function reviewTypeLabel(packetType) {
  const map = {
    auto_observation: "自动观察 / Auto Observation",
    auto_lesson: "自动经验 / Auto Lesson",
    auto_hypothesis: "自动假设 / Auto Hypothesis"
  };
  return map[packetType] || ocEsc(packetType);
}

/**
 * 渲染单个审核包卡片 / Render a single review packet card.
 */
function renderReviewPacketCard(p) {
  const isPending = p.status === "pending_review" || p.status === "ai_consulted";
  const opts = p.options || {};
  const aiSec = p.ai_consultation || {};

  let actionsHtml = "";
  if (isPending) {
    actionsHtml = `
      <div class="review-actions">
        <div class="review-action-group">
          <button class="review-decide-btn review-btn-approve" data-packet-id="${p.packet_id}" data-decision="approve">
            批准 / Approve
          </button>
          <div class="review-consequence">${escHtml((opts.approve || {}).consequence || "记录为正式条目")}</div>
        </div>
        <div class="review-action-group">
          <button class="review-decide-btn review-btn-reject" data-packet-id="${p.packet_id}" data-decision="reject">
            拒绝 / Reject
          </button>
          <div class="review-consequence">${escHtml((opts.reject || {}).consequence || "丢弃，不记录")}</div>
        </div>
        <div class="review-action-group">
          <button class="review-decide-btn review-btn-defer" data-packet-id="${p.packet_id}" data-decision="defer">
            搁置 / Defer
          </button>
          <div class="review-consequence">${escHtml((opts.defer || {}).consequence || "下次再看")}</div>
        </div>
        <div class="review-action-group">
          <button class="review-ai-consult-btn" data-packet-id="${p.packet_id}">
            询问 AI / Ask AI (${aiSec.recommended_tier || "light"}, ~$${(aiSec.estimated_cost_usd || 0.02).toFixed(2)})
          </button>
          <div class="review-consequence">${escHtml(aiSec.pre_built_question ? "让AI评估这个发现" : "暂无AI建议")}</div>
        </div>
      </div>`;
  }

  let aiResultHtml = "";
  if (p.ai_consultation_result) {
    const r = p.ai_consultation_result;
    aiResultHtml = `
      <div class="review-ai-result">
        <div class="review-ai-result-header">AI 咨询结果 / AI Consultation Result</div>
        <div class="review-ai-question"><strong>问题 / Question:</strong> ${escHtml(r.question_sent || "")}</div>
        <div class="review-ai-response"><strong>回复 / Response:</strong> ${escHtml(r.ai_response || "")}</div>
        <div class="review-ai-cost">费用 / Cost: $${(r.cost_usd || 0).toFixed(4)}</div>
      </div>`;
  }

  return `
    <div class="review-packet-card ${isPending ? "review-pending" : "review-decided"}">
      <div class="review-packet-header">
        ${reviewStatusBadge(p.status)}
        ${confidenceBadge(p.confidence_level || "inference")}
        <span class="review-packet-type">${reviewTypeLabel(p.packet_type)}</span>
        <span class="learning-record-ts">${fmtTs(p.created_ts_ms)}</span>
      </div>
      <div class="review-packet-section">
        <div class="review-section-label">简要说明 / What Happened</div>
        <div class="review-section-content">${escHtml(p.what_happened || "")}</div>
      </div>
      <div class="review-packet-section">
        <div class="review-section-label">为什么重要 / Why It Matters</div>
        <div class="review-section-content">${escHtml(p.why_it_matters || "")}</div>
      </div>
      ${actionsHtml}
      ${aiResultHtml}
      <div class="learning-record-id">${p.packet_id}</div>
    </div>`;
}

/**
 * 渲染审核队列 / Render the review queue tab.
 */
function renderReviewQueue(queueData) {
  if (!queueData) return;

  const listEl = document.getElementById("reviewQueueList");
  if (listEl) {
    const pending = queueData.pending_packets || [];
    listEl.innerHTML = pending.length === 0
      ? '<div class="muted-row">暂无待审核项 / No pending review packets</div>'
      : pending.map(p => renderReviewPacketCard(p)).join("");
  }

  const decidedEl = document.getElementById("reviewRecentDecided");
  if (decidedEl) {
    const decided = queueData.recent_decided || [];
    if (decided.length > 0) {
      decidedEl.innerHTML = `
        <div class="review-decided-header">最近已处理 / Recently Decided (${decided.length})</div>
        ${decided.map(p => renderReviewPacketCard(p)).join("")}`;
    } else {
      decidedEl.innerHTML = "";
    }
  }

  // 更新待审核计数 / Update pending review count
  setText("lrnPendingCount", queueData.pending_count ?? 0);
}

/**
 * 触发自动扫描 / Trigger auto scan.
 */
async function triggerAutoScan(scanType) {
  const routeMap = {
    observations: "/api/v1/learning/auto/scan-observations",
    lessons: "/api/v1/learning/auto/scan-lessons",
    hypotheses: "/api/v1/learning/auto/scan-hypotheses"
  };
  const route = routeMap[scanType];
  if (!route) return;

  try {
    const result = await apiPost(route, baseEnvelope());
    const d = result.data || {};
    setActionSummary(
      `扫描${scanType} / Scan ${scanType}`, "success",
      result.state_revision || "-", "-",
      `生成 ${d.packets_generated || 0} 个审核包，跳过 ${d.skipped_duplicates || 0} 个重复。`,
      d
    );
    await loadDashboard();
  } catch (error) {
    setActionSummary(`扫描失败 / Scan Failed (${scanType})`, "failed", "-", "-", String(error), String(error));
  }
}

/**
 * 对审核包做决定 / Apply a review decision.
 */
async function applyReviewDecision(packetId, decision) {
  try {
    const result = await apiPost(`/api/v1/learning/review/${encodeURIComponent(packetId)}/decide`, baseEnvelope({
      payload: { decision, reason: "" }
    }));
    const d = result.data || {};
    const labels = { approve: "批准", reject: "拒绝", defer: "搁置" };
    setActionSummary(
      `${labels[decision] || decision} / ${decision}`, "success",
      result.state_revision || "-", "-",
      `审核包 ${packetId} 已${labels[decision] || decision}。${d.record_created ? " 已创建记录 " + (d.created_record_id || "") : ""}`,
      d
    );
    await loadDashboard();
  } catch (error) {
    setActionSummary("审核失败 / Review Failed", "failed", "-", "-", String(error), String(error));
  }
}

/**
 * 请求 AI 咨询 / Request AI consultation for a review packet.
 */
async function requestAIConsult(packetId) {
  try {
    const result = await apiPost(`/api/v1/learning/review/${encodeURIComponent(packetId)}/decide`, { ...baseEnvelope(), decision: 'ask_ai' });
    const d = result.data || {};
    setActionSummary(
      "AI 咨询 / AI Consult", "success",
      result.state_revision || "-", "-",
      `已咨询 AI (${d.ai_tier || "light"})，费用 $${(d.cost_usd || 0).toFixed(4)}`,
      d
    );
    await loadDashboard();
  } catch (error) {
    setActionSummary("AI 咨询失败 / AI Consult Failed", "failed", "-", "-", String(error), String(error));
  }
}

// ── 事件绑定 / Event binding ──────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  ensureGuiEnhancements();

  // APR01-MEDIUM-13: Token is now in HttpOnly cookie. Clean up legacy localStorage.
  // Auto-connect using cookie auth (no manual token input needed).
  // APR01-MEDIUM-13：Token 已移至 HttpOnly cookie。清理旧 localStorage。
  // 使用 cookie 认证自动连接（无需手动输入 token）。
  localStorage.removeItem('oc_trading_token');
  // Auto-connect: cookie is sent automatically, so just trigger loadDashboard.
  setTimeout(() => { document.getElementById('connectButton').click(); }, 200);

  // 连接按钮 / Connect button
  document.getElementById("connectButton").addEventListener("click", async () => {
    inMemoryToken = document.getElementById("tokenInput").value.trim();
    try {
      await loadDashboard();
      setConnectionStatus("已连接 / Connected", "good");
      setActionSummary("连接 / Connect", "success", "-", "-",
        "连接成功。 / Connected successfully.", { message: "Connected." });
    } catch (error) {
      setConnectionStatus("连接失败 / Failed", "bad");
      setActionSummary("连接 / Connect", "failed", "-", "-", String(error), String(error));
    }
  });

  // 使用事件委托处理所有动态按钮 / Use event delegation for all dynamic buttons
  document.addEventListener("click", (event) => {
    const target = event.target.closest("[data-action]");
    if (target) {
      event.preventDefault();
      runQuickAction(target.dataset.action);
      return;
    }

    // 产品族配置应用 / Product family config apply
    const pfApply = event.target.closest(".pf-apply-btn");
    if (pfApply) {
      event.preventDefault();
      applyProductFamilyConfig(pfApply.dataset.family);
      return;
    }

    // 产品族权限应用 / Product family permissions apply
    const pfPermApply = event.target.closest(".pf-perm-apply-btn");
    if (pfPermApply) {
      event.preventDefault();
      applyProductFamilyPermissions(pfPermApply.dataset.family);
      return;
    }

    // 费用录入 / Cost entry submit
    if (event.target.closest("#submitCostEntry")) {
      event.preventDefault();
      submitCostEntry();
      return;
    }

    // PnL 录入 / PnL entry submit
    if (event.target.closest("#submitPnlEntry")) {
      event.preventDefault();
      submitPnlEntry();
      return;
    }

    // 系统设置：风险策略 / Settings: risk policy
    if (event.target.closest("#applyRiskSwitch")) {
      event.preventDefault();
      applyRiskPolicySetting();
      return;
    }

    // 系统设置：Demo/Learning / Settings: demo/learning
    if (event.target.closest("#applyDemoLearningSettings")) {
      event.preventDefault();
      applyDemoLearningSettings();
      return;
    }

    // ── L 章事件 / L-chapter events ─────────────────────────────────────────

    // 观察录入 / Observation submit
    if (event.target.closest("#submitObservation")) {
      event.preventDefault();
      submitObservation();
      return;
    }

    // 经验录入 / Lesson submit
    if (event.target.closest("#submitLesson")) {
      event.preventDefault();
      submitLesson();
      return;
    }

    // 假设录入 / Hypothesis submit
    if (event.target.closest("#submitHypothesis")) {
      event.preventDefault();
      submitHypothesis();
      return;
    }

    // 实验录入 / Experiment submit
    if (event.target.closest("#submitExperiment")) {
      event.preventDefault();
      submitExperiment();
      return;
    }

    // 假设审批按钮 / Hypothesis verdict buttons
    const hypVerdictBtn = event.target.closest(".hyp-verdict-btn");
    if (hypVerdictBtn) {
      event.preventDefault();
      applyHypothesisVerdict(hypVerdictBtn.dataset.hypId, hypVerdictBtn.dataset.verdict);
      return;
    }

    // 实验审批按钮 / Experiment approval buttons
    const expApproveBtn = event.target.closest(".exp-approve-btn");
    if (expApproveBtn) {
      event.preventDefault();
      applyExperimentApproval(expApproveBtn.dataset.expId, expApproveBtn.dataset.action);
      return;
    }

    // 实验完成按钮 / Experiment completion button
    const expCompleteBtn = event.target.closest(".exp-complete-btn");
    if (expCompleteBtn) {
      event.preventDefault();
      applyExperimentCompletion(expCompleteBtn.dataset.expId);
      return;
    }

    // 保存周期快照 / Save period snapshot
    if (event.target.closest("#savePeriodSnapshot")) {
      event.preventDefault();
      savePeriodSnapshot();
      return;
    }

    // 自动扫描按钮 / Auto scan buttons
    const scanBtn = event.target.closest(".auto-scan-btn");
    if (scanBtn) {
      event.preventDefault();
      triggerAutoScan(scanBtn.dataset.scan);
      return;
    }

    // 审核决策按钮 / Review decision buttons
    const reviewDecideBtn = event.target.closest(".review-decide-btn");
    if (reviewDecideBtn) {
      event.preventDefault();
      applyReviewDecision(reviewDecideBtn.dataset.packetId, reviewDecideBtn.dataset.decision);
      return;
    }

    // AI 咨询按钮 / AI consultation button
    const aiConsultBtn = event.target.closest(".review-ai-consult-btn");
    if (aiConsultBtn) {
      event.preventDefault();
      requestAIConsult(aiConsultBtn.dataset.packetId);
      return;
    }

    // 学习标签页切换 / Learning tab switching
    const tabBtn = event.target.closest(".learning-tab");
    if (tabBtn) {
      event.preventDefault();
      const tabName = tabBtn.dataset.tab;
      // 切换标签页激活状态 / Toggle active tab
      document.querySelectorAll(".learning-tab").forEach(t => t.classList.remove("active"));
      tabBtn.classList.add("active");
      // 切换内容面板 / Toggle content panel
      document.querySelectorAll(".learning-tab-content").forEach(c => c.classList.remove("active"));
      const panelMap = {
        observations: "tabObservations",
        lessons: "tabLessons",
        hypotheses: "tabHypotheses",
        experiments: "tabExperiments",
        reviewQueue: "tabReviewQueue"
      };
      document.getElementById(panelMap[tabName])?.classList.add("active");
      return;
    }

    // ── Paper Trading 按钮处理 / Paper Trading button handlers ──
    const paperActionBtn = event.target.closest("[data-paper-action]");
    if (paperActionBtn) {
      event.preventDefault();
      handlePaperAction(paperActionBtn.dataset.paperAction);
      return;
    }

    if (event.target.id === "paperSubmitOrder") {
      event.preventDefault();
      submitPaperOrder();
      return;
    }

    // ── Market Feed 按钮处理 / Market Feed button handlers ──
    const feedActionBtn = event.target.closest("[data-feed-action]");
    if (feedActionBtn) {
      event.preventDefault();
      handleMarketFeedAction(feedActionBtn.dataset.feedAction);
      return;
    }
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// Paper Trading GUI Functions / 纸上交易 GUI 函数
// ═══════════════════════════════════════════════════════════════════════════════

async function handlePaperAction(action) {
  try {
    let r;
    if (action === "start") {
      r = await apiPost("/api/v1/paper/session/start", { initial_balance: 10000 });
    } else if (action === "pause") {
      r = await apiPost("/api/v1/paper/session/pause", {});
    } else if (action === "resume") {
      r = await apiPost("/api/v1/paper/session/resume", {});
    } else if (action === "stop") {
      r = await apiPost("/api/v1/paper/session/stop", {});
    }
    await refreshPaperTrading();
  } catch (e) {
    console.error("Paper action error:", e);
  }
}

async function submitPaperOrder() {
  const symbol = document.getElementById("paperSymbol").value.trim();
  const side = document.getElementById("paperSide").value;
  const orderType = document.getElementById("paperOrderType").value;
  const qty = parseFloat(document.getElementById("paperQty").value);
  const priceVal = document.getElementById("paperPrice").value;
  const price = priceVal ? parseFloat(priceVal) : null;

  if (!symbol || !qty || qty <= 0) return;

  try {
    const body = { symbol, side, order_type: orderType, qty };
    if (price) body.price = price;
    // Manual order submission disabled — Rust engine manages orders via strategies
    console.warn("paper/order/submit disabled — Rust engine manages orders");
    await refreshPaperTrading();
  } catch (e) {
    console.error("Paper order error:", e);
  }
}

async function refreshPaperTrading() {
  try {
    const [statusR, ordersR, posR, pnlR, fillsR] = await Promise.all([
      apiGet("/api/v1/paper/session/status"),
      apiGet("/api/v1/paper/orders"),
      apiGet("/api/v1/paper/positions"),
      apiGet("/api/v1/paper/pnl"),
      apiGet("/api/v1/paper/fills?limit=20"),
    ]);
    renderPaperSession(statusR.data);
    renderPaperPnl(pnlR.data);
    renderPaperPositions(posR.data);
    renderPaperOrders(ordersR.data);
    renderPaperFills(fillsR.data);
    // Also refresh market feed status / 同步刷新行情流状态
    refreshMarketFeedStatus().catch(() => {});
  } catch (e) {
    console.error("Paper refresh error:", e);
  }
}

function renderPaperSession(d) {
  const state = d.session?.session_state || "inactive";
  const badge = document.getElementById("paperSessionBadge");
  const labels = {
    inactive: "未启动 / Inactive",
    active: "运行中 / Active",
    paused: "已暂停 / Paused",
    completed: "已结束 / Completed",
  };
  badge.textContent = labels[state] || state;
  badge.className = "status-chip " + (state === "active" ? "good" : state === "paused" ? "neutral" : state === "completed" ? "neutral" : "neutral");

  // Update button states
  const isActive = state === "active";
  const isPaused = state === "paused";
  const canStart = state === "inactive" || state === "completed";
  document.querySelector("[data-paper-action='start']").disabled = !canStart;
  document.querySelector("[data-paper-action='pause']").disabled = !isActive;
  document.querySelector("[data-paper-action='resume']").disabled = !isPaused;
  document.querySelector("[data-paper-action='stop']").disabled = !(isActive || isPaused);
}

function renderPaperPnl(d) {
  const el = document.getElementById("paperPnlItems");
  if (!d) { el.textContent = "无数据 / No data"; return; }
  const pnlColor = (v) => v > 0 ? "paper-positive" : v < 0 ? "paper-negative" : "";
  el.innerHTML = `
    <div class="paper-pnl-row"><span>已实现 / Realized</span><span class="${pnlColor(d.realized_pnl)}">${(d.realized_pnl || 0).toFixed(4)} USDT</span></div>
    <div class="paper-pnl-row"><span>未实现 / Unrealized</span><span class="${pnlColor(d.unrealized_pnl)}">${(d.unrealized_pnl || 0).toFixed(4)} USDT</span></div>
    <div class="paper-pnl-row"><span>手续费 / Fees</span><span>-${(d.total_fees_paid || 0).toFixed(4)} USDT</span></div>
    <div class="paper-pnl-row paper-pnl-net"><span>净值 / Net PnL</span><span class="${pnlColor(d.net_paper_pnl)}">${(d.net_paper_pnl || 0).toFixed(4)} USDT</span></div>
  `;
}

function renderPaperPositions(d) {
  const el = document.getElementById("paperPositionsList");
  // Rust returns positions as array, not dict
  const raw = d.positions || {};
  const positions = Array.isArray(raw) ? raw : Object.values(raw);
  if (positions.length === 0) { el.textContent = "无持仓 / No positions"; return; }
  el.innerHTML = positions.map(p => {
    const sym = ocEsc(p.symbol || '??');
    const pnlColor = p.unrealized_pnl > 0 ? "paper-positive" : p.unrealized_pnl < 0 ? "paper-negative" : "";
    return `<div class="paper-position-row">
      <span class="paper-pos-symbol">${sym}</span>
      <span class="paper-pos-side">${ocEsc(p.side)}</span>
      <span>${ocEsc(p.qty)}</span>
      <span>@ ${(p.avg_entry_price || p.entry_price || 0).toFixed(2)}</span>
      <span class="${pnlColor}">${(p.unrealized_pnl || 0).toFixed(4)}</span>
    </div>`;
  }).join("");
}

function renderPaperOrders(d) {
  const el = document.getElementById("paperOrdersList");
  const orders = d.orders || [];
  if (orders.length === 0) { el.textContent = "无订单 / No orders"; return; }
  el.innerHTML = orders.slice(-20).reverse().map(o => {
    const stateLabel = o.state.replace("paper_order_", "");
    const stateClass = o.state.includes("filled") ? "paper-filled" : o.state.includes("canceled") || o.state.includes("rejected") ? "paper-canceled" : "paper-working";
    return `<div class="paper-order-row ${stateClass}">
      <span>${ocEsc(o.symbol)}</span>
      <span>${ocEsc(o.side)}</span>
      <span>${ocEsc(o.order_type)}</span>
      <span>${ocEsc(o.qty)}${o.price ? " @ " + ocEsc(o.price) : ""}</span>
      <span class="paper-order-state">${ocEsc(stateLabel)}</span>
    </div>`;
  }).join("");
}

function renderPaperFills(d) {
  const el = document.getElementById("paperFillsList");
  const fills = d.fills || [];
  if (fills.length === 0) { el.textContent = "无成交 / No fills"; return; }
  el.innerHTML = fills.slice(-20).reverse().map(f => {
    return `<div class="paper-fill-row">
      <span>${ocEsc(f.symbol)}</span>
      <span>${ocEsc(f.side)}</span>
      <span>${ocEsc(f.qty)} @ ${(f.price || 0).toFixed(2)}</span>
      <span>Fee: ${(f.fee || 0).toFixed(6)}</span>
    </div>`;
  }).join("");
}

// ═══════════════════════════════════════════════════════════════════════════════
// Market Feed GUI Functions / 实时行情流 GUI 函数
// ═══════════════════════════════════════════════════════════════════════════════

let _marketFeedRefreshInterval = null;

async function handleMarketFeedAction(action) {
  // Market feed managed by Rust engine — no Python dispatcher needed
  // 行情流由 Rust 引擎管理 — 不需要 Python 分發器
  ocToast('行情流由 Rust 引擎自動管理 / Market feed is managed by Rust engine automatically', 'info');
}

function startMarketFeedRefresh() {
  stopMarketFeedRefresh();
  _marketFeedRefreshInterval = setInterval(() => {
    refreshMarketFeedStatus();
    refreshPaperTrading();
  }, 3000);
}

function stopMarketFeedRefresh() {
  if (_marketFeedRefreshInterval) {
    clearInterval(_marketFeedRefreshInterval);
    _marketFeedRefreshInterval = null;
  }
}

async function refreshMarketFeedStatus() {
  try {
    const resp = await apiGet("/api/v1/paper/market-feed/status");
    renderMarketFeedStatus(resp.data);
  } catch (e) {
    // Feed not available yet
  }
}

function renderMarketFeedStatus(d) {
  const badge = document.getElementById("paperFeedStatusBadge");
  const startBtn = document.getElementById("paperFeedStartBtn");
  const stopBtn = document.getElementById("paperFeedStopBtn");
  const pricesEl = document.getElementById("paperFeedPrices");
  const statsEl = document.getElementById("paperFeedStats");

  const isRunning = d.dispatcher_running || false;
  const attention = d.attention_level || "dormant";

  // Update badge / 更新徽章
  if (isRunning) {
    const wsConnected = d.ws_listener?.connected || false;
    badge.textContent = wsConnected ? "已连接 / Connected" : "连接中 / Connecting...";
    badge.className = "status-chip " + (wsConnected ? "good" : "neutral");
  } else {
    badge.textContent = "未连接 / Disconnected";
    badge.className = "status-chip neutral";
  }

  // Update buttons / 更新按钮
  startBtn.disabled = isRunning;
  stopBtn.disabled = !isRunning;

  // Render latest prices / 渲染最新价格
  const prices = d.latest_prices || {};
  const symbols = Object.keys(prices);
  if (symbols.length > 0) {
    pricesEl.innerHTML = symbols.map(sym => {
      return `<span class="paper-feed-price-item">
        <span class="price-symbol">${ocEsc(sym)}</span>
        <span class="price-value">${prices[sym].toFixed(2)}</span>
      </span>`;
    }).join("");
  } else if (isRunning) {
    pricesEl.textContent = "等待首次行情推送 / Waiting for first price push...";
  } else {
    pricesEl.textContent = "行情流未启动 / Market feed not started";
  }

  // Render stats / 渲染统计
  const stats = d.stats || {};
  const attentionLabels = {
    dormant: "休眠 / Dormant",
    low: "低 / Low",
    medium: "中 / Medium",
    high: "高 / High",
    critical: "紧急 / Critical",
  };
  const attentionClass = "paper-attention-" + attention;

  statsEl.innerHTML = `
    <span class="paper-attention-badge ${attentionClass}">${attentionLabels[attention] || ocEsc(attention)}</span>
    ${stats.ticks_triggered != null ? ` Ticks: ${stats.ticks_triggered}` : ""}
    ${d.ws_listener?.ticker_update_count != null ? ` | 行情更新: ${d.ws_listener.ticker_update_count}` : ""}
    ${stats.volatility_spikes ? ` | 波动飙升: ${stats.volatility_spikes}` : ""}
  `;
}
