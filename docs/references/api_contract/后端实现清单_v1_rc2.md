# OpenClaw / Bybit 后端实现清单 V1 RC2

## 0. 使用方式

本清单按“可直接执行”的工程顺序组织。每项只有两种状态：

- `未完成`
- `完成并通过验证`

不得以“部分完成”替代验收。

---

## 1. 基础工程

### 1.1 仓库结构

- [ ] 建立 `app/api/routers`
- [ ] 建立 `app/models`
- [ ] 建立 `app/services`
- [ ] 建立 `app/connectors`
- [ ] 建立 `app/infra`
- [ ] 建立 `tests/contracts`
- [ ] 建立 `tests/integration`
- [ ] 建立 `tests/gui_readiness`

### 1.2 运行配置

- [ ] 固定 `API_PREFIX=/api/v1`
- [ ] 固定 `API_VERSION=v1`
- [ ] 固定 `SCHEMA_VERSION=v1`
- [ ] 建立环境变量加载器
- [ ] 建立日志格式与 request correlation
- [ ] 建立健康检查端点（服务自身，不属于控制 API 合同）

---

## 2. 枚举与模型冻结

### 2.1 公共模型

- [ ] `RequestEnvelope`
- [ ] `ResponseEnvelope[T]`
- [ ] `SourceContext`
- [ ] `AuditSummaryData`
- [ ] `OverviewData`
- [ ] `ControlPlaneData`
- [ ] `ProductFamiliesData`
- [ ] `BusinessDailyData`
- [ ] `HealthTelemetryData`
- [ ] `LearningOverviewData`
- [ ] `LearningHypothesesData`

### 2.2 枚举注册表

- [ ] demo 状态机枚举
- [ ] gate state 枚举
- [ ] effective allow state 枚举
- [ ] connection state 枚举
- [ ] completeness state 枚举
- [ ] reason code 枚举
- [ ] action result 枚举

### 2.3 验收

- [ ] 所有枚举只出现单一定义
- [ ] 所有 response model 均可直接用于 OpenAPI 导出
- [ ] 所有 POST 都复用统一 envelope

---

## 3. 认证与授权

### 3.1 认证层

- [ ] Bearer token 解析器
- [ ] 会话失效处理
- [ ] `401` 统一异常映射
- [ ] 认证主体对象注入

### 3.2 授权层

- [ ] `require_roles`
- [ ] `require_scopes`
- [ ] `operator_identity_mismatch` 检查
- [ ] `403` 统一异常映射

### 3.3 验收

- [ ] 匿名 POST 均返回 `401`
- [ ] 角色不足返回 `403`
- [ ] `operator_id` 与认证主体不一致返回 `403`

---

## 4. 状态存储与快照编译

### 4.1 state store

- [ ] 定义快照读接口
- [ ] 定义快照写接口
- [ ] 定义 `state_revision` 递增规则
- [ ] 定义 `snapshot_id` 生成规则
- [ ] 定义写锁 / 租约机制

### 4.2 state compiler

- [ ] 编译 `global_execution_authority_state`
- [ ] 编译 `effective_*_allowed_state`
- [ ] 编译 `effective_risk_envelope_state`
- [ ] 编译 `product_family_summary`
- [ ] 编译首页 overview 所需聚合字段

### 4.3 验收

- [ ] 相同输入快照产生稳定相同输出
- [ ] 派生字段禁止被存储层直写覆盖
- [ ] `snapshot_id` 可作为 GUI 同屏一致性标识

---

## 5. OpenClaw / Bybit 适配

### 5.1 适配器骨架

- [ ] `OpenClawRuntimeAdapter`
- [ ] `BybitReadonlyAdapter`
- [ ] runtime snapshot 归一化模型
- [ ] product-family 权限事实归一化模型
- [ ] 连接状态归一化模型

### 5.2 来源语义

- [ ] 固定 `readonly_connector_name = bybit_prod_readonly_main`
- [ ] 固定默认 `execution_connector_name = null`
- [ ] 生成 `connector_role_separation_ok`
- [ ] 生成 `source_snapshot_completeness_state`
- [ ] 生成 `pinned_runtime_snapshot_id`

### 5.3 验收

- [ ] 上游正常时 source_context 完整
- [ ] 上游 partial / missing 时不伪装为 ready
- [ ] 依赖真实私有事实的控制路由在不可判定时返回 `503`

---

## 6. 幂等、并发、审计

### 6.1 幂等服务

- [ ] 定义 `(request_id, idempotency_key)` 存储模型
- [ ] 支持“同体重放返回 replayed”
- [ ] 支持“同 key 异体返回 idempotency_conflict”
- [ ] 记录原始 `audit_ref / state_revision / snapshot_id`

### 6.2 并发控制

- [ ] 统一 `expected_state_revision` 检查
- [ ] 统一 `expected_previous_state` 检查
- [ ] `409` reason code 仅允许并发类 code

### 6.3 审计

- [ ] `last_write_action_*` 更新器
- [ ] `last_control_action_*` 更新器
- [ ] 审计记录持久化
- [ ] `audit_ref` 生成规则

### 6.4 验收

- [ ] 重放不重复推进状态机
- [ ] revision 冲突不写任何 canonical 字段
- [ ] 所有 POST 均写审计

---

## 7. GET 路由实现

### 7.1 system

- [ ] `/system/overview`
- [ ] `/system/chapter-status`
- [ ] `/system/control-plane`
- [ ] `/system/capability-matrix`
- [ ] `/system/product-families`
- [ ] `/system/business/daily`
- [ ] `/system/health`
- [ ] `/system/audit-summary`
- [ ] `/system/source-context`

### 7.2 learning

- [ ] `/learning/overview`
- [ ] `/learning/hypotheses`

### 7.3 验收

- [ ] 所有 GET 返回统一 envelope
- [ ] 所有 GET 返回同一快照时 `snapshot_id` 一致
- [ ] learning 接口 shape 固定，不因实现阶段变化

---

## 8. 控制路由实现

### 8.1 recheck

- [ ] `j-canonical`
- [ ] `k-canonical`
- [ ] `j-closeout`
- [ ] `k-closeout`

### 8.2 demo 状态机

- [ ] `demo/validate`
- [ ] `demo/arm`
- [ ] `demo/enable`
- [ ] `demo/relock`

### 8.3 bundle

- [ ] `safe-recheck-bundle`
- [ ] bundle step 结果对象
- [ ] bundle 统一最终 `state_revision`
- [ ] bundle 统一 `audit_ref`
- [ ] bundle GUI 可见性规则

### 8.4 验收

- [ ] validate 仅做评估与写 gate 结果
- [ ] arm 仅允许从 `closed | relocked` 进入 `armed_but_closed`
- [ ] enable 仅允许从 `armed_but_closed` 进入 `demo_enabled`
- [ ] relock 允许把 demo 主状态机收回到 `relocked`
- [ ] bundle 不向 GUI 暴露中间态为可执行开放

---

## 9. 输入路由实现

### 9.1 输入路由

- [ ] `/input/cost`
- [ ] `/input/event`
- [ ] `/input/manual-note`
- [ ] `/input/config-change`

### 9.2 config-change 白名单

- [ ] 白名单路径硬编码或集中注册
- [ ] 禁止任何 `ACT / DRV / AUD` 路径直写
- [ ] 禁止 demo 主状态机相关字段直写
- [ ] 禁止 effective 派生字段直写

### 9.3 验收

- [ ] 非白名单返回 `400` 或 `422`
- [ ] `config-change` 不得污染动作型字段
- [ ] `last_write_action_*` 正确更新

---

## 10. GUI 联调准备

### 10.1 接口稳定性

- [ ] 所有 GET 响应字段名冻结
- [ ] 所有按钮 gating 字段存在
- [ ] 所有卡片可从单一接口或稳定多接口组合得到

### 10.2 一致性

- [ ] 多接口同屏 `snapshot_id` 校验通过
- [ ] 页面过期提示协议可用
- [ ] 前端不需要猜测状态机前态

### 10.3 验收

- [ ] 首页联调通过
- [ ] 控制中心联调通过
- [ ] 学习页联调通过

---

## 11. 合同测试与集成测试

### 11.1 合同测试

- [ ] 所有路由状态码符合 RC2
- [ ] 所有 `reason_codes` 属于注册表
- [ ] 所有响应带 `source_context`
- [ ] 所有响应带 `snapshot_id`

### 11.2 集成测试

- [ ] OpenClaw runtime healthy
- [ ] runtime degraded
- [ ] private REST down
- [ ] private WS down
- [ ] account facts partial
- [ ] source snapshot missing

### 11.3 状态机测试

- [ ] validate -> arm -> enable -> relock 正常路径
- [ ] validate blocked 路径
- [ ] cooldown blocked 路径
- [ ] operator ack 缺失路径
- [ ] revision 冲突路径
- [ ] replayed 路径

---

## 12. 冻结前发布门槛

- [ ] 状态字典伴随补丁已合入
- [ ] Control API RC2 合同测试全绿
- [ ] GUI 联调最小页面通过
- [ ] 只读链来源展示正确
- [ ] 没有任何直写 `ACT / DRV / AUD` 的残留实现
- [ ] 没有任何未注册 reason code 出现在响应里

