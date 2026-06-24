# Operator Note: Cost Gate Learning SSOT Decision

- Timestamp UTC: `2026-06-24T02:30:18Z`
- Status: `DONE_WITH_CONCERNS`
- Scope: source/test/docs only

新增 `helper_scripts/research/cost_gate_learning_lane/learning_ssot_decision.py`，用來輸出 no-authority `cost_gate_learning_ssot_decision_v1`。

Current decision semantics:

- current learning SSOT can only be artifact `probe_ledger.jsonl` or `NONE`;
- target learning SSOT remains future `pg_backed_cost_gate_learning_ledger`;
- PG-backed cutover is always false unless future schema, writer idempotency, reconstruction proof, proof-exclusion guard, and operator cutover review are separately proven;
- writer config/process flag only routes to migration review, not PG readiness;
- any input claiming Cost Gate lowering, probe/order authority, runtime authority, PG write, order submission, or promotion proof fail-closes as `AUTHORITY_BOUNDARY_VIOLATION`;
- no probe/order/live authority is emitted.

Verification:

- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/learning_ssot_decision.py`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py` -> `86 passed`
- `git diff --check`

Operator action still required before P0 can advance: exchange working-order overhang and SOL/ETH fill-lineage drift must be resolved or explicitly quarantined. This change does not cancel/modify orders, write PG, enable writers, edit crontab, restart services, or grant bounded probe authority.
