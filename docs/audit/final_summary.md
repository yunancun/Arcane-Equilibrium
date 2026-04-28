# Final Audit Summary

Generated: 2026-04-28
Inputs: `docs/audit/audit.md` and segment audit artifacts; cross-checked against `docs/audit/remediation_groups.md` during integration.

## Executive Summary

The full non-test code audit reviewed the repository inventory, entry points, live/paper boundaries, execution and reconciliation, risk controls, secrets, database writes, strategy/agent flow, ML/model registry, schedulers, dashboards/APIs, and operator scripts.

Confirmed findings: 62 total.

- P0: 0
- P1: 29
- P2: 29
- P3: 4

The dominant risk is not one isolated bug. It is fragmented control of live/exchange mutations, risk state, credentials, and durable trading records across Rust, FastAPI, shell scripts, cron, launchd, and DB writers. Before any further live expansion, the system needs one enforced live-write boundary, fail-closed configuration behavior, durable trading lifecycle persistence, and consistent operator authorization on write surfaces.

## Highest-Risk Themes

1. Live/exchange writes can bypass the intended control plane.
   Key findings: LP-001, OE-007, RC-001, OS-001, SW-002.

2. Trading lifecycle records can be lost or misrepresented.
   Key findings: OE-001, OE-002, OE-003, OE-004, DBW-001, DBW-002, DBW-003, DBW-005, OS-002.

3. Risk controls and configs have fail-open or split-brain behavior.
   Key findings: RC-002, RC-004, RC-005, RC-006, SADF-002, SADF-003.

4. API authorization and secrets are inconsistent across critical surfaces.
   Key findings: SC-001, SC-002, SC-003, DAPI-001, RC-003, DAPI-006, DAPI-003, DAPI-004, DAPI-005.

5. Runtime/operator automation can race, duplicate, or kill the wrong process.
   Key findings: SW-001, SW-003, SW-005, SW-006, DAPI-007, OS-003, OS-004, OS-005.

6. ML and learning artifacts are not yet safe as authoritative decision inputs.
   Key findings: MLM-001, MLM-002, MLM-003, MLM-004, MLM-005, SADF-004, SADF-005, SADF-006.

## Recommended Fix Order

### 1. Live Write Boundary Freeze

Goal: no live/mainnet mutation path should exist outside the same signed, mode-aware, operator-authorized control boundary.

Fix first:

- LP-001: require exact `live_reserved` before signing or renewing live authorization.
- OE-007 and OS-001: remove or separately hard-gate direct REST live fallback and shell live flatten paths.
- RC-001: make emergency flatten exchange-aware before local state is marked flat.
- SW-002: ensure live respawn refreshes all live command senders, or uses dynamic command slots.

Exit criteria: every live write, close, flatten, cancel, and reduce-only path proves current signed authorization, current live mode, operator authority, and Rust/live-engine ownership or an explicitly separate emergency authorization.

### 2. Critical Auth And Secret Lockdown

Goal: eliminate unauthenticated or weakly authenticated mutation and remove known credential exposure paths.

Fix next:

- DAPI-001, RC-003, DAPI-006: enforce shared operator/scope dependencies on all state-changing routes.
- SC-001 and SC-002: stop printing operator-capable tokens and reject blank/placeholder GUI passwords.
- SC-003: remove and rotate the committed Grafana FastAPI bearer credential if it was ever valid.
- DAPI-003, DAPI-004, DAPI-005, DAPI-002: strip forwarded cookies and protect dashboard/model/DB detail routes.
- SC-004, SC-005, SC-006, SC-007: move runtime secrets out of argv/env/templates and harden cookie/proxy behavior.

Exit criteria: write routes are operator-gated by default, public routes expose only minimal liveness, and repository/log/process surfaces contain no reusable privileged credentials.

### 3. Durable Trading And Audit Trail Repair

Goal: prevent dropped or duplicated trading facts and make restart restore reconstruct exchange reality.

Fix after the live/auth freeze:

- OE-001: parse and dispatch all private WS records in each Bybit batch message.
- OE-002: emit dispatch-failure terminal events and clear pending/pending-close state on failed sends.
- OE-003 and DBW-003: stop clearing writer buffers on insert failure; add retry or durable outbox.
- DBW-002: centralize critical channel sends and expose drop counters or use awaited/durable send paths.
- OE-004: persist exchange fills using Bybit `exec_id` as durable idempotency input.
- DBW-001 and DBW-005: move `V999__exit_features.sql` into real migration order and make explicit auto-migrate fail closed on `NoPool`.
- OE-005, OE-008, OE-009: tighten fill attribution, partial-failure reporting, and risk-verdict schema fidelity.

Exit criteria: a DB outage, channel full condition, REST failure, or multi-record WS payload cannot silently erase or misstate the trading lifecycle.

### 4. Risk And Config Fail-Closed Pass

Goal: missing config, stale state refreshes, or rejected updates should not weaken risk enforcement.

Fix next:

- RC-004 and SADF-003: fail closed for missing/broken live/demo risk and strategy configs.
- RC-002: preserve cooldown and kill-switch state during periodic H0 refresh.
- RC-005: apply risk governor cascades and `constraints_for()` consistently at order admission.
- RC-006: deprecate or acknowledge legacy `update_risk_config` application results.
- SADF-002: make strategy parameter updates atomic.
- LP-002: fix restart script Cargo package ID so recovery scripts can actually rebuild.

Exit criteria: Demo/Live never start with silent default-active strategy or shadow risk behavior because of missing config, and every accepted risk mutation has an applied-state acknowledgement.

### 5. Operator Automation And Runtime Ownership

Goal: operator tools should be idempotent, service-manager aware, and safe under watchdog/cron/API multi-worker behavior.

Fix next:

- SW-001 and OS-004: protect clean/fresh maintenance windows with maintenance leases, traps, and stale-alert behavior.
- OS-002: require DB/environment-specific destructive reset confirmation that wrappers cannot auto-generate.
- OS-003: replace broad `pkill -f` and port kills with PID/service/cwd validation.
- DAPI-007: remove API-worker self-restart and route restart through managed service tooling.
- SW-003, SW-005, SW-006, SW-007: add leader election or locks for duplicate schedulers, monitors, cron jobs, and telemetry writers.
- OS-005, OS-006, OS-007: add deployment preflight, least-privilege DB bootstrap, safe SQL/password quoting, and robust report JSON encoding.

Exit criteria: planned maintenance cannot race watchdog restart, scripts cannot wipe the wrong DB or kill unrelated processes, and multi-worker API startup cannot duplicate stateful background jobs.

### 6. ML And Agent Decision Integrity

Goal: keep ML, LinUCB, and Teacher outputs observational or clearly bounded until schema, promotion, and reward loops are coherent.

Fix after core live/data/risk safety:

- MLM-001 and MLM-003: enforce feature definition/schema hashes in runtime loading and training data selection.
- MLM-002: promote ONNX quantile trios atomically as one serving unit.
- MLM-004: make labels provisional until full close quantity coverage is known.
- MLM-005: unify LinUCB arm-space definitions and load compatible persisted state at runtime.
- SADF-001, SADF-004, SADF-005, SADF-006: route Teacher directives to explicit active targets, align LinUCB metadata with accepted decisions, mark no-op directives as non-success, and add release-mode Live promotion guards.

Exit criteria: no model, arm state, label, or Teacher directive is represented as production-effective unless runtime behavior and persisted audit state prove it.

## Suggested Execution Batches

Batch A, live blocker: close sections 1 and the P1 subset of section 2. Do this before any live/mainnet expansion.

Batch B, trading record integrity: close section 3. This should land before relying on reconciliation, dashboards, or ML labels for decisions.

Batch C, fail-closed runtime: close section 4. This turns config and risk behavior into predictable startup/admission contracts.

Batch D, operator/runtime hygiene: close section 5. This reduces incident risk during deploys, restarts, cron, and multi-worker API operation.

Batch E, learning correctness: close section 6. This prepares ML/agent components for higher autonomy without making them silently authoritative too early.

## Immediate Release Gate

Treat the following IDs as live-release blockers until fixed or explicitly accepted with a compensating control:

LP-001, OE-001, OE-002, OE-003, OE-004, OE-007, RC-001, RC-002, RC-003, RC-004, RC-005, SC-001, SC-002, SC-003, DBW-001, DBW-002, DBW-003, SADF-001, SADF-003, SW-001, SW-002, DAPI-001, OS-001, OS-002.
