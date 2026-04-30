# TODO Stale Active-Mainline Archive

Date: 2026-04-30

This file preserves the text removed from `TODO.md` during the corrective cleanup. The content below was removed only because it was no longer the active mainline as of the 2026-04-30 runtime/progress recalibration. The full original file remains available at:

- `docs/archive/2026-04-30--TODO-pre-cleanup-snapshot.md`

## Removed From Active: 62-Finding Mainline

Original heading:

```markdown
## 🎯 此刻該做什麼（2026-04-29 CEST · 62-finding remediation A-F deployed · fee-refresh RCA fixed）
```

Reason removed from active state:

- Batch A-F had already been fixed, signed off, deployed, and archived.
- Keeping it as "新主線" made the current queue point at closed work.
- Current mainline is post-remediation edge/dust observation plus time-driven gates.

Original content summary:

- authority audit pointers: `docs/audit/final_record_zh.md`, `docs/audit/final_summary.md`
- PM schedule pointer: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-28--audit_62_findings_remediation_schedule.md`
- count: 62 findings, P1=29 / P2=29 / P3=4 / P0=0
- Batch A-F listed as committed/pushed/deployed
- old Linux runtime note around `af9d552`
- old post-deploy `[22]` / `[27]` / `[32]` framing
- old live authorization schema-v1 blocker framing
- old batch workflow gate/preflight notes

Canonical archive for the completed remediation:

- `docs/archive/2026-04-29--62finding-batch-A-to-F.md`

## Removed From Active: Post-Wave-H Operator Hotfixes

Original content summary:

- `cdc2699` EDGE-DIAG-2-FUP fee-postonly-2
- `20baabe` `restart_all.sh --keep-auth`
- `85a4e2d` CLAUDE.md EDGE-DIAG-2 drift fix

Reason removed from active state:

- These were completed hotfixes, not current action items.
- The details remain in the full pre-cleanup snapshot and Wave A-H archive.

Canonical archive:

- `docs/archive/2026-04-29--wave-A-to-H-narrative.md`

## Replacement Active Block

`TODO.md` now keeps the original v3 timeline and replaces only this stale active-mainline section with:

- post-deploy edge observation
- dust residual runtime proof
- G1-04 final compute
- G2-02 ma_crossover replay
- G2-01 PostOnly acceptance
- Scout heartbeat production caller wiring
