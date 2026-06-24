# API Service Runtime Cutover Exact Unit Diff Packet

Date: 2026-06-24  
Blocker: `P1-API-SERVICE-OWNERSHIP-RUNTIME-CUTOVER-APPLY-REVIEW`  
Scope: source-only / no runtime mutation

## Summary

This checkpoint hardens the API service cutover review packet so a future Demo-to-live-applicable service ownership handoff can be reviewed from exact, reconstructable evidence rather than prose templates.

`helper_scripts/cron/api_service_env_parity.py` now emits an exact redacted current/proposed systemd unit-file diff inside `api_service_runtime_cutover_plan_v1`, including:

- source fragment inventory and drop-in detection
- current unit content SHA256
- proposed unit content SHA256
- unified current/proposed diff
- pre-apply revalidation contract and contract SHA256
- enablement review with `enable_allowed_by_this_packet=false`
- hard `apply_allowed_by_this_packet=false` and `restart_allowed_by_this_packet=false`

No systemd write, daemon-reload, process signal, service restart, API/env/crontab mutation, PG write, Bybit call, Cost Gate change, probe/order/live authority, Rust writer enablement, or promotion proof occurred.

## Fresh Evidence

Source state before this checkpoint:

- Mac `HEAD`: `998e19d2a1223f68ed703465512fae972d0274d0`
- `origin/main`: `998e19d2a1223f68ed703465512fae972d0274d0`
- Runtime supplied snapshot: `/tmp/api_service_env_parity_runtime_snapshot_20260624T1058Z.json`

Fresh generated packet:

- JSON: `/tmp/api_service_env_parity_exact_unit_diff_20260624T1148Z.json`
- Markdown: `/tmp/api_service_env_parity_exact_unit_diff_20260624T1148Z.md`
- Status: `API_SERVICE_ENV_PARITY_DRIFT`
- Plan blockers: `[]`
- Source fragments: `["/home/ncyu/.config/systemd/user/openclaw-trading-api.service"]`
- Single fragment only: `true`
- Drop-ins detected: `false`
- Current unit redaction: `false`
- Proposed unit redaction: `false`
- Existing direct-secret env redactions: `[]`
- Current SHA256: `7178817a50869caa533a420f20228e54a2260bd274cc63ed3cffc605d56b4e83`
- Proposed SHA256: `1a1eaff67922737bde20085c2b87d08b2cf83ca647341b37ecdba723971aa913`
- Contract SHA256: `ba4c79bd60e67a4d5df063633a36f8a2dfaac1669c7c7bd07f73998f1e8b7145`
- Apply/restart/enable allowed by packet: all `false`

## Fail-Closed Guards Added

The packet now blocks runtime apply review if any of these are true:

- `systemctl cat` source headers are missing
- multiple fragments are present
- a `.service.d/` drop-in appears, including drop-in-only output
- current unit content required redaction
- proposed unit content contains redactions
- existing unit env contains direct secret material
- command source contained redacted secret/key/token/password material
- proposed ExecStart cannot be reconstructed from a recognized uvicorn prefix
- unit app and manual process app disagree

Any plan blocker elevates the top-level packet to `API_SERVICE_ENV_PARITY_CUTOVER_PLAN_BLOCKED`; it cannot falsely report clean source-only parity.

## Verification

- `PYTHONPATH=. python3 -m pytest -q helper_scripts/cron/tests/test_api_service_env_parity.py helper_scripts/cron/tests/test_runtime_health_hygiene.py`  
  Result: `44 passed`
- `python3 -m py_compile helper_scripts/cron/api_service_env_parity.py helper_scripts/cron/tests/test_api_service_env_parity.py`  
  Result: pass
- `git diff --check`  
  Result: pass
- CLI smoke against `/tmp/api_service_env_parity_runtime_snapshot_20260624T1058Z.json`  
  Result: packet above
- Direct secret-pattern scan against generated JSON/MD for `postgresql://`, `leaked-secret`, `--api-key`, `OPENCLAW_DATABASE_URL=`  
  Result: no matches

## Runtime Apply Boundary

This checkpoint does not authorize applying the proposed unit.

Before any future apply/restart checkpoint, PM/E3 must take a fresh snapshot and verify the pre-apply contract:

- manual uvicorn pid, cmdline, cwd, selected env keys, listener host/port/workers still match
- current unit SHA/source fragments/drop-in status still match
- proposed unit SHA still matches
- proposed unit binds only the reviewed Tailscale host and keeps `--workers 4`
- no direct secret values are copied into the unit/report
- any `systemctl --user enable` decision remains separately reviewed

## Next Safe Blocker

`P1-API-SERVICE-OWNERSHIP-RUNTIME-CUTOVER-PM-APPLY-REVIEW`

Max safe next action: source/review packet handoff only. A real runtime apply remains a distinct runtime mutation checkpoint.
