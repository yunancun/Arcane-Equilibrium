# P1 Learning SSOT Decision Packet

- Timestamp UTC: `2026-06-24T02:30:18Z`
- Active blocker: `P1-LEARNING-LOOP-CLOSURE`
- Status: `DONE_WITH_CONCERNS`
- Scope: source/test/docs only

## Session Loop State

- `session_goal`: Profit-first Demo-learning Autonomy Improvement Loop under Aggressive Alpha Expansion Mode.
- `active_blocker_id`: `P1-LEARNING-LOOP-CLOSURE`
- `blocker_goal`: record a durable, machine-readable learning SSOT decision between the current artifact ledger and future PG-backed Cost Gate learning ledger.
- `profit_relevance`: autonomous parameter proposals and bounded Demo proof review need one canonical learning evidence source; otherwise profit evidence can be double-counted, stale, or unreconstructable.
- `completed_blockers`: proof-exclusion guard source checkpoint completed in commit `1659ead94e5cd3fafed0bef6738c8aa4e9d83b36`.
- `blocked_blockers`: `P0-PROFIT-EVIDENCE-QUALITY` and `P0-PROFIT-CANDIDATE-SELECTION` remain operator-gated by exchange order overhang and SOL/ETH fill-lineage drift.
- `previous_report_paths`: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--profit_evidence_quality_operator_checkpoint.md`, `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--profit_evidence_quality_proof_exclusion_guard.md`, `docs/CCAgentWorkSpace/Operator/2026-06-24--profit_evidence_quality_proof_exclusion_guard.md`.
- `source_head`: `1659ead94e5cd3fafed0bef6738c8aa4e9d83b36` at loop start.
- `runtime_timestamp`: not refreshed; no runtime action was authorized or needed for this source-only checkpoint.
- `pg_snapshot_timestamp`: not refreshed; no PG read/write was performed.
- `artifact_mtimes`: not refreshed; no canonical runtime artifact was regenerated.
- `operator_action_required`: still required for Bybit cancel/modify/close, PG reconciliation/write, crontab/restart/writer enablement, probe/order/live authority.
- `new_evidence_delta_required`: no runtime delta required for P1 source-only SSOT decision; P0 re-audit still requires operator/runtime evidence delta.
- `new_evidence_delta_found`: source gap found: no explicit Cost Gate learning SSOT decision artifact existed.
- `acceptance_criteria`: artifact-only builder emits no-authority `cost_gate_learning_ssot_decision_v1`, treats `probe_ledger.jsonl` as current SSOT unless future PG-backed gates are proven, never treats writer flags as PG readiness, fail-closes on authority-bearing inputs, and is covered by tests.
- `next_blocker_id`: `P1-AUTONOMOUS-PARAMETER-PROPOSAL` for source-only contract work; P0 candidate selection remains operator-gated.

## Anti-Repeat Decision

`P0-PROFIT-EVIDENCE-QUALITY` already has a read-only operator checkpoint and a source-only proof-exclusion guard report. There is no new source HEAD/runtime snapshot/PG snapshot/artifact mtime/operator authorization delta for the exchange overhang audit, so repeating that audit would violate the anti-repeat rule. The loop moved to `P1-LEARNING-LOOP-CLOSURE`, which had a source-only gap that could be closed safely.

## Change

Added `helper_scripts/research/cost_gate_learning_lane/learning_ssot_decision.py`.

The packet:

- emits schema `cost_gate_learning_ssot_decision_v1`;
- declares `artifact_probe_ledger_jsonl` as current learning SSOT only when activation preflight shows learning rows and no authority boundary violation exists;
- keeps `pg_backed_ledger_is_current_ssot=false` and `pg_backed_cutover_ready=false`;
- records PG migration gates as false for schema verification, writer idempotency, reconstruction proof, and PG probe;
- routes runtime writer flags to `PG_BACKED_LEDGER_MIGRATION_REVIEW_REQUIRED`, not readiness;
- prepends proof-exclusion repair/quarantine before any cutover;
- fail-closes to `AUTHORITY_BOUNDARY_VIOLATION` when an input artifact claims Cost Gate lowering, probe/order authority, runtime authority, PG write, order submission, or promotion proof.

Updated `helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py` and `helper_scripts/SCRIPT_INDEX.md`.

## Verification

- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/learning_ssot_decision.py`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py` -> `86 passed`
- `git diff --check`

## Boundaries

No PG query/write, Bybit call, order/cancel/modify, runtime mutation, service restart, crontab edit, Rust writer enablement, Cost Gate lowering, probe authority, order authority, live promotion, or promotion proof was performed.

## Concerns

This closes the source-only SSOT decision artifact, not the P0 runtime/operator blocker. Candidate selection for a bounded Demo probe remains blocked until open order overhang and fill-lineage drift are resolved or explicitly quarantined by the operator.
