# OpenClaw / Bybit Control API V1 RC2 审核报告

## 0. 审核结论

这轮 RC2 相比上一版，已经把之前最关键的 6 个合同级缺口补上了：

1. 认证 / 授权进入正式合同
2. OpenClaw ↔ Bybit 的来源与连接失败语义进入正式合同
3. `demo/validate` 的接口级语义闭合
4. `safe-recheck-bundle` 的一致性与 GUI 可见性规则闭合
5. 风险配置态与风险生效态拆开
6. 最近控制动作摘要与最近任意写动作摘要拆开

按“API 合同审查”标准，我这次的结论是：

**我没有再看到 P0 级别的合同阻断问题。**  
它现在可以作为 **V1 freeze candidate / RC2 最终候选** 进入实现规划。

但我不会把它表述成“绝对万无一失”。  
原因很简单：**合同可以收紧到足够严谨，但生产安全最终仍取决于实现、部署、密钥管理、权限网关、日志与回放机制。**

所以更准确的说法是：

**作为 API 契约文档，RC2 已达到可冻结候选水平；作为最终生产系统，仍需实现层逐项兑现。**

---

## 1. 本轮逐项审核结果

## 1.1 认证 / 授权

### 审核点
上一版的核心缺口，是 `operator_id` 只是“声称身份”，不是“认证身份”。

### RC2 变化
RC2 新增了：

- `401` / `403` 状态码合同
- `authenticated_actor_id` / roles / scopes 的服务端导出要求
- `operator_id` 与真实认证主体不一致时必须 `403 + operator_identity_mismatch`
- GUI 不得直接保存高权限 secrets

### 结论
这一项已经从“缺失”提升到“合同闭合”。  
后续实现只要按合同落地，就不会再出现“接口逻辑严谨但入口实际上谁都能冒充”的结构性漏洞。

**判定：P0 已关闭。**

---

## 1.2 OpenClaw / Bybit 连接与来源语义

### 审核点
上一版没有把真实世界最常见的失败写进合同：只读链不可用、REST 私有链断、WS 私有链断、快照不完整、权限未知等。

### RC2 变化
RC2 新增了：

- `source_context`
- 只读链与执行链的角色分离合同
- `readonly_connector_name` / `execution_connector_name`
- `connector_role_separation_ok`
- `rest_private_connection_state`
- `ws_private_connection_state`
- `runtime_connection_state`
- `account_fact_completeness_state`
- `source_snapshot_completeness_state`
- 一整组连接 / 来源类 reason code
- `503` 对应来源不可用

### 结论
这一项已经从“只能表达抽象 gate / stale / timeout”升级成“能表达 OpenClaw 与 Bybit 事实链到底坏在哪里”。

这对 GUI 很关键，因为 GUI 不再只能看到“blocked”，而能知道是：
- 没有挂只读链
- 只读链不通
- 私有 REST 失败
- 私有 WS 没准备好
- 快照只拿到部分事实

**判定：P0 已关闭。**

---

## 1.3 `demo/validate` 语义闭合

### 审核点
上一版最大歧义之一，是 `validate` 到底应该：
- 因 gate 未通过而返回接口级阻断，
还是
- 总是成功写入评估结果，只把 gate 结论写进 `data`

### RC2 变化
RC2 明确定义：

- `validate` 是“评估动作”，不是状态推进动作
- 不改 `demo_state_switch`
- 只要评估成功写回，就必须 `action_result = success`
- gate 失败 / 阻断只进 `data.*_gate_state` 与 `data.*_reason_codes`
- 顶层失败只留给并发 / 连接 / 认证 / 内部错误

### 结论
这一项已经彻底闭合。  
GUI 可以稳定把 `validate` 当成“刷新判断面板”的动作，而不是“半控制、半报错”的暧昧动作。

**判定：P0 已关闭。**

---

## 1.4 `safe-recheck-bundle` 一致性与 GUI 中间态

### 审核点
上一版最大的 GUI 风险，是 bundle 非事务、逐步执行、逐步暴露，前端容易看到混合态。

### RC2 变化
RC2 现在要求：

- bundle 获取单次执行租约
- 固定 `bundle_base_snapshot_id`
- 全部步骤基于同一 pinned base snapshot
- 步骤结果先写工作副本
- bundle 末尾统一单次提交
- `state_revision` 只加一次
- GUI 在 bundle 返回前不应看到中间态
- 若来源 / 连接失败，不得提交部分结果

### 结论
这已经把 GUI 最怕的“中间态污染”挡住了。  
同时也保留了 bundle 逐步骤结果，方便控制中心显示明细。

**判定：P0 已关闭。**

---

## 1.5 风险配置态与生效态

### 审核点
上一版把 `risk_envelope_state` 同时当“配置对象”和“当前生效判断”，非常危险。

### RC2 变化
RC2 明确拆成：

- `risk_policy_switch`
- `risk_policy_profile`
- `effective_risk_envelope_state`

并且：

- `config-change` 只允许写配置态
- `effective_risk_envelope_state` 明确只读
- 推导规则全部改为读取 `effective_risk_envelope_state`

### 结论
这一步非常重要。  
它让后端实现者不会再把“改策略”误当成“伪造当前风险结果”。

**判定：P0 已关闭。**

---

## 1.6 审计摘要分层

### 审核点
上一版的输入接口会污染“最近操作摘要”，导致 GUI 首页可能把一条 manual note 显示成最近控制动作。

### RC2 变化
RC2 明确拆成：

- `last_control_action_*`
- `last_write_action_*`

并规定：

- 控制类动作更新两套
- 输入类动作只更新写动作摘要
- `GET /system/overview` 与 `GET /system/audit-summary` 都拆开返回

### 结论
这一点对 GUI 落地非常有价值。  
首页可以稳定显示“最近控制动作”和“最近录入动作”，不会再互相覆盖。

**判定：P0 已关闭。**

---

## 2. 与状态字典的一致性审核

RC2 这次没有强行假装“API 改完就完事”。  
它明确列出了 **状态字典伴随修补清单**，这一点是对的。

需要同步进入状态字典的，至少有三组：

1. `risk_policy_switch / risk_policy_profile / effective_risk_envelope_state`
2. `last_control_action_* / last_write_action_*`
3. 连接与来源状态枚举

这意味着：

- RC2 自身在 API 合同层是闭合的
- 但要真正做到“字典-API- GUI 三方零歧义”，状态字典必须同步补丁

我的判断是：这是**正确的处理方式**。  
因为它诚实地标出了依赖项，而不是把不一致隐掉。

---

## 3. 与 GUI 落地的一致性审核

RC2 现在已经足够考虑 GUI 落地，主要体现在五点：

### 3.1 同屏快照一致性
`snapshot_id` 被正式纳入 envelope，GUI 必须以它判断是否同屏一致。

### 3.2 来源诊断可视化
`source_context` 让 GUI 有能力展示“当前这页到底靠什么链路拿到事实”。

### 3.3 控制按钮安全前置
GUI 必须同时看 `snapshot_id`、`state_revision`、`source_context`，而不是只看某个按钮旁边的小摘要。

### 3.4 bundle 过程的 UI 行为
RC2 明确要求 bundle 过程中冻结受影响控制区，这避免了重复点击和混刷。

### 3.5 学习接口 shape 固定
这避免了前端因为环境差异拿到不同 JSON 结构而频繁特判。

这五点，已经把“能否稳定支撑 GUI MVP / 控制中心 / 运维页”这个层面考虑得比较完整了。

---

## 4. 仍然存在的非阻断注意项

下面这些我不再归类为 P0；它们是实现期必须注意的点。

### 4.1 认证网关仍需真实落地
合同里写了角色和 scope，但你仍需决定：
- JWT / session / mTLS / 内部反向代理哪一种
- token 刷新策略
- 浏览器会话安全策略
- 是否启用 CSRF 防护（取决于 cookie 还是 bearer）

### 4.2 `source_context` 的计算器必须单点实现
不要让：
- REST 适配器
- WS 适配器
- GUI 聚合层
- API 网关

各自算一版连接状态。  
应有单一 source-context compiler。

### 4.3 `snapshot_id` 的生成规则要稳定
建议基于：
- `state_revision`
- `snapshot_ts_ms`
- pinned runtime snapshot id
- 关键来源摘要

生成稳定 ID。  
不要每次 GET 都无意义生成随机 ID，否则 GUI 无法做同屏一致性判断。

### 4.4 bundle 工作副本实现要谨慎
RC2 已经把合同讲清楚，但实现时必须防止：
- 工作副本和真实状态对象共享引用
- 中途异常导致工作副本脏写
- bundle audit 与 step audit 的关联丢失

### 4.5 reason code 与枚举必须真正集中注册
不要只在文档里集中，在代码里又分散写字符串常量。  
否则几周后还是会漂。

---

## 5. 最终签署意见

如果让我给这版 RC2 一个正式签署结论，我会写成：

> **结论：通过合同级审查，可作为 V1 RC2 最终候选进入实现。**
>
> **备注：未发现剩余 P0 级合同阻断问题。**
>
> **条件：状态字典伴随修补必须同步落地；生产安全仍取决于实现层按合同兑现。**

再说得直接一点：

- **作为 API 文档：这版已经够严。**
- **作为最终生产系统：还需要实现、联调、故障注入、权限测试来证明。**

这个结论我认为是诚实且严格的。
