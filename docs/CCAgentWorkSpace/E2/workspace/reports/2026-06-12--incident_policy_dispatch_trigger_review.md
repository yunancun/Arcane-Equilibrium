# P2 Incident-Policy Dispatch Trigger E2 Review

STATUS: DONE_WITH_CONCERNS - reviewed CORE+auth+Bybit path passes adversarial source review, but producer coverage is still incomplete.

> date: 2026-06-12
> scope: adversarial review of existing `incident_policy` CORE + auth invalid producer + Bybit retCode fail-closed producer
> boundary: no CI, no deploy/rebuild/restart, no DB/auth/risk/trading mutation

## Verdict

**PASS-WITH-CONDITIONS**.

No blocker/high/medium/low finding for the reviewed source path.

Conditions:

- Keep TODO state partial. Current code covers CORE, auth invalid, and Bybit retCode fail-closed; it does not cover `sm_halt_stuck`, `position_drift`, or external `engine_dead`.
- Do not claim runtime-complete fail-safe behavior before remaining producers and E4/QA/full-chain review.
- Do not let future producer additions bypass the current arm-vs-notify and push-secret gates.

## Spec Compliance Checks

Passed:

- Arm classes are `auth_invalid`, `bybit_fail_closed`, and `sm_halt_stuck`; notify-only classes are `engine_dead` and `position_drift`.
- Notify-only classes never feed `AllFail` into the watcher, even if notification dispatch returns `AllFail`.
- Arm classes are downgraded to notify-only when Slack/Email push channels are not both enabled.
- Only `DispatchOutcome::AllFail` can feed the C4 watcher, and only for arm mode.
- Single armed owner is enforced before feeding watcher outcome.
- Stale in-flight dispatch is blocked by generation/resolved-generation checks.
- Self-heal only sends `AllSuccess` for the current armed class.
- `incident_policy` does not directly modify RiskGovernor, system mode, live authorization, order placement, or exchange stop state.
- Fail-soft behavior is explicit when watcher/feed senders are unavailable or the outcome receiver is dropped.

## Adversarial Notes

INFO-1: `WatcherUnavailable` returns before ledger state is updated. This is acceptable for the current PA fail-soft model because the watcher is boot-wired in `main_boot_tasks`, but it means a future regression that stops spawning C4 watcher would also make sustained incident accumulation disappear. Do not use incident-policy success as a substitute for a watcher boot healthcheck.

INFO-2: `BybitFailClosed` producer means "Bybit business retCode fail-closed", not full exchange availability. Transport, parse, no-credentials, and signing errors are intentionally not counted by `RetCodeCounter::record_for_error`. Future wording and TODO status should not overclaim this path.

INFO-3: 7d cooling is in-memory and begins when the armed class resolves after a timeout. This matches the current source/test model but remains process-lifetime state, not durable runtime governance.

## Evidence

Source anchors reviewed:

- `rust/openclaw_engine/src/notification_failsafe/incident_policy.rs`
- `rust/openclaw_engine/src/notification_failsafe/providers/single_watcher.rs`
- `rust/openclaw_engine/src/notification_failsafe/dispatchers/three_way.rs`
- `rust/openclaw_engine/src/tasks.rs`
- `rust/openclaw_engine/src/main_boot_tasks.rs`
- `rust/openclaw_engine/src/bybit_rest_client.rs`
- `rust/openclaw_engine/src/live_auth_watcher.rs`
- `rust/openclaw_engine/src/event_consumer/handlers/notification_failsafe_escalate.rs`
- `rust/openclaw_engine/src/event_consumer/tests/c4_failsafe_wire_tests.rs`
- `rust/openclaw_engine/src/bybit_rest_client_tests.rs`

Focused verification already recorded:

```bash
cargo test -p openclaw_engine notification_failsafe::incident_policy --lib
# 15 passed

cargo test -p openclaw_engine event_consumer::tests::c4_failsafe_wire_tests --lib
# 4 passed

cargo test -p openclaw_engine ret_code_counter --lib
# 6 passed
```

Mac and Linux both passed at the preceding source-state checkpoint.

## E2 Decision

Proceed to the next implementation slice, preferably remaining producer coverage, while keeping this ticket partial and explicitly preserving the current C4 owner-boundary model.
