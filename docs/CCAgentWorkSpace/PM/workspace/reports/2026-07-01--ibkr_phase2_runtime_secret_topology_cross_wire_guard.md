# IBKR Phase2 Runtime Secret Topology Cross-Wire Guard

日期：2026-07-01
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 IBKR Phase 2 secret-slot and API topology source hardening

## Verdict

PM SIGN-OFF: DONE_WITH_CONCERNS / SOURCE-ONLY CHECKPOINT ACCEPTED

本 checkpoint 接受為 Phase 2 runtime evidence contract source posture regression guard。它不批准
IBKR contact、connector runtime、secret access、IB Gateway/TWS startup、broker session、
paper order、tiny-live/live 或任何 Bybit 行為變更。

## Changes

- `rust/openclaw_types/tests/ibkr_phase2_runtime_acceptance.rs`
  - 新增 `secret_slot_contract_rejects_each_slot_and_secret_gap_independently`。
  - 新增 `topology_rejects_each_paper_gateway_gap_independently`。
  - Table-driven 覆蓋 secret-slot contract/source identity、contract presence、readonly/paper/live slot posture、secret/account hash、owner-only permission、env-var fallback denial、secret/account serialization、live-secret absence、API topology contract/source identity、baseline、runtime owner、loopback host、paper gateway port、gateway mode、paper environment、deterministic client id、process identity、account hash、server/data/startup/expiry evidence。
  - 保留 live TWS/gateway port aggregate 行為：live port 會同時拒絕 `LivePortDenied` 與 `PaperPortNotUsed`。
- `tests/structure/test_ibkr_phase2_runtime_source_static.py`
  - 新增 secret-slot default/source-template block parser。
  - 新增 API topology default/source-template block parser。
  - 鎖住 default fail-closed posture與 source-template paper-only/no-secret posture。
- PM trace
  - 主計畫新增 #175 checkpoint。
  - Operator summary 新增同名 update。
  - PM memory 新增壓縮記錄。

## Verification

- `rustfmt rust/openclaw_types/tests/ibkr_phase2_runtime_acceptance.rs --check`：PASS
- `python3 -B -m pytest -q tests/structure/test_ibkr_phase2_runtime_source_static.py --tb=short`：`5 passed`
- `cargo test -p openclaw_types --test ibkr_phase2_runtime_acceptance`：`9 passed`
- `cargo fmt -p openclaw_types -- --check`：PASS
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py --tb=short`：PASS
- `git diff --check`：PASS

## Boundary

未執行、未批准：

- IBKR API contact / healthcheck / socket / HTTP
- IBKR SDK import
- secret read/create/serialization
- connector runtime
- IB Gateway / TWS startup
- broker session
- paper order / cancel / replace route
- fill import
- DB apply / evidence writer / scorecard writer
- Linux runtime sync / restart
- tiny-live / live
- Bybit behavior change
