# ALR P2-2 Fresh Persistence Gate

Date: 2026-07-09
Work item: `P2-2-ALR-PERSISTENCE-FRESH-GATE`
Status: `ADVANCED_WITH_PREAPPLY_BLOCKER`
Execution mode: `ROLE_FALLBACK_SINGLE_SESSION`

## Gate Result

The fresh `PM -> E3 -> BB -> PM` gate approves one forward-only V151+ source
migration/repository and an isolated Linux Docker PostgreSQL double-apply. E3
requires append-only tables, conflict-as-error idempotency, parameterized SQL,
no new authority surface, and a single-migration preapply path. BB confirms the
scope has no Bybit, credential, endpoint, order, Cost Gate, or policy surface.

## Fail-Closed Runtime Condition

Linux read-only preflight found a clean checkout at `0bafe2f9e`; Mac and GitHub
are `715334273`. This prevents existing-PG migration apply, scanner reads,
service start, or retention sweep now. The blocker is source alignment, not an
external dependency: after P2-2 source tests/commit/push, PM must align all
three heads and recheck the exact V151 apply scope.

## Next State

`P2-2-ALR-PERSISTENCE-IMPLEMENTATION`: PA/E1 create the isolated
`learning.alr_*` append-only ledger/repository and run its container double-apply
before E2/E4/QA.

State packet: `2026-07-09--scanner_driven_alr_p2_persistence_fresh_gate.state_packet.json`
