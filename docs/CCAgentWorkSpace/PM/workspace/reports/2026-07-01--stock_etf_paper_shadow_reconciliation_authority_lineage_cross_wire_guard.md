# Stock/ETF Paper Shadow Reconciliation Authority Lineage Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；paper-shadow reconciliation authority / lineage hardening

## 結論

已補強 `stock_etf_paper_shadow_reconciliation` 的 contract/scope/authority、paper-fill/shadow-signal/
shadow-fill-model lineage、reconciliation evidence gates 與 no-side-effect boundary coverage。這次只改
acceptance 與 source-static guard，不改 Rust production validator、IPC method、runtime、IBKR connector、
secret、DB/evidence writer、reconciliation writer、shadow collector 或 paper order route。

## 變更

- Rust acceptance 新增 `reconciliation_rejects_each_authority_gap_independently`。
- Rust acceptance 新增 `reconciliation_rejects_each_lineage_gap_independently`。
- Rust acceptance 新增 `reconciliation_rejects_each_evidence_gate_independently`。
- Rust acceptance 新增 `reconciliation_rejects_each_boundary_flag_independently`。
- Acceptance 證明 contract/source/lane/broker/scope/authority/effect gaps 可獨立產生精確 blocker。
- Acceptance 證明 reconciliation run、paper local order、broker order、execution、commission、shadow signal
  ids，以及 lifecycle/event-log/paper-fill-import/shadow-signal/shadow-fill-model/cost/market/divergence/link/
  raw/redacted/source artifact hashes 可獨立阻斷。
- Acceptance 證明 append-only event、paper fill imported、synthetic shadow fill、divergence threshold、
  divergence excess、unmatched paper/shadow fill evidence gates 可獨立阻斷。
- Acceptance 證明 IBKR contact、connector runtime、secret serialization、fill import execution、shadow fill
  generation、reconciliation writer、scorecard writer、DB apply、order route、Bybit path reuse、live/tiny-live、
  margin/short/options/CFD、Python direct broker write flags 可獨立阻斷。
- Python source-static guard 新增 `Default` / `accepted_fixture` block parsers，直接鎖住 accepted fixture
  不可硬編 crypto/Bybit/wrong scope/wrong authority/effectful/empty-lineage/unready-evidence/runtime/secret/
  writer/order posture。

## 驗證

- `rustfmt rust/openclaw_types/tests/stock_etf_paper_shadow_reconciliation_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_paper_shadow_reconciliation_source_static.py --tb=short`：`9 passed`。
- `cargo test -p openclaw_types --test stock_etf_paper_shadow_reconciliation_acceptance`：`10 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 fill import execution、shadow fill generation、reconciliation writer、scorecard writer、DB/evidence writer、
  paper order route、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
