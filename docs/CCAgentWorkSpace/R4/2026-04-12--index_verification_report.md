# R4 索引完整性驗證報告

**日期**：2026-04-12
**角色**：R4 (Reference/Index Maintainer)
**範圍**：全項目索引文件交叉驗證

---

## 一、docs/README.md 文檔索引

### 1.1 worklogs/chapters_a-g/（11 條目）

| 條目 | 狀態 |
|------|------|
| `2026-03-11--openclaw_bybit_进度日志.txt` | [OK] |
| `2026-03-12--openclaw_bybit_进度日志.txt` | [OK] |
| `2026-03-13--详细工作日志.txt` | [OK] |
| `2026-03-13--三日补充综合日志.txt` | [OK] |
| `2026-03-17--chapter_g_工程记录.txt` | [OK] |
| `2026-03-17--chapter_g_执行清单.txt` | [OK] |
| `2026-03-17--engineering_log.txt` | [OK] |
| `2026-03-19--补充记录1.txt` | [OK] |
| `2026-03-19--当前进度图_校正后.txt` | [OK] |
| `2026-03-19--工作记录_含0317至0319校正与修复.txt` | [OK] |
| `2026-03-19--完整版当前进度图.txt` | [OK] |

**結論**：磁盤 11 文件 = 索引 11 條目，完全匹配。

### 1.2 worklogs/chapters_h-i/（14 條目）

| 條目 | 狀態 |
|------|------|
| 全部 14 條目 | [OK] 磁盤完全匹配 |

**結論**：完全匹配。

### 1.3 worklogs/chapters_j-k/（11 條目）

| 條目 | 狀態 |
|------|------|
| 全部 11 條目 | [OK] 磁盤完全匹配 |

**結論**：完全匹配。

### 1.4 worklogs/control_api_gui/（~50 條目）

| 條目 | 狀態 |
|------|------|
| 全部已索引條目 | [OK] 磁盤文件存在 |
| `2026-03-31--round2_batch_records_archive.md` | [OK] 磁盤存在，索引已收錄 |

**結論**：完全匹配。

### 1.5 worklogs/phase5_arch_rc1/（21 條目）

| 條目 | 狀態 |
|------|------|
| 全部 21 條目 | [OK] 磁盤完全匹配 |

**結論**：完全匹配。

### 1.6 worklogs/learning/（1 條目）

| 條目 | 狀態 |
|------|------|
| `2026-03-26--L章_自动学习管线与安全加固_完整工程日志.md` | [OK] |

**結論**：完全匹配。

### 1.7 worklogs/ 頂層（2026-04-08+）

索引列出 13 個文件。磁盤實際有 16 個文件。

| 條目 | 狀態 |
|------|------|
| 索引已列出的 13 個文件 | [OK] 全部存在 |
| `2026-04-11--daily_summary.md` | [MISSING] 未列入索引 |
| `2026-04-12--earned_trust_ladder_and_audit_trail_fix.md` | [MISSING] 未列入索引 |
| `2026-04-12--gui_metrics_db_fallback_and_display_fixes.md` | [MISSING] 未列入索引 |

**結論**：3 個文件未列入索引（04-11 daily summary + 04-12 兩份 worklog）。

### 1.8 handoffs/

| 條目 | 狀態 |
|------|------|
| `2026-03-25_api_gui_handoff/` | [OK] 目錄存在 |

磁盤還有 `README` 文件，未索引但為自述文件，不計缺失。

### 1.9 decisions/

| 條目 | 狀態 |
|------|------|
| 全部 .md/.txt 文件（4 條） | [OK] |
| 全部 .docx 治理源文件（21 條） | [OK] |

**結論**：完全匹配。

### 1.10 audits/

| 條目 | 狀態 |
|------|------|
| `2026-03-30--bilingual_comment_audit_report.md` | [OK] |
| `2026-04-04--bybit_api_infra_audit.md` | [OK] |
| `2026-04-06_consolidated_remediation_report.md` | [OK] |
| `2026-04-07_e3_r6_directive_applier_security_audit.md` | [OK] |
| `2026-04-07_phase4_final_signoff_audit.md` | [OK] |
| `2026-04-08--e2_review_1c3_bbc.md` | [OK] |
| `2026-04-09--db_rw_ml_pipeline_full_audit.md` | [OK] |
| `2026-04-11--3e_arch_e2_multi_role_review.md` | [MISSING] 未列入索引 |
| `2026-04-11--3e_arch_phase_g_reaudit.md` | [MISSING] 未列入索引 |

**結論**：2 個 04-11 審計報告未列入索引。

### 1.11 audits/2026-04-05_l3_comprehensive/（12 條目）

| 條目 | 狀態 |
|------|------|
| 全部 12 條目 | [OK] |

### 1.12 architecture/

| 條目 | 狀態 |
|------|------|
| `DATA_STORAGE_ARCHITECTURE_V1.md` | [OK] |

### 1.13 references/

索引列出 ~30 個文件。磁盤有 35 個 .md 文件 + 子目錄。

| 未列入索引的文件 | 狀態 |
|------|------|
| `2026-04-06--phase4_execution_plan_v2.md` | [MISSING] 未列入索引 |
| `2026-04-07--arch_rc1_1c3a_gap_analysis.md` | [MISSING] 未列入索引 |
| `2026-04-07--arch_rc1_1c3c_recon.md` | [MISSING] 未列入索引 |
| `2026-04-07--arch_rc1_1c3_scope.md` | [MISSING] 未列入索引 |
| `2026-04-11--3e_arch_session_execution_plan.md` | [MISSING] 未列入索引 |
| `2026-04-11--three_engine_parallel_arch_plan.md` | [MISSING] 未列入索引 |
| `math_implementation_notes.md` | [MISSING] 未列入索引 |

**結論**：7 個文件未列入索引。

### 1.14 CCAgentWorkSpace Agent 表

| 條目 | 狀態 |
|------|------|
| PM / FA / PA / CC / E2 / E3 / E4 / E5 / E1 / E1a / A3 / R4 / TW / AI-E / QA | [OK] 全部目錄存在 |
| `CCAgentWorkSpace/QC/` | [MISSING] 目錄存在但未列入 README Agent 表 |
| `CCAgentWorkSpace/Operator/` | [MISSING] 目錄存在但未列入 README Agent 表 |

**結論**：README 列 15 個 Agent，實際有 17 個目錄（缺 QC、Operator）。CLAUDE_REFERENCE.md 已列出 QC，README 遺漏。

### 1.15 未索引的頂層目錄/文件

| 項目 | 狀態 |
|------|------|
| `docs/archive/` | [MISSING] 7 個歸檔文件，docs/README.md 完全未提及此目錄 |
| `docs/execution_plan/` | [MISSING] 11 個文件（含 README.md），docs/README.md 僅在 references 引用了名字相近的文件但未索引此目錄 |
| `docs/rust_migration/` | [MISSING] 9 個文件（含 README.md），docs/README.md 完全未索引此目錄 |
| `docs/KNOWN_ISSUES.md` | [MISSING] 存在但未列入索引 |
| `docs/CLAUDE_CHANGELOG.md` | [OK] 頂層知名文件，非需索引 |
| `docs/CLAUDE_REFERENCE.md` | [OK] 頂層知名文件，非需索引 |

---

## 二、CLAUDE_REFERENCE.md 驗證

### 2.1 引用的腳本/文件

| 引用 | 狀態 |
|------|------|
| `helper_scripts/maintenance_scripts/bybit_connector/run_i10_canonical_h_chain_recheck.sh` | [OK] |
| `helper_scripts/maintenance_scripts/bybit_connector/run_i10_canonical_decision_lease_recheck.sh` | [OK] |

### 2.2 已知文件名修正表

| 修正項 | 狀態 |
|------|------|
| `bybit_local_risk_envelope_gate.py` | [STALE] .py 源文件不存在（僅殘留 `__pycache__` .pyc），疑似 DEAD-PY-2 已刪除 |
| `bybit_local_trade_eligibility_handoff_builder.py` | [STALE] 同上 |
| `bybit_local_judgment_final_audit_contract_check.py` | [STALE] 同上 |

**結論**：文件名修正表中的 3 個「當前正確名」對應的 .py 源文件均已不存在（僅有 `__pycache__` 殘留）。此表已過時，應標記為歷史記錄或刪除。

### 2.3 CCAgentWorkSpace 審計報告引用

| 引用 | 狀態 |
|------|------|
| 2026-03-31 七份報告 (E3/CC/E4/E5/A3/PM/PA) | [OK] 全部存在 |
| 2026-04-01 十份報告 | [OK] AI-E/CC/E3/E4/E5/FA/TW/R4 存在；Operator/pa_review + pm_execution_plan 存在 |

### 2.4 references/ 引用

| 引用 | 狀態 |
|------|------|
| 所有 2026-03-27 系列 references | [OK] |

### 2.5 角色激活矩陣

| 項目 | 狀態 |
|------|------|
| 16 種任務類型 × 角色映射 | [OK] 完整 |
| QC 角色出現在矩陣中 | [OK] |

### 2.6 Sub-Agent Workspace 路徑對照表

| 項目 | 狀態 |
|------|------|
| 16 個角色路徑 | [OK] 全部路徑正確 |
| 缺少 Operator 和 QC | [OK] 表中有 QC，Operator 非標準 Agent |

### 2.7 最後更新日期

| 項目 | 狀態 |
|------|------|
| 標注 "最後更新：2026-04-06" | [STALE] 實際內容截至 04-06 後未更新，但結構性內容（角色/矩陣/路徑）仍然準確 |

---

## 三、CLAUDE_CHANGELOG.md 驗證

### 3.1 格式一致性

| 項目 | 狀態 |
|------|------|
| 標題格式 `### 標題（YYYY-MM-DD）` | [OK] 一致 |
| 按時間倒序排列 | [OK] |
| 最後更新標注 2026-04-12 | [OK] |

### 3.2 最近 commit 覆蓋度

CHANGELOG 最新條目為 2026-04-12 的 3 個條目（Earned-Trust / Phase 6 PM 驗收 / GUI 指標修復）。

| 未記錄的 commit | 狀態 |
|------|------|
| `1392006` fix(demo-gui): drop localStorage cache | [MISSING] 未記錄 |
| `6ed2299` fix(demo-stop): orphan sweep after close_all | [MISSING] 未記錄 |
| `986d724` feat(session): split paper/demo session controls | [MISSING] 未記錄 |
| `35272d3` fix(ipc): add explicit engine param to all IPC commands | [MISSING] 未記錄 |
| `9853845` fix(paper-metrics): use Rust-authoritative balance/peak | [MISSING] 未記錄 |
| `cbb4e45` fix(pnl): charge close fees + add fast_track observability | [MISSING] 未記錄 |
| `b93b83c` docs(worklog) | [OK] 純文檔 commit，可不記錄 |
| `5d99875` feat(live-trust): Earned-Trust TTL Ladder | [OK] 已記錄 |

**結論**：6 個功能/修復 commit 未記錄在 CHANGELOG 中（均為 04-12 日較晚的 commit）。

---

## 四、SCRIPT_INDEX.md 驗證

### 4.1 helper_scripts/SCRIPT_INDEX.md

索引列出 8 個腳本（含 `db/fresh_start_reset.py`）。磁盤實際有 ~75 個腳本。

| 已列入索引 | 狀態 |
|------|------|
| `restart_all.sh` | [OK] |
| `cron_daily_report.sh` | [OK] |
| `cron_observer_cycle.sh` | [OK] |
| `start_paper_trading.sh` | [OK] |
| `schema_diff.py` | [OK] |
| `golden_dataset_gen.py` | [OK] |
| `db/fresh_start_reset.py` | [OK] |

| 未列入索引的重要腳本 | 狀態 |
|------|------|
| `canary/engine_watchdog.py` | [MISSING] CLAUDE.md 灰度驗證引用的核心腳本 |
| `canary/canary_comparator.py` | [MISSING] |
| `canary/canary_schema.py` | [MISSING] |
| `canary/replay_runner.py` | [MISSING] |
| `canary/rollback_drill.sh` | [MISSING] |
| `canary/test_canary.py` | [MISSING] |
| `phase4/backfill_directive_outcomes.py` | [MISSING] |
| `phase4/dl3_go_no_go.py` | [MISSING] |
| `phase4/weekly_report.py` | [MISSING] |
| `maintenance_scripts/` 整個目錄（~60 腳本）| [MISSING] |

**結論**：索引嚴重過時。僅覆蓋根目錄 7 個腳本 + db/ 1 個。缺失 canary/（6 個）、phase4/（3 個）、maintenance_scripts/（~60 個）。覆蓋率約 8/75 = ~11%。

### 4.2 bybit_connector/docs/SCRIPT_INDEX.md

此為早期歷史索引，存在但未深入驗證（maintenance_scripts 下腳本主要為 legacy H/I/J/K 章節修復腳本）。

---

## 五、Memory 索引（MEMORY.md）驗證

### 5.1 主索引文件引用

| 引用 | 狀態 |
|------|------|
| `project_openclaw_positioning.md` | [OK] |
| `project_arch_rc1_unified_config.md` | [OK] |
| `project_hardware_constraints.md` | [OK] |
| `project_ml_dl_learning_architecture.md` | [OK] |
| `project_agent_p2_dynamic_sl_tp.md` | [OK] |
| `project_agent_workspace.md` | [OK] |
| `project_layer2_agent_design.md` | [OK] |
| `project_engine_consolidation_status.md` | [OK] |
| `project_gui_write_paths_inventory.md` | [OK] |
| `project_phase5_promotion_edge_crisis.md` | [OK] |
| `project_live_stage_status.md` | [OK] |
| `feedback_agent_autonomy.md` | [OK] |
| `feedback_audit_template.md` | [OK] |
| `feedback_cross_platform.md` | [OK] |
| `feedback_minimal_confirmation.md` | [OK] |
| `feedback_new_code_rust_first.md` | [OK] |
| `feedback_no_dead_params.md` | [OK] |
| `feedback_position_sizing.md` | [OK] |
| `feedback_pushback.md` | [OK] |
| `feedback_qa_audit_strategy.md` | [OK] |
| `feedback_risk_changes_scoped.md` | [OK] |
| `feedback_role_definition.md` | [OK] |
| `feedback_rust_authoritative_config.md` | [OK] |
| `feedback_subagent_code_writing_refusal.md` | [OK] |
| `feedback_subagent_first.md` | [OK] |
| `feedback_workflow_e2_e4_mandatory.md` | [OK] |
| `feedback_working_principles.md` | [OK] |
| `reference_remote_access.md` | [OK] |
| `reference_restart_script.md` | [OK] |

### 5.2 歸檔目錄

| 引用 | 狀態 |
|------|------|
| `archive/project_batch9_decisions.md` | [OK] |
| `archive/project_gui_upgrade_plan.md` | [OK] |
| `archive/project_local_strategy_plan.md` | [OK] |
| `archive/project_openclaw_deep_analysis.md` | [OK] |
| `archive/project_rust_cutover_decision.md` | [OK] |
| `archive/project_rust_migration_status.md` | [OK] |

**結論**：全部 29 個活躍記憶文件 + 6 個歸檔文件均存在，無過時條目。

---

## 六、其他索引文件驗證

### 6.1 docs/CCAgentWorkSpace/README.md

| 項目 | 狀態 |
|------|------|
| Agent 目錄索引 | [OK] 列出所有 Agent |
| 使用規範 | [OK] |

### 6.2 docs/execution_plan/README.md

| 項目 | 狀態 |
|------|------|
| 目錄存在，含 11 個文件 | [OK] 但 docs/README.md 未索引此子目錄 |

### 6.3 docs/rust_migration/README.md

| 項目 | 狀態 |
|------|------|
| 目錄存在，含 9 個文件 | [OK] 但 docs/README.md 未索引此子目錄 |

---

## 七、問題總結

### 嚴重度分級

#### P1（索引缺失 — 文件存在但未被任何索引收錄）

1. **docs/README.md 缺失 `docs/archive/` 目錄**（7 個歸檔文件完全無索引）
2. **docs/README.md 缺失 `docs/execution_plan/` 目錄**（11 個文件）
3. **docs/README.md 缺失 `docs/rust_migration/` 目錄**（9 個文件）
4. **docs/README.md 缺失 `docs/KNOWN_ISSUES.md`**
5. **helper_scripts/SCRIPT_INDEX.md 覆蓋率 ~11%**：缺失 canary/（6）、phase4/（3）、maintenance_scripts/（~60）

#### P2（索引落後 — 近期文件未及時更新）

6. **docs/README.md worklogs/ 頂層缺 3 個文件**：04-11 daily_summary + 04-12 兩份 worklog
7. **docs/README.md audits/ 缺 2 個文件**：04-11 兩份 3E-ARCH 審計報告
8. **docs/README.md references/ 缺 7 個文件**：04-06~04-11 期間新增
9. **docs/README.md CCAgentWorkSpace 表缺 QC 和 Operator**
10. **CLAUDE_CHANGELOG.md 缺 6 個功能 commit**（04-12 日較晚的 commit）

#### P3（過時/不準確）

11. **CLAUDE_REFERENCE.md 文件名修正表過時**：3 個「當前正確名」的 .py 文件已被 DEAD-PY-2 刪除
12. **CLAUDE_REFERENCE.md 最後更新日期 04-06**，實際截至今仍未更新

### 數字總結

| 指標 | 數值 |
|------|------|
| 總檢查條目 | ~250+ |
| [OK] | ~225 |
| [MISSING] 未索引 | ~25 |
| [STALE] 過時 | 4 |
| Memory 索引健康度 | 100%（35/35 全部有效） |
| docs/README.md 健康度 | ~90%（主體準確，近期更新落後 + 3 目錄未索引） |
| SCRIPT_INDEX 健康度 | ~11%（嚴重落後） |
| CLAUDE_REFERENCE.md 健康度 | ~95%（僅文件名修正表過時） |
| CLAUDE_CHANGELOG.md 健康度 | ~90%（最新 6 commit 未記錄） |

---

## 八、建議優先修復順序

1. **helper_scripts/SCRIPT_INDEX.md** — 補充 canary/、phase4/、maintenance_scripts/ 子目錄（P1）
2. **docs/README.md** — 新增 archive/、execution_plan/、rust_migration/ 三個子目錄的索引段落（P1）
3. **docs/README.md** — 補充近期（04-11/04-12）的 worklogs、audits、references 條目（P2）
4. **docs/README.md** — CCAgentWorkSpace 表補充 QC 和 Operator（P2）
5. **CLAUDE_REFERENCE.md** — 文件名修正表標記為歷史（DEAD-PY-2 已刪源文件）（P3）
6. **CLAUDE_CHANGELOG.md** — 補充 04-12 日 6 個未記錄 commit（P2）
