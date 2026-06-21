# Polymarket label maturity / price catch-up routing

Date: 2026-06-21

## Decision

Split the Polymarket alpha blocker for zero joined IC rows into two concrete wait states:

- `label_horizon_not_matured`: snapshots/features exist, but label targets are still in the future.
- `price_data_not_caught_up_to_label_target`: the report is already past the oldest label target, but PG 1m price data has not caught up far enough to join labels.

## Runtime evidence

- Lead-lag latest sha256: `199fb15e150298ab076fb47e08513546e3e82c02153a5174da09edaa56b995c1`.
- Lead-lag created: `2026-06-20T22:07:53.220512+00:00`.
- Snapshot rows: `3555`.
- Snapshot distinct timestamps: `4`.
- Feature points: `39`.
- Label feature/horizon pairs: `117`.
- Joined rows: `0`.
- Label status counts: `entry_target_after_latest_price=39`, `exit_target_after_latest_price=78`.
- Latest feature timestamp: `2026-06-20T22:07:01.434000+00:00`.
- Latest 1m price timestamp for BTC/ETH/SOL/XRP: `2026-06-20T22:06:00+00:00`.
- Oldest unmatured exit target: `2026-06-20T22:07:01.150000+00:00`.
- Alpha latest sha256: `a77a709ec1f80bd5057a96d6874b297cbf5bdb7e821cdc796050d7f5129585f5`.
- Alpha created: `2026-06-20T22:10:33.742846+00:00`.
- Alpha status: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`.
- Polymarket primary blocker: `price_data_not_caught_up_to_label_target`.

## Read

The durable mirror is working; the collector now has multiple Polymarket snapshot timestamps. The immediate blocker is not a generic lack of snapshots. It is that lead-lag features are newer than the available PG 1m price bars, so forward labels cannot join yet.

This is useful because the next action is now mechanical and bounded: wait for 1m price data to cover the oldest label target, then rerun Polymarket lead-lag and alpha discovery. It does not justify a strategy change or promotion.

## Verification

- TDD red first caught missing `latest_price_ts_utc_by_symbol`.
- Mac alpha+Polymarket suites: `59 passed`.
- Mac cron static: `9 passed`.
- Linux alpha+Polymarket suites: `59 passed`.
- Linux alpha suite: `34 passed`.
- `py_compile`: passed.
- `git diff --check`: passed.
- Linux artifact-only alpha runtime smoke: passed.

## Boundary

Source/test/docs plus selective Linux source sync and `/tmp/openclaw` artifact writes only. Read-only PG through the existing lead-lag wrapper. No PG table write/schema migration, no Bybit private/signed/trading call, no engine/API rebuild/restart, and no credential/auth/risk/order/strategy mutation. Not signal, execution proof, or promotion proof.
