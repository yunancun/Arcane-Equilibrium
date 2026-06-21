# Demo Learning Data-Flow Freshness Blocker

Date: 2026-06-21  
Role: PM local implementation checkpoint  
Status: source/test/docs complete; runtime still unsynced

## Finding

The previous evidence path could distinguish "24h lookback contains Cost Gate
rejects" from "learning ledger exists", but it could not prove the demo
pipeline was still fresh. That matters because a 24h count can look large even
when the latest candidate/reject/order-flow timestamp is already stale.

Latest read-only runtime facts collected after this patch:

- `trade-core` source remains `main...origin/main [behind 5]` and dirty.
- Runtime alpha latest is still old-schema: no killboard schema/runtime-source
  fields, `actionable_alpha_found=True`, `actionable_probe_found=True`.
- PG at `2026-06-21T23:17:12+02:00`: demo/live_demo 1h
  `decision_features=2496`, `risk_verdicts=2496`, latest both
  `2026-06-21 23:15:59.991+02`, but `intents=0`, `orders=0`, `fills=0`.
- 4h remains `intents=0`, `orders=0`, `fills=0`; 24h has only `intents=3`,
  `orders=3`, `fills=0`.
- 1h risk verdicts are entirely Cost Gate:
  `cost_gate(JS-demo): estimated=-6.01bps < 0` with `n=2496`.

So the immediate "no new data at all" condition had recovered by 23:15+02, but
the order/fill evidence lane is still empty and runtime source/artifacts are
still stale.

## Change

`demo_order_stall_audit` now emits a `data_flow_freshness` summary using a
90-minute freshness threshold:

- latest pipeline stage/timestamp/age
- latest learning-data stage/timestamp/age
- `LEARNING_DATA_FLOW_FRESH`
- `LEARNING_DATA_FLOW_STALE`
- observation-only / no-timestamp states

`demo_learning_evidence_audit` now promotes stale learning data to:

```text
DEMO_LEARNING_DATA_FLOW_STALE
```

before it can report `PG_REJECTS_RECORDED_LEARNING_LANE_NOT_ACCUMULATING`.
Alpha-discovery now carries those fields into the cost-gate arm and records the
profitability blocker:

```text
primary_blocker = demo_learning_data_flow_stale
next_trigger = restore_demo_data_flow_before_cost_gate_learning_activation
```

## Verification

- `python3 -m pytest helper_scripts/db/audit/test_demo_order_stall_audit.py -q` -> `12 passed`
- `python3 -m pytest helper_scripts/db/audit/test_demo_learning_evidence_audit.py -q` -> `6 passed`
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` -> `42 passed`
- `python3 -m py_compile helper_scripts/db/audit/demo_order_stall_audit.py helper_scripts/db/audit/demo_learning_evidence_audit.py helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
- `git diff --check`

## Boundary

No runtime source sync, artifact refresh, crontab edit/install, env edit,
deploy/rebuild/restart, PG write/schema migration, Bybit private/signed/trading
call, credential/auth/risk/order/strategy mutation, order authority, Cost Gate
lowering, execution proof, or promotion proof.

## PM Read

This is not a profitability improvement by itself. It prevents a false learning
claim: demo evidence must be both present and fresh before the cost-gate
learning lane can be treated as currently accumulating data.
