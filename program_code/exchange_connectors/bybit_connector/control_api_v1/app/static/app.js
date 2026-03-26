let inMemoryToken = "";

function headers() {
  return {
    "Authorization": `Bearer ${inMemoryToken}`,
    "Content-Type": "application/json"
  };
}

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function safeText(value) {
  return value === undefined || value === null ? "-" : String(value);
}

function variantForState(value) {
  const normalized = String(value || "").toLowerCase();
  if (["passed", "healthy", "ready", "fresh", "complete", "shadow_only", "shadow_control_ready", "success", "true", "allowed"].includes(normalized)) {
    return "good";
  }
  if (["blocked", "disabled", "down", "missing", "failed", "unavailable", "unknown", "false"].includes(normalized)) {
    return "bad";
  }
  if (["partial", "degraded", "demo_reserved", "demo_blocked", "armed_but_closed", "visible_only", "shadow_visible"].includes(normalized)) {
    return "warn";
  }
  return "neutral";
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
    refresh: "刷新概览 / Refresh",
    validate: "验证 Demo / Demo Validate",
    bundle: "安全复核打包 / Safe Recheck Bundle",
    "set-demo-mode": "切到 Demo Reserved / Set Demo Reserved",
    "enable-spot": "开启 Spot Shadow / Enable Spot Shadow",
    "arm-demo": "执行 Demo Arm / Demo Arm"
  };

  const data = result?.data || {};
  let hint = "动作执行完成 / Action completed.";

  if (actionName === "validate") {
    hint = `前提 gate / prerequisites: ${safeText(data.demo_prerequisites_gate_state)} · arm gate: ${safeText(data.demo_arm_gate_state)}`;
  } else if (actionName === "arm-demo") {
    hint = `Demo 状态已切换 / demo state switched to ${safeText(data.demo_state_switch)}.`;
  } else if (actionName === "set-demo-mode" || actionName === "enable-spot") {
    hint = `接受路径 / accepted paths: ${(data.accepted_paths || []).join(", ") || "none"}`;
  } else if (actionName === "bundle") {
    hint = `打包结果 / bundle result: ${safeText(result.action_result)}`;
  } else if (actionName === "refresh") {
    hint = "界面已刷新 / dashboard refreshed.";
  }

  setActionSummary(actionMap[actionName] || actionName, safeText(result.action_result), safeText(result.state_revision), safeText(result.audit_ref), hint, result);
}

function renderKvGrid(nodeId, items) {
  const node = document.getElementById(nodeId);
  node.innerHTML = items.map(([label, value]) => {
    const safeValue = safeText(value);
    return `<div class="kv-item"><dt>${label}</dt><dd><span class="status-chip ${variantForState(safeValue)}">${safeValue}</span></dd></div>`;
  }).join("");
}

function ensureGuiEnhancements() {
  const pageShell = document.querySelector(".page-shell");
  if (!pageShell) return;

  const summaryLabels = document.querySelectorAll("#summaryGrid .summary-label");
  const summaryTexts = [
    "全局模式 / Global Mode",
    "执行权限 / Execution Authority",
    "Demo 状态 / Demo State",
    "快照 / Snapshot",
    "Runtime 快照 / Runtime Snapshot",
    "仍受保护 / Runtime Protected"
  ];
  summaryLabels.forEach((node, index) => {
    if (summaryTexts[index]) node.textContent = summaryTexts[index];
  });

  document.querySelector("label[for='tokenInput']")?.replaceChildren("访问令牌 / Bearer Token");
  document.getElementById("connectButton").textContent = "连接 / Connect";
  document.querySelector(".hero-card .subtle").textContent = "高层状态、保护边界、runtime snapshot 绑定情况 / high-level state, guard boundary, and runtime snapshot binding";

  const topbarSubtle = document.querySelector(".topbar p");
  if (topbarSubtle) topbarSubtle.textContent = "RC2 控制台 / control console · runtime-aware GUI / 已接入 runtime-aware bridge";

  const cards = document.querySelectorAll(".page-shell > .card, .page-shell > .grid.two-up .card");
  cards.forEach((card) => {
    const h2 = card.querySelector("h2");
    if (!h2) return;
    const current = h2.textContent.trim();
    if (current === "来源上下文 / Source Context") {
      card.querySelector(".subtle").textContent = "连接状态、完整性、connector 角色分离 / connection state, completeness, and role separation";
    }
    if (current === "健康摘要 / Health Summary") {
      card.querySelector(".subtle").textContent = "健康评分、关键 gate 与 freshness / health scores, key gates, and freshness";
    }
    if (current === "产品族事实 / Product Family Facts") {
      card.querySelector(".subtle").textContent = "当前 visibility / capability / permission facts 概览 / current visibility, capability, and permission facts";
    }
    if (current === "快捷动作 / Quick Actions") {
      card.querySelector(".subtle").textContent = "仅调用受保护控制面动作，不直接开放真实执行权限 / guarded control actions only";
    }
    if (current === "调试原文 / Debug Raw JSON") {
      card.querySelector(".subtle").textContent = "默认折叠，仅在需要审计或排错时展开 / collapsed by default for audit and debugging only";
    }
  });

  const ths = document.querySelectorAll("table thead th");
  const tableHeaders = [
    "产品族 / Product Family",
    "交易所事实 / Exchange Fact",
    "账户事实 / Account Fact",
    "已启用 / Enabled",
    "可见 / Visible",
    "模式 / Mode",
    "能力 / Capability",
    "执行 / Execution"
  ];
  ths.forEach((th, idx) => {
    if (tableHeaders[idx]) th.textContent = tableHeaders[idx];
  });

  const actionButtons = {
    refresh: "刷新概览 / Refresh",
    validate: "验证 Demo / Demo Validate",
    "set-demo-mode": "切到 Demo Reserved / Set Demo Reserved",
    "enable-spot": "开启 Spot Shadow / Enable Spot Shadow",
    "arm-demo": "执行 Demo Arm / Demo Arm",
    bundle: "安全复核打包 / Safe Recheck Bundle"
  };
  document.querySelectorAll("[data-action]").forEach((button) => {
    const name = button.dataset.action;
    if (actionButtons[name]) button.textContent = actionButtons[name];
  });

  const actionSummaryLabels = document.querySelectorAll("#actionSummaryGrid .summary-label");
  const actionTexts = [
    "最近动作 / Last Action",
    "结果 / Result",
    "状态版本 / State Revision",
    "审计引用 / Audit Ref"
  ];
  actionSummaryLabels.forEach((node, index) => {
    if (actionTexts[index]) node.textContent = actionTexts[index];
  });

  document.querySelectorAll("details.raw-toggle summary")[0].textContent = "查看原始动作响应 / View raw action response";
  document.querySelectorAll("details.raw-toggle summary")[1].textContent = "控制平面原文 / Control Plane Raw";
  document.querySelectorAll("details.raw-toggle summary")[2].textContent = "审计摘要原文 / Audit Raw";
  document.querySelectorAll("details.raw-toggle summary")[3].textContent = "系统总览原文 / Overview Raw";

  if (!document.getElementById("runtimeModeSection")) {
    const grid = document.createElement("section");
    grid.className = "grid two-up injected-grid";
    grid.innerHTML = `
      <section class="card" id="runtimeModeSection">
        <div class="card-header-row">
          <div>
            <h2>运行模式控制 / Runtime Mode Control</h2>
            <p class="subtle">受保护模式切换骨架；当前仅开放低风险 guarded 动作 / guarded mode-control skeleton</p>
          </div>
        </div>
        <div class="mode-grid">
          <div class="summary-item"><span class="summary-label">阶段标签 / Stage Label</span><strong id="modeStageLabel">-</strong></div>
          <div class="summary-item"><span class="summary-label">能力状态 / Capability State</span><strong id="modeCapabilityState">-</strong></div>
          <div class="summary-item"><span class="summary-label">Demo Arm Gate / Demo Arm Gate</span><strong id="modeDemoArmGate">-</strong></div>
          <div class="summary-item"><span class="summary-label">Demo Enable Gate / Demo Enable Gate</span><strong id="modeDemoEnableGate">-</strong></div>
        </div>
        <div class="mode-actions">
          <button data-action="set-demo-mode">切到 Demo Reserved / Set Demo Reserved</button>
          <button data-action="enable-spot">开启 Spot Shadow / Enable Spot Shadow</button>
          <button data-action="validate">验证 Demo 前提 / Validate Demo</button>
          <button data-action="arm-demo">执行 Demo Arm / Demo Arm</button>
          <button class="button-muted" disabled>观测模式 / Observe Only（后续 / later）</button>
          <button class="button-muted" disabled>Live 模式 / Live Mode（封闭 / locked）</button>
        </div>
        <div id="modeControlNote" class="mode-note">当前 GUI 只开放受保护的 demo / shadow 动作；live 相关切换仍保持封闭。 / Only guarded demo/shadow actions are exposed; live switching remains locked.</div>
      </section>
      <section class="card" id="businessSummarySection">
        <div class="card-header-row">
          <div>
            <h2>经营与收益摘要 / Business & Income Summary</h2>
            <p class="subtle">来自 overview 的 daily business summary；当前为展示骨架 / business dashboard skeleton backed by overview</p>
          </div>
        </div>
        <div class="summary-grid business-grid">
          <div class="summary-item"><span class="summary-label">已实现盈亏 / Realized PnL</span><strong id="bizRealizedPnl">-</strong></div>
          <div class="summary-item"><span class="summary-label">未实现盈亏 / Unrealized PnL</span><strong id="bizUnrealizedPnl">-</strong></div>
          <div class="summary-item"><span class="summary-label">毛盈亏 / Gross PnL</span><strong id="bizGrossPnl">-</strong></div>
          <div class="summary-item"><span class="summary-label">总成本 / Total Cost</span><strong id="bizTotalCost">-</strong></div>
          <div class="summary-item"><span class="summary-label">净经营盈亏 / Net Operating PnL</span><strong id="bizNetOperatingPnl">-</strong></div>
          <div class="summary-item"><span class="summary-label">业务事件数 / Business Event Count</span><strong id="bizEventCount">-</strong></div>
        </div>
        <div class="mode-note" id="businessSummaryNote">当前数据来自 overview.daily_business_summary；后续将继续接入更真实的 OpenClaw runtime exporter。 / Data currently comes from overview.daily_business_summary and will later be backed by a deeper runtime exporter.</div>
      </section>`;

    const firstGrid = document.querySelector(".page-shell > .grid.two-up");
    if (firstGrid) {
      firstGrid.before(grid);
    }
  }
}

function renderSummary(overview) {
  const runtime = overview.data.global_runtime;
  const demo = overview.data.demo_control_summary;
  const sourceContext = overview.source_context;

  document.getElementById("summaryGlobalMode").textContent = runtime.global_mode_state;
  document.getElementById("summaryExecutionAuthority").textContent = runtime.global_execution_authority_state;
  document.getElementById("summaryDemoState").textContent = demo.demo_state_switch;
  document.getElementById("summarySnapshot").textContent = `${overview.state_revision} / ${overview.snapshot_id}`;
  document.getElementById("summaryRuntimeSnapshot").textContent = sourceContext.pinned_runtime_snapshot_id;
  document.getElementById("summaryProtected").textContent = String(runtime.runtime_still_protected);

  setRuntimeModeBadge(`${runtime.global_mode_state} · ${demo.demo_state_switch}`, variantForState(runtime.global_execution_authority_state));
}

function renderModeControl(overview) {
  const runtime = overview.data.global_runtime;
  const demo = overview.data.demo_control_summary;
  const stageLabel = document.getElementById("modeStageLabel");
  const capability = document.getElementById("modeCapabilityState");
  const armGate = document.getElementById("modeDemoArmGate");
  const enableGate = document.getElementById("modeDemoEnableGate");
  if (!stageLabel) return;
  stageLabel.textContent = safeText(runtime.global_stage_label);
  capability.textContent = safeText(runtime.global_capability_state);
  armGate.textContent = safeText(demo.demo_arm_gate_state);
  enableGate.textContent = safeText(demo.demo_enable_gate_state);
}

function renderBusinessSummary(overview) {
  const daily = overview.data.daily_business_summary;
  const mapping = {
    bizRealizedPnl: daily.realized_pnl,
    bizUnrealizedPnl: daily.unrealized_pnl,
    bizGrossPnl: daily.gross_pnl,
    bizTotalCost: daily.total_cost,
    bizNetOperatingPnl: daily.net_operating_pnl,
    bizEventCount: daily.business_event_count
  };
  Object.entries(mapping).forEach(([id, value]) => {
    const node = document.getElementById(id);
    if (node) node.textContent = safeText(value);
  });
}

function renderSourceContext(sourceContext) {
  renderKvGrid("sourceContextGrid", [
    ["只读连接器 / Readonly Connector", sourceContext.readonly_connector_name],
    ["执行连接器 / Execution Connector", sourceContext.execution_connector_name || "not_attached"],
    ["私有 REST / REST Private", sourceContext.rest_private_connection_state],
    ["私有 WS / WS Private", sourceContext.ws_private_connection_state],
    ["Runtime 连接 / Runtime Connection", sourceContext.runtime_connection_state],
    ["账户完整性 / Account Completeness", sourceContext.account_fact_completeness_state],
    ["快照完整性 / Snapshot Completeness", sourceContext.source_snapshot_completeness_state],
    ["角色分离 / Role Separation", sourceContext.connector_role_separation_ok],
    ["Runtime 快照 / Runtime Snapshot", sourceContext.pinned_runtime_snapshot_id]
  ]);
}

function renderHealth(overview) {
  const health = overview.data.health_summary;
  renderKvGrid("healthGrid", [
    ["总健康分 / Overall Health Score", health.scores.overall_health_score],
    ["AI 健康分 / AI Health Score", health.scores.ai_health_score],
    ["交易所健康分 / Exchange Health Score", health.scores.exchange_health_score],
    ["新鲜度分 / Data Freshness Score", health.scores.data_freshness_score],
    ["总 gate / Health Gates Overall", health.gates.health_gates_overall_state],
    ["Timeout Gate / Exchange Timeout Gate", health.gates.exchange_timeout_gate_state],
    ["WS 断连 Gate / WS Disconnect Gate", health.gates.ws_disconnect_gate_state],
    ["延迟 Gate / Latency Gate", health.gates.latency_gate_state],
    ["新鲜度 Gate / Freshness Gate", health.gates.freshness_gate_state]
  ]);
}

function renderProductFamilies(productFamilies) {
  const body = document.getElementById("productFamilyTableBody");
  const rows = Object.entries(productFamilies).map(([name, data]) => `
    <tr>
      <td>${name}</td>
      <td><span class="status-chip ${variantForState(data.facts.exchange_permission_fact)}">${data.facts.exchange_permission_fact}</span></td>
      <td><span class="status-chip ${variantForState(data.facts.account_permission_fact)}">${data.facts.account_permission_fact}</span></td>
      <td>${String(data.controls.enabled_switch)}</td>
      <td>${String(data.controls.visibility_switch)}</td>
      <td>${data.controls.mode_switch}</td>
      <td><span class="status-chip ${variantForState(data.derived.capability_state)}">${data.derived.capability_state}</span></td>
      <td><span class="status-chip ${variantForState(data.derived.execution_authority_state)}">${data.derived.execution_authority_state}</span></td>
    </tr>
  `).join("");
  body.innerHTML = rows || '<tr><td colspan="8" class="muted-cell">无数据 / No data</td></tr>';
}

async function apiGet(path) {
  const response = await fetch(path, { headers: headers() });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(pretty(data));
  }
  return data;
}

async function apiPost(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(payload)
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(pretty(data));
  }
  return data;
}

async function loadDashboard() {
  ensureGuiEnhancements();
  const [overview, controlPlane, sourceContext, audit, productFamilies] = await Promise.all([
    apiGet("/api/v1/system/overview"),
    apiGet("/api/v1/system/control-plane"),
    apiGet("/api/v1/system/source-context"),
    apiGet("/api/v1/system/audit-summary"),
    apiGet("/api/v1/system/product-families")
  ]);

  renderSummary(overview);
  renderModeControl(overview);
  renderBusinessSummary(overview);
  renderSourceContext(sourceContext.data);
  renderHealth(overview);
  renderProductFamilies(productFamilies.data);

  document.getElementById("overviewBox").textContent = pretty(overview);
  document.getElementById("controlPlaneBox").textContent = pretty(controlPlane);
  document.getElementById("auditBox").textContent = pretty(audit);
}

async function getOverviewForEnvelope() {
  return await apiGet("/api/v1/system/overview");
}

function baseEnvelope(overview, extra = {}) {
  return {
    request_id: crypto.randomUUID(),
    idempotency_key: crypto.randomUUID(),
    operator_id: "demo-operator",
    reason: "gui-triggered action",
    client_ts_ms: Date.now(),
    expected_state_revision: overview.state_revision,
    expected_previous_state: null,
    payload: {},
    ...extra
  };
}

async function runQuickAction(actionName) {
  try {
    const overview = await getOverviewForEnvelope();
    let result;

    if (actionName === "refresh") {
      await loadDashboard();
      setActionSummary("刷新概览 / Refresh", "success", overview.state_revision, "-", "界面已刷新 / dashboard refreshed.", { message: "Refresh completed." });
      return;
    }

    if (actionName === "validate") {
      result = await apiPost("/api/v1/control/demo/validate", baseEnvelope(overview));
    }

    if (actionName === "bundle") {
      result = await apiPost("/api/v1/control/safe-recheck-bundle", baseEnvelope(overview));
    }

    if (actionName === "set-demo-mode") {
      result = await apiPost("/api/v1/input/config-change", baseEnvelope(overview, {
        payload: { changes: [{ path: "global_runtime.controls.global_execution_mode_switch", value: "demo_reserved" }] }
      }));
    }

    if (actionName === "enable-spot") {
      result = await apiPost("/api/v1/input/config-change", baseEnvelope(overview, {
        payload: { changes: [
          { path: "product_family_status.spot.controls.enabled_switch", value: true },
          { path: "product_family_status.spot.controls.mode_switch", value: "shadow_only" }
        ] }
      }));
    }

    if (actionName === "arm-demo") {
      const demoState = overview.data.demo_control_summary.demo_state_switch;
      result = await apiPost("/api/v1/control/demo/arm", baseEnvelope(overview, {
        expected_previous_state: demoState,
        payload: { acknowledged: true }
      }));
    }

    summarizeActionResult(actionName, result);
    await loadDashboard();
  } catch (error) {
    setActionSummary("动作失败 / Action Failed", "failed", "-", "-", String(error), String(error));
  }
}

document.addEventListener("DOMContentLoaded", () => {
  ensureGuiEnhancements();
  document.getElementById("connectButton").addEventListener("click", async () => {
    inMemoryToken = document.getElementById("tokenInput").value.trim();
    try {
      await loadDashboard();
      setConnectionStatus("已连接 / Connected", "good");
      setActionSummary("连接 / Connect", "success", "-", "-", "连接成功 / connected successfully.", { message: "Connected successfully." });
    } catch (error) {
      setConnectionStatus("连接失败 / Failed", "bad");
      setActionSummary("连接 / Connect", "failed", "-", "-", String(error), String(error));
    }
  });

  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => runQuickAction(button.dataset.action));
  });
});
