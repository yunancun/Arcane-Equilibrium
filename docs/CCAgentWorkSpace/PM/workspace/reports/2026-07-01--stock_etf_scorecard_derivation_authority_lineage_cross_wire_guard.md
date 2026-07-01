# Stock/ETF Scorecard Derivation Authority Lineage Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；scorecard derivation authority / lineage hardening

## 結論

已補強 `stock_etf_scorecard_derivation` 的 artifact identity、ids、hash lineage、atomic/replay/
paper-shadow separation、seal 與 no-side-effect boundary coverage。這次只改 acceptance 與 source-static
guard，不改 Rust production validator、IPC method、runtime、IBKR connector、secret、DB/evidence writer、
scorecard writer、reconciliation writer、shadow collector 或 paper order route。

## 變更

- Rust acceptance 新增 `derivation_rejects_each_identity_gap_independently`。
- Rust acceptance 新增 `derivation_rejects_each_id_gap_independently`。
- Rust acceptance 新增 `derivation_rejects_each_hash_lineage_gap_independently`。
- Rust acceptance 新增 `derivation_rejects_each_evidence_and_seal_gap_independently`。
- Rust acceptance 新增 `derivation_rejects_each_boundary_flag_independently`。
- Acceptance 證明 contract/source/lane/broker/environment gaps 可獨立產生精確 blocker。
- Acceptance 證明 derivation run、strategy、universe、benchmark、as-of ids 可獨立阻斷。
- Acceptance 證明 scorecard input、evidence clock、DQ、paper-shadow reconciliation、formula、
  preregistration、manifest、verdict、source commit、derivation code、output artifact、QC/MIT/QA review
  hashes 可獨立阻斷。
- Acceptance 證明 atomic-facts-only、idempotent replay、paper-shadow fill separation、Bybit-live protection
  與 sealed posture 可獨立阻斷。
- Acceptance 證明 IBKR contact、connector runtime、broker fill import、shadow fill generation、
  reconciliation writer、scorecard writer、DB apply、evidence clock、secret serialization、live/tiny-live
  flags 可獨立阻斷。
- Python source-static guard 新增 `Default` / `accepted_fixture` block parsers，直接鎖住 accepted fixture
  不可硬編 crypto/Bybit/live/shadow/empty-lineage/unsealed/runtime/secret/writer posture。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_scorecard_derivation_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_scorecard_derivation_source_static.py --tb=short`：`7 passed`。
- `cargo test -p openclaw_types --test stock_etf_scorecard_derivation_acceptance`：`11 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 broker fill import execution、shadow fill generation、reconciliation writer、scorecard writer、
  DB/evidence writer、evidence clock start、paper order route、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
