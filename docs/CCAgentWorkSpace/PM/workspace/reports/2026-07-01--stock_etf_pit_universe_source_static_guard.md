# PM Report — Stock/ETF PIT Universe Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：Stock/ETF PIT universe source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`stock_etf_pit_universe.rs` 的 source-only 姿態；不是 IBKR contact、不是 connector runtime、
不是 market-data collection、不是 evidence clock、不是 scorecard writer、不是 DB apply、不是
paper order。

## Completed

- 新增 `tests/structure/test_stock_etf_pit_universe_source_static.py`。
- Guard 要求 `stock_etf_pit_universe.rs` 低於 800 行 governance cap。
- Guard 要求 exact `stock_etf_pit_universe_contract_v1` contract id、universe fields、
  constituent fields、verdict/blocker surface、constituent validator、required-hash validator、
  identifier/symbol helpers 保持在 source 中。
- Guard 要求 default universe fail-closed：CryptoPerp/Bybit、empty universe id/version/hash、
  missing PIT/effective window、zero counts、empty constituents、empty rule/screen/policy hashes、
  not frozen for evidence clock、survivorship controls missing、Bybit live unchanged false、IBKR live
  denied false。
- Guard 要求 accepted fixture 保留 StockEtfCash/IBKR、`US_LARGE_100_V1`、version
  `US_LARGE_100_V1_20260301`、PIT/effective window、3 constituents AMD/MSFT/SPY、max 100、
  inclusion/exclusion/liquidity/tradability/PRIIPs/delisted/corporate-action/market-calendar/source
  hashes、frozen/survivorship controls、Bybit live protection、IBKR live denial。
- Guard 要求 validation matrix 保留 contract/version/lane/broker checks、identifier/hash checks、
  PIT/effective-window/count/max-count/broad-universe checks、constituent validation、required
  hashes、frozen/survivorship/boundary checks。
- Guard 要求 constituent checks 保留 symbol/kind allowlist、instrument identity hash、unknown/cash
  venue denial、USD/tradable/PRIIPs checks、included-only and no exclusion reason for included names。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_pit_universe_source_static.py tests/structure/test_docs_readme_index_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_pit_universe_source_static.py`：
  `8 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_pit_universe_acceptance -- --nocapture`：
  `7 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py -k 'ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles or ibkr_stock_etf_pm_checkpoint_numbers_are_linear'`：
  `2 passed, 5 deselected`。
- `git diff --check`（scoped to #127 files）：PASS。

## Boundary

未批准也未執行：runtime authority、IBKR contact、IBKR SDK import、secret access/creation、
connector runtime、socket/HTTP、market-data collection、evidence clock、scorecard writer、DB apply、
read probe execution、result import execution、paper order/cancel/replace、fill import、order route、
GUI fanout、tiny-live/live、或任何 Bybit behavior change。
