# Stage 1 Demo + A4-C Tombstone Cleanup Archive

Date: 2026-05-16
Scope: active-doc cleanup only. No runtime, DB, auth, risk, strategy, paper,
demo, LiveDemo, or live mutation.

## Decision

Active docs should not keep markers that can be read as runnable work for:

- old W3 Stage 1 paper cohort semantics
- A4-C paper-edge promotion
- A4-C Stage 1 Demo cohort selection
- A4-C same-feature Stage 0R rerun

The durable active rule is:

- Stage 1 promotion evidence is Demo-only after a future green Stage 0R.
- Paper is non-promotional unless a future operator decision explicitly reopens
  it for diagnostics.
- A4-C is diagnostic-only/no-revive for the BTC 1m return + xcorr feature
  shape.
- Future A4-C reopen requires a materially new predictive variable,
  preregistered validation, and fresh strategy×symbol Stage 0R
  `eligible_for_demo_canary=true` evidence.

## What Moved Out Of Active State

Detailed A4-C Step 5b metrics, RCA threshold probes, and old paper-promotion
wording now live in historical reports and archives instead of the active TODO
queue:

- `docs/execution_plan/2026-05-15--a4c_btc_alt_lead_lag_archive_verdict.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--stage0r_preflight_step5b.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--a4c_rca_final_and_c1_proof_start.md`
- `docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`

## Active Tombstone To Preserve

Keep only this active guard:

> A4-C remains diagnostic-only/no-revive; keep `panel.btc_lead_lag_panel` and
> `[57] btc_lead_lag_panel_health`, but do not use A4-C as a Stage 0R promotion
> candidate or Stage 1 Demo cohort source.

Reason: removing every A4-C mention would let future agents rediscover older
specs and mistakenly revive the paper/promotion path. A short tombstone is safer
than silence.

## Files Updated

- `TODO.md`
- `CLAUDE.md`
- `.codex/MEMORY.md`
- `docs/CCAgentWorkSpace/PM/memory.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--stage1_demo_a4c_tombstone_cleanup.md`
- `docs/CCAgentWorkSpace/Operator/2026-05-16--stage1_demo_a4c_tombstone_cleanup.md`
- `docs/README.md`
