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
  const [overview, controlPlane, sourceContext, audit] = await Promise.all([
    apiGet("/api/v1/system/overview"),
    apiGet("/api/v1/system/control-plane"),
    apiGet("/api/v1/system/source-context"),
    apiGet("/api/v1/system/audit-summary")
  ]);

  document.getElementById("overviewBox").textContent = pretty(overview);
  document.getElementById("controlPlaneBox").textContent = pretty(controlPlane);
  document.getElementById("sourceContextBox").textContent = pretty(sourceContext);
  document.getElementById("auditBox").textContent = pretty(audit);
}

async function getOverviewForEnvelope() {
  const overview = await apiGet("/api/v1/system/overview");
  return overview;
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
      result = await apiPost(
        "/api/v1/control/demo/validate",
        baseEnvelope(overview)
      );
    }

    if (actionName === "bundle") {
      result = await apiPost(
        "/api/v1/control/safe-recheck-bundle",
        baseEnvelope(overview)
      );
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
    resultBox.textContent = "连接成功 / Connected successfully.";
  } catch (error) {
    resultBox.textContent = String(error);
  }
});

document.querySelectorAll("[data-action]").forEach((button) => {
  button.addEventListener("click", () => runQuickAction(button.dataset.action));
});
