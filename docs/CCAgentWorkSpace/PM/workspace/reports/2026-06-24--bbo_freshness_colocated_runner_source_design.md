# BBO Freshness Co-Located Runner Source Design

## Session Loop State

- `active_blocker_id`: `P0-BOUNDED-PROBE-BBO-FRESHNESS-COLOCATED-RUNNER-SOURCE-DESIGN-DEMO-ONLY`
- `blocker_goal`: Implement a source-only co-located read-only PG snapshot + construction-preview runner for the AVAX BBO freshness repair path.
- `profit_relevance`: AVAX is cap-feasible but stale-BBO blocked. Reducing snapshot-to-preview latency is the fastest safe path toward candidate-matched demo net-PnL evidence without changing risk gates.
- `operator_action_required`: false for source-only implementation and supplied-mode smoke. Runtime `--pg-readonly` execution still requires a separate runtime review/sync checkpoint.
- `next_blocker_id`: `P0-BOUNDED-PROBE-BBO-FRESHNESS-COLOCATED-RUNNER-RUNTIME-REVIEW-DEMO-ONLY`

## Anti-Repeat Decision

`PROCEED_WITH_SOURCE_ONLY_DESIGN`.

The BBO freshness repair proposal was ready and no co-located runner source/design artifact existed. This checkpoint did not repeat the previous diagnosis or proposal.

## Source Changes

Added:

- `helper_scripts/research/cost_gate_learning_lane/bbo_freshness_colocated_runner.py`
- `helper_scripts/research/tests/test_cost_gate_bbo_freshness_colocated_runner.py`

Hardened:

- `helper_scripts/research/cost_gate_learning_lane/bounded_probe_candidate_construction_preview.py`
- `helper_scripts/research/tests/test_cost_gate_bounded_probe_candidate_construction_preview.py`

Key contract points:

- consumes ready `bounded_probe_bbo_freshness_repair_proposal_v1`;
- reuses `build_candidate_construction_preview`;
- supplied-market mode is smoke-only and cannot close the co-located PG gate;
- `COLOCATED_RUNNER_READY_NO_ORDER` requires `pg_readonly_mode=True`;
- CLI requires exactly one mode: `--market-snapshot-json` or `--pg-readonly`;
- `--pg-readonly` requires `--market-snapshot-output`;
- no Bybit call/order/cancel/modify path exists;
- PG mode uses `set_session(readonly=True, autocommit=True)`;
- runner and construction preview reject enum authority fields and mutation aliases.

## Runtime Smoke Artifact

- `/tmp/openclaw/cost_gate_learning_lane/co_located_bbo_snapshot_preview_runner_design_latest.json`
- sha256 `f520ce1eb6862236eee83862e8a0f30cd46f077232fa2b26378c2ebc31d065a5`
- schema `bounded_probe_bbo_freshness_colocated_runner_v1`
- status `COLOCATED_RUNNER_BBO_STALE_NO_ORDER`
- mode `supplied_market_snapshot`
- preview status `CANDIDATE_CONSTRUCTION_BBO_STALE`
- effective BBO age `1305332.18ms`
- next blocker `P0-BOUNDED-PROBE-BBO-FRESHNESS-COLOCATED-RUNNER-RUNTIME-REVIEW-DEMO-ONLY`

## Review Chain

- PA/E1 initial: FAIL. Found incomplete boundary coverage for cancel/modify/config/env/crontab/risk/freshness mutation fields.
- E2/E4 initial: FAIL. Found enum authority fail-open, supplied-market gate closure, CLI mode ambiguity, and PG output reconstructability gap.
- PM fixes: expanded danger keys, enum authority rejection, supplied smoke status, required CLI mode, required PG output, and focused regressions.
- PA/E1 final: PASS.
- E2/E4 second: FAIL. Found local alias gap for `order_cancel_modify_performed` and `runtime_env_mutation_performed`.
- PM fixes: added aliases to runner and construction preview deny lists plus regressions.
- E2/E4 final: PASS.

## Verification

- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bbo_freshness_colocated_runner.py helper_scripts/research/tests/test_cost_gate_bounded_probe_candidate_construction_preview.py`: `30 passed`.
- Adjacent bounded-probe suite including runner: `100 passed`.
- `python3 -m py_compile ...`: passed.
- `git diff --check`: passed.

## Aggressive Profit Hypotheses

1. `runtime_pg_colocated_preview`
   - `why_it_might_make_money`: removes local copy/helper latency and may get AVAX under the 1000ms BBO freshness gate.
   - `fastest_safe_test`: PM->E3 runtime review to sync/run helper in `--pg-readonly` mode and emit market snapshot + runner artifacts.
   - `required_data`: repair proposal, reroute review, read-only PG ticker/instrument rows, market snapshot output hash, runner packet hash.
   - `failure_condition`: BBO age still > 1000ms or runtime sync/review not approved.
   - `authority_required`: PM->E3 for runtime source sync/run; no Bybit/order authority.
   - `max_safe_next_action`: `P0-BOUNDED-PROBE-BBO-FRESHNESS-COLOCATED-RUNNER-RUNTIME-REVIEW-DEMO-ONLY`.

2. `public_quote_capture_after_runtime_pg_failure`
   - `why_it_might_make_money`: direct public market data may bypass PG lag and better match live order placement.
   - `fastest_safe_test`: E3/BB-reviewed public quote capture packet only after PG runner fails.
   - `required_data`: public quote timestamps, instrument filters, construction preview hash.
   - `failure_condition`: quote timing not reconstructable or requires private/order endpoint.
   - `authority_required`: PM->E3->BB before any exchange-facing call.
   - `max_safe_next_action`: keep as proposal-only fallback.

3. `bbo_lag_alpha_filter`
   - `why_it_might_make_money`: if stale periods correlate with poor fills, freshness can become an execution-quality alpha/risk filter.
   - `fastest_safe_test`: research-only BBO-lag bucket analysis against fills/markout.
   - `required_data`: ticker lag, fills, slippage, fees, markout.
   - `failure_condition`: no relationship between lag and net PnL after fees/slippage.
   - `authority_required`: none for research; QC/risk required before gate changes.
   - `max_safe_next_action`: no gate mutation.

## Status

`DONE_WITH_CONCERNS`.

The source design is implemented and reviewed. Runtime co-located PG execution remains the next checkpoint.
