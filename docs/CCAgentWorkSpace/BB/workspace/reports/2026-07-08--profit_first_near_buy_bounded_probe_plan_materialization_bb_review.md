BB_VERDICT: APPROVE_FOR_PM_SAME_WINDOW_PLAN_MATERIALIZATION_RECHECK
CONFIDENCE: high

# BB Review - NEAR Buy Bounded-Probe Plan Materialization

Reviewed request:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-08--profit_first_near_buy_bounded_probe_plan_materialization_bb_request.json`

## Evidence

- Source alignment checked with `git rev-parse HEAD origin/main`, `git ls-remote origin refs/heads/main`, and Linux `git status --porcelain=v1 --branch && git rev-parse HEAD origin/main`.
- Mac `HEAD`, Mac `origin/main`, GitHub `main`, Linux `HEAD`, and Linux `origin/main` all equaled `015d4033d5fc6dbd1127e3bf6e3ffa0c8100bdc0`.
- Linux worktree was clean. Mac had unrelated dirty files, but target PM/E3 artifacts were unchanged.
- Diff from E3 checkpoint checked with `git diff --name-only ab496b4495bc30eb459c02b0340f97420d6ce57b 015d4033d5fc6dbd1127e3bf6e3ffa0c8100bdc0`; only allowed TODO/changelog/report/request files changed.
- BB request hash checked: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-08--profit_first_near_buy_bounded_probe_plan_materialization_bb_request.json` = `05d27a0419954905faf82a3e02c59d10814d399d6f52149c5b55a13b6d3ba89c`.
- E3 report hash/verdict checked: `docs/CCAgentWorkSpace/E3/workspace/reports/2026-07-08--profit_first_near_buy_bounded_probe_plan_materialization_e3_review.md` = `bb03bcc9d911ad17bff674720f81bb1785061393f6187f51d7ea2f1131cc4ed8`, verdict `APPROVE_FOR_PM_BB_PLAN_MATERIALIZATION_REVIEW`.

## Bybit/API/Policy Compatibility

Runtime hashes checked on `trade-core` with `sha256sum`:

| Artifact | SHA256 |
|---|---|
| `/tmp/openclaw_near_bounded_probe_authorization_20260708T190054Z_db2c9e105/bounded_probe_operator_authorization_authorized.json` | `0e075af5b0a5ef8b3e343caffe7ab3608bbb45cf418600c5cf689e3c5e5e7124` |
| `/tmp/openclaw_near_bounded_probe_authorization_20260708T190054Z_db2c9e105/bounded_probe_plan_inclusion_review.json` | `5e08595c3b009741e3ede221d7ce96c233864d6ddb1f434797b1c105249305fc` |
| `/home/ncyu/BybitOpenClaw/var/openclaw/profit_first_dynamic_candidate_same_window_final_gate_20260708T175744Z_08f7e957_noorder/active_lease_bbo_window/actual_construction_preview.json` | `d4561891a8ddaf318923be31043591033413a58ff66ef2a8acb842b7e79a2981` |
| `/home/ncyu/BybitOpenClaw/var/openclaw/cost_gate_learning_lane/bounded_demo_probe_soak_plan.json` | `30056993b5cae70a0fcad0503221e12bd74dae4e42a29d0d2c88423c64739823` |

- Authorization is scoped to `ma_crossover|NEARUSDT|Buy`, max orders `2`, expires `2026-07-09T00:12:30.886090+00:00`; at Linux review time `2026-07-08T19:30:37Z`, it was unexpired.
- Plan inclusion is no-admission: `ADAPTER_DISABLED`, `allowed_to_submit_order=false`, `no_order_authority=true`; hypothetical adapter-enabled result is `ADMIT_DEMO_LEARNING_PROBE`, but `allowed_to_submit_order_in_current_review=false`.
- Construction preview is compatible as prep only: qty `508.5`, limit `1.8719`, notional `951.86115`, `buy_near_touch_post_only_at_or_below_best_bid`, `passive_against_touch=true`, no private/order submission, no Cost Gate lowering.

## Boundary

- Canonical soak plan remains old `grid_trading|ETHUSDT|Buy`; it must not be consumed as the NEAR plan.
- BB does not authorize canonical plan write in this review, Bybit calls, Decision Lease, adapter enablement, order/probe, Cost Gate lowering, live/mainnet, or proof.
- BB also does not authorize `_latest` overwrite, DB/PG query/write, runtime/service/env/crontab mutation, cancel/modify, or promotion.

## Conditions

- PM must perform same-window source/runtime/hash/candidate/expiry recheck before any materialization.
- Any source, runtime, hash, candidate, canonical-plan, or expiry drift is `ROTATED`.
- If materialized later, it must be the exact reviewed `plan_preview`, written atomically with hash record, and still grants no order authority by itself.

## Next Step

PM may proceed to same-window plan materialization recheck only.

Order-capable Demo action still requires a separate fresh PM->E3->BB scope with active lease, fresh BBO/order shape, adapter/Rust authority, and auditability gates.
