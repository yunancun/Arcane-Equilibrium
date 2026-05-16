# PM Report — Stage 1 Demo + A4-C Tombstone Cleanup

Date: 2026-05-16
Role: PM
Scope: Documentation cleanup only. No runtime, DB, auth, risk, strategy, paper,
demo, LiveDemo, or live mutation.

## Verdict

DONE: active docs now preserve the Stage 1 Demo promotion ladder while removing
misleading active markers for the old W3 paper cohort and A4-C promotion path.

## Changes

- `TODO.md` promoted to v37 and reframed §0.0 as Demo-only Stage 1 + A4-C
  tombstone guard.
- `TODO.md` removed active-sounding A4-C promotion tables and replaced them
  with a short tombstone plus archive links.
- `CLAUDE.md` now states A4-C is diagnostic-only/no-revive and Stage 1 is not
  tied to a W3 paper cohort or A4-C.
- `.codex/MEMORY.md` now keeps the durable rule only: Paper is
  non-promotional, Stage 1 is Demo-only, A4-C is tombstoned unless a materially
  new preregistered variable passes fresh Stage 0R.
- This archive records the cleanup rationale:
  `docs/archive/2026-05-16--stage1_demo_a4c_tombstone_cleanup.md`.

## Boundaries

No paper enablement, Demo canary launch, risk sizing change, live/LiveDemo
relaxation, auth renewal, runtime restart, DB migration, or strategy config
mutation was performed.

## Active Rule After Cleanup

Stage 1 launch requires:

- future strategy×symbol Stage 0R `eligible_for_demo_canary=true`
- operator-approved cohort
- W-AUDIT-3b runtime smoke
- `[55]` lineage evidence available
- Guardian / Decision Lease / SM-04 / StopManager boundaries intact

A4-C does not satisfy this and must not be used as the Stage 1 Demo cohort
source.
