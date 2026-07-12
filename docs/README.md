# docs/ — 项目文档目录 (Project Documentation Directory)

本目录存放玄衡 · Arcane Equilibrium 交易治理系统的所有工程文档、日志、交接记录和决策备忘。

This directory holds all engineering documents, logs, handoff records, and decision memos for the Arcane Equilibrium agentic trading governance system.

> **ROUTER FIRST**
>
> 本文件是文档目录入口，不是 active dispatch queue，也不是完整历史证据库。
> 当前工作状态、owner、gate、runtime evidence、operator action 一律读根目录
> `TODO.md`；本文件只提供稳定目录路由和索引入口。大规模历史 report
> 不在这里全文展开，按主题先看 `docs/_indexes/initiative_index.md`。

## 当前入口速查

| 需要 | 入口 |
|---|---|
| 当前活跃工作 / blocker / next action | `../TODO.md` |
| 稳定项目入口 / 架构地图 | `../README.md` |
| IBKR stock/ETF capability policy | `governance_dev/amendments/2026-07-11--AMD-2026-07-11-01-ibkr-stock-etf-full-live-capability-development.md` — implementation is allowed; activation remains separate |
| agent 启动路由 | `agents/context-loading.md` |
| 主题证据导航 | `_indexes/initiative_index.md` |
| 路径迁移 / redirect 记录 | `_indexes/path_redirects.md` |
| 版本增量历史 | `CLAUDE_CHANGELOG.md` |
| 历史归档 | `archive/` |
| Development-agent 正本 / task closure | `../.codex/agent_registry_v1.json` / `agents/development-agent-governance.md` |

## Multi-Agent 接手路径

| 任务类型 | 必读入口 | 读取边界 |
|---|---|---|
| 接手 active work / 判断是否能开工 | `../TODO.md` | 只把这里当当前 owner、gate、next action 权威。 |
| 找某个主题的设计和证据 | `_indexes/initiative_index.md` | 按主题进设计、报告、archive；不要从长索引反推 active 状态。 |
| 查历史文档或近期交付清单 | `_indexes/document_index.md` | 历史/导航用途；不是 active queue。 |
| 查审计证据 | `_indexes/audit_index.md` | 先确认 `TODO.md` 是否仍 active，再读 audit/report。 |
| 写新文档 / 移动路径 | 本文件 + `_indexes/path_redirects.md` | 先分类和命名；移动前保留 redirect/stub 计划。 |
| 读取历史 role evidence | `CCAgentWorkSpace/README.md` | 只按 task link 读取；当前 sign-off 用同一 closure packet，active state 回到 `TODO.md`。 |
| 执行 runbook / 操作手册 | `runbooks/README.md` | runbook 不是授权；运行态操作先看 `TODO.md` operator actions。 |
| 查架构背景 | `architecture/README.md` + `../README.md` | 旧架构文档可能是 reference，读 banner 和当前 ADR/AMD。 |

---

## 稳定入口索引 (Static Guard Index)

### docs/agents/

| 路径 | 用途 |
|---|---|
| `agents/domain.md` | Agent domain / ownership routing reference |
| `agents/issue-tracker.md` | Issue tracker and TODO hygiene reference |
| `agents/triage-labels.md` | Triage label vocabulary and classification reference |
| `agents/role-profile-memory-standard.md` | 角色 profile / memory 標準（active state 讀 TODO，項目定位讀 README）|
| `agents/development-agent-governance.md` | Development-Agent Governance Module：Registry/Context/Dispatch/Closure、OPS/IB、consumption 與 effect Adapter 正本 |
| `agents/todo-maintenance.md` | TODO.md 維護標準（編輯 TODO 前必讀）|
| `agents/sub-agent-hygiene-sop.md` | 後台 sub-agent 防殺 / 活性偵測 SOP |
| `agents/profit-first-fast-demo-promotion-loop.md` | profit-first 快速 Demo 晉升迴圈 |
| `agents/context-loading.md` | 各 context class 位置與 PG 連線 / dry-run 範例 |
| `agents/profit-first-autonomy-loop.md` | profit-first 自主迴圈 |

### helper_scripts/

- 脚本索引入口：[`../helper_scripts/SCRIPT_INDEX.md`](../helper_scripts/SCRIPT_INDEX.md)

### docs/CCAgentWorkSpace/

当前 workspace 目录包含 20 個 generated development role presets + Operator 目錄。MIT、BB、IB、OPS 是 data/venue/runtime 邊界審計時的穩定入口：

- `CCAgentWorkSpace/MIT/` — Market / Information Theory Auditor；data、feature、CV、schema rigor。
- `CCAgentWorkSpace/BB/` — Bybit Boundary Reviewer；交易所/Bybit 相容性與隔離審查。
- `CCAgentWorkSpace/IB/` — IBKR Broker Compatibility Adapter reviewer；ADR-0048/TWS/session/entitlement/paper-shadow denial。
- `CCAgentWorkSpace/OPS/` — read-only operations reviewer；preflight/rollback/postcheck/RCA，不 apply。
- `CCAgentWorkSpace/Operator/` — Operator-facing 摘要與交接 trace。

### docs/archive/

Top-level archive 檔名索引如下；完整歷史語義仍以 `_indexes/document_index.md` 與 `_indexes/initiative_index.md` 分流查詢。

- `2026-04-01--completed_todo_archive_wave0_7_phase1_3.md`
- `2026-04-03--completed_todo_archive_batch9a_wave8_xp.md`
- `2026-04-03--data_storage_architecture_optimal_draft_v0.1.md`
- `2026-04-03--rust_migration_master_plan_v2.md`
- `2026-04-03--rust_migration_v2.5_consolidated.md`
- `2026-04-03--system_snapshot_external_analysis.md`
- `2026-04-04--completed_todo_archive_phase0123_rust.md`
- `2026-04-06--completed_todo_archive_l3_phases.md`
- `2026-04-07--claude_md_section3_history_phase0_4.md`
- `2026-04-08--arch_rc1_1c_history_archive.md`
- `2026-04-08--main_docs_1c3_1c4_narrative.md`
- `2026-04-09--scanner_todo_phase_a_d_spec.md`
- `2026-04-10--completed_todo_live_gui_dead_py.md`
- `2026-04-11--completed_todo_3e_arch.md`
- `2026-04-11--completed_todo_w19_w20_phase6.md`
- `2026-04-12--changelog_archive_pre_0408.md`
- `2026-04-12--completed_todo_full_program_audit.md`
- `2026-04-13--changelog_archive_0408_0409.md`
- `2026-04-14--completed_todo_w22_phantom_heal.md`
- `2026-04-15--claude_md_section3_snapshot.md`
- `2026-04-15--completed_todo_w22_engine_heal_edge_p3.md`
- `2026-04-15--phase5_promotion_edge_crisis_full.md`
- `2026-04-16--completed_todo_strategy_close_tag_edge_p3_dedup.md`
- `2026-04-17--completed_todo_p0_scanner_phantom_live_guard.md`
- `2026-04-20--claude_md_section3_snapshot.md`
- `2026-04-20--completed_todo_batch.md`
- `2026-04-21--claude_md_section3_snapshot.md`
- `2026-04-21--completed_todo_batch.md`
- `2026-04-22--step_0_derived_todo_batch.md`
- `2026-04-24--completed_todo_batch.md`
- `2026-04-24--todo_refactor_audit.md`
- `2026-04-24--todo_snapshot_pre_refactor.md`
- `2026-04-25--ae_inventory_consolidated.md`
- `2026-04-24--todo_v1_refactor_snapshot.md`
- `2026-04-24--todo_v2_dual_axis_snapshot.md`
- `2026-04-29--62finding-batch-A-to-F.md`
- `2026-04-29--CLAUDE-pre-trim-snapshot.md`
- `2026-04-29--TODO-pre-trim-snapshot.md`
- `2026-04-29--claude_md_section3_pre_04_27_detail.md`
- `2026-04-29--strkusdt-p0-wave.md`
- `2026-04-29--wave-A-to-H-narrative.md`
- `2026-04-30--CLAUDE-pre-cleanup-snapshot.md`
- `2026-04-30--README-pre-cleanup-snapshot.md`
- `2026-04-30--TODO-pre-cleanup-snapshot.md`
- `2026-04-30--TODO-stale-active-mainline.md`
- `2026-04-30--active_docs_cleanup_archive.md`
- `2026-05-01--completed_waves_1_2_3_and_backlog.md`
- `2026-05-02--CLAUDE-pre-trim-snapshot.md`
- `2026-05-02--TODO-pre-trim-snapshot.md`
- `2026-05-06--claude_md_stale_extract.md`
- `2026-05-06--readme_stale_extract.md`
- `2026-05-06--todo_completed_extract.md`
- `2026-05-07--todo_v12_agent_openclaw_replan_archive.md`
- `2026-05-09--claude_md_section5_pre_alpha_surface.md`
- `2026-05-09--qctodo_sprint_n0_n5_archive.md`
- `2026-05-09--w_audit_verified_closed_archive.md`
- `2026-05-09--w_audit_verified_closed_archive_v2.md`
- `2026-05-09--w_audit_verified_closed_archive_v3.md`
- `2026-05-15--todo_v21_completion_cleanup_archive.md`
- `2026-05-15--todo_v24_stale_rows_archive.md`
- `2026-05-16--close_maker_first_phase_1b_round1_archive.md`
- `2026-05-16--stage1_demo_a4c_tombstone_cleanup.md`
- `2026-05-16--todo_v36_completion_cleanup_archive.md`
- `2026-05-17--cold_audit_pm_final.md`
- `2026-05-19--todo_v55_translation_archive.md`
- `2026-05-20--todo_v57_3_closure_cleanup_archive.md`
- `2026-05-21--sprint_1a_alpha_repair_closure.md`
- `2026-05-21--todo_v57_5_route_change_purge.md`
- `2026-05-21--todo_v58_layout_refactor_archive.md`
- `2026-05-21--todo_v60_archive.md`
- `2026-05-23--gui_bybit_first_pnl_refactor.md`
- `2026-05-23--sprint_4plus_5plus_wave1_closure.md`
- `2026-05-29--cold_audit_p1_p2_p3_closure_archive.md`
- `2026-05-30--cold_audit_pm_final.md`
- `2026-05-31--todo_v92_archive.md`
- `2026-05-31--todo_v93_pre_aeg_cleanup_archive.md`
- `2026-06-03--todo_v110_pre_cleanup_archive.md`
- `2026-06-05--l2_advisory_mesh_todo.md`
- `2026-06-10--skills_todo_audit_closed.md`
- `2026-07-04--todo_v738_pre_slim_archive.md`
- `2026-07-09--api_gui_handoff_2026-03-25/`
- `2026-07-09--governance_dev_phase_history/`
- `2026-07-09--gui_baseline_pre_redesign_manifest.md`
- `2026-07-09--legacy_62finding_audit_bundle/`
- `2026-07-09--rust_migration_completed/`
- `2026-07-09--worklogs_2026-04/`
- `README.md`

---

## 强制规则 (Mandatory Rules)

**任何人（包括 AI Agent）向 docs/ 写入或新增文件时，必须遵守以下规则：**

1. **文件必须放到对应分类目录**，不允许直接扔在 `docs/` 根目录
2. **文件名必须遵守命名规范**（见下方"文件命名规范"）
3. **每次新增/移动重要文件后，必须更新 `_indexes/document_index.md` 或对应主题索引**
4. **不允许重复文件**：放入前检查是否已有相同内容的文件
5. **日志必须人类可读**：简洁、清晰、有上下文，中文为主 + 英文辅助
6. **禁止纯 JSON dump 或代码输出当日志**：日志是写给人看的

---

## 目录结构 (Directory Structure)

```
docs/
├── README.md                          ← 本文件（目录总览 + 规范 + 索引入口）
├── KNOWN_ISSUES.md                    ← 已知问题清单（根层参考檔）
├── lessons.md                         ← 教训沉淀（根层参考檔）
├── CLAUDE_REFERENCE.md                ← 从 CLAUDE.md 迁出的按需参考（STALE 快照，见檔头 banner）
│
├── worklogs/                          ← 工作日志（顶层为现役；歷史 phase packet 已歸檔 archive/）
│   └── （顶层文件）                   ← 2026-04-08+ 最新工作日志（直接放根目录；歷史 phase packet 見 "Phase Packet Archive Index" 段）
│
├── handoffs/                          ← 阶段交接文档（按日期+主题分文件夹）
│   └── YYYY-MM-DD_主题名/
│
├── decisions/                         ← 重大架构/设计决策记录 + 治理源文件（DOC/SM/EX .docx）
├── adr/                               ← 架构决策记录（ADR；最新编号见 docs/adr/ 与 SPECIFICATION_REGISTER）
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
├── research/                          ← 研究判准正本（预注册/冻结统计判准；先落档冻结、后跑分析）
│
├── archive/                           ← 已归档/过期文档（DEPRECATED 文件、旧版摘要）
│
├── CCAgentWorkSpace/                  ← Agent 工作空间（profile/memory/workspace per agent）
├── agents/                            ← Agent context loading / TODO maintenance / issue tracker / domain / triage-label 指南
│
├── execution_plan/                    ← 执行计划（Sprint/Wave 排期、里程碑规划；56 现役文件留在本目录）
│   ├── gui_redesign/                  ← GUI 大修工作流（working doc + design/ 四規格 + tokens.css + 樣品；2026-07-10 玄衡儀裁決版）
│   └── (已归档 2026-07-09) 101 个 v5.8 已完结 spec/phase → archive/2026-07-09--execution_plan_v58_closed/
│
├── (已归档 2026-07-09) rust_migration/ → archive/2026-07-09--rust_migration_completed/  ← Rust 迁移文档（迁移完结）
│
└── governance_dev/                    ← 治理开发文档（现役：amendments/ + SPECIFICATION_REGISTER + 根层文件）
    ├── amendments/                    ← 仍 Active spec amendments（正式规范修订记录）
    ├── SPECIFICATION_REGISTER.md      ← 仍 Active spec 索引
    ├── DEPRECATED.md / NAMING_NOTE.md ← 退役口径 + 命名约束
    ├── 2026-03-30--round2_fix_plan*   ← Round 2 修复计划（Batch 7-12）
    └── (已归档 2026-07-09) phase0..12 / changelogs / governance_extracts / audits
        → archive/2026-07-09--governance_dev_phase_history/<同名子目录>/
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

同日多份同类文档（PM proposal 2026-05-27 治理 amendment）：

```
YYYY-MM-DD-N--功能描述.扩展名     # N=1,2,3...，優先於 HHmm，git mtime 已記時分
```

规则：
- **日期在前**：便于按时间排序，一目了然
- **双横线 `--` 分隔**：日期与描述之间、时间与描述之间
- **功能描述用下划线或连字号连接均可**：同一批文件保持一致；避免空格以保路径兼容（hyphen-desc 为 accepted practice，如 `2026-04-29--62finding-batch-A-to-F.md`）。role-infix（如 `--tw_` / `--r4_`）命名跨轮不强制统一，以文件内容为准。
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

- `2000_line_exception_registry.md` — CLAUDE.md §七/§九 2000 行硬上限的
  documented pre-existing exception 正本（超标生产档路径+行数+拆分归属）。

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

详细文档索引已迁出到 `_indexes/document_index.md`，避免本入口文件重新膨胀成历史长表。

新增文档时：

1. 仍按本文件的目录/命名/书写规则放置。
2. 重要交付、结论性报告、迁移记录更新 `_indexes/document_index.md`。
3. 跨主题、会影响后续 agent 路由的入口更新 `_indexes/initiative_index.md`。
4. 移动/重命名路径前先更新 `_indexes/path_redirects.md`，并保留 redirect stub。

> 当前 active state 不进文档索引；请更新根目录 `TODO.md`。
