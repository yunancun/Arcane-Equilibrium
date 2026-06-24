# Operator Note — API Service Runtime Cutover PM Apply

Date: 2026-06-24

The Demo/API control service handoff was executed under E3 review.

What changed:

- manual uvicorn master PID `1859622` was gracefully stopped
- `openclaw-trading-api.service` was started and now owns port `8000`
- unit content was written from the exact reviewed v472 proposal
- current unit backup:
  `/home/ncyu/.config/systemd/user/openclaw-trading-api.service.backup_20260624T113713Z_before_pm_apply_review`

Post-check:

- service `active/running`
- MainPID `2218842`
- listener only on `100.91.109.86:8000`
- `/api/v1/system/health` returns `401`, so the authenticated API surface is reachable
- post-cutover packet `/tmp/api_service_env_parity_packet_post_cutover.json` is `API_SERVICE_ENV_PARITY_CLEAN_SOURCE_ONLY`
- demo engine remains alive

What did not change:

- `systemctl --user enable` was not run; service remains `disabled` for boot autostart
- no Bybit call
- no PG write
- no Cost Gate change
- no probe/order/live authority
- no Rust writer
- no promotion proof

Next: enablement, if desired, needs a separate PM/E3 checkpoint. For profit learning, the more important path remains bounded Demo probe authorization and candidate-matched execution evidence.
