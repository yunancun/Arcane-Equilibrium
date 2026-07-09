# No-Order Refresh E3 Blocked By Source Drift 4eb

Active blocker: `P0-CURRENT-CANDIDATE-NOORDER-REFRESH-CURRENT-HEAD-E3-BB-REQUEST`

Status: `BLOCKED_BY_RUNTIME`

PM rotated from a stale `14f89fda...` sample to `4eb2022ef558c5e6a49b790141691d2b1d40dc42`, recorded runtime evidence at `2026-07-01T14:02:05Z`, produced source-stability READY sha `48e5ef0f839ca7a6a29569ccc6f6524127699d6092c382b6161bb3467720118d`, and generated exact request sha `406cf84724d21b2b4dc7b1d8267e5cc780bfa11c893f2edf0d6eff69e6d0e6c0`.

E3(explorer) verified the request and READY hashes but returned `BLOCKED_BY_SOURCE_DRIFT` because final fetch found `HEAD == origin/main == 3b480dc76b6535840a54841cbd20a90d88e34472`. BB was not dispatched.

Final docs-sync source is `46953ba5d5aa8f21a93b3bf5d83baf7284079ae0`, so the next run must restart from that source or newer.

Artifacts:

- Runtime snapshot: `/tmp/openclaw/noorder_refresh_current_head_20260701T140130Z_4eb2022e/runtime/runtime_snapshot.txt`, sha `8f5538bbdc1d4acb56a8c0259204e8f9fe2e3ef32eda7762fc6183c8ee51a525`.
- Source-stability READY: `/tmp/openclaw/noorder_refresh_current_head_20260701T140130Z_4eb2022e/source_stability/source_stability_window_guard_ready_check.json`, sha `48e5ef0f839ca7a6a29569ccc6f6524127699d6092c382b6161bb3467720118d`.
- Exact request: `/tmp/openclaw/noorder_refresh_current_head_20260701T140130Z_4eb2022e/review_request/current_head_noorder_refresh_e3_bb_review_request.json`, sha `406cf84724d21b2b4dc7b1d8267e5cc780bfa11c893f2edf0d6eff69e6d0e6c0`.
- E3 verdict: `/tmp/openclaw/noorder_refresh_current_head_20260701T140130Z_4eb2022e/review_request/e3_source_drift_verdict.json`, sha `eb715689120cefddf67f96af75e3fa0e63a0fc8a3d6db10addf9b3b64d524318`.
- Final state: `/tmp/openclaw/noorder_refresh_current_head_20260701T140130Z_4eb2022e/session_loop_state_final.json`, sha `971872de6b9ba152ea1c5c555cfc35f609db79f6a2129da210fcac5acb735ee0`.

Boundary: no Control API GET, no Bybit public/private call, no envelope rebuild, no plan preview, no Decision Lease, no canonical plan write, no `_latest`, no PG/service/env/risk mutation, no Cost Gate change, no live/mainnet, no order/fill/PnL/proof, and no BB dispatch.

Next: restart from `46953ba5d5aa8f21a93b3bf5d83baf7284079ae0` or newer with a fresh clean source-stability quiet window. The next exact request must still include a reviewed one-GET runtime-local fast-balance refresh path because v711 equity is stale under 900s.
