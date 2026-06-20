# 2026-06-20 FillSim Cost-Wall Instrumentation

## Summary

PM-local source/test/runtime diagnostic checkpoint. The L1 recorder was fresh again, so the next question was whether the market-making loss was a stale-data artifact, a queue-position artifact, or a real fee/adverse-selection cost wall.

Result: current-regime MM remains structurally below break-even. Even the optimistic front-of-queue fill-only read needs maker rebate to break even.

## Source Change

- `program_code/research/microstructure/fill_sim.py`
  - Added `MAKER_FEE_ROUND_TRIP_BPS`.
  - Every `_net_block` now emits:
    - `edge_before_fees_bps@h`
    - `break_even_fee_round_trip_bps@h_maker_exit`
    - `break_even_maker_fee_bps_per_side@h_maker_exit`
    - `fee_round_trip_shortfall_bps@h_maker_exit`
    - `required_half_spread_bps@h_maker_exit`
    - `required_maker_rebate_bps_per_side@h_maker_exit`
  - Report params now include a `cost_wall_definition`.
- `program_code/research/tests/test_fill_sim_cost_wall.py`
  - Covers normal negative edge, negative break-even fee requiring rebate, and empty-sample `None` output.

## Verification

- Mac:
  - `python3 -m py_compile program_code/research/microstructure/fill_sim.py`
  - `python3 -m pytest -q program_code/research/tests/test_fill_sim_cost_wall.py` -> 3 passed
  - targeted `git diff --check` clean
- trade-core:
  - selective script copy only, no engine/API restart
  - `python3 -m py_compile program_code/research/microstructure/fill_sim.py`
  - temp smoke artifact only: `/tmp/openclaw/research/fillsim/fillsim_cost_wall_smoke_20260620T003611Z.json`

## Runtime Evidence

Fresh L1 smoke window:

- since: `2026-06-20 02:21:10.404000+02:00`
- `l1_rows_post_filter=194305`
- `crossed_after_filter=0`
- `l1_max_age_hours=0.001`
- `n_symbols=36`
- obtop cross-check median abs discrepancy: `0.922bp`

Key 15s fill-only reads:

| Queue/policy | n | half spread | adverse@15 | edge before fees | net maker@15 | break-even fee RT | required rebate/side | required half spread |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| back naive | 2592 | 0.841bp | 2.206bp | -1.365bp | -5.365bp | -1.365bp | 0.682bp | 6.206bp |
| front naive | 4285 | 0.835bp | 1.631bp | -0.796bp | -4.796bp | -0.796bp | 0.398bp | 5.631bp |
| back informed-skip | 2140 | 0.835bp | 2.082bp | -1.247bp | -5.247bp | -1.247bp | 0.623bp | 6.082bp |

Interpretation: queue position helps but does not flip sign. In this window adverse selection alone exceeds captured half-spread before fees; after the current 4bp maker round trip, the shortfall is about 4.8-5.4bp/fill. A zero-fee venue would still not be enough in these rows; the report now states the rebate/spread condition required.

## Boundary

No production report overwrite, no engine/API restart, no PG table write, no schema migration, no Bybit private/signed/trading call, no credential/auth/risk/order/trading mutation.

This is a single-regime smoke, not CP-3 go/no-go or promotion proof. The actionable change is that future fill_sim artifacts now expose the fee/spread/rebate requirement directly, so profitability discussions cannot hide behind raw net values.

## Follow-up: MM Verdict Bridge

Daily `recorder_mm_verdict_cron.sh` now carries the same break-even lens into live MM status, using true maker markout-derived spread capture plus fill_sim adverse selection:

- per-symbol `edge_before_fees_bps`
- `break_even_fee_round_trip_bps`
- `break_even_maker_fee_bps_per_side`
- `fee_round_trip_shortfall_bps`
- `required_spread_captured_bps`
- `required_maker_rebate_bps_per_side`
- top-level `cost_wall_summary`

`runtime_runner.py` preserves `cost_wall_summary` in alpha discovery `arms_raw` detail. The stable `discovery_plan` schema and positive-edge gates are unchanged.

Focused verification:

- `bash -n helper_scripts/cron/recorder_mm_verdict_cron.sh`
- `python3 -m pytest -q helper_scripts/cron/tests/test_fill_sim_refresh_cron_static.py` -> 11 passed
- `python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_throughput.py` -> 10 passed
- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`

Linux selective deploy/smoke:

- `origin/main=31c46bf9` restored to trade-core touched files; checkout HEAD remains old `bb06ae1b` due existing selective-deploy dirty state.
- Linux focused tests passed when run separately: cron static 11, alpha discovery runtime 10, fill_sim cost wall 3.
- Manual read-only `recorder_mm_verdict_cron.sh` emitted status `2026-06-20T00:45:49Z` with `cost_wall_summary.available=true`.
- Best live MM row: `ARBUSDT` net `-0.1437bp`, fee shortfall `0.1437bp`, required rebate `0.0`, but `n_maker_fills=1` and therefore below gate.
- BTC/ETH sample rows still require rebate.
