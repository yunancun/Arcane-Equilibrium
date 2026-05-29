/**
 * Wave 5 Packet B — Autonomy Posture GUI binding.
 * Wave 5 Packet B — Autonomy Posture 前端綁定。
 */

let _currentAutonomyState = null;

// ── 術語 → 白話映射（P3-06 operator comprehension）──
// 為什麼：raw enum / 統計名詞（STANDARD / PASS / escalation_result 等）對非技術
// operator 不可讀。預設顯示中文白話，原始 enum 保留在括號 + title 不丟失真相。
const AUTONOMY_LEVEL_LABELS = {
  STANDARD: '標準自主（門檻較低）',
  CONSERVATIVE: '保守自主（門檻較高）',
};
const AUTONOMY_GATE_LABELS = {
  // 啟用閘門通過與否的白話
  PASS: '已通過',
  BLOCKED: '未達標',
};
const AUTONOMY_ESCALATION_LABELS = {
  // 三路通知升級結果的白話
  delivered: '通知已送達',
  partial: '部分送達',
  all_failed: '三路全失敗（已轉防禦模式）',
  not_triggered: '尚未觸發',
};
const AUTONOMY_NOTIF_LABELS = {
  // 單一通知管道狀態的白話
  delivered: '已送達',
  ok: '已送達',
  failed: '失敗',
  pending: '處理中',
  skipped: '未啟用',
};

// 查表回白話；找不到時回原值（fail-loud：operator 看得到未對應的 raw enum）。
function autonomyPlainLabel(map, raw) {
  if (raw == null || raw === '' || raw === '--') return raw == null ? '--' : String(raw);
  const key = String(raw);
  return Object.prototype.hasOwnProperty.call(map, key) ? map[key] : key;
}

// 白話 +（原始 enum）並列，保留可審計的真相。
function autonomyPlainWithRaw(map, raw) {
  if (raw == null || raw === '' || raw === '--') return '--';
  const key = String(raw);
  if (Object.prototype.hasOwnProperty.call(map, key)) return map[key] + '（' + key + '）';
  return key;
}

// 單一通知管道：可見文字用白話，title tooltip 帶原始 enum 不丟審計真相。
// 為什麼：管道狀態 chip 空間小，不適合括號並列；改以 hover tooltip 暴露 raw enum。
function autonomySetNotifChannel(elId, raw) {
  ocSetText(elId, autonomyPlainLabel(AUTONOMY_NOTIF_LABELS, raw));
  const el = document.getElementById(elId);
  if (el) el.title = String(raw == null ? '--' : raw);
}

function autonomyChipForLevel(level) {
  if (level === 'STANDARD') return ocChip('標準自主 · Level 2 STANDARD', 'warn');
  if (level === 'CONSERVATIVE') return ocChip('保守自主 · Level 1 CONSERVATIVE', 'info');
  return ocChip('未知 · UNKNOWN', 'neutral');
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
    html += ocChip(ok ? '已通過 · PASS' : '未達標 · BLOCKED', ok ? 'good' : 'warn');
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
  // 單管道狀態：白話顯示，原始 enum 以 title tooltip 保留供審計（hover 可見真相）。
  autonomySetNotifChannel('autonomy-notif-slack', notif.slack || '--');
  autonomySetNotifChannel('autonomy-notif-email', notif.email || '--');
  autonomySetNotifChannel('autonomy-notif-banner', notif.banner || '--');
  const escEl = document.getElementById('autonomy-notification-escalation');
  if (escEl) {
    escEl.innerHTML = '升級結果：<strong>' + ocEsc(autonomyPlainWithRaw(AUTONOMY_ESCALATION_LABELS, notif.escalation_result || '--')) + '</strong> '
      + '<span style="font-size:10px">（三路通知全失敗 → 等待 1 小時 → 自動切到 SM-04 防禦模式）</span>';
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
      title.textContent = '即時狀態已連線 / Runtime Connected';
      body.textContent = blockers.length
        ? '自主程度狀態已連線；目前因下列原因暫無法切換：' + blockers.join('、') + '。'
        : '自主程度狀態已連線；切換門檻已全部通過。';
    } else {
      title.textContent = '連線降級 / Degraded';
      body.textContent = '暫時讀不到自主程度狀態；系統先以最保守的「保守自主（Level 1）」顯示。';
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
