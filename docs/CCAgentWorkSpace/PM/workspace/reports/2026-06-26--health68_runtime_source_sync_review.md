# Health [68] Runtime Source Sync Review

Date: 2026-06-26 06:08 CEST

## State

- `active_blocker_id`: `P1-RUNTIME-HEALTH-HYGIENE-68-RUNTIME-SYNC-REVIEW`
- `status`: `DONE_WITH_CONCERNS`
- `session_loop_state`: `/tmp/openclaw/session_loop_state_20260626T035820Z_health68_runtime_sync_review.json`
- `next_blocker_id`: `P1-RUNTIME-HEALTH-HYGIENE-CRON-EXPECTED-HEAD-DRIFT-REVIEW`

Anti-repeat result:

- `P1-RUNTIME-HEALTH-HYGIENE-LOCAL-LINEAGE-68-STALE-WORKING` -> `NO-OP_ALREADY_DONE`; the source patch is already committed and pushed at `0246b263`.
- Runtime-sync review proceeded because Linux `trade-core` was still at `d2cd70d0` while Mac/origin had `0246b263`.

## E3 Review

E3 returned `DONE_WITH_CONCERNS` and allowed exactly one source-only fast-forward to `0246b26361e403e6cb1ddd126eba8e3cd7b91a23`.

Allowed class:

- preflight over SSH
- `git fetch origin main`
- verify `FETCH_HEAD == 0246b263...`
- verify current Linux `HEAD == d2cd70d0` and clean worktree
- `git merge --ff-only FETCH_HEAD`
- post-sync read-only status, no-cache Python tests, and direct [68] invocation in a PG read-only transaction

Forbidden class:

- restart/rebuild
- Linux cargo
- non-fast-forward merge/reset/checkout
- crontab or persistent env mutation
- PG write
- Bybit call of any kind
- control API POST
- `demo_exchange_inventory_readonly.py`
- real `control_api_csrf_post.py`
- adapter/Rust writer enablement
- Cost Gate change
- `_latest` artifact overwrite
- probe/order/live authority
- proof/promotion claims

## Runtime Preflight

At `2026-06-26T04:02:37Z`:

- Linux head: `d2cd70d092916194043e112eeb402fb92bacb699`
- Linux worktree status count: `0`
- remote `origin/main`: `0246b26361e403e6cb1ddd126eba8e3cd7b91a23`
- API MainPID: `2218842`
- crontab `OPENCLAW_ALLOW_MAINNET=1` count: `0`
- crontab `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED` count: `0`
- crontab expected-head `d2cd70d0` count: `5`

Baseline old-runtime [68] via existing wrapper full `--quiet` output:

- healthcheck rc: `1`
- [68] status: `FAIL`
- demo `working_n=4`
- demo `resting=398`
- demo `filled=0`
- divergence critical

## Sync Action

Command class: `git fetch origin main` followed by `git merge --ff-only FETCH_HEAD`, after verifying exact `FETCH_HEAD`.

Result:

- Linux fast-forwarded `d2cd70d0..0246b263`
- post-sync Linux head: `0246b26361e403e6cb1ddd126eba8e3cd7b91a23`
- post-sync worktree status count: `0`

No restart, rebuild, crontab/env mutation, PG write, Bybit/API call, adapter/writer enablement, Cost Gate change, or authority grant occurred.

## Post-Checks

At `2026-06-26T04:03:34Z`:

- Linux head: `0246b26361e403e6cb1ddd126eba8e3cd7b91a23`
- Linux worktree status count: `0`
- API MainPID: `2218842`
- API service: `active`
- watchdog service: `active`
- process `OPENCLAW_ALLOW_MAINNET=1` count: `0`
- process bounded adapter flag count: `0`
- crontab `OPENCLAW_ALLOW_MAINNET=1` count: `0`
- crontab bounded adapter flag count: `0`
- crontab expected-head `d2cd70d0` count: `5`
- crontab expected-head `0246b263` count: `0`
- `git diff --check`: passed

Linux no-cache source tests:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider \
  helper_scripts/db/test_portfolio_resting_exposure_healthcheck.py \
  helper_scripts/db/test_wp03_deploy_gate_healthcheck.py
```

Result: `30 passed`.

Direct [68] invocation in a PG read-only transaction:

- `transaction_read_only_before=on`
- `transaction_read_only_after=on`
- `check68_status=PASS`
- demo `resting=0`
- demo `working_n=0`
- `local_lineage_residual_n=2`
- `local_lineage_residual_notional=398`

This proves the runtime source now classifies the stale close/risk local rows as visible local lineage residuals instead of entry resting exposure.

## Concerns

- The fast-forward brought in intermediate helper/report commits in addition to the [68] file. E3 explicitly forbade invoking the new Bybit inventory helper or CSRF POST helper in this checkpoint; PM did not invoke them.
- Crontab expected-head pins still reference `d2cd70d0` in 5 entries. This can cause scheduled wrapper/source-head drift signals. Fixing it requires a separate PM -> E3 crontab expected-head review.
- No fresh Bybit exchange inventory was collected in this checkpoint. The prior clean exchange evidence remains from the v536 cleanup report; this checkpoint proves [68] runtime behavior, not exchange state.

## Boundary

This checkpoint did not grant bounded Demo authorization, probe/order authority, Cost Gate lowering, promotion proof, or risk-adjusted net PnL proof. Local stale rows, cleanup/risk-close rows, unattributed fills, `flash_dip_buy`, artifact counts, source-smoke, single-window MM positives, and replay-only results remain proof-excluded.

## Aggressive Profit Hypotheses

1. AVAX false-negative near-touch bounded Demo
   - Why it might make money: selected AVAX side-cell still has wide modeled net cushion.
   - Fastest safe test: only after valid bounded Demo authorization plus fresh E3/BB order-envelope review.
   - Failure condition: no touch, taker fill, stale BBO, missing lineage, or net after fees/slippage <= 0.
   - Authority: structured bounded Demo authorization required.
2. Health [68] false-blocker reduction
   - Why it might make money: false health red removal lets candidate review advance without hiding real entry exposure.
   - Fastest safe test: crontab expected-head review so scheduled wrappers stop reporting old source drift.
   - Failure condition: scheduled wrapper source mismatch masks health state or any ordinary entry Working row is hidden.
   - Authority: PM -> E3 crontab review required.
3. Current-fee maker/MM repeat-window branch
   - Why it might make money: repeated maker-positive windows could reduce cost pressure without lowering Cost Gate.
   - Fastest safe test: research-only repeat-window accumulation with maker-realism metrics.
   - Failure condition: single-window only, markout adverse, or net cushion below fees/slippage.
   - Authority: research/proposal only.
