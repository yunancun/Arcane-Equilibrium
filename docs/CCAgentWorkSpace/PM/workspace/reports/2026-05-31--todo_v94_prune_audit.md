# PM Report — TODO v94 Prune Audit

Date: 2026-05-31
Role: PM(default)
Scope: audit whether `TODO.md` v94 reduced v93's 446 lines to 149 lines too aggressively.
Mode: documentation audit only. No runtime deploy, DB write, auth change, or trading action.

## Verdict

**YES, v94 pruned too aggressively for active handoff.**

The v94 direction was correct: `TODO.md` should be an active dispatch queue, not a historical ledger. The old v93 content was not destroyed because it remains in git history and linked reports/archives. However, v94 over-compressed several still-relevant gates into broad statements. A new PM could miss active waits, safety posture, module freeze context, and legacy Alpha/Sprint 2 dependencies.

## What Was Checked

- `ac9dca86:TODO.md` v93, 446 lines.
- `e8f3eaf1:TODO.md` v94, 149 lines.
- `docs/agents/todo-maintenance.md` active queue standard.
- AEG PM second sign-off and engineering arrangement.
- v93 sections for runtime, P0 blockers, workflows, module matrix, safety invariants, active engineering queue, deferred watches, cascade pending, and milestones.

## Findings

1. **AEG design integration is valid.** The new Alpha-Edge design explicitly integrates old foundations: `market.klines`, `market.symbol_universe_snapshots`, funding/OI/long-short tables, regime tables, `market.news_signals`, `AlphaSurface.regime`, `HurstHysteresis`, `panel.basis_panel`, and Sprint 2 runner lineage.
2. **TODO v94 hid active work.** It preserved the main blockers but dropped or over-generalized visible rows for 110017 observability/doc follow-ups, OPS-2 dry-run/runbook gaps, OPS-4 pg_dump test/event gaps, Wave 5 TOTP deferral, Sprint 2 Stage 0R evidence wait, OP1 endpoint misconfig, LG/lease/debt rows, and several scheduled watches.
3. **Module and safety posture should remain visible.** v93's full module matrix was too large, but completely removing M1-M13 and the safety invariants made the freeze/unfreeze logic less obvious.
4. **Historical narrative should stay archived.** Runtime RCA stories, closed sprint ledgers, long drift-audit details, and old closure summaries should not return to active TODO.

## Action Taken

`TODO.md` was updated to v95:

- 149 lines -> 253 lines, still materially smaller than v93's 446 lines.
- Restored compact active context for workflows, M1-M13 posture, safety invariants, active engineering rows, operator actions, deferred/scheduled watches, and cascade/governance watch.
- Kept AEG-S0 as the only Alpha-Edge executable next step.
- Kept E1 hard-blocked from backfill, retention mutation, endpoint implementation, collector implementation, and alpha scoring until AEG-S0 passes.

## Conclusion

The previous cleanup did not erase the project foundation, but it did make the active TODO too thin. v95 corrects that by restoring the old foundation as compact operational state while keeping long history in reports/archive.
