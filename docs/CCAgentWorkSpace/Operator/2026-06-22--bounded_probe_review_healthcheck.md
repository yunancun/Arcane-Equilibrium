# 2026-06-22 — Bounded Probe Review Healthcheck

本輪不是放寬 Cost Gate，也不是授權 probe/order。

核心修正：demo-learning stack healthcheck 現在不只看 ledger 和 blocked-outcome review，還會檢查 bounded demo-probe 的復盤鏈是否存在：

- `sealed_horizon_probe_preflight_latest.json`
- `bounded_probe_result_review_latest.json`
- `bounded_probe_execution_realism_review_latest.json`

如果缺 sealed preflight，會報：

- `BOUNDED_PROBE_PREFLIGHT_MISSING`

如果缺 bounded result / execution review，會報：

- `BOUNDED_PROBE_REVIEW_ARTIFACTS_MISSING`

這些欄位也已傳到 alpha blocker 和 learning worklist，所以不會因為 ledger 已有 40k rows、blocked-outcome review 已有 candidate，就誤判 bounded-probe learning chain 是健康的。

Linux read-only smoke 的現狀：

- `source_ready=true`
- `stack_installed=false`
- `sealed_horizon_probe_preflight_present=true`
- `bounded_probe_result_review_present=false`
- `bounded_probe_execution_realism_review_present=false`
- `bounded_probe_reviews_present=false`
- overall `status=NOT_INSTALLED`

已驗證：Mac py_compile passed；Mac healthcheck tests `7 passed`；Mac alpha/worklist `60 passed`；source commit `252b5bec` 已推送；Linux 已 fast-forward 到 `252b5bec`；Linux 同套測試 `7 passed` + `60 passed`；沒有 CI、沒有 PG write、沒有 Bybit private/signed/trading call、沒有 deploy/restart、沒有 crontab/env/auth/risk/order/strategy mutation、沒有 Cost Gate lowering、沒有 probe/order authority、沒有 promotion proof。
