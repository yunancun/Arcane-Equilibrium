# PM Report — Stock/ETF Disable Cleanup Runbook Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：Stock/ETF disable-cleanup runbook source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`stock_etf_disable_cleanup_runbook.rs` 的 source-only 姿態；不是 service stop、不是 env
mutation、不是 secret inspection、不是 DB cleanup、不是 IBKR contact、不是 paper order、不是
launch authorization。

## Completed

- 新增 `tests/structure/test_stock_etf_disable_cleanup_runbook_source_static.py`。
- Guard 要求 `stock_etf_disable_cleanup_runbook.rs` 低於 800 行 governance cap。
- Guard 要求 exact `stock_etf_kill_switch_and_disable_cleanup_runbook_v1` runbook id、
  required env flag values、required proof kinds、contract/verdict/blocker surface 保持在 source
  中。
- Guard 允許固定 `OPENCLAW_*` disable flag 字面量，但禁止任何 env/fs/network/IBKR SDK/clock/
  thread/process/order/Bybit runtime token。
- Guard 要求 default runbook fail-closed：CryptoPerp/Bybit placeholder、Bybit live unchanged
  proof missing、no launch authority、empty env/proof vectors。
- Guard 要求 accepted fixture 保留 StockEtfCash/IBKR、Bybit live unchanged true、IBKR contact/
  connector runtime/paper order/secret/destructive DB cleanup/tiny-live/live 全部 false。
- Guard 要求 env/proof validation 保留 missing/duplicated/unexpected checks、expected/observed
  value checks、evidence hash checks、proof verified/runtime-authority/destructive-cleanup checks。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_disable_cleanup_runbook_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_disable_cleanup_runbook_source_static.py`：
  `7 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_disable_cleanup_runbook_acceptance -- --nocapture`：
  `7 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py -k 'ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles or ibkr_stock_etf_pm_checkpoint_numbers_are_linear'`：
  `2 passed, 5 deselected`。
- `git diff --check`（scoped to #122 files）：PASS。

## Boundary

未批准也未執行：runtime authority、IBKR contact、IBKR SDK import、secret access/creation/
inspection、connector runtime、socket/HTTP、read probe、result import、collector、market-data
ingestion、DQ writer、paper order/cancel/replace、fill import、service stop、env mutation、
destructive DB cleanup、DB delete/truncate、audit writer、evidence writer/clock、GUI fanout、
paper-shadow launch、tiny-live/live、或任何 Bybit behavior change。
