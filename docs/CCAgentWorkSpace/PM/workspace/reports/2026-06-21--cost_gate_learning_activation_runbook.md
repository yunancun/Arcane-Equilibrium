# 2026-06-21 -- Cost-Gate Learning Activation Runbook

## 結論

本批沒有再加 source wrapper，也沒有做 runtime mutation。根據 v341 audit，剩餘 blocker 是 operator-approved runtime activation；因此新增一份 runbook，把 activation 拆成可審計 gate，避免在 dirty runtime tree 上即興操作。

Runbook:

- `docs/runbooks/2026-06-21--cost_gate_learning_lane_runtime_activation.md`

## 覆蓋範圍

Runbook 明確拆成：

- pre-activation read-only audit
- dirty runtime source reconcile / sync gate
- required source-file presence check
- `cost_gate_learning_lane.status` activation preflight
- cron dry-run preview
- cron install with `OPENCLAW_COST_GATE_LEARNING_CRON_APPLY=1`
- local JSONL append boundary for materialized rejects/outcomes
- optional hot-path writer env + approved restart gate
- post-activation observation
- rollback / stop conditions

它同時把 expected-head 改成 `PM_APPROVED_HEAD=REPLACE_WITH_PM_APPROVED_SHA` 變數，不硬編當前 SHA，避免 runbook 在下一個 commit 後變 stale，也避免 shell 把 angle-bracket placeholder 當 redirection。

## Routing Updates

- `docs/runbooks/README.md`
- `docs/_indexes/document_index.md`
- `docs/_indexes/initiative_index.md`
- `TODO.md` v342
- `docs/CLAUDE_CHANGELOG.md` v342
- PM memory

## Verification

- `git diff --check` passed
- runbook self-check:
  - contains `REPLACE_WITH_PM_APPROVED_SHA`
  - no stale fixed `1346b43d`
  - no malformed `''demo''` SQL quote pattern

## Boundary

Docs/runbook only. No runtime source sync, crontab edit, env edit, deploy/rebuild/restart, ledger append, PG write/schema migration, Bybit private/signed/trading call, writer enablement, order authority, or main Cost Gate lowering.

## Next

The next useful step requires operator approval to execute the runbook gates on `trade-core`: reconcile dirty source, sync to PM-approved `main`, run preflight, install/enable cron, then observe materializer/ledger/outcome/review artifacts.
