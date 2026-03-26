# OpenClaw GUI / Operator Console / Learning Cockpit 设计规格 v1

## 0. 文档目标

这份规格用于定义 OpenClaw / Bybit 项目下一阶段的 **GUI 控制平面 + 运营驾驶舱 + 学习驾驶舱**。

它服务三个核心目标：

1. **替代不可持续的纯 Shell 操作方式**
2. **在不放开 live execution 的前提下，为 demo trading 铺设受控操作入口**
3. **让 Agent 同时具备控制、感知、汇报、经验沉淀、实验提案、自我学习的能力**

这不是一个“好看前端”的规格，而是一个面向真实运营、真实风控、真实审计的控制系统规格。

---

## 1. 核心定位

这个 GUI 不应只是“按钮面板”，而应是一个：

# Operator Console + Learning Cockpit

也就是同时覆盖：

- **控制**：状态查看、recheck、开关、relock、审批
- **经营**：收益、成本、净收益、趋势
- **感知**：系统健康、延迟、瓶颈、机会错失
- **汇报**：日报、周报、异常总结、运营总结
- **学习**：经验沉淀、假设生成、实验提案、结果对比
- **审计**：谁做了什么、什么时候做的、结果如何

一句话定义：

> 这是一个让人类 Operator 和 Agent 可以一起看见系统、控制系统、理解系统、学习系统的驾驶舱。

---

## 2. 当前工程边界（必须写死）

GUI 第一版必须严格继承当前工程真相：

- I = canonical closed, shadow-only
- J = functional_closeout_ready_shadow_only
- K = functional_closeout_ready_design_only_gate_closed
- runtime 必须仍解释为：
  - `system_mode = read_only`
  - `execution_state = disabled`

因此 GUI v1 必须遵守：

1. **Live Trading 入口只能占位，不能可用**
2. **Demo Trading 入口最多做到 guarded / staged control，不得裸开关**
3. **任何按钮都不能绕过现有 contract / recheck / gate 语义**
4. **所有状态变化必须可审计**
5. **所有实验与学习必须是受控的，不得自发 live 自改**

---

## 3. 产品原则

### 原则 1：先看状态，再做动作
GUI 首页必须先显示系统状态，而不是一上来就给危险按钮。

### 原则 2：先复查，再允许推进
所有重要推进动作都应先过 recheck / acceptance / operator acknowledgement。

### 原则 3：所有会改变状态的动作都必须留下审计
不能只有结果，没有谁、何时、为何、前置条件是否满足。

### 原则 4：学习不等于自作主张
Agent 可以提出：
- 观察
- 总结
- 假设
- 实验提案

但不能：
- 自动改 live 配置
- 自动改代码
- 自动放开 execution
- 自动提升未验证策略

### 原则 5：收益必须看净收益
GUI 不允许只展示 trading PnL，而不展示成本。必须有：
- Gross PnL
- Total Cost
- Net PnL

### 原则 6：总结必须区分事实 / 推断 / 假设
防止 Agent 乱归因。

---

## 4. GUI 总体信息架构

建议 v1 采用以下一级导航：

1. **Overview / 总览首页**
2. **Control Center / 控制中心**
3. **Health & Self-Sensing / 自我感知与健康中心**
4. **Business & Cost / 收益与成本看板**
5. **Quick Input / 快速录入**
6. **Reports / 日报周报与复盘**
7. **Learning Center / 自学习中心**
8. **Capability Matrix / 能力矩阵**
9. **Audit Log / 审计日志**
10. **Settings & Config / 配置与连接管理**
11. **Live Control / 正式运行控制（占位禁用）**

---

## 5. 页面规格

## 5.1 Overview / 总览首页

### 目标
让 Operator 在 10 秒内回答：

- 系统现在安全吗？
- 今天赚没赚钱？
- 系统健康吗？
- 当前能不能进入 demo 相关动作？
- 今天最需要关注什么？

### 首页模块

#### A. Global Status 卡片
显示：
- `system_mode`
- `execution_state`
- 当前阶段标签：
  - observe only
  - shadow only
  - design-only gate closed
  - demo armed
  - demo enabled
  - live disabled
- git commit 简号
- last refresh time

#### B. Chapter Status 卡片
显示：
- I status
- J status
- K status
- each status last updated

#### C. Daily PnL 卡片
显示：
- 今日 gross PnL
- 今日 total cost
- 今日 net PnL
- 较昨日变化
- 较 7 日均值变化

#### D. Health Score 卡片
显示：
- overall health score
- AI health
- exchange health
- infra health
- data freshness health

#### E. Attention Panel
显示：
- 今天最危险的 3 个问题
- 今天最值得验证的 3 个假设
- 今天最重要的 3 个提醒

#### F. Recommended Next Actions
显示：
- run K recheck
- review missed opportunities
- investigate latency spike
- approve / reject experiment

---

## 5.2 Control Center / 控制中心

### 目标
替代高频 shell 操作，提供受控推进与一键回锁能力。

### 模块

#### A. Recheck Center
按钮：
- Run J canonical recheck
- Run K canonical recheck
- Run J functional closeout recheck
- Run K functional closeout recheck
- Run all safe rechecks

每个按钮显示：
- last run time
- status: idle / running / passed / failed
- blockers count
- latest summary

#### B. Demo Control Panel
状态机建议：
- `closed`
- `armed_but_closed`
- `demo_enabled`
- `relocked`

按钮建议：
- Validate prerequisites
- Arm demo
- Enable demo
- Relock demo

约束：
- 不能是一个裸 toggle
- 每步必须二次确认
- 每步必须显示前置条件
- 每步必须写审计

#### C. Emergency Relock / Kill
高优先级按钮：
- `RELOCK DEMO`
- `GLOBAL SAFE MODE`

要求：
- 一键可触发
- 结果即时刷新
- 必须写审计
- 必须可验证状态是否真正回锁

#### D. Operator Acknowledgement
所有可能改变执行相关状态的操作，都必须要求：
- 二次确认
- 确认文本输入
- 当前影响说明
- 前置条件清单
- 操作人身份记录

---

## 5.3 Health & Self-Sensing / 自我感知与健康中心

### 目标
让 Agent 和 Operator 共同回答：

- 系统健康吗？
- 慢在哪里？
- 卡在哪里？
- 最近变差是因为什么？

### 模块

#### A. Latency Breakdown
显示：
- AI request latency
- exchange API latency
- websocket reconnect latency
- decision-chain total latency
- per-stage latency breakdown

#### B. Error / Timeout Panel
显示：
- AI timeout count
- Bybit timeout count
- ws disconnect count
- failed rechecks
- stale data alerts

#### C. Infra Bottleneck Panel
显示：
- CPU
- memory
- disk I/O
- network RTT
- queue backlog
- process lag

#### D. Data Freshness Panel
显示：
- key latest artifacts last update time
- stale modules
- source freshness status

#### E. Missed Opportunity Health
显示：
- missed opportunity count
- estimated missed PnL range
- top miss reasons

---

## 5.4 Business & Cost / 收益与成本看板

### 目标
不只是看交易盈亏，而是看 Agent 整体运营是否赚钱。

### 核心指标
- realized PnL
- unrealized PnL
- total fees
- funding / borrowing cost
- AI API cost
- infra cost
- manually entered cost
- net operating PnL

### 模块

#### A. Daily Net PnL

#### B. Weekly / Monthly Trend

#### C. Cost Breakdown
分类：
- trading fee
- funding
- AI model/API
- infra / hardware / hosting
- network
- misc manual inputs

#### D. Cost Attribution
回答：
- 今天成本最高的是哪项
- 本周成本上升主要来自哪项
- 成本是否侵蚀掉利润

---

## 5.5 Quick Input / 快速录入

### 目标
让 Operator 能快速把关键现实信息喂给系统，而不必靠 shell 或手改文件。

### 表单 1：成本录入
字段：
- date
- cost_type
- amount
- currency
- recurring or one-off
- source/vendor
- notes
- optional attachment reference

### 表单 2：事件录入
字段：
- timestamp
- event_type
- severity
- affected_area
- summary
- notes

例如：
- Bybit API 抖动
- 网络中断
- 新硬件上架
- 模型 provider 限流

### 表单 3：配置变更录入
字段：
- change_time
- config_area
- old_value summary
- new_value summary
- operator
- verified or not
- notes

### 表单 4：人工备注 / 标签录入
用于补充 Agent 可能不知道的人类背景：
- “今天网络异常来自家庭线路问题”
- “这次成本增加是一次性硬件采购”

---

## 5.6 Reports / 日报周报与复盘

### 目标
让系统不只是“记录数据”，还能够“生成可运营、可复盘、可行动”的总结。

### 日报
至少回答：
1. 今天赚没赚钱
2. 今天总成本多少
3. 净收益多少
4. 今天系统健康吗
5. 今天异常是什么
6. 明天该注意什么

### 周报
至少回答：
1. 本周净收益
2. 成本结构变化
3. 健康趋势变化
4. 成功经验
5. 失败模式
6. 下周最值得优化的点

### 成功复盘
回答：
- 哪些成功机会被抓住了
- 为什么抓住了
- 成功更可能来自策略 / 基础设施 / AI / 市场 regime 的哪部分

### 失败复盘
回答：
- 为什么没赚到 / 为什么亏
- 是策略失效、系统延迟、交易所问题、硬件问题还是成本问题
- 哪些问题可修，哪些只是市场噪声

### 结构要求
每份总结都应区分：
- 事实
- 推断
- 假设

---

## 5.7 Learning Center / 自学习中心

### 目标
承接 L 章节的早期能力，但以受控方式落地。

### 模块

#### A. Observation Feed
Agent 自动观察到的现象流：
- latency spike
- timeout increase
- cost anomaly
- missed opportunity increase
- risk block increase
- net PnL drop

#### B. Lessons Memory
结构化经验库，每条经验包括：
- title
- date range
- facts
- inferences
- hypotheses
- conclusion
- suggested action
- evidence links
- tags

#### C. Hypothesis Queue
Agent 提出的待验证假设：
- title
- evidence summary
- risk level
- proposed test method
- status

#### D. Experiment Queue
实验提案与执行追踪：
- objective
- variant A/B
- environment: replay / shadow / demo
- expected gain
- expected risk
- status: draft / waiting approval / running / completed / rejected
- result summary

### 学习中心的安全原则
- 允许观察
- 允许总结
- 允许提假设
- 允许提实验
- 不允许直接自动改 live 配置
- 不允许自动放开 execution

---

## 5.8 Capability Matrix / 能力矩阵

### 目标
把章节与能力族的健康状态直观展示出来。

### J 区块
显示：
- canonical chain
- decision
- decision contract
- functional closure

### K 区块
显示：
- transition intake
- decision
- adapter
- lifecycle
- projection
- risk
- audit
- operator switch
- acceptance
- functional closure

每行显示：
- latest exists
- contract green
- state
- blockers
- last updated

---

## 5.9 Audit Log / 审计日志

### 目标
所有关键动作、状态变化、审批都可追踪。

### 记录内容
- operator
- timestamp
- action type
- target module
- before state
- after state
- success/failure
- failure reason
- linked artifact / report

### 需要进入审计的动作
- recheck 触发
- demo arm / enable / relock
- 配置切换
- 成本录入修改
- 实验审批
- 实验终止

---

## 5.10 Settings & Config / 配置与连接管理

### 目标
让常见配置更新更安全、更可视。

### 适合 GUI 管的内容
- provider profile 切换
- API connection test
- active config version
- profile enable / disable
- config rollout status

### 不建议 v1 做的内容
- 明文 secrets 管理
- 任意 raw JSON 编辑
- 任意 shell 执行入口

---

## 5.11 Live Control / 正式运行控制（占位禁用）

### 目标
提前定义未来 live control 的 UI 位置与边界，但现在绝不开放。

显示：
- live control status = unavailable
- reason = not implemented / not authorized
- future prerequisites

必须：
- 所有按钮禁用
- 明确解释当前不可用原因

---

## 6. L 章节能力如何前置接入 GUI

当前建议不是“完整做 L”，而是把 L 的前半部分做成 GUI 可运行能力：

### L0：Self-observation
- Agent 看见自己表现如何

### L1：Lessons memory
- Agent 记住经验，不只是每天重新说一遍

### L2：Hypothesis generation
- Agent 能提出可验证假设

### L3：Experiment proposal
- Agent 能提出受控实验

### L4：Approval workflow
- 需要人工批准才能推进实验

暂不进入：
- live self-modification
- autonomous live parameter rollout
- autonomous code mutation

---

## 7. 数据来源设计

GUI v1 的数据源建议分四类：

### A. Runtime latest JSON
来自现有 latest artifacts：
- I/J/K 状态
- canonical recheck
- functional closure
- capability / contract latest

### B. Telemetry / metrics
- AI latency
- exchange latency
- timeout
- infra metrics
- queue / process lag

### C. Business records
- trading PnL
- fees
- funding cost
- AI API bills
- manual cost inputs

### D. Human input records
- manual notes
- event logs
- config change logs
- experiment approvals

---

## 8. 建议后端分层

不建议 GUI 直接调 shell。

建议至少分三层：

### Layer 1: GUI / OpenClaw front-end
负责：
- 页面
- 表单
- 图表
- 操作交互
- 多步确认

### Layer 2: Control API / Backend service
负责：
- 读取 latest JSON
- 运行受控 recheck
- 校验 prerequisites
- 写审计
- 执行 arm / relock / safe updates

### Layer 3: Data & analytics layer
负责：
- 收益与成本聚合
- telemetry 聚合
- daily report generation
- lessons / hypothesis / experiment storage

---

## 9. 第一版建议必须具备的功能

## Must-have v1
1. Overview
2. Control Center
3. Health & Self-Sensing
4. Business & Cost
5. Quick Input
6. Reports
7. Learning Center（至少 Observation + Lessons + Hypothesis 列表）
8. Capability Matrix
9. Audit Log
10. Live Control placeholder（禁用）

## Should-have v1.1
1. Experiment queue
2. approval workflow
3. change timeline
4. missed opportunity analytics
5. bottleneck drill-down

## Later
1. scenario lab / what-if sandbox
2. richer weekly/monthly reflection
3. more advanced attribution models

---

## 10. Change Timeline / 变更时间轴（建议纳入 v1.1）

建议加入一条统一时间轴，把以下信息叠在一起：
- config changes
- provider changes
- hardware changes
- chapter status changes
- operator actions
- cost changes
- performance changes
- net PnL changes

作用：
- 帮助 Agent 真正建立“变更 -> 结果”的因果回看能力
- 帮助 Operator 快速理解“这次好/坏是从什么时候开始的”

---

## 11. 权限与安全级别

建议至少分三级：

### Viewer
- 只能看状态、看报表、看经验库

### Operator
- 可触发 recheck
- 可录入成本/事件
- 可执行 demo arm/relock 等受限动作

### Admin
- 可做配置切换
- 可审批实验
- 可维护控制平面设置

Live 相关权限在 v1 全部禁用。

---

## 12. 最重要的 UI 文案规则

所有关键状态都必须明确写出“这不代表什么”。

例如：
- `K functional closeout ready` 下面必须补一句：
  - `This does not mean demo trading is enabled.`
- `operator switch model defined` 下面必须补一句：
  - `Operator enable is still unavailable.`
- `acceptance model defined` 下面必须补一句：
  - `Gate remains closed.`

这样能防止视觉层面的误解。

---

## 13. 一句话产品定义

> OpenClaw GUI / Operator Console / Learning Cockpit v1 是一个在严格安全边界内，让人类与 Agent 一起完成“控制、感知、汇报、学习、审计”的运营驾驶舱。

它的第一目标不是让系统变得“更炫”，而是让系统从“shell 驱动的工程品”进化成“可运营、可解释、可学习的受控系统”。

---

## 14. 下一步建议

如果采用本规格，建议下一步按以下顺序推进：

1. 先把 **数据字典 / 状态字典** 定义出来
2. 再把 **页面信息架构** 固化
3. 再定义 **Control API v1**
4. 再做 **GUI MVP**
5. 最后再接入更强的 learning / experiments workflow

最务实的 MVP 顺序：
- Overview
- Control Center
- Capability Matrix
- Quick Input
- Audit Log
- Health & Self-Sensing
- Reports
- Learning Center（最简版）

这会是从当前 J/K 收口状态走向 demo trading 最稳的一条路。