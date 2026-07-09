# PM Authorization - ALR P2-8 Fresh Scanner Shadow Soak

Date: 2026-07-09
State: `AUTHORIZED_EXACT_P2_8_SHADOW_SOAK`
Authority chain: PM -> E3 -> BB -> PM, `ROLE_FALLBACK_SINGLE_SESSION`

PM accepts the E3 and BB reviews without expansion. At source head
`26401fbbce9a97e68583a5b8f069ffa3fba0a4d1`, install the reviewed temporary
ALR cursor drop-in, restart only `openclaw-alr-shadow.service`, remove the
drop-in, and restart only that service once more for recovery verification.

The apply must account for the three listed post-baseline Rust scanner cycles
exactly once through the ALR ledger and must stop on any mismatch. All engine,
exchange, execution, Decision Lease, Cost Gate, risk, proof, serving,
promotion, `_latest`, and non-ALR deletion authority remains denied.
