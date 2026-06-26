# Auth Typed-Confirm Guard Source Fix

Status: `DONE_WITH_CONCERNS`

This round fixed a source-only review-packet issue. The latest runtime auth artifact refreshed to sha `af337e48...`, but it is still `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED` / `decision=defer` with no probe/order authority.

Problem fixed: when preflight was not ready, the Markdown still displayed an exact phrase like:

`authorize_bounded_demo_probe:grid_trading|AVAXUSDT|Sell:0:`

That phrase is impossible to use safely because it has zero probe orders and no authorization id. The source now hides exact `typed_confirm_expected` until preflight is ready and positive probe budget plus authorization id are present. It instead shows a template and readiness reason.

No runtime source sync, crontab edit, service restart, PG write/query, Bybit order action, Cost Gate change, or authority grant was performed.
