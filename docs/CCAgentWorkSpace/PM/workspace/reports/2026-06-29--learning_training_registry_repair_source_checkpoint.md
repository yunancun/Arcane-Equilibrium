# Learning Training/Registry Repair Source Checkpoint

- Date: 2026-06-29
- Source commit: `1a8cedb3` (`Add learning training registry repair packet`)
- Task closed: `P0-LEARN-TRAINING-REGISTRY-REPAIR`
- Next active task: `P0-LEARN-SERVING-SNAPSHOT`

## Result

`helper_scripts/research/cost_gate_learning_lane/learning_training_registry_repair.py` now consumes `learning_stack_health_snapshot_v1` and emits source-only `cost_gate_learning_training_registry_repair_v1` packets.

The repair packet:

- classifies ML maintenance failures and stale maintenance history into deterministic repair items
- classifies model registry stale/incomplete state, ONNX artifact newer-than-registry state, artifact/PG parity mismatch, and legacy artifact retirement review requirements
- includes budget/backpressure gates, operator runbook text, rollback plan text, source refs, and deterministic repair ids
- keeps every action in `allowed_actions` false for actual training, ONNX export, registry write, PG write, artifact deletion, runtime cron/env/service mutation, serving, Cost Gate change, order authority, live authority, and promotion proof
- fail-closes authority-bearing health snapshot input as `TRAINING_REGISTRY_REPAIR_AUTHORITY_BOUNDARY_VIOLATION`
- treats output as a source-only repair plan for later reviewed operations, not as runtime/registry authority

## Verification

- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/learning_training_registry_repair.py helper_scripts/research/tests/test_cost_gate_learning_training_registry_repair.py`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_training_registry_repair.py -q` -> `5 passed`
- `PYTHONPATH=helper_scripts/cron python3 -m pytest helper_scripts/cron/tests/test_learning_stack_health_snapshot.py -q` -> `7 passed`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_training_registry_repair.py tests/helper_scripts/test_model_registry_freshness_shadow.py -q` -> `14 passed`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_training_registry_repair.py helper_scripts/research/tests/test_cost_gate_learning_demo_mutation_envelope.py helper_scripts/research/tests/test_cost_gate_learning_adjudicator.py helper_scripts/research/tests/test_cost_gate_learning_proposal_compiler.py helper_scripts/research/tests/test_cost_gate_learning_event_contract.py helper_scripts/research/tests/test_cost_gate_autonomous_parameter_proposal.py helper_scripts/research/tests/test_cost_gate_learning_lane_decision_packet.py helper_scripts/research/tests/test_cost_gate_bounded_demo_runtime_readiness.py -q` -> `48 passed`
- `git diff --check`

## Residual Verification Note

A wider static-wrapper run that included `tests/helper_scripts/test_ml_training_maintenance_cron_static.py` still fails in existing `test_f08_wrapper_invokes_runner_with_all_jobs`: the wrapper selects the repository venv python under `program_code/exchange_connectors/bybit_connector/control_api_v1/.venv/bin/python3` instead of the test mock PATH python, then reaches local DB/numpy environment setup. This is an existing wrapper/test-environment interaction outside the new source-only repair helper; it remains a residual verification gap for the future ML maintenance wrapper repair lane.

## Boundaries

This checkpoint is source/test/docs only. It performs no training run, no ONNX export, no registry write, no PG query/write, no artifact delete, no model serving/load, no Bybit call, no order submission/cancel/modify, no runtime/env/service/crontab mutation, no writer/adapter enablement, no Cost Gate lowering, no probe/order/live authority, and no promotion/profit proof.

## PM Handoff

Proceed to `P0-LEARN-SERVING-SNAPSHOT`: build a source-only serving snapshot contract that consumes the training/registry repair packet plus health/registry artifacts and emits deterministic immutable serving snapshot candidate/blocked packets with model registry/ONNX parity, feature schema, rollback, canary/shadow/production slot constraints, stale/legacy artifact exclusion, and no model-load/runtime-mutation/PG-write/order/Cost-Gate/promotion authority.
