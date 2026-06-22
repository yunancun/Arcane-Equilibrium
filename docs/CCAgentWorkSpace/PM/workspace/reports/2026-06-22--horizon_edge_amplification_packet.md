# Horizon Edge Amplification Packet

Date: 2026-06-22

## Verdict

`DONE_WITH_BOUNDARIES`.

This checkpoint turns the profitability scorecard's horizon retiming path into a reusable artifact. It does not claim profitability and does not authorize a probe; it names which mixed-horizon side-cell should go through sealed replay before any operator review.

## Changes

- Added `helper_scripts/research/alpha_discovery_throughput/horizon_edge_amplification.py`.
- Added focused tests in `helper_scripts/research/tests/test_horizon_edge_amplification.py`.
- New schema: `horizon_edge_amplification_packet_v1`.
- Input: existing `cost_gate_reject_counterfactual_v2` JSON.
- Output classes:
  - `RETIMING_CANDIDATE`: blocked on the primary horizon but positive on another horizon.
  - `STABLE_MULTI_HORIZON_CANDIDATE`: positive across multiple horizons.
  - `SINGLE_HORIZON_CANDIDATE`: positive on one available horizon.
- Each candidate carries best horizon, primary-horizon action/net, edge amplification versus primary, effective sample count, required next gate, and authority boundary.

## Interpretation

The current profit path is more specific than "lower the Cost Gate": mixed-horizon evidence says some cells may need horizon-specific replay and side-cell routing. For the latest runtime counterfactual, the expected top candidate is `ma_crossover|BTCUSDT|Sell`: primary 60m is block-confirmed, while 240m is positive.

That is an edge-amplification thesis, not an execution proof. The next gate is sealed horizon-specific replay, then bounded demo probe review only after the learning stack is actually accumulating ledger/outcome evidence.

## Verification

- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/horizon_edge_amplification.py helper_scripts/research/tests/test_horizon_edge_amplification.py`
- `python3 -m pytest helper_scripts/research/tests/test_horizon_edge_amplification.py -q` = `2 passed`
- `python3 -m pytest helper_scripts/research/tests/test_horizon_edge_amplification.py helper_scripts/research/tests/test_profitability_path_scorecard.py helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` = `52 passed`
- `git diff --check` passed

## Boundary

No PG query/write/schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy/runtime mutation, deploy/rebuild/restart, Cost Gate lowering, probe/order authority, or promotion proof is granted.

Next runtime step after source sync: run the packet on the current counterfactual artifact and inspect the ranked retiming candidate before deciding whether to build sealed replay.
