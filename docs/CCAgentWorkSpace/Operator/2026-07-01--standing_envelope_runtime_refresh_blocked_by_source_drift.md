# Standing Envelope Runtime Refresh Blocked By Source Drift

PM attempted to refresh the expired Demo standing loss-control envelope for `grid_trading|ETHUSDT|Buy`.

Result: `BLOCKED_BY_RUNTIME`.

- Runtime standing auth sha `8c891b4e...` remains expired at `2026-07-01T17:16:05.473618+00:00`.
- E3/BB approved only exact-source-bound refresh scopes at stale heads `477b248...`, `67c12f...`, and `19dae039...`.
- Final pre-action source check found `HEAD == origin/main == ed2b7514...`, so PM stopped before using those approvals.

No runtime action occurred: no Control API GET, public quote, envelope materialization, plan write, `_latest`, Decision Lease, private/order endpoint, order/fill/PnL/proof, service/env/risk mutation, Cost Gate change, or live/mainnet action.

Next action: `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-SOURCE-STABILITY-CURRENT-HEAD`. PM must start from current source and either get a consumable quiet-window E3/BB approval or add/review a machine-checkable source-impact guard before retrying the standing-envelope runtime refresh.
