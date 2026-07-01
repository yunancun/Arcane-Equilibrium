# PM Report — Stock/ETF Phase0 Manifest Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：Stock/ETF Phase0 manifest source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`stock_etf_phase0_manifest.rs` 的 source-only 姿態；不是 runtime authority、不是 IBKR
contact、不是 connector construction、不是 migration、不是 evidence clock、不是 order route。

## Completed

- 新增 `tests/structure/test_stock_etf_phase0_manifest_source_static.py`。
- Guard 要求 `stock_etf_phase0_manifest.rs` 低於 800 行 governance cap。
- Guard 要求 Phase0 manifest schema/status/scope/generated_at/ADR/AMD/packet paths、required
  contract set、manifest/authority/API baseline/global denials/unlock table/verdict/blocker surface
  保持在 source 中。
- Guard 要求 accepted manifest 仍是 StockEtfCash/IBKR/paper_shadow_only，並保留 authority、
  API baseline、global denials、contracts、phase unlock accepted fixtures。
- Guard 要求 API baseline 保持 `ib_gateway_tws_api`、`loopback_only`、paper port 4002、
  live ports denied、`ibkr_call_performed=false`。
- Guard 要求 global denials 保留 IBKR live、tiny-live、margin、short、options、CFD、transfer、
  account-management writes、Python broker write authority、GUI lane authority、automatic
  promotion 全部 denied。
- Guard 要求 phase unlock 保持 Phase1 只在 E2/E4/QA 後允許，Phase2 contact、Phase3 evidence
  clock、Phase4 GUI runtime、Phase5 online、tiny-live/live 全部 fail-closed。
- Guard 要求 required contract missing/duplicated/unexpected detection 不得消失。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_phase0_manifest_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_phase0_manifest_source_static.py`：
  `6 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_phase0_manifest_acceptance -- --nocapture`：
  `6 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py -k 'ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles or ibkr_stock_etf_pm_checkpoint_numbers_are_linear'`：
  `2 passed, 5 deselected`。
- `git diff --check`（scoped to #119 files）：PASS。

## Boundary

未批准也未執行：runtime authority、IBKR contact、IBKR SDK import、secret access/creation、
connector runtime、socket/HTTP、read probe、result import、collector、market-data ingestion、
DQ writer、paper order/cancel/replace、migration、DB apply、evidence writer/clock、GUI fanout、
tiny-live/live、或任何 Bybit behavior change。
