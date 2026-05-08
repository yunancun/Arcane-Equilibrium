# ADR 0016: Decision Lease Router Flag May Run as Shadow Evidence

Date: 2026-05-09
Status: Accepted

## Context

AMD-2026-05-02-01 originally planned the Decision Lease router flag flip after a
later edge review. During W-C, the operator authorized earlier evidence
collection on Linux `trade-core`.

## Decision

`OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` may remain enabled for W-C / MAG-082
Stage 2 evidence collection when paired with
`OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow`.

The flag is evidence-only in this posture: it writes lease/bypass lineage into
shadow Agent Spine ExecutionPlan rows. It does not authorize true live,
Mainnet, Executor submit authority, scanner authority, strategy/risk mutation,
MAG-083, or MAG-084.

## Consequences

- W-C can collect runtime lineage before MAG-083/MAG-084.
- The 24h MAG-082 window still must PASS.
- Rollback requires setting the flag back to `0` and rebuilding/restarting only
  with explicit operator approval.
- Durable authorization is recorded in
  `docs/governance_dev/2026-05-08--w_c_lease_router_authorized.md`.
