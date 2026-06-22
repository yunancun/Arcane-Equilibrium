# 2026-06-22 — Sealed Horizon Preflight Decision Resolver

## 結論

v394 修掉一個會誤導自主學習閉環的 latest-pointer 問題：如果 `profit_learning_decision_packet_latest.json` 還是舊 generic packet，preflight 現在可以用 `--decision-packet-search-root` 找到真正 aligned 的 sealed decision packet。

這不是 approval，也不會下單。它只避免系統因讀錯 artifact 而錯判「sealed decision packet 不對齊」。

## Linux Smoke

本次故意傳入舊 generic latest：

`/tmp/openclaw/profitability_refresh/20260622T031320Z/cost_gate_learning_lane/profit_learning_decision_packet_latest.json`

同時提供 search root：

`/tmp/openclaw/profitability_refresh/20260622T031320Z`

resolver 正確選中：

`/tmp/openclaw/profitability_refresh/20260622T031320Z/profit_learning_decision_packet_v389/profit_learning_decision_packet_v389_latest.json`

輸出 preflight：

`/tmp/openclaw/profitability_refresh/20260622T031320Z/preflight_resolver_v394/sealed_horizon_probe_preflight_latest.json`

結果：

- sha256：`6bd70df6c09753f1acf135990387968f655021f16cab94e514f699ebe3f7f8e9`
- status：`OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE_REQUIRED`
- `decision_packet_aligned=true`
- remaining gates：`operator_sealed_horizon_review_recorded`、`production_learning_lane_accumulating`

## 邊界

- 沒有降低 Cost Gate
- 沒有 probe/order authority
- 沒有 deploy/restart
- 沒有 PG write/schema migration
- 沒有 Bybit private/signed/trading call
- 沒有 promotion proof

## 下一步

這一步只修 artifact routing。真正往盈利走，下一步仍是 operator 是否 approve sealed preflight，以及 production learning lane 是否開始真實積累 ledger/outcome rows。
