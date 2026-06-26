# Candidate Selection Delta Cap-Feasible Selector Source Fix

Date: 2026-06-26 07:34 CEST

## Required Round Output

| Field | Value |
|---|---|
| `active_blocker_id` | `P0-PROFIT-CANDIDATE-SELECTION-DELTA-REFRESH-NO-ORDER` |
| `blocker_goal` | Use fresh runtime scorecard/candidate/auth artifacts to refresh candidate-selection posture without order/probe authority. |
| `profit_relevance` | Keeps bounded Demo learning focused on an actually constructible current-cap candidate instead of repeatedly routing latest authorization review to cap-infeasible ETH. |
| `constraints_checked` | No Cost Gate lowering, no live promotion, no Bybit order/cancel/modify, no PG write, no runtime source sync, no service/crontab/env mutation, no writer/adapter enablement, no order/probe authority, no proof claim. |
| `previous_evidence_checked` | v549 TODO/report; `2026-06-26--bounded_probe_authorization_antirepeat_todo_hygiene.md`; runtime latest scorecard/candidate/auth artifacts. |
| `new_evidence_delta_required` | Fresh scorecard/candidate/auth artifact delta or source contract evidence. |
| `new_evidence_delta_found` | Runtime artifacts generated at `2026-06-26T05:29-05:30Z`: scorecard still ranks `grid_trading|ETHUSDT|Buy` first, but ETH remains infeasible under current `10 USDT` cap; AVAX remains the top current-cap-feasible candidate from cap-feasible selection evidence. |
| `anti_repeat_decision` | P0 authorization has no AVAX-scoped grant, so no-repeat; proceed with distinct source-only candidate delta fix. |
| `action_taken_or_noop_reason` | Patched cron wrapper to pass an explicit or cap-feasible selected side-cell into false-negative operator review before falling back to top ranked false-negative. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P1-RUNTIME-HEALTH-HYGIENE-CAP-FEASIBLE-SELECTOR-SYNC-REVIEW` |
| `why_not_repeating_current_blocker` | Authorization remains no-authority/defer; the new evidence delta was candidate-routing drift, not a grant. |

## Evidence

Runtime read-only evidence:

| Artifact | Evidence |
|---|---|
| `bounded_probe_operator_authorization_latest.json` | sha `a9eab62e...`, generated `2026-06-26T05:30:53Z`, `decision=defer`, candidate `grid_trading|ETHUSDT|Buy`, no emitted object, active runtime probe/order authority false. |
| `false_negative_candidate_friction_scorecard_latest.json` | sha `ffdd223f...`, generated `2026-06-26T05:30:53Z`, top `grid_trading|ETHUSDT|Buy`, second `grid_trading|AVAXUSDT|Sell`. |
| `false_negative_candidate_packet_latest.json` | sha `1ccceab2...`, generated `2026-06-26T05:29:21Z`, top false-negative `ETH Buy`, AVAX second. |
| `cap_feasible_candidate_selection_avax_sell_20260625T214943Z.json` | `CAP_FEASIBLE_CANDIDATE_SELECTED_FOR_PREFLIGHT_REVIEW`, selected `grid_trading|AVAXUSDT|Sell`, `fits_current_cap=true`, min required `5.0 USDT`, cap `10.0 USDT`. |
| `bounded_probe_candidate_construction_preview_eth_buy_latest.json` | `CANDIDATE_CONSTRUCTION_NOT_FEASIBLE_UNDER_CAP`, min executable notional `15.7105 USDT`, rounded qty `0`, cap `10.0 USDT`. |

Inference: latest authorization is not dangerous because it is defer/no-authority, but it wastes the fastest bounded Demo path by repeatedly targeting cap-infeasible ETH instead of the already selected cap-feasible AVAX candidate.

## Source Change

Files changed:

- `helper_scripts/cron/cost_gate_learning_lane_cron.sh`
- `helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py`

Change:

- Added a cron wrapper selector that reads `selected_candidate.side_cell_key` from a cap-feasible candidate-selection artifact.
- Added explicit override env `OPENCLAW_COST_GATE_FALSE_NEGATIVE_OPERATOR_REVIEW_SELECTED_SIDE_CELL_KEY`.
- Added artifact path env `OPENCLAW_COST_GATE_CAP_FEASIBLE_CANDIDATE_SELECTION_JSON`.
- When a selected side-cell is available, false-negative operator review receives `--selected-side-cell-key`; otherwise behavior falls back to top ranked false-negative.

This does not approve, authorize, submit, or mutate runtime state. It only changes source-side artifact selection once deployed/synced.

Repo-chain record:

| Role step | Decision |
|---|---|
| PM | Treat fresh runtime artifact drift as a distinct source-only candidate-selection delta, not another authorization audit. |
| PA | Minimal design: change cron selection input only; do not change Python authorization/preflight gates. |
| E1 | Patch wrapper to pass explicit/cap-feasible selected side-cell into false-negative operator review. |
| E2 | Diff review: fallback behavior remains; no authority/proof flags or runtime effects are introduced. |
| E4 | Focused shell/static/Python tests passed; no runtime test or deploy was performed. |
| PM | Accept with concern that Linux runtime still needs separate E3-reviewed source sync before effect. |

## Verification

```bash
bash -n helper_scripts/cron/cost_gate_learning_lane_cron.sh
python3 -m pytest -q helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_false_negative_bounded_probe_preflight.py helper_scripts/research/tests/test_cost_gate_bounded_probe_operator_authorization.py
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -k 'false_negative_operator_review or false_negative_candidate_packet'
git diff --check
```

Results: shell syntax passed; cron static `15 passed`; authorization/preflight focused `23 passed`; operator-review policy focused `8 passed, 82 deselected`; diff check passed.

## Aggressive Profit Hypotheses

| Hypothesis | Scores | Why it might make money | Fastest safe test | Required data | Failure condition | Authority |
|---|---|---|---|---|---|---|
| Cap-feasible selector keeps AVAX as fastest bounded Demo candidate | upside High path-enabler; evidence Medium; realism pending runtime refresh; cost good model-only; time Fast after sync; account risk None; governance Low; autonomy High | Avoids losing cycles to cap-infeasible ETH and keeps the proof path on AVAX. | After reviewed runtime source sync, next artifact refresh should point operator review/preflight/auth to AVAX. | Cap-feasible selection, false-negative packet, operator review, authorization packet. | Latest chain still targets ETH, selected candidate not cap-feasible, or any authority flag turns true. | Source/test/docs now; runtime sync needs PM->E3 review. |
| ETH high-edge cap-envelope research | upside High if cap envelope exists; evidence Low-Medium; realism Low under current cap; time Medium; governance Medium if cap pressure | ETH has higher modeled edge but cannot construct under current cap. | Source-only cap-envelope sensitivity packet. | Fresh construction preview, cap envelope, controls, fees/slippage. | Min executable notional remains above approved cap or sample stays too small. | Research only. |
| Horizon-edge ma_crossover path | upside Medium; evidence Low; realism Unknown; time Medium; governance Low | Profitability scorecard shows separate horizon amplification candidates. | Build horizon-specific source-only packet. | Sealed replay, OOS/holdout, cap feasibility, execution realism. | Replay-only or cap-infeasible. | Research only. |

## Stop Condition

The source fix is committed only after validation. It is not yet active on Linux runtime in this checkpoint. Next safe blocker is an E3-reviewed runtime source-sync / expected-head review; no crontab edit, service restart, or runtime mutation was performed here.
