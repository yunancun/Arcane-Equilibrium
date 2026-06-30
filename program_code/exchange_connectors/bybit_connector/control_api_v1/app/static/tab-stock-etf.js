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
  window.renderAuthorizationStatus(authorizationFallback('api_unavailable'));
  window.renderAccountStatus(accountFallback('api_unavailable'));
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
  window.renderAuthorizationStatus(
    authorizationPayload && authorizationPayload.data
      ? authorizationPayload.data
      : authorizationFallback('api_unavailable')
  );
  window.renderAccountStatus(accountPayload && accountPayload.data ? accountPayload.data : accountFallback('api_unavailable'));
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
