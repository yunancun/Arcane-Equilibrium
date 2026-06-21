# Cost-Gate Blocked-Signal Outcome Feedback

## Summary

This batch closes the next learning-loop gap: recorded cost-gate rejects that were not allowed to submit orders can now receive market markout outcome rows.

The new row type is `blocked_signal_outcome`. It is counterfactual learning evidence only. It is not a probe fill, not a `probe_outcome`, not promotion evidence, and not order authority.

## Why

The runtime ledger writer can record current selected side-cells as `ORDER_AUTHORITY_NOT_GRANTED`, but without a follow-up outcome row the system can only prove that the reject was captured, not whether the blocked signal later moved profitably.

The operator question was explicit: if the cost gate blocks a new signal, is it recorded, and is there a mechanism to verify later whether the blocked signal truly lacked profit potential? This adds that mechanism while keeping the main gate closed.

## Implementation

- Added shared record constants in `cost_gate_learning_lane/contract.py`.
- Extended `outcome_writer.py` with `build_blocked_signal_outcome_records(...)`.
- Extended `runtime_adapter.py` with `--record-blocked-outcomes`.
- `blocked_signal_outcome` rows process `probe_admission_decision` rows where `allowed_to_submit_order=false`.
- The rows include side-aware gross bps, explicit cost, realized net bps, source admission decision, and `promotion_evidence=false`.
- `alpha_discovery_throughput.runtime_runner` now summarizes `cost_gate_learning_lane/probe_ledger.jsonl` ledger state:
  - missing / empty / admission rows present / probe outcomes present / blocked-signal outcomes present
  - admission counts
  - `ORDER_AUTHORITY_NOT_GRANTED` counts
  - probe outcome counts
  - blocked-signal outcome counts
  - blocked-signal positive outcome count and average net bps
- `discovery_loop` now changes the cost-gate blocker trigger by real ledger progress:
  - missing or empty ledger -> enable runtime writer
  - admission rows without blocked outcomes -> record blocked-signal outcomes
  - blocked outcomes present -> review outcomes before any probe order authority

## Guardrails

- No PG writes.
- No Bybit calls.
- No order submission.
- No main cost-gate relaxation.
- No runtime config mutation.
- `blocked_signal_outcome` is intentionally distinct from `probe_outcome`, so it does not feed the probe failed-outcome auto-disable path.
- `promotion_evidence=false` remains explicit.

## Verification

- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` -> 15 passed.
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` -> 34 passed.
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/contract.py helper_scripts/research/cost_gate_learning_lane/outcome_writer.py helper_scripts/research/cost_gate_learning_lane/runtime_adapter.py helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py` -> passed.
- `git diff --check` -> passed.

## Boundary

Source/test/docs only. No deploy, rebuild, restart, PG write, schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy/runtime mutation, signal proof, execution proof, or promotion proof.

## Next

1. Deploy/enable runtime writer only after operator review.
2. Observe `probe_admission_decision` rows.
3. Run `--record-blocked-outcomes` with local price observations to label blocked rows.
4. Review blocked-signal net distribution before any demo probe order authority.
