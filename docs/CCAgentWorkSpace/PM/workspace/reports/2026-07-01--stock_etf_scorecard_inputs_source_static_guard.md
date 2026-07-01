# PM Report — Stock/ETF Scorecard Inputs Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：Stock/ETF scorecard input source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住 split
`stock_etf_scorecard_inputs` parent/components/bundle modules 的 source-only 姿態；
不是 IBKR contact、不是 broker fill import、不是 scorecard derivation/writer、不是
DB apply、不是 evidence clock。

## Completed

- 新增 `tests/structure/test_stock_etf_scorecard_inputs_source_static.py`。
- Guard 要求 parent、components、bundle 三檔各自低於 800 行 governance cap。
- Guard 要求 cash ledger、cost model、benchmark、shadow fill model、storage capacity
  contract ids 與 storage caps/retention/query-SLO/archive path prefix 保持在 parent source。
- Guard 要求 cash ledger 仍限制 StockEtfCash/IBKR 且只接受 Paper/ReadOnly，並保留 account、
  snapshot、positions、currency、as-of、source-report checks。
- Guard 要求 cost/benchmark validators、shadow fill synthetic marker、broker paper fill/live
  fill separation、storage universe/rows/index/query-SLO caps、raw/compressed retention order、
  safe lane-scoped archive path、capacity-plan hash、capacity breach blocks evidence clock policy
  不得消失。
- Guard 要求 bundle accepted fixture 仍由 cash ledger/cost/benchmark/shadow fill/storage
  accepted fixtures 組成，並保持 readonly probe result import contract id、scorecard
  derived-only、paper/shadow fills separate、live fill false、Bybit live execution unchanged。
- Guard 要求 bundle validation 保留 sub-validator rejection、cross-contract hashes、source
  commit、derived-only、paper-shadow separation、live fill denial、Bybit live protection、IBKR
  contact、connector runtime、broker fill import、scorecard writer、DB apply、evidence clock、
  secret serialization、live/tiny-live boundary flags。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_scorecard_inputs_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_scorecard_inputs_source_static.py`：
  `7 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_scorecard_inputs_acceptance -- --nocapture`：
  `12 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。

## Boundary

未批准也未執行：IBKR contact、IBKR SDK import、secret access/creation、connector
runtime、socket/HTTP、read probe、result import、collector、market-data ingestion、DQ writer、
paper order/cancel/replace、broker fill import、scorecard derivation/write、DB apply、
evidence writer/clock、GUI fanout、tiny-live/live、或任何 Bybit behavior change。
