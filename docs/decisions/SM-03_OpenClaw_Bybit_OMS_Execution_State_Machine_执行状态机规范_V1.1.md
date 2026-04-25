# OpenClaw / Bybit 交易 Agent

# OMS / Execution State Machine Specification V1.1

## 0. 文档定位

本文件用于定义 **OMS / Execution** 的正式状态机规范。

本文件回答以下问题： - Execution 对象具有哪些正式状态 - 各状态的正式语义是什么 - 哪些事件可以触发状态迁移 - 哪些主体可以触发这些迁移 - 哪些迁移允许自动发生，哪些需要治理动作或人工参与 - 哪些迁移是明令禁止的 - 执行对象在不同状态下允许什么、不允许什么 - 如何处理部分成交、撤单、失败、状态不明与对账修复

本文件是以下文件的下沉落地规范： - 《项目宪法 / 根原则》 - 《字段级与状态级规范》 - 《OMS / Execution 正式边界定义》 - 《Risk Governor 正式边界定义》 - 《Decision Lease State Machine Specification》 - 《Truth Source & Ownership Matrix》 - 《Audit / Incident / Circuit Breaker Policy》

本文件 **不负责**： - 交易所 API 参数细节 - GUI 页面实现 - 数据库建表细节 - 执行算法性能优化细节 - 风险阈值数值

如与上位文件冲突，以《项目宪法 / 根原则》为最高约束。


## 1. 设计目标

OMS / Execution 状态机的目标，是把“执行过程”从一串分散的 API 调用、局部回调与临时内存状态，收敛为一套正式、可审计、可回放、可恢复的状态系统。

它必须保证： - 执行层不是黑箱 - 订单请求不是执行状态本身 - 提交成功不等于成交成功 - 撤单请求不等于撤单完成 - 状态不明时必须进入正式 RECONCILING 路径 - 执行失败后不得凭主观猜测继续推进

一句话：

**OMS / Execution ****状态机，是把“被允许执行的动作”正式化为一套可推进、可中止、可恢复、可闭合的执行生命周期系统。**


## 2. Execution 对象的正式地位

Execution 对象的本质是：

**对某个已被治理链允许推进的受控动作，在执行协调层中的正式执行过程对象。**

它不是： - Lease 本身 - 风险批准结果本身 - 订单事实本身 - 成交事实本身 - 持仓事实本身

它可以： - 被创建 - 被批准提交 - 被提交 - 进入部分成交 - 被请求撤单 - 被取消 - 被失败中止 - 进入对账修复 - 被闭合完成

它不可以： - 绕过 Risk Governor 自行扩张风险 - 以本地猜测代替交易所事实 - 无限悬挂在不确定状态而无对账语义


## 3. 正式状态集合

Execution 正式状态集合如下：
- PENDING
- APPROVED
- SUBMITTED
- PARTIALLY_FILLED
- FILLED
- CANCEL_REQUESTED
- CANCELLED
- FAILED
- RECONCILING
- COMPLETED
- ABORTED

这些状态与《字段级与状态级规范》中的 execution_status 保持一致，但本文件更进一步定义其状态机语义与迁移规则。


## 4. 状态语义

## 4.1 PENDING

### 含义
- Execution 对象已创建，但尚未达到可提交条件
- 仍在等待前置治理链或内部准备完成

### 允许行为
- 被检查
- 被补充执行计划元信息
- 进入 APPROVED
- 被 ABORTED
- 在必要时被 FAILED

### 不允许行为
- 不得直接视为已提交
- 不得产生交易所写动作


## 4.2 APPROVED

### 含义
- Execution 已具备提交条件
- 已可由执行层向交易所适配链发出正式提交动作

### 允许行为
- 进入 SUBMITTED
- 在治理动作下被 ABORTED
- 在前置条件丢失时进入 FAILED

### 不允许行为
- 不得在未提交情况下宣称订单已存在


## 4.3 SUBMITTED

### 含义
- 执行请求已发出
- 正在等待交易所确认、同步链反馈与后续状态推进

### 允许行为
- 进入 PARTIALLY_FILLED
- 进入 FILLED
- 进入 CANCEL_REQUESTED
- 进入 FAILED
- 进入 RECONCILING

### 不允许行为
- 不得在回报缺失时默认成功
- 不得在状态不明时盲目再次重提同一风险


## 4.4 PARTIALLY_FILLED

### 含义
- 执行已部分成交，但尚未完成全部目标

### 允许行为
- 继续推进剩余执行
- 进入 CANCEL_REQUESTED
- 进入 FILLED
- 进入 RECONCILING
- 在必要时进入 ABORTED / FAILED

### 不允许行为
- 不得将未完成部分默认为已完成
- 不得借部分成交为理由扩大风险边界


## 4.5 FILLED

### 含义
- 执行目标对应的委托部分已经完成成交
- 但整个执行生命周期未必已经正式闭合

### 允许行为
- 进入 COMPLETED
- 在需要等待后续确认时进入 RECONCILING

### 不允许行为
- 不得等同于 position_state 已正式同步闭合


## 4.6 CANCEL_REQUESTED

### 含义
- 撤单请求已发出
- 等待交易所确认与事实同步

### 允许行为
- 进入 CANCELLED
- 进入 PARTIALLY_FILLED（若撤单前已发生部分成交）
- 进入 RECONCILING
- 进入 FAILED

### 不允许行为
- 不得在撤单确认前宣布已取消成功


## 4.7 CANCELLED

### 含义
- 撤单结果已正式确认
- 该执行已不再继续推进剩余未成交部分

### 允许行为
- 进入 COMPLETED
- 在必要时进入 RECONCILING（极少数同步冲突场景）

### 不允许行为
- 不得重新回到提交态继续推进同一执行对象


## 4.8 FAILED

### 含义
- 执行在某一步失败，且无法视为成功闭合

### 允许行为
- 进入 RECONCILING（若失败伴随状态不明）
- 进入 COMPLETED（仅在失败闭合后）
- 归档 / 审计 / 复盘

### 不允许行为
- 不得直接重新变回 APPROVED 或 SUBMITTED
- 不得在未重新创建执行对象时重用该执行


## 4.9 RECONCILING

### 含义
- 本地执行视图与外部事实之间存在不确定性
- 必须等待同步链、对账链或人工治理动作确认

### 允许行为
- 等待 Reconciliation 结果
- 根据对账结论进入 FILLED / CANCELLED / FAILED / COMPLETED
- 在必要时进入 ABORTED

### 不允许行为
- 不得凭猜测跳回正常推进路径
- 不得在未对账完成前创建重复风险动作

### 重要语义

RECONCILING 不是异常噪音状态，而是正式安全状态。

**出站迁移依据：**RECONCILING 的出站迁移（迁往 COMPLETED、FAILED、ABORTED 或继续保持 RECONCILING）必须以 Reconciliation Pipeline 产生的正式 reconciliation_result 为依据（见《Reconciliation 正式边界定义》EX-04）。不得以本地猜测或超时默认代替正式对账结论。


## 4.10 COMPLETED

### 含义
- 执行生命周期已经正式闭合
- 不论成功、取消还是失败，都已达到可归档的终结态

### 允许行为
- 归档
- 审计与复盘

### 不允许行为
- 不得再继续推进执行行为


## 4.11 ABORTED

### 含义
- 执行被主动中止，不再继续推进
- 通常由治理动作、上游撤销、冻结或保护性中止触发

### 允许行为
- 进入 COMPLETED
- 归档与复盘

### 不允许行为
- 不得重新恢复执行


## 5. 正式触发事件

Execution 状态迁移只能由正式事件触发。

### 5.1 事件类别
- execution_plan_event
- risk_gate_event
- submission_event
- venue_response_event
- cancel_event
- fill_event
- reconciliation_event
- operator_governance_event
- incident_event

### 5.2 典型事件示例
- execution_created
- execution_submission_approved
- execution_submit_sent
- venue_ack_received
- partial_fill_synced
- full_fill_synced
- cancel_requested
- cancel_confirmed
- submit_failed
- execution_state_unknown
- reconciliation_required
- reconciliation_resolved_as_filled
- reconciliation_resolved_as_cancelled
- operator_abort_requested
- incident_abort_applied

这些事件必须进入正式审计链。


## 6. 状态迁移总图（逻辑）

建议逻辑迁移关系如下：
- PENDING → APPROVED
- PENDING → ABORTED
- PENDING → FAILED
- APPROVED → SUBMITTED
- APPROVED → ABORTED
- APPROVED → FAILED
- SUBMITTED → PARTIALLY_FILLED
- SUBMITTED → FILLED
- SUBMITTED → CANCEL_REQUESTED
- SUBMITTED → FAILED
- SUBMITTED → RECONCILING
- PARTIALLY_FILLED → PARTIALLY_FILLED（剩余推进中）
- PARTIALLY_FILLED → FILLED
- PARTIALLY_FILLED → CANCEL_REQUESTED
- PARTIALLY_FILLED → RECONCILING
- PARTIALLY_FILLED → FAILED
- PARTIALLY_FILLED → ABORTED
- CANCEL_REQUESTED → CANCELLED
- CANCEL_REQUESTED → PARTIALLY_FILLED
- CANCEL_REQUESTED → RECONCILING
- CANCEL_REQUESTED → FAILED
- FILLED → COMPLETED
- FILLED → RECONCILING
- FAILED → RECONCILING
- FAILED → COMPLETED
- RECONCILING → FILLED
- RECONCILING → CANCELLED
- RECONCILING → FAILED
- RECONCILING → COMPLETED
- ABORTED → COMPLETED
- CANCELLED → COMPLETED

### 6.1 核心原则
- 执行生命周期总体应单向收敛到终态
- RECONCILING 是正式安全缓冲态
- COMPLETED 为闭合终态
- 同一执行对象不得无限反复进入提交链


## 7. 允许的迁移

## 7.1 创建与批准阶段

### PENDING -> APPROVED

前提： - 存在正式来源对象 - 已通过 Risk Governor - 当前系统模式允许提交 - 执行计划已就绪

### PENDING -> ABORTED

前提： - operator abort - upstream revoke - freeze / incident 阻断

### PENDING -> FAILED

前提： - 执行对象构建失败 - 核心必要字段缺失 - 提交前安全校验失败且不可恢复


## 7.2 提交阶段

### APPROVED -> SUBMITTED

前提： - 提交请求已正式发出 - 幂等检查通过 - 写入口可用

### APPROVED -> ABORTED

前提： - 提交前被 operator / incident / freeze 中止

### APPROVED -> FAILED

前提： - 提交前发现不可恢复错误


## 7.3 提交后的推进

### SUBMITTED -> PARTIALLY_FILLED

前提： - 同步链确认部分成交

### SUBMITTED -> FILLED

前提： - 同步链确认完整成交

### SUBMITTED -> CANCEL_REQUESTED

前提： - 正式撤单请求发出

### SUBMITTED -> FAILED

前提： - 提交失败且状态明确 - 执行无法继续

### SUBMITTED -> RECONCILING

前提： - 提交后状态不明 - ack 缺失 - 订单状态与本地视图冲突 - 必须交由对账链确认


## 7.4 部分成交阶段

### PARTIALLY_FILLED -> FILLED

前提： - 剩余部分完成成交

### PARTIALLY_FILLED -> CANCEL_REQUESTED

前提： - 正式发起撤单以结束剩余未成交部分

### PARTIALLY_FILLED -> RECONCILING

前提： - 剩余量状态不明 - 部分成交记录与本地状态冲突

### PARTIALLY_FILLED -> FAILED

前提： - 剩余执行出现不可恢复失败

### PARTIALLY_FILLED -> ABORTED

前提： - 受治理动作主动中止剩余执行


## 7.5 撤单阶段

### CANCEL_REQUESTED -> CANCELLED

前提： - 撤单确认完成

### CANCEL_REQUESTED -> PARTIALLY_FILLED

前提： - 撤单前已发生部分成交并被同步确认

### CANCEL_REQUESTED -> RECONCILING

前提： - 撤单结果不明 - 本地与交易所状态不一致

### CANCEL_REQUESTED -> FAILED

前提： - 撤单流程明确失败且无法确认状态闭合


## 7.6 闭合阶段

### FILLED -> COMPLETED

前提： - 执行已正式闭环 - 无未决对账问题

### FILLED -> RECONCILING

前提： - 成交后关键事实仍待对账确认

### FAILED -> RECONCILING

前提： - 失败伴随外部状态不明

### FAILED -> COMPLETED

前提： - 失败已闭合，且不存在进一步对账不确定性

### RECONCILING -> FILLED / CANCELLED / FAILED / COMPLETED

前提： - Reconciliation 给出正式结论

### ABORTED -> COMPLETED

前提： - 中止流程已正式闭合

### CANCELLED -> COMPLETED

前提： - 撤单流程已正式闭合


## 8. 禁止的迁移

以下迁移应明确禁止：

### 8.1 终态回流
- COMPLETED -> SUBMITTED
- COMPLETED -> PARTIALLY_FILLED
- ABORTED -> SUBMITTED
- FAILED -> SUBMITTED
- CANCELLED -> SUBMITTED

### 8.2 跳过批准直接提交
- PENDING -> SUBMITTED

除非未来有上位文档定义特殊保护性执行通道，否则禁止。

### 8.3 跳过提交直接成交
- APPROVED -> FILLED
- APPROVED -> PARTIALLY_FILLED

### 8.4 状态不明时直接宣布成功/失败
- SUBMITTED -> COMPLETED
- CANCEL_REQUESTED -> COMPLETED

除非存在清晰同步与闭合结论，否则禁止。

### 8.5 GUI / Learning 直接改执行状态

GUI、Learning Plane、报表层不得直接将 execution_status 从一个正式状态改到另一个正式状态。


## 9. 自动迁移 vs 人工/治理动作

## 9.1 允许自动发生的迁移

以下迁移通常允许自动发生： - PENDING -> APPROVED - APPROVED -> SUBMITTED - SUBMITTED -> PARTIALLY_FILLED - SUBMITTED -> FILLED - SUBMITTED -> RECONCILING - PARTIALLY_FILLED -> FILLED - CANCEL_REQUESTED -> CANCELLED - RECONCILING -> {FILLED\|CANCELLED\|FAILED\|COMPLETED} - FILLED -> COMPLETED - CANCELLED -> COMPLETED - ABORTED -> COMPLETED

### 说明

这些自动迁移必须仍然： - 有正式触发事件 - 有正式对象更新 - 有审计留痕

## 9.2 通常需要治理动作或人工参与的迁移

以下迁移通常需要 operator / governance / incident 动作参与： - PENDING -> ABORTED - APPROVED -> ABORTED - SUBMITTED -> CANCEL_REQUESTED - PARTIALLY_FILLED -> CANCEL_REQUESTED - PARTIALLY_FILLED -> ABORTED

### 特别说明

若上述迁移由 incident / emergency / reduce-only 等正式治理动作触发，可以自动由治理链推进，但仍应被视为正式治理动作，而非普通状态自然变化。


## 10. 状态进入后的行为约束

## 10.1 PENDING
- 不得写交易所
- 仅允许准备与检查

## 10.2 APPROVED
- 允许提交
- 不得视为订单已存在

## 10.3 SUBMITTED
- 必须等待正式回报或进入 reconciling
- 不得盲目重提同一风险

## 10.4 PARTIALLY_FILLED
- 只允许在批准边界内继续剩余动作
- 不得扩大风险

## 10.5 CANCEL_REQUESTED
- 等待正式撤单结果
- 不得假定已经取消

## 10.6 FILLED
- 允许闭环
- 不得替代持仓真相链

## 10.7 FAILED
- 允许复盘和必要对账
- 不得直接重用该执行对象再推进

## 10.8 RECONCILING
- 不得继续扩张风险
- 必须等待对账结论

## 10.9 ABORTED / CANCELLED / COMPLETED
- 仅允许归档、审计、复盘
- 不允许重新激活


## 11. RECONCILING 的正式安全语义

RECONCILING 是执行层最关键的安全状态之一，必须被正式承认，而不是被视为“技术上有点不确定”的噪音态。

### 11.1 应进入 RECONCILING 的典型场景
- 提交后 ACK 缺失
- 提交结果与本地视图冲突
- 撤单结果不明
- 部分成交数量与本地记录不一致
- 执行对象状态无法仅靠本地推导闭合

### 11.2 RECONCILING 中的原则
- 不猜测
- 不重复冒险
- 不默认成功
- 不默认失败
- 先对账，再推进


## 12. 与 Decision Lease State Machine 的关系

### 12.1 Lease 不等于 Execution

Lease 是受控意图对象；Execution 是执行过程对象。

### 12.2 正式边界

本状态机回答： > “已经被允许推进的动作，在执行层现在处于什么状态？”

Lease 状态机回答： > “该受控意图作为控制对象处于什么生命周期状态？”

因此： - BRIDGED 不等于 SUBMITTED - CONSUMED 通常在执行闭合后发生，但两者并不必然同一时刻


## 13. 与 Risk Governor 的关系

### 13.1 风险批准不是执行状态

Risk Governor 决定： - 能不能推进 - 以多大边界推进 - 是否 reduce-only

Execution 状态机决定： - 进入哪一个执行过程状态 - 如何处理执行中的不确定性

### 13.2 核心原则

Execution 可以比 Risk Governor 更保守： - 更早取消 - 更早放弃 - 更早进入 reconciling

但绝不能比 Risk Governor 更宽松。


## 14. 与 Order / Fill / Position 真相链、Reconciliation 的关系

### 14.1 执行状态不是最终事实

Execution 状态机可以跟踪过程，但最终事实应由： - Order Sync - Fill Sync - Position Sync - Reconciliation

共同闭合。

### 14.2 典型责任分工
- OMS / Execution：过程协调
- Order / Fill / Position Sync：事实同步
- Reconciliation：一致性裁决

### 14.3 正式边界

若执行过程与事实链不一致，应优先进入 RECONCILING，等待 Reconciliation 结论，而不是让执行层自行宣布最终事实。


## 15. 状态迁移对象模板

建议每次 Execution 状态迁移都形成正式对象：

execution_transition:
  transition_id: string
  execution_id: string
  previous_status: PENDING\|APPROVED\|SUBMITTED\|PARTIALLY_FILLED\|FILLED\|CANCEL_REQUESTED\|CANCELLED\|FAILED\|RECONCILING\|COMPLETED\|ABORTED
  next_status: PENDING\|APPROVED\|SUBMITTED\|PARTIALLY_FILLED\|FILLED\|CANCEL_REQUESTED\|CANCELLED\|FAILED\|RECONCILING\|COMPLETED\|ABORTED
  trigger_event_type: execution_plan_event\|risk_gate_event\|submission_event\|venue_response_event\|cancel_event\|fill_event\|reconciliation_event\|operator_governance_event\|incident_event
  trigger_event_id: string
  initiated_by: OMS\|Operator\|IncidentPolicy\|Reconciliation
  transition_reason_codes: []
  approval_required: true\|false
  approved_by: string\|null
  effective_at: datetime
  audit_event_ref: string


## 16. 漂移防护声明

以下倾向应视为 Execution 状态机漂移风险： - Execution 状态被 GUI 任意切换 - SUBMITTED 被误当成“订单肯定存在” - FILLED 被误当成“持仓真相已闭合” - RECONCILING 被当成技术噪音而被跳过 - 执行失败后直接重用旧执行对象继续推进 - Learning Plane 直接改 live 执行状态

一旦出现上述情况，应优先修正状态机与真相链边界，而不是接受为实现细节。


## 17. 一句话总纲

**OMS / Execution ****状态机的职责，是把已被治理链允许推进的动作，正式化为一套从待提交、已提交、部分成交、撤单、失败、对账修复到最终闭合的执行生命周期系统，使执行过程永远不是黑箱、不是猜测、不是前端局部状态，而是一个必须被正式管理、正式审计、正式闭合的过程对象。**
