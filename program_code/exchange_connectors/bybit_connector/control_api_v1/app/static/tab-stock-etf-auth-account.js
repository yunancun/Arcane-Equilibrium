// Display-only renderers for Stock/ETF authorization and account panels.
// This module must remain free of browser writes and broker calls.

(function () {
  function esc(value) {
    return ocEsc(value == null ? '' : String(value));
  }

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
    return '<tr><th>' + esc(label) + '</th><td>' + html + '</td></tr>';
  }

  function chipList(items, emptyText) {
    if (!Array.isArray(items) || items.length === 0) {
      return '<span class="se-muted">' + esc(emptyText || '-') + '</span>';
    }
    return items.map(item => ocChip(String(item), toneFor(item))).join('');
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

  window.renderAuthorizationStatus = renderAuthorizationStatus;
  window.renderAccountStatus = renderAccountStatus;
})();
