# PM Report — Stock/ETF Strategy Hypothesis Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：Stock/ETF strategy hypothesis source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`stock_etf_strategy_hypothesis.rs` 的 source-only 姿態；不是 IBKR contact、不是 connector
runtime、不是 market-data collection、不是 scorecard writer、不是 profitability claim、不是
live/tiny-live authorization、不是 paper order。

## Completed

- 新增 `tests/structure/test_stock_etf_strategy_hypothesis_source_static.py`。
- Guard 要求 `stock_etf_strategy_hypothesis.rs` 低於 800 行 governance cap。
- Guard 要求 exact `stock_etf_strategy_hypothesis_contract_v1` contract id、hypothesis fields、
  family/timeframe/scope enums、verdict/blocker surface、hash validator、limit/control validator、
  identifier helper 保持在 source 中。
- Guard 要求 default hypothesis fail-closed：CryptoPerp/Bybit、empty id/version、UnknownDenied
  family/timeframe/scope、empty universe/cost/rule/design/preregistration hashes、zero holding/
  turnover/constituent/sample controls、all bias/metric/paper-shadow controls false、no profitability/
  live authority claim、Bybit live unchanged false、IBKR live denied false。
- Guard 要求 accepted fixture 保留 StockEtfCash/IBKR、daily momentum large-100 hypothesis id/version、
  DailyMomentum/Daily/StockAndEtf、universe/PIT universe/benchmark/cost/entry/exit/risk/feature/
  data-source/statistical-design/preregistration hashes、holding >= 3 days、turnover 5000 bps、max
  constituents 100、independent observations 50、bias/multiple-testing/benchmark/cost-after/
  no-options-CFD-margin-short controls、paper-shadow-only、no profitability/live authority。
- Guard 要求 validation matrix 保留 contract/version/lane/broker/id/version checks、allowed
  family/timeframe/scope, all hash checks, holding/turnover/constituent/sample limits, bias/metric/
  forbidden-instrument/paper-shadow controls, no premature profitability/live authority/contact/secret。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_strategy_hypothesis_source_static.py tests/structure/test_docs_readme_index_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_strategy_hypothesis_source_static.py`：
  `9 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_strategy_hypothesis_acceptance -- --nocapture`：
  `7 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py -k 'ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles or ibkr_stock_etf_pm_checkpoint_numbers_are_linear'`：
  `2 passed, 5 deselected`。
- `git diff --check`（scoped to #129 files）：PASS。

## Boundary

未批准也未執行：runtime authority、IBKR contact、IBKR SDK import、secret access/creation、
connector runtime、socket/HTTP、market-data collection、evidence clock、scorecard writer、
profitability claim、DB apply、read probe execution、result import execution、paper order/cancel/
replace、fill import、order route、GUI fanout、tiny-live/live、或任何 Bybit behavior change。
