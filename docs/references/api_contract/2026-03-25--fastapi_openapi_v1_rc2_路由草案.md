# OpenClaw / Bybit FastAPI / OpenAPI V1 RC2 路由草案

## 0. 目标

本草案用于把《OpenClaw / Bybit Control API V1 RC2 最终候选版》直接落成后端服务接口骨架，约束：

- 服务前缀固定：`/api/v1`
- 框架目标：FastAPI + Pydantic v2
- 状态字典版本：`openclaw_bybit_state_dictionary@v1`
- API 合同版本：`openclaw_bybit_control_api_v1_rc2@v1`
- V1 默认只接入 `bybit_prod_readonly_main`
- V1 不允许直接下真实单；执行链只允许保留语义与来源展示

---

## 1. 推荐服务分层

```text
app/
  main.py
  api/
    deps.py
    routers/
      system.py
      learning.py
      control.py
      input.py
  models/
    common.py
    enums.py
    system.py
    control.py
    input.py
    learning.py
  services/
    auth_service.py
    state_store.py
    state_compiler.py
    idempotency_service.py
    audit_service.py
    source_context_service.py
    recheck_service.py
    demo_control_service.py
    input_service.py
  connectors/
    openclaw_runtime_adapter.py
    bybit_readonly_adapter.py
  infra/
    locks.py
    settings.py
    logging.py
    errors.py
```

### 1.1 分层职责

- `api/routers/*`：仅做参数绑定、依赖注入、响应组装
- `models/*`：冻结请求 / 响应模型与枚举
- `services/state_store.py`：负责读取 / 提交状态字典快照
- `services/state_compiler.py`：负责派生字段与快照编译
- `services/idempotency_service.py`：负责 `(request_id, idempotency_key)` 追踪
- `services/audit_service.py`：负责审计记录与 `audit_context` 更新
- `services/source_context_service.py`：负责只读链 / 执行链 / 连接状态组装
- `services/recheck_service.py`：负责 J/K recheck 与 closeout 动作
- `services/demo_control_service.py`：负责 validate / arm / enable / relock 状态机
- `services/input_service.py`：负责 cost / event / note / config-change
- `connectors/openclaw_runtime_adapter.py`：统一对 OpenClaw runtime 取数
- `connectors/bybit_readonly_adapter.py`：统一对 Bybit 只读私有事实取数

---

## 2. 安全与依赖注入

## 2.1 FastAPI Security

推荐固定采用以下依赖：

- `HTTPBearer` 或内部 SSO Bearer Token
- `require_authenticated_actor()`
- `require_roles([...])`
- `require_scopes([...])`
- `bind_operator_identity()`

## 2.2 认证上下文对象

```python
AuthenticatedActor(
    actor_id: str,
    actor_type: Literal["human", "service"],
    roles: set[str],
    scopes: set[str],
    session_id: str | None,
)
```

## 2.3 角色 / scope 建议

| 接口族 | 最低角色 | 最低 scope |
| --- | --- | --- |
| `GET /system/*` | `viewer` | `state:read` |
| `GET /learning/*` | `viewer` | `learning:read` |
| `POST /control/recheck/*` | `operator` | `control:recheck` |
| `POST /control/demo/validate` | `operator` | `control:validate` |
| `POST /control/demo/arm` | `operator_guarded` | `control:arm` |
| `POST /control/demo/enable` | `operator_guarded` | `control:enable` |
| `POST /control/demo/relock` | `operator_guarded` | `control:relock` |
| `POST /control/safe-recheck-bundle` | `operator_guarded` | `control:bundle` |
| `POST /input/cost` | `finance_input` or `operator` | `input:cost` |
| `POST /input/event` | `operator` | `input:event` |
| `POST /input/manual-note` | `operator` | `input:note` |
| `POST /input/config-change` | `config_admin` | `input:config` |

---

## 3. 公共模型建议

## 3.1 请求 envelope

```python
class RequestEnvelope(BaseModel):
    request_id: str
    idempotency_key: str
    operator_id: str
    reason: str
    client_ts_ms: int
    expected_state_revision: int
    expected_previous_state: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
```

## 3.2 响应 envelope

```python
class ResponseEnvelope(BaseModel, Generic[T]):
    api_version: Literal["v1"]
    schema_version: Literal["v1"]
    request_id: str | None
    snapshot_ts_ms: int
    snapshot_id: str
    state_revision: int
    action_result: Literal["success", "failed", "blocked", "replayed"]
    reason_codes: list[str]
    warnings: list[str]
    audit_ref: str | None
    source_context: SourceContext
    data: T
```

## 3.3 公共异常映射

| 异常类 | HTTP | `action_result` | 说明 |
| --- | --- | --- | --- |
| `ValidationContractError` | `400` | `failed` | 入参结构 / 枚举 / 路径非法 |
| `AuthenticationError` | `401` | `failed` | 未认证 |
| `AuthorizationError` | `403` | `failed` | 已认证但无权 |
| `RevisionConflictError` | `409` | `failed` | revision / previous_state / 幂等冲突 |
| `BusinessBlockedError` | `422` | `blocked` | gate、ack、cooldown、mode 阻断 |
| `SourceUnavailableError` | `503` | `failed` | 上游事实不可用 |
| `InternalControlError` | `500` | `failed` | 非预期错误 |

---

## 4. 路由注册清单

## 4.1 只读路由

| 方法 | 路径 | tag | response model |
| --- | --- | --- | --- |
| GET | `/api/v1/system/overview` | `system` | `ResponseEnvelope[OverviewData]` |
| GET | `/api/v1/system/chapter-status` | `system` | `ResponseEnvelope[ChapterStatusData]` |
| GET | `/api/v1/system/control-plane` | `system` | `ResponseEnvelope[ControlPlaneData]` |
| GET | `/api/v1/system/capability-matrix` | `system` | `ResponseEnvelope[CapabilityMatrixData]` |
| GET | `/api/v1/system/product-families` | `system` | `ResponseEnvelope[ProductFamiliesData]` |
| GET | `/api/v1/system/business/daily` | `system` | `ResponseEnvelope[BusinessDailyData]` |
| GET | `/api/v1/system/health` | `system` | `ResponseEnvelope[HealthTelemetryData]` |
| GET | `/api/v1/system/audit-summary` | `system` | `ResponseEnvelope[AuditSummaryData]` |
| GET | `/api/v1/system/source-context` | `system` | `ResponseEnvelope[SourceContextData]` |
| GET | `/api/v1/learning/overview` | `learning` | `ResponseEnvelope[LearningOverviewData]` |
| GET | `/api/v1/learning/hypotheses` | `learning` | `ResponseEnvelope[LearningHypothesesData]` |

## 4.2 控制路由

| 方法 | 路径 | tag | response model |
| --- | --- | --- | --- |
| POST | `/api/v1/control/recheck/j-canonical` | `control` | `ResponseEnvelope[RecheckResultData]` |
| POST | `/api/v1/control/recheck/k-canonical` | `control` | `ResponseEnvelope[RecheckResultData]` |
| POST | `/api/v1/control/recheck/j-closeout` | `control` | `ResponseEnvelope[RecheckResultData]` |
| POST | `/api/v1/control/recheck/k-closeout` | `control` | `ResponseEnvelope[RecheckResultData]` |
| POST | `/api/v1/control/demo/validate` | `control` | `ResponseEnvelope[DemoValidateData]` |
| POST | `/api/v1/control/demo/arm` | `control` | `ResponseEnvelope[DemoTransitionData]` |
| POST | `/api/v1/control/demo/enable` | `control` | `ResponseEnvelope[DemoTransitionData]` |
| POST | `/api/v1/control/demo/relock` | `control` | `ResponseEnvelope[DemoTransitionData]` |
| POST | `/api/v1/control/safe-recheck-bundle` | `control` | `ResponseEnvelope[SafeBundleData]` |

## 4.3 输入路由

| 方法 | 路径 | tag | response model |
| --- | --- | --- | --- |
| POST | `/api/v1/input/cost` | `input` | `ResponseEnvelope[InputAcceptedData]` |
| POST | `/api/v1/input/event` | `input` | `ResponseEnvelope[InputAcceptedData]` |
| POST | `/api/v1/input/manual-note` | `input` | `ResponseEnvelope[InputAcceptedData]` |
| POST | `/api/v1/input/config-change` | `input` | `ResponseEnvelope[ConfigChangeAcceptedData]` |

---

## 5. 路由实现约束

## 5.1 GET 统一实现流

1. 读取最新稳定状态快照
2. 编译 `source_context`
3. 绑定同一 `snapshot_id`
4. 按路由裁剪 `data`
5. 返回 `action_result = "success"`

### 5.1.1 GET 禁止项

- 禁止 GET 触发 recheck
- 禁止 GET 更新状态字典 canonical
- 禁止 GET 隐式修复 stale 字段
- 禁止 GET 直接调用高成本外部链路做同步刷新

## 5.2 POST 统一实现流

1. 认证 / 授权
2. 校验 envelope
3. 校验 `operator_id` 与认证主体一致
4. 查询幂等记录
5. 获取写锁
6. 读取当前 canonical 状态
7. 校验 `expected_state_revision`
8. 校验 `expected_previous_state`
9. 执行动作逻辑
10. 更新状态字典 canonical / audit_context
11. 提交新快照并递增 `state_revision`
12. 写入幂等记录
13. 返回稳定响应

### 5.2.1 写锁建议

| 路由 | 锁 key |
| --- | --- |
| recheck / bundle | `control:recheck` |
| demo validate / arm / enable / relock | `control:demo` |
| config-change | `input:config` |
| cost / event / note | `input:append` |

---

## 6. OpenClaw / Bybit 适配落地

## 6.1 统一适配器接口

```python
class OpenClawRuntimeAdapter(Protocol):
    async def get_runtime_snapshot(self) -> RuntimeSnapshot: ...
    async def get_private_rest_status(self) -> ConnectionStatus: ...
    async def get_private_ws_status(self) -> ConnectionStatus: ...
    async def get_account_permission_facts(self) -> AccountPermissionFacts: ...
    async def get_product_family_facts(self) -> ProductFamilyFacts: ...
```

## 6.2 接入原则

- API 层不直接拼 Bybit REST / WS
- 统一从 OpenClaw runtime adapter 取“已归一化事实”
- 若 runtime 不能提供某事实，必须显式返回 `unknown / partial / missing`
- 不得用默认值伪装成 `ready / complete`

## 6.3 连接失败落地

以下场景必须通过 `SourceUnavailableError` 进入 `503`：

- `rest_private_connection_state in {"down", "unknown"}`
- `runtime_connection_state in {"down", "unknown"}`
- `source_snapshot_completeness_state in {"missing"}`
- recheck 需要的账户事实为空
- product-family 权限事实不可判定

---

## 7. GUI 对接约束

## 7.1 首页推荐拉取顺序

1. `/system/overview`
2. `/system/control-plane`
3. `/system/health`
4. `/system/audit-summary`
5. `/system/source-context`

要求：同一页只接受同一 `snapshot_id`。

## 7.2 控制中心推荐拉取顺序

1. `/system/control-plane`
2. `/system/product-families`
3. `/system/health`
4. `/system/source-context`
5. `/system/audit-summary`

## 7.3 前端按钮启用规则

前端只以以下只读字段决定按钮是否可点：

- `demo_arm_gate_state`
- `demo_enable_gate_state`
- `effective_*_allowed_state`
- `global_execution_authority_state`
- `source_context.connector_role_separation_ok`
- `source_context.runtime_connection_state`

前端禁止自行推导状态机前态。

---

## 8. OpenAPI 文档生成要求

## 8.1 tags

- `system`
- `learning`
- `control`
- `input`

## 8.2 securitySchemes

```yaml
components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
```

## 8.3 每个 POST 必须补充的 OpenAPI 说明

- 需要的角色 / scope
- 是否推进状态机
- 是否要求 `expected_previous_state`
- 允许的 `reason_codes`
- 审计写入范围
- 幂等行为

---

## 9. 发布前最小测试矩阵

### 9.1 合同测试

- 所有路由返回统一 envelope
- 所有 POST 缺少认证返回 `401`
- `operator_id` 不一致返回 `403`
- `expected_state_revision` 错误返回 `409`
- 幂等重放返回 `200 + replayed`

### 9.2 OpenClaw 连接测试

- runtime healthy + rest ready + ws ready
- runtime degraded
- private rest down
- ws down
- account facts partial
- source snapshot missing

### 9.3 GUI 一致性测试

- 同屏 `snapshot_id` 一致
- bundle 中间态不可误显示为最终执行开放
- stale 页面必须标记并重拉

---

## 10. 推荐实现顺序

1. 枚举与模型
2. 认证 / 授权依赖
3. `state_store + state_compiler`
4. `source_context_service`
5. 全部 GET
6. `demo/validate`
7. `arm / enable / relock`
8. recheck / closeout
9. safe bundle
10. input routes
11. OpenAPI 导出
12. GUI 联调

