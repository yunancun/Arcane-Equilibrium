# Stock/ETF Shadow Signal Request Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；shadow signal request boundary hardening

## 結論

已補強 `stock_etf_shadow_signal_request` 對 IPC method / BrokerOperation /
AuthorityScope mapping 的 coverage。這次只改 acceptance 與 source-static guard，不改 Rust
production code、IPC method、runtime、IBKR connector、secret、DB/evidence writer 或 paper order
route。

## 變更

- Rust acceptance 新增 `shadow_signal_request_rejects_method_operation_and_paper_write_cross_wire`。
- 證明 shadow signal request 混入 `ImportPaperFills` method 會被 `RequestMethodMismatch` 擋下，
  且不誤報 operation / scope / effect blocker。
- 證明 `EvaluateShadowSignal` 搭配 `PaperOrderSubmit` operation 會被
  `OperationMismatch` 擋下，且不誤報 method / scope / effect blocker。
- 證明 paper-submit method、paper-submit operation、`PaperRehearsal` scope 與
  `effect_capable=true` 污染會同時產生 method / operation / scope / effect blockers。
- Python source-static guard 新增 cross-wire 禁止清單，拒絕 paper order、fill import、readonly
  probe、Bybit-denied method 以及 paper/live operation 混入 shadow signal source。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_shadow_signal_request_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_shadow_signal_request_source_static.py --tb=short`：`7 passed`。
- `cargo test -p openclaw_types --test stock_etf_shadow_signal_request_acceptance`：`6 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access、shadow signal execution。
- 無 shadow fill generation、result import、DB/evidence writer、paper order route、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
