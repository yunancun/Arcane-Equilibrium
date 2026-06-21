# 2026-06-21 -- Demo Order-Stall Payload Scope Correction

## 結論

上一輪 pre-gate drilldown 的 join 結論是對的：最近 4h context rows 沒有 downstream evaluation / risk / intent / order / fill join。

但 follow-up payload-scope probe 修正了操作解讀：這些 context rows 全部標成 `linucb_metadata_scope=signal_observation_only` 且 `accepted_intent_bound=false`。這代表它們是 demo 學習/telemetry 觀察流，不是已接受候選被 silent drop。

因此目前答案是：

- Demo 仍在持續累積 signal observation 數據。
- 最近沒有下單，不是因為 context writer 死掉，也不是因為 actionable context 被靜默丟失。
- 真正缺口仍是可學習的 rejected/actionable ledger：Cost Gate 擋掉的候選需要 bounded demo-learning lane 記錄 admission / blocked outcome / review，而不是直接 globally lower main Cost Gate。

## 2026-06-21 Read-Only Runtime Probe

查詢時間：`2026-06-21 17:03 +02:00`，lookback 4h，`engine_mode IN ('demo','live_demo')`。

Payload-scope aggregate：

| metric | value |
|---|---:|
| context_rows | 21,450 |
| signal_observation_only_contexts | 21,450 |
| accepted_intent_bound_contexts | 0 |
| non_observation_scope_contexts | 0 |
| missing_scope_contexts | 0 |
| distinct_scope_count | 1 |
| linucb_metadata_scopes | `signal_observation_only` |
| strategies | 7 |
| symbols | 33 |
| latest_context_ts | `2026-06-21 17:03:09.785+02` |
| avg_signal_count | 3.8960 |

Source inspection also matches this: `rust/openclaw_engine/src/decision_context_producer.rs` emits signal observation payloads with `accepted_intent_bound=false` and `linucb_metadata_scope=signal_observation_only`.

## 變更

- `helper_scripts/db/audit/demo_order_stall_audit.py`
  - 新增 full-window `context_payload_scope` 聚合。
  - `pre_gate_drilldown_top` 加入 `linucb_metadata_scopes`、`signal_observation_only_contexts`、`accepted_intent_bound_contexts`、`avg_signal_count`。
  - 新分類 `OBSERVATION_ONLY_CONTEXTS_ACTIVE`。
  - `silent_drop_risk` 現在只有在 context 不是全量 observation-only、且 candidate/risk/intent 都沒有落地時才為 true。
- `helper_scripts/db/audit/test_demo_order_stall_audit.py`
  - 測試 payload SQL contract。
  - 測試 observation-only scope 不再報 silent drop。

## 決策

不建議 global lower main Cost Gate。合理方向是 bounded demo-learning lane：允許嚴格 budget / side-cell / operator-reviewed 的 demo probe 或至少 blocked-outcome ledger，讓系統學會哪些 Cost Gate rejection 其實有後驗正 edge。

本輪未授權下單，也未改 runtime；只是把 audit 做到能區分「學習觀察資料正在流」和「actionable 候選被丟失」。

## 驗證

- `python3 -m pytest helper_scripts/db/audit/test_demo_order_stall_audit.py -q` -> `11 passed`
- `python3 -m py_compile helper_scripts/db/audit/demo_order_stall_audit.py helper_scripts/db/audit/test_demo_order_stall_audit.py` -> passed
- Remote read-only PG payload-scope probe via `ssh trade-core` -> passed；no PG writes。

## 邊界

Source/test/docs + read-only runtime PG probe only. No runtime source sync, env edit, deploy, rebuild, restart, cron install, PG table write/schema migration, Bybit private/signed/trading call, order authority, main Cost Gate lowering, credential/auth/risk/order/strategy/runtime mutation, execution proof, or promotion proof.
