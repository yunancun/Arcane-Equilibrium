# Stock/ETF Paper Fill Import Request Authority Lineage Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；paper fill import request authority / lineage hardening

## 結論

已補強 `stock_etf_paper_fill_import_request` 的 lane/broker/environment/method/operation/authority、
lifecycle/event-log/redaction/session lineage、idempotency/replay、stale-state policy 與 no-side-effect
boundary coverage。這次只改 acceptance 與 source-static guard，不改 Rust production validator、IPC method、
runtime、IBKR connector、secret、DB/evidence writer 或 paper order route。

## 變更

- Rust acceptance 新增 `fill_import_request_rejects_each_authority_gap_independently`。
- Rust acceptance 新增 `fill_import_request_rejects_each_lineage_gap_independently`。
- Rust acceptance 新增 `fill_import_request_rejects_each_boundary_flag_independently`。
- Acceptance 證明 contract/source/lane/broker/environment/method/operation/authority/effect gaps 可獨立
  產生精確 blocker。
- Acceptance 證明 request/session/lifecycle/event-log/redaction/source artifact/reconciliation/broker order/
  execution/commission/idempotency/observed-state/stale-policy/raw/redacted artifact lineage gaps 可獨立阻斷。
- Acceptance 明確保留 `StateUnknown` without stale policy 的天然 aggregate 行為：必須同時命中
  `StaleStatePolicyMissing` 與 `StaleUnknownStateWithoutPolicy`。
- Acceptance 證明 duplicate import、explicit stale-unknown flag、IBKR contact、connector runtime、secret
  serialization、fill import execution、DB apply、order route、Bybit path reuse、live/tiny-live、margin/short/
  options/CFD、Python direct broker write flags 可獨立阻斷。
- Python source-static guard 新增 `Default` / `accepted_fixture` block parsers，直接鎖住 accepted fixture
  不可硬編 crypto/Bybit/live/wrong method/wrong operation/effectful/empty-lineage/replay/runtime/secret/order
  posture。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_paper_fill_import_request_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_paper_fill_import_request_source_static.py --tb=short`：`8 passed`。
- `cargo test -p openclaw_types --test stock_etf_paper_fill_import_request_acceptance`：`10 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 fill import execution、DB/evidence writer、paper order route、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
