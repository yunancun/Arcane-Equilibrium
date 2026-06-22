# Runtime Source Reconcile Planner

結論：v370 的手工 runtime dirty-tree manifest 已轉成可重跑的只讀 planner。這沒有修復 `trade-core` runtime source drift，但能讓下一次 operator-approved reconcile 前先產生 machine-readable preserve/review 清單，避免再次手工比對 55 個路徑。

## What Changed

- Added `helper_scripts/deploy/runtime_source_reconcile_planner.py`.
- Added focused tests in `helper_scripts/deploy/tests/test_runtime_source_reconcile_planner.py`.
- Updated `TODO.md` to v371, `docs/CLAUDE_CHANGELOG.md`, `helper_scripts/SCRIPT_INDEX.md`, and PM memory.

## Planner Behavior

The planner compares current worktree paths against a locally available `--target-ref` and emits JSON by default.

Primary classes:

- `tracked_dirty_equals_target`
- `tracked_absent_equals_target_absent`
- `tracked_dirty_differs_from_target`
- `tracked_missing_or_nonfile`
- `tracked_path_absent_from_target`
- `untracked_equals_target`
- `untracked_conflicts_with_target_path`
- `untracked_not_in_target`
- `unreadable_worktree_path`

Review-required classes are fail-closed and listed under `review_required_paths`. Target ref absence returns `TARGET_REF_UNAVAILABLE`; the tool does not fetch.

## Example Read-Only Use

```bash
python3 helper_scripts/deploy/runtime_source_reconcile_planner.py \
  --repo-root /home/ncyu/BybitOpenClaw/srv \
  --target-ref <approved-main-sha-or-local-ref> \
  --json-output /tmp/openclaw/runtime_source_reconcile_plan.json \
  --fail-on-review-required
```

The command above is still only a planner. It does not authorize or perform any reconcile.

## Verification

- `python3 -m py_compile helper_scripts/deploy/runtime_source_reconcile_planner.py helper_scripts/deploy/tests/test_runtime_source_reconcile_planner.py`
- `python3 -m pytest helper_scripts/deploy/tests/test_runtime_source_reconcile_planner.py -q` → `4 passed`
- `git diff --check`
- Local self-check against `origin/main` returned `REVIEW_REQUIRED_BEFORE_RECONCILE` while this batch was still uncommitted local work, which is the expected fail-closed behavior.

## Boundary

Source/test/docs only, plus optional explicit `--json-output` plan artifact. No runtime fetch, pull, checkout, reset, clean, source sync, crontab install, env edit, deploy, rebuild, restart, PG write/schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy mutation, writer enablement, Cost Gate lowering, order authority, probe authority, or promotion proof was performed.

## Next Operator-Gated Step

After this commit is pushed and the target commit is available on `trade-core`, run the planner read-only on runtime. If review-required paths remain, archive/preserve or explicitly discard them before any destructive reconcile. Only after runtime source is clean at the approved head should the demo-learning stack installer dry-run and healthcheck path be retried.
