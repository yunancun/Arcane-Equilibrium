# Cost-Gate Killboard Source-Readiness Blocker

Date: 2026-06-21  
Role: PM local implementation checkpoint  
Status: source/test/docs complete; runtime still unsynced

## Finding

Read-only runtime inspection found the latest alpha-discovery artifact still
classified `cost_gate_demo_learning_lane` as `probe_ready`, even though runtime
facts contradict that readiness:

- `trade-core` source remains at `917be4cc9a3d3549328155f1863d42400c70267f`.
- Runtime has no cost-gate learning cron entry.
- `/tmp/openclaw/cost_gate_learning_lane/` still contains only the old plan and
  policy stdout files.
- There is no active learning ledger/materializer/outcome-review loop.

This is a stale-runtime-code artifact, not true probe readiness.

## Change

- `alpha_discovery_throughput.runtime_runner.collect_cost_gate_learning_lane_arm`
  now attaches compact source activation fields from
  `cost_gate_learning_lane.status.summarize_cost_gate_learning_lane_source`
  when `repo_root` is available.
- The cost-gate arm detail now includes fields such as:
  - `learning_lane_source_activation_ready`
  - `learning_lane_source_activation_status`
  - `learning_lane_git_status`
  - `learning_lane_git_head_short`
  - `learning_lane_git_behind_count`
  - `learning_lane_git_dirty_path_count`
  - `learning_lane_expected_head_status`
- `discovery_loop._cost_gate_learning_lane_state` now blocks cost-gate probe
  readiness whenever `learning_lane_source_activation_ready=false`.

Resulting blocker:

```text
BLOCK / source_health / cost_gate_learning_lane_source_not_activation_ready
```

## Verification

- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` -> `63 passed`
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` -> `36 passed`
- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py`

Regression coverage proves that a valid `OPERATOR_REVIEW` cost-gate plan cannot
become probe-ready if the learning-lane source checkout is not activation-ready.

## Boundary

No runtime source sync, crontab edit/install, env edit, deploy/rebuild/restart,
runtime ledger append, PG write/schema migration, Bybit private/signed call,
writer enablement, order authority, or main Cost Gate lowering.

## PM Read

The cost-gate path remains the most direct learning lever, but runtime alpha
readiness must not be trusted until source is synced and alpha-discovery reruns
on the new code. The next operator-owned step is still runtime source
reconcile/sync, then pre-install refresh-only, activation preflight, and cron
installation if green.
