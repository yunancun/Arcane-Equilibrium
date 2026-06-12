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
| agent 启动路由 | `agents/context-loading.md` |
| 主题证据导航 | `_indexes/initiative_index.md` |
| 路径迁移 / redirect 记录 | `_indexes/path_redirects.md` |
| 版本增量历史 | `CLAUDE_CHANGELOG.md` |
| 历史归档 | `archive/` |
| 角色报告 | `CCAgentWorkSpace/*/workspace/reports/` |

## Multi-Agent 接手路径

| 任务类型 | 必读入口 | 读取边界 |
|---|---|---|
| 接手 active work / 判断是否能开工 | `../TODO.md` | 只把这里当当前 owner、gate、next action 权威。 |
| 找某个主题的设计和证据 | `_indexes/initiative_index.md` | 按主题进设计、报告、archive；不要从长索引反推 active 状态。 |
| 查历史文档或近期交付清单 | `_indexes/document_index.md` | 历史/导航用途；不是 active queue。 |
| 查审计证据 | `_indexes/audit_index.md` | 先确认 `TODO.md` 是否仍 active，再读 audit/report。 |
| 写新文档 / 移动路径 | 本文件 + `_indexes/path_redirects.md` | 先分类和命名；移动前保留 redirect/stub 计划。 |
| 读取 role report | `CCAgentWorkSpace/README.md` | report 是证据；最终当前状态仍回到 `TODO.md`。 |
| 执行 runbook / 操作手册 | `runbooks/README.md` | runbook 不是授权；运行态操作先看 `TODO.md` operator actions。 |
| 查架构背景 | `architecture/README.md` + `../README.md` | 旧架构文档可能是 reference，读 banner 和当前 ADR/AMD。 |

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
│
├── worklogs/                          ← 工作日志（顶层为现役；歷史 phase packet 已歸檔 archive/）
│   └── （顶层文件）                   ← 2026-04-08+ 最新工作日志（直接放根目录；歷史 phase packet 見 "Phase Packet Archive Index" 段）
│
├── handoffs/                          ← 阶段交接文档（按日期+主题分文件夹）
│   └── YYYY-MM-DD_主题名/
│
├── decisions/                         ← 重大架构/设计决策记录 + 治理源文件（DOC/SM/EX .docx）
├── adr/                               ← 架构决策记录（ADR 0001-0047）
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
├── agents/                            ← Agent context loading / TODO maintenance / issue tracker / domain / triage-label 指南
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

同日多份同类文档（PM proposal 2026-05-27 治理 amendment）：

```
YYYY-MM-DD-N--功能描述.扩展名     # N=1,2,3...，優先於 HHmm，git mtime 已記時分
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

详细文档索引已迁出到 `_indexes/document_index.md`，避免本入口文件重新膨胀成历史长表。

新增文档时：

1. 仍按本文件的目录/命名/书写规则放置。
2. 重要交付、结论性报告、迁移记录更新 `_indexes/document_index.md`。
3. 跨主题、会影响后续 agent 路由的入口更新 `_indexes/initiative_index.md`。
4. 移动/重命名路径前先更新 `_indexes/path_redirects.md`，并保留 redirect stub。

> 当前 active state 不进文档索引；请更新根目录 `TODO.md`。
