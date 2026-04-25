# OpenClaw / Bybit 交易 Agent

# Authorization State Machine Specification V1

## 0. 文档定位

本文件用于定义 **Authorization** 的正式状态机规范。

本文件回答以下问题： - 授权对象具有哪些正式状态 - 各状态的正式语义是什么 - 哪些事件可以触发授权状态迁移 - 哪些主体可以触发这些迁移 - 哪些迁移允许自动发生，哪些必须人工批准 - 哪些迁移是明令禁止的 - 授权对象在不同状态下允许什么、不允许什么 - 授权如何创建、激活、冻结、收缩、撤销、过期与恢复

本文件是以下文件的下沉落地规范： - 《项目宪法 / 根原则》 - 《字段级与状态级规范》 - 《Truth Source & Ownership Matrix》 - 《Promotion / Change Control / Authorization Policy》 - 《Audit / Incident / Circuit Breaker Policy》 - 《Risk Governor 正式边界定义》 - 《Control Plane / Operator Console 正式边界定义》

本文件 **不负责**： - 授权范围的具体业务内容枚举细节 - GUI 页面实现 - API 路由细节 - 数据库建表细节 - 具体审批角色配置

如与上位文件冲突，以《项目宪法 / 根原则》为最高约束。


## 1. 设计目标

Authorization 状态机的目标，是把“系统被允许做什么”从松散配置或口头理解，收敛为一套正式、可审计、可版本化、可收缩、可撤销、不可偷偷扩张的治理状态系统。

它必须保证： - 授权不是前端页面上的一组临时勾选值 - 授权不是策略层可以自行放宽的隐性配置 - 授权扩张必须经过正式治理与审批 - 授权收缩与撤销必须可快速触发并可审计 - 授权对象不会在无效状态下继续被系统误用

一句话：

**Authorization ****状态机，是把“Agent**** ****在什么边界内可以做什么”正式化为一套可授予、可收缩、可冻结、可撤销、可过期、可恢复的治理生命周期系统。**


## 2. Authorization 对象的正式地位

Authorization 对象的本质是：

**对**** Agent ****在特定范围、特定阶段、特定模式下可执行行为边界的正式治理许可对象。**

它不是： - H0 / H1-H5 的市场判断 - Risk Governor 的风险裁决结果 - Control Plane 的前端配置快照 - Learning Plane 的建议

它可以： - 被起草 - 被审批 - 被激活 - 被收缩 - 被冻结 - 被撤销 - 被过期 - 被恢复或重新授予

它不可以： - 在无审批情况下自动扩张 - 被 GUI 直接伪造为已生效 - 被学习建议直接改宽


## 3. 正式状态集合

Authorization 正式状态集合如下：
- DRAFT
- PENDING_APPROVAL
- ACTIVE
- RESTRICTED
- FROZEN
- REVOKED
- EXPIRED
- REJECTED

这些状态与 authorization_state 的总体语义保持一致，但本文件进一步定义其状态机规则。


## 4. 状态语义

## 4.1 DRAFT

### 含义
- 授权草案已形成，但尚未进入正式审批流程

### 允许行为
- 被审查
- 被补充作用域与元信息
- 进入审批流程
- 被拒绝或废弃

### 不允许行为
- 不得被系统视为已生效授权
- 不得被 Risk / OMS / I 作为 live 有效授权使用


## 4.2 PENDING_APPROVAL

### 含义
- 授权对象已进入正式审批流程，但尚未生效

### 允许行为
- 等待审批
- 被拒绝
- 被退回修改
- 被取消申请

### 不允许行为
- 不得作为 ACTIVE 授权使用
- 不得在审批未完成时提前放开系统边界


## 4.3 ACTIVE

### 含义
- 授权正式生效
- Agent 在该授权对象定义的边界内可以被允许行动

### 允许行为
- 被 Risk Governor 读取与约束
- 被用于 Lease / Execution / Mode 的合法性检查
- 在条件满足时被收缩、冻结、撤销、过期

### 不允许行为
- 不得无版本、无审计地被静默扩张


## 4.4 RESTRICTED

### 含义
- 授权仍存在，但较 ACTIVE 明显收缩
- 通常表示部分 symbol、策略簇、订单类型、风险额度或运行阶段被缩小

### 允许行为
- 在收缩后的边界内继续使用
- 被进一步冻结或撤销
- 在条件满足时恢复到 ACTIVE

### 不允许行为
- 不得被当作和 ACTIVE 一样宽的授权使用

### 典型场景
- near-miss 后局部撤权
- 恢复观察期内临时收缩授权
- 风险模式降低后的同步授权收紧


## 4.5 FROZEN

### 含义
- 授权对象被临时冻结
- 在冻结期间，该授权不得继续作为可用授权被系统使用

### 允许行为
- 保持冻结
- 被撤销
- 被过期
- 在正式恢复条件下解除冻结

### 不允许行为
- 不得被 H0 / Risk / OMS 继续视作可用授权

### 典型场景
- incident freeze
- emergency stop
- 事故调查期间冻结
- 恢复前观察窗口冻结


## 4.6 REVOKED

### 含义
- 授权被正式撤销
- 不得继续使用

### 允许行为
- 归档
- 审计与复盘
- 必要时基于新流程重新申请新授权对象

### 不允许行为
- 不得重新恢复活跃
- 不得被当作临时暂停

### 重要语义

撤销是终态，不是临时冻结。


## 4.7 EXPIRED

### 含义
- 授权到期失效
- 不得继续使用

### 允许行为
- 归档
- 审计与复盘
- 必要时重新发起新的授权申请

### 不允许行为
- 不得被自动延长或自动恢复为 ACTIVE

### 重要语义

过期是时间或条件触发的自然终止，不等于人工撤销。


## 4.8 REJECTED

### 含义
- 授权草案或申请未获批准，正式不生效

### 允许行为
- 归档
- 复盘
- 重新起草新草案

### 不允许行为
- 不得把被拒绝对象重新标成 ACTIVE
- 不得绕过审批链继续使用


## 5. 正式触发事件

Authorization 状态迁移只能由正式事件触发。

### 5.1 事件类别
- draft_event
- approval_event
- activation_event
- restriction_event
- freeze_event
- revocation_event
- expiry_event
- recovery_event
- incident_event

### 5.2 典型事件示例
- authorization_draft_created
- authorization_submitted_for_approval
- authorization_approved
- authorization_rejected
- authorization_activated
- authorization_restricted
- authorization_freeze_applied
- authorization_revoked
- authorization_expired
- authorization_recovery_approved
- incident_requires_freeze
- observation_window_restriction_applied

这些事件必须进入正式审计链。


## 6. 状态迁移总图（逻辑）

建议逻辑迁移关系如下：
- DRAFT → PENDING_APPROVAL
- DRAFT → REJECTED
- PENDING_APPROVAL → ACTIVE
- PENDING_APPROVAL → REJECTED
- ACTIVE → RESTRICTED
- ACTIVE → FROZEN
- ACTIVE → REVOKED
- ACTIVE → EXPIRED
- RESTRICTED → ACTIVE
- RESTRICTED → FROZEN
- RESTRICTED → REVOKED
- RESTRICTED → EXPIRED
- FROZEN → RESTRICTED
- FROZEN → ACTIVE（条件性）
- FROZEN → REVOKED
- FROZEN → EXPIRED

### 6.1 核心原则
- 授权扩张必须经过正式审批路径
- 授权收缩与冻结可以更快触发
- 终态对象不得回流到活跃状态
- 授权恢复通常应先回到 RESTRICTED，而不是直接完全恢复


## 7. 允许的迁移

## 7.1 草案与审批阶段

### DRAFT -> PENDING_APPROVAL

前提： - 授权草案结构完整 - 作用域清晰 - 生效范围、期限、审批要求已明确

### DRAFT -> REJECTED

前提： - 草案不符合格式或原则要求 - 草案被明确废弃

### PENDING_APPROVAL -> ACTIVE

前提： - 已完成正式审批 - 生效时间满足 - 审计记录完成

### PENDING_APPROVAL -> REJECTED

前提： - 审批未通过 - 审批路径明确拒绝


## 7.2 生效后的治理迁移

### ACTIVE -> RESTRICTED

前提： - 局部撤权 - 观察期保护性收缩 - incident / near-miss 后收缩边界 - 风险模式下降要求同步授权收缩

### ACTIVE -> FROZEN

前提： - incident freeze - emergency stop - 统一暂停某范围授权使用

### ACTIVE -> REVOKED

前提： - operator 正式撤权 - 授权对象失去合法性或必要性 - 事故后决定永久撤销

### ACTIVE -> EXPIRED

前提： - 到达 expires_at - 上位条件要求该授权自然失效


## 7.3 收缩与冻结后的恢复/终止

### RESTRICTED -> ACTIVE

前提： - 限制原因已解除 - 恢复获批 - 观察期完成 - 无 incident / near-miss 未解问题

### RESTRICTED -> FROZEN

前提： - 问题进一步恶化 - incident freeze - emergency stop

### RESTRICTED -> REVOKED

前提： - 局部问题升级为永久撤权 - 授权对象不再可信或不再需要

### RESTRICTED -> EXPIRED

前提： - 授权自然到期

### FROZEN -> RESTRICTED

前提： - 冻结已解除 - 但恢复需保守进行

### FROZEN -> ACTIVE

前提： - 冻结原因已完全解除 - 恢复获得正式批准 - 观察要求允许直接完全恢复

### FROZEN -> REVOKED

前提： - 冻结后确认应永久撤销

### FROZEN -> EXPIRED

前提： - 冻结期间自然过期


## 8. 禁止的迁移

以下迁移应明确禁止：

### 8.1 终态回流
- REVOKED -> ACTIVE
- REVOKED -> RESTRICTED
- EXPIRED -> ACTIVE
- EXPIRED -> RESTRICTED
- REJECTED -> ACTIVE
- REJECTED -> PENDING_APPROVAL

### 8.2 跳过审批直接生效
- DRAFT -> ACTIVE

除非未来上位文档定义某些极低风险预授权模板，否则禁止。

### 8.3 无审计静默扩权

任何授权不得在没有： - 正式审批对象 - 正式触发事件 - 正式审计记录

的情况下，从更窄状态变成更宽状态。

### 8.4 GUI / Learning 直接改授权状态

GUI、Learning Plane、报表层不得直接将授权对象从一个正式状态改到另一个正式状态。

### 8.5 事故期间无条件恢复为 ACTIVE

在 incident / critical incident 相关范围内，不允许跳过恢复条件与观察期直接恢复为 ACTIVE。


## 9. 自动迁移 vs 人工批准

## 9.1 通常允许自动发生的迁移

以下迁移通常允许由治理链自动发生： - DRAFT -> PENDING_APPROVAL - ACTIVE -> RESTRICTED - ACTIVE -> FROZEN - RESTRICTED -> FROZEN - ACTIVE -> EXPIRED - RESTRICTED -> EXPIRED - FROZEN -> EXPIRED

### 说明

这些自动迁移必须仍然： - 有正式事件 - 有正式对象更新 - 有审计留痕

## 9.2 通常必须人工批准的迁移

以下迁移通常必须人工批准： - PENDING_APPROVAL -> ACTIVE - RESTRICTED -> ACTIVE - FROZEN -> RESTRICTED - FROZEN -> ACTIVE - ACTIVE -> REVOKED（通常由正式治理/审批动作触发） - RESTRICTED -> REVOKED

### 特别说明

保守方向的冻结和收缩可由 incident / risk / authorization governance 自动触发； 宽松方向的恢复原则上必须经过审批或正式恢复流程。


## 10. 状态进入后的行为约束

## 10.1 DRAFT
- 不得被系统当作 live 授权使用
- 仅允许编辑与审查

## 10.2 PENDING_APPROVAL
- 等待正式审批
- 不得提前放权

## 10.3 ACTIVE
- 可作为正式授权边界对象被读取
- 允许 H0 / Risk / OMS 使用其边界进行合法性检查

## 10.4 RESTRICTED
- 仅能在收缩后的边界内使用
- 不得按 ACTIVE 宽度解释

## 10.5 FROZEN
- 不得作为有效授权使用
- 仅等待恢复、撤销或过期

## 10.6 REVOKED / EXPIRED / REJECTED
- 均不得作为有效授权使用
- 仅允许归档、审计、复盘


## 11. 授权恢复原则

### 11.1 恢复不是默认动作

授权一旦被冻结或收缩，不应因为“系统看起来已经好了”而自动恢复。

### 11.2 恢复前提

恢复至少应满足： - 触发冻结/收缩的原因已解除 - 风险模式允许恢复 - 相关 incident/near_miss 已完成最小处理 - 审计链与真相源完整性正常 - 恢复已获正式批准（若上位规则要求）

### 11.3 保守恢复优先

原则上： - FROZEN -> RESTRICTED 优先于 FROZEN -> ACTIVE - RESTRICTED -> ACTIVE 应晚于观察期结束


## 12. 与 Risk Governor 的关系

### 12.1 授权不等于风险批准

Authorization 规定的是： > 系统“原则上可在哪个边界内行动”。

Risk Governor 规定的是： > 在当前真实风险、健康、事故与模式条件下，这次具体动作“现在能不能行动”。

因此： - ACTIVE 授权不等于当前行为必然通过 Risk Governor - 授权恢复不等于风险模式恢复

### 12.2 正式边界

Authorization State Machine 负责： - 授权对象本身的生命周期

Risk Governor State Machine 负责： - 风险模式的生命周期

两者应联动，但不可互相替代。


## 13. 与 Control Plane / Operator Console 的关系

### 13.1 Control Plane 的职责
- 展示授权对象
- 发起审批、冻结、撤权、恢复请求

### 13.2 Authorization Governance 的职责
- 接纳并处理这些治理动作
- 更新正式授权对象状态

### 13.3 正式边界

Control Plane 不得： - 直接把页面上的某个选项写成 ACTIVE 授权 - 跳过审批链 - 以前端本地状态伪装成正式授权状态


## 14. 与 Promotion / Change Control 的关系

### 14.1 放权需要进入正式变更链

授权扩张本身是一类高风险变更。

因此： - PENDING_APPROVAL -> ACTIVE 通常应绑定 Change Control 审批 - 授权范围改变应具备版本、理由、观察期与回滚路径

### 14.2 撤权和收缩的特殊性

收缩与冻结属于保守化治理动作，可以更快发生，但仍须正式记录。


## 15. 与 Incident / Recovery 的关系

### 15.1 Incident 场景下的授权处理

若发生 incident / critical incident，应允许或要求： - ACTIVE -> RESTRICTED - ACTIVE -> FROZEN - RESTRICTED -> FROZEN - 在严重情况下进入 REVOKED

### 15.2 Recovery 场景下的授权恢复

恢复时： - 优先恢复到 RESTRICTED - 观察期后再评估是否恢复到 ACTIVE

不得把 incident 后的恢复直接等同于授权完全恢复。


## 16. 授权状态迁移对象模板

建议每次授权状态迁移都形成正式对象：

authorization_transition:
  transition_id: string
  authorization_id: string
  previous_status: DRAFT\|PENDING_APPROVAL\|ACTIVE\|RESTRICTED\|FROZEN\|REVOKED\|EXPIRED\|REJECTED
  next_status: DRAFT\|PENDING_APPROVAL\|ACTIVE\|RESTRICTED\|FROZEN\|REVOKED\|EXPIRED\|REJECTED
  trigger_event_type: draft_event\|approval_event\|activation_event\|restriction_event\|freeze_event\|revocation_event\|expiry_event\|recovery_event\|incident_event
  trigger_event_id: string
  initiated_by: AuthorizationGovernance\|Operator\|IncidentPolicy\|RecoveryApprovalFlow
  transition_reason_codes: []
  approval_required: true\|false
  approved_by: string\|null
  effective_at: datetime
  audit_event_ref: string


## 17. 漂移防护声明

以下倾向应视为 Authorization 状态机漂移风险： - 授权被看成前端配置而非正式治理对象 - 授权扩张在无审批下静默发生 - incident 后授权直接恢复为 ACTIVE - 被撤销或过期的授权继续被系统读取为有效 - Learning Plane 直接推动 live 授权扩张 - Risk Governor 和 Authorization 对象被混成同一个东西

一旦出现上述情况，应优先修正授权治理状态机，而不是接受“先这么方便”。


## 18. 一句话总纲

**Authorization ****状态机的职责，是把**** Agent ****的可行动边界正式化为一套可起草、可审批、可激活、可收缩、可冻结、可撤销、可过期、可恢复的治理生命周期系统，使授权永远不是临时配置、不是前端勾选、不是学习建议，而是一个必须被正式授予、正式收缩、正式审计的治理对象。**
