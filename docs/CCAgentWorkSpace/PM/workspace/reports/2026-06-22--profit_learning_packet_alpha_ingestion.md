# Profit-Learning Packet Alpha Ingestion

## 結論

v376 的 `profit_learning_decision_packet` 已接入 alpha discovery / learning worklist。這讓 Cost Gate demo-learning 的單一 closure packet 不再只是孤立 artifact，而會出現在 profitability blocker scorecard 和 operator-facing worklist。

## 改動

- `runtime_runner.collect_cost_gate_learning_lane_arm` 讀取 `cost_gate_learning_lane/profit_learning_decision_packet_latest.json`，若缺則 fallback `profit_learning_decision_packet.json`。
- `discovery_loop._cost_gate_learning_lane_state` 將新鮮 packet 狀態映射為 blocker：
  - `RUN_REJECT_COUNTERFACTUAL` / `REFRESH_REJECT_COUNTERFACTUAL` -> `profit_learning_reject_counterfactual_required`
  - `BUILD_OR_REFRESH_BOUNDED_LEARNING_PLAN` -> `profit_learning_bounded_plan_required`
  - `ACTIVATE_OR_REPAIR_LEARNING_STACK` -> `profit_learning_stack_activation_or_repair_required`
  - `OPERATOR_REVIEW_DEMO_PROBE_CANDIDATES` -> `profit_learning_demo_probe_candidates_need_operator_review`
- `learning_worklist` 攜帶 packet status、next actions、authority flags、top side-cells，並把 probe candidate packet 保持為 operator-gated review。

## Verification

- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py helper_scripts/research/alpha_discovery_throughput/learning_worklist.py helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py` passed.
- `PYTHONPATH=helper_scripts/research python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py helper_scripts/research/tests/test_cost_gate_learning_lane_decision_packet.py -q` passed: `57 passed`.
- `git diff --check` passed before checkpoint completion.

## Boundary

Source/test/docs plus artifact-only reads when run. No runtime source sync, cron install, env edit, deploy/rebuild/restart, PG query/write/schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy mutation, writer enablement, Cost Gate lowering, order authority, probe authority, or promotion proof.

## Next Step

After runtime source reconcile, the alpha-discovery cron can expose profit-learning packet status directly in killboard/worklist. If the worklist shows `profit_learning_reject_counterfactual_required`, run/refresh the counterfactual scorecard. If it shows `profit_learning_demo_probe_candidates_need_operator_review`, that is still review input only, not automatic demo probe authority.
