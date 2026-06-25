# PM Report: Bounded Probe Active Proof Reconstruction Contract

Date: 2026-06-25
Status: DONE_WITH_CONCERNS
Active blocker: `P0-BOUNDED-PROBE-ACTIVE-CALLER-RESTART-OUTCOME-PROOF-CONTRACT-DEMO-ONLY`

## Decision

Closed the source-only active bounded Demo proof/reconstruction slice. This change makes future active bounded-probe fills reconstructable enough to be either proof-eligible or explicitly proof-excluded.

This is not runtime adapter enablement, not Demo order authority, not Cost Gate proof, and not promotion proof.

## Change

- Active bounded-probe dispatch now uses `reference_source=bounded_probe_active_near_touch` instead of the generic bounded-probe source.
- `PendingOrder` now preserves `signal_ts_ms` and `decision_lease_id` from `OrderDispatchRequest`.
- Pending registration emits `details.active_bounded_probe_proof_key` only for non-close active bounded-probe orders with stable candidate lineage.
- `bounded_probe_active_order.rs` validates active proof keys against engine mode, signal timestamp, side-cell, context, signal, orderLinkId, Decision Lease id, and active reference source.
- Python proof exclusion now rejects active-sourced fill rows unless the proof key passes Rust-equivalent candidate-bound orderLinkId validation and row consistency checks.

## Review Chain

- PA(default): `DONE_WITH_CONCERNS`; accepted the approach, required Python proof exclusion and a non-close guard.
- E2(explorer): `DONE_WITH_CONCERNS`; found top-level/details source masking and malformed proof-key acceptance. PM fixed both.
- E4(worker): `DONE`; focused source verification passed before the E2 follow-up fixes. PM reran final focused verification after those fixes.

## Verification

- `cargo test -p openclaw_engine bounded_probe_active_order --lib`: 13 passed.
- `cargo test -p openclaw_engine active_bounded_probe --lib`: 5 passed.
- `cargo test -p openclaw_engine pending_registration_order_type_tests --lib`: 27 passed.
- `cargo test -p openclaw_engine pending_sweep --lib`: 24 passed.
- `cargo test -p openclaw_engine dual_rail_dispatch --lib`: 30 passed.
- `python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_active_order_wiring_contract.py helper_scripts/research/tests/test_cost_gate_bounded_probe_authority_patch_readiness.py helper_scripts/research/tests/test_cost_gate_bounded_probe_result_review.py helper_scripts/research/tests/test_cost_gate_bounded_probe_execution_realism_review.py`: 58 passed.
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/proof_exclusion.py helper_scripts/research/tests/test_cost_gate_bounded_probe_result_review.py`: passed.
- `git diff --check`: passed.

Formatting note: repo-wide `cargo fmt --all --check` and touched-file rustfmt still report pre-existing file-level rustfmt drift in large Rust files, so PM did not apply broad formatting churn.

## Remaining Concerns

- Actual `adapter_enabled=true` active bounded-probe caller remains unwired/unreviewed.
- Runtime Linux has not been synced for the active-order source patches in this sequence.
- Post-restart pending-order reconciliation still needs a distinct review before any runtime adapter enablement.
- This creates a proof contract; it does not create candidate-matched profit proof or authorize any order path.

## Boundary

Source/test/docs only. No runtime sync, no `/tmp` runtime artifact, no latest/plan/admission/ledger mutation, no PG read/write, no Bybit API call, no order/cancel/modify, no service/env/crontab mutation, no Rust writer enablement, no global Cost Gate lowering, no live/mainnet action, no active probe/order authority, and no promotion proof.

## Next Safe Action

Open the distinct source-only `adapter_enabled=true` active caller enablement review and post-restart reconciliation blocker. Do not repeat this proof/reconstruction slice unless new source/runtime/artifact evidence appears.
