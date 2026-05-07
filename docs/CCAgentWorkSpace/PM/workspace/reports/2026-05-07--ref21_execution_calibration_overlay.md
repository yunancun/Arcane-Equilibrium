# REF-21 Execution Calibration Overlay

## Scope

This checkpoint adds a replay-only execution calibration overlay for one-click
full-chain replay. It does not mutate live/demo risk settings and does not move
strategy, risk, scanner, or execution decisions into the Control API process.
The dedicated Rust `replay_runner` subprocess remains the replay execution
path.

## Implemented

- Added `app/replay_execution_calibration.py`.
  - Reads `trading.fills` as-of the replay window start, using only
    `demo` / `live_demo` rows from the prior 30 days.
  - Computes role shares, adverse slippage q10/q50/q90, fee-rate q50, sample
    count, latest-fill freshness, and confidence tier.
  - Uses `S1_CALIBRATED` only for >=200 fresh slippage samples, `S1_LIMITED`
    for >=30 fresh samples, and otherwise `S2_CONSERVATIVE_BOUND`.
  - Applies a replay-only slippage floor to copied `risk_overrides.slippage`
    and every slippage tier, capped to the Rust `RiskConfig` 100 bps maximum.
  - Marks maker fill probability as unavailable when only fills are present,
    avoiding a false maker-fill-quality claim without order-outcome samples.
- Wired full-chain replay preparation to embed `execution_calibration` in:
  - API response,
  - V049 manifest JSON,
  - input-fidelity summary,
  - replay-only `risk_overrides`.
- Updated the Replay tab one-click summary to show the execution calibration
  verdict and slippage floor as a first-class trust qualifier.

## Verification

- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_execution_calibration.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_full_chain_routes.py`
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_run_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/static/test_replay_subtab_static_assets.py -q`
  - 52 passed.
- `git diff --check`

## Linux Runtime

- Mac/origin checkpoint: `7878aa4a`.
- Linux `trade-core` fast-forwarded from `c0544787` to `7878aa4a`.
- Linux verification:
  - `python3 -m py_compile ...` passed.
  - Targeted replay pytest suite passed: 61 passed / 1 skipped.
  - `cargo build --release -p openclaw_engine --bin replay_runner --features replay_isolated --manifest-path rust/Cargo.toml` passed with pre-existing warnings.
- Applied `V063__market_tickers_funding_rate_for_replay.sql`; verified
  `market.market_tickers.funding_rate` exists.
- API reloaded with `bash helper_scripts/restart_all.sh --api-only --keep-auth`;
  new API parent PID: `2437376`.
- Route/static proof:
  - local source contains `Exec Cal / 執行校準` in `app-paper.js`.
  - `GET /api/v1/replay/full-chain/run` returns 405 Method Not Allowed,
    proving the route is loaded in the reloaded API process.

## Reality Boundary

This is slippage/fee/role-share calibration from historical demo/live_demo
fills. It is not a historical order-book simulator and it does not infer maker
fill probability from fills alone. Until order-outcome samples are recorded and
modeled, maker fill probability remains explicitly unavailable and replay
retains S2/S1-limited confidence depending on available fill attribution.

## Follow-Up Checkpoint: Maker Outcome Calibration

- Added PostOnly order-outcome calibration from
  `trading.orders` + `trading.order_state_changes` using the same 30-day
  as-of window and `demo` / `live_demo` mode scope.
- Added maker outcome fields:
  `maker_order_sample_count`, observed any/full fill probability, rejection /
  cancellation / post-only-cross counts, confidence tier, and
  `recommended_maker_fill_probability_cap`.
- Kept the default maker cap conservative at `0.40` when order outcomes are
  missing or insufficient; observed caps are also clamped to `<= 0.40`.
- Wired the signed replay manifest so the dedicated Rust `replay_runner`
  consumes `execution_calibration.recommended_maker_fill_probability_cap`.
  Risk-accepted PostOnly attempts that do not pass the deterministic cap are
  recorded as qty=0 maker-miss ghost rows instead of being over-claimed as
  immediate maker fills.
- Replay GUI now shows a separate `Maker Fill / Maker成交` trust cell, with
  sample count in the tooltip.

Verification:

- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_execution_calibration.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_full_chain_routes.py`
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_run_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/static/test_replay_subtab_static_assets.py -q`
  - 53 passed.
- `cargo test -p openclaw_engine replay::runner::tests::test_apply_fill_postonly_calibration_cap_records_maker_miss --features replay_isolated`
- `cargo build --release -p openclaw_engine --bin replay_runner --features replay_isolated`
- `git diff --check`

## Follow-Up Checkpoint: BBO-Anchored Taker Pricing

- Added Wave C1 taker reference-price anchoring in Rust replay fills.
  - Market/taker buy reference price cannot be better than fixture best ask
    when valid BBO exists.
  - Market/taker sell reference price cannot be better than fixture best bid
    when valid BBO exists.
  - Existing replay slippage floors still apply on top of the BBO anchor.
  - Missing, crossed, or invalid BBO keeps the previous reference-price path,
    preserving legacy fixture behavior without fabricating microstructure.
- Kept PostOnly maker pricing on the existing limit-price / maker-cap path.
- Applied the same BBO anchor to rejected taker counterfactual ghost fills so
  risk-decision audit rows use the same execution-quality boundary.

Verification:

- `cargo test -p openclaw_engine test_apply_fill_bbo_anchor_bounds_taker_reference_price --features replay_isolated`
- `cargo test -p openclaw_engine test_apply_fill_taker_open_uses_bbo_anchor_when_present --features replay_isolated`
- `cargo build --release -p openclaw_engine --bin replay_runner --features replay_isolated`
- `git diff --check`

Reality boundary:

- This closes the obvious "taker fill better than observed BBO" overclaim when
  local BBO exists.
- It does not create historical BBO/orderbook data for old windows.
- Partial fills, depth-aware sizing, and latency modeling remain Wave C1
  follow-up items before any S1-calibrated execution claim.
