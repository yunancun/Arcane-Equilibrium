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

## Implementation

Added `helper_scripts/cron/flash_dip_touchability_cron.sh`.

The cron is a read-only PG diagnostic:

- Reads recent `trading.orders` rows labeled `flash_dip_buy`.
- Joins `trading.intents` and counts true FlashDip only when joined intent strategy is `flash_dip_buy` and `details.limit_price` exists.
- Uses `market.klines` 1m lows from order timestamp to maker timeout/current time to determine whether the intended limit was touched.
- Writes only local artifacts: `logs/flash_dip_touchability_cron.log`, `logs/flash_dip_touchability.log`, heartbeat, and lock files.
- Enforces `PGOPTIONS="-c default_transaction_read_only=on"`.

Updated `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py` so FlashDip killboard detail reads `logs/flash_dip_touchability.log`. When death-rate remains `n_closed_slots=0` but fresh touchability shows true FlashDip orders and zero touches, the arm reports `CAPTURING_NO_TOUCH` rather than plain `CAPTURING`.

## Verification

- `bash -n helper_scripts/cron/flash_dip_touchability_cron.sh` PASS
- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/runtime_runner.py` PASS
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_throughput.py` = 13 passed
- Linux isolated smoke: piped cron script to `trade-core` with `OPENCLAW_DATA_DIR=/tmp/openclaw_flash_touch_smoke_20260620T012509Z`; it wrote only isolated `/tmp` logs/status and produced the evidence above.

## Boundary

No engine/API restart, no rebuild, no strategy flag change, no Bybit private/signed/trading call, no credential/auth/risk/order mutation, no PG table write/schema migration. This is not promotion proof; it is a repeatable no-touch diagnosis needed before retuning K/ladder behavior.
