# Operator Note: GUI Cap Authority Fix + AVAX Standing Materialization

State transition: `DONE_WITH_CONCERNS`.

Your correction is now enforced in source: GUI/Rust RiskConfig is the source of truth. GUI `10.0%` is `per_trade_risk_pct=0.1`, not a `10 USDT` order cap.

What changed:

- Runtime standing envelope is now materialized for `grid_trading|AVAXUSDT|Sell`, sha `42fca4b3e4bd1143dd8550bb4f36ff85774eed7a3b8acbf3ae99243d2a49d520`, mode `0600`.
- Refreshed preflight now uses `max_demo_notional_usdt_per_order=955.24342626 USDT`.
- Bounded authorization remains blocked: status `GUI_RISK_CAP_INPUT_REQUIRED_FOR_AUTHORIZATION_REVIEW`, because the old placement snapshot still has `10.0` and no GUI cap lineage.
- Rust active bounded-probe default cap is now fail-closed `0.0`; a caller must supply the reviewed GUI cap.

No bounded auth object, Decision Lease, Guardian/Rust authority, order, Cost Gate change, live authority, or profit proof was created.

Next safe step: refresh touchability/placement under the GUI cap lineage, then refresh authority readiness and bounded auth in defer/no-order mode.
