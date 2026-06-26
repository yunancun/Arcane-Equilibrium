# Alpha Bounded-Chain Stale Side-Cell Guard Source Fix

Date: 2026-06-26 08:10 CEST

## Required Round Output

| Field | Value |
|---|---|
| `active_blocker_id` | `P1-RUNTIME-HEALTH-HYGIENE-ALPHA-BOUNDED-CHAIN-STALENESS-GUARD-SOURCE-FIX` |
| `blocker_goal` | Prevent alpha cron from refreshing bounded `_latest` artifacts from a stale bounded preflight when a different cap-feasible selected side-cell exists. |
| `profit_relevance` | Keeps bounded Demo review aimed at current-cap-feasible AVAX instead of repeatedly recycling cap-infeasible ETH artifacts. |
| `constraints_checked` | No Cost Gate lowering, no live promotion, no Bybit order/cancel/modify, no PG write, no service restart/rebuild, no manual cron run, no runtime sync, no `_latest` overwrite, no writer/adapter enablement, no order/probe authority, no proof claim. |
| `previous_evidence_checked` | v551 runtime sync report; runtime cap-feasible AVAX selection artifact; `08:00 CEST` alpha bounded artifacts; alpha cron source/tests. |
| `new_evidence_delta_required` | Post-sync downstream alpha artifact mtime/sha delta or source-path evidence proving stale bounded-chain routing. |
| `new_evidence_delta_found` | `2026-06-26T06:09:34Z` read-only runtime check found `bounded_probe_operator_authorization_latest.json` mtime `2026-06-26 08:00:05 +0200`, sha `dd9a5251...`, still ETH-scoped while cap-feasible selection is AVAX. |
| `anti_repeat_decision` | `P0-BOUNDED-PROBE-AUTHORIZATION` is `NO-OP_NO_AVAX_AUTH_DELTA`; source-only stale-side guard is a distinct P1 runtime-hygiene blocker. |
| `action_taken_or_noop_reason` | Patched alpha cron to fail closed on selected-side-cell mismatch and skip stale bounded scorecard inputs; did not run runtime cron or mutate runtime. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P1-RUNTIME-HEALTH-HYGIENE-ALPHA-BOUNDED-CHAIN-STALENESS-GUARD-SYNC-REVIEW` |
| `why_not_repeating_current_blocker` | The latest auth artifact is still ETH defer/no-authority; reviewing P0 authorization again would not create AVAX proof or authority. |

## Session State

- `/tmp/openclaw/session_loop_state_20260626T060934Z_alpha_bounded_chain_stale_side_cell_guard_source_fix.json`

## Evidence

Read-only runtime snapshot at `2026-06-26T06:09:34Z`:

- Runtime source: clean at `b983622478d5b9fa05df65a375b1f3ca1ae7fda4`.
- Cap-feasible selection count: `1`.
- Cap-feasible selection: `grid_trading|AVAXUSDT|Sell`, status `CAP_FEASIBLE_CANDIDATE_SELECTED_FOR_PREFLIGHT_REVIEW`, `fits_current_cap=true`.
- False-negative review/preflight latest: `2026-06-26 07:29:21 +0200`, still `grid_trading|ETHUSDT|Buy`.
- Alpha downstream bounded chain latest: `2026-06-26 08:00:05 +0200`, still `grid_trading|ETHUSDT|Buy`, `decision=defer`, no active probe/order authority.

Root cause:

- `alpha_discovery_throughput_cron.sh` preferred `false_negative_bounded_probe_preflight_latest.json` when present.
- That stale bounded preflight remained ETH-scoped, even though the cap-feasible selected candidate is AVAX.
- Therefore alpha cron refreshed downstream bounded `_latest` artifacts with ETH again.

Source fix:

- Added `json_side_cell_key()` helper to parse side-cell keys from selected-candidate, candidate, and bounded-design style artifacts.
- Added `OPENCLAW_ALPHA_CAP_FEASIBLE_CANDIDATE_SELECTION_JSON` and `OPENCLAW_ALPHA_SELECTED_SIDE_CELL_KEY` override paths.
- If selected side-cell and bounded preflight side-cell both exist and mismatch, alpha cron now logs `selected_side_cell_mismatch`, skips the bounded review chain, and skips bounded preflight/operator/result/execution-realism inputs to the profitability scorecard.

Validation:

```bash
bash -n helper_scripts/cron/alpha_discovery_throughput_cron.sh
python3 -m pytest -q helper_scripts/cron/tests/test_alpha_discovery_throughput_cron_static.py
python3 -m pytest -q helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py
```

Results:

- bash syntax: PASS
- alpha cron static/execution contract: `9 passed`
- cost-gate cron static contract: `15 passed`

## Decision

This is source-only and not runtime-active yet. The next executable checkpoint is a bounded runtime sync review/apply that fast-forwards runtime source and aligns expected-head pins, without service restart, manual cron run, PG write, Bybit call, `_latest` overwrite, or authority mutation.

## Aggressive Profit Hypotheses

| Hypothesis | Scores | Why it might make money | Fastest safe test | Required data | Failure condition | Authority | Max safe next action |
|---|---|---|---|---|---|---|---|
| AVAX alpha bounded-chain stale-side guard | upside High path-enabler; evidence High for bug path; execution realism source-verified; cost unchanged; time Fast after sync; account risk None now; governance Low; autonomy High | Stops stale ETH from consuming bounded review cycles and lets cap-feasible AVAX reach review. | Runtime sync review/apply, then scheduled artifact review. | Runtime source/crontab head, next alpha/cost-gate artifacts. | Fresh artifacts still ETH after guard sync or any authority flag turns true unexpectedly. | Runtime source/crontab sync only; no order authority. | Prepare sync review; do not run cron manually. |
| AVAX post-guard authorization alignment | upside High path-enabler; evidence Medium; execution realism pending; cost model good; time Fast after sync; account risk None; governance Low; autonomy High | A fresh AVAX-scoped defer packet is the prerequisite for any bounded Demo probe packet. | Review next fresh bounded auth chain for AVAX scope and no-authority fields. | False-negative review, bounded preflight, placement, auth artifacts. | Candidate remains ETH/SUI/FIL or proof/authority fields contaminate review. | Artifact review only. | Wait for fresh scheduled artifact after runtime sync. |
| ETH cap-envelope research | upside High if allowed cap exists; evidence Low-Medium; execution realism Low under current cap; cost good; time Medium; account risk None now; governance Medium; autonomy Medium | ETH modeled edge may be real but is currently non-executable under `10 USDT` cap. | Source-only cap sensitivity packet. | Fresh construction preview, fee/slippage, cap envelope, controls. | Min executable notional remains above any approved envelope. | Research only. | Keep as proposal, not bounded candidate. |

## Status

`DONE_WITH_CONCERNS`.

No order/probe/live authority was granted or implied. No proof or promotion claim was made.
