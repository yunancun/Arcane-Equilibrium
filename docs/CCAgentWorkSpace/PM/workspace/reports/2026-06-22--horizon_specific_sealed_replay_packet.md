# Horizon-Specific Sealed Replay Packet

Date: 2026-06-22

## Verdict

`DONE_WITH_BOUNDARIES`.

This checkpoint turns the horizon retiming proof gate into a reusable sealed replay packet. It does not claim profitability, does not grant a probe, and does not lower the Cost Gate.

## Changes

- Added `helper_scripts/research/alpha_discovery_throughput/horizon_specific_sealed_replay.py`.
- Added focused tests in `helper_scripts/research/tests/test_horizon_specific_sealed_replay.py`.
- New schema: `horizon_specific_sealed_replay_packet_v1`.
- Inputs:
  - preselected `horizon_edge_amplification_packet_v1`
  - replay `cost_gate_reject_counterfactual_v2` artifact
- The packet hashes both inputs and validates:
  - candidate is present and is `RETIMING_CANDIDATE`
  - replay row exists for the selected best horizon
  - selected best horizon still matches replay
  - replay row is `LEARNING_PROBE_CANDIDATE`
  - effective sample / avg net / median gross / hit-rate gates pass
  - primary horizon remains block-confirmed and net-negative
  - edge amplification is positive
  - replay metrics stay within drift tolerance

## Interpretation

This closes the gap between "BTCUSDT Sell 240m looks interesting" and "the selected candidate can be reviewed without hindsight-search ambiguity." The packet binds the selection to hashes and checks gates without looking for a better horizon.

It is still not execution proof. The next gates remain learning-stack ledger/outcome accumulation and then operator review before any bounded demo probe.

## Profitability Thesis Fit

This checkpoint is one step in the Cost Gate escape route, not the whole route. The intended path is to cross the Cost Gate by isolating where edge becomes real: horizon retiming, side-cell filtering, stronger alpha inputs, and execution-realism proof. Global Cost Gate lowering is still rejected because it would raise order count without proving net edge.

The longer-term system target is a durable autonomous learning loop: Demo mode produces rejected/accepted/fill/outcome evidence, cold-path packets convert that evidence into falsifiable candidates, and only machine-checkable candidates become operator-reviewable bounded probes. Profitability should come from learned edge amplification and selective exposure, not from weakening the hot-path Risk Governor.

## Verification

- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/horizon_specific_sealed_replay.py helper_scripts/research/tests/test_horizon_specific_sealed_replay.py`
- `python3 -m pytest helper_scripts/research/tests/test_horizon_specific_sealed_replay.py -q` = `4 passed`
- `python3 -m pytest helper_scripts/research/tests/test_horizon_specific_sealed_replay.py helper_scripts/research/tests/test_horizon_edge_amplification.py helper_scripts/research/tests/test_profitability_path_scorecard.py helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` = `56 passed`
- `git diff --check` passed

## Boundary

No PG query/write/schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy/runtime mutation, deploy/rebuild/restart, Cost Gate lowering, probe/order authority, or promotion proof is granted.

Next runtime step after source sync: generate the sealed replay packet from the current horizon packet and Cost Gate counterfactual artifacts, then inspect whether all gates pass for `ma_crossover|BTCUSDT|Sell` at 240m.
