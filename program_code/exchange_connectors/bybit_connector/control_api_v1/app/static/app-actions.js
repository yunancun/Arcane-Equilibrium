/**
 * OpenClaw Dashboard & Action Handlers
 * OpenClaw 儀表板和動作處理
 *
 * MODULE_NOTE (EN): Extracted from app.js (FIX-08 file size).
 * MODULE_NOTE (中): 從 app.js 提取（FIX-08 文件大小）。
 */

"use strict";

// ── 主數據載入 / Main data loading ───────────────────────────────────────────

async function loadDashboard() {
  ensureGuiEnhancements();

  // 并发載入所有數據（含 L 章學習 + 净 PnL 端点）
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

  // 渲染各區块 / Render each section
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

  // 調試原文 / Debug raw JSON
  document.getElementById("overviewBox").textContent = pretty(overview);
  document.getElementById("controlPlaneBox").textContent = pretty(controlPlane);
  document.getElementById("auditBox").textContent = pretty(audit);

  // Paper Trading 載入 / Load paper trading data
  refreshPaperTrading().catch(() => {});
}

// ── 動作處理：快捷動作 / Action handler: quick actions ───────────────────────

async function runQuickAction(actionName) {
  try {
    if (actionName !== "refresh") {
      const confirmed = await openConfirmModal(actionName);
      if (!confirmed) {
        setActionSummary(
          "已取消 / Cancelled", "blocked", "-", "-",
          "用户取消了關键動作确認。 / User cancelled.", { cancelled: true, action: actionName }
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
    setActionSummary("動作失败 / Action Failed", "failed", "-", "-", String(error), String(error));
  }
}

// ── 動作處理：產品族配置應用 / Action handler: product family config apply ──────

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
    setActionSummary(`產品族配置失败 / PF Config Failed (${family})`, "failed", "-", "-", String(error), String(error));
  }
}

// ── 動作處理：產品族動作權限变更 / Action handler: product family action permissions ──

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
    setActionSummary(`權限变更失败 / Perm Change Failed (${family})`, "failed", "-", "-", String(error), String(error));
  }
}

// ── 動作處理：費用录入 / Action handler: cost entry ──────────────────────────

async function submitCostEntry() {
  const amount = parseFloat(document.getElementById("costAmount")?.value || "0");
  const category = document.getElementById("costCategory")?.value || "manual";
  const note = document.getElementById("costNote")?.value || "";

  if (isNaN(amount) || amount <= 0) {
    setActionSummary("录入失败", "failed", "-", "-", "請輸入有效的正數金额 / Please enter a valid positive amount.", {});
    return;
  }

  try {
    const result = await apiPost("/api/v1/input/cost", baseEnvelope({
      payload: { amount, category, note }
    }));
    summarizeActionResult("cost-entry", result);
    // 清空表單 / Clear form
    document.getElementById("costAmount").value = "";
    document.getElementById("costNote").value = "";
    await loadDashboard();
  } catch (error) {
    setActionSummary("費用录入失败 / Cost Entry Failed", "failed", "-", "-", String(error), String(error));
  }
}

// ── 動作處理：PnL 录入 / Action handler: PnL entry ───────────────────────────

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
    // 清空表單 / Clear form
    document.getElementById("pnlRealized").value = "";
    document.getElementById("pnlUnrealized").value = "";
    document.getElementById("pnlSymbol").value = "";
    await loadDashboard();
  } catch (error) {
    setActionSummary("PnL 录入失败 / PnL Entry Failed", "failed", "-", "-", String(error), String(error));
  }
}

// ── 動作處理：系統設置應用 / Action handler: system settings apply ─────────────

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
    setActionSummary("設置失败 / Settings Failed", "failed", "-", "-", String(error), String(error));
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
    setActionSummary("設置失败 / Settings Failed", "failed", "-", "-", String(error), String(error));
  }
}

