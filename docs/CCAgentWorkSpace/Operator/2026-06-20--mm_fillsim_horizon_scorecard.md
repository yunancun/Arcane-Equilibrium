# Operator Note: MM FillSim Horizon Scorecard

v276 adds diagnostic-only MM `horizon_scorecard` passthrough from fill_sim into recorder MM verdict and alpha discovery. No operator action is requested.

Latest trade-core fresh-L1 2h refresh:

- fill_sim report sha256 `bbc92040206c2f50fe3d9fa6556d1aa6737b4c316cb45d6f935220fa06c36647`
- `horizon_scorecard.status=NO_HORIZON_POSITIVE_CELL`
- 222 fill-only horizon cells evaluated over 5s/15s/30s
- Best cell: `ADAUSDT` / `informed_skip` / `back` / 5s, `n=926`, `net_bps=-2.444`
- 15s best remains `-2.588bp`; 30s best remains `-2.485bp`
- Current-fee sample-gated positives: zero

Read: the current MM cost wall is not explained away by changing the adverse-selection horizon. Fee sensitivity still shows a lower-fee path can become positive in-sample, but current standard fee remains blocked and needs cross-window proof before any promotion chain.

Boundary: no live/demo parameter change, no risk/order/auth mutation, no engine restart, no Bybit private call, no PG write.
