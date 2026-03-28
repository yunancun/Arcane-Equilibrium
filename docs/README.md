# docs/ — 项目文档目录 (Project Documentation Directory)

本目录存放 OpenClaw / Bybit AI Agent 交易系统的所有工程文档、日志、交接记录和决策备忘。

This directory holds all engineering documents, logs, handoff records, and decision memos for the OpenClaw / Bybit AI Agent trading system.

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
│   ├── control_api_gui/               ← Control API + GUI Operator Console 开发
│   └── learning/                      ← L 章节：自动学习管线 / 安全加固
│
├── handoffs/                          ← 阶段交接文档（按日期+主题分文件夹）
│   └── YYYY-MM-DD_主题名/
│
├── decisions/                         ← 重大架构/设计决策记录
│
├── incidents/                         ← 故障/异常事件记录（待填充）
│
└── references/                        ← 长期参考文档（规范、合同、规格书）
    ├── state_dictionary/              ← 状态字典 / 数据字典
    ├── api_contract/                  ← API 合同 / 路由草案 / 审核报告
    └── api_stub/                      ← API 骨架代码
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

### 4. incidents/ — 故障/异常记录

**用途**：记录生产或开发环境中的故障、异常事件及处理过程。

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
| `2026-03-22--项目总报告_含github核对.md` | 项目总报告（含 GitHub 核对，md 版） |
| `2026-03-22--项目总报告_含github核对.txt` | 项目总报告（含 GitHub 核对，txt 版） |
| `2026-03-22--夜间_最终整合总报告.txt` | 夜间最终整合总报告 |
| `2026-03-22--夜间_github迁移与诊断报告.txt` | GitHub 迁移与夜间诊断报告 |
| `2026-03-22--夜间_新对话接手prompt_github版.txt` | 新对话接手 Prompt（GitHub 工作流版） |
| `2026-03-24--工程总报告_结构迁移完成.txt` | 工程总报告：结构迁移完成 + 新工作流 |
| `2026-03-24--交接日志.txt` | 03-24 晚交接日志 |
| `2026-03-24--新对话启动prompt.txt` | 新对话启动 Prompt |
| `2026-03-24--work_report_current_dialogue.txt` | 当前对话工作报告（txt） |
| `2026-03-24--work_report_current_dialogue.md` | 当前对话工作报告（md） |
| `2026-03-24--work_report_current_dialogue.pdf` | 当前对话工作报告（pdf） |

### worklogs/control_api_gui/ — Control API + GUI 开发日志（2026-03-25 ~ 2026-03-26）

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

### worklogs/learning/ — L 章学习系统开发日志（2026-03-26）

| 文件 | 内容 |
|------|------|
| `2026-03-26--L章_自动学习管线与安全加固_完整工程日志.md` | L 章自动学习管线 + 安全加固全量工程日志（含审核包设计、96 测试、8 项安全修复） |

### handoffs/ — 阶段交接文档

| 路径 | 内容 |
|------|------|
| `2026-03-25_api_gui_handoff/` | Control API v1 + GUI v1 阶段交接（含 12 份文档 + source_docs） |

### decisions/ — 架构/设计决策记录

| 文件 | 内容 |
|------|------|
| `2026-03-17--工程一审修改建议报告_终稿.md` | Revision 2 工程一审修改建议报告（md 终稿） |
| `2026-03-17--工程一审修改建议报告_终稿.txt` | Revision 2 工程一审修改建议报告（txt 终稿） |
| `2026-03-20--关于h和i部分的核心设计讨论.txt` | H-I 核心设计讨论（AI 成本均衡 / 本地计算 / 延迟框架 / 设备容错） |

### references/ — 长期参考文档

| 文件 | 内容 |
|------|------|
| **state_dictionary/** | |
| `状态字典_数据字典_v1_最终版.md` | 状态字典 / 数据字典 V1 最终版（1149 行） |
| `状态字典_v1_rc2_伴随补丁.md` | 状态字典 V1 RC2 伴随补丁 |
| **api_contract/** | |
| `control_api_v1_最终定稿.md` | Control API V1 最终定稿（1008 行） |
| `control_api_v1_rc2_最终候选版.md` | Control API V1 RC2 最终候选版 |
| `control_api_v1_rc2_审核报告.md` | Control API V1 RC2 审核报告 |
| `fastapi_openapi_v1_rc2_路由草案.md` | FastAPI / OpenAPI V1 RC2 路由草案 |
| `后端实现清单_v1_rc2.md` | 后端实现清单 V1 RC2 |
| **api_stub/** | |
| `control_api_v1_rc2_fastapi_stub.py` | FastAPI 骨架代码（553 行） |
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
| `2026-03-27--phase2_round2_strategic_audit_report.md` | Phase 2 第二轮审核：实战适用性审核（策略盈利性/管线连通性/数据质量/风控集成/信号可靠性） |
| `2026-03-27--remote_access_guide.md` | 远程访问完整指南：Tailscale 安装配置 + Bybit Demo 访问地址 + secrets 权限加固 |
