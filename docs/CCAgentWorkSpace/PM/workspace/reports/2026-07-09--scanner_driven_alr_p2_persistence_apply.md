# ALR P2-2 Existing-PG Apply

Date: 2026-07-09
Work item: `P2-2-ALR-PERSISTENCE-APPLY`
Status: `ADVANCED`
Execution mode: `ROLE_FALLBACK_SINGLE_SESSION`

## Applied Evidence

Mac, GitHub, and Linux were aligned at `9732dd362`, and Linux was clean. V151
sha256 `294d7ed0...` dry-ran then applied once to existing PostgreSQL. Reflection
confirmed the five ALR-owned tables and required indexes. The bounded repository
read one existing scanner cycle, persisted it, recorded a duplicate event, and
rebuilt its restart state. ALR counts are `3/1/2/1/1` for
artifact/source/ingest/watermark/edge.

## Boundary

No scanner source table mutation, service start, exchange contact, order,
Decision Lease, Cost Gate, proof, serving, promotion, retention sweep, or
`_latest` action occurred. The one scanner cycle is evidence-only, not proof or
profit evidence.

## Next State

P2-3 requires a fresh service/event-consumer gate. Existing PG has no
`trading_ai` role, so the approved user-service DB identity and least-privilege
contract must be resolved before a service can start.
