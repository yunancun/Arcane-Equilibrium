# Operator Checkpoint: Co-Located BBO Runner Source Design

The source-only co-located read-only PG snapshot + construction-preview runner is implemented and reviewed. It does not open an order path.

Runtime supplied-mode smoke:

- `/tmp/openclaw/cost_gate_learning_lane/co_located_bbo_snapshot_preview_runner_design_latest.json`
- sha256 `f520ce1eb6862236eee83862e8a0f30cd46f077232fa2b26378c2ebc31d065a5`
- status `COLOCATED_RUNNER_BBO_STALE_NO_ORDER`
- mode `supplied_market_snapshot`
- preview status `CANDIDATE_CONSTRUCTION_BBO_STALE`
- next blocker `P0-BOUNDED-PROBE-BBO-FRESHNESS-COLOCATED-RUNNER-RUNTIME-REVIEW-DEMO-ONLY`

Important guardrails:

- Supplied-market mode cannot close the co-located PG gate.
- `COLOCATED_RUNNER_READY_NO_ORDER` requires explicit `--pg-readonly`.
- `--pg-readonly` requires `--market-snapshot-output`.
- No Bybit call/order/cancel/modify path exists.
- No PG write path exists.
- No Cost Gate or freshness-gate lowering is recommended.

Verification: PA/E1 PASS, E2/E4 PASS, focused runner+preview `30 passed`, adjacent bounded-probe suite `100 passed`, `py_compile` and `git diff --check` passed.

Next gate: runtime review for whether to sync/run the helper on trade-core in explicit read-only PG mode.
