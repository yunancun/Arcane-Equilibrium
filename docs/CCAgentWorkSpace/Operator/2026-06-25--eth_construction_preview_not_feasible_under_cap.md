# Operator Summary: ETH Construction Preview Not Feasible Under Cap

Date: 2026-06-25
Status: DONE_WITH_CONCERNS

## Result

`grid_trading|ETHUSDT|Buy` has strong blocked-outcome edge evidence, but the no-order construction preview says it cannot fit the current `10 USDT` bounded Demo cap.

## Key Facts

- ETH market data was fresh enough: `548.816ms` BBO age under `1000ms`.
- ETH instrument is trading.
- Passive buy placement would use limit `1571.05`.
- Bybit qty step is `0.01`, so the minimum positive order notional is about `15.7105 USDT`.
- Current bounded cap is `10 USDT`, so rounded qty becomes `0` and the candidate is not constructible.

## Boundary

No Bybit call, no PG write, no order/cancel/modify, no service restart, no Cost Gate lowering, no live/mainnet, no Rust writer/adapter enablement, no probe/order authority, and no promotion proof.

## Next Safe Action

Select or reroute to a cap-feasible candidate, likely a lower-price false-negative candidate, instead of forcing ETH through the current cap.
