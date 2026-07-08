# BB Bounded Demo Final-Window Prep Review

Verdict: `APPROVE_FOR_BOUNDED_DEMO_FINAL_WINDOW_PREP`

Reviewed request: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-08--profit_first_dynamic_candidate_bounded_demo_bb_request.json`

Request sha256: `d0d21a3ba57f093221dd87945fc3e2852972bda9bc4730cc5e59666efc0f057c`

## Evidence

- E3 prerequisite: `APPROVE_FOR_PM_MATERIALIZATION_PREP`; E3 reports no Bybit calls, no Decision Lease, no order/probe/cancel, and no runtime/env/service/DB/Cost Gate mutation.
- Source/runtime heads rechecked: Mac `HEAD == origin/main == da1a04ec...`; Linux `HEAD == origin/main == da1a04ec...`; Linux worktree clean. Mac worktree is dirty with unrelated WIP/untracked reports, so final consumption must recheck heads again.
- Latest runtime candidate did not rotate: `false_negative_candidate_packet_latest.json` sha `1387ae73...` ranks `ma_crossover|NEARUSDT|Buy` as top false-negative; proposal sha `676f6c3e...` selects the same candidate.
- Runtime standing auth matches request: sha `05fe07f5...`, mode `600`, Demo-only, candidate `ma_crossover|NEARUSDT|Buy`, cap `954.46746768` USDT/order, expires `2026-07-09T00:12:30.886090Z`.
- No-order chain refreshed for same candidate through operator-auth readiness: latest operator authorization packet sha `0438247d...`, `decision=defer`, `bounded_demo_probe_authorized=false`, no authorization object emitted.
- Request explicitly forbids this BB review from making public/private Bybit calls, acquiring/releasing Decision Lease, order/probe/cancel/modify, setting operator auth to `authorize`, adapter enablement, restart/build, DB write/migration, Cost Gate lowering, live/mainnet, proof, or promotion.

## BB Judgment

No `ROTATED` condition is present at review time.

The proposed future constraints are acceptable from Bybit/API/policy perspective as prep only: Demo-only, `NEARUSDT` Buy, max 2 probe intents, max `954.46746768` USDT/order, `post_only_near_touch_or_skip`, fresh BBO `<=1000ms`, skip if touch gap `>75bps`, preserve Guardian/Decision Lease/Rust authority, and first-attempt bootstrap is not proof.

Residual Bybit caveat: because this review made no Bybit call, it does not prove current exchange instrument status, tick/qty/min-notional filters, or live BBO. Those must be checked inside the same-window final gate before any exchange-facing action.

## Blockers

None for final-window prep.

Hard stop if, before consumption, any of these changes: latest selected candidate, source/runtime head, Linux cleanliness, listed artifact sha, standing auth freshness, Demo-only scope, cap lineage, or no-authority flags.

## Allowed Next Actions

PM may prepare a separate same-window bounded Demo final gate packet for `ma_crossover|NEARUSDT|Buy`.

That packet may only proceed after rechecking source/runtime heads, Linux cleanliness, latest candidate selection, artifact shas, and standing auth freshness.

## Still Requires Same-Window Final Gate

Before any Bybit public/private call, Decision Lease, order/probe/cancel/modify, or bounded Demo execution, PM must obtain same-window final gate evidence for: active Decision Lease, Guardian/Rust authority, fresh BBO, instrument status/filters, exact order shape, PostOnly reject handling, book cleanliness, auditability, reconstructability, proof exclusion, and exact operator authorization if `defer` is to become `authorize`.

## Forbidden Next Actions

No exchange call, no Decision Lease, no order/probe/cancel/modify, no operator auth `authorize`, no adapter enablement, no service restart/build, no DB write/migration, no Cost Gate lowering, no live/mainnet, and no proof/promotion claim from this BB verdict.
