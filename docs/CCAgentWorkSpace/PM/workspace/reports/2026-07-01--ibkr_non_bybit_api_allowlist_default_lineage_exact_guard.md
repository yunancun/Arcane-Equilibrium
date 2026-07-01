# IBKR Non-Bybit API Allowlist Default Lineage Exact Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；Non-Bybit API allowlist fail-closed hardening

## 結論

已補強 `ibkr_non_bybit_api_allowlist` 的 read/paper-write/denied API action matrix default fail-closed
coverage。這次只改 acceptance 與 source-static guard，不改 Rust production validator、IPC/API routes、IBKR
connector、secret、socket/client construction、paper order routing 或 Bybit 路徑。

## 變更

- Rust acceptance 將 default `NonBybitApiAllowlistV1` blocker 檢查提升為完整順序向量，包含所有 required
  API action missing blockers 與 denied-surface/Bybit-protection blockers。
- Rust acceptance 固定 accepted fixture 的 read、paper-write、denied action buckets 的完整 ordered lists，
  並將 missing/duplicate/wrong-bucket action drift cases 固定為 exact vectors。
- Python source-static guard 新增 allowlist validator 與 action-bucket validator blocker ordering parser，
  並鎖住 root validator 在 denial checks 前先執行 action matrix drift detection。

## 驗證

- `rustfmt --edition 2021 --check rust/openclaw_types/tests/ibkr_non_bybit_api_allowlist_acceptance.rs`：PASS。
- `python3 -B -m pytest -q tests/structure/test_ibkr_non_bybit_api_allowlist_source_static.py --tb=short`：`7 passed`。
- `cargo test -p openclaw_types --test ibkr_non_bybit_api_allowlist_acceptance`：`4 passed`。
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
