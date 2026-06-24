# Bounded Probe Plan Inclusion Review

日期：2026-06-24
Active blocker：`P0-BOUNDED-PROBE-AUTHORIZATION-LATEST-PROPAGATION-REVIEW`
角色鏈：PM -> E1/PM -> E2 -> E4 -> QA/PM
狀態：`DONE_WITH_CONCERNS`

## 結論

本輪沒有把 AVAX timestamped authorization 複製到 `bounded_probe_operator_authorization_latest.json`，也沒有寫 plan、ledger、PG、admission latest，沒有啟用 runtime adapter，沒有 Bybit/API/order 動作。

新增 source-only helper：

- `helper_scripts/research/cost_gate_learning_lane/bounded_probe_plan_inclusion_review.py`
- `helper_scripts/research/tests/test_cost_gate_bounded_probe_plan_inclusion_review.py`
- `helper_scripts/SCRIPT_INDEX.md`

它讀取 fresh false-negative bounded preflight、construction preview、timestamped bounded operator authorization packet，建立 inactive `cost_gate_demo_learning_lane_plan_v1` preview，然後用既有 `runtime_adapter.evaluate_probe_admission` 做兩段 dry-run：

- current review path：`adapter_enabled=False`，必須停在 `ADAPTER_DISABLED` 且 `allowed_to_submit_order=false`
- hypothetical path：`adapter_enabled=True`，只保留 sanitized summary，表示若未來另行打開 adapter 會得到 `ADMIT_DEMO_LEARNING_PROBE`

因此本輪只把「timestamped authorization 能否被安全納入 plan/admission review」變成可重跑檢查；它不是 runtime admission，不是 active order authority。

## Session Loop State

1. `active_blocker_id`: `P0-BOUNDED-PROBE-AUTHORIZATION-LATEST-PROPAGATION-REVIEW`
2. `blocker_goal`: Map the existing AVAX timestamped bounded Demo authorization packet into a no-order, source-only plan-inclusion/admission dry-run review without mutating latest, plan, ledger, runtime adapter, or orders.
3. `profit_relevance`: This is the shortest safe bridge from an authorized high-upside false-negative AVAX candidate to a later bounded Demo order-admission review. It preserves live-applicability by requiring candidate identity, TTL, budget, fee/slippage lineage, and reconstructable adapter decisions before any runtime action.
4. `constraints_checked`: No global Cost Gate lowering; no live/mainnet; no latest overwrite; no plan/ledger/PG write; no Bybit/API/order/cancel/modify; no crontab/service/env mutation; no Rust writer; no runtime adapter enablement; no active runtime probe/order authority; no promotion proof.
5. `previous_evidence_checked`: Runtime clean at `22f5915b`; AVAX public quote and construction preview were ready/no-order; timestamped AVAX authorization packet sha `391dbca5c9a856e9bdaefe99fb82830ddab04ec7e3647a82d2e71a91198f7105` was authorized; latest still pointed to non-ready ETH and must not be used for AVAX.
6. `new_evidence_delta_required`: A source-only propagation mapping was required; repeating broad auth audit, fresh-quote capture, or manual artifact generation would not advance admission.
7. `new_evidence_delta_found`: New helper proves the exact AVAX timestamped packet can produce an inactive plan preview whose current adapter-disabled path rejects order submission while hypothetical adapter-enabled path would admit the same candidate.
8. `anti_repeat_decision`: `PROCEED_SOURCE_ONLY_PROPAGATION_MAPPING`
9. `action_taken_or_noop_reason`: Implemented reusable no-order helper plus regressions instead of rewriting runtime latest/plan by hand.

## Verification

PM local:

```text
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_plan_inclusion_review.py
6 passed

PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -k "runtime_adapter or operator_authorization"
12 passed, 78 deselected

python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/bounded_probe_plan_inclusion_review.py helper_scripts/research/tests/test_cost_gate_bounded_probe_plan_inclusion_review.py && git diff --check
PASS
```

Local smoke copied the real runtime artifacts read-only from `trade-core` and wrote only to `/tmp/openclaw_plan_inclusion_smoke.gbOlqG/`:

```text
review json sha256 cb5ebb36b5798368cd797d812505ea45fb1df4dc94de020c0620fc036b786f58
review markdown sha256 69c2401883f1afc36c90ceb193b212c75f9a928447bb1f42c5a8062895fa3968
status PLAN_INCLUSION_PREVIEW_READY_NO_ADMISSION
inactive_decision ADAPTER_DISABLED false
hypothetical_decision ADMIT_DEMO_LEARNING_PROBE true false
authority_violations []
```

E2 re-review：`STATUS: DONE`, no findings. Prior raw `allowed_to_submit_order=true` leakage and hidden nested authority concerns are resolved.

E4 re-verification：`STATUS: DONE`, same focused tests and `py_compile` / `git diff --check` passed. No runtime/PG/Bybit/order actions.

## Aggressive Profit Hypotheses

1. `runtime_plan_propagation_candidate_scoped_avalanche`
   - `why_it_might_make_money`: AVAX has a ready no-order construction preview and positive false-negative evidence; one candidate-matched Demo probe can measure actual maker fill, fee, slippage, and edge capture.
   - `fastest_safe_test`: PM -> E3 runtime propagation review that writes only a candidate-scoped plan/admission preview under disabled adapter, then separately decides whether to enable bounded demo admission.
   - `required_data`: this plan-inclusion review, timestamped AVAX auth packet, current construction preview, runtime adapter decision, candidate-matched lineage.
   - `failure_condition`: stale auth/quote/preview, latest mismatch, adapter rejects, or any active authority/proof contamination.
   - `authority_required`: E3 before runtime plan/latest/admission mutation; no live authority.
   - `max_safe_next_action`: `P0-BOUNDED-PROBE-AUTHORIZATION-RUNTIME-PROPAGATION-E3-REVIEW-DEMO-ONLY`.
   - scoring: `expected_net_pnl_upside=4`, `evidence_strength=4`, `execution_realism=4`, `cost_after_fees=4`, `time_to_test=4`, `risk_to_account=2`, `risk_to_governance=3`, `autonomy_value=5`.

2. `candidate_matched_probe_lineage_before_any_fill_claim`
   - `why_it_might_make_money`: The probe becomes useful only if attempts/fills/fees/slippage are tied to the exact AVAX candidate and matched blocked controls.
   - `fastest_safe_test`: Source-only lineage contract/checker for any future bounded-probe attempt and outcome rows.
   - `required_data`: candidate key, context/signal IDs, order/fill IDs, fee/slippage, blocked-control outcomes.
   - `failure_condition`: unattributed fill, missing fee/slippage, missing control, or mismatched side-cell.
   - `authority_required`: none for source-only checker; runtime write authority only for future probe logging.
   - `max_safe_next_action`: implement checker if runtime propagation is not immediately approved.
   - scoring: `expected_net_pnl_upside=3`, `evidence_strength=5`, `execution_realism=4`, `cost_after_fees=4`, `time_to_test=3`, `risk_to_account=1`, `risk_to_governance=1`, `autonomy_value=5`.

3. `alternative_low_notional_false_negative_rotation`
   - `why_it_might_make_money`: AVAX is ready now, but a ranked pool of lower-notional false negatives may reveal faster-fill, lower-friction candidates under the same 10 USDT cap.
   - `fastest_safe_test`: Source-only ranking by fresh constructibility, edge bps, min notional, spread, and expected maker touchability.
   - `required_data`: false-negative candidate packet, instrument filters, current quote/PG freshness, fee schedule, construction previews.
   - `failure_condition`: stale BBO, insufficient edge after fees, or no candidate-matched proof path.
   - `authority_required`: none for ranking; E3/BB only for fresh public quote calls.
   - `max_safe_next_action`: keep as fallback, not ahead of AVAX propagation review.
   - scoring: `expected_net_pnl_upside=3`, `evidence_strength=3`, `execution_realism=3`, `cost_after_fees=3`, `time_to_test=3`, `risk_to_account=1`, `risk_to_governance=1`, `autonomy_value=4`.

## Status

11. `status`: `DONE_WITH_CONCERNS`
12. `next_blocker_id`: `P0-BOUNDED-PROBE-AUTHORIZATION-RUNTIME-PROPAGATION-E3-REVIEW-DEMO-ONLY`
13. `why_not_repeating_current_blocker`: The source-only propagation mapping, E2/E4 review, tests, and real-artifact smoke are complete. Repeating authorization generation, fresh quote capture, or broad audit would not add evidence.
14. `branch / commit SHA / push status / short description`: branch `main`; commit SHA and push status are recorded after this report is committed. Short description：source-only bounded Demo plan-inclusion review helper with sanitized hypothetical admission summary and recursive authority rejection.
