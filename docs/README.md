# docs/ — 项目文档目录 (Project Documentation Directory)

本目录存放 OpenClaw / Bybit AI Agent 交易系统的所有工程文档、日志、交接记录和决策备忘。

This directory holds all engineering documents, logs, handoff records, and decision memos for the OpenClaw / Bybit AI Agent trading system.

---

## 目录结构规范 (Directory Structure)

```
docs/
├── README.md                          ← 本文件（目录总览与规范说明）
├── handoffs/                          ← 阶段交接文档（按日期+主题分文件夹）
│   └── YYYY-MM-DD_主题名/
├── worklogs/                          ← 工作日志（按模块分子目录）
│   ├── control_api/
│   ├── gui/
│   ├── learning/
│   ├── runtime/
│   └── general/
├── decisions/                         ← 重大架构/设计决策记录
│   └── YYYY-MM-DD_决策主题.md
├── incidents/                         ← 故障/异常事件记录
│   └── YYYY-MM-DD_事件简述.md
└── references/                        ← 长期参考文档（规范、合同、规格书）
```

---

## 文件命名规范 (File Naming Convention)

所有文档文件统一使用以下格式：

```
YYYY-MM-DD--HHmm--功能描述.md
```

示例：
```
2026-03-25--1430--control_api_rc2_合同审核.md
2026-03-26--0900--l_chapter_observation_feed_实现.md
2026-03-26--1715--net_pnl_dashboard_gui_调试记录.md
```

规则：
- **日期在前**：便于按时间排序，一目了然
- **时间可选**：如果同一天只有一份文档，可省略 `--HHmm` 部分
- **功能描述用下划线连接**：避免空格，保持路径兼容性
- **扩展名统一 `.md`**：Markdown 格式，人类可读

---

## 日志分类说明 (Log Categories)

### 1. handoffs/ — 阶段交接文档

**用途**：一个工程阶段完成后的正式交接记录，供后续开发者或未来的自己快速了解上下文。

**组织方式**：每次交接创建一个子文件夹，命名为 `YYYY-MM-DD_主题名`。

```
handoffs/
└── 2026-03-25_api_gui_handoff/
    ├── API_GUI_STAGE_COMPLETION_README.md    ← 阶段总结
    ├── API_GUI_FULL_ENGINEERING_REPORT.md    ← 完整工程报告
    ├── WORKLOG_2026-03-25.md                ← 当日工作日志
    └── source_docs/                         ← 相关源文档
```

### 2. worklogs/ — 工作日志

**用途**：日常开发过程中的工作记录。简洁、清晰、人类可读。

**组织方式**：按模块分子目录，文件按日期命名。

```
worklogs/
├── control_api/
│   ├── 2026-03-25--api_endpoint_实现.md
│   └── 2026-03-26--product_family_config_写接口.md
├── learning/
│   ├── 2026-03-26--l_chapter_api_layer_实现.md
│   └── 2026-03-27--agent_auto_pipeline_设计.md
└── general/
    └── 2026-03-26--branch_合并_清理.md
```

### 3. decisions/ — 决策记录

**用途**：记录重大架构或设计决策的背景、选项、结论和理由。

**格式建议**：
```markdown
# 决策：<标题>
日期：YYYY-MM-DD
状态：已决定 / 待讨论 / 已废弃

## 背景 (Context)
为什么需要做这个决策？

## 选项 (Options)
1. 方案 A — ...
2. 方案 B — ...

## 结论 (Decision)
选择方案 X，因为...

## 影响 (Consequences)
这个决策会带来什么后果？
```

### 4. incidents/ — 故障/异常记录

**用途**：记录生产或开发环境中的故障、异常事件及处理过程。

**格式建议**：
```markdown
# 事件：<简述>
日期：YYYY-MM-DD HH:mm
严重程度：P0 / P1 / P2 / P3

## 现象 (Symptoms)
## 根因 (Root Cause)
## 处理过程 (Resolution)
## 后续改进 (Follow-up)
```

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

## 现有文档索引 (Existing Documents)

| 路径 | 内容 |
|------|------|
| `handoffs/2026-03-25_api_gui_handoff/` | Control API v1 + GUI v1 阶段交接（含完整工程报告、收口清单、工作日志） |
