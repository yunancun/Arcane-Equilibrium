# Stock/ETF Data Foundation Exact Blocker Guard

日期：2026-07-01
角色：PM(default)
範圍：IBKR `stock_etf_cash` data foundation source-only acceptance hardening

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 補強 Stock/ETF 上游資料基礎 contracts 的 aggregate fail-closed coverage。它只改 acceptance 與
source-static guard，不改 Rust production validator、API/IPC route、GUI runtime、connector、secret、DB、IBKR
runtime 或 Bybit 行為。

## Scope

已完成：

- 在 `stock_etf_instrument_identity_acceptance.rs` 將 default identity、contract/source drift、kind/symbol/venue/
  currency aggregate、tradability/PRIIPs/hash aggregate、authority/boundary regressions 改成 exact ordered blocker
  vectors 或 exact single-blocker vectors。
- 在 `stock_etf_pit_universe_acceptance.rs` 將 default PIT universe、identity/window drift、bad constituent/count
  shape、required hash/freeze/survivorship/boundary aggregate 改成 exact ordered blocker vectors 或 exact
  single-blocker vectors。
- 在 `stock_etf_reference_data_sources_acceptance.rs` 將 default reference-data sources、contract/source drift、
  corporate-action/FX/fee-tax source gaps、environment/freeze/currency/runtime boundary aggregate 改成 exact
  ordered blocker vectors 或 exact single-blocker vectors。
- 移除三個 acceptance 檔中的 loose blocker `has()` / `.contains()` aggregate helper usage。
- 在三個 source-static tests 新增 validator blocker emit-order guard，pin identity/cash-venue、PIT top-level/
  constituent/hash、reference-data corporate-action/FX/fee-tax validators 的 source order。

## Verification

- No data foundation blocker `.contains()` scan：PASS。
- Targeted rustfmt check：PASS。
- Stock/ETF data foundation source static pytest：`28 passed`。
- Stock/ETF data foundation Rust acceptance：`24 passed`。
- Full `cargo test -p openclaw_types --quiet`：PASS。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- `git diff --check`：PASS。

## Boundary

未做也未授權：

- Rust production code change。
- API/IPC route behavior change。
- GUI runtime or view authority change。
- IBKR contact、IBKR SDK import、socket/client construction。
- secret access/creation/serialization。
- connector runtime、broker session、read-only probe execution、data ingestion、fill import execution。
- paper order routing/cancel/replace execution。
- evidence writer、scorecard writer、DB apply。
- paper-shadow launch、release launch、tiny-live/live authorization。
- Linux runtime sync/restart。
- Bybit live/demo execution 行為變更。
