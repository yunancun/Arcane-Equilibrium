# OpenClaw / Bybit Control API V1 RC2 最终候选版

## 0. 冻结范围

- 文档名：`openclaw_bybit_control_api_v1_rc2`
- 适配状态字典：`openclaw_bybit_state_dictionary`
- 目标版本：
  - `document_version = "v1-rc2"`
  - `schema_version = "v1"`
  - `api_version = "v1"`
- 基础前缀：`/api/v1`
- 数据格式：`application/json; charset=utf-8`
- 本版目标：
  1. 补齐认证 / 授权合同
  2. 补齐 OpenClaw ↔ Bybit 连接与来源语义
  3. 定死 `demo/validate` 的接口级返回语义
  4. 定死 `safe-recheck-bundle` 的一致性与 GUI 可见性规则
  5. 拆开风险配置态与风险生效态
  6. 拆开最近控制动作摘要与最近任意写动作摘要
  7. 让 GUI 落地时不需要再猜“这页状态来自哪条链、是否同一快照、是否可安全操作”

---

## 1. 总体合同

### 1.1 统一请求 envelope

所有 `POST` 接口统一使用以下 envelope：

```json
{
  "request_id": "uuid-or-stable-string",
  "idempotency_key": "stable-string",
  "operator_id": "string",
  "reason": "string",
  "client_ts_ms": 0,
  "expected_state_revision": 0,
  "expected_previous_state": null,
  "payload": {}
}
```

### 1.2 统一响应 envelope

所有 `GET` / `POST` 接口统一返回：

```json
{
  "api_version": "v1",
  "schema_version": "v1",
  "request_id": "string|null",
  "snapshot_ts_ms": 0,
  "snapshot_id": "string",
  "state_revision": 0,
  "action_result": "success",
  "reason_codes": [],
  "warnings": [],
  "audit_ref": "string|null",
  "source_context": {},
  "data": {}
}
```

### 1.3 响应 envelope 字段规则

| 字段 | 类型 | 必填 | 规则 |
| --- | --- | --- | --- |
| `api_version` | string | Y | 固定 `v1` |
| `schema_version` | string | Y | 固定 `v1` |
| `request_id` | string/null | Y | `GET` 可为 `null`，`POST` 必须回显 |
| `snapshot_ts_ms` | int | Y | 本次响应绑定的服务端快照时间 |
| `snapshot_id` | string | Y | 同一快照的稳定标识；GUI 多卡片必须以此判断是否同屏一致 |
| `state_revision` | int | Y | 响应对应的最终修订号 |
| `action_result` | string | Y | `success` `failed` `blocked` `replayed` |
| `reason_codes` | string[] | Y | 只允许使用本注册表中的值 |
| `warnings` | string[] | Y | 非阻断提示 |
| `audit_ref` | string/null | Y | 审计引用 ID |
| `source_context` | object | Y | 来源、连接、角色分离、快照完整性上下文 |
| `data` | object | Y | 接口专属返回体 |

### 1.4 HTTP 状态码合同

| HTTP | 使用场景 |
| --- | --- |
| `200` | `GET` 成功；`POST` 成功；或 `POST` 幂等重放 |
| `400` | 请求结构非法、字段缺失、枚举非法、路径非法 |
| `401` | 未认证、令牌缺失、令牌无效、会话失效 |
| `403` | 已认证但无权限、角色不符、`operator_id` 与认证主体不一致 |
| `409` | `state_revision_mismatch` / `previous_state_mismatch` / `idempotency_conflict` / 资源租约冲突 |
| `422` | 业务阻断；例如 gate 未通过、ack 缺失、cooldown 生效 |
| `503` | 读取不到可用上游事实、connector 不可用、来源快照不完整、交易所链路不可判定 |
| `500` | 未预期内部错误 |

### 1.5 幂等规则

1. `(request_id, idempotency_key)` 组合必须可追踪。
2. 同一 `idempotency_key`：
   - 若请求体完全一致，允许返回 `action_result = replayed`
   - 若请求体不一致，必须返回 `409 + idempotency_conflict`
3. `replayed` 不得重复推进状态机，不得重复生成业务记录。
4. `replayed` 必须返回原始 `audit_ref`、原始 `state_revision`、原始 `snapshot_id`。

### 1.6 并发规则

1. 所有写接口必须检查 `expected_state_revision == meta.state_revision`。
2. 所有要求前态的动作接口必须检查 `expected_previous_state`。
3. 任一检查失败：
   - 不得写入任何 canonical 字段
   - 返回 `409`
   - `action_result = failed`
   - `reason_codes` 仅允许并发类 code

### 1.7 认证 / 授权合同

1. 所有 `POST` 接口必须要求认证。
2. 除明确公开的开发态本地调试外，所有控制类与输入类接口不得匿名访问。
3. 服务端必须从认证层导出：
   - `authenticated_actor_id`
   - `authenticated_actor_type`
   - `authenticated_roles`
   - `authenticated_scopes`
4. `operator_id` 只是调用方声明值，不构成认证事实。
5. 若 `operator_id` 与 `authenticated_actor_id` 不一致，必须返回：
   - `403`
   - `action_result = failed`
   - `reason_codes = ["operator_identity_mismatch"]`
6. 最低角色 / scope 建议：
   - 只读接口：`viewer`
   - recheck / validate：`operator`
   - arm / enable / relock：`operator_guarded`
   - config-change：`config_admin`
   - manual-note / cost / event：`operator` 或 `finance_input`
7. GUI 不得直接保存高权限 secrets；GUI 必须通过受控后端会话 / token 调用 API。

### 1.8 审计最小写入集

所有 `POST` 接口必须更新 `audit_context.last_write_action_*`。  
所有控制类 `POST` 还必须更新 `audit_context.last_control_action_*`。

#### 必写字段

- `audit_context.last_write_action_type`
- `audit_context.last_write_action_request_id`
- `audit_context.last_write_action_ts_ms`
- `audit_context.last_write_action_by`
- `audit_context.last_write_action_result`
- `audit_context.last_write_action_reason_codes`
- `audit_context.last_write_action_audit_ref`

控制类接口额外必写：

- `audit_context.last_control_action_type`
- `audit_context.last_control_action_request_id`
- `audit_context.last_control_action_ts_ms`
- `audit_context.last_control_action_by`
- `audit_context.last_control_action_result`
- `audit_context.last_control_action_reason_codes`
- `audit_context.last_control_action_audit_ref`

### 1.9 GET 一致性规则

1. 所有 `GET` 接口都必须返回 `snapshot_id`。
2. GUI 同一屏如果拉取多个 `GET`，必须只接受：
   - `snapshot_id` 相同；或
   - 用户明确触发刷新后整体重绘
3. 若同一屏接口返回不同 `snapshot_id`，GUI 必须标记“页面已过期”并发起重拉。
4. 不允许 GUI 在不同 `snapshot_id` 的结果上混合显示“可执行控制按钮”。

---

## 2. OpenClaw / Bybit 连接与来源合同

### 2.1 `source_context` 统一结构

所有响应都必须带以下 `source_context`：

```json
{
  "readonly_connector_name": "bybit_prod_readonly_main",
  "readonly_connector_role": "fact_source",
  "readonly_connector_scope": "private_readonly",
  "execution_connector_name": null,
  "execution_connector_role": "execution_source_reserved",
  "execution_connector_scope": "not_attached",
  "connector_role_separation_ok": true,
  "rest_private_connection_state": "ready",
  "ws_private_connection_state": "ready",
  "runtime_connection_state": "healthy",
  "account_fact_completeness_state": "complete",
  "source_snapshot_completeness_state": "complete",
  "pinned_runtime_snapshot_id": "string",
  "pinned_runtime_snapshot_ts_ms": 0
}
```

### 2.2 来源规则

1. V1 / RC2 的私有账户事实默认来自只读链路。
2. 默认只读链路角色名固定建议为：`bybit_prod_readonly_main`。
3. 未来执行链路角色名固定建议为：`bybit_prod_live_executor`。
4. 若未接入执行链路，`execution_connector_name = null` 合法。
5. 不允许让只读链路与执行链路在合同层语义混同。
6. `connector_role_separation_ok = false` 时：
   - 不得开放任何受控执行按钮
   - `global_execution_authority_state` 只能落在保守阻断态

### 2.3 连接状态枚举

| 字段 | 合法值 |
| --- | --- |
| `rest_private_connection_state` | `ready` `degraded` `down` `unknown` |
| `ws_private_connection_state` | `ready` `degraded` `down` `unknown` |
| `runtime_connection_state` | `healthy` `degraded` `down` `unknown` |
| `account_fact_completeness_state` | `complete` `partial` `missing` `unknown` |
| `source_snapshot_completeness_state` | `complete` `partial` `missing` `unknown` |

### 2.4 来源阻断规则

出现以下任一情况时，依赖真实私有事实的控制接口必须返回 `503`：

- `readonly_connector_missing`
- `connector_unavailable`
- `exchange_http_error`
- `exchange_auth_failed`
- `exchange_permission_unknown`
- `websocket_not_ready`
- `runtime_fact_unavailable`
- `source_snapshot_incomplete`
- `connector_role_mismatch`

### 2.5 GUI 来源展示要求

GUI 至少要能展示：

- 当前事实链路名称
- 是否为只读链路
- 是否已接执行链路
- REST / WS 是否健康
- 当前页面快照是否完整
- 当前页面 `snapshot_id`
- 当前页面 `state_revision`

---

## 3. Reason code 注册表 RC2

### 3.1 通用并发 / 幂等

- `state_revision_mismatch`
- `previous_state_mismatch`
- `replayed_request`
- `idempotency_conflict`
- `bundle_execution_lease_busy`

### 3.2 认证 / 授权

- `unauthenticated`
- `forbidden_role`
- `forbidden_scope`
- `operator_identity_mismatch`

### 3.3 OpenClaw / Bybit 连接与来源

- `readonly_connector_missing`
- `execution_connector_missing`
- `connector_unavailable`
- `connector_role_mismatch`
- `exchange_http_error`
- `exchange_auth_failed`
- `exchange_permission_unknown`
- `websocket_not_ready`
- `runtime_fact_unavailable`
- `source_snapshot_incomplete`

### 3.4 demo 动作 / gate

- `prerequisites_not_passed`
- `not_armed`
- `not_enabled`
- `operator_ack_required`
- `cooldown_active`
- `health_gate_blocked`
- `risk_envelope_blocked`
- `execution_mode_disabled`
- `live_mode_reserved_only`

### 3.5 权限生效阻断

- `configured_switch_disabled`
- `product_family_disabled`
- `product_family_not_visible`
- `product_family_mode_blocked`
- `global_execution_blocked`
- `demo_not_enabled`
- `risk_scope_blocked`

### 3.6 数据 / 健康

- `runtime_stale`
- `latency_exceeded`
- `exchange_timeout_exceeded`
- `ws_disconnect_exceeded`

### 3.7 输入 / 配置

- `path_not_whitelisted`
- `cfg_field_required`
- `act_field_write_forbidden`
- `drv_field_write_forbidden`
- `aud_field_write_forbidden`
- `immutable_path_forbidden`

---

## 4. 只读接口

## 4.1 `GET /api/v1/system/overview`

### 用途

GUI 首页只读总览。

### 响应 `data`

```json
{
  "global_runtime": {},
  "chapter_status_summary": {},
  "daily_business_summary": {},
  "health_summary": {},
  "demo_control_summary": {},
  "latest_control_action_summary": {},
  "latest_write_action_summary": {}
}
```

### 说明

- `latest_control_action_summary` 仅表示最近控制动作
- `latest_write_action_summary` 表示最近任意写动作
- 不允许再用单一“latest audit summary”覆盖两者

---

## 4.2 `GET /api/v1/system/chapter-status`

直接返回 `chapter_status`。

---

## 4.3 `GET /api/v1/system/control-plane`

### 响应 `data`

```json
{
  "execution_control_summary": {},
  "demo_control": {},
  "action_permissions": {},
  "health_gate_summary": {},
  "risk_envelope": {}
}
```

### 规则

- `risk_envelope` 中必须区分：
  - `risk_policy_switch` / `risk_policy_profile`：配置态
  - `effective_risk_envelope_state`：生效态，只读
- 不允许把 `effective_risk_envelope_state` 作为通用配置入口

---

## 4.4 `GET /api/v1/system/capability-matrix`

直接返回 `capability_matrix`。

---

## 4.5 `GET /api/v1/system/product-families`

直接返回 `product_family_status`。

---

## 4.6 `GET /api/v1/system/business/daily`

直接返回 `business_metrics.daily`。

---

## 4.7 `GET /api/v1/system/health`

直接返回 `health_telemetry`。

---

## 4.8 `GET /api/v1/system/audit-summary`

### 响应 `data`

```json
{
  "latest_control_action_summary": {},
  "latest_write_action_summary": {},
  "last_state_revision_before": 0,
  "last_state_revision_after": 0
}
```

---

## 4.9 `GET /api/v1/system/source-context`

### 用途

GUI 运维页 / 控制中心来源诊断卡。

### 响应 `data`

直接返回 `source_context` 的只读完整视图。

---

## 4.10 `GET /api/v1/learning/overview`

### 固定响应形状

```json
{
  "summary": {},
  "experiments": {},
  "approval_requirements": {}
}
```

### 规则

即使某些子块尚未实现，也必须返回固定 shape；允许空对象，不允许因部署差异切换返回结构。

---

## 4.11 `GET /api/v1/learning/hypotheses`

### 固定响应形状

```json
{
  "hypotheses": [],
  "experiments": [],
  "approval_requirements": {}
}
```

---

## 5. 控制接口

## 5.1 通用前置规则

所有控制接口都必须先完成以下步骤：

1. 认证与授权检查
2. 幂等检查
3. `expected_state_revision` 检查
4. 如需要，`expected_previous_state` 检查
5. 来源与连接可用性检查
6. 生成 `pinned_runtime_snapshot_id`
7. 用该 pinned snapshot 执行动作 / 评估 / recheck

---

## 5.2 `POST /api/v1/control/recheck/j-canonical`

### 请求 `payload`

```json
{}
```

### 成功 `data`

```json
{
  "chapter": "J",
  "recheck_kind": "canonical",
  "canonical_recheck_state": "passed",
  "canonical_recheck_last_verified_ts_ms": 0,
  "chapter_snapshot": {},
  "pinned_runtime_snapshot_id": "string"
}
```

### 允许的顶层 `reason_codes`

- 并发 / 幂等类
- 连接与来源类

---

## 5.3 `POST /api/v1/control/recheck/k-canonical`

与 `j-canonical` 相同，目标章节改为 `K`。

---

## 5.4 `POST /api/v1/control/recheck/j-closeout`

### 请求 `payload`

```json
{}
```

### 成功 `data`

```json
{
  "chapter": "J",
  "recheck_kind": "closeout",
  "closeout_state": "passed",
  "closeout_last_verified_ts_ms": 0,
  "chapter_snapshot": {},
  "pinned_runtime_snapshot_id": "string"
}
```

### 允许的顶层 `reason_codes`

- 并发 / 幂等类
- 连接与来源类

---

## 5.5 `POST /api/v1/control/recheck/k-closeout`

与 `j-closeout` 相同，目标章节改为 `K`。

---

## 5.6 `POST /api/v1/control/demo/validate`

### 动作语义

`validate` 是“评估动作”，不是“推进状态机动作”。

### 请求 `payload`

```json
{}
```

### 合同规则

1. `validate` 不改变 `demo_state_switch`
2. `validate` 可以把 gate 结果评估成 `passed / failed / blocked`
3. 只要评估流程完成，并且成功写回 gate 结果，接口级 `action_result` 必须是 `success`
4. gate 是否通过，不决定接口级 `action_result`
5. 只有以下情况才允许接口级失败：
   - 并发 / 幂等失败
   - 来源 / 连接失败
   - 未认证 / 未授权
   - 内部错误
6. 因此，`validate` 顶层一般不返回 `422`
7. `validate` 的业务阻断信息必须进入 `data.*_gate_state` 与 `data.*_reason_codes`

### 必写字段

- `control_plane.demo_control.demo_validate_requested`
- `control_plane.demo_control.demo_prerequisites_gate_state`
- `control_plane.demo_control.demo_prerequisites_reason_codes`
- `control_plane.demo_control.demo_prerequisites_last_evaluated_ts_ms`
- `control_plane.demo_control.demo_arm_gate_state`
- `control_plane.demo_control.demo_arm_reason_codes`
- `control_plane.demo_control.demo_arm_last_evaluated_ts_ms`
- `control_plane.demo_control.demo_enable_gate_state`
- `control_plane.demo_control.demo_enable_reason_codes`
- `control_plane.demo_control.demo_enable_last_evaluated_ts_ms`
- `control_plane.demo_control.demo_relock_gate_state`
- `control_plane.demo_control.demo_relock_reason_codes`
- `control_plane.demo_control.demo_relock_last_evaluated_ts_ms`
- `control_plane.demo_control.demo_last_action_type`
- `control_plane.demo_control.demo_last_action_result`
- `control_plane.demo_control.demo_last_action_reason_codes`
- `control_plane.demo_control.demo_last_action_ts_ms`

### 成功 `data`

```json
{
  "demo_state_switch": "closed",
  "demo_prerequisites_gate_state": "passed",
  "demo_prerequisites_reason_codes": [],
  "demo_arm_gate_state": "passed",
  "demo_arm_reason_codes": [],
  "demo_enable_gate_state": "blocked",
  "demo_enable_reason_codes": ["not_armed"],
  "demo_relock_gate_state": "passed",
  "demo_relock_reason_codes": [],
  "pinned_runtime_snapshot_id": "string"
}
```

### 顶层 `action_result`

仅允许：

- `success`
- `failed`
- `replayed`

---

## 5.7 `POST /api/v1/control/demo/arm`

### 请求 `payload`

```json
{
  "acknowledged": true
}
```

### 必填前态

`expected_previous_state` 必填，合法值：

- `closed`
- `relocked`

### 进入条件

- `demo_prerequisites_gate_state = passed`
- `global_execution_mode_switch = demo_reserved`
- 若 `demo_operator_ack_required = true`，则 `payload.acknowledged = true`

### 顶层阻断时返回

- `422`
- `action_result = blocked`

### 允许的顶层 `reason_codes`

- `prerequisites_not_passed`
- `operator_ack_required`
- `execution_mode_disabled`
- `live_mode_reserved_only`
- 并发 / 幂等类
- 连接与来源类

---

## 5.8 `POST /api/v1/control/demo/enable`

### 请求 `payload`

```json
{
  "acknowledged": true
}
```

### 必填前态

`expected_previous_state` 必填，且必须为：

- `armed_but_closed`

### 进入条件

- `demo_enable_gate_state = passed`
- `demo_cooldown_state != active`
- 若 `demo_operator_ack_required = true`，则 `payload.acknowledged = true`

### 顶层阻断时返回

- `422`
- `action_result = blocked`

### 允许的顶层 `reason_codes`

- `not_armed`
- `operator_ack_required`
- `cooldown_active`
- `health_gate_blocked`
- `risk_envelope_blocked`
- 并发 / 幂等类
- 连接与来源类

---

## 5.9 `POST /api/v1/control/demo/relock`

### 请求 `payload`

```json
{}
```

### 必填前态

`expected_previous_state` 必填，合法值：

- `armed_but_closed`
- `demo_enabled`
- `relocked`

### 顶层阻断时返回

- `422`
- `action_result = blocked`

### 说明

`relock` 可以在 `relocked` 上幂等式重放，但若不是同一幂等键，不得把“已经是 relocked”自动视为成功推进；仍应遵守前态与幂等合同。

---

## 5.10 `POST /api/v1/control/safe-recheck-bundle`

### 请求 `payload`

```json
{}
```

### 固定执行顺序

1. `j-canonical`
2. `k-canonical`
3. `j-closeout`
4. `k-closeout`
5. `demo-validate`

### RC2 一致性规则

1. bundle 必须获取单次执行租约
2. bundle 必须固定一个 `bundle_base_snapshot_id`
3. 所有步骤必须基于该 pinned base snapshot 执行
4. 所有步骤结果必须先写入工作副本
5. bundle 成功结束后，统一单次提交
6. bundle 只允许递增一次 `state_revision`
7. GUI 在 bundle 返回前，不应看到 bundle 中间态
8. bundle 响应中的 `state_revision` 必须是最终提交后的 revision
9. bundle 顶层 `snapshot_id` 必须是最终提交后的 snapshot
10. 若 bundle 前置并发检查失败，不得提交任何步骤结果
11. 若步骤中出现业务 `failed / blocked`，仍可在工作副本中记录逐步骤结果并完成最终单次提交
12. 若步骤中出现来源 / 连接失败，bundle 顶层返回 `503`，不得提交部分结果

### 成功 `data`

```json
{
  "bundle_base_snapshot_id": "string",
  "bundle_final_snapshot_id": "string",
  "bundle_committed": true,
  "steps": [
    {
      "step_name": "j-canonical",
      "action_result": "success",
      "reason_codes": [],
      "audit_ref": "string"
    },
    {
      "step_name": "k-canonical",
      "action_result": "success",
      "reason_codes": [],
      "audit_ref": "string"
    },
    {
      "step_name": "j-closeout",
      "action_result": "success",
      "reason_codes": [],
      "audit_ref": "string"
    },
    {
      "step_name": "k-closeout",
      "action_result": "success",
      "reason_codes": [],
      "audit_ref": "string"
    },
    {
      "step_name": "demo-validate",
      "action_result": "success",
      "reason_codes": [],
      "audit_ref": "string"
    }
  ]
}
```

### 顶层 `reason_codes`

仅允许：

- `bundle_execution_lease_busy`
- 并发 / 幂等类
- 连接与来源类

### 顶层 `action_result`

仅允许：

- `success`
- `failed`
- `replayed`

---

## 6. 输入接口

## 6.1 `POST /api/v1/input/cost`

### 用途

录入经营成本。

### 成功后要求

- 更新 `business_metrics.daily.*`
- 更新 `audit_context.last_write_action_*`
- 不更新 `audit_context.last_control_action_*`

---

## 6.2 `POST /api/v1/input/event`

### 用途

录入经营 / 运营事件。

### 成功后要求

- 更新业务事件计数或等价事实
- 更新 `audit_context.last_write_action_*`
- 不覆盖最近控制动作摘要

---

## 6.3 `POST /api/v1/input/manual-note`

### 用途

录入人工备注、说明、复盘摘要。

### 成功后要求

- 更新人工备注存储
- 更新 `audit_context.last_write_action_*`
- 不覆盖最近控制动作摘要

---

## 6.4 `POST /api/v1/input/config-change`

### 用途

受控变更 CFG 字段。

### 通用规则

1. 仅允许白名单路径
2. 仅允许写入 `CFG`
3. 禁止写入 `ACT` / `DRV` / `AUD`
4. 禁止把本接口扩展成通用 patch

### RC2 白名单路径

- `meta.environment`
- `global_runtime.controls.global_execution_mode_switch`
- `global_runtime.controls.global_operator_mode_switch`
- `product_family_status.<pf>.controls.enabled_switch`
- `product_family_status.<pf>.controls.visibility_switch`
- `product_family_status.<pf>.controls.mode_switch`
- `control_plane.demo_control.demo_operator_ack_required`
- `control_plane.risk_envelope.risk_policy_switch`
- `control_plane.risk_envelope.risk_policy_profile`
- `control_plane.action_permissions.<action>.configured_*_switch`

### 明确禁止直写的路径示例

- `control_plane.demo_control.demo_state_switch`
- `control_plane.demo_control.demo_cooldown_state`
- `control_plane.demo_control.demo_cooldown_until_ts_ms`
- `control_plane.risk_envelope.effective_risk_envelope_state`
- 任意 `*_gate_state`
- 任意 `*_reason_codes`
- 任意 `audit_context.*`

### 顶层阻断 `reason_codes`

- `path_not_whitelisted`
- `cfg_field_required`
- `act_field_write_forbidden`
- `drv_field_write_forbidden`
- `aud_field_write_forbidden`
- `immutable_path_forbidden`

---

## 7. 推导规则 RC2

## 7.1 `effective_*_allowed_state` 推导顺序

1. 若对应 `configured_*_switch = false`，则 `disabled`，追加 `configured_switch_disabled`
2. 若产品族 `enabled_switch = false`，则 `disabled`，追加 `product_family_disabled`
3. 若产品族 `visibility_switch = false`，则 `blocked`，追加 `product_family_not_visible`
4. 若产品族 `mode_switch` 不允许该动作，则 `blocked`，追加 `product_family_mode_blocked`
5. 若 `global_execution_mode_switch = disabled`，则 `disabled`，追加 `global_execution_blocked`
6. 若当前为 demo 受控动作，且 `demo_state_switch != demo_enabled`，则 `blocked`，追加 `demo_not_enabled`
7. 若 `effective_risk_envelope_state = blocking`，则 `blocked`，追加 `risk_scope_blocked`
8. 否则为 `allowed`

## 7.2 `demo_enable_gate_state` 推导顺序

1. 若 `demo_state_switch != armed_but_closed`，则 `blocked`，追加 `not_armed`
2. 若 `health_telemetry.gates.health_gates_overall_state = failed`，则 `blocked`，追加 `health_gate_blocked`
3. 若 `effective_risk_envelope_state = blocking`，则 `blocked`，追加 `risk_envelope_blocked`
4. 若 `demo_cooldown_state = active`，则 `blocked`，追加 `cooldown_active`
5. 否则 `passed`

## 7.3 `global_execution_authority_state` 推导顺序

1. 若 `global_execution_mode_switch = disabled`，则 `disabled`
2. 若 `global_execution_mode_switch = demo_reserved` 且 `demo_state_switch != demo_enabled`，则 `demo_blocked`
3. 若 `global_execution_mode_switch = demo_reserved` 且 `demo_state_switch = demo_enabled` 且 `health_gates_overall_state != failed` 且 `effective_risk_envelope_state != blocking`，则 `demo_enabled`
4. 若 `global_execution_mode_switch = live_reserved`，则 `live_blocked`
5. 其他未覆盖情况，返回最保守阻断态

## 7.4 `effective_risk_envelope_state` 推导顺序

1. 读取 `risk_policy_switch`
2. 结合当前健康、仓位、频率、手工阻断、策略级阻断事实
3. 若任何强阻断条件满足，则 `blocking`
4. 若无强阻断，但风险策略已配置，则 `configured`
5. 否则 `reserved`

---

## 8. 状态字典伴随修补清单（RC2 必需）

为了让本版 API 与状态字典完全一致，状态字典必须同步加入以下字段：

### 8.1 `control_plane.risk_envelope`

```json
{
  "risk_policy_switch": "default_guarded",
  "risk_policy_profile": "default",
  "effective_risk_envelope_state": "configured"
}
```

### 8.2 `audit_context`

新增：

- `last_control_action_type`
- `last_control_action_request_id`
- `last_control_action_ts_ms`
- `last_control_action_by`
- `last_control_action_result`
- `last_control_action_reason_codes`
- `last_control_action_audit_ref`

新增：

- `last_write_action_type`
- `last_write_action_request_id`
- `last_write_action_ts_ms`
- `last_write_action_by`
- `last_write_action_result`
- `last_write_action_reason_codes`
- `last_write_action_audit_ref`

### 8.3 枚举补丁

新增 / 固定：

- `rest_private_connection_state`
- `ws_private_connection_state`
- `runtime_connection_state`
- `account_fact_completeness_state`
- `source_snapshot_completeness_state`

---

## 9. GUI 落地约束

1. GUI 所有控制按钮都必须读取：
   - 当前 `snapshot_id`
   - 当前 `state_revision`
   - 当前 `source_context`
2. GUI 提交控制动作时，必须回传：
   - `expected_state_revision`
   - 如适用，`expected_previous_state`
3. GUI 不得缓存高权限令牌到浏览器长久存储。
4. GUI 若发现 `source_snapshot_completeness_state != complete`，必须隐藏或禁用高风险控制按钮。
5. GUI 若发现 `connector_role_separation_ok = false`，必须显式报警。
6. GUI 若 bundle 执行中，应显示“操作进行中”并冻结受影响控制区。
7. GUI 若收到新的 `snapshot_id`，必须以整页 / 整卡片集群方式重绘，不得混刷。

---

## 10. 实现硬约束

- 不允许新增未注册 reason code
- 不允许新增未注册枚举值
- 不允许绕开 `expected_state_revision`
- 不允许绕开 `expected_previous_state`
- 不允许让 `operator_id` 代替真实认证主体
- 不允许让 GUI 直接持有执行层秘密
- 不允许 `config-change` 写入 `ACT` / `DRV` / `AUD`
- 不允许把只读链路和执行链路混成同一合同角色
- 不允许 bundle 暴露中间提交态给 GUI
- 不允许 `validate` 用顶层 `422` 表达 gate 失败
- 不允许学习接口返回漂移 shape
