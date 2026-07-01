# IBKR Phase 2 Gate Artifact Exact Lineage Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；Phase 2 immutable gate artifact lineage hardening

## 結論

已補強 `ibkr_phase2_artifact` 的 default artifact、identity/source、external gate、policy flag、runtime
evidence lineage exact-blocker coverage。這次只改 acceptance 與 source-static guard，不改 Rust production
validator、runtime、IBKR connector、secret、DB/evidence writer、paper order route 或 Bybit 路徑。

## 變更

- Rust acceptance 將 default `IbkrPhase2GateArtifactV1` blocker 檢查提升為完整順序向量。
- Rust acceptance 將 contract id/source version drift 固定為 exact 雙 blocker。
- Rust acceptance 將 blocked/retroactive external gate、policy flag mismatch、runtime evidence mismatch 固定為
  exact blocker 向量。
- Python source-static guard 新增 validator blocker ordering parser，鎖住 artifact validator 的 blocker
  emit order，支撐 exact acceptance。

## 驗證

- `rustfmt rust/openclaw_types/tests/ibkr_phase2_artifact_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_ibkr_phase2_artifact_source_static.py --tb=short`：`6 passed`。
- `cargo test -p openclaw_types --test ibkr_phase2_artifact_acceptance`：`9 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 paper order routing、DB/evidence writer、scorecard writer、broker session、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
