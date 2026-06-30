window.STOCK_ETF_RELEASE_PACKET_STATUS_ENDPOINT = '/api/v1/stock-etf/release-packet-status';

window.releasePacketFallback = function releasePacketFallback(reason) {
  const why = reason || 'api_unavailable';
  return {
    release_packet_status_state: 'degraded',
    phase: 'phase5_release_packet_status_source_fixture',
    phase3_started: false,
    phase5_started: false,
    gui_authority: 'display_only',
    release_packet: {
      expected_contract_id: 'stock_etf_release_packet_v1',
      packet_id: '',
      source_version: 0,
      accepted: false,
      blockers: [why],
      source_commit_present: false,
      reviewer_role_count: 0,
      reviewer_roles: [],
      role_report_count: 0,
      e2_log_hash_present: false,
      e3_redaction_log_hash_present: false,
      e4_log_hash_present: false,
      qa_log_hash_present: false,
      manifest_hash_count: 0,
      manifest_hashes: [],
      pg_migrations_declared: false,
      pg_migration_manifest_hash_present: false,
      pg_dry_run_log_hash_present: false,
      pg_double_apply_log_hash_present: false,
      redaction_fixture_hash_present: false,
      gui_screenshot_hash_count: 0,
      dq_manifest_hash_count: 0,
      scorecard_regeneration_hash_count: 0,
      evidence_archive_pointer_present: false,
      evidence_archive_hash_present: false,
      paper_shadow_window_complete: false,
      engineering_shakedown_complete: false,
      secret_content_serialized: false,
      ibkr_live_or_tiny_live_authorized: false,
      sealed: false,
      kill_disable_cleanup_proof: {},
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

window.renderReleasePacketStatus = function renderReleasePacketStatus(data) {
  const status = data || window.releasePacketFallback('api_unavailable');
  const release = status.release_packet || {};
  const kill = release.kill_disable_cleanup_proof || {};
  const state = status.release_packet_status_state || 'blocked';
  const blockers = []
    .concat(release.blockers || [])
    .concat(status.phase2_gate_blockers || [])
    .concat(status.contract_violations || []);
  const manifests = Array.isArray(release.manifest_hashes) ? release.manifest_hashes : [];
  const body = document.getElementById('se-release-packet-body');
  if (!body) return;

  document.getElementById('se-release-packet-state').innerHTML = textChip(state);
  document.getElementById('se-release-packet-sub').textContent =
    release.accepted ? 'source packet ready; runtime blocked' : 'packet blocked';
  setChip('se-release-packet-status', state, toneFor(state));
  body.innerHTML = [
    kvRow('phase', textChip(status.phase || '-')),
    kvRow('phase3_started', boolChip(status.phase3_started, true)),
    kvRow('phase5_started', boolChip(status.phase5_started, true)),
    kvRow('release.expected_contract_id', textChip(release.expected_contract_id || '-')),
    kvRow('release.packet_id', textChip(release.packet_id || '-')),
    kvRow('release.source_version', textChip(release.source_version)),
    kvRow('release.accepted', boolChip(release.accepted, false)),
    kvRow('release.source_commit_present', boolChip(release.source_commit_present, false)),
    kvRow('release.reviewer_roles', chipList(release.reviewer_roles || [], 'none')),
    kvRow(
      'release.counts',
      '<span class="se-code">' +
        ocEsc(
          'roles=' + String(release.reviewer_role_count || 0) +
          ' reports=' + String(release.role_report_count || 0) +
          ' manifests=' + String(release.manifest_hash_count || 0)
        ) +
      '</span>'
    ),
    kvRow('release.e2_log_hash_present', boolChip(release.e2_log_hash_present, false)),
    kvRow('release.e3_redaction_log_hash_present', boolChip(release.e3_redaction_log_hash_present, false)),
    kvRow('release.e4_log_hash_present', boolChip(release.e4_log_hash_present, false)),
    kvRow('release.qa_log_hash_present', boolChip(release.qa_log_hash_present, false)),
    kvRow(
      'release.manifest_hashes',
      chipList(manifests.map(item => (item.label || 'unknown') + ':' + (item.hash_present ? 'hash' : 'missing')), 'none')
    ),
    kvRow('release.pg_migrations_declared', boolChip(release.pg_migrations_declared, true)),
    kvRow('release.pg_dry_run_log_hash_present', boolChip(release.pg_dry_run_log_hash_present, false)),
    kvRow('release.pg_double_apply_log_hash_present', boolChip(release.pg_double_apply_log_hash_present, false)),
    kvRow('release.redaction_fixture_hash_present', boolChip(release.redaction_fixture_hash_present, false)),
    kvRow('release.gui_screenshot_hash_count', textChip(release.gui_screenshot_hash_count || 0)),
    kvRow('release.dq_manifest_hash_count', textChip(release.dq_manifest_hash_count || 0)),
    kvRow('release.scorecard_regeneration_hash_count', textChip(release.scorecard_regeneration_hash_count || 0)),
    kvRow('release.evidence_archive_pointer_present', boolChip(release.evidence_archive_pointer_present, false)),
    kvRow('release.evidence_archive_hash_present', boolChip(release.evidence_archive_hash_present, false)),
    kvRow('release.paper_shadow_window_complete', boolChip(release.paper_shadow_window_complete, false)),
    kvRow('release.engineering_shakedown_complete', boolChip(release.engineering_shakedown_complete, false)),
    kvRow('release.secret_content_serialized', boolChip(release.secret_content_serialized, true)),
    kvRow('release.ibkr_live_or_tiny_live_authorized', boolChip(release.ibkr_live_or_tiny_live_authorized, true)),
    kvRow('release.sealed', boolChip(release.sealed, false)),
    kvRow('kill.flags_disabled', chipList([
      'lane=' + (kill.stock_etf_lane_enabled_false ? 'off' : 'open'),
      'readonly=' + (kill.ibkr_readonly_enabled_false ? 'off' : 'open'),
      'paper=' + (kill.ibkr_paper_enabled_false ? 'off' : 'open'),
    ], 'none')),
    kvRow('kill.collector_stopped', boolChip(kill.collector_stopped, false)),
    kvRow('kill.gui_hidden', boolChip(kill.gui_stock_views_disabled_or_hidden, false)),
    kvRow('kill.live_secret_absence_proven', boolChip(kill.live_secret_absence_proven, false)),
    kvRow('kill.evidence_archive_forward_only', boolChip(kill.evidence_archive_forward_only, false)),
    kvRow('kill.destructive_db_cleanup_requested', boolChip(kill.destructive_db_cleanup_requested, true)),
    kvRow('paper_shadow_launch_authorized', boolChip(status.paper_shadow_launch_authorized, true)),
    kvRow('tiny_live_or_live_authorized', boolChip(status.tiny_live_or_live_authorized, true)),
    kvRow('connector_runtime_started', boolChip(status.connector_runtime_started, true)),
    kvRow('scorecard_writer_started', boolChip(status.scorecard_writer_started, true)),
    kvRow('db_apply_performed', boolChip(status.db_apply_performed, true)),
    kvRow('evidence_clock_started', boolChip(status.evidence_clock_started, true)),
    kvRow('blockers', chipList(blockers, 'none')),
    kvRow('reason', '<span class="se-code">' + ocEsc(status.reason || '-') + '</span>'),
  ].join('');
  document.getElementById('se-release-packet-panel').classList.toggle(
    'se-bad-line',
    (status.contract_violations || []).length > 0
  );
};
