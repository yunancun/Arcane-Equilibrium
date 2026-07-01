# Stock/ETF Broker Operation Authority Taxonomy Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；operation authority taxonomy test/static hardening

## 結論

已補強 `stock_etf_lane` 對 `BrokerOperation` authority taxonomy 的 coverage。這次只改 acceptance 與
source-static guard，不改 Rust production code、broker capability semantics、IPC method、runtime、
IBKR connector、secret、DB/evidence writer 或 paper order route。

## 變更

- Rust acceptance 新增
  `broker_operation_authority_taxonomy_keeps_fill_import_readonly_and_orders_separate`。
- 鎖住 read-only operations：
  `HealthRead`、`AccountSnapshotRead`、`MarketDataRead`、`ContractDetailsRead`、
  `PaperOrderFillImport`、`ScorecardDerive`。
- 鎖住 paper-write operations：
  `PaperOrderSubmit`、`PaperOrderCancel`、`PaperOrderReplace`。
- 鎖住 shadow operations：
  `ShadowSignalEmit`、`ShadowFillReconstruct`。
- 鎖住 denied operations：
  `LiveOrderSubmit`、`MarginOrShort`、`OptionsOrCfd`、`TransferOrAccountWrite`。
- Python source-static guard 新增 method body parser，檢查 `is_read`、`is_paper_write`、
  `is_shadow` 與 `authority_scope` fallback order。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_lane_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_lane_source_static.py --tb=short`：`5 passed`。
- `cargo test -p openclaw_types --test stock_etf_lane_acceptance`：`10 passed`。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access、read-only probe execution。
- 無 fill import / result import、DB/evidence writer、paper order route、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
