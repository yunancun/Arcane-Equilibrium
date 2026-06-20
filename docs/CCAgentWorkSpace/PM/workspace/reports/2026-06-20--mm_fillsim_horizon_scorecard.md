# MM FillSim Horizon Scorecard

## Conclusion

v276 adds a diagnostic-only `horizon_scorecard` to fill_sim, MM verdict status, and alpha-discovery MM detail. It answers one narrow blocker question: whether the current maker cost wall is just an artifact of using the 15s adverse-selection horizon.

Runtime answer: no. In the latest fresh-L1 2h fill_sim refresh, every current-fee fill-only cell remains negative across 5s, 15s, and 30s horizons.

## Runtime Evidence

- Production fill_sim report: `/tmp/openclaw/research/fillsim/fillsim_report.json`
- Report sha256: `bbc92040206c2f50fe3d9fa6556d1aa6737b4c316cb45d6f935220fa06c36647`
- Generated at: `2026-06-20T16:25:56.271973+00:00`
- Data window: 120.0 minutes, 33 symbols, `l1_rows_post_filter=1749143`, `trades_rows=1562327`
- L1 freshness: `l1_max_ts=2026-06-20T16:25:44.186Z`, `l1_max_age_hours=0.003`

`horizon_scorecard`:

- Status: `NO_HORIZON_POSITIVE_CELL`
- Horizons: `[5, 15, 30]`
- Cells evaluated: 222
- Best overall: `ADAUSDT` / `informed_skip` / `back` / `5s`, `n=926`, `net_bps=-2.444`
- Best by horizon:
  - 5s: `ADAUSDT` / `informed_skip`, `net_bps=-2.444`
  - 15s: `ADAUSDT` / `informed_skip`, `net_bps=-2.588`
  - 30s: `ADAUSDT` / `informed_skip`, `net_bps=-2.485`
- Sample-gated positive cells: none

Adjacent scorecards from the same report:

- `edge_scorecard.status=NO_POSITIVE_FILL_ONLY_CELL`; best fill-only cell is `ADAUSDT` / `informed_skip` / 15s, `n=926`, `net_bps=-2.588`
- `conditional_feature_scorecard.status=NO_CONDITIONAL_FEATURE_POSITIVE_CELL`; best current-fee conditional cell `quoted_half_spread_bps_p90_ge`, `net_bps=-3.306`
- `walk_forward_feature_scorecard.status=NO_WALK_FORWARD_FEATURE_TRAIN_POSITIVE`; best train cell `BTWUSDT`, train `-1.841bp`, holdout `-5.442bp`
- `maker_fee_sensitivity_scorecard.status=LOWER_FEE_SAMPLE_GATED_POSITIVE`; current-fee positives remain zero, while the best sample-gated break-even maker fee is `0.706bp/side`
- `fillsim_history_scorecard.status=HISTORY_INSUFFICIENT_WINDOWS`; two valid windows on one date, current-fee historical positives zero

## Runtime Passthrough

Manual MM verdict refresh wrote `/tmp/openclaw/logs/recorder_mm_verdict.log` status at `2026-06-20T16:32:36Z` with line sha256 `82fc3dd6cd55aa0065cea20f35848526a9f92e11a30eff93363438753355a4c7`. The status now preserves `fillsim.horizon_scorecard`.

Alpha discovery refreshed `/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json` with sha256 `f6915d61bbdf2a9067655b5134f35c46e59dc610d6936601d69c1481d402abee`. The MM arm remains `CAPTURING`, `sample_count=16`, `ready_for_probe=0`, and its detail now includes the same `horizon_scorecard`.

## PM Read

The MM blocker is not a 15s horizon artifact. With the current fee path, even the best measured 5s/15s/30s fill-only cell is still below breakeven. The current evidence says any profitable maker path needs at least one of:

- materially stronger queue/filter signal than the current fill-only and conditional reducers find;
- a much lower maker fee or rebate path around the measured break-even band, with cross-window confirmation;
- a non-MM alpha lane that clears cost and robustness gates.

This is not promotion evidence and does not authorize a strategy, risk, order, or runtime change.

## Verification

- Mac focused tests: `48 passed`
- Linux focused tests: `48 passed`
- Mac and Linux `py_compile`: passed
- Mac and Linux cron shell syntax checks: passed
- Linux targeted `git diff --check`: passed

Boundary: source/test/docs plus selective Linux source sync and `/tmp/openclaw` read-only research/status artifacts only. No PG table write, schema migration, Bybit private/signed/trading call, engine/API restart, credential/auth/risk/order/strategy mutation, or promotion proof.
