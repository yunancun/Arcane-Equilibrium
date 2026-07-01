# PM Report — Stock/ETF Read-Only Probe Result Import Request Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：Stock/ETF read-only probe result import request source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`stock_etf_ibkr_readonly_probe_result_import_request.rs` 的 source-only 姿態；不是 IBKR contact、
不是 read probe execution、不是 result import execution、不是 connector runtime、不是 secret
access、不是 evidence/scorecard writer、不是 DB apply、不是 order route。

## Completed

- 新增 `tests/structure/test_stock_etf_ibkr_readonly_probe_result_import_request_source_static.py`。
- Guard 要求 `stock_etf_ibkr_readonly_probe_result_import_request.rs` 低於 800 行 governance cap。
- Guard 要求 exact `stock_etf_ibkr_readonly_probe_result_import_request_v1` contract id、request
  fields、verdict/blocker surface、helper surface、read probe kind 列表保持在 source 中。
- Guard 要求 default request fail-closed：CryptoPerp/Bybit/LiveReservedDenied、Client Portal API、
  transfer/account-write operation、Denied authority、empty lineage hashes、replay/stale flags false、
  all side-effect flags false。
- Guard 要求 accepted fixture 保留 StockEtfCash/IBKR/ReadOnly、ConnectionHealthRead、HealthRead、
  ReadOnly authority、effect=false、result-import/request/probe ids、readonly probe request、
  session attestation、non-Bybit allowlist、redaction/audit policy hashes、payload/raw/redacted/source
  artifact hashes、as-of/import-request timestamps、idempotency key。
- Guard 要求 probe kind 到 NonBybitApiAction/BrokerOperation mapping 保持完整，並要求 API action
  必須 classify 為 read-allowed/external-gate-required/no paper-order gates。
- Guard 要求 common lineage 保留 request/session/allowlist/redaction/audit/result payload/raw/
  redacted/source artifact hashes、as-of <= import-request、idempotency、duplicate/stale denial。
- Guard 要求 kind-specific downstream lineage 保留 health snapshot、account cash ledger、
  market-data provenance、instrument identity、paper lifecycle event log 的 contract/hash checks。
- Guard 要求 boundary flags 保留 no IBKR contact、no connector runtime、no secret serialization、
  no result import、no evidence/scorecard writer、no DB apply、no order/paper order、no Bybit path
  reuse、no live/tiny-live、no margin/short/options/CFD/account-write/entitlement/client-portal/Python
  broker write。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_ibkr_readonly_probe_result_import_request_source_static.py tests/structure/test_docs_readme_index_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_ibkr_readonly_probe_result_import_request_source_static.py`：
  `10 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_ibkr_readonly_probe_result_import_request_acceptance -- --nocapture`：
  `6 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py -k 'ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles or ibkr_stock_etf_pm_checkpoint_numbers_are_linear'`：
  `2 passed, 5 deselected`。
- `git diff --check`（scoped to #125 files）：PASS。

## Boundary

未批准也未執行：runtime authority、IBKR contact、IBKR SDK import、secret access/creation、
connector runtime、socket/HTTP、read probe execution、result import execution、collector、
market-data ingestion、DQ writer、paper order/cancel/replace、fill import、order route、evidence
writer/clock、scorecard writer、DB apply、GUI fanout、tiny-live/live、或任何 Bybit behavior change。
