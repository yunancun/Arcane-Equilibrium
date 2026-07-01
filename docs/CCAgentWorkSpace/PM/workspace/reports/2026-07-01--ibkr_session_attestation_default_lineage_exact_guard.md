# IBKR Session Attestation Default Lineage Exact Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；Phase2 session attestation gate

## 結論

已補強 `IbkrSessionAttestationV1` 的 default 與 aggregate fail-closed coverage。這次只改 acceptance 與
source-static guard，不改 Rust production validator、IPC/API routes、IBKR connector、secret、socket/client
construction、paper order routing 或 Bybit 路徑。

## 變更

- Rust acceptance 將 default `IbkrSessionAttestationV1` 固定為完整 ordered blocker vector，覆蓋 contract/source、
  status、host/port、account/secret fingerprint、process/gateway mode、secret-slot mode、live-secret、API/data
  entitlement metadata、gateway startup、raw artifact hash、attestation window 與 stale blockers。
- Rust acceptance 將 identity/host/live-port fixture drifts、hashed lineage/data-tier/startup aggregate failures、
  live-secret/env-fallback aggregate failures 固定為 exact blocker vectors。
- Python source-static guard 新增 session attestation validator blocker ordering parser，並鎖住 combined
  world-readable slot mode and flag regression 會產生兩個 `SecretSlotWorldReadable` blocker。

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
