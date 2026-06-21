# Cost-Gate Materializer Cron Wiring

## 結論

現在 learning loop 的 source 已經能按順序做完整 artifact 閉環：

PG rejects -> materialized ledger rows -> blocked-signal markout -> blocked-outcome review

這是向「demo 自主學習」更實際的一步：不再只看 aggregate ranking，而是讓已記錄的 Cost Gate reject 進入逐條 outcome evidence pipeline。

## 尚未做的事

本次仍沒有在 runtime 安裝或啟用 cron，也沒有 append ledger。這是 source-level wiring checkpoint。

真正要開始累積 evidence，下一步需要 operator-reviewed runtime activation/sync：

- runtime source sync 到包含本 commit
- 安裝或手動運行 `cost_gate_learning_lane_cron.sh`
- 觀察 `reject_materializer_latest.json`
- 觀察 `probe_ledger.jsonl`
- 觀察 `blocked_outcome_review_latest.json`

## 邊界

沒有：

- 下單
- 授權 demo/live order
- 降低 main Cost Gate
- 寫 PG
- 連 Bybit private/signed/trading API
- 啟用 Rust writer
- runtime deploy / rebuild / restart
- cron install

## 驗證

- Cron static tests：9 passed
- Learning-lane policy tests：58 passed
- Alpha/counterfactual adjacent tests：42 passed
- Python compile：PASS
- Bash syntax：PASS
- Diff whitespace：PASS
