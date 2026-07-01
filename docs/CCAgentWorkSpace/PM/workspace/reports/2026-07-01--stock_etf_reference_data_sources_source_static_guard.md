# PM Report — Stock/ETF Reference Data Sources Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：Stock/ETF reference data sources source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`stock_etf_reference_data_sources.rs` 的 source-only 姿態；不是 IBKR contact、不是 connector
runtime、不是 reference/market-data ingest、不是 evidence clock、不是 scorecard writer、不是
DB migration/apply、不是 live/tiny-live authorization。

## Completed

- 新增 `tests/structure/test_stock_etf_reference_data_sources_source_static.py`。
- Guard 要求 `stock_etf_reference_data_sources.rs` 低於 800 行 governance cap。
- Guard 要求 exact `stock_etf_reference_data_sources_v1` contract id、reference source fields、
  corporate-action/FX/fee-tax validators、verdict/blocker surface 保持在 source 中。
- Guard 要求 default reference sources fail-closed：CryptoPerp/Bybit/LiveReservedDenied、not frozen
  for evidence clock、empty corporate-action/FX/fee source names、zero as-of values、UnknownDenied
  currencies、empty hashes、Bybit live unchanged false、no contact/runtime/secret flags、live/tiny-live
  authorized true as blocker。
- Guard 要求 accepted fixture 保留 StockEtfCash/IBKR/Paper、frozen for evidence clock、
  corporate-action source/as-of/raw/adjustment/policy/dividend hashes、USD/USD FX source/as-of/snapshot/
  drag-model hashes、IBKR paper fee source/as-of/commission/regulatory/tax/withholding/source hashes、
  Bybit live protection、no contact/runtime/secret/live-tiny authority。
- Guard 要求 validation matrix 保留 contract/version/lane/broker checks、ReadOnly/Paper/Shadow-only
  environment allowlist、freeze requirement、corporate-action/FX/fee-tax validator calls、source artifact
  hash、Bybit/contact/runtime/secret/live-tiny blockers。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_reference_data_sources_source_static.py tests/structure/test_docs_readme_index_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_reference_data_sources_source_static.py`：
  `7 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_reference_data_sources_acceptance -- --nocapture`：
  `6 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py -k 'ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles or ibkr_stock_etf_pm_checkpoint_numbers_are_linear'`：
  `2 passed, 5 deselected`。
- `git diff --check`（scoped to #128 files）：PASS。

## Boundary

未批准也未執行：runtime authority、IBKR contact、IBKR SDK import、secret access/creation、
connector runtime、socket/HTTP、reference/market-data ingest、evidence clock、scorecard writer、
DB migration/apply、read probe execution、result import execution、paper order/cancel/replace、
fill import、order route、GUI fanout、tiny-live/live、或任何 Bybit behavior change。
