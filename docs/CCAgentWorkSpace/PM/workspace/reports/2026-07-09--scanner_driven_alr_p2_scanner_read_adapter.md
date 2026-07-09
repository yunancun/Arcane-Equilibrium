# ALR P2-1 Scanner Read Adapter

Date: 2026-07-09
Work item: `P2-1-ALR-SCANNER-READ-ADAPTER`
Status: `ADVANCED`
Execution mode: `ROLE_FALLBACK_SINGLE_SESSION`

## Result

P2-1 is complete. The new pure adapter accepts the existing V030 Rust scanner
row shape, validates it fail-closed, derives a canonical SHA-256 source hash,
and preserves duplicate and late-cycle cursor behavior without mutating the
Rust scanner. Its output has only scanner-evidence authority.

E2 returned one lifecycle issue: because Rust snapshots the registry after its
update, a removed symbol must not remain active and cannot also be added. E1
first added the failing test, then added the two checks; E2 passed the corrected
surface. E4 ran the focused plus adjacent ALR suite twice with `153 passed` each,
and QA accepted this source slice.

## Boundary

No scanner row was actually consumed. No DB connection, migration, append-only
write, service, Linux runtime consumption, retention action, exchange contact,
order, Decision Lease, Cost Gate, serving, promotion, or `_latest` operation
occurred. This is not profit or proof evidence.

## Next State

`P2-2-FRESH-E3-BB-GATE`: produce and execute a fresh exact-scope
`PM -> E3 -> BB -> PM` review before P2-2 may create/apply the isolated
`learning.alr_*` migration/repository surface, start a service, sustain Linux
consumption, or sweep retention.

State packet: `2026-07-09--scanner_driven_alr_p2_scanner_read_adapter.state_packet.json`
