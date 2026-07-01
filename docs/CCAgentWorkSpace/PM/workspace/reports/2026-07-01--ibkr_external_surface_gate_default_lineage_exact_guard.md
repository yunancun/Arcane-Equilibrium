# IBKR External Surface Gate Default Lineage Exact Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；Phase2 pre-contact external surface gate

## 結論

已補強 `ibkr_phase2_gate` external surface gate 的 default 與 wrong-surface aggregate fail-closed coverage。這次只改
acceptance 與 source-static guard，不改 Rust production validator、IPC/API routes、IBKR connector、secret、
socket/client construction、paper order routing 或 Bybit 路徑。

## 變更

- Rust acceptance 將 default `IbkrExternalSurfaceGateV1` 固定為完整 ordered blocker vector，覆蓋 contract/source、
  blocked status、live-port denial proof、secret-contract/live-secret proof、allowlist、redaction/rate-limit/audit/
  paper-attestation/python guard prerequisites。
- Rust acceptance 將 wrong identity、retroactive call-side-effect、wrong API baseline、wrong host/port policy cases
  固定為 exact blocker vectors。
- Python source-static guard 新增 external surface gate validator blocker ordering parser。

## 驗證

- `rustfmt --edition 2021 --check rust/openclaw_types/tests/ibkr_phase2_gate_acceptance.rs`：PASS。
- `python3 -B -m pytest -q tests/structure/test_ibkr_phase2_gate_source_static.py --tb=short`：`7 passed`。
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
