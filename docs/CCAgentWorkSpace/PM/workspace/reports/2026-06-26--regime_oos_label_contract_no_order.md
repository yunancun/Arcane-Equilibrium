# Regime/OOS Label Contract No-Order

Date: 2026-06-26 16:35 CEST

本輪只推進 source-only label/proof contract，沒有 runtime mutation、沒有 PG query/write、沒有 Bybit/API/order/cancel/modify、沒有 private fee read、沒有 Cost Gate/freshness-gate lowering、沒有 probe/order/live authority、沒有盈利或 proof 宣稱。Operator 要求本輪跑完後暫停並整理 TODO，已將 TODO 壓回 active dispatch queue 格式。

## Required Round Output

| Field | Value |
|---|---|
| `active_blocker_id` | `P1-AGGRESSIVE-ALPHA-REGIME-OOS-LABEL-CONTRACT-NO-ORDER` |
| `blocker_goal` | Define a source-only regime/OOS/freshness/survivorship label contract for future AVAX proof rows before any PG/runtime label query, order path, or proof claim. |
| `profit_relevance` | Prevents probing or promoting a bull-only, stale-window, survivor-biased, or single-window false-negative artifact; keeps future Demo evidence portable to live review and tied to real net PnL after fees/slippage. |
| `constraints_checked` | No Cost Gate lowering, no freshness-gate lowering, no live promotion, no Bybit order/cancel/modify/private read, no PG query/write, no runtime/service/env/crontab mutation, no writer/adapter enablement, no cap/risk mutation, no order/probe/live authority, no proof claim. |
| `previous_evidence_checked` | TODO v587; session state `/tmp/openclaw/session_loop_state_20260626T1420Z_regime_oos_label_contract_no_order.json`; reports for cap-feasible filter, evidence-floor gap closure, source-only control identity, and anti-repeat ladder reconciliation; latest runtime auth artifact sha `6d301632...`. |
| `new_evidence_delta_required` | An unclosed source-only regime/OOS/freshness/survivorship label gap plus no admitted P0 auth delta. |
| `new_evidence_delta_found` | Prior reports explicitly left `regime_breadth_freshness_survivorship_labels` and `repeat_or_oos_path_before_any_promotion_claim` open; no existing `regime_oos_label_contract.py`; latest auth remains defer/no-authority. |
| `anti_repeat_decision` | P0 authorization: no-op/no admitted auth delta. Completed AVAX ladder: no-op except this unclosed label contract gap. Proceeded with distinct source-only contract. |
| `action_taken_or_noop_reason` | Added source-only helper/tests, SCRIPT_INDEX entry, local smoke, TODO v588, PM report, changelog/worklog entries. |
| `aggressive_profit_hypotheses` | See table below. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `PAUSED-AFTER-V588-OPERATOR-REQUEST`; on resume, check `P0-BOUNDED-PROBE-AUTHORIZATION` only for a real candidate-scoped auth delta. |
| `why_not_repeating_current_blocker` | Regime/OOS label contract is now source-backed, smoke-tested, and recorded as no-repeat. Rerunning on the same gap/control/auth artifacts adds no evidence. |

## Source Change

Added:

- `helper_scripts/research/cost_gate_learning_lane/regime_oos_label_contract.py`
- `helper_scripts/research/tests/test_cost_gate_regime_oos_label_contract.py`

Updated:

- `helper_scripts/SCRIPT_INDEX.md`
- `TODO.md`

The helper emits `cost_gate_regime_oos_label_contract_v1`. It consumes ready/no-authority gap-closure and control-identity inputs, requires exact AVAX candidate identity, and fails closed on authority/proof/cost-gate/order-admission aliases, not-ready upstream packets, candidate mismatch, or missing required gap keys.

## Smoke Result

Local no-order smoke:

`/tmp/openclaw/regime_oos_label_contract_smoke_20260626T1420Z/regime_oos_label_contract.json`

Result:

- sha256: `739f684258bf1b21ba26f44b1cf964f54a46eee94a5f31f7b9c949b0c3c8a9a7`
- status: `REGIME_OOS_LABEL_CONTRACT_READY_NO_AUTHORITY`
- candidate: `grid_trading|AVAXUSDT|Sell`
- requires PIT regime, market-anchor regime, overlay flags
- requires freshness bucket and recent 90d/180d net fields
- requires point-in-time breadth/survivorship mode
- requires repeat/OOS split, purge/embargo, `n_independent`, `sample_unit`, final verdict and reject reasons
- encodes ADR-0047 downgrades for bull-heavy/rally-only, stale/2024-dominated, survivor-only/narrow breadth, and insufficient non-bull positives
- PG/Bybit/order/probe/live/promotion/proof flags: all false

## Review And Fixes

- PA returned `DONE_WITH_CONCERNS`: source-only contract is the correct next helper if it stays no-authority and includes ADR-0047 evidence matrix requirements.
- E2 first found two HIGH fail-closed gaps:
  - sensitive aliases like `authorizationId`, `cost_gate_proof`, and `orderAdmissionReady` were not rejected
  - incomplete candidate identity could still READY if both inputs omitted the same fields
- PM fixed both:
  - added normalized camelCase/snake_case sensitive-key scan and non-empty contamination detection
  - required all five candidate fields before exact match
  - added regression tests for both cases
- E2 re-check returned `DONE`.

## Verification

```text
PYTHONPATH=helper_scripts/research python3 -m pytest -q \
  helper_scripts/research/tests/test_cost_gate_regime_oos_label_contract.py
9 passed

PYTHONPATH=helper_scripts/research python3 -m pytest -q \
  helper_scripts/research/tests/test_cost_gate_regime_oos_label_contract.py \
  helper_scripts/research/tests/test_cost_gate_source_only_control_identity_contract.py \
  helper_scripts/research/tests/test_cost_gate_false_negative_evidence_floor_gap_closure.py
20 passed

python3 -m py_compile \
  helper_scripts/research/cost_gate_learning_lane/regime_oos_label_contract.py \
  helper_scripts/research/tests/test_cost_gate_regime_oos_label_contract.py
PASS

git diff --check
PASS
```

E4 final rerun returned `DONE`: adjacent suite `20 passed`, `py_compile` passed, `git diff --check` passed, and no runtime/PG/Bybit/ssh/service/cron/order/network actions were run.

## Aggressive Profit Hypotheses

| Hypothesis | Scores | Why it might make money | Fastest safe test | Required data | Failure condition | Authority required | Max safe next action |
|---|---|---|---|---|---|---|---|
| AVAX regime/OOS-gated bounded probe | expected_net_pnl_upside Medium-High; evidence_strength Medium design-only; execution_realism Medium after fills; cost_after_fees depends on actual maker ratio; time_to_test Medium; risk_to_account None now; risk_to_governance Low; autonomy_value High | AVAX is current cap-feasible and has modeled cushion, but only a non-leaky regime/OOS gate can stop the system from mistaking bull/stale/survivor bias for durable edge. | Source-only label contract, then future reviewed read-only label join before any outcome proof. | PIT regime labels, market anchor, overlays, freshness bucket, recent 90d/180d net, PIT universe/survivorship, OOS split, purge/embargo, candidate-matched fills and controls. | Labels are stale/leaky/current-survivor-only, thresholds moved after scoring, no OOS/repeat path, or controls beat probe after costs. | None for contract; PM->E3 review for runtime/PG label query; candidate-scoped auth before any order/fill path. | Pause now per operator request; on resume check real P0 auth delta before any more source-only work. |
| Maker-fee + regime intersection | expected_net_pnl_upside Medium; evidence_strength Low-Medium; execution_realism Medium; cost_after_fees High sensitivity; time_to_test Medium; risk_to_account None now; risk_to_governance Low; autonomy_value Medium | The AVAX edge may exist only when maker execution and non-stale regime labels align; filtering can raise risk-adjusted net PnL even if raw false-negative basket is noisy. | Combine future fee-tier/maker-ratio proof fields with the regime/OOS contract in result-review criteria. | Actual account fee tier, maker/taker labels, fill fees/slippage, regime labels at signal time, matched controls. | Maker ratio falls below threshold, stale labels dominate positives, or net after all-in cost is not positive OOS. | No authority for design; private fee read and probe both require separate reviewed gates. | Keep as review criterion, not a runtime mutation. |
| Cross-symbol research controls as falsification only | expected_net_pnl_upside Medium; evidence_strength Medium context-only; execution_realism Low for proof; cost_after_fees unknown; time_to_test Fast; risk_to_account None; risk_to_governance Low; autonomy_value Medium | SUI/FIL-like false-negative controls can reveal whether AVAX edge is unique or just broad regime beta, reducing bad probes. | Use cross-symbol labels only as robustness context while same-side-cell controls remain proof-required. | Cross-symbol blocked outcomes, PIT labels, same-side-cell AVAX controls, fees/slippage. | Cross-symbol positives are counted as AVAX proof, or AVAX cannot beat same-side-cell controls after costs. | None for source-only analysis; no order/probe authority. | Preserve proof exclusion: cross-symbol rows never satisfy AVAX bounded-probe proof. |

## Status

`DONE_WITH_CONCERNS`.

Concern: this closes a proof-contract gap only. AVAX still has no candidate-matched fills, no bounded authorization, no private fee proof, and no realized risk-adjusted net PnL proof. Per operator request, the session should pause after commit/push.
