# PM Report — Stock/ETF Instrument Identity Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：Stock/ETF instrument identity source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`stock_etf_instrument_identity.rs` 的 source-only 姿態；不是 IBKR contract-details call、不是
market-data subscription、不是 connector runtime、不是 secret access、不是 paper order、不是
evidence/scorecard writer、不是 DB apply。

## Completed

- 新增 `tests/structure/test_stock_etf_instrument_identity_source_static.py`。
- Guard 要求 `stock_etf_instrument_identity.rs` 低於 800 行 governance cap。
- Guard 要求 exact `instrument_identity_contract_v1` contract id、identity fields、listing
  venue/currency/tradability/PRIIPs enums、verdict/blocker surface、cash venue helper、symbol helper
  保持在 source 中。
- Guard 要求 default identity fail-closed：CryptoPerp/Bybit、CryptoPerp instrument kind、empty
  symbol、UnknownDenied venue/currency/tradability/PRIIPs、missing PIT/as-of/hash lineage、Bybit live
  unchanged false、IBKR live/margin/options-CFD denial flags false。
- Guard 要求 accepted fixture 保留 StockEtfCash/IBKR、Stock、`AMD`、XNAS listing/primary exchange、
  USD、Tradable、PRIIPs NotRequired、fractional policy recorded、PIT as-of、market calendar、
  broker contract-details、identity、corporate-action-adjustment、source artifact hashes。
- Guard 要求 validation matrix 保留 contract/version/lane/broker checks、Stock/ETF/Cash-only kind
  allowlist、symbol validator、venue/primary exchange denial、cash/non-cash venue separation、USD-only、
  tradable-only、PRIIPs missing/unknown denial、fractional/PIT/market calendar/hash lineage checks。
- Guard 要求 boundary flags 保留 Bybit live protected、IBKR live denied、margin/short denied、
  options/CFD denied、no IBKR contact、no secret serialization。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_instrument_identity_source_static.py tests/structure/test_docs_readme_index_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_instrument_identity_source_static.py`：
  `7 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_instrument_identity_acceptance -- --nocapture`：
  `8 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py -k 'ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles or ibkr_stock_etf_pm_checkpoint_numbers_are_linear'`：
  `2 passed, 5 deselected`。
- `git diff --check`（scoped to #126 files）：PASS。

## Boundary

未批准也未執行：runtime authority、IBKR contact、IBKR SDK import、contract-details call、
market-data subscription、secret access/creation、connector runtime、socket/HTTP、read probe
execution、result import execution、paper order/cancel/replace、fill import、order route、evidence
writer/clock、scorecard writer、DB apply、GUI fanout、tiny-live/live、或任何 Bybit behavior change。
