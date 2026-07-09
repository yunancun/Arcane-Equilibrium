# E3 Review - ALR P2-3 Event Consumer Scope

E3_VERDICT: APPROVE_FOR_PM_BB_P2_3_SCOPE_REVIEW
CONFIDENCE: medium-high

Reviewed request:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-09--scanner_driven_alr_p2_event_consumer_e3_request.json`

## Read-Only Evidence

- Mac, GitHub, and clean Linux all resolve to `beb555567`.
- Rust scanner persistence currently sends `TradingMsg::ScannerSnapshot` to the
  writer and inserts rows, but has no `NOTIFY`/`LISTEN` producer.
- Existing PG has no `trading_ai`, `alr_*`, or `ncyu` database role; V151 tables
  are owned by `trading_admin`.
- Existing user services do not include an ALR unit.

## Required Security Design

| Severity if violated | Attack path | Required control |
|---|---|---|
| HIGH | ALR service using `trading_admin` can exceed the ledger boundary. | Dedicated non-superuser login; only CONNECT, schema USAGE, scanner SELECT, and ALR SELECT/INSERT; explicitly revoke UPDATE/DELETE and no role inheritance. |
| HIGH | Scanner notification changes availability or leaks payload. | Notify only after successful snapshot persistence; payload contains a non-secret source identity/hash reference only; notification failure is warn-only and does not retain/replay scanner buffer. |
| HIGH | Polling/timer becomes an uncontrolled learner. | LISTEN plus notification-triggered bounded drain; startup reconciliation only; no cron, systemd timer, fixed periodic work, or unbounded backlog loop. |
| MEDIUM | Multiple service instances race or consume excess data. | Advisory lock plus process lock, bounded batch/concurrency/resource budget, transaction rollback, and graceful SIGTERM drain. |
| MEDIUM | Restarting an unrelated runtime surface broadens scope. | Rebuild/restart only the Rust writer/engine after source review, current head alignment, and explicit service-unit verification; no API/watchdog/config change. |

## Gate Conditions

This review authorizes source implementation and isolated tests only. Role/secret
provisioning, engine rebuild/restart, and service start require the implemented
diff, E2/E4/QA results, a fresh three-head/clean recheck, and a second E3
prestart verification of exact privileges/unit contents. No trading or broker
authority is approved.

E3 role memory is pre-existing dirty and was not edited.

E3 AUDIT DONE: 0 CRITICAL / 0 HIGH / 0 MEDIUM in the constrained source scope.
