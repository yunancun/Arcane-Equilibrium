# 2026-06-21 -- Demo Order Stall Audit

本輪新增一個 read-only 診斷工具：`helper_scripts/db/audit/demo_order_stall_audit.py`。

它直接回答 demo 很久沒下單時，到底卡在哪一段：

- signal/context 是否還在寫
- candidate evaluation 是否還在寫
- risk/cost gate 是否還在拒
- approved verdict 是否有變成 intent
- intent 是否有變成 order
- order 是否有 fill

2026-06-21 16:42-16:43 +02:00 的 read-only 實查結果：

- 最近 1h/4h：`decision_context_snapshots` 還在寫，但 `candidate_evaluations/risk/intents/orders/fills=0`。
- 最近 24h：`risk_verdicts=24155`，其中 `rejected=24152`、`approved=3`。
- 24h 內 top reject 是 `cost_gate_js_demo_negative_edge`，`n=24152`。
- 24h 內只有 3 張 demo order，都是 `flash_dip_buy` PostOnly Limit，狀態 `Working`，0 fill。
- 最近 fill 是 `2026-06-20 00:54:59+02`，168h net PnL proxy `-328.9220 USDT`。

判斷：

- 不是完全沒有數據；context 觀測還在累積。
- 但最近 4h 沒有候選/風控/intent/order/fill，短期卡在 signal → candidate/risk 前後。
- 24h 維度則是 Cost Gate 大量拒單，而且拒絕有落 DB，不是 silent drop。
- runtime cost-gate learning ledger 仍未啟用，所以被擋的信號沒有進一步累積 `probe_ledger.jsonl` / `blocked_signal_outcome`。
- 不建議全局 lowering main Cost Gate；下一步應是啟用 bounded demo-learning lane，把被擋信號的後驗 markout 累積起來。

驗證：

- `python3 -m pytest helper_scripts/db/audit/test_demo_order_stall_audit.py -q` -> `7 passed`
- `python3 -m py_compile helper_scripts/db/audit/demo_order_stall_audit.py helper_scripts/db/audit/test_demo_order_stall_audit.py` -> passed

邊界：只做 source/test/docs + read-only PG probe；沒有 deploy/restart、沒有 PG write、沒有 Bybit private/signed/trading call、沒有下單、沒有降低 Cost Gate。
