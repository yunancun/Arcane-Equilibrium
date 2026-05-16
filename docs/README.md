# docs/ — 项目文档目录 (Project Documentation Directory)

本目录存放玄衡 · Arcane Equilibrium 交易治理系统的所有工程文档、日志、交接记录和决策备忘。

This directory holds all engineering documents, logs, handoff records, and decision memos for the Arcane Equilibrium agentic trading governance system.

---

## 强制规则 (Mandatory Rules)

**任何人（包括 AI Agent）向 docs/ 写入或新增文件时，必须遵守以下规则：**

1. **文件必须放到对应分类目录**，不允许直接扔在 `docs/` 根目录
2. **文件名必须遵守命名规范**（见下方"文件命名规范"）
3. **每次新增/移动文件后，必须更新本 README 底部的"文档索引"**
4. **不允许重复文件**：放入前检查是否已有相同内容的文件
5. **日志必须人类可读**：简洁、清晰、有上下文，中文为主 + 英文辅助
6. **禁止纯 JSON dump 或代码输出当日志**：日志是写给人看的

---

## 目录结构 (Directory Structure)

```
docs/
├── README.md                          ← 本文件（目录总览 + 规范 + 文档索引）
│
├── worklogs/                          ← 工作日志（按章节/模块分子目录）
│   ├── chapters_a-g/                  ← A-G 章节：基础层 / 观察者 / 事件层
│   ├── chapters_h-i/                  ← H-I 章节：本地判断内核 / AI 治理 / Decision Lease
│   ├── chapters_j-k/                  ← J-K 章节：Transition Engine / Paper Gate / GitHub 迁移
│   ├── control_api_gui/               ← Control API + GUI Operator Console 开发（2026-03-25~04-02）
│   ├── phase5_arch_rc1/               ← Phase 5 / L3 整改 / ARCH-RC1 开发（2026-04-03~04-07）
│   ├── learning/                      ← L 章节：自动学习管线 / 安全加固
│   └── （顶层文件）                   ← 2026-04-08+ 最新工作日志（直接放根目录）
│
├── handoffs/                          ← 阶段交接文档（按日期+主题分文件夹）
│   └── YYYY-MM-DD_主题名/
│
├── decisions/                         ← 重大架构/设计决策记录 + 治理源文件（DOC/SM/EX .docx）
├── adr/                               ← 架构决策记录（ADR 0001..0022）
│
├── architecture/                      ← 架構設計文件（系統層面設計決策）
│
├── _indexes/                          ← 文檔 inventory / redirect map / GUI metadata（先建索引再重命名）
│
├── audits/                            ← ★ 全系统审计报告（专项 + 综合审计子目录）
│   ├── 2026-04-05--l3_comprehensive/   ← L3 全系统综合审计（12 角色专项报告，2026-04-05）
│   └── （专项审计报告）                ← 按日期命名的专项审计（如 Bybit API 审计）
│                                      ← 注：03-31/04-01 全系统审计报告在 CCAgentWorkSpace/ 对应 Agent 下
│
├── references/                        ← 长期参考文档（规范、合同、规格书）
│   ├── state_dictionary/              ← 状态字典 / 数据字典
│   ├── api_contract/                  ← API 合同 / 路由草案 / 审核报告
│   └── api_stub/                      ← API 骨架代码
│
├── archive/                           ← 已归档/过期文档（DEPRECATED 文件、旧版摘要）
│
├── CCAgentWorkSpace/                  ← Agent 工作空间（profile/memory/workspace per agent）
├── agents/                            ← Agent issue tracker / domain / triage-label 指南
│
├── execution_plan/                    ← 执行计划（Sprint/Wave 排期、里程碑规划）
│
├── rust_migration/                    ← Rust 迁移文档（迁移规划、进度追踪）
│
└── governance_dev/                    ← 治理开发全部文档
    ├── audits/                        ← ★ 审计报告（Round 1/2 审计 + 合规审计）
    ├── changelogs/                    ← T2.01–T2.23 模组变更日志
    ├── governance_extracts/           ← 治理文件结构化提取（索引/速查/技术规格/实现清单）
    ├── phase0_restart/                ← Phase 0 重启审计
    ├── phase0_takeover/               ← Phase 0 接管（目录/代码/AI 架构/计划）
    ├── phase1_gap_analysis/           ← Phase 1 缺口分析
    ├── phase1_governance_wiring/      ← Phase 1 治理接线
    ├── phase2_execution/              ← Phase 2 治理模组执行（21 模组 + PM/TW 审核）
    ├── phase2_risk_hardening/         ← Phase 2 风控强化
    ├── phase3_bug_fix_hardening/      ← Phase 3 Bug 修复强化
    ├── phase3_integration/            ← Phase 3 治理集成 + 安全审计
    ├── phase4_acceptance/             ← Phase 4 验收（合规/测试/UX/文档/PM）
    ├── phase4_reconciliation_hardening/ ← Phase 4 对账强化
    ├── phase5–12/                     ← Phase 5-12（治理完整性/测试/Demo/REST/事件/执行/打磨）
    └── 2026-03-30--round2_fix_plan*   ← Round 2 修复计划（Batch 7-12）
```

---

## 文件命名规范 (File Naming Convention)

所有文档文件统一使用以下格式：

```
YYYY-MM-DD--功能描述.扩展名
```

带时间戳（同一天有多份文档时）：

```
YYYY-MM-DD--HHmm--功能描述.扩展名
```

规则：
- **日期在前**：便于按时间排序，一目了然
- **双横线 `--` 分隔**：日期与描述之间、时间与描述之间
- **功能描述用下划线连接**：避免空格，保持路径兼容性
- **中文描述优先**：描述部分可以用中文，如 `2026-03-26--api_gui_全量工程报告.md`
- **扩展名保留原格式**：`.md` / `.txt` / `.pdf` / `.py` 均可

---

## 日志分类说明 (Log Categories)

### 1. worklogs/ — 工作日志

**用途**：日常开发过程中的工作记录。简洁、清晰、人类可读。

**组织方式**：按章节或模块分子目录，文件按日期命名。

### 2. handoffs/ — 阶段交接文档

**用途**：一个工程阶段完成后的正式交接记录，供后续开发者或未来的自己快速了解上下文。

**组织方式**：每次交接创建一个子文件夹，命名为 `YYYY-MM-DD_主题名`。

### 3. decisions/ — 决策记录

**用途**：记录重大架构或设计决策的背景、选项、结论和理由。

**格式建议**：
```markdown
# 决策：<标题>
日期：YYYY-MM-DD
状态：已决定 / 待讨论 / 已废弃

## 背景 (Context)
## 选项 (Options)
## 结论 (Decision)
## 影响 (Consequences)
```

### 4. audits/ — 全系统审计报告

**用途**：全系统审计报告归档。按月份分子目录（March31、April01 等），每次审计产出多角色报告；专项审计报告（如 Bybit API 审计）直接以日期命名放根目录。

### 5. references/ — 长期参考文档

**用途**：不随版本频繁变化的规范性文档，如 API 合同、状态字典规格书、部署规范等。

---

## 日志书写原则 (Writing Principles)

1. **简单清晰明了**：一段话能说清的不写两段，一句话能说清的不写一段
2. **人类可读优先**：写给人看，不是给程序解析的。用自然语言，避免纯 JSON dump
3. **中文为主，英文辅助**：正文用中文，专有名词保留英文原文（如 Decision Lease、compile_state）
4. **事实与推断分开**：明确标注哪些是确认的事实，哪些是推测或假设
5. **带上下文**：说清"为什么做"而不仅仅是"做了什么"
6. **避免冗余**：代码里能看到的不用在日志里重复，git log 能查到的不用抄一遍

---

## 文档索引 (Document Index)

### 2026-05-16 12-agent consolidated audit + Wave 1-4 (WP-01..13)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-16--12-agent-consolidated-fix-plan.md` | PA 12-agent consolidated audit fix plan：FA/AI-E/QC/E5/A3/E3/MIT/R4/BB/CC finding 驗證 + 修復優先排序 |
| `CCAgentWorkSpace/Operator/2026-05-16--12-agent-consolidated-fix-plan.md` | Operator brief：12-agent consolidated fix plan |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-16--full-scope-testing-audit.md` | E4 full-scope testing audit |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-16--12-agent-audit-pm-signoff.md` | PM 12-agent audit sign-off report |
| `CCAgentWorkSpace/Operator/2026-05-16--12-agent-audit-pm-signoff.md` | Operator brief：12-agent audit PM sign-off |
| `CCAgentWorkSpace/E1a/workspace/reports/2026-05-16--wp01_gui_safety_round1.md` | WP-01 GUI safety Round 1 sign-off（typed-phrase × 4 + LinUCB dead buttons + bilingual + native→modal）|
| `CCAgentWorkSpace/E1a/workspace/reports/2026-05-16--wp01_gui_real_fix.md` | WP-01 GUI Round 2 補修（A3-MAJOR-2 unify / 雙層 modal 拆 / 第 6 metric / 繁簡 / modal lock）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-16--wp02_donchian_deprecate.md` | WP-02 Donchian deprecate sign-off（hygiene-only + audit drift 第 3 次教訓）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-16--wp05_security_hardening.md` | WP-05 security Round 1 sign-off（bind 0.0.0.0 + global exception handler）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-16--wp05_security_real_fix.md` | WP-05 security Round 2 真修（17 routes 38 callsite + handler 順位 + error_sanitize helper）|
| `CCAgentWorkSpace/TW/workspace/reports/2026-05-16--wp09_doc_real_fix.md` | WP-09 doc Round 2 補修（README 126 entries / KNOWN_ISSUES reconcile / REF-21 SUPERSEDED / WP-01/02 sign-off）|
| `CCAgentWorkSpace/A3/workspace/reports/2026-05-16--wp01_round2_re_audit.md` | A3 WP-01 Round 2 對抗審核（8.5/10 GO-conditional）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-16--wp03_ou_sigma_fix.md` | WP-03 OU sigma residual (OLS n-2 dof) sign-off（grid_helpers.rs +170 LOC + 5 new test） |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-16--wp04_ai_observability.md` | WP-04 AI obs+budget sign-off（F-04 record_strategist_invocation + F-01 budget drift fix + F-09 TODO）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-16--wp10_bybit_integration.md` | WP-10 Bybit sign-off（BB-A-1 ReduceOnlyReject=110017 + BB-M-1 backtest URL env var）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-16--reject_cooldown_split_bbmf3.md` | BB-MF-3 reject_cooldown entry/close split sign-off（grid_trading 5 files + 8 new test）|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-16--wp06_wp08_python_fixes.md` | Wave 3 WP-06 deepcopy 3→2 + WP-08 engine_mode + purge_days sign-off |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-16--wp13_reconciler_cmd_tx.md` | Wave 3 WP-13 demo reconciler DemoCmdSenderSlot sign-off |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-16--wave2_3_full_regression.md` | E4 Wave 2-3 full regression (7366 cases Mac-side PASS) |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-16--wave2_wp{03,04,06,08,10,13}_retroactive_review.md` | E2 retroactive review × 6 WP（補 chain breach） |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-16--bbmf3_retroactive_review.md` | E2 retroactive review BB-MF-3（APPROVE-CONDITIONAL） |
| `CCAgentWorkSpace/BB/workspace/reports/2026-05-16--wave2_wp10_bbmf3_round3_bb_review.md` | BB Wave 2 WP-10 + BB-MF-3 Round 3 review（APPROVE-COND）|
| `CCAgentWorkSpace/BB/workspace/reports/2026-05-16--bb_dict_110017_patch.md` | BB 字典 §4.2 110017 ReduceOnlyReject row 補完 |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-16--mit_cron_reconcile.md` | PA reconcile MIT-P0-2「6/12 cron 未裝」= **FALSE FINDING**（廣口徑漂移）|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-15--v094_schema_migration_spec_pa_verdict.md` | PA Wave 2a Track A2 V094 spec finalize verdict |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-15--wave_1_5b_spec_v1_3_amd_v0_4_consolidated.md` | PA Wave 1.5b spec v1.3 + AMD v0.4 consolidated |
| `docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md` | V094 hybrid schema migration spec（Wave 2a Track A2，commit 9b1117a0）|
| `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md` | AMD-2026-05-15-02 v0.4（EDGE-P2-3 Phase 1b 4-agent re-review consolidated）|
| Wave 2 IMPL commit `ef6ea79f` | WP-03 OU sigma + WP-04 AI obs + WP-07 dead code + WP-10 Bybit retCode |
| Wave 2b BB-MF-3 IMPL commit `27f02a07` | reject_cooldown entry/close split (Wave 2b recovery) |
| Wave 3 IMPL commit `f31b6e8f` | WP-06 deepcopy 3→2 + WP-08 engine_mode + purge_days + WP-13 demo reconciler |
| Wave 4 WP-11 commit `564c9db6` | 15 failing Python tests fix (16→1 flaky) |
| Wave 4 closure commit `fca27914` | WP-11 DONE + WP-12 DEFERRED |

### 2026-05-11 Sprint N+1 dispatch + W-D + LG design

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--w_d_mag083_pa_audit.md` | PA MAG-083 三角 audit |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--w2_impl_v12_dispatch_plan.md` | PA W2 A4-C IMPL v1.2 dispatch plan |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p1_v083_ipc_close_fix_design.md` | PA P1 V083 IPC close fix design |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p1_rca1_f1_f2_emergency_fix_plan.md` | PA P1 RCA1 F1/F2 emergency fix plan |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_22h08_deploy_edge_regression_rca.md` | PA P0 22h08 deploy edge regression RCA |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_option_a_position_state_ssot_refactor.md` | PA P0 option A position state SSOT refactor |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p1_strategist_params_persist_ma_crossover_rca.md` | PA P1 Strategist params persist MA crossover RCA |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p2_n2_backlog_tickets.md` | PA P2 N+2 backlog tickets |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--f3_f4_writer_defense_n1_dispatch_plan.md` | PA F3/F4 writer defense N+1 dispatch plan |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_replay_engine_counterfactual_fix_design.md` | PA P0 replay engine counterfactual fix design |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md` | PA LG-2/3/4 design plan |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v1.md` | PA LG-3 spec v1 |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v2_final.md` | PA LG-3 spec v2 final |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-15--close_maker_first_pa_verdict.md` | PA close-maker-first verdict |

#### 2026-05-11 owner reports — E1 (39)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_2_p2_1_bb_breakout_w7_propagation.md` | E1 P1-2 / P2-1 bb_breakout W7 propagation |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w2_impl_2_btc_lead_lag_producer_v088_writer.md` | E1 W2 IMPL 2: BTC→Alt Lead-Lag producer V088 writer |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w1_impl_alpha_panel_aggregator_v085_writer.md` | E1 W1 IMPL alpha panel_aggregator V085 writer |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w1_impl_beta_oi_delta_aggregator_v087_writer.md` | E1 W1 IMPL beta oi_delta_aggregator V087 writer |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w1_impl_gamma_ws_subscription_main_loop.md` | E1 W1 IMPL gamma WS subscription main loop |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w_c_fix_rust_impl.md` | E1 W-C fix Rust impl |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w2_impl_3_strategy_paper_shadow_log.md` | E1 W2 IMPL 3: strategy paper shadow log |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w_c_fix_rust_impl_round2.md` | E1 W-C fix Rust impl round 2 |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w2_impl_5_ipc_slot_main_spawn_step_4_5_wire.md` | E1 W2 IMPL 5: IPC slot main spawn step 4/5 wire |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_1_stable_id_helper.md` | E1 P1-1 stable_id_helper |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_rca1_orphan_er_missed_fill.md` | E1 P1 RCA1 orphan ER missed fill |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_v083_ipc_close_impl_done.md` | E1 P1 V083 IPC close IMPL DONE |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w2_impl_3_check_57.md` | E1 W2 IMPL 3 check 57 |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w2_impl_4_paper_edge_report.md` | E1 W2 IMPL 4: paper edge report |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w2_impl_1_orderbook_wiring.md` | E1 W2 IMPL 1: orderbook wiring |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w2_impl_4_sql_fix.md` | E1 W2 IMPL 4 SQL fix |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--option_a_lite_e1_d_grid_trading.md` | E1 option-A-lite grid_trading |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--option_a_lite_e1_e_funding_arb.md` | E1 option-A-lite funding_arb |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--option_a_lite_e1_b_bb_reversion.md` | E1 option-A-lite bb_reversion |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--option_a_lite_e1_c_bb_breakout.md` | E1 option-A-lite bb_breakout |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--option_a_lite_e1_a_ma_crossover.md` | E1 option-A-lite ma_crossover |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p2_v083_cron_synthetic_id_recognition.md` | E1 P2 V083 cron synthetic ID recognition |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--option_2_replay_counterfactual_validation.md` | E1 option-2 replay counterfactual validation |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--option_2_replay_engine_validation_v2.md` | E1 option-2 replay engine validation v2 |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--replay_tier_a_e1_b_manifest_config_echo.md` | E1 replay tier A: manifest config echo |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--replay_tier_a_e1_a_runner_position_state.md` | E1 replay tier A: runner position state |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--replay_tier_a_e1_c_per_symbol_price.md` | E1 replay tier A: per-symbol price |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--replay_tier_a_e1_d_acceptance_pack.md` | E1 replay tier A: acceptance pack |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--replay_tier_a_27h_validation_run.md` | E1 replay tier A 27h validation run |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_stable_id_helper_impl.md` | E1 P1 stable ID helper impl |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_fill_lineage_drop_fix.md` | E1 P1 fill-lineage drop fix |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg1_t4_h0_block_summary_route.md` | E1 LG-1 T4 H0 block summary route |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg1_t3_h0_flip_runbook_ctor.md` | E1 LG-1 T3 H0 flip runbook ctor |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg1_t1_h0_blocking_test.md` | E1 LG-1 T1 H0 blocking test |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg2_t4_riskconfig_pricing.md` | E1 LG-2 T4 RiskConfig pricing binding |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg1_t2_h0_block_acceptance.md` | E1 LG-1 T2 H0 block acceptance |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg2_t1_contract_tests.md` | E1 LG-2 T1 contract tests |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg2_t3_fee_source_enum.md` | E1 LG-2 T3 FeeSource enum + IPC route |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg2_t2_startup_assertion.md` | E1 LG-2 T2 startup assertion |

#### 2026-05-11 owner reports — E2 (10)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-11--w_c_fix_e2_review_round2.md` | E2 W-C fix review round 2 |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-11--p1_1_stable_id_helper_e2_review.md` | E2 P1-1 stable_id_helper review |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-11--p1_v083_p2_freq_e2_review.md` | E2 P1 V083 P2 frequency review |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-11--w2_chain_e2_adversarial_review.md` | E2 W2 chain adversarial review |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-11--w2_impl_4_sql_fix_e2_review.md` | E2 W2 IMPL 4 SQL fix review |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-11--w2_impl_5_e2_review.md` | E2 W2 IMPL 5 review |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-11--option_a_lite_post_merge_audit.md` | E2 option-A-lite post merge audit |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-11--replay_tier_a_post_impl_audit.md` | E2 replay tier A post-IMPL audit |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-11--p1_fill_lineage_drop_e2_review.md` | E2 P1 fill-lineage drop review |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-11--wave2_2_lg1_lg2_e2_review.md` | E2 Wave 2.2 LG-1/LG-2 review |

#### 2026-05-11 owner reports — E4 (10)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w_c_fix_e4_regression.md` | E4 W-C fix regression |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-11--p1_v083_p2_freq_e4_regression.md` | E4 P1 V083 P2 frequency regression |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w2_chain_e4_regression.md` | E4 W2 chain regression |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w2_impl_4_sql_fix_e4_redryrun.md` | E4 W2 IMPL 4 SQL fix re-dry-run |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w2_impl_5_e4_regression.md` | E4 W2 IMPL 5 regression |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-11--option_a_lite_post_merge_regression.md` | E4 option-A-lite post merge regression |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-11--replay_tier_a_post_impl_regression.md` | E4 replay tier A post-IMPL regression |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w_audit_3b_runtime_smoke.md` | E4 W-AUDIT-3b runtime smoke |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-11--p1_fill_lineage_drop_e4_regression.md` | E4 P1 fill-lineage drop regression |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-11--wave2_2_e4_regression.md` | E4 Wave 2.2 regression |

#### 2026-05-11 owner reports — QC (3)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/QC/workspace/reports/2026-05-11--w_d_mag083_qc_audit.md` | QC W-D MAG-083 audit |
| `CCAgentWorkSpace/QC/workspace/reports/2026-05-11--p1_micro_profit_amplification_math_analysis.md` | QC P1 micro profit amplification 數學分析 |
| `CCAgentWorkSpace/QC/workspace/reports/2026-05-11--lg3_spec_qc_review.md` | QC LG-3 spec review |

#### 2026-05-11 owner reports — MIT (1) / A3 (1) / PM (1)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-11--lg3_spec_mit_review.md` | MIT LG-3 spec review |
| `CCAgentWorkSpace/A3/workspace/reports/2026-05-11--wave2_2_a3_ux.md` | A3 Wave 2.2 UX review |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-11--amd_w6_1_pm_consolidate_signoff.md` | PM AMD-W6-1 consolidate sign-off |

#### 2026-05-11 owner reports — Operator briefs (5)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/Operator/2026-05-11--p1_v083_ipc_close_fix_design.md` | Operator brief: P1 V083 IPC close fix design |
| `CCAgentWorkSpace/Operator/2026-05-11--p0_22h08_deploy_edge_regression_rca.md` | Operator brief: P0 22h08 deploy edge regression RCA |
| `CCAgentWorkSpace/Operator/2026-05-11--p1_strategist_params_persist_ma_crossover_rca.md` | Operator brief: P1 Strategist params persist MA crossover RCA |
| `CCAgentWorkSpace/Operator/2026-05-11--lg_3_spec_v1.md` | Operator brief: LG-3 spec v1 |
| `CCAgentWorkSpace/Operator/2026-05-11--lg_3_spec_v2_final.md` | Operator brief: LG-3 spec v2 final |

#### 2026-05-10 owner reports — E1 (18)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w_audit_8a_phase_a_trait_alpha_surface.md` | E1 W-AUDIT-8a Phase A trait AlphaSurface |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w_audit_4b_m3_part_2_rust_producer_emit_reject.md` | E1 W-AUDIT-4b M3 part 2 Rust producer emit reject |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w7_3_emergency_1tick_defense.md` | E1 W7-3 emergency 1-tick defense |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w2_w7_1_trait_skeleton_prewrite.md` | E1 W2/W7-1 trait skeleton prewrite |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w6_v086_sql_skeleton_prewrite.md` | E1 W6 V086 SQL skeleton prewrite |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w7_2_ma_crossover_bb_reversion_entry_path_query.md` | E1 W7-2 ma_crossover/bb_reversion entry path query |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w7_5_on_fill_bootstrap_import_positions.md` | E1 W7-5 on_fill bootstrap import positions |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w2_v088_btc_lead_lag_panel_sql_skeleton_prewrite.md` | E1 W2 V088 BTC lead-lag panel SQL skeleton prewrite |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w1_v087_sql_skeleton_prewrite.md` | E1 W1 V087 SQL skeleton prewrite |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w6_3c_v086_impl_dry_run_writer_code.md` | E1 W6-3c V086 IMPL dry-run writer code |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w5_e1_c_dynamic_unblock_check_1_impl.md` | E1 W5 dynamic-unblock-check-1 IMPL |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--v085_087_088_dry_run_apply.md` | E1 V085/087/088 dry-run apply |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w5_e1_a_canary_stage_criteria_1_impl.md` | E1 W5 canary-stage-criteria-1 IMPL |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--v089_dry_run_apply.md` | E1 V089 dry-run apply |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--check_65_chain_integrity_post_m3_impl.md` | E1 check 65 chain integrity post-M3 IMPL |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--v091_decision_features_mutex_check_impl.md` | E1 V091 decision_features mutex check IMPL |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--p1_1_bb_reversion_w7_3_propagation.md` | E1 P1-1 bb_reversion W7-3 propagation |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w_c_fix_python_impl.md` | E1 W-C fix Python impl |

#### 2026-05-10 owner reports — E2 (4)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-10--sprint_n0_w2_second_batch_review.md` | E2 Sprint N+0 W2 second batch review |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-10--sprint_n0_w2_third_pass_review.md` | E2 Sprint N+0 W2 third pass review |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-10--w7_3_review.md` | E2 W7-3 review |
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-10--w_c_fix_e2_review.md` | E2 W-C fix review |

#### 2026-05-10 owner reports — E4 (5) / E5 (1)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-10--sprint_n0_w2_regression_baseline.md` | E4 Sprint N+0 W2 regression baseline |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-10--sprint_n0_w2_regression_third_pass.md` | E4 Sprint N+0 W2 regression third pass |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-10--w7_3_regression.md` | E4 W7-3 regression |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-10--w_audit_3b_runtime_smoke_test_design.md` | E4 W-AUDIT-3b runtime smoke test design |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-10--w4_router_lease_guard_drop_test_prewrite.md` | E4 W4 RouterLeaseGuard drop test prewrite |
| `CCAgentWorkSpace/E5/workspace/reports/2026-05-10--w_c_fix_e5_perf_review.md` | E5 W-C fix perf review |

#### 2026-05-10 owner reports — QC (5)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/QC/workspace/reports/2026-05-10--tonusdt_structural_edge_replay.md` | QC TONUSDT structural edge replay |
| `CCAgentWorkSpace/QC/workspace/reports/2026-05-10--w6_rfc_qc_questions_self_answer.md` | QC W6 RFC questions self-answer |
| `CCAgentWorkSpace/QC/workspace/reports/2026-05-10--w2_a4c_qc_review_alpha_decay_dsr.md` | QC W2 A4-C alpha decay / DSR review |
| `CCAgentWorkSpace/QC/workspace/reports/2026-05-10--w6_1_rfc_qc_signoff_verdict.md` | QC W6-1 RFC sign-off verdict |
| `CCAgentWorkSpace/QC/workspace/reports/2026-05-10--amd_w6_1_qc_verify.md` | QC AMD-W6-1 verify |

#### 2026-05-10 owner reports — MIT (9)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--sprint_n0_final_review.md` | MIT Sprint N+0 final review |
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--v083_v084_linux_pg_dry_run_verify.md` | MIT V083/V084 Linux PG dry-run verify |
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--chain_integrity_historical_replay.md` | MIT chain integrity historical replay |
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--governance_reject_baseline_w6_rfc.md` | MIT governance reject baseline W6 RFC |
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w6_rfc_mit_questions_self_answer.md` | MIT W6 RFC questions self-answer |
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w6_3a_close_tag_distribution_audit.md` | MIT W6-3a close tag distribution audit |
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w2_c3_sigma_verify_btcusdt_1m_forward_return.md` | MIT W2-C3 sigma verify BTCUSDT 1m forward return |
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w6_1_rfc_mit_signoff_verdict.md` | MIT W6-1 RFC sign-off verdict |
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--amd_w6_1_mit_verify.md` | MIT AMD-W6-1 verify |

#### 2026-05-10 owner reports — BB (2) / CC (1) / R4 (1)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/BB/workspace/reports/2026-05-10--sprint_n0_final_bybit_compatibility_review.md` | BB Sprint N+0 final Bybit compatibility review |
| `CCAgentWorkSpace/BB/workspace/reports/2026-05-10--w1_w2_bybit_v5_rate_budget_review.md` | BB W1/W2 Bybit V5 rate budget review |
| `CCAgentWorkSpace/CC/workspace/reports/2026-05-10--n1_d0_signoff_compliance_pre_check.md` | CC N+1 D+0 sign-off compliance pre-check |
| `CCAgentWorkSpace/R4/workspace/reports/2026-05-10--n1_d0_docs_audit_pre_signoff.md` | R4 N+1 D+0 docs audit pre-sign-off |

#### 2026-05-10 owner reports — PM (5) / Operator briefs (6)

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-10--n1_d1_second_day_dispatch_sop.md` | PM N+1 D+1 second-day dispatch SOP |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-10--live_today_pnl_gui_fix.md` | PM live today PnL GUI fix |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-10--n0_high5_signoff_draft.md` | PM N+0 HIGH-5 sign-off draft |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-10--live_demo_pnl_series_gui.md` | PM live demo PnL series GUI |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-10--live_demo_pnl_series_refresh_fix.md` | PM live demo PnL series refresh fix |
| `CCAgentWorkSpace/Operator/2026-05-10--pa_governance_4docs_invariant17_closure.md` | Operator brief: PA governance 4 docs invariant 17 closure |
| `CCAgentWorkSpace/Operator/2026-05-10--a4c_btc_alt_lead_lag_spec.md` | Operator brief: A4-C BTC→Alt Lead-Lag spec |
| `CCAgentWorkSpace/Operator/2026-05-10--live_today_pnl_gui_fix.md` | Operator brief: live today PnL GUI fix |
| `CCAgentWorkSpace/Operator/2026-05-10--live_demo_pnl_series_gui.md` | Operator brief: live demo PnL series GUI |
| `CCAgentWorkSpace/Operator/2026-05-10--w6_1_rfc_pa_signoff_verdict.md` | Operator brief: W6-1 RFC PA sign-off verdict |
| `CCAgentWorkSpace/Operator/2026-05-10--live_demo_pnl_series_refresh_fix.md` | Operator brief: live demo PnL series refresh fix |

### 2026-05-15 PM/PA/FA 5-day audit + current-state sync

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--pm_pa_fa_5day_audit_todo_sync.md` | PM/PA/FA 5 日工作质量、TODO/README/MEMORY stale 核查、排序重整与三端同步结果 |
| `CCAgentWorkSpace/Operator/2026-05-15--pm_pa_fa_5day_audit_todo_sync.md` | Operator brief：PM/PA/FA audit verdict、当前事实、重排优先级和 Linux sync blocker |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--stage0r_oi_confirmed_5m_preflight.md` | `bb_breakout_oi_confirmed_5m` Stage 0R replay packet spec；spec-only，未执行 replay，`eligible_for_demo_canary=false` |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--stage0r_oi_confirmed_5m_feasibility_probe.md` | `bb_breakout_oi_confirmed_5m` read-only feasibility probe；data surface healthy but runtime-style rows underpowered/negative，仍不可作 promotion evidence |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--post_rebuild_sync_7b33ab2e.md` | Post-rebuild sync：runtime code line `7b33ab2e` rebuilt；`[27]` immediate PASS under fresh-restart grace，post-grace closure tracked separately |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--alpha_path_phase_c_dispatch.md` | Alpha path dispatch：A4-C remains GATE-RED；W-AUDIT-8a Phase C split into C0 inventory / C1 revival；current TODO 8b/8c naming made canonical |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--p1_intent_freeze_27_post_grace_closure.md` | `[27] intents_counter_freeze` post-grace direct PASS closure；`[66]`/`[67]` remain PASS；Stage 1 demo still blocked by alpha gates |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--w_audit_8a_phase_c0_liquidation_inventory.md` | W-AUDIT-8a Phase C0 liquidation revival inventory：DB/table/retention/source status + production topic guard test + C1 BB probe contract |
| `execution_plan/2026-05-15--w_audit_8a_c1_liquidation_topic_probe_plan.md` | W-AUDIT-8a C1 standalone proof plan：official `allLiquidation.{symbol}` topic, isolated 24h BB probe contract, output files, and production boundary |
| `execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md` | W-AUDIT-8b Funding Skew Directional spec v0.2：cross-sectional crowding signal using FundingSkew + OIDeltaPanel, with QC/MIT/BB Stage 0R design constraints |
| `execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md` | EDGE-P2-3 Phase 1b Close-Maker-First spec：close path maker-first refactor, 3-phase rollout, V094 migration design |
| `execution_plan/2026-05-15--a4c_btc_alt_lead_lag_archive_verdict.md` | A4-C archive verdict：Stage 0R Step 5b failed the R² archive rule, so BTC→Alt Lead-Lag is diagnostic-only and no longer a promotion candidate |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--a4c_unblock_engineering_card.md` | A4-C PM/PA/FA engineering card：archive from promotion, allow only read-only `P1-A4C-RCA-1`, and block demo budget unless a future preregistered Stage 0R packet is green |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--a4c_stage0r_rca_start.md` | A4-C `P1-A4C-RCA-1` read-only RCA start：current 7d dry-run and finite threshold probe both remain below promotion/revive bands |
| `CCAgentWorkSpace/Operator/2026-05-15--a4c_unblock_engineering_card.md` | Operator brief for A4-C archive/RCA card |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--micro_profit_alpha_prework.md` | PM report for P0-MICRO-PROFIT prework：C1 probe packet, 8b spec, A4-C archive verdict, TODO/active-plan sync |
| `CCAgentWorkSpace/Operator/2026-05-15--micro_profit_alpha_prework.md` | Operator brief for P0-MICRO-PROFIT alpha prework |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--todo_v30_three_side_sync.md` | TODO v30 source-sync checkpoint：remove stale active docs sync wording and record source-only Mac/origin/Linux sync boundary |
| `CCAgentWorkSpace/Operator/2026-05-15--todo_v30_three_side_sync.md` | Operator brief for TODO v30 source-only three-side sync |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--a4c_rca_final_and_c1_proof_start.md` | A4-C RCA final + C1 proof start：QC/MIT close `P1-A4C-RCA-1` no-revive and start 24h isolated `allLiquidation.BTCUSDT` proof on `trade-core` |
| `CCAgentWorkSpace/Operator/2026-05-15--a4c_rca_final_and_c1_proof_start.md` | Operator brief for A4-C no-revive RCA closure and running C1 proof |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--w_audit_8b_review_stage0r_design.md` | W-AUDIT-8b Funding Skew review + Stage 0R design：QC/MIT/BB conditional approve design-only with locked K/DSR/PBO, raw panel joins, and funding attribution boundaries |
| `CCAgentWorkSpace/Operator/2026-05-15--w_audit_8b_review_stage0r_design.md` | Operator brief for W-AUDIT-8b review/design checkpoint |
| `CCAgentWorkSpace/Operator/2026-05-15--stage0r_preflight_verification.md` | Operator brief for Stage 0R preflight verification |
| `CCAgentWorkSpace/Operator/2026-05-15--passive_healthcheck_7108035d_plan_sync.md` | Operator brief for passive healthcheck 7108035d plan sync |
| `CCAgentWorkSpace/Operator/2026-05-15--feature_baseline_restore.md` | Operator brief for W-AUDIT-4b feature baseline restore |
| `CCAgentWorkSpace/Operator/2026-05-15--stage0r_preflight_step5b.md` | Operator brief for A4-C Stage 0R Step 5b runtime verification |
| `CCAgentWorkSpace/Operator/2026-05-15--p1_healthcheck_55_invariant.md` | Operator brief for `[55]` fully-filled plan invariant source-clear |
| `CCAgentWorkSpace/Operator/2026-05-15--p1_intent_freeze_27_qty_rounding_rca.md` | Operator brief for `[27]` intent freeze qty rounding RCA |
| `CCAgentWorkSpace/Operator/2026-05-15--f_fa_3_w_c_caveat_2_guard_tests_design.md` | Operator brief for F-FA-3 W-C caveat 2 guard tests design |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_consolidated.md` | AMD-2026-05-15-02 4-agent adversarial review consolidated：17 must-fix / 14 should-fix / QC+FA+BB+MIT 全 APPROVED-CONDITIONAL |
| `CCAgentWorkSpace/QC/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_qc.md` | QC verdict for AMD-2026-05-15-02：4 MF / 5 SF / 3 NTH |
| `CCAgentWorkSpace/FA/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_fa.md` | FA verdict for AMD-2026-05-15-02：4 MF / 5 SF / 4 NTH |
| `CCAgentWorkSpace/BB/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_bb.md` | BB verdict for AMD-2026-05-15-02：5 MF / 3 SF / 4 NTH |
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_mit.md` | MIT verdict for AMD-2026-05-15-02：4 MF / 4 SF / 1 NTH |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--stage0r_preflight_verification.md` | Stage 0R preflight verification report |
| `archive/2026-05-15--todo_v24_stale_rows_archive.md` | TODO v24 中过时 active rows / stale claims 归档，包括 V079 pending、engine 5/8 binary、旧 05-09 demo state、旧 `[55]`/`[67]` 判断 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--p1_healthcheck_55_invariant.md` | `[55]` fully-filled plan invariant source-clear report |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--feature_baseline_restore.md` | W-AUDIT-4b feature baseline restore report，646 active rows / 19 symbols / 34 features |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--stage0r_preflight_step5b.md` | A4-C Stage 0R Step 5b runtime verification，仍 GATE-RED |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-15--passive_healthcheck_7108035d_plan_sync.md` | Passive healthcheck 7108035d plan sync report |

### 2026-05-09 v3 verification + PA redesign + DUAL-TRACK index addendum

| 文件 | 内容 |
|------|------|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md` | PA architectural root cause redesign blueprint — R-1..R-5 upgrade roadmap; alpha-poverty / Strategist scope / Analyst dormant / forcing function gap / 5-Agent skeleton without soul 5 root causes |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_audit_pa_fix_plan_v2.md` | DUAL-TRACK fix plan v2 — Track W (88 finding maintenance) + Track A (R-1..R-5 architectural) parallel |
| `execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md` | W-AUDIT-8a SPEC PHASE — Alpha Surface Foundation interface contract + DAG (R-1 spec phase, no IMPL) |
| `adr/0021-alpha-source-architecture-upgrade.md` | ADR-0021 — Alpha Source Architecture Upgrade R-1..R-5; supersedes LG-X-02..05 system-wide promotion design |
| `adr/0022-strategist-cap-wide-parameter-adjustment-skill.md` | ADR-0022 — Strategist 30%→50% cap as wide_parameter_adjustment skill (freedom-not-gate; SM-05 invariants 完全保留 + 50% 偏離監測 ledger + monthly Guardian veto review) |
| `architecture/2026-05-10--ARCH-04-graduated-canary-5-stage.md` | ARCH-04 — Historical Graduated Canary architecture baseline; Stage 1 paper semantics superseded by AMD-2026-05-15-01 (Stage 0R replay preflight + Stage 1 demo micro-canary), while Live 5-gate / DOC-08 §12 / SM-04 ladder / §二 16 原則 hard boundaries remain unchanged |
| `governance_dev/amendments/2026-05-10--AMD-2026-05-10-03-invariant-5-wording-n0-scope.md` | AMD-2026-05-10-03 — invariant 5 wording 對齊 N+0 actual IMPL (option A per operator 2026-05-10 sign-off discussion；commit `0b9a03ef` 已 land) + invariant 5b N+1 預告 |
| `governance_dev/amendments/2026-05-10--AMD-2026-05-10-04-toml-drift-fix-sop.md` | AMD-2026-05-10-04 — TOML drift gap 治理 SOP (option B-later per operator 2026-05-10；Sprint N+1 W3 cohort 拍板 + atomic patch + W-AUDIT-9 T7 regression + W-AUDIT-3b runtime smoke pre-launch) |
| `governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md` | AMD-2026-05-15-01 — W-AUDIT-9 canary rebase: remove Stage 1 paper cohort, add Stage 0R Replay Preflight, redefine Stage 1 as Demo micro-canary, and require Stage 2 entry from Stage 1 demo evidence |
| `execution_plan/2026-05-10--w_audit_8a_phase_b_tier_2_collector_spec.md` | W1 Phase B Tier 2 panel collector spec v1.1 — Rust panel_aggregator/{funding_curve,oi_delta} 訂閱既有 WS tickers broadcast (BB WS-first push back 採納, rate 100 req/min → 0 req/s ongoing + 75 req cold-start once) + bb_breakout fail-closed 寫 oi_panel_unavailable + 5m/15m/1h schema |
| `execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md` | W2 A4-C BTC→Alt Lead-Lag spec v1.2 — Cohort 8 symbol (BTCUSDT lead + 7 alt; exclude BUSDT/INXUSDT/frozen) + lead signal triple component (return + volume z + book imbalance) over N=120s + V088 panel.btc_lead_lag_panel + 三層 paper-only fence + dual-layer σ acceptance (raw market σ_60=4.54 vs net edge σ=50-80) + +15/+5-15/<+5 階梯 gate + PSR(0) skew/kurt formula 強制 |
| `execution_plan/2026-05-10--p1_canary_stage_criteria_1_spec.md` | P1-CANARY-STAGE-CRITERIA-1 spec — W-AUDIT-9 Stage 1→2→3→4 promotion + demote criteria 寫死 (per QC HIGH push back 2 sample size vs wall-clock 矛盾)；AMD-2026-05-10-05 起草；[58] healthcheck enrich |
| `execution_plan/2026-05-10--p1_canary_cohort_freq_23_spec.md` | P1-CANARY-COHORT-FREQ-23 spec — invariant 23 cohort frequency cap (30d 內 cohort symbol 最多 2 次 Stage 1 entry, 第 3 次 PA+QC override sign-off) + V089 governance.cohort_freq_cap_attempts + AMD-2026-05-10-06 起草 + [63] healthcheck |
| `execution_plan/2026-05-10--p1_dynamic_unblock_check_1_spec.md` | P1-DYNAMIC-UNBLOCK-CHECK-1 spec — 30d cycle audit logic + auto unblock criteria + manual override SOP + reverse re-freeze (per QC v3 NEW-ISSUE-V3-4 17 frozen cells permanent dormant 環路) + V090 governance.unblock_candidates + [64] healthcheck + reuse blocked_symbols_7d_counterfactual.py 改 30d |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-10--sprint_n1_dispatch_draft.md` | **Sprint N+1 Dispatch Draft v3.7** (PA, current authoritative) — 7 Wave (W1-W7) + W6 reframe (governance 沒 over-fit, real gap = metadata + imbalance + duplicate_intent bug) + W7 STRATEGY-POSITION-SYNC (W7-1+W7-3 PR ready) + W2 A4-C fast-track + 24 D+0 提前準備項；HEAD `9695b59a` |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-10--n0_signoff_n1_dispatch_fire_sop.md` | N+0 sign-off + N+1 dispatch fire SOP — pre-fire 檢查 + deploy 步驟 (一次 restart_all --rebuild --keep-auth W7-3+W7-1+W2 trait) + dispatch fire (W7-2/W7-4/W7-5 + W6 + W1 + W2 + W4 + W5 並行) + memory persist + 24h watch |
| `archive/2026-05-09--w_audit_verified_closed_archive_v2.md` | v2 verified-closed archive (R4 v2 errata 補登) |
| `archive/2026-05-09--w_audit_verified_closed_archive_v3.md` | v3 verified-closed archive — DUAL-TRACK structure + 5 commits real cover + cross-agent PA Redesign verdict |
| `../2026-05-09--audit_fix_verification_v3_summary.md` | PM v3 sign-off summary (top-level operator-facing) |
| `CCAgentWorkSpace/{FA,AI-E,E5,E4,E3,CC,QC,MIT,BB,TW,R4,A3}/workspace/reports/2026-05-09--*_v3.md` | 12 v3 verification reports (per-agent re-audit after v2 land) |
| `../2026-05-09--audit_fix_verification_v2_summary.md` | PM v2 sign-off summary (intermediate, superseded by v3) |

### 2026-05 W-AUDIT-1 index addendum（AgentTodo / audit / governance）

| 文件 | 内容 |
|------|------|
| `../2026-05-08--full_audit_fix_plan.md` | 12-agent full audit PA 整合修復計劃：88 unique findings / W-AUDIT-1..7 / 5 pending operator decisions |
| `governance_dev/2026-05-08--w_c_lease_router_authorized.md` | W-C Decision Lease router evidence-mode operator authorization record |
| `governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md` | AMD-2026-05-02-01 + §5.4.1 W-C early evidence flag addendum |
| `governance_dev/amendments/2026-05-03--ref20_wave7_p5_impl_accept_deploy_blocked.md` | AMD-2026-05-03-01 Wave 7 P5 IMPL accepted / deploy blocked split |
| `governance_dev/amendments/2026-05-09--SM-05_executor_shadow_mode_polling_design.md` | AMD-2026-05-09-01 accepted SM-05 Executor shadow-mode polling policy; F-01 implementation pending |
| `governance_dev/amendments/2026-05-09--operator_decision_audit_closure.md` | AMD-2026-05-09-02 operator decision audit closure for P0-DECISION-AUDIT-2/4/5 |
| `governance_dev/amendments/2026-05-09--strategist_wide_adjustment_skill.md` | AMD-2026-05-09-03 Strategist 30%->50% wide_parameter_adjustment skill（freedom-not-gate + RuntimeMaxEnvelope） |
| `governance_dev/amendments/2026-05-09--demo_promotion_evidence_push.md` | AMD-2026-05-09-04 Demo->LivePending promotion_evidence producer + V079 schema + QC push back 採納 |
| `governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md` | AMD-2026-05-09-03 Graduated Canary default-OFF（ARCH-04 配套 default gate） |
| `governance_dev/amendments/2026-05-10--AMD-2026-05-10-05-canary-stage-criteria-spec.md` | AMD-2026-05-10-05 canary stage criteria spec (Stage 1-4 promotion/demote criteria + sample-size gate) |
| `governance_dev/amendments/2026-05-11--AMD-2026-05-11-W6-1-rfc-final-verdict-absorb.md` | AMD-2026-05-11-W6-1 RFC final verdict absorb (W6 governance metadata + duplicate_intent bug + imbalance weight) |
| `governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md` | AMD-2026-05-15-02 EDGE-P2-3 Phase 1b Close-Maker-First refactor (fee optimization pathway + 3-phase灰度 + V094 schema) |
| `governance_dev/SPECIFICATION_REGISTER.md` | SM/EX/DOC/REF/ARCH/AUDIT/LG-X/OPS-X specification register, updated through W-AUDIT-1 + LG-X-05 catch-up |
| `governance_dev/2026-05-11--w_c_window_pass_signoff.md` | W-C MAG-082 Stage 2 WINDOW_PASS sign-off (2026-05-11) |
| `governance_dev/2026-05-11--w_d_mag083_reviewer_brief.md` | W-D MAG-083 reviewer brief |
| `governance_dev/2026-05-11--w_d_mag084_signoff.md` | W-D MAG-084 operator sign-off |
| `governance_dev/2026-05-11--w2_impl_signoff_pack.md` | W2 A4-C IMPL sign-off pack |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-09--w_audit_3_partial_f15_f17_sm05.md` | PM sign-off report for W-AUDIT-3 partial F-15/F-17/SM-05 checkpoint |
| `CCAgentWorkSpace/Operator/2026-05-09--w_audit_3_partial_f15_f17_sm05.md` | Operator-facing copy of W-AUDIT-3 partial checkpoint report |
| `adr/0001-rust-as-trading-authority.md` | ADR-0001: Rust 為唯一交易參數權威 |
| `adr/0002-three-mode-engine-independent-risk-configs.md` | ADR-0002: 三引擎模式獨立風控 config |
| `adr/0003-paper-pipeline-disabled-by-default.md` | ADR-0003: Paper pipeline 預設關閉 |
| `adr/0004-livedemo-no-degradation.md` | ADR-0004: LiveDemo 不因 endpoint 降級 |
| `adr/0005-engine-mode-tag-live-demo.md` | ADR-0005: engine_mode 標籤 live_demo 升級 |
| `adr/0006-bybit-only-exchange.md` | ADR-0006: Bybit 為唯一交易所 |
| `adr/0007-mac-dev-linux-runtime-split.md` | ADR-0007: Mac=開發 / Linux=Runtime |
| `adr/0008-decision-lease-state-machine.md` | ADR-0008: Decision Lease 狀態機 |
| `adr/0009-hot-config-arcswap-no-restart.md` | ADR-0009: ArcSwap 熱重載無需重啟 |
| `adr/0010-timescale-hypertable-with-guard-migrations.md` | ADR-0010: TimescaleDB hypertable + Guard migration |
| `adr/0011-v-migration-linux-pg-dry-run-mandatory.md` | ADR-0011: V### migration Linux PG dry-run 強制 |
| `adr/0012-chinese-only-comments-default.md` | ADR-0012: 注釋默認只寫中文 |
| `adr/0013-openclaw-gateway-not-trading-conductor.md` | ADR-0013: OpenClaw Gateway 非交易指揮 |
| `adr/0014-arcane-equilibrium-soft-rename.md` | ADR-0014: 玄衡 Arcane Equilibrium 軟更名 |
| `adr/0015-openclaw-control-plane-repositioning.md` | ADR-0015: OpenClaw is Control Plane/Gateway, not trading conductor |
| `adr/0016-decision-lease-router-evidence-mode.md` | ADR-0016: Decision Lease router flag may run as shadow evidence |
| `adr/0017-scanner-is-evidence-not-authority.md` | ADR-0017: scanner is always-on evidence infrastructure, not authority |
| `adr/0018-funding-arb-v2-deprecation-watch.md` | ADR-0018: funding_arb V2 retired from active strategy set; W-AUDIT-6 cleanup pending |
| `adr/0019-github-issues-active-tracker.md` | ADR-0019: GitHub Issues active external tracker; git remains SoT |
| `adr/0020-layer2-manual-supervisor-only.md` | ADR-0020: Layer2 is manual supervisor escalation, not autonomous loop |
| `architecture/2026-05-06--openclaw_control_plane_repositioning.md` | ARCH-02: OpenClaw control-plane repositioning |
| `architecture/multi_agent_rework_2026-05-05/ENGINEERING_PLAN.md` | ARCH-03 parent: Agent Decision Spine engineering plan |
| `architecture/multi_agent_rework_2026-05-05/AgentTodo.md` | Historical AgentTodo milestone board for MAG-010..084 |
| `architecture/multi_agent_rework_2026-05-05/2026-05-06--mag015_sprint_a_contract_addendum.md` | MAG-015 Sprint A contract addendum |
| `architecture/multi_agent_rework_2026-05-05/2026-05-06--mag020_scanner_authority_modes.md` | MAG-020 historical scanner authority-mode contract, superseded by ADR-0017 boundary |
| `architecture/multi_agent_rework_2026-05-05/2026-05-07--mag030_agent_spine_rust_module_design.md` | MAG-030 Agent Spine Rust module design |
| `architecture/multi_agent_rework_2026-05-05/2026-05-07--mag034_idempotency_double_execution_audit.md` | MAG-034 idempotency / double execution audit |
| `architecture/multi_agent_rework_2026-05-05/2026-05-07--mag040_strategist_v2_matching_model.md` | MAG-040 Strategist V2 matching model |
| `architecture/multi_agent_rework_2026-05-05/2026-05-07--mag050_guardian_v2_risk_metrics_model.md` | MAG-050 Guardian V2 risk metrics model |
| `architecture/multi_agent_rework_2026-05-05/2026-05-07--mag060_execution_plan_interface.md` | MAG-060 ExecutionPlan interface and order styles |
| `architecture/multi_agent_rework_2026-05-05/2026-05-07--mag070_analyst_insight_l1_l2_l3_schema.md` | MAG-070 AnalystInsight L1/L2/L3 schema |
| `architecture/multi_agent_rework_2026-05-05/2026-05-07--mag080_cutover_policy.md` | MAG-080 shadow -> canary -> primary cutover policy |
| `architecture/multi_agent_rework_2026-05-05/2026-05-07--mag081_canary_flag_runtime_risk_review.md` | MAG-081 canary flag runtime risk review |
| `architecture/multi_agent_rework_2026-05-05/2026-05-07--mag082_24h_canary_validation_checklist.md` | MAG-082 24h canary validation checklist |
| `architecture/multi_agent_rework_2026-05-05/2026-05-07--mag083_final_release_audit_blocked.md` | MAG-083 final release audit blocked report |
| `architecture/multi_agent_rework_2026-05-05/2026-05-07--mag084_operator_signoff_blocked.md` | MAG-084 operator sign-off blocked report |
| `CCAgentWorkSpace/FA/workspace/reports/2026-05-08--full_chain_functional_audit.md` | 12-agent audit input: FA functional audit |
| `CCAgentWorkSpace/AI-E/workspace/reports/2026-05-08--ai_effectiveness_full_audit.md` | 12-agent audit input: AI effectiveness audit |
| `CCAgentWorkSpace/E5/workspace/reports/2026-05-08--full_chain_optimization_audit.md` | 12-agent audit input: optimization / structure audit |
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-08--full_chain_test_audit.md` | 12-agent audit input: test audit |
| `CCAgentWorkSpace/E3/workspace/reports/2026-05-08--full_chain_security_audit.md` | 12-agent audit input: security audit |
| `CCAgentWorkSpace/CC/workspace/reports/2026-05-08--project_compliance_audit.md` | 12-agent audit input: compliance audit |
| `CCAgentWorkSpace/QC/workspace/reports/2026-05-08--strategy_risk_math_audit.md` | 12-agent audit input: quant / strategy audit |
| `CCAgentWorkSpace/MIT/workspace/reports/2026-05-08--db_ml_foundation_audit.md` | 12-agent audit input: DB / ML foundation audit |
| `CCAgentWorkSpace/MIT/README.md` | MIT workspace orientation and current report pointer |
| `CCAgentWorkSpace/BB/workspace/reports/2026-05-08--bybit_api_compatibility_audit.md` | 12-agent audit input: Bybit compatibility audit |
| `CCAgentWorkSpace/BB/README.md` | BB workspace orientation and current report pointer |
| `CCAgentWorkSpace/TW/workspace/reports/2026-05-08--apr_may_doc_audit.md` | 12-agent audit input: TW documentation audit |
| `CCAgentWorkSpace/R4/workspace/reports/2026-05-08--index_completeness_audit.md` | 12-agent audit input: R4 index completeness audit |
| `CCAgentWorkSpace/A3/workspace/reports/2026-05-08--gui_ux_full_audit.md` | 12-agent audit input: GUI/UX audit |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-08--full_audit_pa_fix_plan.md` | PA de-duped full audit fix plan |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-08--mattpocock_skills_setup.md` | PM report: mattpocock skills setup and GitHub Issues posture |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-09--w_audit_1_docs_governance_sync.md` | PM report: W-AUDIT-1 docs/governance sync closure |
| `CCAgentWorkSpace/Operator/2026-05-09--w_audit_1_docs_governance_sync.md` | Operator-facing W-AUDIT-1 completion note |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-07--agenttodo_mag080_cutover_policy.md` | PM report: MAG-080 cutover policy |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-07--agenttodo_mag081_canary_flag_runtime_risk_review.md` | PM report: MAG-081 flag risk review |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-07--agenttodo_mag082_24h_canary_validation_checklist.md` | PM report: MAG-082 validation checklist |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-07--agenttodo_mag083_final_release_audit_blocked.md` | PM report: MAG-083 blocked pre-audit |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-07--agenttodo_mag084_operator_signoff_blocked.md` | PM report: MAG-084 blocked sign-off |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-07--agenttodo_m8_stage2_fast_track_no_go.md` | PM report: M8 fast-track NO-GO |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-07--todo_v13_agent_openclaw_replan.md` | PM report: TODO v13 Agent/OpenClaw replan, superseded by TODO v14 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-07--p1_healthcheck_fail_queue_and_executor_fake_live_fix.md` | PM report: P1 healthcheck FAIL queue and executor fake-live source fix |
| `../helper_scripts/SCRIPT_INDEX.md` | helper_scripts 維護/啟動/CI/DB/audit/cron/operator/research 腳本索引 |

### docs/agents/ — GitHub Issues / Agent triage guidance

| 文件 | 内容 |
|------|------|
| `agents/domain.md` | Agent domain ownership and routing rules for issue triage |
| `agents/issue-tracker.md` | GitHub Issues operating model after the 2026-05-08 tracker decision |
| `agents/triage-labels.md` | Triage labels and severity/status conventions for Agent work |

### _indexes/ — 文档 inventory / redirect map / GUI metadata（2026-05-06+）

| 文件 | 内容 |
|------|------|
| `document_inventory.json` | R4 文档信息架构盘点结果：当前 cluster counts、目标 taxonomy、GUI 热交互候选、分阶段执行计划 |
| `path_redirects.md` | 文档重命名/搬迁 redirect plan；当前仅规划，不代表文件已移动 |

### worklogs/chapters_a-g/ — A-G 章节工作日志（2026-03-11 ~ 2026-03-19）

| 文件 | 内容 |
|------|------|
| `2026-03-11--openclaw_bybit_进度日志.txt` | 03-11 项目启动，基础层搭建进度 |
| `2026-03-12--openclaw_bybit_进度日志.txt` | 03-12 继续基础层开发 |
| `2026-03-13--详细工作日志.txt` | 03-13 详细工作记录 |
| `2026-03-13--三日补充综合日志.txt` | 03-11~13 三日补充综合回顾 |
| `2026-03-17--chapter_g_工程记录.txt` | G 章工程记录（Revision 2） |
| `2026-03-17--chapter_g_执行清单.txt` | G 章执行清单（Revision 2） |
| `2026-03-17--engineering_log.txt` | 03-17 工程日志 |
| `2026-03-19--补充记录1.txt` | 03-19 补充记录 |
| `2026-03-19--当前进度图_校正后.txt` | 进度图校正版 |
| `2026-03-19--工作记录_含0317至0319校正与修复.txt` | 03-17~19 校正与修复工作记录 |
| `2026-03-19--完整版当前进度图.txt` | 完整版进度图（校正后） |

### worklogs/chapters_h-i/ — H-I 章节工作日志（2026-03-20 ~ 2026-03-22）

| 文件 | 内容 |
|------|------|
| `2026-03-20--openclaw_工作记录.txt` | 03-20 H-I 章节开始 |
| `2026-03-20--超详细续接总报告.txt` | 超详细续接总报告 |
| `2026-03-20--h0_本地判断核心蓝图_v1.txt` | H0 本地判断核心蓝图 v1 |
| `2026-03-20--h_i_本地执行内核讨论备份.txt` | H-I 本地执行内核讨论备份 |
| `2026-03-22--0320工作报告_新对话接手版.txt` | 03-20 工作报告（供新对话接手） |
| `2026-03-22--a-i_接手摘要.txt` | A-I 全量接手摘要 |
| `2026-03-22--h_i_正式完工对账报告.txt` | H-I 正式完工对账报告 |
| `2026-03-22--h_i_兼容性对账清单.txt` | H-I 兼容性对账清单（新对话首步验证） |
| `2026-03-22--全量整合总报告.txt` | 全量整合总报告 |
| `2026-03-22--全量整合总报告_重新导出.txt` | 全量整合总报告（重新导出版） |
| `2026-03-22--晚_工程记录.txt` | 03-22 晚间工程记录（Fix H-I） |
| `2026-03-22--晚_新对话接手指示.txt` | 新对话接手指示 |
| `2026-03-22--晚_新对话接手prompt.txt` | 新对话接手 Prompt |
| `2026-03-22--晚_h1_no_call_semantics_patch.txt` | H1 no-call 语义补丁 bundle |

### worklogs/chapters_j-k/ — J-K 章节 + GitHub 迁移（2026-03-22 ~ 2026-03-24）

| 文件 | 内容 |
|------|------|
| `2026-03-22--项目总报告_含github核对.md` | 项目总报告（含 GitHub 核对） |
| `2026-03-22--夜间_最终整合总报告.txt` | 夜间最终整合总报告 |
| `2026-03-22--夜间_github迁移与诊断报告.txt` | GitHub 迁移与夜间诊断报告 |
| `2026-03-22--夜间_新对话接手prompt_github版.txt` | 新对话接手 Prompt（GitHub 工作流版） |
| `2026-03-24--工程总报告_结构迁移完成.txt` | 工程总报告：结构迁移完成 + 新工作流 |
| `2026-03-24--交接日志.txt` | 03-24 晚交接日志 |
| `2026-03-24--新对话启动prompt.txt` | 新对话启动 Prompt |
| `2026-03-24--work_report_current_dialogue.md` | 当前对话工作报告 |

### worklogs/control_api_gui/ — Control API + GUI 开发日志（2026-03-25 ~ 2026-04-02）

| 文件 | 内容 |
|------|------|
| `2026-03-25--jk收口_单独接手文件.txt` | J-K 收口完成版接手文件 |
| `2026-03-25--jk收口_完整工程记录.txt` | J-K 收口完成版完整工程记录 |
| `2026-03-25--g到k详细复盘与程序总表.txt` | G~K 详细复盘与程序总表 |
| `2026-03-25--新对话工作方式与带入文件清单.txt` | 新对话工作方式与带入文件清单 |
| `2026-03-25--新对话启动prompt.txt` | 新对话启动 Prompt |
| `2026-03-26--api_gui_全量工程报告.md` | API + GUI 全量工程报告 |
| `2026-03-26--paper_trading_engine_完整工程日志.md` | Paper Trading Engine 完整工程日志（引擎核心 + 14 路由 + GUI + 43 测试） |
| `2026-03-26--beta_pipeline_shadow_decision_metrics.md` | Beta 管线完善：实时行情 + 自动桥接 + 影子决策管线 + 性能指标（248 测试，73 路由） |
| `2026-03-26--brainstorm_openclaw_agent_architecture.md` | Brainstorm 留档：OpenClaw 定位（通信层非大脑）+ Agent 智能化架构讨论 |
| `2026-03-26--openclaw_fusion_console_systemd_服务化.md` | OpenClaw 融合 + 统一控制台 + systemd 服务化 + 远程访问方案规划 |
| `2026-03-26--brainstorm_layer2_ai_reasoning_engine.md` | Brainstorm：Layer 2 AI 推理引擎设计（三层架构 + Agent 循环 + 工具箱 + 成本控制） |
| `2026-03-27--layer2_ai_engine_design_session.md` | Layer 2 设计工作记录：搜索 Provider 方案调研决策 + 4 层降级体系 + 模型升级判断 + 自适应预算 + PnL 归因 |
| `2026-03-27--phase1_risk_framework_implementation.md` | Phase 1 早期工程日志：S1-S5 安全修复 + 三层 P0/P1/P2 风控 + 8 路由（327→369） |
| `2026-03-27--phase1_complete_engineering_log.md` | Phase 1 中期工程日志（第 1-2 轮审核后） |
| `2026-03-27--phase1_final_audited_engineering_log.md` | ★ Phase 1 最终审核版：4 轮审核 + 25 问题修复 + 405 测试 + 93 路由 |
| `2026-03-27--pre_phase1_audit_fixes.md` | Pre-Phase1 代码审核：metrics 完全重写 + SSRF 防护 + 成本追踪 race fix + adaptive 强制执行 |
| `2026-03-27--phase2_local_strategy_toolkit_engineering_log.md` | ★ Phase 2 完整工程日志：K线管理器 + 6 指标 + 信号生成器 + 4 策略 + 编排器 + 11 路由 + 严格审核修复（620 测试） |
| `2026-03-27--phase3_pipeline_bridge_engineering_log.md` | Phase 3 工程日志：管线桥接器 + 止损管理器 + 信号增强 + 策略增强（640 测试） |
| `2026-03-27--full_system_audit_fix_engineering_log.md` | ★ 全系统审核修复工程日志：7C+19H+28M+16L + 路径统一 + I章去重 + mutator 3x→1x |
| `2026-03-27--roadmap_B_to_I_engineering_log.md` | ★ 路线图 B-I 实现：cron+加权共识+volume+Grid几何+多TF+tick防护+持久化+Delta-Neutral套利（641测试） |
| `2026-03-27--full_day_session_summary.md` | ★★ 完整工作日总结：13 commits + 644 测试 + 20 新文件 + GUI 待做清单 |
| `2026-03-27--gui_three_layer_implementation.md` | GUI 三层架构：Grafana + TradingView + Bybit Demo + 登录系统 + 统一控制台 |
| `2026-03-27--autonomous_agent_scanner_deployer.md` | ★ 自主交易 Agent：市场扫描器 650 符号 + 策略自动部署 + Demo 同步 + 登录系统 |
| `2026-03-27--session2_audit_fix_and_agent_autonomy.md` | Session 2 总结：GUI三层 + Demo + 自主Agent + R1-R5修复 + 第4轮审核7C+10H |
| `2026-03-27--session3_remaining_audit_fixes.md` | Session 3：残留审核全修（时间戳6处+浮点容差+TIF执行+Kahan求和+401刷屏+volume动态+测试修复=646测试） |
| `2026-03-27--gui_10tab_restructure.md` | ★ GUI 10-Tab 全面重构：common.js+8新Tab+双层解释+三层信息密度+99 API端点覆盖 |
| `2026-03-27--session4_gui_10tab_professional_console.md` | ★★ Session 4 完整日志：6 commits+17 files+3964 行+多供应商AI+可编辑风控+中文状态+确认弹窗 |
| `2026-03-27--remote_access_and_security_hardening.md` | 远程访问配置 + 安全加固：Tailscale + secrets 权限 + API key 硬编码消除 |
| `2026-03-27--session5_pipeline_launch_and_openclaw_analysis.md` | Session 5：管线启动验证 + OpenClaw 能力深挖 + systemd 自动重启确认 + Paper Trading 169 单 |
| `2026-03-28--session6_halfday_data_analysis_and_fixes.md` | ★ Session 6：半天数据分析（胜率0%根因）+ 4项修复（扫描器过滤+置信度0.55+.orig stub+3张DB表） |
| `2026-03-28--session7_system_audit_and_fixes.md` | ★★ Session 7：系统全面审核（8模块/12问题）+ 5项修复（市场流自动重启+unknown regime保护+trend cap+时间驱动+confidence对齐），646 测试通过 |
| `2026-03-28--session8_functional_audit_report.md` | ★★★ Session 8：A-J 全面功能审核（25h/684fill/胜率0%）+ E1/G1/H1 三项修复（自动学习/连续亏损暂停/ATR止损接入），428 测试通过 |
| `2026-03-28--session9_bug_fixes_and_verification.md` | ★★ Session 9：3项 bug 修复（net_realized_pnl字段/active_count+1/on_fill仓位同步链路）+ 18个验证测试，664 测试通过 |
| `2026-03-28--session10_ai_cost_and_double_stop_fix.md` | ★★ Session 10：2项修复（total_ai_cost汇总/双重止损防护）+ 7个验证测试，664 测试通过 |
| `2026-03-28--session11_regime_aware_stops.md` | ★★★ Session 11：regime感知止损/止盈/时间三维调整（REGIME_STOP/TP/TIME_MULTIPLIERS）+ 8个验证测试，33+428 测试通过 |
| `2026-03-29--session12_data_analysis_and_bug_fixes.md` | ★★★ Session 12：数据分析发现 0% 胜率根因（fill碎片化+注意力税误关仓），修复 F1/F2/E1a/E1b + GUI G1-G6（活跃订单/价格精度/Demo对比/学习系统），432 测试通过 |
| `2026-03-31--gui_tab_restructure_ollama_optimization.md` | ★★ GUI Tab 重构（Paper+Demo合并+实盘占位）+ Ollama 优化（9B/27B分配+think=False 4x提速+edge filter修复）+ 后台市场流常驻 + 周报时间表调整 |
| `2026-03-31--position_sizing_dynamic_qty_rebalancer.md` | ★★ Position Sizing 重構：3% risk/trade + 25 symbols + 動態 qty（每單重算）+ 智能資本再分配（弱倉自動平倉讓位新機會）|
| `2026-03-31--wave4_p2p3_security_audit_fixes.md` | ★★ Wave 4 P2/P3 批次：5 Sprint · P2-NEW-1~9 + FA-2/3/4 + P3-TECH-1~3（安全補齊 + 端點矩陣完整覆蓋 + NaN/inf 邊界值 + event loop 阻塞修復），2555 tests |
| `2026-03-31--paper_demo_sync_fixes.md` | ★★★ Paper/Demo 同步修復：10 項分歧根源分析 · 3 CRITICAL 修復（止損同步+失敗標記+對賬參數名）· qty 統一四捨五入 · 對賬引擎首次真正運行 |
| `2026-03-31--full_day_complete_engineering_log.md` | ★★★★ 2026-03-31 全天完整工程日誌（整合版）：7-Agent 全系統審計 · P0 CRITICAL×4 修復 · Wave 0-3 全系列 · H0 Gate Day 1-3 · Wave 4 Sprint 4a-4e · Wave 5a Position Sizing + 5b Paper/Demo 同步 · Wave 5 Sprint H鏈接通 · Wave 6 Sprint 0+1a+1b+2 + Cleanup · Phase 2 Batch 2A+2B，2624 tests |
| `2026-04-01--phase2_batch2c_completion.md` | ★★★ Phase 2 Batch 2C 完成：接通 _register_pattern_claims 雙路徑 + backtest_routes.py API + 決策權重集成 · Git 分歧解決（rebase）· 3103 tests |
| `2026-04-01--wave7_demo_sync_spot_category_pinned.md` | ★★★ Wave 7：Paper 內部平倉 Demo 同步 + stop_session 自動清倉 + Spot 品類全鏈路（Scanner+策略+Position）+ demo_reserved 解鎖 + GUI 品類標籤 + BTC/ETH 釘選幣種 |
| `2026-04-01--wave7a_spot_symbol_category.md` | ★★★ Wave 7a Spot 品類啟用 + 方案 A/B symbol-category 映射：SPOT-1~5 全通 + _symbol_category_map 雙向注入 + SymbolCategoryRegistry 啟動填充，3103→3161 tests |
| `2026-04-01--phase3_full_completion_and_wave7b.md` | ★★★★ Wave 7b Inverse 品類（INV-1~5）+ Phase 3 全完成（3A ExperimentLedger/Routes/EvolutionEngine + 3B TruthSourceRegistry持久化/AnalystAgent觀測/auto_seed + 3C EvolutionScheduler週進化/小時清理/GUI dashboard）· 3103→3330 tests |
| `2026-04-01--governance_auth_restart_fix_and_order_unblock.md` | ★★ GovernanceHub 重啟後授權丟失根因診斷與修復：5 層診斷（state.json→audit→bridge stats→auth NONE）· get_status() auth_pending_approval 修復 · /session/reauth 端點 · startup 自動補授 · 首筆 FARTCOINUSDT 訂單解封成交 |
| `2026-04-01--main_legacy_refactor_wave_a_to_e.md` | ★★★★ main_legacy.py 重構全記錄：5265→407 行（-92%），Wave A-E 共拆出 11 模塊，monkey-patch 延遲查找修復，E5 審查 build_review_queue bug 修復，§14 約定建立，3005 tests 零回歸 |
| `2026-04-01--wave8_pa_reality_check_and_parallel_fix.md` | ★★★★ Wave 8 工作日誌：PA 69 項實況檢查 + 6 軌道×2 批並行修復 38/39 項 + strategist 拆分 + on_tick/mutator 拆分 + now_ms 統一 + +148 測試 |
| `2026-04-02--batch9a_deterministic_adaptive_risk.md` | ★★★ Batch 9A 確定性自適應風控：QC 量化審查驅動 · ATR 雙窗口 + 成本感知入場門檻 + 追蹤止損成本約束 + round-trip 真實費用 · 修復 ATR 止損死代碼 bug · +66 測試 · 3703 passed |

### worklogs/phase5_arch_rc1/ — Phase 5 / L3 整改 / ARCH-RC1 開發日誌（2026-04-03 ~ 2026-04-07）

| 文件 | 内容 |
|------|------|
| `2026-04-03--daily_summary.md` | ★★★★ 2026-04-03 日匯總（12 Sessions · 28 Commits）：文檔治理 + Phase 0-3 全覽 + Rust R-00~R-04 |
| `2026-04-04--daily_summary.md` | ★★★★ 2026-04-04 日匯總：V2 策略功能全面啟用（P0 緊急修復）+ Bybit API 基礎設施 |
| `2026-04-04--td01_td02_td03_file_split.md` | Session 3：TD-01/02/03 Python 大文件拆分（Phase 1 前置技術債清零） |
| `2026-04-04--session4_bybit_api_audit.md` | ★★★ Session 4：BB+E5+PA 三角色聯合審計 Bybit V5 API 層 + 完整 API 字典手冊 |
| `2026-04-04--session5_bybit_full_integration.md` | ★★★ Session 5：9 項 API 整合改進 + 3 新模組 + Demo→Live 對齊（PM+PA+FA+BB 四角色） |
| `2026-04-05--daily_summary.md` | ★★★★ 2026-04-05 日匯總（3 Sessions）：Phase 1 Full Rust 數據管線（G1-G4）+ Phase 2/3a/3b ML 基礎設施 + EXT-1 Exchange-as-Truth + RRC-1 設計 + 風控 GUI 補齊 + Demo 架構完成 |
| `2026-04-06--daily_summary.md` | ★★★★ 2026-04-06 日匯總：L3 整改 R0/R1/R2 + Drift Detector 接線 + Phase 4 啟動 |
| `2026-04-06--session10_r0_r1_remediation.md` | ★★★ Session 10：L3 414 findings → 63 tracker + R0 Week 1（7 P0 修復）+ R1 Wave 1（WP-B Security + WP-MIT DB/ML + idle writer） |
| `2026-04-06--session11_p1_6_drift_detector.md` | Session 11：WP-MIT P1-6 drift_detector PG 接線（fetch_active_baselines / DriftMonitorState / PSI 滑動窗口） |
| `2026-04-06--session11_r2_batch.md` | ★★★ Session 11：R1 收尾 + R2 批次（多項 L3 整改繼續推進） |
| `2026-04-06--session11_precompact.md` | Session 11 Pre-Compact 快照：453 engine + 411 core + 35 ml_training · 0 failures |
| `2026-04-06--session12_precompact.md` | Session 12 Pre-Compact 快照：474 engine + 413 core + 35 ml_training · 0 failures |
| `2026-04-06--session13_precompact.md` | ★★★★ Session 13：I-22 event_consumer 拆分 + FA-GAP-2/4 接線（cost_ratio/Kelly ATR%）+ per-symbol 真實費率 + SEC-11 fail-closed + FA-GAP-8/9 dead code 清除 |
| `2026-04-06--session_progress_2.md` | Session 進度快照（Session 2）|
| `2026-04-07--daily_summary.md` | ★★★★ 2026-04-07 日匯總：Phase 4 完成 + ARCH-RC1 1A/1B/1C-1/1C-2 |
| `2026-04-07--session_arch_rc1_1a_1b.md` | ARCH-RC1 1A + 1B：ConfigStore 單一寫入口 + StrategyParams JSON 接線 |
| `2026-04-07--session_arch_rc1_1c1_1c2.md` | ARCH-RC1 1C-1 + 1C-2：IPC patch 接線 + hot-reload ArcSwap |
| `2026-04-07--session_arch_rc1_1c2_complete.md` | ARCH-RC1 1C-2 完成：IPC 全鏈路驗收 |
| `2026-04-07--session_phase4_1_complete.md` | Phase 4-1 完成日誌 |
| `2026-04-07--session_phase4_complete.md` | Phase 4 全量完成日誌 |

### worklogs/ — 頂層工作日志（2026-04-08+，daily_summary 為當日權威）

| 文件 | 内容 |
|------|------|
| `2026-04-08--daily_summary.md` | ★★★★ 2026-04-08 日匯總：ARCH-RC1 1C-3-D/1C-3-E F-mini/1C-3-F/1C-4 + GUI fake-success Wave 1-2 + P1 Per-Trade Risk wiring |
| `2026-04-09--daily_summary.md` | ★★★★ 2026-04-09 日匯總：StrategyAction Enum（策略出場死鎖修復）+ Rust 市場掃描器 Phase A-D + QC/FA 全修 · 830 tests |
| `2026-04-10--daily_summary.md` | ★★★★ 2026-04-10 日匯總：ML Pipeline Remediation + Signal Diamond Phase 1-4 + Fix Round + Live GUI P0-P6 + Phase 6 Reconciler 自動降級 + W19/W20 安全治理 · 850 tests |
| `2026-04-11--daily_summary.md` | ★★★★ 2026-04-11 日匯總：3E-ARCH 三引擎並行 + Multi-Symbol + Fix Rounds Phase A-G |
| `2026-04-12--daily_summary.md` | ★★★★ 2026-04-12 日匯總：全程序鏈審計 P0+P1+P2+P3 58 findings + A3 GUI 36 + BB Bybit API 10 + FIX-08 拆分 + Earned-Trust TTL Ladder + PNL-FIX-1/2 · 4250 tests |
| `2026-04-13--daily_summary.md` | ★★★ 2026-04-13 日匯總：R-06-v2 Agent Value Delivery（Executor shadow IPC / Analyst→DB→Strategist feedback / Guardian rejection / Conductor real health）· 1124 Rust + 2852 Python |
| `2026-04-14--engine_self_healing.md` | ENGINE-HEAL 4 Fix：panic hook + crash-only + WS stale self-cancel + watchdog 4 道保險（尚未合併至 daily_summary）|
| `2026-04-14--qol_1_and_qol_3_delivery.md` | QoL-1（paper_state restore_from_db）+ QoL-3（PyO3 雙 venv 部署）交付（尚未合併至 daily_summary）|
| `2026-04-27--live_auth_watcher_event_consumer_spawn_fix.md` | ★★ P0 Silent Regression：LiveAuthWatcher respawn 路徑遺漏 `spawn_live_pipeline` → event_consumer 8 天未 spawn（2252 tests）· commits 588d207 / 0fa41b1 / merge 1fac9b1 |

> 2026-04-14 worklog audit：所有舊碎片已合併至當日 `daily_summary.md` 並刪除；`2026-04-08--arch_rc1_1c_history_archive.md` 已移至 `docs/archive/`。

### worklogs/learning/ — L 章学习系统开发日志（2026-03-26）

| 文件 | 内容 |
|------|------|
| `2026-03-26--L章_自动学习管线与安全加固_完整工程日志.md` | L 章自动学习管线 + 安全加固全量工程日志（含审核包设计、96 测试、8 项安全修复） |

### handoffs/ — 阶段交接文档

| 路径 | 内容 |
|------|------|
| `2026-03-25_api_gui_handoff/` | Control API v1 + GUI v1 阶段交接（含 12 份文档 + source_docs） |

### decisions/ — 架构/设计决策记录 + 治理源文件

| 文件 | 内容 |
|------|------|
| `2026-04-01--symbol_category_mapping_design.md` | Symbol→Category 映射策略決策：方案 B 運行時映射（短期）+ 方案 A SymbolCategoryRegistry 批量填充（長期），雙層架構設計 |
| `2026-03-17--工程一审修改建议报告_终稿.md` | Revision 2 工程一审修改建议报告（md 终稿） |
| `2026-03-17--工程一审修改建议报告_终稿.txt` | Revision 2 工程一审修改建议报告（txt 终稿） |
| `2026-03-20--关于h和i部分的核心设计讨论.txt` | H-I 核心设计讨论（AI 成本均衡 / 本地计算 / 延迟框架 / 设备容错） |
| **治理源文件（.docx，Operator 原始治理规格）** | |
| `DOC-NAV_...治理文件导航_V3.docx` | 治理文件导航 V3（13 份文件总入口） |
| `DOC-01_...项目宪法与根原则_V2.docx` | 项目宪法：16 条根原则（§5.1–§5.16） |
| `DOC-02_...边界定义_V2.docx` | 系统边界定义（H0 <1ms SLA、执行权限、数据平面） |
| `DOC-03_...字段级与状态级规范_V1.1.docx` | 字段级与状态级规范 |
| `DOC-04_...Agent能力蓝图_V2.docx` | Agent 能力蓝图（A-J 十大能力目标） |
| `DOC-05_...真相源与所有权矩阵_V1.1.docx` | 真相源与所有权矩阵 |
| `DOC-06_...变更治理_V2.docx` | 变更治理流程 |
| `DOC-07_...审计事故与熔断政策_V1.1.docx` | 审计/事故/熔断政策 |
| `DOC-08_...实施桥梁_V1.docx` | 实施桥梁（AI 成本上限 $2/天、provider 配置） |
| `SM-01_...授权状态机规范_V1.docx` | SM-01 授权状态机规范 |
| `SM-02_...决策租约状态机规范_V1.docx` | SM-02 决策租约状态机规范 |
| `SM-03_...执行状态机规范_V1.1.docx` | SM-03 OMS 执行状态机规范 |
| `SM-04_...风控状态机规范_V1.docx` | SM-04 风控状态机规范 |
| `EX-01_...风控边界定义_V2.docx` | 风控边界定义 |
| `EX-02_...OMS与执行正式边界定义_V1.docx` | OMS 与执行正式边界定义 |
| `EX-03_...控制平面正式边界定义_V1.docx` | 控制平面正式边界定义 |
| `EX-04_...对账正式边界定义_V1.docx` | 对账正式边界定义 |
| `EX-05_...学习边界定义_V2.docx` | 学习边界定义 |
| `EX-06_...多Agent编排正式边界定义_V1.docx` | 多 Agent 编排正式边界定义 |
| `EX-07_...感知平面正式边界定义_V1.docx` | 感知/数据平面正式边界定义 |
| `HIST-01_...核心设计总纲_V1.docx` | 历史参考：核心设计总纲 |
| `HIST-02_...治理设计交付包_V1.docx` | 历史参考：治理设计交付包 |

### CCAgentWorkSpace（各 Agent workspace/reports）— ★★★ 2026-03-31 七Agent全系统审计

| Agent | 文件（CCAgentWorkSpace/<Agent>/workspace/reports/） | 内容 |
|-------|------|------|
| E3 | `2026-03-31--e3_security_audit.md` | E3 安全审计：3 CRITICAL / 5 HIGH / 6 MEDIUM / 5 LOW |
| CC | `2026-03-31--cc_compliance_check.md` | CC 合规检查：11/16 原则完全合规，B 级 |
| E4 | `2026-03-31--e4_testing_report.md` | E4 测试评估：71 文件/2480 用例 |
| E5 | `2026-03-31--e5_optimization_report.md` | E5 优化评估：49 项 |
| A3 | `2026-03-31--a3_gui_usability_report.md` | A3 GUI 可用性：6.2/10 |
| PM | `2026-03-31--pm_review.md` | ★ PM 整合审核：71 项去重，~110h 工时 |
| PA | `2026-03-31--pa_review.md` | ★ PA 技术复验：4 CRITICAL 确认属实 |

双语注释审计：`audits/2026-03-30--bilingual_comment_audit_report.md`

### CCAgentWorkSpace（各 Agent workspace/reports）— ★★★ 2026-04-01 十Agent全系统审计

| Agent | 文件（CCAgentWorkSpace/<Agent>/workspace/reports/） | 内容 |
|-------|------|------|
| AI-E | `2026-04-01--ai_effectiveness_audit.md` | AI-E AI 效果审计 |
| CC | `2026-04-01--compliance_check.md` | CC 合规检查：16 条根原则逐一验证 |
| E3 | `2026-04-01--security_audit.md` | E3 安全审计 |
| E4 | `2026-04-01--testing_audit.md` | E4 测试评估 |
| E5 | `2026-04-01--optimization_audit.md` | E5 优化评估 |
| FA | `2026-04-01--functional_gap_audit.md` | FA 功能缺口审计 |
| TW | `2026-04-01--documentation_quality_audit.md` | TW 文档品质审计 |
| R4 | `2026-04-01--document_index_audit.md` | R4 文档索引审计 |
| Operator | `2026-04-01--pa_review.md` | PA 技术复验 |
| Operator | `2026-04-01--pm_execution_plan.md` | PM 执行计划 |

### audits/2026-04-05--l3_comprehensive/ — L3 全系统综合审计（2026-04-05，12 角色专项报告）

注：这批审计文件是 2026-04-05 L3 审计轮次产出，因当时未遵守命名规范（无日期前缀），现统一归入此子目录。

| 文件 | 内容 |
|------|------|
| `audit_A3_gui_usability_report.md` | A3 GUI 可用性审计报告 |
| `audit_AIE_effectiveness_report.md` | AI-E AI 效果评估报告 |
| `audit_BB_bybit_api_report.md` | BB Bybit API 专项审计报告 |
| `audit_CC_compliance_report.md` | CC 合规审计报告 |
| `audit_E3_security_report.md` | E3 安全审计报告 |
| `audit_E4_test_coverage_report.md` | E4 测试覆盖报告 |
| `audit_E5_optimization_report.md` | E5 优化评估报告 |
| `audit_FA_functional_spec_report.md` | FA 功能规格审计报告 |
| `audit_MIT_database_ml_report.md` | MIT 数据库 + ML 专项报告 |
| `audit_QC_math_algorithm_report.md` | QC 数学算法审计报告 |
| `audit_R4_index_verification_report.md` | R4 文档索引完整性审计报告 |
| `audit_TW_document_inventory_report.md` | TW 文档盘点审计报告 |

### audits/（专项审计报告）

| 文件 | 内容 |
|------|------|
| `2026-03-30--bilingual_comment_audit_report.md` | 双语注释全量审计报告（评级 9.5/10，100% 覆盖） |
| `2026-04-04--bybit_api_infra_audit.md` | ★ Bybit API 基础设施专项审计：REST/WS 端点覆盖度、SDK 对接质量、IPC 接口审核 |
| `2026-04-06--consolidated_remediation_report.md` | ★ L3 全系统审计 63 问题整改追踪报告：11 工作包 · 4 波执行 · R0-R3 整改记录 |
| `2026-04-07--e3_r6_directive_applier_security_audit.md` | E3 R6 Directive Applier 安全审计（Phase 4 前置） |
| `2026-04-07--phase4_final_signoff_audit.md` | Phase 4 最终验收审计报告 |
| `2026-04-08--e2_review_1c3_bbc.md` | E2 代码审查：ARCH-RC1 1C-3 BBC（Build-Before-Commit 验收） |
| `2026-04-09--db_rw_ml_pipeline_full_audit.md` | DB 读写 + ML 管线全量审计（Signal Diamond Phase 1 前置）|
| `2026-04-11--3e_arch_e2_multi_role_review.md` | ★★ 3E-ARCH E2 多角色審查：9 角色並行 Phase A-F 全修驗證 |
| `2026-04-11--3e_arch_phase_g_reaudit.md` | ★★ 3E-ARCH Phase G 重審：9/9 PASS — 0 BLOCKER |
| `2026-04-12--full_program_chain_audit.md` | ★★★★ 全程序鏈審計總報告：12 角色合併 · 58 findings（8 P0 · 17 P1 · 28 P2 · 5 P3） |
| `2026-04-12--full_audit_fix_plan_pm_confirmed.md` | ★★★ PM 確認修復計劃：P0~P3 分級修復排期 + PM 簽核 |

### KNOWN_ISSUES.md

| 文件 | 内容 |
|------|------|
| `KNOWN_ISSUES.md` | ★ 已知問題追蹤（OPEN 9 / RESOLVED 15，最後更新 2026-04-12） |

### architecture/ — 架構設計文件

| 文件 | 内容 |
|------|------|
| `DATA_STORAGE_ARCHITECTURE_V1.md` | ★ 數據存儲架構 V1：PG + TimescaleDB 方案 · 8 Schema · 存儲精簡 97%（5.6→0.17 GB/day）· 冷存儲 NAS 策略 |
| `architecture/multi_agent_rework_2026-05-05/2026-05-06--mag015_sprint_a_contract_addendum.md` | AgentTodo Sprint A MAG-015 合約附錄：local observations、OpenClaw view models、supervisor escalation、proposal/approval/channel schemas、endpoint allowlist、cloud budget、store ownership、state transitions |

### references/ — 长期参考文档

| 文件 | 内容 |
|------|------|
| **state_dictionary/** | |
| `2026-03-25--状态字典_数据字典_v1_最终版.md` | 状态字典 / 数据字典 V1 最终版（1149 行） |
| `2026-03-25--状态字典_v1_rc2_伴随补丁.md` | 状态字典 V1 RC2 伴随补丁 |
| **api_contract/** | |
| `2026-03-25--control_api_v1_最终定稿.md` | Control API V1 最终定稿（1008 行） |
| `2026-03-25--control_api_v1_rc2_最终候选版.md` | Control API V1 RC2 最终候选版 |
| `2026-03-25--control_api_v1_rc2_审核报告.md` | Control API V1 RC2 审核报告 |
| `2026-03-25--fastapi_openapi_v1_rc2_路由草案.md` | FastAPI / OpenAPI V1 RC2 路由草案 |
| `2026-03-25--后端实现清单_v1_rc2.md` | 后端实现清单 V1 RC2 |
| **api_stub/** | |
| `2026-03-25--control_api_v1_rc2_fastapi_stub.py` | FastAPI 骨架代码（553 行） |
| **根目录** | |
| `2026-03-25--capability_and_permission_switch_plan_v1.md` | 能力与权限开关规划 V1（md） |
| `2026-03-25--capability_and_permission_switch_plan_v1.pdf` | 能力与权限开关规划 V1（pdf） |
| `2026-03-25--gui_operator_console_learning_cockpit_v1_spec.md` | GUI Operator Console + Learning Cockpit V1 规格书 |
| `2026-03-27--layer2_ai_reasoning_engine_implementation_plan.md` | Layer 2 AI 推理引擎完整实现计划（4 层搜索降级 + 模型升级 + 自适应预算 + 9 路由 + GUI 集成） |
| `2026-03-27--local_trading_logic_audit_and_strategy_plan.md` | 本地交易逻辑审查报告：安全审查 + 本地覆盖缺口 + 盈利可能性评估 + ABCD 策略补齐计划 |
| `2026-03-27--phase1_risk_framework_and_agent_autonomy_design.md` | ★ 全品类风控框架完整设计：三层优先级 P0/P1/P2 + Bybit V5 全 6 品类 + 对抗性止损 + AI 注意力税 + Agent 自主交易 |
| `2026-03-27--phase2_strict_audit_report.md` | ★ Phase 2 严格审核报告：8 CRITICAL + 15 HIGH + 25 MEDIUM + 19 LOW，全 CRITICAL/HIGH 已修复 |
| `2026-03-27--phase2_audit_fix_roadmap.md` | Phase 2 审核修复工程路线图：已完成项 + 待完善项 + 架构级待定 |
| `2026-03-27--system_reference_handbook.md` | ★ 系统参考手册（从 CLAUDE.md 移出的参考性内容：能力目标/API路由/安全加固/产品族/订单类型/风控/部署/历史编号） |
| `2026-03-27--phase2_round2_strategic_audit_report.md` | Phase 2 第二轮审核：实战适用性（策略盈利性/管线连通性/数据质量/风控集成/信号可靠性） |
| `2026-03-27--full_system_audit_A_to_K.md` | ★★ 全系统审核 A-K：569 文件 63,874 行，7 CRITICAL + 19 HIGH + 28 MEDIUM + 16 LOW |
| `2026-03-27--remote_access_guide.md` | 远程访问完整指南：Tailscale 安装配置 + Bybit Demo 访问地址 + secrets 权限加固 |
| `2026-03-22--local_private_layout.md` | 本地私有布局说明：Git 仓库 vs 本地私有目录结构（secrets/srv 分离） |
| `2026-03-30--local_ai_expansion_analysis.md` | 本地 AI 擴展用途分析（Ollama/Qwen 3.5 應用場景，DOC-08 依據） |
| `2026-04-03--openclaw_improvement_report_v3_final.md` | ★★★★ 外部全面改善建議報告 V3 Final：五輪三人審批 34 項修正 · Agent 自主化架構 + 雙層決策 + 四階段放權 + 10 新模組 + 5 策略 V2 + L0-L2 路徑 + Claude API 整合 |
| `2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md` | V1.1+R1 · Agent 認知自適應規範：CognitiveModulator（L0 決策門檻調製）+ OpportunityTracker（遺憾追蹤）+ DreamEngine（閒置蒙特卡洛模擬）— 五角色審查通過，Phase 1 並行組 B |
| `2026-04-03--rust_migration_master_plan_v2.md` | V2 草稿（歸檔）· Rust 遷移總方案初版 |
| `2026-04-03--rust_migration_v2.5_consolidated.md` | V2.5 整合版（歸檔）· 六路缺口修復後 |
| `2026-04-03--rust_migration_v3_final.md` | ★★★★ V3-FINAL · Rust 遷移正式執行依據：五角色三輪審查 · 32,500 行 Rust · 14 週路線圖 · 分級浮點容差 · 四層測試 · 回滾計劃 · 21 項嚴格論證修正 |
| `2026-04-02--system_status_report.md` | 系統狀態報告（2026-04-02）：引擎健康度、測試基準線、已知問題彙整 |
| `2026-04-03--agent_param_tuning_design_draft_v0.2.md` | Agent 參數調整設計草稿 V0.2：策略參數 JSON 介面 · Agent 自主調參機制 · AGT-1 技術規格 |
| `2026-04-03--data_storage_architecture_optimal_draft_v0.1.md` | 數據存儲架構最優方案草稿 V0.1：PG + TimescaleDB · 分區策略 · 冷熱分層 |
| `2026-04-03--llm_abstraction_audit.md` | LLM 抽象層審計：LocalLLMClient ABC 介面覆蓋度 · Ollama 耦合殘留 · 跨平台兼容性評估 |
| `2026-04-03--ml_dl_learning_architecture_v0.4.md` | ★ ML/DL 學習架構 V0.4：Teacher-Student + LightGBM + Optuna + 3 DL 場景 · 三方審查完成 |
| `2026-04-10--signal_diamond_db_todo.md` | ★★ Signal Diamond DB TODO 歸檔：多引擎數據分離 5 Phase 規劃 · Phase 1-4 ✅ + 審計備註 · Phase 5 待實施（⚠ TradingMode→PipelineKind 歷史術語） |
| `2026-04-04--bybit_api_reference.md` | ★★ Bybit API 字典手冊：REST/WS 全端點速查 · V5 API 分類覆蓋 · 開發必讀 |
| `2026-04-04--comprehensive_audit_template_v1.md` | 全面審查模板 V1：L1/L2/L3 三級審計流程 · 5 路並行 9 角色 + DL/DB 專項 |
| `2026-04-04--execution_plan_v1.md` | ★ 融合方案執行計劃 V1：DB + ML/DL + 新聞 Agent 20 週路線圖 · Phase 0-6 詳細規格 |
| `2026-04-04--unified_db_ml_news_workplan_draft_v0.1.md` | 統一 DB + ML + 新聞 Agent 工作計劃草稿 V0.1：融合方案 v0.5 設計文件 · 67 項修正後版本 |
| `2026-04-06--phase4_execution_plan_v2.md` | 融合方案執行計劃 V2：Phase 4 更新版排期 |
| `2026-04-07--arch_rc1_1c3_scope.md` | ARCH-RC1 1C-3 範圍定義 |
| `2026-04-07--arch_rc1_1c3a_gap_analysis.md` | ARCH-RC1 1C-3A 缺口分析 |
| `2026-04-07--arch_rc1_1c3c_recon.md` | ARCH-RC1 1C-3C 對賬設計 |
| `2026-04-11--three_engine_parallel_arch_plan.md` | ★★★ 三引擎並行架構遷移計劃 v4：26 設計決策 · PM+PA+FA 三角色（✅ 已完成） |
| `2026-04-11--3e_arch_session_execution_plan.md` | ★★ 3E-ARCH Session 執行計劃：8 工作日排期（✅ 已完成） |
| `2026-04-06--math_implementation_notes.md` | 數學實現方案彙編：LinUCB/風控公式/統計檢定/校準/shrinkage |
| `2026-04-20--dust_frozen_position_manual_clear_procedure.md` | ★ Dust-Frozen 持倉手動清理 SOP：DUST-EVICTION-GAP-1 P1-8 設計背景 · Bybit GUI 三路線 · Live 前 pre-flight checklist |
| `2026-04-20--cross_platform_redeploy_dependencies.md` | ★ 跨平台重部署依賴參考：Linux→macOS（Apple Silicon）冷裝清單 · brew/rustup/pip 步驟 · systemd↔launchd 差異 · HMAC 憑證重簽陷阱 |
| `2026-05-02--reality_calibrated_fast_replay_governance.md` | REF-19 · Reality-Calibrated Fast Replay 治理契約：Replay 調用 MLDE/DreamEngine 作實驗環境與資料來源，但不改寫其 Agent 自我學習本職；明確 source tagging、execution calibration、demo/live 邊界 |
| `2026-05-02--reality_calibrated_fast_replay_governance_zh.md` | REF-19 中文版 · 與英文契約同義，供 operator-first 閱讀與後續實作引用；明確 Replay 只是 MLDE/DreamEngine 的實驗環境之一，不改變其 Agent 自我學習本職 |
| `2026-05-02--paper_replay_learning_surface_design.md` | REF-20 · Paper Replay Lab + Learning surface 設計：Paper Tab 原地升級為 Replay Lab；Learning 保持知識 cockpit；5-Agent 抽出為 read-only Agents Monitor |
| `2026-05-02--paper_replay_learning_surface_design_zh.md` | REF-20 中文版 · 與英文設計同義，明確 Paper / Learning / 5-Agent / MLDE / DreamEngine 的產品邊界、API/storage 姿態、分階段交付與驗收檢查 |

### execution_plan/ — 执行计划

| 文件 | 内容 |
|------|------|
| `2026-05-02--ref20_paper_replay_lab_dev_plan_draft_v0.1.md` | REF-20 Paper Replay Lab 開發方案 v0.1：早期審查材料，指出 manifest、source tagging、calibration、auth、安全與 UX 等風險 |
| `2026-05-02--ref20_paper_replay_lab_dev_plan_v1.md` | REF-20 Paper Replay Lab 開發方案 V1：第一版開發基線，確認 manifest signature、route auth、replay registry、MLDE source guard、execution calibration、多重檢驗與 5-Agent 抽出等問題大多屬真實風險 |
| `2026-05-02--ref20_v1_round2_audit.md` | REF-20 V1 第二輪 audit：對 V1 的安全、資料、量化、UX、API 審查意見；其中大多成立，但 P2 禁 IntentProcessor / Mac 禁 S2 public data 需在 V2 中反對或改寫 |
| `2026-05-02--ref20_paper_replay_lab_dev_plan_v2.md` | REF-20 Paper Replay Lab 開發方案 V2：整合 Round2 audit；已被 Round3/V2.1 收斂為更嚴格實作基線 |
| `2026-05-02--ref20_v2_round3_audit.md` | REF-20 V2 第三輪 audit：7-agent 審查 V2，指出 schema 物理欄位、MLDE retrofit、DB role guard、V### governance、P2 isolation、UX subdoc、Mac non-actionable policy 等 P0 gates |
| `2026-05-02--ref20_paper_replay_lab_dev_plan_v2_1_round3.md` | REF-20 Paper Replay Lab 開發方案 V2.1 Round3：當前實作前基線；接受 Round3 真實問題，明確 schema/DB/migration/runner/quant/UX gates，保留 P2 isolated no-write TickPipeline/IntentProcessor 方案 |
| `2026-05-02--ref20_ux_subdoc_v1.md` | REF-20 Paper Replay Lab UX Subdoc V1：P1 前必讀 UX contract；定義 Session/Replay/Compare/Handoff、mode badges、disabled states、no submit/cancel 與 handoff gating |
| **`2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md`** | **★ SoT** REF-20 Paper Replay Lab 開發方案 V3：取代 V2.1 Round3 為當前 implementation baseline；§12 25 條 acceptance binding；§4.1 replay.experiments 22 col + replay.simulated_fills 17 col 規範表；§4.2 mlde_shadow_recommendations 三 column 雙路 CHECK |
| `2026-05-03--ref20_implementation_workplan_v1.md` | REF-20 Implementation Workplan V1：9-Wave / 76-task atomic breakdown；§6 hard prereq table 7 條；總工時 12-14 sprint（不含 P5 LG 等期）|
| `2026-05-03--ref20_wave2_dispatch_v1.md` | REF-20 Wave 2 dispatch v1：5 ambiguity decisions（unified terminology / 2only / reuse / Mac/Linux priority / bilingual flexibility）|
| `2026-05-03--ref20_wave1_to_6_master_closure.md` | REF-20 Wave 1-6 master closure summary（commits 9e0c826 / 1851714+b1f6b8a / 5a618ff / 4b48b6d / 457a458 / eb5f106）|
| `2026-05-03--ref20_wave7_defer_note.md` | REF-20 Wave 7 defer note：hard prereq LG-2/3/4 frontend stable NOT GREEN；事件觸發 dispatch 標準；後 commit `c887e4e` operator override IMPL（已正式 amendment AMD-2026-05-03-01 規範 IMPL/Deploy 2-stage gate）|
| `2026-05-03--ref20_wave9_pm_sign_off_template.md` | REF-20 Wave 9 PM sign-off 7-item checklist template；deploy 後 14d gradient observation 起算 |
| `2026-05-03--ref20_final_closure_and_deploy_guidance.md` | REF-20 Final IMPL closure + Operator Deploy Guidance；§4 14-step procedure (Phase A-G)；**注意**：line 99 「~3500+ PASS」是虛構數字（cold reality 3387 PASS，差 113-126；P2-FOLLOW-UP-5 訂正 ticket 待修）|
| `2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_3.md` | REF-21 Full-Chain Replay Engine V1.3：active plan；修正 negative-edge fail-open，補 subprocess deploy path、V057/V058/V059/V060 DDL sketch + Linux PG dry-run、promotion FSM/signatures、Bybit SSOT URI、block bootstrap、survival/correlation/cost thresholds、baseline SLA |
| `2026-05-06--ref21_gui_ux_spec_v1_1.md` | REF-21 Replay GUI/UX Spec V1.1：active GUI companion；補二次確認、cooldown、12-tab 一致性、a11y/i18n、agent quota UI、sign-off SOP |
| `2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_2.md` | REF-21 Full-Chain Replay Engine V1.2：已被 V1.3 supersede，保留作第三輪 audit 追溯 |
| `2026-05-06--ref21_gui_ux_spec_v1.md` | REF-21 Replay GUI/UX Spec V1：已被 V1.1 supersede，保留作 GUI 初版追溯 |
| `2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_1.md` | REF-21 Full-Chain Replay Engine V1.1：已被 V1.2 supersede，保留作第二輪 audit 追溯 |
| `2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1.md` | REF-21 Full-Chain Replay Engine V1：已被 V1.1 supersede，保留作方向性 baseline 與 audit 追溯 |
| `2026-05-XX--ref21_s1_recorder_spec_placeholder.md` | REF-21 S1 recorder placeholder：已被 REF-21 Full-Chain Replay V1 接管，保留作 REF-20 Wave 5 歷史 trace |
| `2026-05-03--ref20_sprint3_track_i_linux_deploy_runbook.md` | REF-20 Sprint 3 Track I Linux deploy runbook |
| `2026-05-03--ref20_sprint4_final_closure.md` | REF-20 Sprint 4 final closure |
| `2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md` | REF-20 Gap Closure Plan V1：Sprint A-D 的 SoT execution plan |
| `2026-05-07--ref21_replay_remaining_wave_reset_v1.md` | REF-21 Replay Remaining Wave Reset V1：REF-21 V1.3 governance gates 保留前提下剩餘 wave 重排 |
| `2026-05-09--w_audit_8b_strategist_alpha_orchestrator_spec.md` | W-AUDIT-8b Strategist Alpha-Source Orchestrator spec（R-2 spec phase） |
| `2026-05-09--w_audit_8c_hypothesis_pipeline_spec.md` | W-AUDIT-8c Hypothesis Pipeline as First-Class Governance Object spec（R-3 spec phase） |
| `2026-05-09--w_audit_8d_per_alpha_source_promotion_gate_spec.md` | W-AUDIT-8d Per-Alpha-Source Live Promotion Gate spec（R-4 spec phase）|
| `2026-05-09--w_audit_8e_spec_as_code_spec.md` | W-AUDIT-8e Spec-as-Code + Module Lifecycle SM spec（R-5 spec phase）|

#### REF-20 governance amendments

| 文件 | 內容 |
|------|------|
| `governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md` | AMD-2026-05-02-01 Decision Lease retrofit 路徑 A（Rust facade + router gate + Python IPC bridge + audit writer fix）|
| `governance_dev/amendments/2026-05-03--ref20_wave7_p5_impl_accept_deploy_blocked.md` | AMD-2026-05-03-01 Wave 7 P5 IMPL-accept-deploy-blocked（IMPL gate vs Deploy gate 2-stage 規範 + 4 AC + 失敗回退 + PM autonomous mode 嚴格門檻 4 條）|

#### REF-20 Sprint reports（cold audit + Sprint 1+2 retroactive）

| 文件 | 內容 |
|------|------|
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_sprint1_partition_design.md` | PA Sprint 1 4 並行 Track partition design + 5 push back |
| `CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_sprint2_track_e_decision_lease_retrofit_design.md` | PA Sprint 2 Track E Decision Lease retrofit AMD-2026-05-02-01 partition + 5 AC SQL + 6 Phase 灰度 rollout |
| `CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_sprint1_track_{a,b,c,d}_*.md` | E1 Sprint 1 4 Track IMPL reports（spawn argv / Rust manifest verify / Python 3 安全洞 / V049-V053 schema）|
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-03--ref20_sprint1_4track_review.md` | E2 Sprint 1 round 1 4 Track review（Track C RETURN-TO-E1 1500 LOC enforce）|
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-03--ref20_sprint1_round2_retrofit_review.md` | E2 Sprint 1 round 2 retrofit verify（Track A + C retrofit PASS + cross-track 7/7）|
| `CCAgentWorkSpace/E2/workspace/reports/2026-05-03--ref20_wave3_to_9_retroactive_master_review.md` | E2 Sprint 2 retroactive Wave 3-9 master review（10 LOW + 7 P2 ticket 提案 + Wave 7 PASS / Wave 3/4/5/6/8/9 CONDITIONAL）|
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-03--ref20_final_closure_e4_cold_audit.md` | E4 cold audit baseline（pre-Sprint 1 真實 pytest/cargo 數字）|
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-03--ref20_sprint1_e4_regression.md` | E4 Sprint 1 regression CONDITIONAL PASS（+13 PASS / +7 lib / 0 新 fail / 2 pre-existing carry-over）|
| `CCAgentWorkSpace/E4/workspace/reports/2026-05-03--ref20_wave3_to_9_retroactive_e4_cumulative.md` | E4 Sprint 2 retroactive Wave 3-9 cumulative（4 P0 forgery flag + 5 mock retroactive flag + 3 P2-FOLLOW-UP 提案）|

#### PM scanner / edge reports（2026-05-06）

| 文件 | 內容 |
|------|------|
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-06--scanner_opportunity_integration_audit.md` | PM scanner opportunity integration audit：整合零散 scanner / edge / market judgment 模塊，定義 shadow-only 中性 opportunity 判斷邊界 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-06--scanner_opportunity_v1_shadow_implementation.md` | Scanner Opportunity v1 shadow implementation：Rust scanner opportunity math、intent details、Python reader、測試與對抗性審查結果 |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-06--scanner_opportunity_healthcheck_51.md` | Scanner Opportunity `[51]` passive healthcheck：snapshot / intent / MLDE row proof coverage + opportunity_lcb_bps calibration，shadow-only |
| `CCAgentWorkSpace/PM/workspace/reports/2026-05-06--agenttodo_sprint_a_event_store_source_wiring.md` | AgentTodo Sprint A MAG-010..014 source wiring：default-off AgentEventStore、MessageBus sink、state/AI invocation hooks、`[52]` healthcheck；Linux row proof pending |

### governance_dev/ — 治理开发文档

> 注意：governance_dev/ 下早期文件使用大寫命名（如 `T2_EXECUTION_SUMMARY.md`），
> 晚於 2026-03-31 的新文件必須遵循 `YYYY-MM-DD--描述.md` 命名規範。

#### governance_dev/audits/ — ★ 审计报告

| 文件 | 内容 |
|------|------|
| `2026-03-30--round2_cold_functional_audit.md` | ★★★ Round 2 冷酷功能审核（任务 1/2/3：32% 完成度 + 架构融合 + Paper Trading 路线图） |
| `2026-03-30--governance_compliance_audit.md` | 治理合规审计（EX-05/06/07/DOC-01~08，合规度 ~65%） |
| `2026-03-30--pipeline_bridge_paper_engine_audit.md` | PipelineBridge + PaperTradingEngine 代码级审计（治理 gate 验证 + 止损验证 + 学习回调验证） |
| `2026-03-31--gap_analysis_287_specs.md` | ★ 287 条治理规格 Gap 分析报告（76% 已实施：67A + 18B + 8C + 2D） |
| `2026-03-31--spec_requirements_287.md` | 287 条规格完整列表（Markdown 版，与 Gap 分析配套） |
| `2026-03-31--spec_requirements_287.json` | 287 条规格完整列表（JSON 机器可读版） |
| `2026-03-31--gap_analysis_findings.json` | Gap 分析发现结果（JSON 结构化输出） |
| `2026-03-31--gap_analysis_file_reference.md` | Gap 分析文件引用索引 |
| `2026-03-31--development_roadmap_v2.md` | 4-Phase 开发路线图 V2（基于 Gap 分析制定） |
| `2026-03-31--phase0_round2.5_audit_report.md` | Phase 0 Round 2.5 审计报告（2 P0 + 1 P1 修复 + 287 spec Gap 分析） |

#### governance_dev/audits/2026-03-30--全面審核/ — ★★★ 全系统冷酷功能审核（9 Batch）

| 文件 | 内容 |
|------|------|
| `00_審查計劃總綱.md` | 审查计划总纲 + 进度追踪（9 Batch，A-I） |
| `01_A_即時問題診斷.md` | ★★★ P0 根因分析：MA_Cross metadata falsy + FundingRate 错误 symbol（10/10 策略全失效） |
| `02_B_交易核心路徑.md` | 交易核心路径验证（B1-B7：状态机/Fill/PnL/round_trip 均正确） |
| `03_C_風控框架.md` | 风控框架验证（P1：drawdown gate 无强制执行；其余 C2-C8 均正确） |
| `04_D_學習系統.md` | 学习系统验证（E1 路径代码就绪，因 0 fills 未实际运行） |
| `05_E_AI治理層.md` | AI 治理层验证（H0/Decision Lease 完整；AI 调用合法跳过） |
| `06_F_掃描器策略部署.md` | 扫描器与策略部署验证（5min 周期、40% 过滤、WS 动态订阅均正确） |
| `07_G_GUI_API端點.md` | GUI 与 API 端点验证（所有关键端点存在，数据源正确） |
| `08_H_測試健康度.md` | 测试健康度（2,166 通过；P0 bug 路径无测试覆盖） |
| `09_I_代碼品質.md` | 代码品质扫描（无 TODO/FIXME/silent except；硬编码值均有注释） |
| `99_審查總結與修復清單.md` | ★★★ 审查总结：3 个问题（P0×2 + P1×1）+ 修复方案 + 系统健康全景 |

#### governance_dev/2026-03-30 Round 2 修复计划

| 文件 | 内容 |
|------|------|
| `2026-03-30--round2_fix_plan_batches_7_12.md` | ★★ Batch 7-12 完整技术规格（Conductor + Guardian + Perception + Analyst + L2 + Paper→Live） |
| `2026-03-30--round2_fix_plan_EXECUTIVE_SUMMARY.md` | 修复计划管理摘要（缺口分析 + 策略 + 风险） |
| `2026-03-30--round2_fix_plan_QUICK_REFERENCE.md` | 修复计划开发速查（批次清单 + 依赖图 + 成本） |
| `2026-03-30--ROUND2_FIX_PLAN_INDEX.md` | 修复计划导航索引 |
| `2026-03-30--round2_pragmatic_fix_plan.md` | Round 2 务实修复计划（优先级排序 + 实施策略） |

#### governance_dev/ — 规格提取与287条治理规格（根目录文件）

| 文件 | 内容 |
|------|------|
| `README.md` | governance_dev 子目录自述文件 |
| `COMPREHENSIVE_SPEC_REQUIREMENTS.md` | 287 条治理规格完整列表（Markdown 版） |
| `COMPREHENSIVE_SPEC_REQUIREMENTS.json` | 287 条治理规格完整列表（JSON 机器可读版） |
| `SPECIFICATION_EXTRACTION_SUMMARY.md` | 规格提取摘要（13 份 .docx → 287 条结构化提取过程） |
| `SPECIFICATION_REGISTER.md` | 规格登记册（DOC/SM/EX 文件版本追踪） |
| `EXTRACTION_VALIDATION.txt` | 提取验证报告（规格数量/覆盖度/交叉引用校验） |
| `QUICK_START_REFERENCE.txt` | 治理开发快速入门参考 |

#### governance_dev/governance_extracts/ — 治理规格提取（5 份参考文档）

| 文件 | 内容 |
|------|------|
| `GOVERNANCE_DOCUMENTATION_INDEX.md` | 治理文档索引（13 份规格文件导航） |
| `GOVERNANCE_IMPLEMENTATION_CHECKLIST.md` | 治理实现清单（需求→代码映射 + 完成度追踪） |
| `GOVERNANCE_QUICK_REFERENCE.md` | 治理速查手册（16 根原则 + 状态机速览） |
| `OPENCLAW_GOVERNANCE_SUMMARY.md` | 治理综合摘要（13 份文件结构化总结） |
| `OPENCLAW_TECHNICAL_SPEC.md` | 技术规格总结（22 份治理规格集） |

#### governance_dev/changelogs/ — T2.01–T2.23 模组变更日志（23 份）

每份治理模组的实现变更日志，命名格式 `2026-03-29_T2.XX_模组名.md`。

#### governance_dev/phase2_execution/ — Phase 2 治理模組执行记录

| 文件 | 内容 |
|------|------|
| `T2_EXECUTION_SUMMARY.md` | ★ Phase 2 执行总览：21 模组矩阵 + 关键指标 |
| `T2_PM_QUALITY_AUDIT_REPORT.md` | Phase 2 PM 品质审核报告（T2.01–T2.23，整体 4/5，0 个 P0 blocker） |
| `T2_TW_COMMENT_AUDIT_REPORT.md` | Phase 2 TW 注释品质审核报告（评级 9.5/10，100% 双语覆盖） |
| `T2_TEST_RESULTS.md` | T2 测试套件执行报告（1485 测试） |
| `PM_FA_FULL_COMPLIANCE_AUDIT.md` | PM + FA 完整合规审计 |
| `PM_T0_ENGINEERING_AUDIT.md` | PM T0 工程审计 |
| `REVIEW_T2_CODE_QUALITY.md` | T2 代码质量审查 |
| `DOCUMENTATION_REVIEW_T2.07-LATEST.md` | T2.07+ 文档审查 |
| `FIXTURE_REFACTOR_SUMMARY.md` | 测试 Fixture 重构总结 |
| `TEST_FIXTURE_OVERVIEW.md` | 测试 Fixture 重构概览 |

#### governance_dev/phase3_integration/ — Phase 3 治理集成

| 文件 | 内容 |
|------|------|
| `PHASE3_WORK_PLAN.md` | Phase 3 工作计划（从 72% 到可安全交易） |
| `T3.01_FA_INTEGRATION_DESIGN.md` | FA 集成设计 |
| `T3_GOVERNANCE_INTEGRATION_GUIDE.md` | Phase 3 治理集成指南 |
| `PHASE3_CODE_REVIEW_REPORT.md` | Phase 3 代码审查报告 |
| `SECURITY_AUDIT_PHASE3.md` | Phase 3 安全审计报告 |
| `2026-03-30_TW_ENGINEERING_AUDIT_REPORT.md` | TW 工程审计报告 |
| `REVIEW_GOVERNANCE_GUI.md` | GUI 治理集成审查（PASS） |

#### governance_dev/phase4_acceptance/ — Phase 4 验收

| 文件 | 内容 |
|------|------|
| `T4.01_CC_COMPLIANCE_MATRIX.md` | CC 合规矩阵 |
| `T4.02_E4_TEST_COVERAGE_REPORT.md` | E4 测试覆盖报告 |
| `T4.03_A3_UX_REVIEW_REPORT.md` | A3 UX 审查报告 |
| `T4.04_R4_DOCUMENT_AUDIT_REPORT.md` | R4 文档审计报告 |
| `T4.05_PM_FINAL_ACCEPTANCE_REPORT.md` | PM 最终验收报告 |
| `T4.06_PM_GUI_GOVERNANCE_PLAN.md` | PM GUI 治理计划 |
| `TEST_REPORT_GOVERNANCE_E4.md` | E4 测试工程师验收报告 |

#### governance_dev/phase1–12 其他阶段 — 各阶段任务书 + PM 验收 + FA 缺口审计

每阶段通常包含：`PHASE*_TASK_BOOK`, `PHASE*_PM_ACCEPTANCE_REPORT`, `FA_GAP_AUDIT_REPORT`。
详见各子目录。

---

### CCAgentWorkSpace/ — Agent 獨立工作空間（2026-03-31 新增）

19 個 Agent 角色各自的獨立工作空間。每個 Agent 有 `profile.md`（角色定位）、`memory.md`（工作記憶）、`workspace/`（報告存檔）。

| 目錄 | Agent | 層次 |
|------|-------|------|
| `CCAgentWorkSpace/PM/` | Project Manager | 管理層 |
| `CCAgentWorkSpace/FA/` | Functional Auditor | 管理層 |
| `CCAgentWorkSpace/PA/` | Project Architect | 管理層 |
| `CCAgentWorkSpace/CC/` | Compliance Checker | 質量保證層 |
| `CCAgentWorkSpace/E2/` | Code Reviewer | 質量保證層 |
| `CCAgentWorkSpace/E3/` | Security Auditor | 質量保證層 |
| `CCAgentWorkSpace/E4/` | Test Engineer | 質量保證層 |
| `CCAgentWorkSpace/E5/` | Optimization Engineer | 質量保證層 |
| `CCAgentWorkSpace/E1/` | Backend Developer | 執行層 |
| `CCAgentWorkSpace/E1a/` | Frontend Developer | 執行層 |
| `CCAgentWorkSpace/A3/` | UX Auditor | 專項審查層 |
| `CCAgentWorkSpace/R4/` | Document Auditor | 專項審查層 |
| `CCAgentWorkSpace/TW/` | Technical Writer | 專項審查層 |
| `CCAgentWorkSpace/AI-E/` | AI Effectiveness Evaluator | 分析層 |
| `CCAgentWorkSpace/MIT/` | ML / DB Foundation Auditor | 專項審查層 |
| `CCAgentWorkSpace/BB/` | Bybit API Compatibility Auditor | 專項審查層 |
| `CCAgentWorkSpace/QA/` | Quality Assurance | 分析層 |
| `CCAgentWorkSpace/QC/` | Quantitative/Math Auditor | 專項審查層 |
| `CCAgentWorkSpace/Operator/` | Operator（人類 Operator 視角） | 管理層 |

---

### archive/ — TODO.md / CLAUDE.md §三 歷史敘述歸檔

| 文件 | 內容 |
|------|------|
| `2026-04-30--active_docs_cleanup_archive.md` | 2026-04-30 active docs cleanup 歸檔說明：CLAUDE/TODO/README 清理範圍、保留快照、Linear 高層同步摘要 |
| `2026-04-30--TODO-stale-active-mainline.md` | 2026-04-30 TODO 修正歸檔：從 active section 移出的過時 62-finding mainline / Post-Wave-H hotfixes 摘要 |
| `2026-04-30--CLAUDE-pre-cleanup-snapshot.md` | 2026-04-30 清理前 `CLAUDE.md` 完整快照 |
| `2026-04-30--TODO-pre-cleanup-snapshot.md` | 2026-04-30 清理前 `TODO.md` 完整快照 |
| `2026-04-30--README-pre-cleanup-snapshot.md` | 2026-04-30 清理前 `README.md` 完整快照 |
| `2026-04-29--62finding-batch-A-to-F.md` | ★★★★ 62-Finding Audit Remediation Batch A-F 全程歸檔（commits `bc3fa70` + `6539e4e` + `5db4e29`）：6 batch × 62 findings × Linear NCY-5~10 milestone 對應 + post-deploy healthcheck status（FAIL [12]+[22] / WARN [27]，live pipeline gate v1→v2）|
| `2026-04-29--strkusdt-p0-wave.md` | ★★★ STRKUSDT Dust Spiral P0 Wave 歸檔：F1 deploy `af48ee1` + F2-F7 6 PR merge（`1dff948` / `5ac7a80` / `310ae29` / `31c8206` / `1341c01` / `1edc6fe`）+ E4 combined 2252/0 + 8 healthcheck [22]-[29] + RCA 三層（entry_notional fail-open / Gate 2 cross-symbol / 41 phantom fills attribution）|
| `2026-04-01--completed_todo_archive_wave0_7_phase1_3.md` | Wave 0-7 / Phase 1-3 completed TODO archive |
| `2026-04-03--completed_todo_archive_batch9a_wave8_xp.md` | Batch 9a / Wave 8 XP completed TODO archive |
| `2026-04-03--data_storage_architecture_optimal_draft_v0.1.md` | Data storage architecture draft archive |
| `2026-04-03--rust_migration_master_plan_v2.md` | Rust migration master plan v2 archive |
| `2026-04-03--rust_migration_v2.5_consolidated.md` | Rust migration v2.5 consolidated archive |
| `2026-04-03--system_snapshot_external_analysis.md` | External system snapshot analysis archive |
| `2026-04-04--completed_todo_archive_phase0123_rust.md` | Phase 0-3 Rust completed TODO archive |
| `2026-04-06--completed_todo_archive_l3_phases.md` | L3 phases completed TODO archive |
| `2026-04-07--claude_md_section3_history_phase0_4.md` | CLAUDE.md §三 Phase 0-4 history archive |
| `2026-04-08--arch_rc1_1c_history_archive.md` | ARCH-RC1 1C history archive |
| `2026-04-08--main_docs_1c3_1c4_narrative.md` | Main docs 1C3/1C4 narrative archive |
| `2026-04-09--scanner_todo_phase_a_d_spec.md` | Scanner TODO Phase A-D spec archive |
| `2026-04-10--completed_todo_live_gui_dead_py.md` | Live GUI dead-Python completed TODO archive |
| `2026-04-11--completed_todo_3e_arch.md` | 3E architecture completed TODO archive |
| `2026-04-11--completed_todo_w19_w20_phase6.md` | W19/W20 Phase 6 completed TODO archive |
| `2026-04-12--changelog_archive_pre_0408.md` | Pre-2026-04-08 changelog archive |
| `2026-04-12--completed_todo_full_program_audit.md` | Full program audit completed TODO archive |
| `2026-04-13--changelog_archive_0408_0409.md` | 2026-04-08/09 changelog archive |
| `2026-04-14--completed_todo_w22_phantom_heal.md` | W22 phantom-heal completed TODO archive |
| `2026-04-15--claude_md_section3_snapshot.md` | CLAUDE.md §三 2026-04-15 snapshot |
| `2026-04-15--completed_todo_w22_engine_heal_edge_p3.md` | W22 engine-heal / Edge P3 completed TODO archive |
| `2026-04-15--phase5_promotion_edge_crisis_full.md` | Phase 5 promotion edge crisis archive |
| `2026-04-16--completed_todo_strategy_close_tag_edge_p3_dedup.md` | Strategy close-tag / Edge P3 dedup archive |
| `2026-04-17--completed_todo_p0_scanner_phantom_live_guard.md` | P0 scanner phantom-live guard archive |
| `2026-04-20--claude_md_section3_snapshot.md` | CLAUDE.md §三 2026-04-20 snapshot |
| `2026-04-20--completed_todo_batch.md` | 2026-04-20 completed TODO batch archive |
| `2026-04-21--claude_md_section3_snapshot.md` | CLAUDE.md §三 2026-04-21 snapshot |
| `2026-04-21--completed_todo_batch.md` | 2026-04-21 completed TODO batch archive |
| `2026-04-22--step_0_derived_todo_batch.md` | Step 0 derived TODO batch archive |
| `2026-04-24--completed_todo_batch.md` | 2026-04-24 completed TODO batch archive |
| `2026-04-24--todo_snapshot_pre_refactor.md` | TODO pre-refactor snapshot archive |
| `2026-04-24--todo_v1_refactor_snapshot.md` | TODO v1 refactor snapshot archive |
| `2026-04-24--todo_v2_dual_axis_snapshot.md` | TODO v2 dual-axis snapshot archive |
| `2026-04-29--CLAUDE-pre-trim-snapshot.md` | CLAUDE.md pre-trim snapshot archive |
| `2026-04-29--TODO-pre-trim-snapshot.md` | TODO pre-trim snapshot archive |
| `2026-04-29--claude_md_section3_pre_04_27_detail.md` | CLAUDE.md §三 pre-2026-04-27 detail archive |
| `2026-04-29--wave-A-to-H-narrative.md` | Wave A-H narrative archive |
| `2026-05-01--completed_waves_1_2_3_and_backlog.md` | Completed Waves 1-3 and backlog archive |
| `2026-05-02--CLAUDE-pre-trim-snapshot.md` | CLAUDE.md 2026-05-02 pre-trim snapshot archive |
| `2026-05-02--TODO-pre-trim-snapshot.md` | TODO 2026-05-02 pre-trim snapshot archive |
| `2026-05-06--claude_md_stale_extract.md` | CLAUDE.md stale extract archive |
| `2026-05-06--readme_stale_extract.md` | README stale extract archive |
| `2026-05-06--todo_completed_extract.md` | TODO completed extract archive |
| `2026-05-07--todo_v12_agent_openclaw_replan_archive.md` | TODO v12 Agent/OpenClaw replan archive |
| `2026-05-09--claude_md_section5_pre_alpha_surface.md` | CLAUDE.md §五 pre-AlphaSurface architecture framing archive |
| `2026-05-09--qctodo_sprint_n0_n5_archive.md` | QCTODO Sprint N+0..N+5 planning archive |
| `2026-05-09--w_audit_verified_closed_archive.md` | W-AUDIT-1..7 verified-closed details archive |
| `2026-05-15--todo_v21_completion_cleanup_archive.md` | TODO v21 completion cleanup archive: completed sprint ledgers, DONE rows, and W-AUDIT priority delta |
| `2026-05-15--todo_v24_stale_rows_archive.md` | TODO v24 stale rows archive：過時 active rows / stale claims 歸檔（V079 pending / engine 5/8 binary / 舊 demo state / 舊 `[55]`/`[67]` 判斷）|
