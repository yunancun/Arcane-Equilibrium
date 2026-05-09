# ADR 0018: Funding Arb V2 Retires From Active Strategy Set

Date: 2026-05-09
Status: Accepted - retire from active strategy set

## Context

`funding_arb` produced poor demo evidence and operational noise. Current risk
configs prevent new funding_arb entries while preserving tighter handling for
legacy positions. `P0-DECISION-AUDIT-4` selected the PA-recommended strategy
verdict: retire `funding_arb` from active promotion and clean it from active
RiskConfig schema in W-AUDIT-6.

## Decision

Keep funding_arb new entries disabled across active runtime configs and retire
it from active strategy promotion. W-AUDIT-6 may remove active RiskConfig
schema entries after targeted source/test cleanup.

The 2026-05-16 audit remains a verification artifact for historical impact and
legacy-row handling, not the retirement decision gate.

## Consequences

- W-AUDIT-6 may implement active RiskConfig cleanup.
- Replay/ML/training consumers should not promote funding_arb from immature or
  contaminated samples.
- Existing positions or historical rows remain auditable.
