# Profit-First Dynamic Candidate No-Authority Chain Repaired

Status: `READY_FOR_PM_E3_DISPATCH`

## Summary

The `ROTATED` blocker was caused by stale false-negative selection wiring in `helper_scripts/cron/cost_gate_learning_lane_cron.sh`: the cron wrapper reused an old cap-feasible selected side-cell `grid_trading|AVAXUSDT|Sell`, which was no longer present in the latest false-negative candidate packet. That made `false_negative_operator_review_latest.json` fail closed with `explicit_side_cell_key_not_found`, even though the current dynamic candidate and standing auth were both `ma_crossover|NEARUSDT|Buy`.

Source fix commit `725fddc3ab365da7655d57aba9ee03bc59d97417` validates any selected side-cell against the freshly generated false-negative candidate packet before passing it to the operator-review producer. If the selected key is stale or absent, the wrapper leaves selection empty so the producer uses the latest top-ranked false-negative candidate.

PM then regenerated only no-authority runtime artifacts from latest runtime inputs. The chain is now candidate-aligned and READY through operator-auth readiness, with `decision=defer` and no order/probe authorization.

## Verification

- `bash -n helper_scripts/cron/cost_gate_learning_lane_cron.sh`: passed.
- `python3 -m pytest -q helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py`: `16 passed`.
- Local no-authority replay from copied runtime inputs restored NEAR Buy chain before runtime refresh.
- Linux source-only fast-forwarded to source fix commit `725fddc3ab365da7655d57aba9ee03bc59d97417`; Linux worktree clean.
- Mac `HEAD`, `origin/main`, GitHub main, Linux `HEAD`, and Linux `origin/main` were all `725fddc3ab365da7655d57aba9ee03bc59d97417` before this source/artifact checkpoint. E3 must consume the committed checkpoint that contains this packet and recheck Mac/GitHub/Linux alignment at that checkpoint.

## Runtime No-Authority Chain

Timestamped runtime refresh stamp: `20260708T125556Z`.

| Artifact | Latest sha | Status |
|---|---|---|
| `false_negative_candidate_packet_latest.json` | `47d4bccb4816e049a8959f27804fae3b9c6f996172e699f03c864e73a52cfddc` | `COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW` |
| `autonomous_parameter_proposal_latest.json` | `76c7846969af266528c658d76b26c0dd7aac3fef1aca79c221725e66b0911370` | `REVIEWABLE_PARAMETER_PROPOSAL_READY` |
| `standing_demo_operator_authorization.json` | `05fe07f5ad4f92c459c4c6f67bfe534a04b0ea4b4e8f2d8aa43879d87009152f` | `STANDING_DEMO_AUTHORIZATION_ACTIVE` |
| `false_negative_operator_review_latest.json` | `9d3d49ad80f0db07ae723e3c31c8cf5571948d877bfabcfe482d4c6801f272ec` | `APPROVED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT` |
| `false_negative_bounded_probe_preflight_latest.json` | `3bcdeaefbcc596bc1c6c5ca983140ff717bbdbdbcedb1d88191af36f4d4ad178` | `READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION` |
| `bounded_probe_touchability_preflight_latest.json` | `5215481a828f2225948a8cf3e5ba5c29f88d63cd5f59421708319bff6ca78340` | `FIRST_ATTEMPT_TOUCHABILITY_BOOTSTRAP_REQUIRED` |
| `bounded_probe_placement_repair_plan_latest.json` | `53c50304b16b04dc840bc27e6aeaef74fc179f2705146431ea0aa6490263602f` | `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW` |
| `bounded_probe_authority_patch_readiness_latest.json` | `87ce92612945c5423a0627c22e3f3ec77cc70491892a761d243e6f8c8e097b3d` | `AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW` |
| `bounded_probe_operator_authorization_latest.json` | `b004ace6f3c278648afe6dfb3bd4e75e99c7705ae52642db68d7401c8ff985eb` | `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`, `decision=defer` |

## Boundary

Performed:

- Source-only cron wrapper fix.
- Focused tests and local no-authority replay.
- Linux source-only fast-forward.
- Runtime no-authority JSON/MD artifact refresh for the current chain.
- PM exact E3 request packet emission.

Not performed:

- No public/private Bybit call.
- No Decision Lease acquire/release.
- No order/probe/cancel/modify.
- No bounded Demo final window.
- No operator auth `authorize`.
- No standing authorization materialization or change.
- No adapter enablement.
- No service restart/build.
- No DB write/migration.
- No Cost Gate lowering.
- No live/mainnet.
- No proof/promotion.

## Next

Dispatch E3 only for the exact no-authority repaired-chain review in:

`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-08--profit_first_dynamic_candidate_no_authority_chain_repaired_e3_request.json`

If E3 sees source/runtime/candidate/hash drift, the result must be `ROTATED`. If E3 approves, PM may prepare a separate BB request; no exchange-facing final-window action is authorized by this packet.
