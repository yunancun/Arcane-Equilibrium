# ADR 0015: OpenClaw Is Control Plane and Gateway, Not Trading Conductor

Date: 2026-05-09
Status: Accepted

## Context

The project was renamed to `玄衡 · Arcane Equilibrium`, while OpenClaw remains
the service-family name for the Control Console, Gateway, API aggregation, and
operator communication surfaces.

## Decision

OpenClaw is not the trading brain, not a second GUI, and not a hot-path trading
conductor. The canonical trading authority remains Rust `openclaw_engine`.
The canonical operator GUI remains the existing FastAPI OpenClaw Control
Console at `trade-core:8000/console`.

External OpenClaw Gateway may relay briefs, diagnostics, proposals, approvals,
and channel events, but any trading side effect must re-enter TradeBot
governance and Rust execution authority.

## Consequences

- No separate OpenClaw trading GUI is introduced.
- OpenClaw Gateway does not hold Bybit credentials.
- Gateway outage must degrade communication only, not stop the runtime engine.
- Proposal and approval routes remain relay/audit surfaces, not order authority.
