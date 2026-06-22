# 2026-06-22 — Demo-Learning Stack Dry-Run Review Alpha Ingestion

本輪把 demo-learning stack 的 installer dry-run review 接進既有 alpha cron。

當前 Linux runtime smoke 結果：

- dry-run status: `DRY_RUN_PREVIEW_PASSED_OPERATOR_APPLY_REVIEW_REQUIRED`
- installer rc: `0`
- forced apply gate: `0`
- mutates crontab: `false`
- crontab mutated: `false`
- source: `SYNCED_CLEAN`
- alpha schema: `alpha_discovery_runtime_killboard_v8`
- worklist schema: `alpha_learning_worklist_v5`
- worklist status: `OPERATOR_GATED_LEARNING_READY`
- top task: `cost_gate_learning_activation`
- blocker: `demo_learning_stack_dry_run_preview_passed_operator_apply_review_required`
- next trigger: `operator_review_dry_run_preview_then_apply_learning_stack_if_accepted`
- Cost Gate lowering: `false`
- order authority: `false`
- probe authority: `false`

已驗證：

- Mac cron tests `9 passed`
- Mac research tests `64 passed`
- Linux cron tests `9 passed`
- Linux research tests `64 passed`
- Linux artifact-only alpha cron smoke passed
- source commit `5eb46806` pushed with `[skip ci]`

這不是：

- cron install
- Cost Gate lowering
- probe/order authority
- PG write/schema migration
- Bybit private/signed/trading call
- deploy/rebuild/restart
- env/auth/risk/order/strategy mutation
- promotion proof

下一個 operator action 是 review dry-run preview。只有另行批准 apply，四條 demo-learning stack cron 才會開始持續累積 rejected-signal learning evidence。
