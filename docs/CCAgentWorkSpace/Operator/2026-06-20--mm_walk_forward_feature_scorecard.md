# MM Walk-Forward Feature Scorecard

Date: 2026-06-20
Owner: PM-local focused monitor/reducer pass
Scope: read-only research instrumentation; not a promotion verdict

## Verdict

The current simple PIT maker feature set does **not** contain a stable short-term edge under current fees.

v251/v252 showed that in-window spread/imbalance/OFI filters can get near the maker cost wall only under lower fees. v254 adds a stricter check: candidate thresholds are selected on the first time half and replayed on the second time half. This prevents the most direct single-window threshold peeking.

Linux isolated 15m smoke result:

| Metric | Value |
|---|---:|
| L1 rows post-filter | 139,391 |
| trades | 76,079 |
| symbols | 33 |
| crossed rows after filter | 0 |
| walk-forward candidates | 51 |
| train quotes | 5,942 |
| holdout quotes | 5,942 |

Scorecard status: `NO_WALK_FORWARD_FEATURE_TRAIN_POSITIVE`

Best train candidate was still negative:

| Candidate | Train n | Train net | Holdout n | Holdout net |
|---|---:|---:|---:|---:|
| `symbol=BCHUSDT` | 106 | -2.061 bps | 79 | -1.429 bps |

Read: more in-window hand-picked conditions over the same simple PIT fields are unlikely to produce the missing current-fee maker edge. The next useful work should target a materially new signal, longer multi-regime evidence, or a non-MM path.

## Evidence

- Artifact: `/tmp/openclaw/research/fillsim/fillsim_walk_forward_smoke_20260620T100549Z.json`
- Artifact sha256: `091eb93d6f653aa605941274134beff8d5a041c85b9577bc245636559c2364c2`
- `conditional_feature_scorecard.status`: `NO_CONDITIONAL_FEATURE_POSITIVE_CELL`
- `walk_forward_feature_scorecard.status`: `NO_WALK_FORWARD_FEATURE_TRAIN_POSITIVE`
- `maker_fee_sensitivity_scorecard.status`: `LOWER_FEE_SAMPLE_GATED_POSITIVE`
- Fresh-slice lower-fee best break-even cell: ADAUSDT per-symbol in-window edge scorecard, break-even `1.22bp/side`

The last bullet is intentionally not a promotion proof: it is in-window/per-symbol and not walk-forward-confirmed.

## Implementation

Updated `program_code/research/microstructure/fill_sim.py`:

- Added `fill_sim_walk_forward_feature_scorecard()`.
- Split quote trials by placement time: first half train, second half holdout.
- Candidate thresholds are learned only on train.
- Candidate set covers `side`, top train symbols, `quoted_half_spread_bps`, `q0`, `q_eff`, `side_book_imb`, `side_signal_ofi10`, `side_signal_btc_lead`, and a small high-spread combo set.
- Status is holdout-positive only when train and holdout are both sample-gated positive.
- `maker_fee_sensitivity_scorecard` includes walk-forward cells only when they are holdout-confirmed.
- CLI human summary now prints `walk_forward_feature_scorecard`.

Updated `helper_scripts/cron/recorder_mm_verdict_cron.sh`:

- Preserves `walk_forward_feature_scorecard` under `fillsim` in MM verdict status.

## Validation

Mac:

- `python3 -m pytest -q program_code/research/tests/test_fill_sim_cost_wall.py program_code/research/tests/test_mm_fee_path_feasibility.py helper_scripts/cron/tests/test_fill_sim_refresh_cron_static.py` -> 29 passed
- `python3 -m py_compile program_code/research/microstructure/fill_sim.py program_code/research/microstructure/fee_path.py`
- `bash -n helper_scripts/cron/recorder_mm_verdict_cron.sh`
- focused `git diff --check` clean

Linux `trade-core`:

- focused tests passed 29/29 before final summary patch and 26/26 after final sync
- fill_sim py_compile passed
- recorder MM `bash -n` passed
- focused diff-check clean
- isolated read-only fill_sim smoke generated the artifact above

## Boundary

No production fill_sim replacement, no engine/API restart, no rebuild, no strategy parameter change, no PG table write/schema migration, no Bybit private/signed/trading call, no credential/auth/risk/order/trading mutation. This is not promotion proof.
