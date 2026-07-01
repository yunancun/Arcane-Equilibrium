# Stock/ETF Readonly Probe Result Import Authority Lineage Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；readonly probe result-import authority / lineage hardening

## 結論

已補強 `stock_etf_ibkr_readonly_probe_result_import_request` 的 authority、common lineage、
kind-specific downstream lineage、timestamp/replay 與 no-side-effect boundary coverage。這次只改
acceptance 與 source-static guard，不改 Rust production validator、IPC method、runtime、IBKR connector、
secret、DB/evidence writer、scorecard writer 或 paper order route。

## 變更

- Rust acceptance 新增 `result_import_request_rejects_each_authority_gap_independently`。
- Rust acceptance 新增 `result_import_request_rejects_each_common_lineage_gap_independently`。
- Rust acceptance 新增 `result_import_request_rejects_each_kind_lineage_gap_independently`。
- Rust acceptance 新增 `result_import_request_rejects_each_boundary_flag_independently`。
- Acceptance 證明 contract/source/lane/broker/environment/action/operation/authority/effect gaps 可獨立
  產生精確 blocker。
- Acceptance 證明 result-import/request/probe ids、readonly probe request、session attestation、
  allowlist、redaction、audit、payload/raw/redacted/source artifacts、result as-of、idempotency、duplicate
  與 stale-review gates 可獨立阻斷。
- Acceptance 明確保留 `import_requested_at_ms=0` 的天然 timestamp aggregate：必須同時命中
  `ImportRequestedAtMissing` 與 `ResultAsOfAfterImportRequested`。
- Acceptance 證明 account cash ledger、market-data provenance、instrument identity、broker lifecycle event
  log 的 kind-specific contract/hash lineage gaps 可獨立產生精確 blocker。
- Acceptance 證明 IBKR contact、connector runtime、secret serialization、result import、evidence writer、
  scorecard writer、DB apply、order route、paper submit、Bybit path reuse、live/tiny-live、margin/short/options/
  CFD、account write、market-data entitlement purchase、Client Portal Web API、Python direct broker write flags
  可獨立阻斷。
- Python source-static guard 新增 `Default` / `accepted_fixture` block parsers，直接鎖住 accepted fixture
  不可硬編 crypto/Bybit/live/paper-write/empty-common-lineage/runtime/secret/order/Bybit-cross-wire posture。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_ibkr_readonly_probe_result_import_request_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_ibkr_readonly_probe_result_import_request_source_static.py --tb=short`：`11 passed`。
- `cargo test -p openclaw_types --test stock_etf_ibkr_readonly_probe_result_import_request_acceptance`：`11 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access、read-only probe execution。
- 無 result import execution、DB/evidence writer、scorecard writer、paper order route、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
