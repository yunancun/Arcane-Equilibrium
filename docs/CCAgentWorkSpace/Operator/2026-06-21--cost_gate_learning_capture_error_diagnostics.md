# Operator Note: Cost-Gate Learning Capture-Error Diagnostics

Date: 2026-06-21

## What Changed

If the demo-learning writer sees an eligible demo/live_demo cost-gate reject but cannot evaluate admission, it now appends a `probe_capture_error` row instead of only logging a warning.

This row means: the rejected signal was captured, but the learning lane could not classify it because plan/path/config was broken.

## Fields To Check

Run the normal preflight:

```bash
cd "$HOME/BybitOpenClaw/srv"
PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.status \
  --data-dir "${OPENCLAW_DATA_DIR:-/tmp/openclaw}" \
  --expected-head "<PM_PUSHED_SHA>" \
  --print-json
```

Check:

- `ledger.ledger_status`
- `ledger.capture_error_count`
- `ledger.captured_reject_count`
- `ledger.latest_capture_error`
- `answers.cost_gate_rejects_recorded`
- `answers.admission_evaluation_errors_recorded`
- `status`
- `activation_blockers`

## Meaning

- `CAPTURE_ERRORS_PRESENT`: rejects are not silently lost, but admission evaluation failed.
- `CAPTURE_ERRORS_NEED_OPERATOR_FIX`: inspect plan path, writer env, and latest capture error before expecting outcome learning.
- `ADMISSION_ROWS_PRESENT`: rejects were evaluated and can move to blocked-signal outcome refresh.
- `MISSING` or `EMPTY`: still no durable reject evidence.

## Boundary

This does not enable the writer, install cron, sync source, deploy, restart, lower the main Cost Gate, grant demo probe authority, submit/cancel orders, call Bybit private APIs, write PG, or mutate runtime config.
