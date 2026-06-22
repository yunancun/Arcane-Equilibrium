# Operator Note: Sealed Horizon Bounded Probe Design

## Summary

The current sealed Cost Gate escape path now includes a concrete inactive demo-probe design packet. It tells us what a bounded demo experiment would test, what limits it should start with, what evidence it must collect, and when it must stop.

This does not approve a probe and does not grant order authority.

## Design Defaults

- Candidate: sealed horizon side-cell from the preflight artifact.
- Initial demo cap: 3 probe intents before review.
- Demo notional cap: 10 USDT per order, 30 USDT total before review.
- Success floor: realized average net bps above 0 and net-positive rate at least 60%.
- Required evidence: admission decisions, demo order/order-state rows, fill/fee/slippage rows, probe outcomes, and post-probe blocked-outcome review.

## Boundary

No Cost Gate lowering, no Bybit trading call, no runtime mutation, no deploy/restart, no writer/env enablement, no probe/order authority, and no promotion proof were granted.

## Operator Gate

The remaining decision is still actual operator review/authorization. If approved later, implementation should enforce the limits through the Rust authority path, not by bypassing Cost Gate in Python.
