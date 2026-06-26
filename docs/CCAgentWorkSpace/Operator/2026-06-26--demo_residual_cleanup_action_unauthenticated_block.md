# Operator Note - Demo Cleanup Auth Block

Date: 2026-06-26

PM executed exactly one reviewed demo cleanup control API POST after fresh
E3/BB approval and fresh cursor-aware demo inventory.

Result: HTTP `401` with `reason_codes=["unauthenticated"]`.

The route did not execute, so no exchange order/position mutation occurred. PM
did not retry and did not use direct Bybit POST fallback.

Current next blocker:

`P1-RUNTIME-HEALTH-HYGIENE-CONTROL-API-AUTH-TOKEN-PATH`

Goal: establish a secret-safe authenticated CLI/control-plane invocation path
that uses the runtime API token source without printing or exfiltrating token
material, then refresh E3/BB before any second cleanup attempt.

Full report:

`docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--demo_residual_cleanup_action_unauthenticated_block.md`
