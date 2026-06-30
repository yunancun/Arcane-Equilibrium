window.STOCK_ETF_DISABLE_CLEANUP_STATUS_ENDPOINT = '/api/v1/stock-etf/disable-cleanup-status';

window.disableCleanupFallback = function disableCleanupFallback(reason) {
  const why = reason || 'api_unavailable';
  return {
    disable_cleanup_status_state: 'degraded',
    phase: 'phase5_disable_cleanup_status_source_fixture',
    phase3_started: false,
    phase5_started: false,
    gui_authority: 'display_only',
    collector_stop_requested: false,
    gui_disable_requested: false,
    evidence_archive_requested: false,
    db_cleanup_requested: false,
    runbook: {
      expected_runbook_id: 'stock_etf_kill_switch_and_disable_cleanup_runbook_v1',
      runbook_id: '',
      source_version: 0,
      accepted: false,
      blockers: [why],
      source_artifact_hash_present: false,
      bybit_live_execution_unchanged: false,
      env_flag_count: 0,
      proof_count: 0,
      env_flags: [],
      proofs: [],
      ibkr_contact_performed: false,
      connector_runtime_started: false,
      paper_order_routed: false,
      secret_slot_created: false,
      secret_content_serialized: false,
      destructive_db_cleanup_requested: false,
      db_delete_or_truncate_allowed: false,
      paper_shadow_launch_authorized: false,
      tiny_live_authorized: false,
      live_authorized: false,
    },
    paper_shadow_launch_authorized: false,
    tiny_live_or_live_authorized: false,
    connector_runtime_started: false,
    scorecard_writer_started: false,
    db_apply_performed: false,
    evidence_clock_started: false,
    contract_violations: [],
    degraded: true,
    reason: why,
  };
};

window.renderDisableCleanupStatus = function renderDisableCleanupStatus(data) {
  const status = data || window.disableCleanupFallback('api_unavailable');
  const runbook = status.runbook || {};
  const state = status.disable_cleanup_status_state || 'blocked';
  const blockers = []
    .concat(runbook.blockers || [])
    .concat(status.phase2_gate_blockers || [])
    .concat(status.contract_violations || []);
  const envFlags = Array.isArray(runbook.env_flags) ? runbook.env_flags : [];
  const proofs = Array.isArray(runbook.proofs) ? runbook.proofs : [];
  const body = document.getElementById('se-disable-cleanup-body');
  if (!body) return;

  document.getElementById('se-disable-cleanup-state').innerHTML = textChip(state);
  document.getElementById('se-disable-cleanup-sub').textContent =
    runbook.accepted ? 'runbook source ready; runtime blocked' : 'runbook blocked';
  setChip('se-disable-cleanup-status', state, toneFor(state));
  body.innerHTML = [
    kvRow('phase', textChip(status.phase || '-')),
    kvRow('phase3_started', boolChip(status.phase3_started, true)),
    kvRow('phase5_started', boolChip(status.phase5_started, true)),
    kvRow('collector_stop_requested', boolChip(status.collector_stop_requested, true)),
    kvRow('gui_disable_requested', boolChip(status.gui_disable_requested, true)),
    kvRow('evidence_archive_requested', boolChip(status.evidence_archive_requested, true)),
    kvRow('db_cleanup_requested', boolChip(status.db_cleanup_requested, true)),
    kvRow('runbook.expected_runbook_id', textChip(runbook.expected_runbook_id || '-')),
    kvRow('runbook.runbook_id', textChip(runbook.runbook_id || '-')),
    kvRow('runbook.source_version', textChip(runbook.source_version)),
    kvRow('runbook.accepted', boolChip(runbook.accepted, false)),
    kvRow('runbook.source_artifact_hash_present', boolChip(runbook.source_artifact_hash_present, false)),
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
    kvRow(
      'env_flags',
      chipList(
        envFlags.map(flag =>
          (flag.name || 'unknown') + '=' + (flag.observed_value || '-') +
          '/' + (flag.expected_value || '-')
        ),
        'none'
      )
    ),
    kvRow(
      'proofs',
      chipList(
        proofs.map(proof =>
          (proof.kind || 'unknown') + ':' + (proof.verified ? 'verified' : 'blocked')
        ),
        'none'
      )
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
    kvRow('paper_shadow_launch_authorized', boolChip(status.paper_shadow_launch_authorized, true)),
    kvRow('tiny_live_or_live_authorized', boolChip(status.tiny_live_or_live_authorized, true)),
    kvRow('connector_runtime_started', boolChip(status.connector_runtime_started, true)),
    kvRow('scorecard_writer_started', boolChip(status.scorecard_writer_started, true)),
    kvRow('db_apply_performed', boolChip(status.db_apply_performed, true)),
    kvRow('evidence_clock_started', boolChip(status.evidence_clock_started, true)),
    kvRow('blockers', chipList(blockers, 'none')),
    kvRow('reason', '<span class="se-code">' + ocEsc(status.reason || '-') + '</span>'),
  ].join('');
  document.getElementById('se-disable-cleanup-panel').classList.toggle(
    'se-bad-line',
    (status.contract_violations || []).length > 0
  );
};
