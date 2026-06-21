# Cost-Gate Outcome Refresh Loop

VERDICT: PASS
CONFIDENCE: high

## 結論

v315 closes the remaining manual seam in the cost-gate demo-learning lane. `cost_gate_learning_lane.outcome_refresh` can now refresh missing blocked-signal/probe outcomes in one command from the append-only ledger plus either a local price export or read-only `market.klines`.

This is still learning infrastructure, not trading authority. It does not lower the main cost gate, grant demo probe orders, submit orders, write PG, call Bybit, mutate runtime config, or create promotion proof.

## What Changed

- Added `helper_scripts/research/cost_gate_learning_lane/outcome_refresh.py`.
- The CLI requires explicit target selection:
  - `--record-blocked-outcomes`
  - `--record-probe-outcomes`
- Default behavior is dry-run summary output. Ledger append requires explicit `--append-ledger`.
- Local file path: `--source-prices <json-or-jsonl>`.
- PG path: `--source-pg` uses the existing read-only kline Adapter; when no missing outcome windows exist it does not connect to PG.
- Alpha-discovery admission-only next trigger now routes to `run_cost_gate_outcome_refresh_for_blocked_signal_outcomes`.

## Operator Command Shape

Dry-run with local PG:

```bash
PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.outcome_refresh \
  --ledger /tmp/openclaw/cost_gate_learning_lane/probe_ledger.jsonl \
  --source-pg \
  --record-blocked-outcomes \
  --output /tmp/openclaw/cost_gate_learning_lane/outcome_refresh_latest.json
```

Append outcomes after reviewing dry-run:

```bash
PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.outcome_refresh \
  --ledger /tmp/openclaw/cost_gate_learning_lane/probe_ledger.jsonl \
  --source-pg \
  --record-blocked-outcomes \
  --append-ledger \
  --output /tmp/openclaw/cost_gate_learning_lane/outcome_refresh_latest.json
```

## Verification

- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` -> `21 passed`.
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` -> `34 passed`.
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/outcome_refresh.py helper_scripts/research/cost_gate_learning_lane/price_observations.py helper_scripts/research/cost_gate_learning_lane/outcome_writer.py helper_scripts/research/cost_gate_learning_lane/runtime_adapter.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py` -> passed.
- CLI help smoke passed.
- Empty-ledger `--source-pg` smoke produced `window_count=0`, `outcome_count=0`, and no PG connection error.

## Boundary

Source/test/docs only. No PG write/schema migration, no Bybit private/signed/trading call, no engine/API rebuild/restart/deploy, no credential/auth/risk/order/strategy/runtime mutation. Formal subagent dispatch was skipped because this session has no explicit subagent request/tool use allowance; PM-local implementation plus focused regression covered this narrow artifact-only Python seam.
