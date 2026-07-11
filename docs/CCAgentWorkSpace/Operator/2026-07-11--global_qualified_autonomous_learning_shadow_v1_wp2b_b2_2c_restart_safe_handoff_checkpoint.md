# Operator Summary — WP2-B2.2c Restart-Safe Handoff

State: `DONE_SOURCE_ACCEPTED_B2_2C_RESTART_SAFE_HANDOFF`
Checkpoint: `328125a08e0f15057a110c69266d6a6ea71c8826`

B2.2c 已完成 source acceptance。candidate board v2 現在會綁定 immutable
handoff identity（board/evidence、source set/cursor、policy、prior decision、
decision time）。即使 scanner idle，新的 stamped board 仍可用既有 immutable
source rows重新評估；完全相同的 semantic handoff 只回傳
`SUPPRESSED_UNCHANGED`，零 artifact/provenance/payload 寫入。

restart/replay 時，既有 artifact 必須 kind、payload、hash、provenance edges 都
完全完整才可 suppression；缺 edge 或資料不一致會 fail closed。沒有 qualified
candidate 時仍寫 durable `target_rotation`，不會變成 training、serving、order 或
authority 行為。

驗證：focused `109 passed`；final integration `190 passed in 0.80s`；E2/QC/QA
PASS，P0/P1 `0/0`。本輪無 migration、cron、service、Linux、PG、Bybit、order、
Decision Lease、Cost Gate、training、serving、promotion 或任何 authority 動作。

這只是 source acceptance，runtime proof 必須另開 fresh exact E3/BB gate。下一個
source-only work 已切到 WP3 proof/reward adapters。
