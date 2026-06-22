# Operator Note: Bounded Probe Touchability Preflight

Date: 2026-06-22
Source commit: `029576af`

v415 adds a no-authority preflight before bounded Demo probe review.

Current Linux smoke result:

- status: `TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE`
- candidate: `ma_crossover|BTCUSDT|Sell`
- order-touchability audit: `PASSIVE_LIMITS_TOO_DEEP_NO_TOUCH`
- reviewed orders: `6`
- fills: `0`
- deep passive no-touch orders: `6`
- max best-touch gap: `1530.6074bp`
- required max initial passive gap: `75bp`

Operational meaning: do not lower Cost Gate based on these orders. The current Demo placement is too far from BBO to create fill-backed learning. Next reviewed work should repair bounded Demo placement with near-touch-or-skip rules and require order-to-fill plus fill/fee/slippage lineage after any probe.

No cron was installed, no env was changed, no service was restarted, no PG write occurred, no Bybit trading/private call was made, and no probe/order authority or promotion proof was granted.
