# E3 Review - ALR P2-8 Fresh Scanner Shadow Soak

Date: 2026-07-09
Verdict: `APPROVE_EXACT_ALR_SERVICE_SCOPE`
Authority chain: PM -> E3 -> BB -> PM, `ROLE_FALLBACK_SINGLE_SESSION`

E3 approves only an `openclaw-alr-shadow.service` unit source-pin update to
`26401fbbce9a97e68583a5b8f069ffa3fba0a4d1`, one temporary environment drop-in
with the reviewed post-baseline UTC cursor, and ALR-only restarts required to
consume then clear that cursor. The code's cursor query is bounded, validates
an offset-aware timestamp, uses `SELECT` only on `trading.scanner_snapshots`,
and persists through the existing append-only idempotency path.

Do not apply a migration, change a DB role, restart/rebuild the Rust engine,
touch the scanner process/cadence/registry, or interact with any exchange,
order, Decision Lease, Cost Gate, proof, serving, promotion, `_latest`, or
retention sweep target beyond the existing ALR-owned zero-entry cache path.
Stop if the three heads drift, the engine PID changes, the unit fails, the
cursor rows cannot be accounted for exactly once, or any authority counter is
nonzero.
