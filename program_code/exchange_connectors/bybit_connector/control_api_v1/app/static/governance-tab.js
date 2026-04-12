/**
 * Governance Tab — Inline script extracted from tab-governance.html.
 * 治理頁面 — 從 tab-governance.html 提取的内嵌腳本。
 *
 * MODULE_NOTE (EN): Extracted from tab-governance.html (FIX-08 file size).
 * MODULE_NOTE (中): 從 tab-governance.html 提取（FIX-08 文件大小）。
 */

// ─── Explainers ───────────────────────────────────────────────
$('explain-governance').innerHTML = ocExplain(
  '治理系统是 OpenClaw 的安全核心，通过 4 个状态机管理授权、风控、租约、对账。',
  '授权 SM (SM-01) 控制操作权限和有效期。风控 SM (SM-04) 动态调整风险等级。租约 SM (SM-02) 管理决策生命周期。对账引擎 (EX-04) 检查纸上交易与交易所的一致性。这些组件通过级联规则联动，确保整个系统始终处于安全状态。'
);

// ─── State Storage ─────────────────────────────────────────────
let _currentStatus = null;
let _currentRiskLevel = 0;

// ─── Event Log (Incident Timeline & Audit Trail) ───────────────
let _govEventLog = [];
let _prevStatus = null;
const MAX_EVENTS = 50;

// ─── Toggle Functions for Collapsible Sections ────────────────
function toggleAuthScope() {
  const body = document.getElementById('auth-scope-body');
  const toggle = document.getElementById('auth-scope-toggle');
  if (body.style.display === 'none') {
    body.style.display = '';
    toggle.textContent = '▼';
  } else {
    body.style.display = 'none';
    toggle.textContent = '▶';
  }
}

function toggleIncidentLog() {
  const body = document.getElementById('incident-log-body');
  const toggle = document.getElementById('incident-toggle');
  if (body.style.display === 'none') {
    body.style.display = '';
    toggle.textContent = '▼';
  } else {
    body.style.display = 'none';
    toggle.textContent = '▶';
  }
}

function toggleAuditTrail() {
  const body = document.getElementById('audit-trail-body');
  const toggle = document.getElementById('audit-toggle');
  if (body.style.display === 'none') {
    body.style.display = '';
    toggle.textContent = '▼';
  } else {
    body.style.display = 'none';
    toggle.textContent = '▶';
  }
}

function togglePendingApprovals() {
  const body = document.getElementById('pending-approvals-body');
  const toggle = document.getElementById('pending-toggle');
  if (body.style.display === 'none') {
    body.style.display = '';
    toggle.textContent = '▼';
  } else {
    body.style.display = 'none';
    toggle.textContent = '▶';
  }
}

// 切换租约详情列表 / Toggle lease detail list
function toggleLeaseList() {
  const body = document.getElementById('lease-list-body');
  const toggle = document.getElementById('lease-list-toggle');
  if (body.style.display === 'none') {
    body.style.display = '';
    toggle.textContent = '▼';
  } else {
    body.style.display = 'none';
    toggle.textContent = '▶';
  }
}

// 切换 PaperLiveGate 准入项目 / Toggle PaperLiveGate criteria list
function togglePLGCriteria() {
  const body = document.getElementById('plg-criteria-body');
  const toggle = document.getElementById('plg-criteria-toggle');
  if (body.style.display === 'none') {
    body.style.display = '';
    toggle.textContent = '▼';
  } else {
    body.style.display = 'none';
    toggle.textContent = '▶';
  }
}

// 切换治理事件流 / Toggle governance events feed
function toggleEventsFeed() {
  const body = document.getElementById('events-feed-body');
  const toggle = document.getElementById('events-feed-toggle');
  if (body.style.display === 'none') {
    body.style.display = '';
    toggle.textContent = '▼';
  } else {
    body.style.display = 'none';
    toggle.textContent = '▶';
  }
}

// ─── Change Detection & Event Logging ──────────────────────────
function detectChanges(newStatus) {
  if (!_prevStatus || !newStatus) { _prevStatus = newStatus; return; }
  const now = new Date().toLocaleTimeString('zh-TW');

  // Auth state change
  const oldAuth = _prevStatus.authorization?.state;
  const newAuth = newStatus.authorization?.state;
  if (oldAuth && newAuth && oldAuth !== newAuth) {
    _govEventLog.unshift({
      time: now,
      sm: 'Auth',
      severity: newAuth === 'FROZEN' ? 'bad' : newAuth === 'RESTRICTED' ? 'warn' : 'good',
      msg: 'Authorization: ' + oldAuth + ' → ' + newAuth,
      from: oldAuth,
      to: newAuth,
      initiator: 'System'
    });
  }

  // Risk level change
  const oldRisk = _prevStatus.risk?.level;
  const newRisk = newStatus.risk?.level;
  if (oldRisk !== undefined && newRisk !== undefined && oldRisk !== newRisk) {
    const NAMES = ['NORMAL','CAUTIOUS','REDUCED','DEFENSIVE','CIRCUIT_BREAKER','MANUAL_REVIEW'];
    _govEventLog.unshift({
      time: now,
      sm: 'Risk',
      severity: newRisk >= 4 ? 'bad' : newRisk >= 2 ? 'warn' : 'good',
      msg: 'Risk Level: ' + oldRisk + ' (' + (NAMES[oldRisk]||'?') + ') → ' + newRisk + ' (' + (NAMES[newRisk]||'?') + ')',
      from: NAMES[oldRisk] || String(oldRisk),
      to: NAMES[newRisk] || String(newRisk),
      initiator: newRisk > oldRisk ? 'Auto-escalation' : 'Operator'
    });
  }

  // Mode change
  const oldMode = _prevStatus.mode;
  const newMode = newStatus.mode;
  if (oldMode && newMode && oldMode !== newMode) {
    _govEventLog.unshift({
      time: now,
      sm: 'Hub',
      severity: newMode === 'FROZEN' ? 'bad' : newMode === 'RESTRICTED' ? 'warn' : 'good',
      msg: 'Governance Mode: ' + oldMode + ' → ' + newMode,
      from: oldMode,
      to: newMode,
      initiator: 'Cross-SM'
    });
  }

  // Consistency change
  const oldCon = _prevStatus.reconciliation?.is_consistent;
  const newCon = newStatus.reconciliation?.is_consistent;
  if (oldCon !== undefined && newCon !== undefined && oldCon !== newCon) {
    _govEventLog.unshift({
      time: now,
      sm: 'Recon',
      severity: newCon ? 'good' : 'bad',
      msg: 'Consistency: ' + (oldCon ? 'OK' : 'Diverged') + ' → ' + (newCon ? 'OK' : 'Diverged'),
      from: oldCon ? 'Consistent' : 'Diverged',
      to: newCon ? 'Consistent' : 'Diverged',
      initiator: 'Reconciliation'
    });
  }

  // Trim to max events
  if (_govEventLog.length > MAX_EVENTS) _govEventLog.length = MAX_EVENTS;
  _prevStatus = newStatus;
}

function renderIncidentLog() {
  const el = document.getElementById('incident-log-content');
  if (_govEventLog.length === 0) {
    el.innerHTML = '<p style="color:var(--text-dim);padding:8px">No events yet / 尚無事件。Events are detected during auto-refresh. / 事件在自動刷新時偵測。</p>'; // SAFE: static HTML only
    return;
  }
  let html = '';
  for (const e of _govEventLog) {
    html += '<div style="padding:8px 0;border-bottom:1px solid var(--border)">';
    html += '<span style="color:var(--text-dim);font-size:0.85em;margin-right:8px">' + ocEsc(e.time) + '</span>';
    html += ocChip(e.sm, 'neutral') + ' ';
    html += ocChip(e.severity === 'bad' ? 'CRITICAL' : e.severity === 'warn' ? 'WARNING' : 'INFO', e.severity) + ' ';
    html += '<span>' + ocEsc(e.msg) + '</span>';
    html += '</div>';
  }
  el.innerHTML = html;
}

// renderAuditTrail: 客户端回退渲染（使用 _govEventLog）
// Client-side fallback render using local event log (session-only data)
function renderAuditTrail() {
  const tbody = document.getElementById('audit-trail-tbody');
  if (_govEventLog.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="color:var(--text-dim)">No state changes detected / 尚未偵測到狀態變更</td></tr>'; // SAFE: static HTML only
    return;
  }
  let html = '';
  for (const e of _govEventLog) {
    html += '<tr>';
    html += '<td>' + ocEsc(e.time) + '</td>';
    html += '<td>' + ocChip(e.sm, 'neutral') + '</td>';
    html += '<td>' + ocEsc(e.msg) + '</td>';
    // 客户端日志没有 change_type，用 from→to 替代 / Client log lacks change_type; use from→to
    html += '<td>' + ocEsc(e.from || '--') + ' → ' + ocEsc(e.to || '--') + '</td>';
    html += '<td>' + ocEsc(e.initiator || '--') + '</td>';
    html += '</tr>';
  }
  tbody.innerHTML = html;
}

// loadAuditTrail: 从服务端加载持久化审计日志
// Load persistent audit trail from server; fall back to client-side log on error/empty
async function loadAuditTrail() {
  const tbody = document.getElementById('audit-trail-tbody');
  try {
    // 调用 govGetAuditChanges(limit) 获取服务端审计记录
    // Call govGetAuditChanges to retrieve server-persisted change records
    const d = await govGetAuditChanges(100);
    const records = (d && d.ok && Array.isArray(d.data)) ? d.data : [];

    if (records.length === 0) {
      // 服务端无数据，降级为客户端日志 / No server data — fall back to client-side log
      renderAuditTrail();
      return;
    }

    let html = '';
    for (const r of records) {
      // 服务端字段: timestamp, who, what, reason, change_type, old_value, new_value, auto_approved, affected_components
      // Server fields: timestamp, who, what, reason, change_type, old_value, new_value, auto_approved, affected_components
      const timeStr = r.when_ms ? ocTime(r.when_ms) : (r.when ? ocTime(r.when * 1000) : '--');
      const who = r.who || '--';
      const what = r.what || '--';
      const changeType = r.change_type || '--';
      const reason = r.reason || '--';
      const whatCn = _translateWhat(what);
      const guidance = _getApprovalGuidance(what);

      html += '<tr>';
      html += '<td style="font-size:11px;white-space:nowrap">' + ocEsc(timeStr) + '</td>';
      html += '<td>' + ocChip(ocEsc(_translateWho(who)), 'neutral') + '</td>';

      // What 列：翻译名 + 风险标签 + 可展开说明
      // What column: translated name + risk badge + expandable explanation
      html += '<td style="max-width:360px">';
      html += '<div style="font-weight:600;font-size:12px">' + ocEsc(whatCn) + '</div>';
      if (guidance) {
        // 风险标签 / Risk badge
        if (guidance.risk) {
          let riskColor = 'var(--text-dim)';
          if (guidance.risk === '高') riskColor = 'var(--red)';
          else if (guidance.risk === '中' || guidance.risk === '中-高') riskColor = 'var(--yellow, #d29922)';
          else if (guidance.risk === '低' || guidance.risk === '低-中') riskColor = 'var(--green)';
          else if (guidance.risk === '无') riskColor = 'var(--text-dim)';
          html += '<span style="display:inline-block;margin:2px 0;padding:1px 6px;border-radius:3px;font-size:9px;font-weight:600;'
            + 'background:' + riskColor + '22;color:' + riskColor + '">风险：' + ocEsc(guidance.risk) + '</span> ';
        }
        // 正式说明（始终可见）/ Formal detail (always visible)
        if (guidance.detail) {
          html += '<div style="font-size:10px;color:var(--text-dim);margin-top:2px;line-height:1.5">' + ocEsc(guidance.detail) + '</div>';
        }
        // 通俗解释（折叠）/ Plain-language explanation (collapsed)
        if (guidance.explain) {
          html += '<details style="margin-top:3px;font-size:10px"><summary style="cursor:pointer;color:var(--accent);user-select:none">'
            + '详细说明</summary>'
            + '<div style="margin-top:4px;padding:6px 8px;background:var(--card-bg);border:1px solid var(--border);border-radius:4px;color:var(--text);line-height:1.7;white-space:pre-line">'
            + ocEsc(guidance.explain) + '</div></details>';
        }
      }
      html += '</td>';

      html += '<td>' + ocChip(ocEsc(changeType), 'info') + '</td>';
      html += '<td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-dim);font-size:11px" title="' + ocEsc(reason) + '">' + ocEsc(reason) + '</td>';
      html += '</tr>';
    }
    tbody.innerHTML = html;
  } catch (e) {
    // 请求失败，降级为客户端日志 / Request failed — fall back to client-side log
    console.warn('Audit trail server load failed, using client-side fallback:', e);
    renderAuditTrail();
  }
}

// ─── Modal Functions ──────────────────────────────────────────

// showRequestAuthModal: 显示授权申请弹窗（DRAFT → PENDING_APPROVAL 流程）
// Show the Request Authorization modal to initiate SM-01 DRAFT → PENDING_APPROVAL flow
function showRequestAuthModal() {
  // 重置表单并显示授权申请弹窗 / Reset form and show modal
  $('request-auth-ttl').value = '24';
  $('request-auth-reason').value = '';
  $('modal-request-auth').style.display = 'flex';
}

// hideRequestAuthModal: 关闭授权申请弹窗
// Hide the Request Authorization modal
function hideRequestAuthModal() {
  $('modal-request-auth').style.display = 'none';
}

// submitRequestAuth: 提交授权申请（POST /api/v1/governance/auth/request）
// Submit the authorization request; on success reload data and close modal
async function submitRequestAuth() {
  const ttl = parseInt($('request-auth-ttl').value) || 24;
  const reason = $('request-auth-reason').value.trim();
  if (!reason) {
    ocToast('请输入申请原因 / Please enter a reason', 'error');
    return;
  }
  const d = await govRequestAuthorization(ttl, reason);
  if (d && d.ok) {
    ocToast('授权申请已提交，等待审批 / Authorization request submitted', 'success');
    hideRequestAuthModal();
    loadAll();
  } else {
    ocToast((d && d.message) ? d.message : '申请失败 / Request failed', 'error');
  }
}

function showApprovalModal() {
  $('approve-note').value = '';
  $('modal-approve').style.display = 'flex';
}

function hideApprovalModal() {
  $('modal-approve').style.display = 'none';
}

function showOverrideModal() {
  $('override-level').value = '';
  $('override-reason').value = '';
  $('modal-override').style.display = 'flex';
}

function hideOverrideModal() {
  $('modal-override').style.display = 'none';
}

function showReconcileModal() {
  $('reconcile-reason').value = '';
  $('modal-reconcile').style.display = 'flex';
}

function hideReconcileModal() {
  $('modal-reconcile').style.display = 'none';
}

// ─── Form Submission ──────────────────────────────────────────
async function submitApproval() {
  const note = $('approve-note').value.trim();
  if (!note) {
    ocToast('Please enter an approval note / 请输入批准备注', 'error');
    return;
  }

  const d = await govPostApprove(note);
  if (d && d.ok) {
    ocToast('Authorization approved / 授权已批准', 'success');
    hideApprovalModal();
    loadAll();
  } else {
    ocToast(d ? d.message : 'Approval failed / 批准失败', 'error');
  }
}

async function submitOverride() {
  const level = $('override-level').value;
  const reason = $('override-reason').value.trim();

  if (!level) {
    ocToast('Please select target level / 请选择目标等级', 'error');
    return;
  }
  if (!reason) {
    ocToast('Please enter a reason / 请输入原因', 'error');
    return;
  }

  const d = await govPostOverride(level, reason);
  if (d && d.ok) {
    ocToast('Risk level de-escalated / 风险等级已降级', 'success');
    hideOverrideModal();
    loadAll();
  } else {
    ocToast(d ? d.message : 'Override failed / 降级失败', 'error');
  }
}

async function submitReconcile() {
  const reason = $('reconcile-reason').value.trim();
  if (!reason) {
    ocToast('Please enter a reason / 请输入原因', 'error');
    return;
  }

  const d = await govPostReconcile(reason);
  if (d && d.ok) {
    ocToast('Reconciliation triggered / 对账已触发', 'success');
    hideReconcileModal();
    loadAll();
  } else {
    ocToast(d ? d.message : 'Reconciliation failed / 对账失败', 'error');
  }
}

// ─── Render Functions ─────────────────────────────────────────

function renderAuthScope(scope) {
  const el = document.getElementById('auth-scope-content');
  if (!scope || Object.keys(scope).length === 0) {
    el.innerHTML = '<p style="color:var(--text-dim);font-size:12px">No scope data / 無範圍資料</p>'; // SAFE: static HTML only
    return;
  }

  let html = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px">';

  // Render each scope key as a card
  for (const [key, value] of Object.entries(scope)) {
    const label = ocEsc(key.replace(/_/g, ' '));
    let valueDisplay;

    if (typeof value === 'boolean') {
      valueDisplay = value ? ocChip('✓ Allowed / 允許', 'good') : ocChip('✗ Denied / 拒絕', 'bad');
    } else if (Array.isArray(value)) {
      valueDisplay = value.map(v => ocChip(ocEsc(String(v)), 'neutral')).join(' ');
    } else if (typeof value === 'object' && value !== null) {
      valueDisplay = '<pre style="font-size:0.8em;margin:4px 0;overflow-x:auto">' + ocEsc(JSON.stringify(value, null, 2)) + '</pre>';
    } else {
      valueDisplay = ocChip(ocEsc(String(value)), 'neutral');
    }

    html += '<div style="background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:10px">';
    html += '<div style="font-size:0.85em;color:var(--text-dim);margin-bottom:4px;text-transform:capitalize">' + label + '</div>';
    html += '<div>' + valueDisplay + '</div>';
    html += '</div>';
  }

  html += '</div>';
  el.innerHTML = html;
}

async function loadAuthScope() {
  try {
    const d = await govGetAuthStatus();
    if (d && d.ok && d.data) {
      renderAuthScope(d.data.scope);
    }
  } catch(e) {
    console.warn('Auth scope unavailable:', e);
  }
}

function renderAuthCard(authData) {
  if (!authData) {
    ocSetHtml('auth-state-badge', ocChip('UNAVAILABLE', 'neutral'));
    ocSetText('auth-expiry', '--');
    ocSetText('auth-state-desc', '');
    renderAuthScope({});
    $('btn-approve').style.display = 'none';
    $('btn-request-auth').style.display = 'none';
    $('auth-pending-indicator').style.display = 'none';
    return;
  }

  const state = authData.state || 'UNKNOWN';
  ocSetHtml('auth-state-badge', govAuthBadge(state));

  const expiresMs = authData.expires_at_ms;
  // ACTIVE → show expiry countdown; other states → hide expiry
  // ACTIVE 显示过期倒计时；其他状态不显示
  ocSetText('auth-expiry', (state === 'ACTIVE' && expiresMs) ? govExpiryCountdown(expiresMs) : '--');

  // State description text / 各状态说明文字
  const AUTH_DESC = {
    NONE:             '无授权对象 No authorization object',
    DRAFT:            '草稿待提交 Draft pending submission',
    PENDING_APPROVAL: '等待操作员审批 Awaiting Operator approval',
    ACTIVE:           '',   // expiry countdown is shown instead / 显示过期倒计时，无需额外说明
    RESTRICTED:       '受限运行 Restricted operation',
    FROZEN:           '已冻结 Frozen — no trading allowed',
    EXPIRED:          '已过期，需重新申请 Re-authorization required',
    REVOKED:          '已吊销，需重新申请 Re-authorization required',
    REJECTED:         '已拒绝，需重新申请 Re-authorization required',
  };
  ocSetText('auth-state-desc', AUTH_DESC[state] || '');

  // Render scope using the new visualizer
  const scope = authData.scope || {};
  renderAuthScope(scope);

  const isPending = authData.pending_approval === true;
  $('auth-pending-indicator').style.display = isPending ? 'block' : 'none';
  $('btn-approve').style.display = isPending ? '' : 'none';

  // Show "Request Authorization" button for states that need a fresh auth object
  // 无授权、草稿、已过期/吊销/拒绝 时显示申请授权按钮
  const needsRequest = ['NONE', 'DRAFT', 'EXPIRED', 'REVOKED', 'REJECTED'].includes(state);
  $('btn-request-auth').style.display = needsRequest ? '' : 'none';
}

function renderRiskCard(riskData) {
  if (!riskData) {
    ocSetHtml('risk-level-badge', ocChip('UNAVAILABLE', 'neutral'));
    ocSetHtml('risk-mode-badge', ocChip('--', 'neutral'));
    ocSetText('risk-reason', '--');
    return;
  }

  const level = riskData.level != null ? riskData.level : 0;
  _currentRiskLevel = level;

  ocSetHtml('risk-level-badge', govRiskBadge(level));

  const mode = riskData.mode || 'UNKNOWN';
  ocSetHtml('risk-mode-badge', govModeBadge(mode));

  const reason = riskData.escalation_reason || '--';
  ocSetText('risk-reason', ocEsc(reason));

  // Populate override dropdown with lower levels
  const selectEl = $('override-level');
  selectEl.innerHTML = '<option value="">-- Select Level --</option>'; // SAFE: static HTML only
  for (let i = 0; i < level; i++) {
    const levelName = GOV_RISK_LEVELS[i] || 'LEVEL_' + i;
    selectEl.innerHTML += '<option value="' + ocEsc(levelName) + '">' + i + ' — ' + ocEsc(levelName) + '</option>'; /* APR01-MEDIUM-4 XSS fix */
  }

  // Disable override button if already at NORMAL
  $('btn-override').disabled = (level === 0);
}

// renderLeaseList: 渲染活跃租约详情列表
// Render the collapsible active lease detail list
function renderLeaseList(leases) {
  const el = document.getElementById('lease-list-content');
  if (!leases || leases.length === 0) {
    el.innerHTML = '<p style="color:var(--text-dim);font-size:12px;padding:4px 0">暫無活躍租約 No active leases</p>'; // SAFE: static HTML only
    return;
  }

  const now = Date.now();
  let html = '<div style="display:flex;flex-direction:column;gap:6px">';
  for (const lease of leases) {
    // lease_id 缩短为最后 8 位 / Truncate lease_id to last 8 chars
    const shortId = (lease.lease_id || lease.id || '--').slice(-8);
    const symbol = lease.symbol || '--';
    const direction = lease.direction || '--';
    const strategy = lease.strategy || '--';

    // 计算过期倒计时 / Calculate expiry countdown
    let expiryStr = '--';
    const expiresAt = lease.expires_at_ms || lease.expires_at;
    if (expiresAt) {
      const expiresMs = typeof expiresAt === 'number' ? expiresAt : new Date(expiresAt).getTime();
      const diffSec = Math.round((expiresMs - now) / 1000);
      if (diffSec <= 0) {
        expiryStr = ocChip('Expired / 已过期', 'bad');
      } else if (diffSec < 60) {
        expiryStr = ocChip(diffSec + 's', 'warn');
      } else {
        expiryStr = ocChip(Math.round(diffSec / 60) + 'm', 'good');
      }
    }

    html += '<div style="background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:8px 10px;font-size:12px">';
    html += '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:4px">';
    html += '<span style="font-family:monospace;color:var(--text-dim)">' + ocEsc('…' + shortId) + '</span>';
    html += ocChip(ocEsc(symbol), 'info') + ' ';
    html += ocChip(ocEsc(direction), direction === 'Buy' || direction === 'buy' ? 'good' : 'bad') + ' ';
    html += '<span style="color:var(--text-dim);font-size:11px">' + ocEsc(strategy) + '</span>';
    html += '<span>Expires: ' + expiryStr + '</span>';
    html += '</div>';
    html += '</div>';
  }
  html += '</div>';
  el.innerHTML = html;
}

function renderLeaseCard(leaseData) {
  if (!leaseData) {
    ocSetText('lease-active', '--');
    ocSetText('lease-total', '--');
    return;
  }

  const activeCount = leaseData.active_count != null ? leaseData.active_count : 0;
  const totalCount = leaseData.total_tracked != null ? leaseData.total_tracked : 0;

  ocSetText('lease-active', String(activeCount));
  ocSetText('lease-total', String(totalCount));
}

function renderReconCard(reconData) {
  if (!reconData) {
    ocSetHtml('recon-consistency', ocChip('UNAVAILABLE', 'neutral'));
    ocSetText('recon-time', '--');
    ocSetText('recon-result', '--');
    return;
  }

  const isConsistent = reconData.is_consistent;
  ocSetHtml('recon-consistency', govConsistencyIcon(isConsistent));

  const lastMs = reconData.last_check_ms;
  ocSetText('recon-time', lastMs ? ocTime(lastMs) : '--');

  const result = reconData.last_result || '--';
  ocSetText('recon-result', ocEsc(result));
}

function renderSummary(fullStatus) {
  const enabled = fullStatus.enabled === true;
  const mode = fullStatus.mode || 'UNKNOWN';
  const incidents = fullStatus.incidents || 0;
  const errors = fullStatus.callback_errors || 0;
  const timestamp = fullStatus.timestamp_ms;

  ocSetHtml('summary-enabled', ocChip(enabled ? 'Yes' : 'No', enabled ? 'good' : 'warn'));
  ocSetHtml('summary-mode', govModeBadge(mode));
  ocSetText('summary-incidents', String(incidents));
  ocSetText('summary-errors', String(errors));
  ocSetText('summary-time', timestamp ? ocTimeShort(timestamp) : '--');
}

// ─── PaperLiveGate Functions ──────────────────────────────────────

// PLG 状态徽章颜色映射 / Badge color for gate status
function _plgStatusColor(status) {
  if (!status) return 'neutral';
  const s = status.toUpperCase();
  if (s === 'OPEN' || s === 'APPROVED') return 'good';
  if (s === 'BLOCKED') return 'bad';
  if (s === 'EVALUATING') return 'warn';
  return 'neutral'; // CLOSED or unknown
}

// loadPaperLiveGate: 加载 Paper→Live 门禁状态
// Load Paper→Live gate status from server
async function loadPaperLiveGate() {
  try {
    // GET /api/v1/governance/paper-live-gate/status
    const d = await ocApi('/api/v1/governance/paper-live-gate/status');
    if (!d || !d.ok) {
      ocSetHtml('plg-status-badge', ocChip('Unavailable / 不可用', 'neutral'));
      ocSetText('plg-score', '--');
      document.getElementById('plg-criteria-list').innerHTML =
        '<p style="color:var(--text-dim);font-size:12px">Data unavailable / 数据不可用</p>'; // SAFE: static HTML only
      return;
    }

    const data = d.data || d;
    const status = data.status || 'UNKNOWN';
    const passedCount = data.passed_count != null ? data.passed_count : '--';
    const totalCount = data.total_count != null ? data.total_count : '--';
    const criteria = Array.isArray(data.criteria) ? data.criteria : [];

    // 渲染状态徽章和评分 / Render status badge and score
    ocSetHtml('plg-status-badge', ocChip(ocEsc(status), _plgStatusColor(status)));
    ocSetText('plg-score', passedCount + '/' + totalCount + ' 通过');

    // 渲染准入项目列表 / Render criteria list
    if (criteria.length === 0) {
      document.getElementById('plg-criteria-list').innerHTML =
        '<p style="color:var(--text-dim);font-size:12px">No criteria data / 无准入项目数据</p>'; // SAFE: static HTML only
    } else {
      let html = '<div style="display:flex;flex-direction:column;gap:6px">';
      for (const c of criteria) {
        const icon = c.passed ? '✅' : '❌';
        const name = c.name || '--';
        const reason = c.reason || '';
        html += '<div style="display:flex;align-items:flex-start;gap:8px;font-size:12px;padding:4px 0;border-bottom:1px solid var(--border)">';
        html += '<span style="flex-shrink:0">' + icon + '</span>';
        html += '<div>';
        html += '<div style="font-weight:' + (c.passed ? '400' : '600') + ';color:' + (c.passed ? 'inherit' : 'var(--red)') + '">' + ocEsc(name) + '</div>';
        if (reason) {
          html += '<div style="color:var(--text-dim);font-size:11px">' + ocEsc(reason) + '</div>';
        }
        html += '</div>';
        html += '</div>';
      }
      html += '</div>';
      document.getElementById('plg-criteria-list').innerHTML = html;
    }
  } catch (e) {
    console.warn('PaperLiveGate load failed:', e);
    ocSetHtml('plg-status-badge', ocChip('Error / 错误', 'bad'));
  }
}

// evaluatePaperLiveGate: 触发准入评估，自动从 Paper Engine 读取当前指标作为评估参数
// Trigger PaperLiveGate evaluation — auto-fills required metrics from Paper Engine status
async function evaluatePaperLiveGate() {
  ocToast('读取指标中... / Fetching metrics...', 'info');
  try {
    // Step 1: Fetch current paper engine metrics to fill required fields
    // 第一步：拉取 Paper Engine 当前指标填充必填字段
    let metrics = {
      paper_start_time_ms: Date.now() - 86400000, // fallback: 1 day ago / 回退：1 天前
      total_trades: 0,
      win_rate_percent: 0,
      net_pnl: 0,
      sharpe_ratio: 0,
      max_drawdown_percent: 0,
      profit_factor: 0,
    };

    try {
      const pe = await ocApi('/api/v1/paper/status');
      if (pe && pe.data) {
        const m = pe.data.metrics || pe.data;
        // Map Paper Engine metric fields to PaperLiveGate requirements
        // 映射 Paper Engine 指标字段到 PaperLiveGate 必填参数
        if (m.start_time_ms != null)       metrics.paper_start_time_ms = m.start_time_ms;
        if (m.total_trades != null)         metrics.total_trades = m.total_trades;
        if (m.win_rate != null)             metrics.win_rate_percent = m.win_rate * 100;
        if (m.win_rate_pct != null)         metrics.win_rate_percent = m.win_rate_pct;
        if (m.net_pnl != null)              metrics.net_pnl = m.net_pnl;
        if (m.sharpe_ratio != null)         metrics.sharpe_ratio = m.sharpe_ratio;
        if (m.max_drawdown_pct != null)     metrics.max_drawdown_percent = m.max_drawdown_pct;
        if (m.profit_factor != null)        metrics.profit_factor = m.profit_factor;
      }
    } catch (fetchErr) {
      console.warn('Could not fetch paper metrics, using defaults:', fetchErr);
    }

    // Step 2: POST evaluation request with populated metrics
    // 第二步：发送携带真实指标的评估请求
    ocToast('评估中... / Evaluating...', 'info');
    const d = await ocPost('/api/v1/governance/paper-live-gate/evaluate', metrics);
    if (d && d.ok) {
      ocToast('Evaluation complete / 评估完成', 'success');
      await loadPaperLiveGate();
      // A3: Auto-expand criteria list after evaluation so operator can see results immediately
      // A3: 评估完成后自动展开准入项目列表，让操作员立即看到结果
      const criteriaBody = document.getElementById('plg-criteria-body');
      const criteriaToggle = document.getElementById('plg-criteria-toggle');
      if (criteriaBody) { criteriaBody.style.display = ''; }
      if (criteriaToggle) { criteriaToggle.textContent = '▼'; }
    } else {
      ocToast((d && d.message) ? d.message : 'Evaluation failed / 评估失败', 'error');
    }
  } catch (e) {
    console.warn('PLG evaluate failed:', e);
    ocToast('Evaluation request failed / 评估请求失败', 'error');
  }
}

// ─── Learning Tier Functions ──────────────────────────────────────

// 层级徽章颜色映射 / Badge color for learning tier
function _ltTierColor(tier) {
  if (!tier) return 'neutral';
  const t = String(tier).toUpperCase();
  if (t === 'L0') return 'neutral';
  if (t === 'L1') return 'good';
  if (t === 'L2') return 'good';
  if (t === 'L3') return 'info';
  return 'warn'; // L4+
}

// loadLearningTier: 加载学习层级状态
// Load learning tier status from server
async function loadLearningTier() {
  try {
    // 调用 governance.js 中的 govGetLearningTier()
    // Call govGetLearningTier() from governance.js
    const d = await govGetLearningTier();
    if (!d || !d.ok) {
      ocSetHtml('lt-tier', ocChip('Unavailable / 不可用', 'neutral'));
      ocSetText('lt-obs', '--');
      ocSetText('lt-winrate', '--');
      ocSetHtml('lt-eligible', ocChip('Unknown / 未知', 'neutral'));
      return;
    }

    const data = d.data || d;
    const tier = data.current_tier || 'L0';
    const obsCount = data.observation_count != null ? data.observation_count : 0;
    const winRate = data.win_rate != null ? data.win_rate : null;
    const eligible = data.eligible_for_promotion === true;
    const nextReqs = data.next_tier_requirements || {};

    // 渲染层级、观测数、胜率 / Render tier, observation count, win rate
    ocSetHtml('lt-tier', ocChip(ocEsc(tier), _ltTierColor(tier)));
    ocSetText('lt-obs', String(obsCount));
    ocSetText('lt-winrate', winRate != null ? (winRate * 100).toFixed(1) + '%' : '--');

    // 进度条：基于下一层级所需观测数 / Progress bar based on next tier observation requirement
    const obsRequired = nextReqs.observations || nextReqs.min_observations || 0;
    const pct = obsRequired > 0 ? Math.min(100, Math.round((obsCount / obsRequired) * 100)) : (eligible ? 100 : 0);
    document.getElementById('lt-progress').style.width = pct + '%';

    // 资格徽章 / Eligibility badge
    ocSetHtml('lt-eligible', ocChip(
      eligible ? '可晋升 Eligible' : '未达标 Not yet',
      eligible ? 'good' : 'neutral'
    ));

    // 晋升按钮仅在可晋升时显示 / Show promote button only when eligible
    const btn = document.getElementById('btn-promote');
    if (btn) btn.style.display = eligible ? '' : 'none';

    // A3: Dynamically filter promote dropdown to only show tiers ABOVE current
    // A3: 动态过滤晋升下拉，只显示高于当前层级的选项（防止误操作降级）
    const tierSelect = document.getElementById('promote-tier');
    if (tierSelect) {
      const tierOrder = { L0: 0, L1: 1, L2: 2, L3: 3, L4: 4, L5: 5 };
      const currentNum = tierOrder[tier] != null ? tierOrder[tier] : 0;
      const allTiers = [
        { value: 'L1', label: 'L1 — Local Ollama' },
        { value: 'L2', label: 'L2 — Cloud AI' },
        { value: 'L3', label: 'L3 — Advanced AI' },
        { value: 'L4', label: 'L4 — Strategy Optimizer' },
        { value: 'L5', label: 'L5 — Full Autonomy' },
      ];
      tierSelect.innerHTML = '<option value="">-- Select Tier --</option>'; // SAFE: static HTML only
      for (const t of allTiers) {
        const tNum = tierOrder[t.value] || 0;
        if (tNum > currentNum) {
          tierSelect.innerHTML += '<option value="' + t.value + '">' + t.label + '</option>';
        }
      }
    }

  } catch (e) {
    console.warn('Learning tier load failed:', e);
    ocSetHtml('lt-tier', ocChip('Error / 错误', 'bad'));
  }
}

// showPromoteModal / hidePromoteModal: 晋升确认弹窗
// Show/hide the manual tier promotion modal
function showPromoteModal() {
  const el = document.getElementById('promote-tier');
  if (el) el.value = '';
  const re = document.getElementById('promote-reason');
  if (re) re.value = '';
  document.getElementById('modal-promote').style.display = 'flex';
}

function hidePromoteModal() {
  document.getElementById('modal-promote').style.display = 'none';
}

// submitPromotion: 提交手动晋升请求
// Submit a manual learning tier promotion
async function submitPromotion() {
  const targetTier = document.getElementById('promote-tier').value;
  const reason = document.getElementById('promote-reason').value.trim();

  if (!targetTier) {
    ocToast('Please select a target tier / 请选择目标层级', 'error');
    return;
  }
  if (!reason) {
    ocToast('Please enter a reason / 请输入原因', 'error');
    return;
  }

  // 调用 governance.js 中的 govPromoteLearningTier()
  // Call govPromoteLearningTier() from governance.js
  const d = await govPromoteLearningTier(targetTier, reason);
  if (d && d.ok) {
    ocToast('Promotion submitted / 晋升请求已提交', 'success');
    hidePromoteModal();
    await loadLearningTier();
  } else {
    ocToast((d && d.message) ? d.message : 'Promotion failed / 晋升失败', 'error');
  }
}

// ─── Events Feed Functions ────────────────────────────────────────

// loadEventsFeed: 加载服务端治理事件流
// Load governance event history from server
async function loadEventsFeed(limit) {
  const lim = limit || 50;
  const el = document.getElementById('events-feed-content');
  try {
    // 调用 governance.js 中的 govGetEvents(limit)
    // Call govGetEvents(limit) from governance.js
    const d = await govGetEvents(lim);
    // Backend: {data: {events: [...], count, limit}} — extract nested array
    // 后端返回 {data: {events: [...], count, limit}}，提取内层数组
    const events = (d && d.ok && d.data && Array.isArray(d.data.events)) ? d.data.events : [];

    if (events.length === 0) {
      el.innerHTML = '<p style="color:var(--text-dim);font-size:12px;padding:8px">No events yet / 暂无事件</p>'; // SAFE: static HTML only
      return;
    }

    let html = '';
    for (const ev of events) {
      // 服务端事件字段: timestamp/time, event_type/type, description/message
      // Server event fields: timestamp/time, event_type/type, description/message
      const ts = ev.timestamp || ev.time || ev.ts;
      const timeStr = ts ? ocTime(ts) : '--';
      const evType = ev.event_type || ev.type || 'EVENT';
      const desc = ev.description || ev.message || ev.msg || '';

      // 根据事件类型选择颜色 / Choose color by event type
      let chipColor = 'neutral';
      const evUpper = evType.toUpperCase();
      if (evUpper.includes('ERROR') || evUpper.includes('FAIL') || evUpper.includes('CIRCUIT')) chipColor = 'bad';
      else if (evUpper.includes('WARN') || evUpper.includes('ESCALAT') || evUpper.includes('REDUCE')) chipColor = 'warn';
      else if (evUpper.includes('APPROV') || evUpper.includes('SUCCESS') || evUpper.includes('OK')) chipColor = 'good';

      html += '<div style="padding:8px 0;border-bottom:1px solid var(--border)">';
      html += '<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:4px">';
      html += '<span style="color:var(--text-dim);font-size:11px;white-space:nowrap">' + ocEsc(timeStr) + '</span>';
      html += ocChip(ocEsc(evType), chipColor);
      html += '</div>';
      if (desc) {
        html += '<div style="font-size:12px;color:var(--text-dim)">' + ocEsc(desc) + '</div>';
      }
      html += '</div>';
    }
    el.innerHTML = html;
  } catch (e) {
    console.warn('Events feed load failed:', e);
    el.innerHTML = '<p style="color:var(--text-dim);font-size:12px;padding:8px">Failed to load events / 事件加载失败</p>'; // SAFE: static HTML only
  }
}

function showUnavailable() {
  const unavailMsg = ocChip('Governance Hub Not Available / 治理中枢未启用', 'warn');

  // Clear all cards
  $('auth-state-badge').innerHTML = unavailMsg;
  $('risk-level-badge').innerHTML = unavailMsg;
  $('lease-active').textContent = '--';
  $('lease-total').textContent = '--';
  $('recon-consistency').innerHTML = unavailMsg;

  // Hide action buttons
  $('btn-approve').disabled = true;
  $('btn-request-auth').disabled = true;
  $('btn-override').disabled = true;
  $('btn-reconcile').disabled = true;
}

// ─── Pending Approvals Rendering ───────────────────────────────────
function renderPendingRecovery(requests) {
  const el = document.getElementById('pending-recovery-content');
  if (!requests || requests.length === 0) {
    el.innerHTML = '<p style="color:var(--text-dim);font-size:12px">目前没有待审批的恢复请求</p>'; // SAFE: static HTML only
    return;
  }

  const _RECOVERY_STATUS_CN = { PENDING: '待批准', APPROVED: '已批准', REJECTED: '已拒绝', EXPIRED: '已过期' };

  let html = '<div style="display:flex;flex-direction:column;gap:8px">';
  for (const req of requests) {
    const statusCn = _RECOVERY_STATUS_CN[req.status] || req.status || '待批准';
    html += '<div style="background:var(--card-bg);border:1px solid var(--border);border-radius:6px;padding:12px;font-size:12px">';
    html += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">' + ocChip(statusCn, 'warn') + '</div>';
    html += '<div style="font-weight:600;margin-bottom:4px">' + ocEsc(req.description || '系统请求恢复到安全状态') + '</div>';
    html += '<div style="margin-top:8px;padding:8px;background:rgba(56,139,253,0.06);border-radius:6px;font-size:11px;color:var(--text-dim);line-height:1.6">'
      + '批准 = 允许系统从异常状态恢复；拒绝 = 保持当前状态不变。'
      + '</div>';
    html += '<div style="display:flex;gap:8px;margin-top:8px">';
    var _reqIdJs = (req.request_id || req.id || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'"); /* APR01-MEDIUM-4 XSS fix: JS string escape */
    html += '<button class="oc-btn oc-btn-success" style="font-size:11px;padding:5px 16px" onclick="confirmApproveRecovery(\'' + ocEsc(_reqIdJs) + '\')">✔ 批准恢复</button>';
    html += '</div>';
    html += '<div style="font-size:10px;color:var(--text-dim);margin-top:6px;opacity:0.6">ID: ' + ocEsc(req.request_id || req.id || '--') + '</div>';
    html += '</div>';
  }
  html += '</div>';
  el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════════════
// 审计变更 完整翻译系统 / Audit Change Complete Translation System
// 覆盖所有 record_change() 调用来源，确保 Operator 能看懂每一条记录
// ═══════════════════════════════════════════════════════════════════════

// ── 变更类型 Change Type ──
const _CHANGE_TYPE_LABELS = {
  STATE_CHANGE:      '状态变更',
  CONFIG_CHANGE:     '配置变更',
  PARAMETER_CHANGE:  '参数变更',
  RISK_OVERRIDE:     '风控覆盖',
  PERMISSION_CHANGE: '权限变更',
  CODE_DEPLOYMENT:   '代码部署',
  ROLLBACK:          '回滚',
  EMERGENCY_CHANGE:  '紧急变更',
};

// ── 审批状态 Approval Status ──
const _APPROVAL_STATUS_CN = {
  PENDING:            '待批准',
  AUTO_APPROVED:      '系统自动批准',
  APPROVED:           '已批准',
  REJECTED:           '已拒绝',
  EMERGENCY_BYPASSED: '紧急跳过（需事后补批）',
};

function _changeTypeBadge(ct) {
  const label = _CHANGE_TYPE_LABELS[ct] || ct || '未知';
  const isRisk = ct === 'RISK_OVERRIDE' || ct === 'EMERGENCY_CHANGE';
  return ocChip(label, isRisk ? 'bad' : 'info');
}

// ── 授权状态值 Authorization State Values ──
const _AUTH_STATE_CN = {
  DRAFT: '草稿', PENDING_APPROVAL: '待批准', ACTIVE: '生效中', SUSPENDED: '已暂停',
  FROZEN: '已冻结', EXPIRED: '已过期', REVOKED: '已撤销',
  NOT_REQUESTED: '未申请', REQUESTED: '已申请', APPROVED: '已批准', DENIED: '已拒绝',
};

// ── 风控等级 Risk Level ──
const _RISK_LEVEL_CN = {
  NORMAL: '正常（无限制）', CAUTIOUS: '谨慎（降低仓位）', REDUCED: '缩减（限制开仓）',
  DEFENSIVE: '防御（只许平仓）', CIRCUIT_BREAKER: '熔断（全部冻结）', MANUAL_REVIEW: '人工审核（全停）',
};

// ── 订单状态 OMS Order State ──
const _OMS_STATE_CN = {
  PENDING_NEW: '等待提交', ACCEPTED: '已接受', REJECTED: '被拒绝', PARTIALLY_FILLED: '部分成交',
  FILLED: '完全成交', PENDING_CANCEL: '等待取消', CANCELLED: '已取消',
  EXPIRED: '已过期', FAILED: '失败', PENDING_AMEND: '等待修改', AMENDED: '已修改',
};

// ── 决策租约状态 Decision Lease State ──
const _LEASE_STATE_CN = {
  IDLE: '空闲', REQUESTED: '已请求', ACTIVE: '生效中', EXECUTING: '执行中',
  COMPLETED: '已完成', EXPIRED: '已过期', REVOKED: '已撤销', FAILED: '失败',
};

// ── 组件名 Component Names ──
const _COMP_CN = {
  risk_manager: '风控管理器', RiskManager: '风控管理器', RiskGovernor: '风控治理器',
  PaperTradingEngine: 'Paper 模拟引擎', paper_engine: 'Paper 模拟引擎',
  governance_hub: '治理中枢', GovernanceHub: '治理中枢',
  linear: '合约(USDT)', spot: '现货', inverse: '反向合约', option: '期权',
  Authorization: '授权系统', DecisionLease: '决策租约', OMS: '订单管理',
};
function _translateComp(c) { return _COMP_CN[c] || c; }

// ── 发起人 Who ──
function _translateWho(who) {
  if (!who) return '--';
  if (who === 'demo-operator' || who === 'operator') return '操作员 Operator';
  if (who === 'system' || who === 'SYSTEM') return '系统自动 System';
  if (who === 'GovernanceHub') return '治理中枢 GovernanceHub';
  if (who === 'RiskManager') return '风控管理器 RiskManager';
  if (who === 'PaperLiveGate') return 'Paper→Live 准入门控';
  if (who.toLowerCase().includes('agent')) return 'AI Agent 代理';
  return who;
}

// 翻译一个状态值（尝试所有状态字典）
function _translateStateVal(val) {
  if (!val || typeof val !== 'string') return val;
  return _AUTH_STATE_CN[val] || _RISK_LEVEL_CN[val] || _OMS_STATE_CN[val] || _LEASE_STATE_CN[val] || val;
}

// ── 核心：what 描述翻译 + 审批后果说明 ──
// 每条规则：{ pattern, cn: 中文描述, approve: 批准后果, reject: 拒绝后果 }
// 覆盖所有 record_change() 调用产生的 what 文本
const _WHAT_RULES = [

  // ═══ 1. 对账不一致 ═══
  { pattern: /^Reconciliation mismatch detected: (.+)$/,
    cn: (m) => '账目核对发现差异 — 严重性：' + m[1],
    risk: '中-高',
    detail: '系统核对本地持仓/订单记录与交易所实际状态时发现不一致。差异可能影响风险敞口计算的准确性。CRITICAL 级别将自动提升风控等级。',
    explain: '系统会定期把"我们自己记录的持仓和订单"与"交易所那边实际的数据"做对比。如果两边对不上，就说明某处出了偏差。\n\n'
      + '常见原因：网络延迟导致同步滞后、交易所端订单被手动修改、系统重启后部分状态未恢复。\n\n'
      + '如果差异涉及持仓数量，意味着我们以为的风险和实际风险可能不同——这种情况需要尽快排查。',
    approve: '确认差异已知晓，系统继续运行。CRITICAL 级别将自动触发风控升级。',
    reject: '标记为需进一步调查。系统不停止，但记录保持待处理状态。',
  },

  // ═══ 2. 授权冻结 ═══
  { pattern: /^Authorization frozen: (\d+) active leases revoked$/,
    cn: (m) => '授权已冻结 — ' + m[1] + ' 个交易许可已撤销',
    risk: '高',
    detail: '系统检测到严重异常，已执行紧急冻结。所有进行中的交易许可被强制撤销，系统停止接受新交易指令。需在「授权管理」区域手动恢复。',
    explain: '这相当于按下了"紧急暂停键"。当系统发现严重问题（比如风控连续告警、对账严重不一致）时，会自动冻结一切交易活动来保护账户。\n\n'
      + '冻结后，AI 无法再执行任何新的买卖操作，直到你手动排查问题并在上方「授权管理」区域恢复授权。\n\n'
      + '注意：拒绝此记录不会解除冻结——冻结只能通过手动操作恢复。',
    approve: '确认冻结必要，系统保持冻结状态。',
    reject: '记录异议，但系统仍保持冻结。解冻需在「授权管理」中手动操作。',
  },

  // ═══ 3. 授权缓存刷新 ═══
  { pattern: /^Authorization cache invalidated$/,
    cn: () => '授权缓存已刷新',
    risk: '无',
    detail: '授权状态变更后，内部缓存已自动清理并重新加载。属于正常系统维护操作，无需人工干预。',
    explain: '这是系统内部的"自动刷新"。每次授权状态发生变化（比如从"待审批"变成"已激活"），系统需要清理旧的缓存数据，确保所有模块读到的都是最新状态。\n\n'
      + '你通常不需要对这条记录做任何操作——除非你最近没有做过任何授权变更却频繁看到此记录，那可能意味着有程序异常。',
    approve: '确认知晓，无需后续操作。',
    reject: '标记异常。仅在未预期出现此记录时使用。',
  },

  // ═══ 4. 风控等级变更 ═══
  { pattern: /^Risk level changed: (.+) → (.+)$/,
    cn: (m) => '风控保护等级调整：' + (_RISK_LEVEL_CN[m[1]] || m[1]) + ' → ' + (_RISK_LEVEL_CN[m[2]] || m[2]),
    risk: '中',
    detail: '系统根据市场状况或账户表现自动调整了风控等级。等级越高，仓位限制越严格、止损越紧。调整不可通过拒绝回退，如需修改请在「风控管理」中操作。',
    explain: '风控等级决定了系统允许承受多大的风险。当市场剧烈波动或账户出现亏损时，系统会自动提高等级（更严格的保护）；市场平稳时会降低等级（恢复正常交易空间）。\n\n'
      + '等级提高 = 更安全但交易空间受限（仓位更小、止损更紧）\n'
      + '等级降低 = 交易空间更大但风险增加',
    approve: '同意风控调整，系统按新等级执行。',
    reject: '记录异议。风控等级不会回退，如需调整请在「风控管理」中操作。',
  },

  // ═══ 5. 风控降级已执行 ═══
  { pattern: /^RiskGovernor de-escalation approved: (.+) → (.+)$/,
    cn: (m) => '风控降级已执行：' + (_RISK_LEVEL_CN[m[1]] || m[1]) + ' → ' + (_RISK_LEVEL_CN[m[2]] || m[2]),
    risk: '低',
    detail: '此前提交的风控等级降低请求已获批并执行。系统已恢复至更宽松的保护等级，允许更大仓位和更多交易操作。此记录为已完成操作的确认。',
    explain: '有人（通常是你自己）认为之前的高风控等级不再必要，提交了降级请求并已获批。现在系统回到了更宽松的状态，AI 可以使用更大的仓位进行交易。\n\n'
      + '这条记录只是告知你操作已完成，批准或拒绝都不会改变已经执行的结果。',
    approve: '确认知晓操作已完成。',
    reject: '无实际效果，操作已执行。',
  },

  // ═══ 6. 交易授权状态变更 ═══
  { pattern: /^Authorization: (.+) → (.+)$/,
    cn: (m) => '交易授权状态变更：' + (_AUTH_STATE_CN[m[1]] || m[1]) + ' → ' + (_AUTH_STATE_CN[m[2]] || m[2]),
    risk: '低-中',
    detail: '交易授权控制系统是否有权执行交易。状态包括：草稿(DRAFT)、待审批(PENDING)、已激活(ACTIVE)、已限制(RESTRICTED)、已冻结(FROZEN)、已过期(EXPIRED)。纸盘模式授权自动批准，实盘需人工审批。',
    explain: '交易授权相当于系统的"营业执照"——有效时可以交易，失效时一切停止。\n\n'
      + '状态流转：草稿 → 待审批 → 已激活 → （正常运行） → 过期/冻结/撤销\n\n'
      + '纸盘模式（模拟交易，无真实资金）的授权会自动批准。如果未来启用实盘交易，每次授权都需要你亲自审批。\n\n'
      + '拒绝不会回退状态变更，要修改请在「授权管理」区域操作。',
    approve: '同意此授权变更。',
    reject: '记录异议。状态不会回退，如需修改请在「授权管理」中操作。',
  },

  // ═══ 7. 风控引擎状态转换 ═══
  { pattern: /^RiskGovernor: (.+) → (.+)$/,
    cn: (m) => '风控引擎状态转换：' + (_RISK_LEVEL_CN[m[1]] || m[1]) + ' → ' + (_RISK_LEVEL_CN[m[2]] || m[2]),
    risk: '中',
    detail: '风控引擎保护等级发生变化。等级从低到高：正常→注意→警告→危险→紧急。升级为保护措施，降级需确认市场已恢复稳定。',
    explain: '风控引擎是系统中负责"盯风险"的核心模块。它有 5 个保护等级，类似天气预警的蓝色/黄色/橙色/红色信号。\n\n'
      + '等级提高通常是因为：市场波动加剧、账户亏损增加、或对账发现异常。\n'
      + '等级降低通常是因为：异常已消除、市场恢复平稳。',
    approve: '确认风控引擎判断正确。',
    reject: '标记需审查。等级不会自动回退。',
  },

  // ═══ 8. 订单状态变更 ═══
  { pattern: /^OmsOrder (.+): (.+) → (.+)$/,
    cn: (m) => '订单 ' + m[1].substring(0,12) + '… 状态变更：' + (_OMS_STATE_CN[m[2]] || m[2]) + ' → ' + (_OMS_STATE_CN[m[3]] || m[3]),
    risk: '低',
    detail: '交易订单执行状态发生转换。正常流程：创建→提交→成交。出现"已拒绝"可能因价格滑点过大或余额不足。单笔订单状态变更通常无需人工干预。',
    explain: '每一笔交易订单都有一个生命周期：创建 → 提交给交易所 → 交易所确认成交（或拒绝）。\n\n'
      + '如果看到"已拒绝(REJECTED)"，可能的原因：\n'
      + '• 账户余额不足以下这笔单\n'
      + '• 市场价格变化太快，超出了可接受的范围\n'
      + '• 订单数量不符合交易所的最小/最大限制\n\n'
      + '偶尔的拒绝是正常的。如果大量订单被拒绝，则可能需要检查账户状态或参数配置。',
    approve: '确认订单执行流程正常。',
    reject: '标记订单可能存在异常，需人工检查。',
  },

  // ═══ 9. AI 交易许可变更 ═══
  { pattern: /^DecisionLease: (.+) → (.+)$/,
    cn: (m) => 'AI 交易许可变更：' + (_LEASE_STATE_CN[m[1]] || m[1]) + ' → ' + (_LEASE_STATE_CN[m[2]] || m[2]),
    risk: '低',
    detail: 'AI 的临时交易执行许可发生状态变更。许可有时效性，到期后 AI 需重新申请方可继续交易。这是防止 AI 异常时无限制下单的安全机制。',
    explain: 'AI 每次要执行交易前，必须先获取一个有时间限制的"通行证"（交易许可）。通行证到期后 AI 就不能再下单，必须重新申请。\n\n'
      + '这个机制的目的是防止 AI 在出现故障时疯狂下单——即使 AI 认为应该交易，没有有效通行证就无法执行。\n\n'
      + '许可的获取和释放是自动完成的，正常情况下不需要你做任何操作。',
    approve: '确认许可变更正常。',
    reject: '标记异常。仅在 AI 不应获得许可时使用。',
  },

  // ═══ 10. 紧急熔断 — 回撤 ═══
  { pattern: /^Session halted due to drawdown/,
    cn: () => '紧急熔断 — 回撤超过安全阈值',
    risk: '高',
    detail: '账户净值从最高点回撤幅度超过预设阈值，系统已自动暂停所有新交易。需检查持仓和市场状况，确认安全后在「交易会话」区域重新启动。熔断不可通过拒绝取消。',
    explain: '你的账户净值从历史最高点下跌的比例，超过了你设定的安全线。这就像汽车的安全气囊——检测到"碰撞"后自动弹出保护。\n\n'
      + '熔断后系统不会再开任何新仓，但已有的持仓不会被自动平掉。你需要：\n'
      + '1. 查看当前持仓和市场走势\n'
      + '2. 决定是否手动平掉部分或全部持仓\n'
      + '3. 等市场恢复后，在「交易会话」区域手动重新启动交易',
    approve: '确认知晓熔断，系统保护措施已生效。',
    reject: '无实际效果。熔断为自动保护机制，恢复交易需手动操作。',
  },

  // ═══ 11. 紧急熔断 — 单日亏损 ═══
  { pattern: /^Session halted due to daily loss/,
    cn: () => '紧急熔断 — 单日亏损超过限额',
    risk: '高',
    detail: '今日累计亏损超过预设的单日最大限额，系统已自动暂停所有新交易。次日将自动重置，或可在「交易会话」中调整限额后手动恢复。熔断不可通过拒绝取消。',
    explain: '今天的总亏损金额超过了你设定的"每天最多亏多少"的上限。这就像信用卡的每日消费限额——到达上限后自动锁定。\n\n'
      + '恢复方式：\n'
      + '1. 等到次日（限额会自动重置）\n'
      + '2. 如果你确认当前市场状况安全，可以手动调高限额后重启交易',
    approve: '确认知晓熔断，保护措施已生效。',
    reject: '无实际效果。恢复交易需手动操作或等待次日重置。',
  },

  // ═══ 12. 风控参数修改 ═══
  { pattern: /^Updated risk config parameter: (.+)$/,
    cn: (m) => '风控参数已修改：' + m[1],
    risk: '中',
    detail: '风控配置参数已被修改（可能由 AI 自主优化或系统自动调整）。参数直接影响仓位大小、止损比例等交易行为。拒绝仅标记记录，不回退参数。如需改回请在「风控设置」中操作。',
    explain: '风控参数控制着交易的安全边界，例如：\n'
      + '• 最大仓位大小 = 每笔交易最多投入多少资金\n'
      + '• 止损比例 = 亏损到什么程度自动止损\n'
      + '• 最大持仓数量 = 同时最多持有几个品种\n'
      + '• 每日最大亏损限额 = 一天最多允许亏多少\n\n'
      + '参数放宽意味着交易更激进（潜在收益和风险都增大），收紧意味着更保守（风险降低但机会也减少）。',
    approve: '确认参数调整合理，系统按新参数执行。',
    reject: '记录异议。参数不会自动回退，如需改回请在「风控设置」中操作。',
  },

  // ═══ 13. 模拟→实盘评估 ═══
  { pattern: /^PaperLiveGate evaluation: (.+)$/,
    cn: (m) => '模拟→实盘升级评估：' + m[1],
    risk: '无',
    detail: '系统完成了从模拟交易升级至实盘交易的准备度评估（含胜率、盈亏比、运行天数、回撤、稳定性等 11 项指标）。评估结果不会自动改变系统模式，升级需在「授权管理」中手动授权。',
    explain: '这是系统自动做的一个"体检报告"——评估目前的模拟交易表现是否达到了可以用真金白银做实盘的标准。\n\n'
      + '评估指标包括：模拟交易至少运行 21 天、胜率达标、盈亏比合理、最大回撤可控、系统运行稳定等。\n\n'
      + 'PASS = 各项达标，可以考虑升级到实盘\n'
      + 'FAIL = 还有指标未达标，建议继续模拟\n\n'
      + '无论评估结果如何，系统不会自动切换到实盘——必须你手动授权。',
    approve: '确认已阅读评估报告。',
    reject: '记录对评估结果的疑问。不影响系统运行。',
  },

  // ═══ 16. 门控事件 ═══
  { pattern: /^Gate event: (.+)$/,
    cn: (m) => '模拟→实盘门控事件：' + m[1],
    risk: '无',
    detail: '模拟→实盘门控系统产生了事件记录（如评估启动、指标达标/不达标等）。仅为信息记录，不影响当前交易。',
    explain: '门控系统会持续跟踪各项指标，并在指标发生变化时生成事件记录。例如"某项指标刚刚达标"或"新一轮评估开始"。\n\n'
      + '这些事件不会改变任何交易行为，只是帮你了解系统向实盘迈进的进度。',
    approve: '确认已阅读。',
    reject: '标记需进一步了解。',
  },
];

// ── 翻译 what 描述 ──
function _translateWhat(what) {
  if (!what) return '（无描述）';
  for (const rule of _WHAT_RULES) {
    const m = what.match(rule.pattern);
    if (m) return typeof rule.cn === 'function' ? rule.cn(m) : rule.cn;
  }
  return what; // 无匹配规则时返回原文
}

// ── 获取审批后果说明 ──
function _getApprovalGuidance(what) {
  if (!what) return null;
  for (const rule of _WHAT_RULES) {
    if (what.match(rule.pattern)) return rule;
  }
  return null;
}

// ── 格式化 old/new value ──
function _formatValue(val) {
  if (val == null || val === '--') return '--';
  // 先尝试翻译单个状态值
  const translated = _translateStateVal(val);
  if (translated !== val) return translated + '（' + val + '）';
  try {
    const parsed = JSON.parse(val);
    if (Array.isArray(parsed)) {
      if (parsed.length === 0) return '（空列表）';
      if (parsed.length <= 5) return parsed.join(', ');
      return parsed.slice(0, 5).join(', ') + '… 共 ' + parsed.length + ' 项';
    }
    if (typeof parsed === 'object' && parsed !== null) {
      // 特殊处理常见对象结构
      if ('session_halted' in parsed) {
        return parsed.session_halted ? '会话已熔断' + (parsed.halt_reason ? '（' + parsed.halt_reason + '）' : '') : '会话正常';
      }
      // 通用对象：转为 key=value 对
      return Object.entries(parsed).map(([k,v]) => k + '=' + v).join(', ');
    }
    return String(parsed);
  } catch (_) {
    // 非 JSON，尝试翻译为已知状态
    const t = _translateStateVal(String(val));
    return t !== String(val) ? t + '（' + val + '）' : String(val);
  }
}

function renderPendingAudit(changes) {
  const el = document.getElementById('pending-audit-content');
  const btnBulk = document.getElementById('btn-bulk-actions');
  if (!changes || changes.length === 0) {
    el.innerHTML = '<p style="color:var(--text-dim);font-size:12px">目前没有待批准的变更</p>'; // SAFE: static HTML only
    if (btnBulk) btnBulk.style.display = 'none';
    return;
  }
  if (btnBulk) btnBulk.style.display = '';

  let html = '<div style="display:flex;flex-direction:column;gap:12px">';
  for (const c of changes) {
    const cid = ocEsc(c.change_id || '');
    const cidJs = ocEsc((c.change_id || '').replace(/'/g, "\\'")); /* B12: JS string escape + HTML attribute escape */
    const statusLabel = _APPROVAL_STATUS_CN[c.approval_status] || c.approval_status || '待批准';
    const statusChip = ocChip(statusLabel, 'warn');

    // Translate description + get guidance
    const whatCn = _translateWhat(c.what);
    const guidance = _getApprovalGuidance(c.what);

    // Parse old→new values into readable format
    let changeDetail = '';
    if (c.old_value != null || c.new_value != null) {
      const oldStr = _formatValue(c.old_value);
      const newStr = _formatValue(c.new_value);
      changeDetail = '<div style="margin:6px 0;padding:8px 10px;background:var(--card-bg);border:1px solid var(--border);border-radius:6px;font-size:11px;line-height:1.8">'
        + '<div><span style="color:var(--text-dim)">变更前：</span><span style="color:var(--red)">' + ocEsc(oldStr) + '</span></div>'
        + '<div><span style="color:var(--text-dim)">变更后：</span><span style="color:var(--green)">' + ocEsc(newStr) + '</span></div>'
        + '</div>';
    }

    // Affected components (translated)
    let comps = '';
    if (c.affected_components && c.affected_components.length > 0) {
      comps = '<div style="margin-top:4px;font-size:11px;color:var(--text-dim)">影响范围：'
        + c.affected_components.map(x => ocEsc(_translateComp(x))).join('、') /* APR01-MEDIUM-4 XSS fix */
        + '</div>';
    }

    html += '<div style="background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:14px;font-size:12px">';
    // Header row: type badge + status + time
    html += '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px">';
    html += _changeTypeBadge(c.change_type);
    html += statusChip;
    html += '<span style="margin-left:auto;font-size:11px;color:var(--text-dim)">' + ocTime(c.when_ms || c.when) + '</span>';
    html += '</div>';
    // What — main description (Chinese)
    html += '<div style="font-weight:600;margin-bottom:6px;font-size:13px">' + ocEsc(whatCn) + '</div>';

    // Risk badge + formal explanation (always visible)
    // 风险标签 + 正式说明（始终可见）
    if (guidance) {
      let riskColor = 'var(--text-dim)';
      if (guidance.risk === '高') riskColor = 'var(--red)';
      else if (guidance.risk === '中' || guidance.risk === '中-高') riskColor = 'var(--yellow, #d29922)';
      else if (guidance.risk === '低' || guidance.risk === '低-中') riskColor = 'var(--green)';

      if (guidance.risk) {
        html += '<span style="display:inline-block;margin-bottom:6px;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:600;'
          + 'background:' + riskColor + '22;color:' + riskColor + ';border:1px solid ' + riskColor + '44'
          + '">风险等级：' + ocEsc(guidance.risk) + '</span>';
      }
      if (guidance.detail) {
        html += '<div style="margin-bottom:8px;padding:8px 10px;background:rgba(88,166,255,0.06);border-left:3px solid var(--accent);border-radius:0 6px 6px 0;font-size:11px;color:var(--text);line-height:1.7">'
          + ocEsc(guidance.detail) + '</div>';
      }
      // Collapsible plain-language explanation (hidden by default)
      // 可折叠的通俗说明（默认隐藏）
      if (guidance.explain) {
        const eid = 'explain-' + cid.replace(/[^a-zA-Z0-9]/g, '');
        html += '<details style="margin-bottom:8px;font-size:11px"><summary style="cursor:pointer;color:var(--accent);user-select:none;padding:4px 0">'
          + '详细说明 / Learn more</summary>'
          + '<div style="margin-top:6px;padding:8px 10px;background:var(--card-bg);border:1px solid var(--border);border-radius:6px;color:var(--text);line-height:1.8;white-space:pre-line">'
          + ocEsc(guidance.explain) + '</div></details>';
      }
    }

    // Who + reason
    html += '<div style="color:var(--text-dim);margin-bottom:4px">发起人：<strong style="color:var(--text)">' + ocEsc(_translateWho(c.who)) + '</strong></div>';
    if (c.reason) {
      html += '<div style="color:var(--text-dim);margin-bottom:4px">原因：' + ocEsc(c.reason) + '</div>';
    }
    // Old→New value diff
    html += changeDetail;
    // Affected components
    html += comps;

    // Approve / Reject buttons with per-item guidance
    const isPending = c.approval_status === 'PENDING' || c.approval_status === 'EMERGENCY_BYPASSED';
    if (isPending) {
      // Show approve/reject consequences
      html += '<div style="margin-top:10px;border:1px solid var(--border);border-radius:6px;overflow:hidden;font-size:11px">';
      html += '<div style="display:flex">';
      html += '<div style="flex:1;padding:8px 10px;background:rgba(63,185,80,0.06);border-right:1px solid var(--border)">';
      html += '<div style="font-weight:600;color:var(--green);margin-bottom:4px">✔ 批准后果</div>';
      html += '<div style="color:var(--text);line-height:1.6">' + ocEsc(guidance ? guidance.approve : '确认此变更有效。') + '</div>';
      html += '</div>';
      html += '<div style="flex:1;padding:8px 10px;background:rgba(248,81,73,0.06)">';
      html += '<div style="font-weight:600;color:var(--red);margin-bottom:4px">✖ 拒绝后果</div>';
      html += '<div style="color:var(--text);line-height:1.6">' + ocEsc(guidance ? guidance.reject : '标记此变更为不合规，需要进一步处理。') + '</div>';
      html += '</div>';
      html += '</div></div>';

      html += '<div style="display:flex;gap:8px;margin-top:10px">';
      html += '<button class="oc-btn oc-btn-success" style="font-size:12px;padding:6px 20px" '
        + 'onclick="auditApprove(\'' + cidJs + '\')">✔ 批准</button>';
      html += '<button class="oc-btn oc-btn-danger" style="font-size:12px;padding:6px 20px" '
        + 'onclick="auditReject(\'' + cidJs + '\')">✖ 拒绝</button>';
      html += '</div>';
    }
    html += '<div style="font-size:10px;color:var(--text-dim);margin-top:8px;opacity:0.5">ID: ' + cid
      + (c.what ? ' · 原文 Original: ' + ocEsc(c.what) : '') + '</div>';
    html += '</div>';
  }
  html += '</div>';
  el.innerHTML = html;
}

async function auditApprove(changeId) {
  const reason = prompt('批准原因 Approval reason (optional):') ?? '';
  if (reason === null) return;  // cancelled
  const d = await govApproveAuditChange(changeId, reason);
  if (d && d.ok) {
    ocToast('Change approved / 变更已批准', 'success');
    loadPendingApprovals();
  } else {
    ocToast((d && d.message) || 'Approve failed / 批准失败', 'error');
  }
}

async function auditReject(changeId) {
  const reason = prompt('拒绝原因 Rejection reason (required):');
  if (!reason || !reason.trim()) { ocToast('Please enter a rejection reason / 请输入拒绝原因', 'error'); return; }
  const d = await govRejectAuditChange(changeId, reason.trim());
  if (d && d.ok) {
    ocToast('Change rejected / 变更已拒绝', 'success');
    loadPendingApprovals();
  } else {
    ocToast((d && d.message) || 'Reject failed / 拒绝失败', 'error');
  }
}

async function bulkAudit(action) {
  const isApprove = action === 'approve';
  const msg = isApprove
    ? '确认全部同意？\nApprove all pending changes?'
    : '确认全部拒绝？\nReject all pending changes?';
  if (!confirm(msg)) return;

  const reason = isApprove ? 'Operator bulk approved' : (prompt('拒绝原因 Rejection reason:') || '').trim();
  if (!isApprove && !reason) { ocToast('请输入拒绝原因', 'error'); return; }

  // Fetch current pending list and process one by one
  const pending = await govGetPendingAudit();
  if (!pending || !pending.ok || !pending.data) { ocToast('获取待审批列表失败', 'error'); return; }

  let ok = 0, fail = 0;
  for (const c of pending.data) {
    const d = isApprove
      ? await govApproveAuditChange(c.change_id, reason)
      : await govRejectAuditChange(c.change_id, reason);
    if (d && d.ok) ok++; else fail++;
  }

  const label = isApprove ? '同意 approved' : '拒绝 rejected';
  ocToast(ok + ' 项已' + label + (fail ? '，' + fail + ' 项失败' : ''), ok ? 'success' : 'error');
  loadPendingApprovals();
}

async function loadPendingApprovals() {
  const recovery = await govGetPendingRecovery();
  if (recovery && recovery.ok) {
    renderPendingRecovery(recovery.data || []);
  } else {
    const el = document.getElementById('pending-recovery-content');
    if (el) el.innerHTML = '<p style="color:var(--red);font-size:12px">Failed to load recovery requests / 載入恢復請求失敗（治理中枢可能未启用）</p>'; // SAFE: static HTML only
  }

  const audit = await govGetPendingAudit();
  if (audit && audit.ok) {
    renderPendingAudit(audit.data || []);
  } else {
    const el = document.getElementById('pending-audit-content');
    if (el) el.innerHTML = '<p style="color:var(--red);font-size:12px">Failed to load pending approvals / 載入待批准項目失敗（治理中枢可能未启用）</p>'; // SAFE: static HTML only
  }
}

async function confirmApproveRecovery(requestId) {
  if (confirm('Approve this recovery request? / 批准此恢復請求?')) {
    const d = await govApprovePendingRecovery(requestId);
    if (d && d.ok) {
      ocToast('Recovery request approved / 恢復請求已批准', 'success');
      loadPendingApprovals();
      loadAll();
    } else {
      ocToast(d ? d.message : 'Approval failed / 批准失敗', 'error');
    }
  }
}

// ─── Data Loading ─────────────────────────────────────────────
async function loadAll() {
  const d = await govGetStatus();

  if (!d || !d.ok) {
    if (d && d.error_code === 'governance_hub_unavailable') {
      showUnavailable();
    }
    return;
  }

  _currentStatus = d.data;

  if (_currentStatus) {
    const auth = _currentStatus.authorization || {};
    const risk = _currentStatus.risk || {};
    const leases = _currentStatus.leases || {};
    const recon = _currentStatus.reconciliation || {};

    renderAuthCard(auth);
    renderRiskCard(risk);
    renderLeaseCard(leases);
    renderReconCard(recon);
    renderSummary(_currentStatus);

    // Load scope visualization (async, complements auth card)
    loadAuthScope();

    // Detect changes and render incident log (client-side session data)
    // 检测状态变更并渲染事件时间线（客户端会话数据）
    detectChanges(_currentStatus);
    renderIncidentLog();

    // Load audit trail from server (with client-side fallback)
    // 从服务端加载持久化审计日志（客户端回退）
    loadAuditTrail().catch(e => console.warn('Audit trail load failed:', e));

    // Load lease detail list from server
    // 从服务端加载租约详情列表
    // Backend returns {data: {active_count, total_tracked, leases: [...], all_leases: [...]}}
    // 后端返回 {data: {active_count, total_tracked, leases: [...], all_leases: [...]}}
    govGetLeases().then(ld => {
      const leaseList = (ld && ld.ok && ld.data && Array.isArray(ld.data.leases)) ? ld.data.leases : [];
      renderLeaseList(leaseList);
    }).catch(e => console.warn('Lease list load failed:', e));

    // Load Paper→Live Gate status
    // 加载 Paper→Live 门禁状态
    loadPaperLiveGate().catch(e => console.warn('PLG load failed:', e));

    // Load learning tier status
    // 加载学习层级状态
    loadLearningTier().catch(e => console.warn('Learning tier load failed:', e));

    // Load governance events feed
    // 加载治理事件流
    loadEventsFeed().catch(e => console.warn('Events feed load failed:', e));

    // Load pending approvals (async, non-blocking)
    loadPendingApprovals().catch(e => console.warn('Failed to load pending approvals:', e));
  }
}

// ─── Init ─────────────────────────────────────────────────────
loadAll();
ocStartRefresh(loadAll, 10000);

// Close modals on background click
['modal-request-auth', 'modal-approve', 'modal-override', 'modal-reconcile', 'modal-promote'].forEach(id => {
  const el = $(id);
  if (el) {
    el.addEventListener('click', function(e) {
      if (e.target === this) {
        this.style.display = 'none';
      }
    });
  }
});
