# PM Report — IBKR Phase2 Gate Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：IBKR Phase 2 pre-contact gate source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`ibkr_phase2_gate.rs` 的 source-only 姿態；不是 external-surface gate PASS、不是
session attestation runtime、不是第一次 IBKR contact。

## Completed

- 新增 `tests/structure/test_ibkr_phase2_gate_source_static.py`。
- Guard 要求 `ibkr_phase2_gate.rs` 低於 800 行 governance cap。
- Guard 要求 ADR/AMD、external-surface gate、session attestation、paper/live port
  constants 保持精確。
- Guard 要求 external-surface gate type surface、13 個 gate fields、18 個 gate
  blockers、`ibkr_contact_allowed: blockers.is_empty()` 與 retroactive
  `ibkr_call_performed` blocker 保持在 source 中。
- Guard 要求 session attestation type surface、20 個 attestation fields、28 個
  attestation blockers、loopback/paper-port/live-port/env-fallback/staleness checks
  保持在 source 中。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_ibkr_phase2_gate_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_ibkr_phase2_gate_source_static.py`：
  `4 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test ibkr_phase2_gate_acceptance -- --nocapture`：
  `11 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。

## Boundary

未批准也未執行：IBKR contact、IBKR SDK import、secret access/creation、connector
runtime、socket/HTTP、read probe、result import、collector、market-data ingestion、
DQ writer、paper order/cancel/replace、fill import、DB apply、evidence writer/clock、
scorecard writer、GUI fanout、tiny-live/live、或任何 Bybit behavior change。
