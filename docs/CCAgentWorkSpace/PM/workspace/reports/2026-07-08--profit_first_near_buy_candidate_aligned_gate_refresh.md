# Profit-First NEAR Buy Candidate-Aligned Gate Refresh

Status: `READY_FOR_PM_E3_DISPATCH`

## Executive Summary

PM did not reuse the stale `STOP_RUNTIME_GATE_NOT_READY` intake stop as a terminal state. The loop refreshed the current runtime artifacts, confirmed the current candidate is `ma_crossover|NEARUSDT|Buy`, and completed the no-authority candidate-aligned gate chain required before a PM->E3 dispatch.

The latest runtime `_latest` packet is newer than the 2026-07-07 prompt snapshot:

- Candidate: `ma_crossover|NEARUSDT|Buy`
- Blocked outcomes: `764040`
- False-negative candidate count: `1`
- Avg net: `64.983bps`
- Candidate packet sha256: `0dc8b5bebab9e65804a2a3d77246ff35210ace9d337d95601bc617e36d7a8bf0`
- Operator review ready: `true`

The runtime standing authorization remains the old `grid_trading|ETHUSDT|Buy` object and expired at `2026-07-08T01:53:48.341325+00:00`. It was not consumed as NEAR authority. A candidate-aligned NEAR Buy standing authorization preview was generated only as a source/report artifact and was not materialized into runtime.

## Source And Runtime Sync

Initial Mac `HEAD`, Mac `origin/main`, GitHub `main`, Linux `HEAD`, and Linux `origin/main` were aligned at `1d8caa7179c3b11f1858c7dd859a1ccdad04b68c` after the required source-only Linux fast-forward. Linux worktree was clean. The Linux sync was source-only; no build, restart, env mutation, DB write, Decision Lease, Bybit call, order, probe, or cancellation was performed.

## Producer Repair

The standing envelope producer could not consume the current false-negative candidate packet because the candidate row had an empty `risk_cap_lineage`. PM repaired the producer instead of hand-writing JSON:

- File: `helper_scripts/research/cost_gate_learning_lane/standing_demo_loss_control_envelope_review.py`
- Added GUI/Rust RiskConfig plus accepted Demo equity fallback for missing candidate packet cap lineage.
- Preserved fail-closed behavior when neither candidate lineage nor reviewed GUI/equity inputs are present.
- Added regression coverage in `helper_scripts/research/tests/test_cost_gate_standing_demo_loss_control_envelope_review.py`.

The derived cap lineage used GUI-backed Rust RiskConfig semantics: `per_trade_risk_pct=0.1`, Demo equity `9544.67467679`, resolved cap `954.46746768` USDT, and `local 10 USDT` is explicitly not global risk authority.

## Gate Chain

| Gate | Artifact | Status | Authority result |
|---|---|---|---|
| Standing Demo loss-control envelope draft | `2026-07-08--profit_first_near_buy_candidate_aligned_gate_refresh.standing_demo_loss_control_envelope_review.json` | `STANDING_DEMO_LOSS_CONTROL_ENVELOPE_REVIEW_READY_NO_RUNTIME_MUTATION` | No runtime materialization, no probe/order authority |
| False-negative operator review refresh | `2026-07-08--profit_first_near_buy_candidate_aligned_gate_refresh.false_negative_operator_review.json` | `APPROVED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT` | Preflight approval only, no runtime authority |
| False-negative bounded-probe preflight | `2026-07-08--profit_first_near_buy_candidate_aligned_gate_refresh.false_negative_bounded_probe_preflight.json` | `READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION` | No probe/order authority |
| Touchability preflight | `2026-07-08--profit_first_near_buy_candidate_aligned_gate_refresh.bounded_probe_touchability_preflight.json` | `FIRST_ATTEMPT_TOUCHABILITY_BOOTSTRAP_REQUIRED` | Candidate has no matched prior orders; not proof |
| Placement repair plan | `2026-07-08--profit_first_near_buy_candidate_aligned_gate_refresh.bounded_probe_placement_repair_plan.json` | `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW` | `post_only_near_touch_or_skip`, no active plan |
| Authority patch readiness | `2026-07-08--profit_first_near_buy_candidate_aligned_gate_refresh.bounded_probe_authority_patch_readiness.json` | `AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW` | Source-ready only; not runtime enablement |
| Operator authorization readiness | `2026-07-08--profit_first_near_buy_candidate_aligned_gate_refresh.bounded_probe_operator_authorization_readiness.json` | `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW` | `decision=defer`; no authorization object emitted |

The touchability audit was a read-only Linux PG audit and produced `FILL_FLOW_PRESENT` aggregate evidence over 100 reviewed orders, but candidate-matched NEAR Buy order/fill counts remain zero. The first NEAR attempt therefore requires the placement repair plan's near-touch-or-skip behavior and cannot be counted as proof.

## Next Dispatch

PM generated `2026-07-08--profit_first_near_buy_candidate_aligned_gate_refresh.exact_scope_request.json` for E3. The request is intentionally narrow:

- Review source/artifact checkpoint and source/runtime stability.
- If still current, authorize candidate-aligned standing Demo loss-control materialization and no-order refresh only.
- Keep bounded-probe operator authorization at `defer`.
- Do not open public/private Bybit, Decision Lease, order/probe, adapter enablement, service restart, DB write, Cost Gate mutation, live/mainnet, or proof/promotion in this request.

If E3 approves and a later step becomes exchange-facing, PM must open BB as a separate exact scope before any final bounded Demo window.

## Boundary Ledger

Performed:

- Source/artifact reads.
- Source-only Linux fast-forward while clean and fast-forwardable.
- Source-only producer/test repair.
- Read-only Linux PG audit.
- No-authority candidate-aligned packet generation.

Not performed:

- No live/mainnet.
- No public/private Bybit call.
- No order/probe/cancel/modify.
- No Decision Lease acquire/release.
- No runtime standing auth materialization.
- No runtime env/service mutation.
- No DB write/migration.
- No Cost Gate lowering.
- No proof/promotion claim.
