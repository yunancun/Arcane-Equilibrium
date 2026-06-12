# P2 Incident-Policy position_drift Producer Coverage

> ticket: `P2-INCIDENT-POLICY-DISPATCH-TRIGGER`
> date: 2026-06-12
> scope: source-only producer coverage for `position_drift`
> boundary: no CI, no deploy/rebuild/restart, no DB/auth/risk/trading mutation

## Decision

`position_drift` is now source-live as a notify-only producer coverage slice.

The producer does not create a new drift definition. It reuses the reconciler's existing source of truth:

- `DriftVerdict` classification from `position_reconciler`;
- `PERSISTENT_DRIFT_CYCLES = 3`;
- `STARTUP_GRACE_MS = 5 minutes`;
- post-orphan/post-ghost `drifts`, so already-handled orphan/ghost entries are not reported as unresolved.

`IncidentClass::PositionDrift` is already `NotifyOnly` in `incident_policy`, so this producer cannot feed `AllFail` into the C4 watcher timer.

## Implementation

Files:

- `rust/openclaw_engine/src/position_reconciler/incident.rs`
- `rust/openclaw_engine/src/position_reconciler/mod.rs`

Runtime behavior:

- tracks unresolved actionable drift keys (`MajorDrift`, `SideFlip`, `Orphan`, `Ghost`) after each successful reconcile cycle;
- ignores `MinorDrift`;
- suppresses and does not accumulate during startup grace;
- reports only after an actionable key remains unresolved for 3 consecutive reconcile cycles;
- includes engine, risk level, unresolved drift count, persistent count, max streak, threshold, and a bounded sample in detail;
- calls `incident_policy::report_resolved(IncidentClass::PositionDrift)` once when the persistent drift clears;
- reports again at local 60s cadence while active, with incident_policy still owning class-level 5m throttle/cooling.

No existing `ReconcilerAction`, `PipelineCommand`, RiskGovernor transition, auth file, DB, order, or exchange write path changed.

## Verification

Mac focused Rust:

- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine position_reconciler::incident --lib` -> 6 passed
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine position_reconciler --lib` -> 94 passed
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine notification_failsafe::incident_policy --lib` -> 15 passed
- `rustfmt --edition 2021 --check rust/openclaw_engine/src/position_reconciler/incident.rs` -> passed
- `git diff --check` -> passed

Workspace-wide `cargo fmt --manifest-path rust/Cargo.toml --all --check` still reports pre-existing formatting drift outside this slice, so it was not used as a gate for this focused change.

## Remaining

Do not mark the ticket complete yet.

Still pending:

- external `engine_dead` watchdog notify-only producer coverage
- BB/E2 focused review for `sm_halt_stuck` + `position_drift`
- E4/QA/full-chain review for expanded producer coverage
- runtime deploy/rebuild/restart only after explicit operator approval

Recommended next work: wire external `engine_dead` watchdog notify-only, then run BB/E2 review over all newly added producer slices before E4/QA/full-chain.
