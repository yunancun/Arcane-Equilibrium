# Learning Serving Snapshot Source And Runtime Checkpoint

- Date: 2026-06-29
- Source commit: `f1d1a26c` (`Add learning serving snapshot packet`)
- Runtime head: `f1d1a26c19954a79d28014f75451c4a882f8d450`
- Task closed: `P0-LEARN-SERVING-SNAPSHOT`
- Next active task: `P0-LEARN-PROOF-PROMOTION-GATE`

## Result

`helper_scripts/research/cost_gate_learning_lane/learning_serving_snapshot.py` now consumes `cost_gate_learning_training_registry_repair_v1`, `learning_stack_health_snapshot_v1`, a model registry summary artifact, and an optional `learning_runtime_serving_state_v1` artifact. It emits source-only `cost_gate_learning_serving_snapshot_v1` packets.

The serving snapshot packet:

- requires the training/registry repair packet to be in the no-repair-required state before a candidate can be emitted
- checks registry row presence, shadow/canary row presence, q10/q50/q90 artifact hashes, artifact hash parity, feature schema hash, and ONNX-not-newer-than-registry health
- excludes stale/legacy artifacts unless they are explicitly retired or excluded from serving
- requires runtime loaded version and artifact hashes to match registry intent, or requires an explicit visible rule-based fallback with hidden ML inference rejected
- records shadow/canary/production slot constraints while keeping slot writes false
- fail-closes authority-bearing input
- keeps model load, runtime mutation, registry/PG write, serving authority, Cost Gate change, order/live authority, and promotion proof false

Linux `trade-core` was fast-forwarded to the same source head, with the five learning cron expected-head pins repinned to `f1d1a26c19954a79d28014f75451c4a882f8d450`. Engine PID `877736` stayed running; no engine/API restart was performed.

Runtime materialization under `/tmp/openclaw/session_loop_state_20260629T_serving_snapshot/` produced:

- readiness `/tmp/openclaw/session_loop_state_20260629T_serving_snapshot/bounded_demo_runtime_readiness_after_f1d_sync.json` sha `8f9da6b0d5be10fe98a17a1a78020f2adc27957fdbbb301c18b5ebf7552b7a13`
- learning health `/tmp/openclaw/session_loop_state_20260629T_serving_snapshot/learning_stack_health_snapshot_after_f1d_sync.json` sha `f8c41c311034dd3464e83ecc0dad324628373be4501d0fb7e1c449ae0f51b536`
- training/registry repair `/tmp/openclaw/session_loop_state_20260629T_serving_snapshot/learning_training_registry_repair_after_f1d_sync.json` sha `1a9f72192764fdfed80799e14ca1a005b3d9bf09d322c519867b8a5ca1f2ab7a`
- serving snapshot `/tmp/openclaw/session_loop_state_20260629T_serving_snapshot/learning_serving_snapshot_after_f1d_sync.json` sha `83ac78520c9739b17378ddc1d88f3150237a36a1e96b87a236cf6eca7bbeb68d`

The runtime serving snapshot status is `LEARNING_SERVING_SNAPSHOT_BLOCKED_BY_TRAINING_REGISTRY_REPAIR_NO_AUTHORITY`. The bounded Demo readiness status remains `BOUNDED_DEMO_RUNTIME_BLOCKED_BY_CREDENTIALS` because the Demo slot key is still `FWkGZX...g53T` / sha12 `317f982c009f` while the expected key prefix is `BHw4...`, and connector config remains `BYBIT_MODE=read_only`, `BYBIT_CONNECTOR_WRITE_ENABLED=false`.

## Verification

- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/learning_serving_snapshot.py helper_scripts/research/tests/test_cost_gate_learning_serving_snapshot.py`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_learning_serving_snapshot.py` -> `10 passed`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_learning_serving_snapshot.py helper_scripts/research/tests/test_cost_gate_learning_training_registry_repair.py helper_scripts/research/tests/test_cost_gate_learning_demo_mutation_envelope.py helper_scripts/research/tests/test_cost_gate_learning_adjudicator.py helper_scripts/research/tests/test_cost_gate_learning_proposal_compiler.py helper_scripts/research/tests/test_cost_gate_learning_event_contract.py helper_scripts/research/tests/test_cost_gate_bounded_demo_runtime_readiness.py` -> `46 passed`
- runtime `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/learning_serving_snapshot.py helper_scripts/research/tests/test_cost_gate_learning_serving_snapshot.py`
- runtime adjacent serving/repair/envelope/adjudicator/proposal/event/readiness suite -> `46 passed`
- `git diff --check`

## Boundaries

This checkpoint is source/runtime-sync/read-only-materialization only. It performs no model load, no runtime service/env mutation, no registry write, no PG query/write, no serving slot write, no Bybit call, no order submission/cancel/modify, no writer/adapter enablement, no Cost Gate lowering, no probe/order/live authority, and no promotion/profit proof.

## PM Handoff

Proceed to `P0-LEARN-PROOF-PROMOTION-GATE`: build a source-only ProofPacket -> PromotionVerdict gate requiring candidate-matched Demo fills, actual fees/slippage/spread/capacity/execution realism/tail risk, OOS/repeat evidence, matched controls, registry/serving snapshot agreement, and proof-exclusion pass before any promotion review can be considered.
