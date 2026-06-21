# Cost-Gate Learning Loop Status Ingestion

Date: 2026-06-21

## Runtime Fact

Read-only Linux probe found the cost-gate learning lane is still not accumulating runtime evidence:

- No `/tmp/openclaw/cost_gate_learning_lane/probe_ledger.jsonl`.
- No `/tmp/openclaw/cost_gate_learning_lane/blocked_outcome_review_latest.json`.
- No `/tmp/openclaw/cron_heartbeat/cost_gate_learning_lane.last_fire`.
- No `/tmp/openclaw/logs/cost_gate_learning_lane.log`.

The only observed lane artifacts were the prior demo-learning plan and an empty policy stdout file.

## Change

`alpha_discovery_throughput.runtime_runner` now attaches a learning-loop status surface to the `cost_gate_demo_learning_lane` arm:

- heartbeat path / present / mtime / age
- status log path / latest `ts_utc` / age / error
- latest refresh and review artifact paths
- last refresh/review rc
- last status ledger row count
- latest review status and next trigger

`alpha_discovery_throughput.discovery_loop` now uses that surface to separate:

- `NOT_SEEN`: cron/writer/loop not observed.
- `RUNNING_NO_LEDGER_ROWS`: loop ran, but no reject rows exist yet.
- stale/error states.
- admission-only, insufficient blocked outcomes, failed review, and positive review candidates.

## Verification

- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` = 26 passed.
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` = 34 passed.
- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py` passed.

## Boundary

Source/test/docs plus read-only Linux artifact probes only.

No PG table write, schema migration, Bybit private/signed/trading call, engine/API rebuild or restart, deploy, credential/auth/risk/order/strategy/runtime mutation, main Cost Gate relaxation, signal proof, execution proof, or promotion proof.

## Read

This closes a visibility gap. The system can now say "learning loop not seen" or "loop ran but no ledger rows" directly in the alpha killboard instead of requiring manual SSH inspection.
