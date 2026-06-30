// Display-only renderers for Stock/ETF scorecard and launch panels.
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

  window.renderScorecardStatus = renderScorecardStatus;
  window.renderLaunchStatus = renderLaunchStatus;
})();
