# IBKR Embedded Allowlist Gate Exact Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；Phase2 embedded non-Bybit allowlist gate checks

## 結論

已補強 `ibkr_phase2_gate_acceptance` 內嵌的 `NonBybitApiAllowlistV1` default 與 drift fail-closed coverage。這次只改
Rust acceptance 與 PM 記錄，不改 Rust production validator、IPC/API routes、IBKR connector、secret、socket/client
construction、paper order routing 或 Bybit 路徑。

## 變更

- Rust acceptance 將 embedded default `NonBybitApiAllowlistV1` 固定為完整 ordered blocker vector，包含 contract/source、
  每個 required API action missing、denial flags 與 Bybit live protection。
- Rust acceptance 將 embedded identity/source/API baseline/action drift/denial/contact/secret/Bybit aggregate failure
  固定為 exact blocker vector。

## 驗證

- `rustfmt --edition 2021 --check rust/openclaw_types/tests/ibkr_phase2_gate_acceptance.rs`：PASS。
- `python3 -B -m pytest -q tests/structure/test_ibkr_phase2_gate_source_static.py --tb=short`：`8 passed`。
- `cargo test -p openclaw_types --test ibkr_phase2_gate_acceptance`：`13 passed`。
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
