# Operator Note: Bounded Probe Active Proof Reconstruction Contract

Date: 2026-06-25
Status: DONE_WITH_CONCERNS
Blocker: `P0-BOUNDED-PROBE-ACTIVE-CALLER-RESTART-OUTCOME-PROOF-CONTRACT-DEMO-ONLY`

## What Changed

- Future active bounded Demo requests are tagged with active-specific source `bounded_probe_active_near_touch`.
- Pending orders now retain signal timestamp and Decision Lease id for reconstruction.
- Audit details can include `active_bounded_probe_proof_key` for non-close active bounded-probe orders.
- Result review now excludes active-sourced fills from proof unless the proof key matches candidate lineage, demo/live_demo mode, positive signal timestamp, Decision Lease, and candidate-bound orderLinkId hash/shape.

## What Did Not Change

No runtime sync, no Demo order, no Bybit call, no PG action, no service/crontab/env mutation, no global Cost Gate lowering, no live/mainnet action, no active probe/order authority, and no promotion proof.

## Verification

Focused Rust suites passed: active-order 13, active bounded submission 5, pending registration 27, pending sweep 24, dual-rail dispatch 30.
Focused Python suites passed: 58 tests plus py_compile and `git diff --check`.

## Next Safe Action

Review the actual `adapter_enabled=true` active caller path and post-restart pending-order reconciliation as a separate source-only blocker before any runtime adapter enablement.
