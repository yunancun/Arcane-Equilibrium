(function () {
  const ENDPOINT = '/api/v1/stock-etf/phase0-status';
  window.STOCK_ETF_PHASE0_STATUS_ENDPOINT = ENDPOINT;

  function esc(value) {
    return ocEsc(value == null ? '' : String(value));
  }

  function toneFor(value) {
    const s = String(value || '').toLowerCase();
    if (s === 'accepted_no_runtime_authority' || s === 'true') return 'good';
    if (s === 'degraded' || s === 'blocked' || s === 'false') return 'warn';
    if (s === 'contract_violation_blocked' || s === 'denied') return 'bad';
    return 'neutral';
  }

  function textChip(value) {
    return ocChip(value == null || value === '' ? '-' : String(value), toneFor(value));
  }

  function boolChip(value, goodWhenFalse) {
    const flag = value === true;
    const good = goodWhenFalse ? !flag : flag;
    return ocChip(flag ? 'true' : 'false', good ? 'good' : 'bad');
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

  function setChip(id, text, type) {
    const node = document.getElementById(id);
    if (!node) return;
    const safeType = ['good', 'warn', 'bad', 'neutral', 'info'].includes(type) ? type : 'neutral';
    node.textContent = text == null || text === '' ? '-' : String(text);
    node.className = 'oc-chip oc-chip-' + safeType;
  }

  window.phase0Fallback = function phase0Fallback(reason) {
    const why = reason || 'api_unavailable';
    return {
      phase0_status_state: 'degraded',
      scope: 'paper_shadow_only',
      gui_authority: 'display_only',
      phase0_accepted: false,
      manifest: {
        schema: '',
        generated_at: '',
        status: '',
        scope: '',
        adr: '',
        amd: '',
        contract_packet: '',
        accepted: false,
        blockers: [why],
      },
      contract_count: 0,
      contracts: [],
      api_baseline: {
        selected: '',
        host_policy: '',
        paper_port_default_candidate: 0,
        live_ports_denied: false,
        ibkr_call_performed: false,
      },
      global_denials: {},
      phase_unlock: {},
      phase1_runtime_started: false,
      phase2_started: false,
      phase3_started: false,
      phase4_runtime_started: false,
      phase5_started: false,
      paper_shadow_launch_authorized: false,
      tiny_live_or_live_authorized: false,
      connector_runtime_started: false,
      db_apply_performed: false,
      evidence_clock_started: false,
      scorecard_writer_started: false,
      ibkr_call_performed: false,
      secret_slot_touched: false,
      order_routed: false,
      bybit_ipc_reused: false,
      contract_violations: [],
      degraded: true,
      reason: why,
    };
  };

  window.renderPhase0Status = function renderPhase0Status(status) {
    const manifest = status.manifest || {};
    const api = status.api_baseline || {};
    const denials = status.global_denials || {};
    const unlock = status.phase_unlock || {};
    const blockers = (status.contract_violations || []).concat(manifest.blockers || []);
    const state = status.phase0_status_state || 'blocked';
    document.getElementById('se-phase0-state').innerHTML = textChip(state);
    document.getElementById('se-phase0-sub').textContent =
      'contracts=' + String(status.contract_count || 0) + ' scope=' + (status.scope || 'paper_shadow_only');
    setChip('se-phase0-status', state, toneFor(state));
    document.getElementById('se-phase0-body').innerHTML = [
      kvRow('manifest.schema', textChip(manifest.schema || '-')),
      kvRow('manifest.status', textChip(manifest.status || '-')),
      kvRow('manifest.generated_at', textChip(manifest.generated_at || '-')),
      kvRow('manifest.scope', textChip(manifest.scope || status.scope || '-')),
      kvRow('manifest.accepted', boolChip(status.phase0_accepted, false)),
      kvRow('contract_count', textChip(status.contract_count || 0)),
      kvRow('api.selected', textChip(api.selected || '-')),
      kvRow('api.host_policy', textChip(api.host_policy || '-')),
      kvRow('api.paper_port_default_candidate', textChip(api.paper_port_default_candidate || 0)),
      kvRow('api.live_ports_denied', boolChip(api.live_ports_denied, false)),
      kvRow('api.ibkr_call_performed', boolChip(api.ibkr_call_performed, true)),
      kvRow('denial.ibkr_live', boolChip(denials.ibkr_live, false)),
      kvRow('denial.tiny_live', boolChip(denials.tiny_live, false)),
      kvRow('denial.gui_lane_authority', boolChip(denials.gui_lane_authority, false)),
      kvRow('denial.python_broker_write_authority', boolChip(denials.python_broker_write_authority, false)),
      kvRow('unlock.phase1', '<span class="se-code">' + esc(unlock.phase1_type_config_schema_ipc || '-') + '</span>'),
      kvRow('unlock.phase2', '<span class="se-code">' + esc(unlock.phase2_ibkr_external_contact || '-') + '</span>'),
      kvRow('unlock.phase5', '<span class="se-code">' + esc(unlock.phase5_paper_shadow_online || '-') + '</span>'),
      kvRow('phase1_runtime_started', boolChip(status.phase1_runtime_started, true)),
      kvRow('phase2_started', boolChip(status.phase2_started, true)),
      kvRow('phase3_started', boolChip(status.phase3_started, true)),
      kvRow('phase4_runtime_started', boolChip(status.phase4_runtime_started, true)),
      kvRow('phase5_started', boolChip(status.phase5_started, true)),
      kvRow('paper_shadow_launch_authorized', boolChip(status.paper_shadow_launch_authorized, true)),
      kvRow('tiny_live_or_live_authorized', boolChip(status.tiny_live_or_live_authorized, true)),
      kvRow('connector_runtime_started', boolChip(status.connector_runtime_started, true)),
      kvRow('db_apply_performed', boolChip(status.db_apply_performed, true)),
      kvRow('evidence_clock_started', boolChip(status.evidence_clock_started, true)),
      kvRow('scorecard_writer_started', boolChip(status.scorecard_writer_started, true)),
      kvRow('ibkr_call_performed', boolChip(status.ibkr_call_performed, true)),
      kvRow('secret_slot_touched', boolChip(status.secret_slot_touched, true)),
      kvRow('order_routed', boolChip(status.order_routed, true)),
      kvRow('bybit_ipc_reused', boolChip(status.bybit_ipc_reused, true)),
      kvRow('blockers', chipList(blockers, 'none')),
      kvRow('reason', '<span class="se-code">' + esc(status.reason || '-') + '</span>'),
    ].join('');
    document.getElementById('se-phase0-panel').classList.toggle(
      'se-bad-line',
      (status.contract_violations || []).length > 0
    );
  };
})();
