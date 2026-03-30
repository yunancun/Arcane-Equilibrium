# PHASE 3 GAP AUDIT REPORT — OpenClaw Project
## First Analyst (FA) Audit Results
**Date:** 2026-03-30
**Audit Scope:** Post-Phase 2 governance module integration gaps
**Repo:** `/sessions/fervent-serene-einstein/BybitOpenClaw`
**App Path:** `program_code/exchange_connectors/bybit_connector/control_api_v1/app/`

---

## EXECUTIVE SUMMARY

Seven governance gaps identified across code implementation, injection wiring, and test coverage. Gaps range from P0 (circuit breaker not functioning) to P2 (monitoring gaps). Two pre-existing test failures confirmed as LEGITIMATE BUGS requiring fixes in core risk control logic.

**Baseline:** Phase 2 successfully hardened 8 modules via GovernanceHub injection. Phase 3 audit reveals 7 new gaps that prevent full governance activation.

---

## DETAILED FINDINGS

### GAP-P3-001: Session Drawdown Halt Not Triggering (CRITICAL)

**Severity:** P0
**Status:** CONFIRMED FAILURE
**File(s) Affected:**
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_engine.py` (lines 1352-1361)
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/risk_manager.py` (lines 946-953)

**Description:**
Session drawdown halt logic implemented in paper_trading_engine.py but **not being triggered** during tick processing. Test `test_session_drawdown_halts` fails because:
1. RiskManager.check_positions_on_tick() called correctly (line 1317)
2. Engine checks peak vs current balance (lines 1353-1357)
3. BUT: drawdown check occurs AFTER position closes and PnL recomputation (line 1311)
4. Problem: **peak_balance not updated before drawdown check** — peak remains at initial 10000 while current is 10000 (fees/slippage haven't reduced balance yet at fill time)
5. Drawdown calculation: `(peak - current) / peak * 100` = `(10000 - 10000) / 10000 * 100` = 0%
6. Result: halt condition never triggered even when balance drops below threshold

**Root Cause:**
Peak balance tracking happens AFTER drawdown check (line 1424-1426), creating a race condition. Realized PnL updates balance progressively as fills execute, but peak_balance snapshot doesn't capture the high-water mark correctly when positions are closed within the same tick.

**Suggested Fix:**
1. Update peak_balance BEFORE risk manager tick checks (move lines 1424-1426 to line 1313)
2. OR: Recalculate peak from historical fills/positions at tick start
3. Ensure drawdown check uses consistent snapshot of peak-to-current delta

**Estimated Effort:** M

**Test Failure Output:**
```
AssertionError: assert False is True
where False = <session state>.get('session_halted')
expected session_halted=True but got False
```

---

### GAP-P3-002: Daily Loss Pre-Order Check Not Blocking (P0)

**Severity:** P0
**Status:** CONFIRMED FAILURE
**File(s) Affected:**
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/risk_manager.py` (lines 642-645)

**Description:**
Test `test_daily_loss_blocks_and_closes` fails because daily loss pre-order check is not blocking new orders after daily limit exceeded. Expected behavior:
1. Daily loss 5% (exceeds 1% limit)
2. New order submitted for 0.001 BTC
3. RiskManager.check_order_allowed() should return (False, "daily_loss_...")

**Actual Behavior:**
check_order_allowed() returns (True, "ok") even though daily loss check exists at lines 642-645.

**Root Cause:**
The daily loss calculation in check_order_allowed() requires accurate session state with `daily_start_balance_usdt`. Test mutates state AFTER opening position but before loss closure. Possible issues:
1. daily_start_balance not properly set when session starts
2. daily_start_date not being tracked (reset each UTC day)
3. current_paper_balance not reflecting losses after fills execute

**Code Analysis (lines 640-645):**
```python
daily_loss_pct = ((daily_start - balance_now) / daily_start) * 100
if daily_loss_pct >= self._config.max_daily_loss_pct:
    return False, f"daily_loss_{daily_loss_pct:.1f}pct_exceeds_max_{self._config.max_daily_loss_pct:.1f}pct"
```

The logic is correct, but session state tracking for daily loss boundaries needs verification.

**Suggested Fix:**
1. Verify daily_start_balance is initialized on session start (not just on daily boundary)
2. Ensure daily_start_date resets each calendar day (UTC)
3. Confirm current_paper_balance is updated after fills execute (before pre-order checks)
4. Add logging to trace daily_start vs current balance in tests

**Estimated Effort:** M

**Test Failure Output:**
```
assert result["rejected_reason"] is not None
AssertionError: assert None is not None
Expected: rejected_reason containing "daily_loss"
Got: rejected_reason = None (order accepted)
```

---

### GAP-P3-003: ProtectiveOrderManager.check_triggers() Never Called (P1)

**Severity:** P1
**Status:** UNIMPLEMENTED INVOCATION
**File(s) Affected:**
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/protective_order_manager.py` (line 376)
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_engine.py` (tick mutator)

**Description:**
ProtectiveOrderManager is initialized and wired to PaperTradingEngine (paper_trading_routes.py line 71), but its trigger-checking method is **never invoked** during tick processing.

Design intended:
- check_triggers() should run on every market tick
- Protective orders (HARD_STOP_LOSS, SOFT_STOP_LOSS, etc.) should be evaluated
- Triggered orders execute via callback to execute_protective_action()

**Actual Implementation:**
- No call to `self._protective_order_manager.check_triggers()` anywhere in paper_trading_engine.py tick mutator
- Protective orders sit idle; circuit breaker (EMERGENCY_CLOSE_ALL) never executes
- Last line of defense against system-wide account destruction not operational

**Impact:**
DOC-01 §5.9 compliance gap: "Exchange-side must always maintain disaster protection baseline. When local system fails completely, pre-staged conditional orders on exchange are the account's last survival line."

**Code Inspection:**
- ProtectiveOrderManager is set on ENGINE (line 71 of paper_trading_routes.py)
- `self._protective_order_manager` reference exists in PaperTradingEngine (line 683)
- BUT: tick() mutator never calls check_triggers()

**Suggested Fix:**
Add tick invocation in paper_trading_engine.py tick() mutator after risk checks (around line 1350):
```python
# Check protective orders on tick (last line of defense)
if self._protective_order_manager:
    self._protective_order_manager.check_triggers(state, market_prices)
```

**Estimated Effort:** S

---

### GAP-P3-004: ScannerRateLimiter Never Injected into PipelineBridge (P2)

**Severity:** P2
**Status:** CREATED BUT UNINJECTED
**File(s) Affected:**
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_routes.py` (line 159)
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/phase2_strategy_routes.py` (initialization section)
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/pipeline_bridge.py` (lines 80, 135, 243-247)

**Description:**
ScannerRateLimiter module (T2.07) is:
1. ✓ Created as SCANNER_RATE_LIMITER in paper_trading_routes.py (line 159)
2. ✓ Has set_scanner_rate_limiter() method in PipelineBridge (line 135)
3. ✓ Is called in scan path (pipeline_bridge.py lines 243-247)
4. ✗ **NEVER INJECTED** into PIPELINE_BRIDGE

Result: Rate limiter always evaluates as None; fallback allows all scans (line 250-252).

**Code Flow:**
```python
# paper_trading_routes.py line 159
SCANNER_RATE_LIMITER = ScannerRateLimiter()

# phase2_strategy_routes.py — NO injection call:
# Missing: PIPELINE_BRIDGE.set_scanner_rate_limiter(SCANNER_RATE_LIMITER)

# pipeline_bridge.py line 243-247 (on_tick)
if self._scanner_rate_limiter:
    can_scan, reason = self._scanner_rate_limiter.can_scan()
    # ... always None, fallback to allow scan
else:  # <-- always executes
    self._refresh_kline_volume()  # <-- scans every 60s without limit
```

**Impact:**
Market scanner executes unthrottled; potential API rate limit violations when scanning 10+ symbols simultaneously.

**Suggested Fix:**
Add injection in phase2_strategy_routes.py (after PIPELINE_BRIDGE creation, around line 220):
```python
# T2.07: Inject ScannerRateLimiter
from .paper_trading_routes import SCANNER_RATE_LIMITER as _SCANNER_RATE_LIMITER_REF
if PIPELINE_BRIDGE is not None and _SCANNER_RATE_LIMITER_REF is not None:
    PIPELINE_BRIDGE.set_scanner_rate_limiter(_SCANNER_RATE_LIMITER_REF)
    logger.info("ScannerRateLimiter injected into PipelineBridge")
```

**Estimated Effort:** S

---

### GAP-P3-005: Daily Loss Auto-Close Not Halting Session (P1)

**Severity:** P1
**Status:** PARTIAL IMPLEMENTATION
**File(s) Affected:**
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/risk_manager.py` (lines 968-978)

**Description:**
Daily loss check in check_positions_on_tick() (lines 968-978) auto-closes positions but **does NOT halt the session**. Code explicitly says:
```python
# Don't halt session, but close all positions as protective measure
# 不熔断 session，但平掉所有仓位作为保护措施
for symbol, pos in list(positions.items()):
    close_orders.append({...})
```

Test expects new orders to be BLOCKED after daily loss limit, but:
1. Pre-order check (check_order_allowed) references daily loss (lines 642-645)
2. Tick-time auto-close (check_positions_on_tick) closes open positions but lets new orders through
3. Inconsistency: positions are force-closed but session continues accepting orders

**Design Question:**
Should daily loss limit:
- A) Just auto-close existing positions (current), OR
- B) Block new orders + auto-close (test expectation), OR
- C) Halt session entirely (stricter than B)?

Current code implements A, but test expects B. This is a **design clarity gap**, not a bug per se, but test is checking for documented behavior (from docstring).

**Suggested Fix:**
Either:
1. Update test to match implementation (A) — remove assertion for blocked orders
2. Update implementation to match test (B) — add session_halted flag or pre-order check enforcement
3. Document the intended behavior in module docstring

**Estimated Effort:** S (once design choice is confirmed)

---

### GAP-P3-006: ChangeAuditLog Recording Limited to GovernanceHub (P2)

**Severity:** P2
**Status:** LIMITED SCOPE
**File(s) Affected:**
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub.py` (lines 350, 721)
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/change_audit_log.py` (line 160)

**Description:**
ChangeAuditLog.record_change() is called from only 2 locations, both within GovernanceHub:
1. Line 350: On cross-SM cascade (lease revocation due to auth freeze)
2. Line 721: On risk escalation event

**Gap:**
Significant system changes NOT being logged to ChangeAuditLog:
- Order submissions (paper_trading_engine.py)
- Position closures (paper_trading_engine.py)
- Risk config updates (risk_manager.py)
- Session start/stop events
- Protective order creations (protective_order_manager.py)
- Reconciliation state changes (reconciliation_engine.py)

These are operational changes that should be part of governance audit trail per T2.04 (ChangeAuditLog design goal: "record all material governance-affecting changes").

**Example Gap:**
When RiskManager.check_positions_on_tick() force-closes a position due to daily loss, no ChangeAuditLog record is created. When paper_trading_engine auto-halts session due to drawdown, the halt event is only internal state (no governance audit trail).

**Suggested Fix:**
1. Expand ChangeAuditLog invocations to cover:
   - Risk config changes (agent_adjust, update_global_config)
   - Protective order state transitions
   - Session halt events
   - Reconciliation findings (if severity >= CRITICAL)
2. Add audit callback from PaperTradingEngine risk-triggered closures
3. Document expected audit events in module docstrings

**Estimated Effort:** M

---

### GAP-P3-007: ReconciliationEngine Public API Not Wired (P2)

**Severity:** P2
**Status:** CREATED BUT UNUSED
**File(s) Affected:**
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/reconciliation_engine.py` (line 243)
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub.py` (lines 564-610)

**Description:**
ReconciliationEngine.reconcile() public method exists but is **never called**. Design intent (per docstring):
- Reconcile local (Paper) vs external (Demo/Exchange) state
- Detect discrepancies in orders, positions, fills, balance
- Report findings with severity levels
- Trigger incidents (freeze, manual review, auto-correct)

**Current Status:**
- ReconciliationEngine is created (not in code shown, but mentioned in governance_hub docstring line 10)
- has reconcile() method (line 243)
- GovernanceHub has reconciliation integration (lines 564-610: reconcile() method exists)
- BUT: No periodic reconciliation trigger (e.g., on tick, on order, on timer)

**Code Inventory:**
- ReconciliationEngine instantiation: Not found in paper_trading_routes or phase2_strategy_routes
- Reconciliation injection: Not found in PipelineBridge or GovernanceHub setters
- Reconciliation trigger: No scheduler or event handler calling reconcile()

**Impact:**
T2.04 EX-04 reconciliation layer sits idle. If Paper engine and Demo connector drift, divergence goes undetected.

**Suggested Fix:**
1. Create ReconciliationEngine in paper_trading_routes.py
2. Inject into GovernanceHub via set_reconciliation_engine()
3. Add periodic tick-based or order-based reconciliation triggers
4. Wire reconciliation reports into incident handling

**Estimated Effort:** M

---

## TEST FAILURES ANALYSIS

### test_session_drawdown_halts (LEGITIMATE BUG)

**Test Location:**
`program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_risk_manager.py::TestTickChecks::test_session_drawdown_halts`

**Failure:**
```
AssertionError: assert False is True
where False = <session>.get('session_halted')
expected session_halted=True but got False
```

**Root Cause:** (See GAP-P3-001 above)
Peak balance tracking bug prevents drawdown detection.

**Fix Priority:** P0 BLOCKING

---

### test_daily_loss_blocks_and_closes (LEGITIMATE BUG)

**Test Location:**
`program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_risk_manager.py::TestDailyLoss::test_daily_loss_blocks_and_closes`

**Failure:**
```
assert result["rejected_reason"] is not None
AssertionError: assert None is not None
Expected: rejected_reason contains "daily_loss"
Got: rejected_reason = None (order accepted despite daily loss limit)
```

**Root Cause:** (See GAP-P3-002 above)
Daily loss state tracking or balance update issue.

**Fix Priority:** P0 BLOCKING

---

## SUMMARY TABLE

| GAP ID | Component | Issue | Severity | Effort | Status |
|--------|-----------|-------|----------|--------|--------|
| GAP-P3-001 | paper_trading_engine + risk_manager | Session drawdown halt never triggers | P0 | M | TEST FAIL |
| GAP-P3-002 | risk_manager | Daily loss pre-order check not blocking | P0 | M | TEST FAIL |
| GAP-P3-003 | protective_order_manager + paper_trading_engine | check_triggers() never called on tick | P1 | S | UNIMPLEMENTED |
| GAP-P3-004 | pipeline_bridge + paper_trading_routes | ScannerRateLimiter created but not injected | P2 | S | UNINJECTED |
| GAP-P3-005 | risk_manager | Daily loss auto-close vs order blocking inconsistency | P1 | S | DESIGN GAP |
| GAP-P3-006 | change_audit_log | Audit recording limited to GovernanceHub cascades | P2 | M | LIMITED SCOPE |
| GAP-P3-007 | reconciliation_engine + governance_hub | Reconciliation engine not wired for periodic triggers | P2 | M | UNUSED |

---

## PHASE 3 READINESS ASSESSMENT

**Current Status:** Phase 3 NOT READY FOR PRODUCTION

**Blockers (must fix before Phase 4):**
- GAP-P3-001: Session drawdown halt (P0 — circuit breaker non-functional)
- GAP-P3-002: Daily loss pre-order check (P0 — loss control not enforced)

**Major Issues (should fix in Phase 3):**
- GAP-P3-003: Protective orders (P1 — last line of defense not active)
- GAP-P3-005: Daily loss design clarification (P1 — behavioral gap)

**Minor Issues (Phase 3 polish):**
- GAP-P3-004: Scanner rate limiter injection (P2 — efficiency/rate limit risk)
- GAP-P3-006: Audit log scope expansion (P2 — observability gap)
- GAP-P3-007: Reconciliation wiring (P2 — drift detection gap)

---

## RECOMMENDATIONS

1. **Immediate (P0):** Fix peak_balance tracking and daily loss state management to unblock test suite
2. **Short-term (P1):** Activate protective order checks and clarify daily loss session halt policy
3. **Medium-term (P2):** Complete dependency injections and expand audit logging scope
4. **Documentation:** Add integration test for end-to-end governance activation (all 7 SMs active)

---

**Report Generated:** 2026-03-30
**Analyst:** FA (First Analyst, Claude)
**Next Review:** Post-fix verification (GAP-P3-001, GAP-P3-002)
