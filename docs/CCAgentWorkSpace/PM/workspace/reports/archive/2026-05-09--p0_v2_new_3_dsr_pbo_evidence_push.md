# P0-V2-NEW-3 DSR/PBO Evidence Push

Date: 2026-05-09
Scope: source/test checkpoint only

## Result

`P0-V2-NEW-3-DSR-PBO-EVIDENCE-CRON` is source/test closed.

The fix connects the existing DSR/PBO + portfolio tail-risk promotion gates to
real realized-edge evidence instead of leaving `demo_selection_bias_report` and
`demo_tail_risk_report` absent forever.

## What Changed

- `james_stein_estimator.run_james_stein()` now returns real per-cell
  `raw_bps_series` in memory, while keeping JSON snapshots compact.
- New `program_code/ml_training/promotion_evidence.py` builds strategy-level
  observed Sharpe, trial Sharpes, PBO candidate return matrices, and portfolio
  returns from those real series.
- `edge_estimator_scheduler.py` pushes Demo-only promotion evidence after each
  James-Stein cycle. `live_demo` is intentionally skipped so it cannot
  overwrite Demo->LivePending evidence.
- `PromotionGate.update_demo_selection_bias_evidence()` now fails closed on
  invalid DSR/PBO input instead of raising out of the caller.
- V079 adds `learning.strategy_trial_ledger` plus
  `learning.promotion_pipeline.demo_selection_bias_report` and
  `demo_tail_risk_report` JSON columns.
- Governance promotion status reloads DB report rows fail-soft so persisted
  evidence can surface after runtime migration apply.

## Boundary

No cron install, V079 DB apply, rebuild, restart, live auth mutation,
strategy/risk config mutation, or order authority change was performed.

Stress exposures are not invented. If
`OPENCLAW_PROMOTION_STRESS_EXPOSURES_JSON` is absent, tail-risk evidence remains
fail-closed (`defer_data` or `block`) rather than producing a fake pass.

## Verification

- `python3 -m py_compile` on changed Python modules: PASS
- `pytest` targeted promotion evidence/scheduler/promotion pipeline/V079: PASS
- Existing edge scheduler observability/cutoff/leader-lock regressions: PASS
- V073 + V079 migration static tests: PASS
- `git diff --check`: PASS
