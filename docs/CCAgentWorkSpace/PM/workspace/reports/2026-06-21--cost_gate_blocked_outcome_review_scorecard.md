# Cost-Gate Blocked Outcome Review Scorecard

VERDICT: PASS
CONFIDENCE: high

## 結論

v316 adds a conservative review scorecard after the cost-gate outcome refresh loop. Once blocked signals have `blocked_signal_outcome` rows, `cost_gate_learning_lane.outcome_review` groups them by side-cell and classifies each group as:

- `COLLECT_MORE_BLOCKED_SIGNAL_OUTCOMES`
- `KEEP_COST_GATE_BLOCKED`
- `DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE`

The aggregate scorecard can ask for more data, keep current blocks, or request operator review before demo probe authority. It cannot grant authority by itself.

## Thresholds

Default side-cell review thresholds:

- `min_outcomes_per_side_cell = 3`
- `min_avg_net_bps = 0.0`
- `min_net_positive_pct = 60.0`

These are deliberately weak enough for early demo-learning triage but still fail-closed: one or two positive blocked markouts are not enough to become a review candidate.

## Alpha Discovery Integration

`alpha_discovery_throughput.runtime_runner` now attaches `blocked_signal_outcome_review` when blocked outcomes exist. `discovery_loop` uses that status:

- insufficient sample -> `continue_recording_and_refreshing_blocked_signal_outcomes`
- failed side-cells -> `keep_cost_gate_blocked_for_reviewed_side_cells`
- threshold-clearing side-cells -> `operator_review_blocked_outcome_scorecard_before_demo_probe_authority`

## CLI

```bash
PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.outcome_review \
  --ledger /tmp/openclaw/cost_gate_learning_lane/probe_ledger.jsonl \
  --output /tmp/openclaw/cost_gate_learning_lane/blocked_outcome_review_latest.json
```

## Verification

- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` -> `23 passed`.
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` -> `34 passed`.
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/outcome_review.py helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py` -> passed.
- CLI help smoke passed.
- Empty-ledger review smoke returned `NO_BLOCKED_SIGNAL_OUTCOMES`.
- `git diff --check` passed.

## Boundary

Source/test/docs only. No PG write/schema migration, no Bybit private/signed/trading call, no engine/API rebuild/restart/deploy, no credential/auth/risk/order/strategy/runtime mutation. The review scorecard is not signal proof, execution proof, promotion proof, or Cost Gate relaxation.
