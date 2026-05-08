# TW 文件盤查 — 2026-04-01 ~ 2026-05-08（重複 / 合併 / 應歸檔）

**角色**：TW（Technical Writer）
**審計日期**：2026-05-08
**窗口**：2026-04-01 ~ 2026-05-08（38 天，非操作員寫的「4 月初~5 月初」筆誤更正）
**上一次 TW 審計**：`2026-04-24--file_dedup_merge_audit_apr01_apr24.md`（14 天前，本次為增量 + 新範圍）
**基準 commit**：`4e2d2883`（main HEAD · 5/8 mattpocock skills setup）
**今日範疇邊界**：盤查不合併不刪不改，只產出修復方案候選由後續 PA fix plan 派工

---

## §1 Executive Summary

| 類別 | 數量 |
|---|---:|
| 窗口內 docs/ .md 文件總數（含 CCAgentWorkSpace） | ~1850 |
| 窗口內 .claude_reports（gitignored 本地） | ~430 |
| 4/25-5/8 新增 active 文件（粗估） | ~720 |
| **本報告 P0 重大誤導/雙倍源** | 0 |
| **本報告 P1 應合併 / 標 superseded** | 9 組 |
| **本報告 P2 應歸檔 active** | 11 個 |
| **本報告 P3 索引漂移** | 5 組（README + SCRIPT_INDEX） |
| **本報告 P4 注釋規範違反** | 2 個新檔（中文缺）|
| 過去 4/27 後 worklogs/ daily_summary 缺失 | **12 天**（嚴重 §三 sync 違反）|
| Operator/ 鏡像 PM/workspace/reports 同名 5/7 | 38 對（屬設計鏡像，**非** 嚴格重複）|

**整體健康度**：**中等偏弱**。自 04-24 audit 以來 P0 0 持續維持（大改檔治理穩）。但：

- **worklogs/ 4/28 起 12 天空檔**：5/1-5/8 0 份 daily_summary，所有日常工作記錄全在 `.claude_reports`（本機 gitignored）/ `CCAgentWorkSpace/<role>/workspace/reports/`（agent 級別），跨日聚合視角缺失
- **REF-20 v0.1→v3 + REF-21 v1→v1.3 多版本疊加**：execution_plan/ 內 REF-20 共 7 份（v0.1/v1/v1_round2_audit/v2/v2_round3_audit/v2.1/v3）+ REF-21 共 4 份 plan + 2 份 GUI spec，未統一掛 `> ⚠️ SUPERSEDED by VX` header
- **multi_agent_rework 14 份新增 + ENGINEERING_PLAN + AgentTodo 完全未在 docs/README.md 索引**（5/5 onwards 大塊新內容沒進索引）
- **SCRIPT_INDEX.md 最後更新 5/3**：5/4-5/8 新增 ~10 個 cron + healthcheck script 全 missing
- **2 個新 cron script 違反 5/5 後 governance 中文注釋默認規則**：`ref21_market_microstructure_recorder.py` / `ref21_market_recorder_retention.py` 純英文 docstring

---

## §2 時間範圍文件清單（按目錄樹組織）

### 2.1 `docs/worklogs/` 頂層（2026-04-08 後 active）

**4 月**（已合理）：
- `2026-04-08~17--daily_summary.md`（10 份，含部分非 daily-summary 命名）
- `2026-04-18` 有 4 份碎片（dual_track_exit_design / live_gate_binding/fallback / session_progress_p06）+ `2026-04-18-1` + `2026-04-18-2`
- `2026-04-19-2--track_p_counterfactual_audit.md`（無 04-19 daily_summary）
- `2026-04-20--p1_5_a2_drawdown_continuity_implementation.md` + `pyo3_eliminate_phase2_migration_spec.md`
- `2026-04-21--decision_outcomes_rca.md`
- `2026-04-22--*.md` × 7（p0_13_atr / p0_14_edge / passive_wait / p1_10_ma / p0_13_14_execution / counterfactual_replay / backfill_labels）
- `2026-04-27--live_auth_watcher_event_consumer_spawn_fix.md`

**5 月（嚴重缺失）**：
- 5/1-5/8 共 8 天 0 份 worklog top-level
- 4/27 ~ 5/8 共 12 天無 daily_summary
- 所有 5 月 active 工作分散於：
  - `CCAgentWorkSpace/PM/workspace/reports/` 5/1-5/8 共 ~80 份
  - `CCAgentWorkSpace/E1/workspace/reports/` 5/2-5/5 共 ~70 份
  - `CCAgentWorkSpace/PA/workspace/reports/` 5/1-5/3 RFC 8 份 + REF-20 sprint 多份
  - `.claude_reports/` 5/2-5/8 共 ~57 份（gitignored 本地）
  - `docs/architecture/multi_agent_rework_2026-05-05/` 14 份 mag020-mag084 + 2 份 plan
  - `docs/execution_plan/` 5/2-5/7 共 27 份 ref20/ref21
  - `docs/governance_dev/amendments/` 5/2 + 5/3 共 2 份 AMD
  - `docs/architecture/2026-05-06--openclaw_control_plane_repositioning.md`

### 2.2 `docs/audits/`

- 4 月：18 份；5 月新增 1 份（`2026-05-03--P0-DATA-INDICATOR-SWEEP_verdict.md`）
- 結構未變

### 2.3 `docs/archive/`

- 4 月歸檔 27 份（含 04-29~30 active_docs cleanup 5 份 / pre-cleanup snapshot 3 份）
- 5 月歸檔 5 份（5/1 wave 1+2+3 closure / 5/2 CLAUDE+TODO pre-trim snapshot 2 份 / 5/6 stale_extract 2 份 / 5/7 todo_v12_replan）
- ✅ §三 衛生規則執行良好，pre-trim snapshot 機制完整

### 2.4 `docs/execution_plan/`

5/2-5/7 新增 27 份（**最多碎片**），重點：

| 主題 | 版本數 | 狀態 |
|---|---:|---|
| REF-20 paper replay lab dev plan | v0.1 / v1 / v1_round2_audit / v2 / v2_round3_audit / v2.1 / v3 = **7 份** | v3 SoT，但 v0.1-v2.1 多份未統一加 superseded header |
| REF-20 supplementary | ux_subdoc_v1 / wave2_dispatch / wave1-6_master_closure / wave7_defer_note / wave9_pm_signoff_template / final_closure / sprint3 deploy / sprint4 final = **8 份** | active |
| REF-20 gap closure | reality_backtest_plan_v1 = **1 份** | 5/4 active |
| REF-21 full chain replay | v1 / v1.1 / v1.2 / v1.3 = **4 份** | v1.3 active；v1/v1.1/v1.2 已標 superseded |
| REF-21 GUI UX spec | v1 / v1.1 = **2 份** | v1.1 active |
| REF-21 supplementary | s1_recorder_spec_placeholder / replay_remaining_wave_reset = **2 份** | active |
| OpenClaw（5/6 開始） | gateway_dev_plan / gui_control_console_plan = **2 份** | active |

### 2.5 `docs/references/`

5/2-5/3 新增 8 份（同議題雙語版）：

| 議題 | 中英版本 |
|---|---|
| REF-19 Reality Calibrated Replay Governance | `reality_calibrated_fast_replay_governance.md` + `_zh.md` (5/2) |
| REF-20 Paper Replay Learning Surface Design | `paper_replay_learning_surface_design.md` + `_zh.md` (5/2) |
| REF-20 Paper Replay Lab Governance v2 | `ref20_paper_replay_lab_governance_v2.md` + `_zh.md` (5/3) |
| REF-19 v2 | `reality_calibrated_fast_replay_governance_v2.md` + `_zh.md` (5/3) |

### 2.6 `docs/architecture/`

- `multi_agent_rework_2026-05-05/`（5/5-5/7 新建子目錄）：
  - `ENGINEERING_PLAN.md` (5/5)
  - `AgentTodo.md` (5/5)
  - `2026-05-06--mag015_sprint_a_contract_addendum.md`
  - `2026-05-06--mag020_scanner_authority_modes.md`
  - `2026-05-07--mag030_agent_spine_rust_module_design.md`
  - `2026-05-07--mag034_idempotency_double_execution_audit.md`
  - `2026-05-07--mag040_strategist_v2_matching_model.md`
  - `2026-05-07--mag050_guardian_v2_risk_metrics_model.md`
  - `2026-05-07--mag060_execution_plan_interface.md`
  - `2026-05-07--mag070_analyst_insight_l1_l2_l3_schema.md`
  - `2026-05-07--mag080_cutover_policy.md`
  - `2026-05-07--mag081_canary_flag_runtime_risk_review.md`
  - `2026-05-07--mag082_24h_canary_validation_checklist.md`
  - `2026-05-07--mag083_final_release_audit_blocked.md`
  - `2026-05-07--mag084_operator_signoff_blocked.md`
- `2026-05-06--openclaw_control_plane_repositioning.md`

### 2.7 `docs/adr/`

5/6 同 commit 一次性新增 14 份 ADR 0001-0014：✅ 結構良好。是 5/6 唯一新增類型，與 multi_agent_rework + OpenClaw repositioning 同期決策落地。

### 2.8 `docs/governance_dev/amendments/`

5/2 + 5/3 共 2 份 AMD（SM-02 路徑 A retrofit + REF-20 Wave 7 amendment）。✅ 命名規範。

### 2.9 `docs/CCAgentWorkSpace/<agent>/workspace/reports/`

5/1-5/8 各 agent 數量：

| Agent | 5月數量 | 性質 |
|---|---:|---|
| PM | ~80 份 | dispatch + signoff + scanner + ref20/ref21 + agenttodo m0/sprint_a/m8 + 4/30 trio |
| E1 | ~70 份 | impl 報告（5/2 LG-5 多 round / 5/3 ref20 wave 系列 / 5/4-5/5 sprint a/b/c/d）|
| E2 | ~25 份 | review |
| E4 | ~19 份 | regression |
| PA | ~30 份 | RFC + sprint design |
| Operator | ~50 份 | 對 PM workspace 鏡像（給 operator 看）|
| QA | 1 份（5/4 ref20_sprint_a_r3_smoke_e2e） | 嚴重冷清 |
| E1a | 1 份（5/5 ref20_sprint_b1_r4_impl）| 冷清 |
| QC / FA / MIT / CC / E3 / E5 / R4 / TW / A3 / AI-E / BB | 大多 0-3 份 5月 | 冷清 |
| TW | 0 份（本報告為首份 5月）| 工作未進入 5 月 doc cleanup wave |

### 2.10 `.claude_reports/` (gitignored 本地審核報告)

- 4/21~5/8 範圍共 ~430 份
- 5/2 LG-5 W3 系列 ~30 份
- 5/3 ref20 wave3-6 + sprint1+3 共 ~15 份
- 5/4-5/5 sprint a/b/c 共 ~10 份
- 5/6 arcane rename + scanner opp + mag015 共 6 份
- 5/7 P1 healthcheck fix 1 份
- 5/8 ai_provider_management_full_wiring 1 份

✅ 規範遵守（gitignore 隔絕 + 命名規範）。

---

## §3 重複文件偵測

### 3.1 [DUPLICATE]（直接內容雙倍）

無。本次盤查未發現完全內容雙倍源。

### 3.2 [MERGE-CANDIDATE]（高相似度 / 同議題多版本未合併）

| # | 檔案組 | 重疊描述 | 建議 | 優先級 |
|---|---|---|---|---|
| 1 | `docs/execution_plan/2026-05-02--ref20_paper_replay_lab_dev_plan_draft_v0.1.md` (DRAFT v0.1) + `_v1.md` + `_v1_round2_audit.md` + `_v2.md` + `_v2_round3_audit.md` + `_v2_1_round3.md` | REF-20 v3 是 SoT（README L502 標 ★ SoT）；前 7 份未統一加 `> ⚠️ SUPERSEDED by V3` blockquote header；CLAUDE.md §三 沒指引閱讀順序 | 7 份頭部加標準 superseded blockquote；或整批移 `docs/archive/` 並在 `docs/references/` 留 1 個 V3 active；或建 `docs/execution_plan/_history/` 子目錄 | P1 |
| 2 | `docs/execution_plan/2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1{,_1,_2,_3}.md` (4 份) + `2026-05-06--ref21_gui_ux_spec_v1{,_1}.md` (2 份) | v1/v1.1/v1.2 已 README 標 superseded（OK）；但 4 份本檔頭部 0 superseded blockquote header；GUI spec v1 標 superseded（OK）但 v1.1 頭未標 active marker | 4 份 v1/v1.1/v1.2 頭部加 `> ⚠️ SUPERSEDED by V1.3` blockquote；v1.3 / GUI v1.1 加 `> ✅ ACTIVE` marker；同步 README L509-L514 已有歸類 | P1 |
| 3 | `docs/references/2026-05-02--reality_calibrated_fast_replay_governance.md` + `_zh.md` + `2026-05-03--*_v2.md` + `_v2_zh.md` (4 份) | REF-19 governance 雙語版 + v2 雙語版共 4 份；無 ”v1 superseded by v2” 標記；README L486-L487 沒標 v1 過期 | v1 雙語兩份頭部加 `> ⚠️ SUPERSEDED by 2026-05-03 v2` blockquote；README 歸類 superseded；或合併為 v1+v2 對比版 | P1 |
| 4 | `docs/references/2026-05-02--paper_replay_learning_surface_design{,_zh}.md` + `2026-05-03--ref20_paper_replay_lab_governance_v2{,_zh}.md` | 同議題 design 文 → governance 文，雙中英版本 4 份；可能 design v1 已被 governance v2 implicitly 替代 | 確認 v2 是否替代 v1，若是補 superseded header；若是漸進補充則加 `> 🟡 USE TOGETHER WITH v2` cross-link | P2 |
| 5 | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-02--lg5_impl_{1_producer,1_producer_round2,2_consumer,2_consumer_round2,3_healthcheck}.md` + `lg5_w3_fup_{1,1_round2,2_fix_1,2_fix_1_round2,2_fix2_impl_1_2,2_fix2_impl_2_consumer,3}.md` (12 份) | LG-5 W3 5/2 單日 12 份 round + fup_1/2/3 系列；屬同 wave 連續修補；無單一 closeout 摘要 | E1 wave closeout 報告（總結 12 round → 1 final）；現 12 份保留作 audit trail | P2 |
| 6 | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-04~05--ref20_sprint_a_r1_impl.md` + `r2_impl.md` + `r3_impl.md` + `r3_round6_impl.md`（連同 5/5 sprint_b r0t0/r5t1t2/r5t3/r5t456 + sprint_c r6t0prime/r6t1t2/r6t7/w2/w3/w5/w6 + sprint_c2 w1/w2/w3 + sprint_d r8 共 18 份）| Sprint A/B/C/D round/wave 報告 18 份；最終總 closure 已在 `docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md` + memory；缺 closure 摘要 link | E1 加 1 份 `2026-05-05--ref20_sprint_a_b_c_d_closure_summary.md` 引用 18 round; 或維持現狀（LG-5 慣例）| P3 |
| 7 | `docs/CCAgentWorkSpace/Operator/2026-05-07--agenttodo_mag03[0-5]_*.md` × 6 + `mag04[0-5]_*.md` × 6 + `mag05[0-4]_*.md` × 5 + `mag06[0-4]_*.md` × 5 + `mag07[0-4]_*.md` × 5 + `mag08[0-4]_*.md` × 5 = **32 份 mag 報告**（5/7 同日）+ 對應 PM/workspace/reports/ 32 份同名 mirror | Operator 是 PM 給 operator 看的 brief；PM 為內部報告。設計鏡像，**內容不同視角**（但結構性 duplicate） | 不合併（因兩用途不同）；補 README 索引引用 single canonical（PM 為內部，Operator 為 brief） | P3 |
| 8 | `docs/audits/2026-04-16--g2_funding_arb_clean_edge.md` (59 行 n=10) vs `2026-04-17--g2_funding_arb_clean_edge_v2.md` (82 行 n=13) | 4/24 audit 已點名待合併，14 天後仍未處理；funding_arb 已 V2 棄策略路徑 | 合併為 `g2_funding_arb_monitor_closeout.md` + 補 final 結論；或整夾移 archive/ | P1（carry-over from 4/24 audit）|
| 9 | `docs/CCAgentWorkSpace/E5/2026-04-12--e5_optimization_final_report.md` + `2026-04-12--optimization_assessment_report.md` | 04-24 audit P2 點名待合併，14 天後仍未處理 | E5 owner 自行併或維持兩份 | P2（carry-over）|

### 3.3 同議題散落多份（建議補 index，不合併）

- **REF-20 Sprint 1+2+3 4 Track**：分散在 PA/E1/E2/E4 共 ~25 份；memory `project_2026_05_03_ref20_sprint1_2_closure.md` 已聚合，建議 PM 在 5/3 sign-off report 補 doc index pointer 鏈
- **MAG-010..MAG-084 系列**：14 份 architecture mag 文 + 32 份 5/7 PM/Operator 鏡像，整體 m0/sprint_a/m8 closure 在 PM 多份分批 signoff，建議補 `agenttodo_master_index.md` 1 份指向 14 mag + 32 鏡像

---

## §4 應合併清單（source → target + 理由）

| # | source | target | 合併理由 |
|---|---|---|---|
| M1 | `docs/execution_plan/2026-05-02--ref20_*v0.1/v1/v2/v2.1/round2_audit/round3_audit.md`（6 份）| 整批 → `docs/archive/2026-05-08--ref20_v0_v2_1_history.md`（壓縮歸檔）+ V3 active 留 execution_plan/ | V3 是 SoT（README L502 標）；6 份 history 留執行計畫目錄是 noise；archive 壓縮為單一歷史檔可保留 audit trail |
| M2 | `docs/execution_plan/2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1.md` + `_v1_1.md` + `_v1_2.md`（3 份）| 整批 → `docs/archive/2026-05-08--ref21_v1_v1_2_history.md`（壓縮歸檔）+ v1.3 active 留 execution_plan/ | 同上理由，v1.3 active；v1/v1.1/v1.2 已 superseded（README 標）|
| M3 | `docs/execution_plan/2026-05-06--ref21_gui_ux_spec_v1.md` | → archive/ 同 M2 history 檔內 | v1.1 superseded v1（README L512 標）|
| M4 | `docs/audits/2026-04-16--g2_funding_arb_clean_edge.md`（n=10）| → `docs/archive/2026-05-08--g2_funding_arb_monitor_closeout.md`（含 v2 的 n=13）| funding_arb 已 V2 棄策略路徑 commit `a19797d`，v1+v2 兩份 audit closeout 應合併 |
| M5 | `docs/audits/2026-04-17--g2_funding_arb_clean_edge_v2.md`（n=13）| → 同 M4 | 同上 |
| M6 | `docs/references/2026-05-02--reality_calibrated_fast_replay_governance.md` + `_zh.md`（v1 雙語）| → archive/`2026-05-08--ref19_v1_history.md` 壓縮；保留 v2 雙語 active | 5/3 v2 替代 v1（推測，需確認）|
| M7 | `docs/references/2026-05-02--paper_replay_learning_surface_design.md` + `_zh.md`（v1 雙語）| 確認 governance v2 是否完全替代 design v1，若是 → archive | 不確定，需 PM 釐清 |
| M8 | `docs/CCAgentWorkSpace/E5/2026-04-12--{e5_optimization_final_report,optimization_assessment_report}.md`（carry-over from 4/24）| 合併為 `2026-04-12--e5_full_assessment_to_final.md` 或 archive | 14 天前已點名 |
| M9 | `docs/worklogs/2026-04-18--*.md`（4 份碎片）+ `2026-04-18-1.md` + `2026-04-18-2.md`（共 6 份）| 補 `2026-04-18--daily_summary.md` 作 index | 4/24 audit 點名 P1，14 天未處理；本應合併或補 daily |

---

## §5 應歸檔清單（active 文件已 stale）

| # | 文件 | 最後 mtime | 應歸檔理由 | 優先級 |
|---|---|---|---|---|
| A1 | `docs/KNOWN_ISSUES.md`（如存在） | 4/12 stale 14+天 | 04-24 audit P1，14 天後仍倒退 | P1 |
| A2 | `docs/CLAUDE_REFERENCE.md` | 4/12 stale 26 天 | 04-24 audit P1，未同步 5 月 6 重大更新（multi_agent / openclaw repositioning / scanner opportunity / arcane rename / mag015~084 / decision lease retrofit）| P1 |
| A3 | `docs/CLAUDE_CHANGELOG.md`（1976+ 行） | 4/24 audit 1976 行；現可能更高 | 超過 1200 行硬上限 700+ 行 | P1 |
| A4 | `docs/execution_plan/phase_0a~6.md`（9 份） | 4/20 mtime | 4/24 audit 點名加 HISTORICAL header；14 天後仍未處理 | P2 |
| A5 | `docs/rust_migration/00-07.md`（8 份）| 4/20 mtime | 4/24 audit 點名加 HISTORICAL header；R-07 Go/No-Go 4/10 過 | P2 |
| A6 | `docs/references/2026-04-04--comprehensive_audit_template_v1.md` | stale | 4/24 audit P3，仍 ORPHAN 14 天 | P2 |
| A7 | `docs/references/2026-04-12--g_sr1_signal_tightening_plan_v2.md` | 4/12 | v2.5 已 FINAL；4/24 audit 點名 14 天 | P2 |
| A8 | `docs/references/2026-04-11--3e_arch_session_execution_plan.md` + `three_engine_parallel_arch_plan.md` | 4/11 | 4/24 audit P1，14 天後仍未加 status header；3E-ARCH 已完成 | P2 |
| A9 | `docs/CCAgentWorkSpace/<agent>/2026-04-12--*.md`（10+ 份各 agent L3 audit）| 4/12 | 屬 4/12 全程序鏈 audit 系列（snapshot），現實已大量 superseded（多波 wave 後）| P3 |
| A10 | `program_code/exchange_connectors/bybit_connector/control_api_v1/WIRING_INTEGRITY_AUDIT.md`（631 行）| 窗口內 | 4/24 audit P2，0 外部引用 14 天後仍存 | P2 |
| A11 | `program_code/exchange_connectors/bybit_connector/control_api_v1/L1_01_TRADE_ATTRIBUTION_FIX_SUMMARY.md`（236 行）| 窗口內 | 同 A10 | P2 |

---

## §6 MODULE_NOTE / 雙語注釋規範違反

### 6.1 5/2-5/8 新增/重大改檔抽樣

✅ 中英雙語 / 中文齊備：
- `helper_scripts/db/passive_wait_healthcheck/checks_scanner_market.py`（雙語 OK，中英 docstring + MODULE_NOTE）
- `helper_scripts/db/passive_wait_healthcheck/checks_agent_spine.py`（中文為主 + 英文 module purpose）
- `helper_scripts/db/passive_wait_healthcheck/checks_openclaw_gateway.py`（中文 MODULE_NOTE 主）
- `helper_scripts/db/passive_wait_healthcheck/checks_pricing_binding.py`（中英雙語 MODULE_NOTE EN）
- `helper_scripts/learning/lg5_re_evaluate_pending.py`（中英雙語 MODULE_NOTE）

❌ **違反 2026-05-05 governance change（默認中文，不准只英文）**：

| 檔 | 行 | 違反 | 補修建議 |
|---|---|---|---|
| `helper_scripts/cron/ref21_market_microstructure_recorder.py` | 1-9 | docstring 純英文：`"""REF-21 local ticker/orderbook recorder for future replay fidelity..."""` 無中文 | 加中文 MODULE_NOTE：「REF-21 本地 ticker/orderbook 錄製器，提供未來 replay 真實微觀結構數據源」 |
| `helper_scripts/cron/ref21_market_recorder_retention.py` | 1-7 | docstring 純英文：`"""REF-21 market recorder retention for replay microstructure tables..."""` | 加中文 MODULE_NOTE：「REF-21 market recorder 數據保留期清理 cron」 |

CLAUDE.md §七（2026-05-05 governance）：「新建/修改的注釋默認只寫中文（不再強制中英對照）；發現注釋僅英文 → 仍 push back（中文是必要層）」。

### 6.2 大致統計

抽樣 6 個 5/2-5/8 新檔 → 4/6 中文齊全（67%）+ 2/6 純英文（33%）。違反率不嚴重但需提醒 sibling CC 注意。

---

## §7 SCRIPT_INDEX.md / docs/README.md 索引漂移

### 7.1 `helper_scripts/SCRIPT_INDEX.md` 漂移（最後 5/3）

5/4-5/8 新增腳本但 SCRIPT_INDEX 未登記：

| 腳本 | mtime 估 | 狀態 |
|---|---|---|
| `helper_scripts/cron/ref21_market_microstructure_recorder.py` | 5/6+ | 0 登記 |
| `helper_scripts/cron/ref21_market_recorder_retention.py` | 5/6+ | 0 登記 |
| `helper_scripts/cron/test_ref21_market_microstructure_recorder.py` | 5/6+ | 0 登記 |
| `helper_scripts/cron/test_ref21_market_recorder_retention.py` | 5/6+ | 0 登記 |
| `helper_scripts/cron/mlde_shadow_recommendations_retention_cron.sh` | 5月 | 0 登記 |
| `helper_scripts/cron/ref21_symbol_universe_snapshot_cron.sh` | 5月 | 0 登記 |
| `helper_scripts/db/passive_wait_healthcheck/checks_agent_spine.py` | 5月 | 0 登記 |
| `helper_scripts/db/passive_wait_healthcheck/checks_openclaw_gateway.py` | 5月 | 0 登記 |
| `helper_scripts/db/passive_wait_healthcheck/checks_pricing_binding.py` | 5月 | 0 登記 |
| `helper_scripts/db/passive_wait_healthcheck/checks_replay_maintenance.py` | 5月 | 0 登記 |
| `helper_scripts/db/passive_wait_healthcheck/checks_scanner_market.py` | 5月 | 0 登記 |
| `helper_scripts/db/passive_wait_healthcheck/checks_strategy.py` | 5月 | 0 登記 |
| `helper_scripts/db/passive_wait_healthcheck/checks_execution.py` | 5月 | 0 登記 |
| `helper_scripts/db/test_*_healthcheck.py` 系列（10+ 檔）| 5月 | 0 登記 |
| `helper_scripts/db/ref21_backfill_v058_v059.py` | 5月 | 0 登記 |
| `helper_scripts/learning/lg5_re_evaluate_pending.py` | 5/2 | 0 登記 |

合計 ~20+ 個腳本未登記。SCRIPT_INDEX.md 5/3 後未更新。

### 7.2 `docs/README.md` 索引漂移

| 漏登 | 數量 |
|---|---:|
| `docs/architecture/multi_agent_rework_2026-05-05/2026-05-07--mag020.md ~ mag084.md` | 13 份（mag015 已登）|
| `docs/architecture/multi_agent_rework_2026-05-05/ENGINEERING_PLAN.md` | 1 份 |
| `docs/architecture/multi_agent_rework_2026-05-05/AgentTodo.md` | 1 份 |
| `docs/architecture/2026-05-06--openclaw_control_plane_repositioning.md` | 1 份 |
| `docs/adr/0001~0014.md` | 14 份（檢查是否有 adr 索引段落）|
| `docs/audits/2026-05-03--P0-DATA-INDICATOR-SWEEP_verdict.md` | 1 份 |
| `docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md` + `2026-05-03--ref20_wave7_*.md` | README L521-L522 已登 |
| `docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md` | 1 份 |
| `docs/execution_plan/2026-05-07--ref21_replay_remaining_wave_reset_v1.md` | 1 份 |
| 5/2-5/3 references/ 雙語版 4 對 | README L486-L489 已登（部分）|

合計 32+ 份新檔漏登 docs/README.md。

### 7.3 `docs/CLAUDE_CHANGELOG.md`

未檢查當前行數（4/24 audit 1976 行，超舊上限 1200 行）。governance 5/2 已將上限改為 1500，本檔現多大不知。**P1 carry-over**。

---

## §8 CCAgentWorkSpace 整潔度

### 8.1 各 Agent workspace/reports/ 5月活躍度

| Agent | 5月份 | 5/8 健康 |
|---|---:|---|
| PM | ~80 | 健康但雜亂 |
| E1 | ~70 | 健康（高頻 sprint impl）|
| PA | ~30 | 健康 |
| E2 | ~25 | 健康（review）|
| E4 | ~19 | 健康（regression）|
| Operator | ~50 | 健康（mirror PM）|
| **MIT** | 1 | ❌ 冷清 5/2 LG-5 RFC review only |
| **QA** | 1 | ❌ 冷清，5/4 ref20_sprint_a_r3_smoke_e2e only |
| **E1a** | 1 | ❌ 冷清 |
| **QC** | 0-2 | ❌ 冷清 |
| **CC** | 1（4/28 5dim attribution）| ❌ 冷清，無 5月 compliance audit |
| **FA** | 1（5/2 decision_lease_review_signoff）| ❌ 冷清 |
| **TW** | 0 | ❌ 完全冷清，本報告為首份 |
| **A3** | 0 | ❌ 5月無 GUI usability audit |
| **AI-E** | 0 | ❌ |
| **R4** | 0 | ❌ |
| **BB** | 0 | ❌ |
| **E3** | 0 | ❌ |
| **E5** | 0 | ❌ |

合計 18 agent 中 9 個 5月完全冷清或極少活躍。**E2/E4 review 鏈良好**，但 **TW/CC/QA/QC/AI-E/E5/A3 等審查角色 5月幾乎未活**。

### 8.2 同 Agent workspace 內同主題重複

- **E1 5/2 LG-5 W3 12 round 系列**：屬同 wave audit trail，不需合併
- **E1 5/3-5/5 ref20 sprint a/b/c/d round/wave 18 份**：需 sprint closure 摘要

### 8.3 Profile/Memory 完整性

抽樣 TW + PM 路徑：
- ✅ TW profile.md 56 行 OK；memory.md 86 行 OK；報告 2 份（4/1+4/24）
- ✅ 各 agent profile/memory/workspace/reports/ 結構齊全

### 8.4 Operator/ 鏡像規模

5/7 同日 38 份 mag**\* operator brief 對應 PM 38 份內部 — **設計重複**（兩用途不同）。READ 路徑：operator 直查 Operator/；CC 沿用 PM/。**不合併**，但建議：
- README 加說明：「Operator/ 是 PM 給 operator 看的 brief view，內容 = PM/workspace/reports/<同名>」
- 或 Operator/ 改 symlink → PM/workspace/reports/

---

## §9 .claude_reports 盤點

### 9.1 數量分布

- 4/21-4/24：~52（4/24 audit baseline）
- 4/25-5/8：估 ~430 - 52 = ~378 份新增 14 天 = **~27 份/日**
- 5/2 LG-5 W3 單日：~30 份 ⚠️ 高峰
- 5/3 ref20 sprint：~15 份
- 5/4-5/5 sprint A/B/C：~10 份
- 5/6-5/8：~9 份

### 9.2 .gitignore + 命名規範

✅ `.claude_reports/` 在 gitignore（本機隔絕）；命名 `YYYYMMDD_HHMMSS_<topic>.md` 規範良好。

### 9.3 未歸檔：

按 4/24 audit 結論「不合併 daily_summary，本機備份按需 per-day 子目錄」，現 .claude_reports 仍是平鋪 ~430 份，無 per-day 子目錄。**建議**：operator 視需要分 `2026-05/` 月 sub-dir，或保持平鋪 + 用文件名前綴排序（現狀夠用）。

---

## §10 CLAUDE.md §三 衛生

### 10.1 §三 數據點檢查

CLAUDE.md §三 內提及里程碑：

| 里程碑 | 日期 | 是否完成 +2 日 | 是否歸檔 |
|---|---|---|---|
| Decision Lease retrofit Path A LAND | 5/3（commit dbcf845b + 0ad79f67）| ✅ 5/8 已 5+ 日 | ⚠️ §三 line 99 仍記載；amendment §5.4 有 deferred operator action 5/15+ 待，**保留合理** |
| REF-20 P6 PRODUCTION CLOSED | 5/3 | ✅ 5+ 日 | ✅ memory `project_2026_05_03_*.md` + `archive/2026-05-06--claude_md_stale_extract.md` 歸檔；§三 line 118 留簡短描述 OK |
| REF-21 v1.3 active plan + scanner opportunity canary checkpoint `98ce3d00` | 5/6 | 🟡 2 日內，§三 保留合理 | ⏸ 等 5/8+2=5/10 後評估 |
| Sprint A/B/C/D closed | 5/5 | ✅ 3 日 | ⚠️ 部分敘述仍在 §三 line 116-127；建議 5/8 歸檔到 `docs/archive/2026-05-08--claude_md_section3_snapshot.md` |
| MAG-010..019 + MAG-082 stage 2 evidence window | 5/7 | 🟡 1 日，§三 保留合理 | ⏸ 等 5/9 後評估 |

### 10.2 結論

✅ §三 衛生規則大致遵守（5/2 trim snapshot land、5/6 stale_extract land）。**1 個輕微 carry-over**：Sprint A/B/C/D Wave 1-9 narrative 部分仍在 §三 line 116-127，按 +2 day 規則 5/7 即應歸檔，目前 5/8 多 1 日。建議 5/8 同 commit 歸檔 snapshot。

### 10.3 §三 數值 vs runtime drift（CLAUDE.md §七 規則）

§三 數值點：
- maker fill rate live_demo 7d **36.6%** — 採集 5/2-5/3，5/8 已 5-6 日，「滿 7 日未自動化重驗」邊界，建議 sibling CC 重 query 確認
- 24h slippage live_demo **-92.47 bps** — 同上邊界
- `[40]` realized edge avg **-27.93 bps**（2026-05-06 17:43 UTC）— 2 日前，OK
- `[51]` snapshot routes 485/485, scanner intents 50/50 — 2 日前，OK
- `[52]` strict PASS messages=2 state_changes=11 ai_invocations=2 — 5/2-5/8 之間，邊界 7 日

**建議**：sibling CC 5/9 morning 跑 healthcheck 重採樣，drift 修正同 commit。

---

## §11 Top 30 文件 housekeeping action（按 ROI 排序）

| 排序 | Action | 文件 / 路徑 | ROI 估 | 工時 |
|---|---|---|---|---:|
| 1 | 標 superseded blockquote header | `docs/execution_plan/2026-05-02--ref20_*v0.1/v1/v2/v2.1/round2_audit/round3_audit.md`（6 份）| 高（避免新 CC 讀錯版本）| 30 min |
| 2 | 標 superseded blockquote header | `docs/execution_plan/2026-05-06--ref21_*_v1/v1_1/v1_2.md` + `gui_ux_spec_v1.md`（4 份）| 高（同上）| 20 min |
| 3 | 補 README 索引 | docs/architecture/multi_agent_rework/ 14 份 mag\*\* + ENGINEERING_PLAN + AgentTodo + openclaw_control_plane_repositioning | 高（5/5-5/7 大塊新內容無索引）| 30 min |
| 4 | 補 README 索引 | docs/adr/0001-0014（14 份 ADR）| 高（治理權威文件 0 索引）| 15 min |
| 5 | 更新 SCRIPT_INDEX.md | helper_scripts/cron/ ref21\* + mlde_shadow + symbol_universe + helper_scripts/db/passive_wait_healthcheck/checks_agent_spine + checks_openclaw_gateway + checks_pricing_binding + checks_scanner_market + 各 test_\*.py + ref21_backfill_v058_v059.py + lg5_re_evaluate_pending.py（~20 個）| 高 | 45 min |
| 6 | 補中文 MODULE_NOTE | `helper_scripts/cron/ref21_market_microstructure_recorder.py`（純英文 docstring）| 中（governance 違反）| 5 min |
| 7 | 補中文 MODULE_NOTE | `helper_scripts/cron/ref21_market_recorder_retention.py`（純英文）| 中 | 5 min |
| 8 | 歸檔 §三 snapshot | `docs/archive/2026-05-08--claude_md_section3_snapshot.md` 含 5/3-5/5 sprint A/B/C/D narrative + 5/6 scanner canary 部分 | 中（§三 衛生 carry-over）| 30 min |
| 9 | 合併 audit | `docs/audits/2026-04-16/17--g2_funding_arb_clean_edge*.md` → `2026-05-08--g2_funding_arb_monitor_closeout.md` | 中（4/24 audit P1 carry-over）| 20 min |
| 10 | 加 status header | `docs/execution_plan/phase_0a~6.md`（9 份） + `docs/rust_migration/00-07.md`（8 份）批量 `> ✅ HISTORICAL — executed; see archive/`  | 中 | 30 min |
| 11 | 更新 KNOWN_ISSUES.md | 全 OPEN 項 review，標已閉合 | 中 | 60 min |
| 12 | 更新 CLAUDE_REFERENCE.md | 同步 5 月 6 重大更新 | 中 | 60 min |
| 13 | 拆分 CLAUDE_CHANGELOG.md | 中段（4/14-5/1）拆 archive | 中 | 45 min |
| 14 | 4/18 daily_summary | 補 `docs/worklogs/2026-04-18--daily_summary.md` index 引用 6 碎片 | 低（4/24 audit P1 carry-over）| 20 min |
| 15 | 4/19/4/20/4/21/4/22/4/24 daily_summary | 同 14（5 天）| 低 | 60 min |
| 16 | 5/1-5/8 daily_summary | 8 天，從 PM/E1/PA workspace + .claude_reports 抽提（高消耗，建議只補近 3 天）| 低（多碎片不易合）| 90 min |
| 17 | 標 superseded | `docs/references/2026-04-12--g_sr1_signal_tightening_plan_v2.md`（v2.5 已 FINAL）| 低（4/24 audit P2 carry-over）| 5 min |
| 18 | 標 superseded | `docs/references/2026-05-02--reality_calibrated_fast_replay_governance{,_zh}.md`（5/3 v2 替代待確認）| 低 | 10 min |
| 19 | 加 ORPHAN status | `docs/references/2026-04-04--comprehensive_audit_template_v1.md` | 低（4/24 audit P3 carry-over）| 5 min |
| 20 | 移 archive | `program_code/.../WIRING_INTEGRITY_AUDIT.md` + `L1_01_TRADE_ATTRIBUTION_FIX_SUMMARY.md` | 低 | 10 min |
| 21 | 合併 E5 | `docs/CCAgentWorkSpace/E5/2026-04-12--{e5_optimization_final,optimization_assessment}.md` | 低 | 15 min |
| 22 | 補 sprint closure 摘要 | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_a_b_c_d_closure_summary.md` | 低 | 30 min |
| 23 | 補 README architecture 段 | OpenClaw 13-tab dictionary doc（5/6 CLAUDE.md mention 但 docs/ 0 entry）| 低 | 15 min |
| 24 | E1a/QA/MIT/CC/A3/AI-E/R4/BB/E3/E5/QC 5月空轉 | E1a/QA 1 份；MIT/CC/A3/AI-E/R4/BB/E3/E5/QC 0-1 份；建議 PM 5/9 起 dispatch 補審 | 低（governance）| N/A |
| 25 | 治理 0 補檢 | TW 5/8 後固定每週 1 次 doc audit；CC 每月 compliance；QA 每 wave smoke | 低 | 治理 |
| 26 | Operator/ 鏡像策略明文 | docs/README.md 加 1 段「Operator/ vs PM/workspace/reports 鏡像規則」 | 低 | 10 min |
| 27 | .claude_reports 月分目錄 | operator 自決定 | N/A | N/A |
| 28 | docs/README.md L161 onwards 新建 architecture/multi_agent_rework_2026-05-05 子段 | 同 #3 | 中 | 同 #3 |
| 29 | TW memory 報告索引補 | TW memory 表加 5/8 本報告路徑 | 低 | 5 min |
| 30 | 整理 CCAgentWorkSpace agent ★ 4/12 audit 標 supersede | 11 個 agent root `2026-04-12--*_audit_report.md` 加 superseded by L3 audit / Wave header | 低（4/24 audit P2 carry-over）| 30 min |

---

## §12 TW Verdict

### 12.1 整體文檔健康度評分

**70% / 100%**（中等偏弱）

| 維度 | 評分 | 說明 |
|---|---:|---|
| §三 衛生規則執行 | 85% | snapshot 機制活躍（5/2 + 5/6）；1 個輕微 carry-over（5/3-5/5 sprint）|
| 命名規範遵守 | 95% | `YYYY-MM-DD--描述.md` 廣泛遵守；`.claude_reports` `YYYYMMDD_HHMMSS` 良好 |
| README 索引同步 | 50% | 5/5-5/7 大塊新內容（multi_agent_rework + adr + openclaw_repositioning）幾乎 0 索引 |
| SCRIPT_INDEX 同步 | 45% | 5/3 後 5 天無更新，~20+ script 漏登 |
| 雙語注釋遵守 | 75% | 6/6 抽樣中 4/6 中文齊備；2 個 ref21 cron 純英文（5/5 governance change 後仍違反）|
| Worklog daily_summary | 30% | 4/27-5/8 共 12 天 0 worklog top-level，全工散在 .claude_reports + agent workspace |
| RFC 多版本管理 | 40% | REF-20 7 版 + REF-21 6 版未統一 superseded blockquote header |
| Agent workspace 利用 | 50% | E1/PM 高頻；TW/CC/MIT/QA/QC/AI-E/E5/A3/R4/BB/E3 大幅冷清 |
| Pre-trim/cleanup snapshot 機制 | 90% | 5/2 + 5/6 雙 snapshot trim；機制成熟 |
| .claude_reports 隔絕 | 100% | gitignore + 命名 + 內容規範完整 |

### 12.2 建議下一輪 cleanup wave

**P1（5/9-5/12，48h 內）**：
- 補 README 索引（multi_agent_rework 14 份 + ADR 14 份 + openclaw_repositioning + audits 1 份 + execution_plan 2 份 = 共 32+ 條）
- 更新 SCRIPT_INDEX.md（~20+ 個漏登 script）
- 補中文 MODULE_NOTE（ref21 2 個 cron）
- 標 superseded blockquote header（REF-20 6 份 + REF-21 4 份 + REF-19 1 對中英）
- 歸檔 §三 snapshot（5/8 發布）

**P2（5/13-5/19，1 週內）**：
- carry-over from 4/24：g2_funding_arb 合併 / phase_0a~6 + rust_migration HISTORICAL header / E5 4/12 雙報告合併
- KNOWN_ISSUES.md / CLAUDE_REFERENCE.md / CLAUDE_CHANGELOG.md 三大 stale 文件更新
- 補 4/27-5/8 daily_summary（從 .claude_reports + agent workspace 抽提至少最近 3 天 5/6-5/8）

**P3（5/20-，長期）**：
- 整理 11 個 agent 4/12 audit ★ root reports 加 supersede header
- 監督 TW/CC/MIT/QA 等冷清 agent workspace 重新進入 wave dispatch
- WIRING_INTEGRITY_AUDIT + L1_01_TRADE_ATTRIBUTION_FIX_SUMMARY 移 archive
- references/2026-04-04--comprehensive_audit_template_v1.md 移 templates/

### 12.3 對比上輪 4/24 audit 進展

| 項 | 4/24 狀態 | 5/8 狀態 | 趨勢 |
|---|---|---|---|
| §三 衛生 04-22+04-23 snapshot 缺 | 待處理 | ✅ 5/2 + 5/6 已歸檔；4/30 + 4/29 已歸檔 | ✅ 大幅改善 |
| 4/22 daily_summary 缺 | 待處理 | ❌ 仍未補；新增 4/27-5/8 12 天 0 daily_summary | ❌ 倒退 |
| KNOWN_ISSUES.md / CLAUDE_REFERENCE.md / CLAUDE_CHANGELOG.md 3 大 stale | 待處理 | ❌ 14 天後仍未處理 | ❌ 持續 stale |
| g2_funding_arb v1+v2 合併 | 待處理 | ❌ 14 天後仍未合併（funding_arb 已 V2 棄路徑）| ❌ |
| phase_0a~6 + rust_migration HISTORICAL | 待處理 | ❌ 14 天後仍未加 header | ❌ |
| 04-12 g_sr1_signal_tightening_plan_v2 標 superseded | 待處理 | ❌ 14 天後仍未標 | ❌ |
| arch_rc1 雙副本 | ✅ 已消 | ✅ 維持 | ✅ |
| 3 個 DEPRECATED 進 archive | ✅ 已處理 | ✅ 維持 | ✅ |
| 自上輪 04-24 至今活躍 docs/ | ~539 → ~700+ | ~700+ → ~1850（含 CCAgentWorkSpace agent reports） | 📈 大量新增 |
| 新增 governance：5/2 trim、5/3 sprint 1+2+3 closure、5/4-5/5 gap closure plan、5/6 ADR + multi_agent + arcane rename | N/A | ✅ 多波 active wave 完成 | ✅ governance velocity 高 |

**結論**：5/2 trim + ADR 14 條 + multi_agent rework 設計大量交付是 5月最大 doc 進展；但日常 hygiene（README 索引、SCRIPT_INDEX、stale 三大 reference）持續退步。**建議 PA fix plan 優先派 §11 Top 5 P1 ROI 為 wave 任務**，5/9-5/12 sprint 內收斂。

---

TW AUDIT DONE: docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-08--apr_may_doc_audit.md
