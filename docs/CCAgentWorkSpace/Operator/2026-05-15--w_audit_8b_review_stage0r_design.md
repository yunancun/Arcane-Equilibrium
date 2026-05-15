# Operator Brief — W-AUDIT-8b Review + Stage 0R Design

Date: 2026-05-15

## Result

- `W-AUDIT-8b` Funding Skew is approved for Stage 0R replay design only.
- It is not strategy-implementation ready.
- No demo/live launch, runtime config change, risk/sizing edit, or funding-payment edge credit is authorized.

## Review Verdict

- QC: valid hypothesis, but v0.1 needs revision. Use 30m primary horizon, split long-squeeze vs short-fade branches, require `DSR >= 0.95`, explicit `K_total`, and PBO fail-closed.
- MIT: raw panel as-of joins only; preserve data provenance; stale >300s excludes rows; eligibility funding attribution mode is `excluded`.
- BB: no exchange blocker for replay design; add symbol-specific funding interval, funding cap/source mode, and timestamp alignment rules.

## Next

Build only the read-only Stage 0R replay query/report packet for `funding_skew_directional.v0_2`.

Minimum new candidate count is `4050` cells before prior comparable trials:

`25 symbols × 2 branches × 3 z_hi × 3 percentile pairs × 3 OI thresholds × 3 horizons`.

C1 liquidation proof remains separate and still running on `trade-core` as PID `4100789`.
