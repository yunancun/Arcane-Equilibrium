# TODO Tail Deferred-Debt Relocation

Date: 2026-06-18
Owner: PM
Scope: TODO/changelog/memory/report hygiene only

## Decision

Move the low-priority tail deferred-debt rows from `TODO.md` §5 active queue to §7 delayed/scheduled observation.

This is not a completion claim. The goal is to keep §5 as the active dispatch queue while preserving each wait condition in §7.

## Rows Moved

- `P2-PACKET-C-C5-GUI-BANNER-ACK-ROLE`: wait for Packet C4 / `failsafe_ack_role` config freeze.
- `P1-OPS-2-HOTRELOAD` / `P2-OPS-2-AUDIT-ENDPOINT` / `P2-OPS-2-CRON-DRIFT` / `P2-OPS-2-RUNBOOK-HEALTHCHECK-SQL` / `P3-OPS-2-RUNBOOK-EMERGENCY-AUDIT-CONTRACT`: Sprint 4+ runbook debt.
- `P1-LG-5`: 90d reviewer-maturity cadence.
- `P1-LEASE-1`: wait for `P0-LG-3` dispatch/closure.
- `P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP`: wait for Phase 2a Demo PASS.
- `P1-INTENTYPE-FIELD-VISIBILITY-DEFER`: wait for PA builder-pattern spec.
- `P3-OPS-4-PG-DUMP-EVENT-EXTEND` / `P3-SUB-AGENT-HYGIENE-SOP-CARGO-TEST-AFTER-ATOMIC`: Sprint bandwidth / SOP debt.

## Rows Intentionally Left In §5

Rows with current operator/action/review gates stayed in §5, including OP-1 dry-run, OPS-4 deploy, TOTP backend, A1/A2 runner, Earn Wave C/D, 110009 semantics, reconciler/D2 review, AC19 decision, and other active work.

## Boundary

No CI, source code change, deploy, rebuild, restart, runtime mutation, DB mutation, auth change, risk change, order change, or trading change.
