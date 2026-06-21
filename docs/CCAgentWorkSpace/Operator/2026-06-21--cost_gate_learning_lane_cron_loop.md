# Operator Note: Cost-Gate Learning Lane Cron Loop

Date: 2026-06-21

## Status

Source is ready for a dry-run-gated hourly artifact loop. It is not installed by this batch.

Current runtime observation before install: `/tmp/openclaw/cost_gate_learning_lane/` has no `probe_ledger.jsonl`, so blocked demo cost-gate signals are not yet accumulating outcome evidence.

## Dry Run

```bash
cd "$HOME/BybitOpenClaw/srv"
helper_scripts/cron/install_cost_gate_learning_lane_cron.sh
```

## Install

Only after source is synced and the demo-learning writer decision is approved:

```bash
cd "$HOME/BybitOpenClaw/srv"
OPENCLAW_COST_GATE_LEARNING_CRON_APPLY=1 \
  helper_scripts/cron/install_cost_gate_learning_lane_cron.sh
```

Default schedule: minute 27 hourly.

## Watch

- Heartbeat: `/tmp/openclaw/cron_heartbeat/cost_gate_learning_lane.last_fire`
- Cron log: `/tmp/openclaw/logs/cost_gate_learning_lane_cron.log`
- Status log: `/tmp/openclaw/logs/cost_gate_learning_lane.log`
- Ledger: `/tmp/openclaw/cost_gate_learning_lane/probe_ledger.jsonl`
- Refresh latest: `/tmp/openclaw/cost_gate_learning_lane/outcome_refresh_latest.json`
- Review latest: `/tmp/openclaw/cost_gate_learning_lane/blocked_outcome_review_latest.json`

## Rollback

```bash
OPENCLAW_COST_GATE_LEARNING_CRON_APPLY=1 \
  "$HOME/BybitOpenClaw/srv/helper_scripts/cron/install_cost_gate_learning_lane_cron.sh" --remove
```

## Boundary

This cron writes local JSONL/JSON/log/heartbeat artifacts only and uses read-only PG. It does not grant order authority, lower the main Cost Gate, place or cancel orders, call Bybit private APIs, write PG, mutate runtime config, or create promotion proof.
