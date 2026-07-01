# PM Report — Stock/ETF Scorecard Derivation Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：Stock/ETF scorecard derivation source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`stock_etf_scorecard_derivation.rs` 的 source-only 姿態；不是 IBKR contact、不是
broker fill import、不是 shadow fill generation、不是 reconciliation writer、不是
scorecard writer、不是 DB apply、不是 evidence clock。

## Completed

- 新增 `tests/structure/test_stock_etf_scorecard_derivation_source_static.py`。
- Guard 要求 `stock_etf_scorecard_derivation.rs` 低於 800 行 governance cap。
- Guard 要求 derivation contract id、request/verdict/blocker surface、id validator、hash
  validator、authority validator 保持在 source 中。
- Guard 要求 default 仍 fail-closed：CryptoPerp/Bybit、LiveReservedDenied、atomic-facts-only
  false、idempotent replay false、paper/shadow separation false、Bybit live protection false、
  sealed false。
- Guard 要求 accepted fixture 仍是 StockEtfCash/IBKR/Paper，並保留 atomic-facts-only、
  idempotent replay、paper/shadow separation、Bybit live execution unchanged、no side-effect
  flags 與 sealed=true。
- Guard 要求 derivation/strategy/universe/benchmark/as-of ids 與 scorecard input、
  evidence clock manifest、DQ manifest、paper-shadow reconciliation、formula appendix、
  statistical preregistration、scorecard manifest/verdict、source commit、derivation code、
  output artifact、QC/MIT/QA review hash checks 不得消失。
- Guard 要求 derived-only、idempotent replay、paper-shadow separation、Bybit live protection、
  IBKR contact、connector runtime、broker fill import、shadow fill generation、reconciliation
  writer、scorecard writer、DB apply、evidence clock、secret serialization、live/tiny-live、
  sealed boundary flags 不得消失。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_scorecard_derivation_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_scorecard_derivation_source_static.py`：
  `6 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_scorecard_derivation_acceptance -- --nocapture`：
  `5 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。

## Boundary

未批准也未執行：IBKR contact、IBKR SDK import、secret access/creation、connector
runtime、socket/HTTP、read probe、result import、collector、market-data ingestion、DQ writer、
paper order/cancel/replace、broker fill import、shadow fill generation、reconciliation writer、
scorecard writer、DB apply、evidence writer/clock、GUI fanout、tiny-live/live、或任何
Bybit behavior change。
