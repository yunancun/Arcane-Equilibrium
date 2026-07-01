# Stock/ETF Phase0 Manifest Default Lineage Exact Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；Phase0 manifest fail-closed lineage hardening

## 結論

已補強 `stock_etf_phase0_manifest` 的 Phase0 named contract packet manifest default fail-closed
coverage。這次只改 acceptance 與 source-static guard，不改 Rust production validator、IPC/API routes、
IBKR connector、secret、paper order route、DB/evidence writer、GUI runtime 或 Bybit 路徑。

## 變更

- Rust acceptance 將 default `StockEtfPhase0ContractPacketManifestV1` blocker 檢查提升為完整順序向量，
  包含 top-level identity、authority path、API baseline、global denial、所有 required contract missing、
  phase unlock fail-closed blockers。
- Rust acceptance 將 accepted fixture 合約集合改成 `required_phase0_contract_ids()` 的完整 ordered
  equality，並將 contract completeness/duplicate/unexpected、API baseline、global denial/unlock mutation cases
  固定為 exact vectors。
- Python source-static guard 新增 manifest/authority/API/contracts/unlock validator blocker ordering parser，
  並鎖住 root validator child-call order。

## 驗證

- `rustfmt --edition 2021 --check rust/openclaw_types/tests/stock_etf_phase0_manifest_acceptance.rs`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_phase0_manifest_source_static.py --tb=short`：`7 passed`。
- `cargo test -p openclaw_types --test stock_etf_phase0_manifest_acceptance`：`6 passed`。
- Full `cargo test -p openclaw_types`：PASS。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 IPC/API route、endpoint behavior、GUI runtime change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 paper order routing、broker session、DB/evidence writer、scorecard writer。
- 無 paper-shadow launch、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
