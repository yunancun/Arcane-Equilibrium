# TODO v36 Completion Cleanup

Date: 2026-05-16
Role: PM
Scope: Documentation cleanup only. No runtime, DB, auth, risk, strategy, paper,
demo, LiveDemo, or live mutation.

## Request

Operator asked to update TODO, cross-validate completed portions, remove fully
completed material into an appropriate archive, and be extra careful not to
clean up in-progress or dependency-bearing work.

## Cross-Validation

PM checked completed TODO rows against:

- referenced git commits via local `git cat-file -e <sha>^{commit}`
- PM / E2 / E4 / BB reports under `docs/CCAgentWorkSpace/`
- current runtime summary from the v35 three-side sync/rebuild report
- existing 2026-05-15 and 2026-05-16 archive/report files

## Changes

- Promoted active TODO to v36.
- Moved completed v35 / 2026-05-15..16 detail into
  `docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`.
- Trimmed active TODO to blockers, dependent gates, deferred work, and runnable
  backlog.
- Corrected stale W-AUDIT-8a C1 wording: the standalone `allLiquidation.BTCUSDT`
  proof ended `FAIL_CONNECTION` at `2026-05-16T00:37:25Z` after
  `17055.2s/86400s`; it is not proof-eligible.
- Kept `P1-BBMF3-WIRE-1` active because E2/BB verified the cooldown plumbing
  and tests landed, but production reject callback wiring remains Phase 1b
  scope.

## Active Items Explicitly Preserved

- `P0-EDGE-1`
- `P0-LG-1`, `P0-LG-2`, `P0-LG-3`
- `P0-OPS-1..4`
- `LG-1`, `LG-2`, `LG-3`
- W-AUDIT-8a C1 full-duration proof rerun
- W-AUDIT-8b read-only Stage 0R packet
- EDGE-P2-3 Phase 1b gates and follow-ups
- `P1-WAVE-3-5-LINUX-MIGRATION-BACKLOG`
- `P1-BBMF3-WIRE-1`
- WP-11 Phase 2 residuals and WP-12 deferred work
- incomplete P2 backlog rows

## Result

TODO is now a compact active dispatch queue. Completed material remains
traceable through the archive, changelog, README index, PM memory, and this
report.
