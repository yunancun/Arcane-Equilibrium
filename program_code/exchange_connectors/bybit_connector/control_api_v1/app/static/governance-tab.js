/**
 * Governance Tab — Inline script extracted from tab-governance.html.
 * 治理頁面 — 從 tab-governance.html 提取的內嵌腳本。
 *
 * MODULE_NOTE (EN): Extracted from tab-governance.html (FIX-08 file size).
 * MODULE_NOTE (中): 從 tab-governance.html 提取（FIX-08 文件大小）。
 */

// ─── Explainers ───────────────────────────────────────────────
$('explain-governance').innerHTML = ocExplain(
  '治理系統是玄衡的安全核心，通過 SM-01 授權、SM-02 租約、SM-03 執行和 SM-04 風控管理交易边界。',
  '授權 SM (SM-01) 控制操作權限和有效期。租約 SM (SM-02) 管理決策生命周期。執行 SM (SM-03) 管理訂單从建立到成交、取消或失败的生命周期。風控 SM (SM-04) 動態調整風險等级。對賬引擎 (EX-04) 作为擴展檢查系統記錄与交易所實際状态是否一致。'
);

// ─── State Storage ─────────────────────────────────────────────
let _currentStatus = null;
let _currentAuthState = null;
let _currentRiskLevel = null;
let _currentLeaseActive = null;

// W-AUDIT-7c round 2 fix [#5][#6]：cache 最近一次 pending list，
// bulkAudit / confirmApproveRecovery modal body 內顯示具體影響時可直接讀取，
// 避免每次點按鈕都 re-fetch（也避免 modal open 前還沒有資料可顯示）。
// loadPendingApprovals 每次刷新都會更新此 cache。
let _lastPendingRecovery = [];
let _lastPendingAudit = [];

// ─── Event Log (Incident Timeline & Audit Trail) ───────────────
let _govEventLog = [];
let _prevStatus = null;
const MAX_EVENTS = 50;

// ─── SM-03 Derived Status / SM-03 派生狀態 ─────────────────────
function updateOmsCard() {
  const readinessEl = document.getElementById('oms-readiness');
  const blockerEl = document.getElementById('oms-blocker');
  if (!readinessEl || !blockerEl) return;

  const authState = _currentAuthState || 'UNKNOWN';
  const riskLevel = _currentRiskLevel;
  const activeLeases = _currentLeaseActive;

  let label = 'UNKNOWN';
  let chipType = 'neutral';
  let blocker = '等待治理状态載入 / Waiting for governance status';

  if (authState !== 'ACTIVE') {
    label = 'CLOSED';
    chipType = 'neutral';
    blocker = 'SM-01 未處於 ACTIVE，訂單不得進入執行状态。';
  } else if (riskLevel != null && riskLevel >= 4) {
    label = 'RISK LOCKED';
    chipType = 'bad';
    blocker = 'SM-04 處於高風險等级，執行状态應停止推進。';
  } else if (activeLeases != null && activeLeases > 0) {
    label = 'LEASE READY';
    chipType = 'good';
    blocker = '存在 SM-02 活跃租約；符合範圍的意圖可進入 SM-03 校驗。';
  } else if (activeLeases === 0) {
    label = 'IDLE';
    chipType = 'neutral';
    blocker = '暂無活跃租約；没有意圖應進入訂單執行状态。';
  } else {
    label = 'WAITING';
    chipType = 'neutral';
    blocker = '等待租約状态載入 / Waiting for lease state';
  }

  ocSetHtml('oms-readiness', ocChip(label, chipType));
  ocSetText('oms-blocker', blocker);
  if (typeof window.updateQuickStatus === 'function') {
    window.updateQuickStatus(undefined, undefined, undefined, undefined, label);
  }
}

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

// 切换租約详情列表 / Toggle lease detail list
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

// loadAuditTrail: 从服務端載入持久化審計日志
// Load persistent audit trail from server; fall back to client-side log on error/empty
async function loadAuditTrail() {
  const tbody = document.getElementById('audit-trail-tbody');
  try {
    // 調用 govGetAuditChanges(limit) 获取服務端審計記錄
    // Call govGetAuditChanges to retrieve server-persisted change records
    const d = await govGetAuditChanges(100);
    const records = (d && d.ok && Array.isArray(d.data)) ? d.data : [];

    if (records.length === 0) {
      // 服務端無數據，降级为客户端日志 / No server data — fall back to client-side log
      renderAuditTrail();
      return;
    }

    let html = '';
    for (const r of records) {
      // 服務端字段: timestamp, who, what, reason, change_type, old_value, new_value, auto_approved, affected_components
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

      // What 列：翻译名 + 風險標簽 + 可展開說明
      // What column: translated name + risk badge + expandable explanation
      html += '<td style="max-width:360px">';
      html += '<div style="font-weight:600;font-size:12px">' + ocEsc(whatCn) + '</div>';
      if (guidance) {
        // 風險標簽 / Risk badge
        if (guidance.risk) {
          let riskColor = 'var(--text-dim)';
          if (guidance.risk === '高') riskColor = 'var(--red)';
          else if (guidance.risk === '中' || guidance.risk === '中-高') riskColor = 'var(--yellow, #d29922)';
          else if (guidance.risk === '低' || guidance.risk === '低-中') riskColor = 'var(--green)';
          else if (guidance.risk === '無') riskColor = 'var(--text-dim)';
          html += '<span style="display:inline-block;margin:2px 0;padding:1px 6px;border-radius:3px;font-size:9px;font-weight:600;'
            + 'background:' + riskColor + '22;color:' + riskColor + '">風險：' + ocEsc(guidance.risk) + '</span> ';
        }
        // 正式說明（始終可见）/ Formal detail (always visible)
        if (guidance.detail) {
          html += '<div style="font-size:10px;color:var(--text-dim);margin-top:2px;line-height:1.5">' + ocEsc(guidance.detail) + '</div>';
        }
        // 通俗解釋（折叠）/ Plain-language explanation (collapsed)
        if (guidance.explain) {
          html += '<details style="margin-top:3px;font-size:10px"><summary style="cursor:pointer;color:var(--accent);user-select:none">'
            + '详細說明</summary>'
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
    // 請求失败，降级为客户端日志 / Request failed — fall back to client-side log
    console.warn('Audit trail server load failed, using client-side fallback:', e);
    renderAuditTrail();
  }
}

// ─── Modal Functions ──────────────────────────────────────────

// showRequestAuthModal: 顯示授權申請弹窗（DRAFT → PENDING_APPROVAL 流程）
// Show the Request Authorization modal to initiate SM-01 DRAFT → PENDING_APPROVAL flow
function showRequestAuthModal() {
  // 重置表單并顯示授權申請弹窗 / Reset form and show modal
  $('request-auth-ttl').value = '24';
  $('request-auth-reason').value = '';
  $('modal-request-auth').style.display = 'flex';
}

// hideRequestAuthModal: 關閉授權申請弹窗
// Hide the Request Authorization modal
function hideRequestAuthModal() {
  $('modal-request-auth').style.display = 'none';
}

// submitRequestAuth: 提交授權申請（POST /api/v1/governance/auth/request）
// Submit the authorization request; on success reload data and close modal
async function submitRequestAuth() {
  const ttl = parseInt($('request-auth-ttl').value) || 24;
  const reason = $('request-auth-reason').value.trim();
  if (!reason) {
    ocToast('請輸入申請原因 / Please enter a reason', 'error');
    return;
  }
  const d = await govRequestAuthorization(ttl, reason);
  if (d && d.ok) {
    ocToast('授權申請已提交，等待審批 / Authorization request submitted', 'success');
    hideRequestAuthModal();
    loadAll();
  } else {
    ocToast((d && d.message) ? d.message : '申請失败 / Request failed', 'error');
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
    ocToast('Please enter an approval note / 請輸入批準備注', 'error');
    return;
  }

  const d = await govPostApprove(note);
  if (d && d.ok) {
    ocToast('Authorization approved / 授權已批准', 'success');
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
    ocToast('Please select target level / 請選擇目標等级', 'error');
    return;
  }
  if (!reason) {
    ocToast('Please enter a reason / 請輸入原因', 'error');
    return;
  }

  const d = await govPostOverride(level, reason);
  if (d && d.ok) {
    ocToast('Risk level de-escalated / 風險等级已降级', 'success');
    hideOverrideModal();
    loadAll();
  } else {
    ocToast(d ? d.message : 'Override failed / 降级失败', 'error');
  }
}

async function submitReconcile() {
  const reason = $('reconcile-reason').value.trim();
  if (!reason) {
    ocToast('Please enter a reason / 請輸入原因', 'error');
    return;
  }

  const d = await govPostReconcile(reason);
  if (d && d.ok) {
    ocToast('Reconciliation triggered / 對賬已触发', 'success');
    hideReconcileModal();
    loadAll();
  } else {
    ocToast(d ? d.message : 'Reconciliation failed / 對賬失败', 'error');
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
    _currentAuthState = null;
    ocSetHtml('auth-state-badge', ocChip('UNAVAILABLE', 'neutral'));
    ocSetText('auth-expiry', '--');
    ocSetText('auth-state-desc', '');
    renderAuthScope({});
    $('btn-approve').style.display = 'none';
    $('btn-request-auth').style.display = 'none';
    $('auth-pending-indicator').style.display = 'none';
    updateOmsCard();
    return;
  }

  const state = authData.state || 'UNKNOWN';
  _currentAuthState = state;
  ocSetHtml('auth-state-badge', govAuthBadge(state));

  const expiresMs = authData.expires_at_ms;
  // ACTIVE → show expiry countdown; other states → hide expiry
  // ACTIVE 顯示過期倒計時；其他状态不顯示
  ocSetText('auth-expiry', (state === 'ACTIVE' && expiresMs) ? govExpiryCountdown(expiresMs) : '--');

  // State description text / 各状态說明文字
  const AUTH_DESC = {
    NONE:             '無授權對象 No authorization object',
    DRAFT:            '草稿待提交 Draft pending submission',
    PENDING_APPROVAL: '等待操作員審批 Awaiting Operator approval',
    ACTIVE:           '',   // expiry countdown is shown instead / 顯示過期倒計時，無需额外說明
    RESTRICTED:       '受限運行 Restricted operation',
    FROZEN:           '已冻結 Frozen — no trading allowed',
    EXPIRED:          '已過期，需重新申請 Re-authorization required',
    REVOKED:          '已吊銷，需重新申請 Re-authorization required',
    REJECTED:         '已拒絕，需重新申請 Re-authorization required',
  };
  ocSetText('auth-state-desc', AUTH_DESC[state] || '');
  // Quick status banner update / 更新快速状态栏
  if (typeof window.updateQuickStatus === 'function') window.updateQuickStatus(state, undefined, undefined, undefined);
  updateOmsCard();

  // Render scope using the new visualizer
  const scope = authData.scope || {};
  renderAuthScope(scope);

  const isPending = authData.pending_approval === true;
  $('auth-pending-indicator').style.display = isPending ? 'block' : 'none';
  $('btn-approve').style.display = isPending ? '' : 'none';

  // Show "Request Authorization" button for states that need a fresh auth object
  // 無授權、草稿、已過期/吊銷/拒絕 時顯示申請授權按钮
  const needsRequest = ['NONE', 'DRAFT', 'EXPIRED', 'REVOKED', 'REJECTED'].includes(state);
  $('btn-request-auth').style.display = needsRequest ? '' : 'none';
}

function renderRiskCard(riskData) {
  if (!riskData) {
    _currentRiskLevel = null;
    ocSetHtml('risk-level-badge', ocChip('UNAVAILABLE', 'neutral'));
    ocSetHtml('risk-mode-badge', ocChip('--', 'neutral'));
    ocSetText('risk-reason', '--');
    updateOmsCard();
    return;
  }

  const level = riskData.level != null ? riskData.level : 0;
  _currentRiskLevel = level;

  ocSetHtml('risk-level-badge', govRiskBadge(level));

  const mode = riskData.mode || 'UNKNOWN';
  ocSetHtml('risk-mode-badge', govModeBadge(mode));

  const reason = riskData.escalation_reason || '--';
  ocSetText('risk-reason', ocEsc(reason));
  // Quick status banner update / 更新快速状态栏風險等级
  const riskName = GOV_RISK_LEVELS[level] || ('L' + level);
  if (typeof window.updateQuickStatus === 'function') window.updateQuickStatus(undefined, riskName, undefined, undefined);
  updateOmsCard();

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

// renderLeaseList: 渲染活跃租約详情列表
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
    // lease_id 縮短为最后 8 位 / Truncate lease_id to last 8 chars
    const shortId = (lease.lease_id || lease.id || '--').slice(-8);
    const symbol = lease.symbol || '--';
    const direction = lease.direction || '--';
    const strategy = lease.strategy || '--';

    // 計算過期倒計時 / Calculate expiry countdown
    let expiryStr = '--';
    const expiresAt = lease.expires_at_ms || lease.expires_at;
    if (expiresAt) {
      const expiresMs = typeof expiresAt === 'number' ? expiresAt : new Date(expiresAt).getTime();
      const diffSec = Math.round((expiresMs - now) / 1000);
      if (diffSec <= 0) {
        expiryStr = ocChip('Expired / 已過期', 'bad');
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
    _currentLeaseActive = null;
    ocSetText('lease-active', '--');
    ocSetText('lease-total', '--');
    updateOmsCard();
    return;
  }

  const activeCount = leaseData.active_count != null ? leaseData.active_count : 0;
  const totalCount = leaseData.total_tracked != null ? leaseData.total_tracked : 0;
  _currentLeaseActive = activeCount;

  ocSetText('lease-active', String(activeCount));
  ocSetText('lease-total', String(totalCount));
  updateOmsCard();
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
  // Quick status banner update / 更新快速状态栏對賬状态
  const reconLabel = isConsistent === true ? 'OK' : isConsistent === false ? 'DRIFT' : '--';
  if (typeof window.updateQuickStatus === 'function') window.updateQuickStatus(undefined, undefined, reconLabel, undefined);
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

// loadPaperLiveGate: 載入 Paper→Live 门禁状态
// Load Paper→Live gate status from server
async function loadPaperLiveGate() {
  try {
    // GET /api/v1/governance/paper-live-gate/status
    const d = await ocApi('/api/v1/governance/paper-live-gate/status');
    if (!d || !d.ok) {
      ocSetHtml('plg-status-badge', ocChip('Unavailable / 不可用', 'neutral'));
      ocSetText('plg-score', '--');
      document.getElementById('plg-criteria-list').innerHTML =
        '<p style="color:var(--text-dim);font-size:12px">Data unavailable / 數據不可用</p>'; // SAFE: static HTML only
      return;
    }

    const data = d.data || d;
    const status = data.status || 'UNKNOWN';
    const passedCount = data.passed_count != null ? data.passed_count : '--';
    const totalCount = data.total_count != null ? data.total_count : '--';
    const criteria = Array.isArray(data.criteria) ? data.criteria : [];

    // 渲染状态徽章和評分 / Render status badge and score
    ocSetHtml('plg-status-badge', ocChip(ocEsc(status), _plgStatusColor(status)));
    ocSetText('plg-score', passedCount + '/' + totalCount + ' 通過');

    // 渲染准入项目列表 / Render criteria list
    if (criteria.length === 0) {
      document.getElementById('plg-criteria-list').innerHTML =
        '<p style="color:var(--text-dim);font-size:12px">No criteria data / 無准入项目數據</p>'; // SAFE: static HTML only
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
    ocSetHtml('plg-status-badge', ocChip('Error / 錯誤', 'bad'));
  }
}

// evaluatePaperLiveGate: 触发准入評估，自動从 Paper Engine 读取當前指標作为評估参數
// Trigger PaperLiveGate evaluation — auto-fills required metrics from Paper Engine status
async function evaluatePaperLiveGate() {
  ocToast('读取指標中... / Fetching metrics...', 'info');
  try {
    // Step 1: Fetch current paper engine metrics from real backend endpoints.
    // Do not synthesize 1-day/zero-trade defaults: those can incorrectly turn
    // "unknown" into a real gate evaluation.
    // 第一步：只讀真後端端點。不可用 1 天 / 0 交易等預設值偽造成真評估。
    const [sessionRes, metricsRes] = await Promise.allSettled([
      ocApi('/api/v1/paper/session/status'),
      ocApi('/api/v1/paper/metrics'),
    ]);
    const sessionData = sessionRes.status === 'fulfilled' && sessionRes.value && sessionRes.value.data
      ? sessionRes.value.data
      : null;
    const metricData = metricsRes.status === 'fulfilled' && metricsRes.value && metricsRes.value.data
      ? metricsRes.value.data
      : null;
    if (!sessionData || !metricData) {
      ocToast('Paper metrics unavailable; evaluation not sent / Paper 指標不可用，未送出評估', 'error');
      return;
    }

    const sess = sessionData.session || {};
    const trade = metricData.trade_metrics || {};
    const dd = metricData.drawdown_metrics || {};
    const pnl = sessionData.pnl || metricData.pnl_summary || {};
    const pickNum = (...vals) => {
      for (const v of vals) {
        const n = Number(v);
        if (Number.isFinite(n)) return n;
      }
      return null;
    };
    const paperStart = pickNum(
      sess.started_ts_ms,
      sess.paper_start_time_ms,
      metricData.paper_start_time_ms
    );
    const totalTrades = pickNum(trade.total_round_trips, metricData.total_round_trips);
    const winRate = pickNum(trade.win_rate);
    const winRatePercent = winRate == null ? pickNum(trade.win_rate_percent, metricData.win_rate_pct) :
      (Math.abs(winRate) <= 1 ? winRate * 100 : winRate);
    const metrics = {
      paper_start_time_ms: paperStart,
      total_trades: totalTrades,
      win_rate_percent: winRatePercent,
      net_pnl: pickNum(pnl.net_paper_pnl, metricData.net_pnl),
      sharpe_ratio: pickNum(metricData.sharpe_ratio),
      max_drawdown_percent: pickNum(dd.max_drawdown_pct, metricData.max_drawdown_pct),
      profit_factor: pickNum(trade.profit_factor, trade.win_loss_ratio),
    };
    const missing = Object.entries(metrics)
      .filter(([, v]) => v == null)
      .map(([k]) => k);
    if (missing.length) {
      ocToast('Paper gate missing real fields: ' + missing.join(', '), 'error');
      return;
    }

    // Step 2: POST evaluation request with populated metrics
    // 第二步：發送攜带真實指標的評估請求
    ocToast('評估中... / Evaluating...', 'info');
    const d = await ocPost('/api/v1/governance/paper-live-gate/evaluate', metrics);
    if (d && d.ok) {
      ocToast('Evaluation complete / 評估完成', 'success');
      await loadPaperLiveGate();
      // A3: Auto-expand criteria list after evaluation so operator can see results immediately
      // A3: 評估完成后自動展開准入项目列表，讓操作員立即看到結果
      const criteriaBody = document.getElementById('plg-criteria-body');
      const criteriaToggle = document.getElementById('plg-criteria-toggle');
      if (criteriaBody) { criteriaBody.style.display = ''; }
      if (criteriaToggle) { criteriaToggle.textContent = '▼'; }
    } else {
      ocToast((d && d.message) ? d.message : 'Evaluation failed / 評估失败', 'error');
    }
  } catch (e) {
    console.warn('PLG evaluate failed:', e);
    ocToast('Evaluation request failed / 評估請求失败', 'error');
  }
}

// ─── Learning Tier Functions ──────────────────────────────────────

// 層级徽章颜色映射 / Badge color for learning tier
function _ltTierColor(tier) {
  if (!tier) return 'neutral';
  const t = String(tier).toUpperCase();
  if (t === 'L0') return 'neutral';
  if (t === 'L1') return 'good';
  if (t === 'L2') return 'good';
  if (t === 'L3') return 'info';
  return 'warn'; // L4+
}

// loadLearningTier: 載入學習層级状态
// Load learning tier status from server
async function loadLearningTier() {
  try {
    // 調用 governance.js 中的 govGetLearningTier()
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
    // Quick status banner update / 更新快速状态栏學習層级
    if (typeof window.updateQuickStatus === 'function') window.updateQuickStatus(undefined, undefined, undefined, tier);
    const obsCount = data.observation_count != null ? data.observation_count : 0;
    const winRate = data.win_rate != null ? data.win_rate : null;
    const eligible = data.eligible_for_promotion === true;
    const nextReqs = data.next_tier_requirements || {};

    // 渲染層级、观測數、勝率 / Render tier, observation count, win rate
    ocSetHtml('lt-tier', ocChip(ocEsc(tier), _ltTierColor(tier)));
    ocSetText('lt-obs', String(obsCount));
    ocSetText('lt-winrate', winRate != null ? (winRate * 100).toFixed(1) + '%' : '--');

    // 進度條：基于下一層级所需观測數 / Progress bar based on next tier observation requirement
    const obsRequired = nextReqs.observations || nextReqs.min_observations || 0;
    const pct = obsRequired > 0 ? Math.min(100, Math.round((obsCount / obsRequired) * 100)) : (eligible ? 100 : 0);
    document.getElementById('lt-progress').style.width = pct + '%';

    // 資格徽章 / Eligibility badge
    ocSetHtml('lt-eligible', ocChip(
      eligible ? '可晋升 Eligible' : '未达標 Not yet',
      eligible ? 'good' : 'neutral'
    ));

    // 晋升按钮仅在可晋升時顯示 / Show promote button only when eligible
    const btn = document.getElementById('btn-promote');
    if (btn) btn.style.display = eligible ? '' : 'none';

    // A3: Dynamically filter promote dropdown to only show tiers ABOVE current
    // A3: 動態過滤晋升下拉，只顯示高于當前層级的選项（防止誤操作降级）
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
    ocSetHtml('lt-tier', ocChip('Error / 錯誤', 'bad'));
  }
}

// showPromoteModal / hidePromoteModal: 晋升确認弹窗
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

// submitPromotion: 提交手動晋升請求
// Submit a manual learning tier promotion
async function submitPromotion() {
  const targetTier = document.getElementById('promote-tier').value;
  const reason = document.getElementById('promote-reason').value.trim();

  if (!targetTier) {
    ocToast('Please select a target tier / 請選擇目標層级', 'error');
    return;
  }
  if (!reason) {
    ocToast('Please enter a reason / 請輸入原因', 'error');
    return;
  }

  // 調用 governance.js 中的 govPromoteLearningTier()
  // Call govPromoteLearningTier() from governance.js
  const d = await govPromoteLearningTier(targetTier, reason);
  if (d && d.ok) {
    ocToast('Promotion submitted / 晋升請求已提交', 'success');
    hidePromoteModal();
    await loadLearningTier();
  } else {
    ocToast((d && d.message) ? d.message : 'Promotion failed / 晋升失败', 'error');
  }
}

// ─── Events Feed Functions ────────────────────────────────────────

// loadEventsFeed: 載入服務端治理事件流
// Load governance event history from server
async function loadEventsFeed(limit) {
  const lim = limit || 50;
  const el = document.getElementById('events-feed-content');
  try {
    // 調用 governance.js 中的 govGetEvents(limit)
    // Call govGetEvents(limit) from governance.js
    const d = await govGetEvents(lim);
    // Backend: {data: {events: [...], count, limit}} — extract nested array
    // 后端返回 {data: {events: [...], count, limit}}，提取內層數組
    const events = (d && d.ok && d.data && Array.isArray(d.data.events)) ? d.data.events : [];

    if (events.length === 0) {
      el.innerHTML = '<p style="color:var(--text-dim);font-size:12px;padding:8px">No events yet / 暂無事件</p>'; // SAFE: static HTML only
      return;
    }

    let html = '';
    for (const ev of events) {
      // 服務端事件字段: timestamp/time, event_type/type, description/message
      // Server event fields: timestamp/time, event_type/type, description/message
      const ts = ev.timestamp || ev.time || ev.ts;
      const timeStr = ts ? ocTime(ts) : '--';
      const evType = ev.event_type || ev.type || 'EVENT';
      const desc = ev.description || ev.message || ev.msg || '';

      // 根據事件類型選擇颜色 / Choose color by event type
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
    el.innerHTML = '<p style="color:var(--text-dim);font-size:12px;padding:8px">Failed to load events / 事件載入失败</p>'; // SAFE: static HTML only
  }
}

function showUnavailable() {
  const unavailMsg = ocChip('Governance Hub Not Available / 治理中枢未啟用', 'warn');

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
    el.innerHTML = '<p style="color:var(--text-dim);font-size:12px">目前没有待審批的恢復請求</p>'; // SAFE: static HTML only
    return;
  }

  const _RECOVERY_STATUS_CN = { PENDING: '待批准', APPROVED: '已批准', REJECTED: '已拒絕', EXPIRED: '已過期' };

  let html = '<div style="display:flex;flex-direction:column;gap:8px">';
  for (const req of requests) {
    const statusCn = _RECOVERY_STATUS_CN[req.status] || req.status || '待批准';
    html += '<div style="background:var(--card-bg);border:1px solid var(--border);border-radius:6px;padding:12px;font-size:12px">';
    html += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">' + ocChip(statusCn, 'warn') + '</div>';
    html += '<div style="font-weight:600;margin-bottom:4px">' + ocEsc(req.description || '系統請求恢復到安全状态') + '</div>';
    html += '<div style="margin-top:8px;padding:8px;background:rgba(56,139,253,0.06);border-radius:6px;font-size:11px;color:var(--text-dim);line-height:1.6">'
      + '批准 = 允許系統从異常状态恢復；拒絕 = 保持當前状态不变。'
      + '</div>';
    html += '<div style="display:flex;gap:8px;margin-top:8px">';
    var _reqIdJs = (req.request_id || req.id || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'"); /* APR01-MEDIUM-4 XSS fix: JS string escape */
    html += '<button class="oc-btn oc-btn-success" style="font-size:11px;padding:5px 16px" onclick="confirmApproveRecovery(\'' + ocEsc(_reqIdJs) + '\')">✔ 批准恢復</button>';
    html += '</div>';
    html += '<div style="font-size:10px;color:var(--text-dim);margin-top:6px;opacity:0.6">ID: ' + ocEsc(req.request_id || req.id || '--') + '</div>';
    html += '</div>';
  }
  html += '</div>';
  el.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════════════
// 審計变更 完整翻译系統 / Audit Change Complete Translation System
// 覆盖所有 record_change() 調用来源，确保 Operator 能看懂每一條記錄
// ═══════════════════════════════════════════════════════════════════════

// ── 变更類型 Change Type ──
const _CHANGE_TYPE_LABELS = {
  STATE_CHANGE:      '状态变更',
  CONFIG_CHANGE:     '配置变更',
  PARAMETER_CHANGE:  '参數变更',
  RISK_OVERRIDE:     '風控覆盖',
  PERMISSION_CHANGE: '權限变更',
  CODE_DEPLOYMENT:   '代码部署',
  ROLLBACK:          '回滚',
  EMERGENCY_CHANGE:  '紧急变更',
};

// ── 審批状态 Approval Status ──
const _APPROVAL_STATUS_CN = {
  PENDING:            '待批准',
  AUTO_APPROVED:      '系統自動批准',
  APPROVED:           '已批准',
  REJECTED:           '已拒絕',
  EMERGENCY_BYPASSED: '紧急跳過（需事后补批）',
};

function _changeTypeBadge(ct) {
  const label = _CHANGE_TYPE_LABELS[ct] || ct || '未知';
  const isRisk = ct === 'RISK_OVERRIDE' || ct === 'EMERGENCY_CHANGE';
  return ocChip(label, isRisk ? 'bad' : 'info');
}

// ── 授權状态值 Authorization State Values ──
const _AUTH_STATE_CN = {
  DRAFT: '草稿', PENDING_APPROVAL: '待批准', ACTIVE: '生效中', SUSPENDED: '已暂停',
  FROZEN: '已冻結', EXPIRED: '已過期', REVOKED: '已撤銷',
  NOT_REQUESTED: '未申請', REQUESTED: '已申請', APPROVED: '已批准', DENIED: '已拒絕',
};

// ── 風控等级 Risk Level ──
const _RISK_LEVEL_CN = {
  NORMAL: '正常（無限制）', CAUTIOUS: '謹慎（降低倉位）', REDUCED: '縮减（限制開倉）',
  DEFENSIVE: '防御（只許平倉）', CIRCUIT_BREAKER: '熔斷（全部冻結）', MANUAL_REVIEW: '人工審核（全停）',
};

// ── 訂單状态 OMS Order State ──
const _OMS_STATE_CN = {
  PENDING_NEW: '等待提交', ACCEPTED: '已接受', REJECTED: '被拒絕', PARTIALLY_FILLED: '部分成交',
  FILLED: '完全成交', PENDING_CANCEL: '等待取消', CANCELLED: '已取消',
  EXPIRED: '已過期', FAILED: '失败', PENDING_AMEND: '等待修改', AMENDED: '已修改',
};

// ── 決策租約状态 Decision Lease State ──
const _LEASE_STATE_CN = {
  IDLE: '空閒', REQUESTED: '已請求', ACTIVE: '生效中', EXECUTING: '執行中',
  COMPLETED: '已完成', EXPIRED: '已過期', REVOKED: '已撤銷', FAILED: '失败',
};

// ── 組件名 Component Names ──
const _COMP_CN = {
  risk_manager: '風控管理器', RiskManager: '風控管理器', RiskGovernor: '風控治理器',
  PaperTradingEngine: 'Paper 模擬', paper_engine: 'Paper 模擬',
  governance_hub: '治理中枢', GovernanceHub: '治理中枢',
  linear: '合約(USDT)', spot: '現货', inverse: '反向合約', option: '期權',
  Authorization: '授權系統', DecisionLease: '決策租約', OMS: '訂單管理',
};
function _translateComp(c) { return _COMP_CN[c] || c; }

// ── 发起人 Who ──
function _translateWho(who) {
  if (!who) return '--';
  if (who === 'demo-operator' || who === 'operator') return '操作員 Operator';
  if (who === 'system' || who === 'SYSTEM') return '系統自動 System';
  if (who === 'GovernanceHub') return '治理中枢 GovernanceHub';
  if (who === 'RiskManager') return '風控管理器 RiskManager';
  if (who === 'PaperLiveGate') return 'Paper→Live 准入门控';
  if (who.toLowerCase().includes('agent')) return 'AI Agent 代理';
  return who;
}

// 翻译一個状态值（嘗試所有状态字典）
function _translateStateVal(val) {
  if (!val || typeof val !== 'string') return val;
  return _AUTH_STATE_CN[val] || _RISK_LEVEL_CN[val] || _OMS_STATE_CN[val] || _LEASE_STATE_CN[val] || val;
}

// ── 核心：what 描述翻译 + 審批后果說明 ──
// 每條規則：{ pattern, cn: 中文描述, approve: 批准后果, reject: 拒絕后果 }
// 覆盖所有 record_change() 調用產生的 what 文本
const _WHAT_RULES = [

  // ═══ 1. 對賬不一致 ═══
  { pattern: /^Reconciliation mismatch detected: (.+)$/,
    cn: (m) => '賬目核對發現差異 — 严重性：' + m[1],
    risk: '中-高',
    detail: '系統核對本地持倉/訂單記錄与交易所實際状态時發現不一致。差異可能影响風險敞口計算的准确性。CRITICAL 级别将自動提升風控等级。',
    explain: '系統会定期把"我们自己記錄的持倉和訂單"与"交易所那边實際的數據"做對比。如果兩边對不上，就說明某處出了偏差。\n\n'
      + '常见原因：網絡延遲导致同步滞后、交易所端訂單被手動修改、系統重啟后部分状态未恢復。\n\n'
      + '如果差異涉及持倉數量，意味着我们以为的風險和實際風險可能不同——這種情况需要尽快排查。',
    approve: '确認差異已知晓，系統繼續運行。CRITICAL 级别将自動触发風控升级。',
    reject: '標記为需進一步調查。系統不停止，但記錄保持待處理状态。',
  },

  // ═══ 2. 授權冻結 ═══
  { pattern: /^Authorization frozen: (\d+) active leases revoked$/,
    cn: (m) => '授權已冻結 — ' + m[1] + ' 個交易許可已撤銷',
    risk: '高',
    detail: '系統檢測到严重異常，已執行紧急冻結。所有進行中的交易許可被强制撤銷，系統停止接受新交易指令。需在「授權管理」區域手動恢復。',
    explain: '這相當于按下了"紧急暂停键"。当系統發現严重问題（比如風控連續告警、對賬严重不一致）時，會自動冻結一切交易活動来保護賬户。\n\n'
      + '冻結后，AI 無法再執行任何新的买卖操作，直到你手動排查问題并在上方「授權管理」區域恢復授權。\n\n'
      + '注意：拒絕此記錄不會解除冻結——冻結只能通過手動操作恢復。',
    approve: '确認冻結必要，系統保持冻結状态。',
    reject: '記錄異議，但系統仍保持冻結。解冻需在「授權管理」中手動操作。',
  },

  // ═══ 3. 授權缓存刷新 ═══
  { pattern: /^Authorization cache invalidated$/,
    cn: () => '授權缓存已刷新',
    risk: '無',
    detail: '授權状态变更后，內部缓存已自動清理并重新載入。屬於正常系統維護操作，無需人工干预。',
    explain: '這是系統內部的"自動刷新"。每次授權状态發生变化（比如从"待審批"变成"已激活"），系統需要清理旧的缓存數據，确保所有模块读到的都是最新状态。\n\n'
      + '你通常不需要對這條記錄做任何操作——除非你最近没有做過任何授權变更却频繁看到此記錄，那可能意味着有程序異常。',
    approve: '确認知晓，無需后續操作。',
    reject: '標記異常。仅在未预期出現此記錄時使用。',
  },

  // ═══ 4. 風控等级变更 ═══
  { pattern: /^Risk level changed: (.+) → (.+)$/,
    cn: (m) => '風控保護等级調整：' + (_RISK_LEVEL_CN[m[1]] || m[1]) + ' → ' + (_RISK_LEVEL_CN[m[2]] || m[2]),
    risk: '中',
    detail: '系統根據市场状况或賬户表現自動調整了風控等级。等级越高，倉位限制越严格、止損越紧。調整不可通過拒絕回退，如需修改請在「風控管理」中操作。',
    explain: '風控等级決定了系統允許承受多大的風險。当市场剧烈波動或賬户出現亏損時，系統會自動提高等级（更严格的保護）；市场平稳時会降低等级（恢復正常交易空間）。\n\n'
      + '等级提高 = 更安全但交易空間受限（倉位更小、止損更紧）\n'
      + '等级降低 = 交易空間更大但風險增加',
    approve: '同意風控調整，系統按新等级執行。',
    reject: '記錄異議。風控等级不會回退，如需調整請在「風控管理」中操作。',
  },

  // ═══ 5. 風控降级已執行 ═══
  { pattern: /^RiskGovernor de-escalation approved: (.+) → (.+)$/,
    cn: (m) => '風控降级已執行：' + (_RISK_LEVEL_CN[m[1]] || m[1]) + ' → ' + (_RISK_LEVEL_CN[m[2]] || m[2]),
    risk: '低',
    detail: '此前提交的風控等级降低請求已获批并執行。系統已恢復至更宽松的保護等级，允許更大倉位和更多交易操作。此記錄为已完成操作的确認。',
    explain: '有人（通常是你自己）認为之前的高風控等级不再必要，提交了降级請求并已获批。現在系統回到了更宽松的状态，AI 可以使用更大的倉位進行交易。\n\n'
      + '這條記錄只是告知你操作已完成，批准或拒絕都不會改变已經執行的結果。',
    approve: '确認知晓操作已完成。',
    reject: '無實際效果，操作已執行。',
  },

  // ═══ 6. 交易授權状态变更 ═══
  { pattern: /^Authorization: (.+) → (.+)$/,
    cn: (m) => '交易授權状态变更：' + (_AUTH_STATE_CN[m[1]] || m[1]) + ' → ' + (_AUTH_STATE_CN[m[2]] || m[2]),
    risk: '低-中',
    detail: '交易授權控制系統是否有權執行交易。状态包括：草稿(DRAFT)、待審批(PENDING)、已激活(ACTIVE)、已限制(RESTRICTED)、已冻結(FROZEN)、已過期(EXPIRED)。Paper 模擬授權自動批准，Live 實盤需人工審批。',
    explain: '交易授權相當于系統的"营業執照"——有效時可以交易，失效時一切停止。\n\n'
      + '状态流转：草稿 → 待審批 → 已激活 → （正常運行） → 過期/冻結/撤銷\n\n'
      + 'Paper 模擬（無真實資金）的授權會自動批准。如果未來啟用 Live 實盤交易，每次授權都需要你亲自審批。\n\n'
      + '拒絕不會回退状态变更，要修改請在「授權管理」區域操作。',
    approve: '同意此授權变更。',
    reject: '記錄異議。状态不會回退，如需修改請在「授權管理」中操作。',
  },

  // ═══ 7. 風控引擎状态转换 ═══
  { pattern: /^RiskGovernor: (.+) → (.+)$/,
    cn: (m) => '風控引擎状态转换：' + (_RISK_LEVEL_CN[m[1]] || m[1]) + ' → ' + (_RISK_LEVEL_CN[m[2]] || m[2]),
    risk: '中',
    detail: '風控引擎保護等级發生变化。等级从低到高：正常→注意→警告→危險→紧急。升级为保護措施，降级需确認市场已恢復稳定。',
    explain: '風控引擎是系統中負責"盯風險"的核心模块。它有 5 個保護等级，類似天气预警的蓝色/黃色/橙色/红色信號。\n\n'
      + '等级提高通常是因为：市场波動加剧、賬户亏損增加、或對賬發現異常。\n'
      + '等级降低通常是因为：異常已消除、市场恢復平稳。',
    approve: '确認風控引擎判斷正确。',
    reject: '標記需審查。等级不會自動回退。',
  },

  // ═══ 8. 訂單状态变更 ═══
  { pattern: /^OmsOrder (.+): (.+) → (.+)$/,
    cn: (m) => '訂單 ' + m[1].substring(0,12) + '… 状态变更：' + (_OMS_STATE_CN[m[2]] || m[2]) + ' → ' + (_OMS_STATE_CN[m[3]] || m[3]),
    risk: '低',
    detail: '交易訂單執行状态發生转换。正常流程：建立→提交→成交。出現"已拒絕"可能因價格滑点過大或余额不足。單笔訂單状态变更通常無需人工干预。',
    explain: '每一笔交易訂單都有一個生命周期：建立 → 提交給交易所 → 交易所确認成交（或拒絕）。\n\n'
      + '如果看到"已拒絕(REJECTED)"，可能的原因：\n'
      + '• 賬户余额不足以下這笔單\n'
      + '• 市场價格变化太快，超出了可接受的範圍\n'
      + '• 訂單數量不符合交易所的最小/最大限制\n\n'
      + '偶尔的拒絕是正常的。如果大量訂單被拒絕，則可能需要檢查賬户状态或参數配置。',
    approve: '确認訂單執行流程正常。',
    reject: '標記訂單可能存在異常，需人工檢查。',
  },

  // ═══ 9. AI 交易許可变更 ═══
  { pattern: /^DecisionLease: (.+) → (.+)$/,
    cn: (m) => 'AI 交易許可变更：' + (_LEASE_STATE_CN[m[1]] || m[1]) + ' → ' + (_LEASE_STATE_CN[m[2]] || m[2]),
    risk: '低',
    detail: 'AI 的临時交易執行許可發生状态变更。許可有時效性，到期后 AI 需重新申請方可繼續交易。這是防止 AI 異常時無限制下單的安全機制。',
    explain: 'AI 每次要執行交易前，必须先获取一個有時間限制的"通行證"（交易許可）。通行證到期后 AI 就不能再下單，必须重新申請。\n\n'
      + '這個機制的目的是防止 AI 在出現故障時疯狂下單——即使 AI 認为應該交易，没有有效通行證就無法執行。\n\n'
      + '許可的获取和釋放是自動完成的，正常情况下不需要你做任何操作。',
    approve: '确認許可变更正常。',
    reject: '標記異常。仅在 AI 不應获得許可時使用。',
  },

  // ═══ 10. 紧急熔斷 — 回撤 ═══
  { pattern: /^Session halted due to drawdown/,
    cn: () => '交易暂停 Trading Halted — 回撤超過安全阈值',
    risk: '高',
    detail: '賬户净值从最高点回撤幅度超過预設阈值，系統已自動暂停所有新交易。需檢查持倉和市场状况，确認安全后在「授權租約 Lease」區域重新啟動。熔斷不可通過拒絕取消。',
    explain: '你的賬户净值从歷史最高点下跌的比例，超過了你設定的安全線。這就像汽车的安全气囊——檢測到"碰撞"后自動弹出保護。\n\n'
      + '熔斷后系統不會再開任何新倉，但已有的持倉不會被自動平掉。你需要：\n'
      + '1. 查看當前持倉和市场走势\n'
      + '2. 決定是否手動平掉部分或全部持倉\n'
      + '3. 等市场恢復后，在「授權租約 Lease」區域手動重新啟動交易',
    approve: '确認知晓熔斷，系統保護措施已生效。',
    reject: '無實際效果。熔斷为自動保護機制，恢復交易需手動操作。',
  },

  // ═══ 11. 紧急熔斷 — 單日亏損 ═══
  { pattern: /^Session halted due to daily loss/,
    cn: () => '交易暂停 Trading Halted — 單日亏損超過限额',
    risk: '高',
    detail: '今日累計亏損超過预設的單日最大限额，系統已自動暂停所有新交易。次日将自動重置，或可在「授權租約 Lease」中調整限额后手動恢復。熔斷不可通過拒絕取消。',
    explain: '今天的總亏損金额超過了你設定的"每天最多亏多少"的上限。這就像信用卡的每日消費限额——到达上限后自動锁定。\n\n'
      + '恢復方式：\n'
      + '1. 等到次日（限额會自動重置）\n'
      + '2. 如果你确認當前市场状况安全，可以手動調高限额后重啟交易',
    approve: '确認知晓熔斷，保護措施已生效。',
    reject: '無實際效果。恢復交易需手動操作或等待次日重置。',
  },

  // ═══ 12. 風控参數修改 ═══
  { pattern: /^Updated risk config parameter: (.+)$/,
    cn: (m) => '風控参數已修改：' + m[1],
    risk: '中',
    detail: '風控配置参數已被修改（可能由 AI 自主優化或系統自動調整）。参數直接影响倉位大小、止損比例等交易行为。拒絕仅標記記錄，不回退参數。如需改回請在「風控設置」中操作。',
    explain: '風控参數控制着交易的安全边界，例如：\n'
      + '• 最大倉位大小 = 每笔交易最多投入多少資金\n'
      + '• 止損比例 = 亏損到什么程度自動止損\n'
      + '• 最大持倉數量 = 同時最多持有几個品種\n'
      + '• 每日最大亏損限额 = 一天最多允許亏多少\n\n'
      + '参數放宽意味着交易更激進（潜在收益和風險都增大），收紧意味着更保守（風險降低但機會也减少）。',
    approve: '确認参數調整合理，系統按新参數執行。',
    reject: '記錄異議。参數不會自動回退，如需改回請在「風控設置」中操作。',
  },

  // ═══ 13. Paper 模擬→Live 實盤 評估 ═══
  { pattern: /^PaperLiveGate evaluation: (.+)$/,
    cn: (m) => 'Paper 模擬 → Live 實盤 升级評估：' + m[1],
    risk: '無',
    detail: '系統完成了从 Paper 模擬 升级至 Live 實盤 的準備度評估（含勝率、盈亏比、運行天數、回撤、稳定性等 11 项指標）。評估結果不會自動改变系統模式，升级需在「授權管理」中手動授權。',
    explain: '這是系統自動做的一個"體檢報告"——評估目前的 Paper 模擬 表現是否达到了可以用真金白银做 Live 實盤 的標准。\n\n'
      + '評估指標包括：Paper 模擬 至少運行 21 天、勝率达標、盈亏比合理、最大回撤可控、系統運行稳定等。\n\n'
      + 'PASS = 各项达標，可以考虑升级到 Live 實盤\n'
      + 'FAIL = 還有指標未达標，建議繼續 Paper 模擬\n\n'
      + '無論評估結果如何，系統不會自動切换到 Live 實盤——必须你手動授權。',
    approve: '确認已阅读評估報告。',
    reject: '記錄對評估結果的疑问。不影响系統運行。',
  },

  // ═══ 16. 门控事件 ═══
  { pattern: /^Gate event: (.+)$/,
    cn: (m) => 'Paper 模擬 → Live 實盤 门控事件：' + m[1],
    risk: '無',
    detail: 'Paper 模擬 → Live 實盤 门控系統產生了事件記錄（如評估啟動、指標达標/不达標等）。仅为信息記錄，不影响當前交易。',
    explain: '门控系統会持續跟踪各项指標，并在指標發生变化時生成事件記錄。例如"某项指標刚刚达標"或"新一轮評估開始"。\n\n'
      + '這些事件不會改变任何交易行为，只是帮你了解系統向 Live 實盤 邁進的進度。',
    approve: '确認已阅读。',
    reject: '標記需進一步了解。',
  },
];

// ── 翻译 what 描述 ──
function _translateWhat(what) {
  if (!what) return '（無描述）';
  for (const rule of _WHAT_RULES) {
    const m = what.match(rule.pattern);
    if (m) return typeof rule.cn === 'function' ? rule.cn(m) : rule.cn;
  }
  return what; // 無匹配規則時返回原文
}

// ── 获取審批后果說明 ──
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
  // 先嘗試翻译單個状态值
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
      // 特殊處理常见對象結構
      if ('session_halted' in parsed) {
        return parsed.session_halted ? '交易已暂停 Trading Halted' + (parsed.halt_reason ? '（' + parsed.halt_reason + '）' : '') : '交易正常運行';
      }
      // 通用對象：转为 key=value 對
      return Object.entries(parsed).map(([k,v]) => k + '=' + v).join(', ');
    }
    return String(parsed);
  } catch (_) {
    // 非 JSON，嘗試翻译为已知状态
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
      comps = '<div style="margin-top:4px;font-size:11px;color:var(--text-dim)">影响範圍：'
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
    // 風險標簽 + 正式說明（始終可见）
    if (guidance) {
      let riskColor = 'var(--text-dim)';
      if (guidance.risk === '高') riskColor = 'var(--red)';
      else if (guidance.risk === '中' || guidance.risk === '中-高') riskColor = 'var(--yellow, #d29922)';
      else if (guidance.risk === '低' || guidance.risk === '低-中') riskColor = 'var(--green)';

      if (guidance.risk) {
        html += '<span style="display:inline-block;margin-bottom:6px;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:600;'
          + 'background:' + riskColor + '22;color:' + riskColor + ';border:1px solid ' + riskColor + '44'
          + '">風險等级：' + ocEsc(guidance.risk) + '</span>';
      }
      if (guidance.detail) {
        html += '<div style="margin-bottom:8px;padding:8px 10px;background:rgba(88,166,255,0.06);border-left:3px solid var(--accent);border-radius:0 6px 6px 0;font-size:11px;color:var(--text);line-height:1.7">'
          + ocEsc(guidance.detail) + '</div>';
      }
      // Collapsible plain-language explanation (hidden by default)
      // 可折叠的通俗說明（默認隐藏）
      if (guidance.explain) {
        const eid = 'explain-' + cid.replace(/[^a-zA-Z0-9]/g, '');
        html += '<details style="margin-bottom:8px;font-size:11px"><summary style="cursor:pointer;color:var(--accent);user-select:none;padding:4px 0">'
          + '详細說明 / Learn more</summary>'
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
      html += '<div style="color:var(--text);line-height:1.6">' + ocEsc(guidance ? guidance.approve : '确認此变更有效。') + '</div>';
      html += '</div>';
      html += '<div style="flex:1;padding:8px 10px;background:rgba(248,81,73,0.06)">';
      html += '<div style="font-weight:600;color:var(--red);margin-bottom:4px">✖ 拒絕后果</div>';
      html += '<div style="color:var(--text);line-height:1.6">' + ocEsc(guidance ? guidance.reject : '標記此变更为不合規，需要進一步處理。') + '</div>';
      html += '</div>';
      html += '</div></div>';

      html += '<div style="display:flex;gap:8px;margin-top:10px">';
      html += '<button class="oc-btn oc-btn-success" style="font-size:12px;padding:6px 20px" '
        + 'onclick="auditApprove(\'' + cidJs + '\')">✔ 批准</button>';
      html += '<button class="oc-btn oc-btn-danger" style="font-size:12px;padding:6px 20px" '
        + 'onclick="auditReject(\'' + cidJs + '\')">✖ 拒絕</button>';
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
  const reason = await openPromptModal({
    title: '批准原因 / Approval Reason',
    body: '可選。留空将按無備注批准。',
    label: '原因 / Reason',
    confirmLabel: '批准 / Approve'
  });
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
  const reason = await openPromptModal({
    title: '拒絕原因 / Rejection Reason',
    label: '原因 / Reason',
    required: true,
    multiline: true,
    confirmLabel: '拒絕 / Reject'
  });
  if (!reason || !reason.trim()) { ocToast('Please enter a rejection reason / 請輸入拒絕原因', 'error'); return; }
  const d = await govRejectAuditChange(changeId, reason.trim());
  if (d && d.ok) {
    ocToast('Change rejected / 变更已拒絕', 'success');
    loadPendingApprovals();
  } else {
    ocToast((d && d.message) || 'Reject failed / 拒絕失败', 'error');
  }
}

async function bulkAudit(action) {
  const isApprove = action === 'approve';
  // W-AUDIT-7c (2026-05-09): 批次 approve / reject 是 critical-grade governance 寫操作，
  // 影響可能涉及多筆 SM-01 / SM-04 / SM-02 變更；用高摩擦 typed-confirm 取代 native confirm()，
  // 避免一鍵誤觸全批通過 / 全批拒絕。phrase = 'CONFIRM'，case-sensitive。
  // round 2 fix [#7]：trigger button 在 await modal **前** disabled，try/finally 復位，避免併發雙觸。
  // round 2 fix [#5]：modal body 顯示具體 PENDING 筆數 + 前 5 筆 change_id，避免凌晨盲飛。
  // round 2 fix [#8][#9]：cancel/部分失敗顯 toast + 失敗 change_id 列表。
  const triggerBtn = (typeof event !== 'undefined' && event && event.currentTarget) ? event.currentTarget : null;
  if (triggerBtn) triggerBtn.disabled = true;
  try {
    // 先 fetch pending list，modal body 才能顯示 N 筆 + 前 5 筆 change_id。
    // 此處 fetch 失敗 = 後端不可用，直接 abort，不開 modal。
    const pending = await govGetPendingAudit();
    if (!pending || !pending.ok || !Array.isArray(pending.data)) {
      ocToast('获取待審批列表失败 / Failed to load pending list', 'error');
      return;
    }
    const items = pending.data;
    if (items.length === 0) {
      ocToast('目前沒有待審批變更 / No pending changes', 'neutral');
      return;
    }
    // 同步刷新 cache（loadPendingApprovals 之外的入口也能更新）
    _lastPendingAudit = items;

    const sample = items.slice(0, 5).map(function(c) { return c.change_id || c.id || '(no-id)'; });
    const overflow = items.length > 5 ? ('\n... 及其他 ' + (items.length - 5) + ' 筆') : '';
    const sampleLines = sample.map(function(id, i) { return '  ' + (i + 1) + '. ' + id; }).join('\n');

    const titleZh = isApprove ? '批量批准全部待審 / Bulk Approve All Pending' : '批量拒絕全部待審 / Bulk Reject All Pending';
    const bodyZh = (isApprove
      ? '即將批准 ' + items.length + ' 筆 PENDING 變更，立即生效。\n受影響範圍可能包含 SM-01 授權、SM-04 風險等級、Decision Lease 規則。\n建議先逐項複核後再批量通過。'
      : '即將拒絕 ' + items.length + ' 筆 PENDING 變更，理由將寫入 audit trail。\n拒絕後待審項回復為已關閉狀態，需重新申請。'
    ) + '\n\n變更清單（前 5 筆）:\n' + sampleLines + overflow;

    // round 3 fix HIGH-1：await openTypedConfirmModal 必包 try/catch；
    //   singleton guard 在已開 modal 時 reject('modal already open')，
    //   caller 若不接 → unhandled rejection + finally 仍 re-enable button =
    //   user 誤判「按了沒反應」再點一次。本 try/catch 把 reject 顯式 toast 出來。
    let proceed;
    try {
      proceed = await openTypedConfirmModal({
        title: titleZh,
        body: bodyZh,
        phrase: 'CONFIRM',
        confirmLabel: isApprove ? '確認批量批准 / Approve All' : '確認批量拒絕 / Reject All',
        confirmClass: isApprove ? 'oc-btn-primary' : 'oc-btn-danger',
        impact: '所有 ' + items.length + ' 筆 PENDING 同時 commit',
        rollback: '無自動回滾；需個別申請新變更覆蓋'
      });
    } catch (err) {
      if (err && err.message === 'modal already open') {
        ocToast('已有確認對話框打開，請先完成當前操作 / Another confirm dialog is open', 'warn');
      } else {
        ocToast('開啟確認對話框失敗 / Open confirm dialog failed: ' + (err && err.message || err), 'error');
      }
      return; // finally 會 re-enable button
    }
    if (!proceed) {
      ocToast('已取消批量' + (isApprove ? '批准 / Bulk approve cancelled' : '拒絕 / Bulk reject cancelled'), 'neutral');
      return;
    }

    let reason;
    if (isApprove) {
      reason = 'Operator bulk approved';
    } else {
      const promptResult = await openPromptModal({
        title: '批量拒絕原因 / Bulk Rejection Reason',
        label: '原因 / Reason',
        required: true,
        multiline: true,
        confirmLabel: '拒絕全部 / Reject All'
      });
      reason = (promptResult || '').trim();
      if (!reason) {
        ocToast('已取消批量拒絕（未提供原因） / Bulk reject cancelled (no reason)', 'neutral');
        return;
      }
    }

    // counter 不再用 `ok` / `fail`（與外層 `proceed` 命名衝突已解，但保持語意清晰；
    // round 2 fix [#1]：原本宣告兩次 `ok` 觸發 SyntaxError 整檔 parse fail）
    let okCount = 0, failCount = 0;
    const failedChangeIds = [];
    for (const c of items) {
      const d = isApprove
        ? await govApproveAuditChange(c.change_id, reason)
        : await govRejectAuditChange(c.change_id, reason);
      if (d && d.ok) {
        okCount++;
      } else {
        failCount++;
        failedChangeIds.push(c.change_id || c.id || '(no-id)');
      }
    }

    const label = isApprove ? '同意 approved' : '拒絕 rejected';
    let toastMsg = okCount + ' 项已' + label + (failCount ? '，' + failCount + ' 项失败' : '');
    if (failedChangeIds.length) {
      // 失敗詳情 toast 後再開一個常駐 banner 顯示完整 id list（≤ 10 個直顯，超過截斷）
      const shown = failedChangeIds.slice(0, 10).join(', ');
      const more = failedChangeIds.length > 10 ? ' ...(+' + (failedChangeIds.length - 10) + ')' : '';
      toastMsg += '\n失敗：[' + shown + more + ']';
    }
    ocToast(toastMsg, okCount ? (failCount ? 'warn' : 'success') : 'error');
    loadPendingApprovals();
  } finally {
    if (triggerBtn) triggerBtn.disabled = false;
  }
}

async function loadPendingApprovals() {
  // round 2 fix [#5][#6]：每次刷新都同步更新 cache，
  // 供 bulkAudit / confirmApproveRecovery modal body 顯示具體影響使用。
  const recovery = await govGetPendingRecovery();
  if (recovery && recovery.ok) {
    _lastPendingRecovery = Array.isArray(recovery.data) ? recovery.data : [];
    renderPendingRecovery(_lastPendingRecovery);
  } else {
    _lastPendingRecovery = [];
    const el = document.getElementById('pending-recovery-content');
    if (el) el.innerHTML = '<p style="color:var(--red);font-size:12px">Failed to load recovery requests / 載入恢復請求失敗（治理中枢可能未啟用）</p>'; // SAFE: static HTML only
  }

  const audit = await govGetPendingAudit();
  if (audit && audit.ok) {
    _lastPendingAudit = Array.isArray(audit.data) ? audit.data : [];
    renderPendingAudit(_lastPendingAudit);
  } else {
    _lastPendingAudit = [];
    const el = document.getElementById('pending-audit-content');
    if (el) el.innerHTML = '<p style="color:var(--red);font-size:12px">Failed to load pending approvals / 載入待批准項目失敗（治理中枢可能未啟用）</p>'; // SAFE: static HTML only
  }
}

async function confirmApproveRecovery(requestId) {
  // W-AUDIT-7c (2026-05-09): Recovery approve 是 critical-grade governance 寫操作，
  // 接受 recovery request 等於放寬已被風控擋下的執行邊界（SM-04 / Decision Lease）。
  // 用高摩擦 typed-confirm 取代 native confirm()，phrase = 'CONFIRM'。
  // round 2 fix [#6]：先從 _lastPendingRecovery cache 找具體 request 細節
  //   （strategy / symbol / freeze reason / 待 review 時長），modal body 顯示，
  //   避免 funding_arb_BTCUSDT vs bb_breakout_ETHUSDT 盲批准。
  // round 2 fix [#7]：trigger button 在 await modal **前** disabled，try/finally 復位。
  // round 2 fix [#8]：cancel 顯 toast，不靜默 return。
  const triggerBtn = (typeof event !== 'undefined' && event && event.currentTarget) ? event.currentTarget : null;
  if (triggerBtn) triggerBtn.disabled = true;
  try {
    // 從已 cache 的 list 中找該 request；無新 API call。
    let req = null;
    if (Array.isArray(_lastPendingRecovery) && _lastPendingRecovery.length) {
      req = _lastPendingRecovery.find(function(r) { return (r.request_id || r.id) === requestId; }) || null;
    }
    // 若 cache 過期或沒命中（例如 user 未刷新），強制 reload 一次再找
    if (!req) {
      try {
        const fresh = await govGetPendingRecovery();
        if (fresh && fresh.ok && Array.isArray(fresh.data)) {
          _lastPendingRecovery = fresh.data;
          req = fresh.data.find(function(r) { return (r.request_id || r.id) === requestId; }) || null;
        }
      } catch (_e) { /* fallthrough — modal still 可開但只顯通用 body */ }
    }

    let detailLines = '';
    if (req) {
      const parts = [];
      if (req.strategy) parts.push('策略 / Strategy: ' + req.strategy);
      if (req.symbol) parts.push('幣種 / Symbol: ' + req.symbol);
      if (req.freeze_reason || req.reason) parts.push('凍結原因 / Freeze reason: ' + (req.freeze_reason || req.reason));
      if (req.description) parts.push('說明 / Description: ' + req.description);
      if (req.created_at || req.requested_at) {
        const tsRaw = req.created_at || req.requested_at;
        const ts = new Date(tsRaw);
        if (!isNaN(ts.getTime())) {
          const ageMs = Date.now() - ts.getTime();
          const ageMin = Math.max(0, Math.floor(ageMs / 60000));
          parts.push('待 review 時長 / Pending for: ' + ageMin + ' min（自 ' + tsRaw + '）');
        } else {
          parts.push('提交時間 / Requested: ' + tsRaw);
        }
      }
      if (parts.length) detailLines = '\n\n變更細節:\n  ' + parts.join('\n  ');
    } else {
      detailLines = '\n\n（請求細節無法載入，僅以 ID 識別）';
    }

    // round 3 fix HIGH-1：await openTypedConfirmModal 必包 try/catch；singleton guard reject 不靜默。
    // round 3 fix LOW-1：rename `const ok` → `const proceed`，與 bulkAudit 保持一致避免 future-proofing footgun。
    let proceed;
    try {
      proceed = await openTypedConfirmModal({
        title: '批准恢復請求 / Approve Recovery Request — ' + requestId,
        body: '批准恢復請求 = 放寬已被風控阻擋的執行邊界。\n受影響範圍：SM-04 風險等級、Decision Lease 授權鏈、可能觸發 Executor 重新進入 active 狀態。\n請確認 incident root cause 已查清且風控狀態安全。' + detailLines,
        phrase: 'CONFIRM',
        confirmLabel: '確認批准恢復 / Approve Recovery',
        confirmClass: 'oc-btn-danger',
        impact: '放寬風控保護邊界；對賬 / 風控可能立即重新啟用',
        rollback: '無自動回滾；需新發 recovery override 收回'
      });
    } catch (err) {
      if (err && err.message === 'modal already open') {
        ocToast('已有確認對話框打開，請先完成當前操作 / Another confirm dialog is open', 'warn');
      } else {
        ocToast('開啟確認對話框失敗 / Open confirm dialog failed: ' + (err && err.message || err), 'error');
      }
      return; // finally 會 re-enable button
    }
    if (!proceed) {
      ocToast('已取消批准恢復 / Recovery approval cancelled', 'neutral');
      return;
    }
    const d = await govApprovePendingRecovery(requestId);
    if (d && d.ok) {
      ocToast('Recovery request approved / 恢復請求已批准', 'success');
      loadPendingApprovals();
      loadAll();
    } else {
      ocToast(d ? d.message : 'Approval failed / 批准失敗', 'error');
    }
  } finally {
    if (triggerBtn) triggerBtn.disabled = false;
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
    // 檢測状态变更并渲染事件時間線（客户端會話數據）
    detectChanges(_currentStatus);
    renderIncidentLog();

    // Load audit trail from server (with client-side fallback)
    // 从服務端載入持久化審計日志（客户端回退）
    loadAuditTrail().catch(e => console.warn('Audit trail load failed:', e));

    // Load lease detail list from server
    // 从服務端載入租約详情列表
    // Backend returns {data: {active_count, total_tracked, leases: [...], all_leases: [...]}}
    // 后端返回 {data: {active_count, total_tracked, leases: [...], all_leases: [...]}}
    govGetLeases().then(ld => {
      const leaseList = (ld && ld.ok && ld.data && Array.isArray(ld.data.leases)) ? ld.data.leases : [];
      renderLeaseList(leaseList);
    }).catch(e => console.warn('Lease list load failed:', e));

    // Load Paper→Live Gate status
    // 載入 Paper→Live 门禁状态
    loadPaperLiveGate().catch(e => console.warn('PLG load failed:', e));

    // Load learning tier status
    // 載入學習層级状态
    loadLearningTier().catch(e => console.warn('Learning tier load failed:', e));

    // Load governance events feed
    // 載入治理事件流
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
