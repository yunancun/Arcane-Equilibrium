# MM Walk-Forward Failure Summary

## Conclusion

v277 adds a compact `walk_forward_feature_scorecard.failure_summary` and passes it into alpha-discovery MM detail. The diagnostic answers whether the existing PIT feature/filter family is failing only because the failure is hidden deep inside the full fill_sim report.

Runtime answer: no hidden near-ready filter exists in the current 2h fresh-L1 window. The walk-forward search evaluated 51 train-only-threshold candidates and found zero train sample-gated positives, zero holdout confirmations, and no current-fee promotion evidence.

## Runtime Evidence

- Production fill_sim report: `/tmp/openclaw/research/fillsim/fillsim_report.json`
- Report sha256: `b9bdeba681d6182de8eda32031e81320e6f628893aa65c5a645d334aa524a9ca`
- Generated at: `2026-06-20T16:43:37.514040+00:00`
- Data window: 120.0 minutes, 33 symbols, `l1_rows_post_filter=1756794`, `trades_rows=1602324`
- L1 freshness: `l1_max_ts=2026-06-20T16:43:26.177Z`, `l1_max_age_hours=0.003`

Walk-forward scorecard:

- `walk_forward_feature_scorecard.status=NO_WALK_FORWARD_FEATURE_TRAIN_POSITIVE`
- `failure_summary.status=NO_TRAIN_POSITIVE_CELL`
- Candidates evaluated: 51
- Train sample-gated positives: 0
- Holdout-confirmed candidates: 0
- Best train candidate: `quoted_half_spread_bps train_p75 AND side_book_imb train_p75`
  - train `n_fill_only=263`, `net_bps=-3.524`, fee shortfall `3.524bp`
  - holdout `n_fill_only=265`, `net_bps=-3.260`, fee shortfall `3.260bp`
- Best holdout candidate: `symbol == ADAUSDT`
  - train `n_fill_only=559`, `net_bps=-3.802`
  - holdout `n_fill_only=714`, `net_bps=-1.998`

Adjacent current-fee scorecards from the same report remain negative:

- `edge_scorecard.status=NO_POSITIVE_FILL_ONLY_CELL`; best fill-only cell is `LABUSDT` / `informed_skip`, `n=170`, `net_bps=-1.730`
- `horizon_scorecard.status=NO_HORIZON_POSITIVE_CELL`; 222 horizon cells, best also `LABUSDT` / 15s, `net_bps=-1.730`
- `conditional_feature_scorecard.status=NO_CONDITIONAL_FEATURE_POSITIVE_CELL`; best single-window condition `quoted_half_spread_bps_p90_ge`, `net_bps=-3.335`
- `maker_fee_sensitivity_scorecard.status=LOWER_FEE_SAMPLE_GATED_POSITIVE`; best break-even maker fee improved to `1.135bp/side`, but current `2.0bp/side` remains blocked
- History scorecard sha256 `a8752b9172cae3f82de5c0adc9caa06ae64c40374a56b5b5179c1d638e8f7579`: 3 valid windows, one date, current-fee positives 0, walk-forward holdout confirmations 0

## Runtime Passthrough

Manual MM verdict refresh wrote `/tmp/openclaw/logs/recorder_mm_verdict.log` status at `2026-06-20T16:50:41Z`, line sha256 `d8c43bde35ff8f11e622734dcb5b939b82ef155c2e6e84dffe323f2a26f9da87`. The status preserves the full walk-forward scorecard under `fillsim.walk_forward_feature_scorecard`.

Alpha discovery refreshed `/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json`, sha256 `3a834cad9e3ba3abbdc72014fab4b09dc2647046cfa232379a3d4f3172e787b3`, and now exposes `walk_forward_failure_summary` directly in the MM arm detail. The MM arm remains `CAPTURING`, `sample_count=16`, `artifacts_ready=false`, `ready_for_probe=0`.

## PM Read

This narrows the MM diagnosis. The current blocker is not merely:

- a bad 15s adverse-selection horizon;
- missing a simple spread / imbalance / OFI combo;
- a holdout-only reporting blind spot.

The current PIT feature family does not produce even a train-positive sample-gated current-fee cell in the latest fresh window. The next rational paths are:

- fee/rebate or VIP/market-maker business path, now quantified around `1.135bp/side` in this window but scale-gated;
- materially new signal families beyond the current spread/queue/OFI/BTC-lead filters;
- non-MM alpha lanes, especially Polymarket after sample gate or future Gate-B/FlashDip evidence.

No strategy, risk, order, or runtime behavior changed.

## Verification

- Mac focused tests: `48 passed`
- Linux focused tests: `48 passed`
- Mac and Linux `py_compile`: passed
- Mac and Linux cron shell syntax checks: passed
- Mac and Linux diff-check: passed
- Linux targeted metadata check: no `._*` / `.DS_Store`

Boundary: source/test/docs plus selective Linux source sync and `/tmp/openclaw` read-only research/status artifacts only. No PG table write, schema migration, Bybit private/signed/trading call, engine/API restart, credential/auth/risk/order/strategy mutation, or promotion proof.
