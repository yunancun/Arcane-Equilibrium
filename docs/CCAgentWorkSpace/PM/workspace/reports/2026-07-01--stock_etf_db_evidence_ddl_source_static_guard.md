# PM Report — Stock/ETF DB Evidence DDL Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：Stock/ETF DB evidence DDL source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`stock_etf_db_evidence_ddl.rs` 的 source-only 姿態；不是 migration apply、不是 PG write、
不是 sqlx registration、不是 DB runtime、不是 IBKR contact、不是 paper order、不是 evidence
clock。

## Completed

- 新增 `tests/structure/test_stock_etf_db_evidence_ddl_source_static.py`。
- Guard 要求 `stock_etf_db_evidence_ddl.rs` 低於 800 行 governance cap。
- Guard 要求 exact `stock_etf_db_evidence_ddl_v1` contract id、source-only SQL path、
  required schemas/tables/natural keys、contract/verdict/blocker/source-audit surface 保持在
  source 中。
- Guard 要求 accepted fixture 維持 source-only：不複製到 `sql/migrations/`、不做 DB apply、
  不做 PG write、不註冊 sqlx migration、不宣稱 PM/Operator apply authorization。
- Guard 要求 E2/E4 review、Linux PG dry-run、double-apply、Guard A/B/C、stock asset-lane
  check、IBKR broker check、live denial、paper-shadow table separation、synthetic shadow check、
  audit event table、forward-only retention、destructive rollback denial 保持 required。
- Guard 要求 source SQL auditor 保留 source-only banner、migration/apply denial、destructive
  SQL denial、schema/table/column/natural-key/FK checks、stock/IBKR/paper/live checks、raw hash、
  append-only audit event、hypertable/retention plan、hot-path index checks。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_db_evidence_ddl_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_db_evidence_ddl_source_static.py`：
  `6 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_db_evidence_ddl_acceptance -- --nocapture`：
  `10 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py -k 'ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles or ibkr_stock_etf_pm_checkpoint_numbers_are_linear'`：
  `2 passed, 5 deselected`。
- `git diff --check`（scoped to #121 files）：PASS。

## Boundary

未批准也未執行：runtime authority、IBKR contact、IBKR SDK import、secret access/creation、
connector runtime、socket/HTTP、read probe、result import、collector、market-data ingestion、
DQ writer、paper order/cancel/replace、fill import、migration apply、PG write/dry-run、sqlx
registration、DB runtime、audit writer、evidence writer/clock、GUI fanout、tiny-live/live、或任何
Bybit behavior change。
