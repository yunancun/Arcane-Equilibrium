# PM Report — Stock/ETF Scorecard Verdict Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：Stock/ETF scorecard verdict source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`stock_etf_scorecard_verdict.rs` 的 source-only 姿態；不是 IBKR contact、不是
scorecard writer、不是 DB apply、不是 evidence clock、不是 tiny-live/live authorization、
不是 Bybit gate lowering。

## Completed

- 新增 `tests/structure/test_stock_etf_scorecard_verdict_source_static.py`。
- Guard 要求 `stock_etf_scorecard_verdict.rs` 低於 800 行 governance cap。
- Guard 要求 verdict contract id、label enum、request/verdict/blocker surface、contract/hash/
  threshold/window/divergence/profitability/probability/quality/review authority validators 保持在
  source 中。
- Guard 要求 default 仍 fail-closed：CryptoPerp/Bybit、LiveReservedDenied、
  InsufficientEvidence、derived-only false、paper/shadow separation false、Bybit live protection
  false、sealed false。
- Guard 要求 profitability-feasible fixture 保留 StockEtfCash/IBKR/Paper、window/observation
  門檻、net PnL、positive LCBs、divergence threshold、PSR/DSR thresholds、quality labels、
  derived-only、paper/shadow separation、no live fill、Bybit live unchanged、no tiny-live/live、
  sealed=true。
- Guard 要求 label dispatch 保留 ProfitabilityFeasible/ResearchPromising/EngineeringReady/
  ExecutionModelInvalid/InsufficientEvidence/Kill 差異，且 ExecutionModelInvalid 必須有 execution
  failure evidence。
- Guard 要求 formula appendix、statistical preregistration、scorecard input、evidence clock、
  DQ、benchmark/cost/strategy/reference/reconciliation/manifest/rationale hashes，window、
  independent observation、divergence、PSR/DSR、LCB、quality label checks 不得消失。
- Guard 要求 QC/MIT/QA review hashes/pass flags、derived-only、paper-shadow separation、live
  fill denial、Bybit live protection、IBKR contact、connector runtime、broker fill import、
  scorecard writer、DB apply、evidence clock、secret serialization、live/tiny-live、sealed boundary
  flags 不得消失。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_scorecard_verdict_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_scorecard_verdict_source_static.py`：
  `7 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_scorecard_verdict_acceptance -- --nocapture`：
  `8 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。

## Boundary

未批准也未執行：IBKR contact、IBKR SDK import、secret access/creation、connector
runtime、socket/HTTP、read probe、result import、collector、market-data ingestion、DQ writer、
paper order/cancel/replace、broker fill import、scorecard writer、DB apply、evidence writer/clock、
Bybit gate lowering、GUI fanout、tiny-live/live、或任何 Bybit behavior change。
