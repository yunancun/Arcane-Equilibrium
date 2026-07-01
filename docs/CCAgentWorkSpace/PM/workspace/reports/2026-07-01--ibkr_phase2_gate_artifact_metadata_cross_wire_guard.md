# IBKR Phase2 Gate Artifact Metadata Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；Phase 2 gate artifact metadata hardening

## 結論

已補強 immutable Phase 2 gate artifact 的 metadata、reviewer、seal、hash 與 default fail-closed
posture。這次只新增 acceptance 與 source-static guard，不改 Rust production code、IPC method、
runtime、IBKR connector、secret lookup、broker session、PASS artifact materialization、paper order route
或 tiny-live/live authority。

## 變更

- Rust acceptance 新增 `artifact_rejects_each_metadata_seal_and_hash_gap_independently`。
- 證明 artifact id、ADR、AMD、source commit、created-at、immutable storage path、PM reviewer、
  Operator reviewer、sealed flag、raw artifact hash、redacted summary hash 缺失或錯誤都會各自只產生
  單一 blocker。
- 保留既有 gate/runtime mismatch aggregate coverage；不把會同時拒絕 external gate 的 runtime drift
  誤標成 single-blocker。
- Python source-static guard 新增 default block parser，鎖住 empty/unsealed/no-reviewer/no-runtime/
  no-secret/topology-default/hash-empty fail-closed posture。

## 驗證

- `rustfmt rust/openclaw_types/tests/ibkr_phase2_artifact_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_ibkr_phase2_artifact_source_static.py --tb=short`：`5 passed`。
- `cargo test -p openclaw_types --test ibkr_phase2_artifact_acceptance`：`9 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 PASS artifact materialization、broker session、broker routing、paper order route、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
