---
name: P0-6 RCA 完成 + 修復方案
description: P0-6 INTENT-WRITE-GAP-1 根因（FUP抑制+cost_gate死循環）及兩層修復方案（startup triage + natural bootstrap）
type: project
originSessionId: dad4b1fd-c98b-4910-a767-30e3c3772e43
---
## P0-6 Root Cause (2026-04-17 confirmed)

### Live_Demo blocker: cost_gate_live cold-start fail-closed
- `settings/edge_estimates.json` = `{}` (3 bytes, never written)
- `intent_processor/gates.rs:184-191` — cost_gate_live: no edge estimate → fail-closed
- 630k decision_features exist (passes all pre-cost-gate gates) but 0 get final approval
- Dead-loop: no fills → no edge data → cost gate stays closed → no fills

### Demo blocker: correlated exposure ~70% >= 65% limit
- `risk_checks.rs:98` — correlated_exposure_pct >= limits.correlated_exposure_max_pct
- 0 decision_features (blocked before evaluate_predictor_gate)
- Secondary: Guardian direction_conflict for 17.8k Rejected verdicts

### Root cause of stuck positions: FUP suppression deadlock
- `position_reconciler/mod.rs:602-620` — FUP suppression check
- `import_positions()` (paper_state.rs:373-404) syncs Bybit positions into paper_state + positions_mirror with owner_strategy="bybit_sync"
- Reconciler classifies Bybit positions as Orphan → FUP check finds them in mirror → **suppresses orphan verdict**
- Orphan handler's Stage C close logic NEVER triggers for bybit_sync positions
- Positions are neither managed nor closed → permanent exposure deadlock

### Design blind spot
- `ExchangeGateResult.rejected_reason` is computed by every gate but NEVER persisted to DB — dropped when `!gate.approved`
- P0-6 DIAG instrumentation added to `on_tick.rs` (rate-limited warn!) — remove after fix confirmed

## Fix Plan (two layers)

### Layer 1: Startup Position Triage (core fix)
After `import_positions()`, before tick loop:
1. Iterate all `owner_strategy == "bybit_sync"` positions
2. Check if symbol is in scanner active universe + any strategy covers it
3. **Claimed** → update owner_strategy to strategy name → managed normally
4. **Unclaimed** → remove from paper_state (keep off mirror) → reconciler sees as true orphan → handle_orphan → Stage C close

Files: paper_state.rs (new triage fn) + event_consumer/mod.rs (call triage) + tests

### Layer 2: Live_Demo natural bootstrap (no code change to cost_gate)
1. Demo unblocked → accumulates fills
2. james_stein_estimator runs periodically → edge_estimates.json populated
3. Live_Demo cost_gate_live reads edge data → naturally unblocks
4. cost_gate_live fail-closed design fully preserved

### Additional improvements
- `adopt_orphan()` accept owner_strategy param (not hardcoded "orphan_adopted")
- Persist rejected_reason to DB (eliminate diagnostic blind spot)

**Why:** These fixes are live-ready — same logic handles manual/API residual positions on real live.
**How to apply:** When implementing P0-6 fix, follow this plan exactly. When touching orphan_handler or paper_state, check these root causes still match current code.
