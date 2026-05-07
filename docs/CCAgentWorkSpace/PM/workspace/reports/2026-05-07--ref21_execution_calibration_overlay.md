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

## Reality Boundary

This is slippage/fee/role-share calibration from historical demo/live_demo
fills. It is not a historical order-book simulator and it does not infer maker
fill probability from fills alone. Until order-outcome samples are recorded and
modeled, maker fill probability remains explicitly unavailable and replay
retains S2/S1-limited confidence depending on available fill attribution.
