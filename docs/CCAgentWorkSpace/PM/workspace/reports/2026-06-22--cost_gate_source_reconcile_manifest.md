# Cost Gate Source Reconcile Manifest

日期：2026-06-22
角色：PM 主會話
狀態：PASS（source/test/docs + read-only runtime probe）

## 結論

這個 checkpoint 補的是 runtime activation 前最後一個實用可見性缺口：preflight 之前能說 source `DIRTY` / `BEHIND_UPSTREAM`，但沒有把「哪些 dirty path 需要人工 reconcile、下一步該做什麼」結構化輸出。

現在 `cost_gate_learning_lane.status` 的 source summary 會輸出：

- `source_reconcile_required`
- `source_reconcile_status`
- `source_reconcile_reasons`
- `source_reconcile_next_actions`
- `source_reconcile_dirty_manifest`
- `source_reconcile_dirty_manifest_truncated`
- `git_dirty_status_counts`

這不改變 activation gate，也不放寬任何條件；只是讓 operator 授權 source reconcile/sync 前能用同一個 preflight artifact 看到可機讀的 dirty manifest。

## 行為

- dirty/tracked/untracked paths：`DIRTY_PATH_REVIEW_REQUIRED`
- behind-only checkout：`SOURCE_SYNC_REQUIRED`
- synced clean checkout：`SOURCE_RECONCILE_NOT_REQUIRED`

dirty manifest row 包含：

- git status code
- path
- optional old path
- tracked/untracked category
- action hint

manifest capped at 50 rows and marks truncation instead of emitting unbounded output.

## Same-Turn Runtime Fact

2026-06-22 read-only `trade-core` check confirmed the external blocker remains:

- runtime source：`HEAD=917be4cc`
- local `origin/main=1401848b`
- checkout：`behind 5` plus many dirty/untracked paths
- learning lane：only old `demo_learning_lane_plan_latest.json`; no heartbeat/status log/ledger/materializer/outcome refresh/review
- engine PID：`35187`, no `OPENCLAW_DEMO_LEARNING_LANE_*` writer env
- PG 1h/4h/24h demo/live_demo reject counts remain present, but no recent orders/fills
- alpha latest remains old schema `alpha_discovery_runtime_killboard_v1` with stale actionable flags

## Verification

- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/status.py helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` = `63 passed`
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` = `44 passed`

## Boundary

Performed:

- source/test/docs edits
- read-only runtime ssh/git/ls/PG SELECT/proc/artifact inspection

Not performed:

- runtime source sync
- artifact refresh
- crontab edit/install
- env edit
- deploy/rebuild/restart
- PG write/schema migration
- Bybit private/signed/trading call
- credential/auth/risk/order/strategy mutation
- order authority
- Cost Gate lowering
- execution proof or promotion proof

## Review Attention

`helper_scripts/research/cost_gate_learning_lane/status.py` is now about 1700 lines, above the 800-line review-attention threshold and below the 2000-line hard cap. This change was kept in-file because it extends the existing source summary/preflight contract. If this surface grows again, split source/git reconcile helpers into a dedicated module before adding more behavior.

## Next

The actual runtime closure still needs explicit operator authorization:

1. review/preserve/discard dirty runtime local changes;
2. sync runtime source to PM-approved head;
3. rerun activation preflight;
4. run preinstall refresh-only;
5. install/enable the learning cron;
6. separately decide whether to enable hot-path writer env and restart.

Until then, demo will continue recording Cost Gate rejects without converting them into learning-lane outcomes.
