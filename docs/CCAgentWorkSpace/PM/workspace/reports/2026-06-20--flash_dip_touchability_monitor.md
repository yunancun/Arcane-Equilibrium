# 2026-06-20 FlashDip Touchability Monitor

## Verdict

FlashDip current zero-profit / zero-fill behavior is now empirically separated from a fill-path failure: the runtime is arming intended deep-K maker limits, but recent orders did not touch their intended limit before timeout.

Linux read-only smoke over the last 72h produced:

- `order_labeled_count=19`
- `true_order_count=18`
- `strategy_mismatch_count=1`
- `missing_limit_count=0`
- `touched_count=0`
- `touch_rate_pct=0.0`
- `median_ref_to_limit_bps=1667.54`
- `median_closest_miss_bps=1595.84`
- `min_closest_miss_bps=1030.33`
- `max_closest_miss_bps=1762.67`
- `latest_order_ts=2026-06-20T02:00:00+02`

One flash-labeled row was not true FlashDip after intent join:

- `POLUSDT`, `order_id=oc_dm_1781892403054_12`, `intent_strategy=grid_trading`

## K-Ladder Addendum

The touchability status now includes a counterfactual K ladder. It infers the current prior close from the current live limit and `OPENCLAW_FLASH_DIP_CURRENT_K_PCT` (default `15`), then evaluates candidate limits for `OPENCLAW_FLASH_DIP_TOUCH_K_PCTS` (default `0,1,2,3,4,5,6,8,10,12,15`) against the same 1m min-low window.

Linux isolated smoke at `/tmp/openclaw_flash_touch_ladder_smoke_20260620T013444Z` produced this 72h ladder:

| K pct | touched / true orders | touch rate | median closest miss bps |
|---:|---:|---:|---:|
| 0 | 18 / 18 | 100.0000% | -143.53 |
| 1 | 14 / 18 | 77.7778% | -43.97 |
| 2 | 4 / 18 | 22.2222% | 57.62 |
| 3 | 3 / 18 | 16.6667% | 161.31 |
| 4 | 2 / 18 | 11.1111% | 267.15 |
| 5 | 2 / 18 | 11.1111% | 375.23 |
| 6 | 1 / 18 | 5.5556% | 485.60 |
| 8 | 0 / 18 | 0.0000% | 713.55 |
| 10 | 0 / 18 | 0.0000% | 951.63 |
| 12 | 0 / 18 | 0.0000% | 1200.53 |
| 15 | 0 / 18 | 0.0000% | 1595.84 |

Read: K8-K15 are still no-touch in this quiet window. K1 would have touched most rows, but that is a different, much less tail-dislocation-like strategy. K2-K6 provide the useful exploration band to monitor before any strategy retune proposal.

## Implementation

Added `helper_scripts/cron/flash_dip_touchability_cron.sh`.

The cron is a read-only PG diagnostic:

- Reads recent `trading.orders` rows labeled `flash_dip_buy`.
- Joins `trading.intents` and counts true FlashDip only when joined intent strategy is `flash_dip_buy` and `details.limit_price` exists.
- Uses `market.klines` 1m lows from order timestamp to maker timeout/current time to determine whether the intended limit was touched.
- Emits `k_ladder` counterfactual touchability for candidate K values without changing any live strategy parameter.
- Writes only local artifacts: `logs/flash_dip_touchability_cron.log`, `logs/flash_dip_touchability.log`, heartbeat, and lock files.
- Enforces `PGOPTIONS="-c default_transaction_read_only=on"`.

Updated `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py` so FlashDip killboard detail reads `logs/flash_dip_touchability.log`. When death-rate remains `n_closed_slots=0` but fresh touchability shows true FlashDip orders and zero touches, the arm reports `CAPTURING_NO_TOUCH` rather than plain `CAPTURING`.

## Verification

- `bash -n helper_scripts/cron/flash_dip_touchability_cron.sh` PASS
- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/runtime_runner.py` PASS
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_throughput.py` = 13 passed
- Linux isolated smoke: piped cron script to `trade-core` with `OPENCLAW_DATA_DIR=/tmp/openclaw_flash_touch_smoke_20260620T012509Z`; it wrote only isolated `/tmp` logs/status and produced the evidence above.
- Linux isolated ladder smoke: piped the expanded cron script to `trade-core` with `OPENCLAW_DATA_DIR=/tmp/openclaw_flash_touch_ladder_smoke_20260620T013444Z`; it wrote only isolated `/tmp` logs/status and produced the K-ladder table above.
- Linux selective deploy: restored the touched helper/runtime/docs files from `origin/main` to `trade-core`, preserving the existing selective-deploy dirty checkout shape.
- Linux focused checks after restore: cron `bash -n` PASS, runtime runner `py_compile` PASS, alpha discovery focused tests 13 passed.
- Runtime activation: installed hourly user cron `17 * * * * ... flash_dip_touchability_cron.sh`, then manually ran it once against production `/tmp/openclaw`; status line at `2026-06-20T01:28:59Z` matched the evidence above.
- Alpha discovery activation check: manual `alpha_discovery_throughput_cron.sh` refresh at `2026-06-20T01:29:10Z` reported FlashDip `gate_status=CAPTURING_NO_TOUCH`, action `RUN_READ_ONLY_CAPTURE`, and fresh touchability `age_seconds=11.306709`.
- K-ladder activation check: after selective deploy of the ladder extension, manual production touchability run at `2026-06-20T01:36:52Z` wrote `deepest_candidate_k_with_touch_pct=6` and `k_ladder_len=11`; manual alpha discovery refresh at `2026-06-20T01:37:02Z` preserved `CAPTURING_NO_TOUCH` and exposed K2 `4/18` vs K8 `0/18` in `arms_raw.detail.touchability.k_ladder`.

## Boundary

Selective helper/docs deploy + user crontab + local `/tmp/openclaw` log/artifact writes only. No engine/API restart, no rebuild, no strategy flag change, no Bybit private/signed/trading call, no credential/auth/risk/order mutation, no PG table write/schema migration. This is not promotion proof; it is a repeatable no-touch diagnosis needed before retuning K/ladder behavior.
