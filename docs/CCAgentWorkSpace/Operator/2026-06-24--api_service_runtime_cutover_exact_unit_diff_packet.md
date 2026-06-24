# Operator Note — API Service Runtime Cutover Exact Unit Diff Packet

Date: 2026-06-24

The API service cutover packet is now reviewable as an exact unit-file diff, not just a prose plan.

Fresh source-only packet:

- `/tmp/api_service_env_parity_exact_unit_diff_20260624T1148Z.json`
- status `API_SERVICE_ENV_PARITY_DRIFT`
- `plan_blockers=[]`
- one base unit fragment, no drop-ins
- current SHA `7178817a50869caa533a420f20228e54a2260bd274cc63ed3cffc605d56b4e83`
- proposed SHA `1a1eaff67922737bde20085c2b87d08b2cf83ca647341b37ecdba723971aa913`
- contract SHA `ba4c79bd60e67a4d5df063633a36f8a2dfaac1669c7c7bd07f73998f1e8b7145`
- `apply_allowed=false`, `restart_allowed=false`, `enable_allowed=false`

No service write/restart was performed. This is still a review packet.

Why this matters for later live applicability:

- the demo/API handoff can be rebuilt from source-fragment inventory, exact diff, and SHA checks
- stale or drop-in-modified systemd state fails closed before any apply
- direct secrets and redacted command/unit content cannot be turned into a proposed unit
- the future apply step must revalidate the manual process, listener, env keys, and current unit SHA against the reviewed contract

Verification passed: focused pytest `44 passed`, py_compile, `git diff --check`, CLI smoke, and direct secret-pattern scan.

Boundary: no systemd apply, no daemon-reload, no process signal, no service restart, no API/env/crontab mutation, no PG/Bybit action, no Cost Gate change, no probe/order/live authority, no Rust writer, and no promotion proof.
