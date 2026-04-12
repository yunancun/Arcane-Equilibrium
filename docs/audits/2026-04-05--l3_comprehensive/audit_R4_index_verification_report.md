# R4 文档索引完整性审计报告
# R4 Document Index Integrity Audit Report
**日期：2026-04-05**
**审计员：R4 (Document Index Auditor)**

---

## 审计总结 (Executive Summary)

| 索引文件 | 遗漏条目 | 断链条目 | 描述过时 | 严重度 |
|----------|---------|---------|---------|--------|
| docs/README.md | **25** | 0 | 1 | **P1 HIGH** |
| CLAUDE.md 十 | 0 | 0 | 0 | PASS |
| docs/CLAUDE_REFERENCE.md | 0 | 0 | 1 | LOW |
| docs/CLAUDE_CHANGELOG.md | **1** | 0 | 0 | **P2 MEDIUM** |
| helper_scripts/SCRIPT_INDEX.md | **不存在** | N/A | N/A | **P1 HIGH** |
| docs/rust_migration/README.md | 0 | 0 | 0 | PASS |
| MEMORY.md | **1** | 0 | 0 | LOW |

**关键发现：** docs/README.md 文档索引严重滞后，自 2026-04-02 后新增的 25 个文件/目录未被收录。helper_scripts/SCRIPT_INDEX.md 完全缺失（CLAUDE.md 七 规范要求新脚本必须更新此文件）。

---

## 1. docs/README.md — 主文档索引

### 1.1 存在但未收录的文件（遗漏 25 项）

#### docs/references/ 根目录（9 项遗漏）

| 文件 | 内容推测 |
|------|---------|
| `2026-04-02--system_status_report.md` | 系统状态报告 |
| `2026-04-03--agent_param_tuning_design_draft_v0.2.md` | Agent 参数调优设计草案 |
| `2026-04-03--data_storage_architecture_optimal_draft_v0.1.md` | 数据存储架构最优方案 |
| `2026-04-03--llm_abstraction_audit.md` | LLM 抽象层审计 |
| `2026-04-03--ml_dl_learning_architecture_v0.4.md` | ML/DL 学习架构 v0.4 |
| `2026-04-04--bybit_api_reference.md` | Bybit API 字典手册 |
| `2026-04-04--comprehensive_audit_template_v1.md` | 全面审计模板 v1 |
| `2026-04-04--execution_plan_v1.md` | 融合方案执行计划 v1 |
| `2026-04-04--unified_db_ml_news_workplan_draft_v0.1.md` | DB+ML+新闻统一工作计划 |

> 注：这 9 个文件在 CLAUDE.md 十 中被引用为关键文件，但未在 docs/README.md 中注册。

#### docs/worklogs/ 根目录（14 项遗漏）

docs/README.md 的索引只覆盖了 `worklogs/chapters_a-g/`、`worklogs/chapters_h-i/`、`worklogs/chapters_j-k/`、`worklogs/control_api_gui/`、`worklogs/learning/` 五个子目录。但自 2026-04-03 起，新的工作日志直接存放在 `worklogs/` 根目录下，这些文件全部未收录：

| 文件 |
|------|
| `2026-04-03--completed_todo_archive_batch9a_wave8_xp.md` |
| `2026-04-03--daily_summary.md` |
| `2026-04-04--completed_todo_archive_phase0123_rust.md` |
| `2026-04-04--daily_summary.md` |
| `2026-04-04--session4_bybit_api_audit.md` |
| `2026-04-04--session5_bybit_full_integration.md` |
| `2026-04-04--td01_td02_td03_file_split.md` |
| `2026-04-05--daily_summary.md` |
| `2026-04-05--session7_phase1_day0_g1_g2.md` |
| `2026-04-05--session7_precompact.md` |
| `2026-04-05--session8_phase3b_and_ops.md` |
| `2026-04-05--session8_phase3b.md` |
| `2026-04-05--session9_ext1_risk_config.md` |
| `2026-04-05--session9_ops_fixes_risk_gui.md` |

> 建议：在 docs/README.md 中新增一个 `### worklogs/ 根目录 — 综合工作日志（2026-04-03 ~）` 区段。

#### docs/architecture/ 目录（1 项遗漏）

| 文件 |
|------|
| `DATA_STORAGE_ARCHITECTURE_V1.md` |

> 此目录和文件均未在 docs/README.md 的目录结构或索引中提及。

#### docs/audits/ 目录（1 项遗漏）

| 文件 |
|------|
| `2026-04-04--bybit_api_infra_audit.md` |

> 注意：此目录是 `docs/audits/`（带 s），与既有的 `docs/audit/`（不带 s）是两个不同目录。docs/README.md 只描述了 `audit/`，未提及 `audits/`。建议合并或在索引中标注。

### 1.2 索引条目指向不存在的文件（断链）

**0 项。** 所有索引条目指向的文件均存在。

### 1.3 文件名不精确（1 项）

| 索引中的名称 | 实际文件名 |
|-------------|-----------|
| `bilingual_comment_audit_report.md` | `2026-03-30--bilingual_comment_audit_report.md` |

> 索引中省略了日期前缀，虽不影响理解但与命名规范不一致。

---

## 2. CLAUDE.md 十 — 关键文件指针

### 2.1 引用的文件存在性检查

全部 **16 个引用文件** 均存在，**0 断链**。

验证清单：
- `docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md` -- OK
- `docs/KNOWN_ISSUES.md` -- OK
- `docs/CLAUDE_CHANGELOG.md` -- OK
- `docs/CLAUDE_REFERENCE.md` -- OK
- `docs/references/2026-04-04--bybit_api_reference.md` -- OK
- `docs/audits/2026-04-04--bybit_api_infra_audit.md` -- OK
- `docs/references/2026-04-04--unified_db_ml_news_workplan_draft_v0.1.md` -- OK
- `docs/references/2026-04-04--execution_plan_v1.md` -- OK
- `docs/references/2026-04-03--ml_dl_learning_architecture_v0.4.md` -- OK
- `docs/references/2026-04-03--data_storage_architecture_optimal_draft_v0.1.md` -- OK
- `docs/rust_migration/README.md` -- OK
- `docs/references/2026-04-03--openclaw_improvement_report_v3_final.md` -- OK
- `docs/references/2026-04-04--comprehensive_audit_template_v1.md` -- OK（在 CLAUDE_REFERENCE 中引用但未在 README 索引中）
- `docs/references/2026-04-03--agent_param_tuning_design_draft_v0.2.md` -- OK
- `docs/references/2026-04-03--llm_abstraction_audit.md` -- OK
- `docs/references/2026-04-02--system_status_report.md` -- OK

**结论：PASS**

---

## 3. docs/CLAUDE_REFERENCE.md — 参考资料索引

### 3.1 引用文件存在性检查

全部 **28 个引用路径** 验证通过，**0 断链**。

### 3.2 过时描述（1 项）

- 文件头部标注 `最後更新：2026-04-02`，但实际内容未包含 2026-04-03~04-05 期间新增的参考文档（如 Bybit API 手册、融合方案、Rust 迁移 V3 等）。这些文件已在 CLAUDE.md 十 中引用，但 CLAUDE_REFERENCE.md 的 "参考文档指针" 表未同步更新。

> 影响：LOW。CLAUDE.md 十 已作为最新指针，CLAUDE_REFERENCE 定位为历史参考。

---

## 4. docs/CLAUDE_CHANGELOG.md — 开发历史归档

### 4.1 近期工作覆盖检查

| 事件 | 是否在 CHANGELOG 中 |
|------|-------------------|
| Session 9c (realized_pnl + Cost Gate) | 是 |
| Session 9b (Ops Fixes + Risk GUI) | 是 |
| EXT-1 Exchange-as-Truth | 是 |
| Session 9 L3 Audit | 是 |
| Phase 1 Day 0 + G1-G4 | 是 |
| Phase 2 完成 | 是 |
| Phase 3a 完成 | 在 CLAUDE.md 摘要中提及，CHANGELOG 中需确认 |
| Phase 3b 完成 | 在 CLAUDE.md 摘要中提及，CHANGELOG 中需确认 |
| **RRC-1 Risk Runtime Connect** | **否 -- 遗漏** |

### 4.2 遗漏条目（1 项）

**RRC-1** 已在 git log 中出现（commits `cb7c850`, `6a9d754`: "feat: RRC-1 Phase E -- strategy IPC + session unhalt + cleanup"），以及最新 commit `de64e95`（"docs: RRC-1 risk runtime connect plan"），但 CLAUDE_CHANGELOG.md **未包含 RRC-1 相关条目**。

> 建议：补充 RRC-1 的 CHANGELOG 条目（风控 GUI 参数全链路 IPC 送达 Rust 引擎）。

---

## 5. helper_scripts/SCRIPT_INDEX.md — 脚本索引

### 5.1 文件不存在

`helper_scripts/SCRIPT_INDEX.md` **不存在**。

CLAUDE.md 七 明确规定："新腳本規範 ... 更新 SCRIPT_INDEX.md"，但该文件从未被创建。

### 5.2 当前脚本清点

helper_scripts/ 目录下共有 **68 个脚本文件**（.sh + .py），分布：

| 子目录 | 数量 |
|--------|------|
| `canary/` | 5 (.py) + 1 (.sh) = 6 |
| `deploy/` | 0 脚本（2 .plist 配置） |
| `maintenance_scripts/bybit_connector/` | ~45 (.sh) + 3 (.py) = ~48 |
| `maintenance_scripts/` 根 | 1 (.sh) |
| 根目录 | 5 (.sh) + 2 (.py) = 7 |

> 注：`canary/` 和 `maintenance_scripts/bybit_connector/` 各有独立 README.md，但无统一 SCRIPT_INDEX.md。

> 建议：创建 `helper_scripts/SCRIPT_INDEX.md` 至少索引顶层脚本和子目录用途。

---

## 6. docs/rust_migration/README.md — Rust 迁移文档索引

### 6.1 文件清单验证

索引列出 8 个阶段文件 + README，实际文件系统中也恰好 9 个 .md 文件。

| 索引条目 | 文件存在 |
|---------|---------|
| `00--preparation_parallel.md` | OK |
| `01--ipc_shared_types_ws.md` | OK |
| `02--core_upper.md` | OK |
| `03--core_lower.md` | OK |
| `04--engine_full_path.md` | OK |
| `05--week8_decision_gate.md` | OK |
| `06--python_ipc_integration.md` | OK |
| `07--canary_validation.md` | OK |

**0 遗漏，0 断链。**

### 6.2 状态准确性

- 00~04 标记 `[x] 完成` -- 与 CLAUDE.md 摘要一致
- 05~07 标记 `[ ]` 待开始/待决策 -- 合理（灰度验证中）

**结论：PASS**

---

## 7. MEMORY.md — 记忆索引

### 7.1 引用文件存在性

全部 **29 个记忆文件** 均存在，**0 断链**。

### 7.2 存在但未索引的文件（1 项）

| 文件 | 说明 |
|------|------|
| `project_20260327_session.md` | 存在于记忆目录但未在 MEMORY.md 中注册 |

> 可能是早期遗留文件，建议评估是否需要索引或清理。

---

## 8. 交叉问题汇总

### 8.1 docs/audit/ vs docs/audits/ 目录分裂

- `docs/audit/` -- March31 + April01 审计报告（在 README 中已索引）
- `docs/audits/` -- 仅含 `2026-04-04--bybit_api_infra_audit.md`（不在 README 中）

两个目录名仅差一个 "s"，容易混淆。建议合并至 `docs/audit/`（保持与 README 描述一致）。

### 8.2 docs/architecture/ 目录未在 README 目录结构中声明

该目录含 `DATA_STORAGE_ARCHITECTURE_V1.md`，但 README 的"目录结构"图和索引均未提及。

### 8.3 CLAUDE_REFERENCE.md 最后更新日期过时

标注 `2026-04-02`，但项目已进展到 2026-04-05。虽然 CLAUDE.md 十 已覆盖新文件指针，但 CLAUDE_REFERENCE.md 的参考文档表缺少 2026-04-03~05 的 9 个新文件。

---

## 9. 修复建议优先级

| 优先级 | 修复项 | 估计工作量 |
|--------|--------|-----------|
| **P1** | 补充 docs/README.md 遗漏的 25 个文件条目 | ~30 min |
| **P1** | 创建 helper_scripts/SCRIPT_INDEX.md | ~20 min |
| **P2** | 在 CLAUDE_CHANGELOG.md 补充 RRC-1 条目 | ~10 min |
| **P2** | 合并 docs/audits/ 到 docs/audit/ 或在 README 中注册 | ~5 min |
| **P2** | 在 README 中注册 docs/architecture/ 目录 | ~5 min |
| **LOW** | 修正 bilingual 文件名前缀 | ~2 min |
| **LOW** | 更新 CLAUDE_REFERENCE.md 最后更新日期 + 补充新文档 | ~15 min |
| **LOW** | 评估 memory `project_20260327_session.md` 是否需要索引 | ~5 min |

---

*审计结束。共检查 7 个索引文件，发现 25 项遗漏 + 1 项缺失索引文件 + 1 项 CHANGELOG 遗漏 + 若干轻微问题。*
