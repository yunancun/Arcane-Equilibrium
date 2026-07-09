# TW 文件盤查 — 2026-04-01 ~ 2026-04-24（重複 / 合併 / 死文件）

**角色**：TW（Technical Writer）
**審計日期**：2026-04-24
**窗口**：2026-04-01 ~ 2026-04-24（mtime filter）
**上一次 TW 審計**：`2026-04-12--document_audit_report.md`（12 天前，本次為增量 + 新增窗口）
**基準 commit**：`1a53400`（main HEAD · EDGE-DIAG-1-FUP-IPC）

---

## 0. 執行摘要

| 類別 | 數量 |
|---|---|
| 窗口內 docs/ .md 文件 | 539 |
| 窗口內 Python 文件 | 447 |
| 窗口內 Rust 文件 | 232 |
| 窗口內 SQL migrations | 24（V001-V023 + V999 + rollback + template + test）|
| 窗口內 .claude_reports 本地報告 | 52（gitignored）|
| **本報告發現 P0 矛盾** | 0（無誤導性矛盾）|
| **本報告發現 P1 合併建議** | 7 組 |
| **本報告發現 P2 可歸檔** | 11 組 |
| **本報告發現 P3 死文件候選** | 4 |

**整體健康度**：**中等偏好**。自 04-12 audit 後 P0 項（3 個 DEPRECATED 已移入 archive/ + arch_rc1_1c_history_archive 去重）皆已修復。但：
- §三衛生規則執行不完全（04-22 里程碑仍在 §三 未歸檔為 snapshot 04-22）
- CLAUDE_CHANGELOG.md 1976 行仍超 1200 行硬上限（已部分歸檔但未拆分）
- KNOWN_ISSUES.md / CLAUDE_REFERENCE.md 仍停留在 04-12
- 04-16 / 04-18 ~ 04-22 的 daily_summary 大量缺失，同日碎片未合併

---

## 1. 重複檢測

### 1.1 [DUPLICATE]（確認重複內容）

無新的直接內容重複項。上輪 TW audit（04-12）提出的 3 個 DEPRECATED 檔均已進 archive/（OK）。

### 1.2 [MERGE-CANDIDATE]（高相似度 / 可合併）

| # | 檔案組 | 重疊描述 | 建議 | 優先級 |
|---|---|---|---|---|
| 1 | `docs/references/2026-04-12--g_sr1_signal_tightening_plan_v2.md`（539 行）vs `v2.5.md`（973 行）| v2 是 draft；v2.5 = FINAL（5 輪 review 共 52 findings 全修）。v2 狀態 `Supersedes: Conversation-only v1`，自身已被 v2.5 superseded | v2 加入 `> ⚠️ DEPRECATED — superseded by v2.5.md` header → 歸檔 archive/ | P1 |
| 2 | `docs/references/2026-04-11--3e_arch_session_execution_plan.md`（570 行）vs `three_engine_parallel_arch_plan.md`（1525 行）| 同日兩份 3E-ARCH 文檔，內容互補但 session_execution 是 three_engine 的執行切分。已進 archive 2026-04-11--completed_todo_3e_arch.md 但原始 plan 仍在 references/ | 標註 STATUS 為 已完成實施，兩份合併為 `docs/references/2026-04-11--3e_arch_combined_plan.md` 或同時歸檔 archive/ | P1 |
| 3 | `docs/audits/2026-04-16--g2_funding_arb_clean_edge.md`（59 行，n=10）vs `2026-04-17--g2_funding_arb_clean_edge_v2.md`（82 行，n=13）| 同一監控 daemon 的兩輪快照；v2 已含 v1 數據趨勢。memory `project_g2_funding_arb_monitor.md` 已記載結案 NEGATIVE | v1 + v2 併入單一 `g2_funding_arb_monitor_closeout.md`（補 final 結論）或直接歸檔 archive/ | P1 |
| 4 | `docs/worklogs/2026-04-22--p0_13_atr_scale_qc_research.md`（365 行）+ `p0_14_edge_estimates_miss_rca.md`（456 行）+ `p0_13_14_execution_resume_plan.md`（480 行）+ `passive_wait_silent_fail_audit.md`（265 行）| 4 份同日同議題 4 階段：audit → 2 RCA → 執行計畫 | 合併為 `2026-04-22--p0_13_14_full_spec_and_rca.md`（single source），或至少補 `2026-04-22--daily_summary.md` 做 index | P1 |
| 5 | `docs/worklogs/2026-04-18--dual_track_exit_design.md` + `2026-04-18-1--dual_track_exit_feasibility.md` + `2026-04-18-2--exit_features_table_design.md` | 同日同 TODO（DUAL-TRACK-EXIT-1）3 份階段文檔 | 合併為 `2026-04-18--dual_track_exit_1_full_spec.md` 或補 daily_summary 做 index | P1 |
| 6 | `docs/CCAgentWorkSpace/E5/2026-04-12--e5_optimization_final_report.md` + `2026-04-12--optimization_assessment_report.md` | 同日同 agent 兩份：一份 "final report"（23 項完成後） + 一份 "assessment"（優化前評估）| 併為 `2026-04-12--e5_full_assessment_to_final.md`（pre+post 比對） | P2 |
| 7 | CCAgentWorkSpace 各 agent 2026-03-31/04-01 sprint 報告（15+ 份 E1/E2/E3/E4/PA/CC/FA）vs `docs/audits/2026-04-05--l3_comprehensive/` 12 份 | 同樣在 04-12 TW audit 已列出。04-01 sprint reports 僅被同目錄 agent memory 引用，無外部引用 | 03-31/04-01 sprint reports 加 `superseded by L3 audit 2026-04-05` header → 移入 agent `workspace/archive/` | P2 |

### 1.3 同議題散落多份報告（無合併動作，但建議補 index）

- **FA-PHANTOM 系列**：`2026-04-14--fa_phantom_fup7_margin_threshold_decision.md` / `2026-04-15--fa_phantom_2_fix_spec.md` / `2026-04-16--phantom2_fup_reduce_to_half_cascade_rca.md` / `2026-04-16--reconciler_burst_escalation_rca.md`（4 份，跨 3 天）。建議 memory/`project_fa_phantom_bug.md` 增加一節 "doc index" 列這 4 檔。
- **LIVE-GATE 系列**：`2026-04-18--live_gate_binding_1_implementation.md` + `live_gate_fallback_1_implementation.md`（同日兩檔）已合理（binding + fallback 不同子議題），無須合併。
- **Edge 系列 04-22**：見 1.2 #4。

---

## 2. 合併建議（補 daily_summary）

per CLAUDE.md §七「每日整合」規則，當天 worklog 碎片應合併為 `YYYY-MM-DD--daily_summary.md`。

### 2.1 缺失 daily_summary 列表

| 日期 | 碎片數 | 建議 | 優先級 |
|---|---:|---|---|
| 2026-04-16 | 1（`p0_0_deploy_and_p0_5_discovery.md`，合格工程日誌）| rename 為 `daily_summary.md` 或補 1 份整合 | P2 |
| 2026-04-18 | 4（dual_track_exit_design / session_progress_p06 / live_gate_binding / live_gate_fallback）| 補 `daily_summary.md` | P1 |
| 2026-04-18-1 | 1（dual_track_exit_feasibility）| 合併 04-18 index | P1 |
| 2026-04-18-2 | 1（exit_features_table_design）| 合併 04-18 index | P1 |
| 2026-04-19 | 0（**無當日 top-level worklog，只有 04-19-2**）| 補 `daily_summary.md`（可記 PIPELINE-SLOT-1 / E5-P1 等）| P1 |
| 2026-04-19-2 | 1（track_p_counterfactual_audit）| 合併 04-19 index | P1 |
| 2026-04-20 | 2（p1_5_a2 + pyo3_eliminate_phase2）| 補 `daily_summary.md` | P1 |
| 2026-04-21 | 1（decision_outcomes_rca） | 補 `daily_summary.md`（含 T4 wiring + V2 swap + EDGE-P2-3 PostOnly）| P1 |
| 2026-04-22 | 5（p0_13 audit / p0_13 QC / p0_14 RCA / p0_13_14 exec plan / p1_10 audit / passive_wait_silent_fail / counterfactual_replay_audit_spec / backfill_labels_stalled_rca）= **7 個碎片**| 補 `daily_summary.md` + 實施 1.2 #4 合併 | P0（碎片最多，context 恢復困難）|
| 2026-04-23 | 0 top-level worklog（全走 .claude_reports）| 若 .claude_reports 之外還有後續改動，補 daily_summary | P2 |
| 2026-04-24 | 0 top-level worklog | 今日活躍中，P1-11 audit closeout 尚在 .claude_reports | 今日結束前補 |

### 2.2 §三 snapshot 歸檔缺失

per CLAUDE.md §七 衛生規則「完成 +2 日歸檔」：

| 里程碑日期 | 當前 §三 狀態 | 已歸檔 snapshot | 應做 |
|---|---|---|---|
| 2026-04-22 | 里程碑索引表有一行，但完整敘述在 §三 正文 ~100 行（TICK-PIPELINE-MOD-SPLIT-1 + TRACK-P-V2-SWAP-1）| ❌ 無 `2026-04-22--claude_md_section3_snapshot.md` | 歸檔 04-22 + 04-23 整塊細節 |
| 2026-04-23 | 里程碑索引表有一行 + §三 正文含 DEDUP-PY-RUST / INFRA-PREBUILD-1 A+B / WS-RETIRE-1 ~120 行 | ❌ 無 | 4-25 後可歸檔 |

建議：下次 commit 新增 `docs/archive/2026-04-23--claude_md_section3_snapshot.md`（涵蓋 04-22 + 04-23 明細），§三 正文僅保留里程碑索引行，CLAUDE.md 體量縮減 ~200 行。

### 2.3 Agent reports 批次合併

04-01 日起各 agent 每日（及 sprint）個別報告 ~30+ 份，現在依 agent 歸類，與 04-05 L3 comprehensive audit 重疊。本次不主張合為 batch 報告（各 agent reports 是 dispatch artifact、L3 audit 是橫向 review），但建議 agent `workspace/reports/` 每月壓縮到 `workspace/archive/`。

---

## 3. 死文件候選 [ORPHAN / STALE]

### 3.1 [ORPHAN]（grep 全庫無外部引用）

| # | 文件 | 最後 mtime | 引用點 | 建議 | 優先級 |
|---|---|---|---|---|---|
| 1 | `program_code/exchange_connectors/bybit_connector/control_api_v1/WIRING_INTEGRITY_AUDIT.md`（631 行）| 窗口內 | 0 外部 .md 引用 | 加 date prefix `2026-MM-DD--` + 移 `docs/audits/` 或標 historic | P2 |
| 2 | `program_code/exchange_connectors/bybit_connector/control_api_v1/L1_01_TRADE_ATTRIBUTION_FIX_SUMMARY.md`（236 行）| 窗口內 | 0 外部 .md 引用 | 同上 → `docs/archive/` 或刪 | P2 |
| 3 | `docs/references/2026-04-04--comprehensive_audit_template_v1.md` | 舊 | 04-12 TW audit 列為 ORPHAN，12 天後仍無人引用 | 遷移 `docs/references/templates/` + 更新 CLAUDE.md §八 audit 模板段落引用 | P3 |

`API_TOKEN_RESET_GUIDE.md` **被 auth.py 引用**（活文件）不歸此列。

### 3.2 [STALE]（活檔但 >1 週未更新 + 無 TODO 指針）

| # | 文件 | 問題 | 優先級 |
|---|---|---|---|
| 1 | `docs/KNOWN_ISSUES.md` | mtime 04-20（顯示最後更新日期 04-12），10 OPEN 項未 review。04-16 起 P0-0 / P0-4 / P0-9 / LIVE-GUARD-1 / LIVE-GATE-BINDING-1 均完成但 KNOWN_ISSUES 未同步 | P1（誤導性陳舊）|
| 2 | `docs/CLAUDE_REFERENCE.md` | mtime 04-20（顯示最後更新 04-12），缺 04-13 後的 H1-H5 正名（非 stub）/ 5-Agent runtime state / 3E-ARCH 修正 / Layer 2 Mac dev | P1 |
| 3 | `docs/CLAUDE_CHANGELOG.md` | 1976 行，超 1200 行硬上限。已有 `2026-04-12--changelog_archive_pre_0408.md` + `2026-04-13--changelog_archive_0408_0409.md` 歸檔頭尾，但 04-10 ~ 現在的中段未拆 | P1 |
| 4 | `docs/execution_plan/phase_0a.md ~ phase_6.md` 9 份 | 時間窗口 `4/11-4/17` ~ `8/14-8/27`，與實際進度脫節（Phase 0-5 早完成，Phase 6 名稱複用但內容不對）。04-20 mtime 可能是 git pull 觸發 | 加 `> ✅ HISTORICAL — this plan has been executed; see archive completed_todo_*` header 或整夾移 `docs/archive/execution_plan_original/` | P2 |
| 5 | `docs/rust_migration/00-07.md` 8 份 | 同上，Rust 遷移已完成（R-07 Go/No-Go 2026-04-10 過），但檔仍在 references/rust_migration | 加 HISTORICAL header 或移 archive/ | P2 |

### 3.3 [GOVERNANCE_DEV]（歷史保留，無需行動）

`docs/governance_dev/`（127 份 .md，窗口內 mtime 命中）已有 `DEPRECATED.md` 指向 Rust 實現。與 04-12 audit 結論一致：無需額外行動。

### 3.4 DEDUP 殘留（非死文件，但值得 note）

- `helper_scripts/maintenance_scripts/bybit_connector/`（6 檔 / 532 行）vs `program_code/exchange_connectors/bybit_connector/scripts/`（5 檔 / 89 行 shim wrappers）仍共存。2026-04-23 DEDUP-PY-RUST Part D 已刪 98 個 shell（maintenance + scripts）；剩 11 檔為 I10 canonical + 仍在用的 wrappers，屬正常保留，**非本次審計刪除對象**。

---

## 4. §三 衛生規則遵守度（CLAUDE.md §七）

| 規則 | 狀態 |
|---|---|
| 完成里程碑當天 +2 日歸檔到 snapshot | 🟡 部分：04-22 / 04-23 未歸檔（應在今日或明日執行）|
| §三 只記載「現況 + ≤2 天完成」 | 🟡 §三 正文約 25 行 04-22 + 04-23 明細，符合 ±2 日窗口但快過期 |
| 里程碑索引表保留 1 行條目 | ✅ OK |
| 完整敘述 + commit + 測試數進 archive | ✅ OK 已歸檔 04-15 / 04-20 / 04-21 三份 snapshot |

**動作建議**：2026-04-25 晨間 commit 同次：
1. 新建 `docs/archive/2026-04-23--claude_md_section3_snapshot.md`（含 04-22 + 04-23 明細）
2. §三 正文刪對應段落，保留索引表行（2026-04-22 / 2026-04-23 已有索引行）
3. 指針表增一行 `- §三 2026-04-22/23 完整敘述 → docs/archive/2026-04-23--claude_md_section3_snapshot.md`

---

## 5. 其他觀察

### 5.1 .claude_reports（本地 gitignored）

04-01 ~ 04-24 合計 52 份；04-23 單日 31 份碎片（DEDUP-PY-RUST Tier A/B + 多 sub-agent）；04-24 至目前 6 份。per CLAUDE.md §七「與 worklogs 職能互補」，**不合併 daily_summary**，但若單日超過 20 份，建議本機端備份時分 per-day 子目錄（operator 視需要）。

### 5.2 04-24 P1-11 系列（本次審計中）

`.claude_reports/20260424_{015831,022414,024807}_p1_11_*.md` 3 份 + CLAUDE.md §三 已記入，P1-11 全工明日（+2 日）可歸檔 snapshot 時一併整合。

### 5.3 CCAgentWorkSpace 空目錄殘留

`E1a/workspace/`、`QA/workspace/`：仍空（04-12 audit 已註）。保留無害。

---

## 6. 優先修復建議

### P0（誤導性矛盾）
**無**。所有已識別的過期項都有自標或指向正確版本。

### P1（本週處理）
1. 補缺失 daily_summary：04-18 / 04-19 / 04-20 / 04-21 / **04-22（最緊）** / 04-24
2. 合併 1.2 #1 / #2 / #3 / #4 / #5 共 5 組碎片
3. 更新 KNOWN_ISSUES.md（10 OPEN 項 review）
4. 更新 CLAUDE_REFERENCE.md 同步到 04-23 狀態
5. 拆分 CLAUDE_CHANGELOG.md 中段（04-10 ~ 04-20）到 archive/
6. 新建 `2026-04-23--claude_md_section3_snapshot.md` 歸檔 04-22 + 04-23 明細

### P2（下週處理）
7. execution_plan/phase_*.md 與 rust_migration/*.md 加 HISTORICAL header 或整夾移 archive/
8. 合併 1.2 #6 / #7 兩組
9. WIRING_INTEGRITY_AUDIT / L1_01_TRADE_ATTRIBUTION 加 date prefix 或歸檔
10. CCAgentWorkSpace 各 agent 03-31/04-01 sprint reports 加 `superseded by L3` header + 移 `workspace/archive/`
11. 04-16 p0_0_deploy_and_p0_5_discovery.md rename 為 daily_summary 或保留（看 operator）

### P3（長期）
12. `references/2026-04-04--comprehensive_audit_template_v1.md` 搬到 templates/ 子目錄 + 更新 CLAUDE.md §八 引用
13. governance_dev/ 壓縮成 tarball（127 份，5 MB+ 樹噪音）

---

## 7. 關鍵數字

| 指標 | 值 |
|---|---|
| 窗口內 docs/ .md 文件 | 539 |
| .claude_reports 本地碎片 | 52（04-01 ~ 04-24）|
| daily_summary 存在天數 | 9 天（04-08~17 中 04-16 缺）|
| daily_summary **缺失**天數 | 7 天（04-16/18/19/20/21/22/24，不算 04-23 本身只走 .claude_reports）|
| snapshot 歸檔成功 | 3 份（04-15 / 04-20 / 04-21）|
| snapshot **缺失**歸檔 | 1 份（04-22 + 04-23 合併）|
| 窗口內 Rust 文件改動 | 232 |
| 窗口內 Python 文件改動 | 447 |
| CLAUDE_CHANGELOG.md 當前行數 | 1976（超 1200 硬上限 **+776 行**）|
| SQL migrations 新增在窗口 | V019 / V020 / V021 / V023（4 檔，+ template + test + rollback）|

---

## 8. 對比上輪 TW audit（2026-04-12）

| 項目 | 04-12 audit 狀態 | 04-24 狀態 |
|---|---|---|
| 3 個 DEPRECATED 未進 archive/ | 待處理 | ✅ 已處理（全在 archive/）|
| arch_rc1_1c_history_archive 雙副本 | worklogs + archive 雙份 | ✅ 只剩 archive/ |
| 5 個缺失 daily_summary（04-06/07/09/10/12） | 待處理 | ✅ 全補（04-09 ~ 04-15 連續 OK）|
| CLAUDE_REFERENCE.md 過時 | 04-06 stale | ❌ 仍 04-12 stale（倒退）|
| KNOWN_ISSUES.md 過時 | 04-05 stale | ❌ 仍 04-12 stale（倒退）|
| CLAUDE_CHANGELOG.md 超長 | 2135 行 | 🟡 1976 行（-159，但仍超限）|
| references/ 孤兒 7 個 | 待處理 | 🟡 部分處理（多數 03-27/03-30 時期仍在）|
| CCAgentWorkSpace 04-01 報告 supersede 標註 | 待處理 | ❌ 未處理 |

**結論**：P0 實際問題都已閉合；P1/P2 doc hygiene 積欠增加（主因 04-16 ~ 04-22 交易緊急工作占用時間，daily_summary 斷開）。本次建議優先補 P1 合併 + snapshot，下週處理 P2。

---

TW AUDIT DONE: docs/CCAgentWorkSpace/TW/workspace/reports/2026-04-24--file_dedup_merge_audit_apr01_apr24.md
