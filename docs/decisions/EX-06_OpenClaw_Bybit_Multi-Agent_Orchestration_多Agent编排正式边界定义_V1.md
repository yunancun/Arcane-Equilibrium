# OpenClaw / Bybit 交易 Agent

# Multi-Agent Orchestration

# 多 Agent 编排正式边界定义 V1

## 2026-05-06 权威澄清 / Authoritative Clarification

本文件保留为历史治理设计，但其中「OpenClaw 作为 Conductor + Ops」的早期解释已被 2026-05-06 架构覆写。

当前权威定位见：

- `docs/architecture/2026-05-06--openclaw_control_plane_repositioning.md`
- `docs/execution_plan/2026-05-06--openclaw_gateway_development_plan.md`
- `docs/execution_plan/2026-05-06--gui_openclaw_control_console_plan.md`

新的边界：

- 本地 5-Agent（Scout / Strategist / Guardian / Analyst / Executor）保持在 TradeBot FastAPI + Postgres + Rust engine 栈内，不迁入外部 OpenClaw runtime。
- 外部 OpenClaw Gateway 只作为通信、移动端入口、上级汇总、云模型升级、proposal/approval relay；不得成为交易决策权威或第二 GUI。
- `trade-core:8000/console` 是唯一 canonical GUI，后续命名为 OpenClaw Control Console。
- `MessageBus` 是 legacy/advisory local trace，不是新的 Agent Decision Spine 权威对象通信层。

后续实现和评审若与本文件旧表述冲突，以 2026-05-06 架构覆写为准。


## 0. 文档定位 Document Positioning

本文件定义 OpenClaw / Bybit 交易 Agent 的 Multi-Agent 协作架构。

本文件回答以下问题：

- 系统有哪些 Agent？各自职责边界是什么？

- 历史设想中 OpenClaw 作为 Conductor 的具体职责和权限是什么？（2026-05-06 后仅作历史参考）

- Agent 之间如何通信？冲突如何仲裁？

- 在资源受限阶段，多 Agent 如何退化运行？

- 与现有 H0→H5→I→Risk→OMS 链路如何映射？

如与《项目宪法》冲突，以宪法为最高约束。


## 1. 架构总览 Architecture Overview

**历史视图：OpenClaw（Conductor + Ops 角色，2026-05-06 后已 superseded）
  ├── Scout Agent（情报）
  ├── Strategist Agent（策略）
  ├── Guardian Agent（风控）
  ├── Analyst Agent（进化）
  └── Executor Agent（执行）
H0 门控（始终独立，零成本本地确定性）**

核心设计原则：

- OpenClaw 是中央编排器，不是独立的第 6 个 Agent——它利用已有的 Multi-Agent routing、Cron、web-pilot、Memory 等能力统一协调

- H0 门控始终独立于所有 Agent，任何 Agent 的交易意图必须先通过 H0

- 每个 Agent 有明确的职责边界，不得越界操作

- Agent 之间通过结构化对象通信，不通过自由文本

## 2. 历史方案：OpenClaw 编排器 / Historical OpenClaw as Conductor

### 2.1 定位

历史方案曾设想 OpenClaw 不是一个独立的交易 Agent，而是所有 Agent 的编排层，利用 OpenClaw 已有的平台能力承担 Conductor + Ops 双重角色。该解释已被 2026-05-06 架构覆写：外部 OpenClaw Gateway 只作通信 / mobile / supervisor / proposal relay，本地 Conductor 与 5-Agent runtime 留在 TradeBot 内部。


### 2.2 利用的 OpenClaw 已有能力

| **OpenClaw 能力** | **在交易系统中的用途** |
|---|---|
| Multi-Agent routing（隔离工作空间） | Scout / Strategist / Guardian / Analyst / Executor 各自独立工作空间 |
| Cron + Heartbeat 定时 | 驱动 L1 每 5 分钟 regime 扫描、每 30 分钟新闻搜索、每日报告 |
| web-pilot 网页搜索/抓取 | 驱动 Scout Agent 的新闻搜索和情报收集 |
| Memory 向量检索 | 驱动 Analyst Agent 的知识库（历史模式、学到的教训） |
| Telegram 通信通道 | 告警推送（止损触发、异常事件、日报） |
| Canvas A2UI 实时渲染 | 历史设想；2026-05-06 后排除为 canonical GUI 路径，现有 FastAPI console 是唯一 GUI |
| 51 内置 skill | 历史设想；后续第三方 skill 必须安全审查，不能接触交易 secrets |


### 2.3 Conductor 职责

- 任务分发：接收市场事件，决定哪个 Agent 需要介入

- 冲突仲裁：当 Strategist 想开仓但 Guardian 说收紧时，按优先级裁决

- 资源分配：管理 AI 计算预算在 Agent 间的分配

- Agent 生命周期管理：启动、健康检查、降级、重启

- Ops 职责：系统健康监控、基础设施告警、Telegram 推送


### 2.4 Conductor 不可以做的事

- 不可以直接下单（必须通过 Executor → 统一执行入口）

- 不可以覆盖 Guardian 的风控否决（Guardian 优先于 Strategist）

- 不可以修改 P0/P1 硬上限

- 不可以绕过 H0 门控


## 3. Scout Agent 情报 Agent

### 3.1 职责

Scout 是系统的"眼睛和耳朵"，负责感知外部世界的信息。

- 新闻搜索：每 30 分钟通过搜索降级体系扫描 crypto 新闻

- 事件日历：维护结构化的 crypto 事件日历（Token Unlock / 上币 / 协议升级 / FOMC / CPI）

- 情绪分析：解析搜索结果，打分为 positive / negative / neutral

- 交易所异常监控：大额清算 / funding rate 异常飙升 / OI 突变


### 3.2 输出对象

- intel_object：结构化情报对象，包含 source / timestamp / freshness / fact_or_inference / sentiment_score / relevance_score

- event_alert：重大事件告警（FOMC 前 2 小时、Token Unlock 前 24 小时等）


### 3.3 Scout 不可以做的事

- 不产生交易信号（只提供情报，由 Strategist 决定是否交易）

- 不修改风控参数（只通知 Guardian 有重大事件）

- 不直接执行交易所 API 调用


### 3.4 数据质量标记

所有 Scout 输出必须标记认知级别（对齐宪法 §5.10）：

- fact：交易所 API 返回的确定数据（价格、成交量、funding rate）

- inference：基于多个事实推导的结论（情绪趋势、事件影响评估）

- hypothesis：基于有限信息的猜测（市场方向预测）

## 4. Strategist Agent 策略 Agent

### 4.1 职责

Strategist 是系统的"大脑"，负责所有交易决策。

- 币种选择：从 650+ 符号中筛选有结构性机会的币种

- 策略匹配：根据 regime 和币种特征选择最优策略（MA Crossover / Grid / Funding Arb / BB Breakout / 自主孵化策略）

- 参数优化：基于 ATR、波动率、流动性自动设定止损距离/仓位/时间窗

- 组合分配：当同时有多个机会时，决定资源优先级和资金分配

- 时段意识：在不同交易时段调整策略权重


### 4.2 输出对象

- trade_intent：结构化交易意图（symbol / strategy / direction / size / params / confidence / thesis / invalidation_condition）

- portfolio_allocation：策略间资金分配建议


### 4.3 Strategist 不可以做的事

- 不可以绕过 Guardian 风控审查直接下单

- 不可以突破 P0/P1 硬上限

- 不可以在 H0 门控未通过时产生交易意图

- 不可以忽略 Scout 的重大事件告警


## 5. Guardian Agent 风控 Agent

### 5.1 职责

Guardian 是系统的"安全官"，拥有否决权。

- P2 动态风控：在 P0/P1 硬边界内自主调整风控参数

- 组合相关性监控：多个高相关持仓的集中暴露检测

- 事件响应：收到 Scout 的重大事件告警后自主收紧风控

- Max drawdown 监控：session / daily / 全局回撤追踪

- 连续亏损检测：连亏 N 次自动冷却


### 5.2 Guardian 的特殊权限

**Guardian 的风控结论优先于 Strategist 的交易意图。当两者冲突时，Guardian 获胜。**

- 否决权：可否决任何交易意图

- 缩仓权：可要求减少持仓

- 降级权：可触发系统退化到更保守模式

- 熔断权：可触发 CIRCUIT_BREAKER


### 5.3 Guardian 不可以做的事

- 不可以放宽 P0/P1 硬上限（只能在内收紧）

- 不可以直接下单（通知 Executor 执行保护性动作）

- 不可以忽略 H0 门控结论

## 6. Analyst Agent 进化 Agent

### 6.1 职责

Analyst 是系统的"进化引擎"，不只做复盘，更主动发现模式和孵化新策略。


### 6.2 五层进化能力

| **层级** | **名称** | **职责** |
|---|---|---|
| L1 | 被动复盘 | 每笔交易归因（alpha / timing / sizing / execution / cost）、胜率统计、策略排名 |
| L2 | 主动模式发现 | 跨交易、跨策略、跨币种发现系统性模式（如"squeeze 下 MA Crossover 持仓超 14h 亏损概率 75%"） |
| L3 | 假设与实验 | 基于 L2 模式生成可检验假设 → 在 shadow/paper 中设计实验 → 收集结果 |
| L4 | 策略进化 | 参数进化 + 策略权重调整 + 新策略孵化 + 跨策略迁移学习 |
| L5 | 元学习 | 改善学习方式本身：归因模型是否准确？假设生成是否有偏差？ |


### 6.3 策略孵化流程

- Analyst 提出新策略概念（基于 L2 模式发现）

- 在 shadow 环境验证基本可行性

- 在 paper 环境正式验证（满足 DOC-08 §11 闸门条件的子集）

- Paper 验证通过 → 自动进入 live（不需要 Operator 预批准）

- 进入 live 后通知 Operator（事后审计）


### 6.4 Regime 转换预测

- 波动率压缩到极值 → 即将爆发的前兆

- 成交量持续萎缩 + 窄幅 → squeeze 接近临界

- Funding rate 从极端回归 → 趋势可能反转

- 多时间框架 regime 不一致 → 过渡期


### 6.5 Analyst 不可以做的事

- 不可以直接修改 live 配置（通过正式变更流程 DOC-06）

- 不可以直接下单

- 不可以修改 P0/P1 硬上限


## 7. Executor Agent 执行 Agent

### 7.1 职责

Executor 是系统的"手"，专注于"怎么下单最聪明"。它不决定"做不做"，只决定"怎么做"。

- 接收 Strategist 的 trade_intent（经 Guardian 审查通过）

- 选择最优执行方式（limit / market / split / iceberg / TWAP）

- maker 优先策略：非紧急入场用 Post-Only，止盈用限价单

- 对抗性止损管理：硬/软止损、ATR 动态、止损隐身、反猎杀

- 时段意识执行：周末降低频率、session 交接期谨慎

- 订单状态追踪 + 成交回报 + 持仓更新


### 7.2 Executor 不可以做的事

- 不可以自主决定交易方向或币种（只执行被批准的意图）

- 不可以突破 Guardian 设定的仓位上限

- 不可以关闭硬止损

- 不可以绕过统一执行入口

## 8. Agent 间通信协议 Inter-Agent Communication

### 8.1 通信原则

- 所有 Agent 间通信必须通过结构化对象，不通过自由文本

- 每个通信对象必须有 sender / receiver / timestamp / object_type / priority

- 通信对象必须持久化以支持审计


### 8.2 主要通信流

| **发送方 → 接收方** | **对象类型** | **触发条件** |
|---|---|---|
| Scout → Strategist | intel_object | 发现有交易相关性的情报 |
| Scout → Guardian | event_alert | 发现重大风险事件 |
| Strategist → Guardian | trade_intent | 有交易意图待风控审查 |
| Guardian → Strategist | risk_verdict | 审查结论（approved / rejected / modified） |
| Strategist → Executor | approved_intent | 经 Guardian 批准的交易意图 |
| Executor → Analyst | execution_report | 订单执行结果（fill / reject / partial） |
| Executor → Analyst | round_trip_complete | 完整交易闭环结果 |
| Analyst → Strategist | pattern_insight | 发现的系统性模式 |
| Analyst → Guardian | risk_pattern | 发现的风险模式 |
| Analyst → OpenClaw | strategy_proposal | 新策略孵化提案 |
| OpenClaw → All | system_directive | 系统级指令（降级、恢复、配置变更） |


## 9. 冲突仲裁规则 Conflict Resolution

当 Agent 之间产生冲突时，按以下优先级裁决：


| **冲突场景** | **裁决规则** |
|---|---|
| Strategist 想开仓，Guardian 说收紧 | Guardian 获胜——风控优先于盈利 |
| Scout 报告重大利空，Strategist 仍想做多 | Guardian 介入，至少收紧风控参数 |
| Analyst 建议调整参数，Strategist 不同意 | Analyst 建议记录但不强制——Strategist 有策略自主权 |
| Executor 报告滑点异常，Guardian 要熔断 | Guardian 获胜——可触发 CIRCUIT_BREAKER |
| 多个 Agent 同时请求 AI 计算资源 | OpenClaw 按优先级分配：Guardian > Scout(urgent) > Strategist > Analyst > Scout(routine) |

**核心原则：Guardian 的风控结论永远优先于 Strategist 的交易意图。安全 > 收益。**

## 10. 资源受限模式 Resource-Constrained Mode

在预算不足或系统资源紧张阶段，多 Agent 角色可由同一个本地 Ollama 模型通过不同 prompt 切换扮演。


### 10.1 单 Ollama 多角色模式

- 一个 Qwen2.5 7B 实例通过不同 system prompt 扮演 Scout / Strategist / Guardian / Analyst 角色

- Executor 始终由本地确定性代码实现（不需要 LLM）

- H0 始终由本地确定性代码实现（不需要 LLM）

- 角色切换有开销（context switch），不适合高频交互——适合每个角色每 5 分钟运行一次


### 10.2 职责边界不因资源模式而模糊

即使由同一个模型扮演，Scout 的输出仍然必须是 intel_object，Strategist 的输出仍然必须是 trade_intent，Guardian 的输出仍然必须是 risk_verdict。结构化对象的边界不变。


### 10.3 升级路径

- 阶段一：单 Ollama 多角色（零外部成本）

- 阶段二：Ollama + 低成本云端混合（Scout 用 Perplexity 搜索，其他角色本地）

- 阶段三：关键角色用云端模型（Strategist 用 Sonnet，Guardian 用 Haiku 快速判断）

- 阶段四：各 Agent 独立模型实例（完整 Multi-Agent）

## 11. 与现有 H0→H5→I→Risk→OMS 链路映射

| **现有概念** | **Multi-Agent 映射** | **说明** |
|---|---|---|
| H0 本地确定性判断 | 保持不变 | 始终独立于所有 Agent |
| H1 市场解读 | Scout + Strategist | Scout 提供情报，Strategist 解读 |
| H2 反证审视 | Strategist 内部 + Analyst | Strategist 反向验证 + Analyst 历史比对 |
| H3 成本审查 | OpenClaw 预算分配 + Strategist | OpenClaw 管全局预算，Strategist 管单笔成本 |
| H4 风险审查 | Guardian | Guardian 全面接管 |
| H5 综合 / Lease 起草 | Strategist → OpenClaw 批准 | Strategist 生成意图，OpenClaw 协调形成 Lease |
| I Decision Lease | OpenClaw 管理生命周期 | Lease 创建/激活/过期/撤销由 OpenClaw 管理 |
| Risk Governor | Guardian | Guardian = 增强版 Risk Governor |
| OMS / Execution | Executor | Executor = 增强版 OMS |
| Learning Plane | Analyst | Analyst = 增强版 Learning Plane |
| Control Plane | OpenClaw + GUI | OpenClaw 协调 + GUI 展示 |


## 12. 一句话总纲 One-Line Summary

*OpenClaw 作为中央编排器统一协调五个专职 Agent（Scout / Strategist / Guardian / Analyst / Executor），H0 门控始终独立运行，Agent 之间通过结构化对象通信，Guardian 的风控结论永远优先于 Strategist 的交易意图，在资源受限阶段可由单个本地模型扮演多角色但职责边界不因此模糊。*
