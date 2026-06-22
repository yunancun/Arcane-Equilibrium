# Sealed Horizon Bounded Probe Design

## Verdict

STATUS: DONE_WITH_CONCERNS
CONFIDENCE: high

`sealed_horizon_bounded_demo_probe_preflight_v1` now carries an inactive `bounded_demo_probe_design_v1`. This moves the Cost Gate escape path from "operator should review" to a concrete review packet: candidate side-cell/horizon, edge snapshot, edge-amplification levers, initial demo-only caps, success criteria, stop conditions, and required review artifacts.

The concern is intentional: this is still pre-authorization. It grants no Cost Gate lowering, no probe/order authority, no runtime mutation, and no promotion proof.

## What Changed

- Added `bounded_demo_probe_design_v1` to `helper_scripts/research/cost_gate_learning_lane/sealed_horizon_probe_preflight.py`.
- Added design readiness states:
  - `NOT_READY_FOR_OPERATOR_PROBE_REVIEW`
  - `OPERATOR_REVIEW_READY_FOR_BOUNDED_DEMO_PROBE_DESIGN`
  - `READY_FOR_SEPARATE_OPERATOR_AUTHORIZATION`
  - `AUTHORITY_BOUNDARY_VIOLATION`
- Included inactive suggested initial limits:
  - `max_probe_intents_before_review=3`
  - `max_demo_notional_usdt_per_order=10`
  - `max_total_demo_notional_usdt_before_review=30`
- Included success criteria:
  - `min_realized_avg_net_bps=0`
  - `min_realized_net_positive_pct=60`
  - fill/fee/slippage quality must be recorded
- Added stop conditions for authority drift, main Cost Gate adjustment requests, learning-lane stoppage, negative realized edge, and lineage gaps.
- Mirrored design status/limits into `alpha_discovery_throughput.profitability_path_scorecard` top path evidence.

## Why It Matters

The system already proved that production learning-lane evidence can accumulate. The next bottleneck is not more local backtest math; it is a bounded demo experiment that can verify whether blocked signals survive real demo fill, fee, and slippage conditions.

This change makes that experiment auditable before any approval. It supports the profitability thesis through side-cell specialization, horizon retiming, and learning from blocked signals, not through global Cost Gate lowering.

## Verification

- `python3 -m py_compile ...` passed for touched modules/tests.
- `PYTHONPATH=helper_scripts/research python3 -m pytest helper_scripts/research/tests/test_cost_gate_sealed_horizon_probe_preflight.py helper_scripts/research/tests/test_profitability_path_scorecard.py -q` -> `12 passed`.
- `PYTHONPATH=helper_scripts/research python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_cost_gate_sealed_horizon_operator_review.py helper_scripts/research/tests/test_cost_gate_sealed_horizon_learning_evidence.py -q` -> `58 passed`.
- `PYTHONPATH=helper_scripts/research python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` -> `71 passed`.
- `git diff --check` passed.
- Linux source fast-forwarded to `39176be3`; Linux py_compile and focused preflight/profitability tests passed (`12 passed`).
- Linux artifact-only sealed preflight smoke refreshed `/tmp/openclaw/cost_gate_learning_lane/sealed_horizon_probe_preflight_latest.json` sha256 `6d642a78e23d744c21fbb49e7618ffd66e7a2fa279923c73fc7d0f6b3ceea14d`, status `OPERATOR_REVIEW_REQUIRED`, design status `OPERATOR_REVIEW_READY_FOR_BOUNDED_DEMO_PROBE_DESIGN`, candidate `ma_crossover|BTCUSDT|Sell@240m`.
- Linux artifact-only profitability scorecard smoke wrote `/tmp/openclaw/profitability_refresh/20260622T031320Z/bounded_probe_design_v397/profitability_path_scorecard_latest.json` sha256 `6eb327b7c0f5ad96eaad2d9e0e9bb4ffaff88c3222910f4d442cb15905082f30`, closure `COST_GATE_ESCAPE_PREFLIGHT_BLOCKED_BY_OPERATOR_REVIEW`.

## Boundaries

No CI, no PG write/schema migration, no Bybit private/signed/trading call, no deploy/rebuild/restart, no crontab install, no writer/env enablement, no credential/auth/risk/order/strategy/runtime mutation, no Cost Gate lowering, no probe/order authority, and no promotion proof.

## Next Gate

Operator review remains required. If the operator approves later, the next engineering step should be a separate Rust-authority bounded demo-probe authorization path with these limits and stop conditions enforced, not a Python-side shortcut.
