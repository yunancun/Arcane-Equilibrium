# Stock/ETF Scorecard Verdict Authority Lineage Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；scorecard verdict authority / lineage hardening

## 結論

已補強 `stock_etf_scorecard_verdict` 的 artifact identity、hash lineage、threshold/statistical quality、
review gates、derived-only / paper-shadow separation / live denial 與 no-side-effect boundary coverage。這次
只改 acceptance 與 source-static guard，不改 Rust production validator、IPC method、runtime、IBKR connector、
secret、DB/evidence writer、scorecard writer、evidence clock 或 paper order route。

## 變更

- Rust acceptance 新增 `scorecard_verdict_rejects_each_identity_gap_independently`。
- Rust acceptance 新增 `scorecard_verdict_rejects_each_hash_lineage_gap_independently`。
- Rust acceptance 新增 `scorecard_verdict_rejects_each_threshold_shape_gap_independently`。
- Rust acceptance 新增 `scorecard_verdict_rejects_each_profitability_and_quality_gap_independently`。
- Rust acceptance 新增 `scorecard_verdict_rejects_each_review_authority_and_boundary_gap_independently`。
- Acceptance 證明 contract/source/lane/broker/environment gaps 可獨立產生精確 blocker。
- Acceptance 證明 scorecard input、evidence clock、DQ、formula、preregistration、benchmark、cost、
  strategy、reference-data、paper-shadow reconciliation、manifest 與 rationale hashes 可獨立阻斷。
- Acceptance 證明 window/observation/divergence/probability threshold shape、positive LCB、PSR/DSR、
  quality label gates 可獨立阻斷。
- Acceptance 證明 QC/MIT/QA review hashes/pass flags、derived-only、paper-shadow separation、live-fill denial、
  Bybit-live protection、IBKR contact、connector runtime、broker fill import、scorecard writer、DB apply、
  evidence clock、secret serialization、live/tiny-live、sealed posture 與 execution-model-invalid special case
  可獨立阻斷。
- Python source-static guard 新增 `Default` / `profitability_feasible_fixture` block parsers，直接鎖住
  profitability fixture 不可硬編 crypto/Bybit/live/empty-lineage/missing-threshold/runtime/secret/writer/
  live/tiny-live posture。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_scorecard_verdict_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_scorecard_verdict_source_static.py --tb=short`：`8 passed`。
- `cargo test -p openclaw_types --test stock_etf_scorecard_verdict_acceptance`：`14 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 broker fill import execution、scorecard writer、DB/evidence writer、evidence clock start、paper order
  route、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
