# PM Report — Stock/ETF GUI Lane Contract Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：Stock/ETF GUI lane contract source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`stock_etf_gui_lane_contract.rs` 的 source-only 姿態；不是 GUI write surface、不是 lane
selection authority、不是 IBKR contact、不是 secret/order widget、不是 runtime route。

## Completed

- 新增 `tests/structure/test_stock_etf_gui_lane_contract_source_static.py`。
- Guard 要求 `stock_etf_gui_lane_contract.rs` 低於 800 行 governance cap。
- Guard 要求 exact `gui_lane_contract_v1` contract id、16 個 Stock/ETF GET-only endpoint
  constants/path、contract/verdict/blocker surface 保持在 source 中。
- Guard 要求 default contract fail-closed：CryptoPerp default、Stock/ETF tab missing、endpoints
  empty/not GET-only、display-only/client-state-untrusted/authority-denial flags 全部 false。
- Guard 要求 accepted fixture 保留 display-only、client lane state untrusted、localStorage/query/
  hidden-field authority denied、no login-success selector、no POST route、no order/secret widget、
  no render-time IBKR contact、paper order entry hidden、stock live disabled display、CFD hidden。
- Guard 要求 route/auth/cache partition、crypto tab regression、Decision Lease risk regression、
  static/route/crypto hashes、live-order/secret-slot/pre-gate-contact denials 保持 required。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_gui_lane_contract_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_gui_lane_contract_source_static.py`：
  `6 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_gui_lane_contract_acceptance -- --nocapture`：
  `9 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py -k 'ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles or ibkr_stock_etf_pm_checkpoint_numbers_are_linear'`：
  `2 passed, 5 deselected`。
- `git diff --check`（scoped to #123 files）：PASS。

## Boundary

未批准也未執行：runtime authority、IBKR contact、IBKR SDK import、secret access/creation、
connector runtime、socket/HTTP、read probe、result import、collector、market-data ingestion、
DQ writer、paper order/cancel/replace、fill import、GUI write surface、lane selection authority、
POST route、order widget、secret widget、audit writer、DB apply、evidence writer/clock、
tiny-live/live、或任何 Bybit behavior change。
