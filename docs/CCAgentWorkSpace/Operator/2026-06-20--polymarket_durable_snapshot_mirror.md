# Polymarket durable snapshot mirror

Date: 2026-06-20

## Operator read

Polymarket lead-lag evidence is now mirrored outside volatile `/tmp`, so sample history should survive `/tmp/openclaw` cleanup.

This is not a signal and not a promotion. It only makes the research evidence chain durable enough to keep accumulating samples.

## Current state

- Lead-lag latest: `e86ca7daf701da329b76ee51deddc552005a829480a3b0926c30b4b6f8dfb4f7`.
- Snapshot rows: `2685`.
- Snapshot timestamps: `3`.
- Duplicate mirror run dirs skipped: `1`.
- IC sample: `0`.
- Lead-lag verdict: `INSUFFICIENT_SAMPLE`.
- Alpha latest: `1619ca99dbfe10c22ee79d83cf44312aae434687c03fd4bfaa5ccfe94a4ff825`.
- Alpha scorecard: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`.

## Action

No operator action, no strategy change, no probe, no order.

Let the collector/lead-lag cron continue accumulating dated snapshots. Recompute after label horizons mature and only escalate if the normal AEG/replay/execution-realism gates produce durable evidence.

## Boundary

Artifact-only research durability change. No PG write, Bybit private/signed/trading call, engine/API rebuild/restart, credential/auth/risk/order mutation, or promotion proof.
