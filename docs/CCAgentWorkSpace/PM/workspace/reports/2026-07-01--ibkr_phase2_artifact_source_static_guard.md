# PM Report — IBKR Phase2 Artifact Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：IBKR Phase 2 immutable gate artifact source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`ibkr_phase2_artifact.rs` 的 source-only 姿態；不是 external-surface gate PASS、
不是 immutable artifact materialization、不是第一次 IBKR contact。

## Completed

- 新增 `tests/structure/test_ibkr_phase2_artifact_source_static.py`。
- Guard 要求 `ibkr_phase2_artifact.rs` 低於 800 行 governance cap。
- Guard 要求 artifact fields、verdict/blocker enum、`is_sha256_hex`、PM/Operator
  reviewer check、policy-flag cross-check、runtime contract cross-check 保持在 source
  中。
- Guard 要求 artifact default 仍 fail-closed：empty contract/source/artifact fields、
  default blocked external gate、default secret-slot contract、default API topology。
- Guard 要求 validate 仍以 `blockers.is_empty()` 作為 `ibkr_contact_allowed` 的唯一
  source verdict，並拒絕 retroactive `ibkr_call_performed`。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_ibkr_phase2_artifact_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_ibkr_phase2_artifact_source_static.py`：
  `4 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test ibkr_phase2_artifact_acceptance -- --nocapture`：
  `8 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。

## Boundary

未批准也未執行：IBKR contact、IBKR SDK import、secret access/creation、connector
runtime、socket/HTTP、read probe、result import、collector、market-data ingestion、
DQ writer、paper order/cancel/replace、fill import、DB apply、evidence writer/clock、
scorecard writer、GUI fanout、tiny-live/live、或任何 Bybit behavior change。
