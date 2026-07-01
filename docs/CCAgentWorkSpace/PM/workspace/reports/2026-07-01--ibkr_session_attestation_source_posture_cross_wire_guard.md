# IBKR Session Attestation Source Posture Cross-Wire Guard

日期：2026-07-01
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 IBKR `stock_etf_cash` Phase 2 pre-contact source/test hardening

## Verdict

PM SIGN-OFF: DONE_WITH_CONCERNS / SOURCE-ONLY CHECKPOINT ACCEPTED

本 checkpoint 接受為 Phase 2 session attestation source posture regression guard。它不批准
IBKR contact、connector runtime、secret access、broker session、paper order、tiny-live/live
或任何 Bybit 行為變更。

## Changes

- `rust/openclaw_types/tests/ibkr_phase2_gate_acceptance.rs`
  - 新增 `session_attestation_rejects_each_secret_lineage_and_window_gap_independently`。
  - Table-driven 覆蓋 session attestation contract/source identity、status、environment、host、paper port、account fingerprint、live account marker、process identity、gateway mode、secret fingerprint、secret slot mode、world-readable secret、live secret absence、env-var credential fallback、API server version、data tier、entitlements fingerprint、market-data entitlement purchase denial、gateway startup time、raw artifact hash、invalid attestation window。
  - 保留 live TWS/gateway port aggregate 行為：live port 會同時拒絕 `LivePortDenied` 與 `PortNotPaperGatewayDefault`。
  - 新增 stale attestation single-blocker coverage。
- `tests/structure/test_ibkr_phase2_gate_source_static.py`
  - 新增 session default / paper fixture block parser。
  - 鎖住 default fail-closed posture 與 paper fixture 的 loopback、paper gateway、no-live-secret、hash-lineage posture。
- PM trace
  - 主計畫新增 #173 checkpoint。
  - Operator summary 新增同名 update。
  - PM memory 新增壓縮記錄。

## Verification

- `rustfmt rust/openclaw_types/tests/ibkr_phase2_gate_acceptance.rs --check`：PASS
- `python3 -B -m pytest -q tests/structure/test_ibkr_phase2_gate_source_static.py --tb=short`：`6 passed`
- `cargo test -p openclaw_types --test ibkr_phase2_gate_acceptance`：`13 passed`
- `cargo fmt -p openclaw_types -- --check`：PASS
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py --tb=short`：PASS
- `git diff --check`：PASS

## Boundary

未執行、未批准：

- IBKR API contact / healthcheck / socket / HTTP
- IBKR SDK import
- secret read/create/serialization
- connector runtime
- session attestation runtime
- broker session
- paper order / cancel / replace route
- fill import
- DB apply / evidence writer / scorecard writer
- Linux runtime sync / restart
- tiny-live / live
- Bybit behavior change
