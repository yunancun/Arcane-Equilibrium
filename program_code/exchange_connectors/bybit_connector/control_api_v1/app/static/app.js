let inMemoryToken = "";

const CRITICAL_ACTIONS = {
  "set-demo-mode": {
    title: "切换到 Demo Reserved",
    subtitle: "Set execution mode to demo_reserved",
    risk: "这会把全局执行模式从 disabled 推进到 demo_reserved。它不会直接开启真实执行，但会改变后续 demo 控制链路的可达性。",
    consequence: "后果：后续 validate / arm 的 gate 判断会基于 demo 模式运行。若误操作，可能让界面进入更接近可执行的受保护状态。"
  },
  "enable-spot": {
    title: "开启 Spot Shadow",
    subtitle: "Enable spot product family in shadow mode",
    risk: "这会修改产品族控制配置，使 spot 从可见但关闭，推进为受控 shadow 模式。",
    consequence: "后果：spot 控制面展示和部分 gate 结果会随之变化，但仍不会直接放开 live execution。"
  },
  "arm-demo": {
    title: "执行 Demo Arm",
    subtitle: "Move demo state to armed_but_closed",
    risk: "这是 demo 状态机的关键节点。执行后，demo 主状态会从 closed/relocked 进入 armed_but_closed。",
    consequence: "后果：系统会更接近 demo enable，但仍处于封闭保护态；若前置 gate 不满足则会被阻断。"
  },
  bundle: {
    title: "执行安全复核打包",
    subtitle: "Run safe recheck bundle",
    risk: "该动作会触发多步复核/聚合逻辑，并刷新控制判断结果。",
    consequence: "后果：页面上的 readiness、gate、audit 摘要可能一起变化，适合在明确知道用途时再执行。"
  }
};

function headers() {
  return {
    Authorization: `Bearer ${inMemoryToken}`,
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
  if (["passed", "healthy", "ready", "fresh", "complete", "shadow_only", "shadow_control_ready", "success", "true", "allowed"].includes(normalized)) return "good";
  if (["blocked", "disabled", "down", "missing", "failed", "unavailable", "unknown", "false"].includes(normalized)) return "bad";
  if (["partial", "degraded", "demo_reserved", "demo_blocked", "armed_but_closed", "visible_only", "shadow_visible"].includes(normalized)) return "warn";
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
    refresh: "刷新概览",
    validate: "验证 Demo",
    bundle: "安全复核打包",
    "set-demo-mode": "切到 Demo Reserved",
    "enable-spot": "开启 Spot Shadow",
    "arm-demo": "执行 Demo Arm"
  };

  const data = result?.data || {};
  let hint = "动作执行完成。";
  let helper = "Action completed.";

  if (actionName === "validate") {
    hint = `前提 gate：${safeText(data.demo_prerequisites_gate_state)}；Arm gate：${safeText(data.demo_arm_gate_state)}`;
    helper = `Prerequisites gate: ${safeText(data.demo_prerequisites_gate_state)}; Arm gate: ${safeText(data.demo_arm_gate_state)}`;
  } else if (actionName === "arm-demo") {
    hint = `Demo 状态切换为：${safeText(data.demo_state_switch)}`;
    helper = `Demo state switched to: ${safeText(data.demo_state_switch)}`;
  } else if (actionName === "set-demo-mode" || actionName === "enable-spot") {
    hint = `已接受路径：${(data.accepted_paths || []).join(", ") || "none"}`;
    helper = `Accepted paths: ${(data.accepted_paths || []).join(", ") || "none"}`;
  } else if (actionName === "bundle") {
    hint = `打包结果：${safeText(result.action_result)}`;
    helper = `Bundle result: ${safeText(result.action_result)}`;
  } else if (actionName === "refresh") {
    hint = "界面已刷新。";
    helper = "Dashboard refreshed.";
  }

  setActionSummary(
    `${actionMap[actionName] || actionName} / ${actionMap[actionName] ? actionName.replaceAll("-", " ") : actionName}`,
    safeText(result.action_result),
    safeText(result.state_revision),
    safeText(result.audit_ref),
    `${hint} ${helper}`,
    result
  );
}

function zhEnPrimary(zh, en) {
  return `<span class="label-zh">${zh}</span><span class="label-en">${en}</span>`;
}

function annotateGlossary(termZh, termEn, noteZh, noteEn) {
  return `<div class="glossary-pill"><span class="glossary-term">${termZh}</span><span class="glossary-term-en">${termEn}</span><span class="glossary-note">${noteZh} / ${noteEn}</span></div>`;
}

function renderKvGrid(nodeId, items) {
  const node = document.getElementById(nodeId);
  node.innerHTML = items.map(([labelHtml, value]) => {
    const safeValue = safeText(value);
    return `<div class="kv-item"><dt>${labelHtml}</dt><dd><span class="status-chip ${variantForState(safeValue)}">${safeValue}</span></dd></div>`;
  }).join("");
}

function ensureGuiEnhancements() {
  const pageShell = document.querySelector(".page-shell");
  if (!pageShell) return;

  document.querySelector("label[for='tokenInput']")?.replaceChildren("访问令牌 / Bearer Token");
  document.getElementById("connectButton").textContent = "连接 / Connect";

  const topbarSubtle = document.querySelector(".topbar p");
  if (topbarSubtle) topbarSubtle.textContent = "RC2 控制台 · OpenClaw/Bybit 受保护控制面 / RC2 control console for guarded operations";

  const heroSubtle = document.querySelector(".hero-card .subtle");
  if (heroSubtle) heroSubtle.textContent = "高层状态、保护边界与 runtime snapshot 绑定情况。English helper text is intentionally lighter below.";

  const summaryLabels = document.querySelectorAll("#summaryGrid .summary-label");
  const summaryTexts = [
    zhEnPrimary("全局模式", "Global Mode"),
    zhEnPrimary("执行权限", "Execution Authority"),
    zhEnPrimary("Demo 状态", "Demo State"),
    zhEnPrimary("快照", "Snapshot"),
    zhEnPrimary("Runtime 快照", "Runtime Snapshot"),
    zhEnPrimary("仍受保护", "Runtime Protected")
  ];
  summaryLabels.forEach((node, index) => { if (summaryTexts[index]) node.innerHTML = summaryTexts[index]; });

  const cards = document.querySelectorAll(".page-shell > .card, .page-shell > .grid.two-up .card");
  cards.forEach((card) => {
    const h2 = card.querySelector("h2");
    if (!h2) return;
    const current = h2.textContent.trim();
    if (current.includes("来源上下文")) {
      h2.innerHTML = zhEnPrimary("来源上下文", "Source Context");
      card.querySelector(".subtle").textContent = "连接状态、完整性和 connector 角色分离。Small English hints stay secondary to reduce clutter.";
    }
    if (current.includes("健康摘要")) {
      h2.innerHTML = zhEnPrimary("健康摘要", "Health Summary");
      card.querySelector(".subtle").textContent = "健康评分、关键 gate 与 freshness。Used to judge whether runtime facts are trustworthy enough.";
    }
    if (current.includes("产品族事实")) {
      h2.innerHTML = zhEnPrimary("产品族事实", "Product Family Facts");
      card.querySelector(".subtle").textContent = "当前 visibility / capability / permission facts 概览。English kept secondary for readability.";
    }
    if (current.includes("快捷动作")) {
      h2.innerHTML = zhEnPrimary("快捷动作", "Quick Actions");
      card.querySelector(".subtle").textContent = "仅调用受保护控制面动作，不直接开放真实执行权限。Critical actions now require second confirmation.";
    }
    if (current.includes("调试原文")) {
      h2.innerHTML = zhEnPrimary("调试原文", "Debug Raw JSON");
      card.querySelector(".subtle").textContent = "默认折叠，仅在需要审计或排错时展开。These raw blocks are not the primary UI.";
    }
  });

  const ths = document.querySelectorAll("table thead th");
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
  ths.forEach((th, idx) => { if (tableHeaders[idx]) th.innerHTML = tableHeaders[idx]; });

  const actionButtons = {
    refresh: "刷新概览",
    validate: "验证 Demo",
    "set-demo-mode": "切到 Demo Reserved",
    "enable-spot": "开启 Spot Shadow",
    "arm-demo": "执行 Demo Arm",
    bundle: "安全复核打包"
  };
  document.querySelectorAll("[data-action]").forEach((button) => {
    const name = button.dataset.action;
    if (actionButtons[name]) button.innerHTML = `${actionButtons[name]}<span class="button-sub">${name.replaceAll("-", " ")}</span>`;
  });

  const actionSummaryLabels = document.querySelectorAll("#actionSummaryGrid .summary-label");
  const actionTexts = [
    zhEnPrimary("最近动作", "Last Action"),
    zhEnPrimary("结果", "Result"),
    zhEnPrimary("状态版本", "State Revision"),
    zhEnPrimary("审计引用", "Audit Ref")
  ];
  actionSummaryLabels.forEach((node, index) => { if (actionTexts[index]) node.innerHTML = actionTexts[index]; });

  const rawSummaries = document.querySelectorAll("details.raw-toggle summary");
  if (rawSummaries[0]) rawSummaries[0].innerHTML = zhEnPrimary("查看原始动作响应", "View raw action response");
  if (rawSummaries[1]) rawSummaries[1].innerHTML = zhEnPrimary("控制平面原文", "Control Plane Raw");
  if (rawSummaries[2]) rawSummaries[2].innerHTML = zhEnPrimary("审计摘要原文", "Audit Raw");
  if (rawSummaries[3]) rawSummaries[3].innerHTML = zhEnPrimary("系统总览原文", "Overview Raw");

  if (!document.getElementById("guiConceptHints")) {
    const hintCard = document.createElement("section");
    hintCard.className = "card glossary-card";
    hintCard.id = "guiConceptHints";
    hintCard.innerHTML = `
      <div class="card-header-row">
        <div>
          <h2>${zhEnPrimary("关键概念提示", "Key Concept Hints")}</h2>
          <p class="subtle">放在不起眼的位置，只补充关键词释义，不打断主体排版。</p>
        </div>
      </div>
      <div class="glossary-wrap">
        ${annotateGlossary("Gate", "Gate", "门槛判断，表示某动作是否满足前提", "a gate decides whether an action is allowed to proceed")}
        ${annotateGlossary("Shadow", "Shadow", "影子模式，只做可见性/控制验证，不开放真实执行", "shadow means validation and visibility without real live execution")}
        ${annotateGlossary("Demo Arm", "Demo Arm", "把 demo 状态推进到 armed_but_closed 的关键节点", "a critical demo-state transition to armed_but_closed")}
        ${annotateGlossary("Snapshot", "Snapshot", "同一屏数据的一致性标识", "the consistency marker for one screen of data")}
      </div>`;
    const hero = document.querySelector(".hero-card");
    if (hero) hero.after(hintCard);
  }

  if (!document.getElementById("runtimeModeSection")) {
    const grid = document.createElement("section");
    grid.className = "grid two-up injected-grid";
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
          <button data-action="set-demo-mode">切到 Demo Reserved<span class="button-sub">Set Demo Reserved</span></button>
          <button data-action="enable-spot">开启 Spot Shadow<span class="button-sub">Enable Spot Shadow</span></button>
          <button data-action="validate">验证 Demo 前提<span class="button-sub">Validate Demo</span></button>
          <button data-action="arm-demo">执行 Demo Arm<span class="button-sub">Demo Arm</span></button>
          <button class="button-muted" disabled>观测模式<span class="button-sub">Observe Only · later</span></button>
          <button class="button-muted" disabled>Live 模式<span class="button-sub">Live Mode · locked</span></button>
        </div>
        <div id="modeControlNote" class="mode-note">当前 GUI 只开放受保护的 demo / shadow 动作；live 相关切换仍保持封闭。轻微英文说明保留在小字中，避免干扰主阅读流。</div>
      </section>
      <section class="card" id="businessSummarySection">
        <div class="card-header-row">
          <div>
            <h2>${zhEnPrimary("经营与收益摘要", "Business & Income Summary")}</h2>
            <p class="subtle">来自 overview 的 daily business summary；当前为展示骨架，后续继续接更真实的 runtime exporter。</p>
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
        <div class="mode-note">当前只展示 overview 中已有的 daily business summary；后续可再做日/周/月切片与更完整收益面板。</div>
      </section>`;

    const firstGrid = document.querySelector(".page-shell > .grid.two-up");
    if (firstGrid) firstGrid.before(grid);
  }

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
          <div class="confirm-note">请确认你理解该动作不会直接开放真实 live execution，但会推进控制状态或影响可见控制结果。 / Please confirm you understand this does not directly open live execution, but it changes guarded control state or visible control outcomes.</div>
        </div>
        <div class="confirm-modal-footer">
          <button class="button-muted confirm-cancel" data-close-modal="true">取消 / Cancel</button>
          <button id="confirmModalProceed">确认执行 / Confirm</button>
        </div>
      </div>`;
    document.body.appendChild(modal);
  }
}

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
      document.querySelectorAll("[data-close-modal='true']").forEach((node) => node.replaceWith(node.cloneNode(true)));
      const proceed = document.getElementById("confirmModalProceed");
      proceed.replaceWith(proceed.cloneNode(true));
    };

    modal.querySelectorAll("[data-close-modal='true']").forEach((node) => {
      node.onclick = () => {
        cleanup();
        resolve(false);
      };
    });
    document.getElementById("confirmModalProceed").onclick = () => {
      cleanup();
      resolve(true);
    };
  });
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
    </tr>`).join("");
  body.innerHTML = rows || '<tr><td colspan="8" class="muted-cell">无数据 / No data</td></tr>';
}

async function apiGet(path) {
  const response = await fetch(path, { headers: headers() });
  const data = await response.json();
  if (!response.ok) throw new Error(pretty(data));
  return data;
}

async function apiPost(path, payload) {
  const response = await fetch(path, { method: "POST", headers: headers(), body: JSON.stringify(payload) });
  const data = await response.json();
  if (!response.ok) throw new Error(pretty(data));
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

    if (actionName !== "refresh") {
      const confirmed = await openConfirmModal(actionName);
      if (!confirmed) {
        setActionSummary("已取消 / Cancelled", "blocked", "-", "-", "用户取消了关键动作确认。 / User cancelled the critical action.", { cancelled: true, action: actionName });
        return;
      }
    }

    if (actionName === "refresh") {
      await loadDashboard();
      setActionSummary("刷新概览 / Refresh", "success", overview.state_revision, "-", "界面已刷新。 / Dashboard refreshed.", { message: "Refresh completed." });
      return;
    }
    if (actionName === "validate") result = await apiPost("/api/v1/control/demo/validate", baseEnvelope(overview));
    if (actionName === "bundle") result = await apiPost("/api/v1/control/safe-recheck-bundle", baseEnvelope(overview));
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
      setActionSummary("连接 / Connect", "success", "-", "-", "连接成功。 / Connected successfully.", { message: "Connected successfully." });
    } catch (error) {
      setConnectionStatus("连接失败 / Failed", "bad");
      setActionSummary("连接 / Connect", "failed", "-", "-", String(error), String(error));
    }
  });

  document.addEventListener("click", (event) => {
    const target = event.target.closest("[data-action]");
    if (!target) return;
    event.preventDefault();
    runQuickAction(target.dataset.action);
  });
});
