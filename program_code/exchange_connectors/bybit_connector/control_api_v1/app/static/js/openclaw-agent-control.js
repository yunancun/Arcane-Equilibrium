/**
 * OpenClaw Agent Control read-only frontend.
 *
 * MODULE_NOTE (中文):
 *   MAG-018：tab-agents.html 的只讀 Agent Control foundation。只讀取
 *   /api/v1/openclaw/status 與 /api/v1/openclaw/self-state，渲染 topology、
 *   gateway/channel posture、authority boundary、degraded/error state。
 *   本檔不發 POST/PUT/PATCH/DELETE，不提供交易或 proposal 控制。
 */

"use strict";

const _OPENCLAW_CONTROL_TIMERS = {
  selfState: null,
};

let _openclawPollSeq = 0;

function _openclawSetState(type) {
  ["loading", "error"].forEach(function (name) {
    const el = document.getElementById("openclaw-control-" + name);
    if (el) el.style.display = (name === type) ? "" : "none";
  });
  const dataEl = document.getElementById("openclaw-control-data");
  if (dataEl) dataEl.style.display = (type === "data") ? "" : "none";
}

function _openclawRequestId() {
  if (typeof _ocUUID === "function") return _ocUUID();
  return "openclaw-" + Date.now() + "-" + Math.random().toString(16).slice(2);
}

function _openclawSender() {
  try {
    return localStorage.getItem("oc_username") || "console";
  } catch (_) {
    return "console";
  }
}

async function _openclawApi(path) {
  const headers = {
    "x-openclaw-source": "tradebot-console",
    "x-openclaw-channel": "console",
    "x-openclaw-sender": _openclawSender(),
    "x-openclaw-auth-profile": "read_only",
    "x-openclaw-request-id": _openclawRequestId(),
  };
  try {
    const r = await fetch(path, {
      method: "GET",
      headers: headers,
      credentials: "same-origin",
      signal: AbortSignal.timeout(8000),
    });
    if (!r.ok) {
      if (typeof ocHandleUnauthenticatedResponse === "function") {
        await ocHandleUnauthenticatedResponse(r);
      }
      console.warn("[openclaw-agent-control] GET " + path + " -> " + r.status);
      return null;
    }
    return await r.json();
  } catch (e) {
    console.warn("[openclaw-agent-control] network error: " + path, e);
    return null;
  }
}

function _openclawStatusChip(status, degraded) {
  const s = String(status || "unknown").toLowerCase();
  if (s === "pass" && !degraded) return ocChip("PASS", "good");
  if (s === "fail") return ocChip("FAIL", "bad");
  if (s === "degraded" || degraded) return ocChip("DEGRADED", "warn");
  if (s === "warn") return ocChip("WARN", "warn");
  if (s === "disabled") return ocChip("DISABLED", "neutral");
  return ocChip("UNKNOWN", "bad");
}

function _openclawCapability(label, allowed, safeWhenFalse) {
  const ok = safeWhenFalse ? allowed === false : allowed === true;
  const chip = ok ? "good" : "bad";
  const state = allowed ? "yes" : "no";
  return '<span>' + ocEsc(label) + '</span><span>'
    + ocChip(state, chip) + '</span>';
}

function _openclawNum(value) {
  if (value == null || !isFinite(Number(value))) return "--";
  return String(Number(value));
}

function _openclawPanelHtml(title, bodyHtml) {
  return '<h4>' + ocEsc(title) + '</h4>' + bodyHtml;
}

function _renderOpenClawAuthority(statusPayload) {
  const data = (statusPayload && statusPayload.data) || {};
  const authority = data.authority || {};
  const eventStore = data.agent_event_store || {};
  const rows = eventStore.recent_rows || {};
  let html = '<div class="agent-control-kv">';
  html += '<span>Trading authority</span><span><code>'
    + ocEsc(authority.trading_authority || "--") + '</code></span>';
  html += '<span>Gateway role</span><span>'
    + ocEsc(authority.gateway_role || "--") + '</span>';
  html += '<span>Event rows 30m</span><span>'
    + 'msg ' + _openclawNum(rows.messages)
    + ' / state ' + _openclawNum(rows.state_changes)
    + ' / ai ' + _openclawNum(rows.ai_invocations)
    + '</span>';
  html += '<span>Row proof</span><span>'
    + ocChip(eventStore.row_proof ? "complete" : "incomplete", eventStore.row_proof ? "good" : "warn")
    + '</span>';
  html += _openclawCapability("Submit orders", authority.can_submit_orders, true);
  html += _openclawCapability("Mutate live config", authority.can_mutate_live_config, true);
  html += _openclawCapability("Read secrets", authority.can_read_secrets, true);
  html += _openclawCapability("Proposal endpoints", authority.deferred_workflows_enabled, true);
  html += '</div>';
  ocSetHtml("openclaw-authority-panel", _openclawPanelHtml("Authority Lockdown", html));
}

function _renderOpenClawGateway(statusPayload) {
  const data = (statusPayload && statusPayload.data) || {};
  const gateway = data.gateway || {};
  const runtime = data.runtime || {};
  const budget = data.model_budget || {};
  const channels = gateway.channels || {};
  let channelHtml = '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px">';
  Object.keys(channels).forEach(function (name) {
    const value = channels[name];
    const chip = value === "available" ? "good" : "neutral";
    channelHtml += ocChip(name + ": " + value, chip);
  });
  channelHtml += '</div>';

  let html = '<div class="agent-control-kv">';
  html += '<span>Gateway</span><span>'
    + ocChip(gateway.status || "unknown", gateway.configured ? "good" : "neutral")
    + '</span>';
  html += '<span>Runtime connection</span><span>'
    + ocChip(runtime.runtime_connection_state || "unknown", runtime.runtime_connection_state === "healthy" ? "good" : "warn")
    + '</span>';
  html += '<span>Engine alive</span><span>'
    + ocChip(String(runtime.engine_alive), runtime.engine_alive === true ? "good" : "warn")
    + '</span>';
  html += '<span>Cloud supervisor</span><span>'
    + ocChip(budget.cloud_enabled ? "enabled" : "disabled", budget.cloud_enabled ? "warn" : "neutral")
    + '</span>';
  html += '</div>' + channelHtml;
  ocSetHtml("openclaw-gateway-panel", _openclawPanelHtml("Gateway / Channel Posture", html));
}

function _topologyNodeClass(row) {
  const state = String(row.runtime_state || "").toLowerCase();
  if (state === "running" || state === "available" || state === "healthy") return "good";
  if (state === "disabled" || state === "not_configured") return "warn";
  if (state === "offline" || state === "failed" || state === "error") return "bad";
  return "warn";
}

function _renderOpenClawTopology(selfPayload) {
  const data = (selfPayload && selfPayload.data) || {};
  const agents = data.agents || [];
  const gateway = data.gateway || {};
  const runtime = data.runtime || {};
  const nodes = agents.slice();
  nodes.push({
    role: "gateway",
    runtime_state: gateway.status || "unknown",
    source: gateway.configured ? "configured" : "not_configured",
  });
  nodes.push({
    role: "rust_engine",
    runtime_state: runtime.runtime_connection_state || "unknown",
    source: runtime.engine_alive === true ? "engine_alive" : "runtime_summary",
  });

  let html = '<div class="agent-control-topology">';
  nodes.forEach(function (row) {
    const cls = _topologyNodeClass(row);
    const role = row.role || "unknown";
    const state = row.runtime_state || "unknown";
    const source = row.source || "";
    html += '<div class="agent-control-node ' + cls + '">';
    html += '<div class="agent-control-node-name">' + ocEsc(role) + '</div>';
    html += '<div class="agent-control-node-meta">' + ocEsc(state) + '</div>';
    if (source) {
      html += '<div class="agent-control-node-meta">' + ocEsc(source) + '</div>';
    }
    html += '</div>';
  });
  html += '</div>';
  ocSetHtml("openclaw-topology-panel", _openclawPanelHtml("Topology", html));
}

function _renderOpenClawBlockers(selfPayload) {
  const data = (selfPayload && selfPayload.data) || {};
  const blockers = data.open_blockers || [];
  let html = '<div class="agent-control-blockers">';
  if (!blockers.length) {
    html += '<div style="color:var(--text-dim);font-size:12px">No active MAG-018 read-only blockers.</div>';
  } else {
    blockers.forEach(function (blocker) {
      const severity = blocker.severity || "warn";
      html += '<div class="agent-control-blocker ' + (severity === "fail" ? "fail" : "") + '">';
      html += '<div><strong>' + ocEsc(blocker.code || "blocker") + '</strong> '
        + ocChip(severity, severity === "fail" ? "bad" : "warn") + '</div>';
      html += '<div style="color:var(--text-dim);margin-top:3px">'
        + ocEsc(blocker.summary || "") + '</div>';
      html += '</div>';
    });
  }
  html += '</div>';
  ocSetHtml("openclaw-blockers-panel", _openclawPanelHtml("Degraded / Error State", html));
}

async function loadOpenClawAgentControl() {
  const mySeq = ++_openclawPollSeq;
  _openclawSetState("loading");
  const results = await Promise.allSettled([
    _openclawApi("/api/v1/openclaw/status"),
    _openclawApi("/api/v1/openclaw/self-state"),
  ]);
  if (mySeq !== _openclawPollSeq) return;
  const statusPayload = results[0].status === "fulfilled" ? results[0].value : null;
  const selfPayload = results[1].status === "fulfilled" ? results[1].value : null;
  if (!statusPayload && !selfPayload) {
    _openclawSetState("error");
    return;
  }
  const primary = statusPayload || selfPayload;
  const chipEl = document.getElementById("openclaw-control-status-chip");
  if (chipEl && primary) {
    chipEl.innerHTML = _openclawStatusChip(primary.status, primary.degraded);
  }
  _renderOpenClawAuthority(statusPayload || selfPayload);
  _renderOpenClawGateway(statusPayload || selfPayload);
  _renderOpenClawTopology(selfPayload || statusPayload);
  _renderOpenClawBlockers(selfPayload || statusPayload);
  _openclawSetState("data");
}

function _openclawRegisterTimer() {
  if (_OPENCLAW_CONTROL_TIMERS.selfState) {
    clearInterval(_OPENCLAW_CONTROL_TIMERS.selfState);
  }
  _OPENCLAW_CONTROL_TIMERS.selfState = setInterval(loadOpenClawAgentControl, 30000);
}

function _openclawClearTimers() {
  if (_OPENCLAW_CONTROL_TIMERS.selfState) {
    clearInterval(_OPENCLAW_CONTROL_TIMERS.selfState);
    _OPENCLAW_CONTROL_TIMERS.selfState = null;
  }
}

function startOpenClawAgentControl() {
  loadOpenClawAgentControl();
  _openclawRegisterTimer();
}

window.addEventListener("pagehide", _openclawClearTimers);
document.addEventListener("visibilitychange", function () {
  if (document.hidden) {
    _openclawClearTimers();
  } else {
    startOpenClawAgentControl();
  }
});
