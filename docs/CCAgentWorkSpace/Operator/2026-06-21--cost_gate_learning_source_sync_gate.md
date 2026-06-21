# Operator Note: Cost-Gate Learning Source-Sync Gate

Date: 2026-06-21

## What Changed

The cost-gate learning activation preflight now checks local git checkout readiness in addition to learning artifacts.

Run after the source is available on `trade-core`:

```bash
cd "$HOME/BybitOpenClaw/srv"
PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.status --data-dir "${OPENCLAW_DATA_DIR:-/tmp/openclaw}" --print-json
```

## Source Fields

Watch these fields before enabling writer or cron:

- `source.source_activation_status`
- `source.source_activation_ready`
- `source.git_head_short`
- `source.git_upstream`
- `source.git_ahead_count`
- `source.git_behind_count`
- `source.git_dirty_path_count`
- `source.git_untracked_path_count`
- `answers.runtime_source_ready_for_activation`
- `activation_blockers`

## Meaning

- `SYNCED_CLEAN`: source checkout is eligible for activation checks.
- `DIRTY`: tracked or untracked local files exist; reconcile before activation.
- `BEHIND_UPSTREAM`: runtime source is behind its configured upstream; sync before activation.
- `AHEAD_OF_UPSTREAM` / `DIVERGED`: source state needs operator/PM review before activation.
- `NO_UPSTREAM` / `NOT_GIT_REPO` / `GIT_UNREADABLE`: source provenance is not strong enough for activation.

## Current Runtime Read

Latest read-only probe still shows `trade-core` behind origin/main and dirty. Cost-gate learning artifacts are still missing, so demo rejects are not yet accumulating learning evidence.

## Boundary

This check is read-only local git metadata. It does not fetch, pull, reset, clean, install cron, enable the writer, lower Cost Gate, grant order authority, place or cancel orders, call Bybit private APIs, write PG, mutate runtime config, or create promotion proof.
