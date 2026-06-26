# Operator Brief - Private Fee-Tier Read Envelope E3/BB Review No-Read

本輪只做 review + source hardening，沒有執行 private fee read。

- 完成：E3/BB review 後，將 future fee-rate envelope 收窄為 `GET /v5/account/fee-rate?category=linear&symbol=AVAXUSDT`，且 sanitized artifact 只允許保存 exact candidate fee row，不保存 cross-symbol fee rows。
- 完成：新增 strict parser policy；未來 `makerFeeRate` / `takerFeeRate` missing、malformed、NaN、infinite 都是 no-proof，不能被當成 0 fee 或 rebate。
- 完成：明確 one-symbol fee artifact 是 standalone proof artifact only，不得替換 Rust `AccountManager` broad fee cache，也不得滿足 live fee-rate count assertion。
- 驗證：focused `10 passed`；adjacent suite `29 passed`；`py_compile` 和 `git diff --check` passed；hardened smoke artifact sha `c1081ff412fd1e855b8a6ff4856734789e6c9e862ed8124330c48f87e77c165b`，status `PRIVATE_FEE_TIER_READ_ENVELOPE_READY_NO_READ`。
- 邊界：沒有 credential load、沒有 Bybit account API call、沒有 PG query/write、沒有 order/cancel/modify、沒有 runtime/service/env/crontab mutation、沒有降低 Cost Gate/freshness gate、沒有授權 probe/order/live、沒有宣稱 profit/proof。

當前停止點：P0 authorization 仍 blocked。actual private fee read 仍是 separate runtime/exchange-facing action；除非後續明確開一個 one-shot runtime read checkpoint，否則不得執行。
