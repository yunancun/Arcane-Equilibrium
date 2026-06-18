# TODO v173 BB Reversion Regime Observability SQL Closure

Date: 2026-06-18
Role: PM
Scope: TODO active-queue hygiene backed by read-only source/runtime evidence

## Decision

Archive `P1-BB-REVERSION-REGIME-OBSERVABILITY` from `TODO.md` §5.

The row's remaining acceptance was post-deploy SQL evidence that new `bb_reversion` intents carry the Hurst regime observability keys. That evidence is now present.

## Evidence

- Source merge `6628b4cf` is an ancestor of runtime source HEAD `83b7632d`.
- Linux `trade-core` checkout contains `6628b4cf`.
- Production schema: `trading.intents.details` is `jsonb`.
- Source writer emits top-level `details.hurst_label` and `details.hurst_value` from the same-tick Hurst snapshot; tests assert present-null behavior when Hurst is missing and value-null behavior for non-finite Hurst.
- Linux true DB read-only SQL:
  - window: `strategy_name='bb_reversion' AND ts >= TIMESTAMPTZ '2026-06-11 02:00:00+00'`
  - count: `n=10`
  - `details ? 'hurst_label'`: `10/10`
  - `details ? 'hurst_value'`: `10/10`
  - span: `2026-06-13 18:05:00.004+02` to `2026-06-18 17:41:00+02`
  - latest sampled rows show `hurst_label=mean_reverting` with numeric `hurst_value`.

## What This Does Not Close

This closes observability/key-presence only. It does not prove bb_reversion alpha and does not close the sample-size decision.

`P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK` remains active for 2026-06-27 and still decides bb_breakout/bb_reversion Stage 0R baseline vs M7 retire/extension. If `bb_reversion@mean_reverting` sample size remains below 100, the existing extension rule still applies.

## Changes Made

- `TODO.md`: v172 -> v173, removed the active row, updated archive marker, and clarified the 06-27 sample-size row.
- `docs/CLAUDE_CHANGELOG.md`: added v173 increment.
- `docs/CCAgentWorkSpace/PM/memory.md`: added PM memory entry.
- Added this PM report and an Operator mirror.

## Boundary

Read-only DB/source verification plus docs/TODO hygiene only.

No CI, deploy, rebuild, restart, production source mutation, runtime mutation, DB write, auth/risk/order/trading mutation.
