# 2026-06-22 — Alpha Cron Activation Packet And Source Cleanliness

本輪把 activation packet 接進既有 alpha cron 的自然刷新路徑。

當前 Linux runtime smoke 結果：

- source: `SYNCED_CLEAN`
- packet: `READY_FOR_OPERATOR_DRY_RUN`
- alpha schema: `alpha_discovery_runtime_killboard_v8`
- worklist schema: `alpha_learning_worklist_v5`
- top task: `cost_gate_learning_activation`
- blocker: `demo_learning_stack_activation_packet_ready_for_operator_dry_run`
- next trigger: `run_dry_run_preview_then_apply_only_if_installer_preflight_passes`
- missing crons: `4`
- healthcheck: `NOT_INSTALLED`

本輪還修掉一個 source-health 問題：`vol_event_trigger.py` 的週期性 robust-ruling latest report 現在預設寫到 `/tmp/openclaw/order_flow_alpha/`，不再寫 tracked docs file。Linux 上原先的 generated report 已保存到：

`/tmp/openclaw/order_flow_alpha/vol-event-robust-ruling.pre_v409_runtime_copy.md`

已驗證：

- Mac cron tests `6 passed`
- Mac research tests `64 passed`
- Linux cron tests `6 passed`
- Linux research tests `64 passed`
- Linux artifact-only alpha cron smoke passed
- source commit `2d4bad29` pushed with `[skip ci]`

這不是：

- cron install
- Cost Gate lowering
- probe/order authority
- PG write/schema migration
- Bybit private/signed/trading call
- deploy/rebuild/restart
- env/auth/risk/order/strategy mutation
- promotion proof

下一個 operator action 仍然只是 review activation packet 的 dry-run path。只有另行批准 apply，四條 demo-learning stack cron 才會開始持續累積 rejected-signal learning evidence。
