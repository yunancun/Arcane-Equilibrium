# Polymarket Lead-Lag IC Cron + Killboard

Date: 2026-06-20
Owner: PM
Scope: artifact-only runtime feedback loop for Polymarket v2 lead-lag IC

## Summary

The v262 manual Polymarket lead-lag IC harness is now a durable hourly Linux loop and is visible in the alpha-discovery killboard.

Runtime state:

- Polymarket v2 collector: active hourly at minute 7.
- Lead-lag IC cron: active hourly at minute 17.
- Latest IC verdict: `INSUFFICIENT_SAMPLE`.
- Latest alpha-discovery action: `polymarket_leadlag_ic` = `RUN_READ_ONLY_CAPTURE`.
- Promotion readiness: `ready_for_probe=0`, `ready_for_aeg_chain=0`.

This is the correct current state: the data lane is live, but the v2 hourly time series still has only one distinct snapshot timestamp in the current smoke report.

## Implemented

- Added `helper_scripts/cron/polymarket_leadlag_ic_cron.sh`.
- Added `helper_scripts/cron/install_polymarket_leadlag_ic_cron.sh`.
- Added `helper_scripts/cron/tests/test_polymarket_leadlag_ic_cron_static.py`.
- Wired `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py` to read `<DATA>/research/polymarket_leadlag/polymarket_leadlag_latest.json` as arm `polymarket_leadlag_ic`.
- Extended `helper_scripts/research/tests/test_alpha_discovery_throughput.py` with Polymarket arm coverage.
- Updated `helper_scripts/SCRIPT_INDEX.md`, `TODO.md`, changelog, and PM memory.

The cron wrapper:

- Reads PG credentials from `basic_system_services.env`.
- Exports `PGOPTIONS="-c default_transaction_read_only=on"`.
- Defaults to `query_set=v2`, `mode=hourly-topn`, `symbols=BTCUSDT,ETHUSDT`, `horizons=15,60,240`, `min_points=30`.
- Writes dated and latest IC reports under `<DATA>/research/polymarket_leadlag/`.
- Appends compact status JSONL to `<DATA>/logs/polymarket_leadlag_ic.log`.
- Emits heartbeat `<DATA>/cron_heartbeat/polymarket_leadlag_ic.last_fire`.
- Uses a stale-lock guard and exits fail-soft.

The installer:

- Is Linux-only.
- Is dry-run by default.
- Requires `OPENCLAW_POLYMARKET_LEADLAG_CRON_APPLY=1` to write crontab.
- Installs an idempotent active hourly entry at minute 17.
- Supports `--remove`.

## Runtime Evidence

Manual wrapper smoke on `trade-core` wrote:

- Report: `/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_20260620T120018Z.json`
- Latest: `/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_latest.json`
- sha256: `15d68093c1e618ae9bfb234b072b6e4a5d3113c28b799e9d1af9913f46b3fab6`

Key fields:

- `query_set_version=v2`
- `mode=hourly-topn`
- `symbols=["BTCUSDT","ETHUSDT"]`
- `horizons_minutes=[15,60,240]`
- `snapshot_rows=860`
- `snapshot_distinct_timestamps=1`
- `delta_rows=0`
- `joined_rows=0`
- `price_rows=64`
- `status=INSUFFICIENT_SAMPLE`
- `reason=max joined IC points 0 below min_points 30`

Alpha-discovery refresh at `2026-06-20T12:00:33Z`:

- `is_fast_discovery_active=true`
- `active_arm_count=6`
- `source_ok_count=7`
- `source_present_count=6`
- `ready_for_aeg_chain=0`
- `ready_for_probe=0`
- `run_read_only_capture=4`
- `wait=2`
- `block=1`
- `actionable_alpha_found=false`
- `actionable_probe_found=false`

Polymarket arm:

- `arm_id=polymarket_leadlag_ic`
- `gate_status=CAPTURING`
- `action=RUN_READ_ONLY_CAPTURE`
- `sample_count=0`
- `artifacts_ready=false`
- `reason=sample_count_below_gate`
- `promotion_boundary=research_context_only_not_signal_or_promotion_proof`

Installed crontab line:

```cron
17 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw OPENCLAW_POLYMARKET_LEADLAG_QUERY_SET=v2 OPENCLAW_POLYMARKET_LEADLAG_MIN_POINTS=30 /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/polymarket_leadlag_ic_cron.sh >> /tmp/openclaw/logs/polymarket_leadlag_ic_cron.cron.log 2>&1
```

Crontab backup before install:

- `/tmp/openclaw/cron_backups/crontab_before_polymarket_leadlag_ic_20260620T120044Z.txt`

## Verification

Local:

```bash
PYTHONPATH=helper_scripts/research python3 -m pytest -q --import-mode=importlib helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_polymarket_leadlag.py
python3 -m pytest -q helper_scripts/cron/tests/test_polymarket_leadlag_ic_cron_static.py
python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/polymarket_leadlag/__init__.py helper_scripts/research/polymarket_leadlag/harness.py
git diff --check -- helper_scripts/cron/polymarket_leadlag_ic_cron.sh helper_scripts/cron/install_polymarket_leadlag_ic_cron.sh helper_scripts/cron/tests/test_polymarket_leadlag_ic_cron_static.py helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/tests/test_alpha_discovery_throughput.py
```

Result:

- `23 passed`
- `9 passed`
- py_compile passed
- diff-check passed

Linux `trade-core` after selective source sync:

- `23 passed`
- `9 passed`
- `bash -n` passed
- py_compile passed
- manual wrapper smoke passed
- alpha-discovery refresh included `polymarket_leadlag_ic`
- cron installed active

## Boundary

Allowed effects:

- Source/test/docs changes.
- Selective Linux source sync.
- Linux user crontab update.
- `/tmp/openclaw` artifact/log/heartbeat writes.
- Read-only PG `market.klines` SELECT path.

Explicit non-effects:

- No PG table write or schema migration.
- No Bybit private/signed/trading call.
- No engine/API rebuild or restart.
- No credential/auth/risk/order/strategy mutation.
- No signal output.
- No promotion proof.

## Next Trigger

Let the hourly v2 collector and IC cron accumulate enough distinct snapshot timestamps. When max per-cell IC points clears the sample gate, the next required review is:

- residualized BTC/ETH forward returns,
- regime split,
- HAC / autocorrelation-aware statistics,
- multiple-testing correction,
- QC/MIT/AI-E adversarial review,
- AEG matrix before any probe or promotion.

Until then, the correct action is continued read-only capture.

## Rollback

Remove the cron entry:

```bash
cd /home/ncyu/BybitOpenClaw/srv
OPENCLAW_POLYMARKET_LEADLAG_CRON_APPLY=1 helper_scripts/cron/install_polymarket_leadlag_ic_cron.sh --remove
```

Or restore from:

```bash
crontab /tmp/openclaw/cron_backups/crontab_before_polymarket_leadlag_ic_20260620T120044Z.txt
```
