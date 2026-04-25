# OpenClaw / Bybit 交易 Agent

# OMS / Execution 正式边界定义 V1

## 0. 文档定位

本文件用于定义 **OMS / Execution** 在 OpenClaw / Bybit 交易 Agent 中的正式职责边界。

本文件回答以下问题： - OMS / Execution 的正式定位是什么 - 它接收什么输入，产出什么输出 - 它可以做什么，不可以做什么 - 它与 I（Decision Lease Control Plane）、Risk Governor、Order / Fill / Position 真相链、Reconciliation、Control Plane、Learning Plane 的边界是什么 - 它如何管理执行意图、订单提交流程、撤改单流程、部分成交、失败恢复与执行状态机

本文件 **不负责**： - 交易所 API 具体路由参数 - GUI 页面细节 - 具体数据库表结构 - 风险阈值数值 - 策略公式本身 - 交易所适配层的低层代码实现

如与《项目宪法 / 根原则》冲突，以宪法为最高约束。


## 1. 正式定义

### 1.1 OMS / Execution 的本质

OMS / Execution 不是策略层，不是风险层，也不是交易所事实真相链本身。

它的正式定义是：

**系统中负责将已经通过治理链放行的受控交易意图，转换为受控执行行为，并管理订单生命周期、执行状态、部分成交、撤改单、失败恢复与执行级审计的统一执行协调层。**

### 1.2 一句话定位

**OMS / Execution ****的职责不是决定“该不该做”，而是在“已被允许做”的前提下，尽可能以正确、可控、可审计、可恢复的方式把事情做成。**


## 2. 在全链路中的位置

OMS / Execution 在主链中的正式位置如下：

**市场与账户世界**** → H0 → H1-H5 → ****I（Lease**** Control ****Plane）→**** Risk Governor → OMS / Execution → Venue Adapter → Exchange → Order / Fill / Position Sync → Reconciliation**

### 2.1 关键语义
- H0 决定是否进入审议链
- H1-H5 决定是否形成 Lease 草案
- I 管理 Lease 生命周期
- Risk Governor 决定是否允许推进及可承担风险边界
- **OMS / Execution ****决定如何把已获准的行为落地为执行行为**
- 交易所事实链与对账链决定最终事实对象

因此： - OMS / Execution 不是最终市场判断者 - OMS / Execution 不是最终风险裁决者 - OMS / Execution 也不是订单 / 成交 / 持仓事实的最终真相源


## 3. 核心职责

OMS / Execution 必须承担以下核心职责：
- **执行意图接收与校验**
- **执行计划生成**
- **订单提交流程控制**
- **撤单**** / ****改单**** / reduce-only ****执行控制**
- **部分成交处理**
- **执行状态机维护**
- **执行错误与恢复流程**
- **执行级幂等保护**
- **执行级审计与可追溯性**
- **向订单**** / ****成交**** / ****持仓事实链提供受控动作输入**


## 4. 核心边界原则

### 4.1 单一写入口原则在执行层的落实

OMS / Execution 是系统中唯一合法的交易写入协调层。

这意味着： - 任何下单、撤单、改单、保护性 reduce-only 动作，都必须经过 OMS / Execution - GUI 不得直接写交易所 - H0 / H1-H5 / I / Learning 不得绕过 OMS / Execution - Risk Governor 也不得直接写交易所，而应通过治理结果约束 OMS / Execution

### 4.2 执行层不拥有自由交易权

OMS / Execution 只能在以下前提同时满足时行动： - 存在正式对象（如 decision_lease 或正式控制动作） - 已通过 Risk Governor 裁决 - 当前 system_state / risk_state / authorization_state / health_state 允许该行为

OMS / Execution 不得因为“现在机会很好”而自行创建风险暴露。

### 4.3 执行层不是事实真相源

OMS / Execution 可以： - 提交请求 - 跟踪过程 - 更新 execution_state

但不应自称为以下对象的最终真相源： - order_state - fill_state - position_state

这些对象的最终真相应来自交易所同步链 + 对账链。


## 5. 输入

OMS / Execution 的正式输入必须是结构化治理对象，而不是自由文本。

### 5.1 主要输入对象
- decision_lease
- risk_decision
- system_state
- risk_state
- authorization_state
- health_state
- position_state
- order_state（已有订单上下文）
- execution_state（既有执行上下文）
- operator 控制动作（正式对象化后）

### 5.2 可引用但不能代替正式输入的对象
- deliberation_state
- h0_decision
- GUI 临时操作状态
- 报表摘要
- Learning 建议

这些对象可以帮助解释，但不能替代正式执行授权链。


## 6. 输出

OMS / Execution 的正式输出必须是结构化执行结果，而不是交易所事实本身。

### 6.1 正式输出对象
- execution_state
- execution_request
- execution_action_log
- audit_event

### 6.2 正式输出类型
- execution_created
- execution_approved_for_submit
- execution_submitted
- execution_partially_filled
- execution_filled
- execution_cancel_requested
- execution_cancelled
- execution_failed
- execution_reconciling
- execution_completed
- execution_aborted

### 6.3 输出应至少包含
- execution_id
- source_object_type
- source_object_id
- execution_intent_type
- execution_status
- execution_style
- request_count
- last_action_at
- last_error_code
- reduce_only
- reconciliation_required


## 7. OMS / Execution 可以做什么

## 7.1 执行计划生成

OMS / Execution 可以根据正式输入决定： - 是新开仓、加仓、减仓还是全平 - 使用何种执行风格 - 是否拆分执行 - 是否等待某一执行条件满足后再提交 - 是否需要取消旧订单后重提

但前提是： - 不改变 Risk Governor 已给定的风险边界 - 不超出 Lease 与授权允许范围

## 7.2 提交、撤单、改单

OMS / Execution 可以负责： - 创建订单请求 - 提交至交易所适配层 - 在允许情况下发起 cancel / replace - 根据 reduce-only 要求生成保护性动作

## 7.3 部分成交处理

OMS / Execution 必须能处理： - 部分成交后的剩余执行 - 部分成交后的撤单或继续执行决策 - 部分成交导致的执行计划收缩

### 重要边界

它可以基于执行策略决定“剩下的怎么做”，但不能借此扩大风险边界。

## 7.4 幂等与重复提交防护

OMS / Execution 必须承担执行级幂等保护责任，至少防止： - 同一意图重复下单 - 网络重试导致重复订单 - 状态机错乱导致多次执行同一动作

## 7.5 失败恢复与执行降级

OMS / Execution 必须具备正式失败恢复路径，例如： - 网络错误后的有限次重试 - 提交不确定状态后的对账确认 - 无法确认订单状态时进入 reconciling - 在不安全时停止继续推进并请求人工复核


## 8. OMS / Execution 不可以做什么

## 8.1 不负责市场判断

OMS / Execution 不负责： - 判断现在是趋势还是震荡 - 判断该不该做多做空 - 重新解释市场结构

这些属于 H0 / H1-H5。

## 8.2 不负责风险放权

OMS / Execution 不得： - 放宽风险预算 - 忽略 reduce-only 要求 - 越过冻结范围 - 因“快成交了”而自行扩大风险

这些属于 Risk Governor / Control Plane。

## 8.3 不负责授权扩张

OMS / Execution 不得： - 在未授权 symbol 上执行 - 启用未授权订单类型 - 启用未授权策略簇路径

## 8.4 不负责最终事实裁定

OMS / Execution 不得把自己的中间状态视为以下对象的最终事实： - order_state - fill_state - position_state

它只能持有“执行视角状态”，最终事实应由同步链与对账链确认。

## 8.5 不得脱离正式对象行动

OMS / Execution 不得基于： - GUI 按钮直接意图 - 一段 AI 文本 - 开发调试口头指令 - 未登记 Lease - 未通过风险审批的动作

直接产生交易所写动作。


## 9. 执行状态机的正式语义

建议 OMS / Execution 至少使用以下正式执行状态：
- pending
- approved
- submitted
- partially_filled
- filled
- cancel_requested
- cancelled
- failed
- reconciling
- completed
- aborted

### 9.1 状态语义

#### pending

执行对象已创建，但尚未具备提交条件。

#### approved

已通过治理链，可进入提交阶段。

#### submitted

执行请求已发出，等待交易所回报与后续同步。

#### partially_filled

部分成交，仍有剩余动作需要管理。

#### filled

执行目标已按计划成交完成。

#### cancel_requested

已请求撤单，等待正式结果。

#### cancelled

撤单已确认完成。

#### failed

执行流程在某步失败，未成功完成目标动作。

#### reconciling

本地执行视图与外部事实存在不确定性，需等待同步 / 对账确认。

#### completed

执行流程结束，且状态已闭合。

#### aborted

执行被主动终止，不再继续推进。

### 9.2 状态转换原则
- 关键状态跳变必须进入 audit_event
- 不允许无审计记录的跳变
- submitted 后若状态不明，应优先进入 reconciling，而不是默认失败或默认成功
- completed 仅在执行闭环结束后可进入


## 10. 执行意图类型

建议正式区分以下执行意图：
- new_entry
- add_position
- reduce_position
- full_exit
- cancel_order
- modify_order
- protective_action

### 10.1 特别说明

protective_action 应包括： - reduce-only 减仓 - 风险驱动平仓 - 熔断后的保护性收缩

保护性动作在制度优先级上应高于一般扩张性动作。


## 11. 与 I（Decision Lease Control Plane）的边界

### I 的职责
- 管理 Lease 生命周期
- 接纳、注册、冻结、撤销、过期 Lease
- 受控桥接下游

### OMS / Execution 的职责
- 把已被允许推进的 Lease 转化为执行流程
- 管理执行状态机

### 明确边界

I 解决的是： > “这个受控意图是否存在、是否活跃、是否仍可桥接。”

OMS / Execution 解决的是： > “这个已可桥接的受控意图，如何被安全地落实为执行动作。”

因此： - Lease active ≠ execution 自动开始 - bridged ≠ execution 一定成功 - OMS / Execution 不修改 Lease 生命周期事实


## 12. 与 Risk Governor 的边界

### Risk Governor 的职责
- 最终风险裁决
- 放行 / 拒绝 / 缩仓 / 降级 / 冻结 / 熔断

### OMS / Execution 的职责
- 在获准边界内执行

### 明确边界

OMS / Execution 可以基于执行现实做： - 更保守地执行 - 更慢地执行 - 更小心地执行

但不可以做： - 比 Risk Governor 更激进地执行 - 超出批准仓位或风险边界 - 在被 reduce-only 时新增风险

换言之：

**执行层可以比风险层更保守，但绝不能比风险层更宽松。**


## 13. 与 Order / Fill / Position 真相链的边界

### Order / Fill / Position 真相链职责
- 同步交易所事实
- 形成正式 order_state / fill_state / position_state
- 对账并校正本地视图

### OMS / Execution 职责
- 产生执行请求
- 跟踪执行过程
- 使用正式事实反馈修正自己的执行状态

### 明确边界

OMS / Execution 可以： - 持有执行中的临时视图 - 追踪已提交但未确认的动作 - 依据同步反馈更新执行状态

OMS / Execution 不得： - 在无同步/对账确认时，宣布订单已成交 - 在持仓事实未确认时，擅自假定 position_state 已闭合 - 以自己的中间视图替代正式真相链


## 14. 与 Reconciliation 的边界

### Reconciliation 的职责
- 检查本地视图与外部事实是否一致
- 输出正式一致性判断
- 在需要时触发纠正、冻结或人工审查

### OMS / Execution 的职责
- 在执行不确定时进入 reconciling
- 等待对账结论
- 配合而不是绕过对账链

### 明确边界

OMS / Execution 不能因为“执行逻辑上应该成功”就跳过对账。

当存在以下情形时，应优先交给 Reconciliation： - 请求成功但回报丢失 - 提交后状态不明 - 部分成交与本地剩余量不一致 - 撤单结果不确定 - 持仓变化与预期不一致


## 15. 与 Control Plane / Operator Console 的边界

### Control Plane 可以做什么
- 发起正式治理动作
- 触发 cancel / freeze / emergency stop / reduce_only / manual takeover
- 展示执行状态与对账状态

### OMS / Execution 的边界

Control Plane 不得： - 直接伪造 execution_state - 直接写 order_state / fill_state / position_state - 绕过 OMS 直写交易所

Operator 可以通过 Control Plane 触发正式动作，但动作本身仍须进入 OMS / Execution 正式链路，并写入审计事件。


## 16. 与 Learning Plane 的边界

### Learning Plane 可以做什么
- 复盘执行质量
- 归因执行错误
- 提出执行风格、重试策略、保护规则改进建议

### Learning Plane 不可以做什么
- 直接改写 live 执行逻辑
- 直接修改幂等机制
- 直接放宽重试条件
- 直接启用更激进执行方式

所有执行相关改动，必须走正式 Change Control。


## 17. 执行失败与恢复责任

OMS / Execution 必须具备正式失败分类与恢复路径。

### 17.1 典型失败族
- submit_failure
- ack_timeout
- duplicate_risk
- cancel_failure
- replace_failure
- partial_fill_stall
- reconciliation_required
- venue_adapter_error
- unknown_execution_state

### 17.2 恢复原则
- 优先保全账户，而不是强行追求完成执行
- 在状态不明时优先进入 reconciling
- 在风险较高时优先 reduce-only 或 freeze
- 恢复动作本身也必须可审计

### 17.3 禁止恢复方式

禁止通过以下方式“恢复”： - 在状态不明时盲目重提新单 - 以本地猜测覆盖订单真实状态 - 为了“完成计划”而放宽风险边界


## 18. 正式执行对象模板建议

建议每次正式执行至少具备如下结构：

execution_object:
  execution_id: string
  source_object_type: lease\|operator_action\|risk_protective_action
  source_object_id: string
  execution_intent_type: new_entry\|add_position\|reduce_position\|full_exit\|cancel_order\|modify_order\|protective_action
  execution_style: passive_limit\|aggressive_limit\|market_if_required\|split_execution\|reduce_only
  execution_status: pending\|approved\|submitted\|partially_filled\|filled\|cancel_requested\|cancelled\|failed\|reconciling\|completed\|aborted
  reduce_only: true\|false
  request_count: number
  last_action_at: datetime
  last_error_code: string\|null
  reconciliation_required: true\|false
  created_at: datetime
  updated_at: datetime


## 19. 漂移防护声明

未来若出现以下倾向，应视为 OMS / Execution 边界漂移风险： - Execution 越来越像策略引擎 - Execution 自己解释市场并决定是否值得做 - Execution 直接绕过 Risk Governor - GUI 直接变成写交易所的快捷路径 - OMS 自己宣布订单 / 持仓最终事实 - Learning Plane 开始热改执行行为

一旦出现上述趋势，应优先修正边界，而不是接受“先这么做更方便”。


## 20. 一句话总纲

**OMS / Execution ****的正式职责，是在不改变风险边界、不篡改事实真相、不绕过治理链的前提下，把已经通过正式治理链放行的受控意图，转换为可控、可审计、可恢复的执行行为；它不负责寻找机会，不负责放宽风险，也不负责宣布最终交易事实，但必须对执行过程本身的正确性、幂等性、可追溯性与失败恢复负责。**
