// Display-only fallback payloads and renderers for Stock/ETF data foundation and policy panels.
// This module must remain free of browser writes and broker calls.

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

function dataFoundationFallback(reason) {
  const why = reason || 'api_unavailable';
  return {
    data_foundation_status_state: 'degraded',
    phase: 'phase2_data_foundation_status_source_fixture',
    phase2_started: false,
    phase3_started: false,
    gui_authority: 'display_only',
    instrument_identity: {
      expected_contract_id: 'instrument_identity_contract_v1',
      contract_id: '',
      source_version: 0,
      accepted: false,
      blockers: [why],
      symbol: '',
      instrument_kind: 'stock',
      listing_venue: 'unknown_denied',
      primary_exchange: 'unknown_denied',
      currency: 'unknown_denied',
      tradability_status: 'unknown_denied',
      priips_kid_status: 'unknown_denied',
      fractional_policy_recorded: false,
      point_in_time_asof_ms: 0,
      market_calendar_id_present: false,
      market_calendar_hash_present: false,
      broker_contract_details_hash_present: false,
      instrument_identity_hash_present: false,
      corporate_action_adjustment_version_hash_present: false,
      source_artifact_hash_present: false,
      bybit_live_execution_unchanged: true,
      ibkr_live_denied: true,
      margin_short_denied: true,
      options_cfd_denied: true,
      ibkr_contact_performed: false,
      secret_content_serialized: false,
    },
    reference_data_sources: {
      expected_contract_id: 'stock_etf_reference_data_sources_v1',
      contract_id: '',
      source_version: 0,
      accepted: false,
      blockers: [why],
      environment: 'paper',
      frozen_for_evidence_clock: false,
      corporate_action_source_name: '',
      corporate_action_asof_ms: 0,
      corporate_action_raw_hash_present: false,
      corporate_action_adjustment_version_hash_present: false,
      corporate_action_policy_hash_present: false,
      dividend_treatment_hash_present: false,
      fx_rate_source_name: '',
      fx_rate_asof_ms: 0,
      base_currency: 'unknown_denied',
      quote_currency: 'unknown_denied',
      fx_rate_snapshot_hash_present: false,
      fx_drag_model_hash_present: false,
      fee_schedule_source_name: '',
      fee_schedule_asof_ms: 0,
      commission_schedule_hash_present: false,
      exchange_regulatory_fee_hash_present: false,
      tax_ftt_placeholder_hash_present: false,
      withholding_tax_treatment_hash_present: false,
      source_artifact_hash_present: false,
      bybit_live_execution_unchanged: true,
      ibkr_contact_performed: false,
      connector_runtime_started: false,
      secret_content_serialized: false,
      live_or_tiny_live_authorized: false,
    },
    contract_details_request_started: false,
    reference_data_collection_started: false,
    collector_started: false,
    market_data_ingestion_started: false,
    connector_runtime_started: false,
    db_apply_performed: false,
    evidence_clock_started: false,
    scorecard_writer_started: false,
    contract_violations: [],
    degraded: true,
    reason: why,
  };
}

function policyFallback(reason) {
  const why = reason || 'api_unavailable';
  return {
    policy_status_state: 'degraded',
    phase: 'phase2_policy_status_source_fixture',
    phase2_started: false,
    phase3_started: false,
    gui_authority: 'display_only',
    risk_policy: {
      expected_contract_id: 'stock_etf_risk_policy_v1',
      contract_id: '',
      source_version: 0,
      config_version: 0,
      accepted: false,
      blockers: [why],
      environment: 'paper',
      enabled: false,
      shadow_only: true,
      max_order_notional_usd: 0,
      max_position_notional_usd: 0,
      max_daily_notional_usd: 0,
      max_open_orders: 0,
      max_open_positions: 0,
      allow_fractional_shares: false,
      allow_margin: false,
      allow_short: false,
      allow_options: false,
      allow_cfd: false,
      allow_transfer: false,
      allow_live: false,
      allowed_kind_count: 0,
      denied_kind_count: 0,
      requires_frozen_universe_hash: false,
      requires_instrument_identity_hash: false,
      requires_market_session: false,
      cost_model_required_before_shadow_fill: false,
      cost_model_required_before_scorecard: false,
      commission_schedule_required: false,
      spread_estimate_required: false,
      slippage_estimate_required: false,
      fx_drag_required: false,
      conservative_fill_penalty_required: false,
      rust_authority_required: false,
      session_attestation_required: false,
      decision_lease_required: false,
      guardian_required: false,
      idempotency_key_required: false,
      broker_reconciliation_required: false,
      bybit_live_execution_unchanged: true,
      ibkr_contact_performed: false,
      connector_runtime_started: false,
      secret_content_serialized: false,
    },
    broker_capability_registry: {
      expected_registry_id: 'broker_capability_registry_v1',
      registry_id: '',
      source_version: 0,
      accepted: false,
      blockers: [why],
      operation_count: 0,
      required_audit_field_count: 0,
      read_operation_count: 0,
      lane_scoped_ipc_contract_id: 'lane_scoped_ipc_v1',
      readonly_probe_request_contract_id: 'stock_etf_ibkr_readonly_probe_request_v1',
      readonly_probe_result_import_request_contract_id:
        'stock_etf_ibkr_readonly_probe_result_import_request_v1',
      read_rows_require_lane_scoped_ipc: false,
      read_rows_require_readonly_probe_request: false,
      scorecard_requires_readonly_probe_result_import_request: false,
      paper_operation_count: 0,
      denied_operation_count: 0,
      bybit_live_execution_unchanged: true,
      python_broker_write_authority_denied: true,
      ibkr_live_denied: true,
      cfd_margin_reserved_denied: true,
      first_ibkr_contact_performed: false,
      secret_content_serialized: false,
    },
    risk_runtime_started: false,
    paper_order_rehearsal_started: false,
    paper_order_submitted: false,
    connector_runtime_started: false,
    db_apply_performed: false,
    evidence_clock_started: false,
    scorecard_writer_started: false,
    contract_violations: [],
    degraded: true,
    reason: why,
  };
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
      'registry.readonly_probe_result_import_request_contract_id',
      textChip(registry.readonly_probe_result_import_request_contract_id || '-')
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
      'registry.scorecard_requires_readonly_probe_result_import_request',
      boolChip(registry.scorecard_requires_readonly_probe_result_import_request, false)
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
