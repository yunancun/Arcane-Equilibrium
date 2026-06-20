# 2026-06-20 -- FlashDip Dependent L1 Blocker Propagation

PM source report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-20--flash_dip_dependent_l1_blocker_propagation.md`.

Runtime read: alpha latest sha256 `05d0baa71008cc31024c0e58bbe86b5c98f50edae0919691ffaabd519f57a585`, created `2026-06-20T18:50:21.382935+00:00`.

Operator meaning: `flash_dip_execution_realism` now inherits the L1 replay child blocker. Because L1 replay is `HISTORICAL_CANDIDATES_BEFORE_L1_CAPTURE_WAIT_NEXT_CANDIDATE`, execution-realism is also `engineering_actionable=false` and uses next trigger `wait_for_next_flash_dip_candidate_after_l1_capture_start_then_replay`.

Boundary: source/test/docs plus read-only artifact refresh only. No engine/API restart, no rebuild, no strategy parameter change, no order/auth/risk/runtime mutation, and no Bybit private/signed/trading call.
