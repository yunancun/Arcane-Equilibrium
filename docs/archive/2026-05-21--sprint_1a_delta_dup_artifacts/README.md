# Sprint 1A-δ Multi-Session Dual Write — Archived Dup Artifacts

**Date archived**: 2026-05-21
**Reason**: Sprint 1A-δ 3-4 sub-agent 並行派發 + parallel session 同時段 dual write，產生 5 pair dup naming artifact。R4 audit (a per dedup recommendation) 採用 ADR-aligned 版本；其餘版本歸檔此處供 reference + audit trail。

## Dedup Decisions（per R4 audit 2026-05-21 §Task 2）

| # | 棄置 file | KEEP 替代 file | KEEP 理由 |
|---|---|---|---|
| 1 | `2026-05-21--m5_model_client_design_spec.md` (36KB) | `2026-05-21--m5_online_learning_design_spec.md` (461 行) | 461 行版本 6 method (`get_predict / get_predict_streaming / drift_callback / rollback / throttle / health`) **完全對齊 ADR-0035 Decision 1**；棄置版本 6 method 缺 drift_callback / rollback / throttle 違反 Decision 1 |
| 2 | `2026-05-21--v114_m5_online_learning_reserved_schema_spec.md` (179 行) | `2026-05-21--v114_m5_model_versions_streaming_schema_spec.md` (190 行) | 190 行版本明確 EXTEND 既有 `learning.model_versions` 表 ADD COLUMN streaming_enabled + streaming_state，**完全對齊 ADR-0035 Decision 2**；棄置版本 14 section outline 抽象未對齊 Decision 2 |
| 3 | `2026-05-21--v115_m12_order_router_reserved_schema_spec.md` (208 行) | `2026-05-21--v115_m12_order_router_audit_schema_spec.md` (288 行) | 288 行版本命名更精確（V115 主軸是 audit log schema；對齊 ADR-0039 Decision 3 標題「Adaptive Routing Audit Schema」）+ 更詳細 column draft + hypertable 判斷 + retention/compression 範式 + V107 dedup OQ-3 |

## Pending operator 仲裁（未歸檔）

| # | dup pair | 推薦 |
|---|---|---|
| 4 | M13 design spec | MERGE — 取 `m13_multi_venue_asset_class_design_spec.md` (mine 427) 結構 + `m13_asset_class_venue_design_spec.md` (parallel 624) 細節，保 mine 檔名 per dispatch packet line 165 一致；MERGE 後 parallel mv 到本 archive |
| 5 | V116 schema spec | operator 仲裁 SPLIT vs MERGE：(a) MERGE `v116_m13_multi_venue_reserved_schema_spec.md` (mine 101) 三表 routing.venue_lifecycle + `v116_m13_asset_venue_dim_schema_spec.md` (parallel 288) reference.asset_class_dim + venue_dim 為 V116 三表 placeholder；(b) SPLIT V116 dim table（B 主軸）+ V117 venue audit（A 改 V117）— 推薦 (a) per R4 |

## Multi-Session Dual Write Rule

per memory `project_multi_session_memory_race` 2026-04-23：
- commit-first / 不認識改動禁 revert / 接手三連加 memory log 檢查 / 保留兩版供 operator 決定 canonical or merge

本歸檔反映 R4 audit 採 (a) ADR-aligned 推薦；保留棄置版本供 audit trail；不刪除。

## Reference

- R4 audit report inline 2026-05-21（task notification affd343f；§Task 2 5 dup naming dedup recommendation）
- Archive parent: `docs/archive/2026-05-21--sprint_1a_alpha_repair_closure.md` §J + §K
- Commit chain: `90c808ce` (Sprint 1A-δ 10 file land 含 dup) + (pending Sprint 1A-ε commit 含本 dedup)
