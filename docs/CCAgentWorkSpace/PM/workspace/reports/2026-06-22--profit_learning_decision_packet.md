# Profit-Learning Decision Packet

## 結論

新增 `helper_scripts/research/cost_gate_learning_lane/decision_packet.py`，把已存在但分散的 demo learning artifacts 合成一個 fail-closed next-step packet。

它不再重寫 counterfactual 或 outcome engine，而是消費既有 JSON：

- `demo_data_flow_monitor`：是否仍有 demo/live_demo data flow、Cost Gate rejects 是否被記錄、是否有 silent-drop risk。
- `cost_gate_reject_counterfactual`：被擋信號事後市場 outcome 是否產生 learning candidates。
- bounded demo-learning plan：是否已有 operator-review plan。
- activation preflight / stack health：source、cron、ledger、writer、review 是否 ready/active。
- blocked-outcome review：是否有需要 operator review 的 demo probe authority candidates。

## Decision States

主要狀態包括：

- `DATA_FLOW_MONITOR_REQUIRED`
- `RUN_REJECT_COUNTERFACTUAL`
- `REFRESH_REJECT_COUNTERFACTUAL`
- `BUILD_OR_REFRESH_BOUNDED_LEARNING_PLAN`
- `RUN_LEARNING_LANE_ACTIVATION_PREFLIGHT`
- `ACTIVATE_OR_REPAIR_LEARNING_STACK`
- `WAIT_FOR_BLOCKED_OUTCOME_REVIEW`
- `OPERATOR_REVIEW_DEMO_PROBE_CANDIDATES`
- `KEEP_COST_GATE_AND_CONTINUE_COLLECTION`

所有分支都固定：

- `global_cost_gate_lowering_recommended=false`
- `order_authority_granted=false`
- `main_cost_gate_adjustment=NONE`
- `promotion_evidence=false`

## Verification

- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/decision_packet.py helper_scripts/research/tests/test_cost_gate_learning_lane_decision_packet.py` passed.
- `PYTHONPATH=helper_scripts/research python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_decision_packet.py -q` passed: `5 passed`.
- Related focused regression passed: `81 passed`.
- CLI smoke `python3 helper_scripts/research/cost_gate_learning_lane/decision_packet.py --print-json` returned fail-closed `DATA_FLOW_MONITOR_REQUIRED`.
- `git diff --check` passed before checkpoint completion.

## Boundary

Source/test/docs plus local artifact-only read/write when run. The packet does not connect to PG, call Bybit, place orders, lower the main Cost Gate, mutate config/risk/auth/runtime, install cron, enable writer, or grant probe authority. It was not run on Linux/runtime because runtime source remains unsynced.

## Next Step

After runtime source reconcile, generate fresh data-flow, counterfactual, plan, activation/stack-health, and blocked-outcome artifacts, then run the packet as the single operator-facing closure view. If it reports `ACTIVATE_OR_REPAIR_LEARNING_STACK`, source/cron/writer activation is still the blocker. If it reports `OPERATOR_REVIEW_DEMO_PROBE_CANDIDATES`, that is review input only, not automatic order authority.
