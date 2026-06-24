# API Service Env-Parity Packet Checkpoint

Date: 2026-06-24

## Session Loop State

- active_blocker_id: `P1-API-SERVICE-OWNERSHIP-ENV-PARITY`
- blocker_goal: compare the reachable manual uvicorn Trading API process/env with the inactive systemd unit and produce a no-restart env-parity packet/runbook surface.
- profit_relevance: this improves Demo evidence capture reconstructability and later live applicability by making the API owner/env reproducible. It is not alpha proof, not PnL proof, and not promotion evidence.
- source_head:
  - Mac/origin source ledger: `863aefd9676bb8d9208687c238e2997e7877d50c`
  - runtime operational source: `dc1416e5d886c74e2ddd8d28cc78a220950f9fde`
- runtime_timestamp: `2026-06-24T10:02:41Z`
- pg_snapshot_timestamp: read-only `2026-06-24 12:03:03.506914+02`
- session_loop_state: `/tmp/profit_first_session_loop_state_api_env_parity_20260624T1003Z.json`

## Constraints Checked

- No Bybit order/cancel/modify call.
- No PG write/schema migration.
- No service restart, process signal, systemd mutation, env mutation, or crontab edit.
- No live/mainnet authority.
- No probe/order authority.
- No global Cost Gate lowering.
- No Rust writer enablement.
- No promotion proof.
- Broad Demo API authorization is still not treated as live/mainnet authorization or implicit bounded-probe/order authority.
- BB review skipped: this checkpoint is local API/systemd ownership review and does not touch exchange-facing behavior.

## Previous Evidence Checked

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--runtime_cron_expected_head_patch_api_ownership.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--runtime_source_sync_artifact_refresh_checkpoint.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--runtime_source_artifact_hygiene_packet.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--bounded_probe_authorization_exact_confirm_gate.md`

## New Evidence Delta Required

- Current runtime source HEAD/status.
- Current manual uvicorn command/cwd/exe/env-key snapshot with secrets redacted.
- Current systemd unit/status snapshot.
- Current listener/API reachability snapshot.
- Current bind-host helper constraint.

## New Evidence Delta Found

- Runtime source is clean at `dc1416e5d886c74e2ddd8d28cc78a220950f9fde`.
- Manual Trading API process is present and reachable on `100.91.109.86:8000`.
- Manual process command: `.venv/bin/uvicorn app.main:app --host 100.91.109.86 --port 8000 --workers 4`.
- `openclaw-trading-api.service` is loaded but inactive/dead and disabled.
- Unit `ExecStart` uses `--host 0.0.0.0 --port 8000`, omits `--workers 4`, and lacks the runtime `OPENCLAW_*` env keys present on the manual process.
- `helper_scripts/lib/api_bind_host.sh` rejects `0.0.0.0` / `::` as all-interface exposure.
- API root/console return 303, `/api/v1/system/health` returns 401, and public `/health` endpoints return 404. This is reachability/ownership evidence only, not an alpha proof.

## Anti-Repeat Decision

`PROCEED_SOURCE_ONLY`.

The prior cron expected-head drift is already complete and was not repeated. This blocker had new evidence delta: API manual process/service unit env parity mismatch after cron/source/artifact drift was closed. The work advanced the remaining API ownership blocker without restarting or mutating the service.

## Action Taken

1. Built `session_loop_state` at `/tmp/profit_first_session_loop_state_api_env_parity_20260624T1003Z.json`.
2. Added `helper_scripts/cron/api_service_env_parity.py`.
3. Added `helper_scripts/cron/tests/test_api_service_env_parity.py`.
4. Updated `helper_scripts/SCRIPT_INDEX.md`.
5. Ran local CLI smoke against a redacted runtime snapshot:
   - snapshot: `/tmp/api_service_env_parity_runtime_snapshot_20260624T1007Z.json`
   - packet JSON: `/tmp/api_service_env_parity_packet_20260624T1025Z.json`
   - packet Markdown: `/tmp/api_service_env_parity_packet_20260624T1025Z.md`
6. Packet status: `API_SERVICE_ENV_PARITY_DRIFT`.
7. Packet findings:
   - `service_inactive_while_manual_process_present`
   - `unsafe_unit_bind_host`
   - `bind_host_mismatch`
   - `worker_count_mismatch`
   - `unit_missing_runtime_env_keys`
8. Packet no-authority answers all remained conservative:
   - `service_restart_performed=false`
   - `runtime_mutation_performed=false`
   - `env_mutation_performed=false`
   - `pg_write_performed=false`
   - `bybit_call_performed=false`
   - `global_cost_gate_lowering_recommended=false`
   - `probe_authority_granted=false`
   - `order_authority_granted=false`
   - `live_authority_granted=false`
   - `promotion_evidence=false`

## Review Chain

- `E2(explorer)` initial review found three source issues:
  - missing process env evidence could falsely report clean,
  - env/service mutation contamination was not rejected,
  - raw command lines could leak inline secret args.
- PM fixed all three with regressions.
- `E3(explorer)` verdict: no security blocker for this no-restart packet; BB skipped because non-exchange-facing. E3 asked to keep any future restart/apply behind E3 review and runtime authorization.
- `E4(worker)` final regression: `DONE`.
- `E2(explorer)` final exact redaction re-review: `DONE`, verdict `CLOSED`.

## Verification

- `PYTHONPATH=. python3 -m pytest -q helper_scripts/cron/tests/test_api_service_env_parity.py helper_scripts/cron/tests/test_runtime_health_hygiene.py` -> `30 passed`
- `python3 -m py_compile helper_scripts/cron/api_service_env_parity.py helper_scripts/cron/tests/test_api_service_env_parity.py` -> PASS
- `git diff --check` -> PASS
- CLI smoke on supplied runtime snapshot -> `API_SERVICE_ENV_PARITY_DRIFT`, no authority/mutation flags.

## Aggressive Profit Hypotheses

### 1. API owner env-parity as Demo evidence-throughput lever

- why_it_might_make_money: a reproducible API service owner reduces control-plane ambiguity, making Demo fills, authorization attempts, and learning artifacts easier to reconstruct and later port to live-grade operation.
- fastest_safe_test: no-restart packet plus E3-reviewed unit patch proposal; keep manual owner until parity accepted.
- required_data: manual process env keys, unit env keys, bind host, workers, API reachability, rollback plan.
- failure_condition: unit cannot reproduce manual env/host/workers safely, or restart risks losing current control-plane access.
- authority_required: none for packet; E3 plus explicit runtime mutation gate before any future restart/apply.
- max_safe_next_action: `draft_no_restart_systemd_unit_env_parity_patch`.
- scoring: expected_net_pnl_upside 4/10, evidence_strength 8/10, execution_realism 7/10, cost_after_fees 4/10, time_to_test 7/10, risk_to_account 1/10, risk_to_governance 3/10, autonomy_value 7/10.

### 2. AVAX false-negative bounded Demo candidate after touchability repair

- why_it_might_make_money: `grid_trading|AVAXUSDT|Sell` remains the top false-negative candidate with strong blocked-outcome net cushion and is the cleanest bounded-review path.
- fastest_safe_test: candidate-scoped touchability/near-touch placement simulation and exact bounded authorization packet; no global Cost Gate change.
- required_data: candidate-matched order/fill lineage, placement plan, fee/slippage model, matched blocked controls.
- failure_condition: no candidate-matched fills, no-touch/deep passive orders, or realized net fails after fees/slippage versus matched controls.
- authority_required: explicit bounded Demo probe authority before any order/probe.
- max_safe_next_action: `candidate_scoped_touchability_repair_sim_before_any_probe`.
- scoring: expected_net_pnl_upside 8/10, evidence_strength 6/10, execution_realism 4/10, cost_after_fees 6/10, time_to_test 6/10, risk_to_account 2/10, risk_to_governance 2/10, autonomy_value 9/10.

### 3. Same-key MM current-fee repeat window

- why_it_might_make_money: the SOXLUSDT current-fee MM cell is positive after current maker fee in one independent window; exact-repeat evidence could identify a low-friction maker path without lowering Cost Gate.
- fastest_safe_test: accumulate or replay one more independent window for the exact same candidate key.
- required_data: fresh L1/trade/fill-sim report, window summaries, exact candidate-key identity, current fee preserved.
- failure_condition: second independent window fails positive current-fee net, OOS/walk-forward fails, or maker execution realism fails.
- authority_required: none for read-only repeat evidence; QC/operator review before any bounded Demo probe.
- max_safe_next_action: `accumulate_or_replay_independent_windows_for_same_current_fee_mm_cell`.
- scoring: expected_net_pnl_upside 7/10, evidence_strength 5/10, execution_realism 5/10, cost_after_fees 7/10, time_to_test 8/10, risk_to_account 1/10, risk_to_governance 1/10, autonomy_value 8/10.

## Status

`DONE_WITH_CONCERNS`.

The source-only env-parity packet/runbook surface is complete and reviewed. The actual API service ownership drift remains intentionally unresolved because applying a systemd unit, changing env, signaling processes, or restarting the service is a runtime mutation and should be a separate E3-reviewed runtime cutover checkpoint.

## Next Blocker

`P1-API-SERVICE-OWNERSHIP-RUNTIME-CUTOVER-REVIEW` if the next session chooses to convert the packet into a reviewed unit patch/apply plan; otherwise resume the profit blocker order at the next source-only alpha evidence task.

## Why Not Repeating Current Blocker

The current blocker produced new durable source artifacts, tests, CLI smoke output, and a reviewed packet. Re-running the same API env-parity audit without a new service/unit/process snapshot or a unit patch proposal would be `NO-OP_NO_EVIDENCE_DELTA`.
