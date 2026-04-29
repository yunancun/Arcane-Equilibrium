# W1-T2 Attribution Gap Close

Date: 2026-04-29 21:20 CEST

## Scope

Operator asked to verify the prior debug findings, assess whether the completed fixes met the actual requirement, identify gaps, and then “全部修掉”. I treated that as fixing engineering gaps only. No live/demo risk parameters were changed, no strategy was stopped, and no live authorization boundary was loosened.

## Findings Verified

- The original `[38] grid_trading_lifecycle_drift` problem is real, not a monitoring artifact. After the earlier silent-dead fix, runtime healthcheck consistently shows live_demo grid positions closing much faster than demo and re-entering more often.
- The W1-T1/W1-T3/W1-T4 work was necessary but incomplete. Schema, consumers, and monitoring existed, but the producer-side close emitters still wrote dynamic close text into `trading.fills.strategy_name` and left `exit_reason` empty.
- GUI copy was mostly fixed, but `tab-learning.html` still had one explanatory block implying shadow/no-order behavior in the Learning dashboard context.
- `[39]` was too strict during rollout because a 24h window naturally contains pre-W1-T2 legacy rows.

## Fixes

- `5895579` completed W1-T2 producer-side attribution for common close emitters:
  - canonical close helper now writes normalized `strategy_name` plus free-text `exit_reason`;
  - external/confirmed fill paths use the same legacy-tag normalizer;
  - `build_close_tags_from_legacy()` converts `strategy_close:*`, `risk_close:*`, `stop_trigger:*`, and `ipc_close:*` into the V033 two-field contract.
- `854cae1` fixed the post-deploy gap found by DB readback: zero-PnL IPC/manual close rows now count as close rows for DB attribution when they carry a legacy close prefix.
- `[38]` now matches both legacy close-prefix rows and post-W1-T2 `exit_reason IS NOT NULL`, scoped by `entry_context_id` back to grid entries.
- `[39]` now hard-fails on 1h recent distinct cardinality and treats 24h excess as rollout WARN while old rows age out.
- Learning dashboard text now describes engine execution gates rather than implying “shadow only / no real orders.”

## Verification

- Local Rust full lib: 2372 passed.
- Local `cargo check --bins`: PASS with existing warnings.
- Local targeted Python/API/healthcheck pytest: 67 passed, 11 existing warnings.
- Local `python3 -m py_compile` for healthcheck scripts: PASS.
- Local `git diff --check`: PASS.
- Linux deploy: `trade-core` fast-forwarded to `854cae1`; release rebuild/restart used `PATH="$HOME/.cargo/bin:$PATH"` because non-login SSH lacks cargo in PATH.
- Runtime after deploy: engine PID `779344`, API PID `779449`, watchdog `engine_alive=true`, paper/demo/live snapshots fresh.
- DB short-window proof after `854cae1`: new zero-PnL `risk_close:ipc_close_symbol` rows write `exit_reason=ipc_close_symbol`.
- Passive healthcheck after deploy:
  - `[38]` FAIL remains a real grid behavior signal: live_demo re-entry rate 0.72, lifetime_ratio 0.35.
  - `[39]` WARN: 1h distinct strategy_name=7, 24h distinct=22 while legacy rows age out.
  - Existing WARNs `[12]`, `[33]`, and `[11]` unchanged.

## Remaining Gaps

- `[38]` is intentionally still failing. This requires an operator/risk decision on grid live_demo behavior, not more instrumentation.
- `[39]` should be rechecked after a full 24h rollover. The important recent window is now within threshold.
- Some static system paths such as `risk_close:ipc_close_symbol` can remain as system attribution keys when there is no owner snapshot. They now carry `exit_reason`, but they are not forced into one of the five entry-strategy names unless an owner strategy exists.

## Recommendation

Next decision should be risk-policy, not plumbing: decide whether live_demo grid should pause selected robust-negative cells, widen trailing distance toward demo behavior, reduce levels, or disable partial TP. Keep `[38]` failing until that policy is explicitly changed and verified.
