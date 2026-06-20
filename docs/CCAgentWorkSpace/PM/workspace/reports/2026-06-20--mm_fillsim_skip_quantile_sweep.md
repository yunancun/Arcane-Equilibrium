# MM FillSim Skip-Quantile Sweep

Date: 2026-06-20

## Summary

Ran an isolated read-only sweep over the existing fill-sim `skip_quantile` knob to test whether more aggressive informed-skip filtering can lift maker fill-only edge over fees on the current fresh L1 slice.

It did not produce a sample-gated positive cell.

## Setup

- Runtime: Linux `trade-core`
- Scope: read-only PG plus local artifacts only
- Window: latest 15 minutes via `--hours 0.25`
- Min L1 events: 50
- Output paths: `/tmp/openclaw/research/fillsim/fillsim_scorecard_q*.json`
- Production fill_sim report replacement: no

## Results

| skip_quantile | Best symbol | Policy | n | Net after maker RT fee | Status |
|---:|---|---|---:|---:|---|
| 0.00 | BSBUSDT | naive | 35 | -1.480bp | `NO_POSITIVE_FILL_ONLY_CELL` |
| 0.10 | ADAUSDT | informed-skip | 125 | -1.276bp | `NO_POSITIVE_FILL_ONLY_CELL` |
| 0.20 | ADAUSDT | informed-skip | 109 | -1.214bp | `NO_POSITIVE_FILL_ONLY_CELL` |
| 0.30 | BEATUSDT | informed-skip | 2 | +17.364bp | `POSITIVE_FILL_ONLY_CELL_BELOW_SAMPLE_GATE` |

All four runs had `positive_sample_gate_count=0`.

## Interpretation

The current OFI/BTC-lead informed-skip filter helps only marginally in this slice. More aggressive skipping can manufacture a nominal positive cell, but it collapses sample size to n=2 and must be treated as an overfit hint.

The maker path remains worth pursuing because it is the only current lens that can invert fee sign, but the next useful work is a stronger conditional filter or more regime-day evidence, not a demo/live strategy change.

## Boundary

No source change in this evidence checkpoint, no production artifact replacement, no engine/API restart, no rebuild, no strategy parameter change, no PG table write/schema migration, no Bybit private/signed/trading call, and no credential/auth/risk/order/trading mutation.
