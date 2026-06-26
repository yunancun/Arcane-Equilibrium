# Authorization Gate Status Clarity Source Fix

Date: 2026-06-26 08:46 CEST

本輪是 source-only clarity fix + TODO hygiene。沒有 runtime sync、沒有手動 cron、沒有 `_latest` 覆寫、沒有 PG、沒有 Bybit/API/order/cancel/modify、沒有 Cost Gate/cap/risk mutation、沒有 writer/adapter enablement、沒有 probe/order/live authority。

## Required Round Output

| Field | Value |
|---|---|
| `active_blocker_id` | `P1-AUTHORIZATION-GATE-STATUS-CLARITY-SOURCE-FIX` |
| `blocker_goal` | Make bounded authorization artifacts classify false-negative preflight/operator-review blockers accurately instead of reporting misleading sealed-horizon status, without granting authority or changing runtime behavior. |
| `profit_relevance` | Reduces wasted authorization/review cycles and keeps the system pointed at the exact gate before any candidate-matched, fee/slippage-aware Demo PnL evidence can exist. |
| `constraints_checked` | No Cost Gate lowering, no live promotion, no Bybit order/cancel/modify, no PG write, no service restart/rebuild, no runtime sync, no manual cron run, no `_latest` overwrite, no writer/adapter enablement, no order/probe authority, no proof claim. |
| `previous_evidence_checked` | v555 AVAX latest-chain review; fresh `08:29/08:30 CEST` AVAX runtime artifacts; bounded authorization source/tests; TODO maintenance standard. |
| `new_evidence_delta_required` | Source-only clarity gap between false-negative preflight schema/status and sealed-horizon authorization status wording. |
| `new_evidence_delta_found` | AVAX false-negative preflight is `OPERATOR_REVIEW_REQUIRED`, but bounded authorization previously emitted `SEALED_HORIZON_PREFLIGHT_NOT_READY`, hiding the real false-negative operator-review gate. |
| `anti_repeat_decision` | Proceed with source-only classification fix; do not repeat P0 authorization read-only audit because no candidate-scoped auth delta exists. |
| `action_taken_or_noop_reason` | Implemented fail-closed false-negative preflight status/gate labels, updated scorecard/discovery classifications, added focused regression coverage, and compressed `TODO.md` to active-queue shape. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P1-RUNTIME-HEALTH-HYGIENE-AUTH-STATUS-CLARITY-SYNC-REVIEW` after the operator-requested pause; `P0-BOUNDED-PROBE-AUTHORIZATION` remains blocked until real auth evidence changes. |
| `why_not_repeating_current_blocker` | Source fix and tests are complete; repeating it without source/runtime artifact evidence changes would be anti-repeat noise. |

## Source Changes

- `helper_scripts/research/cost_gate_learning_lane/bounded_probe_operator_authorization.py`
  - Added false-negative preflight constants.
  - Preserved schema version in preflight summary.
  - Emits `false_negative_preflight_ready` when the preflight schema is `cost_gate_false_negative_bounded_demo_probe_preflight_v1`.
  - Emits `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED` for `OPERATOR_REVIEW_REQUIRED`; otherwise `FALSE_NEGATIVE_PREFLIGHT_NOT_READY`.
- `helper_scripts/research/alpha_discovery_throughput/profitability_path_scorecard.py`
  - Treats the new false-negative statuses as authorization gates not ready.
  - Adds proof-gate label and next-move class for false-negative operator review.
- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
  - Marks `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED` as operator-actionable.
  - Marks `FALSE_NEGATIVE_PREFLIGHT_NOT_READY` as engineering-actionable.
- `helper_scripts/research/tests/test_cost_gate_bounded_probe_operator_authorization.py`
  - Adds fail-closed coverage proving no authorization object, no active runtime probe/order authority, and no Cost Gate lowering.

## Verification

```text
python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_operator_authorization.py
19 passed

python3 -m pytest -q helper_scripts/research/tests/test_profitability_path_scorecard.py
18 passed

python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_throughput.py -k 'bounded_probe_operator_authorization or profitability_closure or runtime_killboard'
6 passed, 78 deselected

python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/bounded_probe_operator_authorization.py helper_scripts/research/alpha_discovery_throughput/profitability_path_scorecard.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py
PASS

git diff --check
PASS
```

## TODO Hygiene

`TODO.md` was reduced to active-dispatch shape:

- compact masthead only
- current runtime facts with timestamps/evidence
- one active state-machine table
- short active queue with executable next action / wait condition
- hard gates
- aggressive alpha backlog
- handoff commands

Completed long evidence remains in reports/changelog, not TODO.

## Aggressive Profit Hypotheses

| Hypothesis | Scores | Why it might make money | Fastest safe test | Required data | Failure condition | Authority required | Max safe next action |
|---|---|---|---|---|---|---|---|
| AVAX candidate-scoped authorization admission | expected_net_pnl_upside High path-enabler; evidence_strength High for route; execution_realism blocked by auth; cost_after_fees unchanged; time_to_test Fast if valid auth appears; risk_to_account None now; risk_to_governance Medium; autonomy_value High | AVAX is selected, cap-feasible, and current-fee false-negative positive. A valid scoped auth is the next gate before bounded Demo can create real fill/PnL evidence. | Review only a new scoped auth/typed-confirm/standing-auth artifact delta; no self-grant. | Exact candidate-scoped false-negative preflight approval and bounded probe authorization evidence. | No exact scoped auth, stale candidate, or any authority contamination. | E3/BB review before any order/probe path. | Stop at auth gate unless the artifact delta is real. |
| AVAX near-touch first-attempt design | upside Medium-High; evidence Medium; execution_realism pending; cost_after_fees favorable if maker/touchable; time_to_test Medium; risk_to_account None now; risk_to_governance Low; autonomy_value Medium | Current placement artifacts suggest first-attempt touchability is the next execution-realism bottleneck; near-touch-or-skip could avoid dead passive orders. | Source-only design review after authorization gate is satisfiable. | Touchability, placement repair, BBO freshness, fill lineage, maker/taker fee assumptions. | Candidate-matched touch sample absent, spread expands, or maker edge disappears after fees/slippage. | Design/proposal only until authorization exists. | Keep as bounded-demo design packet, not an order. |
| ETH cap-envelope research | upside High if a safe cap envelope exists; evidence Low-Medium; execution_realism Low under current cap; cost_after_fees good in modeled sample; time_to_test Medium; risk_to_account None now; risk_to_governance Medium; autonomy_value Medium | ETH Buy modeled edge is high, but current `10 USDT` cap makes it non-constructible. A future envelope might unlock larger notional symbols. | Source-only cap sensitivity and min-notional construction analysis. | Construction previews, fee/slippage model, controls, cap/risk envelope. | Min executable notional stays above any approved cap or edge collapses under realistic costs. | QC/operator/E3/BB for any future cap mutation. | Research packet only; no cap mutation. |

## Status

`DONE_WITH_CONCERNS`.

Concern: v556 is not runtime-synced. Runtime artifacts will keep old wording until a separate reviewed sync applies the source fix. The operator requested a pause after this round, so the next action is queued but not executed here.
