# Cost-Gate Learning Lane Cron Loop

Date: 2026-06-21

## Why

The current demo-learning lane can plan, record, refresh, and review cost-gate blocked signals, but the runtime check found the evidence stream is not actually accumulating yet:

- Linux `trade-core` is behind origin by 5 commits and dirty.
- `/tmp/openclaw/cost_gate_learning_lane/` has `demo_learning_lane_plan_latest.json` and empty policy stdout only.
- No `probe_ledger.jsonl` exists, and no `blocked_outcome_review_latest.json` exists.

So the immediate blocker is not "the review math is missing"; it is durable autonomous evidence accumulation after Cost Gate rejects.

## Change

Added:

- `helper_scripts/cron/cost_gate_learning_lane_cron.sh`
- `helper_scripts/cron/install_cost_gate_learning_lane_cron.sh`
- `helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py`

The wrapper runs the existing artifact-only refresh/review chain:

1. Read `$OPENCLAW_DATA_DIR/cost_gate_learning_lane/probe_ledger.jsonl`.
2. Use read-only PG `market.klines` through `cost_gate_learning_lane.outcome_refresh`.
3. Append missing `blocked_signal_outcome` JSONL rows when `OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES=1`.
4. Generate dated/latest `outcome_refresh_*.json`.
5. Generate dated/latest `blocked_outcome_review_*.json`.
6. Append compact status JSONL to `$OPENCLAW_DATA_DIR/logs/cost_gate_learning_lane.log`.

The installer is Linux-only, dry-run by default, idempotent, and reversible with `--remove`. Actual install requires `OPENCLAW_COST_GATE_LEARNING_CRON_APPLY=1`.

## Boundary

This is source/test/docs only.

No PG table writes, schema migrations, Bybit private/signed/trading calls, engine/API rebuild or restart, deploy, credential/auth/risk/order/strategy/runtime mutation, order authority, main Cost Gate relaxation, signal proof, execution proof, or promotion proof.

## Verification

- `python3 -m pytest helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py -q` = 9 passed.
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` = 23 passed.
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` = 34 passed.
- `bash -n` passed for wrapper and installer.
- `py_compile` passed for outcome refresh/review plus alpha runtime/discovery modules.
- Empty-ledger smoke wrote refresh/review/status artifacts with `ledger_row_count=0` and `review_status=NO_BLOCKED_SIGNAL_OUTCOMES`.

## Read

This supports the profit mandate by converting "Cost Gate rejected it, maybe wrongly" into a continuous evidence loop. It does not assume local cost estimates are perfect, but it still requires measured blocked-signal outcomes and operator review before any demo probe authority.
