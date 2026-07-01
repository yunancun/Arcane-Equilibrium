# IBKR External Surface Gate Precontact Cross-Wire Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；external surface gate precontact hardening

## 結論

已補強 `IbkrExternalSurfaceGateV1` 的 pre-contact gate posture。這次只新增 acceptance 與
source-static guard，不改 Rust production code、IPC method、runtime、IBKR connector、secret lookup、
session attestation runtime、broker session、paper order route 或 tiny-live/live authority。

## 變更

- Rust acceptance 新增 `external_surface_gate_rejects_each_precontact_gap_independently`。
- 證明 contract id、source version、status、ADR、AMD、API baseline、host policy、port policy、
  live-port denial、secret contract、live-secret absence、API allowlist、redaction suite、rate-limit
  policy、audit-event policy、paper-attestation contract、Python no-write guard、retroactive IBKR call
  都會各自只產生單一 blocker。
- Python source-static guard 新增 default / passing fixture block parser，鎖住 default blocked posture 與
  passing fixture no-side-effect posture。

## 驗證

- `rustfmt rust/openclaw_types/tests/ibkr_phase2_gate_acceptance.rs --check`：PASS。
- `python3 -B -m pytest -q tests/structure/test_ibkr_phase2_gate_source_static.py --tb=short`：`5 passed`。
- `cargo test -p openclaw_types --test ibkr_phase2_gate_acceptance`：`12 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 endpoint / IPC method change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 session attestation runtime、broker session、broker routing、paper order route、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
