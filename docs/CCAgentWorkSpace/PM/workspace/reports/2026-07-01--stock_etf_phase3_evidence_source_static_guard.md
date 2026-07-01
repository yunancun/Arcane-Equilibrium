# PM Report — Stock/ETF Phase3 Evidence Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：Stock/ETF Phase3 evidence parent and market-data child source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`stock_etf_phase3_evidence.rs` 與 `stock_etf_phase3_evidence/market_data.rs` 的 source-only
姿態；不是 market-data ingest、不是 evidence clock runtime、不是 DQ/evidence/scorecard writer、
不是 DB apply、不是 IBKR contact、不是 connector runtime。

## Completed

- 新增 `tests/structure/test_stock_etf_phase3_evidence_source_static.py`。
- Guard 要求 parent 低於 800 行、market-data child 低於 500 行 governance cap。
- Guard 要求 parent 保留 collector run、DQ manifest、evidence clock、verdict/blocker surface、
  market-data child module/re-export、Phase3 contract ids、5-day green minimum。
- Guard 要求 child 保留 market-data provenance、adjustment marker、frozen evidence inputs、
  source fixtures、validation helpers、hash checks。
- Guard 要求 collector run 保留 PIT universe、market-data provenance、reference data sources、
  storage-capacity lineage hashes、gap/DQ/replay/source hashes、5 green sessions、no ingestion/
  writer/DB/secret/live flags。
- Guard 要求 DQ manifest 保留 named market-data provenance lineage、shape-vs-quality split、
  10000 bps coverage/completeness, latency/provenance/scorecard-regeneration gates, no DQ writer/
  evidence clock/scorecard/DB/runtime flags。
- Guard 要求 evidence clock day 保留 collector/DQ/source/market-data/scorecard-input lineage,
  frozen inputs, DQ manifest, connector/shadow 5-day gates, PassDay/QuarantinedDay/WindowComplete
  status rules, and no checker runtime/write/DB/live authority。
- Guard 要求 market-data provenance 保留 source vendor, entitlement tier, raw payload hash,
  timestamps, adjustment marker, corporate action hash, symbol, instrument identity, calendar session,
  source artifact, Bybit protection, no contact/runtime/secret/live authority。
- Guard 要求 frozen inputs 保留 universe/benchmark/cost/strategy/reference/divergence hashes,
  corporate-action/FX/fee as-of, GUI evidence view, scorecard regeneration readiness。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_phase3_evidence_source_static.py tests/structure/test_docs_readme_index_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_phase3_evidence_source_static.py`：
  `10 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_phase3_evidence_acceptance -- --nocapture`：
  `19 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py -k 'ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles or ibkr_stock_etf_pm_checkpoint_numbers_are_linear'`：
  `2 passed, 5 deselected`。
- `git diff --check`（scoped to #130 files）：PASS。

## Boundary

未批准也未執行：runtime authority、IBKR contact、IBKR SDK import、secret access/creation、
connector runtime、socket/HTTP、market-data ingest、collector runtime、DQ writer、evidence clock
runtime、evidence writer、scorecard writer、DB apply、read probe execution、result import execution、
paper order/cancel/replace、fill import、order route、GUI fanout、tiny-live/live、或任何 Bybit
behavior change。
