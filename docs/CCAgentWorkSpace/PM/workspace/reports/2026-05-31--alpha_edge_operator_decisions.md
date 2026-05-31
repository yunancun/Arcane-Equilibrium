# PM Report — Alpha-Edge Operator Decisions

Date: 2026-05-31
Role: PM(default)
Scope: operator decisions after S1-W1-S1 / S2-W0-S1 / S4-W0-S1 dispatch.
Mode: decision record + planning amendment; no runtime deploy, no DB write, no live/auth/order/execution change.

## Decisions

PM SIGN-OFF: **CONDITIONAL / READY FOR PA-MIT AMENDMENT**.

Operator decisions:

1. `market.klines` retention extension is approved in principle: `365d -> 1095d`.
2. Track 1 primary backfill window is approved: `18mo`.
3. Breadth posture is approved in principle: collect the full survivorship-corrected universe, but start primary analysis with core25.
4. Breadth must be automated and integrated into the workflow.
5. S4 is downgraded. 2024 bull data can be used for falsification/regime sensitivity, but not for standalone confidence or promotion proof.
6. The regime critique applies globally to S1-Sx. Every candidate needs cross-regime robustness/falsification, not only Track 4.

If execution happens on 2026-06-01, the 18mo analytical window is approximately 2024-12-01 to 2026-06-01. A supplemental 2024-11 stress/regime slice may be loaded for funding-extreme analysis, but it must remain a stress/falsification slice and cannot dominate promotion verdicts.

## Breadth Automation Requirement

The next packet must add a breadth-ladder report before S1-W2/S1-W3 verdict.

Required first run:

- Run after S1-W1-S2/S3 backfill and data-quality verify.
- Compare at least core25, scanner-active, top-liquidity 40-50, and full survivorship/cohort diagnostics where data quality permits.
- Use point-in-time universe and liquidity membership where possible; no current-survivor-only shortcut.
- Report whether any cross-sectional result is breadth-limited or only appears after adding low-quality symbols.

Required rerun triggers:

- Initial post-backfill run.
- Monthly when at least 30d of new data accrues.
- Universe drift greater than 10%.
- Before any Stage 0R / promotion claim.

## Global Regime Robustness Requirement

S4 is no longer an isolated bull-data track. It becomes part of a global regime/falsification overlay.

Required for S1-Sx verdicts:

- Report bull / range / bear / chop / high-vol slices when data supports them.
- Flag stale-data sensitivity, especially if old 2024 evidence dominates.
- Classify bull-only positive performance as regime-bet / learning-only unless cross-regime robustness is separately proven.
- Do not allow 2024 bull-only results to satisfy P0-EDGE promotion evidence.

## Next Executable Work

Do not dispatch E1 backfill implementation directly from the old plan. First dispatch PA/MIT to amend the execution packet for:

1. alpha-history storage implementation details,
2. breadth-ladder automation,
3. global regime robustness gates,
4. funding-history storage path after S4 downgrade.

After that amendment, E1 can implement the public Bybit history backfill writer with idempotent inserts and coverage reports.
