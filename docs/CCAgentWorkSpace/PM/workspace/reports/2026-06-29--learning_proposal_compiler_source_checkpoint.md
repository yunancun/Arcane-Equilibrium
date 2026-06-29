# Learning Proposal Compiler Source Checkpoint

- Date: 2026-06-29
- Source commit: `7cfec46e` (`Add learning proposal compiler`)
- Task closed: `P0-LEARN-PROPOSAL-COMPILER`
- Next active task: `P0-LEARN-ADJUDICATOR`

## Result

`helper_scripts/research/cost_gate_learning_lane/learning_proposal_compiler.py` now consumes `cost_gate_learning_event_contract_v1` and emits source-only `cost_gate_learning_proposal_compiler_v1` packets.

The compiler:

- groups `cost_gate_learning_event_v1` events deterministically by candidate id
- emits review-only proposal candidates with deterministic proposal ids
- summarizes evidence windows, event type counts, proof tier counts, source event ids, and source event packet hashes
- propagates upstream quarantine state and authority-boundary violations
- fail-closes authority-bearing input
- keeps `blocked_markout_proxy` as review/context evidence only
- fixes `blocked_markout_proxy_counts_as_fill_backed_proof=false`
- keeps fill-backed proof readiness and promotion proof readiness false

## Verification

- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/learning_proposal_compiler.py helper_scripts/research/tests/test_cost_gate_learning_proposal_compiler.py`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_proposal_compiler.py -q` -> `6 passed`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_proposal_compiler.py helper_scripts/research/tests/test_cost_gate_learning_event_contract.py helper_scripts/research/tests/test_cost_gate_autonomous_parameter_proposal.py helper_scripts/research/tests/test_cost_gate_learning_lane_decision_packet.py -q` -> `25 passed`
- `git diff --check`

## Boundaries

This checkpoint is source/test/docs only. It preserves `artifact_probe_ledger_jsonl` as the current learning SSOT and does not start PG-backed cutover. It performs no PG query/write, no Bybit call, no order submission/cancel/modify, no runtime/env/service/crontab mutation, no Demo mutation, no Cost Gate lowering, no probe/order/live authority, and no promotion/profit proof.

## PM Handoff

Proceed to `P0-LEARN-ADJUDICATOR`: adjudicate review-only proposal candidates into deterministic decisions with reject/defer/review labels, proof-tier eligibility gates, quarantine and authority propagation, and no-mutation/no-order/no-Cost-Gate-change answers.
