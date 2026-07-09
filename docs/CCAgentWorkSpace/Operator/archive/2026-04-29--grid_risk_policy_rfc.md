# Grid Risk Policy RFC — Operator Summary

Date: 2026-04-29 21:45 CEST

Recommended first wave:

1. Add demo's robust-negative `grid_trading.blocked_symbols` list to `settings/strategy_params_live.toml`.
2. Reduce live grid density: `grid_levels = 10` → `7`.
3. Leave trailing and partial TP unchanged for now.

Reason: latest DB evidence shows live_demo `[38]` is dominated by `strategy_close:grid_close_*`, not trailing stops. `partial_tp_enabled` is currently schema/validation only and has no runtime consumer, so disabling it would not materially change behavior.

Current `[38]` baseline:

- demo: n=40, p50=4.8 min, fee_burn=0.24, re-entry=0.41
- live_demo: n=98, p50=1.7 min, fee_burn=0.45, re-entry=0.72

Decision requested: approve `strategy_params_live.toml` change only. Keep `[38]` active as the acceptance gate.
