# 2026-06-22 — Demo-Learning Stack Activation Packet

本輪不是安裝 cron，也不是降低 Cost Gate，更不是授權 probe/order。

核心新增：`helper_scripts/cron/demo_learning_stack_activation_packet.py`。它只讀 stack healthcheck 和 Cost Gate activation preflight，生成一份 operator-review packet，列出：

- 目前 stack 狀態；
- 缺失的四條 cron；
- 四件套 planned stack；
- dry-run preview command；
- operator-only apply command；
- rollback command；
- post-install verification command；
- Cost Gate escape thesis 和 edge-amplification levers；
- no-authority 邊界。

Linux read-only smoke 現狀：

- `status=READY_FOR_OPERATOR_DRY_RUN`
- `healthcheck_status=NOT_INSTALLED`
- `source_ready=true`
- `stack_installed=false`
- `missing_cron_count=4`
- missing crons：demo evidence、sealed horizon preflight、Cost Gate learning lane、stack healthcheck
- `sealed_preflight_present=true`
- `bounded_reviews_present=false`
- `global_cost_gate_lowering_recommended=false`
- `order_authority_granted=false`
- `probe_authority_granted=false`

已驗證：Mac py_compile passed；Mac focused pytest `12 passed`；source commit `43f228f3` pushed；Linux source fast-forward 到 `43f228f3`；Linux py_compile + focused pytest `12 passed`；Linux `git diff --check` clean。

本 note 不授權 runtime cron install。若要推進到真正積累自主學習數據，下一個 operator action 是先跑 packet 中的 dry-run preview；只有 installer preflight 通過後，才另行決定是否 apply。
