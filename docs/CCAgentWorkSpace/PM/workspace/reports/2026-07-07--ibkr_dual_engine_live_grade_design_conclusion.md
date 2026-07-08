# IBKR Dual Engine Live-Grade Design Conclusion

Date: 2026-07-07
Role: PM local design conclusion
Scope: IBKR `stock_etf_cash` engineering direction

## Conclusion

Operator clarified the intended IBKR shape: mirror the current Bybit
Demo/LiveDemo/Live architecture, not a two-paper-engine-only design.

The accepted design direction is:

- `ibkr_demo_engine`: demo/paper endpoint profile for validation, sample
  collection, paper order lifecycle rehearsal, and evidence generation.
- `ibkr_live_engine`: live-grade engine profile for local gate/risk/session
  testing now, with possible future true-live API binding only after live
  gates and the required governance update pass.

This conclusion changes the engineering target shape, not current runtime
authority. Under current ADR-0048 / AMD-2026-06-29-01, true IBKR live contact
and live execution still require a future ADR/AMD or equivalent governance
update before activation.

## Engine Shape

### `ibkr_demo_engine`

- Endpoint profile: `paper_demo`.
- API capability: paper read/write is acceptable.
- Purpose: validation, sample collection, paper lifecycle, shadow/evidence
  loops.
- Risk profile: demo-style, still bounded and auditable.
- Denied actions: withdraw, transfer, account-management writes, margin, short,
  options, CFD unless future governance explicitly changes scope.

### `ibkr_live_engine`

- Endpoint profile: `live_reserved` / live-grade profile.
- Current use: local live-grade gate/risk/session rehearsal, optionally against
  paper endpoint while true live credentials are absent.
- Future use: may bind true live API if the operator later provides it and the
  live governance gates pass.
- Risk profile: live-style, including sticky halt, stricter exposure/loss
  controls, Decision Lease, Guardian, authorization, audit, idempotency, and
  reconciliation.
- Default posture: no true-live authority until live gates pass.

## Secret And Capability Interface

The agent does not need secret contents. Engineering should expose only:

- slot identity,
- selected endpoint profile,
- capability flags,
- fingerprint/hash metadata,
- permission/status evidence.

Default interface may be read-write capable for IBKR API, but withdraw and
transfer surfaces must not exist or must remain typed-denied. Secret creation,
credential issuance, and API-side permission control remain operator-managed.

## Session And Port Model

The two engines need distinct runtime identities:

- distinct session slot,
- distinct client id,
- distinct endpoint profile,
- distinct audit/session epoch.

Port assignment should follow the repo/runtime port map and existing Bybit
service layout after a source/runtime port audit. Do not hard-code speculative
IBKR ports in production code; capture them in config and Phase2 topology
evidence.

## Phase2 Seal And Latency

The Phase2 seal must not be a per-order expensive operation.

Correct model:

- Seal once per session/admission epoch.
- Re-seal on startup, reconnect, credential rotation, endpoint profile change,
  policy/capability change, topology change, or TTL expiry.
- Per call, perform only a lightweight cached check:
  - current session epoch is valid,
  - capability permits the action,
  - Decision Lease is active where required,
  - Guardian/risk gates pass,
  - idempotency/audit append path is available.

This keeps the order path live-grade without adding avoidable per-call seal
latency.

## Boundary

This conclusion does not authorize:

- IBKR true-live contact,
- live order execution,
- credential inspection,
- Gateway/TWS startup,
- connector runtime,
- paper/live API calls,
- withdraw or transfer,
- Bybit order-path reuse,
- runtime MCP execution.

It authorizes the next no-contact engineering design direction only: build the
IBKR source contracts and fixtures around a dual-engine shape that can later be
bound to real paper/live credentials through gates.

## Supersedes

This report supersedes the narrower "two paper API only" interpretation from
the prior operator-verification discussion. It does not supersede ADR-0048's
current true-live denial; that requires a future governance update before any
real IBKR live activation.
