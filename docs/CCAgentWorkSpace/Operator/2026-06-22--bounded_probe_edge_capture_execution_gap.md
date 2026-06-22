# 2026-06-22 — Bounded Probe Edge-Capture Execution Gap

本輪不是放寬 Cost Gate，也不是給 probe/order authority。

核心變更：未來 bounded demo probe 即使實際 net PnL 為正，也必須跑贏同 side-cell / 同 horizon 的 matched `blocked_signal_outcome` controls，才會被主閉環視為可進一步 review 的 Cost Gate evidence。若 probe 正收益但低於 control，系統會標記 `PROBE_UNDERPERFORMS_MATCHED_CONTROL_EXECUTION_GAP`，並轉成 engineering blocker：`bounded_probe_result_review_probe_under_captures_matched_control_edge`。

這代表下一步應先查 execution realism：slippage、timing、fill quality、horizon retiming。不要把這種結果直接當作 Cost Gate lowering 或追加 probe budget 的理由。

已驗證：Mac py_compile passed；Mac focused pytest `77 passed`；Mac `git diff --check` passed；source commit `bc7053a9` 已推送；Linux `trade-core` 已 fast-forward 到 `bc7053a9`；Linux py_compile passed；Linux focused pytest `77 passed`。

邊界未變：沒有 CI、沒有 PG write/migration、沒有 Bybit private/signed/trading call、沒有 deploy/restart、沒有 cron/env/auth/risk/order/strategy mutation、沒有 Cost Gate lowering、沒有 probe/order authority、沒有 promotion proof。
