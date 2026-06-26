# Operator Note - Demo Residual Cleanup Refresh Action

Timestamp: 2026-06-26T03:18Z

Result: `DONE_WITH_CONCERNS`.

The reviewed demo cleanup route executed exactly once from `trade-core` using
the runtime-local control API token path. It returned HTTP `200`,
`closed_all=true`, and `partial_failure=false`.

Independent post-action Bybit demo full scan is clean:

- open orders: `0`
- nonzero positions: `0`

Artifacts:

- pre-inventory:
  `/tmp/openclaw/audit/bybit_demo_cleanup_refresh_pre_inventory/20260626T030910Z_pre_inventory.json`
- action meta:
  `/tmp/openclaw/audit/demo_residual_cleanup_refresh_action/20260626T030949Z_session_stop_meta.json`
- post-inventory:
  `/tmp/openclaw/audit/bybit_demo_cleanup_refresh_post_inventory/20260626T031031Z_post_inventory.json`

Concern: passive healthcheck [68] still fails from four local stale
`Working` rows in `trading.order_state_changes`; exchange truth is clean. These
rows, cleanup/risk-close rows, and unattributed rows are proof-excluded and
must not count toward bounded-probe, Cost Gate, promotion, or PnL proof.

Next active blocker: `P0-PROFIT-CANDIDATE-SELECTION`.
