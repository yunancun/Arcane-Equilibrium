# OpenClaw / Bybit Control API V1 最终定稿

## 0. 冻结范围

- 文档名：`openclaw_bybit_control_api_v1`
- 适配状态字典：`openclaw_bybit_state_dictionary`
- 适配版本：
  - `document_version = "v1"`
  - `schema_version = "v1"`
  - `api_version = "v1"`
- 基础前缀：`/api/v1`
- 数据格式：`application/json; charset=utf-8`
- 除只读接口外，所有写接口都必须：
  - 写入审计摘要
  - 增加 `state_revision`
  - 返回统一响应 envelope
  - 遵守幂等与并发检查

---

## 1. 统一合同

### 1.1 请求 envelope

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

#### 字段规则

| 字段 | 类型 | 必填 | 规则 |
| --- | --- | --- | --- |
| `request_id` | string | Y | 本次请求唯一标识；写入审计 |
| `idempotency_key` | string | Y | 同一业务动作重试必须保持不变 |
| `operator_id` | string | Y | 操作人或调用主体 |
| `reason` | string | Y | 变更原因；禁止空字符串 |
| `client_ts_ms` | int | Y | 客户端动作时间 |
| `expected_state_revision` | int | Y | 必须等于当前 `meta.state_revision` |
| `expected_previous_state` | string/null | N | 仅状态机动作接口要求 |
| `payload` | object | Y | 动作专属字段 |

### 1.2 响应 envelope

所有 `GET` / `POST` 接口统一返回：

```json
{
  "api_version": "v1",
  "schema_version": "v1",
  "request_id": "string|null",
  "snapshot_ts_ms": 0,
  "state_revision": 0,
  "action_result": "success",
  "reason_codes": [],
  "warnings": [],
  "audit_ref": "string|null",
  "data": {}
}
```

#### 字段规则

| 字段 | 类型 | 必填 | 规则 |
| --- | --- | --- | --- |
| `api_version` | string | Y | 固定 `v1` |
| `schema_version` | string | Y | 固定 `v1` |
| `request_id` | string/null | Y | `GET` 可为 `null`；`POST` 必须回显 |
| `snapshot_ts_ms` | int | Y | 服务端快照时间 |
| `state_revision` | int | Y | 本次响应对应修订号 |
| `action_result` | string | Y | `success` `failed` `blocked` `replayed` |
| `reason_codes` | string[] | Y | 只能使用注册表中的值 |
| `warnings` | string[] | Y | 非阻断提示 |
| `audit_ref` | string/null | Y | 审计引用 ID |
| `data` | object | Y | 接口专属返回体 |

### 1.3 HTTP 状态码合同

| HTTP | 使用场景 |
| --- | --- |
| `200` | `GET` 成功；`POST` 成功；或 `POST` 因幂等重放返回 `replayed` |
| `400` | 请求结构非法、字段缺失、枚举非法、路径非法 |
| `409` | `state_revision_mismatch` / `previous_state_mismatch` / `idempotency_conflict` |
| `422` | 业务阻断；例如 gate 未通过、ack 缺失、cooldown 生效 |
| `500` | 未预期内部错误 |

### 1.4 幂等规则

1. `(request_id, idempotency_key)` 组合必须可追踪。
2. 同一 `idempotency_key`：
   - 若请求体完全一致，允许返回 `action_result = replayed`
   - 若请求体不一致，必须返回 `409 + idempotency_conflict`
3. `replayed` 不得重复推进状态机，不得重复创建业务记录。
4. `replayed` 仍必须返回原始 `audit_ref`。

### 1.5 并发规则

1. 所有写接口必须检查 `expected_state_revision == meta.state_revision`。
2. 所有要求前态的动作接口必须检查 `expected_previous_state`。
3. 任一检查失败：
   - 不得写入任何 canonical 字段
   - 返回 `409`
   - `action_result = failed`
   - `reason_codes` 仅允许对应并发类 code

### 1.6 审计最小写入集

所有成功或失败的 `POST` 接口都必须更新：

- `audit_context.last_operator_action_type`
- `audit_context.last_operator_action_request_id`
- `audit_context.last_operator_action_ts_ms`
- `audit_context.last_operator_action_by`
- `audit_context.last_operator_action_result`
- `audit_context.last_operator_action_reason_codes`

其中：

- 成功动作写 `success`
- 被 gate 阻断写 `blocked`
- 并发/契约失败写 `failed`
- 幂等重放写 `replayed`

---

## 2. 只读接口

### 2.1 `GET /api/v1/system/overview`

#### 用途
GUI 首页只读总览。

#### 响应 `data`

```json
{
  "global_runtime": {},
  "chapter_status_summary": {},
  "daily_business_summary": {},
  "health_summary": {},
  "demo_control_summary": {},
  "latest_audit_summary": {}
}
```

#### 字段来源

- `global_runtime`：来自 `global_runtime.derived`
- `chapter_status_summary`：来自 `chapter_status.*`
- `daily_business_summary`：来自 `business_metrics.daily`
- `health_summary`：来自 `health_telemetry.gates` + 关键 telemetry
- `demo_control_summary`：来自 `control_plane.demo_control`
- `latest_audit_summary`：来自 `audit_context`

---

### 2.2 `GET /api/v1/system/chapter-status`

#### 响应 `data`

```json
{
  "I": {},
  "J": {},
  "K": {}
}
```

直接返回 `chapter_status`。

---

### 2.3 `GET /api/v1/system/control-plane`

#### 响应 `data`

```json
{
  "execution_control_summary": {},
  "demo_control": {},
  "action_permissions": {},
  "health_gate_summary": {},
  "risk_envelope": {}
}
```

直接返回 `control_plane`。

---

### 2.4 `GET /api/v1/system/capability-matrix`

#### 响应 `data`

直接返回 `capability_matrix`。

---

### 2.5 `GET /api/v1/system/product-families`

#### 响应 `data`

直接返回 `product_family_status`。

---

### 2.6 `GET /api/v1/system/business/daily`

#### 响应 `data`

直接返回 `business_metrics.daily`。

---

### 2.7 `GET /api/v1/system/health`

#### 响应 `data`

直接返回 `health_telemetry`。

---

### 2.8 `GET /api/v1/system/audit-summary`

#### 响应 `data`

直接返回 `audit_context`。

---

### 2.9 `GET /api/v1/learning/overview`

#### 响应 `data`

返回 `learning_state.summary` 与 `learning_state.experiments` 的只读聚合视图。  
若实现中未拆 summary 子块，则直接返回 `learning_state`。

---

### 2.10 `GET /api/v1/learning/hypotheses`

#### 响应 `data`

返回学习侧假设、实验、批准要求相关只读视图。  
V1 可直接返回 `learning_state.experiments`。

---

## 3. 控制接口

## 3.1 `POST /api/v1/control/recheck/j-canonical`

### 请求 `payload`

```json
{}
```

### 写入目标

- `capability_matrix.J.canonical_recheck_state`
- `capability_matrix.J.canonical_recheck_last_verified_ts_ms`
- `chapter_status.J.chapter_state`
- `chapter_status.J.current_phase_ready`
- `chapter_status.J.readiness_scope`
- `chapter_status.J.execution_meaning`
- `chapter_status.J.last_verified_ts_ms`
- `chapter_status.J.source_of_truth`

### 成功 `data`

```json
{
  "chapter": "J",
  "recheck_kind": "canonical",
  "canonical_recheck_state": "passed",
  "canonical_recheck_last_verified_ts_ms": 0,
  "chapter_snapshot": {}
}
```

### 失败 / 阻断 reason code

仅允许：

- `state_revision_mismatch`
- `replayed_request`
- `idempotency_conflict`

---

## 3.2 `POST /api/v1/control/recheck/k-canonical`

与 `j-canonical` 相同，目标章节替换为 `K`。

---

## 3.3 `POST /api/v1/control/recheck/j-closeout`

### 请求 `payload`

```json
{}
```

### 写入目标

- `capability_matrix.J.closeout_state`
- `capability_matrix.J.closeout_last_verified_ts_ms`
- `chapter_status.J.chapter_state`
- `chapter_status.J.current_phase_ready`
- `chapter_status.J.readiness_scope`
- `chapter_status.J.execution_meaning`
- `chapter_status.J.last_verified_ts_ms`
- `chapter_status.J.source_of_truth`

### 成功 `data`

```json
{
  "chapter": "J",
  "recheck_kind": "closeout",
  "closeout_state": "passed",
  "closeout_last_verified_ts_ms": 0,
  "chapter_snapshot": {}
}
```

### 失败 / 阻断 reason code

仅允许：

- `state_revision_mismatch`
- `replayed_request`
- `idempotency_conflict`

---

## 3.4 `POST /api/v1/control/recheck/k-closeout`

与 `j-closeout` 相同，目标章节替换为 `K`。

---

## 3.5 `POST /api/v1/control/demo/validate`

### 请求 `payload`

```json
{}
```

### 必查条件

- `expected_state_revision`
- 若提供 `expected_previous_state`，必须等于当前 `control_plane.demo_control.demo_state_switch`

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
  "demo_relock_reason_codes": []
}
```

### 合法 `action_result`

- `success`
- `failed`
- `replayed`

### 失败 / 阻断 reason code

仅允许：

- `state_revision_mismatch`
- `previous_state_mismatch`
- `replayed_request`
- `idempotency_conflict`

---

## 3.6 `POST /api/v1/control/demo/arm`

### 请求 `payload`

```json
{}
```

### 必填前态

`expected_previous_state` 必填，合法值仅允许：

- `closed`
- `relocked`

### 进入条件

- `control_plane.demo_control.demo_prerequisites_gate_state = passed`
- `global_runtime.controls.global_execution_mode_switch = demo_reserved`

### 成功后必写

- `control_plane.demo_control.demo_state_switch = armed_but_closed`
- `control_plane.demo_control.demo_last_action_type = arm`
- `control_plane.demo_control.demo_last_action_result = success`
- `control_plane.demo_control.demo_last_action_reason_codes = []`
- `control_plane.demo_control.demo_last_action_ts_ms = client_ts_ms`

### 成功 `data`

```json
{
  "previous_demo_state_switch": "closed",
  "demo_state_switch": "armed_but_closed"
}
```

### 失败 / 阻断 reason code

仅允许：

- `previous_state_mismatch`
- `prerequisites_not_passed`
- `execution_mode_disabled`
- `live_mode_reserved_only`
- `state_revision_mismatch`
- `replayed_request`
- `idempotency_conflict`

---

## 3.7 `POST /api/v1/control/demo/enable`

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

- `control_plane.demo_control.demo_enable_gate_state = passed`
- `control_plane.demo_control.demo_operator_ack_required = false`，或 `payload.acknowledged = true`
- `control_plane.demo_control.demo_cooldown_state != active`

### 成功后必写

- `control_plane.demo_control.demo_state_switch = demo_enabled`
- `control_plane.demo_control.demo_operator_ack_completed = true`
- `control_plane.demo_control.demo_last_action_type = enable`
- `control_plane.demo_control.demo_last_action_result = success`
- `control_plane.demo_control.demo_last_action_reason_codes = []`
- `control_plane.demo_control.demo_last_action_ts_ms = client_ts_ms`

### 成功 `data`

```json
{
  "previous_demo_state_switch": "armed_but_closed",
  "demo_state_switch": "demo_enabled",
  "demo_operator_ack_completed": true
}
```

### 失败 / 阻断 reason code

仅允许：

- `previous_state_mismatch`
- `not_armed`
- `operator_ack_required`
- `cooldown_active`
- `health_gate_blocked`
- `risk_envelope_blocked`
- `state_revision_mismatch`
- `replayed_request`
- `idempotency_conflict`

---

## 3.8 `POST /api/v1/control/demo/relock`

### 请求 `payload`

```json
{}
```

### 必填前态

`expected_previous_state` 必填，合法值仅允许：

- `armed_but_closed`
- `demo_enabled`
- `relocked`

### 成功后必写

- `control_plane.demo_control.demo_state_switch = relocked`
- `control_plane.demo_control.demo_cooldown_state = active`
- `control_plane.demo_control.demo_cooldown_until_ts_ms = client_ts_ms + cooldown_policy_ms`
- `control_plane.demo_control.demo_last_action_type = relock`
- `control_plane.demo_control.demo_last_action_result = success`
- `control_plane.demo_control.demo_last_action_reason_codes = []`
- `control_plane.demo_control.demo_last_action_ts_ms = client_ts_ms`

### 成功 `data`

```json
{
  "previous_demo_state_switch": "demo_enabled",
  "demo_state_switch": "relocked",
  "demo_cooldown_state": "active",
  "demo_cooldown_until_ts_ms": 0
}
```

### 失败 / 阻断 reason code

仅允许：

- `previous_state_mismatch`
- `state_revision_mismatch`
- `replayed_request`
- `idempotency_conflict`

---

## 3.9 `POST /api/v1/control/safe-recheck-bundle`

### 请求 `payload`

```json
{}
```

### 固定执行顺序

V1 固定按以下顺序执行，不接受自定义章节选择：

1. `j-canonical`
2. `k-canonical`
3. `j-closeout`
4. `k-closeout`
5. `demo-validate`

### 原子性规则

- V1 不要求全局事务回滚
- 但必须返回逐步骤结果
- 后续步骤是否继续，取决于实现策略；V1 推荐：
  - 若并发契约失败，立即终止
  - 若业务结果为 `failed` 或 `blocked`，仍可继续后续只读/验证型步骤
- 响应中必须明确每一步状态

### 成功 `data`

```json
{
  "steps": [
    {
      "step_name": "j-canonical",
      "action_result": "success",
      "reason_codes": []
    },
    {
      "step_name": "k-canonical",
      "action_result": "success",
      "reason_codes": []
    },
    {
      "step_name": "j-closeout",
      "action_result": "success",
      "reason_codes": []
    },
    {
      "step_name": "k-closeout",
      "action_result": "success",
      "reason_codes": []
    },
    {
      "step_name": "demo-validate",
      "action_result": "success",
      "reason_codes": []
    }
  ]
}
```

### 失败 / 阻断 reason code

仅允许逐步骤返回各自注册表内值；顶层可附加：

- `state_revision_mismatch`
- `replayed_request`
- `idempotency_conflict`

---

## 4. 输入接口

## 4.1 `POST /api/v1/input/cost`

### 用途

登记人工成本/运营成本输入，用于更新 `business_metrics.daily` 及其来源计数。

### 请求 `payload`

```json
{
  "occurred_ts_ms": 0,
  "amount": 0,
  "currency": "USDT",
  "cost_category": "exchange_fee",
  "source_ref": "string|null",
  "note": "string|null"
}
```

### 字段规则

| 字段 | 类型 | 必填 | 规则 |
| --- | --- | --- | --- |
| `occurred_ts_ms` | int | Y | 成本发生时间 |
| `amount` | number | Y | 成本金额；必须 `>= 0` |
| `currency` | string | Y | 报表币种或原始币种 |
| `cost_category` | string | Y | V1 由实现侧白名单约束 |
| `source_ref` | string/null | N | 外部凭证/记录引用 |
| `note` | string/null | N | 备注 |

### 成功后必写

- `business_metrics.daily.total_cost`
- `business_metrics.daily.net_operating_pnl`
- `business_metrics.daily.manual_cost_included`
- `business_metrics.daily.manual_cost_source_count`

### 成功 `data`

```json
{
  "cost_record_accepted": true,
  "business_daily_snapshot": {}
}
```

### reason code

仅允许：

- `state_revision_mismatch`
- `replayed_request`
- `idempotency_conflict`

---

## 4.2 `POST /api/v1/input/event`

### 用途

登记业务/系统事件。

### 请求 `payload`

```json
{
  "event_ts_ms": 0,
  "event_type": "string",
  "event_scope": "system",
  "severity": "info",
  "message": "string",
  "related_ref": "string|null",
  "tags": []
}
```

### 字段规则

| 字段 | 类型 | 必填 | 规则 |
| --- | --- | --- | --- |
| `event_ts_ms` | int | Y | 事件时间 |
| `event_type` | string | Y | 事件类型 |
| `event_scope` | string | Y | 例如 `system` `trading` `learning` `operator` |
| `severity` | string | Y | 建议白名单：`info` `warn` `error` |
| `message` | string | Y | 简述 |
| `related_ref` | string/null | N | 关联对象 |
| `tags` | string[] | Y | 标签列表 |

### 成功后必写

- `business_metrics.daily.business_event_count` 或等价事件计数
- `audit_context` 最近动作摘要

### 成功 `data`

```json
{
  "event_record_accepted": true
}
```

### reason code

仅允许：

- `state_revision_mismatch`
- `replayed_request`
- `idempotency_conflict`

---

## 4.3 `POST /api/v1/input/manual-note`

### 用途

写入人工备注，用于审计和后续复盘。

### 请求 `payload`

```json
{
  "note_ts_ms": 0,
  "note_scope": "operator",
  "title": "string",
  "body": "string",
  "related_ref": "string|null"
}
```

### 字段规则

| 字段 | 类型 | 必填 | 规则 |
| --- | --- | --- | --- |
| `note_ts_ms` | int | Y | 备注时间 |
| `note_scope` | string | Y | 备注范围 |
| `title` | string | Y | 标题 |
| `body` | string | Y | 正文 |
| `related_ref` | string/null | N | 关联对象 |

### 成功 `data`

```json
{
  "manual_note_accepted": true
}
```

### reason code

仅允许：

- `state_revision_mismatch`
- `replayed_request`
- `idempotency_conflict`

---

## 4.4 `POST /api/v1/input/config-change`

### 用途

唯一通用配置写入口。  
禁止用于写任何 `ACT` / `DRV` / `AUD` 字段。

### 请求 `payload`

```json
{
  "target_path": "string",
  "new_value": null,
  "expected_current_value": null
}
```

### 字段规则

| 字段 | 类型 | 必填 | 规则 |
| --- | --- | --- | --- |
| `target_path` | string | Y | 只允许白名单路径 |
| `new_value` | any | Y | 必须与目标字段类型匹配 |
| `expected_current_value` | any | N | 若提供则必须与当前值完全一致 |

### 允许写入路径白名单

- `meta.environment`
- `global_runtime.controls.global_execution_mode_switch`
- `global_runtime.controls.global_operator_mode_switch`
- `product_family_status.<pf>.controls.enabled_switch`
- `product_family_status.<pf>.controls.visibility_switch`
- `product_family_status.<pf>.controls.mode_switch`
- `control_plane.action_permissions.global.configured_*_switch`
- `control_plane.action_permissions.by_product_family.<pf>.configured_*_switch`
- `control_plane.risk_envelope.risk_envelope_state`
- `control_plane.risk_envelope.max_notional_limit`
- `control_plane.risk_envelope.max_order_count_limit`
- `control_plane.risk_envelope.allowed_symbol_scope`
- `control_plane.demo_control.demo_operator_ack_required`
- `learning_state.experiments.approval_required`

### 路径展开规则

- `<pf>` 仅允许：
  - `spot`
  - `margin`
  - `perp_linear`
  - `perp_inverse`
  - `options`
  - `other_derivatives_reserved`
- `configured_*_switch` 仅允许：
  - `configured_new_order_allowed_switch`
  - `configured_cancel_allowed_switch`
  - `configured_amend_allowed_switch`
  - `configured_reduce_only_allowed_switch`
  - `configured_increase_position_allowed_switch`
  - `configured_close_position_allowed_switch`

### 拒绝条件

任一命中即拒绝：

- 目标路径不在白名单
- 目标字段类型不匹配
- 目标字段为 `ACT` / `DRV` / `AUD`
- 提供了 `expected_current_value` 且不匹配当前值
- 枚举值不在注册表中

### 成功 `data`

```json
{
  "target_path": "global_runtime.controls.global_execution_mode_switch",
  "old_value": "disabled",
  "new_value": "demo_reserved"
}
```

### reason code

仅允许：

- `state_revision_mismatch`
- `idempotency_conflict`
- `replayed_request`

---

## 5. reason code 最终注册表

## 5.1 并发 / 幂等

- `state_revision_mismatch`
- `previous_state_mismatch`
- `replayed_request`
- `idempotency_conflict`

## 5.2 demo validate / arm / enable / relock

- `prerequisites_not_passed`
- `not_armed`
- `not_enabled`
- `operator_ack_required`
- `cooldown_active`
- `health_gate_blocked`
- `risk_envelope_blocked`
- `execution_mode_disabled`
- `live_mode_reserved_only`

## 5.3 权限生效阻断

- `configured_switch_disabled`
- `product_family_disabled`
- `product_family_not_visible`
- `product_family_mode_blocked`
- `global_execution_blocked`
- `demo_not_enabled`
- `risk_scope_blocked`

## 5.4 数据 / 健康

- `runtime_stale`
- `latency_exceeded`
- `exchange_timeout_exceeded`
- `ws_disconnect_exceeded`

## 5.5 接口契约补充

- `invalid_payload`
- `invalid_target_path`
- `invalid_enum_value`
- `type_mismatch`
- `expected_current_value_mismatch`

---

## 6. 推导与回写硬约束

### 6.1 直接写入禁止

以下字段只能由内部计算/动作处理器写入，任何外部接口不得直写：

- `control_plane.demo_control.demo_state_switch`
- `control_plane.demo_control.demo_validate_requested`
- `control_plane.demo_control.demo_operator_ack_completed`
- `control_plane.demo_control.demo_*_gate_state`
- `control_plane.demo_control.demo_*_reason_codes`
- `control_plane.demo_control.demo_*_last_evaluated_ts_ms`
- `control_plane.demo_control.demo_last_action_*`
- `control_plane.demo_control.demo_cooldown_state`
- `control_plane.demo_control.demo_cooldown_until_ts_ms`
- 所有 `effective_*_allowed_state`
- 所有 `effective_*_reason_codes`
- 所有 `*_summary`
- 所有 `audit_context.*`

### 6.2 `effective_*_allowed_state` 推导规则

对任一动作权限，按以下顺序判断：

1. 若对应 `configured_*_switch = false`，则 `disabled`，追加 `configured_switch_disabled`
2. 若产品族 `enabled_switch = false`，则 `disabled`，追加 `product_family_disabled`
3. 若产品族 `visibility_switch = false`，则 `blocked`，追加 `product_family_not_visible`
4. 若产品族 `mode_switch` 不允许该动作，则 `blocked`，追加 `product_family_mode_blocked`
5. 若 `global_runtime.controls.global_execution_mode_switch = disabled`，则 `disabled`，追加 `global_execution_blocked`
6. 若当前为 demo 受控动作，且 `demo_state_switch != demo_enabled`，则 `blocked`，追加 `demo_not_enabled`
7. 若 `control_plane.risk_envelope.risk_envelope_state = blocking`，则 `blocked`，追加 `risk_scope_blocked`
8. 否则为 `allowed`

### 6.3 `demo_enable_gate_state` 推导规则

按以下顺序判断：

1. 若 `demo_state_switch != armed_but_closed`，则 `blocked`，追加 `not_armed`
2. 若 `health_telemetry.gates.health_gates_overall_state = failed`，则 `blocked`，追加 `health_gate_blocked`
3. 若 `control_plane.risk_envelope.risk_envelope_state = blocking`，则 `blocked`，追加 `risk_envelope_blocked`
4. 若 `demo_cooldown_state = active`，则 `blocked`，追加 `cooldown_active`
5. 否则 `passed`

### 6.4 `global_execution_authority_state` 推导规则

1. 若 `global_execution_mode_switch = disabled`，则 `disabled`
2. 若 `global_execution_mode_switch = demo_reserved` 且 `demo_state_switch != demo_enabled`，则 `demo_blocked`
3. 若 `global_execution_mode_switch = demo_reserved` 且 `demo_state_switch = demo_enabled` 且 `health_telemetry.gates.health_gates_overall_state != failed` 且 `risk_envelope_state != blocking`，则 `demo_enabled`
4. 若 `global_execution_mode_switch = live_reserved`，则 `live_blocked`
5. 其他未覆盖情况，返回最保守阻断态

---

## 7. V1 实现硬约束

- 不允许新增未注册 reason code
- 不允许新增未注册枚举值
- 不允许把 `config-change` 扩展成通用 patch
- 不允许绕开 `expected_state_revision`
- 不允许绕开 `expected_previous_state`
- 不允许通过任何接口直接写 `ACT` / `DRV` / `AUD`
- 不允许 `GET` 接口返回与状态字典路径不一致的字段名
- 所有 `POST` 接口返回体都必须带最新 `state_revision`
- 所有 `POST` 接口都必须写入审计摘要
- `safe-recheck-bundle` 仅是编排接口，不得引入新的独立状态机
