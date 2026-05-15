# Active Plan

Version: v1.0
Date: 2026-05-15
Source: TODO.md v21 + PM Stage 0R verification report, commit `6799e7ef`

## Current Sprint

- Sprint: N+0 W1-W2 FOUNDATION HEAVY
- Business-chain target: 63% -> 65%

## This Week Focus

- Stage 0R verification: DONE. Verdict is GATE-RED; A4-C is not eligible for demo canary.
- Step 4 fill-lineage WARN resolution: resolve `[55]` `WARN_REAL_FILL_PROPAGATION_PARTIAL`, or get explicit operator waiver before any Stage 1 demo micro-canary launch.

## Blockers

- 🚨 Stage 0R GATE-RED: A4-C `eligible_for_demo_canary=false` (commit `6799e7ef`). No Stage 1 demo cohort selected.
- ⚠️ `WARN_REAL_FILL_PROPAGATION_PARTIAL`: 15/89 real-fill reports. Demo canary remains blocked unless this reaches PASS or the operator accepts a micro-canary waiver.

## Available P1 Tasks

- `P1-STABLE-ID-1`
- `P1-RCA-1`
- `LG-2/3/4` design
- W7 propagation: `P1-1`, `P1-2`, `P2-1`

## Engine Status

- Linux `trade-core` is the active runtime machine.
- Demo and live pipelines are active.
- Paper is disabled and remains blocked for promotion evidence.

## Next Step

Wait for the operator decision: accept the current fill-lineage WARN as a micro-canary waiver, or wait for edge / lineage evidence to improve before Stage 1 demo micro-canary.
