# TODO v30 Three-Side Source Sync

Date: 2026-05-15 21:50 CEST
Scope: source/docs sync only.

## Facts

- Mac worktree was clean before this update.
- Mac `HEAD`, local `origin/main`, and Linux `trade-core` were all at
  pre-v30 base `9a72d054`.
- Linux `trade-core` worktree was clean before this update.
- Active docs still had stale sync wording in a few places:
  `TODO.md v28` in `CLAUDE.md`, and `81bc0862` as the latest source-sync SHA
  in `CLAUDE.md` / `active-plan.md`.

## Changes

- Promoted `TODO.md` to v30.
- Aligned `CLAUDE.md`, `active-plan.md`, `.codex/MEMORY.md`, `.codex/WORKLOG.md`,
  PM memory, and docs index with the source-only sync checkpoint.
- Recorded that runtime binary code line remains rebuilt `7b33ab2e`; the v30
  update does not imply a rebuild or restart.

## Boundaries

No runtime rebuild/restart, DB write, auth renewal, production WS topic revival,
paper enablement, demo canary, live/LiveDemo relaxation, sizing, risk, or config
mutation was performed or authorized.

## PM Verdict

TODO v30 is a bookkeeping/source-sync checkpoint. It does not change alpha
eligibility: A4-C remains archived/diagnostic-only, W-AUDIT-8a C1 still waits
for BB 24h isolated proof, and W-AUDIT-8b still needs QC/MIT/BB review plus
Stage 0R replay design.
