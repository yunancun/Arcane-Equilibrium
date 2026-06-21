# 2026-06-21 -- Cost-Gate Learning Activation Runbook

新增 operator-gated runtime activation runbook:

- `docs/runbooks/2026-06-21--cost_gate_learning_lane_runtime_activation.md`

它把下一步拆成明確 gate：只讀 audit、dirty runtime source reconcile/sync、preflight、cron dry-run/install、append boundary、可選 hot-path writer restart、觀察與 rollback。這份 runbook 不是授權；執行任何 runtime write 仍需要你明確批准。

這輪沒有 runtime sync、沒有改 crontab、沒有改 env、沒有 restart、沒有 append ledger、沒有 PG write、沒有 Bybit call、沒有下單、沒有 lower Cost Gate。
