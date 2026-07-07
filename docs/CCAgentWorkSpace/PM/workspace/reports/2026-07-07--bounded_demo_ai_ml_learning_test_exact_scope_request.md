# Bounded Demo AI/ML Learning Test Exact-Scope Request

Date: 2026-07-07

Role chain: PM -> E3 -> BB -> PM

## PM request

Open the same-window exact-scope gate for a bounded Demo AI/ML learning test on:

- Candidate: `grid_trading|ETHUSDT|Buy`
- Standing Demo cap: `954.18759458`
- Standing Demo expiry: `2026-07-08T01:53:48.341325+00:00`
- Source HEAD: `243e0cd6d57edb2039b144ed55b9a7556dcef633`

This request does not grant order/probe authority. It asks E3, then BB only if E3 approves, to decide whether the exact bounded Demo AI/ML learning-test scope can proceed.

## Current evidence

- Runtime/loss-control prior gate: `RUNTIME_LOSS_CONTROL_READY`
- Runtime readiness artifact: `/home/ncyu/BybitOpenClaw/var/openclaw/demo_only_engine_env_restoration_20260707T133658Z_e655de9/readiness/bounded_demo_runtime_readiness_after_materialization_engine544751.json`
- Runtime readiness SHA256: `b77946c0985680a2fe7ff0c332d2ce79e1c204d61e59e92295f88bd6104c05b6`
- Standing Demo authorization SHA256: `eabf2dab8ddbe9c680a4b047d7a338d5d34a30a28a36134ab820e83a1b174197`
- Source stability ready check: `/home/ncyu/BybitOpenClaw/var/openclaw/bounded_demo_ai_ml_learning_test_20260707T141248Z_243e0cd6d/source/source_stability_ready_check.json`
- Source stability ready SHA256: `4e67badd14e1bde3e4f4c20a5d24aeeef69dbbdb93e775c1feb5989fe68e35aa`
- Runtime precheck: `/home/ncyu/BybitOpenClaw/var/openclaw/bounded_demo_ai_ml_learning_test_20260707T141248Z_243e0cd6d/precheck/bounded_demo_ai_ml_learning_test_precheck.json`
- Runtime precheck SHA256: `7b3d6881f78446a9c4c053569dc7bd6aff4654a6b7436e2c55872151a226db49`

## Current blockers observed by PM precheck

- `false_negative_bounded_probe_preflight_latest_not_ready`
- `bounded_probe_placement_repair_plan_latest_not_ready`
- `bounded_probe_authority_patch_readiness_latest_not_ready`
- `bounded_probe_operator_authorization_latest_not_authorize`
- `no_existing_pm_supervised_one_shot_order_runner_identified`

## Exact requested scope if approved

1. Revalidate source/runtime/auth/readiness for the current candidate and active standing Demo envelope.
2. Refresh only no-order bounded probe/test readiness artifacts through existing reviewed helpers.
3. Use only existing reviewed public BBO/instrument and Decision Lease helpers if all prerequisite gates are READY.
4. Proceed to at most one Demo-only PostOnly near-touch limit-or-skip order only if BB approves the same exact scope, all machine gates are READY, and an existing PM-supervised audited runner is identified.
5. Skip rather than place if any gate is stale, missing, mismatched, or non-READY.

## Explicit denials

- No live/mainnet.
- No paper.
- No Cost Gate lowering or change.
- No DB write or migration.
- No secret value/hash/prefix/suffix output.
- No MCP server/config/credential access.
- No model promotion, symlink promotion, or serving reload.
- No runtime env mutation/restart.
- No direct exchange private read.
- No manual direct Bybit order path.
- No order/probe unless E3 and BB approve the same exact scope and all gates are machine READY.

## PM recommendation

PM recommends `BLOCKED_STOP_LOSS_CONTROL` unless E3 can identify a reviewed runner and show the bounded probe/test gate chain can be made machine READY within the exact scope. Use `STOP_BOUNDARY` for any requested scope expansion or unreviewed order path.
