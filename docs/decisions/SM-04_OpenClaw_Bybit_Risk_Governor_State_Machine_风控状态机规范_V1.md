# OpenClaw / Bybit 交易 Agent

# Risk Governor State Machine Specification V1

## 0. 文档定位

本文件用于定义 **Risk Governor** 的正式状态机规范。

本文件回答以下问题： - Risk Governor 具有哪些正式状态 - 各状态的语义是什么 - 哪些事件可以触发状态迁移 - 哪些主体可以触发这些迁移 - 哪些迁移是自动触发，哪些必须人工批准 - 哪些迁移是禁止的 - 进入某状态后系统允许什么、不允许什么 - 状态恢复与升级的正式路径是什么

本文件是以下文件的下沉落地规范： - 《项目宪法 / 根原则》 - 《字段级与状态级规范》 - 《Risk Governor 正式边界定义》 - 《Audit / Incident / Circuit Breaker Policy》 - 《Promotion / Change Control / Authorization Policy》

本文件 **不负责**： - 风险阈值具体数值 - GUI 页面实现 - API 路由细节 - 数据库建表细节 - 交易所适配层代码

如与上位文件冲突，以《项目宪法 / 根原则》为最高约束。


## 1. 设计目标

Risk Governor 状态机的目标，是把“风险治理模式”从模糊概念变成正式、可审计、可回放、可验证的状态系统。

它必须保证： - 风险模式不是任意字符串 - 状态切换不是隐性热改 - 进入保守状态有明确触发条件 - 恢复到更宽松状态有明确前提条件 - 任何关键状态跃迁都能被审计与复盘

一句话：

**Risk Governor ****的状态机，是系统风险治理意志的正式机械表达。**


## 2. 正式状态集合

Risk Governor 正式状态集合如下：
- NORMAL
- CAUTIOUS
- REDUCED
- DEFENSIVE
- CIRCUIT_BREAKER
- MANUAL_REVIEW

这些状态与《Audit / Incident / Circuit Breaker Policy》保持一致，但本文件更进一步定义其状态机语义与迁移规则。


## 3. 状态语义

## 3.1 NORMAL

### 含义
- 正常风险治理模式
- 允许在授权矩阵与风控边界内对新风险做常规裁决

### 允许行为
- 在已授权范围内正常审查并批准新风险
- 常规缩仓 / 拒绝 / downsize / pass
- 常规 Lease 风险放行

### 不允许行为
- 绕过授权矩阵
- 绕过健康检查
- 忽略近失误或事故前兆

### 典型进入条件
- 系统健康稳定
- 无未解决 incident
- 无熔断进行中
- 关键链路（审计、对账、真相源）完整


## 3.2 CAUTIOUS

### 含义
- 轻度保守模式
- 风险治理仍允许新风险，但门槛显著提高

### 允许行为
- 仅在更高置信 / 更低维护 / 更低风险场景下批准新风险
- 更频繁地输出 downsize
- 更频繁地输出 manual_review_required

### 不允许行为
- 像 NORMAL 一样默认放行边缘机会
- 忽视轻度异常累积

### 典型进入条件
- anomaly 增多
- 数据质量轻度下降
- 执行摩擦上升
- 强对手主导迹象增强导致 edge 不确定性变高
- 某类 near-miss 的前兆出现


## 3.3 REDUCED

### 含义
- 收缩模式
- 仍可能允许新风险，但范围、仓位、策略簇、symbol 数量或订单类型明显受限

### 允许行为
- 只批准最保守、最高质量、最低维护的机会
- 强制大比例 downsize
- 局部冻结某些 symbol / 策略簇 / 行为类型

### 不允许行为
- 正常频率地创建新风险
- 扩张授权范围
- 宽松地恢复到普通行为分布

### 典型进入条件
- near-miss 已确认
- anomaly 聚集
- 局部 incident 影响尚未完全扩大但已需收缩
- 某关键链路稳定性明显下降
- 对账链出现持续 lagging 或局部 mismatch 风险


## 3.4 DEFENSIVE

### 含义
- 防御模式
- 默认禁止新增风险，只允许保命性质或治理要求的动作

### 允许行为
- reduce-only
- 保护性减仓 / 平仓
- 必要的冻结、撤销、保护性调整
- 为调查和稳定服务的最小必要动作

### 不允许行为
- 任何扩张性新风险
- 授权扩张
- 正常策略推进

### 典型进入条件
- incident 已确认
- 风险 / 状态一致性不再可靠
- 核心链路健康不足以支持新增风险
- 审计链缺口需要先稳定后调查


## 3.5 CIRCUIT_BREAKER

### 含义
- 熔断模式
- 系统处于强制停止非保护性推进的状态

### 允许行为
- emergency stop 后的保命动作
- 必要的 reduce-only
- 事故围堵与恢复准备动作
- 审计、调查、校准、重同步

### 不允许行为
- 新增风险
- 恢复前的自动 live 推进
- 放权
- 非保守型变更上线

### 典型进入条件
- critical incident
- 风控穿透或接近穿透
- 真相源完整性失效
- 统一写入口可信性失效
- 审计链关键缺口影响系统可信性


## 3.6 MANUAL_REVIEW

### 含义
- 人工复核模式
- 系统不完全停摆，但某类关键决策必须等待人工参与

### 允许行为
- 已有风险的保守管理
- 明确规定范围内的人工协同决策
- 事故恢复前的有限审查动作

### 不允许行为
- 在需要人工复核的对象上继续自动推进
- 以“系统已经很确定”为理由跳过人工

### 典型进入条件
- 新型异常情境
- 多层结论冲突过大
- 风险结论与授权结论冲突严重
- 恢复前的审查期


## 4. 正式触发事件

Risk Governor 状态迁移只能由正式事件触发。

### 4.1 事件类别
- health_event
- risk_event
- incident_event
- authorization_event
- operator_governance_event
- recovery_event
- reconciliation_event
- execution_safety_event

### 4.2 典型事件示例
- health_degraded
- data_quality_unreliable
- daily_loss_limit_warning
- drawdown_threshold_warning
- near_miss_recorded
- incident_confirmed
- critical_incident_confirmed
- reconciliation_mismatch_detected
- audit_integrity_broken
- operator_emergency_stop
- operator_manual_review_required
- recovery_approved
- observation_window_completed

这些事件必须进入正式审计链，而不是只存在于前端或日志中。


## 5. 状态迁移总图（逻辑）

建议逻辑迁移关系如下：
- NORMAL → CAUTIOUS
- CAUTIOUS → REDUCED
- REDUCED → DEFENSIVE
- DEFENSIVE → CIRCUIT_BREAKER
- 任意状态 → MANUAL_REVIEW
- MANUAL_REVIEW 可回到更保守或更宽松状态（视审批）
- CIRCUIT_BREAKER → DEFENSIVE → REDUCED → CAUTIOUS → NORMAL

### 5.1 核心原则
- 保守方向升级可以自动触发
- 宽松方向恢复必须满足条件，且通常需要审批
- 不允许从严重状态直接跳回 NORMAL


## 6. 允许的迁移

## 6.1 自动允许的保守化迁移

### NORMAL -> CAUTIOUS

可由以下事件触发： - anomaly 聚集 - 轻度健康下降 - 执行摩擦明显变差 - 数据质量降为 degraded - 连续 near-miss 前兆

### CAUTIOUS -> REDUCED

可由以下事件触发： - near-miss 正式记录 - 健康进一步下降 - 局部状态一致性问题 - 风险预算使用恶化 - 连续 anomaly 未收敛

### REDUCED -> DEFENSIVE

可由以下事件触发： - incident 确认 - reconciliation mismatch 影响 live 可信性 - 风险对象可信性下降 - 账户风险状态升至 critical

### DEFENSIVE -> CIRCUIT_BREAKER

可由以下事件触发： - critical incident - emergency stop - 风控穿透 - 真相源完整性失效 - 审计完整性失效且影响核心治理可信性

### 任意状态 -> MANUAL_REVIEW

可由以下事件触发： - operator 明确要求 - 未知新型异常 - 多层结论严重冲突 - 恢复审批前要求人工审查


## 6.2 允许的恢复性迁移

### CAUTIOUS -> NORMAL

前提： - 异常已消退 - 观察窗口内无新增 anomaly 聚集 - 健康 / 对账 /审计链正常 - 不存在待解决 near-miss 前兆

### REDUCED -> CAUTIOUS

前提： - 局部问题已缓解 - 风险预算与健康恢复到可接受范围 - 触发 REDUCED 的原因已不再成立

### DEFENSIVE -> REDUCED

前提： - incident 已围堵 - 不再需要全局或广泛 reduce-only - 真相链与对账链可可信运行 - 恢复计划已获批准

### CIRCUIT_BREAKER -> DEFENSIVE

前提： - critical incident 已被正式认定与围堵 - 风险扩散已停止 - 核心链路最低可运行性恢复 - 恢复批准已形成正式对象

### MANUAL_REVIEW -> CAUTIOUS / REDUCED / DEFENSIVE

前提： - 人工审查已完成 - 结论明确 - 恢复或继续保守的路径已明确


## 7. 禁止的迁移

以下迁移应明确定义为 **禁止**：

### 7.1 直接跨级恢复
- CIRCUIT_BREAKER -> NORMAL
- DEFENSIVE -> NORMAL
- REDUCED -> NORMAL

原因： - 不符合渐进恢复原则 - 不符合事故后观察窗口要求

### 7.2 无事件无审计迁移

任何状态不得在没有： - 正式触发事件 - 正式决策对象 - 正式审计记录

的情况下静默切换。

### 7.3 前端本地状态直接改变风险模式

禁止 GUI / 前端本地状态直接将风险模式从 REDUCED 改成 NORMAL。

### 7.4 Learning Plane 直接改变风险模式

Learning Plane 可以建议进入更保守状态或提出恢复建议，但不得直接切换 live 风险模式。

### 7.5 Execution / OMS 直接放宽风险模式

Execution / OMS 不得因为“执行看起来没问题”而主动把模式从 CAUTIOUS 拉回 NORMAL。


## 8. 自动触发 vs 人工批准

## 8.1 自动触发原则

以下方向的迁移通常允许自动触发： - 向更保守状态迁移 - 向 MANUAL_REVIEW 迁移 - 从 NORMAL 到 CAUTIOUS - 在明确触发条件下的 CAUTIOUS -> REDUCED

## 8.2 必须人工批准的迁移

以下迁移通常必须人工批准： - DEFENSIVE -> REDUCED - CIRCUIT_BREAKER -> DEFENSIVE - 任何恢复到更宽松级别的跨阶段恢复 - 观察窗口未完成时的恢复 - 涉及 incident / critical incident 后的恢复

### 8.3 可采用模板化审批的恢复

某些低严重度情况下，可以采用模板化审批： - CAUTIOUS -> NORMAL - REDUCED -> CAUTIOUS

前提是： - 无 incident - 无真相源完整性问题 - 无审计缺口


## 9. 状态进入后的行为约束

## 9.1 NORMAL
- 正常裁决
- 正常新风险审批
- 正常授权范围内运行

## 9.2 CAUTIOUS
- 提高入场门槛
- 下调批准仓位
- 提高 manual review 概率
- 更频繁拒绝边缘机会

## 9.3 REDUCED
- 仅允许最高质量机会
- 局部冻结部分 symbol / 策略簇
- 大比例 downsize
- 限制订单类型与行为类型

## 9.4 DEFENSIVE
- 禁止新增风险
- 只允许 reduce-only / protective action
- 等待人工审查或事故围堵

## 9.5 CIRCUIT_BREAKER
- 停止所有非保护性推进
- 冻结 live 扩张
- 禁止恢复前自动推进
- 禁止变更扩张

## 9.6 MANUAL_REVIEW
- 对指定范围内的关键动作改为人工审批
- 非指定范围可按当前基础模式继续运行（若上位策略允许）


## 10. 风险状态决策对象模板

建议每次状态迁移都生成正式对象：

risk_mode_transition:
  transition_id: string
  previous_mode: NORMAL\|CAUTIOUS\|REDUCED\|DEFENSIVE\|CIRCUIT_BREAKER\|MANUAL_REVIEW
  next_mode: NORMAL\|CAUTIOUS\|REDUCED\|DEFENSIVE\|CIRCUIT_BREAKER\|MANUAL_REVIEW
  trigger_event_type: health_event\|risk_event\|incident_event\|operator_governance_event\|recovery_event\|reconciliation_event\|execution_safety_event
  trigger_event_id: string
  transition_reason_codes: []
  initiated_by: RiskGovernor\|Operator\|RecoveryApprovalFlow
  approval_required: true\|false
  approved_by: string\|null
  effective_at: datetime
  observation_window_required: true\|false
  audit_event_ref: string


## 11. 观察窗口制度

### 11.1 观察窗口的必要性

任何向更宽松方向的恢复，都应考虑观察窗口。

### 11.2 观察窗口要求

在观察窗口中： - 禁止进一步放宽超过当前批准级别 - 提高审计密度 - 提高 incident / near-miss 检查频率 - 相关变更扩张继续冻结

### 11.3 观察窗口结束条件

至少应满足： - 无新增同类异常 - 触发恢复的根因已不再出现 - 审计链、对账链、健康链稳定 - Operator 未提出回退


## 12. 与 Audit / Incident Policy 的关系

Risk Governor 状态机依赖 Incident Policy，但不等于 Incident Policy。

### 12.1 Incident Policy 负责
- 定义 anomaly / near_miss / incident / critical_incident
- 定义事故处置流程
- 定义熔断、恢复、复盘制度

### 12.2 本状态机负责
- 把这些事故与异常的治理意图正式落到 Risk Governor 的状态迁移系统中

换句话说： - Incident Policy 回答“出什么事算什么等级” - 本文件回答“出了这类事后 Risk Governor 应切到哪个模式，以及怎么恢复”


## 13. 与 Authorization Policy 的关系

### 13.1 放权前提

任何授权扩张都不得在以下状态中进行： - DEFENSIVE - CIRCUIT_BREAKER - MANUAL_REVIEW（若针对相关范围）

### 13.2 恢复与放权先后

原则上： - 先完成恢复与观察 - 再考虑重新进入授权扩张流程

不得把“风险模式恢复”与“授权扩张”混为一步完成。


## 14. 漂移防护声明

以下倾向应视为状态机漂移风险： - 风险模式成为 GUI 任意切换的字符串 - 恢复过程跳过观察窗口 - 保守化迁移没有正式事件和审计 - 重大事故后直接恢复到 NORMAL - Learning 建议直接影响风险模式 - Execution 或策略层自行放宽风险模式

一旦出现上述情况，应优先修正状态机治理，而不是接受“先这样方便”。


## 15. 一句话总纲

**Risk Governor ****状态机的职责，是把系统的风险治理模式正式化为一套可审计、可触发、可回滚、可渐进恢复的状态系统，使系统在异常时能够自动向更保守方向收缩，在恢复时必须按正式条件与观察窗口渐进放开，而不能依靠隐性热改或主观乐观直接恢复。**
