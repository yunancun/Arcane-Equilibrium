# OpenClaw / Bybit 交易 Agent

# Decision Lease State Machine Specification V1

## 0. 文档定位

本文件用于定义 **Decision Lease** 的正式状态机规范。

本文件回答以下问题： - Decision Lease 具有哪些正式状态 - 各状态的正式语义是什么 - 哪些事件可以触发状态迁移 - 哪些主体可以触发这些迁移 - 哪些迁移允许自动发生，哪些必须人工批准 - 哪些迁移是明令禁止的 - Lease 在不同状态下允许什么、不允许什么 - Lease 如何被冻结、撤销、过期、桥接与消费

本文件是以下文件的下沉落地规范： - 《项目宪法 / 根原则》 - 《H0-H1~H5-I 正式边界定义》 - 《字段级与状态级规范》 - 《Truth Source & Ownership Matrix》 - 《Risk Governor 正式边界定义》 - 《Promotion / Change Control / Authorization Policy》 - 《Audit / Incident / Circuit Breaker Policy》

本文件 **不负责**： - 风险阈值具体数值 - GUI 页面实现 - API 路由细节 - 数据库建表细节 - 交易所适配细节

如与上位文件冲突，以《项目宪法 / 根原则》为最高约束。


## 1. 设计目标

Decision Lease 状态机的目标，是把“受控交易意图”从静态对象变成一个具备正式生命周期、正式约束、正式审计与正式失效语义的控制对象。

它必须保证： - Lease 不是自由文本建议 - Lease 不是订单 - Lease 不是风险批准本身 - Lease 的存在、活跃、冻结、撤销、过期、桥接、消费，均有正式状态与正式审计 - Lease 不会以模糊方式长期悬挂在系统中

一句话：

**Decision Lease ****状态机，是把“已形成但尚未落地的受控交易意图”制度化为正式控制对象的生命周期系统。**


## 2. Lease 的正式地位

Decision Lease 的本质是：

**带有条件、时效、作用范围与失效语义的受控交易意图。**

它不是： - 交易所订单对象 - 最终风险批准结果 - 执行状态对象 - 持仓事实对象

它可以： - 被登记 - 被激活 - 被冻结 - 被撤销 - 被桥接给下游治理链 - 被消费 - 被过期

它不可以： - 直接等价于实盘写动作 - 在无状态机约束下长期存在 - 被 GUI 或学习平面直接伪造状态


## 3. 正式状态集合

Decision Lease 正式状态集合如下：
- DRAFT
- REGISTERED
- ACTIVE
- BRIDGED
- FROZEN
- REVOKED
- EXPIRED
- REJECTED
- CONSUMED

这些状态与《字段级与状态级规范》中的 lease_status 语义保持一致，但本文件更进一步定义其状态机语义与迁移规则。


## 4. 状态语义

## 4.1 DRAFT

### 含义
- Lease 草案已形成，但尚未被 I 正式接纳为控制对象

### 允许行为
- 被检查
- 被补充元信息
- 被拒绝接纳
- 被正式注册

### 不允许行为
- 不得桥接下游
- 不得视为已激活
- 不得视为风险已批准

### 典型来源
- H5 的 Lease 起草输出


## 4.2 REGISTERED

### 含义
- Lease 已被 I 正式接纳并登记
- Lease 已成为正式控制对象，但尚未进入可桥接活跃窗口

### 允许行为
- 等待激活条件满足
- 被冻结
- 被撤销
- 被拒绝继续推进
- 等待过期

### 不允许行为
- 未经激活直接桥接
- 被视为订单或执行对象

### 典型进入条件
- I 成功接纳 Lease 草案
- 基本元数据齐备
- 审计登记完成


## 4.3 ACTIVE

### 含义
- Lease 处于生效窗口内
- 可以在后续治理链中被评估是否桥接下游

### 允许行为
- 接受 Risk Governor 风险裁决
- 被桥接
- 被冻结
- 被撤销
- 被过期

### 不允许行为
- 自动等价为 execution
- 绕过 Risk Governor 直接执行

### 典型进入条件
- 已注册
- 生效时间已到
- 未被冻结、未撤销、未过期
- 当前系统模式允许 Lease 处于活跃状态


## 4.4 BRIDGED

### 含义
- Lease 已被正式桥接给下游治理链（通常指 Risk Governor / Execution 侧）
- 表示 Lease 已进入下一治理阶段

### 允许行为
- 等待被消费
- 在必要时被撤销（若下游尚未闭环）
- 进入 consumed 或后续终止状态

### 不允许行为
- 被重复桥接
- 被视为执行一定成功

### 重要语义

BRIDGED 不等于： - 风险一定批准 - execution 一定提交 - 订单一定存在

它只表示： - Lease 已从控制平面向下游正式交接


## 4.5 FROZEN

### 含义
- Lease 被暂时冻结
- 在冻结期间，Lease 不得继续向下游推进

### 允许行为
- 保持冻结
- 被解除冻结回到可接受状态（受限）
- 被撤销
- 被过期

### 不允许行为
- 继续桥接
- 自动恢复为 active 而无正式条件

### 典型进入条件
- operator freeze
- incident / risk freeze
- authorization freeze
- 恢复观察期间保护性冻结


## 4.6 REVOKED

### 含义
- Lease 已被正式撤销
- 不得继续使用

### 允许行为
- 归档
- 审计与复盘

### 不允许行为
- 重新激活
- 重新桥接
- 重新消费

### 重要语义

撤销是终态，不是临时暂停。


## 4.7 EXPIRED

### 含义
- Lease 已超过有效时间窗口或失效条件已满足
- 不得继续使用

### 允许行为
- 归档
- 审计与复盘

### 不允许行为
- 重新激活
- 重新桥接

### 重要语义

过期是基于时间/条件的自然终止，不等于人工撤销。


## 4.8 REJECTED

### 含义
- Lease 草案或 Lease 对象在某一步被正式拒绝接纳/拒绝推进

### 允许行为
- 归档
- 审计与复盘

### 不允许行为
- 重新进入 active / bridged
- 伪装成撤销或过期

### 重要语义

REJECTED 用于表示： - 这不是有效 Lease - 或这不是可继续推进的 Lease


## 4.9 CONSUMED

### 含义
- Lease 已完成其控制使命，并被正式消费闭合

### 典型场景
- 已成功进入下游并形成闭环
- 已被执行链消化完成
- 已不应继续作为活跃控制对象存在

### 允许行为
- 归档
- 审计与复盘

### 不允许行为
- 被重复桥接
- 被重新激活

### 重要语义

CONSUMED 是“生命周期完成”，不是“执行一定赚钱”或“策略正确”。


## 5. 正式触发事件

Lease 状态迁移只能由正式事件触发。

### 5.1 事件类别
- draft_event
- registration_event
- activation_event
- risk_governance_event
- operator_governance_event
- authorization_event
- incident_event
- expiry_event
- execution_closure_event

### 5.2 典型事件示例
- lease_draft_created
- lease_registration_accepted
- lease_registration_rejected
- lease_activation_window_open
- lease_invalidated
- lease_bridge_approved
- lease_bridge_rejected
- lease_freeze_requested
- lease_revoke_requested
- authorization_scope_revoked
- incident_freeze_applied
- lease_expired_by_time
- lease_consumed_by_execution_flow

这些事件必须进入正式审计链。


## 6. 状态迁移总图（逻辑）

建议逻辑迁移关系如下：
- DRAFT → REGISTERED
- DRAFT → REJECTED
- REGISTERED → ACTIVE
- REGISTERED → FROZEN
- REGISTERED → REVOKED
- REGISTERED → EXPIRED
- REGISTERED → REJECTED
- ACTIVE → BRIDGED
- ACTIVE → FROZEN
- ACTIVE → REVOKED
- ACTIVE → EXPIRED
- ACTIVE → REJECTED
- BRIDGED → CONSUMED
- BRIDGED → REVOKED（有限、条件性）
- FROZEN → REGISTERED 或 ACTIVE（条件性恢复）
- FROZEN → REVOKED
- FROZEN → EXPIRED

### 6.1 核心原则
- Lease 的生命周期必须单向总体收敛
- 终态对象不得回到活跃状态
- 不允许无限悬挂在中间态
- BRIDGED 之后必须最终闭合到终态


## 7. 允许的迁移

## 7.1 草案接纳阶段

### DRAFT -> REGISTERED

前提： - Lease 草案结构完整 - 关键字段齐备 - 审计登记成功 - I 接纳成功

### DRAFT -> REJECTED

前提： - 草案缺失关键字段 - 草案违反正式边界 - 草案无效或不被接纳


## 7.2 注册到活跃

### REGISTERED -> ACTIVE

前提： - 已到 valid_from - 未被冻结、未撤销、未过期 - 当前 system / authorization / incident 状态允许进入 active

### REGISTERED -> FROZEN

前提： - operator freeze - authorization freeze - incident freeze - recovery window freeze

### REGISTERED -> REVOKED

前提： - operator revoke - authorization revocation - upstream correction requiring invalidation

### REGISTERED -> EXPIRED

前提： - 超过 expires_at - 失效条件已满足

### REGISTERED -> REJECTED

前提： - 后置校验发现该 Lease 不应被正式接纳为有效控制对象


## 7.3 活跃到下游推进/终止

### ACTIVE -> BRIDGED

前提： - Lease 仍在有效窗口 - 未被冻结、未撤销、未过期 - 下游桥接条件满足 - Risk Governor / 下游治理链允许推进

### ACTIVE -> FROZEN

前提： - incident freeze - operator freeze - authorization freeze - recovery / observation freeze

### ACTIVE -> REVOKED

前提： - operator revoke - authorization withdrawn - upstream invalidation - incident handling requires revoke

### ACTIVE -> EXPIRED

前提： - expires_at 到达 - invalidation 条件触发

### ACTIVE -> REJECTED

前提： - 后置风险或治理链明确判定不应继续作为合法 Lease


## 7.4 冻结后的处理

### FROZEN -> REGISTERED

前提： - 冻结解除 - 尚未到 active 条件，仍应回到 registered 等待

### FROZEN -> ACTIVE

前提： - 冻结解除 - 生效条件仍满足 - 未过期、未撤销 - 恢复路径允许

### FROZEN -> REVOKED

前提： - 冻结后决定永久撤销

### FROZEN -> EXPIRED

前提： - 冻结期间自然过期


## 7.5 桥接后的闭合

### BRIDGED -> CONSUMED

前提： - 下游已接收并完成其控制闭合 - 该 Lease 不应再继续独立活跃

### BRIDGED -> REVOKED

前提： - 仅在下游尚未形成不可逆闭环前允许 - 必须有正式撤销条件和审计

### 说明

BRIDGED 后一般应尽快闭合，不应长期停留。


## 8. 禁止的迁移

以下迁移应明确禁止：

### 8.1 终态回流
- REVOKED -> ACTIVE
- REVOKED -> BRIDGED
- EXPIRED -> ACTIVE
- EXPIRED -> BRIDGED
- REJECTED -> REGISTERED
- REJECTED -> ACTIVE
- CONSUMED -> ACTIVE
- CONSUMED -> BRIDGED

### 8.2 跳过注册
- DRAFT -> ACTIVE
- DRAFT -> BRIDGED
- DRAFT -> CONSUMED

### 8.3 跳过活跃直接桥接
- REGISTERED -> BRIDGED

除非未来上位文档明确允许特殊 Lease 类型，否则禁止。

### 8.4 无审计静默迁移

任何关键 Lease 状态不得在没有： - 正式触发事件 - 正式状态迁移对象 - 正式审计事件

的情况下静默变化。

### 8.5 GUI / Learning 直接改 Lease 状态

GUI、Learning Plane、报表层不得直接将 Lease 从一个正式状态改到另一个正式状态。


## 9. 自动迁移 vs 人工批准

## 9.1 允许自动发生的迁移

以下迁移通常允许自动发生： - DRAFT -> REGISTERED - DRAFT -> REJECTED - REGISTERED -> ACTIVE - REGISTERED -> EXPIRED - ACTIVE -> EXPIRED - ACTIVE -> BRIDGED（前提是下游治理条件满足） - BRIDGED -> CONSUMED

### 说明

这些自动迁移必须仍然： - 有正式触发事件 - 有正式对象更新 - 有审计留痕

## 9.2 通常需要人工或治理动作参与的迁移

以下迁移通常需要 operator / governance action： - REGISTERED -> FROZEN - ACTIVE -> FROZEN - REGISTERED -> REVOKED - ACTIVE -> REVOKED - FROZEN -> REGISTERED - FROZEN -> ACTIVE

### 特别说明

若冻结或撤销是由 incident / authorization / recovery policy 自动触发，则可以由治理链自动发生，但仍应被视为正式治理动作，而非普通自动状态变化。


## 10. 状态进入后的行为约束

## 10.1 DRAFT
- 不得桥接
- 不得执行
- 只能审查与接纳

## 10.2 REGISTERED
- 可等待激活
- 可冻结/撤销/过期
- 不得直接下游执行

## 10.3 ACTIVE
- 可接受风险裁决与桥接评估
- 不得自动等价为订单

## 10.4 BRIDGED
- 不得重复桥接
- 应尽快闭合到终态

## 10.5 FROZEN
- 不得继续推进
- 等待治理解除或终止

## 10.6 REVOKED / EXPIRED / REJECTED / CONSUMED
- 均为终态
- 仅允许归档、审计、复盘
- 不允许恢复活跃


## 11. 状态迁移对象模板

建议每次 Lease 状态迁移都形成正式对象：

lease_transition:
  transition_id: string
  lease_id: string
  previous_status: DRAFT\|REGISTERED\|ACTIVE\|BRIDGED\|FROZEN\|REVOKED\|EXPIRED\|REJECTED\|CONSUMED
  next_status: DRAFT\|REGISTERED\|ACTIVE\|BRIDGED\|FROZEN\|REVOKED\|EXPIRED\|REJECTED\|CONSUMED
  trigger_event_type: draft_event\|registration_event\|activation_event\|risk_governance_event\|operator_governance_event\|authorization_event\|incident_event\|expiry_event\|execution_closure_event
  trigger_event_id: string
  initiated_by: I\|Operator\|AuthorizationGovernance\|IncidentPolicy\|ExecutionClosureFlow
  transition_reason_codes: []
  approval_required: true\|false
  approved_by: string\|null
  effective_at: datetime
  audit_event_ref: string


## 12. 过期与失效制度

### 12.1 过期必须是正式能力

Lease 不允许无限期挂着“也许还能用”。

每个 Lease 必须至少具备： - valid_from - expires_at

或由上位文档明确规定某类 Lease 的特殊时效逻辑。

### 12.2 失效条件优先于主观判断

如果 Lease 的 invalidation 条件已满足，则应优先触发： - ACTIVE -> EXPIRED - 或 REGISTERED -> EXPIRED

而不是继续保留活跃状态等待主观决定。


## 13. 与 Risk Governor 的关系

### 13.1 Lease 状态机不替代风险裁决

Lease 的 ACTIVE 或 BRIDGED 不等于风险已批准。

Risk Governor 负责： - 是否允许该 Lease 继续推进 - 以什么边界推进

### 13.2 正式边界

本状态机回答： > “Lease 作为控制对象，现在处于什么生命周期状态？”

Risk Governor 回答： > “这个 Lease 在当前风险模式下能不能往下走？”

因此两者必须并存，而不能相互吞并。


## 14. 与 OMS / Execution 的关系

### 14.1 Lease 状态机不替代执行状态机

BRIDGED 不等于 execution_submitted。

Execution 状态机负责： - 提交 - 撤改单 - 部分成交 - 失败恢复 - 执行闭环

Lease 状态机负责： - 作为控制对象的生命周期

### 14.2 消费闭合

只有当下游闭环明确完成后，Lease 才应进入 CONSUMED。


## 15. 与 Authorization / Incident 的关系

### 15.1 Authorization

若授权被收缩或撤销，应允许触发： - REGISTERED -> REVOKED - ACTIVE -> FROZEN - ACTIVE -> REVOKED

### 15.2 Incident

若发生 incident / critical incident，应允许触发： - REGISTERED -> FROZEN - ACTIVE -> FROZEN - 在严重情况下直接进入 REVOKED

但必须由正式治理链触发，不得由前端随意改状态。


## 16. 漂移防护声明

以下倾向应视为 Lease 状态机漂移风险： - Lease 被当成订单对象使用 - ACTIVE 被当成“肯定会执行” - BRIDGED 被当成“已经成交” - GUI 直接改 Lease 状态 - Learning Plane 直接回写 Lease 生命周期 - Lease 长期停留在中间态且无过期语义 - 被撤销或过期的 Lease 被重新激活

一旦出现上述情况，应优先修正状态机与治理链，而不是保留为“实现细节”。


## 17. 一句话总纲

**Decision Lease ****状态机的职责，是把受控交易意图正式化为一套有接纳、有激活、有冻结、有撤销、有过期、有桥接、有消费的生命周期系统，使**** Lease ****永远不是模糊建议、不是订单、不是风险批准本身，而是一个必须被正式管理、正式约束、正式审计的控制对象。**
