function seReconToneFor(value) {
  const s = String(value || '').toLowerCase();
  if (s === 'false' || s === 'source') return 'good';
  if (s === 'degraded' || s === 'blocked' || s === 'not_started') return 'warn';
  if (s === 'contract_violation_blocked' || s === 'true' || s === 'denied') return 'bad';
  return 'neutral';
}

function seReconTextChip(value) {
  return ocChip(value == null || value === '' ? '-' : String(value), seReconToneFor(value));
}

function seReconBoolChip(value, goodWhenFalse) {
  const flag = value === true;
  const good = goodWhenFalse ? !flag : flag;
  return ocChip(flag ? 'true' : 'false', good ? 'good' : 'bad');
}

function seReconKvRow(label, html) {
  return '<tr><th>' + ocEsc(label) + '</th><td>' + html + '</td></tr>';
}

function seReconChipList(items, emptyText) {
  if (!Array.isArray(items) || items.length === 0) {
    return '<span class="se-muted">' + ocEsc(emptyText || '-') + '</span>';
  }
  return items.map(item => ocChip(String(item), seReconToneFor(item))).join('');
}

function seReconSetChip(id, text, type) {
  const node = document.getElementById(id);
  if (!node) return;
  const safeType = ['good', 'warn', 'bad', 'neutral', 'info'].includes(type) ? type : 'neutral';
  node.textContent = text == null || text === '' ? '-' : String(text);
  node.className = 'oc-chip oc-chip-' + safeType;
}

function reconciliationFallback(reason) {
  const why = reason || 'api_unavailable';
  return {
    reconciliation_status_state: 'degraded',
    phase: 'phase3_reconciliation_status_source_fixture',
    phase3_started: false,
    gui_authority: 'display_only',
    matching: {
      expected_reconciliation_contract_id: 'stock_etf_paper_shadow_reconciliation_v1',
      reconciliation_contract_id: '',
      reconciliation_accepted: false,
      reconciliation_blockers: [why],
      lifecycle_event_accepted: false,
      shadow_fill_model_accepted: false,
      lifecycle_blockers: [why],
      shadow_blockers: [why],
      append_only_event_ready: false,
      paper_order_id_present: false,
      broker_order_id_present: false,
      execution_id_present: false,
      commission_report_id_present: false,
      contract_reconciliation_run_id_present: false,
      shadow_signal_id_present: false,
      shadow_fill_price_present: false,
      paper_shadow_link_present: false,
      paper_shadow_link_hash_present: false,
      divergence_bps: 0,
      divergence_threshold_bps: 0,
      divergence_within_threshold: false,
      unmatched_paper_fill_count: 0,
      unmatched_shadow_fill_count: 0,
      reconciliation_run_id_present: false,
      paper_fill_imported: false,
      shadow_fill_synthetic: false,
      raw_artifact_hash_present: false,
      redacted_summary_hash_present: false,
      reconciliation_writer_started: false,
      ibkr_contact_performed: false,
      connector_runtime_started: false,
      secret_content_serialized: false,
      fill_import_performed: false,
      shadow_fill_generated: false,
    },
    paper_shadow_reconciliation_started: false,
    paper_orders_ready: false,
    paper_fills_ready: false,
    shadow_fills_ready: false,
    scorecard_writer_started: false,
    db_apply_performed: false,
    contract_violations: [],
    degraded: true,
    reason: why,
  };
}

function renderReconciliationStatus(data) {
  const status = data || reconciliationFallback('api_unavailable');
  const matching = status.matching || {};
  const state = status.reconciliation_status_state || 'blocked';
  const reconciliationBlockers = []
    .concat(matching.lifecycle_blockers || [])
    .concat(matching.shadow_blockers || [])
    .concat(matching.reconciliation_blockers || [])
    .concat(status.phase2_gate_blockers || [])
    .concat(status.contract_violations || []);
  document.getElementById('se-reconciliation-state').innerHTML = seReconTextChip(state);
  document.getElementById('se-reconciliation-sub').textContent =
    matching.paper_shadow_link_hash_present ? 'contract-linked' : 'reconciliation blocked';
  seReconSetChip('se-reconciliation-status', state, seReconToneFor(state));
  document.getElementById('se-reconciliation-body').innerHTML = [
    seReconKvRow('phase', seReconTextChip(status.phase || '-')),
    seReconKvRow('phase3_started', seReconBoolChip(status.phase3_started, true)),
    seReconKvRow('reconciliation_started', seReconBoolChip(status.paper_shadow_reconciliation_started, true)),
    seReconKvRow('paper_orders_ready', seReconBoolChip(status.paper_orders_ready, true)),
    seReconKvRow('paper_fills_ready', seReconBoolChip(status.paper_fills_ready, true)),
    seReconKvRow('shadow_fills_ready', seReconBoolChip(status.shadow_fills_ready, true)),
    seReconKvRow(
      'expected_reconciliation_contract_id',
      '<span class="se-code">' + ocEsc(matching.expected_reconciliation_contract_id || '-') + '</span>'
    ),
    seReconKvRow(
      'reconciliation_contract_id',
      '<span class="se-code">' + ocEsc(matching.reconciliation_contract_id || '-') + '</span>'
    ),
    seReconKvRow('reconciliation_accepted', seReconBoolChip(matching.reconciliation_accepted, true)),
    seReconKvRow('lifecycle_event_accepted', seReconBoolChip(matching.lifecycle_event_accepted, true)),
    seReconKvRow('shadow_fill_model_accepted', seReconBoolChip(matching.shadow_fill_model_accepted, true)),
    seReconKvRow('append_only_event_ready', seReconBoolChip(matching.append_only_event_ready, true)),
    seReconKvRow('paper_order_id_present', seReconBoolChip(matching.paper_order_id_present, true)),
    seReconKvRow('broker_order_id_present', seReconBoolChip(matching.broker_order_id_present, true)),
    seReconKvRow('execution_id_present', seReconBoolChip(matching.execution_id_present, true)),
    seReconKvRow('commission_report_id_present', seReconBoolChip(matching.commission_report_id_present, true)),
    seReconKvRow('reconciliation_run_id_present', seReconBoolChip(matching.reconciliation_run_id_present, true)),
    seReconKvRow(
      'contract_reconciliation_run_id_present',
      seReconBoolChip(matching.contract_reconciliation_run_id_present, true)
    ),
    seReconKvRow('shadow_signal_id_present', seReconBoolChip(matching.shadow_signal_id_present, true)),
    seReconKvRow('shadow_fill_price_present', seReconBoolChip(matching.shadow_fill_price_present, true)),
    seReconKvRow('paper_shadow_link_present', seReconBoolChip(matching.paper_shadow_link_present, true)),
    seReconKvRow('paper_shadow_link_hash_present', seReconBoolChip(matching.paper_shadow_link_hash_present, true)),
    seReconKvRow('paper_fill_imported', seReconBoolChip(matching.paper_fill_imported, true)),
    seReconKvRow('shadow_fill_synthetic', seReconBoolChip(matching.shadow_fill_synthetic, true)),
    seReconKvRow(
      'divergence',
      '<span class="se-code">' +
        ocEsc(
          'bps=' + String(matching.divergence_bps || 0) +
          ' threshold=' + String(matching.divergence_threshold_bps || 0) +
          ' within=' + String(matching.divergence_within_threshold === true)
        ) +
      '</span>'
    ),
    seReconKvRow(
      'unmatched_counts',
      '<span class="se-code">' +
        ocEsc(
          'paper=' + String(matching.unmatched_paper_fill_count || 0) +
          ' shadow=' + String(matching.unmatched_shadow_fill_count || 0)
        ) +
      '</span>'
    ),
    seReconKvRow('raw_artifact_hash_present', seReconBoolChip(matching.raw_artifact_hash_present, true)),
    seReconKvRow('redacted_summary_hash_present', seReconBoolChip(matching.redacted_summary_hash_present, true)),
    seReconKvRow('reconciliation_writer_started', seReconBoolChip(matching.reconciliation_writer_started, true)),
    seReconKvRow('ibkr_contact_performed', seReconBoolChip(matching.ibkr_contact_performed, true)),
    seReconKvRow('connector_runtime_started', seReconBoolChip(matching.connector_runtime_started, true)),
    seReconKvRow('secret_content_serialized', seReconBoolChip(matching.secret_content_serialized, true)),
    seReconKvRow('fill_import_performed', seReconBoolChip(matching.fill_import_performed, true)),
    seReconKvRow('shadow_fill_generated', seReconBoolChip(matching.shadow_fill_generated, true)),
    seReconKvRow('scorecard_writer_started', seReconBoolChip(status.scorecard_writer_started, true)),
    seReconKvRow('db_apply_performed', seReconBoolChip(status.db_apply_performed, true)),
    seReconKvRow('blockers', seReconChipList(reconciliationBlockers, 'none')),
    seReconKvRow('reason', '<span class="se-code">' + ocEsc(status.reason || '-') + '</span>'),
  ].join('');
  document.getElementById('se-reconciliation-panel').classList.toggle(
    'se-bad-line',
    (status.contract_violations || []).length > 0
  );
}
