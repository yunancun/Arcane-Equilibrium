# Stock/ETF Broker Capability Paper Fill Import Gate Hardening

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；broker capability registry test/static hardening

## 結論

已補強 `PaperOrderFillImport` 在 broker capability registry 內的 ReadOnly gate coverage。這次只改測試與
source-static guard，不改 Rust production code、IPC method、runtime、IBKR connector、secret、DB/evidence
writer 或 paper order route。

## 變更

- Rust acceptance 新增 `paper_fill_import_row_is_readonly_and_requires_session_lifecycle_gate`。
- 鎖住 `PaperOrderFillImport` row：
  - `AuthorityScope::ReadOnly`
  - `typed_denial_reason=None`
  - `rust_owned=false`
  - `audit_event_required=true`
  - `source_artifact_hash_required=true`
  - required gates 包含 `IBKR_SESSION_ATTESTATION_CONTRACT_ID` 與
    `IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID`
- Python source-static guard 新增 exact block parser，直接檢查
  `Op::PaperOrderFillImport => ExpectedCapability`。
- Guard 明確禁止該 block 混入 `PaperRehearsal`、scoped authorization、Decision Lease 或 Guardian gate。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_broker_capability_registry_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_broker_capability_registry_source_static.py --tb=short`：`6 passed`。
- `cargo test -p openclaw_types --test stock_etf_broker_capability_registry_acceptance`：`11 passed`。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access、read-only probe execution。
- 無 fill import / result import、DB/evidence writer、paper order route、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
