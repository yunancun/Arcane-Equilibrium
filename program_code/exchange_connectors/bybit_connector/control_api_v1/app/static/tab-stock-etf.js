const LANE_STATUS_ENDPOINT = '/api/v1/stock-etf/lane-status';
const READINESS_ENDPOINT = '/api/v1/stock-etf/readiness';
const DATA_FOUNDATION_STATUS_ENDPOINT = '/api/v1/stock-etf/data-foundation-status';
const POLICY_STATUS_ENDPOINT = '/api/v1/stock-etf/policy-status';
const AUTHORIZATION_STATUS_ENDPOINT = '/api/v1/stock-etf/authorization-status';
const ACCOUNT_STATUS_ENDPOINT = '/api/v1/stock-etf/account-status';
const EVIDENCE_STATUS_ENDPOINT = '/api/v1/stock-etf/evidence-status';
const UNIVERSE_STATUS_ENDPOINT = '/api/v1/stock-etf/universe-status';
const SHADOW_STATUS_ENDPOINT = '/api/v1/stock-etf/shadow-status';
const PAPER_STATUS_ENDPOINT = '/api/v1/stock-etf/paper-status';
const RECONCILIATION_STATUS_ENDPOINT = '/api/v1/stock-etf/reconciliation-status';
const SCORECARD_STATUS_ENDPOINT = '/api/v1/stock-etf/scorecard-status';
const LAUNCH_STATUS_ENDPOINT = '/api/v1/stock-etf/launch-status';

function renderFallback() {
  const data = {
    default_asset_lane: 'crypto_perp',
    readiness_state: 'degraded',
    source_readiness: { denial_reasons: ['api_unavailable'], paper_ready: false, readonly_ready: false, live_denied: true },
    gui_authority: 'display_only',
    phase2_gate_status: 'BLOCKED',
    phase2_gate_blockers: ['api_unavailable'],
    api_allowlist: {
      contract_id: '',
      source_version: 0,
      accepted: false,
      blockers: ['api_unavailable'],
      read_action_count: 0,
      paper_write_action_count: 0,
      denied_action_count: 0,
      ibkr_contact_performed: false,
      secret_content_serialized: false,
      bybit_live_execution_protected: false,
    },
    first_ibkr_contact_allowed: false,
    immutable_pass_artifact_present: false,
    connector_enabled: false,
    readonly_probe_request: {
      contract_id: 'stock_etf_ibkr_readonly_probe_request_v1',
      source_version: 1,
      request_artifact_present: false,
      request_validated: false,
      accepted_for_contact: false,
      status: 'blocked_no_request_artifact',
      blockers: ['api_unavailable', 'probe_request_artifact_missing'],
      ibkr_contact_performed: false,
      connector_runtime_started: false,
      secret_content_serialized: false,
      order_routed: false,
      paper_order_submitted: false,
      db_apply_performed: false,
      evidence_clock_started: false,
      bybit_path_reused: false,
      live_or_tiny_live_authorized: false,
    },
    readonly_probe_result_import_request: {
      contract_id: 'stock_etf_ibkr_readonly_probe_result_import_request_v1',
      source_version: 1,
      request_artifact_present: false,
      request_validated: false,
      accepted_for_import: false,
      status: 'blocked_no_result_import_request_artifact',
      blockers: ['api_unavailable', 'probe_result_import_request_artifact_missing'],
      ibkr_contact_performed: false,
      connector_runtime_started: false,
      secret_content_serialized: false,
      result_import_performed: false,
      evidence_writer_started: false,
      scorecard_writer_started: false,
      db_apply_performed: false,
      order_routed: false,
      paper_order_submitted: false,
      bybit_path_reused: false,
      live_or_tiny_live_authorized: false,
    },
    connector_skeleton: {
      surface_id: 'ibkr_stock_etf_readonly_connector_skeleton_v1',
      accepted: false,
      status: 'blocked_source_only',
      blockers: ['api_unavailable'],
      network_contact_performed: false,
      secret_content_loaded: false,
      paper_channel_exposed: false,
      live_channel_exposed: false,
      order_write_method_present: false,
      bybit_path_reused: false,
    },
    ibkr_live_enabled: false,
    stock_live_disabled: true,
    paper_order_entry_visible: false,
    ibkr_call_performed: false,
    secret_slot_touched: false,
    order_routed: false,
    bybit_ipc_reused: false,
    denied_operations: ['ibkr_api_contact_before_phase2_gate'],
    degraded: true,
    reason: 'api_unavailable',
  };
  window.renderReadiness(data, null);
  renderDataFoundationStatus(dataFoundationFallback('api_unavailable'));
  renderPolicyStatus(policyFallback('api_unavailable'));
  window.renderAuthorizationStatus(authorizationFallback('api_unavailable'));
  window.renderAccountStatus(accountFallback('api_unavailable'));
  window.renderEvidenceStatus(evidenceFallback('api_unavailable'));
  window.renderUniverseStatus(universeFallback('api_unavailable'));
  window.renderShadowStatus(shadowFallback('api_unavailable'));
  window.renderPaperStatus(paperFallback('api_unavailable'));
  renderReconciliationStatus(reconciliationFallback('api_unavailable'));
  window.renderScorecardStatus(scorecardFallback('api_unavailable'));
  window.renderLaunchStatus(launchFallback('api_unavailable'));
  if (window.renderPhase0Status && window.phase0Fallback) {
    window.renderPhase0Status(window.phase0Fallback('api_unavailable'));
  }
  if (window.renderReleasePacketStatus && window.releasePacketFallback) {
    window.renderReleasePacketStatus(window.releasePacketFallback('api_unavailable'));
  }
  if (window.renderDisableCleanupStatus && window.disableCleanupFallback) {
    window.renderDisableCleanupStatus(window.disableCleanupFallback('api_unavailable'));
  }
}

async function loadReadiness() {
  const [
    lanePayload,
    readinessPayload,
    dataFoundationPayload,
    policyPayload,
    authorizationPayload,
    accountPayload,
    evidencePayload,
    universePayload,
    shadowPayload,
    paperPayload,
    reconciliationPayload,
    scorecardPayload,
    launchPayload,
    phase0Payload,
    releasePacketPayload,
    disableCleanupPayload,
  ] = await Promise.all([
    ocApi(LANE_STATUS_ENDPOINT, { method: 'GET', timeoutMs: 5000, toastOnError: false }),
    ocApi(READINESS_ENDPOINT, { method: 'GET', timeoutMs: 5000, toastOnError: false }),
    ocApi(DATA_FOUNDATION_STATUS_ENDPOINT, { method: 'GET', timeoutMs: 5000, toastOnError: false }),
    ocApi(POLICY_STATUS_ENDPOINT, { method: 'GET', timeoutMs: 5000, toastOnError: false }),
    ocApi(AUTHORIZATION_STATUS_ENDPOINT, { method: 'GET', timeoutMs: 5000, toastOnError: false }),
    ocApi(ACCOUNT_STATUS_ENDPOINT, { method: 'GET', timeoutMs: 5000, toastOnError: false }),
    ocApi(EVIDENCE_STATUS_ENDPOINT, { method: 'GET', timeoutMs: 5000, toastOnError: false }),
    ocApi(UNIVERSE_STATUS_ENDPOINT, { method: 'GET', timeoutMs: 5000, toastOnError: false }),
    ocApi(SHADOW_STATUS_ENDPOINT, { method: 'GET', timeoutMs: 5000, toastOnError: false }),
    ocApi(PAPER_STATUS_ENDPOINT, { method: 'GET', timeoutMs: 5000, toastOnError: false }),
    ocApi(RECONCILIATION_STATUS_ENDPOINT, { method: 'GET', timeoutMs: 5000, toastOnError: false }),
    ocApi(SCORECARD_STATUS_ENDPOINT, { method: 'GET', timeoutMs: 5000, toastOnError: false }),
    ocApi(LAUNCH_STATUS_ENDPOINT, { method: 'GET', timeoutMs: 5000, toastOnError: false }),
    ocApi(window.STOCK_ETF_PHASE0_STATUS_ENDPOINT, { method: 'GET', timeoutMs: 5000, toastOnError: false }),
    ocApi(window.STOCK_ETF_RELEASE_PACKET_STATUS_ENDPOINT, { method: 'GET', timeoutMs: 5000, toastOnError: false }),
    ocApi(window.STOCK_ETF_DISABLE_CLEANUP_STATUS_ENDPOINT, { method: 'GET', timeoutMs: 5000, toastOnError: false }),
  ]);
  if (!readinessPayload || !readinessPayload.data) {
    renderFallback();
    return;
  }
  window.renderReadiness(readinessPayload.data, lanePayload && lanePayload.data ? lanePayload.data : null);
  renderDataFoundationStatus(
    dataFoundationPayload && dataFoundationPayload.data
      ? dataFoundationPayload.data
      : dataFoundationFallback('api_unavailable')
  );
  renderPolicyStatus(policyPayload && policyPayload.data ? policyPayload.data : policyFallback('api_unavailable'));
  window.renderAuthorizationStatus(
    authorizationPayload && authorizationPayload.data
      ? authorizationPayload.data
      : authorizationFallback('api_unavailable')
  );
  window.renderAccountStatus(accountPayload && accountPayload.data ? accountPayload.data : accountFallback('api_unavailable'));
  window.renderEvidenceStatus(evidencePayload && evidencePayload.data ? evidencePayload.data : evidenceFallback('api_unavailable'));
  window.renderUniverseStatus(universePayload && universePayload.data ? universePayload.data : universeFallback('api_unavailable'));
  window.renderShadowStatus(shadowPayload && shadowPayload.data ? shadowPayload.data : shadowFallback('api_unavailable'));
  window.renderPaperStatus(paperPayload && paperPayload.data ? paperPayload.data : paperFallback('api_unavailable'));
  renderReconciliationStatus(
    reconciliationPayload && reconciliationPayload.data
      ? reconciliationPayload.data
      : reconciliationFallback('api_unavailable')
  );
  window.renderScorecardStatus(
    scorecardPayload && scorecardPayload.data
      ? scorecardPayload.data
      : scorecardFallback('api_unavailable')
  );
  window.renderLaunchStatus(
    launchPayload && launchPayload.data
      ? launchPayload.data
      : launchFallback('api_unavailable')
  );
  if (window.renderPhase0Status && window.phase0Fallback) {
    window.renderPhase0Status(
      phase0Payload && phase0Payload.data
        ? phase0Payload.data
        : window.phase0Fallback('api_unavailable')
    );
  }
  if (window.renderReleasePacketStatus && window.releasePacketFallback) {
    window.renderReleasePacketStatus(
      releasePacketPayload && releasePacketPayload.data
        ? releasePacketPayload.data
        : window.releasePacketFallback('api_unavailable')
    );
  }
  if (window.renderDisableCleanupStatus && window.disableCleanupFallback) {
    window.renderDisableCleanupStatus(
      disableCleanupPayload && disableCleanupPayload.data
        ? disableCleanupPayload.data
        : window.disableCleanupFallback('api_unavailable')
    );
  }
}

waitForServerUp(loadReadiness);
