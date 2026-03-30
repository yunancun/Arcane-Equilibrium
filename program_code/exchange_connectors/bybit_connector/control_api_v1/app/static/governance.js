/**
 * OpenClaw Trading System — Governance API Module
 * 治理系统 API 模块：授权、风控、租约、对账
 */

// ─── Constants ────────────────────────────────────────────────────────────────
const GOV_AUTH_STATES = {
  ACTIVE: 'good',
  RESTRICTED: 'warn',
  FROZEN: 'bad',
  PENDING_APPROVAL: 'info',
  DRAFT: 'neutral',
  NONE: 'neutral',
};

const GOV_RISK_LEVELS = {
  0: 'NORMAL',
  1: 'CAUTIOUS',
  2: 'REDUCED',
  3: 'DEFENSIVE',
  4: 'CIRCUIT_BREAKER',
  5: 'MANUAL_REVIEW',
};

const GOV_RISK_COLORS = {
  0: 'good',
  1: 'good',
  2: 'warn',
  3: 'warn',
  4: 'bad',
  5: 'bad',
};

const GOV_MODES = {
  NORMAL: 'good',
  RESTRICTED: 'warn',
  FROZEN: 'bad',
  MANUAL_REVIEW: 'info',
};

// ─── API Functions ────────────────────────────────────────────────────────────

async function govGetStatus() {
  // GET /api/v1/governance/status
  return ocApi('/api/v1/governance/status');
}

async function govGetAuthStatus() {
  // GET /api/v1/governance/auth/status
  return ocApi('/api/v1/governance/auth/status');
}

async function govPostApprove(note) {
  // POST /api/v1/governance/auth/approve
  return ocPost('/api/v1/governance/auth/approve', { approval_note: note || '' });
}

async function govGetRiskLevel() {
  // GET /api/v1/governance/risk/level
  return ocApi('/api/v1/governance/risk/level');
}

async function govPostOverride(targetLevel, reason) {
  // POST /api/v1/governance/risk/override
  return ocPost('/api/v1/governance/risk/override', {
    target_level: targetLevel,
    reason: reason || '',
  });
}

async function govPostReconcile(reason) {
  // POST /api/v1/governance/reconcile
  return ocPost('/api/v1/governance/reconcile', {
    paper_state: {},  // In full impl, would be populated from session state
    demo_state: null,
    reason: reason || 'manual_trigger',
  });
}

async function govGetLeases() {
  // GET /api/v1/governance/leases
  return ocApi('/api/v1/governance/leases');
}

async function govPostHealthCheck() {
  // POST /api/v1/governance/health-check
  return ocPost('/api/v1/governance/health-check', {});
}

async function govGetPendingRecovery() {
  // GET /api/v1/governance/recovery/pending
  return ocApi('/api/v1/governance/recovery/pending');
}

async function govApprovePendingRecovery(requestId) {
  // POST /api/v1/governance/recovery/{request_id}/approve
  return ocPost(`/api/v1/governance/recovery/${requestId}/approve`, {});
}

async function govGetPendingAudit() {
  // GET /api/v1/governance/audit/pending
  return ocApi('/api/v1/governance/audit/pending');
}

async function govGetSymbolWhitelist() {
  // GET /api/v1/governance/symbols/whitelist
  return ocApi('/api/v1/governance/symbols/whitelist');
}

async function govAddSymbolWhitelist(symbol, category) {
  // POST /api/v1/governance/symbols/whitelist
  return ocPost('/api/v1/governance/symbols/whitelist', {
    symbol: symbol,
    category: category,
  });
}

async function govRemoveSymbolWhitelist(symbol, category) {
  // DELETE /api/v1/governance/symbols/whitelist/{symbol}?category=...
  return ocApi(`/api/v1/governance/symbols/whitelist/${symbol}?category=${category}`, {
    method: 'DELETE',
  });
}

// ─── Render Helpers ──────────────────────────────────────────────────────────

function govAuthBadge(state) {
  // Returns ocChip HTML: ACTIVE→good, RESTRICTED→warn, FROZEN→bad, PENDING_APPROVAL→info
  const type = GOV_AUTH_STATES[state] || 'neutral';
  return ocChip(ocEsc(state), type);
}

function govRiskBadge(level) {
  // Returns ocChip HTML with level number and name
  const name = GOV_RISK_LEVELS[level] || 'UNKNOWN';
  const type = GOV_RISK_COLORS[level] || 'neutral';
  return ocChip(level + ' — ' + name, type);
}

function govModeBadge(mode) {
  // Returns ocChip HTML: NORMAL→good, RESTRICTED→warn, FROZEN→bad, MANUAL_REVIEW→info
  const type = GOV_MODES[mode] || 'neutral';
  return ocChip(ocEsc(mode), type);
}

function govExpiryCountdown(ms) {
  // Returns string like "2h 15m" or "EXPIRED" (red)
  if (!ms) return '--';

  const now = Date.now();
  const remaining = ms - now;

  if (remaining <= 0) {
    return ocChip('EXPIRED', 'bad');
  }

  const totalSecs = Math.floor(remaining / 1000);
  const hours = Math.floor(totalSecs / 3600);
  const minutes = Math.floor((totalSecs % 3600) / 60);

  if (hours > 0) {
    return hours + 'h ' + minutes + 'm';
  } else if (minutes > 0) {
    return minutes + 'm';
  } else {
    return '<' + totalSecs + 's';
  }
}

function govConsistencyIcon(isConsistent) {
  // Returns "✓ Consistent" or "⚠ Diverged"
  if (isConsistent === true) {
    return ocChip('✓ Consistent', 'good');
  } else if (isConsistent === false) {
    return ocChip('⚠ Diverged', 'warn');
  } else {
    return ocChip('-- Unknown', 'neutral');
  }
}
