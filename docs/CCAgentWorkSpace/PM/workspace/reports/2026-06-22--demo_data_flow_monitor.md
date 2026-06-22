# Demo Data Flow Rolling Monitor

## 結論

新增 `helper_scripts/db/audit/demo_data_flow_monitor.py`，把既有 `demo_order_stall_audit` 包成 1h/4h/24h 預設多窗口監控。這讓「demo 很久沒有再下單」不再只是一次性 SQL 判讀，而是可以重跑、輸出 JSON/Markdown、可被後續 cron 或 operator review 消費的 data-flow state。

它重點回答：

- 最近窗口是否完全空窗。
- 較大窗口是否仍有 candidate / risk / reject / order / fill 資料。
- Cost Gate 擋單是否被記錄，而不是 silent drop。
- broader window 有 orders 但無 fills 時，先把問題歸到 order-to-fill gap，而不是直接降低全局 Cost Gate。

## Classifier

新增摘要狀態包括：

- `RECENT_WINDOW_EMPTY_PRIOR_ORDER_FLOW_NO_FILLS`
- `RECENT_WINDOW_EMPTY_COST_GATE_REJECT_WALL`
- `RECENT_WINDOW_EMPTY_PRIOR_CANDIDATE_OR_REJECT_DATA`
- `COST_GATE_REJECT_WALL_NO_ORDER_FLOW`
- `DEMO_ORDER_FLOW_PRESENT_NO_FILLS`
- `DEMO_FILL_FLOW_PRESENT`
- `NO_DEMO_DATA_ANY_WINDOW`

所有摘要都保留 `global_cost_gate_lowering_recommended=false`。當 broader window 有 Cost Gate rejects 且無 fills 時，輸出 `bounded_demo_learning_lane_requires_runtime_activation=true`，表達下一步應該是 bounded demo learning lane，而不是無邊界放寬主 Cost Gate。

## Verification

- `python3 -m py_compile helper_scripts/db/audit/demo_data_flow_monitor.py helper_scripts/db/audit/test_demo_data_flow_monitor.py helper_scripts/db/audit/demo_order_stall_audit.py helper_scripts/db/audit/test_demo_order_stall_audit.py` passed.
- `python3 -m pytest helper_scripts/db/audit/test_demo_data_flow_monitor.py helper_scripts/db/audit/test_demo_order_stall_audit.py -q` passed: `17 passed`.
- `git diff --check` passed before checkpoint completion.

## Boundary

Source/test/docs only. The new monitor performs read-only PG SELECT when run, and optional local artifact output only. It was not run on Linux/runtime because runtime source remains unsynced and does not yet contain this file. No runtime sync, cron install, env edit, deploy/rebuild/restart, PG write/schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy mutation, writer enablement, Cost Gate lowering, order/probe authority, or promotion proof was performed.

## Next Step

After operator-approved source reconcile, run the monitor on `trade-core` for 1h/4h/24h demo/live_demo and then schedule it alongside the demo-learning evidence cron. The next engineering target is to connect this rolling state to a replayable blocked-signal outcome audit, so Cost Gate rejects can be judged against subsequent market movement instead of being silently forgotten.
