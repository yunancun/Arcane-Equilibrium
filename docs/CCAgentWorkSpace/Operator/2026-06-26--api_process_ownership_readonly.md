# API Process Ownership Read-Only

Status: `DONE_WITH_CONCERNS`

This round fixed the TODO state, not the runtime. Read-only evidence now shows the trading API and watchdog are owned by user systemd services:

- `openclaw-trading-api.service`: active/running, MainPID `2218842`
- `openclaw-watchdog.service`: active/running, MainPID `1538268`
- API cgroup: `app.slice/openclaw-trading-api.service`

The older TODO wording that service ownership was not established is stale. No service restart, crontab edit, PG write, source sync, Bybit order action, Cost Gate change, or authority mutation was performed.

P0 bounded probe authorization remains blocked: latest runtime auth sha `e7420e21...` is still `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED` / `decision=defer` with no granted probe/order authority.
