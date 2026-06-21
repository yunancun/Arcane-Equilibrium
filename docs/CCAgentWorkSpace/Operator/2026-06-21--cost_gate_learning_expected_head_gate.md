# Operator Note: Cost-Gate Learning Expected-Head Gate

Date: 2026-06-21

## Command

Use the PM-pushed commit SHA as the expected source head:

```bash
cd "$HOME/BybitOpenClaw/srv"
PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.status \
  --data-dir "${OPENCLAW_DATA_DIR:-/tmp/openclaw}" \
  --expected-head "<PM_PUSHED_SHA>" \
  --print-json
```

Equivalent env form:

```bash
OPENCLAW_EXPECTED_SOURCE_HEAD="<PM_PUSHED_SHA>" \
PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.status \
  --data-dir "${OPENCLAW_DATA_DIR:-/tmp/openclaw}" \
  --print-json
```

## Fields To Check

- `source.git_head`
- `source.git_head_short`
- `source.expected_head`
- `source.expected_head_status`
- `source.expected_head_matches`
- `source.expected_head_error`
- `activation_blockers`

## Meaning

- `MATCH`: runtime `HEAD` matches the expected SHA prefix.
- `MISMATCH`: runtime source is not the PM-pushed commit; do not activate writer/cron.
- `INVALID`: the expected SHA is not a 7-40 character hex prefix.
- `UNKNOWN_HEAD`: local git `HEAD` could not be read.

This check complements `source_activation_status`. Both must be clean before activation: expected head must match, and the checkout must not be dirty/diverged/behind/ahead.

## Boundary

This is read-only local git metadata. It does not fetch, pull, reset, clean, install cron, enable the writer, lower Cost Gate, grant order authority, place or cancel orders, call Bybit private APIs, write PG, mutate runtime config, or create promotion proof.
