# Operator Note: Cost-Gate Learning Loop Status Ingestion

Date: 2026-06-21

## What Changed

The alpha-discovery killboard now reads cost-gate learning-loop runtime artifacts directly.

Key fields to watch in `cost_gate_demo_learning_lane` blocker detail:

- `learning_loop_status`
- `learning_loop_heartbeat_present`
- `learning_loop_heartbeat_age_seconds`
- `learning_loop_status_age_seconds`
- `learning_loop_last_refresh_rc`
- `learning_loop_last_review_rc`
- `learning_loop_last_ledger_row_count`
- `learning_loop_last_review_status`

## Status Meanings

- `NOT_SEEN`: no heartbeat, status log, or learning artifacts were observed.
- `RUNNING_NO_LEDGER_ROWS`: cron/status loop ran, but no ledger rows exist yet.
- `STALE_STATUS` / `STALE_HEARTBEAT`: loop exists but has not fired recently.
- `ERROR`: latest refresh or review rc was nonzero.
- `RUNNING`: status log is recent and non-empty.

## Current Runtime Read

The latest read-only probe still found no learning-loop heartbeat/status log/ledger/review artifact on Linux. That means demo cost-gate rejects are not yet accumulating outcome evidence.

## Boundary

This is visibility only. It does not install cron, enable the writer, lower Cost Gate, grant order authority, place or cancel orders, call Bybit private APIs, write PG, mutate runtime config, or create promotion proof.
