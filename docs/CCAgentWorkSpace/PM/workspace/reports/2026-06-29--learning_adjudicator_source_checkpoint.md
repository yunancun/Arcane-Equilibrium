# Learning Adjudicator Source Checkpoint

- Date: 2026-06-29
- Source commit: `300ee0af` (`Add learning adjudicator`)
- Task closed: `P0-LEARN-ADJUDICATOR`
- Next active task: `P0-LEARN-DEMO-MUTATION-ENVELOPE`

## Result

`helper_scripts/research/cost_gate_learning_lane/learning_adjudicator.py` now consumes `cost_gate_learning_proposal_compiler_v1` and emits source-only `cost_gate_learning_adjudicator_v1` packets.

The adjudicator:

- ranks proposal candidates deterministically
- emits review-only decisions with deterministic decision ids
- supports explicit decision labels: `REVIEW`, `DEFER`, and `REJECT`
- gates fill-backed proof eligibility separately from review/context evidence
- treats `blocked_markout_proxy` as defer/context only, not fill-backed proof
- propagates upstream quarantine state and authority-boundary violations
- fail-closes authority-bearing input
- keeps Demo mutation readiness false and promotion proof readiness false

## Verification

- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/learning_adjudicator.py helper_scripts/research/tests/test_cost_gate_learning_adjudicator.py`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_adjudicator.py -q` -> `6 passed`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_adjudicator.py helper_scripts/research/tests/test_cost_gate_learning_proposal_compiler.py helper_scripts/research/tests/test_cost_gate_learning_event_contract.py helper_scripts/research/tests/test_cost_gate_autonomous_parameter_proposal.py helper_scripts/research/tests/test_cost_gate_learning_lane_decision_packet.py -q` -> `31 passed`
- after external source commit `1637004b` appeared, reran `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_adjudicator.py helper_scripts/research/tests/test_cost_gate_learning_proposal_compiler.py helper_scripts/research/tests/test_cost_gate_learning_event_contract.py -q` -> `19 passed`
- `git diff --check`

## Boundaries

This checkpoint is source/test/docs only. It preserves `artifact_probe_ledger_jsonl` as the current learning SSOT and does not start PG-backed cutover. It performs no PG query/write, no Bybit call, no order submission/cancel/modify, no runtime/env/service/crontab mutation, no Demo mutation, no Cost Gate lowering, no probe/order/live authority, and no promotion/profit proof.

## PM Handoff

Proceed to `P0-LEARN-DEMO-MUTATION-ENVELOPE`: compile adjudicated review-only learning decisions into an inert, operator-gated Demo mutation envelope with explicit bounded Demo/runtime authorization gates, credential/mode blocker preservation, quarantine and authority propagation, and no-mutation/no-order/no-Cost-Gate-change answers.
