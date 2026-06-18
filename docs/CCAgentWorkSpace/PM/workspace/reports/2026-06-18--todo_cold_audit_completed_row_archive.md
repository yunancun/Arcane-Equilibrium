# TODO v180 cold-audit completed-row archive

**Date**: 2026-06-18
**Scope**: TODO queue hygiene only

## Decision

Archived these completed rows out of `TODO.md` §5:

- `AUDIT-2026-06-14-AUTH-1`
- `AUDIT-2026-06-14-PROFIT-1`

They were kept in §5 after v164 because each carried a real caveat, but the caveats are no longer active engineering tasks:

- AUTH-1 source fix has already been through PA→E1→E2→E3→E4, committed, and included in the cold-audit Linux deploy. The remaining direct-socket bypass is a future architecture/operator decision, not a current fix-wave action.
- PROFIT-1 has an accepted NO-FIX ruling. The double-deduct bug is mathematically real, but the runtime path is dormant until a validated-positive cell exists. Passive sentinel `[90]` remains the active trigger.

## Preserved Future Gates

`TODO.md` §7 now carries the remaining tails:

- `P2-LIVE-AUTHZ-RUST-DIRECT-SOCKET-FUTURE`: reopen only if operator wants to close direct-socket bypass by moving live authz context into Rust.
- `P1-COST-GATE-DOUBLE-DEDUCT-TRIGGER`: reopen only if explore-gate/Stage0R writes `validation_passed=true` positive cells or forward PnL proves released cells positive.

## Boundary

Docs/TODO/changelog/memory/report hygiene only. No CI, no source/code change, no deploy/rebuild/restart, no production runtime/DB/auth/risk/order/trading mutation.
