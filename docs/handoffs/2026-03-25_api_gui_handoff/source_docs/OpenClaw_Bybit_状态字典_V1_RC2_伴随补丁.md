# OpenClaw / Bybit 状态字典 V1 RC2 伴随补丁

## 0. 目的

本补丁用于让《OpenClaw / Bybit 状态字典 / 数据字典 V1 最终版》与《OpenClaw / Bybit Control API V1 RC2 最终候选版》完全对齐。

本文件只给出需要补入或替换的字段，不重写整份字典。

---

## 1. `control_plane.risk_envelope` 补丁

### 1.1 替换合同结构

```json
{
  "risk_policy_switch": "default_guarded",
  "risk_policy_profile": "default",
  "effective_risk_envelope_state": "configured"
}
```

### 1.2 字段表

| 路径 | 类型 | 必填 | Canonical | 写入 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `control_plane.risk_envelope.risk_policy_switch` | string | Y | Y | CFG | 风险策略配置开关 |
| `control_plane.risk_envelope.risk_policy_profile` | string | Y | Y | CFG | 风险配置档位 |
| `control_plane.risk_envelope.effective_risk_envelope_state` | string | Y | Y | DRV | 风险生效态；禁止直写 |

### 1.3 新枚举

| 字段 | 合法值 |
| --- | --- |
| `risk_policy_switch` | `default_guarded` `manual_blocked` `reserved` |
| `effective_risk_envelope_state` | `reserved` `configured` `blocking` |

---

## 2. `audit_context` 补丁

### 2.1 新增控制动作摘要

```json
{
  "last_control_action_type": null,
  "last_control_action_request_id": null,
  "last_control_action_ts_ms": null,
  "last_control_action_by": null,
  "last_control_action_result": null,
  "last_control_action_reason_codes": [],
  "last_control_action_audit_ref": null
}
```

### 2.2 新增写动作摘要

```json
{
  "last_write_action_type": null,
  "last_write_action_request_id": null,
  "last_write_action_ts_ms": null,
  "last_write_action_by": null,
  "last_write_action_result": null,
  "last_write_action_reason_codes": [],
  "last_write_action_audit_ref": null
}
```

### 2.3 字段表

| 路径 | 类型 | 必填 | Canonical | 写入 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `audit_context.last_control_action_type` | string/null | Y | Y | AUD | 最近控制动作类型 |
| `audit_context.last_control_action_request_id` | string/null | Y | Y | AUD | 最近控制动作请求 ID |
| `audit_context.last_control_action_ts_ms` | int/null | Y | Y | AUD | 最近控制动作时间 |
| `audit_context.last_control_action_by` | string/null | Y | Y | AUD | 最近控制动作操作者 |
| `audit_context.last_control_action_result` | string/null | Y | Y | AUD | 最近控制动作结果 |
| `audit_context.last_control_action_reason_codes` | string[] | Y | Y | AUD | 最近控制动作原因码 |
| `audit_context.last_control_action_audit_ref` | string/null | Y | Y | AUD | 最近控制动作审计引用 |
| `audit_context.last_write_action_type` | string/null | Y | Y | AUD | 最近任意写动作类型 |
| `audit_context.last_write_action_request_id` | string/null | Y | Y | AUD | 最近任意写动作请求 ID |
| `audit_context.last_write_action_ts_ms` | int/null | Y | Y | AUD | 最近任意写动作时间 |
| `audit_context.last_write_action_by` | string/null | Y | Y | AUD | 最近任意写动作操作者 |
| `audit_context.last_write_action_result` | string/null | Y | Y | AUD | 最近任意写动作结果 |
| `audit_context.last_write_action_reason_codes` | string[] | Y | Y | AUD | 最近任意写动作原因码 |
| `audit_context.last_write_action_audit_ref` | string/null | Y | Y | AUD | 最近任意写动作审计引用 |

---

## 3. 连接与来源枚举补丁

### 3.1 新增枚举

| 字段 | 合法值 |
| --- | --- |
| `rest_private_connection_state` | `ready` `degraded` `down` `unknown` |
| `ws_private_connection_state` | `ready` `degraded` `down` `unknown` |
| `runtime_connection_state` | `healthy` `degraded` `down` `unknown` |
| `account_fact_completeness_state` | `complete` `partial` `missing` `unknown` |
| `source_snapshot_completeness_state` | `complete` `partial` `missing` `unknown` |

### 3.2 建议承载位置

建议这些字段通过 API `source_context` 暴露，同时在运行时状态编译器内部保留同名中间事实结构；
状态字典 V1 主体不新增第 11 个顶层块，不改变冻结顶层结构。

---

## 4. `control_plane.action_permissions` 补丁

### 4.1 明确分层

必须维持以下分离：

- `configured_*_switch`：CFG，配置意图
- `effective_*_allowed_state`：DRV，实际生效结果

### 4.2 禁止项补充

以下字段禁止 `config-change` 直写：

- 任意 `effective_*_allowed_state`
- 任意 `*_reason_codes` 派生集合
- 任意与 demo 动作处理器绑定的 `ACT` 字段

---

## 5. `meta` 与 API envelope 对齐说明

状态字典仍保持：

- `meta.snapshot_ts_ms`
- `meta.state_revision`

API envelope 额外返回：

- `snapshot_id`
- `request_id`
- `audit_ref`
- `source_context`

这些字段属于 API 响应上下文，不要求写回状态字典根对象。

---

## 6. 推导规则补丁

### 6.1 `effective_risk_envelope_state`

固定顺序：

1. 读取 `risk_policy_switch`
2. 读取健康阻断事实
3. 读取仓位 / 频率 / 人工阻断事实
4. 任一强阻断 -> `blocking`
5. 若无强阻断且风险策略已配置 -> `configured`
6. 否则 -> `reserved`

### 6.2 `global_execution_authority_state`

固定顺序：

1. 读取 `global_execution_mode_switch`
2. 读取 `demo_state_switch`
3. 读取 `demo_enable_gate_state`
4. 读取 `source_context.connector_role_separation_ok`
5. 读取 `source_context.runtime_connection_state`
6. 按 RC2 合同输出 `disabled / demo_blocked / demo_guarded / demo_enabled / live_blocked / live_guarded / live_enabled`

---

## 7. `config-change` 白名单补丁

### 7.1 允许写入

- `meta.environment`
- `global_runtime.controls.global_execution_mode_switch`
- `global_runtime.controls.global_operator_mode_switch`
- `control_plane.risk_envelope.risk_policy_switch`
- `control_plane.risk_envelope.risk_policy_profile`
- `control_plane.action_permissions.<pf>.configured_*_switch`
- `product_family_status.<pf>.mode_switch`

### 7.2 明确禁止直写

- `control_plane.demo_control.*`
- 任意 `ACT`
- 任意 `AUD`
- 任意 `DRV`
- 任意 `effective_*_allowed_state`
- `global_execution_authority_state`
- `effective_risk_envelope_state`

---

## 8. GUI 兼容要求

- GUI 首页优先使用 API envelope 的 `snapshot_id` 判断一致性
- GUI 不得尝试从状态字典根对象中寻找 `snapshot_id`
- GUI 最近操作卡片应优先显示 `last_control_action_*`；必要时再显示 `last_write_action_*`
