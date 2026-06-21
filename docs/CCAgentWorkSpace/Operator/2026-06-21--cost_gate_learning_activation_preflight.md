# Operator Note: Cost-Gate Learning Activation Preflight

Date: 2026-06-21

## Command

After source sync on `trade-core`, run:

```bash
cd "$HOME/BybitOpenClaw/srv"
PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.status --data-dir "${OPENCLAW_DATA_DIR:-/tmp/openclaw}" --print-json
```

## What It Answers

- Are cost-gate reject ledger rows present?
- Is evidence currently accumulating?
- Are rejected signals being recorded, or is silent-drop risk still present?
- Are blocked-signal markout outcomes present?
- Is the blocked-signal profitability review mechanism available?

## Key Statuses

- `NOT_ACCUMULATING`: plan may exist, but ledger/writer/cron evidence is missing.
- `LOOP_RUNNING_NO_LEDGER_ROWS`: learning cron ran, but no reject ledger rows exist yet.
- `ADMISSION_ONLY_NEEDS_OUTCOME_REFRESH`: rejects are recorded, but blocked-signal outcomes are missing.
- `BLOCKED_OUTCOMES_ACCUMULATING`: blocked-signal outcomes exist, but review gate is not cleared.
- `REVIEW_CANDIDATE_OPERATOR_REVIEW`: blocked-signal markouts clear review thresholds; operator review is required before any demo probe authority.
- `KEEP_BLOCKED_REVIEWED`: reviewed blocked side-cells did not clear thresholds.

## Current Runtime Read

Latest read-only probe still found no `probe_ledger.jsonl`, no learning-loop heartbeat, no learning-loop status log, and no blocked-outcome review latest artifact on Linux. That means runtime is not yet accumulating cost-gate learning evidence.

## Boundary

This preflight is read-only. It does not install cron, enable the writer, lower Cost Gate, grant order authority, place or cancel orders, call Bybit private APIs, write PG, mutate runtime config, or create promotion proof.
