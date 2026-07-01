# Stock/ETF Phase3 Evidence Exact Blocker Guard

日期：2026-07-01
角色：PM(default)
範圍：IBKR `stock_etf_cash` Phase3 evidence source-only acceptance hardening

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 補強 `StockEtfPhase3` evidence contracts 的 aggregate fail-closed coverage。它只改 acceptance 與
source-static guard，不改 Rust production validator、collector runtime、evidence clock runtime、API/IPC route、
GUI runtime、connector、secret、DB 或 Bybit 行為。

## Scope

已完成：

- 在 `stock_etf_phase3_evidence_acceptance.rs` 將 market-data provenance 的 contract/source drift 與 boundary
  regressions 改成 exact ordered blocker vectors。
- 將 frozen evidence inputs 的 reference-data lineage gap 改成 exact single-blocker assertion。
- 將 collector run 的 lineage aggregate 與 runtime side-effect aggregate 改成 exact ordered blocker vectors。
- 將 evidence-clock pass-day gate/status regressions、contract/lineage drift、checker side effects 改成 exact
  ordered blocker vectors 或 exact single-blocker vectors。
- 將 DQ manifest runtime side-effect aggregate 改成 exact ordered blocker vector。
- 在 `test_stock_etf_phase3_evidence_source_static.py` 擴充 validator blocker emit-order guard，pin market-data
  provenance、frozen inputs、collector run、DQ manifest、evidence-clock validators 的 lineage、side-effect 與 status
  blocker order。

## Verification

- No Phase3 blocker `.contains()` scan：PASS。
- Targeted rustfmt check：PASS。
- Stock/ETF Phase3 evidence source static pytest：`16 passed`。
- Stock/ETF Phase3 evidence Rust acceptance：`24 passed`。
- Full `cargo test -p openclaw_types --quiet`：PASS。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- `git diff --check`：PASS。

## Boundary

未做也未授權：

- Rust production code change。
- market-data ingestion or collector runtime startup。
- evidence clock runtime startup。
- IPC/API route behavior change。
- GUI runtime or evidence-view authority change。
- IBKR contact、IBKR SDK import、socket/client construction。
- secret access/creation/serialization。
- connector runtime、broker session、read-only probe execution、fill import execution。
- paper order routing/cancel/replace execution。
- evidence writer、scorecard writer、DB apply。
- paper-shadow launch、release launch、tiny-live/live authorization。
- Linux runtime sync/restart。
- Bybit live/demo execution 行為變更。
