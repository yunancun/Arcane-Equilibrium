# 2026-06-22 — Demo-Learning Stack Dry-Run Review Alpha Ingestion

## 結論

v409 讓 alpha cron 能持續刷新 activation packet，但下一步仍只是「應該跑 dry-run」。v410 把 dry-run 本身也變成可追蹤 artifact，並接回 alpha/worklist。

目前 Linux runtime evidence 顯示 dry-run preview 已通過，但仍停在 operator apply review gate。這不是 cron install，也不是 Cost Gate lowering。

## Source 變更

- Added `helper_scripts/cron/demo_learning_stack_dry_run_review.py`
  - reads canonical `demo_learning_stack_activation_packet_latest.json`;
  - resolves current source HEAD;
  - runs `install_demo_learning_stack_crons.sh` only with `OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=0`;
  - writes `demo_learning_stack_dry_run_review_v1`;
  - records return code, stdout/stderr tails, forced apply gate, crontab mutation flag, and no-authority answers.
- Updated `helper_scripts/cron/alpha_discovery_throughput_cron.sh`
  - refreshes activation packet;
  - refreshes dry-run review;
  - then runs alpha runtime.
- Updated alpha/worklist ingestion so passed dry-run preview becomes:

`demo_learning_stack_dry_run_preview_passed_operator_apply_review_required`

## Runtime Evidence

Linux artifact-only smoke after source sync:

- dry-run status: `DRY_RUN_PREVIEW_PASSED_OPERATOR_APPLY_REVIEW_REQUIRED`
- reason: `installer_dry_run_preview_passed_without_crontab_mutation`
- expected head: `5eb46806a8f3`
- installer rc: `0`
- forced apply gate: `0`
- mutates crontab: `false`
- crontab mutated: `false`
- operator apply required: `true`
- global Cost Gate lowering recommended: `false`
- order authority granted: `false`
- probe authority granted: `false`
- alpha schema: `alpha_discovery_runtime_killboard_v8`
- alpha created: `2026-06-22T15:45:27.917464+00:00`
- source status: `SYNCED_CLEAN`
- worklist schema: `alpha_learning_worklist_v5`
- worklist status: `OPERATOR_GATED_LEARNING_READY`
- top task: `cost_gate_learning_activation`
- blocker: `demo_learning_stack_dry_run_preview_passed_operator_apply_review_required`
- objective: `operator_review_learning_stack_dry_run_preview_before_cron_apply`

## Verification

- Mac `bash -n` passed.
- Mac py_compile passed.
- Mac cron tests: `9 passed`.
- Mac research alpha/worklist tests: `64 passed`.
- Source commit: `5eb46806a8f3dba84036a5a5b173330b26f6e6f5` (`[skip ci]`).
- Linux source fast-forwarded to `5eb46806`.
- Linux `bash -n` + py_compile passed.
- Linux cron tests: `9 passed`.
- Linux research alpha/worklist tests: `64 passed`.
- Linux artifact-only alpha cron smoke passed and source remained clean.

## PM Read

The profitable path still is not a blanket lower Cost Gate. The better engineering loop is:

1. activate the demo-learning stack only after operator review;
2. continuously accumulate rejected-signal ledger/outcome/review evidence;
3. identify side-cell/horizon-specific blocked signals where matched controls show real gross edge;
4. use bounded demo probes only after review, then measure whether execution captures the control edge.

v410 removes the last opaque step before stack activation: the operator can now inspect a concrete dry-run preview and know it did not mutate crontab or grant trading authority.

## Boundary

No CI run. No PG write/schema migration. No Bybit private/signed/trading call. No deploy/rebuild/restart. No crontab install. No writer/env/auth/risk/order/strategy mutation. No Cost Gate lowering. No probe/order authority. No promotion proof.
