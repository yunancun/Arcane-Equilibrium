# ADR 0049: Scanner-Driven ALR Operational Shadow

Date: 2026-07-09
Status: Accepted

## Context

P0/P1 established source-only ALR contracts, but intentionally stopped before durable ingestion, a service process, or a learning-owned persistence surface. That source-only stop is historical evidence, not the operational P2 terminal state.

The Rust scanner already persists each completed cycle as an immutable source record in `trading.scanner_snapshots`. Its natural key is `(scan_id, ts)`, while ADR-0017 keeps scanner ranking as evidence only.

## Decision

1. ALR P2 is a local, user-level shadow runtime. It consumes existing Rust scanner snapshots read-only and must not alter scanner cadence, scoring, registry membership, websocket subscriptions, or dispatch.
2. The scanner adapter identifies a source cycle by `(ts, scan_id)`, binds a canonical content hash, and advances a durable watermark only through an ALR-owned append-only ledger. Recovery re-reads a bounded overlap and lets the ledger's idempotency key suppress duplicates.
3. `trading.scanner_snapshots` supplies intake evidence, not target proof, trading authority, serving authority, or a PnL assertion. ALR retains negative/control/OOS evidence and distinguishes fact, inference, and hypothesis.
4. P2 persistence is limited to new `learning.alr_*` tables. It is append-only, preserves raw source payload plus hashes, and records target, dataset, training, evaluation, feedback, retention, and state lineage.
5. The shadow service is event/backlog/novelty driven. It is not a cron job or fixed-time learning scheduler. Backpressure, a single-instance lock, resource limits, graceful shutdown, and fail-closed recovery are required.
6. Training and statistical evaluation may produce a challenger artifact only. ALR cannot serve, promote, overwrite `_latest`, mutate RiskConfig/Guardian, acquire a Decision Lease, or make a trading decision.
7. Retention is two-phase: reference graph, quarantine, grace/recheck, then sweep. A sweep may remove only ALR-owned, rebuildable, unreferenced derived cache. Orders, fills, fees, slippage, proof, dispute, negative/control/OOS, audit, authorization, risk, reconciliation, and lineage data are never ordinary-delete candidates.

## Operational Gates

- Source and isolated-container tests may proceed under this ADR.
- Before creating or applying the P2 migration, starting the service, beginning sustained Linux runtime consumption, or applying retention, PM must obtain a fresh scoped `PM -> E3 -> BB -> PM` approval and record the exact source/runtime heads.
- Linux read-only preflight is allowed only within the current P2 scope; it grants no Bybit contact, order, probe, Cost Gate, Decision Lease, or proof authority.
- Deployment requires Mac/GitHub/Linux source-head alignment, an idempotent migration dry-run, a rollback plan, and post-start authority counters of zero.

## Explicit Non-Goals

- No Bybit REST/WS or official MCP calls by ALR.
- No order/probe/cancel/modify, live/mainnet, Decision Lease, Cost Gate change, risk/Guardian mutation, scanner trading/proof authority, model serving/promotion, or `_latest` overwrite.
- No claim of profit without candidate-matched, after-cost, controlled OOS proof.

## Consequences

P2 may close a durable local learning shadow loop without opening a trading path. `DONE_OPERATIONAL_SHADOW` requires the P2 queue's scanner ingestion, persistence, service, training/evaluation, feedback, retention, health, restart-recovery, Linux soak, and adversarial audit criteria; it is separate from the P3 bounded Demo authorization gate.

## 2026-07-10 V3 Freshness And Learning Completion Addendum

This addendum preserves the original ADR and AMD-2026-07-09-02 as historical authorization records, but supersedes their P2-8 completion interpretation. The prior `DONE_OPERATIONAL_SHADOW` state is invalid because steady-state fresh ingestion was later falsified. Current completion truth follows AMD-2026-07-10-02 and ALR P2 queue v2.

### Freshness And Health

1. Notification consumption preserves the exact `(scan_id, ts)` identity. A notification is wake/identity only; it is never the scanner payload, proof, reward, or trading authority.
2. A durable live watermark performs bounded catch-up for missed or coalesced notifications. Fresh/live and historical backfill lanes use independent persistent cursor/state; fresh is always serviced first, while historical work is capped and low priority. Normal operation cannot depend on temporary `ALR_RECONCILE_AFTER` state or a service drop-in.
3. Health persists `raw_latest_ts`, `alr_latest_source_ts`, `ingest_lag_seconds`, `fresh_raw_only_count`, `historical_backfill_remaining`, notification received/consumed/invalid counts, `last_success_at`, and real failure/restart counters. Untrained work is not an ingestion-gap proxy, and failure/restart counts cannot be hard-coded to zero.

### Acceptance

The acceptance surface includes 79k+1 fresh-priority behavior; duplicate, out-of-order, late, coalesced/missed notification handling; crash/restart and watermark recovery; concurrent single-instance enforcement; starvation resistance; forced raw-only health alarms; scanner SELECT-only access; and false/zero authority counters.

Runtime completion requires at least ten consecutive natural Rust scanner cycles with no temporary cursor, bounded-latency raw/ALR identity equality, `fresh_raw_only_count=0`, duplicate `0`, and an advancing ALR source timestamp. The window must survive one ALR-only service restart without restarting the engine. Any failed window is repaired and restarted from cycle one.

### Learning, Retention, And Terminal Truth

Scanner evidence may select a research object, but training labels/rewards require candidate-matched point-in-time lineage, `proof_packet_v1`, `reward_ledger_v1`, actual fee/slippage/funding, reconstruction, and an after-cost label. Evaluation requires walk-forward, purge/embargo, OOS, matched controls, and negative cells. Eligible evidence must produce an actual run with `model_training_performed=true`; outputs remain challenger-only and never auto-serve, auto-promote, or overwrite `_latest`.

Retention remains reference-graph-first and may delete only ALR-owned, rebuildable, unreferenced derived cache after quarantine and grace/recheck. If production has no eligible cache, the truthful result is `NOT_EXERCISED_NO_ELIGIBLE_CACHE`, not a claimed sweep.

The only normal terminal is `DONE_FRESH_OPERATIONAL_LEARNING_SHADOW`. When all safe sources are proven insufficient for a qualified label, the only alternative terminal is `WAIT_OPERATOR_DEMO_AUTH_EXACT`, and it requires a new executable-but-unauthorized exact packet. The current exact packet is `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-10--alr_f5_exact_demo_authorization_packet.json`, SHA-256 `1ab349a6f753e4d3846b0699d7404f18e231d8ca95b8f250bb19b9f89b7eabde`, with Operator authorization false, execution false, and hash-bound E3/BB approval for Operator decision only.

Neither this ADR, the alternative terminal, nor the packet grants exchange contact, order/probe/cancel/modify/close, Decision Lease, Cost Gate, live/mainnet, Guardian/RiskConfig mutation, proof, serving, promotion, or `_latest` authority. Protected fill/order/cost/proof/control/OOS/audit/authorization/risk/reconciliation/lineage evidence remains non-deletable, and all authority maps/counters remain false/zero.

## 2026-07-10 Global Qualified Autonomous Learning Shadow V1 Addendum

AMD-2026-07-10-03 supersedes only the preceding addendum's terminal and exact
SUI packet binding. The fresh-lane, truthful-health, adversarial,
qualified-learning, retention, and hard-boundary clauses above remain active.
The historical SUI packet SHA `1ab349a6...abde` is now
`ROTATED_UNCONSUMABLE_STALE_PACKET`: it binds source `091b5d446...`, while the
WP0 baseline observed Mac/origin/Linux at `1a3ecdd579...` and the running ALR
service pin at `8dfa1200a...`; its E3/BB reviews were presentation-only and are
stale. Operator decision is no longer requested for that packet.

The active completion truth is the G1-G9 contract in AMD-2026-07-10-03 and the
canonical Goal queue under
`docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/2026-07-10--global_qualified_autonomous_learning_shadow_v1/`.
`WAIT_OPERATOR_DEMO_AUTH_EXACT`, `DEFER_EVIDENCE`, no eligible cache, source-only
completion, and backlog exhaustion are nonterminal. `CHALLENGER_ACCEPT` remains
isolated learning state and grants no serving, promotion, `_latest`, risk,
Decision Lease, exchange, or order authority.

Any future candidate-matched Demo evidence acquisition is a separate external
effect: it requires a current qualified candidate, fresh SHA-bound E3/BB and
Operator approval, and same-window Rust/Guardian/Decision-Lease/GUI RiskConfig,
equity, BBO/instrument/order shape, disaster-protection, audit, and
reconstruction gates. The Goal itself grants none of that authority.

## 2026-07-21 Accepted Advisory-Serving Authority Pointer

ADR-0051 and AMD-2026-07-21-01 are Accepted S0.2 source-policy authority. They
supersede only the overbroad interpretation that this actor-specific denial
permanently forbids a separate hash-bound Rust consumer; this ADR and
AMD-2026-07-09-02/07-10-02/07-10-03 remain current historical authority for
ALR, trainer, controller and challenger no-serving/no-promotion, `_latest`,
broker, order, lease, risk and direct-apply denials. The immutable dependency is
`docs/execution_plan/ai_ml_landing/receipts/S0.2-serving-authority-receipt-v1.json`;
S0.3 must consume that exact receipt rather than infer adoption from ADR/AMD
status. S0.2 has no runtime, deploy, migration, PostgreSQL, broker or order
effect, implements no ML5/ML6, and cannot claim `PROGRAM_ADOPTED`.
