# Stock/ETF Tiny-Live Eligibility Authority Lineage Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；tiny-live ADR eligibility authority / lineage hardening

## 結論

已補強 `stock_etf_tiny_live_eligibility` 的 contract identity、ADR/AMD/spec path、Phase 5 release packet
lineage、scorecard lineage、paper-shadow reconciliation lineage、DQ/preregistration/review hashes、statistical
gates、review gates、ADR-discussion-only decision、secret denial 與 sealed posture coverage。這次只改
acceptance 與 source-static guard，不改 Rust production validator、IPC method、runtime、IBKR connector、
secret、DB/evidence writer、release executor、paper order route 或 Bybit 路徑。

## 變更

- Rust acceptance 新增 `tiny_live_eligibility_rejects_each_identity_and_path_gap_independently`。
- Rust acceptance 新增 `tiny_live_eligibility_rejects_each_hash_lineage_gap_independently`。
- Rust acceptance 新增 `tiny_live_eligibility_rejects_each_statistical_gate_gap_independently`。
- Rust acceptance 新增 `tiny_live_eligibility_rejects_each_label_and_review_gap_independently`。
- Rust acceptance 新增 `tiny_live_eligibility_rejects_each_decision_secret_and_seal_gap_independently`。
- Acceptance 證明 contract id missing/mismatch、source version、ADR/AMD/spec path 可各自只產生單一對應
  blocker。
- Acceptance 證明 Phase 5 release packet、scorecard derivation/verdict/manifest、paper-shadow reconciliation、
  DQ manifest、statistical preregistration、QC/MIT/QA review hashes 可各自只產生單一對應 blocker。
- Acceptance 證明 paper-shadow window、benchmark after-cost LCB、independent observations、cost-stress LCB、
  divergence threshold/exceeded gates 可各自獨立阻斷。
- Acceptance 證明 concentration/regime/freshness labels、QC/MIT/QA review pass flags、NotEligible、
  TinyLiveAuthorized、LiveAuthorized、secret serialization 與 unsealed posture 可各自獨立阻斷。
- Python source-static guard 新增 impl-block parser，精準鎖住 `TinyLiveAdrEligibilityV1::adr_discussion_fixture`
  與 `Default`，確保 fixture 只代表 future ADR discussion eligibility，不硬編 tiny-live/live approval。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_tiny_live_eligibility_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_tiny_live_eligibility_source_static.py --tb=short`：`7 passed`。
- `cargo test -p openclaw_types --test stock_etf_tiny_live_eligibility_acceptance`：`13 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 release execution、DB/evidence writer、scorecard writer、broker session、paper order route、tiny-live/live
  authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
