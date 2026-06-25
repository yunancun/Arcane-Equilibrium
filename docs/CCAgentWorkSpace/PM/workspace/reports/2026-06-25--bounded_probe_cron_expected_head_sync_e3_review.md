# PM Report: Bounded Probe Cron Expected-Head Sync E3 Review

Date: 2026-06-25
Status: DONE_WITH_CONCERNS
Active blocker: `P0-BOUNDED-PROBE-CRON-EXPECTED-HEAD-SYNC-E3-REVIEW-DEMO-ONLY`

## Decision

Closed the expected-head sync checkpoint. Runtime checkout and learning cron expected-head pins now align at `d2971aa511b7b2891d615d6c4dc9f582ab572835`.

## Evidence

- E3 selected option A: sync Linux checkout to `d2971aa5`, then update expected-head pins to `d2971aa5`.
- PM fast-forwarded `/home/ncyu/BybitOpenClaw/srv` from `b180546c` to `d2971aa5`.
- PM replaced exactly 11 crontab expected-head occurrences from `bdc1e1568431797cd1001e4484bf2da7ae6df7c4` to `d2971aa511b7b2891d615d6c4dc9f582ab572835`.
- Post-check: Linux `HEAD=origin/main=d2971aa5`, worktree clean, crontab line count `70`, old SHA count `0`, new SHA count `11`.
- `OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES=0` count is `1`; `=1` count is `0`.
- `OPENCLAW_ALLOW_MAINNET=1` count is `0`; `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED` count is `0`.
- Running engine env still reports `OPENCLAW_ALLOW_MAINNET=0`; engine was not restarted.
- Latest bounded-probe authority artifact remains old-state `PLACEMENT_REPAIR_PLAN_NOT_READY`; no artifact refresh was claimed.

## Boundary

FF-only source checkout sync plus crontab expected-head SHA replacement and docs only. No rebuild, no restart, no service/env mutation beyond reviewed crontab hash pins, no PG write, no Bybit API call, no order/cancel/modify, no Rust writer or adapter enablement, no Cost Gate lowering, no probe/order/live authority, and no promotion proof.

## Next Safe Action

Open a no-order artifact refresh review so natural bounded-probe authority/readiness artifacts can be refreshed against `d2971aa5`. Post-restart active bounded-probe pending-order reconciliation remains a separate proof blocker before adapter enablement or Demo order action.
