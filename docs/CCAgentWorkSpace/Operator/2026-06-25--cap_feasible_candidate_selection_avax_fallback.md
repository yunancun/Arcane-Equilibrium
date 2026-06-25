# Operator Summary: Cap-Feasible AVAX Fallback Selected

Date: 2026-06-25
Status: DONE

## Result

ETHUSDT Buy is excluded under the current `10 USDT` bounded cap. The selected fallback candidate is:

`grid_trading|AVAXUSDT|Sell`

## Key Facts

- AVAX is Trading.
- Current bounded cap remains `10.0 USDT`.
- Minimum required notional is `5.0 USDT`.
- Min positive qty notional is `0.6209 USDT`.
- False-negative evidence: avg net `73.5511bps`, `48/48` net-positive outcomes.
- The AVAX packet approves preflight review only. It does not grant probe/order authority.

## Boundary

No Bybit call, no order/cancel/modify, no PG write, no `_latest` overwrite, no service restart, no Cost Gate lowering, no cap widening, no Rust writer/adapter enablement, no live/mainnet, no probe/order authority, and no promotion proof.

## Next Safe Action

Build an AVAX no-order construction preview. If fresh public quote/BBO data is needed, stop for E3/BB review before making any exchange-facing call.
