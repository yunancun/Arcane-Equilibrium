// Display-only renderers for Stock/ETF evidence, universe, shadow, and paper panels.
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

  function renderEvidenceStatus(data) {
    const evidence = data || evidenceFallback('api_unavailable');
    const marketData = evidence.market_data_provenance || {};
    const collector = evidence.collector_run || {};
    const clock = evidence.evidence_clock || {};
    const frozen = evidence.frozen_inputs || {};
    const dq = evidence.dq_manifest || {};
    const scorecard = evidence.scorecard || {};
    const evidenceBlockers = []
      .concat(marketData.blockers || [])
      .concat(collector.blockers || [])
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
      kvRow('collector_run.accepted', boolChip(collector.accepted, false)),
      kvRow('collector_run.contract_id', textChip(collector.contract_id || '-')),
      kvRow(
        'collector_run.sessions',
        '<span class="se-code">' +
          ocEsc(
            'expected=' + String(collector.expected_trading_sessions || 0) +
            ' completed=' + String(collector.completed_trading_sessions || 0)
          ) +
        '</span>'
      ),
      kvRow('collector_run.market_data_ingestion_started', boolChip(collector.market_data_ingestion_started, true)),
      kvRow('collector_run.evidence_writer_started', boolChip(collector.evidence_writer_started, true)),
      kvRow('collector_run.scorecard_writer_started', boolChip(collector.scorecard_writer_started, true)),
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

  window.renderEvidenceStatus = renderEvidenceStatus;
  window.renderUniverseStatus = renderUniverseStatus;
  window.renderShadowStatus = renderShadowStatus;
  window.renderPaperStatus = renderPaperStatus;
})();
