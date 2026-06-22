# Runtime Source Reconcile Recorded Target Dry Run

日期：2026-06-22
角色：PM
範圍：只讀 runtime source reconcile 證據刷新；不執行 runtime apply。

重要口徑：本報告證明 recorded target `34066e5eb0aa15b51284d4e0013fbf73f4874784` 的 probe/dry-run 結果。後續文檔 commit 會自然推進 `origin/main`；若 operator 要 apply 較新的 target，必須先對 then-current `origin/main` 重跑 probe/dry-run。

## 結論

operator apply packet 已刷新到 recorded target `34066e5eb0aa15b51284d4e0013fbf73f4874784`。`trade-core` runtime source 仍停在 `917be4cc9a3d3549328155f1863d42400c70267f`，target object 尚未在 runtime 可用，dirty/untracked 路徑 56，其中 13 條仍屬 review-required。Apply helper dry-run 返回 `DRY_RUN_OPERATOR_APPROVAL_REQUIRED`，blockers 為空，預覽 10 條命令，但沒有在 runtime 執行任何命令。

這代表：下一步可以由 operator 審批是否使用 current-target apply packet 進行 source reconcile；在此之前，v375-v377 的 demo data-flow monitor、profit-learning packet、alpha/worklist ingestion 仍不能算已在 Linux runtime 運行。

## Recorded Target

- Local `HEAD`：`34066e5eb0aa15b51284d4e0013fbf73f4874784`
- Local `origin/main`：`34066e5eb0aa15b51284d4e0013fbf73f4874784`
- Runtime repo：`trade-core:/home/ncyu/BybitOpenClaw/srv`
- Runtime HEAD：`917be4cc9a3d3549328155f1863d42400c70267f`
- Local probe JSON：`/tmp/runtime_source_remote_reconcile_plan_current.json`
- Local apply dry-run JSON：`/tmp/runtime_source_reconcile_apply_plan_current.json`

## Read-Only Probe

Command shape:

```bash
python3 helper_scripts/deploy/runtime_source_remote_reconcile_probe.py \
  --local-repo-root . \
  --target-ref origin/main \
  --remote-mode ssh \
  --ssh-host trade-core \
  --remote-repo-root /home/ncyu/BybitOpenClaw/srv \
  --human \
  --json-output /tmp/runtime_source_remote_reconcile_plan_current.json
```

Result:

- status：`REVIEW_REQUIRED_BEFORE_REMOTE_RECONCILE`
- target：`34066e5eb0aa15b51284d4e0013fbf73f4874784`
- remote target object available：`false`
- dirty/untracked paths：56
- review-required paths：13
- class counts：
  - `tracked_dirty_equals_target=29`
  - `tracked_dirty_differs_from_target=7`
  - `untracked_equals_target=14`
  - `untracked_conflicts_with_target_path=6`

Review-required paths remain:

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

## Apply Dry Run

Command shape:

```bash
python3 helper_scripts/deploy/runtime_source_reconcile_apply.py \
  --local-repo-root . \
  --target-ref origin/main \
  --ssh-host trade-core \
  --remote-repo-root /home/ncyu/BybitOpenClaw/srv \
  --expected-target-commit 34066e5eb0aa15b51284d4e0013fbf73f4874784 \
  --expected-remote-head 917be4cc9a3d3549328155f1863d42400c70267f \
  --expected-dirty-count 56 \
  --expected-review-required-count 13 \
  --review-packet docs/CCAgentWorkSpace/Operator/2026-06-22--runtime_source_reconcile_review_packet.md \
  --review-accepted \
  --confirm-target-wins \
  --human \
  --json-output /tmp/runtime_source_reconcile_apply_plan_current.json
```

Result:

- status：`DRY_RUN_OPERATOR_APPROVAL_REQUIRED`
- probe status：`REVIEW_REQUIRED_BEFORE_REMOTE_RECONCILE`
- dirty/untracked paths：56
- review-required paths：13
- blockers：`[]`
- command count：10
- archive preview：`/tmp/openclaw/runtime_source_reconcile_archive/source_reconcile_20260622T022119Z_34066e5eb0aa`

The dry-run packet previews fetch, verify target object, archive status/diff/worktree paths, reset to target, clean reviewed untracked paths, and post-verify commands. These were only rendered into the local dry-run JSON/output; none were executed.

## Boundary

Performed:

- local `git fetch origin main`
- local source/head inspection
- read-only SSH runtime worktree probe
- local `/tmp` JSON artifact writes
- local `jq` inspection

Not performed:

- no runtime fetch/pull/checkout/reset/clean/stash/source sync
- no runtime cron install
- no env edit
- no deploy/rebuild/restart
- no PG query/write/schema migration
- no Bybit private/signed/trading call
- no credential/auth/risk/order/strategy mutation
- no writer enablement
- no Cost Gate lowering
- no order/probe authority
- no promotion proof

## Next Action

If operator approves runtime source reconcile, rerun this dry-run one more time immediately before real apply if `origin/main` has advanced or differs from the recorded target. Then execute only the reviewed apply path under the explicit `--apply` and `OPENCLAW_RUNTIME_SOURCE_RECONCILE_APPLY=1` gates.
