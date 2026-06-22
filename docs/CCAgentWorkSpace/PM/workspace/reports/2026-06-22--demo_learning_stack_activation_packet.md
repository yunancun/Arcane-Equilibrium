# 2026-06-22 — Demo-Learning Stack Activation Packet

## 結論

v406 已證明 runtime source ready，但四條 demo-learning stack cron 全缺，所以 healthcheck 正確報 `NOT_INSTALLED`。這輪補的是「下一步該怎麼審核」：新增 no-authority activation packet，把 stack health、Cost Gate learning-lane activation preflight、缺失 cron、operator dry-run/apply/rollback/verification commands、以及盈利路徑的 Cost Gate escape thesis 放進同一個 machine-readable JSON。

這不是 cron install，不是 Cost Gate lowering，也不是 probe/order authorization。它只把「如何把 demo reject data 變成持續自主學習 evidence loop」從長文檔變成可重跑、可審核的 artifact。

## Source 變更

- `helper_scripts/cron/demo_learning_stack_activation_packet.py`
  - 新增 schema `demo_learning_stack_activation_packet_v1`。
  - 讀 `demo_learning_stack_healthcheck.build_healthcheck()` 與 `cost_gate_learning_lane.status.build_cost_gate_learning_lane_activation_preflight()`。
  - 輸出狀態分支：
    - `SOURCE_NOT_READY`
    - `READY_FOR_OPERATOR_DRY_RUN`
    - `STACK_ALREADY_ACTIVE`
    - `STACK_INSTALLED_REPAIR_REQUIRED`
    - `LEARNING_REVIEW_REFRESH_REQUIRED`
    - `REVIEW_REQUIRED`
  - 輸出四件套 planned stack：demo evidence、sealed horizon preflight、Cost Gate learning lane、stack healthcheck。
  - 輸出 operator commands：dry-run preview、operator-only apply、operator-only rollback、post-install verification。
  - 固定 no-authority answers：`global_cost_gate_lowering_recommended=false`、`order_authority_granted=false`、`probe_authority_granted=false`、`promotion_proof=false`。
- `helper_scripts/cron/tests/test_demo_learning_stack_activation_packet.py`
  - 覆蓋缺 cron -> `READY_FOR_OPERATOR_DRY_RUN`。
  - 覆蓋 dirty source -> `SOURCE_NOT_READY`。
  - 覆蓋 active stack -> `STACK_ALREADY_ACTIVE`。

## 對盈利路徑的含義

我們不應把 Cost Gate 逃逸理解成全局降門檻。更穩的路徑是：

1. 讓 demo/live_demo rejected signals 自動持續積累。
2. 對同 side-cell/horizon 的 blocked outcomes 做 matched-control review。
3. 只有當 blocked controls 顯示 Cost Gate 確實擋掉正 edge，才進 operator-reviewed bounded demo probe。
4. probe 結果再經 result review + execution-realism review，確認實際執行能捕獲控制組 edge。
5. 若 under-capture，先修 timing、slippage、fill-quality、horizon retiming，再談 Cost Gate/operator review。

這輪 packet 的價值是把第 1 步從「知道缺 cron」推進到「知道要審核哪個 dry-run / apply / rollback / verify 套件」，讓系統可以真正開始長期自主學習，而不是停在一次性測算。

## 驗證

- Mac py_compile passed：
  - `helper_scripts/cron/demo_learning_stack_activation_packet.py`
  - `helper_scripts/cron/tests/test_demo_learning_stack_activation_packet.py`
- Mac focused pytest：
  - `helper_scripts/cron/tests/test_demo_learning_stack_activation_packet.py`
  - `helper_scripts/cron/tests/test_demo_learning_stack_healthcheck.py`
  - result：`12 passed`
- Source commit：`43f228f367720effac6068b9f60c073684667fce Add demo learning stack activation packet [skip ci]`。
- GitHub `origin/main` pushed to `43f228f3` for the source checkpoint。
- Linux `trade-core:/home/ncyu/BybitOpenClaw/srv` fast-forwarded to `43f228f3`。
- Linux py_compile passed for the new packet and test。
- Linux focused pytest same suite：`12 passed`。
- Linux `git diff --check` passed。
- Linux read-only activation packet stdout smoke reported:
  - `status=READY_FOR_OPERATOR_DRY_RUN`
  - `reason=source_ready_but_one_or_more_stack_crons_missing`
  - `operator_next_action=run_dry_run_preview_then_apply_only_if_installer_preflight_passes`
  - `install_review_ready=true`
  - `healthcheck_status=NOT_INSTALLED`
  - `cost_gate_activation_status=REVIEW_CANDIDATE_OPERATOR_REVIEW`
  - `source_ready=true`
  - `stack_installed=false`
  - `missing_cron_count=4`
  - `missing_crons=["demo_learning_evidence","sealed_horizon_probe_preflight","cost_gate_learning_lane","demo_learning_stack_healthcheck"]`
  - `sealed_preflight_present=true`
  - `bounded_reviews_present=false`
  - `global_cost_gate_lowering_recommended=false`
  - `order_authority_granted=false`
  - `probe_authority_granted=false`

## 邊界

本 checkpoint 是 source/test/docs + Linux source sync/read-only/static tests + read-only activation packet stdout smoke。未執行 CI。沒有 PG write/schema migration、沒有 Bybit private/signed/trading call、沒有 deploy/rebuild/restart、沒有 crontab install、沒有 env/auth/risk/order/strategy/runtime mutation、沒有 writer enablement、沒有 Cost Gate lowering、沒有 probe/order authority、沒有 promotion proof。
