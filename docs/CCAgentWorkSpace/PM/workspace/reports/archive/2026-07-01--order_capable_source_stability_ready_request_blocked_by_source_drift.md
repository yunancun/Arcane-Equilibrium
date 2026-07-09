# Order-Capable Source-Stable Request Blocked By Source Drift

Date: 2026-07-01

Active blocker: `P0-CURRENT-CANDIDATE-ORDER-CAPABLE-DEMO-INVOKE-FRESH-WINDOW-RUN-GATE`

Status: `BLOCKED_BY_RUNTIME`

## Summary

PM used the v707 source-stability guard from clean detached source `f20e753b3356d0f54d52276c25978da47f6fc57d` to produce a real quiet-window checkpoint:

- First sample: `/tmp/openclaw/source_stability_window_guard_20260701T0833Z_clean_detached_first_sample/source_stability_window_guard_first_sample.json`, sha `8dea787380242babcf36596db3250c9b4096e9e8189054de03ad1e62397f78d4`, status `SOURCE_STABILITY_WINDOW_SAMPLE_RECORDED_NO_APPROVAL`.
- Ready check: `/tmp/openclaw/source_stability_window_guard_20260701T0835Z_clean_detached_ready_check/source_stability_window_guard_ready_check.json`, sha `aa470b851bbd06af64ac01f49310326936a6ad9dbb0a687a7495744d6209eb67`, status `SOURCE_STABILITY_WINDOW_READY_FOR_E3_BB_REVIEW`, quiet elapsed `92.412202s`.

PM then regenerated current-head no-runtime review artifacts from the same clean source:

- Source contract: `/tmp/openclaw/order_capable_fresh_window_current_head_revalidation_20260701T0837Z_f20e753b_source_stable_clean_head/source_contract/active_order_wiring_contract_eth_buy_current_head_noauth.json`, sha `f2d2a3dec00a4ca3069b250799bdccb98fc6febcf8fda0175beb102184704a92`, status `ACTIVE_ORDER_WIRING_CONTRACT_READY_FOR_E3_BB_REVIEW`.
- Blocked packet: `/tmp/openclaw/order_capable_fresh_window_current_head_revalidation_20260701T0837Z_f20e753b_source_stable_clean_head/packet/order_capable_demo_invoke_e3_bb_review_request.json`, sha `979b86b0997f1c360b201ce9d8aa4f493c7a1db1f2fb8d430cf5d674cb1352ed`, blocked only by `renewed_active_bbo_manifest_stale_for_review_packet`, authority violations `[]`.
- E3/BB request: `/tmp/openclaw/renewed_active_bbo_e3_bb_review_20260701T0837Z_f20e753b_source_stable_clean_head_stale_manifest_refresh/e3_bb_active_lease_bbo_renewed_review_request.json`, sha `680be49cfdb40a91523361ef220b80fb03e74fa6b62ed1275690a31ebc6f4482`.
- Manifest: `/tmp/openclaw/renewed_active_bbo_e3_bb_review_20260701T0837Z_f20e753b_source_stable_clean_head_stale_manifest_refresh/manifest.json`, sha `be836f88dad6a3e0d904171a71b897a41f4ef7801347d7c4b263f66ca1c26b44`.

E3 returned `BLOCKED`: during review, current `origin/main` advanced to `f181ec892cd5cd93b2d3e13826008af7a67a2dd1`, tripping the request stop condition `source_head_or_origin_main_differs_from_request`. BB returned `APPROVE_WITH_CONDITIONS` for the exact request, but approval cannot be consumed without E3 and without a fresh exact-current-head source check.

## Verification

- Focused tests from clean worktree: `43 passed`.
- `py_compile` for `source_stability_window_guard.py`, `bounded_probe_active_order_wiring_contract.py`, and `current_candidate_order_capable_demo_invoke_review_packet.py`: passed.
- JSON sanity for source-stability samples, source contract, blocked packet, request, and manifest: passed.
- Runtime read-only check at `2026-07-01T08:32:35Z`: runtime source `e16d3323cb58a549262f6bfa6f1ef48ca140aea0`, runtime origin `c5fce0c6008b783e8264ce06a3a5f781fe18c26e`, API and watchdog services active.
- Runtime standing auth snapshot sha `8c891b4e675821118d79921631ccd07c29907130e24ee4dde1483f0be20cfe4f`, status `STANDING_DEMO_AUTHORIZATION_ACTIVE`, expiry `2026-07-01T17:16:05.473618+00:00`.
- Runtime soak plan snapshot sha `30056993b5cae70a0fcad0503221e12bd74dae4e42a29d0d2c88423c64739823`, status `READY_FOR_DEMO_LEARNING_PROBE`.

## Boundary

No Phase A/B execution occurred. No public Demo quote, private/order endpoint, Decision Lease acquire/release, PG write, service/env/risk mutation, Cost Gate change, live/mainnet action, order/cancel/modify, fill, PnL, or proof occurred.

## Next

Do not reuse request sha `680be49c...` or BB approval. Next PM must start from current `HEAD == origin/main == f181ec892cd5cd93b2d3e13826008af7a67a2dd1` or newer, obtain a fresh clean source-stability quiet window, regenerate an exact-current-head request, and obtain both E3 and BB approval before any Phase A/B. If source continues to advance during review, stop as `BLOCKED_BY_RUNTIME` or coordinate an explicit source freeze; do not hard-loop stale approvals. Phase C/order remains blocked pending separate exact in-window E3/BB approval.
