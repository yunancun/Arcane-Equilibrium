# Runtime Source Reconcile Blocker Manifest

結論：`trade-core` 不是單純 behind，而是一個 selective-restore mixed tree。這是 demo-learning stack 無法安全安裝的當前 blocker。好消息是 55 個 dirty/untracked 路徑中有 43 個已經等於 current main；真正需要 operator/PM preserve/reconcile 決策的是少數衝突路徑。

## Read-Only Facts

- Runtime source HEAD：`917be4cc9a3d3549328155f1863d42400c70267f`
- Runtime local `origin/main`：`1401848b5f61136051d2b623c71dbad006a99459`
- GitHub/local main：`e2b90306d919426bc109d82b32ca9ff5b021dd01`
- Runtime HEAD is ancestor of local/GitHub main：`true`
- Dirty status count：55 paths (`36` modified, `19` untracked)
- Demo-learning stack cron grep：`NO_DEMO_LEARNING_STACK_CRON_MATCHES`
- Missing artifacts：healthcheck latest JSON, healthcheck status log, healthcheck heartbeat, demo evidence heartbeat, Cost Gate learning heartbeat

## Dirty Tree Classification

| Class | Count | Meaning |
|---|---:|---|
| `tracked_dirty_equals_current_main` | 29 | Runtime file is dirty relative to old HEAD but already equals current main. |
| `untracked_equals_current_main` | 14 | Runtime untracked file already equals a tracked current-main file. |
| `tracked_dirty_differs_from_current_main` | 7 | Must be reviewed/preserved before reset/clean. |
| `untracked_conflicts_with_current_main_path` | 3 | Would conflict with current-main tracked paths. |
| `untracked_not_in_current_main` | 2 logical entries | One local-only report plus the untracked Cost Gate learning-lane directory. |

## Review-Required Paths

Tracked dirty paths that differ from current main:

- `TODO.md`
- `docs/CCAgentWorkSpace/PM/memory.md`
- `docs/CLAUDE_CHANGELOG.md`
- `helper_scripts/SCRIPT_INDEX.md`
- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
- `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
- `helper_scripts/research/tests/test_alpha_discovery_throughput.py`

Untracked files that conflict with current-main paths:

- `helper_scripts/db/audit/cost_gate_reject_counterfactual.py`
- `helper_scripts/db/audit/test_cost_gate_reject_counterfactual.py`
- `helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py`

Untracked Cost Gate learning-lane directory:

- `helper_scripts/research/cost_gate_learning_lane/__init__.py` differs from current main.
- `helper_scripts/research/cost_gate_learning_lane/policy.py` differs from current main.
- `helper_scripts/research/cost_gate_learning_lane/__pycache__/__init__.cpython-312.pyc` is local-only.
- `helper_scripts/research/cost_gate_learning_lane/__pycache__/policy.cpython-312.pyc` is local-only.

## Interpretation

The 43 content-equivalent paths are residue from selective runtime source restores; they do not need semantic preservation. The review-required paths are mostly stale partial versions of files that later evolved on main. They should still be archived or explicitly discarded by an operator-approved reconcile step because a reset/clean would be destructive to the runtime working tree.

## Boundary

This report used read-only `ssh trade-core` commands only: git status/rev-parse/ls-remote, crontab inspection, file existence checks, and local/remote hash comparison. No runtime fetch, pull, reset, clean, source sync, crontab install, env edit, deploy, rebuild, restart, PG write, Bybit call, writer enablement, Cost Gate lowering, or order/probe authority was performed.

## Next Operator-Gated Step

If approved, the safe runtime path is:

1. Archive or otherwise preserve the review-required runtime paths above.
2. Reconcile runtime source to approved main `e2b90306d919426bc109d82b32ca9ff5b021dd01`.
3. Dry-run `helper_scripts/cron/install_demo_learning_stack_crons.sh` with expected head.
4. Only after a clean dry-run/preflight, apply the three-cron stack.
5. Verify healthcheck latest JSON, the three heartbeats, and Cost Gate learning ledger/outcome/review accumulation before any bounded demo-probe review.
