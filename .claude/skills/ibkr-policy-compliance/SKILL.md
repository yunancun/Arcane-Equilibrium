---
name: ibkr-policy-compliance
description: Reviews IBKR/TWS compatibility, ADR-0048 phase gates, session and entitlement semantics, paper/shadow effect classes, and typed live denials. Use when a task mentions IBKR, TWS, stock_etf_cash, broker session topology, market-data entitlement, read-only probe, paper order lifecycle, or IBKR policy/cost drift.
allowed-tools: Read, Grep, Glob, Bash, WebSearch, WebFetch
---

# IBKR Policy And Compatibility Review

## Boundary first

- Reviewer role is `IB(explorer)` and read-only.
- It never opens TWS/socket/API contact, reads secrets, submits/cancels/replaces an
  order, mutates account state, or grants a phase gate.
- Contact/effect uses `broker_probe_adapter_v1` only after a lane-specific
  approved intent.
- ADR-0048 read-only/paper/shadow scope remains separate from Bybit. IBKR
  live/tiny-live, margin, short, options/CFD, transfer, and auto-promotion remain
  typed denied unless a future normative decision changes them.

## Authority and freshness

Use the typed authority matrix:

- normative permission: `CLAUDE.md`, ADR-0048, active AMD/operator decision
- implementation: Rust schema/client, contracts, tests
- active state: `TODO.md`
- runtime: timestamped TWS/session/artifact observation
- external policy: current official IBKR documentation verified when material
- claim proof: hash-pinned gate/probe/closure artifacts

Cross-class disagreement is DRIFT/CONFLICT. Runtime connectivity cannot create
permission. Official-policy facts require a verified source/time; do not rely on
profile memory.

## Review workflow

1. Bind lane, broker, environment, phase, contact class, effect class, and exact
   source/runtime baseline.
2. Verify prerequisite artifact hashes and the active external-surface gate.
3. Check TWS/Gateway topology: loopback/host/port/client-id ownership,
   reconnect/session expiry, duplicate-client collision, and fail-closed state.
4. Check authentication/secret slot/redaction without exposing values.
5. Check account fingerprint, permissions, paper/read-only posture, and typed
   denial of live/account-write operations.
6. Check market-data entitlement, delayed/live semantics, pacing/rate budgets,
   subscription lifecycle, timeout/error normalization, and audit lineage.
7. Check contract/instrument identity, exchange/currency/calendar/corporate-action
   mapping and point-in-time provenance.
8. For paper effect design, check preview vs effect separation, idempotency,
   submit/cancel/replace lifecycle, reconciliation, fills, fees/taxes/FX, and
   source/runtime authorization distinction.
9. Separate states explicitly: source-ready, external-gate-ready, session-ready,
   entitlement-ready, runtime-active, effect-authorized, evidence-producing.
10. Produce verdict and denial list; request a Probe Adapter intent when real
    contact evidence is required.

## Required negative tests

- BB/Bybit evidence cannot satisfy an IBKR gate.
- A localhost/TWS configuration string cannot prove a live session.
- A connected session without entitlement cannot prove usable market data.
- Read-only probe success cannot authorize paper writes.
- Paper lifecycle success cannot authorize live/tiny-live.
- Missing/stale host, environment, observed_at, expiry, or digest is UNVERIFIED.
- Client/UI-provided lane state is untrusted authority.

## Output

Return immutable `role_fragment_v1` with `payload_kind=gate_fragment_v1`: work status, gate verdict, phase/contact/
effect class, facts/inferences/assumptions, official-policy freshness, evidence
scope/hashes, typed denials, unverified surfaces, consumption availability, and
next owner/Adapter intent. Do not write a role report or memory.
