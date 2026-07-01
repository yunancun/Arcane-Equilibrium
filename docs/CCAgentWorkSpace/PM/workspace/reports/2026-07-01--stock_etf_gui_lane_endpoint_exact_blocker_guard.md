# Stock/ETF GUI Lane Endpoint Exact Blocker Guard

日期：2026-07-01
角色：PM(default)
範圍：IBKR `stock_etf_cash` GUI lane source-only endpoint acceptance hardening

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 補強 `StockEtfGuiLaneContractV1` read-only endpoint aggregate fail-closed coverage。它只改
acceptance guard，不改 Rust production validator、GUI runtime、API/IPC route、connector、secret、DB、IBKR runtime
或 Bybit 行為。

## Scope

已完成：

- 在 `stock_etf_gui_lane_contract_acceptance.rs` 將 all Stock/ETF read-only status endpoint mismatch / not-GET-only
  aggregate 改成完整 exact ordered blocker vector。
- 移除該 test 中 32 個 loose `verdict.blockers.contains(...)` membership assertions。
- 保持既有 `test_stock_etf_gui_lane_contract_source_static.py` source-order guard；本 checkpoint 不改 production
  source validator。
- 本輪全域掃描已確認 Stock/ETF acceptance/static blocker guard 不再有 broad `.contains()` blocker membership。

## Verification

- Global loose blocker scan：PASS。
- Targeted rustfmt check：PASS。
- Stock/ETF GUI lane source static pytest：`7 passed`。
- Stock/ETF GUI lane Rust acceptance：`9 passed`。
- Full `cargo test -p openclaw_types --quiet`：PASS。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- `git diff --check`：PASS。

## Boundary

未做也未授權：

- Rust production code change。
- GUI runtime/API/IPC route behavior change。
- endpoint implementation or server startup。
- IBKR contact、IBKR SDK import、socket/client construction。
- secret access/creation/serialization。
- connector runtime、broker session、read-only probe execution、fill import execution。
- paper order routing/cancel/replace execution。
- evidence writer、scorecard writer、DB apply。
- paper-shadow launch、release launch、tiny-live/live authorization。
- Linux runtime sync/restart。
- Bybit live/demo execution 行為變更。
