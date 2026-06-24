# Operator Checkpoint: Bounded Probe Order Construction Repair

Current BTC bounded candidate `ma_crossover|BTCUSDT|Sell` passed no-order admission dry-run, but order construction is still blocked:

- BBO age `1652ms` exceeds the 1000ms freshness gate.
- BTCUSDT minimum positive qty at the preview limit is `60.0402 USDT`.
- Current bounded Demo cap is `10 USDT/order`.

I added a source-only repair helper and generated:

- `/tmp/openclaw/cost_gate_learning_lane/candidate_universe_instrument_screen_false_negative_latest.json`
- `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_order_construction_repair_latest.json`

Latest repair packet status is `ORDER_CONSTRUCTION_REPAIR_REQUIRED`, sha256 `5a5940cf7b1a54ec80a188527fe36695a26454f0b4b14a7fa8e9027a0fda9040`.

Key result: do not raise BTC cap as the first move. A read-only screen found 9 false-negative candidates that already fit the 10 USDT cap. Top candidate is `grid_trading|AVAXUSDT|Sell`, false-negative rank 1, avg net `73.5511bps`, 48/48 net-positive 60m outcomes, minimum executable notional `5.0 USDT`.

Boundary preserved: no Bybit order/cancel/modify, no PG write, no canonical plan mutation, no ledger append, no service/crontab/env mutation, no Rust writer, no Cost Gate lowering, no live/mainnet, and no promotion proof.

Verification: PA/E1 PASS, E2/E4 PASS, focused helper `11 passed`, adjacent bounded-probe suite `42 passed`, `py_compile` and `git diff --check` passed.

Next gate: `P0-BOUNDED-PROBE-LOWER-PRICE-CANDIDATE-REROUTE-REVIEW-DEMO-ONLY`.
