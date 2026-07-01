# Stock/ETF Tiny-Live Eligibility Decision Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；tiny-live ADR eligibility boundary hardening

## 結論

已補強 `stock_etf_tiny_live_eligibility` artifact 對 ADR-discussion-only decision matrix、
secret serialization、sealed posture 的 coverage。這次只改 acceptance 與 source-static guard，不改
Rust production code、IPC method、runtime、IBKR connector、secret、DB/evidence writer、paper order
route 或 tiny-live/live authority。

## 變更

- Rust acceptance 新增
  `tiny_live_eligibility_rejects_decision_and_secret_cross_wire_independently`。
- 證明 `NotEligible` decision 只產生 `DecisionNotAdrDiscussionOnly`。
- 證明 `TinyLiveAuthorized` decision 只產生 `TinyLiveAuthorizationRequested`。
- 證明 `LiveAuthorized` decision 只產生 `LiveAuthorizationRequested`。
- 證明 `secret_content_serialized=true` 只產生 `SecretContentSerialized`。
- 證明 `sealed=false` 只產生 `NotSealed`。
- Python source-static guard 新增 fixture cross-wire 禁止清單，拒絕 `TinyLiveAuthorized`、
  `LiveAuthorized`、secret serialization、unsealed posture 被 hardcoded 到
  `adr_discussion_fixture()`，並鎖住 default fail-closed posture。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_tiny_live_eligibility_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_tiny_live_eligibility_source_static.py --tb=short`：`7 passed`。
- `cargo test -p openclaw_types --test stock_etf_tiny_live_eligibility_acceptance`：`8 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 tiny-live/live authorization、DB/evidence writer、paper order route。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
