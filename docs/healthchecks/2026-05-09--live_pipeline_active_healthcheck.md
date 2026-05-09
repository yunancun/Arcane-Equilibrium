# `[56] live_pipeline_active`

**Date**: 2026-05-09  
**Scope**: P0-NEW-ISSUE-1 LiveDemo `auth_missing` regression sentinel  
**Implementation**: `srv/helper_scripts/db/passive_wait_healthcheck/checks_live_pipeline.py`  
**Tests**: `srv/helper_scripts/db/test_live_pipeline_healthcheck.py`

## Purpose

Detect the regression where the live slot is configured for LiveDemo but the
signed `live/authorization.json` file is missing, causing Rust to refuse the
Live pipeline at boot and leaving runtime demo-only.

`[Xb]` is already used by `pipeline_triangulation`, so this new sentinel uses
the next numeric slot, `[56]`.

## Contract

- If `OPENCLAW_LIVE_PIPELINE_HEALTH_REQUIRED=0`, PASS-skip.
- If the live slot lacks a non-empty `api_key` or `api_secret`, PASS-skip by
  default.
- If `OPENCLAW_LIVE_PIPELINE_HEALTH_REQUIRED=1` and the live slot is incomplete,
  FAIL.
- If the live slot is configured, `live/authorization.json` must be non-empty.
- If authorization exists, `$OPENCLAW_DATA_DIR/pipeline_snapshot_live.json`
  must exist and be fresher than `OPENCLAW_LIVE_PIPELINE_STALE_SECONDS`
  (default 180s).

The check is read-only. It never writes or renews `authorization.json`.

## Current Runtime Fact

On Linux `trade-core` after the 2026-05-09 01:37 UTC rebuild/restart:

- `live/api_key`: present
- `live/api_secret`: present
- `live/bybit_endpoint`: present, endpoint resolves to LiveDemo
- `live/authorization.json`: missing
- `pipeline_snapshot_live.json`: stale

Expected verdict before operator renewal: `FAIL`.

