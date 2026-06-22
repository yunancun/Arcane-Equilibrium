# Profit-Learning Packet Alpha Ingestion

## 結論

Alpha discovery / learning worklist now reads the Cost Gate profit-learning decision packet when present. This makes the packet visible in the normal operator-facing killboard/worklist path.

## What Changes For Operators

Once runtime source is reconciled and the packet is generated under `/tmp/openclaw/cost_gate_learning_lane/`, alpha discovery can surface:

- missing data-flow monitor
- stale/missing reject counterfactual
- missing bounded learning plan
- learning-stack activation/repair blocker
- blocked-outcome review wait
- operator-review demo probe candidates

The ingestion remains recommendation-only. It does not lower Cost Gate, grant order authority, or install/enable anything.

## Verification

- Mac py_compile passed for runtime runner, discovery loop, worklist, and focused tests.
- Mac focused pytest passed: `57 passed`.
- Mac `git diff --check` passed before checkpoint completion.

## Boundary

No runtime fetch/pull/reset/clean/source sync was performed. No cron install, env edit, deploy/rebuild/restart, PG query/write/schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy mutation, writer enablement, Cost Gate lowering, order authority, probe authority, or promotion proof was performed.
