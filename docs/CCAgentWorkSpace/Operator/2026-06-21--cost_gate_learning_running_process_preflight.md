# Operator Note: Cost-Gate Learning Running-Process Preflight

Date: 2026-06-21

## What Changed

The cost-gate learning preflight can now inspect the active Rust engine process environment. This proves whether the currently running engine actually loaded `OPENCLAW_DEMO_LEARNING_LANE_WRITER`, not just whether the env file contains it.

## Runtime Check

After operator-approved source sync, env-file update, and engine restart, run:

```bash
cd "$HOME/BybitOpenClaw/srv"
ENGINE_PID="$(pgrep -n -f 'rust/target/release/openclaw-engine|openclaw-engine')"
PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.status \
  --data-dir "${OPENCLAW_DATA_DIR:-/tmp/openclaw}" \
  --expected-head "<PM_PUSHED_SHA>" \
  --runtime-env-file "${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}/environment_files/basic_system_services.env" \
  --engine-pid "$ENGINE_PID" \
  --require-writer-enabled \
  --require-process-writer-enabled \
  --print-json
```

Check:

- `writer_process.writer_process_status`
- `writer_process.writer_process_enabled`
- `writer_process.proc_environ_path`
- `writer_process.plan_path`
- `writer_process.ledger_path`
- `answers.runtime_writer_process_enabled`
- `answers.running_engine_writer_disabled_or_unset_drop_risk`
- `activation_blockers`

## Meaning

- `writer_process_status=ENABLED`: the running engine process has the writer flag.
- `DISABLED` / `UNSET` / `INVALID`: the active engine should not be expected to append new cost-gate reject rows.
- `PROC_ENVIRON_UNREADABLE`: the process env could not be inspected; treat activation as unproven.
- `running_engine_writer_not_enabled`: activation is not ready under `--require-process-writer-enabled`.

## Boundary

This is read-only process environment inspection. It does not edit env files, sync source, deploy, rebuild, restart, install cron, lower the main Cost Gate, grant demo probe authority, submit/cancel orders, call Bybit private APIs, write PG, or mutate runtime config.
