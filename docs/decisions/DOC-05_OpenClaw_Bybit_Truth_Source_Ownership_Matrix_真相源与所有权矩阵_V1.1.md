# OpenClaw / Bybit 交易 Agent

# Truth Source & Ownership Matrix V1.1

## 0. 文档定位

本文件用于定义 OpenClaw / Bybit 交易 Agent 中各核心对象的： - 唯一真相源（Source of Truth） - 主写入方（Primary Writer） - 允许读取方（Readers） - 建议权来源（Advisory Writers） - 人工覆盖路径（Human Override Path） - 禁止写入方（Forbidden Writers） - 冲突处理原则（Conflict Resolution）

本文件是《项目宪法 / 根原则》《H0-H1~H5-I 正式边界定义》《字段级与状态级规范》的治理落地文件。

本文件 **不负责**： - API 路由细节 - 数据库表设计 - GUI 排版 - 策略参数数值 - 风控阈值数值

如与上位文档冲突，以《项目宪法 / 根原则》为最高约束。


## 1. 核心目标

本文件的核心目标只有一个：

**防止系统中出现多个模块各自维护“自己的真相版本”，并通过明确所有权矩阵，确保关键对象的写权、读权、建议权与人工覆盖路径始终可审计、可验证、可回滚。**


## 2. 基本术语定义

### 2.1 Source of Truth（真相源）

指某类核心对象在系统中的正式事实来源。

要求： - 同一关键对象只能有一个正式真相源 - 下游可以缓存、投影、衍生、展示，但不得自称为正式真相源 - 若存在外部事实源（如交易所），则本系统中的真相源通常应定义为“交易所事实同步链 + 对账确认后的正式对象”，而不是任意模块本地缓存

### 2.2 Primary Writer（主写入方）

指唯一有权对该对象正式状态进行写入或状态迁移的模块/链路。

### 2.3 Reader（读取方）

指允许读取该对象用于判断、展示、审计、学习或报表的模块。

### 2.4 Advisory Writer（建议权来源）

指可以提出修改建议、候选值或草案，但 **不能直接成为正式写入** 的模块。

### 2.5 Human Override Path（人工覆盖路径）

指人类 Operator 可以依法对该对象施加控制的正式路径。

注意： - 人工覆盖不等于任意修改底层事实 - 人工覆盖应通过受控治理对象实现，并留下审计事件

### 2.6 Forbidden Writer（禁止写入方）

指在任何情况下都不得直接写入该对象正式状态的模块。


## 3. 总体原则

### 3.1 单对象单真相源原则

关键对象只能有一个正式真相源。

允许： - 缓存副本 - 只读镜像 - 报表投影 - GUI 展示层映射 - 学习平面分析副本

不允许： - GUI 自己发明正式状态 - 学习平面直接改写 live 正式对象 - H0 / H / I / GUI / 报表各自维护一份“自己的最终状态”

### 3.2 主写入方唯一原则

每类核心对象必须明确唯一主写入方。

即使存在多条数据输入，也必须通过单一治理链路收敛为正式写入。

### 3.3 建议权与写权分离原则

可以提出建议的模块，不等于可以落地生效的模块。

特别强调： - H1-H5 对 Lease 有起草权，不等于对 Lease 生命周期有正式写权 - Learning Plane 对规则与参数有建议权，不等于有 live 写权 - GUI 对控制动作有触发权，不等于可以直写交易对象

### 3.4 人工覆盖必须受控原则

人工是最终治理者，但人工动作必须通过： - 正式控制平面 - 明确审批路径 - 审计事件 - 可回滚机制

实现。

### 3.5 禁止展示层反向污染原则

GUI、报表、摘要层不得将： - 展示标签 - 本地推导结果 - 临时前端状态

反向写回正式状态对象。


## 4. 所有权矩阵总表（高层）

| 对象 | 真相源 | 主写入方 | 建议权来源 | 人工覆盖路径 | 禁止写入方 |
|---|---|---|---|---|---|
| system_state | 控制平面正式状态对象 | Control Plane / Governance Core | 风险链、Operator 建议 | Operator 通过 Control API | GUI 前端、Learning、H0、H1-H5、I |
| health_state | 健康监控链正式对象 | Health / Monitoring Pipeline | 风险链可建议降级 | Operator 可触发保护模式，不直接伪造健康值 | GUI、Learning、H0、H1-H5 |
| market_state | 市场状态引擎正式对象 | Market State Engine | H1 可引用解释，不可改写 | 无直接人工改写；仅能调整状态引擎规则版本 | GUI、Learning、H0、H1-H5、I |
| account_state | 账户同步与对账链 | Account Sync + Reconciliation | 报表/学习可做衍生 | 人工不可伪造账户事实，只能触发校准/重同步 | GUI、Learning、H0、H1-H5、I |
| risk_state | 风险治理链正式对象 | Risk Governor | H4、Learning 可建议 | Operator 可通过治理动作触发更高保护模式 | GUI、H0、H1-H5、I、报表 |
| authorization_state | 授权治理链正式对象 | Authorization Governance + Approval Path | Learning、H4、Operator 建议 | Operator 审批/撤权 | GUI 前端、H0、H1-H5、I |
| candidate_context | 候选构建链 | Candidate Builder / Orchestrator | H0 可补充决定引用 | Operator 仅可关闭/标记，不应伪造来源 | GUI、Learning、报表 |
| h0_decision | H0 正式决定对象 | H0 Core | 无外部建议覆盖写入 | Operator 仅可追加 override 事件，不改原决定 | GUI、H1-H5、I、Learning |
| deliberation_state | H1-H5 审议正式对象 | H1-H5 Deliberation Pipeline | 无外部直接改写 | Operator 可要求重审，不改写原审议结果 | GUI、Learning、I |
| decision_lease | I 控制平面正式对象 | I Lease Control Plane | H5 提供草案；Risk/Operator 可影响状态流转 | Operator 可冻结/撤销/批准路径 | GUI 前端、Learning、H0、H1-H5 直接写正式状态 |
| execution_state | 执行治理链正式对象 | Execution Coordinator / OMS | Risk 可阻断；Lease 可桥接 | Operator 可触发 cancel/reduce_only/stop | GUI、Learning、H0、H1-H5、I 直接写执行状态 |
| order_state | 订单事实同步与对账链 | Order Sync + Reconciliation | Execution 提交请求但不写最终事实 | Operator 可触发正式取消路径 | GUI、Learning、H0、H1-H5、I |
| fill_state | 成交事实同步链 | Fill Sync + Reconciliation | 无 | 人工不可伪造成交事实 | GUI、Learning、H0、H1-H5、I、Execution |
| position_state | 持仓事实同步与对账链 | Position Sync + Reconciliation | Risk/Execution 可引用 | Operator 可触发 reduce/close，不直接写持仓事实 | GUI、Learning、H0、H1-H5、I |
| audit_event | 审计链正式对象 | Audit Pipeline | 各模块提供事件源 | Operator 动作也必须进入审计链 | GUI、报表直接写审计结果 |
| learning_record | 学习平面正式对象 | Learning Plane | Audit/Report 提供输入 | Operator 可审批建议，不改原学习记录 | GUI、H0、H1-H5、I、Execution |


## 5. 对象级详细所有权规范

## 5.1 system_state

### 真相源

system_state 的真相源是 **控制平面正式状态对象**，而不是 GUI 当前画面显示值，也不是某模块的本地运行标志。

### 主写入方
- Control Plane
- Governance Core

### 允许读取方
- H0
- H1-H5
- I
- Risk Governor
- Execution
- GUI
- Audit
- Learning

### 建议权来源
- Risk Governor 可建议切换到更保守模式
- Operator 可提出或发起模式切换
- Incident policy 可触发模式变化建议

### 人工覆盖路径
- 通过 Control API / Operator Console
- 必须生成 audit_event
- 必须带有 reason_code / approved_by

### 禁止写入方
- GUI 前端组件
- H0
- H1-H5
- I
- Learning Plane
- 报表层

### 备注

system_state 是控制约束对象，不应被任何低层模块隐式热修改。


## 5.2 health_state

### 真相源

health_state 的真相源是 **健康监控链正式对象**，由健康监测、数据质量监测、对账监测等统一收敛。

### 主写入方
- Health / Monitoring Pipeline

### 建议权来源
- Risk Governor 可基于健康状态建议保护动作
- Operator 可触发人工保护模式，但不是直接篡改 health_state

### 人工覆盖路径
- 人工不能把不健康改成健康
- 只能通过治理动作触发：
  - manual_safe
  - review_required
  - emergency_stop

### 禁止写入方
- GUI
- Learning
- H0
- H1-H5
- I

### 备注

健康值是诊断结果，不应被业务逻辑层假写。


## 5.3 market_state

### 真相源

market_state 的真相源是 **市场状态引擎正式对象**，由原始行情流、状态识别引擎、标准化逻辑统一生成。

### 主写入方
- Market State Engine

### 建议权来源
- H1 可对市场做解释，但不得反向写回 market_state
- Learning 可建议改进状态识别规则，但不得直接改写 live 状态

### 人工覆盖路径
- 人工不能手工写一个“当前是 trend_up”成为真相
- 只能通过变更流程修改状态识别规则版本

### 禁止写入方
- H0
- H1-H5
- I
- GUI
- Learning live path

### 备注

market_state 是“标准化世界状态”，不是任何一段 AI 叙述文本。


## 5.4 account_state

### 真相源

account_state 的真相源是 **账户同步与对账链**，而不是任何报表缓存或 GUI 估算值。

### 主写入方
- Account Sync Pipeline
- Reconciliation Pipeline

### 建议权来源
- Reporting 可生成衍生统计
- Learning 可引用与归因

### 人工覆盖路径
- 不允许人工伪造账户权益、余额、PnL 事实
- 仅允许人工触发：
  - 重新同步
  - 校准
  - 事故标记

### 禁止写入方
- GUI
- Learning
- H0
- H1-H5
- I


## 5.5 risk_state

### 真相源

risk_state 的真相源是 **Risk Governor ****正式对象**。

### 主写入方
- Risk Governor

### 建议权来源
- H4 可提出风险一致性审查意见
- Learning 可提出风险守卫建议
- Operator 可要求保守化

### 人工覆盖路径
- Operator 可以把系统切到更保守状态
- Operator 不应绕过审计直接伪造风险预算已使用值

### 禁止写入方
- GUI 前端
- H0
- H1-H5
- I
- Reporting

### 备注

风险状态是治理真相，不能由策略层自我声明。


## 5.6 authorization_state

### 真相源

authorization_state 的真相源是 **授权治理链**** + ****审批路径**。

### 主写入方
- Authorization Governance
- Approval Workflow

### 建议权来源
- H4 可提出授权不匹配意见
- Learning 可提出放权/撤权建议
- Operator 可发起授权调整

### 人工覆盖路径
- 必须通过正式审批动作
- 必须记录：
  - 生效范围
  - 失效时间
  - 批准人
  - 原因

### 禁止写入方
- GUI 直写
- H0
- H1-H5
- I
- Execution

### 备注

授权是治理结论，不是策略的自由意志。


## 5.7 candidate_context

### 真相源

candidate_context 的真相源是 **候选构建链**** / ****候选编排器**。

### 主写入方
- Candidate Builder
- Orchestrator

### 建议权来源
- H0 可引用并附加决定对象，但不改写候选来源事实
- Learning 可用作历史分析输入

### 人工覆盖路径
- 可人工关闭候选
- 可人工标记异常候选
- 不应人工伪造其触发来源

### 禁止写入方
- GUI 直接创建伪候选成为正式对象
- H1-H5 反向改候选来源
- I 改候选起因


## 5.8 h0_decision

### 真相源

h0_decision 的真相源是 **H0 Core ****正式决定对象**。

### 主写入方
- H0 Core

### 建议权来源
- 无外部建议直接覆盖 H0 决定
- 上游只能影响输入，不影响已形成决定的真相

### 人工覆盖路径
- 可追加 operator_override 审计事件
- 不直接改写历史 h0_result
- 若需重跑，应生成新决定对象，不覆盖旧对象

### 禁止写入方
- H1-H5
- I
- GUI
- Learning

### 备注

历史 H0 决定应不可被重写，只能新增后续解释或重跑版本。


## 5.9 deliberation_state

### 真相源

deliberation_state 的真相源是 **H1-H5 ****审议流水线正式对象**。

### 主写入方
- H1-H5 Deliberation Pipeline

### 建议权来源
- 无其他模块直接写入审议正式结果
- 外部模块只能要求“重新审议”

### 人工覆盖路径
- 可要求重审
- 可将结果标记为“人工复核必需”
- 不应直接把审议结果改成另一个结果

### 禁止写入方
- I
- GUI
- Learning
- Execution

### 备注

审议是过程性真相，不应被下游治理链反向篡改。


## 5.10 decision_lease

### 真相源

decision_lease 的真相源是 **I Lease Control Plane ****正式对象**。

### 主写入方
- I Lease Control Plane

### 建议权来源
- H5 提供 LEASE_DRAFT
- Risk Governor 可影响是否允许继续流转
- Operator 可冻结/撤销/审批

### 人工覆盖路径
- 可冻结
- 可撤销
- 可进入人工审批路径
- 不能将 Lease 伪装成订单对象

### 禁止写入方
- H0
- H1-H5 直接写正式 Lease 状态
- GUI 直改 Lease 状态
- Learning

### 备注

Lease 是控制对象，不是策略层的自由文本结论。


## 5.11 execution_state

### 真相源

execution_state 的真相源是 **Execution Coordinator / OMS ****正式对象**。

### 主写入方
- Execution Coordinator
- OMS

### 建议权来源
- Lease 提供桥接依据
- Risk Governor 可阻断 / 限制
- Operator 可触发 cancel / reduce_only 路径

### 人工覆盖路径
- 通过正式执行控制动作
- 不直接伪造执行成功/失败状态

### 禁止写入方
- H0
- H1-H5
- I
- GUI 前端
- Learning


## 5.12 order_state

### 真相源

order_state 的真相源是 **订单事实同步链**** + ****对账确认链**。

### 主写入方
- Order Sync
- Reconciliation

### 建议权来源
- Execution 可以提交订单请求
- 但提交请求 ≠ 订单正式事实写入

### 人工覆盖路径
- 可触发正式 cancel / replace 路径
- 不可伪造订单已成交/已取消事实

### 禁止写入方
- GUI
- Learning
- H0
- H1-H5
- I

### 备注

交易所返回与对账链确认后的对象，才是正式订单状态。


## 5.13 fill_state

### 真相源

fill_state 的真相源是 **成交事实同步链**。

### 主写入方
- Fill Sync
- Reconciliation

### 建议权来源
- 无

### 人工覆盖路径
- 无直接覆盖
- 仅可标记异常或请求重同步

### 禁止写入方
- 所有非成交同步链路模块

### 备注

成交事实不可人工伪造。


## 5.14 position_state

### 真相源

position_state 的真相源是 **持仓同步与对账链**。

### 主写入方
- Position Sync
- Reconciliation

### 建议权来源
- Risk 可建议 reduce_only
- Execution 可触发影响持仓的行为
- 但都不能直接写正式持仓事实

### 人工覆盖路径
- 可触发减仓/平仓动作
- 不可直接写“当前持仓 = 0”作为事实

### 禁止写入方
- GUI
- Learning
- H0
- H1-H5
- I


## 5.15 audit_event

### 真相源

audit_event 的真相源是 **Audit Pipeline ****正式对象**。

### 主写入方
- Audit Pipeline

### 建议权来源
- 各模块可发出事件源
- 但最终写入由审计链统一收敛

### 人工覆盖路径
- Operator 行为必须进入审计链
- 不能跳过审计链形成“未记录的人工动作”

### 禁止写入方
- GUI 直接伪造审计结果
- 报表反向生成正式审计对象

### 备注

审计事件应不可默默消失或被覆盖。


## 5.16 learning_record

### 真相源

learning_record 的真相源是 **Learning Plane ****正式对象**。

### 主写入方
- Learning Plane

### 建议权来源
- Audit、Reporting、Review 可作为输入来源
- 但学习记录的正式归因由学习链路形成

### 人工覆盖路径
- 可审批“建议是否进入变更流程”
- 不应直接重写历史学习记录的归因事实

### 禁止写入方
- GUI
- H0
- H1-H5
- I
- Execution

### 备注

学习记录是“复盘真相”，不是 live 真相。


### 5.17 risk_decision

语义：Risk Governor 的正式风控裁决结果对象。真相源：Risk Governor。主写入方：Risk Governor。允许读取方：OMS / Execution、Control Plane、Audit、Learning。建议权来源：无（Risk Governor 独立裁决）。人工覆盖：Operator 可通过治理动作影响风控模式，但不伪造裁决结果。禁止写入方：GUI、H0、H1-H5、I、Learning。

### 5.18 reconciliation_result

语义：Reconciliation 的正式一致性校验结果对象。真相源：Reconciliation Pipeline。主写入方：Reconciliation。允许读取方：Risk Governor、OMS、Control Plane、Audit、Learning。建议权来源：无。人工覆盖：可触发重新对账，不可伪造一致性结论。禁止写入方：GUI、H0、H1-H5、I、Execution、Learning。

### 5.19 learning_suggestion

语义：Learning Plane 生成的候选变更建议对象。真相源：Learning Plane。主写入方：Learning Plane。允许读取方：Control Plane（展示与审批）、Audit。建议权来源：Audit / Report 提供输入。人工覆盖：Operator 可审批/拒绝建议进入 Change Control。禁止写入方：GUI、H0、H1-H5、I、Execution。特别说明：learning_suggestion 不等于 live 变更，必须经 Change Control 流程才能影响实盘。

### 5.20 operator_action

语义：操作员通过 Control Plane 发起的正式治理动作对象。真相源：Control Plane。主写入方：Control Plane / Operator Console。允许读取方：所有模块（作为治理输入）、Audit。建议权来源：Risk Governor 可建议保护性动作。人工覆盖：本对象即为人工治理的正式载体。禁止写入方：H0、H1-H5、I、Learning、Execution 直接伪造。

### 5.21 change_request

真相源：Change Control Pipeline。主写入方：Change Control Pipeline。允许读取方：Control Plane（审批展示）、Audit、Learning（作为建议来源）。建议权来源：Operator、Learning、Audit Review、Engineering。人工覆盖：Operator 可审批/拒绝/回滚。禁止写入方：GUI 直接伪造、H0/H1-H5/I 直接生成。备注：change_request 是变更治理的正式载体，完整字段模板见 DOC-06 §9。

### 5.22 incident_record

真相源：Incident Pipeline。主写入方：Incident Pipeline + Operator。允许读取方：Control Plane、Risk Governor、Audit、Learning（复盘用途）。建议权来源：Risk Governor、Reconciliation 可触发事故升级。人工覆盖：Operator 拥有事故认定权、恢复批准权。禁止写入方：GUI 直接伪造、Learning 直接改写、H0/H1-H5/I。备注：事故记录是事故治理的正式载体，完整字段模板见 DOC-07 §8。


## 6. 冲突处理矩阵

## 6.1 冲突类型

系统中可能出现以下冲突： 1. **对象事实冲突**：两个模块对同一关键对象给出不同状态 2. **时序冲突**：旧状态覆盖新状态 3. **展示污染冲突**：GUI/报表状态混入正式状态 4. **学习污染冲突**：学习建议被误当作正式生效对象 5. **本地缓存冲突**：模块缓存与正式真相源不一致

## 6.2 统一处理原则

### 原则 A：正式真相源优先

一旦冲突，正式真相源优先。

### 原则 B：对账确认优先于局部即时感知

对于订单、成交、持仓类对象： - 对账链正式对象优先于临时本地视图

### 原则 C：治理对象优先于展示对象

对于 system_state、risk_state、authorization_state： - 治理链正式对象优先于 GUI 本地状态

### 原则 D：旧版本不得覆盖新版本

任何对象更新必须以版本/时间/序列号防止回退写入。

### 原则 E：冲突必须显式审计

检测到关键对象冲突时，必须生成正式 audit_event。


## 7. 人工覆盖总原则

人工覆盖是治理动作，不是篡改事实。

### 允许的人工治理动作
- 切换系统模式
- 冻结/撤销 Lease
- 触发 reduce_only / emergency_stop
- 批准/撤销授权
- 发起重审、重同步、重跑
- 标记事故与异常

### 不允许的人工动作
- 伪造成交事实
- 伪造持仓事实
- 伪造账户权益
- 伪造健康正常
- 无审计记录的底层热改


## 8. GUI / Control API / Learning 的特别限制

## 8.1 GUI

GUI 可以： - 读取 - 展示 - 触发受控治理动作 - 进行标签映射

GUI 不可以： - 直接成为真相源 - 直接写核心对象正式状态 - 以展示层本地计算替代正式对象

## 8.2 Control API

Control API 可以： - 发起正式治理动作 - 触发模式切换、冻结、审批、回滚路径

Control API 不应： - 绕过真相源链路直接写业务事实对象 - 绕过审计链

## 8.3 Learning Plane

Learning Plane 可以： - 读取大量历史对象 - 输出归因和建议 - 生成候选改进

Learning Plane 不可以： - 直接改写 live 真相对象 - 直接改变授权矩阵 - 直接把建议当作正式生效状态


## 9. 版本与可回滚要求

所有真相源链和所有权矩阵若发生变更，必须记录： - 版本号 - 变更理由 - 影响对象 - 是否需要迁移 - 是否影响 API / GUI / 审计 / 历史回放 - 回滚方案

不得无版本、无审计地变更关键对象所有权。


## 10. 落地使用方式

本文件应作为以下后续工作的直接依据： - API 字段写入权限控制 - GUI 前后端状态管理限制 - Risk Governor 写权限设计 - Lease Control Plane 状态迁移设计 - Execution / OMS 主写入责任划分 - Reconciliation 设计 - 审计事件落盘规范 - 学习平面读写隔离

若某个实现方案无法清楚落入本矩阵，应优先判断： 1. 是否写错层了 2. 是否试图绕过单一真相源原则 3. 是否把建议权误当成写权


## 11. 一句话总纲

**Truth Source & Ownership Matrix ****的目标，是确保系统中每个关键对象都只有一个正式真相源、一个主写入方、清晰的读取边界、受控的人工覆盖路径，并彻底阻断**** ****GUI、学习平面、局部缓存与低层模块对**** live ****真相的反向污染。**
