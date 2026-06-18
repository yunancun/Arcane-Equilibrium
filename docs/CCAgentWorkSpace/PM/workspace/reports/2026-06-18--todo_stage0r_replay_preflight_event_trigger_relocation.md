# TODO Stage0R Replay Preflight Event-Trigger Relocation

Date: 2026-06-18
Owner: PM
Scope: TODO/changelog/memory/report hygiene only

## Decision

Move `P1-SPRINT2-STAGE0R-REPLAY-PREFLIGHT-DISPATCH` from `TODO.md` §5 active engineering queue to §7 delayed/scheduled observation.

This is a relocation, not a completed-row archive. The row already states that the evidence check is done and that future action is event-triggered; keeping it in §5 incorrectly makes it look like there is an active engineering dispatch to run now.

## Evidence Rechecked

- `docs/CCAgentWorkSpace/FA/workspace/reports/2026-06-10--ac_s2_a3_evidence_check.md`: 0 candidates satisfy AC-S2-A-3; no Stage0R replay preflight dispatch should be sent now; trigger mode should change from date-triggered to event-triggered.
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-13--a1_basis_p2ops_p3_forward_checkpoint.md`: A1 basis wire is functional, but candidate remains dormant because there are no A1 signals after the entry gate.
- Existing TODO row: A1/A2 demo inactive, 0 fills, no green Stage 0R artifact, no operator demo-canary approval.

## Preserved Reopen Triggers

Recheck only if one of these occurs:

1. Any candidate gets green Stage 0R preflight and operator approval for demo canary, followed by D+14 review.
2. AEG-S3 produces the first real `candidate_regime_metrics` rows.
3. Residual Stage0R preflight flag-ON first run completes.
4. Funding exceeds 30% APR and A1 entry-gate regime reappears.

Backstop remains 2026-06-27 with `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK`.

## Boundary

No CI, source code change, deploy, rebuild, restart, runtime mutation, DB mutation, auth change, risk change, order change, or trading change.
