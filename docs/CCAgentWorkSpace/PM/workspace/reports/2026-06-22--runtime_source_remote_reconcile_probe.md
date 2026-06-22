# Runtime Source Remote Reconcile Probe

結論：新增 Mac-side read-only remote probe 後，即使 `trade-core` runtime 尚未 fetch target commit，也能用本地 approved target tree 直接比對 runtime worktree，生成 preserve/review 清單。這推進了 source drift blocker 的可操作性，但仍沒有執行 runtime reconcile。

## Why This Was Needed

v371 planner requires the target object to exist in the inspected repo. Runtime currently cannot resolve target `6e29c06f44b343f805f3f5eaab36208cf1b608cc`, so direct runtime planner execution would fail closed before producing a path manifest.

The new `helper_scripts/deploy/runtime_source_remote_reconcile_probe.py` solves that gap by:

- reading target blobs from the local repo;
- reading remote `git status` and worktree file/symlink bytes over SSH;
- comparing the two without requiring the target object on runtime;
- emitting the same review-required vs content-equivalent planning surface.

## Runtime Probe Result

Command shape:

```bash
python3 helper_scripts/deploy/runtime_source_remote_reconcile_probe.py \
  --local-repo-root . \
  --target-ref origin/main \
  --ssh-host trade-core \
  --remote-repo-root /home/ncyu/BybitOpenClaw/srv \
  --human
```

Result:

- status: `REVIEW_REQUIRED_BEFORE_REMOTE_RECONCILE`
- target: `6e29c06f44b343f805f3f5eaab36208cf1b608cc`
- runtime HEAD: `917be4cc9a3d3549328155f1863d42400c70267f`
- runtime local `origin/main`: `1401848b5f61136051d2b623c71dbad006a99459`
- runtime target object available: `false`
- dirty/untracked paths: `56`
- content-equivalent paths: `43`
- review-required paths: `13`

Class counts:

- `tracked_dirty_equals_target`: 29
- `tracked_dirty_differs_from_target`: 7
- `untracked_equals_target`: 14
- `untracked_conflicts_with_target_path`: 5
- `untracked_not_in_target`: 1

Review-required paths:

- `TODO.md`
- `docs/CCAgentWorkSpace/PM/memory.md`
- `docs/CLAUDE_CHANGELOG.md`
- `helper_scripts/SCRIPT_INDEX.md`
- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
- `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
- `helper_scripts/research/tests/test_alpha_discovery_throughput.py`
- `docs/CCAgentWorkSpace/E1/workspace/reports/vol-event-robust-ruling.md`
- `helper_scripts/db/audit/cost_gate_reject_counterfactual.py`
- `helper_scripts/db/audit/test_cost_gate_reject_counterfactual.py`
- `helper_scripts/research/cost_gate_learning_lane/__init__.py`
- `helper_scripts/research/cost_gate_learning_lane/policy.py`
- `helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py`

## Demo Data Context

Read-only runtime PG check at approximately `2026-06-22 03:16 +02`:

- `1h`: decision_features `0`, risk_verdicts `0`, intents `0`, orders `0`, fills `0`
- `4h`: decision_features `2699`, risk_verdicts `2699`, intents `3`, orders `3`, fills `0`
- `24h`: decision_features `56155`, risk_verdicts `56155`, intents `3`, orders `3`, fills `0`
- 4h risk reasons: `2696` Cost Gate negative-edge blocks, `3` empty reasons
- 24h orders: all `flash_dip_buy`, status `Working`, no fills

Interpretation: engine/watchdog are alive, but demo data is intermittent; most signals are Cost Gate blocked, and the few orders that passed are unfilled maker orders. Demo-learning stack heartbeats/latest artifacts are still absent.

## Verification

- `python3 -m py_compile helper_scripts/deploy/runtime_source_reconcile_planner.py helper_scripts/deploy/runtime_source_remote_reconcile_probe.py helper_scripts/deploy/tests/test_runtime_source_reconcile_planner.py helper_scripts/deploy/tests/test_runtime_source_remote_reconcile_probe.py`
- `python3 -m pytest helper_scripts/deploy/tests/test_runtime_source_reconcile_planner.py helper_scripts/deploy/tests/test_runtime_source_remote_reconcile_probe.py -q` → `7 passed`
- `git diff --check`
- true runtime remote probe passed read-only and wrote only local `/tmp/runtime_source_remote_reconcile_plan.json`

## Boundary

Source/test/docs plus read-only SSH/git/worktree/PG probes and optional local JSON artifact only. No runtime fetch, pull, checkout, reset, clean, source sync, crontab install, env edit, deploy, rebuild, restart, PG write/schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy mutation, writer enablement, Cost Gate lowering, order authority, probe authority, or promotion proof was performed.

## Next Operator-Gated Step

1. Preserve or explicitly discard the 13 review-required runtime paths.
2. Under operator approval, make target `6e29c06f44b343f805f3f5eaab36208cf1b608cc` available on runtime and reconcile source.
3. Rerun the direct runtime planner or the Mac-side remote probe until source is clean/equivalent.
4. Only then dry-run/install demo-learning stack crons and verify healthcheck/heartbeats/ledger/outcome/review accumulation before considering any bounded Cost Gate learning review.
