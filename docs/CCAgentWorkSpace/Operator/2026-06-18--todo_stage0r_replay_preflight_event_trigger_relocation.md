# Operator Brief: Stage0R Replay Preflight TODO Relocation

Date: 2026-06-18
Owner: PM

## What Changed

`P1-SPRINT2-STAGE0R-REPLAY-PREFLIGHT-DISPATCH` was moved out of `TODO.md` §5 active engineering queue and into §7 delayed/scheduled observation.

This does not mark Stage0R replay preflight complete. It only reflects the existing evidence posture: the 2026-06-10 FA check found 0 candidates satisfying AC-S2-A-3, and there is no current candidate/operator gate that should dispatch a replay preflight now.

## Operator-Relevant Trigger

The row should be revisited only when one of the preserved triggers fires:

1. A candidate gets green Stage 0R preflight plus operator demo-canary approval.
2. AEG-S3 produces real `candidate_regime_metrics` rows.
3. Residual Stage0R preflight flag-ON first run happens.
4. Funding exceeds 30% APR and A1 entry-gate regime returns.

Backstop review remains 2026-06-27 with the BB strategies 30d catch-up clock.

## Boundary

Docs hygiene only. No runtime, DB, auth, risk, order, or trading changes.
