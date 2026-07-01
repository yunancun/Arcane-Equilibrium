# Stock/ETF Broker Capability Registry Authority Lineage Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；broker capability registry authority / lineage hardening

## 結論

已補強 `stock_etf_broker_capability_registry` 的 registry identity、StockEtfCash/IBKR lane separation、
Bybit/live/python-write/contact/secret denials、required audit fields、required operation coverage 與 operation
row authority/gate/typed-denial/rust/audit/source-artifact shape。這次只改 acceptance 與 source-static guard，
不改 Rust production validator、runtime、IBKR connector、secret、DB/evidence writer、paper order route 或
Bybit 路徑。

## 變更

- Rust acceptance 新增 `registry_rejects_each_top_level_gap_independently`。
- Rust acceptance 新增 `registry_rejects_each_operation_coverage_gap_independently`。
- Rust acceptance 新增 `registry_rejects_each_operation_shape_gap_independently`。
- Acceptance 證明 registry id/source/lane/broker、Bybit live protection、Python broker write denial、IBKR live
  denial、CFD/margin denial、first-contact denial、secret denial、required audit fields 可各自只產生單一對應
  blocker。
- Acceptance 證明 missing operation、duplicated operation 可各自只產生單一對應 blocker。
- Acceptance 證明 paper submit/live/paper-fill-import rows 的 authority scope、required gates、typed denial、
  rust ownership、audit event、source artifact hash requirements 可各自只產生單一對應 blocker。
- Python source-static guard 新增 required-operations/default/accepted-fixture block parsers，鎖住 default
  fail-closed posture、accepted StockEtfCash/IBKR/no-contact/no-secret posture、以及 REQUIRED_OPERATIONS 全矩陣。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_broker_capability_registry_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_broker_capability_registry_source_static.py --tb=short`：`8 passed`。
- `cargo test -p openclaw_types --test stock_etf_broker_capability_registry_acceptance`：`14 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 paper order routing、DB/evidence writer、scorecard writer、broker session、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
