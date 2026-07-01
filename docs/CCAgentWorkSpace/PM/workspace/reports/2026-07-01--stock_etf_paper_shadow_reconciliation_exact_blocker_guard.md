# Stock/ETF Paper Shadow Reconciliation Exact Blocker Guard

日期：2026-07-01
角色：PM(default)
範圍：IBKR `stock_etf_cash` paper/shadow source-only acceptance hardening

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 補強 `StockEtfPaperShadowReconciliationV1` paper-shadow reconciliation contract 的 aggregate
fail-closed coverage。它只改測試與 source-static guard，不改 Rust production validator、IPC、API route、
GUI runtime、connector、secret、DB 或 Bybit 行為。

## Scope

已完成：

- 在 `stock_etf_paper_shadow_reconciliation_acceptance.rs` 將 default reconciliation contract 固定為完整
  ordered blocker vector，覆蓋 contract/source identity、lane/broker/scope/authority、reconciliation run、
  paper order / broker order / execution / commission / shadow-signal ids、all lineage hashes 與 base
  reconciliation evidence gates。
- 將 scope/AuthorityScope/effect cross-wire、lineage/hash aggregate、unmatched/divergent evidence aggregate、
  no-side-effect boundary regression cases 改成 exact ordered vectors。
- 移除 reconciliation blocker 的 loose `has()` / `blockers.contains` helper；aggregate cases 現在會對
  missing、extra、duplicated 或 reordered blockers fail deterministically。
- 在 `test_stock_etf_paper_shadow_reconciliation_source_static.py` 補 validator blocker emit-order guard，pin
  top-level、required fields、reconciliation evidence 與 boundary flags 的 source order。

## Verification

- Targeted rustfmt check：PASS。
- Stock/ETF paper-shadow reconciliation source static pytest：`10 passed`。
- Stock/ETF paper-shadow reconciliation Rust acceptance：`10 passed`。
- Full `cargo test -p openclaw_types --quiet`：PASS。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- `git diff --check`：PASS。

## Boundary

未做也未授權：

- Rust production code change。
- IPC/API route behavior change。
- GUI runtime or lane selector authority change。
- IBKR contact、IBKR SDK import、socket/client construction。
- secret access/creation/serialization。
- connector runtime、broker session、paper order routing/cancel/replace execution。
- lifecycle writer、fill import execution、shadow fill generation、reconciliation writer、scorecard writer。
- DB/evidence writer、evidence clock、paper-shadow launch、release launch、tiny-live/live authorization。
- Linux runtime sync/restart。
- Bybit live/demo execution 行為變更。
