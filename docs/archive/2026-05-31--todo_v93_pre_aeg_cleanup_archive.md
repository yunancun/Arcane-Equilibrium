# TODO v93 Pre-AEG Cleanup Archive

Date: 2026-05-31
Purpose: archive material removed from `TODO.md` during the Alpha-Edge Regime Evidence Governance cleanup.

Exact pre-cleanup source: `TODO.md` v93 at commit `ac9dca86` / `HEAD^` before the v94 AEG cleanup commit. Retrieve with:

```bash
git show ac9dca86:TODO.md
```

Audit note: v94 correctly moved historical narrative out of active TODO, but it over-pruned active handoff state. v95 restores compact active rows for still-relevant workflows, module posture, safety invariants, engineering queue items, scheduled watches, and cascade/governance gates. See `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--todo_v94_prune_audit.md`.

## Archived From Active TODO

The previous TODO mixed active blockers with long historical detail from:

- 2026-05-29 runtime recovery, 110017 close-loop RCA, and batched deploy history.
- 2026-05-29 cold-audit closure details.
- 2026-05-30 seven-gap cleanup and basis-panel deployment narrative.
- V1->V5.8 drift audit closure pointer.
- Layered Autonomy v2 Wave 5 detailed cascade notes.
- Large deferred/dormant watch tables and old cross-wave collision notes.
- Closed P0/P1/P2 rows already linked from older archives.

Those details remain available in the existing source reports and archives:

- `docs/archive/2026-05-31--todo_v92_archive.md`
- `docs/archive/2026-05-29--cold_audit_p1_p2_p3_closure_archive.md`
- `docs/archive/2026-05-23--sprint_4plus_5plus_wave1_closure.md`
- `docs/archive/2026-05-21--todo_v60_archive.md`
- `docs/audits/2026-05-25--v1_to_v58_full_consolidation_drift.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--alpha_edge_now_three_parallel_dispatch.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--alpha_edge_regime_evidence_pm_second_signoff.md`

## Active State Preserved In New TODO

The cleaned TODO v94 preserved:

- P0 blockers: `P0-EDGE-1`, `P0-LG-3`, `P0-OPS residual`.
- Immediate Alpha-Edge next action: AEG-S0 contract sprint only.
- E1 hard block before AEG-S0 passes.
- Operator hand-actions: OP-1/OP-2/OP-3, restore drill, system-level unit install, live-auth renewal.
- Key active source/review rows: LG-3 review/deploy gate, A2 runner auth fix, A1 basis wire, incident C4/C5, OPS-2 D+14.
- Deferred watch items with explicit trigger dates only.

v95 additionally restores compact active visibility for:

- Workflow B, Earn Wave C, Layered Autonomy v2 Wave 5, and Sprint 2 / Stage 0R legacy alpha posture.
- M1-M13 module freeze/unfreeze context.
- The 9 safety invariants as active constraints.
- 110017 observability/doc follow-ups; OPS-2/OPS-4 runbook/test/dry-run gaps; Wave 5 TOTP deferral; Stage 0R evidence wait; OP1 endpoint misconfig; LG/lease/debt rows.
- Near-term milestones previously hidden by v94, including 2026-06-01, 2026-06-02, 2026-06-10, 2026-06-11, 2026-06-13, 2026-06-27, and 2026-08-21 triggers.

## Cleanup Rule

From v94 onward, `TODO.md` should remain an active dispatch queue. Long evidence narratives must live in reports/archive and be linked, not copied.
