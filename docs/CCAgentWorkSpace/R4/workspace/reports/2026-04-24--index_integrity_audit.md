# R4 索引完整性審計報告
# R4 Index Integrity Audit

**日期**：2026-04-24
**對象**：TradeBot 全項目所有索引（12 核心索引 × 存在 / broken / orphan / 時效 / 分類 / 肥瘦 / 跨索引矛盾）
**基準**：CLAUDE.md §七「強制同步規則」+ §十關鍵文件指針 + §十一索引結構
**前次 R4 報告**：`2026-04-01--document_index_audit.md`（23 天前）
**模式**：審計，不修索引

---

## 零、TL;DR（8 個嚴重，3 個極嚴重）

| 編號 | 嚴重性 | 問題 | 索引 |
|---|---|---|---|
| **R4-2024-01** | **CRITICAL** | `docs/README.md` 4 天未更新，20 個 2026-04-12 之後的 reference / 8 個最新 audit / 21 個頂層 worklog / 26 個 archive 全部未列 | `docs/README.md` |
| **R4-2024-02** | **CRITICAL** | `sql/migrations/README.md` 只列 V001–V005，實際 V006–V023 共 18 個 migration（+ templates/ + tests/ 子目錄）完全未索引；V004 檔名不對（README 寫 `V004__learning_features_obs_risk_news_tables.sql` 實際為 `V004__learning_features_obs_risk_tables.sql`） | `sql/migrations/README.md` |
| **R4-2024-03** | **CRITICAL** | `docs/CLAUDE_REFERENCE.md` 最後更新 2026-04-12，12 天未同步；標榜為「主索引速查」卻遺漏 2026-04-15 後全部 reference / audit / worklog | `docs/CLAUDE_REFERENCE.md` |
| R4-2024-04 | HIGH | `docs/archive/` 無 `README.md` / `index.md`，30 個歸檔文件全部僅靠外部索引間接引用，無內部導航 | `docs/archive/` |
| R4-2024-05 | HIGH | `helper_scripts/SCRIPT_INDEX.md` 漏 11 個 active script（`linux_bootstrap_db.sh` / `mac_bootstrap_db.sh` / `v2_swap_24h_observation.sh` / 5 個 db/*.py+sh / `research/bb_breakout_threshold_sweep.py` 等） | `helper_scripts/SCRIPT_INDEX.md` |
| R4-2024-06 | HIGH | `docs/CLAUDE_CHANGELOG.md` 4 處 ghost link（`2026-04-14--engine_self_healing.md` 等指向不存在路徑，實際上 2026-04-14 worklog audit 已合併刪除） | `docs/CLAUDE_CHANGELOG.md` |
| R4-2024-07 | HIGH | `docs/README.md` 大量 ghost link（17 個 phase5_arch_rc1 session-level 文件 + control_api_gui 中 2026-04-04/06/07 session 分項文件），已合併到 daily_summary 後未更新 README | `docs/README.md` |
| R4-2024-08 | MEDIUM | 根目錄 `SCRIPT_INDEX.md` / `LOGICAL_SCRIPT_CATEGORY_MAP.md` **不存在**（任務清單指向） | 根目錄 |
| R4-2024-09 | MEDIUM | R4 workspace 自身 `memory.md` 2026-03-31 後無任何更新；所謂「持續積累」實際 23 天空白（含本次審計前） | `R4/memory.md` |
| R4-2024-10 | MEDIUM | `docs/CCAgentWorkSpace/README.md` 未更新至 §三 2026-04-23 reframe（仍寫 17 個 Agent，QC 角色存在但未列入表格分類） | `docs/CCAgentWorkSpace/README.md` |
| R4-2024-11 | LOW | `docs/CLAUDE_CHANGELOG.md` 1976 行 · 106 條目，已越過 §七建議肥瘦線（>200 行），但作為歸檔編年本可接受 | `docs/CLAUDE_CHANGELOG.md` |

---

## 一、索引 × 狀態彙總表

| # | 索引 | 存在 | Broken links | Orphans | 最後 mtime | 實際最新文件 mtime | 差距 | 狀態 |
|---|---|---|---|---|---|---|---|---|
| 1 | `docs/README.md` | ✅ | **17+** | **75+** | 2026-04-20 21:31 | 2026-04-24 02:54 | 4 天 | **CRITICAL stale** |
| 2 | `docs/CCAgentWorkSpace/README.md` | ✅ | 0 | 1（QC 未分類） | 2026-04-20 21:31 | 2026-04-20 | 4 天 | MEDIUM stale |
| 3 | `docs/CLAUDE_CHANGELOG.md` | ✅ | **4** | 0（不負責 index 全集） | 2026-04-24 02:54 | current | 0 天 | **HIGH broken links only** |
| 4 | `docs/CLAUDE_REFERENCE.md` | ✅ | 0 | **30+** | 2026-04-20 21:31 | 2026-04-24 | 4 天 | **CRITICAL stale** |
| 5 | CLAUDE.md §三「已完成里程碑索引」 | ✅ | 0 | 0 | 2026-04-24 02:53 | current | 0 天 | OK |
| 6 | `TODO.md` | ✅ | 1（glob pattern，非檔） | N/A | 2026-04-24 02:50 | current | 0 天 | OK |
| 7 | `docs/archive/` index | ❌ 缺失 | N/A | 30 個檔 | — | — | — | HIGH 缺失 |
| 8 | auto-memory `MEMORY.md` | ✅ | 0 | 0 | — | — | 0 天 | OK |
| 9 | `helper_scripts/SCRIPT_INDEX.md` | ✅ | 0 | **11** | 2026-04-24 01:51 | 2026-04-24 | 0 天 | HIGH missing entries |
| 10 | 根 `SCRIPT_INDEX.md` | ❌ 不存在 | — | — | — | — | — | MEDIUM（任務 prompt 有列） |
| 10b | 根 `LOGICAL_SCRIPT_CATEGORY_MAP.md` | ❌ 不存在 | — | — | — | — | — | MEDIUM（任務 prompt 有列） |
| 11 | `sql/migrations/README.md` | ✅ | 1（檔名拼錯） | **18**（V006-V023） | 2026-04-20 21:31 | 2026-04-24 01:03 | 4 天 | **CRITICAL stale** |
| 12a | `docs/references/` 子目錄 index | ❌ 無單獨 | — | — | — | — | — | LOW（`docs/README.md` 有覆蓋） |
| 12b | `docs/audits/` 子目錄 index | ❌ 無單獨 | — | — | — | — | — | LOW（同上） |
| 12c | `docs/worklogs/` 子目錄 index | ❌ 無單獨 | — | — | — | — | — | LOW（同上） |

> **註**：mtime 顯示為 `Apr 20 21:31` 是 repo 2026-04-20 首次 clone 時的 checkout 時刻；實際檔案內容從 git 看 `2026-04-12` 以後未被 commit 觸碰。

---

## 二、明確遺漏清單（文件存在但索引沒列）

### 2.1 `docs/README.md` 未索引（75+ 個，按目錄分）

**docs/audits/**（8 個）:
- 2026-04-15--edge_predictor_backend_selection.md
- 2026-04-16--demo_zero_strategy_exit_audit.md
- 2026-04-16--g2_funding_arb_clean_edge.md
- 2026-04-17--g2_funding_arb_clean_edge_v2.md
- 2026-04-18--e5_full_codebase_audit.md
- 2026-04-20--edge_p2_3_phase1b_bybit_postonly_audit.md
- 2026-04-20--pyo3_eliminate_phase2_e2_review.md
- 2026-04-24--todo_refactor_audit.md

**docs/references/**（12 個）:
- 2026-04-12--g_sr1_signal_tightening_plan_v2.md + `_v2.5.md`
- 2026-04-13--r06_deep_analysis_agent_value.md
- 2026-04-14--fa_phantom_fup7_margin_threshold_decision.md
- 2026-04-15--arch_rc1_unified_config_contract.md · edge_predictor_spec.md · fa_phantom_2_fix_spec.md
- 2026-04-16--phantom2_fup_reduce_to_half_cascade_rca.md · python_rust_dedup_cleanup_plan.md · reconciler_burst_escalation_rca.md
- 2026-04-17--adaptive_exit_fasttrack_proposal.md
- 2026-04-23--model_canary_promotion_rules_draft.md

**docs/worklogs/**（頂層，21 個）:
- 2026-04-14--daily_summary.md
- 2026-04-15--daily_summary.md
- 2026-04-16--p0_0_deploy_and_p0_5_discovery.md
- 2026-04-17--daily_summary.md
- 2026-04-18--dual_track_exit_design.md · live_gate_binding_1_implementation.md · live_gate_fallback_1_implementation.md · session_progress_p06_permanent_fix.md
- 2026-04-18-1--dual_track_exit_feasibility.md · 2026-04-18-2--exit_features_table_design.md
- 2026-04-19-2--track_p_counterfactual_audit.md
- 2026-04-20--p1_5_a2_drawdown_continuity_implementation.md · pyo3_eliminate_phase2_migration_spec.md
- 2026-04-21--decision_outcomes_rca.md
- 2026-04-22--backfill_labels_stalled_rca.md · counterfactual_replay_audit_spec.md · p0_13_14_execution_resume_plan.md · p0_13_atr_scale_qc_research.md · p0_14_edge_estimates_miss_rca.md · p1_10_ma_crossover_sl_tp_audit.md · passive_wait_silent_fail_audit.md

**docs/archive/**（26 個，全部未建獨立索引）:
完整 ls 見附錄 A。

### 2.2 `sql/migrations/README.md` 未索引（18 個）

V006 policies / V007 ledger / V008 fills_fee / V009 phase4_ml / V010 ai_budget / V011 foundation / V012 directive_exec / V013 weekly / V014 engine_events / V015 engine_mode_sep / V016 learning_fb / V017 edge_predictor + V017_rollback / V018 paper_state / **V019 strategist** / **V020 tie_break** / **V021 fills_exit_source** / **V023 model_registry** / V999 exit_features

**+ `sql/migrations/templates/`** 子目錄（新 schema guard templates，2026-04-24 新增，CLAUDE.md §七「新 SQL migration 規範」強制引用）**完全未索引**。
**+ `sql/migrations/tests/`** 子目錄（`test_schema_guards.sql`）**完全未索引**。

### 2.3 `helper_scripts/SCRIPT_INDEX.md` 未索引（11 個）

- `linux_bootstrap_db.sh`（DB 初始化，CLAUDE.md §七 Engine 自動遷移章節明確引用）
- `mac_bootstrap_db.sh`（Mac 對應工具）
- `v2_swap_24h_observation.sh`（Track P v2 觀察腳本）
- `db/audit_migrations.py`（V023 silent-noop postmortem 核心工具，CLAUDE.md §七 引用）
- `db/check_migration_status.py`
- `db/counterfactual_v2_parity.py`（EDGE-DIAG-1 工具鏈）
- `db/phase1a_c_readiness.py`
- `db/deploy_V017.sh` / `db/deploy_V018.sh`
- `db/passive_wait_healthcheck.sh`（Cron wrapper，CLAUDE.md §七「被動等待 TODO 必附 healthcheck」核心）
- `research/bb_breakout_threshold_sweep.py`（P1-11 Phase 1 sweep 工具，2026-04-24 新增）

### 2.4 `docs/CLAUDE_REFERENCE.md` 未列入「參考文檔」表（30+）

該索引自認是「參考資料按需讀取」速查，卻止步於 2026-04-12；2026-04-15 後的 `arch_rc1_unified_config_contract.md` / `edge_predictor_spec.md` / 全部 phantom/dedup/live_gate 系列等新增都未納入。

---

## 三、幽靈清單（索引列了但文件不在了）

### 3.1 `docs/CLAUDE_CHANGELOG.md` 的 ghost links（4 個）

| Ghost path | 可能現狀 |
|---|---|
| `docs/worklogs/2026-04-10--ml_pipeline_remediation_complete.md` | 合併到 2026-04-10 daily_summary 後刪除 |
| `docs/worklogs/2026-04-12--gui_metrics_db_fallback_and_display_fixes.md` | 同上，已合併 |
| `docs/worklogs/2026-04-14--engine_self_healing.md` | README.md 有列，實際已刪（2026-04-14 worklog audit 明載「所有舊碎片已合併至 daily_summary 並刪除」）|
| `docs/worklogs/2026-04-14--qol_1_and_qol_3_delivery.md` | 同上 |
| `docs/worklogs/2026-04-15--lane_a_ml_mit_26_trainer_handover.md` | 同上 |

### 3.2 `docs/README.md` 的 ghost links（17 個，均屬合併後遺留）

`docs/worklogs/phase5_arch_rc1/` 下：
- 2026-04-04--session4_bybit_api_audit.md / session5_bybit_full_integration.md / td01_td02_td03_file_split.md
- 2026-04-06--session10_r0_r1_remediation.md / session11_p1_6_drift_detector.md / session11_r2_batch.md
- 2026-04-06--session11_precompact.md / session12_precompact.md / session13_precompact.md / session_progress_2.md
- 2026-04-07--session_arch_rc1_1a_1b.md / 1c1_1c2.md / 1c2_complete.md
- 2026-04-07--session_phase4_1_complete.md / session_phase4_complete.md

`docs/worklogs/` 頂層：
- 2026-04-14--engine_self_healing.md · 2026-04-14--qol_1_and_qol_3_delivery.md

實測：`ls docs/worklogs/phase5_arch_rc1/` 只剩 5 個 daily_summary.md（04-03~04-07），所有 session-level 文件已刪除。

### 3.3 `sql/migrations/README.md` 的檔名拼錯（1 個）

README 列：`V004__learning_features_obs_risk_news_tables.sql`
實際：`V004__learning_features_obs_risk_tables.sql`（無 `_news`）

---

## 四、跨索引矛盾與分類問題

### 4.1 `docs/CCAgentWorkSpace/README.md` 漏 QC 角色分類

`docs/README.md` 第 614 行有 `CCAgentWorkSpace/QC/ — Quantitative/Math Auditor` 分類於「專項審查層」；但 `docs/CCAgentWorkSpace/README.md` 的 Agent 索引表（行 28–45）QC 行明確存在，列於「顧問層」——跨索引層級不一致。
- docs/README.md → 專項審查層
- CCAgentWorkSpace/README.md → 顧問層

### 4.2 `docs/README.md` 第 40 行仍列 `incidents/` 目錄

「2026-04-01 R4 audit」R4-05 已指出該目錄不存在，23 天未修正。實測：`docs/incidents/` 確實不存在。

### 4.3 CLAUDE.md §三 里程碑表（17 個 row）vs CLAUDE_CHANGELOG（106 個 entry）vs archive/（26 個 snapshot）

三處**量級不一致**但並非矛盾：
- §三表 = 不重複 1-liner（每日 1 row）
- CHANGELOG = 每個 commit/里程碑單獨一條
- archive = 只留大批量歸檔檔

惟 `CLAUDE.md §三` 只列「已完成里程碑」但許多條目同日合併多 commit，**無 archive 對應**（如 2026-04-23 一行涵蓋 DEDUP 收尾 + INFRA-PREBUILD-1 A+B，但 `docs/archive/2026-04-23--*` 不存在，只能依賴 §三 自身 + CHANGELOG 文字敘述）。

---

## 五、索引自身過肥/過稀

| 索引 | 行數 | 判斷 | 備註 |
|---|---|---|---|
| `docs/README.md` | 615 | 過肥但分類合理 | §七無硬上限，只需內容準確 |
| `docs/CCAgentWorkSpace/README.md` | 50 | 適中 | 無補強壓力 |
| `docs/CLAUDE_CHANGELOG.md` | 1976 | 極肥 | 作為編年歸檔可接受，但已有 106 條目 |
| `docs/CLAUDE_REFERENCE.md` | 181 | 瘦但過期 | 標榜「主索引速查」實際只覆蓋到 2026-04-12 |
| `CLAUDE.md` 全檔 | 443 | 正常 | §七有 800 警告線、1200 硬上限（code 文件用） |
| `TODO.md` | 700 | 稍肥 | 活躍任務表不受 §七限制 |
| `helper_scripts/SCRIPT_INDEX.md` | 86 | 瘦但有漏 | 應補齊 11 個活動 script |
| `sql/migrations/README.md` | 65 | 嚴重過稀 | 只覆蓋 5/23 migration |

---

## 六、時效性矩陣

| 索引 | 最後修訂 | 當前系統狀態最後重要事件 | 時效差 |
|---|---|---|---|
| `docs/README.md` | 2026-04-20 21:31 | 2026-04-24 02:54（P1-11 + FIX-26-DEADLOCK-1 + CLAUDE.md update） | **4 天** |
| `docs/CLAUDE_REFERENCE.md` | 2026-04-12 | 2026-04-24 | **12 天** |
| `docs/CCAgentWorkSpace/README.md` | 2026-04-20 | 2026-04-24 | **4 天** |
| `sql/migrations/README.md` | 2026-04-11（FIX-35 執行後未觸碰） | 2026-04-24（V023 入 repo） | **13 天** |
| `helper_scripts/SCRIPT_INDEX.md` | 2026-04-24 01:51 | 2026-04-24 02:54 | 0 天 |
| `docs/CLAUDE_CHANGELOG.md` | 2026-04-24 02:54 | 0 天 | 0 天 |
| CLAUDE.md §三 | 2026-04-24 02:53 | 0 天 | 0 天 |
| `TODO.md` | 2026-04-24 02:50 | 0 天 | 0 天 |

**關鍵發現**：主流「活文件」（CLAUDE.md / TODO.md / CHANGELOG）同步良好；**「目錄索引」類文件（README 系列 + migration README）全面落後**，反映 operator 工作流重心集中在產出不在維護索引。

---

## 七、R4 Workspace 自身狀態

| 項目 | 狀態 |
|---|---|
| `R4/memory.md` 最後有效更新 | 2026-03-31（Wave 4 完成記錄；「項目上下文」條目指當時狀態） |
| `R4/workspace/reports/` | 僅 1 個舊報告 `2026-04-01--document_index_audit.md` |
| 「工作記憶」章節 | 仍為「首次啟動，記憶從這次任務開始積累」模板 |
| 報告索引 | 全空（`| — | — | — |`） |

**診斷**：R4 自 2026-04-01 後被閒置，與 2026-04-24 系統實際狀態脫節 23 天。本次審計為 R4 第 2 份報告。

---

## 八、建議優先級（不修，僅建議）

### P0（立即必修，索引失真直接影響 session 接手效率）
1. **`docs/README.md` 大更新** — 批量補 75+ 個新檔 + 清 17 個 ghost + 修 `incidents/` 結構圖 + 同步至 2026-04-24
2. **`sql/migrations/README.md` 重建** — 18 個 migration + templates/ + tests/ 子目錄 + V004 檔名拼錯
3. **`docs/CLAUDE_REFERENCE.md` 更新** — 加 2026-04-13 至 2026-04-23 所有重要 reference/audit/worklog

### P1（next sprint）
4. **`docs/archive/` 建 `README.md` index** — 30 個歸檔檔無獨立導航
5. **`helper_scripts/SCRIPT_INDEX.md` 補 11 個** — 含 CLAUDE.md §七 引用的 `audit_migrations.py` / `passive_wait_healthcheck.sh` / `linux_bootstrap_db.sh`
6. **`docs/CLAUDE_CHANGELOG.md` 清 4 個 ghost link** — 僅需文字編輯
7. **CCAgentWorkSpace/README.md 跨索引對齊** — QC 角色層級與 docs/README.md 一致

### P2（積壓）
8. **根 `SCRIPT_INDEX.md` / `LOGICAL_SCRIPT_CATEGORY_MAP.md` 建立或從任務 prompt 刪除引用** — 避免誤導
9. R4 `memory.md` 建立持續更新習慣（本報告附加到「報告索引」表）

---

## 附錄 A：`docs/archive/` 完整列表（30 個，全部未納入 docs/README.md 的 archive 區塊）

```
2026-04-01--completed_todo_archive_wave0_7_phase1_3.md
2026-04-03--completed_todo_archive_batch9a_wave8_xp.md
2026-04-03--data_storage_architecture_optimal_draft_v0.1.md
2026-04-03--rust_migration_master_plan_v2.md
2026-04-03--rust_migration_v2.5_consolidated.md
2026-04-03--system_snapshot_external_analysis.md
2026-04-04--completed_todo_archive_phase0123_rust.md
2026-04-06--completed_todo_archive_l3_phases.md
2026-04-07--claude_md_section3_history_phase0_4.md
2026-04-08--arch_rc1_1c_history_archive.md
2026-04-08--main_docs_1c3_1c4_narrative.md
2026-04-09--scanner_todo_phase_a_d_spec.md
2026-04-10--completed_todo_live_gui_dead_py.md
2026-04-11--completed_todo_3e_arch.md
2026-04-11--completed_todo_w19_w20_phase6.md
2026-04-12--changelog_archive_pre_0408.md
2026-04-12--completed_todo_full_program_audit.md
2026-04-13--changelog_archive_0408_0409.md
2026-04-14--completed_todo_w22_phantom_heal.md
2026-04-15--claude_md_section3_snapshot.md
2026-04-15--completed_todo_w22_engine_heal_edge_p3.md
2026-04-15--phase5_promotion_edge_crisis_full.md
2026-04-16--completed_todo_strategy_close_tag_edge_p3_dedup.md
2026-04-17--completed_todo_p0_scanner_phantom_live_guard.md
2026-04-20--claude_md_section3_snapshot.md
2026-04-20--completed_todo_batch.md
2026-04-21--claude_md_section3_snapshot.md
2026-04-21--completed_todo_batch.md
2026-04-22--step_0_derived_todo_batch.md
2026-04-24--completed_todo_batch.md
```

**觀察**：CLAUDE.md §三「里程碑索引」+ TODO.md 尾部有局部對照引用，但沒有一個 index 將這 30 個檔視為 archive 集合做分類管理。

---

## 附錄 B：統計摘要

```
核心索引盤點：12 個（11 聲明存在 + 1 缺失 + 2 不存在）
實際檢查覆蓋：docs/README.md + 4 個子目錄 + 2 個 Agent README + migration + scripts + auto-memory + CLAUDE.md §三 + TODO.md
Orphan 文件總數：~75+（docs/）+ 18（sql/migrations/）+ 11（helper_scripts/） = 約 104 個文件索引缺失
Ghost link 總數：17（docs/README.md）+ 4（CHANGELOG）+ 1（migration 拼錯） = 22 個
跨索引矛盾：QC 角色層級 / incidents/ 結構圖殘留
時效落後 ≥4 天：3 個核心索引（README + CLAUDE_REFERENCE + CCAgentWorkSpace README）
時效落後 ≥12 天：2 個（CLAUDE_REFERENCE + migration README）
```

---

*R4 Document Auditor*
*2026-04-24*
*純審計報告，未修改任何索引文件。*

R4 AUDIT DONE: docs/CCAgentWorkSpace/R4/workspace/reports/2026-04-24--index_integrity_audit.md
