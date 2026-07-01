# PM Report — IBKR Non-Bybit API Allowlist Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：IBKR non-Bybit API allowlist/deny matrix source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`ibkr_non_bybit_api_allowlist.rs` 的 source-only 姿態；不是 external-surface gate
PASS、不是 IBKR client construction、不是 read probe、不是 paper order submission。

## Completed

- 新增 `tests/structure/test_ibkr_non_bybit_api_allowlist_source_static.py`。
- Guard 要求 `ibkr_non_bybit_api_allowlist.rs` 低於 800 行 governance cap。
- Guard 要求 allowlist contract id、action enum、denial reason enum、decision、
  allowlist/verdict/blocker surface、classifier、required-action list 與 bucket
  validator 保持在 source 中。
- Guard 要求 10 個 read actions、3 個 paper-write actions、10 個 denied actions 與
  10 個 typed denial reasons 不得消失。
- Guard 要求 paper-write action 仍需要 external surface gate、session attestation 與
  paper-order gates，且不能在 external gate 後直接 allowed。
- Guard 要求 live order、live account fingerprint、transfer、margin/short/options/CFD、
  market-data entitlement purchase、account management write、Client Portal Web API 仍
  typed-denied。
- Guard 要求 drift detection 保留 missing/duplicated/wrong-bucket checks，並要求
  retroactive IBKR contact、secret serialization、Bybit live execution unprotected 都會
  block。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_ibkr_non_bybit_api_allowlist_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_ibkr_non_bybit_api_allowlist_source_static.py`：
  `5 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test ibkr_phase2_gate_acceptance -- --nocapture`：
  `11 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。

## Boundary

未批准也未執行：IBKR contact、IBKR SDK import、secret access/creation、connector
runtime、socket/HTTP、read probe、result import、collector、market-data ingestion、
DQ writer、paper order/cancel/replace、fill import、DB apply、evidence writer/clock、
scorecard writer、GUI fanout、tiny-live/live、或任何 Bybit behavior change。
