# LearningEvent Contract Source Checkpoint

- Date: 2026-06-29
- Source commit: `6b93cf2a` (`Add learning event contract`)
- Task closed: `P0-LEARN-LEDGER-EVENT-CONTRACT`
- Next active task: `P0-LEARN-PROPOSAL-COMPILER`

## Result

`helper_scripts/research/cost_gate_learning_lane/learning_event_contract.py` now wraps the current artifact `probe_ledger.jsonl` and explicit artifact JSON inputs into deterministic `cost_gate_learning_event_v1` packets under `cost_gate_learning_event_contract_v1`.

Each event carries:

- deterministic `event_id` and `event_packet_sha256`
- event type and source schema/record type
- candidate id / side-cell identity
- source generated timestamp
- source refs with path, source sha, row sha, line number or artifact index
- proof tier
- no-authority answers fixed false for runtime mutation, PG write, Bybit call, order submission, Cost Gate lowering, probe/order/live authority, promotion evidence, and promotion proof

`blocked_signal_outcome` rows and `outcome_source=market_markout_proxy_for_blocked_signal` are labeled `proof_tier=blocked_markout_proxy`. Malformed JSONL, non-object rows/artifacts, missing candidate identity, and missing/unparseable source timestamps are quarantined. Authority-bearing input fails closed as `AUTHORITY_BOUNDARY_VIOLATION` and emits no consumable events.

## Verification

- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/learning_event_contract.py helper_scripts/research/tests/test_cost_gate_learning_event_contract.py`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_event_contract.py -q` -> `7 passed`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_event_contract.py helper_scripts/research/tests/test_cost_gate_autonomous_parameter_proposal.py helper_scripts/research/tests/test_cost_gate_learning_lane_decision_packet.py -q` -> `19 passed`
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/learning_event_contract.py helper_scripts/research/cost_gate_learning_lane/learning_ssot_decision.py helper_scripts/research/cost_gate_learning_lane/autonomous_parameter_proposal.py helper_scripts/research/tests/test_cost_gate_learning_event_contract.py`
- `git diff --check`

## Boundaries

This checkpoint is source/test/docs only. It preserves `artifact_probe_ledger_jsonl` as the current learning SSOT and does not start PG-backed cutover. It performs no PG query/write, no Bybit call, no order submission/cancel/modify, no runtime/env/service/crontab mutation, no Demo mutation, no Cost Gate lowering, no probe/order/live authority, and no promotion/profit proof.

## PM Handoff

Proceed to `P0-LEARN-PROPOSAL-COMPILER`: consume versioned `LearningEvent` packets into review-only proposal candidates with deterministic grouping, evidence-window summaries, proof-tier filters, quarantine propagation, and authority-contamination fail-closed behavior. `blocked_markout_proxy` remains context/review evidence only and must not be counted as fill-backed proof.
