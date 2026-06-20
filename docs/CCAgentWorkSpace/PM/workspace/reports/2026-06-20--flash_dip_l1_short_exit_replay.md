# 2026-06-20 -- FlashDip L1 Short-Exit Replay

## Scope

Follow-up to the v245 execution-realism artifact. The 2-day K6/N2/C3/nf0.5% path is blocked by recent intraday execution realism, but v245 still showed a research-only 240m short-exit signal. This checkpoint adds an L1/trades replay gate for that weaker hypothesis.

Hard boundary: read-only PG, local research artifact only, no strategy/risk/order/runtime mutation, no Bybit private/signed/trading call, no live/demo parameter change.

## Delivered

- Added `helper_scripts/research/tail_dislocation_meanrev/shallow_retune_l1_short_exit_replay.py`.
- Added focused tests in `helper_scripts/research/tests/test_tail_dislocation_shallow_retune.py`.
- Replay model:
  - deep passive maker buy rests from UTC day start;
  - adverse fill if trades/book sweep through the level;
  - queue fill when best bid touches the limit and same-side sell prints consume modeled queue ahead;
  - taker sell exit measured at 15/60/240m with maker-entry + taker-exit fees.
- Verdict now explicitly distinguishes L1 coverage holes from ordinary sample shortage via `l1_candidate_coverage` and `no_l1_rows_for_candidate_window`.

## Verification

- Mac: `PYTHONPATH=helper_scripts/research/tail_dislocation_meanrev python3 -m py_compile ...` PASS.
- Mac: `PYTHONPATH=helper_scripts/research/tail_dislocation_meanrev python3 -m pytest -q helper_scripts/research/tests/test_tail_dislocation_shallow_retune.py` = 11 passed.
- Linux `trade-core`: same py_compile PASS.
- Linux `trade-core`: same focused pytest = 11 passed.
- Linux read-only PG artifact:
  - `/tmp/openclaw/research/tail_dislocation_meanrev/shallow_retune_l1_short_exit_replay_20260620T023713Z.json`
  - sha256 `231d3c57ae8f8945e114a77b8e5b0f8688149ffae738e72c5c31b2ac47631be2`

## Result

- Verdict: `L1_SHORT_EXIT_INSUFFICIENT_SAMPLE`.
- Fail reasons: `no_l1_rows_for_candidate_window`, `gate_horizon_sample_below_min_filled`, `gate_horizon_sample_below_min_days`.
- Candidate overlap: 3 events / 1 day / `APTUSDT`, `ATOMUSDT`, `AVAXUSDT`.
- Candidate window: 2026-06-18 00:00:00Z to 2026-06-19 04:00:00Z.
- Trades loaded: 608,227 rows across the 3 symbols.
- L1 loaded: 0 rows across the 3 symbols.
- Queue fractions 0.0 / 0.5 / 1.0: 0 filled, 0 exit measured.

## PM Read

This does not kill the short-exit alpha. The current replay cannot evaluate L1/queue survival because recorder-v2 has no L1 rows for the actual candidate day/symbols, while trade prints exist in the same window.

The immediate conclusion is data-gated: keep K6/N2/C3/nf0.5% blocked for any live/demo 2-day retune, and keep the short-exit path as research-only pending a future K6-style candidate with continuous L1 coverage or an explicitly instrumented capture window.
