# PM Checkpoint Report — IBKR Stock/ETF Collector Run Contract

Date: 2026-07-01

## Verdict

PM SIGN-OFF: APPROVED for source-only checkpoint.

This checkpoint adds `stock_etf_collector_run_v1` as a Phase 3 source-only
collector run manifest contract. It does not approve collector runtime,
market-data ingestion, evidence writer, scorecard writer, DB apply, IBKR contact,
paper orders, tiny-live, or live.

## Scope

- Added `StockEtfCollectorRunV1` to `openclaw_types`.
- Raised Phase0 named contracts from 33 to 34 and added the contract to the
  repository manifest/spec packet.
- Added default-blocked `[collector_run]` to the Phase 3 evidence template.
- Exposed default-blocked `collector_run` through existing
  `stock_etf.get_evidence_status`, FastAPI evidence normalization/fallbacks, and
  the GUI evidence panel.
- No new FastAPI endpoint, IPC method, GUI fanout, background work, connector
  import, runtime process, or Linux sync/restart was added.

## Acceptance

The validator requires exact identity and lineage before a future source
artifact can be accepted:

- contract id `stock_etf_collector_run_v1`
- source version 1
- `stock_etf_cash` / IBKR / paper-shadow lane binding
- collector run id and trading day
- at least 5 expected and completed green trading sessions
- PIT universe, market-data provenance, reference-data sources, storage
  capacity, gap report, DQ manifest, replay manifest, and source artifact hashes
- explicit false side-effect flags for IBKR contact, connector runtime,
  market-data ingestion, evidence writer, scorecard writer, DB apply, secret
  serialization, and tiny-live/live authority

## Verification

- `python3 -m py_compile ...` for changed Python files: PASS
- `node --check ...tab-stock-etf-evidence-paper.js ...tab-stock-etf-fallbacks.js`: PASS
- `rustfmt --edition 2021 --check ...`: PASS
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`: `120 passed`
- `cargo test -p openclaw_types`: `287` tests passed
- `cargo test -p openclaw_engine stock_etf -- --nocapture`: Stock/ETF target tests `31 passed`
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`: `2 passed`
- `git diff --check`: PASS

Known unrelated warnings during engine focused test:

- `openclaw_engine/src/live_auth_watcher_tests.rs` `ScriptedSpawn` visibility warning
- `openclaw_engine/tests/m3_emitter_replay_forbidden.rs` unused import warning

## Dispatch Note

Repository rule normally expects `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`
for feature/source-contract work. This desktop session did not expose a sub-agent
spawn tool, so PM completed the work locally and compensated with focused and
full regression coverage plus source-only boundary checks.

## Boundaries

No IBKR contact, IBKR SDK import, socket/HTTP, secret access/creation, connector
runtime, read probe execution, collector start, market-data ingestion, paper
order/cancel/replace, fill import, evidence writer, scorecard writer, DB apply,
evidence clock, Linux runtime sync/restart, tiny-live/live authority, or Bybit
behavior change occurred.
