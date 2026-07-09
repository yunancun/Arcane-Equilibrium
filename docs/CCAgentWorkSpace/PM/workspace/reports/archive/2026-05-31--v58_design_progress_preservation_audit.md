# PM Report — V5.8 Design Progress Preservation Audit

Date: 2026-05-31
Role: PM(default)
Scope: re-check all V5.8 design assets, current progress, and whether TODO cleanup incorrectly removed them.
Mode: documentation audit only. No runtime deploy, DB write, auth change, or trading action.

## Verdict

**V5.8 was not destroyed or incorrectly removed. It is reasonably preserved as long-term autonomy architecture.**

The current TODO should not carry the full V5.8 design ledger. The correct active posture is:

- V5.8 remains the 13-module autonomy design foundation.
- AEG/ADR-0047 now governs Alpha-Edge evidence, regime labeling, breadth automation, and promotion gating.
- V5.8 active-IMPL is frozen except already-landed scaffolds and explicitly visible follow-ups, because P0-EDGE-1 cost-wall evidence is the binding constraint.

## Files Checked

Core files:

- `docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- `docs/execution_plan/2026-05-25--sprint_2_business_dispatch_packet.md`
- `docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md`
- `docs/audits/2026-05-25--v1_to_v58_full_consolidation_drift.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v58_pm_final_verdict.md`
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`
- all `2026-05-21--m1..m13_*_design_spec.md` files, plus M4 leakage and M11/M7 dedup specs.
- ADR-0034 through ADR-0045, ADR-0046, ADR-0047.
- current `TODO.md` v96, `docs/CLAUDE_CHANGELOG.md`, `docs/README.md`, and v92/v93 archives.

## Design Inventory Status

| Area | Preservation state |
|---|---|
| V5.8 main plan | Preserved. It explicitly says V5.8 supplements v5.7 and does not supersede it. |
| 13 module specs | Preserved and indexed in `docs/README.md`; total module/spec body remains available. |
| ADR/runbook layer | Preserved. ADR-0034..0045 encode the governance corrections and module boundaries. |
| Sprint 2 Alpha Tournament | Preserved, but now subordinate to Alpha SSOT and AEG evidence gates. |
| V1->V5.8 drift audit | Preserved as audit/history, not active TODO body. |
| TODO active visibility | Restored in v95 via compact M1-M13 matrix, workflow rows, safety invariants, and scheduled watches; v96 adds the V5.8 preservation checkpoint. |

## Current Progress By Module

| Module | Current progress | Correct active posture |
|---|---|---|
| M1 LAL | Design + ADR + V112 SQL/source skeleton exist; active auto-grant not runtime-proven. | Frozen until alpha evidence gate; P0-LG-3 review remains separate. |
| M2 Overlay | Design/V105 spec exists; no active production IMPL. | Frozen; keep as Y2/overlay gate design. |
| M3 Health | V106 SQL + health/emitter scaffold + M3 metric emitter work landed; auto-degradation not full. | Keep residuals visible in OPS; no new autonomy IMPL until gate. |
| M4 Hypothesis Discovery | V100/V103 + Stage 1 runner + Linux no-writeback empirical done; GovernanceHub lease seam fail-closed; writeback blocked by lease-ID/schema mismatch. | Retained as DRAFT-only research support; no promotion authority. |
| M5 Online Learning | Trait stub + tests exist. | Y3+/AUM gate only. |
| M6 Reward Weight | Design + ADR/V110 spec exist; no production IMPL. | Frozen. |
| M7 Decay | Original V113 design exists; actual current plan moved to free V116 spec; E1 IMPL held. | Frozen until first net-positive candidate reaches `stage0_ready`. |
| M8 Anomaly | V109 SQL + writer skeleton exist; detector not wired as active trigger. | Read-only/frozen; AEG regime classifier is separate and must be fixed before alpha scoring. |
| M9 A/B | Design + ADR/V108 spec exist; no production IMPL. | Frozen. |
| M10 Discovery | Tier A design/backend lineage exists; B-E pending. | AEG can feed Tier B+, but no promotion outside evidence matrix. |
| M11 Replay | V107 SQL exists; register-only cron / smoke liveness exists; divergence output still incomplete. | Keep `[48]` residual visible; Stage-A smoke is not promotion evidence. |
| M12 Order Routing | Trait stub + tests exist; adaptive routing not implemented. | Future Sprint 6+ work only. |
| M13 Multi-asset/venue | AssetClass/Venue enum stub + tests exist; Binance trade remains Y3+ earliest. | No active IMPL. |

## What Was Reasonably Removed From Active TODO

- Full V5.8 design text and line-by-line module specs.
- Historical 14-agent audit detail and old closure narratives.
- Old Y1 income/autonomy projections as active dispatch content.
- Long V### placeholder descriptions already covered by specs and archives.

These are design history and reference material, not current dispatch rows.

## What Must Remain Visible

- M1-M13 compact posture and freeze/unfreeze gate.
- Sprint 2 / Stage 0R legacy alpha state, explicitly subordinate to AEG.
- M4 no-writeback / lease-ID blocker.
- M11 Stage-A smoke vs divergence-output distinction.
- V### reconcile debt: original V5.8 V105-V116 roster is not today's SQL migration truth.
- AEG-S0 hard block before any alpha-history backfill or scoring.

## Risks / Drift Found

1. **Schema-numbering drift is real.** V5.8's original V105-V116 roster is no longer a direct SQL execution plan. Current `sql/migrations/` head is V115, with V113/V114/V115 used by later OPS/failsafe/basis-panel work. TODO already tracks this as `v92 V### reconcile`; future agents must not copy V5.8 §9 into migrations without PM/MIT review.
2. **Sprint 2 Alpha Tournament is preserved but superseded for promotion.** A1/A2/A3 legacy evidence remains useful, but any promotion now requires AEG regime/breadth/freshness/survivorship/execution-realism matrices.
3. **V5.8 schedule is stale as an execution schedule.** It remains architecture; current execution is blocked by P0-EDGE-1 and AEG-S0.

## Conclusion

The TODO cleanup should not restore the full V5.8 ledger. v96 now keeps the correct compact preservation posture, leaves a visible checkpoint pointing to this audit, and keeps the V### reconcile row active until the doc-side numbering debt is closed.
