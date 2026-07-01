# IBKR Phase2 Artifact Metadata Lineage Exact Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；Phase2 immutable gate artifact metadata

## 結論

已補強 `ibkr_phase2_artifact` 的 review/seal/hash/path aggregate metadata fail-closed coverage。這次只改
acceptance 與 source-static guard，不改 Rust production validator、IPC/API routes、IBKR connector、secret、
socket/client construction、paper order routing 或 Bybit 路徑。

## 變更

- Rust acceptance 將 `IbkrPhase2GateArtifactV1` review/seal/hash/path aggregate failure 固定為完整 ordered
  blocker vector，覆蓋 immutable path missing、artifact unsealed、Operator review missing、raw artifact hash
  invalid、redacted summary hash invalid。
- Python source-static guard 在既有 artifact blocker order 之外，新增 secret contract validation、API topology
  validation、runtime gate/artifact match 的 child-check order 鎖定。

## 驗證

- `rustfmt --edition 2021 --check rust/openclaw_types/tests/ibkr_phase2_artifact_acceptance.rs`：PASS。
- `python3 -B -m pytest -q tests/structure/test_ibkr_phase2_artifact_source_static.py --tb=short`：`6 passed`。
- `cargo test -p openclaw_types --test ibkr_phase2_artifact_acceptance`：`9 passed`。
- Full `cargo test -p openclaw_types`：PASS。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 IPC/API route、endpoint behavior、GUI runtime change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access、socket/client construction。
- 無 paper order routing、broker session、DB/evidence writer、scorecard writer。
- 無 paper-shadow launch、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
