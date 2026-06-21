# 2026-06-21 -- Cost gate learning-lane scorecard

## Decision

The previous counterfactual audit proved that cost-gate rejects are recorded but not learnable enough through the current outcome path. This pass turns that audit into a machine-readable learning-lane selector.

`helper_scripts/db/audit/cost_gate_reject_counterfactual.py` now emits schema `cost_gate_reject_counterfactual_v2`, optional JSON output, and per-row `learning_lane_action`. Classification is conservative:

- `LEARNING_PROBE_CANDIDATE`: only for `negative_edge` reject rows whose sample, median gross, average net, and net-positive rate clear thresholds.
- `BLOCK_CONFIRMED`: rejected cells that look correctly blocked.
- `DATA_COVERAGE_BLOCKER`: rows such as `cost_gate_atr_unavailable`; these require data/feature coverage work, not exploration budget.
- `TAIL_ONLY_WATCH`, `NO_PROBE`, `INSUFFICIENT_SAMPLE`: not ready for demo-learning exploration.

## Runtime Evidence

Linux read-only artifact refresh:

- Markdown: `/tmp/openclaw/cost_gate_counterfactual/cost_gate_reject_counterfactual_latest.md`
- Markdown sha256: `1e0a015192ed621c896dbe2a400a7c96b54b3ef3acae8826d6ecfde22ef61e2c`
- JSON: `/tmp/openclaw/cost_gate_counterfactual/cost_gate_reject_counterfactual_latest.json`
- JSON sha256: `fee82cbcd0f730c78c1b35f01a8ad4c81d17b31335218086128f7ce82a23ccd3`
- Generated: `2026-06-21T10:32:30+00:00`

Coverage:

- cost-gate risk verdicts/features: `181,989`
- joined intents: `0`
- joined outcomes: `0`
- old decision-context pending backlog: `6,827,559`
- context coverage: `0.1934%`
- outcome path: `OUTCOME_PATH_STALLED_FOR_FEATURE_REJECTS`

Learning-lane action counts:

- `LEARNING_PROBE_CANDIDATE`: `4`
- `BLOCK_CONFIRMED`: `11`
- `DATA_COVERAGE_BLOCKER`: `54`
- `INSUFFICIENT_SAMPLE`: `25`
- `NO_PROBE`: `5`
- `TAIL_ONLY_WATCH`: `1`

Probe candidates:

- `ma_crossover ETHUSDT Sell`: avg net `97.9788bp`, net-positive `86.01%`
- `ma_crossover NEARUSDT Sell`: avg net `16.2197bp`, net-positive `99.95%`
- `grid_trading LTCUSDT Sell`: avg net `9.5123bp`, net-positive `65.15%`
- `grid_trading ATOMUSDT Sell`: avg net `3.5169bp`, net-positive `56.02%`

## PM Read

This is the next concrete step toward the operator's direction: demo as an autonomous learning system, not merely a controlled order switch.

The scorecard does not authorize broad gate loosening. It identifies where a future bounded demo-learning lane should spend tiny exploration budget, and where it should not. `cost_gate_atr_unavailable` rows are intentionally excluded from probe candidates because they are data-coverage failures, not completed edge estimates.

## Verification

- Mac: `python3 -m pytest -q helper_scripts/db/audit/test_cost_gate_reject_counterfactual.py program_code/research/tests/test_fill_sim_cost_wall.py` -> `30 passed`
- Mac: `python3 -m py_compile helper_scripts/db/audit/cost_gate_reject_counterfactual.py`
- Mac: `git diff --check`
- Linux: audit tests -> `6 passed`
- Linux: py_compile passed
- Linux: read-only report generation passed with `PGOPTIONS="-c default_transaction_read_only=on"`

## Boundary

Source/test/docs plus selective Linux source sync and `/tmp/openclaw` artifact writes. No PG table write or schema migration. No Bybit private/signed/trading call. No engine/API rebuild or restart. No credential, auth, risk, order, strategy, or runtime config mutation. This is candidate-selection evidence for a future bounded demo-learning lane, not permission to trade.
