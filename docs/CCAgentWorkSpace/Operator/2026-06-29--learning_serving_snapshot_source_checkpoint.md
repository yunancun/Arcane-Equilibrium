# Learning Serving Snapshot Source Checkpoint

- Date: 2026-06-29
- Source commit: `f1d1a26c` (`Add learning serving snapshot packet`)
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

## Verification

- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/learning_serving_snapshot.py helper_scripts/research/tests/test_cost_gate_learning_serving_snapshot.py`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_serving_snapshot.py -q` -> `8 passed`
- `PYTHONPATH=helper_scripts/cron python3 -m pytest helper_scripts/cron/tests/test_learning_stack_health_snapshot.py -q` -> `7 passed`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_serving_snapshot.py helper_scripts/research/tests/test_cost_gate_learning_training_registry_repair.py tests/helper_scripts/test_model_registry_freshness_shadow.py -q` -> `22 passed`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_serving_snapshot.py helper_scripts/research/tests/test_cost_gate_learning_training_registry_repair.py helper_scripts/research/tests/test_cost_gate_learning_demo_mutation_envelope.py helper_scripts/research/tests/test_cost_gate_learning_adjudicator.py helper_scripts/research/tests/test_cost_gate_learning_proposal_compiler.py helper_scripts/research/tests/test_cost_gate_learning_event_contract.py helper_scripts/research/tests/test_cost_gate_autonomous_parameter_proposal.py helper_scripts/research/tests/test_cost_gate_learning_lane_decision_packet.py helper_scripts/research/tests/test_cost_gate_bounded_demo_runtime_readiness.py -q` -> `56 passed`
- `git diff --check`

## Boundaries

This checkpoint is source/test/docs only. It performs no model load, no runtime service/env/cron mutation, no registry write, no PG query/write, no serving slot write, no Bybit call, no order submission/cancel/modify, no writer/adapter enablement, no Cost Gate lowering, no probe/order/live authority, and no promotion/profit proof. Runtime `trade-core` remains last verified at `1a8cedb3`; this source commit has not been runtime-synced or used to load/serve a model.

## PM Handoff

Proceed to `P0-LEARN-PROOF-PROMOTION-GATE`: build a source-only ProofPacket -> PromotionVerdict gate requiring candidate-matched Demo fills, actual fees/slippage/spread/capacity/execution realism/tail risk, OOS/repeat evidence, matched controls, registry/serving snapshot agreement, and proof-exclusion pass before any promotion review can be considered.
