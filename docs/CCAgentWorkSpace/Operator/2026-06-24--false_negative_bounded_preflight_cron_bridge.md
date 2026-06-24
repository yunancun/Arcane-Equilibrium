# Operator Note: False-Negative Bounded Preflight Cron Bridge

Date: 2026-06-24
Status: `DONE_WITH_CONCERNS`
Source commit: `744d51366d9baf8dfbf05186fe4d6bc7e8cf8a7c`

## What Changed

The selected false-negative path is now wired into the source cron/review chain.

- `cost_gate_learning_lane_cron.sh` refreshes learning SSOT, autonomous parameter proposal, and `false_negative_bounded_probe_preflight_latest`.
- Cost Gate bounded review stages now use the active bounded preflight source instead of hardcoding sealed-horizon preflight.
- `alpha_discovery_throughput_cron.sh` prefers false-negative bounded preflight latest when it exists; otherwise it falls back to sealed-horizon preflight.
- Profitability scorecard now has generic `bounded_probe_preflight_*` fields so false-negative evidence is not mislabeled as sealed-horizon proof.

## What This Is Not

- Not a live promotion.
- Not a global Cost Gate reduction.
- Not a probe/order authorization.
- Not a Bybit order/cancel/modify.
- Not a PG write, crontab edit, service restart, deploy, or Rust writer enablement.
- Not PnL proof or promotion proof.

Runtime read-only evidence still showed Linux source at `c88deea7`, so this source change is not runtime-proven yet.

## Current Blocker

`P0-BOUNDED-PROBE-AUTHORIZATION`

The source chain can now produce the right review artifacts for the selected false-negative candidate, but an actual bounded Demo probe still requires candidate-specific authorization and later candidate-matched fills/controls. Broad Demo API permission is not treated as live/mainnet authority or as a typed bounded-probe authorization object.

## Verification

Passed:

- bash syntax for both cron wrappers
- `py_compile` for profitability scorecard
- cron static tests: `17 passed`
- profitability scorecard tests: `18 passed`
- bounded Cost Gate helper suite: `142 passed`
- alpha runtime tests: `80 passed`
- alpha worklist tests: `10 passed`
- `git diff --check`

## Safe Next Action

If continuing operationally, the next safe checkpoint is runtime source sync plus artifact-only cron refresh to confirm the selected false-negative preflight latest is produced from runtime data. That still must not be interpreted as order authority or promotion proof.

Residual concerns:

- Missing false-negative preflight fails closed but may leave older latest files visible.
- Alpha fallback to sealed-horizon is backward-compatible, not false-negative-only.
