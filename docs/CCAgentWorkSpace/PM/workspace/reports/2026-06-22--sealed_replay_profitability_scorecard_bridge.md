# Sealed Replay Profitability Scorecard Bridge

Date: 2026-06-22

## Verdict

`DONE_WITH_BOUNDARIES`.

This checkpoint connects the passed horizon-specific sealed replay artifact back into the profitability path scorecard. It prevents the engineering loop from repeatedly recommending "build sealed replay" after the sealed replay already passed.

## Change

- Extended `helper_scripts/research/alpha_discovery_throughput/profitability_path_scorecard.py`.
- Added CLI input `--horizon-sealed-replay-json`.
- Added scorecard status `SEALED_HORIZON_REPLAY_READY_FOR_LEARNING_ACCUMULATION`.
- Added focused regression coverage in `helper_scripts/research/tests/test_profitability_path_scorecard.py`.

When a sealed replay packet passes for the same side-cell, the matching horizon retiming path now carries:

- sealed replay status and reason
- failed gate names
- best horizon metrics
- primary horizon block-confirmation metrics
- input sha256 hashes
- next gate: `learning_stack_accumulates_ledger_and_outcome_rows_for_sealed_horizon_candidate`

## Interpretation

This moves the Cost Gate profitability chain one gate forward:

1. Counterfactual identified horizon-specific positive edge.
2. Horizon amplification ranked the retiming side-cell.
3. Sealed replay revalidated the selected side-cell without hindsight search.
4. Profitability scorecard now recognizes that sealed state and points to learning-stack ledger/outcome accumulation.

The current blocker is therefore not "find the candidate again." It is runtime learning evidence: probe ledger, blocked-signal outcomes, writer/cron loop, and later execution realism.

## Verification

- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/profitability_path_scorecard.py helper_scripts/research/tests/test_profitability_path_scorecard.py`
- `python3 -m pytest helper_scripts/research/tests/test_profitability_path_scorecard.py -q` = `3 passed`
- `python3 -m pytest helper_scripts/research/tests/test_profitability_path_scorecard.py helper_scripts/research/tests/test_horizon_specific_sealed_replay.py helper_scripts/research/tests/test_horizon_edge_amplification.py helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` = `57 passed`
- `git diff --check` passed

## Boundary

Artifact-only source/test/docs plus future local artifact reads/writes. No PG query/write/schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy/runtime mutation, deploy/rebuild/restart, Cost Gate lowering, probe/order authority, or promotion proof.
