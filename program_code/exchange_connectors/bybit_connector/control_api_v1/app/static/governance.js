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
  // 对账前先拉取 paper engine 当前状态填充 paper_state
  // Before reconciling, fetch current paper engine metrics to populate paper_state

  let paperState = {};
  try {
    // 从 /api/v1/paper/status 获取仓位、余额和订单数量
    // Fetch positions, balance, total_orders from paper engine status
    const ps = await ocApi('/api/v1/paper/status');
    if (ps && ps.data) {
      const d = ps.data;
      paperState = {
        positions: d.positions || [],
        balance: d.balance !== undefined ? d.balance : null,
        total_orders: d.total_orders !== undefined ? d.total_orders : null,
      };
    }
  } catch (_e) {
    // paper status 获取失败时回退到空对象，不阻断对账
    // If paper status fetch fails, fall back to empty dict — do not block reconcile
    paperState = {};
  }

  return ocPost('/api/v1/governance/reconcile', {
    paper_state: paperState,
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

async function govGetAuditChanges(limit) {
  // GET /api/v1/governance/audit/changes — real persistent audit log
  // 获取真实持久化审计变更日志（ChangeAuditLog 写盘记录）
  return ocApi('/api/v1/governance/audit/changes?limit=' + (limit || 100));
}

async function govGetEvents(limit) {
  // GET /api/v1/governance/events — server-side governance event history
  // 获取服务端治理事件历史（跨重启持久化）
  return ocApi('/api/v1/governance/events?limit=' + (limit || 50));
}

async function govGetLearningTier() {
  // GET /api/v1/governance/learning-tier/status — tier level, metrics, promotion eligibility
  // 获取学习层级状态：当前层级、观察数、胜率、晋升资格
  return ocApi('/api/v1/governance/learning-tier/status');
}

async function govPromoteLearningTier(targetTier, reason) {
  // POST /api/v1/governance/learning-tier/promote — operator manual promotion
  // 操作员手动晋升学习层级（需 Operator 角色）
  return ocPost('/api/v1/governance/learning-tier/promote', {
    target_tier: targetTier,
    reason: reason || 'manual_operator_promotion',
    approved_by: 'operator',
  });
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
