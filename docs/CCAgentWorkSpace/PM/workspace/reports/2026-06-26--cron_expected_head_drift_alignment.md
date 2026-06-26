# Cron Expected-Head Drift Alignment

Date: 2026-06-26 06:24 CEST

## State

- `active_blocker_id`: `P1-RUNTIME-HEALTH-HYGIENE-CRON-EXPECTED-HEAD-DRIFT-REVIEW`
- `status`: `DONE_WITH_CONCERNS`
- `session_loop_state`: `/tmp/openclaw/session_loop_state_20260626T041121Z_cron_expected_head_drift_review.json`
- `next_blocker_id`: `P1-RUNTIME-HEALTH-HYGIENE-CRON-POST-ALIGNMENT-HYGIENE-SNAPSHOT`

Anti-repeat result:

- Did not repeat completed [68] local-lineage source patch.
- Did not repeat completed [68] runtime source sync.
- Proceeded because runtime crontab still had stale `d2cd70d0` expected-head pins after Linux source was verified at `0246b263`.

## E3 Review

E3 returned `DONE_WITH_CONCERNS` and allowed only a narrow crontab expected-head literal alignment:

- backup current crontab under `/tmp/openclaw/audit/...` with restrictive permissions
- replace exact literal `d2cd70d092916194043e112eeb402fb92bacb699` with `0246b26361e403e6cb1ddd126eba8e3cd7b91a23`
- preserve line count, schedules, wrappers, redirects, log paths, env flags, and authority posture
- install via `crontab <file>` only after replacement-only verification
- rollback from backup only if post-checks failed

Forbidden:

- service restart/rebuild/daemon-reload
- Linux cargo
- source sync to docs head
- schedule, wrapper, log path, or authority flag edits
- PG write
- Bybit/API/order/cancel/modify call
- adapter/Rust writer enablement
- Cost Gate change
- live/probe/order authority
- `_latest` overwrite or profit/proof claim

## Runtime Baseline

At `2026-06-26T04:12:02Z`:

- Linux source: `0246b26361e403e6cb1ddd126eba8e3cd7b91a23`
- Linux worktree status count: `0`
- crontab line count: `70`
- stale expected-head matching lines: `57,67,68,69,70`
- exact old literal count: `11`
- new literal count: `0`
- `OPENCLAW_ALLOW_MAINNET=1` count: `0`
- `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED` count: `0`
- `RECORD_PROBE_OUTCOMES=1` count: `0`
- `OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES=0` count: `1`

Prior precedent checked:

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--runtime_cron_expected_head_patch_api_ownership.md`

## Apply Action

The first guarded script attempt failed before any mutation because `set -euo pipefail` combined with a zero-match `grep` count exited nonzero. PM verified live crontab remained unchanged afterward.

The second guarded apply succeeded.

Runtime audit dir:

- `/tmp/openclaw/audit/crontab_expected_head_sync_20260626T041735Z`

Audit metadata:

- pre sha256: `fb80d948de240a37fd19a4271a33ee7ff033586d21ef98d98311a992d2db3bf6`
- post sha256: `4f94371fc779a644aaae2c119596840b26d4fbbf8eaf61dd1bc6dea613003bbc`
- runtime head: `0246b26361e403e6cb1ddd126eba8e3cd7b91a23`
- audit-time API MainPID: `2218842`
- line count: `70`
- old literal count: `0`
- new literal count: `11`
- new literal lines: `57,67,68,69,70`
- authority flag counts: mainnet `0`, bounded adapter `0`, record probe outcomes `1` `0`, record probe outcomes `0` `1`

The diff changes only expected-head SHA values on lines 57 and 67-70.

## Post-Checks

Read-only post-check at `2026-06-26T04:21:04Z`:

- Linux source: `0246b26361e403e6cb1ddd126eba8e3cd7b91a23`
- Linux worktree status count: `0`
- crontab line count: `70`
- old literal count: `0`
- new literal count: `11`
- new literal lines: `57,67,68,69,70`
- `OPENCLAW_ALLOW_MAINNET=1` count: `0`
- `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED` count: `0`
- `RECORD_PROBE_OUTCOMES=1` count: `0`
- `OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES=0` count: `1`
- `systemctl --user openclaw-trading-api.service`: active/enabled, MainPID `2218842`
- `systemctl --user openclaw-watchdog.service`: active/running/enabled

Scope clarification:

- system-level `openclaw-api` and `openclaw-watchdog` are inactive, but those names are not the canonical runtime user-service checks for this API/watchdog posture.

## Concerns

- This checkpoint only removed stale expected-head metadata from crontab. It does not prove profitability, bounded-probe outcome quality, Cost Gate readiness, or order-path safety.
- Scheduled wrappers were not manually run in this checkpoint. The next safe step is a read-only post-alignment hygiene snapshot, not another crontab edit.
- Broad chat authorization is not treated as a machine-checkable bounded-probe grant. Actual AVAX bounded Demo execution remains blocked by the structured authorization gate and fresh E3/BB order-envelope review.

## Boundary

No global Cost Gate lowering, live promotion, probe/order authority grant, Bybit call, PG write, service restart/rebuild, daemon-reload, source sync to docs head, Rust writer/adapter enablement, `_latest` overwrite, or proof/promotion claim occurred.

Proof exclusions remain unchanged: `flash_dip_buy`, cleanup/risk-close, unattributed fills, local stale rows, artifact counts, source-smoke, single-window MM positives, and replay-only results cannot count as bounded-probe or Cost Gate proof.

## Aggressive Profit Hypotheses

1. AVAX false-negative near-touch bounded Demo
   - why it might make money: selected side-cell has a wide modeled net cushion after current costs.
   - fastest safe test: admit machine-checkable bounded Demo authorization, then run fresh E3/BB order-envelope review for one capped post-only near-touch-or-skip design.
   - required data: valid auth object, fresh BBO, cap/min-notional, order/fill/fee/slippage lineage, matched blocked controls.
   - failure condition: no touch, taker fill, stale BBO, missing lineage, net after fees/slippage <= 0, or control underperforms.
   - authority required: structured bounded Demo authorization plus E3/BB.
2. Cron/source false-blocker reduction
   - why it might make money: scheduled learning artifacts can now fail on real trading/evidence issues instead of stale source metadata.
   - fastest safe test: on resume, run a no-mutation hygiene snapshot from current crontab/source/user-service/artifact evidence.
   - required data: runtime source head, crontab snapshot, API/watchdog user-service state, selected artifact mtimes.
   - failure condition: source drift, authority/proof contamination, or mutation requirement appears.
   - authority required: read-only PM/E3 hygiene snapshot.
3. Current-fee maker/MM repeat-window branch
   - why it might make money: repeated maker-positive windows could reduce execution cost without lowering Cost Gate.
   - fastest safe test: accumulate independent current-fee windows and maker-realism scores only.
   - required data: maker/taker fees, queue proxies, spread/markout, distinct dates, matched controls.
   - failure condition: single-window only, net cushion below costs, or maker ratio unrealistic.
   - authority required: research/proposal only.
