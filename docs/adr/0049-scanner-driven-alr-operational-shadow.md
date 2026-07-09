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
