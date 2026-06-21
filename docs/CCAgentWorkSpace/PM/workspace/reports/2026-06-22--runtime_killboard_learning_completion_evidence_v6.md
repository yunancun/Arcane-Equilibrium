# Runtime Killboard Learning Completion Evidence v6

## Summary

This checkpoint makes the runtime killboard/history expose the completion contract for the current top learning task.

`alpha_discovery_throughput.runtime_runner` now emits schema `alpha_discovery_runtime_killboard_v6`. The top-level killboard and history rows mirror:

- `top_learning_task_completion_gate`
- `top_learning_task_completion_status`
- `top_learning_task_completion_evidence_required_count`
- `top_learning_task_evidence_key_count`
- compact `top_learning_task_evidence`
- Cost Gate top blocked-review candidate side-cell, wrongful-block score, and net cost cushion when present

## Why

v359-v363 made the learning worklist richer, but operator/runtime consumers still had to parse the full worklist to know what proves the top task complete. v6 exposes the practical completion/evidence surface directly beside the killboard action flags.

## Files

- `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
- `helper_scripts/research/tests/test_alpha_discovery_throughput.py`
- `TODO.md`
- `docs/CLAUDE_CHANGELOG.md`
- `helper_scripts/SCRIPT_INDEX.md`
- `docs/CCAgentWorkSpace/PM/memory.md`

## Verification

- `PYTHONPATH=helper_scripts/research python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/alpha_discovery_throughput/learning_worklist.py helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py` -> `48 passed`

## Boundary

Source/test/docs only. No runtime source sync, artifact refresh, crontab/env edit, deploy/rebuild/restart, PG write/schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy mutation, Cost Gate lowering, order authority, execution proof, or promotion proof.

## Next

After operator-approved runtime source reconcile, a fresh alpha discovery runtime artifact should show v6 schema and top learning task completion/evidence fields. Until then, existing runtime artifacts remain stale if generated from old source.
