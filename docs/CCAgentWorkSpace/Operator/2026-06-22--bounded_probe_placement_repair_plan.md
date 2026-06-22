# Operator Note: Bounded Probe Placement Repair Plan

Date: 2026-06-22
Source commit: `88d7713d`

v416 adds a no-authority placement repair plan after the touchability preflight.

Current Linux smoke result:

- status: `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW`
- candidate: `ma_crossover|BTCUSDT|Sell`
- order mode: `post_only_near_touch_or_skip`
- touchability baseline: `PASSIVE_LIMITS_TOO_DEEP_NO_TOUCH`
- reviewed orders: `6`
- fills: `0`
- deep passive no-touch orders: `6`
- max best-touch gap: `1530.6074bp`
- required max initial passive gap: `75bp`
- max fresh BBO age: `1000ms`
- active: `false`
- separate operator authorization required: `true`

Operational meaning: do not lower Cost Gate globally. If operator approval is granted later, the next implementation should be a bounded Demo-only patch in the existing Rust authority path: fresh BBO, maker-side near-touch post-only limit, skip-and-record when the gap is too wide, then order-to-fill and fill/fee/slippage review after the first repaired probe.

No cron was installed, no env was changed, no service was restarted, no PG write occurred, no Bybit trading/private call was made, and no probe/order authority or promotion proof was granted.
