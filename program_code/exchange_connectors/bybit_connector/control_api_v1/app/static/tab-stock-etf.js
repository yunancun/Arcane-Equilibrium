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

function toneFor(value) {
  const s = String(value || '').toLowerCase();
  if (s === 'paper_ready' || s === 'readonly_ready' || s === 'source_ready' || s === 'pass' || s === 'false' || s === 'source') return 'good';
  if (s === 'phase2_blocked' || s === 'degraded' || s === 'shadow_only' || s === 'blocked' || s === 'not_started' || s === 'source_ready_runtime_blocked') return 'warn';
  if (s === 'contract_violation_blocked' || s === 'true' || s === 'denied') return 'bad';
  return 'neutral';
}

function boolChip(value, goodWhenFalse) {
  const flag = value === true;
  const good = goodWhenFalse ? !flag : flag;
  return ocChip(flag ? 'true' : 'false', good ? 'good' : 'bad');
}

function textChip(value) {
  return ocChip(value == null || value === '' ? '-' : String(value), toneFor(value));
}

function setChip(id, text, type) {
  const node = document.getElementById(id);
  if (!node) return;
  const safeType = ['good', 'warn', 'bad', 'neutral', 'info'].includes(type) ? type : 'neutral';
  node.textContent = text == null || text === '' ? '-' : String(text);
  node.className = 'oc-chip oc-chip-' + safeType;
}

function kvRow(label, html) {
  return '<tr><th>' + ocEsc(label) + '</th><td>' + html + '</td></tr>';
}

function chipList(items, emptyText) {
  if (!Array.isArray(items) || items.length === 0) {
    return '<span class="se-muted">' + ocEsc(emptyText || '-') + '</span>';
  }
  return items.map(item => ocChip(String(item), toneFor(item))).join('');
}

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
  renderReadiness(data, null);
  renderDataFoundationStatus(dataFoundationFallback('api_unavailable'));
  renderPolicyStatus(policyFallback('api_unavailable'));
  renderAuthorizationStatus(authorizationFallback('api_unavailable'));
  renderAccountStatus(accountFallback('api_unavailable'));
  renderEvidenceStatus(evidenceFallback('api_unavailable'));
  renderUniverseStatus(universeFallback('api_unavailable'));
  renderShadowStatus(shadowFallback('api_unavailable'));
  renderPaperStatus(paperFallback('api_unavailable'));
  renderReconciliationStatus(reconciliationFallback('api_unavailable'));
  renderScorecardStatus(scorecardFallback('api_unavailable'));
  renderLaunchStatus(launchFallback('api_unavailable'));
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

function renderReadiness(data, laneStatus) {
  const source = data.source_readiness || {};
  const apiAllowlist = data.api_allowlist || {};
  const readonlyProbe = data.readonly_probe_request || {};
  const connectorSkeleton = data.connector_skeleton || {};
  const lane = laneStatus || {};
  const flags = lane.flags || {};
  const defaultLane = lane.default_asset_lane || data.default_asset_lane || 'crypto_perp';
  document.getElementById('se-default-lane').innerHTML = textChip(defaultLane);
  document.getElementById('se-readiness-state').innerHTML = textChip(data.readiness_state || 'blocked');
  document.getElementById('se-readiness-sub').textContent =
    (source.denial_reasons || []).join(', ') || 'no source denial reasons';
  document.getElementById('se-paper-state').innerHTML = boolChip(source.paper_ready, false);
  document.getElementById('se-paper-sub').textContent = source.shadow_only ? 'shadow_only' : 'paper flag path';
  document.getElementById('se-live-state').innerHTML = boolChip(data.ibkr_live_enabled, true);
  setChip('se-gui-authority', data.gui_authority || 'display_only', 'neutral');
  setChip('se-phase2-status', data.phase2_gate_status || 'BLOCKED', toneFor(data.phase2_gate_status || 'blocked'));
  setChip(
    'se-api-allowlist-status',
    apiAllowlist.accepted ? 'accepted' : 'blocked',
    apiAllowlist.accepted ? 'good' : 'bad'
  );
  setChip('se-degraded', data.degraded ? 'degraded' : 'source', data.degraded ? 'warn' : 'good');

  document.getElementById('se-lane-body').innerHTML = [
    kvRow('asset_lane', textChip(data.asset_lane || 'stock_etf_cash')),
    kvRow('broker', textChip(data.broker || 'ibkr')),
    kvRow('default_asset_lane', textChip(defaultLane)),
    kvRow('lane_status_state', textChip(lane.lane_status_state || '-')),
    kvRow('flag.stock_etf_lane_enabled', boolChip(flags.stock_etf_lane_enabled, false)),
    kvRow('flag.ibkr_readonly_enabled', boolChip(flags.ibkr_readonly_enabled, false)),
    kvRow('flag.ibkr_paper_enabled', boolChip(flags.ibkr_paper_enabled, false)),
    kvRow('flag.stock_etf_shadow_only', boolChip(flags.stock_etf_shadow_only, false)),
    kvRow('readonly_ready', boolChip(source.readonly_ready, false)),
    kvRow('paper_ready', boolChip(source.paper_ready, false)),
    kvRow('paper_order_entry_visible', boolChip(data.paper_order_entry_visible, true)),
  ].join('');

  document.getElementById('se-phase2-body').innerHTML = [
    kvRow('immutable_pass_artifact_present', boolChip(data.immutable_pass_artifact_present, false)),
    kvRow('first_ibkr_contact_allowed', boolChip(data.first_ibkr_contact_allowed, false)),
    kvRow('connector_enabled', boolChip(data.connector_enabled, false)),
    kvRow('readonly_probe.contract_id', textChip(readonlyProbe.contract_id || '-')),
    kvRow('readonly_probe.source_version', textChip(readonlyProbe.source_version || 0)),
    kvRow('readonly_probe.status', textChip(readonlyProbe.status || 'blocked_no_request_artifact')),
    kvRow('readonly_probe.accepted_for_contact', boolChip(readonlyProbe.accepted_for_contact, false)),
    kvRow('connector_skeleton.surface_id', textChip(connectorSkeleton.surface_id || '-')),
    kvRow('connector_skeleton.accepted', boolChip(connectorSkeleton.accepted, false)),
    kvRow('connector_skeleton.status', textChip(connectorSkeleton.status || 'blocked_source_only')),
    kvRow('stock_live_disabled', boolChip(data.stock_live_disabled, false)),
  ].join('');

  document.getElementById('se-api-allowlist-body').innerHTML = [
    kvRow('contract_id', textChip(apiAllowlist.contract_id || '-')),
    kvRow('source_version', textChip(apiAllowlist.source_version)),
    kvRow('accepted', boolChip(apiAllowlist.accepted, false)),
    kvRow(
      'action_counts',
      '<span class="se-code">' +
        ocEsc(
          'read=' + String(apiAllowlist.read_action_count || 0) +
          ' paper_write=' + String(apiAllowlist.paper_write_action_count || 0) +
          ' denied=' + String(apiAllowlist.denied_action_count || 0)
        ) +
      '</span>'
    ),
    kvRow('ibkr_contact_performed', boolChip(apiAllowlist.ibkr_contact_performed, true)),
    kvRow('secret_content_serialized', boolChip(apiAllowlist.secret_content_serialized, true)),
    kvRow('bybit_live_execution_protected', boolChip(apiAllowlist.bybit_live_execution_protected, false)),
    kvRow('blockers', chipList(apiAllowlist.blockers, 'none')),
  ].join('');

  document.getElementById('se-guard-body').innerHTML = [
    kvRow('ibkr_call_performed', boolChip(data.ibkr_call_performed, true)),
    kvRow('secret_slot_touched', boolChip(data.secret_slot_touched, true)),
    kvRow('order_routed', boolChip(data.order_routed, true)),
    kvRow('bybit_ipc_reused', boolChip(data.bybit_ipc_reused, true)),
    kvRow('readonly_probe.request_artifact_present', boolChip(readonlyProbe.request_artifact_present, true)),
    kvRow('readonly_probe.request_validated', boolChip(readonlyProbe.request_validated, true)),
    kvRow('readonly_probe.ibkr_contact_performed', boolChip(readonlyProbe.ibkr_contact_performed, true)),
    kvRow('readonly_probe.connector_runtime_started', boolChip(readonlyProbe.connector_runtime_started, true)),
    kvRow('readonly_probe.secret_content_serialized', boolChip(readonlyProbe.secret_content_serialized, true)),
    kvRow('readonly_probe.order_routed', boolChip(readonlyProbe.order_routed, true)),
    kvRow('readonly_probe.paper_order_submitted', boolChip(readonlyProbe.paper_order_submitted, true)),
    kvRow('readonly_probe.db_apply_performed', boolChip(readonlyProbe.db_apply_performed, true)),
    kvRow('readonly_probe.evidence_clock_started', boolChip(readonlyProbe.evidence_clock_started, true)),
    kvRow('readonly_probe.bybit_path_reused', boolChip(readonlyProbe.bybit_path_reused, true)),
    kvRow('readonly_probe.live_or_tiny_live_authorized', boolChip(readonlyProbe.live_or_tiny_live_authorized, true)),
    kvRow('readonly_probe.blockers', chipList(readonlyProbe.blockers, 'none')),
    kvRow('connector_skeleton.network_contact_performed', boolChip(connectorSkeleton.network_contact_performed, true)),
    kvRow('connector_skeleton.secret_content_loaded', boolChip(connectorSkeleton.secret_content_loaded, true)),
    kvRow('connector_skeleton.paper_channel_exposed', boolChip(connectorSkeleton.paper_channel_exposed, true)),
    kvRow('connector_skeleton.live_channel_exposed', boolChip(connectorSkeleton.live_channel_exposed, true)),
    kvRow('connector_skeleton.order_write_method_present', boolChip(connectorSkeleton.order_write_method_present, true)),
    kvRow('connector_skeleton.bybit_path_reused', boolChip(connectorSkeleton.bybit_path_reused, true)),
    kvRow('connector_skeleton.blockers', chipList(connectorSkeleton.blockers, 'none')),
    kvRow('reason', '<span class="se-code">' + ocEsc(data.reason || '-') + '</span>'),
  ].join('');

  const denied = Array.isArray(data.denied_operations) ? data.denied_operations : [];
  const blockers = []
    .concat(source.denial_reasons || [])
    .concat(data.phase2_gate_blockers || [])
    .concat(readonlyProbe.blockers || [])
    .concat(apiAllowlist.blockers || [])
    .concat(data.contract_violations || []);
  setChip('se-denied-count', String(denied.length), denied.length ? 'warn' : 'neutral');
  document.getElementById('se-denied-list').innerHTML = chipList(denied, 'no denied operations');
  document.getElementById('se-blocker-list').innerHTML = chipList(blockers, 'no current blockers');
  setChip('se-updated', new Date().toLocaleTimeString(), data.degraded ? 'warn' : 'good');

  document.getElementById('se-phase2-panel').classList.toggle('se-warn-line', data.first_ibkr_contact_allowed !== true);
  document.getElementById('se-api-allowlist-panel').classList.toggle('se-bad-line', apiAllowlist.accepted !== true);
  document.getElementById('se-guard-panel').classList.toggle('se-bad-line', (data.contract_violations || []).length > 0);
}

function renderDataFoundationStatus(data) {
  const status = data || dataFoundationFallback('api_unavailable');
  const identity = status.instrument_identity || {};
  const reference = status.reference_data_sources || {};
  const state = status.data_foundation_status_state || 'blocked';
  const dataBlockers = []
    .concat(identity.blockers || [])
    .concat(reference.blockers || [])
    .concat(status.phase2_gate_blockers || [])
    .concat(status.contract_violations || []);
  document.getElementById('se-data-foundation-state').innerHTML = textChip(state);
  document.getElementById('se-data-foundation-sub').textContent =
    identity.accepted && reference.accepted ? 'source_ready' : 'identity/reference blocked';
  setChip('se-data-foundation-status', state, toneFor(state));
  document.getElementById('se-data-foundation-body').innerHTML = [
    kvRow('phase', textChip(status.phase || '-')),
    kvRow('environment', textChip(status.environment || 'paper')),
    kvRow('phase2_started', boolChip(status.phase2_started, true)),
    kvRow('phase3_started', boolChip(status.phase3_started, true)),
    kvRow('contract_details_request_started', boolChip(status.contract_details_request_started, true)),
    kvRow('reference_data_collection_started', boolChip(status.reference_data_collection_started, true)),
    kvRow('instrument.accepted', boolChip(identity.accepted, false)),
    kvRow('instrument.expected_contract_id', textChip(identity.expected_contract_id || '-')),
    kvRow('instrument.contract_id', textChip(identity.contract_id || '-')),
    kvRow('instrument.source_version', textChip(identity.source_version)),
    kvRow(
      'instrument.identity',
      '<span class="se-code">' +
        ocEsc(
          'symbol=' + String(identity.symbol || '-') +
          ' kind=' + String(identity.instrument_kind || '-') +
          ' venue=' + String(identity.listing_venue || '-') +
          ' primary=' + String(identity.primary_exchange || '-')
        ) +
      '</span>'
    ),
    kvRow(
      'instrument.tradeability',
      '<span class="se-code">' +
        ocEsc(
          'ccy=' + String(identity.currency || '-') +
          ' tradability=' + String(identity.tradability_status || '-') +
          ' priips=' + String(identity.priips_kid_status || '-')
        ) +
      '</span>'
    ),
    kvRow('instrument.fractional_policy_recorded', boolChip(identity.fractional_policy_recorded, false)),
    kvRow('instrument.point_in_time_asof_ms', textChip(identity.point_in_time_asof_ms || 0)),
    kvRow('instrument.market_calendar_id_present', boolChip(identity.market_calendar_id_present, false)),
    kvRow('instrument.market_calendar_hash_present', boolChip(identity.market_calendar_hash_present, false)),
    kvRow('instrument.contract_details_hash_present', boolChip(identity.broker_contract_details_hash_present, false)),
    kvRow('instrument.identity_hash_present', boolChip(identity.instrument_identity_hash_present, false)),
    kvRow('instrument.corporate_action_hash_present', boolChip(identity.corporate_action_adjustment_version_hash_present, false)),
    kvRow('instrument.source_artifact_hash_present', boolChip(identity.source_artifact_hash_present, false)),
    kvRow('instrument.bybit_live_execution_unchanged', boolChip(identity.bybit_live_execution_unchanged, false)),
    kvRow('instrument.ibkr_live_denied', boolChip(identity.ibkr_live_denied, false)),
    kvRow('instrument.margin_short_denied', boolChip(identity.margin_short_denied, false)),
    kvRow('instrument.options_cfd_denied', boolChip(identity.options_cfd_denied, false)),
    kvRow('instrument.ibkr_contact_performed', boolChip(identity.ibkr_contact_performed, true)),
    kvRow('instrument.secret_content_serialized', boolChip(identity.secret_content_serialized, true)),
    kvRow('reference.accepted', boolChip(reference.accepted, false)),
    kvRow('reference.expected_contract_id', textChip(reference.expected_contract_id || '-')),
    kvRow('reference.contract_id', textChip(reference.contract_id || '-')),
    kvRow('reference.source_version', textChip(reference.source_version)),
    kvRow('reference.frozen_for_evidence_clock', boolChip(reference.frozen_for_evidence_clock, false)),
    kvRow(
      'reference.sources',
      '<span class="se-code">' +
        ocEsc(
          'corp=' + String(reference.corporate_action_source_name || '-') +
          ' fx=' + String(reference.fx_rate_source_name || '-') +
          ' fee=' + String(reference.fee_schedule_source_name || '-')
        ) +
      '</span>'
    ),
    kvRow(
      'reference.asof_ms',
      '<span class="se-code">' +
        ocEsc(
          'corp=' + String(reference.corporate_action_asof_ms || 0) +
          ' fx=' + String(reference.fx_rate_asof_ms || 0) +
          ' fee=' + String(reference.fee_schedule_asof_ms || 0)
        ) +
      '</span>'
    ),
    kvRow(
      'reference.currencies',
      '<span class="se-code">' +
        ocEsc(
          'base=' + String(reference.base_currency || '-') +
          ' quote=' + String(reference.quote_currency || '-')
        ) +
      '</span>'
    ),
    kvRow('reference.corporate_action_raw_hash_present', boolChip(reference.corporate_action_raw_hash_present, false)),
    kvRow('reference.corporate_action_policy_hash_present', boolChip(reference.corporate_action_policy_hash_present, false)),
    kvRow('reference.dividend_treatment_hash_present', boolChip(reference.dividend_treatment_hash_present, false)),
    kvRow('reference.fx_rate_snapshot_hash_present', boolChip(reference.fx_rate_snapshot_hash_present, false)),
    kvRow('reference.fx_drag_model_hash_present', boolChip(reference.fx_drag_model_hash_present, false)),
    kvRow('reference.commission_schedule_hash_present', boolChip(reference.commission_schedule_hash_present, false)),
    kvRow('reference.exchange_regulatory_fee_hash_present', boolChip(reference.exchange_regulatory_fee_hash_present, false)),
    kvRow('reference.tax_ftt_placeholder_hash_present', boolChip(reference.tax_ftt_placeholder_hash_present, false)),
    kvRow('reference.withholding_tax_treatment_hash_present', boolChip(reference.withholding_tax_treatment_hash_present, false)),
    kvRow('reference.source_artifact_hash_present', boolChip(reference.source_artifact_hash_present, false)),
    kvRow('reference.bybit_live_execution_unchanged', boolChip(reference.bybit_live_execution_unchanged, false)),
    kvRow('reference.ibkr_contact_performed', boolChip(reference.ibkr_contact_performed, true)),
    kvRow('reference.connector_runtime_started', boolChip(reference.connector_runtime_started, true)),
    kvRow('reference.secret_content_serialized', boolChip(reference.secret_content_serialized, true)),
    kvRow('reference.live_or_tiny_live_authorized', boolChip(reference.live_or_tiny_live_authorized, true)),
    kvRow('collector_started', boolChip(status.collector_started, true)),
    kvRow('market_data_ingestion_started', boolChip(status.market_data_ingestion_started, true)),
    kvRow('connector_runtime_started', boolChip(status.connector_runtime_started, true)),
    kvRow('db_apply_performed', boolChip(status.db_apply_performed, true)),
    kvRow('evidence_clock_started', boolChip(status.evidence_clock_started, true)),
    kvRow('scorecard_writer_started', boolChip(status.scorecard_writer_started, true)),
    kvRow('blockers', chipList(dataBlockers, 'none')),
    kvRow('reason', '<span class="se-code">' + ocEsc(status.reason || '-') + '</span>'),
  ].join('');
  document.getElementById('se-data-foundation-panel').classList.toggle(
    'se-bad-line',
    (status.contract_violations || []).length > 0
  );
}

function renderPolicyStatus(data) {
  const status = data || policyFallback('api_unavailable');
  const risk = status.risk_policy || {};
  const registry = status.broker_capability_registry || {};
  const state = status.policy_status_state || 'blocked';
  const blockers = []
    .concat(risk.blockers || [])
    .concat(registry.blockers || [])
    .concat(status.phase2_gate_blockers || [])
    .concat(status.contract_violations || []);
  document.getElementById('se-policy-state').innerHTML = textChip(state);
  document.getElementById('se-policy-sub').textContent =
    risk.accepted && registry.accepted ? 'source_ready' : 'risk/capability blocked';
  setChip('se-policy-status', state, toneFor(state));
  document.getElementById('se-policy-body').innerHTML = [
    kvRow('phase', textChip(status.phase || '-')),
    kvRow('environment', textChip(status.environment || 'paper')),
    kvRow('phase2_started', boolChip(status.phase2_started, true)),
    kvRow('phase3_started', boolChip(status.phase3_started, true)),
    kvRow('risk_runtime_started', boolChip(status.risk_runtime_started, true)),
    kvRow('paper_order_rehearsal_started', boolChip(status.paper_order_rehearsal_started, true)),
    kvRow('paper_order_submitted', boolChip(status.paper_order_submitted, true)),
    kvRow('risk.expected_contract_id', textChip(risk.expected_contract_id || '-')),
    kvRow('risk.contract_id', textChip(risk.contract_id || '-')),
    kvRow('risk.source_version', textChip(risk.source_version)),
    kvRow('risk.config_version', textChip(risk.config_version)),
    kvRow('risk.accepted', boolChip(risk.accepted, false)),
    kvRow('risk.enabled', boolChip(risk.enabled, true)),
    kvRow('risk.shadow_only', boolChip(risk.shadow_only, false)),
    kvRow(
      'risk.notional_caps',
      '<span class="se-code">' +
        ocEsc(
          'order=' + String(risk.max_order_notional_usd || 0) +
          ' position=' + String(risk.max_position_notional_usd || 0) +
          ' daily=' + String(risk.max_daily_notional_usd || 0)
        ) +
      '</span>'
    ),
    kvRow(
      'risk.open_caps',
      '<span class="se-code">' +
        ocEsc(
          'orders=' + String(risk.max_open_orders || 0) +
          ' positions=' + String(risk.max_open_positions || 0)
        ) +
      '</span>'
    ),
    kvRow('risk.allow_fractional_shares', boolChip(risk.allow_fractional_shares, false)),
    kvRow('risk.allow_margin', boolChip(risk.allow_margin, true)),
    kvRow('risk.allow_short', boolChip(risk.allow_short, true)),
    kvRow('risk.allow_options', boolChip(risk.allow_options, true)),
    kvRow('risk.allow_cfd', boolChip(risk.allow_cfd, true)),
    kvRow('risk.allow_transfer', boolChip(risk.allow_transfer, true)),
    kvRow('risk.allow_live', boolChip(risk.allow_live, true)),
    kvRow(
      'risk.instrument_kinds',
      '<span class="se-code">' +
        ocEsc(
          'allowed=' + String(risk.allowed_kind_count || 0) +
          ' denied=' + String(risk.denied_kind_count || 0)
        ) +
      '</span>'
    ),
    kvRow('risk.requires_frozen_universe_hash', boolChip(risk.requires_frozen_universe_hash, false)),
    kvRow('risk.requires_instrument_identity_hash', boolChip(risk.requires_instrument_identity_hash, false)),
    kvRow('risk.requires_market_session', boolChip(risk.requires_market_session, false)),
    kvRow('risk.cost_model_required_before_shadow_fill', boolChip(risk.cost_model_required_before_shadow_fill, false)),
    kvRow('risk.cost_model_required_before_scorecard', boolChip(risk.cost_model_required_before_scorecard, false)),
    kvRow('risk.commission_schedule_required', boolChip(risk.commission_schedule_required, false)),
    kvRow('risk.spread_estimate_required', boolChip(risk.spread_estimate_required, false)),
    kvRow('risk.slippage_estimate_required', boolChip(risk.slippage_estimate_required, false)),
    kvRow('risk.fx_drag_required', boolChip(risk.fx_drag_required, false)),
    kvRow('risk.conservative_fill_penalty_required', boolChip(risk.conservative_fill_penalty_required, false)),
    kvRow('risk.rust_authority_required', boolChip(risk.rust_authority_required, false)),
    kvRow('risk.session_attestation_required', boolChip(risk.session_attestation_required, false)),
    kvRow('risk.decision_lease_required', boolChip(risk.decision_lease_required, false)),
    kvRow('risk.guardian_required', boolChip(risk.guardian_required, false)),
    kvRow('risk.idempotency_key_required', boolChip(risk.idempotency_key_required, false)),
    kvRow('risk.broker_reconciliation_required', boolChip(risk.broker_reconciliation_required, false)),
    kvRow('risk.bybit_live_execution_unchanged', boolChip(risk.bybit_live_execution_unchanged, false)),
    kvRow('risk.ibkr_contact_performed', boolChip(risk.ibkr_contact_performed, true)),
    kvRow('risk.connector_runtime_started', boolChip(risk.connector_runtime_started, true)),
    kvRow('risk.secret_content_serialized', boolChip(risk.secret_content_serialized, true)),
    kvRow('registry.expected_registry_id', textChip(registry.expected_registry_id || '-')),
    kvRow('registry.registry_id', textChip(registry.registry_id || '-')),
    kvRow('registry.source_version', textChip(registry.source_version)),
    kvRow('registry.accepted', boolChip(registry.accepted, false)),
    kvRow(
      'registry.lane_scoped_ipc_contract_id',
      textChip(registry.lane_scoped_ipc_contract_id || '-')
    ),
    kvRow(
      'registry.readonly_probe_request_contract_id',
      textChip(registry.readonly_probe_request_contract_id || '-')
    ),
    kvRow(
      'registry.read_rows_require_lane_scoped_ipc',
      boolChip(registry.read_rows_require_lane_scoped_ipc, false)
    ),
    kvRow(
      'registry.read_rows_require_readonly_probe_request',
      boolChip(registry.read_rows_require_readonly_probe_request, false)
    ),
    kvRow(
      'registry.counts',
      '<span class="se-code">' +
        ocEsc(
          'ops=' + String(registry.operation_count || 0) +
          ' audit=' + String(registry.required_audit_field_count || 0) +
          ' read=' + String(registry.read_operation_count || 0) +
          ' paper=' + String(registry.paper_operation_count || 0) +
          ' denied=' + String(registry.denied_operation_count || 0)
        ) +
      '</span>'
    ),
    kvRow('registry.bybit_live_execution_unchanged', boolChip(registry.bybit_live_execution_unchanged, false)),
    kvRow('registry.python_broker_write_authority_denied', boolChip(registry.python_broker_write_authority_denied, false)),
    kvRow('registry.ibkr_live_denied', boolChip(registry.ibkr_live_denied, false)),
    kvRow('registry.cfd_margin_reserved_denied', boolChip(registry.cfd_margin_reserved_denied, false)),
    kvRow('registry.first_ibkr_contact_performed', boolChip(registry.first_ibkr_contact_performed, true)),
    kvRow('registry.secret_content_serialized', boolChip(registry.secret_content_serialized, true)),
    kvRow('connector_runtime_started', boolChip(status.connector_runtime_started, true)),
    kvRow('db_apply_performed', boolChip(status.db_apply_performed, true)),
    kvRow('evidence_clock_started', boolChip(status.evidence_clock_started, true)),
    kvRow('scorecard_writer_started', boolChip(status.scorecard_writer_started, true)),
    kvRow('blockers', chipList(blockers, 'none')),
    kvRow('reason', '<span class="se-code">' + ocEsc(status.reason || '-') + '</span>'),
  ].join('');
  document.getElementById('se-policy-panel').classList.toggle(
    'se-bad-line',
    (status.contract_violations || []).length > 0
  );
}

function renderAuthorizationStatus(data) {
  const status = data || authorizationFallback('api_unavailable');
  const matrix = status.authorization_matrix || {};
  const flags = status.feature_flags || {};
  const secret = status.secret_slot_contract || {};
  const artifact = status.phase2_gate_artifact || {};
  const session = status.session_attestation || {};
  const envelope = status.authorization_envelope || {};
  const state = status.authorization_status_state || 'blocked';
  const blockers = []
    .concat(matrix.blockers || [])
    .concat(secret.blockers || [])
    .concat(artifact.blockers || [])
    .concat(session.blockers || [])
    .concat(status.phase2_gate_blockers || [])
    .concat(status.contract_violations || []);
  document.getElementById('se-authorization-state').innerHTML = textChip(state);
  document.getElementById('se-authorization-sub').textContent =
    matrix.request_allowed ? 'paper authority claimed' : 'authority blocked';
  setChip('se-authorization-status', state, toneFor(state));
  document.getElementById('se-authorization-body').innerHTML = [
    kvRow('phase', textChip(status.phase || '-')),
    kvRow('environment', textChip(status.environment || 'paper')),
    kvRow('phase2_started', boolChip(status.phase2_started, true)),
    kvRow('phase3_started', boolChip(status.phase3_started, true)),
    kvRow('paper_order_authority_present', boolChip(status.paper_order_authority_present, true)),
    kvRow('scoped_authorization_present', boolChip(status.scoped_authorization_present, true)),
    kvRow('decision_lease_valid', boolChip(status.decision_lease_valid, true)),
    kvRow('guardian_allows', boolChip(status.guardian_allows, true)),
    kvRow('matrix.expected_contract_id', textChip(matrix.expected_contract_id || '-')),
    kvRow('matrix.contract_id', textChip(matrix.contract_id || '-')),
    kvRow('matrix.source_version', textChip(matrix.source_version)),
    kvRow('matrix.request_allowed', boolChip(matrix.request_allowed, true)),
    kvRow('matrix.effective_scope', textChip(matrix.effective_authority_scope || 'denied')),
    kvRow('matrix.gui_override_denied', boolChip(matrix.gui_lane_state_override_denied, false)),
    kvRow('matrix.server_rust_authoritative', boolChip(matrix.server_rust_matrix_authoritative, false)),
    kvRow(
      'matrix.request',
      '<span class="se-code">' +
        ocEsc(
          'lane=' + String(matrix.request_asset_lane || '-') +
          ' broker=' + String(matrix.request_broker || '-') +
          ' env=' + String(matrix.request_environment || '-') +
          ' kind=' + String(matrix.request_instrument_kind || '-') +
          ' op=' + String(matrix.request_operation || '-')
        ) +
      '</span>'
    ),
    kvRow(
      'flags',
      '<span class="se-code">' +
        ocEsc(
          'lane=' + String(flags.stock_etf_lane_enabled === true) +
          ' readonly=' + String(flags.ibkr_readonly_enabled === true) +
          ' paper=' + String(flags.ibkr_paper_enabled === true) +
          ' default=' + String(flags.asset_lane_default || '-') +
          ' shadow_only=' + String(flags.stock_etf_shadow_only !== false)
        ) +
      '</span>'
    ),
    kvRow('secret.expected_contract_id', textChip(secret.expected_contract_id || '-')),
    kvRow('secret.contract_id', textChip(secret.contract_id || '-')),
    kvRow('secret.accepted', boolChip(secret.accepted, false)),
    kvRow('secret.contract_present', boolChip(secret.contract_present, false)),
    kvRow('secret.readonly_slot_posture', textChip(secret.readonly_slot_posture || 'unknown')),
    kvRow('secret.paper_slot_posture', textChip(secret.paper_slot_posture || 'unknown')),
    kvRow('secret.live_slot_posture', textChip(secret.live_slot_posture || 'unknown')),
    kvRow('secret.owner_only_permissions', boolChip(secret.owner_only_permissions, false)),
    kvRow('secret.env_fallback_denied', boolChip(secret.env_var_credential_fallback_denied, false)),
    kvRow('secret.live_absent_or_empty', boolChip(secret.live_secret_absent_or_empty, false)),
    kvRow('secret.fingerprint_present', boolChip(secret.secret_slot_fingerprint_present, false)),
    kvRow('secret.account_hash_present', boolChip(secret.account_fingerprint_hash_present, false)),
    kvRow('secret.secret_content_serialized', boolChip(secret.secret_content_serialized, true)),
    kvRow('secret.account_id_serialized', boolChip(secret.account_id_serialized, true)),
    kvRow('phase2_artifact.expected_contract_id', textChip(artifact.expected_contract_id || '-')),
    kvRow('phase2_artifact.contract_id', textChip(artifact.contract_id || '-')),
    kvRow('phase2_artifact.contact_allowed', boolChip(artifact.ibkr_contact_allowed, true)),
    kvRow('phase2_artifact.sealed', boolChip(artifact.sealed, false)),
    kvRow('phase2_artifact.raw_hash_present', boolChip(artifact.raw_artifact_hash_present, false)),
    kvRow('phase2_artifact.redacted_hash_present', boolChip(artifact.redacted_summary_hash_present, false)),
    kvRow('session.expected_contract_id', textChip(session.expected_contract_id || '-')),
    kvRow('session.contract_id', textChip(session.contract_id || '-')),
    kvRow('session.status', textChip(session.status || 'BLOCKED')),
    kvRow('session.attestation_accepted', boolChip(session.attestation_accepted, true)),
    kvRow('session.environment', textChip(session.environment || 'read_only')),
    kvRow('session.account_live', boolChip(session.account_fingerprint_is_live, true)),
    kvRow('session.raw_hash_present', boolChip(session.raw_artifact_hash_present, false)),
    kvRow('envelope.permission_scope', textChip(envelope.permission_scope || 'denied')),
    kvRow('envelope.secret_fingerprint_present', boolChip(envelope.secret_slot_fingerprint_present, false)),
    kvRow('envelope.account_hash_present', boolChip(envelope.account_fingerprint_hash_present, false)),
    kvRow('envelope.risk_hash_present', boolChip(envelope.risk_config_hash_present, false)),
    kvRow('envelope.expires_at_ms', textChip(envelope.expires_at_ms || 0)),
    kvRow('paper_order_submitted', boolChip(status.paper_order_submitted, true)),
    kvRow('connector_runtime_started', boolChip(status.connector_runtime_started, true)),
    kvRow('db_apply_performed', boolChip(status.db_apply_performed, true)),
    kvRow('blockers', chipList(blockers, 'none')),
    kvRow('reason', '<span class="se-code">' + ocEsc(status.reason || '-') + '</span>'),
  ].join('');
  document.getElementById('se-authorization-panel').classList.toggle(
    'se-bad-line',
    (status.contract_violations || []).length > 0
  );
}

function renderAccountStatus(data) {
  const status = data || accountFallback('api_unavailable');
  const account = status.account_snapshot || {};
  const session = status.session_attestation || {};
  const policy = status.paper_attestation_policy || {};
  const state = status.account_status_state || 'blocked';
  const blockers = []
    .concat(status.phase2_gate_blockers || [])
    .concat(account.blockers || [])
    .concat(session.blockers || [])
    .concat(policy.blockers || [])
    .concat(status.contract_violations || []);
  document.getElementById('se-account-state').innerHTML = textChip(state);
  document.getElementById('se-account-sub').textContent =
    session.status || (status.degraded ? 'degraded' : 'BLOCKED');
  setChip('se-account-status', state, toneFor(state));
  document.getElementById('se-account-body').innerHTML = [
    kvRow('phase', textChip(status.phase || '-')),
    kvRow('environment', textChip(status.environment || 'paper_readonly')),
    kvRow('phase2_started', boolChip(status.phase2_started, true)),
    kvRow('first_ibkr_contact_allowed', boolChip(status.first_ibkr_contact_allowed, true)),
    kvRow('connector_enabled', boolChip(status.connector_enabled, true)),
    kvRow('readonly_snapshot_started', boolChip(status.readonly_account_snapshot_started, true)),
    kvRow('paper_snapshot_started', boolChip(status.paper_account_snapshot_started, true)),
    kvRow('account_snapshot_present', boolChip(status.account_snapshot_present, true)),
    kvRow('portfolio_positions_present', boolChip(status.portfolio_positions_snapshot_present, true)),
    kvRow('cash_ledger_present', boolChip(status.cash_ledger_present, true)),
    kvRow('paper_attestation_present', boolChip(status.paper_account_attestation_present, true)),
    kvRow('session_attestation_present', boolChip(status.session_attestation_present, true)),
    kvRow('connector_runtime_started', boolChip(status.connector_runtime_started, true)),
    kvRow('gateway_socket_open', boolChip(status.gateway_socket_open, true)),
    kvRow('account.contract_id', textChip(account.contract_id || '-')),
    kvRow('account.expected_contract_id', textChip(account.expected_contract_id || '-')),
    kvRow('account.accepted', boolChip(account.accepted, true)),
    kvRow('account.fingerprint_hash_present', boolChip(account.account_fingerprint_hash_present, true)),
    kvRow('account.snapshot_hash_present', boolChip(account.account_snapshot_hash_present, true)),
    kvRow('account.positions_hash_present', boolChip(account.portfolio_positions_hash_present, true)),
    kvRow(
      'account.balances',
      '<span class="se-code">' +
        ocEsc(
          'ccy=' + String(account.currency || '-') +
          ' cash=' + String(account.cash_balance_minor_units || 0) +
          ' buying_power=' + String(account.buying_power_minor_units || 0)
        ) +
      '</span>'
    ),
    kvRow('account.as_of_ms', textChip(account.as_of_ms || 0)),
    kvRow('account.source_report_hash_present', boolChip(account.source_report_hash_present, true)),
    kvRow('session.contract_id', textChip(session.contract_id || '-')),
    kvRow('session.expected_contract_id', textChip(session.expected_contract_id || '-')),
    kvRow('session.status', textChip(session.status || 'BLOCKED')),
    kvRow('session.accepted', boolChip(session.accepted, true)),
    kvRow('session.environment', textChip(session.environment || 'read_only')),
    kvRow('session.host', textChip(session.host || '-')),
    kvRow('session.port', textChip(session.port || 0)),
    kvRow('session.gateway_mode', textChip(session.gateway_mode || 'unknown')),
    kvRow('session.fingerprint_present', boolChip(session.account_fingerprint_present, true)),
    kvRow('session.fingerprint_is_live', boolChip(session.account_fingerprint_is_live, true)),
    kvRow('session.process_identity_present', boolChip(session.process_identity_present, true)),
    kvRow('session.secret_fingerprint_present', boolChip(session.secret_slot_fingerprint_present, true)),
    kvRow('session.api_server_version_present', boolChip(session.api_server_version_present, true)),
    kvRow('session.raw_artifact_hash_present', boolChip(session.raw_artifact_hash_present, true)),
    kvRow('policy.contract_id', textChip(policy.contract_id || '-')),
    kvRow('policy.expected_contract_id', textChip(policy.expected_contract_id || '-')),
    kvRow('policy.accepted', boolChip(policy.accepted, false)),
    kvRow('policy.paper_environment_only', boolChip(policy.paper_environment_only, false)),
    kvRow('policy.live_account_denied', boolChip(policy.live_account_fingerprint_denied, false)),
    kvRow('policy.margin_short_options_cfd_denied', boolChip(policy.margin_short_options_cfd_denied, false)),
    kvRow('ibkr_call_performed', boolChip(status.ibkr_call_performed, true)),
    kvRow('secret_slot_touched', boolChip(status.secret_slot_touched, true)),
    kvRow('order_routed', boolChip(status.order_routed, true)),
    kvRow('bybit_ipc_reused', boolChip(status.bybit_ipc_reused, true)),
    kvRow('db_apply_performed', boolChip(status.db_apply_performed, true)),
    kvRow('blockers', chipList(blockers, 'none')),
    kvRow('reason', '<span class="se-code">' + ocEsc(status.reason || '-') + '</span>'),
  ].join('');
  document.getElementById('se-account-panel').classList.toggle(
    'se-bad-line',
    (status.contract_violations || []).length > 0
  );
}

function renderEvidenceStatus(data) {
  const evidence = data || evidenceFallback('api_unavailable');
  const marketData = evidence.market_data_provenance || {};
  const clock = evidence.evidence_clock || {};
  const frozen = evidence.frozen_inputs || {};
  const dq = evidence.dq_manifest || {};
  const scorecard = evidence.scorecard || {};
  const evidenceBlockers = []
    .concat(marketData.blockers || [])
    .concat(clock.blockers || [])
    .concat(frozen.blockers || [])
    .concat(dq.shape_blockers || [])
    .concat(evidence.contract_violations || []);
  const state = evidence.evidence_status_state || 'blocked';
  document.getElementById('se-evidence-state').innerHTML = textChip(state);
  document.getElementById('se-evidence-sub').textContent =
    clock.status || (evidence.degraded ? 'degraded' : 'NOT_STARTED');
  setChip('se-evidence-status', state, toneFor(state));
  document.getElementById('se-evidence-body').innerHTML = [
    kvRow('phase', textChip(evidence.phase || '-')),
    kvRow('phase3_started', boolChip(evidence.phase3_started, true)),
    kvRow('market_data_provenance.accepted', boolChip(marketData.accepted, false)),
    kvRow('market_data_provenance.ibkr_contact_performed', boolChip(marketData.ibkr_contact_performed, true)),
    kvRow('market_data_provenance.connector_runtime_started', boolChip(marketData.connector_runtime_started, true)),
    kvRow('evidence_clock.status', textChip(clock.status || 'NOT_STARTED')),
    kvRow('evidence_clock.accepted', boolChip(clock.accepted, false)),
    kvRow('evidence_clock.started', boolChip(evidence.evidence_clock_started, true)),
    kvRow('scorecard.writer_started', boolChip(evidence.scorecard_writer_started, true)),
    kvRow('scorecard.db_apply_performed', boolChip(evidence.db_apply_performed, true)),
    kvRow('frozen_inputs.accepted', boolChip(frozen.accepted, false)),
    kvRow('frozen_inputs.gui_evidence_view_available', boolChip(frozen.gui_evidence_view_available, false)),
    kvRow('dq.shape_accepted', boolChip(dq.shape_accepted, false)),
    kvRow(
      'dq.coverage_bps',
      '<span class="se-code">' +
        ocEsc(
          'calendar=' + String(dq.calendar_aware_coverage_bps || 0) +
          ' symbol=' + String(dq.symbol_completeness_bps || 0)
        ) +
      '</span>'
    ),
    kvRow('dq.latency_dq_passed', boolChip(dq.latency_dq_passed, false)),
    kvRow('dq.market_data_provenance_accepted', boolChip(dq.market_data_provenance_accepted, false)),
    kvRow('scorecard.daily_regeneration_passed', boolChip(scorecard.daily_scorecard_regeneration_passed, false)),
    kvRow('blockers', chipList(evidenceBlockers, 'none')),
    kvRow('reason', '<span class="se-code">' + ocEsc(evidence.reason || '-') + '</span>'),
  ].join('');
  document.getElementById('se-evidence-panel').classList.toggle(
    'se-bad-line',
    (evidence.contract_violations || []).length > 0
  );
}

function renderUniverseStatus(data) {
  const status = data || universeFallback('api_unavailable');
  const universe = status.universe || {};
  const state = status.universe_status_state || 'blocked';
  const universeBlockers = []
    .concat(universe.blockers || [])
    .concat(status.phase2_gate_blockers || [])
    .concat(status.contract_violations || []);
  document.getElementById('se-universe-state').innerHTML = textChip(state);
  document.getElementById('se-universe-sub').textContent =
    universe.accepted ? (universe.universe_id || 'source_ready') : 'PIT universe blocked';
  setChip('se-universe-status', state, toneFor(state));
  document.getElementById('se-universe-body').innerHTML = [
    kvRow('phase', textChip(status.phase || '-')),
    kvRow('phase3_started', boolChip(status.phase3_started, true)),
    kvRow('contract.accepted', boolChip(universe.accepted, false)),
    kvRow('contract_id', textChip(universe.contract_id || '-')),
    kvRow('source_version', textChip(universe.source_version)),
    kvRow('universe_id', textChip(universe.universe_id || '-')),
    kvRow('universe_version', textChip(universe.universe_version || '-')),
    kvRow('universe_hash_present', boolChip(universe.universe_hash_present, false)),
    kvRow(
      'constituents',
      '<span class="se-code">' +
        ocEsc(
          'count=' + String(universe.constituent_count || 0) +
          ' max=' + String(universe.max_constituents || 0)
        ) +
      '</span>'
    ),
    kvRow('frozen_for_evidence_clock', boolChip(universe.frozen_for_evidence_clock, false)),
    kvRow('survivorship_controls', boolChip(universe.survivorship_bias_controls_present, false)),
    kvRow('ibkr_contact_performed', boolChip(universe.ibkr_contact_performed, true)),
    kvRow('secret_content_serialized', boolChip(universe.secret_content_serialized, true)),
    kvRow('collector_started', boolChip(status.collector_started, true)),
    kvRow('market_data_ingestion_started', boolChip(status.market_data_ingestion_started, true)),
    kvRow('db_apply_performed', boolChip(status.db_apply_performed, true)),
    kvRow('blockers', chipList(universeBlockers, 'none')),
    kvRow('reason', '<span class="se-code">' + ocEsc(status.reason || '-') + '</span>'),
  ].join('');
  document.getElementById('se-universe-panel').classList.toggle(
    'se-bad-line',
    (status.contract_violations || []).length > 0
  );
}

function renderShadowStatus(data) {
  const status = data || shadowFallback('api_unavailable');
  const shadow = status.shadow_fill_model || {};
  const strategy = status.strategy_hypothesis || {};
  const state = status.shadow_status_state || 'blocked';
  const shadowBlockers = []
    .concat(shadow.blockers || [])
    .concat(strategy.blockers || [])
    .concat(status.phase2_gate_blockers || [])
    .concat(status.contract_violations || []);
  document.getElementById('se-shadow-state').innerHTML = textChip(state);
  document.getElementById('se-shadow-sub').textContent =
    strategy.accepted ? (strategy.hypothesis_id || 'source_ready') : 'shadow model blocked';
  setChip('se-shadow-status', state, toneFor(state));
  document.getElementById('se-shadow-body').innerHTML = [
    kvRow('phase', textChip(status.phase || '-')),
    kvRow('phase3_started', boolChip(status.phase3_started, true)),
    kvRow('shadow_fill_model.accepted', boolChip(shadow.accepted, false)),
    kvRow('shadow_fill_model.contract_id', textChip(shadow.contract_id || '-')),
    kvRow('shadow_fill_model.source_version', textChip(shadow.source_version)),
    kvRow('shadow_fill_model.synthetic_shadow', boolChip(shadow.synthetic_shadow, false)),
    kvRow('broker_paper_fill_linked', boolChip(shadow.broker_paper_fill_linked, true)),
    kvRow('live_fill_linked', boolChip(shadow.live_fill_linked, true)),
    kvRow(
      'shadow_cost_bps',
      '<span class="se-code">' +
        ocEsc(
          'spread=' + String(shadow.spread_bps || 0) +
          ' slip=' + String(shadow.slippage_bps || 0) +
          ' cost=' + String(shadow.cost_bps || 0)
        ) +
      '</span>'
    ),
    kvRow('strategy.accepted', boolChip(strategy.accepted, false)),
    kvRow('strategy.contract_id', textChip(strategy.contract_id || '-')),
    kvRow('strategy_family', textChip(strategy.strategy_family || 'unknown_denied')),
    kvRow('primary_timeframe', textChip(strategy.primary_timeframe || 'unknown_denied')),
    kvRow('instrument_scope', textChip(strategy.instrument_scope || 'unknown_denied')),
    kvRow('paper_shadow_only', boolChip(strategy.paper_shadow_only, false)),
    kvRow('profitability_claimed', boolChip(strategy.profitability_claimed, true)),
    kvRow('live_or_tiny_live_authority_claimed', boolChip(strategy.live_or_tiny_live_authority_claimed, true)),
    kvRow('shadow_collector_started', boolChip(status.shadow_collector_started, true)),
    kvRow('shadow_signal_emitted', boolChip(status.shadow_signal_emitted, true)),
    kvRow('shadow_fill_generated', boolChip(status.shadow_fill_generated, true)),
    kvRow('scorecard_writer_started', boolChip(status.scorecard_writer_started, true)),
    kvRow('db_apply_performed', boolChip(status.db_apply_performed, true)),
    kvRow('blockers', chipList(shadowBlockers, 'none')),
    kvRow('reason', '<span class="se-code">' + ocEsc(status.reason || '-') + '</span>'),
  ].join('');
  document.getElementById('se-shadow-panel').classList.toggle(
    'se-bad-line',
    (status.contract_violations || []).length > 0
  );
}

function renderPaperStatus(data) {
  const status = data || paperFallback('api_unavailable');
  const lifecycle = status.lifecycle_event || {};
  const reconstructability = status.reconstructability || {};
  const state = status.paper_status_state || 'blocked';
  const paperBlockers = []
    .concat(lifecycle.blockers || [])
    .concat(status.phase2_gate_blockers || [])
    .concat(status.contract_violations || []);
  document.getElementById('se-paper-lifecycle-state').innerHTML = textChip(state);
  document.getElementById('se-paper-lifecycle-sub').textContent =
    lifecycle.accepted ? 'append-only event ready' : 'paper lifecycle blocked';
  setChip('se-paper-status', state, toneFor(state));
  document.getElementById('se-paper-body').innerHTML = [
    kvRow('phase', textChip(status.phase || '-')),
    kvRow('phase2_started', boolChip(status.phase2_started, true)),
    kvRow('paper_lifecycle_started', boolChip(status.paper_lifecycle_started, true)),
    kvRow('paper_order_submitted', boolChip(status.paper_order_submitted, true)),
    kvRow('paper_fill_imported', boolChip(status.paper_fill_imported, true)),
    kvRow('paper_reconciliation_started', boolChip(status.paper_reconciliation_started, true)),
    kvRow('paper_account_snapshot_present', boolChip(status.paper_account_snapshot_present, true)),
    kvRow('broker_paper_attestation_present', boolChip(status.broker_paper_attestation_present, true)),
    kvRow('lifecycle.accepted', boolChip(lifecycle.accepted, false)),
    kvRow('lifecycle.operation', textChip(lifecycle.operation || 'paper_order_submit')),
    kvRow('lifecycle.previous_state', textChip(lifecycle.previous_state || '-')),
    kvRow('lifecycle.next_state', textChip(lifecycle.next_state || '-')),
    kvRow('lifecycle.allowed', boolChip(lifecycle.allowed, true)),
    kvRow('expected_request_contract_id', textChip(lifecycle.expected_request_contract_id || '-')),
    kvRow('request_contract_id', textChip(lifecycle.request_contract_id || '-')),
    kvRow('event_sequence', '<span class="se-code">' + ocEsc(String(lifecycle.event_sequence || 0)) + '</span>'),
    kvRow('event_sequence_present', boolChip(lifecycle.event_sequence_present, true)),
    kvRow('genesis_event', boolChip(lifecycle.genesis_event, true)),
    kvRow('state_machine_fields_present', boolChip(lifecycle.state_machine_contract_fields_present, false)),
    kvRow('previous_event_hash_present', boolChip(lifecycle.previous_event_hash_present, true)),
    kvRow('event_hash_present', boolChip(lifecycle.event_hash_present, true)),
    kvRow('request_envelope_hash_present', boolChip(lifecycle.request_envelope_hash_present, true)),
    kvRow('stale_state_policy', textChip(lifecycle.stale_state_policy || '-')),
    kvRow('stale_state_policy_present', boolChip(lifecycle.stale_state_policy_present, true)),
    kvRow('broker_order_id_present', boolChip(lifecycle.broker_order_id_present, true)),
    kvRow('execution_id_present', boolChip(lifecycle.execution_id_present, true)),
    kvRow('commission_report_id_present', boolChip(lifecycle.commission_report_id_present, true)),
    kvRow('idempotency_key_present', boolChip(lifecycle.idempotency_key_present, true)),
    kvRow('reconciliation_run_id_present', boolChip(lifecycle.reconciliation_run_id_present, true)),
    kvRow('raw_artifact_hash_present', boolChip(lifecycle.raw_artifact_hash_present, true)),
    kvRow('redacted_summary_hash_present', boolChip(lifecycle.redacted_summary_hash_present, true)),
    kvRow('append_only_event_ready', boolChip(reconstructability.append_only_event_ready, true)),
    kvRow('event_hash_chain_ready', boolChip(reconstructability.event_hash_chain_ready, true)),
    kvRow('request_envelope_linked', boolChip(reconstructability.request_envelope_linked, true)),
    kvRow('reconstructability_stale_policy', boolChip(reconstructability.stale_state_policy_present, true)),
    kvRow('restart_recovery_required', boolChip(reconstructability.restart_recovery_required, true)),
    kvRow('manual_review_required', boolChip(reconstructability.manual_review_required, true)),
    kvRow('db_apply_performed', boolChip(status.db_apply_performed, true)),
    kvRow('blockers', chipList(paperBlockers, 'none')),
    kvRow('reason', '<span class="se-code">' + ocEsc(status.reason || '-') + '</span>'),
  ].join('');
  document.getElementById('se-paper-panel').classList.toggle(
    'se-bad-line',
    (status.contract_violations || []).length > 0
  );
}

function renderScorecardStatus(data) {
  const status = data || scorecardFallback('api_unavailable');
  const derivation = status.scorecard_derivation || {};
  const scorecard = status.scorecard || {};
  const state = status.scorecard_status_state || 'blocked';
  const scorecardBlockers = []
    .concat(derivation.blockers || [])
    .concat(scorecard.blockers || [])
    .concat(status.phase2_gate_blockers || [])
    .concat(status.contract_violations || []);
  document.getElementById('se-scorecard-state').innerHTML = textChip(state);
  document.getElementById('se-scorecard-sub').textContent =
    scorecard.accepted ? (scorecard.verdict_label || 'source_ready') : 'scorecard verdict blocked';
  setChip('se-scorecard-status', state, toneFor(state));
  document.getElementById('se-scorecard-body').innerHTML = [
    kvRow('phase', textChip(status.phase || '-')),
    kvRow('phase3_started', boolChip(status.phase3_started, true)),
    kvRow('derivation.accepted', boolChip(derivation.accepted, false)),
    kvRow('derivation.contract_id', textChip(derivation.contract_id || '-')),
    kvRow('derivation.expected_contract_id', textChip(derivation.expected_contract_id || '-')),
    kvRow('derivation.run_id_present', boolChip(derivation.derivation_run_id_present, false)),
    kvRow('derivation.input_bundle_hash_present', boolChip(derivation.scorecard_input_bundle_hash_present, false)),
    kvRow('derivation.paper_shadow_reconciliation_hash_present', boolChip(derivation.paper_shadow_reconciliation_hash_present, false)),
    kvRow('derivation.verdict_hash_present', boolChip(derivation.scorecard_verdict_hash_present, false)),
    kvRow('derivation.output_artifact_hash_present', boolChip(derivation.output_artifact_hash_present, false)),
    kvRow('derivation.atomic_facts_only', boolChip(derivation.derived_from_atomic_facts_only, false)),
    kvRow('derivation.idempotent_replay_proven', boolChip(derivation.idempotent_replay_proven, false)),
    kvRow('derivation.reconciliation_writer_started', boolChip(derivation.reconciliation_writer_started, true)),
    kvRow('contract.accepted', boolChip(scorecard.accepted, false)),
    kvRow('contract_id', textChip(scorecard.contract_id || '-')),
    kvRow('expected_contract_id', textChip(scorecard.expected_contract_id || '-')),
    kvRow('source_version', textChip(scorecard.source_version)),
    kvRow('verdict_label', textChip(scorecard.verdict_label || 'insufficient_evidence')),
    kvRow('scorecard_input_bundle_hash_present', boolChip(scorecard.scorecard_input_bundle_hash_present, false)),
    kvRow('formula_appendix_hash_present', boolChip(scorecard.formula_appendix_hash_present, false)),
    kvRow('statistical_preregistration_hash_present', boolChip(scorecard.statistical_preregistration_hash_present, false)),
    kvRow('paper_shadow_reconciliation_hash_present', boolChip(scorecard.paper_shadow_reconciliation_hash_present, false)),
    kvRow('scorecard_manifest_hash_present', boolChip(scorecard.scorecard_manifest_hash_present, false)),
    kvRow(
      'sample_window',
      '<span class="se-code">' +
        ocEsc(
          'days=' + String(scorecard.paper_shadow_window_trading_days || 0) +
          ' min_days=' + String(scorecard.min_window_trading_days || 0) +
          ' obs=' + String(scorecard.independent_observation_count || 0) +
          ' min_obs=' + String(scorecard.min_independent_observation_count || 0)
        ) +
      '</span>'
    ),
    kvRow(
      'net_costs_minor_units',
      '<span class="se-code">' +
        ocEsc(
          'gross=' + String(scorecard.gross_pnl_minor_units || 0) +
          ' net=' + String(scorecard.net_pnl_minor_units || 0) +
          ' comm=' + String(scorecard.commission_minor_units || 0) +
          ' spread_slip=' + String(scorecard.spread_slippage_minor_units || 0)
        ) +
      '</span>'
    ),
    kvRow(
      'lcbs_bps',
      '<span class="se-code">' +
        ocEsc(
          'benchmark=' + String(scorecard.benchmark_excess_lcb_bps || 0) +
          ' cost_stress=' + String(scorecard.conservative_cost_stress_lcb_bps || 0)
        ) +
      '</span>'
    ),
    kvRow(
      'paper_shadow_divergence',
      '<span class="se-code">' +
        ocEsc(
          'bps=' + String(scorecard.paper_shadow_divergence_bps || 0) +
          ' max=' + String(scorecard.max_paper_shadow_divergence_bps || 0)
        ) +
      '</span>'
    ),
    kvRow(
      'psr_dsr_bps',
      '<span class="se-code">' +
        ocEsc(
          'psr=' + String(scorecard.psr_bps || 0) +
          ' min_psr=' + String(scorecard.min_psr_bps || 0) +
          ' dsr=' + String(scorecard.dsr_bps || 0) +
          ' min_dsr=' + String(scorecard.min_dsr_bps || 0)
        ) +
      '</span>'
    ),
    kvRow('label.concentration', boolChip(scorecard.concentration_label_passed, false)),
    kvRow('label.regime', boolChip(scorecard.regime_label_passed, false)),
    kvRow('label.breadth', boolChip(scorecard.breadth_label_passed, false)),
    kvRow('label.freshness', boolChip(scorecard.freshness_label_passed, false)),
    kvRow('label.survivorship', boolChip(scorecard.survivorship_label_passed, false)),
    kvRow('label.execution_realism', boolChip(scorecard.execution_realism_label_passed, false)),
    kvRow('review.qc_hash_present', boolChip(scorecard.qc_review_hash_present, false)),
    kvRow('review.mit_hash_present', boolChip(scorecard.mit_review_hash_present, false)),
    kvRow('review.qa_hash_present', boolChip(scorecard.qa_review_hash_present, false)),
    kvRow('scorecard_is_derived_only', boolChip(scorecard.scorecard_is_derived_only, false)),
    kvRow('paper_and_shadow_fills_separate', boolChip(scorecard.paper_and_shadow_fills_separate, false)),
    kvRow('live_fill_claimed', boolChip(scorecard.live_fill_claimed, true)),
    kvRow('bybit_live_execution_unchanged', boolChip(scorecard.bybit_live_execution_unchanged, false)),
    kvRow('sealed', boolChip(scorecard.sealed, false)),
    kvRow('scorecard_writer_started', boolChip(status.scorecard_writer_started, true)),
    kvRow('db_apply_performed', boolChip(status.db_apply_performed, true)),
    kvRow('evidence_clock_started', boolChip(status.evidence_clock_started, true)),
    kvRow('live_or_tiny_live_authorized', boolChip(status.live_or_tiny_live_authorized, true)),
    kvRow('blockers', chipList(scorecardBlockers, 'none')),
    kvRow('reason', '<span class="se-code">' + ocEsc(status.reason || '-') + '</span>'),
  ].join('');
  document.getElementById('se-scorecard-panel').classList.toggle(
    'se-bad-line',
    (status.contract_violations || []).length > 0
  );
}

function renderLaunchStatus(data) {
  const status = data || launchFallback('api_unavailable');
  const release = status.release_packet || {};
  const runbook = status.disable_cleanup_runbook || {};
  const tinyLive = status.tiny_live_adr_eligibility || {};
  const state = status.launch_status_state || 'blocked';
  const launchBlockers = []
    .concat(release.blockers || [])
    .concat(runbook.blockers || [])
    .concat(tinyLive.blockers || [])
    .concat(status.phase2_gate_blockers || [])
    .concat(status.contract_violations || []);
  document.getElementById('se-launch-state').innerHTML = textChip(state);
  document.getElementById('se-launch-sub').textContent =
    release.accepted && runbook.accepted && tinyLive.accepted ? 'release packet accepted' : 'launch blocked';
  setChip('se-launch-status', state, toneFor(state));
  document.getElementById('se-launch-body').innerHTML = [
    kvRow('phase', textChip(status.phase || '-')),
    kvRow('phase3_started', boolChip(status.phase3_started, true)),
    kvRow('phase5_started', boolChip(status.phase5_started, true)),
    kvRow('release.expected_contract_id', textChip(release.expected_contract_id || '-')),
    kvRow('release.packet_id', textChip(release.packet_id || '-')),
    kvRow('release.source_version', textChip(release.source_version)),
    kvRow('release.accepted', boolChip(release.accepted, false)),
    kvRow('release.paper_shadow_window_complete', boolChip(release.paper_shadow_window_complete, false)),
    kvRow('release.engineering_shakedown_complete', boolChip(release.engineering_shakedown_complete, false)),
    kvRow(
      'release.counts',
      '<span class="se-code">' +
        ocEsc(
          'roles=' + String(release.role_report_count || 0) +
          ' manifests=' + String(release.manifest_hash_count || 0) +
          ' screenshots=' + String(release.gui_screenshot_hash_count || 0) +
          ' dq=' + String(release.dq_manifest_hash_count || 0) +
          ' regen=' + String(release.scorecard_regeneration_hash_count || 0)
        ) +
      '</span>'
    ),
    kvRow('release.pg_migrations_declared', boolChip(release.pg_migrations_declared, true)),
    kvRow('release.pg_dry_run_log_hash_present', boolChip(release.pg_dry_run_log_hash_present, false)),
    kvRow('release.pg_double_apply_log_hash_present', boolChip(release.pg_double_apply_log_hash_present, false)),
    kvRow('release.redaction_fixture_hash_present', boolChip(release.redaction_fixture_hash_present, false)),
    kvRow('release.evidence_archive_pointer_present', boolChip(release.evidence_archive_pointer_present, false)),
    kvRow('release.evidence_archive_hash_present', boolChip(release.evidence_archive_hash_present, false)),
    kvRow('release.secret_content_serialized', boolChip(release.secret_content_serialized, true)),
    kvRow('release.ibkr_live_or_tiny_live_authorized', boolChip(release.ibkr_live_or_tiny_live_authorized, true)),
    kvRow('release.sealed', boolChip(release.sealed, false)),
    kvRow('runbook.expected_runbook_id', textChip(runbook.expected_runbook_id || '-')),
    kvRow('runbook.runbook_id', textChip(runbook.runbook_id || '-')),
    kvRow('runbook.source_version', textChip(runbook.source_version)),
    kvRow('runbook.accepted', boolChip(runbook.accepted, false)),
    kvRow('runbook.bybit_live_execution_unchanged', boolChip(runbook.bybit_live_execution_unchanged, false)),
    kvRow(
      'runbook.counts',
      '<span class="se-code">' +
        ocEsc(
          'env_flags=' + String(runbook.env_flag_count || 0) +
          ' proofs=' + String(runbook.proof_count || 0)
        ) +
      '</span>'
    ),
    kvRow('runbook.ibkr_contact_performed', boolChip(runbook.ibkr_contact_performed, true)),
    kvRow('runbook.connector_runtime_started', boolChip(runbook.connector_runtime_started, true)),
    kvRow('runbook.paper_order_routed', boolChip(runbook.paper_order_routed, true)),
    kvRow('runbook.secret_slot_created', boolChip(runbook.secret_slot_created, true)),
    kvRow('runbook.secret_content_serialized', boolChip(runbook.secret_content_serialized, true)),
    kvRow('runbook.destructive_db_cleanup_requested', boolChip(runbook.destructive_db_cleanup_requested, true)),
    kvRow('runbook.db_delete_or_truncate_allowed', boolChip(runbook.db_delete_or_truncate_allowed, true)),
    kvRow('runbook.paper_shadow_launch_authorized', boolChip(runbook.paper_shadow_launch_authorized, true)),
    kvRow('runbook.tiny_live_authorized', boolChip(runbook.tiny_live_authorized, true)),
    kvRow('runbook.live_authorized', boolChip(runbook.live_authorized, true)),
    kvRow('tiny_live.expected_contract_id', textChip(tinyLive.expected_contract_id || '-')),
    kvRow('tiny_live.contract_id', textChip(tinyLive.contract_id || '-')),
    kvRow('tiny_live.source_version', textChip(tinyLive.source_version)),
    kvRow('tiny_live.accepted', boolChip(tinyLive.accepted, false)),
    kvRow('tiny_live.decision', textChip(tinyLive.decision || 'not_eligible')),
    kvRow('tiny_live.scorecard_derivation_hash_present', boolChip(tinyLive.scorecard_derivation_hash_present, false)),
    kvRow('tiny_live.scorecard_verdict_hash_present', boolChip(tinyLive.scorecard_verdict_hash_present, false)),
    kvRow('tiny_live.paper_shadow_reconciliation_hash_present', boolChip(tinyLive.paper_shadow_reconciliation_hash_present, false)),
    kvRow('tiny_live.qa_review_hash_present', boolChip(tinyLive.qa_review_hash_present, false)),
    kvRow('tiny_live.paper_shadow_window_complete', boolChip(tinyLive.paper_shadow_window_complete, false)),
    kvRow(
      'tiny_live.thresholds',
      '<span class="se-code">' +
        ocEsc(
          'lcb=' + String(tinyLive.benchmark_relative_after_cost_lcb_bps || 0) +
          ' obs=' + String(tinyLive.independent_observation_count || 0) +
          ' min_obs=' + String(tinyLive.min_independent_observation_count || 0) +
          ' cost_lcb=' + String(tinyLive.conservative_cost_stress_lcb_bps || 0) +
          ' div=' + String(tinyLive.paper_shadow_divergence_bps || 0) +
          ' max_div=' + String(tinyLive.max_paper_shadow_divergence_bps || 0)
        ) +
      '</span>'
    ),
    kvRow('tiny_live.concentration_label_passed', boolChip(tinyLive.concentration_label_passed, false)),
    kvRow('tiny_live.regime_label_passed', boolChip(tinyLive.regime_label_passed, false)),
    kvRow('tiny_live.freshness_label_passed', boolChip(tinyLive.freshness_label_passed, false)),
    kvRow('tiny_live.qc_review_passed', boolChip(tinyLive.qc_review_passed, false)),
    kvRow('tiny_live.mit_review_passed', boolChip(tinyLive.mit_review_passed, false)),
    kvRow('tiny_live.qa_review_passed', boolChip(tinyLive.qa_review_passed, false)),
    kvRow('tiny_live.secret_content_serialized', boolChip(tinyLive.secret_content_serialized, true)),
    kvRow('tiny_live.sealed', boolChip(tinyLive.sealed, false)),
    kvRow('paper_shadow_launch_authorized', boolChip(status.paper_shadow_launch_authorized, true)),
    kvRow('tiny_live_or_live_authorized', boolChip(status.tiny_live_or_live_authorized, true)),
    kvRow('connector_runtime_started', boolChip(status.connector_runtime_started, true)),
    kvRow('scorecard_writer_started', boolChip(status.scorecard_writer_started, true)),
    kvRow('db_apply_performed', boolChip(status.db_apply_performed, true)),
    kvRow('evidence_clock_started', boolChip(status.evidence_clock_started, true)),
    kvRow('blockers', chipList(launchBlockers, 'none')),
    kvRow('reason', '<span class="se-code">' + ocEsc(status.reason || '-') + '</span>'),
  ].join('');
  document.getElementById('se-launch-panel').classList.toggle(
    'se-bad-line',
    (status.contract_violations || []).length > 0
  );
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
  renderReadiness(readinessPayload.data, lanePayload && lanePayload.data ? lanePayload.data : null);
  renderDataFoundationStatus(
    dataFoundationPayload && dataFoundationPayload.data
      ? dataFoundationPayload.data
      : dataFoundationFallback('api_unavailable')
  );
  renderPolicyStatus(policyPayload && policyPayload.data ? policyPayload.data : policyFallback('api_unavailable'));
  renderAuthorizationStatus(
    authorizationPayload && authorizationPayload.data
      ? authorizationPayload.data
      : authorizationFallback('api_unavailable')
  );
  renderAccountStatus(accountPayload && accountPayload.data ? accountPayload.data : accountFallback('api_unavailable'));
  renderEvidenceStatus(evidencePayload && evidencePayload.data ? evidencePayload.data : evidenceFallback('api_unavailable'));
  renderUniverseStatus(universePayload && universePayload.data ? universePayload.data : universeFallback('api_unavailable'));
  renderShadowStatus(shadowPayload && shadowPayload.data ? shadowPayload.data : shadowFallback('api_unavailable'));
  renderPaperStatus(paperPayload && paperPayload.data ? paperPayload.data : paperFallback('api_unavailable'));
  renderReconciliationStatus(
    reconciliationPayload && reconciliationPayload.data
      ? reconciliationPayload.data
      : reconciliationFallback('api_unavailable')
  );
  renderScorecardStatus(
    scorecardPayload && scorecardPayload.data
      ? scorecardPayload.data
      : scorecardFallback('api_unavailable')
  );
  renderLaunchStatus(
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
