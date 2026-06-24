# Operator Note — Standing Demo Authorization Contract

日期：2026-06-24
狀態：`DONE_WITH_CONCERNS`

## 結論

你的「Demo API 全權授權」現在不需要每次用 broad language 重複問，但也不會被系統直接當作下單權限。

我把它收斂成一個可審計 contract：

- `standing_demo_operator_authorization_v1`
- 只能是 Demo / LiveDemo，不是 live/mainnet
- 必須再綁定到單一 candidate
- 必須有 max order cap 和 expiry
- 必須沒有 Cost Gate lowering、promotion proof、active runtime authority、writer、PG、Bybit、service mutation 訊號

這樣後續 Demo 經驗才可以 apply live：每一次 Demo probe 都能被重建成「誰授權、哪個 candidate、幾筆、到期時間、費用/滑點/成交 lineage、matched control」。

## 本輪沒有做的事

- 沒有下單
- 沒有 cancel/modify
- 沒有 live/mainnet
- 沒有 PG write
- 沒有 service restart
- 沒有啟 Rust writer
- 沒有降低 Cost Gate
- 沒有 promotion proof

Runtime 已同步到 `bdc1e156`，alpha artifact 顯示 expected-head `MATCH`，runtime/order authority、promotion、Cost Gate mutation 全是 false。

## 下一步

下一個安全 checkpoint 不是直接下單，而是為 exactly one candidate 產生 structured standing Demo authorization artifact。最可能候選仍是 false-negative path：

`grid_trading|AVAXUSDT|Sell`

只有在該 artifact 通過 candidate-scope、budget、TTL、lineage、fee/slippage、control 條件後，才可進入 runtime admission / bounded Demo probe 路徑。
