# OpenClaw / Bybit 交易 Agent

# Audit / Incident / Circuit Breaker Policy V1.1

## 0. 文档定位

本文件用于定义 OpenClaw / Bybit 交易 Agent 中与 **审计、异常、近失误、事故、熔断、冻结、恢复、复盘** 相关的正式治理制度。

本文件回答以下问题： - 什么是审计对象，什么是普通日志 - 什么是异常（anomaly）、近失误（near-miss）、事故（incident）、重大事故（critical incident） - 什么情况下系统必须降级、冻结、只减仓或熔断 - 哪些主体可以触发这些动作 - 熔断后如何调查、记录、回滚与恢复 - 什么条件下可以重新放开交易

本文件是对以下上位文件的治理延伸： - 《项目宪法 / 根原则》 - 《H0-H1~H5-I 正式边界定义》 - 《字段级与状态级规范》 - 《Truth Source & Ownership Matrix》 - 全部正式边界定义文件（EX-01～EX-05） - 《Promotion / Change Control / Authorization Policy》

本文件 **不负责**： - GUI 具体布局 - API 具体路由 - 数据库物理设计 - 策略数学细节 - 具体阈值数值

如与上位文件冲突，以《项目宪法 / 根原则》为最高约束。


## 1. 核心目标

本文件的核心目标是：

**确保系统在出现异常、状态冲突、风控风险、执行异常、审计缺口或未知行为时，能够以正式制度而非临时人工拍脑袋的方式，快速保护账户、保全审计链、限制风险扩散、完成调查复盘，并在满足明确恢复条件前禁止不受控重新放开。**


## 2. 审计的正式地位

### 2.1 审计不是附加功能

审计不是“方便以后看一看”的辅助功能，而是系统成立条件的一部分。

如果某关键动作无法通过正式对象和正式事件在事后还原： - 触发前状态 - 判断依据 - 风控结论 - 授权依据 - 执行动作 - 最终后果

则视为治理失败，而不是“记录稍微少了点”。

### 2.2 审计对象与普通日志的区别

#### 正式审计对象

必须进入正式审计链的事件至少包括： - system_mode 变化 - operator override - h0_decision 结果 - deliberation 完成 - lease 注册 / 撤销 / 冻结 / 过期 - risk_rejected / risk_downgraded / circuit_breaker_triggered - execution_submitted / failed / cancelled - order / fill / position 对账异常 - 授权变化 - 事故认定 - 恢复批准

#### 普通运行日志

普通日志可以记录： - 调试信息 - 性能细节 - 非关键中间状态 - 原始 tracing 信息

普通日志不得替代正式审计对象。

### 2.3 审计链原则

正式审计链必须满足： - 不可静默绕过 - 关键事件不可被前端伪造 - 关键状态跳变必须能关联对象 ID - 人工动作必须进入审计链 - 审计事件应具备时间、行为体、对象、结果、原因代码


## 3. 事件分级体系

本系统中的异常事件分为五级：
- notice
- anomaly
- near_miss
- incident
- critical_incident

### 3.1 notice

定义： - 轻微、不影响风险边界与核心治理链的可观测异常

示例： - 单次接口轻微延迟抖动 - 某个非关键摘要字段暂时缺失 - 某次 shadow 推理超时但主链未受影响

默认动作： - 记录 - 观察 - 不触发模式变化

### 3.2 anomaly

定义： - 偏离正常预期、值得关注，但尚未构成事故或近失误

示例： - H0 与 H1-H5 多次出现高冲突 - 某 symbol 的 market_state 稳定性异常差 - 局部对账延迟增加但尚未 mismatch - 执行滑点显著高于历史中位但未触发风险穿透

默认动作： - 记录正式 audit_event - 增加监控 - 视情况降频 / 缩范围

### 3.3 near_miss

定义： - 本可导致事故或风险穿透，但最终被保护机制挡住，或仅因运气/外部因素未造成实质损害

示例： - 订单本应重复提交，但幂等机制成功阻断 - 风控差点被绕过，但最终被统一入口拦下 - 系统本应在异常状态继续开仓，但 reduce_only 保护生效 - 状态冲突本可能导致错误平仓，但人工及时接管避免损失

默认动作： - 正式记录 near-miss - 进入复盘 - 暂停该链路扩张性变更 - 视严重程度触发局部降级

### 3.4 incident

定义： - 已对系统行为、账户安全、治理链完整性或审计完整性造成实质影响的正式事故

示例： - 状态冲突导致错误行为发生 - risk_state 与实际执行链不一致并产生实质影响 - 不该开的单被开出 - 该撤的 Lease 未及时撤销并进入下游 - 审计链关键事件丢失 - 对账 mismatch 已影响 live 决策

默认动作： - 立即进入事故处置流程 - 相关范围降级 / 冻结 - 必须人工审查

### 3.5 critical_incident

定义： - 直接威胁账户生存、治理基线或系统可信性的重大事故

示例： - 风控穿透 - 大规模重复下单 - 统一写入口失控 - 真相源混乱导致关键对象不可可信 - 熔断机制失效 - 事故期间系统仍持续扩大风险 - 无法解释的 live 行为且审计链不完整

默认动作： - 立即触发 CIRCUIT_BREAKER - 全局或大范围 freeze - 禁止授权扩张 - 禁止恢复前继续 live 自主


## 4. 风险响应模式体系

系统正式运行模式至少包括： - NORMAL - CAUTIOUS - REDUCED - DEFENSIVE - CIRCUIT_BREAKER - MANUAL_REVIEW

### 4.1 NORMAL

含义： - 正常运行 - 已授权范围内允许正常行为

### 4.2 CAUTIOUS

含义： - 轻度保护模式

典型动作： - 提高入场门槛 - 降低新仓频率 - 下调建议仓位 - 增加人工关注度

适用情形： - anomaly 增多 - 数据质量轻度下降 - 执行摩擦明显升高

### 4.3 REDUCED

含义： - 收缩运行模式

典型动作： - 仅允许高置信机会 - 明显缩小授权范围 - 减小风险预算 - 局部暂停某策略簇 / symbol

适用情形： - near-miss 发生 - 局部事故尚未扩散 - 决策链与执行链稳定性下降

### 4.4 DEFENSIVE

含义： - 防御模式

典型动作： - 禁止开新风险 - 只允许减仓或保护性操作 - 冻结高风险路径 - 等待人工复核

适用情形： - incident 已确认 - 对账异常未解 - 风险与状态一致性不可靠

### 4.5 CIRCUIT_BREAKER

含义： - 熔断模式

典型动作： - 停止所有非保护性新增行为 - 全局或大范围冻结 - 所有恢复动作必须走正式审批

适用情形： - critical incident - 风控穿透 - 真相源冲突导致 live 可信性失效 - 统一写入口或熔断链本身出现严重问题

### 4.6 MANUAL_REVIEW

含义： - 系统主动把决策交还给人

典型动作： - 禁止自动推进某类关键决策 - 要求人工审查后继续

适用情形： - 未知新型异常 - 多层结论冲突严重 - 超出模型适用边界


## 5. 熔断触发制度

## 5.1 自动触发源

以下链路可自动触发熔断或建议熔断： - Risk Governor - Health / Monitoring Pipeline - Reconciliation Pipeline - Execution Safety Guard - Incident Detection Pipeline

### 5.2 必须考虑熔断的典型场景

至少包括： - 风控穿透或接近穿透 - 状态冲突导致 live 行为不可可信 - 订单重复提交风险已实质化 - 关键真相源失去可信性 - 审计链关键缺口 - 对账 mismatch 持续且影响 live - 系统仍在异常中持续扩大风险 - 人工无法解释的关键行为出现

### 5.3 熔断粒度

熔断不一定总是全局，但必须有明确粒度： - symbol 级熔断 - 策略簇级熔断 - 执行链级熔断 - live 写入级熔断 - 全局熔断

### 5.4 熔断后的默认行为

除保护性动作外： - 不开新仓 - 不扩张授权 - 不上线新变更 - 不自动恢复


## 6. 只减仓（Reduce-Only）制度

### 6.1 Reduce-Only 的正式定位

reduce_only 不是临时技巧，而是正式风险响应模式的一部分。

### 6.2 应进入 Reduce-Only 的典型场景
- 风险状态不再允许新风险
- 对账链部分失真但持仓事实仍可可信读取
- 执行链健康不足以支撑新开仓
- 市场异常、流动性脆弱、但仍需保命减仓
- 事故处理中需要防止继续扩大风险

### 6.3 Reduce-Only 的边界

Reduce-Only 允许： - 减仓 - 平仓 - 必要保护性调整

Reduce-Only 不允许： - 新增风险暴露 - 借故加仓 - 借“重建仓位”名义创建新风险


## 7. 事故处置流程

## 7.1 处置阶段

事故处置至少分为六个阶段：
- detect
- contain
- stabilize
- investigate
- remediate
- recover

### 7.2 detect（发现）

目标： - 识别异常是否已上升为 near_miss / incident / critical_incident

要求： - 形成正式 audit_event - 绑定对象范围 - 绑定初步影响范围

### 7.3 contain（围堵）

目标： - 阻止风险继续扩散

可能动作： - symbol 级冻结 - 策略级冻结 - reduce_only - global circuit breaker - operator takeover

### 7.4 stabilize（稳定）

目标： - 确保账户与系统进入可调查状态

要求： - 停止扩大风险 - 保留审计链 - 固定关键状态快照 - 禁止未经审批继续 live 扩张

### 7.5 investigate（调查）

目标： - 查清根因、影响范围、是否存在制度缺口

至少回答： - 事实发生了什么 - 哪一层先出现异常 - 哪个守卫没有挡住 - 哪个对象真相链出现冲突 - 审计是否完整 - 是否有近失误被提前忽视

### 7.6 remediate（修复）

目标： - 修复问题、验证修复、形成变更与回滚记录

要求： - 不允许“边 live 边试修”作为默认方案 - 修复建议应进入正式变更治理流程

### 7.7 recover（恢复）

目标： - 在满足正式恢复条件后，逐步恢复到可接受运行级别

要求： - 不允许从事故状态直接跳回全面正常 - 应经过阶段性恢复


## 8. 事故调查最小模板

建议每个 incident / critical_incident 至少记录：

incident_record:
  incident_id: string
  severity: near_miss\|incident\|critical_incident
  detected_at: datetime
  detected_by: module\|operator
  affected_scope:
    symbols: []
    strategies: []
    modes: []
    objects: []
  initial_actions: []
  account_impact:
    pnl_impact: number\|null
    risk_impact: string
  root_cause_family: state_conflict\|execution_failure\|risk_gap\|audit_gap\|auth_gap\|logic_error\|unknown
  truth_source_integrity: intact\|degraded\|broken
  audit_integrity: intact\|partial\|broken
  containment_complete: true\|false
  remediation_required: true\|false
  authorization_freeze_required: true\|false
  recovery_approved_by: string\|null


## 9. 恢复制度（Recovery Policy）

## 9.1 恢复不是默认动作

系统在以下条件全部满足前，不应恢复到更高运行级别： - 事故已被正式认定与记录 - 风险已被围堵 - 根因分析已完成到可接受程度 - 对应修复已完成或有明确隔离措施 - 审计链已确认完整或缺口已被正式标记 - 恢复范围已定义清楚 - 恢复批准已形成正式记录

### 9.2 恢复分级

恢复应按下列顺序渐进： - halted / circuit_breaker → manual_review → defensive → reduced → cautious → normal

不允许无条件跨级恢复。

### 9.3 恢复批准权

以下情形必须由 Operator 或正式审批路径批准恢复： - critical_incident 后恢复 - 涉及真相源完整性问题的恢复 - 涉及授权重新开启的恢复 - 涉及统一写入口曾异常的恢复


## 10. 近失误（Near-Miss）制度

### 10.1 Near-Miss 的正式意义

Near-miss 不应被视为“没出事就算了”，而应视为：

**系统本可能出事，只是被某道防线挡住了，或侥幸未造成损害。**

### 10.2 Near-Miss 的治理要求

Near-miss 至少应触发： - 正式记录 - 原因分类 - 是否需要新增守卫评估 - 是否冻结相关扩张性变更评估 - 是否触发局部降级评估

### 10.3 近失误累计效应

同类 near-miss 重复出现，应视为 incident 前兆。

当同一类 near-miss 在一定窗口内连续出现时，应： - 自动提高严重等级评估 - 至少进入 CAUTIOUS 或 REDUCED - 暂停相关放权与上线扩张


## 11. 与变更冻结的关系

事故或 near-miss 发生后，应评估是否进入变更冻结窗口。

至少以下情况应触发冻结评估： - 审计链缺口 - 真相源冲突 - 风控守卫失效 - 统一写入口行为异常 - 恢复条件未满足

冻结期间： - 禁止授权扩张 - 禁止自动生效任何非保守型变更 - 禁止 broad live rollout - 仅允许保护性修复与必要回滚


## 12. Operator 的职责与权限

### 12.1 Operator 在事故中的角色

Operator 不是单纯知情者，而是事故治理链中的最终责任人。

### 12.2 Operator 至少必须拥有
- 事故认定权
- 冻结权
- 熔断权
- 恢复批准权
- 局部撤权权
- 全局降级权
- 调查发起权
- 复盘结论确认权

### 12.3 Operator 不应做的事
- 跳过审计直接处理
- 为求恢复速度而绕过正式调查
- 在根因不明时贸然恢复到正常模式


## 13. 事故后的复盘要求

### 13.1 复盘不是可选项

对 incident 与 critical_incident，复盘是必需项；对 near_miss，复盘是强建议项。

### 13.2 复盘至少应回答
- 事实发生了什么
- 为什么系统没能在更前面挡住
- 哪道守卫起了作用 / 没起作用
- 哪些指标其实已经发出预警
- 为什么没有更早降级
- 是局部问题还是制度问题
- 是否需要新增守卫 / 回滚 / 撤权 / 冻结扩张

### 13.3 复盘产出

复盘至少应产出： - 正式 incident review 记录 - 是否形成 change_request - 是否形成 de-authorization 动作 - 是否形成新增 guard 提案 - 是否要求更新审计字段或状态规范


## 14. 恢复后的观察期制度

### 14.1 观察期必要性

事故后恢复不等于问题已经完全消失。

### 14.2 观察期要求

恢复后应设置明确观察期，在观察期内： - 降低授权范围 - 提高审计密度 - 增加人工检查频率 - 暂停相关放权申请

### 14.3 观察期结束条件

至少应满足： - 无重复问题 - 核心指标回稳 - 对账、审计、健康链稳定 - 无新增 near_miss 聚集


## 15. 一句话总纲

**Audit / Incident / Circuit Breaker Policy ****的目标，是让系统在异常和事故面前，优先保护账户、保全审计链、限制风险扩散、禁止不受控恢复，并通过正式调查、修复、回滚与渐进恢复制度，把“出事后的治理能力”变成系统的内生能力，而不是临时应急反应。**
