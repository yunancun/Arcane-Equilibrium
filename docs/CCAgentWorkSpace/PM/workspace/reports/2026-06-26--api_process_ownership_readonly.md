# API Process Ownership Read-Only

1. `active_blocker_id`: `P1-RUNTIME-HEALTH-HYGIENE-API-PROCESS-OWNERSHIP`
2. `blocker_goal`: Clarify whether the runtime trading control API and watchdog are unmanaged/manual processes or owned by service units, without restart, service mutation, crontab edit, PG write, Bybit order action, or authority mutation.
3. `profit_relevance`: Indirect but material. Correct process ownership prevents unsafe runtime apply/restart assumptions and keeps the demo-learning path reconstructable before any bounded probe can produce live-applicable evidence.
4. `constraints_checked`: No Bybit private/order endpoint, no order/cancel/modify, no PG query/write, no source sync, no crontab edit, no service restart, no runtime env mutation, no Rust writer/adapter enablement, no Cost Gate/freshness-gate lowering, no probe/order/live authority, and no profit/proof claim.
5. `previous_evidence_checked`: TODO v577, session state `/tmp/openclaw/session_loop_state_20260626T114512Z_api_process_ownership_readonly.json`, latest maker cost-cushion report, latest runtime source-sync no-apply report, source/origin HEAD, runtime source HEAD, latest runtime auth artifact, and user/system systemd unit snapshots.
6. `new_evidence_delta_required`: Read-only runtime evidence resolving whether API/watchdog ownership is established under systemd user units.
7. `new_evidence_delta_found`: `systemctl --user` shows `openclaw-trading-api.service` loaded/active/running with MainPID `2218842`, and `openclaw-watchdog.service` loaded/active/running with MainPID `1538268`. `/proc/2218842/cgroup` is `/user.slice/user-1000.slice/user@1000.service/app.slice/openclaw-trading-api.service`. System-level `systemctl` has no matching OpenClaw units, which is expected because these are user services. Runtime auth sha changed to `e7420e21f546845661dd2ba1841baf8d81f4af70e5241d6a4053cf40e74ab855` but remains `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, `decision=defer`, AVAX candidate, and no granted probe/order authority.
8. `anti_repeat_decision`: `PROCEED_READ_ONLY_NEW_EVIDENCE_DELTA`; P0 auth has a new sha but no admitted authority, so P0 is not repeated. API ownership has new service/cgroup evidence and can be closed.
9. `action_taken_or_noop_reason`: Updated TODO/report/operator/worklog/changelog state to mark API process ownership `DONE_WITH_CONCERNS`. No runtime action was taken because the evidence already establishes user-systemd ownership and no process mutation is needed.
10. `aggressive_profit_hypotheses`:

| Hypothesis | why_it_might_make_money | fastest_safe_test | required_data | failure_condition | authority_required | max_safe_next_action | Scoring |
|---|---|---|---|---|---|---|---|
| AVAX maker-first bounded micro-probe | The current cap-feasible AVAX Sell path has no-order construction evidence and a positive source-only maker cost cushion. | Only after a candidate-scoped bounded Demo authorization object or exact typed confirm passes E3/BB order-envelope review. | Scoped auth, fresh BBO, Decision Lease/Rust admission, post-only envelope, candidate-matched fills, actual fees/slippage, same-side-cell controls. | No scoped auth, stale BBO, post-only reject/taker conversion counted as maker success, or net PnL after fees/slippage <= 0. | Candidate-scoped bounded Demo auth plus runtime/order review. | Keep blocked at P0 auth; do not place orders. | upside High; evidence Medium; realism Medium; cost favorable if maker; time Medium; account risk bounded only after auth; governance High; autonomy High |
| Actual fee-tier and maker-ratio evidence route | If actual Demo maker fees or maker ratio are better than conservative worksheet assumptions, the same signal could have a larger after-cost cushion without changing risk limits. | Design a read-only fee evidence packet; do not use it as proof until tied to candidate-matched fills. | Account fee tier provenance, actual fill liquidity role, fee fields, slippage, maker/taker labels, order/fill lineage. | Fee source is stale/unverified, maker/taker role is missing, or cross-symbol/unattributed fills enter proof. | Read-only E3/BB review for any private account fee read; no order authority. | Source-only packet design only, if opened later. | upside Medium; evidence Low-Medium; realism Medium; cost High impact; time Medium; account risk None for design; governance Low; autonomy Medium |
| Runtime sync apply after ownership clarity | Confirmed user-systemd ownership makes a future no-restart source-sync envelope easier to verify, reducing drift before reusable demo probes. | Separate apply checkpoint: fast-forward runtime source and update all 11 expected-head pins together, with post-check API PID/auth unchanged. | Current source head, runtime head, crontab pins, service PID/cgroup, auth sha, post-check plan. | Partial pin update, service restart, cron run, auth artifact mutation, writer enablement, or order/probe path mutation. | PM/E3 apply review; no order authority. | Keep deferred unless PM/operator opens runtime source availability work. | upside Low-Medium; evidence High; realism High; cost Low; time Fast; account risk Low; governance Medium; autonomy Medium |

11. `status`: `DONE_WITH_CONCERNS`
12. `next_blocker_id`: `P0-BOUNDED-PROBE-AUTHORIZATION` on a real scoped auth delta; otherwise no repeat. `P1-RUNTIME-HEALTH-HYGIENE-SOURCE-SYNC-APPLY-REVIEW` remains deferred and separate.
13. `why_not_repeating_current_blocker`: API and watchdog ownership are now established under `systemctl --user`; repeating the same read-only audit without unit/PID/cgroup/service-file change would not add evidence.
14. `branch_commit_push`: Pending at report creation; final PM response records branch, commit SHA, and push status.

## Evidence

- Source/origin: `210474bbd3284d22bd015cf7c9b8e71838fb4386`, clean.
- Runtime source: `dd22810ee41c353c1d214d9a3217862d7b2bac74`, clean.
- Runtime timestamp: `2026-06-26T11:45:12Z`.
- API unit: `openclaw-trading-api.service`, `ActiveState=active`, `SubState=running`, `MainPID=2218842`, `UnitFileState=enabled`, `FragmentPath=/home/ncyu/.config/systemd/user/openclaw-trading-api.service`.
- API command: `uvicorn app.main:app --host 100.91.109.86 --port 8000 --workers 4`.
- API cgroup: `/user.slice/user-1000.slice/user@1000.service/app.slice/openclaw-trading-api.service`.
- Watchdog unit: `openclaw-watchdog.service`, `ActiveState=active`, `SubState=running`, `MainPID=1538268`, `UnitFileState=enabled`.
- System-level units: no matching OpenClaw/Bybit/trade services found.

## E3 Review

E3 status: `DONE_WITH_CONCERNS`.

- API ownership passes: `openclaw-trading-api.service` is a user systemd unit, active/running and enabled, with `MainPID=ExecMainPID=2218842`.
- `/proc/2218842/cgroup` places the uvicorn master and workers inside `app.slice/openclaw-trading-api.service`; this is not an unmanaged/manual uvicorn process.
- TODO v577's "service ownership is not established" statement is stale/incomplete.
- No runtime mutation, service restart, source apply, crontab/env edit, PG write, Bybit call, or authority grant is required.
- Reconstructability caveat: the session-loop artifact is on the Mac `/tmp/openclaw/...`; the runtime service evidence remains independently reproducible from `systemctl --user` and `/proc` on `trade-core`.

## PM Decision

Close the blocker as `DONE_WITH_CONCERNS`. The concern is only that runtime source remains intentionally behind local source; that belongs to the separate source-sync apply review and does not make API ownership unknown. No runtime mutation is justified by this checkpoint.
