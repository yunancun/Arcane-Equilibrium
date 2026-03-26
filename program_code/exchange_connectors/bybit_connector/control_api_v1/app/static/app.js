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

function variantForState(value) {
  const normalized = String(value || "").toLowerCase();
  if (["passed", "healthy", "ready", "fresh", "complete", "shadow_only", "shadow_control_ready"].includes(normalized)) {
    return "good";
  }
  if (["blocked", "disabled", "down", "missing", "failed", "unavailable", "unknown"].includes(normalized)) {
    return "bad";
  }
  if (["partial", "degraded", "demo_reserved", "demo_blocked", "armed_but_closed"].includes(normalized)) {
    return "warn";
  }
  return "neutral";
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

  setRuntimeModeBadge(
    `${runtime.global_mode_state} · ${demo.demo_state_switch}`,
    variantForState(runtime.global_execution_authority_state)
  );
}

function renderKvGrid(nodeId, items) {
  const node = document.getElementById(nodeId);
  node.innerHTML = items.map(([label, value]) => {
    const safeValue = value === undefined || value === null ? "-" : String(value);
    return `<div class="kv-item"><dt>${label}</dt><dd><span class="status-chip ${variantForState(safeValue)}">${safeValue}</span></dd></div>`;
  }).join("");
}

function renderSourceContext(sourceContext) {
  renderKvGrid("sourceContextGrid", [
    ["Readonly Connector", sourceContext.readonly_connector_name],
    ["Execution Connector", sourceContext.execution_connector_name || "not_attached"],
    ["REST Private", sourceContext.rest_private_connection_state],
    ["WS Private", sourceContext.ws_private_connection_state],
    ["Runtime Connection", sourceContext.runtime_connection_state],
    ["Account Completeness", sourceContext.account_fact_completeness_state],
    ["Snapshot Completeness", sourceContext.source_snapshot_completeness_state],
    ["Role Separation", sourceContext.connector_role_separation_ok],
    ["Runtime Snapshot", sourceContext.pinned_runtime_snapshot_id]
  ]);
}

function renderHealth(overview) {
  const health = overview.data.health_summary;
  renderKvGrid("healthGrid", [
    ["Overall Health Score", health.scores.overall_health_score],
    ["AI Health Score", health.scores.ai_health_score],
    ["Exchange Health Score", health.scores.exchange_health_score],
    ["Data Freshness Score", health.scores.data_freshness_score],
    ["Health Gates Overall", health.gates.health_gates_overall_state],
    ["Exchange Timeout Gate", health.gates.exchange_timeout_gate_state],
    ["WS Disconnect Gate", health.gates.ws_disconnect_gate_state],
    ["Latency Gate", health.gates.latency_gate_state],
    ["Freshness Gate", health.gates.freshness_gate_state]
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
  const [overview, controlPlane, sourceContext, audit, productFamilies] = await Promise.all([
    apiGet("/api/v1/system/overview"),
    apiGet("/api/v1/system/control-plane"),
    apiGet("/api/v1/system/source-context"),
    apiGet("/api/v1/system/audit-summary"),
    apiGet("/api/v1/system/product-families")
  ]);

  renderSummary(overview);
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
  const resultBox = document.getElementById("actionResultBox");
  try {
    const overview = await getOverviewForEnvelope();
    let result;

    if (actionName === "refresh") {
      await loadDashboard();
      resultBox.textContent = "刷新成功 / Refresh completed.";
      return;
    }

    if (actionName === "validate") {
      result = await apiPost("/api/v1/control/demo/validate", baseEnvelope(overview));
    }

    if (actionName === "bundle") {
      result = await apiPost("/api/v1/control/safe-recheck-bundle", baseEnvelope(overview));
    }

    if (actionName === "set-demo-mode") {
      result = await apiPost(
        "/api/v1/input/config-change",
        baseEnvelope(overview, {
          payload: {
            changes: [
              {
                path: "global_runtime.controls.global_execution_mode_switch",
                value: "demo_reserved"
              }
            ]
          }
        })
      );
    }

    if (actionName === "enable-spot") {
      result = await apiPost(
        "/api/v1/input/config-change",
        baseEnvelope(overview, {
          payload: {
            changes: [
              {
                path: "product_family_status.spot.controls.enabled_switch",
                value: true
              },
              {
                path: "product_family_status.spot.controls.mode_switch",
                value: "shadow_only"
              }
            ]
          }
        })
      );
    }

    if (actionName === "arm-demo") {
      const demoState = overview.data.demo_control_summary.demo_state_switch;
      result = await apiPost(
        "/api/v1/control/demo/arm",
        baseEnvelope(overview, {
          expected_previous_state: demoState,
          payload: { acknowledged: true }
        })
      );
    }

    resultBox.textContent = pretty(result);
    await loadDashboard();
  } catch (error) {
    resultBox.textContent = String(error);
  }
}

document.getElementById("connectButton").addEventListener("click", async () => {
  inMemoryToken = document.getElementById("tokenInput").value.trim();
  const resultBox = document.getElementById("actionResultBox");
  try {
    await loadDashboard();
    setConnectionStatus("已连接 / Connected", "good");
    resultBox.textContent = "连接成功 / Connected successfully.";
  } catch (error) {
    setConnectionStatus("连接失败 / Failed", "bad");
    resultBox.textContent = String(error);
  }
});

document.querySelectorAll("[data-action]").forEach((button) => {
  button.addEventListener("click", () => runQuickAction(button.dataset.action));
});
