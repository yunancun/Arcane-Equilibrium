# OpenClaw / Bybit 交易 Agent

# Reconciliation 正式边界定义 V1

## 0. 文档定位

本文件用于定义 **Reconciliation** 在 OpenClaw / Bybit 交易 Agent 中的正式职责边界。

本文件回答以下问题： - Reconciliation 的正式定位是什么 - 它接收什么输入，产出什么输出 - 它可以做什么，不可以做什么 - 它与 OMS / Execution、Order / Fill / Position 真相链、Risk Governor、Control Plane、Audit、Learning 的边界是什么 - 当本地视图与外部事实不一致时，谁有权裁定、谁有权触发冻结、谁有权触发人工介入 - Reconciliation 如何参与 incident、reduce-only、freeze 与恢复门控

本文件 **不负责**： - 交易所 API 具体细节 - GUI 页面布局 - 数据库物理表结构 - 具体对账频率、轮询参数、重试次数数值 - 策略逻辑本身

如与《项目宪法 / 根原则》冲突，以宪法为最高约束。


## 1. 正式定义

### 1.1 Reconciliation 的本质

Reconciliation 不是策略层，不是执行层，也不是交易所适配层。

它的正式定义是：

**系统中负责对本地过程视图、同步链事实视图与外部交易所事实进行一致性校验、冲突识别、正式裁定与纠偏触发的独立事实治理层。**

它的目标不是“让流程看起来顺畅”，而是确保： - 本地视图不会在事实不明时自我说服 - 执行链不会在状态不明时继续扩大风险 - 风险治理基于可信事实而不是基于猜测 - 关键对象在出现冲突时有正式裁定机制

### 1.2 一句话定位

**Reconciliation ****的职责不是帮助系统更乐观，而是在事实不清时强迫系统承认“不知道”，并把这种不知道转化为正式治理动作。**


## 2. 在全链路中的位置

Reconciliation 在主链中的正式位置如下：

**Lease / Risk / OMS ****推进**** → Venue Adapter / Exchange → Order / Fill / Position Sync → Reconciliation → ****正式一致性结论**** → ****风险**** / ****执行**** / ****控制平面后续动作**

### 2.1 关键语义
- OMS / Execution 负责过程协调
- Order / Fill / Position Sync 负责同步外部事实
- **Reconciliation ****负责判断这些事实与本地视图是否一致，以及不一致时应如何治理**

因此： - Reconciliation 不是“附加校验” - Reconciliation 是事实治理闭环的一部分


## 3. 核心职责

Reconciliation 必须承担以下核心职责：
- **正式对象一致性校验**
- **本地视图与外部事实冲突识别**
- **一致性状态正式裁定**
- **不确定状态下的风险保护触发**
- **对账驱动的**** freeze / reduce-only / manual_review ****建议或触发**
- **对账结果审计留痕**
- **为恢复与复盘提供正式事实基线**


## 4. Reconciliation 可以校验的对象范围

至少包括以下核心对象： - order_state - fill_state - position_state - account_state（必要时） - execution_state 与上述事实对象的一致性 - decision_lease 与执行闭环的一致性（间接）

### 4.1 特别说明

Reconciliation 主要校验的是： - 本地过程对象 vs 正式事实对象 - 同步链对象 vs 交易所外部事实 - 不同正式对象之间是否逻辑一致

而不是重新做策略判断。


## 5. 输入

Reconciliation 的输入必须优先来自正式对象与外部事实源，而不是展示层状态。

### 5.1 主要输入对象
- execution_state
- order_state
- fill_state
- position_state
- account_state
- venue adapter 回报
- exchange 查询结果
- system_state
- risk_state
- health_state
- audit_event（必要时）

### 5.2 可引用但不能代替正式输入的对象
- GUI 页面显示状态
- 前端缓存
- 临时调试日志
- Learning 复盘摘要
- H0/H1-H5 文本解释

这些对象可以辅助调查，但不能成为正式一致性裁定依据。


## 6. 输出

Reconciliation 的正式输出必须是结构化一致性结论与治理建议/触发，而不是自由文本意见。

### 6.1 正式输出对象
- reconciliation_result
- reconciliation_action_request
- audit_event

### 6.2 正式输出类型
- in_sync
- lagging
- mismatch_detected
- state_unknown
- manual_review_required
- freeze_recommended
- reduce_only_recommended
- incident_escalation_required

### 6.3 输出应至少包含
- reconciliation_id
- target_object_type
- target_object_id
- consistency_result
- source_snapshot_refs
- reason_codes
- risk_impact_assessment
- action_required
- decided_at
- decided_by_module


## 7. Reconciliation 可以做什么

## 7.1 正式裁定一致性

Reconciliation 可以正式给出以下裁定： - 对象一致 - 对象暂时落后但可接受 - 对象已存在 mismatch - 当前事实状态未知 - 必须人工复核

### 重要说明

这里的“裁定”指事实一致性裁定，不是市场判断裁定。

## 7.2 触发保守治理动作

当对账发现以下情形时，Reconciliation 应能触发或建议： - RECONCILING 保持 - reduce_only - freeze_scope - manual_review - incident_escalation

### 典型场景
- 提交后状态不明
- 撤单结果不明
- 部分成交数量不一致
- 本地持仓与交易所持仓不一致
- 订单状态与执行状态逻辑冲突

## 7.3 驱动事实闭合

Reconciliation 可以为以下对象提供正式闭合依据： - 执行对象应进入哪种终态 - 订单状态是否可被确认 - 持仓状态是否已可信闭合

但它不直接改写交易所事实，只裁定系统应采用哪个正式一致性结论。


## 8. Reconciliation 不可以做什么

## 8.1 不负责重新下单或撤单

Reconciliation 不直接： - 下新单 - 撤单 - 改单 - 平仓

它可以触发正式治理动作请求，但执行应由 OMS / Execution 负责。

## 8.2 不负责放宽风险

Reconciliation 发现一致性良好，不等于自动放宽 Risk Governor 风险模式。

它可以提供恢复依据，但不替代 Risk Governor 或 Recovery Governance。

## 8.3 不伪造事实

Reconciliation 不应： - 凭猜测补写成交 - 凭本地预期宣布订单已填满 - 在无法确认时硬判定为成功

### 核心原则

**不确定就标不确定，不可用猜测把系统从不确定中“拉出来”。**

## 8.4 不替代审计与复盘

Reconciliation 输出的是正式一致性结论，但不替代： - incident review - learning attribution - change request

这些应由各自治理链承担。


## 9. 正式一致性状态

建议 Reconciliation 至少使用以下正式一致性状态：
- IN_SYNC
- LAGGING
- MISMATCH_DETECTED
- STATE_UNKNOWN
- MANUAL_REVIEW_REQUIRED

### 9.1 IN_SYNC
- 本地视图与外部事实一致
- 可作为正常推进或闭合依据

### 9.2 LAGGING
- 同步滞后但暂未发现实质冲突
- 需要观察，不一定立即升级事故

### 9.3 MISMATCH_DETECTED
- 已发现正式冲突
- 必须触发保守治理动作评估

### 9.4 STATE_UNKNOWN
- 关键对象当前无法被可靠裁定
- 必须优先采取保守处理

### 9.5 MANUAL_REVIEW_REQUIRED
- 仅靠自动对账无法给出可接受结论
- 需人工介入


## 10. 与 OMS / Execution 的边界

### OMS / Execution 的职责
- 执行协调
- 状态推进
- 提交 / 撤改单 / 部分成交管理
- 进入 RECONCILING

### Reconciliation 的职责
- 对执行过程与正式事实是否一致做裁定
- 当不一致时触发治理动作建议

### 明确边界

OMS / Execution 可以说： - “我现在不知道结果” - “我需要进入 RECONCILING”

Reconciliation 才能正式裁定： - 该对象是否一致 - 是否 mismatch - 是否必须 freeze / reduce_only / manual_review

因此： - Execution 不替代 Reconciliation - Reconciliation 也不替代 Execution 发动作


## 11. 与 Order / Fill / Position 真相链的边界

### Sync 链职责
- 拉取、同步、标准化交易所事实
- 更新正式事实对象

### Reconciliation 职责
- 比对这些正式事实与本地过程对象
- 在冲突时给出正式一致性结论

### 明确边界

Sync 链负责“拿到事实”，Reconciliation 负责“判断这些事实与系统内其他对象是否一致”。


## 12. 与 Risk Governor 的边界

### Risk Governor 的职责
- 最终风险裁决
- 决定是否 reduce-only / freeze / circuit breaker

### Reconciliation 的职责
- 提供一致性层面的正式依据
- 可触发或建议风险保护动作

### 明确边界

Reconciliation 可以输出： - freeze_recommended - reduce_only_recommended - incident_escalation_required

但最终风险模式与范围治理，仍由 Risk Governor / Incident Policy / Control Plane 正式落地。


## 13. 与 Control Plane / Operator Console 的边界

### Control Plane 的职责
- 展示对账状态
- 承载人工干预入口
- 承载恢复与调查入口

### Reconciliation 的职责
- 输出正式一致性裁定

### 明确边界

Control Plane 不得： - 直接把前端观察结果写成 in_sync - 直接把某个 mismatch 在页面上“点一下就没了”

如果 Operator 处理了问题，仍需通过正式动作： - 重同步 - freeze - manual review - recovery approval

并进入审计链。


## 14. 与 Audit 的边界

### Audit 的职责
- 记录正式事件

### Reconciliation 的职责
- 产出正式一致性结论与动作建议

### 明确边界

Reconciliation 每次重要裁定至少应生成： - 正式 reconciliation_result - 关联 audit_event

关键 mismatch、state_unknown、manual_review_required 不得只停留在普通日志。


## 15. 与 Learning Plane 的边界

### Learning Plane 的职责
- 复盘为什么会 mismatch
- 归因为什么会进入 state_unknown
- 提出改进建议

### Reconciliation 的职责
- 在 live 中对一致性做正式裁定

### 明确边界

Learning 可以读取 Reconciliation 结果，但不得： - 直接把某次历史推论回写成 live 一致性结论 - 直接更改 live 对账规则而不走 Change Control


## 16. 与 Incident / Recovery 的关系

### 16.1 Incident 触发

以下 Reconciliation 结果应至少触发 incident 评估： - MISMATCH_DETECTED - STATE_UNKNOWN 持续存在 - 同类 mismatch 连续出现 - 关键对象（持仓/订单/成交）真相链冲突

### 16.2 Recovery 前提

若历史上发生对账冲突，则恢复到更宽松模式前应至少满足： - mismatch 已确认消失 - sync 链稳定 - 执行链与事实链重新一致 - 观察窗口完成


## 17. Reconciliation 动作分级

建议至少支持以下正式动作分级：

### 17.1 Observe
- 仅记录并继续观察
- 适用于 LAGGING

### 17.2 Hold
- 暂停该对象继续自动推进
- 适用于轻度状态不明

### 17.3 Reduce-Only Recommended
- 建议切换相关范围为保守收缩路径
- 适用于关键对象状态不明但账户仍有风险暴露

### 17.4 Freeze Recommended
- 建议冻结某 symbol / 策略簇 / 执行链 / 授权范围
- 适用于 mismatch 已形成

### 17.5 Incident Escalation
- 正式上报为 incident 或 critical incident 评估对象


## 18. Reconciliation 结果对象模板

建议每次正式对账裁定至少形成如下对象：

reconciliation_result:
  reconciliation_id: string
  target_object_type: order\|fill\|position\|account\|execution
  target_object_id: string
  consistency_result: IN_SYNC\|LAGGING\|MISMATCH_DETECTED\|STATE_UNKNOWN\|MANUAL_REVIEW_REQUIRED
  local_snapshot_ref: string
  external_snapshot_ref: string
  compared_at: datetime
  reason_codes: []
  risk_impact_assessment: low\|medium\|high\|critical
  action_required: none\|observe\|hold\|reduce_only_recommended\|freeze_recommended\|incident_escalation_required\|manual_review_required
  decided_by_module: Reconciliation
  audit_event_ref: string


## 19. 典型场景规则

### 19.1 提交后 ACK 缺失
- Execution 应进入 RECONCILING
- Reconciliation 应输出 STATE_UNKNOWN 或 LAGGING
- 若持续无法确认，应升级为 MANUAL_REVIEW_REQUIRED 或 MISMATCH_DETECTED

### 19.2 撤单结果不明
- 不得默认已撤成功
- 应进入 RECONCILING
- 若风险暴露仍可能存在，应建议 reduce_only 或 freeze

### 19.3 本地持仓与交易所持仓不一致
- 应直接视为高优先级一致性问题
- 至少输出 MISMATCH_DETECTED
- 应评估 freeze / incident escalation

### 19.4 部分成交数量不一致
- 不得继续按本地剩余量推进
- 先进入 RECONCILING
- 等待正式一致性结论


## 20. 漂移防护声明

以下倾向应视为 Reconciliation 边界漂移风险： - 对账被简化为普通日志比对 - mismatch 只在页面提示，不进入正式治理链 - Execution 自己宣布“应该没事”而跳过对账 - GUI 人工把 mismatch 状态点掉就算修复 - Learning 历史推论直接改写 live 一致性规则 - 在 state_unknown 下继续扩张风险

一旦出现上述趋势，应优先修正对账治理边界，而不是接受“先跑起来再说”。


## 21. 一句话总纲

**Reconciliation ****的正式职责，是在本地视图、同步链事实与外部交易所事实之间建立独立的一致性裁定层：它不负责下单、不负责放宽风险、不负责伪造事实，但必须在事实不明时迫使系统承认“不知道”，并把这种不确定性正式转化为**** hold、reduce-only、freeze、manual review ****或**** incident escalation ****等治理动作。**
