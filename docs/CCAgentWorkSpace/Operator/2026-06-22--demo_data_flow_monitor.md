# Demo Data Flow Rolling Monitor

## 結論

新增 `helper_scripts/db/audit/demo_data_flow_monitor.py`，用 read-only PG SELECT 多窗口調用 `demo_order_stall_audit`。預設窗口是 1h/4h/24h，輸出 compact JSON/Markdown，用來判斷 demo/live_demo 是否仍在積累 learning/order-flow 資料。

它把「最近沒有再下單」拆成可操作狀態：

- recent short window empty
- broader window Cost Gate reject wall
- broader window order-flow but no fills
- broader window fill-flow present
- no data in any window

## Runtime Note

這次沒有在 `trade-core` 執行新 monitor，因為 runtime source 仍未 reconcile，runtime checkout 不含此新文件。先前 runtime 事實仍沿用 v372/v374：demo/live_demo 1h decisions/risk/intents/orders/fills all 0；4h decisions/risk=2699，其中 2696 Cost Gate blocks，3 Working flash_dip orders，0 fills。

## Verification

- Mac py_compile passed for monitor + adjacent audit/test files.
- Mac focused pytest passed: `17 passed`.
- Mac `git diff --check` passed before checkpoint completion.

## Boundary

No runtime fetch/pull/reset/clean/source sync was performed. No cron install, env edit, deploy/rebuild/restart, PG write/schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy mutation, writer enablement, Cost Gate lowering, order authority, probe authority, or promotion proof was performed.

## Operator Next Step

1. First approve or reject the pending runtime source reconcile apply packet.
2. After runtime source is aligned, run:

```bash
python3 helper_scripts/db/audit/demo_data_flow_monitor.py \
  --engine-mode demo \
  --engine-mode live_demo \
  --window-hours 1 \
  --window-hours 4 \
  --window-hours 24 \
  --output /tmp/openclaw/demo_data_flow_monitor.md \
  --json-output /tmp/openclaw/demo_data_flow_monitor.json
```

3. If status remains a Cost Gate reject wall or order-flow-without-fills, wire the result into the blocked-signal outcome audit before any broader Cost Gate relaxation.
