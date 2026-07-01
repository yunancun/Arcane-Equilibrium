# PM Report — IBKR Feature Flag Secret Auth Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：IBKR feature-flag / secret / scoped authorization matrix source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`ibkr_feature_flag_secret_auth.rs` 的 source-only 姿態；不是 feature flag
enablement、不是 secret-slot reader、不是 Phase 2 artifact PASS、不是 session
runtime、不是 paper order authorization。

## Completed

- 新增 `tests/structure/test_ibkr_feature_flag_secret_auth_source_static.py`。
- Guard 要求 `ibkr_feature_flag_secret_auth.rs` 低於 800 行 governance cap。
- Guard 要求 matrix contract id、authorization envelope、matrix/verdict/blocker
  surface、evaluation helper 保持在 source 中。
- Guard 要求 default 仍 fail-closed：empty contract/source version、read-only/denied
  envelope、default feature flags、default secret/artifact/session/envelope contracts、
  GUI override denied false、server Rust authoritative false。
- Guard 要求 decision chain 仍同時檢查 lane/broker/live environment/instrument/live
  or account-write operation、read-only/paper/shadow-only flags、secret contract、
  live-secret absence、Phase2 artifact、session attestation 與 authorization envelope。
- Guard 要求 authorization envelope 維持 scope、hash validity、expiry、
  secret-slot fingerprint 與 account fingerprint 跨 secret/artifact/session 的一致性
  檢查。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_ibkr_feature_flag_secret_auth_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_ibkr_feature_flag_secret_auth_source_static.py`：
  `5 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test ibkr_feature_flag_secret_auth_acceptance -- --nocapture`：
  `8 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。

## Boundary

未批准也未執行：IBKR contact、IBKR SDK import、secret access/creation、connector
runtime、socket/HTTP、read probe、result import、collector、market-data ingestion、
DQ writer、paper order/cancel/replace、fill import、DB apply、evidence writer/clock、
scorecard writer、GUI fanout、tiny-live/live、或任何 Bybit behavior change。
