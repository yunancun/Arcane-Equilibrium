# ADR 0018: Funding Arb V2 Remains Disabled Pending Audit

Date: 2026-05-09
Status: Accepted with deferred final retirement

## Context

`funding_arb` produced poor demo evidence and operational noise. Current risk
configs prevent new funding_arb entries while preserving tighter handling for
legacy positions. TODO still requires a 2026-05-16 14d audit before final
retention or schema removal decisions.

## Decision

Keep funding_arb new entries disabled across active runtime configs until the
2026-05-16 audit and `P0-DECISION-AUDIT-4` operator strategy verdict.

Do not treat this ADR as approval to delete RiskConfig schema or permanently
retire all funding_arb code.

## Consequences

- W-AUDIT-6 may prepare the cleanup plan, but final deletion waits for operator
  strategy verdict.
- Replay/ML/training consumers should not promote funding_arb from immature or
  contaminated samples.
- Existing positions or historical rows remain auditable.
