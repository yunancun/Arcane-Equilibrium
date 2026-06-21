# Operator Note: Cost-Gate Learning Writer Config Preflight

Date: 2026-06-21

## What Changed

The cost-gate learning preflight now reports whether the demo-learning writer is explicitly enabled and which plan/ledger paths it will use. `restart_all.sh` also forwards the writer env vars into the Rust engine process, so env-file settings are no longer dead parameters after a normal restart.

## Runtime Check

After operator-approved source sync and before enabling learning collection, run:

```bash
cd "$HOME/BybitOpenClaw/srv"
PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.status \
  --data-dir "${OPENCLAW_DATA_DIR:-/tmp/openclaw}" \
  --expected-head "<PM_PUSHED_SHA>" \
  --runtime-env-file "${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}/environment_files/basic_system_services.env" \
  --require-writer-enabled \
  --print-json
```

Check:

- `writer_config.writer_config_status`
- `writer_config.plan_path`
- `writer_config.ledger_path`
- `answers.runtime_writer_enabled`
- `answers.writer_disabled_or_unset_drop_risk`
- `activation_blockers`

## Meaning

- `writer_config_status=ENABLED`: writer env is explicitly enabled in the inspected runtime env.
- `DISABLED` / `UNSET` / `INVALID`: do not expect new cost-gate rejects to accumulate in `probe_ledger.jsonl`.
- `runtime_writer_not_enabled` blocker: activation is not ready under `--require-writer-enabled`.
- Blank `OPENCLAW_DEMO_LEARNING_LANE_PLAN` or `OPENCLAW_DEMO_LEARNING_LANE_LEDGER` now safely falls back to default paths under `$OPENCLAW_DATA_DIR/cost_gate_learning_lane/`.

## Boundary

This does not edit env files, sync source, deploy, rebuild, restart, install cron, lower the main Cost Gate, grant demo probe authority, submit/cancel orders, call Bybit private APIs, write PG, or mutate runtime config.
