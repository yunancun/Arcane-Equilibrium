# Dust / Edge / Scout Follow-through

Date: 2026-04-30
Owner: PM

## Scope

Operator asked to do the three immediately actionable items:

1. Dust residual runtime proof.
2. Post-deploy cutoff edge observation.
3. Scout heartbeat production caller wiring.

No live authorization, strategy parameter, risk parameter, or deploy/restart action was performed.

## Runtime Proof: Dust Full-close

Fact: Linux runtime was alive and source/runtime HEAD was `fa5ee46`.

Fact: DB query after the 2026-04-30 21:10 CEST runtime load found 8 Demo/LiveDemo orders with `trading.orders.qty = 0.0`; every one joined to a nonzero `trading.fills.qty`.

Key rows:

| Engine | Symbol | Order Strategy | Order Qty | Fill Qty | Fill Strategy | Exit Reason | Later Position Snapshot |
|---|---:|---|---:|---:|---|---|---|
| demo | APEUSDT | `risk_close:ipc_close_symbol` | 0.0 | 0.1 | `orphan_frozen` | `ipc_close_symbol` | false |
| live_demo | XAGUSDT | `risk_close:ipc_close_symbol` | 0.0 | 0.001 | `orphan_frozen` | `ipc_close_symbol` | false |

Inference: Bybit's full-position close form (`qty=0 + reduceOnly + closeOnTrigger`) is now proven on real Demo/LiveDemo close paths for below-minNotional residues. This does not imply historical dust disappears automatically; it means future full-close dispatch can close through exchange-side full-position semantics instead of stale explicit local qty.

## Cutoff Edge Observation

Cutoff used: 2026-04-30 21:10 CEST.

`[33] maker_fill_rate` cutoff slice:

| Metric | Value |
|---|---:|
| Entry fills | 15 |
| Maker-like fills | 6 / 15 = 40.0% |
| Avg fee | 4.13 bps |
| Fee drop | 39.0% |
| Limit rows | 6 |
| PostOnly rows | 6 |

By strategy:

| Strategy | n | Maker-like | Avg fee | Fee drop |
|---|---:|---:|---:|---:|
| ma_crossover | 6 | 50.0% | 4.02 bps | 42.4% |
| grid_trading | 5 | 40.0% | 4.42 bps | 30.9% |
| bb_breakout | 2 | 50.0% | 3.75 bps | 50.0% |
| orphan_frozen | 2 | 0.0% | 4.15 bps | 38.6% |

`[38] grid_trading_lifecycle_drift` cutoff slice:

| Engine | Lifecycles | p50 lifetime | Fee burn | Re-entry |
|---|---:|---:|---:|---:|
| demo | 1 | 13.71 min | 1.959 | 0 / 3 |
| live_demo | 1 | 12.96 min | 0.111 | 0 / 2 |

Verdict: insufficient sample for `[38]`; healthcheck minimum is 5 lifecycles per side. The rolling 24h `[38]` FAIL remains real, but it still mixes pre-cutoff data.

`[40] realized_edge_acceptance` cutoff slice:

- MLDE rows: 0.
- Verdict: no post-cutoff MLDE acceptance data yet.

PM conclusion: keep P0 observation active. Do not make an edge promotion/rejection decision from rolling windows alone while they still mix old samples.

## Scout Heartbeat Wiring

Changed:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring_scanner.py`
  - Empty ScoutWorker scans now call `ScoutAgent.record_scan()`.
  - Successful intel-producing ScoutWorker scans call `ScoutAgent.record_scan()` once after `produce_intel()`.

Added:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategy_wiring_scanner.py`
  - Hermetic fake MarketScanner / ScoutWorker / ScoutAgent tests.
  - Covers both top-opportunity and no-opportunity scan paths.

## Verification

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategy_wiring_scanner.py -q`
  - 2 passed.
- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_heartbeat_contract.py -q`
  - 36 passed.
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring_scanner.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategy_wiring_scanner.py`
  - Passed.

## Remaining

- Continue cutoff observation until `[33]`, `[38]`, and `[40]` have enough post-deploy sample.
- G1-04 final fee/R:R compute remains time-driven around 2026-05-01/02.
- This checkpoint did not deploy/restart Python API; source is ready for the next normal runtime reload.
