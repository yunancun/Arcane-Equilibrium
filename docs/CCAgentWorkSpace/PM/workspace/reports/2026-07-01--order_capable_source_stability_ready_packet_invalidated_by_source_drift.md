# Order-Capable Source-Stable Packet Invalidated By Source Drift

Date: 2026-07-01

Active blocker: `P0-CURRENT-CANDIDATE-ORDER-CAPABLE-DEMO-INVOKE-FRESH-WINDOW-RUN-GATE`

Status: `BLOCKED_BY_RUNTIME`

## Summary

PM started from actual clean source `HEAD == origin/main == 2ee1e1873c77a637c0f8806e0fa3174d5c917eab` and established session loop state:

- Initial state: `/tmp/openclaw/session_loop_state_20260701T0852Z_order_capable_current_head_2ee1e187_source_stability_retry/session_loop_state.json`, sha `511336ffd6f427a2d09505cf5a038c07d9d1c55d525fe86cd59f6739b175ff33`.
- Final state: `/tmp/openclaw/session_loop_state_20260701T0852Z_order_capable_current_head_2ee1e187_source_stability_retry/session_loop_state_final.json`, sha `3ad0c65f37379f7d0386331150461ad83e6fe94640d6f824198145161cfef9ac`.

The source-stability guard produced a real quiet-window checkpoint:

- First sample: `/tmp/openclaw/source_stability_window_guard_20260701T0853Z_2ee1e187_clean_detached_first_sample/source_stability_window_guard_first_sample.json`, sha `de4f484858d3e54dc0862b14f88647fd64c216eda2626ac98460025406ebdd59`, status `SOURCE_STABILITY_WINDOW_SAMPLE_RECORDED_NO_APPROVAL`.
- Ready check: `/tmp/openclaw/source_stability_window_guard_20260701T0856Z_2ee1e187_clean_detached_ready_check/source_stability_window_guard_ready_check.json`, sha `0d1e8619b94af2201a8b47e2af6651fb0734577b688103273ef90d54d7001bf8`, status `SOURCE_STABILITY_WINDOW_READY_FOR_E3_BB_REVIEW`, quiet elapsed `88.077425s`.

PM then rebuilt the no-runtime current-head evidence:

- Source contract: `/tmp/openclaw/order_capable_fresh_window_current_head_revalidation_20260701T0857Z_2ee1e187_source_stable_clean_head/source_contract/active_order_wiring_contract_eth_buy_current_head_noauth.json`, sha `80f36416e0f37c78307432d5ad9ee5245404e3e6c64f468ac89a205ccb9b5522`, status `ACTIVE_ORDER_WIRING_CONTRACT_READY_FOR_E3_BB_REVIEW`.
- Blocked packet: `/tmp/openclaw/order_capable_fresh_window_current_head_revalidation_20260701T0857Z_2ee1e187_source_stable_clean_head/packet/order_capable_demo_invoke_e3_bb_review_request.json`, sha `db1b85524a0bdf2a778d0d956999a85143ed358567d572612bc2e006f6a3f162`, status `CURRENT_CANDIDATE_ORDER_CAPABLE_DEMO_INVOKE_REVIEW_PACKET_BLOCKED_BY_LOSS_CONTROL`, loss-control blockers `["renewed_active_bbo_manifest_stale_for_review_packet"]`, authority violations `[]`.

Before generating the E3/BB stale-BBO refresh request, PM fetched again and observed source drift to `HEAD == origin/main == 87ce8fbbbad94b496f73ba93d259095ee89de3d7`. The `2ee1e187` source-stability ready artifact, source contract, and packet are therefore stale and not consumable.

## Runtime Snapshot

- Runtime host: `trade-core`
- Runtime repo: `/home/ncyu/BybitOpenClaw/srv`
- Runtime head: `e16d3323cb58a549262f6bfa6f1ef48ca140aea0`
- Runtime origin: `c5fce0c6008b783e8264ce06a3a5f781fe18c26e`
- Runtime status: `## main...origin/main [ahead 8, behind 164]`
- Runtime timestamp: `2026-07-01T08:58:20Z`
- `openclaw-trading-api.service`: active
- `openclaw-watchdog.service`: active

Runtime artifact snapshots under `/tmp/openclaw/order_capable_source_stability_ready_20260701T0856Z_2ee1e187_runtime_snapshots/` matched the expected standing auth, canonical soak plan, stale renewed-BBO manifest, and strict fill scan hashes. The soak plan still carries older bounded-auth timing and must be rechecked before any order-capable use.

## Boundary

No E3/BB request was dispatched. No Phase A/B execution occurred. No public Demo quote, private/order endpoint, Decision Lease acquire/release, PG write, service/env/risk mutation, Cost Gate change, live/mainnet action, order/cancel/modify, fill, PnL, or proof occurred.

## Next

Do not reuse the `2ee1e187` source-stability ready artifact or packet sha `db1b8552...`.

Next PM must start from current `HEAD == origin/main == 87ce8fbbbad94b496f73ba93d259095ee89de3d7` or newer, obtain a fresh clean source-stability quiet window, regenerate an exact-current-head request, and obtain both E3 and BB approval before any Phase A/B. If source continues to advance during review, stop as `BLOCKED_BY_RUNTIME` or coordinate an explicit source freeze; do not hard-loop stale approvals. Phase C/order remains blocked pending separate exact in-window E3/BB approval.
