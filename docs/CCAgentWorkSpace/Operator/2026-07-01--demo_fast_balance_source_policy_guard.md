# Demo Fast-Balance Source Policy Guard

已完成一個 source/test checkpoint，目標是解除前一輪 BB 阻擋的兩個可機器檢查條件。

- fast-balance equity artifact capture 現在可用 `--forbid-env-token` 強制禁止 `OPENCLAW_API_TOKEN` fallback；若 env token 存在，會在發出 Control API GET 前 fail-closed。
- artifact 會記錄 token source、env-token policy、token-file mode/path metadata，但不輸出 token value/hash/prefix/suffix。
- Control API `GET /api/v1/strategy/demo/balance?fast=1` 在 Rust Demo snapshot 缺失時不再 fall back 到 Bybit wallet REST；它會回 `rust_snapshot_fast` + `snapshot_unavailable` 的 non-ready payload。

驗證通過：helper focused tests `13 passed`、GUI fast snapshot tests `8 passed`、py_compile、diff-check；E2/E4 read-only review 沒有 blocking finding，E4 提出的 CLI/redaction 測試缺口已補。這輪沒有做 runtime/exchange action，沒有 Control API GET、public quote、Decision Lease、order、PG write、service/env/risk mutation、Cost Gate change、live/mainnet、fill/PnL/proof。

下一步仍是 `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD`：用最新 source 重新產生 exact E3/BB runtime-refresh request，並在 request 中使用新的 `--forbid-env-token` contract。runtime standing envelope 仍需 fresh E3/BB 後才能刷新；目前 expired envelope 不授權 probe/order。
