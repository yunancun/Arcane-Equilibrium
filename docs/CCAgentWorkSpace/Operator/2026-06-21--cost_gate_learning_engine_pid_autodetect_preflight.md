# Operator Note: Cost-Gate Learning Engine PID Auto-Detect Preflight

Date: 2026-06-21

## What Changed

The cost-gate learning preflight can now auto-detect the running `openclaw-engine` process from `/proc/*/cmdline`. It matches only processes whose argv[0] basename is exactly `openclaw-engine`, avoiding shell/pgrep false positives.

## Runtime Check

After operator-approved source sync, env-file update, and engine restart, run:

```bash
cd "$HOME/BybitOpenClaw/srv"
PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.status \
  --data-dir "${OPENCLAW_DATA_DIR:-/tmp/openclaw}" \
  --expected-head "<PM_PUSHED_SHA>" \
  --runtime-env-file "${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}/environment_files/basic_system_services.env" \
  --require-writer-enabled \
  --require-process-writer-enabled \
  --print-json
```

No manual `ENGINE_PID=...` is needed in the common Linux path. The preflight auto-detects it when process writer enablement is required and no PID/proc path is supplied.

## Fields To Check

- `writer_process.engine_pid_detection_status`
- `writer_process.engine_pid_detected`
- `writer_process.engine_pid_candidate_count`
- `writer_process.writer_process_status`
- `answers.runtime_writer_process_enabled`
- `activation_blockers`

## Meaning

- `FOUND`: exactly one engine process was detected and inspected.
- `MULTIPLE_FOUND`: more than one candidate was found; the highest PID was inspected and candidates are listed.
- `NOT_FOUND`: no active engine process matched argv[0] basename `openclaw-engine`.
- `PROC_ROOT_MISSING` / `PROC_ROOT_UNREADABLE`: process detection could not run on this host.
- `running_engine_writer_not_enabled`: activation remains blocked under `--require-process-writer-enabled`.

## Boundary

This is read-only process discovery and environment inspection. It does not edit env files, sync source, deploy, rebuild, restart, install cron, lower the main Cost Gate, grant demo probe authority, submit/cancel orders, call Bybit private APIs, write PG, or mutate runtime config.
