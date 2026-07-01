# PM Report — Stock/ETF Paper Order Fixture Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：Stock/ETF paper order accepted fixture source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`stock_etf_paper_order_request/fixtures.rs` 的 accepted preview/submit/cancel/replace source-only
fixture shape；不是 paper order route、不是 paper submit/cancel/replace execution、不是 IBKR
contact、不是 connector runtime、不是 secret access。

## Completed

- 新增 `tests/structure/test_stock_etf_paper_order_request_fixtures_source_static.py`。
- Guard 要求 `stock_etf_paper_order_request/fixtures.rs` 低於 400 行 governance cap。
- Guard 要求 fixture module 保留 accepted preview/submit/cancel/replace fixture functions、paper
  order request contract id、lane-scoped IPC methods、broker operations、authority scopes、
  instrument/order/price/TIF enums。
- Guard 要求 preview fixture 保留 StockEtfCash/IBKR/Paper、PreviewPaperOrder、PaperOrderSubmit、
  ReadOnly authority、SPY ETF buy limit DAY shape、risk/instrument/cost/PIT/source hashes、effect
  fields absent via default。
- Guard 要求 submit fixture 保留 SubmitPaperOrder、PaperRehearsal、effect_capable=true、
  session/scoped/decision/guardian/lifecycle/broker-registry/audit lineage、local order id、
  idempotency key、preview-only source hashes cleared。
- Guard 要求 cancel fixture 保留 CancelPaperOrder、PaperOrderCancel、PaperRehearsal、broker order id
  and cancel reason。
- Guard 要求 replace fixture 保留 ReplacePaperOrder、PaperOrderReplace、replacement idempotency/
  quantity/limit-price/TIF/reason fields while clearing original submit/cancel fields。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_paper_order_request_fixtures_source_static.py tests/structure/test_docs_readme_index_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_paper_order_request_fixtures_source_static.py`：
  `6 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_paper_order_request_acceptance -- --nocapture`：
  `8 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py -k 'ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles or ibkr_stock_etf_pm_checkpoint_numbers_are_linear'`：
  `2 passed, 5 deselected`。
- `git diff --check`（scoped to #131 files）：PASS。

## Boundary

未批准也未執行：runtime authority、IBKR contact、IBKR SDK import、secret access/creation、
connector runtime、socket/HTTP、paper order route、paper submit/cancel/replace execution、
market-data ingest、evidence clock、scorecard writer、DB apply、read probe execution、result import
execution、GUI fanout、tiny-live/live、或任何 Bybit behavior change。
