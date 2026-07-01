# Stock/ETF Readonly Probe Result Import Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；readonly probe result import mapping hardening

## 結論

已補強 `stock_etf_ibkr_readonly_probe_result_import_request` 對 probe kind / API action /
BrokerOperation mapping 的 coverage。這次只改 acceptance 與 source-static guard，不改 Rust production
code、IPC method、runtime、IBKR connector、secret、DB/evidence writer 或 paper order route。

## 變更

- Rust acceptance 新增 `result_import_request_rejects_probe_action_operation_cross_wire`。
- 證明 `MarketDataSnapshot` 搭配 `AccountSummarySnapshotRead` action 會被
  `ProbeActionMismatch` 擋下。
- 證明 `MarketDataSnapshot` 搭配 `AccountSnapshotRead` operation 會被
  `OperationMismatch` 擋下。
- 證明 result-import envelope 混入 `PaperOrderSubmit` action 時，必須產生
  `ProbeActionMismatch` 與 `ApiActionNotReadAllowed`。
- Python source-static guard 新增 mapping function body parser，檢查 `expected_api_action` /
  `expected_operation` 不含 paper-order/live-order 污染。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_ibkr_readonly_probe_result_import_request_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_ibkr_readonly_probe_result_import_request_source_static.py --tb=short`：`10 passed`。
- `cargo test -p openclaw_types --test stock_etf_ibkr_readonly_probe_result_import_request_acceptance`：`7 passed`。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access、read-only probe execution。
- 無 result import、DB/evidence writer、paper order route、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
