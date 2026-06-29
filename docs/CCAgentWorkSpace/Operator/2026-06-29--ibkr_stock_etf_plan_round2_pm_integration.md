# Operator Brief — IBKR Stock/ETF Plan 二輪對抗性審核

日期：2026-06-29
結論：工程方向有效，但仍只批准 Phase 0。

## Verdict

八角色第二輪審核（CC / FA / PA / E3 / E5 / QC / MIT / QA）沒有發現可以跳過
Phase 0 的捷徑。相反，它們一致確認：

- 不能確認「無遺漏」。
- 不能確認「按排程後完整上線」。
- 不能批准 Phase 1+ 實作。
- 不能觸碰 IBKR API、secret、paper order、GUI runtime 或 evidence clock。

## 最重要的變更

Phase 0 不再只是「寫一份 ADR」。它必須產出一整包可審核契約：

- `broker_capability_registry_v1`
- `phase2_ibkr_external_surface_gate_v1`
- `lane_scoped_ipc_v1`
- `ibkr_paper_order_lifecycle_v1`
- `stock_etf_db_evidence_ddl_v1`
- `gui_lane_contract_v1`
- `stock_etf_evidence_clock_v1`
- `stock_etf_release_packet_v1`
- `stock_etf_kill_switch_and_disable_cleanup_runbook_v1`

## PM 判斷

這條 stock/ETF lane 值得繼續探索，但正確做法是先把 contract、negative tests、
data lineage、release artifacts 和 disable path 寫死，再讓 E1 實作。提前接
IBKR connector 會累積技術債。

下一步只允許：Phase 0 ADR/AMD + named contract packet。

仍禁止：Phase 1 code、IBKR healthcheck、secret slot、paper fill import、paper order
rehearsal、GUI runtime、6-8 週 evidence clock、tiny-live/live。
