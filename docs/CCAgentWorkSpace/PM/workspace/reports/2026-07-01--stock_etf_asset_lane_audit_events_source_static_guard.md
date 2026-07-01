# PM Report — Stock/ETF Asset-Lane Audit Events Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：Stock/ETF asset-lane audit event source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`stock_etf_audit_events.rs` 的 source-only 姿態；不是 audit writer、不是 DB apply、不是 IBKR
contact、不是 connector runtime、不是 evidence clock、不是 order route。

## Completed

- 新增 `tests/structure/test_stock_etf_audit_events_source_static.py`。
- Guard 要求 `stock_etf_audit_events.rs` 低於 800 行 governance cap。
- Guard 要求 exact `audit.asset_lane_events_v1` contract id、event kind 列表、event field
  surface、verdict/blocker surface 保持在 source 中。
- Guard 要求 default event 維持 fail-closed：`source_version=0`、`Unknown` event kind、sequence
  missing、StockEtfCash/IBKR/ReadOnly、`allowed=false`、no secret serialization、no raw payload
  inline。
- Guard 要求 accepted genesis/chained fixtures 保留 hash linkage、IBKR external-surface source、
  scorecard input reference、readonly/derived permission scopes。
- Guard 要求 validation matrix 保留 schema/source-version、event id/kind/sequence、genesis
  previous-hash、non-genesis hash、actor/source、lane/broker/live denial、account/session/source
  hashes、allowed/denied denial-reason rules、input hashes、secret/raw-payload denials。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_audit_events_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_audit_events_source_static.py`：
  `6 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_audit_events_acceptance -- --nocapture`：
  `9 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py -k 'ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles or ibkr_stock_etf_pm_checkpoint_numbers_are_linear'`：
  `2 passed, 5 deselected`。
- `git diff --check`（scoped to #120 files）：PASS。

## Boundary

未批准也未執行：runtime authority、IBKR contact、IBKR SDK import、secret access/creation、
connector runtime、socket/HTTP、read probe、result import、collector、market-data ingestion、
DQ writer、paper order/cancel/replace、fill import、audit writer、DB apply、evidence writer/clock、
GUI fanout、tiny-live/live、或任何 Bybit behavior change。
