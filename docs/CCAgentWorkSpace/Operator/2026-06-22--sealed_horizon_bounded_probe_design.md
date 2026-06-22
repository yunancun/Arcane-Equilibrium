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

## Latest Evidence

- Sealed preflight latest: `/tmp/openclaw/cost_gate_learning_lane/sealed_horizon_probe_preflight_latest.json`
- sha256: `6d642a78e23d744c21fbb49e7618ffd66e7a2fa279923c73fc7d0f6b3ceea14d`
- Status: `OPERATOR_REVIEW_REQUIRED`
- Design status: `OPERATOR_REVIEW_READY_FOR_BOUNDED_DEMO_PROBE_DESIGN`
- Profitability scorecard smoke sha256: `6eb327b7c0f5ad96eaad2d9e0e9bb4ffaff88c3222910f4d442cb15905082f30`
