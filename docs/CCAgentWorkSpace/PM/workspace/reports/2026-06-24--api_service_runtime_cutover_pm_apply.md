# API Service Runtime Cutover PM Apply

Date: 2026-06-24  
Blocker: `P1-API-SERVICE-OWNERSHIP-RUNTIME-CUTOVER-PM-APPLY-REVIEW`  
Scope: Demo/API service ownership handoff only

## Decision

E3 reviewed the fresh v472 exact unit diff contract and returned `STATUS: DONE`.

PM executed the guarded runtime handoff from the manual uvicorn owner to `openclaw-trading-api.service`.

BB was skipped because this checkpoint was not exchange-facing: no Bybit REST/WS/IPC behavior, no order/cancel/modify, no probe/order authority, and no live authority.

## Pre-Apply Evidence

Fresh pre-apply artifacts:

- session loop state: `/tmp/profit_first_session_loop_state_api_cutover_pm_apply_review_20260624T1132Z.json`
- fresh runtime snapshot: `/tmp/api_service_env_parity_runtime_snapshot_pre_apply_revalidation.json`
- fresh parity packet: `/tmp/api_service_env_parity_packet_pre_apply_revalidation.json`

Pre-apply packet:

- status: `API_SERVICE_ENV_PARITY_DRIFT`
- evidence gaps: `[]`
- plan blockers: `[]`
- source fragments: `["/home/ncyu/.config/systemd/user/openclaw-trading-api.service"]`
- single fragment only: `true`
- drop-ins detected: `false`
- current SHA: `7178817a50869caa533a420f20228e54a2260bd274cc63ed3cffc605d56b4e83`
- proposed SHA: `1a1eaff67922737bde20085c2b87d08b2cf83ca647341b37ecdba723971aa913`
- contract SHA: `ba4c79bd60e67a4d5df063633a36f8a2dfaac1669c7c7bd07f73998f1e8b7145`
- manual master PID: `1859622`
- manual bind: `100.91.109.86:8000`
- manual workers: `4`
- manual cwd: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1`

## Runtime Action

PM executed the E3-approved minimal sequence:

1. verified current unit SHA and proposed temp unit SHA
2. verified manual PID/cmdline/cwd/listener still matched the reviewed contract
3. backed up current unit to:
   `/home/ncyu/.config/systemd/user/openclaw-trading-api.service.backup_20260624T113713Z_before_pm_apply_review`
4. wrote exactly the proposed unit content
5. verified written unit SHA equals `1a1eaff67922737bde20085c2b87d08b2cf83ca647341b37ecdba723971aa913`
6. ran `systemctl --user daemon-reload`
7. gracefully SIGTERM'd manual uvicorn master PID `1859622`
8. started `openclaw-trading-api.service`

The first apply command attempt failed before mutation due shell quoting around `awk $1`; it performed no unit write, daemon-reload, signal, or service start. The corrected command used `cut` for SHA extraction and completed.

## Post-Apply Evidence

Service post-check:

- `ActiveState=active`
- `SubState=running`
- `MainPID=2218842`
- `ExecStart` binds `100.91.109.86:8000` with `--workers 4`
- `UnitFileState=disabled`
- `ss` listener only on `100.91.109.86:8000`
- `/api/v1/system/health` returns HTTP `401`, proving the authenticated API surface is reachable
- old manual PID `1859622` is absent

Post-cutover parity:

- snapshot: `/tmp/api_service_env_parity_runtime_snapshot_post_cutover.json`
- packet: `/tmp/api_service_env_parity_packet_post_cutover.json`
- status: `API_SERVICE_ENV_PARITY_CLEAN_SOURCE_ONLY`
- findings: `[]`
- evidence gaps: `[]`
- plan blockers: `[]`
- systemd active state: `active`
- systemd main PID: `2218842`
- current unit SHA: `1a1eaff67922737bde20085c2b87d08b2cf83ca647341b37ecdba723971aa913`
- apply/restart/enable allowed by packet: all `false`

Additional sanity:

- runtime repo remains clean at `dc1416e5d886c74e2ddd8d28cc78a220950f9fde`
- demo engine watchdog: `engine_alive=true`, demo alive, snapshot age `24.3s`
- `systemctl --user is-enabled openclaw-trading-api.service`: `disabled`
- `systemctl --user is-active openclaw-trading-api.service`: `active`

## Boundaries Preserved

- no `systemctl --user enable`
- no Bybit call
- no PG write
- no Cost Gate lowering
- no probe/order/live authority
- no Rust writer enablement
- no promotion proof
- no live/mainnet change

## Next Safe Blocker

`P1-API-SERVICE-OWNERSHIP-ENABLEMENT-REVIEW`

Enablement is not urgent for profit evidence. It should only be reviewed after the active service remains healthy and a separate PM/E3 checkpoint decides whether boot autostart is desirable.

For the profit loop, the higher-value next blocker remains bounded Demo probe authorization / execution realism, not API service enablement.
