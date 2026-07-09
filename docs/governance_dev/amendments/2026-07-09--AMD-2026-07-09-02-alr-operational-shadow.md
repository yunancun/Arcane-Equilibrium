# AMD-2026-07-09-02: ALR Operational Shadow Authorization

Date: 2026-07-09
Status: Accepted
Related ADRs: ADR-0017, ADR-0035, ADR-0049

## Decision

The Operator authorizes the P2 Autonomous Learning Runtime operational shadow loop described in ADR-0049. This supersedes the previous ALR `SOURCE_ONLY_OFFLINE_P0_P1` terminal condition only for the P2 workstream. It does not supersede any trading, live, broker, Cost Gate, or Decision Lease boundary elsewhere in the repository.

Authorized P2 work:

- Rust-scanner snapshot read-adapter, training orchestration, ALR-owned persistence, retention, health/status, tests, migration source, user-level shadow-service source, and operational documentation.
- Mac source/test, isolated database or container testing, and Linux read-only preflight.
- After a fresh exact-scope `PM -> E3 -> BB -> PM` gate: create/apply the isolated `learning.alr_*` migration, start the user-level shadow service, read existing scanner snapshots, write only ALR-owned ledgers/state/artifact tables, and apply ALR-owned derived-cache quarantine/sweep.

## Invariants

1. Rust scanner remains the source of scanner facts and remains evidence only; ALR may not change its cadence, score, registry, subscriptions, or dispatch.
2. Every scanner cycle carries `(ts, scan_id)`, a canonical hash, and a persisted watermark/lineage path. Duplicate or crash-replayed cycles are idempotent, never silently rewritten.
3. ALR outputs are challenger/research artifacts. They cannot auto-serve, promote, overwrite `_latest`, or assert profitable performance.
4. A target with missing proof/reward evidence records `DEFER_EVIDENCE` and rotates to another eligible target; it is not a global stop.
5. Retention is reference-graph first. Sweep is limited to ALR-owned, rebuildable, unreferenced derived cache after quarantine and grace/recheck.
6. Service authority counters must remain zero for exchange, trading, order, Decision Lease, Cost Gate, serving, and promotion surfaces.

## Prohibitions That Remain

- No ALR-initiated Bybit REST/WS, official MCP, order/probe/cancel/modify, Decision Lease, Cost Gate reduction, live/mainnet, RiskConfig/Guardian/order dispatch mutation, scanner trading/proof authority, auto-serving/promotion, or `_latest` overwrite.
- No deletion of orders/fills/fees/slippage, proof/dispute, negative/control/OOS, audit, authorization, risk, reconciliation, or lineage data.
- No P3 Demo outcome production without a separately generated exact-scope candidate, side, order shape, window, loss-control, Decision Lease, E3/BB, and Operator authorization request.

## Gate Sequence

| Gate | Scope | Required evidence |
|---|---|---|
| P2-0 | boundary and queue | ADR/AMD, root TODO, versioned queue, PM role fallback record |
| P2-1 | scanner adapter | source contract for snapshot/cycle/hash/watermark; no scanner mutation |
| P2-2 | persistence source | migration/repository/idempotency/recovery/provenance tests; fresh E3/BB before any apply |
| P2-3..P2-7 | service loop | event-driven shadow behavior, zero authority counters, health and retention controls |
| P2-8 | Linux shadow soak | three real new scanner cycles, durable restart, no duplicate processing, target decision |
| P3-GATE | bounded Demo outcome | stop at `WAIT_OPERATOR_DEMO_AUTH` after emitting the exact request |

## Sign-off

| Role | Status | Basis |
|---|---|---|
| Operator | Accepted | `ALR_OPERATIONAL_COMPLETION_V2` prompt on 2026-07-09 |
| PM | Active | P2-0 operational boundary and queue |
| CC | Conditional approve | Scanner evidence-only and no authority expansion retained |
| FA | Conditional approve | Operational shadow and Demo/profit proof remain distinct |
| PA | Feasible | Existing `trading.scanner_snapshots` is the read source; no scanner mutation |
| E3 / BB | Pending fresh scope | Required before migration apply, service start, or retention sweep |
