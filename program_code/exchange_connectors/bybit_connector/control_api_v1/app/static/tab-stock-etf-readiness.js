// Display-only readiness renderer for the Stock/ETF lane boundary panel.
// This module must remain free of browser writes and broker calls.

(function () {
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

  function renderReadiness(data, laneStatus) {
    const source = data.source_readiness || {};
    const apiAllowlist = data.api_allowlist || {};
    const readonlyProbe = data.readonly_probe_request || {};
    const readonlyProbeResultImport = data.readonly_probe_result_import_request || {};
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
      kvRow('readonly_probe_result_import.contract_id', textChip(readonlyProbeResultImport.contract_id || '-')),
      kvRow('readonly_probe_result_import.source_version', textChip(readonlyProbeResultImport.source_version || 0)),
      kvRow('readonly_probe_result_import.status', textChip(readonlyProbeResultImport.status || 'blocked_no_result_import_request_artifact')),
      kvRow('readonly_probe_result_import.accepted_for_import', boolChip(readonlyProbeResultImport.accepted_for_import, false)),
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
      kvRow('readonly_probe_result_import.request_artifact_present', boolChip(readonlyProbeResultImport.request_artifact_present, true)),
      kvRow('readonly_probe_result_import.request_validated', boolChip(readonlyProbeResultImport.request_validated, true)),
      kvRow('readonly_probe_result_import.accepted_for_import', boolChip(readonlyProbeResultImport.accepted_for_import, true)),
      kvRow('readonly_probe_result_import.ibkr_contact_performed', boolChip(readonlyProbeResultImport.ibkr_contact_performed, true)),
      kvRow('readonly_probe_result_import.connector_runtime_started', boolChip(readonlyProbeResultImport.connector_runtime_started, true)),
      kvRow('readonly_probe_result_import.secret_content_serialized', boolChip(readonlyProbeResultImport.secret_content_serialized, true)),
      kvRow('readonly_probe_result_import.result_import_performed', boolChip(readonlyProbeResultImport.result_import_performed, true)),
      kvRow('readonly_probe_result_import.evidence_writer_started', boolChip(readonlyProbeResultImport.evidence_writer_started, true)),
      kvRow('readonly_probe_result_import.scorecard_writer_started', boolChip(readonlyProbeResultImport.scorecard_writer_started, true)),
      kvRow('readonly_probe_result_import.db_apply_performed', boolChip(readonlyProbeResultImport.db_apply_performed, true)),
      kvRow('readonly_probe_result_import.order_routed', boolChip(readonlyProbeResultImport.order_routed, true)),
      kvRow('readonly_probe_result_import.paper_order_submitted', boolChip(readonlyProbeResultImport.paper_order_submitted, true)),
      kvRow('readonly_probe_result_import.bybit_path_reused', boolChip(readonlyProbeResultImport.bybit_path_reused, true)),
      kvRow('readonly_probe_result_import.live_or_tiny_live_authorized', boolChip(readonlyProbeResultImport.live_or_tiny_live_authorized, true)),
      kvRow('readonly_probe_result_import.blockers', chipList(readonlyProbeResultImport.blockers, 'none')),
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
      .concat(readonlyProbeResultImport.blockers || [])
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

  window.renderReadiness = renderReadiness;
})();
