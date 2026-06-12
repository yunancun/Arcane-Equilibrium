# P2 Incident-Policy sm_halt_stuck Producer Coverage

> ticket: `P2-INCIDENT-POLICY-DISPATCH-TRIGGER`
> date: 2026-06-12
> scope: source-only producer coverage for `sm_halt_stuck`
> boundary: no CI, no deploy/rebuild/restart, no DB/auth/risk/trading mutation

## Decision

`sm_halt_stuck` is now source-live as a producer coverage slice.

Implementation uses Rust runtime HaltSession state as the source of truth:

- `TickPipeline.halt_kind`
- `TickPipeline.halt_set_ts_ms`
- `paper_paused` / `session_halted` only as diagnostic detail

The producer intentionally does not read passive healthcheck `[69]`. The PA spec's `[69]H4` reference is stale in the current repo; `[69]` is now a WP-03 deploy-gate selector, not SM halt-stuck.

## Implementation

Files:

- `rust/openclaw_engine/src/event_consumer/sm_halt_incident.rs`
- `rust/openclaw_engine/src/event_consumer/loop_handlers.rs`
- `rust/openclaw_engine/src/event_consumer/mod.rs`

Runtime behavior:

- observes active HaltSession after every `pipeline.on_tick()`;
- observes again after the 60s lease/auth sweep, so stuck halt state still feeds while ticks are sparse;
- feeds `IncidentClass::SmHaltStuck` through existing `incident_policy::spawn_report_incident`;
- uses a 5s producer cadence while active; incident policy still owns the 120s sustained arm window;
- calls `incident_policy::report_resolved(IncidentClass::SmHaltStuck)` once when HaltSession clears;
- operator IPC pause is not reported because it has `halt_kind=None` by design.

No C4 owner handler, set_trading_stop path, RiskGovernor transition, auth file, DB, or exchange write path changed.

## Verification

Mac focused Rust:

- `cargo test -p openclaw_engine sm_halt_incident --lib` -> 5 passed
- `cargo test -p openclaw_engine notification_failsafe::incident_policy --lib` -> 15 passed
- `cargo test -p openclaw_engine event_consumer::tests::c4_failsafe_wire_tests --lib` -> 4 passed
- `cargo test -p openclaw_engine tick_pipeline::tests::halt_ttl --lib` -> 20 passed
- `cargo test -p openclaw_engine ret_code_counter --lib` -> 6 passed

## Remaining

Do not mark the ticket complete yet.

Still pending:

- `position_drift` notify-only producer coverage
- external `engine_dead` watchdog notify-only producer coverage
- BB/E2/E4/QA/full-chain review for the expanded producer coverage
- runtime deploy/rebuild/restart only after explicit operator approval

Recommended next work: wire `position_drift` notify-only if reconciler source is stable; otherwise run BB/E2 focused review on this `sm_halt_stuck` slice before adding another producer.
