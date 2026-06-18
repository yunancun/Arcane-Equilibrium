# TODO v182 SCHEMA-1 completed-row archive

已從 TODO §5 移出 `AUDIT-2026-06-14-SCHEMA-1`。

原因：SCHEMA-1 本體已完成，schema contract test / PR-only PG CI / audit_migrations informational-only relabel 都已在 repo；E2/E4 與 cold-audit fix-wave 報告已留證。

沒有隱藏剩餘 blocker：它原本牽出的 `MIGRATION-TREE-1` 已在 v171 archive pass 關閉，後續 migration 風險由 V### / Linux PG dry-run 規則承接。

邊界：文檔隊列整理；沒有 CI、沒有代碼改動、沒有 deploy/rebuild/restart、沒有 runtime/DB/auth/risk/order/trading mutation。
