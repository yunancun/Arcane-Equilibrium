# Horizon Edge Amplification Packet

Date: 2026-06-22

## Summary

I added a reusable artifact for the "amplify edge" path. It reads the multi-horizon Cost Gate counterfactual and ranks side-cells where changing the holding horizon may turn a blocked signal into a positive candidate.

Expected current top path: `ma_crossover|BTCUSDT|Sell` is blocked at the 60m primary horizon but positive at 240m, so the next proof gate is sealed 240m replay, not global Cost Gate lowering.

I also separated true retiming from "primary horizon already positive but other horizons blocked", so the packet does not overcount mixed-horizon cells as retiming unlocks.

## Verified

- py_compile passed
- focused horizon packet tests = `2 passed`
- related alpha/profitability tests = `52 passed`
- `git diff --check` passed

## Boundary

No Cost Gate lowering, no probe/order authority, no PG write, no Bybit call, no deploy/restart, and no promotion proof.
