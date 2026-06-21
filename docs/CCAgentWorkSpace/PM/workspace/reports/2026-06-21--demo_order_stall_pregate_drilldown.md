# 2026-06-21 -- Demo Order-Stall Pre-Gate Drilldown

## 結論

上一輪 `demo_order_stall_audit.py` 已把 demo no-order 拆到 pipeline 階段；本輪再補 pre-gate drilldown，讓 audit 不只說「最近 4h 只有 context、沒有 candidate/risk」，而能直接列出哪些 `engine_mode / strategy / symbol / decision_type` 的 context row 沒有 downstream evaluation / risk / intent / order / fill join。

這仍是 read-only PG audit，不寫 DB、不連 Bybit、不下單、不改 runtime/risk/config。

## 2026-06-21 Read-Only Runtime Probe

查詢時間：`2026-06-21 16:49 +02:00`，lookback 4h，`engine_mode IN ('demo','live_demo')`。

Top context rows 全部是 `decision_type=signal_generated` 且 downstream join 全 0。前幾名：

- `demo / ma_crossover / REUSDT`：`context_rows=549`，latest `2026-06-21 16:49:01+02`。
- `demo / ma_crossover / LABUSDT`：`context_rows=546`，latest `2026-06-21 16:49:00+02`。
- `demo / ma_crossover / ADAUSDT`：`context_rows=513`，latest `2026-06-21 16:49:07+02`。
- `demo / ma_crossover / NEARUSDT`：`context_rows=494`，latest `2026-06-21 16:42:12+02`。
- `demo / ma_crossover / FILUSDT`：`context_rows=490`，latest `2026-06-21 16:48:28+02`。

Interpretation：短期斷點不是 DB/context writer 停止，而是 signal/context 之後沒有進入 candidate evaluation / Guardian risk。集中在 `ma_crossover` 的多 symbol context stream，這是後續 producer/pre-gate 診斷的優先入口。

## 變更

- `helper_scripts/db/audit/demo_order_stall_audit.py`
  - 新增 `build_pre_gate_drilldown_sql()`。
  - JSON 新增 `pre_gate_drilldown_summary` / `pre_gate_drilldown_top`。
  - Markdown 新增 `## Pre-Gate Drilldown` 表格。
  - summary 明確標註 `scope=top_limit_rows_only`，避免把 top-N 當全量。
- `helper_scripts/db/audit/test_demo_order_stall_audit.py`
  - 新增 SQL contract 測試，鎖住 context_id 對 downstream 表的 left join。
  - 新增 summary 測試，確保 unjoined context rows 可機器讀。

## 驗證

- `python3 -m pytest helper_scripts/db/audit/test_demo_order_stall_audit.py -q` -> `9 passed`
- `python3 -m py_compile helper_scripts/db/audit/demo_order_stall_audit.py helper_scripts/db/audit/test_demo_order_stall_audit.py` -> passed
- Remote read-only PG drilldown probe via `ssh trade-core` -> passed；no PG writes。

## 邊界

Source/test/docs + read-only runtime PG probe only. No runtime source sync, env edit, deploy, rebuild, restart, cron install, PG table write/schema migration, Bybit private/signed/trading call, order authority, main Cost Gate lowering, credential/auth/risk/order/strategy/runtime mutation, execution proof, or promotion proof.
