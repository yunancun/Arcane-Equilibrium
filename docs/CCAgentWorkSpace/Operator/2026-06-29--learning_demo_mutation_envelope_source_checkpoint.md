# Learning Demo Mutation Envelope Source Checkpoint

- Date: 2026-06-29
- Source commit: `ed54bf93` (`Add learning demo mutation envelope`)
- Task closed: `P0-LEARN-DEMO-MUTATION-ENVELOPE`
- Next active task: `P0-LEARN-TRAINING-REGISTRY-REPAIR`

## Result

`helper_scripts/research/cost_gate_learning_lane/learning_demo_mutation_envelope.py` now consumes `cost_gate_learning_adjudicator_v1` plus optional `bounded_demo_runtime_readiness_v1` and emits source-only `cost_gate_learning_demo_mutation_envelope_v1` packets.

The envelope:

- wraps review/defer/reject learning decisions into deterministic inert envelope ids
- preserves operator gate, runtime readiness gate, credential/mode blockers, standing-auth/final-window gate requirements, source event ids, and source event hashes
- propagates upstream quarantine state and authority-boundary violations
- fail-closes authority-bearing adjudicator or runtime-readiness input
- keeps `blocked_markout_proxy` as context/defer evidence only
- keeps Demo mutation authority, runtime mutation authority, order authority, Cost Gate change authority, and promotion proof false
- treats a green runtime readiness artifact as a prerequisite for a later operator/runtime apply checkpoint, not as mutation authority

## Verification

- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/learning_demo_mutation_envelope.py helper_scripts/research/tests/test_cost_gate_learning_demo_mutation_envelope.py`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_demo_mutation_envelope.py -q` -> `7 passed`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_demo_mutation_envelope.py helper_scripts/research/tests/test_cost_gate_learning_adjudicator.py helper_scripts/research/tests/test_cost_gate_learning_proposal_compiler.py helper_scripts/research/tests/test_cost_gate_learning_event_contract.py helper_scripts/research/tests/test_cost_gate_bounded_demo_runtime_readiness.py -q` -> `31 passed`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_demo_mutation_envelope.py helper_scripts/research/tests/test_cost_gate_learning_adjudicator.py helper_scripts/research/tests/test_cost_gate_learning_proposal_compiler.py helper_scripts/research/tests/test_cost_gate_learning_event_contract.py helper_scripts/research/tests/test_cost_gate_autonomous_parameter_proposal.py helper_scripts/research/tests/test_cost_gate_learning_lane_decision_packet.py helper_scripts/research/tests/test_cost_gate_bounded_demo_runtime_readiness.py -q` -> `43 passed`
- `git diff --check`

## Boundaries

This checkpoint is source/test/docs only. It preserves `artifact_probe_ledger_jsonl` as the current learning SSOT and does not start PG-backed cutover, runtime installation, or runtime mutation. It performs no PG query/write, no Bybit call, no order submission/cancel/modify, no runtime/env/service/crontab mutation, no writer/adapter enablement, no Demo mutation, no Cost Gate lowering, no probe/order/live authority, and no promotion/profit proof.

## PM Handoff

Proceed to `P0-LEARN-TRAINING-REGISTRY-REPAIR`: build a source-only ML maintenance / model registry repair contract that classifies training maintenance failures, registry staleness, ONNX-vs-registry freshness, artifact parity gaps, and legacy-retirement requirements into deterministic repair packets with budget/backpressure gates and no-runtime-mutation/no-order/no-Cost-Gate-change answers.
