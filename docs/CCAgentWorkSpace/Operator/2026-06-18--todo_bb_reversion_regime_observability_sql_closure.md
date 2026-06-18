# Operator Brief — TODO v173 BB Reversion Regime Observability SQL Closure

PM removed `P1-BB-REVERSION-REGIME-OBSERVABILITY` from `TODO.md` §5.

Reason: post-deploy SQL acceptance now passes. On Linux production DB, `bb_reversion` intents since `2026-06-11 02:00:00+00` have `hurst_label` and `hurst_value` in `trading.intents.details` for 10/10 rows.

This does not close the 2026-06-27 bb_strategy sample-size/retire decision. `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK` remains active.

Boundary: read-only SQL/source check plus docs hygiene only. No CI, deploy, rebuild, restart, DB write, auth/risk/order/trading mutation.
