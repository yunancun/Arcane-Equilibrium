# 2026-06-22 — Bounded Probe Execution-Realism Review

本輪不是放寬 Cost Gate，也不是授權 probe/order。

核心變更：如果 future bounded demo probe 正收益但低於同 side-cell / 同 horizon 的 matched `blocked_signal_outcome` controls，系統不再只標記 generic execution gap，而是要求生成 `bounded_demo_probe_execution_realism_review_v1`。

這個 review 會分解：

- probe vs control 的 net/gross/cost gap；
- entry delay gap；
- probe outcome 是否 fill-backed，還是只有 proxy markout；
- 第一個 repair hypothesis，例如 fill-backed execution missing、horizon/signal timing gross-edge gap、fee/slippage/fill-cost gap、entry timing delay gap。

主閉環現在會區分兩種狀態：

- `bounded_probe_execution_realism_review_required`：還缺診斷 artifact。
- `bounded_probe_execution_realism_gap_diagnosed_repair_required`：已有診斷，先修復/重放再談 Cost Gate/operator review。

已驗證：Mac py_compile passed；Mac focused pytest `82 passed`；Mac `git diff --check` passed；source commit `7c04097f` 已推送；Linux `trade-core` 已 fast-forward 到 `7c04097f`；Linux py_compile passed；Linux focused pytest `82 passed`。

邊界未變：沒有 CI、沒有 PG write/migration、沒有 Bybit private/signed/trading call、沒有 deploy/restart、沒有 cron/env/auth/risk/order/strategy mutation、沒有 Cost Gate lowering、沒有 probe/order authority、沒有 promotion proof。
