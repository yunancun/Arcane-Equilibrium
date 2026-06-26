# TODO Source Pointer Drift Correction

Date: 2026-06-26 16:56 CEST

本輪只修 active dispatch queue 的 source 指針漂移。沒有重跑 P0 授權 audit，沒有新增研究 helper，沒有 private fee read、Bybit/API/order/cancel/modify、PG query/write、runtime/service/env/crontab mutation、Cost Gate lowering、writer/adapter enablement、probe/order/live authority，亦沒有 proof/profit claim。

## Required Round Output

| Field | Value |
|---|---|
| `active_blocker_id` | `P1-TODO-MAINTENANCE-SOURCE-POINTER-DRIFT-CORRECTION` |
| `blocker_goal` | Correct TODO v590 source/origin pointer drift while preserving semantic anti-repeat for P0 authorization. |
| `profit_relevance` | A correct active queue prevents the loop from chasing stale source state and keeps attention on the only current profit unlock: candidate-scoped bounded Demo authorization followed by matched after-fee outcomes. |
| `constraints_checked` | No Cost Gate lowering, no freshness-gate lowering, no live promotion, no Bybit order/cancel/modify/private read, no PG query/write, no runtime/service/env/crontab mutation, no writer/adapter enablement, no cap/risk mutation, no order/probe/live authority, no proof claim. |
| `previous_evidence_checked` | TODO v590; PM report `2026-06-26--p0_auth_semantic_delta_noop_no_authority.md`; session state `/tmp/openclaw/session_loop_state_20260626T1456Z_todo_source_pointer_drift_correction.json`; runtime auth/review/preflight artifacts. |
| `new_evidence_delta_required` | TODO masthead/source pointer drift or semantic P0 auth delta. |
| `new_evidence_delta_found` | TODO v590 masthead pointed to source/origin `53568ce5...` while current source/origin pre-v591 checkpoint is `cafbef04...`. Runtime P0 auth semantics did not change. |
| `anti_repeat_decision` | `DONE_WITH_CONCERNS`: source-only TODO drift was actionable; P0 authorization remains `NO-OP_NO_EVIDENCE_DELTA` / `BLOCKED_BY_RUNTIME_AUTHORIZATION`. |
| `action_taken_or_noop_reason` | Updated TODO to v591, added changelog/worklog entries, and recorded this short PM report. |
| `aggressive_profit_hypotheses` | See table below. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P0-BOUNDED-PROBE-AUTHORIZATION` only if a semantic auth delta appears; otherwise `WAIT_FOR_SEMANTIC_P0_AUTH_DELTA_OR_SEPARATELY_REVIEWED_RUNTIME_SCOPE`. |
| `why_not_repeating_current_blocker` | The only new delta was TODO metadata drift. Bounded auth remains defer/no-auth/no typed-confirm/no probe-order authority, so repeating P0 audit would violate anti-repeat. |

## Runtime Evidence

- Source/origin pre-v591 checkpoint: `cafbef0481158de23826497d876d60f446a0b3f0`.
- Runtime source: `b224c759200d8dfc6fc4a53cbee39b8fb3683118`, read-only at `2026-06-26T14:55:39Z`; runtime is behind source/origin by docs/TODO/report-only commits.
- Bounded auth latest: sha `310a5ed51f21460ff673da2474241bc434227fadc8bc8392a8f79f0586279632`, mtime `2026-06-26T14:45:04.954460Z`, status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, `decision=defer`, candidate `grid_trading|AVAXUSDT|Sell`, no `authorization_id`, no typed confirm match, no probe/order authority.
- False-negative review remains `PENDING_COST_GATE_FALSE_NEGATIVE_OPERATOR_REVIEW`, expected preflight confirm `approve_cost_gate_false_negative_preflight:grid_trading|AVAXUSDT|Sell:2`, match `false`.
- Preflight remains `OPERATOR_REVIEW_REQUIRED`.

## Aggressive Profit Hypotheses

| Hypothesis | Scores | Why it might make money | Fastest safe test | Required data | Failure condition | Authority required | Max safe next action |
|---|---|---|---|---|---|---|---|
| AVAX maker-first bounded Demo micro-probe | expected_net_pnl_upside High; evidence_strength Medium-High design; execution_realism Medium; cost_after_fees critical; time_to_test Medium if auth appears; risk_to_account None now; risk_to_governance Low now; autonomy_value High | AVAX remains the current cap-feasible false-negative candidate with prior source-only proof scaffolding; a bounded, attributed Demo probe could finally produce real matched after-fee outcomes. | Wait for semantic scoped auth delta, then PM -> E3 -> BB review. | Auth object or exact typed confirm, fresh preview/BBO, Decision Lease/Rust admission, fills with fee/slippage lineage and controls. | No scoped auth, stale BBO, missing lineage, or net PnL after fees/slippage <= 0. | Candidate-scoped bounded Demo authorization plus E3/BB. | Do not order; keep TODO pointer accurate and wait for semantic auth delta. |
| Private fee-tier one-shot read | expected_net_pnl_upside Medium; evidence_strength Medium design-only; execution_realism High for fee truth; cost_after_fees High impact; time_to_test Medium; risk_to_account None now; risk_to_governance Medium if bypassed; autonomy_value Medium | Actual maker/taker account fees can validate or kill modeled AVAX edge without lowering the global Cost Gate. | Separate one-shot PM -> E3 -> BB private read checkpoint. | Exact `AVAXUSDT` fee row, sanitized artifact, strict parser, no cache replacement. | Endpoint unsupported, row missing/malformed, secret leakage, or artifact reused as proof. | Fresh runtime/exchange-facing read authorization. | Keep blocked; do not read private API in this round. |
| Fresh low-price false-negative rerank only on real artifact delta | expected_net_pnl_upside Medium; evidence_strength Medium; execution_realism Medium; cost_after_fees mixed; time_to_test Fast after data delta; risk_to_account None; risk_to_governance Low; autonomy_value High | If new scorecards change cap-feasible ranking, a different side-cell might offer higher after-cost upside without cap mutation. | Source-only rerank only when scorecard/cap/proposal artifacts change. | Fresh false-negative scorecard, cap feasibility, BBO/freshness, controls, fee/slippage assumptions. | Same artifacts, no repeat/OOS path, or edge disappears after costs. | Research only; bounded auth before order. | Do not rerun on current artifacts. |

## Verification

Verification for this docs-only checkpoint:

```text
python3 -m json.tool /tmp/openclaw/session_loop_state_20260626T1456Z_todo_source_pointer_drift_correction.json
PASS

git diff --check
PASS

TODO self-check: next PM can identify P0 auth as blocked/no-repeat in under one minute.
PASS
```

No code changed; no pytest suite is required for this docs-only metadata correction.
