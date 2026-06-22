# Profitability Path Scorecard

Date: 2026-06-22

## Verdict

`DONE_WITH_BOUNDARIES`.

This checkpoint changes the work shape from repeated manual diagnosis to a reusable profitability path scorecard. It does not claim profitability; it ranks the paths that could plausibly cross the cost wall and names the next proof gate for each.

## Changes

- Added `helper_scripts/research/alpha_discovery_throughput/profitability_path_scorecard.py`.
- New schema: `alpha_profitability_path_scorecard_v1`.
- Inputs are existing artifacts only:
  - Cost Gate reject counterfactual
  - Cost Gate profit-learning decision packet
  - learning plan / activation preflight
  - MM fill-sim + history
  - Polymarket lead-lag replay
  - Gate-B watch
- Ranked path classes:
  - bounded demo-learning probe
  - horizon retiming / side-cell filter
  - low-friction MM alpha search
  - fee / rebate / scale path
  - Polymarket lead-lag alpha path
  - Gate-B listing-fade event wait
- Each path carries edge bps, cost threshold, effective sample, next gate, next action, and authority boundary.
- Fixed `demo_order_stall_audit.py` SQL literal percent escaping for psycopg `%s` queries, which unblocked the data-flow monitor runtime SQL path.

## Interpretation

The correct profit path is not global Cost Gate lowering. The current evidence says:

- Cost Gate rejects contain bounded learning candidates, but they still need data-flow, ledger/outcome accumulation, and demo execution realism.
- Mixed-horizon side-cells are a concrete edge-amplification route: retiming and side-cell specialization may cross cost where a global threshold change would be too blunt.
- MM remains a current-fee cost-wall problem until train-confirmed gross edge clears the round-trip fee across windows.
- Fee/rebate is a business/scale route, not alpha proof.
- Polymarket and Gate-B remain evidence-building paths, not promotion evidence.

## Verification

- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/profitability_path_scorecard.py helper_scripts/db/audit/demo_order_stall_audit.py helper_scripts/db/audit/demo_data_flow_monitor.py helper_scripts/db/audit/test_demo_order_stall_audit.py helper_scripts/research/tests/test_profitability_path_scorecard.py`
- `python3 -m pytest helper_scripts/research/tests/test_profitability_path_scorecard.py helper_scripts/db/audit/test_demo_order_stall_audit.py helper_scripts/db/audit/test_demo_data_flow_monitor.py -q` = `20 passed`
- `python3 -m pytest helper_scripts/research/tests/test_profitability_path_scorecard.py helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_cost_gate_learning_lane_decision_packet.py helper_scripts/db/audit/test_demo_order_stall_audit.py helper_scripts/db/audit/test_demo_data_flow_monitor.py -q` = `73 passed`
- `git diff --check` passed

## Boundary

No runtime env/cron/deploy/restart, PG write/schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy mutation, Cost Gate lowering, probe/order authority, or promotion proof is granted.

Next runtime step after source sync: run the scorecard on `trade-core` artifacts, rerun the data-flow monitor with the SQL fix, and refresh the profit-learning packet.
