# Stock/ETF DB Evidence DDL Exact Blocker Guard

日期：2026-07-01
角色：PM(default)
範圍：IBKR `stock_etf_cash` DB evidence DDL source-auditor acceptance hardening

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 補強 `StockEtfDbEvidenceDdl` source SQL auditor mutation cases 的 exact blocker coverage。它只改
acceptance guard，不改 Rust production validator、source-only SQL draft、migration registry、API/IPC route、
GUI runtime、connector、secret、DB、IBKR runtime 或 Bybit 行為。

## Scope

已完成：

- 在 `stock_etf_db_evidence_ddl_acceptance.rs` 將 source SQL auditor 的 required-column drift cases 改成 exact
  single-blocker vectors。
- 將 required foreign-key drift、synthetic-shadow check drift、destructive statement injection、migration dry-run
  text drift、guard B/C drift、hypertable/retention-plan drift 改成 exact single-blocker vectors。
- 移除 DB evidence DDL acceptance 中 loose `has_source_blocker()` / `.contains()` helper usage。
- 保持既有 `test_stock_etf_db_evidence_ddl_source_static.py` source-order guard；本 checkpoint 不改 production
  source validator 或 source-only SQL draft。

## Verification

- No DB evidence DDL source-auditor `.contains()` scan：PASS。
- Targeted rustfmt check：PASS。
- Stock/ETF DB evidence DDL source static pytest：`7 passed`。
- Stock/ETF DB evidence DDL Rust acceptance：`10 passed`。
- Full `cargo test -p openclaw_types --quiet`：PASS。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- `git diff --check`：PASS。

## Boundary

未做也未授權：

- Rust production code change。
- source-only SQL draft behavior change。
- sql/migrations copy or sqlx migration registration。
- Postgres open/write/apply/dry-run execution。
- API/IPC route behavior change。
- GUI runtime or view authority change。
- IBKR contact、IBKR SDK import、socket/client construction。
- secret access/creation/serialization。
- connector runtime、broker session、read-only probe execution、fill import execution。
- paper order routing/cancel/replace execution。
- evidence writer、scorecard writer、DB apply。
- paper-shadow launch、release launch、tiny-live/live authorization。
- Linux runtime sync/restart。
- Bybit live/demo execution 行為變更。
