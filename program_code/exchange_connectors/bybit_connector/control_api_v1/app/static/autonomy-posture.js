/**
 * Wave 5 Packet B — Autonomy Posture GUI binding.
 * Wave 5 Packet B — Autonomy Posture 前端綁定。
 */

let _currentAutonomyState = null;

function autonomyChipForLevel(level) {
  if (level === 'STANDARD') return ocChip('Level 2 - STANDARD', 'warn');
  if (level === 'CONSERVATIVE') return ocChip('Level 1 - CONSERVATIVE', 'info');
  return ocChip('UNKNOWN', 'neutral');
}

function autonomyFmtTime(value) {
  if (!value) return '--';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toISOString().replace('T', ' ').replace(/\.\d+Z$/, ' UTC');
}

function autonomyRenderEligibility(eligibility) {
  const el = document.getElementById('autonomy-eligibility-list');
  if (!el) return;
  const gates = (eligibility && Array.isArray(eligibility.gates)) ? eligibility.gates : [];
  if (!gates.length) {
    el.innerHTML = '<div style="color:var(--text-dim);font-size:12px">No eligibility data / 無門檻資料</div>';
    return;
  }
  let html = '';
  gates.forEach(function(gate) {
    const ok = gate.passed === true;
    html += '<div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start;'
      + 'padding:8px 10px;border:1px solid var(--border);border-radius:6px;background:var(--bg)">';
    html += '<div style="min-width:0">';
    html += '<div style="font-size:12px;font-weight:600">' + ocEsc(gate.id || '-') + ' · ' + ocEsc(gate.label || '-') + '</div>';
    html += '<div style="font-size:11px;color:var(--text-dim);line-height:1.5">' + ocEsc(gate.detail || '') + '</div>';
    html += '</div>';
    html += ocChip(ok ? 'PASS' : 'BLOCKED', ok ? 'good' : 'warn');
    html += '</div>';
  });
  el.innerHTML = html;
}

function autonomyRenderMatrix(matrix) {
  const tbody = document.getElementById('autonomy-matrix-tbody');
  if (!tbody) return;
  const rows = Array.isArray(matrix) ? matrix : [];
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="5" style="color:var(--text-dim)">No matrix data / 無矩陣資料</td></tr>';
    return;
  }
  let html = '';
  rows.forEach(function(row) {
    html += '<tr>';
    html += '<td>' + ocEsc(row.id || '-') + '</td>';
    html += '<td>' + ocEsc(row.path || '-') + '</td>';
    html += '<td>' + ocEsc(row.category || '-') + '</td>';
    html += '<td>' + ocEsc(row.level1 || '-') + '</td>';
    html += '<td>' + ocEsc(row.level2 || '-') + '</td>';
    html += '</tr>';
  });
  tbody.innerHTML = html;
}

function autonomyRenderPosture(payload) {
  _currentAutonomyState = payload || null;
  const level = payload && payload.current_level ? payload.current_level : 'UNKNOWN';
  ocSetHtml('autonomy-current-level-badge', autonomyChipForLevel(level));
  ocSetText('autonomy-last-switched', autonomyFmtTime(payload && payload.last_switched_at_utc));
  ocSetText('autonomy-switched-by', 'by ' + ((payload && payload.switched_by) || '--'));
  ocSetText('autonomy-switch-reason', (payload && payload.switch_reason) || '--');

  const notif = (payload && payload.notification) || {};
  ocSetText('autonomy-notif-slack', notif.slack || '--');
  ocSetText('autonomy-notif-email', notif.email || '--');
  ocSetText('autonomy-notif-banner', notif.banner || '--');
  const escEl = document.getElementById('autonomy-notification-escalation');
  if (escEl) {
    escEl.innerHTML = 'Escalation result: <strong>' + ocEsc(notif.escalation_result || '--') + '</strong> '
      + '<span style="font-size:10px">（三路全 fail -> 1h wait -> SM-04 Defensive）</span>';
  }

  autonomyRenderEligibility(payload && payload.eligibility);
  autonomyRenderMatrix(payload && payload.matrix);

  const button = document.getElementById('autonomy-switch-btn');
  const blockers = (payload && Array.isArray(payload.switch_blockers)) ? payload.switch_blockers : [];
  if (button) {
    button.disabled = !(payload && payload.can_switch === true);
    button.title = blockers.length
      ? ('Blocked: ' + blockers.join(', '))
      : ('Switch to ' + (payload.target_level || 'target level'));
  }

  const title = document.getElementById('autonomy-runtime-banner-title');
  const body = document.getElementById('autonomy-runtime-banner-body');
  if (title && body) {
    if (payload && payload.wiring_status === 'pg_path_active') {
      title.textContent = 'Runtime Connected / 已接通';
      body.textContent = blockers.length
        ? 'V099 state 已接通；切換目前受 ' + blockers.join(', ') + ' 限制。'
        : 'V099 state 已接通；切換門檻已通過。';
    } else {
      title.textContent = 'Degraded / 降級';
      body.textContent = 'Autonomy Level state 暫不可用；系統按 Level 1 Conservative 顯示。';
    }
  }
}

async function loadAutonomyPosture() {
  try {
    const d = await govGetAutonomyLevelState();
    if (d && d.ok && d.data) {
      autonomyRenderPosture(d.data);
      return;
    }
  } catch (e) {
    console.warn('Autonomy posture load failed:', e);
  }
  autonomyRenderPosture({
    wiring_status: 'degraded',
    current_level: 'CONSERVATIVE',
    switch_blockers: ['state_unavailable'],
    can_switch: false,
    eligibility: { gates: [] },
    matrix: [],
  });
}

async function autonomyOpenSwitchModal() {
  const state = _currentAutonomyState;
  if (!state) {
    ocToast('Autonomy state not loaded / 自主程度狀態尚未載入', 'error');
    return;
  }
  const blockers = Array.isArray(state.switch_blockers) ? state.switch_blockers : [];
  if (blockers.length || state.can_switch !== true) {
    ocToast('Switch blocked: ' + blockers.join(', '), 'warn');
    return;
  }

  const reason = await openPromptModal({
    title: 'Switch Autonomy Level',
    body: 'Target: ' + state.target_level_label,
    label: 'Reason / 理由（>=30 chars）',
    required: true,
    multiline: true,
    maxlength: 1000,
  });
  if (!reason) return;
  if (reason.trim().length < 30) {
    ocToast('Reason must be at least 30 characters / 理由至少 30 字元', 'error');
    return;
  }

  const totp = await openPromptModal({
    title: 'TOTP Required',
    body: '6-digit TOTP only; backend fail-closed if unavailable.',
    label: 'TOTP',
    required: true,
    maxlength: 32,
  });
  if (!totp) return;

  const confirmed = await openTypedConfirmModal({
    title: 'Confirm Autonomy Level Switch',
    body: 'Switching changes system-wide governance posture. In-flight leases keep their original level snapshot.',
    phrase: 'CONFIRM SWITCH',
    confirmLabel: 'Switch / 切換',
    confirmClass: 'oc-btn-danger',
  });
  if (!confirmed) return;

  const result = await govSwitchAutonomyLevel({
    target_level: state.target_level,
    reason: reason.trim(),
    typed_confirm_phrase: 'CONFIRM SWITCH',
    totp_code: String(totp).trim(),
  });
  if (result && result.ok) {
    ocToast('Autonomy Level switched / 自主程度已切換', 'success');
    loadAutonomyPosture();
  } else {
    ocToast((result && result.message) || 'Autonomy switch failed / 切換失敗', 'error');
  }
}
