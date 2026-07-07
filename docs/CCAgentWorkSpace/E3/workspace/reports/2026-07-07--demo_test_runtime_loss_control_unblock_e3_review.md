# 2026-07-07 Demo Test Runtime Loss-Control Unblock E3 Review

Role: E3(worker) security / runtime authorization pre-review.

Verdict: `BLOCKED_STOP_LOSS_CONTROL`

BB dispatch: `NO` for demo testing from the current operator assertion. Dispatch BB only after PM produces a new exact-scope runtime/env restoration or loss-control refresh packet that is source-stable at the current reviewed head and requests BB review for a bounded exchange-facing scope.

## Scope

Reviewed operator assertion: `runtime/loss-control 已解除、三端同步、可以進行 demo 測試`.

Hard boundary held: no runtime mutation, DB read/write/migration, exchange/private read, MCP/config/credential/secret access, order/probe, Cost Gate change, deploy/restart, live/mainnet, model reload/symlink, bounded Demo outcome ingestion, or service/env change.

Permitted checks performed:

- local repo documents and PM artifacts;
- local git status/head;
- remote `origin/main` head via `git ls-remote`;
- Linux checkout git head/status only, without service/env/DB/exchange access.

## Source-State Facts

- Mac local `srv` head: `e49ef454564a08bb89e0b11900f681027067a530`.
- Mac local `origin/main`: `77f0b56782000a73c28215f1dc2762e5bdb09b07`.
- Mac local branch state: `main...origin/main [ahead 4]`.
- Mac local worktree is dirty, with modified auth/control-api/IBKR/memory paths and untracked PM/operator/memory files.
- GitHub remote `refs/heads/main`: `77f0b56782000a73c28215f1dc2762e5bdb09b07`.
- Linux `trade-core` checkout: clean `main...origin/main`, `HEAD == origin/main == 77f0b56782000a73c28215f1dc2762e5bdb09b07`.

Assessment: GitHub and Linux are aligned, but the Mac repo is not aligned with `origin/main` and is dirty. This is not a machine-checkable three-side source-stable current-head state for granting runtime/loss-control READY.

## Artifact Facts

Latest PM standing Demo loss-control packet:

- Report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--standing_demo_loss_control_authorization_blocked_by_engine_env.md`
- State packet: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--standing_demo_loss_control_authorization_blocked_by_engine_env.state_packet.json`
- Status: `BLOCKED`.
- Stop reason: `STOP_LOSS_CONTROL`.
- E3 had approved the exact refresh request for BB review, and BB approved that exact refresh boundary.
- The approval was not consumed into materialization because runtime readiness blocked on:
  - `engine_env:engine_env_OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED_not_1`
  - `standing_authorization:standing_auth_expired`
- Corrected readiness status: `BOUNDED_DEMO_RUNTIME_BLOCKED_BY_ENGINE_ENV`.
- No guardrail run occurred after corrected readiness.
- No standing envelope was materialized.
- Existing standing authorization remains expired.

Latest AI/ML downstream loop packet:

- Report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_downstream_loop_wp7_learning_effect_review_stop_loop.md`
- State packet: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_downstream_loop_wp7_learning_effect_review_stop_loop.state_packet.json`
- Status: `STOPPED`.
- Blocking gate: `RUNTIME_LOSS_CONTROL_BLOCKED`.
- It explicitly denies runtime mutation, DB read/write, exchange/private read, order/probe, Cost Gate change, deploy, live/mainnet, model reload/symlink, runtime learning, and bounded Demo outcome ingestion.

Current TODO active blocker:

- `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD` remains `BLOCKED_BY_RUNTIME_ENV`.
- TODO states the next executable dispatch is a PM->E3 runtime/env decision, not order/probe or demo testing.

## Authorization Criteria Review

Required for `RUNTIME_LOSS_CONTROL_READY`:

| Criterion | Result | Evidence |
|---|---|---|
| Machine-checkable exact-scope packet exists | `FAIL` | Latest exact-scope packet is `BLOCKED`, not READY. |
| Source-stable current head | `FAIL` | Mac local head is ahead 4 and dirty; prior approved source was `798843f2`, not current local `e49ef454` or remote/Linux `77f0b567`. |
| E3/BB-approved current scope | `FAIL` | Prior E3/BB approval was for a stopped refresh attempt and cannot be reused after non-expiry readiness blocker. |
| Runtime readiness has no non-expiry blocker | `FAIL` | Readiness blocker includes `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=0`, not only expired standing auth. |
| Guardrail/materialization completed if required | `FAIL` | PM report says no guardrail/materialization occurred. |
| No authority expansion | `FAIL if consumed` | Treating the operator assertion as demo-test authority would expand beyond the approved stopped refresh boundary. |

## E3 Judgment

Fact: the latest machine-readable PM packets classify runtime/loss-control as blocked, not ready.

Inference: the operator assertion alone is insufficient to override expired standing authorization, a non-expiry engine-env blocker, absence of guardrail/materialization, and current source-state drift.

Assumption: no newer exact-scope READY packet exists outside the repo paths and state checked in this review. If one exists, PM must register it as a machine-checkable artifact and reroute E3/BB review before demo testing.

## Why Demo Testing Cannot Proceed

Demo testing would require consuming runtime/loss-control authority. The only current artifacts say that authority is blocked by engine env plus expired standing authorization, and no materialized envelope exists. Starting demo testing now would bypass the required PM->E3->BB loss-control gate, Decision Lease/Rust authority sequence, and proof-exclusion rules.

## Next Safe Actions

1. PM opens a separate exact-scope runtime/env decision to restore Demo-only engine env `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=1`, with no paper/live/mainnet enablement and no Cost Gate change.
2. Re-establish source-stable current head for the selected scope; do not reuse `798843f2` approval unless PM explicitly proves it is still the reviewed current scope.
3. Rerun source gate, exactly one allowed fast-balance artifact if authorized, readiness, guardrail with `--allow-expired-standing-auth-readiness-only`, and materialization only if readiness has no non-expiry blocker.
4. Dispatch BB only for that exact refreshed exchange-facing review scope.
5. After a valid materialized loss-control envelope exists, open any demo-test/order-capable action as a separate fresh same-window E3/BB review with active lease, fresh BBO/instrument/order shape, Guardian/Rust authority, auditability, and reconstructability.
