# 2026-06-22 — Demo-Learning Activation Packet Alpha Ingestion

本輪把 v407 activation packet 接進 alpha runtime 和 learning worklist。

效果：

- `alpha_discovery_runtime_killboard_v8` 會讀 canonical activation packet。
- `alpha_learning_worklist_v5` 會攜帶 packet evidence。
- 如果 packet 是 `READY_FOR_OPERATOR_DRY_RUN`，blocker 會變成：
  `demo_learning_stack_activation_packet_ready_for_operator_dry_run`
  而不是泛化的 `demo_learning_stack_not_installed`。

它會把以下資訊帶進 worklist：

- 缺哪些 cron；
- dry-run preview command；
- operator-only apply command；
- rollback command；
- post-install verification command；
- Cost Gate escape thesis；
- edge-amplification levers；
- `global_cost_gate_lowering_recommended=false`；
- `order_authority_granted=false`；
- `probe_authority_granted=false`；
- `promotion_proof=false`。

已驗證：

- Mac py_compile passed；
- Mac focused alpha/worklist pytest `62 passed`；
- source commit `277b00be` pushed with `[skip ci]`；
- Linux source fast-forwarded to `277b00be`；
- Linux py_compile + same focused pytest `62 passed`；
- Mac/Linux `git diff --check` clean。

這不是 cron install，也不是降低 Cost Gate，也不是 probe/order 授權。

下一個 operator action 仍然只是審核 packet 裡的 dry-run path。只有另行批准 apply，四條 demo-learning stack cron 才能開始真正持續積累 rejected-signal learning evidence。
