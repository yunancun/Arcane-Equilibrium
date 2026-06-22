# Runtime Source Reconcile Apply Packet

## 結論

新增 `helper_scripts/deploy/runtime_source_reconcile_apply.py`，把已完成的 read-only remote probe 和 review packet 轉成 operator-gated apply bundle。默認 dry-run；不會執行任何 runtime command。真 apply 必須同時具備：

- `--apply`
- exact `--expected-target-commit`
- exact `--expected-remote-head`
- expected dirty/review counts（建議帶上）
- `--review-packet`
- `--review-accepted`
- `--confirm-target-wins`
- `OPENCLAW_RUNTIME_SOURCE_RECONCILE_APPLY=1`

apply bundle 的命令順序是：fetch target、verify target object、archive dirty status/diff/worktree paths、reset to exact target、clean reviewed untracked paths、verify HEAD/status。

## True Runtime Dry Run

Command shape used against `trade-core` was dry-run only:

```bash
python3 helper_scripts/deploy/runtime_source_reconcile_apply.py \
  --local-repo-root . \
  --target-ref origin/main \
  --ssh-host trade-core \
  --remote-repo-root /home/ncyu/BybitOpenClaw/srv \
  --expected-target-commit eaed0cf23b1a350d7e2cbd84639710d840e9f2dd \
  --expected-remote-head 917be4cc9a3d3549328155f1863d42400c70267f \
  --expected-dirty-count 56 \
  --expected-review-required-count 13 \
  --review-packet docs/CCAgentWorkSpace/Operator/2026-06-22--runtime_source_reconcile_review_packet.md \
  --review-accepted \
  --confirm-target-wins \
  --human
```

Result:

- status: `DRY_RUN_OPERATOR_APPROVAL_REQUIRED`
- target: `eaed0cf23b1a350d7e2cbd84639710d840e9f2dd`
- remote HEAD: `917be4cc9a3d3549328155f1863d42400c70267f`
- probe status: `REVIEW_REQUIRED_BEFORE_REMOTE_RECONCILE`
- dirty paths: 56
- review-required paths: 13
- blockers: none
- commands executed: none

## Verification

- `python3 -m py_compile` for deploy planner/probe/apply scripts and tests passed.
- Focused deploy pytest passed: `11 passed`.
- Runtime apply-packet dry-run was read-only and produced only stdout.

## Boundary

No runtime fetch/pull/reset/clean/source sync was performed. No cron install, env edit, deploy/rebuild/restart, PG write/schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy mutation, writer enablement, Cost Gate lowering, order authority, probe authority, or promotion proof was performed.

## Next Step

The next non-repetitive step is an explicit operator decision: authorize the apply packet, or reject/adjust the target-wins disposition. After apply, rerun the remote probe and direct runtime planner before installing the demo-learning stack.
