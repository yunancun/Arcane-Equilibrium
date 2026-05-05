---
status: accepted
---

# Trading intents flow through a Decision Lease state machine, not direct execution

Per SM-02, every controlled trading intent is wrapped in a Decision Lease object with a 9-state lifecycle (`DRAFT / REGISTERED / ACTIVE / BRIDGED / FROZEN / REVOKED / EXPIRED / REJECTED / CONSUMED`), per-intent TTL of 0.1–300s, and an audit-only writer path. AI output never becomes a live order — it becomes a Lease that must be activated, risk-approved by Guardian, bridged downstream, and consumed, all auditable.

## Consequences

Decision Lease is per-intent and complements EarnedTrust T0–T3 session Authorization (24h–360h, SM-01) — the two are orthogonal, not interchangeable. The Path A retrofit (commit `dbcf845b`, 2026-05-03) wired the Rust facade and router gate; the feature flag `OPENCLAW_LEASE_ROUTER_GATE_ENABLED` ships default OFF for canary, so production behavior is currently unchanged until promotion.
