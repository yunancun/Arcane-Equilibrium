# PM Report: Cost-Gate Learning Source-Sync Activation Gate

Date: 2026-06-21

## Objective

Prevent cost-gate learning writer/cron activation on a stale or dirty runtime checkout. The previous preflight could tell whether artifacts were accumulating, but it did not make source sync/dirty state part of the same machine-readable activation evidence.

## Runtime Fact

Read-only probe still shows Linux `trade-core` at `917be4cc`, behind origin/main by 5 commits, with many modified/untracked files. Cost-gate learning artifacts are still missing:

- `probe_ledger.jsonl`
- `outcome_refresh_latest.json`
- `blocked_outcome_review_latest.json`
- `cron_heartbeat/cost_gate_learning_lane.last_fire`
- `logs/cost_gate_learning_lane.log`

Therefore runtime is not accumulating cost-gate learning evidence, and activation must first reconcile source state.

## Change

Extended `helper_scripts/research/cost_gate_learning_lane/status.py` with read-only local git checkout readiness.

New fields include:

- `source_activation_status`
- `source_activation_ready`
- `git_head_short`
- `git_branch`
- `git_upstream`
- `git_ahead_count`
- `git_behind_count`
- `git_dirty_path_count`
- `git_untracked_path_count`
- `git_dirty_path_sample`
- `runtime_source_ready_for_activation`
- `activation_blockers`

The git checks use only local metadata: `git rev-parse`, `git status --porcelain`, and `git rev-list` against the configured upstream. They do not fetch, pull, reset, clean, deploy, restart, or mutate runtime state.

## Verification

- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` = 33 passed
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` = 34 passed
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/status.py helper_scripts/research/alpha_discovery_throughput/runtime_runner.py` passed

## Boundary

Source/test/docs + read-only Linux probe only. No deploy, restart, PG write/schema migration, Bybit private/signed/trading call, order authority, auth/risk/runtime/config mutation, main Cost Gate lowering, execution proof, signal proof, or promotion proof.
