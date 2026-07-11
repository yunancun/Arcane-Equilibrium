---
status: accepted
date: 2026-07-11
scope: stock_etf_cash IBKR full live-capability development; activation remains separately operator-gated
supersedes: conflicting IBKR capability-development restrictions in ADR-0048, AMD-2026-06-29-01, and AMD-2026-07-08-01; supersedes AMD-2026-07-09-01 before acceptance
---

# AMD-2026-07-11-01: IBKR Stock/ETF Full Live-Capability Development and Explicit Activation Separation

Date: 2026-07-11

Status: **Accepted**

Operator decision: the PM request `IBKR_STOCK_ETF_FULL_LIVE_CAPABILITY_MAX_IMPLEMENTATION_LOOP_V1` is the explicit Operator acceptance for this amendment. No additional Operator permission is needed for the development scope defined here.

Related: ADR-0006, ADR-0033, ADR-0040, ADR-0048; AMD-2026-06-29-01, AMD-2026-07-08-01, AMD-2026-07-09-01.

Scope: `stock_etf_cash` with `broker=ibkr`; readonly, paper, shadow, tiny-live, and live **capability development** only. Options, CFD, margin, short, transfer, and account-management writes remain outside this scope and denied.

## Supersession and interpretation

This Accepted AMD supersedes **only** the conflicting IBKR restrictions in ADR-0048, AMD-2026-06-29-01, and AMD-2026-07-08-01 that prohibited development of live/tiny-live-capable source, production wiring, live secret-slot handling, live transport configuration, or order-lifecycle implementation. Their historical rationale, lane isolation, Rust authority, fail-closed recovery, audit, and non-IBKR boundaries remain in force unless this AMD explicitly changes them.

AMD-2026-07-09-01 was a draft and was never accepted. It is superseded before acceptance; it grants no independent credential-write authority.

**This is a development authorization, not broker activation.** It must never be read as permission to log in, connect a socket, call an IBKR API, request data, place/cancel/replace an order, or create a money effect.

## Decision

The project shall implement a production-wired, live-capable IBKR cash stock/ETF engine for the closed `stock_etf_cash` lane. Allowed no-contact work includes all of the following:

1. Real production callers; Gateway/TWS transport and recoverable session lifecycle; readonly, paper, shadow, tiny-live, and live configuration separation.
2. Fingerprint-only credential-slot and session-attestation handling; account, cash, positions, open orders, executions, fills, commissions, contract details, market-data snapshot/subscription, trading-hours, and entitlement interfaces.
3. Preview/place/cancel/replace, partial-fill/reject/reconnect/reconcile state machines; idempotency, duplicate-event handling, stale-session protection, order-id drift recovery, and unknown-terminal-state fail-closed handling.
4. Rust-owned order/risk authority, Guardian, Decision Lease, global Cost Gate, account/position/notional/order limits, kill switch, audit lineage, DB/evidence, IPC, FastAPI, GUI, observability, rollback, fake-TWS integration, and inactive deployment.
5. Source edits, tests, commits, pushes, three-way synchronization, and inactive deployment that does not contact IBKR.

Python remains control plane and thin IPC only. It may render/request operator workflows but is never broker order/risk authority. GUI state, credential existence, a connected-looking display, or any client request is never authorization.

## Activation and external verification boundary

The default configuration is **inactive**. Missing IBKR credentials, Gateway/TWS session, account, entitlement, market session, or live approval is recorded as `EXTERNAL_VERIFICATION_PENDING`; it blocks only the corresponding real-contact verification, never the remaining source, fake-TWS, GUI, deployment, recovery, or documentation work.

No credential, slot, account, or session auto-activates any mode. Credentials/session never auto-activate. A real broker contact requires a current, Rust-validated `ibkr_activation_envelope_v1` that binds at least:

- `lane=stock_etf_cash`, `broker=ibkr`, target environment and operation scope;
- `BUILD_GIT_SHA`, account fingerprint, Gateway/session attestation and fingerprint;
- risk-config hash and position/notional/order limits;
- global Cost Gate, Guardian, and Decision Lease lineage;
- Operator identity, activation nonce, issued-at, expiry, revocation epoch, and kill-switch epoch.

This requirement applies to every real-contact mode, including readonly and
paper, not only tiny-live/live orders.

Tiny-live and live additionally require an explicit, time-bounded, commit/account/session-bound Operator activation for the exact operation scope. The Rust authority validates the envelope before any transport contact or effect; expiry, mismatch, revocation, reconnect, stale session, unresolved reconciliation, or kill switch fails closed. A valid envelope is necessary but does not waive broker credentials, entitlements, market-hours, or safety checks.

### Activation-authenticity and replay boundary

`ibkr_activation_envelope_v1` is accepted only when Rust verifies a
Rust-owned, authenticated Operator activation record. Its canonical approval
must bind the issuer identity and verification key or immutable approval hash,
the envelope payload digest, activation nonce, and the account/session/build
scope. Rust atomically consumes the nonce before the first permitted contact and
rejects replay, duplicate consumption, stale issue time, expiry, revoked epoch,
or kill-switch epoch mismatch. A reconnect or scope change requires a new
activation; neither an existing session nor a previously valid envelope may be
silently reused.

Python, FastAPI, and the GUI may request or display an activation workflow but
must not create, alter, relay raw authorization material, or attest an Operator
activation. The Phase 2 owner-only read-only seal and its approval are not an
activation authority and cannot be substituted for this record.

### Credential custody boundary

Live-capable implementation preserves secret custody. Only Rust may use a
credential after validation of the activation envelope; Python, FastAPI, GUI,
clients, IPC payloads, databases, and logs must never receive, serialize,
return, or persist credential or activation-secret plaintext. Secret paths are
not client-controlled and must reject symlinks, require a regular owner-owned
file with restrictive mode and owner-only ancestors, and reject environment
variable credential fallback. The Rust transport may emit only a redacted audit
record after validated use. Slot creation or secret replacement is never an
implicit activation.

Until that envelope and the corresponding human-provided session are present, the lane must remain inactive and must not initiate login, socket/API contact, subscription, data request, or order effect. Fake TWS/Gateway and local fixture testing are allowed and are not broker contact.

## Invariants that remain non-negotiable

1. Rust is the sole order, execution, risk, and activation authority; Python/FastAPI/GUI remain control-plane or thin IPC surfaces.
2. Guardian, Decision Lease, global Cost Gate, idempotency, account/session fingerprinting, audit lineage, limits, and kill switch cannot be bypassed or weakened. The global Cost Gate must not be reduced.
3. `margin`, `short`, `options`, `cfd`, `transfer`, and account-management writes remain permanently denied for this lane. New products or capital/legal conflicts require a new Operator decision.
4. Bybit remains the only currently active live execution venue unless and until an IBKR activation envelope is valid for the exact bound session and operation. This AMD does not change Bybit behavior or authority.
5. Default/inactive, paper-capable, and live-capable builds/configuration must be reproducible. A live-capable build is not an active or broker-contacting build.
6. Production code may not hide missing callers behind `allow(dead_code)`, fixtures, templates, previews, fabricated accounts/market/order data, or fake-success assertions.
7. Restart, disconnect, duplicate event, partial fill, rejection, stale session, order-id drift, unknown terminal state, and recovery must fail closed until reconciled from the Rust-owned truth path.

## Required implementation and evidence posture

Implementation proceeds through the current loop backlog W1--W11: sealed-artifact hardening and caller wiring; transport/session and health IPC; account/market/entitlement reads; full order lifecycle and reconciliation; Rust activation/risk/audit; DB/API/GUI/service/observability/rollback; fake-TWS E2E; inactive Linux deployment; and an adversarial global gap rescan.

Every implementation change follows the applicable PM route. Authority/security surfaces add CC/E3, IBKR surfaces add IB, runtime surfaces add OPS, and end-to-end claims add QA. Actual broker contact, paper order, tiny-live order, or live order is external verification, requires the separate activation conditions above, and cannot be proven by source tests.

The only permitted final states are:

- `IBKR_FULL_LIVE_CAPABILITY_COMPLETE_EXTERNAL_ACTIVATION_PENDING` after every no-contact source, production-wiring, test, GUI, inactive-deployment, recovery, documentation, synchronization, and gap-matrix item passes, with only human credentials/session/activation and real receipt pending.
- `IBKR_FULL_LIVE_READY_VERIFIED` after a separately authorized live session and activation yields IB/E3/OPS/QA-attested health, account, market, lifecycle, and money-boundary evidence.
- `HARD_BLOCKED_OPERATOR_DECISION_REQUIRED` only for a new product, funding, or legal conflict not covered here; never for missing credentials, session, Gateway, or market availability.

## Required source-of-truth updates

On acceptance, update `CLAUDE.md`, `README.md`, `CONTEXT.md`, `TODO.md`, `.codex/MEMORY.md`, ADR-0048, the superseded amendments, this specification register, and the documentation/initiative indexes. Those summaries must distinguish capability development from activation and must not portray source readiness as broker authorization.

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | `IBKR_STOCK_ETF_FULL_LIVE_CAPABILITY_MAX_IMPLEMENTATION_LOOP_V1` request | 2026-07-11 | Accepted |
| PM | W0 policy materialization | 2026-07-11 | Active |
| PA | Capability/activation separation design fragment | 2026-07-11 | Accepted input |
