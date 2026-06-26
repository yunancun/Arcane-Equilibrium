# Cap Envelope Evidence Floor Source Patch

Date: 2026-06-26 09:24 CEST

本輪是 source/test/docs checkpoint。目標是把「高 upside 但需要更高 per-order cap 的候選」轉成可審核 proposal 之前的最低證據地板，接進既有 `cost_gate_autonomous_parameter_proposal_v1`。沒有 runtime sync、沒有手動 cron、沒有 `_latest` 覆寫、沒有 PG query/write、沒有 Bybit/API/order/cancel/modify、沒有 Cost Gate/cap/risk mutation、沒有 writer/adapter enablement、沒有 probe/order/live authority。

## Required Round Output

| Field | Value |
|---|---|
| `active_blocker_id` | `P1-AGGRESSIVE-ALPHA-CAP-ENVELOPE-EVIDENCE-FLOOR-SOURCE-ONLY` |
| `blocker_goal` | Define and enforce the minimum source-level evidence floor before a high-priced/high-upside learned candidate can become a cap-envelope proposal. |
| `profit_relevance` | Keeps ETH-like high-upside paths available for future review while preventing a hidden cap/exposure increase from bypassing survival/risk/authorization gates. |
| `constraints_checked` | No Cost Gate lowering, no live promotion, no Bybit order/cancel/modify, no PG query/write, no runtime/env/crontab/service mutation, no `_latest` overwrite, no Rust writer/adapter enablement, no cap/risk mutation, no probe/order/live authority, no profit/proof claim. |
| `previous_evidence_checked` | TODO v558; v558 ETH cap report; runtime read-only artifact snapshot at `2026-06-26T07:14:29Z`; alpha regime governance audit; P0 cost-wall audit; source contracts `autonomous_parameter_proposal.py`, `proof_exclusion.py`, `bounded_probe_result_review.py`, and `aeg_execution_realism.builder`. |
| `new_evidence_delta_required` | P0 auth had no real delta, so only a distinct source-only evidence-floor contract could advance the loop. |
| `new_evidence_delta_found` | Existing autonomous proposal converted learned candidates into review packets, but did not encode a reusable cap-envelope evidence floor. |
| `anti_repeat_decision` | `P0-BOUNDED-PROBE-AUTHORIZATION` = `NO-OP_NO_EVIDENCE_DELTA`; ETH cap sensitivity = `NO-OP_ALREADY_DONE`; proceed with source-only cap-envelope evidence-floor patch. |
| `action_taken_or_noop_reason` | Added no-authority `cost_gate_cap_envelope_evidence_floor_v1` to autonomous parameter proposals and tests proving cap mutation remains disallowed. |
| `aggressive_profit_hypotheses` | See table below. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P1-RUNTIME-HEALTH-HYGIENE-CAP-ENVELOPE-PROPOSAL-SYNC-REVIEW` if runtime sync is explicitly pursued; otherwise P0 authorization remains blocked until real auth delta. |
| `why_not_repeating_current_blocker` | The source contract is now present and tested. Repeating without runtime sync, new evidence, or a new code contract need would be noise. |

## Source Change

Changed:

- `helper_scripts/research/cost_gate_learning_lane/autonomous_parameter_proposal.py`
- `helper_scripts/research/tests/test_cost_gate_autonomous_parameter_proposal.py`
- `helper_scripts/SCRIPT_INDEX.md`

The autonomous proposal now emits:

- `cap_envelope_evidence_floor.schema_version = cost_gate_cap_envelope_evidence_floor_v1`
- an inactive `bounded_demo_probe_cap_envelope` proposed parameter row with `mutation_allowed_by_this_packet=false`
- `answers.cap_envelope_mutation_allowed=false`
- markdown line `Cap envelope mutation allowed: False`

The evidence floor requires, before any future cap-envelope review:

- candidate side-cell matches the learning packet
- candidate-matched controls
- candidate-matched fee/slippage and maker/taker labels
- fresh BBO and instrument metadata for tick/qty/min-notional
- cap staircase with discrete exposure tiers
- portfolio exposure and survival-risk budget math
- empirical execution realism or explicit research-only status
- proof-exclusion scan for all fill-backed rows
- regime/breadth/freshness/survivorship labels
- repeat or OOS path before any promotion claim

Execution-realism thresholds are aligned to existing AEG gates: sample count `>=30`, maker fill `>=0.60`, maker adverse selection p95 `<=3.50bps`, latency p95 `<=2000ms`, participation p95 `<=0.05`, positive capacity above proposed tier notional, and order availability `PASS`.

## Role Chain

| Role | Result |
|---|---|
| PM | Established session state and anti-repeat decision; selected source-only contract patch. |
| PA/E1 | Scoped implementation to the existing autonomous proposal contract; no new runtime artifact type or cron path. |
| E2 | Reviewed for fail-open authority risk: all new cap-envelope rows are inactive and mutation-forbidden; no authority-bearing answers are set true. |
| E4 | Ran focused and adjacent tests plus compile/diff checks. |
| QA/PM | Confirmed TODO/report boundary and no runtime/order/proof claim. |

## Verification

```text
PYTHONPATH=helper_scripts/research python3 -m pytest -q \
  helper_scripts/research/tests/test_cost_gate_autonomous_parameter_proposal.py \
  helper_scripts/research/tests/test_cost_gate_false_negative_bounded_probe_preflight.py
10 passed

python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/autonomous_parameter_proposal.py
PASS

git diff --check
PASS
```

## Aggressive Profit Hypotheses

| Hypothesis | Scores | Why it might make money | Fastest safe test | Required data | Failure condition | Authority required | Max safe next action |
|---|---|---|---|---|---|---|---|
| ETH Tier-1 cap envelope becomes reviewable after evidence floor | expected_net_pnl_upside High; evidence_strength Low-Medium now; execution_realism Low now; cost_after_fees modeled favorable; time_to_test Medium; risk_to_account None now/Medium if cap changes; risk_to_governance Medium; autonomy_value High | ETH has the strongest modeled false-negative lead, and the first executable tier is discrete, not open-ended cap drift. | Generate or wait for a proposal only after the new floor fields are present in runtime artifacts and evidence exists. | Candidate-matched controls, fees/slippage, BBO/metadata, cap staircase, portfolio risk, empirical execution realism, regime labels. | Any floor item missing, sample remains small, or cap rise weakens survival/risk envelope. | Operator/QC cap review plus PM -> E3 -> BB before order. | Source/runtime sync review only; no cap mutation. |
| Current-cap AVAX remains fastest bounded Demo path | upside High path-enabler; evidence Medium-High; realism blocked by auth; cost modeled favorable; time Fast if valid auth appears; account risk None now; governance Medium; autonomy High | AVAX fits current cap and does not require cap-envelope mutation. | Review only a real AVAX-scoped typed-confirm/standing-auth artifact delta. | Exact false-negative preflight approval, bounded auth object, fresh BBO, cap construction, fees/fills/slippage lineage. | No exact auth, stale candidate, or authority contamination. | Candidate-scoped auth plus E3/BB; no authority now. | Stop at authorization gate. |
| Low-price false-negative candidates can avoid cap-envelope complexity | upside Medium; evidence Medium; realism Medium; cost Mixed; time Fast; account risk None source-only; governance Low; autonomy Medium | Some lower-price symbols may preserve edge under existing `10 USDT` cap, avoiding exposure expansion. | Source-only screen using the same evidence floor minus cap-increase review. | Cap-feasible screen, scorecard, spread/markout controls, lineage and proof exclusions. | Net cushion disappears after realistic costs or no subgroup has repeat/OOS path. | Research only; bounded auth before order. | Evidence-floor ranking proposal only. |

## Boundary

This patch only changes source/test/docs. It does not grant authority, does not lower Cost Gate, does not mutate cap/risk/order/runtime state, and does not make ETH or any other candidate execution-eligible.
