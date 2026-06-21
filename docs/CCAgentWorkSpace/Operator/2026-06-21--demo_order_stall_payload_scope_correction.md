# 2026-06-21 -- Demo Order-Stall Payload Scope Correction

本輪修正 demo 無下單診斷的關鍵解讀。

新的 read-only PG 實查：`2026-06-21 17:03 +02:00`，最近 4h：

- `decision_context_snapshots` payload-scope rows：21,450
- `signal_observation_only_contexts`：21,450
- `accepted_intent_bound_contexts`：0
- `non_observation_scope_contexts`：0
- `missing_scope_contexts`：0
- scope 唯一值：`signal_observation_only`
- latest context：`2026-06-21 17:03:09.785+02`

所以短期 context row 無 downstream join 不是 silent drop；這些 rows 是明確標記的 observation/learning telemetry，不是已接受的下單候選。

`demo_order_stall_audit.py` 已更新：

- JSON/Markdown 新增 `context_payload_scope`
- pre-gate top rows 顯示 scope / obs-only / accepted-bound
- 新狀態 `OBSERVATION_ONLY_CONTEXTS_ACTIVE`
- 全量 observation-only 時 `silent_drop_risk=false`

操作判斷：demo 學習觀察流仍在累積；真正缺的是 Cost Gate rejection 的 bounded learning lane runtime ledger / blocked outcome / review，不是直接降低主 Cost Gate。

驗證：

- `python3 -m pytest helper_scripts/db/audit/test_demo_order_stall_audit.py -q` -> `11 passed`
- `py_compile` passed
- remote read-only PG payload-scope probe passed

邊界：只讀 PG + source/test/docs；沒有 deploy/restart、沒有 PG write、沒有 Bybit private/signed/trading call、沒有下單、沒有降低 Cost Gate。
