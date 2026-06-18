# TODO v181 schedule-only duplicate cleanup

**Date**: 2026-06-18
**Scope**: TODO queue hygiene only

## Decision

Removed two schedule-only duplicate rows from `TODO.md` §5:

- `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK`
- `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1`

Both rows are passive waits with explicit review dates and no current executable engineering action. Keeping them in §5 made the active queue look busier than it is.

## Preserved Schedule

`TODO.md` §7 now carries the details:

- 2026-06-27: decide bb_breakout/bb_reversion Stage 0R baseline vs M7 retire/extend; if `bb_reversion@mean_reverting` sample size remains below 100, extend.
- 2026-08-21: run fallback dead-enum 90d audit plus halt root-cause review; `halt_audit.log` is ready, with earlier review only if healthcheck regresses.

## Boundary

Docs/TODO/changelog/memory/report hygiene only. No CI, no source/code change, no deploy/rebuild/restart, no production runtime/DB/auth/risk/order/trading mutation.
