# Governance Specification Register / 治理規範註冊表

**Project:** OpenClaw / Bybit
**Last Updated:** 2026-05-06
**Maintained By:** R4 (Document Auditor) · TW catch-up（2026-04-29）· FA Sign-off path A（2026-05-02 AMD-2026-05-02-01）

---

## Amendments / 規範修訂（2026-05 新增）

> Amendments are spec-level adjustments **without** changing the SM/EX/DOC numbered specifications themselves; they record implementation reaffirmations, scope clarifications, or last-mile fills (e.g., R-04 retrofit). Each amendment is dated `YYYY-MM-DD` and code-prefixed `AMD-YYYY-MM-DD-NN`.

| Code | 對應 spec | 路徑 | 日期 | 摘要 |
|------|----------|------|------|------|
| AMD-2026-05-02-01 | SM-02 §scope · DOC-01 §5.3 | `docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md` | 2026-05-02 | Path A — Rust `acquire_lease()` facade R-04 retrofit；spec 條文 0 改動，回填 v3 plan §1.3 last-mile；bundled with 18 blocker #6 audit writer fix；E4 5 條 acceptance criteria（AC-1~5）|

---

## Active Specifications / 活躍規範

### State Machine Specifications (SM)

| Code | Name | Module | Status | Description |
|------|------|--------|--------|-------------|
| SM-01 | Authorization State Machine | authorization_state_machine.py | ✅ Active | 8 states, 16 transitions, fail-closed auth |
| SM-02 | Decision Lease State Machine | decision_lease_state_machine.py | ✅ Active | 9 states, TTL-based lease lifecycle |
| SM-03 | (Reserved) | — | ⏳ Reserved | Reserved for future state machine |
| SM-04 | Risk Governor State Machine | risk_governor_state_machine.py | ✅ Active | 6-level risk escalation/de-escalation |

### Exchange Specifications (EX)

| Code | Name | Module(s) | Status | Description |
|------|------|-----------|--------|-------------|
| EX-01 | Protection & Anti-Hunt | protective_order_manager.py, portfolio_risk_control.py | ✅ Active | Hard stops, ATR dynamic distance, correlation gates |
| EX-02 | OMS & Order Lifecycle | oms_state_machine.py | ✅ Active | 11-state order management with reconciliation gate |
| EX-03 | (Reserved) | — | ⏳ Reserved | Reserved for future exchange spec |
| EX-04 | Reconciliation Engine | reconciliation_engine.py | ✅ Active | Paper vs. live/demo position consistency checks |
| EX-05 | Learning Tiers & Autonomy | learning_tier_gate.py | ✅ Active | L1-L5 analyst evolution with tier gates |
| EX-06 | Agent Conflict Arbitration | multi_agent_framework.py, market_regime.py | ✅ Active | Scout/Conductor pattern, fact/inference/hypothesis |
| EX-07 | Agent Data Access Control | governance_hub.py | ✅ Active | Cross-SM authorization and data flow control |

### Organization Document Specifications (DOC)

| Code | Name | Module(s) | Status | Description |
|------|------|-----------|--------|-------------|
| DOC-01 | Core Risk Doctrine | protective_order_manager.py | ✅ Active | Hard stop-loss §5.9, position sizing, risk limits |
| DOC-02 | Scanning & Monitoring | scanner_rate_limiter.py | ✅ Active | 5-minute scan interval, rate limiting |
| DOC-03 | Market Regime Detection | market_regime.py | ✅ Active | Regime classification, confidence scoring |
| DOC-04 | Agent Learning Evolution | learning_tier_gate.py | ✅ Active | Tier advancement criteria, performance metrics |
| DOC-06 | Change Audit Log | change_audit_log.py | ✅ Active | Append-only JSONL, rotation, thread-safe |
| DOC-07 | Audit Persistence | audit_persistence.py | ✅ Active | JSONL audit trail, file rotation |
| DOC-08 | Incident Response | incident_event_model.py | ✅ Active | Incident classification, SM trigger integration |

---

## Reference Documents (REF) / 參考規格文件（2026-04 補登）

> **REF-XX**：屬「規格性質」的長期參考文件（架構契約 / 設計規範 / 跨語言邊界 / Agent 行為規範）。
> 與 SM/EX/DOC 不同處：REF 通常為跨多模組的協調規格，無單一 implementing module。
> 路徑：`docs/references/` 或 `docs/architecture/`，所有檔遵循 `YYYY-MM-DD--<topic>.md` 命名。

| Code | Name | Path | Status | Description |
|------|------|------|--------|-------------|
| REF-01 | ARCH-RC1 Unified Config Contract | docs/references/2026-04-15--arch_rc1_unified_config_contract.md | ✅ Active | 3-Config + StrategyParams Rust 權威 / ArcSwap 熱重載 / 4 IPC 寫入面（2026-04-07 定稿） |
| REF-02 | Rust Migration V3-FINAL | docs/references/2026-04-03--rust_migration_v3_final.md | ✅ Active | Rust 遷移正式執行依據：32,500 行 / 14 週路線圖 / 分級浮點容差 / 四層測試（五角色三輪審查 21 修正） |
| REF-03 | Agent Cognitive Adaptation Spec V1 | docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md | 🟡 Draft | CognitiveModulator + OpportunityTracker + DreamEngine（五角色審查通過，Phase 1 並行組 B；CLAUDE.md §二 衍生「認知調製 ≠ 能力限制」實施準則） |
| REF-04 | ML/DL Learning Architecture V0.4 | docs/references/2026-04-03--ml_dl_learning_architecture_v0.4.md | ✅ Active | Teacher-Student + LightGBM + Optuna + 3 DL 場景（三方審查完成） |
| REF-05 | Bybit V5 API Reference (SSOT) | docs/references/2026-04-04--bybit_api_reference.md | ✅ Active | REST/WS 全端點速查 · V5 API 分類覆蓋 · 開發必讀（SSOT 標記 v1.1，2026-04-26 G9-01 路徑修正後） |
| REF-06 | Comprehensive Audit Template V1 | docs/references/2026-04-04--comprehensive_audit_template_v1.md | ✅ Active | L1/L2/L3 三級審計流程 · 5 路並行 9 角色 + DL/DB 專項 |
| REF-07 | Execution Plan V1 (Fusion Plan) | docs/references/2026-04-04--execution_plan_v1.md | ✅ Active | DB + ML/DL + 新聞 Agent 20 週路線圖 · Phase 0-6 詳細規格 |
| REF-08 | Math Implementation Notes | docs/references/2026-04-06--math_implementation_notes.md | ✅ Active | 數學實現方案彙編：LinUCB/風控公式/統計檢定/校準/shrinkage |
| REF-09 | Phase 4 Execution Plan V2 | docs/references/2026-04-06--phase4_execution_plan_v2.md | ✅ Active | 融合方案執行計劃 V2：Phase 4 更新版排期 |
| REF-10 | ARCH-RC1 1C-3 Scope | docs/references/2026-04-07--arch_rc1_1c3_scope.md | ✅ Active | ARCH-RC1 1C-3 範圍定義 |
| REF-11 | ARCH-RC1 1C-3A Gap Analysis | docs/references/2026-04-07--arch_rc1_1c3a_gap_analysis.md | ✅ Active | ARCH-RC1 1C-3A 缺口分析 |
| REF-12 | ARCH-RC1 1C-3C Reconciliation | docs/references/2026-04-07--arch_rc1_1c3c_recon.md | ✅ Active | ARCH-RC1 1C-3C 對賬設計 |
| REF-13 | Signal Diamond DB TODO | docs/references/2026-04-10--signal_diamond_db_todo.md | ✅ Active | 多引擎數據分離 5 Phase 規劃（Phase 1-4 ✅，Phase 5 待實施） |
| REF-14 | 3E-ARCH Three-Engine Parallel Plan V4 | docs/references/2026-04-11--three_engine_parallel_arch_plan.md | ✅ Active | 三引擎並行架構遷移計劃 v4：26 設計決策 · PM+PA+FA 三角色（已完成） |
| REF-15 | 3E-ARCH Session Execution Plan | docs/references/2026-04-11--3e_arch_session_execution_plan.md | ✅ Active | 3E-ARCH Session 執行計劃：8 工作日排期（已完成） |
| REF-16 | Dust-Frozen Position Manual Clear SOP | docs/references/2026-04-20--dust_frozen_position_manual_clear_procedure.md | ✅ Active | DUST-EVICTION-GAP-1 P1-8 設計背景 · Bybit GUI 三路線 · Live 前 pre-flight checklist |
| REF-17 | Cross-Platform Redeploy Dependencies | docs/references/2026-04-20--cross_platform_redeploy_dependencies.md | ✅ Active | Linux→macOS（Apple Silicon）冷裝清單 · brew/rustup/pip 步驟 · systemd↔launchd 差異 · HMAC 憑證重簽陷阱 |
| REF-18 | Model Canary Promotion Rules (Draft) | docs/references/2026-04-23--model_canary_promotion_rules_draft.md | 🟡 Draft | INFRA-PREBUILD-1 Part B Model Registry canary 狀態機 + Phase 晉升閾值 + Operator playbook（Phase 4 auto-promote cron 延後） |
| REF-19 | Reality-Calibrated Fast Replay Governance | docs/references/2026-05-02--reality_calibrated_fast_replay_governance.md<br>中文：docs/references/2026-05-02--reality_calibrated_fast_replay_governance_zh.md | 🟡 Draft | Replay/MLDE/DreamEngine 邊界契約：Replay 是實驗環境與資料來源之一；ML/Dream 仍為 Agent 自我學習與策略/風控調參能力；禁止 replay 直接 live/demo mutation |
| REF-20 | Paper Replay Lab and Learning Surface Design | docs/references/2026-05-02--paper_replay_learning_surface_design.md<br>中文：docs/references/2026-05-02--paper_replay_learning_surface_design_zh.md<br>★ SoT V3：docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md<br>Workplan V1：docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md | ⚠️ Active-with-Cold-Audit-Caveat | Paper Tab 原地升級為 Replay Lab；Learning 保持知識 cockpit 並新增 replay evidence / ML-Dream producer monitor；5-Agent 從 Learning 抽出為 read-only Agents Monitor。**2026-05-03 8-agent cold audit 揭 Wave 1-9 IMPL 是結構性 false positive**（runner 從未啟動 → vacuous truth）；Sprint 1 修 5 P0 critical security + 3 schema drift（commit edf33c0）；Sprint 2 補 §八 evidence trail + AMD-2026-05-03-01 Wave 7 IMPL/Deploy 2-stage gate（commits aa9343c + 5184990）；deploy 待 Sprint 3 Linux 實機（cargo --release replay_runner + 18 V### apply + 5 e2e smoke + Decision Lease retrofit AMD-2026-05-02-01）+ Sprint 4 14d gradient observation。詳 TODO P1-INFRA-3a-m + docs/CCAgentWorkSpace/{PA,E1,E2,E4}/workspace/reports/2026-05-03--ref20_sprint{1,2}_*.md |
| REF-21 | Full-Chain Replay Engine | docs/execution_plan/2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_3.md | 🟠 Revise / Blocked | Active V1.3 plan；provisional `/full-chain/prepare` endpoint default-OFF；R2/R3 前必過 subprocess deploy path、expanded write confinement、V057/V058/V059/V060 Linux PG dry-run、negative-edge fail-closed promotion FSM、SECURITY DEFINER metrics、Bybit SSOT URI/rate/IP policy、block bootstrap、survival/correlation/cost gates、baseline SLA、GUI V1.1；MLDE/DreamEngine 僅作 verified advisory / exploration consumer。 |

### Architecture Specifications

| Code | Name | Path | Status | Description |
|------|------|------|--------|-------------|
| ARCH-01 | Data Storage Architecture V1 | docs/architecture/DATA_STORAGE_ARCHITECTURE_V1.md | ✅ Active | PG + TimescaleDB · 8 Schema · 存儲精簡 97%（5.6→0.17 GB/day）· 冷存儲 NAS 策略 |

---

## Audit Catalog (AUDIT) / 審計報告目錄（2026-04 補登）

> **AUDIT-XX**：重大審計報告索引。涵蓋多角色聯合審計、合規審查、安全審計、ARCH 審查。
> register 不重複內容，僅追蹤審計與規範條目（SM/EX/DOC/REF）的對應關係，便於後續引用。
> 路徑：`docs/audits/`，所有檔遵循 `YYYY-MM-DD--<topic>.md` 命名。

| Code | Name | Path | Date | Cross-Reference |
|------|------|------|------|------------------|
| AUDIT-01 | Bilingual Comment Audit | docs/audits/2026-03-30--bilingual_comment_audit_report.md | 2026-03-30 | CLAUDE.md §七 雙語注釋規範 |
| AUDIT-02 | Bybit V5 API Infrastructure Audit | docs/audits/2026-04-04--bybit_api_infra_audit.md | 2026-04-04 | REF-05 / BB+E5 聯合審核 |
| AUDIT-03 | L3 Consolidated Remediation Report | docs/audits/2026-04-06--consolidated_remediation_report.md | 2026-04-06 | L3 414 findings → 63 tracker · 11 工作包 · R0-R3 整改記錄 |
| AUDIT-04 | E3 R6 Directive Applier Security Audit | docs/audits/2026-04-07--e3_r6_directive_applier_security_audit.md | 2026-04-07 | Phase 4 前置安全審查 |
| AUDIT-05 | Phase 4 Final Sign-off Audit | docs/audits/2026-04-07--phase4_final_signoff_audit.md | 2026-04-07 | Phase 4 最終驗收審計報告 |
| AUDIT-06 | E2 Review ARCH-RC1 1C-3 BBC | docs/audits/2026-04-08--e2_review_1c3_bbc.md | 2026-04-08 | REF-10 / ARCH-RC1 1C-3 Build-Before-Commit 驗收 |
| AUDIT-07 | DB R/W + ML Pipeline Full Audit | docs/audits/2026-04-09--db_rw_ml_pipeline_full_audit.md | 2026-04-09 | Signal Diamond Phase 1 前置 |
| AUDIT-08 | 3E-ARCH E2 Multi-Role Review | docs/audits/2026-04-11--3e_arch_e2_multi_role_review.md | 2026-04-11 | REF-14 / REF-15 · 9 角色並行 Phase A-F 全修驗證 |
| AUDIT-09 | 3E-ARCH Phase G Re-audit | docs/audits/2026-04-11--3e_arch_phase_g_reaudit.md | 2026-04-11 | REF-14 · 9/9 PASS — 0 BLOCKER |
| AUDIT-10 | Full Program Chain Audit | docs/audits/2026-04-12--full_program_chain_audit.md | 2026-04-12 | 12 角色合併 · 58 findings（8 P0 · 17 P1 · 28 P2 · 5 P3） |
| AUDIT-11 | Full Audit Fix Plan (PM Confirmed) | docs/audits/2026-04-12--full_audit_fix_plan_pm_confirmed.md | 2026-04-12 | AUDIT-10 配套 · P0~P3 分級修復排期 + PM 簽核 |
| AUDIT-12 | TODO Refactor Audit (10-Agent) | docs/audits/2026-04-24--todo_refactor_audit.md | 2026-04-24 | 10 Agent 獨立 audit · PA FIX-PLAN（45 findings / 6 工作組 / 4 Wave）· PM Sign-off |

> **註**：早期審計（2026-04-05 L3 12 角色報告）位於 `docs/audits/2026-04-05--l3_comprehensive/` 子目錄；
> Phase 治理審計位於 `docs/governance_dev/audits/`（如 `2026-03-31--gap_analysis_287_specs.md`）。
> 各 Agent workspace audit 位於 `docs/CCAgentWorkSpace/<Agent>/workspace/reports/`，不在本表內。

---

## Specification Numbering Rules / 編號規則

- **SM-XX**: State Machine specifications (core governance automata)
- **EX-XX**: Exchange specifications (trading operations and integration)
- **DOC-XX**: Organization document specifications (policies and procedures)
- **REF-XX**: Reference specifications (architecture contracts, design specs, cross-language boundaries; 2026-04 新增類別)
- **ARCH-XX**: Architecture specifications (system-level design documents; 2026-04 新增類別)
- **AUDIT-XX**: Audit catalog (major audit reports cross-referenced to SM/EX/DOC/REF; 2026-04 新增類別)
- **§** notation: Section references within a spec (e.g., "DOC-01 §5.9", "REF-01 §3")

---

## Cross-Reference Summary / 交叉引用摘要

| Metric | Count |
|--------|-------|
| Active SM/EX/DOC specifications | 16 |
| Reserved specifications | 2 (SM-03, EX-03) |
| Active REF specifications | 19 |
| Active ARCH specifications | 1 |
| Active AUDIT entries (2026-04) | 12 |
| Total code references | 335+ |
| Implementing modules | 22 |
| Test coverage | 2,308+ Rust lib tests + Python pytest（持續增加） |

---

## How to Add New Specifications / 如何新增規範

1. Assign next available code in appropriate category (SM/EX/DOC/REF/ARCH/AUDIT)
2. Create implementation module / document following naming convention
   - Code modules：`lowercase_snake_case.py` / `.rs`
   - Documents：`YYYY-MM-DD--<topic>.md`（中文描述優先）
3. Add spec code references in code comments (e.g., `# Per SM-XX §Y` / `// REF-XX`)
4. Create test file with matching name (test_module_name.py)
5. Add changelog entry in `docs/governance_dev/phase{N}_*/changelogs/` 或 `docs/CLAUDE_CHANGELOG.md`
6. Update this register **and** `docs/README.md` 索引

---

## Catch-up History / 補登歷史

| 日期 | 動作 | 範圍 |
|------|------|------|
| 2026-04-29 | TW catch-up（4 月補登） | 新增 REF-01~18（18 條 reference 規格）+ ARCH-01（架構規格）+ AUDIT-01~12（12 條主要審計索引）。新增 3 個編號類別：REF / ARCH / AUDIT。`Last Updated` 由 2026-03-30 → 2026-04-29。詳見 commit message 與 `docs/CCAgentWorkSpace/TW/memory.md` 同日記錄。 |

---

*OpenClaw / Bybit Governance Specification Register*
