# Operator Checkpoint: AVAX Candidate Construction Preview

The AVAX reroute candidate is mathematically constructible under the current 10 USDT/order cap, but it is not ready for demo order admission because the market snapshot is stale.

Candidate:

- `grid_trading|AVAXUSDT|Sell`
- passive sell limit `6.045`
- rounded qty `1.6`
- rounded notional `9.672 USDT`
- min positive qty notional `0.6045 USDT`
- min notional `5.0 USDT`
- cap `10.0 USDT`

Runtime preview:

- `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_candidate_construction_preview_avax_sell_latest.json`
- sha256 `3d652a3a5f28433adf33944e1dcf63d6a7a05ab176f161efaba3569611237600`
- status `CANDIDATE_CONSTRUCTION_BBO_STALE`
- blocking gates `["bbo_freshness"]`
- reported BBO age `4791.161ms`
- effective BBO age at preview generation `1229558.906ms`
- max allowed BBO age `1000ms`

Boundary preserved: no Bybit order/cancel/modify, no PG write, no canonical plan/ledger mutation, no service/crontab/env mutation, no Rust writer, no Cost Gate lowering, no live/mainnet, and no promotion proof.

Verification: PA/E1 PASS, E2/E4 PASS, focused helper `15 passed`, adjacent bounded-probe suite `85 passed`, `py_compile` and `git diff --check` passed.

Next gate: `P0-BOUNDED-PROBE-REROUTE-FRESH-BBO-CONSTRUCTION-REFRESH-DEMO-ONLY`.
