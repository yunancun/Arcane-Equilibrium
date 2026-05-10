# R4 文檔審計 — 2026-05-10 Sprint N+1 D+0 Pre-Sign-Off

**基準**：HEAD `1d9dccf1`、採集時間 2026-05-10、Mac dev session（Linux runtime 未實測）

## 1. docs/README.md 缺漏 list

**Tally：應登記 31 條 / 實登記 5 條（ARCH-04 + AMD-03 + AMD-04 + ADR-0021 + ADR-0022）= 16% 完整度** — 與 v3 verification（64%）相比 **再回退至 ~58%（30+ 篇 +5 治理 / 31+5 應有）**。

| 類別 | 缺漏 file | 缺漏數 | 嚴重性 |
|---|---|---|---|
| PA reports | 14 篇（除 a4c_btc_alt_lead_lag_spec.md 為副本可不雙登）| 13 | HIGH |
| QC reports | tonusdt_structural_edge_replay / w6_rfc_qc_questions / w2_a4c_qc_review | 3 | HIGH |
| MIT reports | tonusdt 對應 chain_integrity / governance_reject_baseline / w6_rfc_mit / w6_3a_close_tag / w2_c3_sigma_verify / sprint_n0_final_review / v083_v084_linux_pg_dry_run | 7 | HIGH |
| E1 reports | w_audit_8a_phase_a_trait / w_audit_4b_m3_part_2_rust_producer / w7_3_emergency_1tick / w2_w7_1_trait_skeleton | 4 | HIGH |
| E2 reports | sprint_n0_w2_second_batch_review / sprint_n0_w2_third_pass_review / w7_3_review | 3 | HIGH |
| E4 reports | sprint_n0_w2_regression_baseline / sprint_n0_w2_regression_third_pass / w7_3_regression / w_audit_3b_runtime_smoke_test_design | 4 | HIGH |
| BB reports | sprint_n0_final_bybit_compatibility_review / w1_w2_bybit_v5_rate_budget_review | 2 | HIGH |
| execution_plan specs | w_audit_8a_phase_b_tier_2_collector / a4c_btc_alt_lead_lag / p1_canary_stage_criteria_1 / p1_canary_cohort_freq_23 / p1_dynamic_unblock_check_1 | 5 | **CRITICAL** — Spec 是 IMPL 入口 |

**命名規範**：所有 41 件 file 命名均符合 `YYYY-MM-DD--描述.md` ✅、放入正確子目錄 ✅、無 docs/ 根 violation ✅。

**a4c_btc_alt_lead_lag_spec.md 雙路徑**：`PA/workspace/reports/` + `execution_plan/` 兩處皆有 — 屬 PA spec → execution_plan 副本，需 docs/README 雙登或註明「副本」關係。

## 2. Cross-reference accuracy verdict

**PASS（dispatch v3.7 內部 cross-ref 經 grep 全驗實存）**：
- 8 commit hash（b42731f6 / c9fb0b8f / db8d57ae / da6c1f80 / 4bb5d485 / d914c02e / b1e5d6da / 1d9dccf1）— 部分（b42731f6 / c9fb0b8f / da6c1f80 / db8d57ae）在 dispatch_draft 內可驗
- 21+ file path 引用 → 全 grep 命中真實檔
- §0.5 to §6 內所有 `srv/docs/CCAgentWorkSpace/...` ref 100% 存在

## 3. CLAUDE.md drift verdict

| 維度 | 狀態 | 結論 |
|---|---|---|
| §三 header `(2026-05-09 W-AUDIT-1 sync)` | 1 day 內，未過 7 日 | OK 但需補 N+0 closure 摘要 |
| §三 「Strategy / Edge」表 | 仍引 2026-05-08 PA audit + 2026-05-09 3C 7d audit | **DRIFT MED**：memory `project_2026_05_10_sprint_n0_closure.md` 已標 [40] avg_net `-17.82→+8.75 bps`，§三 仍寫 `-17.82bps vs baseline -16.70bps`。Sprint N+0 closure runtime 已 verify，§三 數值 stale |
| §三 「Active Blockers」 | 列 W-AUDIT-1..7 | **DRIFT HIGH**：Sprint N+0 已 land W-AUDIT-9 V80/82/83/84，TODO §11.1 已派 W-AUDIT-3b/8a Phase A/4b/6c/6d 進入 Sprint N+0；§三 未提 Sprint N+0 active；W-AUDIT-1/2 source-closed 但仍列 active |
| §三 「W-C / MAG-082」 | 2026-05-08 22:09 UTC 數據 | 採集時間 2 day 前，未過 7 日 OK |
| §十 「下一步工作指針」 | 引 W-AUDIT-1..7 路徑 | **DRIFT HIGH**：未提 v3.7 dispatch / Sprint N+0 closure / Sprint N+1 D+0；operator decision pending sign-off 階段需 §十 補 v3.7 dispatch path 引用 |
| §三 衛生規則「runtime 數值必註採集時間」 | [33]/[38]/[40]/[42b]/[42c]/[45]/[51]/[56] 多無時間戳 | **G6-04 DRIFT MED**：除 [56]（09:41 UTC）外多數 cell 缺顯式 ISO timestamp |

## 4. Memory + SCRIPT_INDEX 更新清單

- **MEMORY.md** 已含 `[Sprint N+0 closure 2026-05-10](project_2026_05_10_sprint_n0_closure.md)` ✅；但需新增 `[Sprint N+1 D+0 pre-dispatch readiness 2026-05-10]` 條目於 N+1 dispatch fire 後
- **SCRIPT_INDEX.md** grep 0 條 2026-05-10 entry ✅（本日無新 helper script），無需 update
- **R4 memory.md**：本次 audit 後 append 「2026-05-10 N+1 D+0 docs audit pre-signoff」+ 報告索引條目（指向本 audit）
- 各 agent memory（PA/QC/MIT/E1/E2/E4/BB）2026-05-10 update 多數已落（grep 12 hit）✅

## 5. Governance doc drift（ARCH/ADR/AMD review）

| Doc | 狀態 | 對 v3.7 dispatch 是否 valid |
|---|---|---|
| ARCH-04 graduated canary | 已 land docs/architecture/2026-05-10--ARCH-04-graduated-canary-5-stage.md | ✅ valid，dispatch §11.1 W-AUDIT-9 Sprint N+0 IMPL T1-T7 對齊 |
| ADR-0022 strategist-cap wide-parameter-adjustment-skill | 已 land + commit `75b6e5f2` | ✅ valid，dispatch §17 invariant 17 引 |
| AMD-2026-05-09-03 graduated canary default | docs/README 線 188 引 | ✅ valid（2 day 前）|
| AMD-2026-05-10-03 invariant-5-wording-n0-scope | 已 land | ✅ valid，dispatch invariant 5 對齊 |
| AMD-2026-05-10-04 toml-drift-fix-sop | 已 land | ✅ valid，TODO §11.1 W3 cohort 拍板對齊 |
| ADR-0021 alpha-source-architecture-upgrade | docs/README 線 169 已加 | ✅ valid |

**無 v3.7 取代 / 廢棄 governance doc**。

## 6. Fix Priority

**CRITICAL（Sprint N+1 D+0 sign-off 前同 commit 修）**：
1. **docs/README.md** 加新 section `### 2026-05-10 Sprint N+0 closure + Sprint N+1 D+0 pre-dispatch index addendum`，登記 31 條 file（含 5 條 execution_plan spec — IMPL 入口禁缺）

**HIGH（D+0 dispatch 前修）**：
2. **CLAUDE.md §三 Strategy / Edge** 表更新 `[40]` 為 `+8.75 bps`（per memory N+0 closure）+ 註明採集時間
3. **CLAUDE.md §三 Active Blockers** 表加 Sprint N+0 active rows / 移 W-AUDIT-1/2 至 source-closed
4. **CLAUDE.md §十** 補 v3.7 dispatch path + Sprint N+0 closure memory pointer

**MED（D+0 dispatch fire 同 commit 修）**：
5. **CLAUDE_CHANGELOG.md** 新增 2026-05-10 Sprint N+0 closure entry（記 V80/82/83/84 land + invariant 14✅/6 DEFER/2 PARTIAL/0 FAIL + ADR-0022/ARCH-04/AMD-03/04 land + commit `b6ed4975`）
6. **R4 memory.md** append 本次 audit + 報告索引條
7. **§三 衛生 G6-04**：[33]/[38]/[40]/[42b]/[42c]/[45]/[51] 7 cell 補採集時間戳

**LOW（next R4 cycle）**：
8. **R4 SOP**：v3 verification 已揭 5-commit window 索引維護是 pull-model；建議 N+1 PM dispatch fire SOP 強制觸發 R4 quick docs sync
