# Sealed Replay Profitability Scorecard Bridge

Date: 2026-06-22

## Summary

I connected the passed sealed replay evidence back into the profitability path scorecard.

Before this, the scorecard could still say the next step was to build a sealed replay packet. Now, if the sealed packet already passed for the same side-cell, the scorecard advances the path to learning-stack ledger/outcome accumulation.

## Current Meaning

The current Cost Gate path is no longer "find BTCUSDT Sell 240m again." That was already sealed.

The current blocker is runtime learning evidence:

- probe ledger rows
- blocked-signal outcome rows
- writer/cron loop
- later execution realism

## Verified

- py_compile passed
- focused scorecard tests = `3 passed`
- related alpha/profitability tests = `57 passed`
- `git diff --check` passed

## Boundary

No Cost Gate lowering, no probe/order authority, no PG write, no Bybit call, no deploy/restart, and no promotion proof.
