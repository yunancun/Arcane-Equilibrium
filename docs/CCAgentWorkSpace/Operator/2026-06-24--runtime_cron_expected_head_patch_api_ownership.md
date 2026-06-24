# Operator Note: Runtime Cron Expected-Head Patch / API Ownership

Date: 2026-06-24

Result: `DONE_WITH_CONCERNS`.

What changed:

- Updated four active demo-learning cron entries so their expected-head pins match operational runtime source `dc1416e5d886c74e2ddd8d28cc78a220950f9fde`.
- Added missing expected-head envs to the Cost Gate learning-lane cron.
- Preserved schedules, wrappers, log paths, and existing flags.
- Runtime backup: `/tmp/openclaw/runtime_hygiene/crontab_backup_20260624T095358Z_before_expected_head_patch_dc1416e5.txt`.

Post-check:

- `cron_expected_head_drift_present=false`
- `runtime_source_drift_present=false`
- `artifact_compatibility_drift_present=false`
- remaining drift: `API_SERVICE_OWNERSHIP_DRIFT`

What did not happen:

- no Bybit order/cancel/modify,
- no PG write,
- no service restart,
- no API process mutation,
- no Cost Gate lowering,
- no probe/order/live authority,
- no Rust writer enablement,
- no promotion proof.

API ownership was intentionally not changed. The reachable manual uvicorn process and the inactive systemd unit are not equivalent; the unit lacks current runtime env parity and differs in host/workers. Next safe blocker is an env-parity/runbook packet before any restart.

