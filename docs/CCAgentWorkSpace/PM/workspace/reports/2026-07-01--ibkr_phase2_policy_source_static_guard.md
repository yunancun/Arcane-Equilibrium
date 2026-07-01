# PM Report — IBKR Phase2 Policy Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：IBKR Stock/ETF Phase 2 prerequisite policy source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`ibkr_phase2_policies.rs` 的 source-only 姿態；不是 Phase 2 runtime start、不是
external-surface gate PASS，也不是 IBKR contact。

## Completed

- 新增 `tests/structure/test_ibkr_phase2_policies_source_static.py`。
- Guard 要求 `ibkr_phase2_policies.rs` 低於 800 行 governance cap。
- Guard 要求 redaction、rate-limit、audit-event、paper-attestation、Python no-write
  guard 的 named contract id 與 policy `impl` 保持在 source 中。
- Guard 禁止 runtime material、network、clock/thread/process、order 和 Bybit runtime
  tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_ibkr_phase2_policies_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_ibkr_phase2_policies_source_static.py`：
  `3 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test ibkr_phase2_policy_acceptance -- --nocapture`：
  `9 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。

## Boundary

未批准也未執行：IBKR contact、IBKR SDK import、secret access/creation、connector
runtime、socket/HTTP、read probe、result import、collector、market-data ingestion、
DQ writer、paper order/cancel/replace、fill import、DB apply、evidence writer/clock、
scorecard writer、GUI fanout、tiny-live/live、或任何 Bybit behavior change。
