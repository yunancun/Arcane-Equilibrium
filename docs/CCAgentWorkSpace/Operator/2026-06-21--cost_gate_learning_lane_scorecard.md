# 2026-06-21 -- Cost gate learning-lane scorecard

I upgraded the cost-gate reject audit so it now outputs a machine-readable JSON scorecard, not only a Markdown table.

Latest Linux read-only artifacts:

- Markdown sha256: `1e0a015192ed621c896dbe2a400a7c96b54b3ef3acae8826d6ecfde22ef61e2c`
- JSON sha256: `fee82cbcd0f730c78c1b35f01a8ad4c81d17b31335218086128f7ce82a23ccd3`
- Status: `LEARNING_LANE_PROBE_CANDIDATES_PRESENT`
- Outcome path: `OUTCOME_PATH_STALLED_FOR_FEATURE_REJECTS`

Current probe candidates:

- `ma_crossover ETHUSDT Sell`
- `ma_crossover NEARUSDT Sell`
- `grid_trading LTCUSDT Sell`
- `grid_trading ATOMUSDT Sell`

Important guardrail: `cost_gate_atr_unavailable` is now classified as `DATA_COVERAGE_BLOCKER`, not as a probe candidate. This prevents missing-ATR rows from being mistaken for alpha.

Operational read: still do not globally lower the main cost gate. This scorecard is the candidate selector for a future bounded demo-learning lane.
