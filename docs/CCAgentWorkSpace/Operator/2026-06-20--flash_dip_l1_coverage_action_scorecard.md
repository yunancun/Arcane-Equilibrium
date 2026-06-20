# 2026-06-20 -- FlashDip L1 Coverage Action Scorecard

PM source report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-20--flash_dip_l1_coverage_action_scorecard.md`.

Runtime read: latest FlashDip L1 replay artifact sha256 `bad7a5078217f11b292b948d3439d6e960b03c082c86caa4b8426cc3474441f9`; alpha latest sha256 `7775d35d0031b0c1eb787c0169142414baa8beb8f48800f9a421749836e4672b`.

Operator meaning: current FlashDip L1 blocker is `HISTORICAL_CANDIDATES_BEFORE_L1_CAPTURE_WAIT_NEXT_CANDIDATE`, not an immediate recorder repair. Existing missing windows ended before symbol L1 capture began. Next trigger is `wait_for_next_flash_dip_candidate_after_l1_capture_start_then_replay`.

Boundary: read-only PG plus local `/tmp/openclaw` artifact/log writes only. No engine/API restart, no rebuild, no strategy parameter change, no order/auth/risk/runtime mutation, and no Bybit private/signed/trading call.
