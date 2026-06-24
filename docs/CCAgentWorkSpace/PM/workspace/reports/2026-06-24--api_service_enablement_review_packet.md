# API Service Enablement Review Packet

Date: 2026-06-24
Active blocker: `P1-API-SERVICE-OWNERSHIP-ENABLEMENT-REVIEW`
Status: `DONE_WITH_CONCERNS`
Scope: source-only / read-only runtime evidence

## Session Loop State

- `session_goal`: Profit-first Demo-learning Autonomy Improvement Loop under Aggressive Alpha Expansion Mode.
- `active_blocker_id`: `P1-API-SERVICE-OWNERSHIP-ENABLEMENT-REVIEW`
- `blocker_goal`: review whether the post-cutover user systemd API service should be boot-autostart enabled, and define exact readiness/rollback gates without running `systemctl enable`.
- `profit_relevance`: stable Demo/API ownership improves evidence capture, auditability, reconstructability, and later live applicability. This is infrastructure hygiene only; it is not alpha proof, PnL proof, bounded-probe proof, or promotion evidence.
- `completed_blockers`: `P0-PROFIT-EVIDENCE-QUALITY`, `P0-PROFIT-CANDIDATE-SELECTION`, `P1-LEARNING-LOOP-CLOSURE`, `P1-AUTONOMOUS-PARAMETER-PROPOSAL`, and base `P1-RUNTIME-HEALTH-HYGIENE`.
- `blocked_blockers`: `P0-BOUNDED-PROBE-AUTHORIZATION` remains blocked by exact candidate-scoped typed-confirm; `P0-PROFIT-OUTCOME-REVIEW` has no authorized bounded-probe outcomes.
- `previous_report_paths`: API env-parity, no-apply cutover plan, exact unit diff packet, runtime cutover PM apply, and bounded authorization fail-closed reports.
- `source_head`: `b0b0c6714e21c5a398b2f470f0593c6cf33e2ab5`
- `runtime_timestamp`: `2026-06-24T13:57:04+02:00`
- `pg_snapshot_timestamp`: `2026-06-24 13:49:05.150707+02` read-only `SELECT now()` only.
- `artifact_mtimes`: learning SSOT / autonomous proposal / bounded authorization artifacts refreshed around `2026-06-24T13:29-13:45+02`.
- `operator_action_required`: false for this source-only review; true for any future `systemctl --user enable`.
- `new_evidence_delta_required`: post-cutover service state, enablement facts, fresh parity packet, and E3 review.
- `new_evidence_delta_found`: yes.
- `acceptance_criteria`: produce a no-authority enablement review, classify future enable gates, preserve no Bybit/PG/order/probe/live/Cost Gate authority, and require a future PM/E3 runtime checkpoint before enablement.
- `next_blocker_id`: `P0-PROFIT-OUTCOME-REVIEW` only after authorized bounded-probe outcomes exist; otherwise continue source-only execution-realism/profit-hypothesis preparation.

Session-loop packet:

- `/tmp/profit_first_session_loop_state_api_enablement_review_20260624T1350Z.json`
- status: `DONE_WITH_CONCERNS`
- anti-repeat decision: `source_only_progress_allowed_for_active_blocker`
- dispatch allowed: `true`
- all authority/mutation answers false.

## Anti-Repeat Decision

This did not repeat `P0-BOUNDED-PROBE-AUTHORIZATION`: that blocker has fresh fail-closed exact-confirm evidence and no typed-confirm delta.

This also did not repeat API cutover apply: service ownership handoff is already done. The new evidence delta is the post-cutover boot-autostart question: the service is active/running but the user unit is still disabled.

## Fresh Evidence

Fresh runtime snapshot:

- `/tmp/api_service_enablement_runtime_snapshot_20260624T1402Z.json`

Fresh parity packet:

- `/tmp/api_service_enablement_parity_packet_20260624T1402Z.json`
- `/tmp/api_service_enablement_parity_packet_20260624T1402Z.md`

Key facts:

- runtime source: `dc1416e5d886c74e2ddd8d28cc78a220950f9fde`, clean
- service: `openclaw-trading-api.service`
- active state: `active`
- sub state: `running`
- main PID: `2218842`
- start timestamp: `2026-06-24 13:37:14 CEST`
- unit file state: `disabled`
- unit SHA256: `1a1eaff67922737bde20085c2b87d08b2cf83ca647341b37ecdba723971aa913`
- listener: `100.91.109.86:8000` only
- unauthenticated health GET: HTTP `401`
- `[Install] WantedBy=default.target`: present
- `loginctl`: `Linger=yes`
- `default.target`: active
- `default.target.wants/openclaw-trading-api.service`: absent

Fresh parity status:

- `API_SERVICE_ENV_PARITY_CLEAN_SOURCE_ONLY`
- findings: `[]`
- evidence gaps: `[]`
- plan blockers: `[]`
- `enable_allowed_by_this_packet=false`
- `requires_e3_review_before_enable=true`

Secret/input mode evidence is path-and-mode only; no secret content was read:

- `/tmp/openclaw/runtime_secrets`: `0700`
- `/tmp/openclaw/runtime_secrets/openclaw_database_url`: `0600`
- `/home/ncyu/BybitOpenClaw/secrets/environment_files/ipc_secret.txt`: `0600`
- `/home/ncyu/BybitOpenClaw/secrets/environment_files/live_auth_signing_key.txt`: `0600`

## E3 Review

`E3(explorer)` returned `STATUS: DONE_WITH_CONCERNS`.

E3 conclusion:

- A source-only enablement review packet is appropriate now.
- Future `systemctl --user enable openclaw-trading-api.service` is security-acceptable only as a separate PM-supervised checkpoint.
- Enablement must use `enable` without `--now` because the service is already active.
- BB is not required unless scope expands into exchange-facing behavior.

Future enablement gates before any mutation:

1. Fresh parity packet remains `API_SERVICE_ENV_PARITY_CLEAN_SOURCE_ONLY`.
2. Unit SHA remains `1a1eaff67922737bde20085c2b87d08b2cf83ca647341b37ecdba723971aa913` or a new exact-diff packet is reviewed.
3. Bind remains Tailscale-only, not `0.0.0.0` or `::`.
4. Required secret inputs remain file-based, with `0600` files and `0700` runtime secret dir.
5. `/tmp/openclaw` runtime files/socket are present or have an explicit boot recreation path.
6. `OPENCLAW_ALLOW_MAINNET=1` is absent and no live auth, Cost Gate, probe, or order authority is granted.
7. Post-check verifies `is-enabled=enabled`, symlink target, service still active, listener/health unchanged.
8. Rollback is `systemctl --user disable openclaw-trading-api.service` plus symlink removal verification.

## Action Taken

1. Built the required session-loop state before dispatch.
2. Dispatched `E3(explorer)` for read-only runtime/security review.
3. Regenerated fresh runtime snapshot and parity packet after E3 warned not to rely on prior post-cutover `/tmp` packets.
4. Produced this source-only review packet.

No `systemctl --user enable`, disable, restart, daemon-reload, process signal, crontab edit, API POST, PG write, Bybit call, Cost Gate change, Rust writer enablement, probe/order/live authority, or promotion proof occurred.

## Aggressive Profit Hypotheses

### 1. AVAX false-negative near-touch bounded path

- why_it_might_make_money: `grid_trading|AVAXUSDT|Sell` remains the top false-negative candidate, but touchability is the missing bridge.
- fastest_safe_test: candidate-scoped near-touch simulation and one bounded Demo probe only after exact typed-confirm.
- required_data: candidate-matched order/fill lineage, fees, slippage, BBO freshness, matched blocked controls.
- failure_condition: no candidate-matched fill, taker conversion, or negative net after fees/slippage.
- authority_required: none for simulation; exact bounded Demo authorization before any order.
- max_safe_next_action: source-only touchability/execution-realism preparation.
- scoring: expected_net_pnl_upside 8/10, evidence_strength 6/10, execution_realism 4/10, cost_after_fees 6/10, time_to_test 6/10, risk_to_account 2/10, risk_to_governance 2/10, autonomy_value 9/10.

### 2. SOXL current-fee MM repeat-window confirmation

- why_it_might_make_money: one same-key current-fee-positive maker window exists; a repeat would identify a low-friction route without lowering Cost Gate.
- fastest_safe_test: read-only independent-window replay/refresh for the exact candidate key.
- required_data: L1/trade/fill-sim history, exact key identity, current fee, queue policy, train/holdout split.
- failure_condition: second window fails positive current-fee net or key identity changes.
- authority_required: none for replay; QC/operator review before any future probe.
- max_safe_next_action: source-only repeat-window evidence accumulation.
- scoring: expected_net_pnl_upside 7/10, evidence_strength 5/10, execution_realism 5/10, cost_after_fees 7/10, time_to_test 8/10, risk_to_account 1/10, risk_to_governance 1/10, autonomy_value 8/10.

### 3. API enablement as evidence-throughput resilience

- why_it_might_make_money: boot-stable Demo/API improves continuous evidence capture and live-applicable operational reproducibility.
- fastest_safe_test: future `enable --no-now` checkpoint after fresh E3 parity gates.
- required_data: fresh parity clean packet, unit SHA, linger/default target, symlink absence/presence, listener/health unchanged.
- failure_condition: all-interface bind, missing secret file modes, absent boot recreation path, or any authority contamination.
- authority_required: explicit PM/E3 runtime mutation checkpoint before enablement.
- max_safe_next_action: no-enable review only; actual enablement remains separate.
- scoring: expected_net_pnl_upside 4/10, evidence_strength 8/10, execution_realism 8/10, cost_after_fees 4/10, time_to_test 6/10, risk_to_account 1/10, risk_to_governance 4/10, autonomy_value 7/10.

## Status

`DONE_WITH_CONCERNS`

Concern: the source-only enablement review is complete, but boot autostart is not enabled. That is intentional. A future enablement apply would be a runtime mutation and must be a separate PM/E3 checkpoint.

## Why Not Repeating Current Blocker

This checkpoint has distinct new evidence after the cutover: active/running service, disabled unit, fresh parity clean packet, boot target facts, linger state, and E3 review. Re-running this exact source-only review without a new unit SHA, service state, boot policy, or operator/runtime-authorization delta would be `NO-OP_NO_EVIDENCE_DELTA`.
