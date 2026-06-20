# MM FillSim Edge Scorecard

Date: 2026-06-20

## Summary

Added a compact `edge_scorecard` to the fill-sim report so the maker path can be evaluated by nearest-to-breakeven conditional cells instead of reading nested pooled/per-symbol/queue-dose blocks by hand.

This does not create promotion proof. The latest isolated smoke still shows no positive fill-sim maker cell after fees.

## Changes

- `program_code/research/microstructure/fill_sim.py`
  - Added `fill_sim_edge_scorecard()`.
  - Ranks fill_only maker-edge cells across:
    - pooled primary queue
    - pooled queue-dose positions
    - per-symbol primary queue
    - `naive` and `informed_skip` policies
  - Reports best cell, best back-of-queue cell, positive cells, sample-gated positive cells, and nearest-to-breakeven cells.
- `helper_scripts/cron/recorder_mm_verdict_cron.sh`
  - Passes `fillsim.edge_scorecard` through the MM verdict status.
  - Adds `best_n_maker_fills` to `cost_wall_summary`.
- Focused tests pin the scorecard reducer and cron status fields.

## Runtime Evidence

Direct Linux read-only fill-sim smoke:

- Artifact: `/tmp/openclaw/research/fillsim/fillsim_scorecard_smoke_20260620T090830Z.json`
- Production report replacement: no
- Window: 15 minutes
- L1 rows: 142,881
- Trades: 86,471
- Symbols: 34
- L1 max age: 0.0h
- Scorecard status: `NO_POSITIVE_FILL_ONLY_CELL`

Best fill-sim cell:

- Symbol: ADAUSDT
- Queue: back-of-queue
- Policy: informed-skip
- Track: fill_only
- n: 121
- Half-spread: 3.070bp
- Adverse selection @15s: 0.152bp
- Edge before fees: 2.918bp
- Net after 4bp maker round-trip fee: -1.082bp

Isolated MM verdict wrapper smoke:

- Data dir: `/tmp/openclaw_mm_scorecard_smoke2`
- FillSim report source: the isolated scorecard smoke artifact above
- Cost-wall best symbol: ARBUSDT
- Best live-markout net: +0.1213bp
- `best_n_maker_fills`: 1
- Interpretation: positive live-markout estimate is below the 30-fill sample gate and is not actionable.

## Verification

- Mac: `program_code/research/tests/test_fill_sim_cost_wall.py` = 5 passed.
- Mac: `helper_scripts/cron/tests/test_fill_sim_refresh_cron_static.py` = 11 passed; `recorder_mm_verdict_cron.sh` bash syntax PASS.
- Mac: fill_sim py_compile PASS; diff-check clean.
- Linux: same focused tests/py_compile PASS after selective sync.
- Linux: isolated direct fill-sim smoke PASS.
- Linux: isolated MM verdict wrapper smoke PASS.

## Interpretation

The maker path remains the closest plausible path because it can flip the fee sign, but current measured fill-sim cells still do not clear fees. The most useful next research is not a generic parameter retune; it is to discover whether a defensible conditional filter can lift back-of-queue fill_only edge by at least ~1.1bp without losing sample robustness.

## Boundary

No engine/API restart, no rebuild, no strategy parameter change, no production fill_sim replacement, no PG table write/schema migration, no Bybit private/signed/trading call, and no credential/auth/risk/order/trading mutation.
