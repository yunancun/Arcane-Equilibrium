# Operator Note: Current Candidate Public Quote / Construction Refresh

State transition: `DONE_WITH_CONCERNS`.

The current AVAX Sell candidate now has fresh no-order public quote and construction artifacts using the GUI-resolved cap:

- GUI `P1 Risk/Trade = 10.0%` -> `per_trade_risk_pct=0.1`
- accepted Demo equity: `9552.43426257`
- resolved cap: `955.24342626 USDT`
- local `10 USDT` bounded-probe cap is not authority

Primary artifact:

- `/tmp/openclaw/current_candidate_public_quote_construction_refresh_20260627T021157Z/current_candidate_public_quote_construction_refresh.json`
- sha `be96831c0aa40a8aefbc7eab343dd09060439faac39f2a2ac5c208ecc606d684`
- status `CURRENT_CANDIDATE_PUBLIC_QUOTE_CONSTRUCTION_REFRESH_READY_NO_ORDER`

Construction preview:

- limit price `6.552`
- rounded qty `145.7`
- rounded notional `954.6264 USDT`
- BBO age `497.462ms`
- no blocking gates

Boundary: no order, no private Bybit endpoint, no PG write, no runtime mutation, no Cost Gate change, no probe/order/live authority. `order_admission_ready=false` remains the operative boundary.
