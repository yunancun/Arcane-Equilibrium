# Source-Only Control Identity Contract No-Order

Date: 2026-06-26 10:18 CEST

本輪把 AVAX future proof / matched control / research control 的 identity rules 固定成 machine-checkable source-only contract。沒有 runtime mutation、沒有 manual cron、沒有 PG、沒有 Bybit/API/order/cancel/modify、沒有 Cost Gate/cap/risk mutation、沒有 writer/adapter enablement、沒有 probe/order/live authority、沒有盈利或 proof 宣稱。

## Required Round Output

| Field | Value |
|---|---|
| `active_blocker_id` | `P1-AGGRESSIVE-ALPHA-SOURCE-ONLY-CONTROL-IDENTITY-CONTRACT-NO-ORDER` |
| `blocker_goal` | Define a machine-checkable source-only candidate/control identity contract for future AVAX proof without querying PG, touching Bybit, changing runtime/cap/risk/order state, or granting authority. |
| `profit_relevance` | Prevents false profitability claims by requiring future AVAX proof to match exact candidate side-cell outcomes to admissible blocked controls before any risk-adjusted net PnL after fees/slippage is credited. |
| `constraints_checked` | No Cost Gate lowering, no live promotion, no Bybit order/cancel/modify, no PG query/write, no service restart/rebuild, no manual cron run, no `_latest` overwrite, no writer/adapter enablement, no cap/risk mutation, no order/probe/live authority, no proof claim. |
| `previous_evidence_checked` | TODO v563; session state `/tmp/openclaw/session_loop_state_20260626T081124Z_source_only_control_identity_contract_no_order.json`; gap-closure report; existing result-review/proof-exclusion source; runtime auth artifact mtime `2026-06-26T08:00:05Z`. |
| `new_evidence_delta_required` | Gap-closure design identifying `candidate_matched_controls_present` as open, plus no true P0 authorization delta. |
| `new_evidence_delta_found` | Runtime auth refreshed to sha `2565acf8...` but remains AVAX defer/no-authority; gap-closure smoke supplies a concrete control-identity lane. |
| `anti_repeat_decision` | Proceeded with a distinct source-only contract helper; skipped P0 authorization because refreshed auth is not authority. |
| `action_taken_or_noop_reason` | Added source-only control identity helper, focused tests, script index entry, local smoke, TODO/report/operator/changelog/memory updates. |
| `aggressive_profit_hypotheses` | See table below. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P0-BOUNDED-PROBE-AUTHORIZATION` only if a real candidate-scoped auth delta appears; otherwise `P1-AGGRESSIVE-ALPHA-CURRENT-CAP-STAIRCASE-RISK-WORKSHEET-NO-ORDER`. |
| `why_not_repeating_current_blocker` | Control identity is now source-backed and smoke-tested; rerunning on the same gap/auth artifacts adds no evidence. |

## Source Change

Added:

- `helper_scripts/research/cost_gate_learning_lane/source_only_control_identity_contract.py`
- `helper_scripts/research/tests/test_cost_gate_source_only_control_identity_contract.py`

Updated:

- `helper_scripts/SCRIPT_INDEX.md`

The helper emits `cost_gate_source_only_control_identity_contract_v1`. It consumes a ready/no-authority gap-closure packet and fail-closes on Cost Gate lowering, cap/risk/runtime mutation, PG query/write, Bybit/order, probe/order/live authority, or promotion/proof signals.

## Smoke Result

Local no-order smoke:

`/tmp/openclaw/source_only_control_identity_contract_smoke_20260626T081124Z/control_identity_contract.json`

Result:

- status: `SOURCE_ONLY_CONTROL_IDENTITY_CONTRACT_READY_NO_AUTHORITY`
- candidate: `grid_trading|AVAXUSDT|Sell`
- same-side-cell control required: `true`
- cross-symbol control counts as candidate proof: `false`
- admissible proof outcome: exact `side_cell_key/strategy_name/symbol/side/outcome_horizon_minutes`
- admissible matched control: same-side-cell `blocked_signal_outcome`
- research controls: robustness/candidate-selection/regime context only
- probe/order authority: `false/false`
- promotion/proof: `false/false`

## Verification

```text
PYTHONPATH=helper_scripts/research python3 -m pytest -q \
  helper_scripts/research/tests/test_cost_gate_source_only_control_identity_contract.py
6 passed

PYTHONPATH=helper_scripts/research python3 -m pytest -q \
  helper_scripts/research/tests/test_cost_gate_source_only_control_identity_contract.py \
  helper_scripts/research/tests/test_cost_gate_false_negative_evidence_floor_gap_closure.py
11 passed

PYTHONPATH=helper_scripts/research python3 -m pytest -q \
  helper_scripts/research/tests/test_cost_gate_bounded_probe_result_review.py \
  helper_scripts/research/tests/test_cost_gate_bounded_probe_execution_realism_review.py
18 passed

python3 -m py_compile \
  helper_scripts/research/cost_gate_learning_lane/source_only_control_identity_contract.py \
  helper_scripts/research/tests/test_cost_gate_source_only_control_identity_contract.py
PASS

PYTHONPATH=helper_scripts/research python3 -m pytest -q \
  helper_scripts/research/tests/test_cost_gate_source_only_control_identity_contract.py \
  helper_scripts/research/tests/test_cost_gate_false_negative_evidence_floor_gap_closure.py \
  helper_scripts/research/tests/test_cost_gate_bounded_probe_result_review.py \
  helper_scripts/research/tests/test_cost_gate_bounded_probe_execution_realism_review.py
29 passed

python3 -m json.tool \
  /tmp/openclaw/session_loop_state_20260626T081124Z_source_only_control_identity_contract_no_order.json
PASS

python3 -m json.tool \
  /tmp/openclaw/source_only_control_identity_contract_smoke_20260626T081124Z/control_identity_contract.json
PASS

git diff --check
PASS
```

## Aggressive Profit Hypotheses

| Hypothesis | Scores | Why it might make money | Fastest safe test | Required data | Failure condition | Authority required | Max safe next action |
|---|---|---|---|---|---|---|---|
| AVAX current-cap staircase + risk worksheet | expected_net_pnl_upside Medium; evidence_strength Medium-Low; execution_realism Low; cost_after_fees modeled favorable; time_to_test Fast; risk_to_account None now; risk_to_governance Low-Medium; autonomy_value High | If AVAX can be represented as discrete executable tiers inside the existing `10 USDT` cap, a future bounded probe can be sized without cap mutation. | Source-only worksheet using current cap and reviewed read-only instrument metadata path. | Cap, BBO, tick/qty/min-notional, max orders, portfolio exposure budget, survival envelope. | First executable tier exceeds approved cap or portfolio exposure cannot stay inside current envelope. | None for worksheet; operator/QC/E3/BB for any cap/risk mutation. | Implement source-only current-cap staircase/risk worksheet unless real auth delta appears. |
| Fee/slippage/maker-taker evidence schema | expected_net_pnl_upside Medium; evidence_strength Medium design-only; execution_realism Low until fills; cost_after_fees critical; time_to_test Fast; risk_to_account None; governance Low; autonomy_value High | AVAX modeled edge can only become real net PnL if future rows carry actual fee/slippage/maker-taker labels. | Source-only schema contract that future result review must enforce. | Fill fees, slippage, maker/taker, orderLinkId, exchange order/fill ids, source artifact links. | Any future row has missing fees/slippage/maker-taker or proof-exclusion reasons. | None for schema; bounded auth before any fill path. | Keep as next evidence-floor sub-contract after cap/risk worksheet. |
| Regime/OOS label contract | expected_net_pnl_upside Medium; evidence_strength Low-Medium; execution_realism Medium source-only; cost_after_fees unknown; time_to_test Medium; risk_to_account None; governance Low; autonomy_value High | A leak-free regime/OOS contract can prevent probing a bull-only or stale false-negative artifact. | Define source-only label/join contract before any PG/runtime query. | Point-in-time regime labels, symbol breadth, freshness, survivorship, distinct dates, OOS splits. | Labels are stale, leaky, not tied to signal timestamps, or single-window only. | None for design; reviewed read-only path for runtime/PG labels later. | Defer until cap/risk and fee/schema contracts exist. |

## Status

`DONE_WITH_CONCERNS`.

Concern: this is a contract, not evidence of realized profit. AVAX still has no candidate-matched fills, no bounded authorization, and no proof-grade outcome. P0 authorization remains blocked/no-repeat.
