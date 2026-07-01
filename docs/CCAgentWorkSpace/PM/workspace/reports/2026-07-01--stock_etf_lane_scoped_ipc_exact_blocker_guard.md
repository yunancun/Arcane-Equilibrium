# Stock/ETF Lane-Scoped IPC Exact Blocker Guard

日期：2026-07-01
角色：PM(default)
範圍：IBKR `stock_etf_cash` read-only/paper/shadow source-only acceptance hardening

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 補強 `StockEtfLaneScopedIpcContractV1` source-only lane-scoped IPC contract 的 aggregate
fail-closed coverage。它只改 acceptance 與 source-static guard，不改 Rust production validator、IPC runtime、
API route、GUI runtime、connector、secret、DB 或 Bybit 行為。

## Scope

已完成：

- 在 `stock_etf_lane_scoped_ipc_acceptance.rs` 將 default lane-scoped IPC contract 固定為完整 ordered blocker
  vector，覆蓋 contract/source identity、Stock/ETF lane、IBKR broker、Rust authority owner、Python forward-only、
  direct broker write denial、Bybit IPC reuse denial、existing Bybit paper path denial、live environment denial、
  Bybit live unchanged proof，以及 20 個 required IPC methods 的 missing blockers。
- 將 top-level boundary regressions、exact contract/source mismatch、command coverage once-only、denied/unknown method
  aggregate、paper-effect command shape failures、paper-order request-shape cross-wire cases 改成 exact ordered
  vectors 或 exact single-blocker vectors。
- 移除 lane-scoped IPC blocker 的 loose `has()` / `blockers.contains` helper；aggregate cases 現在會對 missing、
  extra、duplicated 或 reordered blockers fail deterministically。
- 在 `test_stock_etf_lane_scoped_ipc_source_static.py` 補 validator blocker emit-order guard，pin top-level IPC
  contract flags、denied/missing/duplicated command checks，以及 command shape validation 的 source order。

## Verification

- Targeted rustfmt check：PASS。
- Stock/ETF lane-scoped IPC source static pytest：`7 passed`。
- Stock/ETF lane-scoped IPC Rust acceptance：`12 passed`。
- Full `cargo test -p openclaw_types --quiet`：PASS。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- `git diff --check`：PASS。

## Boundary

未做也未授權：

- Rust production code change。
- IPC runtime/server startup。
- IPC/API route behavior change。
- GUI runtime or lane selector authority change。
- IBKR contact、IBKR SDK import、socket/client construction。
- secret access/creation/serialization。
- connector runtime、broker session、read-only probe execution、result/fill import execution。
- paper order routing/cancel/replace execution。
- evidence writer、scorecard writer、DB apply。
- paper-shadow launch、release launch、tiny-live/live authorization。
- Linux runtime sync/restart。
- Bybit live/demo execution 行為變更。
