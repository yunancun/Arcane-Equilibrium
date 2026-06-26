# Health [68] Local Lineage Residual Source Patch

Date: 2026-06-26 05:50 CEST

## State

- `active_blocker_id`: `P1-RUNTIME-HEALTH-HYGIENE-LOCAL-LINEAGE-68-STALE-WORKING`
- `status`: `DONE_WITH_CONCERNS`
- `session_loop_state`: `/tmp/openclaw/session_loop_state_20260626T_p1_health68_local_lineage.json`
- `next_blocker_id`: `P1-RUNTIME-HEALTH-HYGIENE-68-RUNTIME-SYNC-REVIEW`

Anti-repeat result:

- `P1-LEARNING-LOOP-CLOSURE` -> `NO-OP_ALREADY_DONE` because `2026-06-24--learning_ssot_decision_packet.md` already closed the durable learning SSOT decision.
- `P1-AUTONOMOUS-PARAMETER-PROPOSAL` -> `NO-OP_ALREADY_DONE` because `2026-06-24--autonomous_parameter_proposal_contract.md` already closed the reviewable-proposal contract.
- Health [68] local-lineage blocker proceeded because the v536 cleanup produced new evidence: exchange full-scan clean, while [68] still failed from local close/risk `Working` rows.

## Evidence

The v536 cleanup report recorded an independent post-action demo exchange inventory with open orders `0` and nonzero positions `0`, but passive health [68] still saw demo `working_n=4`, `resting=398`, `filled=0`.

The local rows matched close/risk lineage shapes, not fresh entry exposure:

- `oc_close_mf_fb_dm_1782442166742_135`
- `oc_risk_dm_1782442146668_133`
- `oc_risk_dm_1782440967557_121`
- `oc_close_mf_fb_dm_1782440965566_120`

## Change

`helper_scripts/db/passive_wait_healthcheck/checks_portfolio_resting_exposure.py` now splits Working rows into ordinary entry exposure and narrow close/risk lineage rows:

- order prefixes: `oc_risk_`, `oc_close_`, `oc_ipc_close_`
- strategy prefixes: `risk_close:`, `strategy_close:`

Close/risk Working rows with no same-symbol local filled position are excluded from entry resting exposure and surfaced in the [68] message as:

- `local_lineage_residual_n`
- `local_lineage_residual_notional`

Close/risk Working rows with a same-symbol local filled position are merged back into resting exposure and still drive divergence. Ordinary entry Working rows are unchanged and still fail closed under the existing thresholds.

## Review

E2 verdict: `DONE`.

- No P0/P1 blocker found.
- The classifier is narrow and does not hide ordinary entry exposure.
- Close/risk rows with a filled position are still counted.

E4 verdict: `DONE_WITH_CONCERNS`.

- `py_compile` and focused pytest passed.
- E4 requested coverage for `oc_ipc_close_` and strategy-prefix-only rows whose order id does not start with `oc_*`.
- That concern was addressed before close by adding test rows for `oc_ipc_close_`, `risk_close:` and `strategy_close:` external order ids.

## Verification

Commands run on Mac/source checkout:

```bash
python3 -m py_compile helper_scripts/db/passive_wait_healthcheck/checks_portfolio_resting_exposure.py
python3 -m pytest -q helper_scripts/db/test_portfolio_resting_exposure_healthcheck.py
python3 -m pytest -q helper_scripts/db/test_portfolio_resting_exposure_healthcheck.py helper_scripts/db/test_wp03_deploy_gate_healthcheck.py
git diff --check
```

Result: focused and adjacent pytest returned `30 passed`; `py_compile` and `git diff --check` passed.

## Boundaries

No runtime source sync, service restart, rebuild, crontab/env mutation, PG write, Rust writer enablement, adapter enablement, Bybit order/cancel/modify, Cost Gate change, live action, probe/order authority, or profitability proof was performed.

This source patch is not a bounded Demo proof. It does not count any cleanup/risk-close/unattributed/local-stale row toward Cost Gate, promotion, or net-PnL proof.

## Concerns

- The patch is source-only and is not synced to Linux runtime. Runtime passive health [68] will not reflect it until a separate source-sync/review checkpoint.
- Runtime PG schema compatibility was not probed in this checkpoint; source migration V003 includes `trading.orders.strategy_name`, and the local tests cover backward-compatible 4-column fixtures.

## Aggressive Profit Hypotheses

1. AVAX false-negative near-touch bounded Demo: high upside if the selected `grid_trading|AVAXUSDT|Sell` side-cell can produce candidate-matched post-only fills after a valid bounded Demo authorization and fresh E3/BB order-envelope review. Failure condition: no touch, taker fill, stale BBO, missing lineage, or net after fees/slippage <= 0.
2. Health [68] false-blocker reduction: medium upside because removing a local lineage false-red can unblock safe candidate review faster without weakening exchange truth. Fastest safe test: separate runtime source-sync review plus read-only [68] recheck.
3. Current-fee maker/MM repeat-window branch: medium upside but low evidence; safest next step is research-only accumulation of independent maker-positive windows with queue/spread/markout realism, not order authority.
