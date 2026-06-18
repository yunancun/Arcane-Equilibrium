# TODO P5-SM Completed-Row Relocation

**Date**: 2026-06-18
**Scope**: TODO lifecycle hygiene for `P5-SM-OPTION2-CONVERGENCE`

## Decision

Removed `P5-SM-OPTION2-CONVERGENCE` from `TODO.md` §5.

The row's active acceptance body was already complete: `[82]` step-ii 48h soak passed on Linux true DB at 2026-06-13T02:05:59Z. The same row also carried stale caveats saying V138/V139 and L2 activation had not run; those facts were superseded by later operator-approved V138/V139, seed, manual V140, L2 cron, embedding backfill, and B3 source-wiring checkpoints.

## Preserved Gate

This does not close P5-SM step-iii.

`TODO.md` §6 now carries `P5-SM step-iii CUTOVER sign-off` as an operator-gated action. It still requires operator sign-off plus CC/E2/BB/E4 review chain. If the two P5-SM soak flags are removed or converged and `[82]` emits fail-closed noise within 72h, use the existing CC LOW-2 SOP.

## Boundary

Docs hygiene only. No CI, source/code change, deploy, rebuild, restart, runtime mutation, DB mutation, auth mutation, risk mutation, order mutation, or trading mutation.
