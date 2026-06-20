# 2026-06-20 FlashDip Death-Rate Freshness Gate

## Summary

PM-local source/test checkpoint. The FlashDip death-rate monitor is the survival lens for the current non-MM positive-alpha candidate path. Alpha discovery was reading its latest status line without timestamp freshness validation, so a stopped cron could keep the killboard looking active.

## Change

- `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
  - `collect_flash_dip_arm()` now requires fresh `ts_utc`.
  - Stale/missing timestamp becomes `gate_status=SOURCE_FAILURE`, `source_ok=false`, and `source_error=stale_artifact`.
  - `artifacts_ready=false` when stale, even if old `n_closed_slots` met the threshold.
  - Current missing/not-yet-fired behavior remains fail-soft capture.
- `helper_scripts/research/tests/test_alpha_discovery_throughput.py`
  - Added regression for stale FlashDip death-rate status.

## Verification

- `python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_throughput.py` -> 11 passed
- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`

Linux selective deploy/smoke:

- `origin/main=4d06336d` restored to trade-core touched files; checkout HEAD remains old `bb06ae1b` due existing selective-deploy dirty state.
- Linux focused test passed: alpha discovery runtime 11.
- Manual artifact-only `alpha_discovery_throughput_cron.sh` refreshed latest killboard at `2026-06-20T00:52:47Z`.
- Current FlashDip death-rate status is still inside the 36h window: `age_seconds=71986.8`, `source_ok=true`, `gate_status=READY`, `sample_count=0`, `artifacts_ready=false`.

## Boundary

No engine/API restart, no PG write, no Bybit private/signed/trading call, no auth/risk/order mutation. This is not promotion proof; it is a truthfulness gate so the discovery loop does not overstate live FlashDip evidence.
