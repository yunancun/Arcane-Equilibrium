# PM Report — Stock/ETF Risk Policy Source Static Guard

日期：2026-07-01
角色：PM(default)
範圍：Stock/ETF cash risk-policy source guard。

## Verdict

`DONE_WITH_CONCERNS`

本 checkpoint 可接受。它只新增 structure/static regression，鎖住
`stock_etf_risk_policy.rs` 的 source-only 姿態；不是 risk policy runtime enablement、
不是 IBKR contact、不是 connector start、不是 paper order authorization。

## Completed

- 新增 `tests/structure/test_stock_etf_risk_policy_source_static.py`。
- Guard 要求 `stock_etf_risk_policy.rs` 低於 800 行 governance cap。
- Guard 要求 risk-policy contract id、source config structs、caps/cash-only/universe/
  cost-model/paper-order validators、hash helper 與 verdict/blocker surface 保持在
  source 中。
- Guard 要求 default 仍 fail-closed：CryptoPerp/Bybit、LiveReservedDenied、
  `enabled=true` 會被 blocker 擋住、`shadow_only=false`、margin/short/options/CFD/
  transfer/live all true、Bybit live protected false。
- Guard 要求 accepted fixture 仍為 StockEtfCash/IBKR Paper、`enabled=false`、
  `shadow_only=true`、cash-only、stock/ETF/cash allowed、CFD/crypto denied、Bybit live
  unchanged、no IBKR contact、no connector runtime、no secret serialization。
- Guard 要求 caps 維持 positive finite 與 order <= position <= daily ordering，
  max open orders/positions 上限檢查仍存在。
- Guard 要求 frozen universe、instrument identity、market session、commission、
  spread/slippage/FX/conservative penalty、Rust authority、session attestation、
  decision lease、guardian、idempotency key、broker reconciliation gates 不得消失。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

## Verification

- `python3 -B -m py_compile tests/structure/test_stock_etf_risk_policy_source_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_risk_policy_source_static.py`：
  `5 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_risk_policy_acceptance -- --nocapture`：
  `8 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。

## Boundary

未批准也未執行：IBKR contact、IBKR SDK import、secret access/creation、connector
runtime、socket/HTTP、read probe、result import、collector、market-data ingestion、
DQ writer、paper order/cancel/replace、fill import、DB apply、evidence writer/clock、
scorecard writer、GUI fanout、tiny-live/live、或任何 Bybit behavior change。
