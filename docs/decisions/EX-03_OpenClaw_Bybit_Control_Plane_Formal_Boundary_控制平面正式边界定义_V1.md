# OpenClaw / Bybit 交易 Agent

# Control Plane / Operator Console 正式边界定义 V1

## 0. 文档定位

本文件用于定义 **Control Plane / Operator Console** 在 OpenClaw / Bybit 交易 Agent 中的正式职责边界。

本文件回答以下问题： - Control Plane / Operator Console 的正式定位是什么 - 它接收什么输入，产出什么输出 - 它可以做什么，不可以做什么 - 它与 H0、H1-H5、I、Risk Governor、OMS / Execution、Authorization、Audit、Learning 的边界是什么 - 它如何承载人工治理、审批、冻结、恢复、模式切换与观察台职能 - 它如何做到“可控制”但“不污染真相源”

本文件 **不负责**： - GUI 视觉设计与页面排版 - 前端框架选型 - API 路由参数细节 - 数据库物理表结构 - 策略公式与执行算法本身 - 交易所底层适配逻辑

如与《项目宪法 / 根原则》冲突，以宪法为最高约束。


## 1. 正式定义

### 1.1 Control Plane 的本质

Control Plane / Operator Console 不是策略层，不是风险层，不是执行层，也不是事实真相链本身。

它的正式定义是：

**系统中负责承载人工治理、模式控制、审批动作、冻结动作、恢复动作、状态观测、审计浏览与治理级操作入口的统一控制与治理平面。**

### 1.2 一句话定位

**Control Plane / Operator Console ****的职责不是代替系统做交易判断，而是为人类**** Operator ****提供一个受控、可审计、可回滚的治理入口，使人类能够观察系统、批准系统、限制系统、冻结系统、恢复系统，但不能绕过正式主链伪造系统事实。**


## 2. 在全系统中的位置

Control Plane / Operator Console 的正式位置如下：

**它横跨主系统之上，读取各正式状态对象，向正式治理链发起人工治理动作，但本身不直接替代主判断链、主风险链、主执行链或真相源链。**

### 2.1 主要交互对象

Control Plane / Operator Console 需要读取： - system_state - health_state - market_state（展示/理解用途） - account_state - risk_state - authorization_state - candidate_context - h0_decision - deliberation_state - decision_lease - execution_state - order_state - fill_state - position_state - audit_event - learning_record

同时它需要能够发起正式治理动作到： - Control / Governance Core - Authorization Governance - I Lease Control Plane - Risk Governor - OMS / Execution（通过正式控制动作，而非直接交易写操作） - Incident / Recovery 流程


## 3. 核心职责

Control Plane / Operator Console 必须承担以下核心职责：
- **系统观测与状态总览**
- **人工治理动作入口**
- **审批与撤权入口**
- **模式切换入口**
- **冻结、熔断、恢复入口**
- **审计浏览与事故调查辅助入口**
- **学习结果审阅与变更治理入口**
- **操作员权限边界承载**


## 4. 核心边界原则

### 4.1 控制平面不是事实真相源

Control Plane / Operator Console 可以读取、展示、触发治理动作，但不得成为以下对象的正式真相源： - market_state - account_state - risk_state - order_state - fill_state - position_state - decision_lease - execution_state

它可以呈现这些对象的当前正式状态，但不能把前端本地状态、表单值、标签映射反向写成正式真相。

### 4.2 控制平面不是交易写入口

即使 Operator 点击按钮，Control Plane 也不得直接写交易所。

所有交易相关动作必须： - 转化为正式治理动作对象 - 进入 Risk / I / OMS 正式链路 - 进入审计链

### 4.3 控制平面不是策略脑

Control Plane 不负责： - 生成交易观点 - 起草 Lease - 计算市场 regime - 决定某笔交易是否有 alpha

它可以展示这些结果，但不负责创造这些结果。

### 4.4 控制平面不是“后台随便改数据库”

Control Plane 的存在，是为了把人工治理从“隐性后门”变成“正式对象化动作”。

因此： - 不允许无审计热改 - 不允许直接修改关键事实对象 - 不允许以调试接口绕过治理主链


## 5. 输入

Control Plane / Operator Console 的输入必须优先来自正式对象与正式审计链，而不是前端自行推导的“感觉值”。

### 5.1 主要输入对象
- system_state
- health_state
- risk_state
- authorization_state
- decision_lease
- execution_state
- order_state
- fill_state
- position_state
- audit_event
- learning_record
- incident / recovery objects

### 5.2 可作为展示补充但非正式真相的对象
- 页面级聚合统计
- 图表缓存
- 本地搜索结果
- 前端筛选器状态
- 展示标签映射

这些对象不得被反向写回正式系统对象。


## 6. 输出

Control Plane / Operator Console 的正式输出不应是“直接结果”，而应是：
- **治理动作请求（governance**** action ****request）**
- **审批决定对象（approval**** ****decision）**
- **模式切换请求（mode**** transition ****request）**
- **冻结**** / ****恢复**** / ****撤权**** / ****变更治理请求**
- **审计事件源**

### 6.1 典型输出动作类型
- system_mode_change_request
- authorization_change_request
- lease_freeze_request
- lease_revoke_request
- risk_reduce_only_request
- emergency_stop_request
- manual_review_request
- recovery_approval
- change_request_approval
- de_authorization_request
- operator_cancel_request
- operator_reduce_position_request

### 6.2 输出要求

每个正式治理动作至少应包含： - action_id - action_type - target_object_type - target_object_id - initiated_by - initiated_at - reason_codes - operator_comment（可选） - requires_approval - audit_event_ref


## 7. Control Plane 可以做什么

## 7.1 状态观测

Control Plane 可以提供： - 系统模式总览 - 风险状态总览 - 健康状态总览 - Lease 总览 - 执行 / 订单 / 成交 / 持仓总览 - 审计事件查看 - 学习结果查看 - incident / recovery 过程查看

### 要求

观测应基于正式对象读取，不以本地缓存猜测替代。

## 7.2 人工治理动作触发

Control Plane 可以发起： - 模式切换 - 审批/拒绝 - 冻结/撤销 Lease - reduce-only 请求 - emergency stop - 局部撤权 - 恢复批准 - 变更审批

### 要求

这些动作必须： - 对象化 - 可审计 - 可追溯 - 进入对应正式治理链

## 7.3 审批与授权治理

Control Plane 可以承载： - 授权扩张审批 - 授权撤销 - 运行阶段变更审批 - Change Control 审批 - 恢复审批

### 要求

审批动作不是“前端按钮状态变化”，而必须生成正式审批对象或正式审计事件。

## 7.4 事故治理支撑

Control Plane 可以承载： - incident 页面 - near-miss / incident 浏览 - 冻结操作 - 恢复操作 - 事故复盘入口 - 观察期状态展示

## 7.5 操作员权限管理

Control Plane 应支持区分不同操作员角色与权限级别，但该权限模型本身仍应进入正式治理对象，而不是只停留在前端路由控制。


## 8. Control Plane 不可以做什么

## 8.1 不直接写交易所

Control Plane 不得： - 直接发订单到交易所 - 直接撤单到交易所 - 直接修改交易所仓位

所有此类动作都必须通过 OMS / Execution 正式链。

## 8.2 不直接改正式事实对象

Control Plane 不得直接重写： - position_state - order_state - fill_state - account_state - market_state - health_state

若人类希望“修正”，应通过： - 重同步 - 校准流程 - 事故标记 - 变更流程

而不是直接篡改事实对象。

## 8.3 不替代 Risk Governor

Control Plane 可以： - 触发人工保守动作 - 触发 manual review - 发起 emergency stop

但不得： - 自己伪造风险批准结果 - 绕过 Risk Governor 让未批准行为进入执行链

## 8.4 不替代 I（Lease Control Plane）

Control Plane 可以： - 触发 Lease 冻结/撤销请求

但不得： - 自己维护 Lease 生命周期真相 - 前端直接宣布 Lease 已 active / revoked 成为正式状态

## 8.5 不替代 Learning Plane

Control Plane 可以展示学习建议、审批学习建议进入变更流程。

但不得： - 自己生成正式归因结论 - 跳过 Change Control 直接上线学习建议


## 9. 与 H0 的边界

### H0 的职责
- 本地确定性准入与硬门控

### Control Plane 的职责
- 观察 H0 决定
- 追加治理动作（例如要求 review）

### 明确边界

Control Plane 不负责重做 H0 判断。

如果 Operator 认为 H0 判断有问题，应通过： - 审计记录 - 变更治理 - 重跑 / 重审

而不是直接篡改既有 h0_decision 对象。


## 10. 与 H1-H5 的边界

### H1-H5 的职责
- AI 审议治理与 Lease 草案生成

### Control Plane 的职责
- 展示审议结果
- 允许人工请求重审 / 标记 manual review

### 明确边界

Control Plane 不应： - 代写 deliberation 结果 - 手工改写 H1/H2/H3/H4/H5 结论 - 把前端评论伪装为正式审议结论


## 11. 与 I（Decision Lease Control Plane）的边界

### I 的职责
- Lease 生命周期真相与控制

### Control Plane 的职责
- 提供 Lease 观察与治理动作入口

### 明确边界

Control Plane 可以发起： - lease_freeze_request - lease_revoke_request - manual_review_request

但最终 Lease 状态变化应由 I 正式落地并写入真相对象。


## 12. 与 Risk Governor 的边界

### Risk Governor 的职责
- 正式风险裁决

### Control Plane 的职责
- 触发人工保守动作
- 触发 emergency stop
- 触发恢复审批
- 展示风险裁决结果

### 明确边界

Control Plane 不得： - 自行生成 risk_approved - 自行伪造 risk_rejected - 以 UI 按钮状态代替风险对象正式结果

如果 Operator 要强制更保守，应该通过： - 模式切换 - freeze - reduce-only 请求 - de-authorization

而不是通过伪造风险结论。


## 13. 与 OMS / Execution 的边界

### OMS / Execution 的职责
- 统一写入协调层
- 管理执行状态机

### Control Plane 的职责
- 发起正式控制动作
- 展示执行状态与问题

### 明确边界

Control Plane 可以发起： - operator_cancel_request - operator_reduce_position_request - emergency_stop_request

但这些动作仍应： - 进入 OMS / Execution 正式链路 - 进入审计链 - 遵循当前风险与系统模式约束

Control Plane 不得绕过 OMS 直接触发交易所操作。


## 14. 与 Authorization Governance 的边界

### Authorization Governance 的职责
- 维护 authorization_state
- 生效审批后的授权变更

### Control Plane 的职责
- 发起授权调整请求
- 展示授权范围
- 承载审批页面

### 明确边界

Control Plane 不应直接把页面上选择的值写成正式授权对象； 正式授权生效必须经过 Authorization Governance 与审计链。


## 15. 与 Audit 的边界

### Audit 的职责
- 形成正式审计对象

### Control Plane 的职责
- 浏览审计
- 发起需要记录的治理动作

### 明确边界

Control Plane 可以是审计事件源，但不是正式审计真相源。

任何关键人工动作都必须进入 Audit Pipeline，而不是只留在前端操作日志里。


## 16. 与 Learning Plane 的边界

### Learning Plane 的职责
- 复盘
- 归因
- 生成建议

### Control Plane 的职责
- 展示学习结果
- 发起审批 / 拒绝 / 延后处理

### 明确边界

Control Plane 不得： - 把学习建议直接生效 - 直接把建议写入 live 配置 - 以前端操作绕过 Change Control


## 17. Operator Console 的正式职能分区

建议 Operator Console 至少逻辑分为以下几类区：
- **Overview ****区**
  - system / health / risk / account 总览
- **Governance ****区**
  - mode 切换
  - freeze / emergency stop
  - manual review
- **Lease ****区**
  - lease 查看
  - freeze / revoke 请求
- **Execution ****区**
  - execution / order / fill / position 观察
  - operator control action 入口
- **Authorization ****区**
  - 授权范围浏览
  - 放权/撤权审批
- **Incident ****区**
  - anomaly / near-miss / incident / recovery 流程
- **Learning / Change Control ****区**
  - 学习建议查看
  - 变更审批与 rollout 状态

### 说明

这些是逻辑职能分区，不等于具体 GUI tab 数量或页面结构必须这样实现。


## 18. 操作员动作模板建议

建议任何正式人工治理动作至少具有如下结构：

operator_action:
  action_id: string
  action_type: system_mode_change\|lease_freeze\|lease_revoke\|manual_review\|risk_reduce_only\|emergency_stop\|authorization_change_request\|recovery_approval\|change_request_approval\|operator_cancel_request\|operator_reduce_position_request
  target_object_type: string
  target_object_id: string
  initiated_by: operator_id
  initiated_at: datetime
  reason_codes: []
  operator_comment: string\|null
  requires_followup_approval: true\|false
  audit_event_ref: string


## 19. 漂移防护声明

未来若出现以下倾向，应视为 Control Plane 边界漂移风险： - GUI 逐步变成直接写交易所的后台 - 前端状态逐步替代正式对象真相 - 页面筛选结果被误当成系统正式状态 - Operator 可以无审计地热改关键对象 - 学习建议从页面直接点一下就 live 生效 - Control Plane 越来越像另一个策略层或风控层

一旦出现上述趋势，应优先修正边界，而不是用“先这样方便操作”作为理由继续保留。


## 20. 一句话总纲

**Control Plane / Operator Console ****的正式职责，是为人类**** Operator ****提供一个统一、受控、可审计、可回滚的治理入口，用于观察系统、审批系统、限制系统、冻结系统与恢复系统；它不负责创造市场判断、不负责伪造系统真相、不负责直接写交易所，但必须确保人工治理始终通过正式对象与正式链路进入系统，而不是通过隐性后门污染系统。**
