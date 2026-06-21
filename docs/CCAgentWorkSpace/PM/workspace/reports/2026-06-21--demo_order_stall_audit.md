# 2026-06-21 -- Demo Order Stall Audit

## 結論

本輪新增 `helper_scripts/db/audit/demo_order_stall_audit.py`，把 demo/live_demo 無下單拆成固定 pipeline 階段診斷：

`decision_context_snapshots / decision_features_evaluations -> risk_verdicts -> intents -> orders -> fills`

它是 read-only PG audit：不寫 DB、不連 Bybit、不下單、不改 runtime / risk / config。目的不是直接放寬 Cost Gate，而是把「到底卡在哪一段」變成可重跑的 JSON/Markdown 證據。

## 2026-06-21 Read-Only Runtime Probe

查詢時間：`2026-06-21 16:42-16:43 +02:00`，範圍 `engine_mode IN ('demo','live_demo')`。

24h 聚合：

- `decision_context_snapshots=124014`，latest `2026-06-21 16:42:30+02`。
- `candidate_evaluations=24166`，latest `2026-06-21 11:48:59+02`。
- `decision_features=24155`，其中 `rejected_decision_features=24152`。
- `risk_verdicts=24155`，其中 `approved=3` / `rejected=24152`。
- `intents=3` / `orders=3` / `fills=0`。
- top reject code：`cost_gate_js_demo_negative_edge`，`n=24152`。
- top risk reason：`cost_gate(JS-demo): estimated=-2.74bps < 0`，`n=23889`。
- evaluation outcome：全部為 `use_legacy_no_predictor` / `evaluation_log`，`n=24166`。

最近窗口：

- 1h：`decision_context_snapshots=5082`，但 `candidate_evaluations/risk/intents/orders/fills=0`。
- 4h：`decision_context_snapshots=21383`，但 `candidate_evaluations/risk/intents/orders/fills=0`。
- 6h：`decision_context_snapshots=31699`，`candidate_evaluations=20634` / `risk_verdicts=20632`，但 `intents/orders/fills=0`，latest candidate/risk 均停在 `11:48:59+02`。

24h 內 3 張 order：

- `SUIUSDT` / `XRPUSDT` / `BNBUSDT`，strategy=`flash_dip_buy`。
- 全部 `demo`、`Limit`、`PostOnly`、state=`Working`。
- 無 fill，無 reject/cancel reason。
- `price` audit projection 為 NULL，與 runtime source behind/old writer projection 的事實一致，不能當成交品質證據。

168h 背景：

- `risk_verdicts=174287`，`approved=1117` / `rejected=173170`。
- `intents=1117` / `orders=1567` / `fills=586`。
- latest fill `2026-06-20 00:54:59+02`。
- 168h net PnL proxy `-328.9220 USDT`。

## 判斷

- demo 不是完全沒有資料：signal/context 仍持續寫入。
- 但最近 4h 沒有 candidate evaluation / risk verdict / intent / order / fill，短期卡在 `signal_to_candidate` 或策略 pre-gate。
- 24h 維度，大量候選被 Cost Gate 拒絕且有 DB 記錄，不是 silent drop；但 runtime cost-gate learning ledger 仍未啟用，這些拒絕沒有被轉成 `probe_ledger.jsonl` / `blocked_signal_outcome`。
- 少量通過的 order 沒有 fill，屬 order-to-fill / maker PostOnly working gap，不是盈利證據。
- 不建議全局降低主 Cost Gate。應先啟用 bounded demo-learning lane：捕捉被擋 signal 的後驗 markout，再根據 side-cell evidence 做 operator review。

## 變更

- 新增 `helper_scripts/db/audit/demo_order_stall_audit.py`
  - CLI：`--engine-mode` / `--lookback-hours` / `--top-limit` / `--output` / `--json-output`。
  - 輸出 schema：`demo_order_stall_audit_v1`。
  - 分類狀態：`NO_RECENT_PIPELINE_DATA`、`SIGNAL_OBSERVATION_ONLY_PRE_GATE`、`PREDICTOR_OR_STRATEGY_PRE_RISK_GATE`、`COST_GATE_REJECTING_ALL_RECENT_ATTEMPTS`、`APPROVED_VERDICT_INTENT_PERSISTENCE_GAP`、`INTENT_TO_ORDER_GAP`、`ORDER_TO_FILL_GAP`、`ORDER_REJECT_OR_POST_ONLY_GAP`、`RECENT_FILL_FLOW_PRESENT`。
- 新增 `helper_scripts/db/audit/test_demo_order_stall_audit.py`
  - 鎖住 SQL read-only contract、pipeline table coverage、risk reason category、分類狀態與 JSON/Markdown answers。

## 驗證

- `python3 -m pytest helper_scripts/db/audit/test_demo_order_stall_audit.py -q` -> `7 passed`
- `python3 -m py_compile helper_scripts/db/audit/demo_order_stall_audit.py helper_scripts/db/audit/test_demo_order_stall_audit.py` -> passed
- Remote read-only PG probe via `ssh trade-core` -> passed after loading `basic_system_services.env`; no PG writes.

## 邊界

Source/test/docs + read-only runtime PG probe only. No runtime source sync, env edit, deploy, rebuild, restart, cron install, PG table write/schema migration, Bybit private/signed/trading call, order authority, main Cost Gate lowering, credential/auth/risk/order/strategy/runtime mutation, execution proof, or promotion proof.
