# Sealed Horizon Evidence Review Bridge

## Summary

`sealed_horizon_learning_evidence_v1` is now consumed by both upper-level closure artifacts:

- `alpha_profitability_path_scorecard_v1`
- `cost_gate_profit_learning_decision_packet_v1`

This turns the existing sealed BTCUSDT Sell 240m scratch evidence from an isolated packet into an operator-reviewable bounded demo-probe candidate. It does not grant order authority, probe authority, runtime mutation, Cost Gate lowering, or promotion proof.

## Source Changes

- `helper_scripts/research/alpha_discovery_throughput/profitability_path_scorecard.py`
  - Added `--horizon-learning-evidence-json`.
  - New path status: `SEALED_HORIZON_LEARNING_EVIDENCE_READY_FOR_OPERATOR_REVIEW`.
  - New next gate: `operator_reviews_bounded_demo_probe_for_sealed_horizon_candidate`.
  - Carries sealed learning evidence metrics such as horizon, blocked outcomes, avg net bps, net-positive percent, and input sha256s.

- `helper_scripts/research/cost_gate_learning_lane/decision_packet.py`
  - Added `--sealed-horizon-learning-evidence-json`.
  - New packet status: `OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE`.
  - Keeps production learning-lane activation/repair as a required next action before any runtime probe.

## Verification

- `python3 -m py_compile ...` passed.
- `PYTHONPATH=helper_scripts/research python3 -m pytest helper_scripts/research/tests/test_profitability_path_scorecard.py helper_scripts/research/tests/test_cost_gate_learning_lane_decision_packet.py -q` = `10 passed`.
- `PYTHONPATH=helper_scripts/research python3 -m pytest helper_scripts/research/tests/test_profitability_path_scorecard.py helper_scripts/research/tests/test_cost_gate_learning_lane_decision_packet.py helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py -q` = `62 passed`.
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_sealed_horizon_learning_evidence.py helper_scripts/research/tests/test_profitability_path_scorecard.py helper_scripts/research/tests/test_cost_gate_learning_lane_decision_packet.py -q` = `13 passed`.
- `git diff --check` passed.
- Linux `trade-core` fast-forwarded to the checkpoint and artifact-only smokes passed:
  - `/tmp/openclaw/profitability_refresh/20260622T031320Z/profitability_path_scorecard_v389/profitability_path_scorecard_v389_latest.json`
  - `/tmp/openclaw/profitability_refresh/20260622T031320Z/profit_learning_decision_packet_v389/profit_learning_decision_packet_v389_latest.json`
  - top path/status: `horizon_edge_amplification:ma_crossover|BTCUSDT|Sell` / `SEALED_HORIZON_LEARNING_EVIDENCE_READY_FOR_OPERATOR_REVIEW`
  - decision status: `OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE`
  - sealed evidence: 16,515 240m blocked outcomes, avg net `3.0511bp`, net-positive `68.56%`

## Boundary

Artifact-only source/test/docs checkpoint. No PG write/schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy/runtime mutation, deploy/rebuild/restart, Cost Gate lowering, probe/order authority, or promotion proof.
