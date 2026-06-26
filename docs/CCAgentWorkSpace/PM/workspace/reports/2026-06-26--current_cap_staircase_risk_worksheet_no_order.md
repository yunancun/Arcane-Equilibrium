# Current-Cap Staircase Risk Worksheet No-Order

Date: 2026-06-26 10:26 CEST

本輪把 AVAX 在既有 `10 USDT` per-order cap 下的 executable tier ladder 與 portfolio/survival risk worksheet 做成 machine-checkable source-only helper。沒有 runtime mutation、沒有 manual cron、沒有 PG、沒有 Bybit/API/order/cancel/modify、沒有 Cost Gate/cap/risk mutation、沒有 writer/adapter enablement、沒有 probe/order/live authority、沒有盈利或 proof 宣稱。

## Required Round Output

| Field | Value |
|---|---|
| `active_blocker_id` | `P1-AGGRESSIVE-ALPHA-CURRENT-CAP-STAIRCASE-RISK-WORKSHEET-NO-ORDER` |
| `blocker_goal` | Define a source-only current-cap AVAX executable tier ladder and portfolio/survival risk worksheet without cap/risk/runtime/order mutation or authority. |
| `profit_relevance` | Determines whether the selected AVAX candidate can be sized inside the existing `10 USDT` cap and bounded portfolio exposure before any real risk-adjusted net PnL proof after fees/slippage is attempted. |
| `constraints_checked` | No Cost Gate lowering, no live promotion, no Bybit order/cancel/modify, no PG query/write, no service restart/rebuild, no manual cron run, no `_latest` overwrite, no writer/adapter enablement, no cap/risk mutation, no order/probe/live authority, no proof claim. |
| `previous_evidence_checked` | TODO v564; session state `/tmp/openclaw/session_loop_state_20260626T082031Z_current_cap_staircase_risk_worksheet_no_order.json`; control identity contract smoke; no-order AVAX construction preview; runtime auth mtime `2026-06-26T08:15:05Z`. |
| `new_evidence_delta_required` | Completed control identity contract plus open `cap_staircase_with_discrete_exposure_tiers` and `portfolio_exposure_and_survival_risk_budget_math` gaps; no true P0 authorization delta. |
| `new_evidence_delta_found` | Runtime auth refreshed to sha `4a0aa283...` but remains AVAX defer/no-authority; no-order construction preview shows AVAX constructible under `10 USDT` cap but BBO stale. |
| `anti_repeat_decision` | Proceeded with a distinct source-only staircase/risk helper; skipped P0 authorization because refreshed auth is not authority. |
| `action_taken_or_noop_reason` | Added source-only current-cap staircase/risk worksheet helper, focused tests, script index entry, local smoke, TODO/report/operator/changelog/memory updates. |
| `aggressive_profit_hypotheses` | See table below. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P0-BOUNDED-PROBE-AUTHORIZATION` only if a real candidate-scoped auth delta appears; otherwise `P1-AGGRESSIVE-ALPHA-FEE-SLIPPAGE-MAKER-TAKER-SCHEMA-NO-ORDER`. |
| `why_not_repeating_current_blocker` | Current-cap staircase/risk worksheet is source-backed and smoke-tested; rerunning on the same construction/auth artifacts adds no evidence. |

## Source Change

Added:

- `helper_scripts/research/cost_gate_learning_lane/current_cap_staircase_risk_worksheet.py`
- `helper_scripts/research/tests/test_cost_gate_current_cap_staircase_risk_worksheet.py`

Updated:

- `helper_scripts/SCRIPT_INDEX.md`

The helper emits `cost_gate_current_cap_staircase_risk_worksheet_v1`. It consumes ready/no-authority control identity contract and supplied no-order construction preview artifacts, then fail-closes on Cost Gate lowering, cap/risk/runtime mutation, PG query/write, Bybit/order, probe/order/live authority, or promotion/proof signals.

## Smoke Result

Local no-order smoke:

`/tmp/openclaw/current_cap_staircase_risk_worksheet_smoke_20260626T082031Z/current_cap_staircase_risk_worksheet.json`

Result:

- status: `CURRENT_CAP_STAIRCASE_RISK_WORKSHEET_READY_NO_AUTHORITY`
- candidate: `grid_trading|AVAXUSDT|Sell`
- cap: `10.0 USDT`
- limit price: `6.064`
- qty step: `0.1`
- min notional: `5.0 USDT`
- executable tier count: `8`
- min executable tier: `0.9 AVAX` / `5.4576 USDT`
- max tier under cap: `1.6 AVAX` / `9.7024 USDT`
- review assumption: `3` probe orders / `30.0 USDT` total review cap
- max executable tier reserved notional: `29.1072 USDT`
- cap mutation required: `false`
- risk mutation required: `false`
- order admission ready: `false`
- BBO refresh required before order admission: `true`
- probe/order authority: `false/false`
- promotion/proof: `false/false`

## Verification

```text
PYTHONPATH=helper_scripts/research python3 -m pytest -q \
  helper_scripts/research/tests/test_cost_gate_current_cap_staircase_risk_worksheet.py
6 passed

PYTHONPATH=helper_scripts/research python3 -m pytest -q \
  helper_scripts/research/tests/test_cost_gate_current_cap_staircase_risk_worksheet.py \
  helper_scripts/research/tests/test_cost_gate_source_only_control_identity_contract.py \
  helper_scripts/research/tests/test_cost_gate_bounded_probe_order_construction_repair.py \
  helper_scripts/research/tests/test_cost_gate_false_negative_evidence_floor_gap_closure.py
28 passed

python3 -m py_compile \
  helper_scripts/research/cost_gate_learning_lane/current_cap_staircase_risk_worksheet.py \
  helper_scripts/research/tests/test_cost_gate_current_cap_staircase_risk_worksheet.py
PASS

python3 -m json.tool \
  /tmp/openclaw/session_loop_state_20260626T082031Z_current_cap_staircase_risk_worksheet_no_order.json
PASS

python3 -m json.tool \
  /tmp/openclaw/current_cap_staircase_risk_worksheet_smoke_20260626T082031Z/current_cap_staircase_risk_worksheet.json
PASS

git diff --check
PASS
```

## Aggressive Profit Hypotheses

| Hypothesis | Scores | Why it might make money | Fastest safe test | Required data | Failure condition | Authority required | Max safe next action |
|---|---|---|---|---|---|---|---|
| Fee/slippage/maker-taker evidence schema | expected_net_pnl_upside Medium-High; evidence_strength Medium design-only; execution_realism Low until fills; cost_after_fees critical; time_to_test Fast; risk_to_account None; risk_to_governance Low; autonomy_value High | AVAX is current-cap constructible, so the next proof blocker is whether future rows carry actual fee/slippage/maker-taker labels needed for net PnL. | Source-only schema contract that future result review must enforce. | Fill fees, slippage, maker/taker labels, orderLinkId, exchange order/fill ids, source artifact links. | Any future row has missing fees/slippage/maker-taker labels or proof-exclusion reasons. | None for schema; candidate-scoped bounded auth before any fill path. | Implement fee/slippage/maker-taker schema unless real auth delta appears. |
| Fresh BBO read-only readiness path | expected_net_pnl_upside Medium; evidence_strength Medium; execution_realism Medium after fresh snapshot; cost_after_fees modeled favorable; time_to_test Fast with reviewed read-only path; risk_to_account None; risk_to_governance Low-Medium; autonomy_value Medium | The current cap works, but BBO staleness is a hard order-admission blocker. A fresh read-only snapshot can make sizing/order-envelope review realistic without authority. | Reviewed read-only BBO/instrument snapshot capture only. | Fresh BBO, tick/qty/min-notional, spread, instrument status, timestamp/freshness gate. | BBO stale, spread worsens, instrument not Trading, or min tier no longer fits cap. | PM->E3 for runtime read if needed; no order authority. | Keep as read-only follow-up after schema contract. |
| Micro tier selection for maker placement | expected_net_pnl_upside Medium; evidence_strength Low-Medium; execution_realism Low until fills; cost_after_fees favorable only if maker; time_to_test Medium; risk_to_account None now; risk_to_governance Medium; autonomy_value Medium | Among 8 tiers, smaller tiers may reduce adverse selection and exposure while preserving fill realism for a bounded probe. | Source-only tier policy proposal using current ladder and future fee/slippage schema. | Tier ladder, spread, maker/taker fee model, queue/fill realism, exposure budget. | Tier too small to satisfy min notional, maker fill probability too low, or costs exceed modeled cushion. | Research only; E3/BB + auth before any order. | Defer until fee/slippage schema exists. |

## Status

`DONE_WITH_CONCERNS`.

Concern: AVAX is constructible under the current cap, but the construction preview BBO is stale and there is still no bounded authorization. This is sizing/risk design only, not order admission or profit proof.
