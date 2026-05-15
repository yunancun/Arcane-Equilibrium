# 2026-05-15 TODO v21 Completion Cleanup Archive

Purpose: move completed and superseded TODO v21 planning ledger out of the
active dispatch queue so `TODO.md` remains an active queue under the 700-line
limit.

Source file before cleanup:
- `TODO.md` v21, 754 lines.

Cross-check inputs:
- `active-plan.md` v1.0, 2026-05-15: Stage 0R verification DONE/GATE-RED;
  current focus is `[55]` fill-lineage WARN resolution.
- `git log` at `0d8b0df3` (`[ae-pm] [skip ci] establish active plan snapshot`).
- PM reports:
  - `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--canary_rebase_step3_step4.md`
  - `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--stage0r_preflight_verification.md`
- Governance sign-offs:
  - `docs/governance_dev/2026-05-11--w_c_window_pass_signoff.md`
  - `docs/governance_dev/2026-05-11--w_d_mag084_signoff.md`
  - `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`

## Archived From Active TODO

### Historical label / sprint ledgers

Moved out of active queue:
- `§1 Wave Label Reconciliation`
- `§4.1.1 Sprint N+0 + D+0 EXECUTION statistics`
- `§5 PM Sign-off Pre-flight Checklist` full 22-invariant ledger
- `§6 Sprint N+0 Day-by-Day Dispatch`
- `§6.5 Sprint N+1 D+0 Pre-dispatch Readiness Snapshot`
- `§6.6 Sprint N+1 D+0 EXECUTION Snapshot`
- `§6.7 Post-MAG-084 P1 Follow-up Wave Plan`
- `§7 W-AUDIT-6d Mid-Ground` detailed DSR derivation

Reason: these are completed planning/execution ledgers. Active blockers and
open follow-up IDs remain in `TODO.md` §0.0, §4, §10, §11, and §12.

### Completed / superseded rows

Rows marked completed or moved out of active queue after cross-check:

| ID / Section | Evidence | Active follow-up retained |
|---|---|---|
| `P1-STABLE-ID-1` | `b830e3fa`, `e40b2a76`, `d069b9e8`; E2 report `2026-05-11--p1_1_stable_id_helper_e2_review.md` | none |
| `P1-RCA-1` investigation | QA report `2026-05-11--p1_rca_1_orphan_er_investigation.md`; PA emergency/follow-up plans | `P1-FILL-LINEAGE-*`, `P1-HEALTHCHECK-55-INVARIANT`, `P1-STARTUP-BURST-MITIGATION` |
| `P1-W-AUDIT-3b-SMOKE` | `d069b9e8`; PM Step 3 evidence 2026-05-15 | `[55]` real-fill gate retained |
| `P1-FILL-LINEAGE-DROP` | `e17ead2b`; E4 report `2026-05-11--p1_fill_lineage_drop_e4_regression.md`; TODO v21 already records Wave 1.6 deploy evidence | monitor, invariant redesign, startup-burst mitigation retained |
| `P0-MIT-LABEL-CLOSE-TAG-1` | TODO invariant 21 and commit `db17e205`: post-M3 chain integrity era-split 100% | P0 edge remains active |
| `P1-CRON-ML-1` | TODO invariant 18 says 24h fire verified; memory correction `12695e9b` | V079 runtime status remains separate if reopened |
| `P2-DUAL-RAIL-ORDER-ID` | `2f1c385b` | none |
| `P2-RUNTIME-SHADOW-SPLIT` | `122015b7` | none |
| `P2-V19-CYCLE` | This cleanup cycle | future TODO hygiene as needed |

## W-AUDIT Priority Verdict

No wholesale W-AUDIT reorder is required, but demo-canary critical path is
rebased:

1. Do not launch Stage 1 demo micro-canary from A4-C until both conditions hold:
   a future Stage 0R replay preflight returns `eligible_for_demo_canary=true`,
   and `[55]` fill-lineage reaches PASS or PM/operator explicitly accepts a
   waiver.
2. A4-C (`W-AUDIT-8d`) remains implementation-complete but promotion-blocked
   by the 2026-05-15 GATE-RED metrics; it should not consume the top active
   slot until diagnostic evidence matures or the spec is revised.
3. Immediate active priority is `[55]` lineage hardening/monitoring plus
   P0-LG-1/2/3 and P0-OPS gates; Alpha Surface Phase C/D and alternative alpha
   candidates should proceed without treating A4-C Stage 1 as scheduled.

Boundary: this archive is documentation-only. No `active-plan.md`, runtime
code, live auth, rebuild, restart, or deploy was modified.
