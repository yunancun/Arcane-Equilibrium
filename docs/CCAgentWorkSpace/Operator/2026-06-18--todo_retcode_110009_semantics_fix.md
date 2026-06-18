# Operator note: retCode 110009 source fix

Date: 2026-06-18

## What Changed

Source now treats Bybit `110009` as stop-order-limit-exceeded, not
PositionNotFound:

- `BybitRetCode::StopOrderLimitExceeded = 110009`
- dispatch no longer classifies 110009 as NoOp
- 110009 now fails closed as Structural

## Validation

Focused Rust tests passed:

- retCode classification tests: 2 passed
- changed dispatch classifier/helper tests: passed
- full `event_consumer::dispatch::tests`: 56 passed

## Runtime Boundary

No deploy, rebuild, restart, DB change, auth change, risk change, or trading
operation occurred in this pass. Running engine binary is not claimed to include
the fix until a future normal deploy gate loads this source.
