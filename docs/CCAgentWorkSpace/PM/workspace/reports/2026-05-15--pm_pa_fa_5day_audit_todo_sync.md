# PM/PA/FA 5-day Audit and TODO Sync — 2026-05-15

**Owner chain**: PM -> PA(default) -> FA(default) -> PM
**Scope**: documentation / active-state reconciliation only
**Runtime authority**: none

## Boundary

This audit did not change code, strategy config, risk config, auth, DB data,
paper/demo/live runtime, or canary stage. It only reconciled active state across
`TODO.md`, `README.md`, `CLAUDE.md`, `.codex/MEMORY.md`, `active-plan.md`, docs
index, and archives.

## 5-day Work Quality Verdict

The last 5 days produced real governance and observability improvements:
W-C/MAG-082 and W-D/MAG-083/MAG-084 closed; W-AUDIT-4b feature baselines were
restored; `[55]` was corrected from a misleading all-chain ratio to a
fully-filled plan invariant; `[4]` phys lock and `[Xb]` triangulation were
fixed; A4-C Stage 0R was rerun fail-closed instead of being forced into demo.

Quality caveat: churn was high. Several intermediate reports and TODO rows were
correct when written but stale after later runtime checks. PM should treat
latest TODO v25 and the 2026-05-15 reports as the active state, not older
05-09/05-10 source-only checkpoints.

## PA Verdict Incorporated

PA classified `TODO.md` v24 as the closest active queue but flagged stale
state in `CLAUDE.md`, `README.md`, `.codex/MEMORY.md`, and `active-plan.md`.
PA also classified `2026-05-15--stage0r_oi_confirmed_5m_preflight.md` as
spec-only: no replay execution, no runtime mutation, and
`eligible_for_demo_canary=false`.

## FA Verdict Incorporated

FA agreed that business/alpha quality has not crossed the promotion bar:
Stage 0R remains red, paper promotion stays frozen, W3 Stage 1 demo
micro-canary must not launch, and OI-confirmed 5m is only a next Stage 0R
candidate spec. FA priority order: alpha repair first, then true-live
prerequisites, then observability hardening, then P2/docs hygiene.

## Current Facts Reconciled

| Area | Current state |
|---|---|
| Stage 0R / canary | A4-C Step 5b is GATE-RED; no Stage 1 demo cohort selected. |
| OI-confirmed 5m | Spec-only packet; not execution evidence; `eligible_for_demo_canary=false`. |
| `[55]` | Source-cleared: 25/25 fully-filled plan chains have real-fill ER; 0 missing; 13 partial chains diagnostic. |
| `[67]` | Restored: 646 active feature-baseline rows / 19 symbols / 34 features; standalone PASS. |
| `[27]` | Latest full passive healthcheck 2026-05-15 15:47 UTC hard-fails `intents_counter_freeze`: demo stale=50.1m, live_demo stale=46.2m, 30min intents=0 while approved verdicts/DCS continued. |
| V079 | Applied on `trade-core`; `_sqlx_migrations` max=90; V079/V085/V086/V087/V088/V089/V090 success; `learning.strategy_trial_ledger` rows=16,212. |
| MAG | MAG-082 WINDOW_PASS and MAG-083/MAG-084 signed/closed on 2026-05-11. |
| True live | Still blocked by edge, LG-1/2/3, ops, and explicit operator sign-off. |
| Linux sync | Source tree has unrelated dirty WIP; do not force reset or pull over it. |

## Files Updated

- `TODO.md` -> v25 active queue and stale-row cleanup.
- `active-plan.md` -> v1.3 current sprint posture.
- `README.md` -> current tabs, external tool posture, and Decision Lease flag boundary.
- `CLAUDE.md` -> TODO v25 sources and MAG current status.
- `.codex/MEMORY.md` -> current active-memory pointers.
- `docs/README.md` -> index for this audit and OI spec.
- `docs/CLAUDE_CHANGELOG.md` -> audit sync entry.
- `docs/archive/2026-05-15--todo_v24_stale_rows_archive.md` -> stale rows moved out of active interpretation.

## Reordered TODO Policy

1. No paper promotion, no Stage 1 demo micro-canary, no true-live authority
   until a future Stage 0R packet is green and governance gates are satisfied.
2. Alpha path: A4-C revise-or-archive / diagnostic maturity, then W-AUDIT-8a
   Phase C/D, `8c` liquidation, and `8b` funding skew.
3. True-live prerequisites: `P0-EDGE-1`, `P0-LG-1/2/3`, `P0-OPS-1..4`.
4. Runtime hardening: clear `P1-INTENT-FREEZE-27`, then fill-lineage monitor,
   startup burst, V083 current-log follow-up, feature baseline burn-in, W6-5
   metrics.
5. P2 hygiene / GUI / AI UX cleanup after the above gates.
