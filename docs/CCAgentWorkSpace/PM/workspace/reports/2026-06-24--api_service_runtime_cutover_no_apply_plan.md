# API Service Runtime Cutover No-Apply Plan

Date: 2026-06-24

## Session Loop State

- active_blocker_id: `P1-API-SERVICE-OWNERSHIP-RUNTIME-CUTOVER-REVIEW`
- blocker_goal: convert the API env-parity drift packet into a reviewable, no-apply systemd cutover plan that preserves the manual uvicorn host/port/workers/working-directory/env shape.
- profit_relevance: API ownership reproducibility improves Demo evidence capture, auditability, and later live applicability of the control plane. This is infrastructure hygiene only; it is not alpha proof, PnL proof, bounded-probe proof, or promotion evidence.
- source_head: `73fcd85fd2f3c593b1be80575a6c975829474880` before this patch.
- runtime_source_head: `dc1416e5d886c74e2ddd8d28cc78a220950f9fde` from supplied read-only runtime evidence.
- runtime_timestamp: `2026-06-24T10:31Z`
- pg_snapshot_timestamp: read-only `2026-06-24 12:30:58.647219+02`
- session_loop_state: `/tmp/profit_first_session_loop_state_api_cutover_review_20260624T1032Z.json`

## Constraints Checked

- No Bybit order/cancel/modify call.
- No PG write/schema migration.
- No systemd apply, daemon-reload, process signal, service restart, env mutation, crontab edit, or runtime file write.
- No live/mainnet authority.
- No probe/order authority.
- No global Cost Gate lowering.
- No Rust writer enablement.
- No promotion proof.
- Broad Demo API authorization remains operational permission, not live/mainnet authority and not an implicit bounded-probe/order authorization object.

## Previous Evidence Checked

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--api_service_env_parity_packet.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--runtime_cron_expected_head_patch_api_ownership.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--runtime_source_sync_artifact_refresh_checkpoint.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--bounded_probe_authorization_exact_confirm_gate.md`

## New Evidence Delta Required

- Current supplied manual uvicorn process command/cwd/env-key snapshot.
- Current supplied systemd unit/status snapshot.
- Current no-apply packet output with explicit apply/restart denial.
- Fresh review of command reconstruction and secret handling.

## New Evidence Delta Found

- Manual uvicorn remains represented as `.venv/bin/uvicorn app.main:app --host 100.91.109.86 --port 8000 --workers 4`.
- `openclaw-trading-api.service` remains inactive/disabled in the supplied status and its unit shape differs from the manual process.
- The packet now emits `api_service_runtime_cutover_plan_v1` with:
  - `apply_allowed_by_this_packet=false`
  - `restart_allowed_by_this_packet=false`
  - `requires_e3_review_before_apply=true`
  - `requires_runtime_mutation_checkpoint_before_apply=true`
  - proposed ExecStart preserving the reviewed uvicorn prefix plus host/port/workers.
  - safe env materialization for non-secret values and `_FILE` secret paths only.
  - preflight/apply/rollback/verification templates marked as templates, not authority.
- CLI smoke on `/tmp/api_service_env_parity_runtime_snapshot_20260624T1031Z.json` produced `API_SERVICE_ENV_PARITY_DRIFT` with no apply/restart authority and no plan blockers.

## Anti-Repeat Decision

`PROCEED_SOURCE_ONLY_NO_APPLY_PLAN`.

The prior API env-parity audit is complete and was not repeated as a naked audit. This checkpoint adds a new source artifact surface: a no-apply cutover plan with explicit blockers/guards, command reconstruction, env redaction, tests, and review.

## Action Taken

1. Extended `helper_scripts/cron/api_service_env_parity.py` to emit `runtime_cutover_plan`.
2. Added safe unit-env proposal logic:
   - direct secret-like env vars, including `DATABASE_URL` and `DSN`, are redacted and never materialized.
   - `_FILE` secret paths are preserved as path evidence.
3. Added uvicorn command-prefix reconstruction:
   - direct `uvicorn app.main:app ...` is preserved.
   - `/usr/bin/python3 -m uvicorn app.main:app ...` is preserved.
   - unrecognized non-uvicorn prefixes fail closed as `proposed_exec_start_incomplete`.
4. Added regression coverage for no-apply plan shape, direct database URL redaction, non-file secret redaction, wrapper preservation, and unrecognized-prefix blocking.
5. Updated `helper_scripts/SCRIPT_INDEX.md`.

## Review Chain

- `E3(explorer)` reviewed the no-apply packet and found no blocker; BB was not needed because this checkpoint is not exchange-facing.
- `E2(explorer)` initially found two issues:
  - direct `OPENCLAW_DATABASE_URL` could be materialized if custom required env keys were used.
  - wrapper commands such as `/usr/bin/python3 -m uvicorn app.main:app` could be reconstructed incorrectly.
- PM fixed both issues.
- `E2(explorer)` final review: `STATUS: DONE`, no blocker.
- `E4(explorer)` final regression: `STATUS: DONE`, no findings.

## Verification

- `PYTHONPATH=. python3 -m pytest -q helper_scripts/cron/tests/test_api_service_env_parity.py helper_scripts/cron/tests/test_runtime_health_hygiene.py` -> `35 passed`
- `python3 -m py_compile helper_scripts/cron/api_service_env_parity.py helper_scripts/cron/tests/test_api_service_env_parity.py` -> PASS
- `git diff --check` -> PASS
- CLI smoke with `PYTHONPATH=.` on supplied runtime snapshot -> `API_SERVICE_ENV_PARITY_DRIFT`, `apply_allowed=false`, `restart_allowed=false`, no authority/mutation flags.
- E2 focused tests -> `13 passed`.
- E4 focused tests -> `13 passed` twice and supplied-snapshot CLI smoke passed.

## Aggressive Profit Hypotheses

### 1. API service ownership cutover as evidence-quality throughput

- why_it_might_make_money: stable API ownership reduces control-plane ambiguity, making Demo fills, authorization attempts, and learning artifacts easier to reconstruct and later port to live-grade operation.
- fastest_safe_test: run the no-apply packet on fresh snapshots after any operator-approved service cutover, then require env/host/workers parity and health checks before accepting ownership.
- required_data: fresh process/unit snapshots, env-key parity, authenticated health response, listener ownership, rollback proof.
- failure_condition: proposed unit cannot reproduce manual uvicorn safely, secret materialization is required, or health checks fail after cutover.
- authority_required: none for this packet; explicit runtime mutation checkpoint plus E3 review before any apply/restart.
- max_safe_next_action: `runtime_cutover_apply_review_with_fresh_snapshots_and_backup_plan`.
- scoring: expected_net_pnl_upside 4/10, evidence_strength 8/10, execution_realism 7/10, cost_after_fees 4/10, time_to_test 6/10, risk_to_account 1/10, risk_to_governance 3/10, autonomy_value 7/10.

### 2. AVAX false-negative candidate touchability repair

- why_it_might_make_money: `grid_trading|AVAXUSDT|Sell` remains a high-upside false-negative path, but candidate-matched touchability is still the missing bridge from reviewable edge to bounded Demo proof.
- fastest_safe_test: source-only candidate-scoped placement/touchability simulation using the existing repair plan before any order authority.
- required_data: candidate-matched order/fill lineage, near-touch placement feasibility, fee/slippage assumptions, matched blocked controls.
- failure_condition: no candidate-matched fill path, deep passive overhang, or modeled net after fees/slippage fails matched controls.
- authority_required: none for simulation; exact bounded Demo authorization object before any probe/order.
- max_safe_next_action: `candidate_scoped_touchability_repair_sim_before_any_probe`.
- scoring: expected_net_pnl_upside 8/10, evidence_strength 6/10, execution_realism 4/10, cost_after_fees 6/10, time_to_test 6/10, risk_to_account 2/10, risk_to_governance 2/10, autonomy_value 9/10.

### 3. SOXL current-fee MM repeat-window confirmation

- why_it_might_make_money: one independent same-key window is positive after current maker fee, and a repeated same-key confirmation could identify a low-friction maker route without lowering Cost Gate.
- fastest_safe_test: wait for or replay one more independent same-key current-fee MM window and keep maker execution-realism gates intact.
- required_data: fresh L1/trade/fill-sim window summaries, exact candidate-key identity, current fee, queue policy, OOS/walk-forward evidence.
- failure_condition: second window fails positive current-fee net, key identity shifts, or maker execution realism fails.
- authority_required: none for read-only repeat evidence; QC/operator review before any bounded Demo probe.
- max_safe_next_action: `accumulate_or_replay_independent_windows_for_same_current_fee_mm_cell`.
- scoring: expected_net_pnl_upside 7/10, evidence_strength 5/10, execution_realism 5/10, cost_after_fees 7/10, time_to_test 8/10, risk_to_account 1/10, risk_to_governance 1/10, autonomy_value 8/10.

## Status

`DONE_WITH_CONCERNS`.

The no-apply cutover review artifact is complete. The concern is intentionally residual: no service ownership mutation was performed, so the actual manual-to-systemd cutover remains unresolved and must be a separate runtime mutation checkpoint.

## Next Blocker

`P1-API-SERVICE-OWNERSHIP-RUNTIME-CUTOVER-APPLY-REVIEW`.

## Why Not Repeating Current Blocker

This blocker produced new source behavior, tests, a supplied-snapshot CLI smoke, and E2/E3/E4 review. Re-running the same env-parity audit without fresh runtime snapshots or an actual runtime apply checkpoint would be `NO-OP_NO_EVIDENCE_DELTA`.
