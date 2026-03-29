# T3 治理集成指南 / T3 Governance Integration Guide

**Phase:** Phase 3 — 執行（修改與二次開發）
**Date:** 2026-03-30
**Authors:** FA (Architecture) + E1a (Implementation) + E5 (Optimization) + E2 (Review) + E3 (Security) + TW (Documentation)

---

## 1. Overview / 概述

Phase 3 將 4 個獨立的治理狀態機集成到現有交易系統中，形成統一的**治理集線器（GovernanceHub）**。該模式確保：

1. **H0 授權閘** — 每個操作前檢查授權狀態
2. **跨 SM 聯動** — 風險升級自動限制授權，對賬不一致觸發風險升級
3. **線程安全** — 所有跨 SM 操作由單一 RLock 保護
4. **Fail-Closed 安全** — 治理不可用時拒絕操作，不繞過

---

### 治理集線器的目的

The GovernanceHub serves as the **central orchestration point** for:

- **Authorization State Machine (SM-01)** — Manages trading approval scopes and expiration
- **Risk Governor State Machine (SM-04)** — Monitors risk metrics and escalates thresholds
- **Decision Lease State Machine (SM-02)** — Enforces "lease-before-decide" for trade intents
- **Reconciliation Engine (EX-04)** — Detects paper vs. demo/exchange state mismatches

Rather than modifying each SM's internal logic, Phase 3 **injects the hub at boundaries** — in API routes, trade submission, risk checks — to enforce governance without invasive changes.

---

## 2. Architecture / 架構

### 2.1 System Integration Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                     main.py (entrypoint)                         │
│  app.include_router(governance_router)  ← Phase 3 新增            │
└───────────────────────────┬──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                 governance_hub.py (NEW — 核心集成層)              │
│                                                                   │
│  Singleton Instances:                                             │
│    AUTH_SM    = AuthorizationStateMachine(...)                    │
│    RISK_GOV   = RiskGovernorStateMachine(...)                     │
│    LEASE_SM   = DecisionLeaseStateMachine(...)                    │
│    RECON_ENG  = ReconciliationEngine(...)                         │
│                                                                   │
│  Hot-Path Methods:                                                │
│    is_authorized()          → bool (100ms TTL cache)             │
│    check_risk_and_act()     → int (risk level)                   │
│    acquire_lease()          → str | None (lease_id)              │
│    release_lease()          → bool                                │
│    reconcile()              → dict (report)                       │
│    get_status()             → GovernanceStatus                    │
│                                                                   │
│  Cross-SM Wiring (Callbacks):                                     │
│    _on_risk_escalation()           (Risk → Auth/Lease)           │
│    _on_reconciliation_mismatch()   (Recon → Risk)                │
│    _on_auth_frozen()               (Auth → Lease)                │
└───────────────────────────┬──────────────────────────────────────┘
                            │
          ┌─────────────────┼──────────────────┐
          │                 │                  │
┌─────────▼───────┐  ┌──────▼────────┐  ┌────▼──────────┐
│ paper_trading_  │  │ pipeline_     │  │ risk_         │
│ routes.py       │  │ bridge.py     │  │ manager.py    │
│                 │  │               │  │               │
│ Initialize      │  │ on_tick():    │  │ check_        │
│ GOV_HUB here    │  │   check auth  │  │ positions():  │
│ Pass to ENGINE  │  │   check lease │  │   feed risk   │
│                 │  │   before      │  │   metrics to  │
│                 │  │   submit      │  │   RISK_GOV    │
└─────────────────┘  └───────────────┘  └───────────────┘
```

### 2.2 Core Components

#### governance_hub.py — GovernanceHub Class

**Location:** `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub.py`

```python
class GovernanceHub:
    """
    Thread-safe central integration point for all 4 governance state machines.
    保护所有跨 SM 操作的单一 RLock。
    """

    def __init__(self, *, audit_dir: str, enabled: bool = True):
        """Initialize all 4 SMs with audit callbacks."""

    def is_authorized(self) -> bool:
        """H0 gate check with 100ms TTL cache (hot path optimization)."""

    def get_risk_level(self) -> Optional[int]:
        """Current risk level (0=NORMAL ... 5=MANUAL_REVIEW)."""

    def check_risk_and_act(self, metrics: dict[str, Any]) -> Optional[int]:
        """Feed risk metrics; auto-escalate and restrict auth if needed."""

    def acquire_lease(self, intent_id: str, scope: str, ttl_seconds: float) -> Optional[str]:
        """Acquire decision lease for trade intent. Hot path; fail-closed."""

    def release_lease(self, lease_id: str, consumed: bool = False) -> bool:
        """Release or consume lease after execution."""

    def reconcile(
        self,
        paper_state: dict[str, Any],
        demo_state: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Run reconciliation; escalate risk if major mismatch detected."""

    def get_status(self) -> GovernanceStatus:
        """Combined governance status for API/GUI."""
```

---

## 3. API Reference / API 參考

### 3.1 GovernanceHub Python API

#### is_authorized() — H0 Gate Check

```python
def is_authorized(self) -> bool:
    """
    Check if current authorization permits operations.
    檢查當前授權是否允許操作。

    Hot path: Called on every tick/intent. Uses 100ms TTL cache.

    Returns:
        True if in ACTIVE or RESTRICTED state; False if FROZEN or disabled
    """
```

**Usage Example:**

```python
hub = GovernanceHub(audit_dir="/var/log/openclaw_audit")

# Before starting a trading session
if not hub.is_authorized():
    print("Trading authorization denied")
    return

# Proceed with trading
```

**Cache Behavior:**
- First call acquires lock, queries `AuthorizationSM.get_effective()`
- Result cached for 100ms (configurable via `_cache_ttl_ms`)
- Cache invalidated on `restrict()`, `freeze()`, or risk escalation
- Subsequent calls within TTL window skip lock entirely (lock-free fast path)

---

#### check_risk_and_act() — Risk Evaluation

```python
def check_risk_and_act(self, metrics: dict[str, Any]) -> Optional[int]:
    """
    Feed risk metrics to governor; auto-escalate if thresholds exceeded.
    將風險指標提供給總督；如果超過閾值則自動升級。

    Args:
        metrics: Risk metrics dict, e.g.:
            {
                'drawdown_pct': 5.2,
                'daily_loss_pct': 3.1,
                'correlation_alert': True,
                'var_breach': False
            }

    Returns:
        New risk level (0-5) or None on error

    Cascading Actions:
        Level ≥ 2 (REDUCED) → restrict all ACTIVE authorizations
        Level ≥ 4 (CIRCUIT_BREAKER) → freeze all authorizations
        Level ≥ 5 (MANUAL_REVIEW) → change mode to MANUAL_REVIEW
    """
```

**Usage Example:**

```python
from program_code.exchange_connectors.bybit_connector.control_api_v1.app import GOV_HUB

# In risk_manager.py after computing risk metrics
metrics = {
    'drawdown_pct': risk_pressure['drawdown'],
    'daily_loss_pct': risk_pressure['daily_loss'],
}
new_level = GOV_HUB.check_risk_and_act(metrics)
if new_level and new_level >= 4:
    logger.warning(f"Circuit breaker triggered: risk level {new_level}")
```

---

#### acquire_lease() — Lease Acquisition

```python
def acquire_lease(
    self,
    intent_id: str,
    scope: str,
    ttl_seconds: float = 30.0
) -> Optional[str]:
    """
    Acquire a decision lease for a trade intent.
    為交易意圖獲取決策租約。

    Args:
        intent_id: Unique identifier for this trade decision
        scope: Lease scope, e.g. 'TRADE_ENTRY', 'TRADE_EXIT'
        ttl_seconds: Lease validity window (default 30s)

    Returns:
        lease_id (str) if successful; None if denied (fail-closed)

    Fail-Closed Scenarios:
        - Authorization not in ACTIVE/RESTRICTED state
        - Authorization does not permit this scope
        - Lease SM unavailable
        - Governance disabled
    """
```

**Usage Example:**

```python
# In paper_trading_engine.submit_order()
lease_id = hub.acquire_lease(
    intent_id=order.order_id,
    scope="TRADE_ENTRY",
    ttl_seconds=30.0
)

if lease_id is None:
    return {"ok": False, "reason": "Lease denied"}

try:
    # Execute order
    result = self._fill_order(order)
finally:
    # Consume lease on completion
    hub.release_lease(lease_id, consumed=True)
```

---

#### reconcile() — Reconciliation

```python
def reconcile(
    self,
    paper_state: dict[str, Any],
    demo_state: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """
    Run reconciliation between paper trading and demo/exchange states.
    在紙上交易和演示/交易所狀態之間執行對賬。

    Args:
        paper_state: Current paper trading portfolio state
        demo_state: Demo/exchange state (defaults to paper_state if None)

    Returns:
        Reconciliation report dict:
        {
            "ok": bool,
            "result": "MATCH" | "MINOR_DISCREPANCY" | "MAJOR_DISCREPANCY" | "FATAL",
            "is_consistent": bool,
            "severity": "INFO" | "CRITICAL" | "FATAL",
            "discrepancies": [list of mismatches],
            "reason": str (if error)
        }

    Auto-Escalation Triggers:
        - severity="CRITICAL" → escalate RiskGovernor to DEFENSIVE
        - severity="FATAL" → freeze all authorizations, escalate to MANUAL_REVIEW
    """
```

**Usage Example:**

```python
# In paper_trading_engine.stop_session()
paper_state = self.paper_store.snapshot()
report = hub.reconcile(paper_state)

if report.get("severity") == "FATAL":
    logger.critical(f"Fatal reconciliation mismatch: {report}")
    # System is now frozen; requires operator intervention
else:
    logger.info(f"Reconciliation: {report['result']}")
```

---

#### get_status() — Status Query

```python
def get_status(self) -> GovernanceStatus:
    """
    Get combined governance status for API/GUI.
    獲取聯合治理狀態供 API/GUI 使用。

    Returns:
        GovernanceStatus object with all SM states, risk level, leases, etc.
    """
```

**GovernanceStatus Structure:**

```python
@dataclass
class GovernanceStatus:
    timestamp_ms: int
    enabled: bool
    mode: str  # "NORMAL", "RESTRICTED", "FROZEN", "MANUAL_REVIEW"

    # Authorization state
    auth_state: str | None              # "ACTIVE", "RESTRICTED", "FROZEN", "NONE"
    auth_expires_at_ms: int | None
    auth_scope: dict[str, Any]          # {"TRADE_ENTRY": true, ...}
    auth_pending_approval: bool

    # Risk governor state
    risk_level: int | None              # 0-5
    risk_level_name: str | None         # "NORMAL", "CAUTIOUS", ...
    risk_escalation_reason: str | None

    # Lease state
    active_leases_count: int
    total_leases_tracked: int

    # Reconciliation state
    last_reconciliation_ms: int | None
    last_reconciliation_result: str | None
    is_consistent: bool | None

    # Audit
    incident_count: int
    callback_errors: int
```

---

### 3.2 REST API Endpoints

All governance endpoints are mounted under `/api/v1/governance/` with FastAPI `APIRouter`.

#### GET /status — Combined Governance Dashboard

```
GET /api/v1/governance/status

Response (200 OK):
{
    "ok": true,
    "message": "governance_status",
    "data": {
        "timestamp_ms": 1711832400000,
        "enabled": true,
        "mode": "NORMAL",
        "authorization": {
            "state": "ACTIVE",
            "expires_at_ms": 1711836000000,
            "scope": {"TRADE_ENTRY": true, "TRADE_EXIT": true},
            "pending_approval": false
        },
        "risk": {
            "level": 1,
            "level_name": "CAUTIOUS",
            "escalation_reason": null
        },
        "leases": {
            "active_count": 2,
            "total_tracked": 15
        },
        "reconciliation": {
            "last_check_ms": 1711832300000,
            "last_result": "MATCH",
            "is_consistent": true
        },
        "incidents": 0,
        "callback_errors": 0
    }
}

Response (503 Service Unavailable):
{
    "ok": false,
    "detail": "Governance hub not available"
}
```

---

#### GET /auth/status — Authorization Details

```
GET /api/v1/governance/auth/status

Response (200 OK):
{
    "ok": true,
    "message": "authorization_status",
    "data": {
        "state": "ACTIVE",
        "expires_at_ms": 1711836000000,
        "scope": {
            "TRADE_ENTRY": true,
            "TRADE_EXIT": true,
            "RISK_OVERRIDE": false
        },
        "pending_approval": false,
        "is_effective": true
    }
}

Response (403 Forbidden):
{
    "ok": false,
    "message": "Governance hub disabled",
    "code": "governance_disabled"
}
```

---

#### POST /auth/approve — Operator Approval

```
POST /api/v1/governance/auth/approve
Content-Type: application/json

Request:
{
    "approval_note": "Approved for Q2 trading campaign"
}

Response (200 OK):
{
    "ok": true,
    "message": "authorization_approved",
    "data": {
        "status": "approval_recorded",
        "note": "Approved for Q2 trading campaign",
        "next_state": "ACTIVE"
    }
}

Response (401 Unauthorized):
{
    "ok": false,
    "detail": "Authentication required"
}

Response (403 Forbidden):
{
    "ok": false,
    "detail": "Operator role required"  ← SECURITY: Non-operators rejected
}

Response (404 Not Found):
{
    "ok": false,
    "code": "no_pending_approval",
    "message": "No pending authorization approval"
}
```

**Authorization Verification:**
- Endpoint checks `actor.operator_role == "Operator"` or `actor.is_operator == True`
- Non-operators receive 403 Forbidden with logged warning
- Approval note sanitized (HTML-escaped, max 500 chars) before logging

---

#### GET /risk/level — Risk Governor Status

```
GET /api/v1/governance/risk/level

Response (200 OK):
{
    "ok": true,
    "message": "risk_level_status",
    "data": {
        "level": 2,
        "level_name": "REDUCED",
        "escalation_reason": "Drawdown exceeded 5%",
        "mode": "RESTRICTED"
    }
}

Risk Levels:
  0 = NORMAL            (green, no action)
  1 = CAUTIOUS          (yellow, monitoring)
  2 = REDUCED           (orange, position size reduced 50%)
  3 = DEFENSIVE         (red, new positions blocked)
  4 = CIRCUIT_BREAKER   (dark red, all auth frozen)
  5 = MANUAL_REVIEW     (purple, operator intervention required)
```

---

#### POST /risk/override — Operator De-Escalation

```
POST /api/v1/governance/risk/override
Content-Type: application/json

Request:
{
    "target_level": "NORMAL",
    "reason": "False alarm in correlation detection; market condition assessed as normal."
}

Response (200 OK):
{
    "ok": true,
    "message": "risk_override_applied",
    "data": {
        "status": "override_applied",
        "current_level": 2,
        "target_level": 0,
        "reason": "False alarm in correlation detection..."
    }
}

Response (403 Forbidden):
{
    "ok": false,
    "code": "escalation_not_allowed",
    "message": "Cannot escalate via override; only de-escalation allowed"
}

Response (401/403):
{
    "ok": false,
    "detail": "Operator role required"  ← SECURITY: Non-operators rejected
}
```

**Constraints:**
- Only **de-escalation** allowed (moving towards NORMAL)
- Cannot escalate via this endpoint (use automatic triggers only)
- Operator must provide reason (sanitized, max 500 chars)
- Action logged with operator name and timestamp

---

#### POST /reconcile — Manual Reconciliation

```
POST /api/v1/governance/reconcile
Content-Type: application/json

Request:
{
    "paper_state": {
        "positions": {"BTCUSD": {"size": 1.0, "entry_price": 50000}},
        "cash": 95000.0,
        "last_update_ms": 1711832400000
    },
    "demo_state": {
        "positions": {...},
        "cash": 95000.0,
        "last_update_ms": 1711832400000
    },
    "reason": "manual_end_of_day_check"
}

Response (200 OK):
{
    "ok": true,
    "message": "reconciliation_complete",
    "data": {
        "result": "MATCH",
        "is_consistent": true,
        "severity": "INFO",
        "discrepancies": [],
        "timestamp_ms": 1711832400000
    }
}

Response (200 OK — Major Mismatch):
{
    "ok": true,
    "message": "reconciliation_complete",
    "data": {
        "result": "MAJOR_DISCREPANCY",
        "is_consistent": false,
        "severity": "CRITICAL",
        "discrepancies": [
            {
                "field": "positions.ETHUSD.size",
                "paper_value": 5.0,
                "demo_value": 4.8,
                "delta": -0.2
            }
        ],
        "timestamp_ms": 1711832400000
    }
}
```

**Auto-Actions on Severity:**
- `severity="CRITICAL"` → Risk escalated to DEFENSIVE
- `severity="FATAL"` → Risk escalated to MANUAL_REVIEW, all authorizations frozen

---

#### GET /leases — Active Leases

```
GET /api/v1/governance/leases

Response (200 OK):
{
    "ok": true,
    "message": "leases_list",
    "data": {
        "active_count": 2,
        "total_tracked": 23,
        "leases": [
            {
                "lease_id": "lease_001",
                "intent_id": "order_xyz",
                "scope": "TRADE_ENTRY",
                "state": "ACTIVE",
                "created_at_ms": 1711832350000,
                "expires_at_ms": 1711832380000
            },
            ...
        ]
    }
}
```

---

## 4. Cross-SM Wiring Rules / 跨狀態機聯動規則

The GovernanceHub implements **automatic cascading** between state machines via callbacks.

| Trigger Event | Source SM | Target SM | Action | Condition |
|---|---|---|---|---|
| Risk Level Change | RiskGovernor | AuthSM | `restrict()` | new_level ≥ 2 (REDUCED) |
| Risk Level Change | RiskGovernor | AuthSM | `freeze()` | new_level ≥ 4 (CIRCUIT_BREAKER) |
| Risk Level Change | RiskGovernor | LeaseSM | `revoke_all_active()` | new_level ≥ 3 (DEFENSIVE) |
| Auth → FROZEN | AuthSM | LeaseSM | `revoke_all_active()` | Immediate |
| Recon MAJOR | Recon | RiskGovernor | `escalate(DEFENSIVE)` | Immediate |
| Recon FATAL | Recon | AuthSM | `freeze()` | Immediate |
| Recon FATAL | Recon | RiskGovernor | `escalate(MANUAL_REVIEW)` | Immediate |
| Lease EXPIRED (bulk) | LeaseSM | AuditLog | `log_bulk_expiry()` | Background cleanup |

**Example Cascade Flow:**

```
User's position hits 10% drawdown
    ↓
RiskGovernor evaluates → escalates to REDUCED (level 2)
    ↓
_on_risk_escalation(1, 2) triggered
    ↓
AuthSM.restrict() called → all ACTIVE auths moved to RESTRICTED
    ↓
is_authorized() returns True, but acquire_lease() returns None for new intents
    ↓
User can view/manage existing positions, cannot open new ones
```

---

## 5. Configuration / 配置

### Environment Variables

All configuration via environment variables (12-factor app):

```bash
# Enable/disable entire governance system (default: true)
export OPENCLAW_GOVERNANCE_ENABLED=true

# Audit directory for persistence
export OPENCLAW_GOVERNANCE_AUDIT_DIR=/var/log/openclaw_audit

# Risk evaluation mode (not yet implemented; reserved)
export OPENCLAW_RISK_EVALUATION_MODE=online

# Cache TTL for authorization checks (milliseconds)
export OPENCLAW_GOVERNANCE_CACHE_TTL_MS=100
```

### Initialization in main.py / paper_trading_routes.py

```python
# In paper_trading_routes.py
from pathlib import Path
from program_code.exchange_connectors.bybit_connector.control_api_v1.app.governance_hub import GovernanceHub

# Initialize GOV_HUB singleton
audit_dir = os.environ.get(
    "OPENCLAW_GOVERNANCE_AUDIT_DIR",
    str(Path(__file__).parent / ".." / "audit_logs")
)
GOV_HUB = GovernanceHub(
    audit_dir=audit_dir,
    enabled=os.environ.get("OPENCLAW_GOVERNANCE_ENABLED", "true").lower() == "true"
)

# Pass to trading engine
ENGINE = PaperTradingEngine(
    PAPER_STORE,
    risk_manager=RISK_MANAGER,
    governance_hub=GOV_HUB  ← Phase 3 addition
)

# In main.py
from .governance_routes import governance_router
app.include_router(governance_router)  ← Phase 3 addition
```

### Audit File Format

Audit logs written to `{OPENCLAW_GOVERNANCE_AUDIT_DIR}/{sm_name}_audit.jsonl`:

```json
{"timestamp_ms": 1711832400000, "sm_name": "authorization", "event": "state_transition", "from": "NONE", "to": "PENDING_APPROVAL"}
{"timestamp_ms": 1711832410000, "sm_name": "authorization", "event": "approved_by", "authorization_id": "auth_123", "actor": "operator_alice"}
{"timestamp_ms": 1711832420000, "sm_name": "risk_governor", "event": "escalated", "from_level": 1, "to_level": 2, "reason": "drawdown_5pct"}
```

**File Permissions:**
- Set to `0o600` (owner read-write only) after each write
- Audit files are sensitive; contain decision history and risk events
- No world-readable; requires admin access to `/var/log/openclaw_audit`

---

## 6. Safety Invariants / 安全不變量

### Fail-Closed Principle

All authorization checks default to **deny** if governance is unavailable:

```python
# In is_authorized()
if not self._enabled or self._mode == GovernanceMode.FROZEN:
    return False  # Fail-closed: deny on uncertainty

# In acquire_lease()
if not self._enabled or not self._initialized or not self.is_authorized():
    return None  # Fail-closed: deny on uncertainty
```

**Why:** A trading system without governance is safer than one with broken governance that doesn't enforce checks.

### Conservative Direction Auto-Triggers

Risk escalations and reconciliation mismatches **automatically restrict/freeze** without operator approval:

- Risk ≥ REDUCED → auto-restrict auth (orange mode)
- Risk ≥ CIRCUIT_BREAKER → auto-freeze auth (red mode)
- Recon FATAL → auto-freeze auth (emergency stop)

This is **opposite** of expansion, which requires explicit approval.

### Expansion Requires Approval

Only **operator intervention** can:
- Approve new authorizations
- De-escalate risk (return to NORMAL)
- Resume trading after freeze

This asymmetry ensures conservative defaults.

### Lock Contention Mitigation

To prevent lock bottlenecks on hot paths:

1. **Authorization cache (100ms TTL)** — `is_authorized()` skips lock if result cached
2. **Lazy initialization** — SMs initialized on first access, not app startup
3. **Lock boundaries** — Callbacks minimize lock duration:
   - Collect state under lock
   - Execute actions outside lock
   - Re-acquire lock only for final updates

### Exception Safety

All callback chains wrapped in try-except:

```python
def _on_risk_escalation(self, old_level, new_level):
    try:
        # ... callback work ...
    except Exception as e:
        with self._lock:
            self._callback_errors += 1  # Track errors
        logger.debug(f"Callback error: {e}")
        # Continue; don't crash on callback failure
```

Error tracking enables operators to diagnose cascade failures via `GET /status` → `callback_errors` field.

### Audit Persistence

All state transitions logged to JSONL audit files:

- Each SM has its own `{sm_name}_audit.jsonl`
- Events include timestamp, actor (if operator), reason
- Immutable append-only log (file permissions `0o600`)
- Enables forensic investigation of governance decisions

---

## 7. Integration Points / 集成點

### 7.1 paper_trading_routes.py — Initialization

**What was added:**

```python
# 1. Initialize GovernanceHub
from program_code.exchange_connectors.bybit_connector.control_api_v1.app.governance_hub import GovernanceHub

audit_dir = os.environ.get(
    "OPENCLAW_GOVERNANCE_AUDIT_DIR",
    str(Path(__file__).parent / ".." / "audit_logs")
)
GOV_HUB = GovernanceHub(audit_dir=audit_dir, enabled=True)

# 2. Pass to ENGINE constructor
ENGINE = PaperTradingEngine(
    PAPER_STORE,
    risk_manager=RISK_MANAGER,
    governance_hub=GOV_HUB  ← New parameter
)

# 3. Check authorization before session start
@router.post("/sessions")
def create_session(...):
    if not GOV_HUB.is_authorized():
        raise HTTPException(status_code=403, detail="Trading authorization denied")
    # ... create session ...
```

**Why:** Central point for hub initialization ensures singleton pattern. Passed to ENGINE enables governance checks on every order.

---

### 7.2 paper_trading_engine.py — Order Submission

**What was added:**

```python
class PaperTradingEngine:
    def __init__(self, store, risk_manager, governance_hub=None):
        self._governance_hub = governance_hub

    def submit_order(self, order: Order) -> OrderResult:
        # 1. H0 gate: check authorization
        if self._governance_hub and not self._governance_hub.is_authorized():
            return OrderResult(
                ok=False,
                reason="Authorization denied",
                governance_mode="FROZEN"
            )

        # 2. Acquire lease
        lease_id = None
        if self._governance_hub:
            lease_id = self._governance_hub.acquire_lease(
                intent_id=order.order_id,
                scope="TRADE_ENTRY" if order.side == "BUY" else "TRADE_EXIT",
                ttl_seconds=30.0
            )
            if lease_id is None:
                return OrderResult(
                    ok=False,
                    reason="Decision lease denied",
                    governance_reason="Lease unavailable"
                )

        # 3. Fill order
        try:
            result = self._fill_order(order)

            # 4. Feed risk metrics to governor
            if self._governance_hub and result.ok:
                metrics = {
                    'drawdown_pct': self._compute_drawdown(),
                    'daily_loss_pct': self._compute_daily_loss(),
                }
                self._governance_hub.check_risk_and_act(metrics)

            return result
        finally:
            # 5. Release lease
            if lease_id and self._governance_hub:
                self._governance_hub.release_lease(lease_id, consumed=True)
```

**Why:** Orders are the critical decision point. Governance checks before fill, risk feedback after fill, lease lifecycle ensures atomicity.

---

### 7.3 pipeline_bridge.py — Intent Submission

**What was added:**

```python
def process_pending_intents(engine, hub):
    """Process trade intents, checking governance at entry."""

    for intent in PENDING_INTENTS:
        # Before submitting intent to engine, check governance
        if hub:
            if not hub.is_authorized():
                logger.info(f"Intent {intent.intent_id} blocked: authorization denied")
                intent.mark_rejected("authorization_denied")
                continue

            # Acquire lease for this intent
            lease_id = hub.acquire_lease(
                intent_id=intent.intent_id,
                scope=intent.scope,  # e.g., "TRADE_ENTRY"
                ttl_seconds=intent.ttl_seconds
            )

            if lease_id is None:
                logger.info(f"Intent {intent.intent_id} blocked: lease denied")
                intent.mark_rejected("lease_unavailable")
                continue

        # Submit intent to engine
        result = engine.submit_order(intent.to_order())

        # Release lease
        if lease_id and hub:
            hub.release_lease(lease_id, consumed=result.ok)
```

**Why:** Pipeline entry point needs governance check to prevent downstream processing of denied intents.

---

### 7.4 risk_manager.py — Risk Metrics Feedback

**What was added:**

```python
class RiskManager:
    def __init__(self, max_position_pct=0.5, governance_hub=None):
        self._governance_hub = governance_hub

    def check_positions(self, portfolio) -> dict:
        """Check risk constraints; feed metrics to governor."""

        # Compute risk pressure
        risk_pressure = self._compute_risk_pressure(portfolio)

        # Feed to governance hub
        if self._governance_hub:
            metrics = {
                'drawdown_pct': risk_pressure['drawdown'],
                'daily_loss_pct': risk_pressure['daily_loss'],
                'volatility': risk_pressure['volatility'],
                'correlation_alert': risk_pressure['correlation'] > 0.8,
            }
            risk_level = self._governance_hub.check_risk_and_act(metrics)

            # Scale position limits based on risk governor level
            if risk_level is not None and risk_level >= 2:
                return {
                    'effective_max_position_pct': self._effective_max_position_pct(risk_level),
                    'risk_level': risk_level,
                    'reason': 'Risk escalation applied position limits'
                }

        return {'effective_max_position_pct': self._max_position_pct}
```

**Why:** Risk metrics are computed continuously; feeding them to governance enables automatic escalation without operator intervention.

---

## 8. Testing / 測試

### Test Coverage Summary

| Component | Test Count | Coverage |
|---|---|---|
| GovernanceHub core | 46 tests | Unit tests for each method |
| Authorization SM | 12 tests | State transitions, approval flow |
| Risk Governor SM | 8 tests | Risk escalation cascade |
| Decision Lease SM | 10 tests | Lease lifecycle (draft, activate, consume, revoke) |
| Reconciliation Engine | 8 tests | Match, minor, major, fatal mismatches |
| Cross-SM integration | 8 tests | Risk→Auth, Recon→Risk, Auth→Lease cascades |
| **Total** | **92 tests** | **Comprehensive** |

### Test Files

**Location:** `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/`

1. **test_governance_hub.py** — 46 tests
   - `test_is_authorized_*` (8 tests) — Cache behavior, fast path
   - `test_acquire_release_lease_*` (10 tests) — Lease lifecycle
   - `test_check_risk_and_act_*` (8 tests) — Risk escalation
   - `test_reconcile_*` (12 tests) — Reconciliation matching
   - `test_cross_sm_cascade_*` (8 tests) — Callback chains

2. **test_integration_governance.py** — 8 tests
   - `test_risk_escalation_restricts_auth` — Risk ≥ REDUCED
   - `test_circuit_breaker_freezes_auth` — Risk ≥ CIRCUIT_BREAKER
   - `test_recon_mismatch_escalates_risk` — Recon MAJOR
   - `test_auth_frozen_revokes_leases` — Auth FROZEN
   - `test_hot_path_cache_performance` — 100ms cache effectiveness
   - `test_concurrent_operations` — Thread safety
   - `test_exception_in_callback_doesnt_crash` — Error resilience
   - `test_audit_persistence` — JSONL file writing

### Running Tests

```bash
# Run all governance tests
pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_governance_hub.py -v

# Run integration tests only
pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_integration_governance.py -v

# Run with coverage
pytest --cov=program_code.exchange_connectors.bybit_connector.control_api_v1.app.governance_hub \
       program_code/exchange_connectors/bybit_connector/control_api_v1/tests/

# Run hot-path performance test
pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_integration_governance.py::test_hot_path_cache_performance -v -s
```

---

## 9. Deployment / 部署

### Pre-Deployment Checklist

- [ ] Environment variables set (see Section 5)
- [ ] Audit directory exists and writable by app process
- [ ] Database migrations applied (if any)
- [ ] TLS/HTTPS enabled for `/api/v1/governance/` endpoints
- [ ] Operator authentication configured (depends on your auth system)
- [ ] Rate limiting configured (recommended: 10 req/sec per IP for approval endpoints)
- [ ] Monitoring/alerting configured for `governance_hub` logs

### Deployment Steps

#### 1. Build and Test

```bash
cd /sessions/eloquent-wonderful-feynman/BybitOpenClaw

# Install dependencies
pip install -r requirements.txt

# Run full test suite
pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/ -v

# Type check
mypy program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub.py
```

#### 2. Configure Environment

```bash
# On trade-core Ubuntu server
export OPENCLAW_GOVERNANCE_ENABLED=true
export OPENCLAW_GOVERNANCE_AUDIT_DIR=/var/log/openclaw_audit
export OPENCLAW_RISK_EVALUATION_MODE=online

# Create audit directory with restrictive permissions
mkdir -p /var/log/openclaw_audit
chmod 700 /var/log/openclaw_audit
chown openclaw:openclaw /var/log/openclaw_audit
```

#### 3. Start Service

```bash
# Via systemd (recommended)
systemctl start openclaw-trading-api

# Or via Docker
docker run -e OPENCLAW_GOVERNANCE_ENABLED=true \
           -e OPENCLAW_GOVERNANCE_AUDIT_DIR=/var/log/audit \
           -v /var/log/openclaw_audit:/var/log/audit \
           bybit-openclaw:phase3
```

#### 4. Verify Governance is Active

```bash
# Check governance status
curl -H "Authorization: Bearer $(cat /var/openclaw/operator_token)" \
     http://localhost:8000/api/v1/governance/status

# Expected response:
{
  "ok": true,
  "data": {
    "enabled": true,
    "mode": "NORMAL",
    "authorization": { "state": "NONE", ... },
    ...
  }
}
```

#### 5. Initialize Authorization

Before trading begins, an operator must approve authorization:

```bash
# Step 1: Create authorization request (in-app)
# ...creates auth in PENDING_APPROVAL state

# Step 2: Operator approves
curl -X POST \
     -H "Authorization: Bearer $(cat /var/openclaw/operator_token)" \
     -H "Content-Type: application/json" \
     -d '{"approval_note": "Approved for Phase 3 deployment"}' \
     http://localhost:8000/api/v1/governance/auth/approve

# Expected response:
{
  "ok": true,
  "message": "authorization_approved",
  "data": { "status": "approval_recorded", "next_state": "ACTIVE" }
}

# Step 3: Verify authorization is ACTIVE
curl -H "Authorization: Bearer $(cat /var/openclaw/operator_token)" \
     http://localhost:8000/api/v1/governance/auth/status
```

#### 6. Enable/Disable Governance (Emergency)

```bash
# Disable governance (fail-closed: operations are denied)
export OPENCLAW_GOVERNANCE_ENABLED=false
systemctl restart openclaw-trading-api

# Re-enable
export OPENCLAW_GOVERNANCE_ENABLED=true
systemctl restart openclaw-trading-api
```

**Note:** Disabling governance means `is_authorized()` returns `False` for all checks, preventing all trading. This is the **fail-safe** mode.

---

## 10. Troubleshooting / 故障排除

### Issue: "Governance hub not available"

**Symptoms:** API returns `503 Service Unavailable`

**Causes:**
- GovernanceHub initialization failed
- State machine import error
- Audit directory not writable

**Solution:**

```bash
# Check logs
tail -f /var/log/openclaw/app.log | grep -i governance

# Verify audit directory
ls -la /var/log/openclaw_audit/
ls -la /var/log/openclaw_audit/*_audit.jsonl

# Check file permissions
stat /var/log/openclaw_audit/authorization_audit.jsonl
# Should show: Access: (0600/-rw-------)

# Restart service with debug logging
export OPENCLAW_LOG_LEVEL=DEBUG
systemctl restart openclaw-trading-api
```

---

### Issue: "Authorization denied" on every order

**Symptoms:** All orders rejected with `authorization_denied`

**Possible Causes:**
1. Authorization state is FROZEN (risk escalation triggered)
2. Authorization expired
3. Authorization never approved
4. Cache corruption

**Solution:**

```bash
# Step 1: Check authorization status
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/governance/auth/status

# If state="NONE", create and approve authorization (see Deployment Step 5)
# If state="FROZEN", check risk level

# Step 2: Check risk level
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/governance/risk/level

# If level >= 4 (CIRCUIT_BREAKER), operator must de-escalate:
curl -X POST \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"target_level":"NORMAL","reason":"Risk assessment complete; safe to resume."}' \
     http://localhost:8000/api/v1/governance/risk/override

# Step 3: Verify authorization cache is fresh
# Cache has 100ms TTL; wait 200ms and retry
sleep 0.2
# Retry order submission
```

---

### Issue: Lease acquisition failing (returns None)

**Symptoms:** Orders fail with "Decision lease denied"

**Possible Causes:**
1. Authorization not in ACTIVE/RESTRICTED state
2. Authorization scope doesn't include TRADE_ENTRY/TRADE_EXIT
3. Too many active leases (resource exhaustion)

**Solution:**

```bash
# Check authorization scope
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/governance/auth/status

# Expected scope:
# { "TRADE_ENTRY": true, "TRADE_EXIT": true, ... }

# If scope is empty, operator must grant scope (in-app authorization update)

# Check active leases
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/governance/leases

# If active_count is high (>100), check for lease expiry issues:
tail -f /var/log/openclaw_audit/decision_lease_audit.jsonl | grep -i "expired\|revoked"

# Clean up expired leases (should happen automatically, but can be forced):
# [Requires new endpoint; consider adding in Phase 4]
```

---

### Issue: Reconciliation keeps finding "MAJOR_DISCREPANCY"

**Symptoms:** Manual reconciliation reports major mismatches repeatedly

**Possible Causes:**
1. Paper trading engine and exchange state out of sync
2. Demo state snapshot stale
3. Position size rounding errors

**Solution:**

```bash
# Step 1: Get latest states
PAPER_STATE=$(curl -s -H "Authorization: Bearer $TOKEN" \
                   http://localhost:8000/api/v1/paper-trading/snapshot | jq .data)

DEMO_STATE=$(curl -s -H "Authorization: Bearer $TOKEN" \
                  http://localhost:8000/api/v1/demo/snapshot | jq .data)

# Step 2: Manual reconciliation
curl -X POST \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d "{\"paper_state\": $PAPER_STATE, \"demo_state\": $DEMO_STATE, \"reason\": \"manual_diagnosis\"}" \
     http://localhost:8000/api/v1/governance/reconcile | jq .

# Step 3: Analyze discrepancies
# If minor (< 0.5% position delta), safe to ignore
# If major (> 5% position delta):
#   - Check recent order fills
#   - Verify slippage models
#   - Check for partial fills

# Step 4: If issue persists, operator may de-escalate risk
# (After investigating root cause in paper_trading_engine logs)
```

---

### Issue: Callback errors in governance status

**Symptoms:** `GET /status` returns `callback_errors > 0`

**Cause:** An exception occurred in a cross-SM callback (e.g., during risk escalation)

**Solution:**

```bash
# Check detailed logs
tail -f /var/log/openclaw/app.log | grep -i "callback_error\|_on_risk_escalation\|_on_reconciliation"

# Common sources:
# 1. State machine method not found (version mismatch)
# 2. Database connection lost during callback
# 3. Lock contention timeout

# To clear error counter (requires code change; not exposed via API):
# 1. Restart app service
#    systemctl restart openclaw-trading-api
#
# 2. Or implement /admin/governance/reset-error-counter endpoint (Phase 4)
```

---

### Issue: High latency on is_authorized() checks

**Symptoms:** Order submission slow even without lease/reconciliation

**Cause:** Cache miss or lock contention

**Solution:**

```bash
# Verify cache is working (100ms TTL):
# 1. Instrument is_authorized() with timing logs
# 2. Expected hot-path latency: <1ms (cached), ~5ms (lock acquire + SM query)

# If seeing >50ms consistently:
#   - Check CPU usage: if high, context switch issue
#   - Check lock contention: review governance status for incident_count
#   - Consider increasing cache TTL (tunable via env var in Phase 4)

# Profile with cProfile:
python -m cProfile -s cumtime -m pytest test_governance_hub.py::test_hot_path_cache_performance

# Expected output: is_authorized() < 0.1ms per call (hot path)
```

---

## Glossary / 術語表

| Term | English | 中文 | Definition |
|---|---|---|---|
| H0 Gate | Authorization Check | 授權門檢 | First-line authorization check before any operation |
| Fail-Closed | Default Deny | 預設拒絕 | System denies operations when governance unavailable |
| SM | State Machine | 狀態機 | Governance component managing state transitions |
| Lease | Decision Lease | 決策租約 | Time-limited permission to execute a trade decision |
| Reconciliation | State Sync | 狀態同步 | Comparison of paper trading vs. demo/exchange state |
| Escalation | Risk Increase | 風險升級 | Automatic restriction on operations due to risk |
| De-Escalation | Risk Decrease | 風險降級 | Operator intervention to return to normal |
| Cascade | Cross-SM Flow | 跨機聯動 | Automatic triggering of actions in other SMs |
| Audit Trail | Event Log | 審計軌跡 | Immutable record of all governance decisions |
| TTL | Time-To-Live | 有效期 | Duration for which cached data remains valid |

---

## References

- **FA Design:** `T3.01_FA_INTEGRATION_DESIGN.md`
- **Authorization SM Spec:** (linked in governance_dev/)
- **Risk Governor SM Spec:** (linked in governance_dev/)
- **Decision Lease SM Spec:** (linked in governance_dev/)
- **Reconciliation Engine Spec:** (linked in governance_dev/)

---

**Document signed off by TW (Technical Writer)**
Date: 2026-03-30
Status: Ready for Developer Handoff (E1a Implementation)

---

*For questions or clarifications, contact FA (Framework Architect) or refer to the Phase 3 governance team Slack channel.*
