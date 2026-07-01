# IBKR Feature Flag Secret Auth Authority Cross-Wire Guard

日期：2026-07-01
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 IBKR `stock_etf_cash` Phase 2 feature-flag/secret/scoped-auth source hardening

## Verdict

PM SIGN-OFF: DONE_WITH_CONCERNS / SOURCE-ONLY CHECKPOINT ACCEPTED

本 checkpoint 接受為 Phase 2 feature flag / secret / scoped authorization matrix
source posture regression guard。它不批准 IBKR contact、connector runtime、secret
access、authorization runtime、broker session、paper order、tiny-live/live 或任何
Bybit 行為變更。

## Changes

- `rust/openclaw_types/tests/ibkr_feature_flag_secret_auth_acceptance.rs`
  - 新增 `feature_flag_secret_auth_rejects_each_authority_gap_independently`。
  - Table-driven 覆蓋 contract/source identity、server-Rust matrix authority、GUI override denial、lane、broker、environment、instrument kind、operation denial、lane/read/paper/shadow flags、secret contract、Phase 2 artifact、session attestation、authorization envelope mismatch、permission scope、risk config hash、expiry、secret/account fingerprint mismatch。
  - 新增 aggregate lineage regression，保留 live-secret absence 與 invalid secret/account hash 的多 blocker 行為。
- `tests/structure/test_ibkr_feature_flag_secret_auth_source_static.py`
  - 新增 authorization envelope default / paper fixture block parser。
  - 新增 matrix default block parser。
  - 鎖住 default denied posture、paper rehearsal fixture hashes、matrix default fail-closed posture。
- PM trace
  - 主計畫新增 #174 checkpoint。
  - Operator summary 新增同名 update。
  - PM memory 新增壓縮記錄。

## Verification

- `rustfmt rust/openclaw_types/tests/ibkr_feature_flag_secret_auth_acceptance.rs --check`：PASS
- `python3 -B -m pytest -q tests/structure/test_ibkr_feature_flag_secret_auth_source_static.py --tb=short`：`6 passed`
- `cargo test -p openclaw_types --test ibkr_feature_flag_secret_auth_acceptance`：`10 passed`
- `cargo fmt -p openclaw_types -- --check`：PASS
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py --tb=short`：PASS
- `git diff --check`：PASS

## Boundary

未執行、未批准：

- IBKR API contact / healthcheck / socket / HTTP
- IBKR SDK import
- secret read/create/serialization
- connector runtime
- authorization runtime
- broker session
- paper order / cancel / replace route
- fill import
- DB apply / evidence writer / scorecard writer
- Linux runtime sync / restart
- tiny-live / live
- Bybit behavior change
