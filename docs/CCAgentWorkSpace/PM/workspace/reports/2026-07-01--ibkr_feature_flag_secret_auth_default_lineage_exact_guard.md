# IBKR Feature Flag Secret Auth Default Lineage Exact Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；feature flag / secret / scoped-auth matrix hardening

## 結論

已補強 `ibkr_feature_flag_secret_auth` 的 feature flag、secret contract、Phase2 artifact、session attestation、
authorization envelope aggregate fail-closed coverage。這次只改 acceptance 與 source-static guard，不改 Rust
production validator、IPC/API routes、IBKR connector、secret、socket/client construction、paper order routing
或 Bybit 路徑。

## 變更

- Rust acceptance 將 default `FeatureFlagSecretAuthMatrixV1` blocker 檢查提升為完整順序向量，覆蓋
  contract/source、server authority、GUI override、lane/paper/shadow flags、secret/artifact/session、envelope
  hash/expiry blockers。
- Rust acceptance 將 readonly/paper/live/shadow/gui、fingerprint mismatch、aggregate secret/hash failures、
  contract/source drift cases 固定為 exact vectors。
- Python source-static guard 新增 root validator 與 authorization-envelope validator blocker ordering parser，
  並鎖住 secret -> artifact -> session -> envelope validation order。

## 驗證

- `rustfmt --edition 2021 --check rust/openclaw_types/tests/ibkr_feature_flag_secret_auth_acceptance.rs`：PASS。
- `python3 -B -m pytest -q tests/structure/test_ibkr_feature_flag_secret_auth_source_static.py --tb=short`：`7 passed`。
- `cargo test -p openclaw_types --test ibkr_feature_flag_secret_auth_acceptance`：`10 passed`。
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
