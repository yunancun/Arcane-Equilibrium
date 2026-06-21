# Learning Worklist Cost Gate Review Evidence v3

## Summary

This checkpoint connects the v362 Cost Gate blocked-outcome review ranking into the alpha learning worklist.

`alpha_discovery_throughput.learning_worklist` now emits schema `alpha_learning_worklist_v3`. Cost Gate outcome/probe review tasks carry the ranked blocked side-cell evidence directly in task `evidence`, including:

- blocked-review schema/status
- top blocked review side-cell
- top review candidate side-cell
- wrongful-block score
- net cost cushion
- latest learning-loop review top fields

When a Cost Gate operator-probe task has a ranked blocked side-cell, the task objective becomes:

`operator_review_top_blocked_signal_side_cell_before_bounded_demo_probe`

## Why

v362 made the blocked-outcome review artifact rank missed-profit opportunities, but the worklist still only said "operator probe review" or "cost gate outcome review." That made autonomous handoff weaker than necessary.

This update makes the work item itself name the concrete evidence that should be reviewed before any bounded demo probe.

## Files

- `helper_scripts/research/alpha_discovery_throughput/learning_worklist.py`
- `helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py`
- `TODO.md`
- `docs/CLAUDE_CHANGELOG.md`
- `helper_scripts/SCRIPT_INDEX.md`
- `docs/CCAgentWorkSpace/PM/memory.md`

## Verification

- `PYTHONPATH=helper_scripts/research python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/learning_worklist.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py` -> `3 passed`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_throughput.py` -> `44 passed`

## Boundary

Source/test/docs only. No runtime source sync, artifact refresh, crontab/env edit, deploy/rebuild/restart, PG write/schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy mutation, Cost Gate lowering, order authority, execution proof, or promotion proof.

## Next

After operator-approved runtime source reconcile and learning-lane activation, the worklist should show the same top blocked side-cell fields in task evidence. That will make the next operator/QC review more concrete before any bounded demo-probe authority is considered.
