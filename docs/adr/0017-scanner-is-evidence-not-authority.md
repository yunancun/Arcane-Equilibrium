# ADR 0017: Scanner Is Always-On Evidence Infrastructure

Date: 2026-05-09
Status: Accepted

## Context

Scanner previously had legacy authority-mode language and healthchecks that
could be read as a hard gate. The operator clarified that scanner should be
infrastructure, always on by default, not something that enables, disables, or
degrades trading authority through a mode switch.

## Decision

Scanner provides market context, active-universe attribution, route fitness,
opportunity evidence, and legacy would-block audit evidence.

Scanner cannot hard-gate opens, close positions, force reductions, control live
auth, place orders, mutate risk/strategy config, or unlock executor authority.

## Consequences

- `scanner_config.toml` no longer carries `[authority]`.
- Legacy would-blocks are audit evidence only.
- Passive healthcheck `[41]` reports contradictory would-block evidence as
  WARN calibration data, not FAIL.
- Guardian, Decision Lease, H0/P0/P1, live authorization, and Rust execution
  authority remain the enforceable gates.
