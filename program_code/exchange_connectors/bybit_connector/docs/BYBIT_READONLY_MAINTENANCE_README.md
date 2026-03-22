# Bybit Readonly / Observer / Business-Event 维护说明

## 1. 文档目的

这份文档用于给未来人工维护者快速说明：

- 这套脚本目前是做什么的
- 各脚本在整条链路里的位置
- 各阶段的输入 / 输出 / 依赖关系
- 哪些状态是“正常但为空”，不能误判为故障
- 后续修改 version / 字段 / 状态时，需要同步哪些文件

当前系统定位：

- **只读观察器（readonly observer）**
- **不允许真实执行**
- **AI 决策仍然关闭**
- **business event 链路已接入状态分类，但尚未看到真实业务事件**
- 当前不是交易执行系统，而是生产级只读观测基础设施

---

## 2. 当前阶段总览

### D21
只读观察器主链路打通并加固：

- private REST readonly checks
- preflight guard
- snapshot
- snapshot -> postgres
- ws smoke
- ws runtime facts
- decision packet
- observer verdict
- acceptance
- runtime state
- final summary
- handoff
- readonly audit

### D22
business-event 侧开始接入：

- D22.1 fixture / smoke 归一化
- D22.2 从 ws jsonl 提取 business messages，并生成 runtime facts
- D22.3 business event state 分类
- D22.4 business event state 接入 runtime / summary / audit
- D22.5 policy / handoff 接入 business-event 含义

---

## 3. 主链路脚本作用说明

### 3.1 基础只读采集

#### bybit_private_account_check.py
作用：
- 拉取账户只读信息
- 输出 account 最新快照原始结果

典型下游：
- bybit_private_rest_preflight_guard.py
- bybit_snapshot_to_postgres.py

---

#### bybit_private_positions_check.py
作用：
- 拉取持仓只读信息
- 当前用于观察 linear 持仓是否存在

典型下游：
- bybit_private_rest_preflight_guard.py
- bybit_snapshot_to_postgres.py

---

#### bybit_private_order_history_check.py
作用：
- 拉取订单历史只读信息
- 当前用于观察是否存在近期订单活动

典型下游：
- bybit_private_rest_preflight_guard.py
- bybit_snapshot_to_postgres.py

---

#### bybit_private_execution_history_check.py
作用：
- 拉取成交历史只读信息
- 当前用于观察近期成交活动
- 一般同时看 spot / linear

典型下游：
- bybit_private_rest_preflight_guard.py
- bybit_snapshot_to_postgres.py

---

### 3.2 REST 安全闸门

#### bybit_private_rest_preflight_guard.py
作用：
- 在后续 snapshot / observer pipeline 运行前，检查 REST 采集结果是否齐全且成功
- 属于只读链路的第一层健康门

主要判断：
- 文件是否存在
- retCode 是否为 0
- 各接口是否 ok

重要说明：
- 这里只是“能否继续 observer pipeline”
- 不代表系统具备交易 readiness

典型下游：
- bybit_full_readonly_observer_cycle.py
- bybit_build_decision_packet.py
- bybit_runtime_state_resolver.py

---

### 3.3 Snapshot 与入库

#### bybit_snapshot_to_postgres.py
作用：
- 将 account / positions / order_history / execution_history 汇总成统一 snapshot
- 生成 latest / dated snapshot 文件
- 提供 payload_time_summary，便于后续 freshness 判断

典型下游：
- bybit_normalize_latest_snapshot_to_postgres.py
- bybit_build_decision_packet.py
- bybit_observer_acceptance_check.py
- bybit_runtime_state_resolver.py
- bybit_readonly_audit.py

---

#### bybit_normalize_latest_snapshot_to_postgres.py
作用：
- 将 snapshot 中的信息规范化写入 Postgres 原始表 / 规范表
- 主要服务于后续查询、审计、历史追踪

---

### 3.4 WebSocket 侧

#### bybit_ws_smoke_to_postgres.py
作用：
- 做一次私有 WS smoke test
- 验证 auth / subscribe / basic connectivity
- 将结果写入 latest / dated 文件，并落 postgres

重要说明：
- smoke test 成功 ≠ 出现业务事件
- 当前常见状态是只有 control-plane 消息，没有 business-topic 消息

---

#### bybit_build_ws_runtime_facts.py
作用：
- 从 persistent listener 状态中提炼运行事实
- 给出 listener_health / connection_state / signal_strength / business_topic_event_count 等状态

关键语义：
- `control_only`：有 auth/subscribe 控制面活动，但没有业务 topic 事件
- `idle_but_connected`：连接仍在，但近期没有新 topic 活动
- 这些状态在当前阶段**可以是健康的**

典型下游：
- bybit_build_decision_packet.py
- bybit_runtime_state_resolver.py
- bybit_failure_policy_builder.py
- bybit_readonly_final_summary.py
- bybit_readonly_audit.py

---

### 3.5 Observer 推理链

#### bybit_build_decision_packet.py
作用：
- 将 snapshot + ws smoke + ws runtime facts + preflight guard 汇总成统一决策输入包
- 当前是 observer-first 设计，不开启 AI 交易决策

典型字段：
- account_summary
- position_summary
- order_summary
- execution_summary
- ws_runtime_summary
- freshness
- risk_flags
- local_decision_hints

重要说明：
- `should_query_ai=false` 是当前策略设计，不是故障

---

#### bybit_decision_packet_to_postgres.py
作用：
- 将 decision packet 落库，供审计和历史检索

---

#### bybit_build_observer_verdict.py
作用：
- 基于 decision packet 生成本地 observer verdict
- 当前标准结论通常是 `OBSERVE_ONLY`

重要说明：
- `OBSERVE_ONLY` 是当前健康状态
- 并不表示系统异常，而是符合 readonly 阶段设计

---

#### bybit_observer_verdict_to_postgres.py
作用：
- 将 observer verdict 落库

---

### 3.6 总控 / 验收 / 状态汇总

#### bybit_full_readonly_observer_cycle.py
作用：
- 将 D21 主链路按顺序串起来执行
- 输出完整 cycle 结果
- 记录每个 stage 的 stdout / stderr / ok / returncode
- guard 阶段额外保留 `parsed_guard`

阶段顺序：
- private_rest x4
- guard x1
- post_guard x4

这个脚本相当于：
- 主流程执行器
- 主健康链路骨架
- 多数最终状态判断的上游来源

---

#### bybit_observer_acceptance_check.py
作用：
- 检查 observer 链路是否满足当前阶段验收标准
- 是“当前 readonly observer 是否通过阶段验收”的核心判断文件之一

重要说明：
- 如果 freshness 超时，会导致 acceptance fail
- 所以它不是“永远稳定为 true”的文件，而是随时间变化

---

#### bybit_runtime_state_resolver.py
作用：
- 汇总 acceptance / packet / verdict / ws facts / preflight / snapshot / business_event_state
- 生成当前统一 runtime state

当前版本：
- 已集成 business event state
- 当前版本应为 `v5`

重要说明：
- runtime_state 会随着 freshness 变化而变成 degraded
- 这通常是因为数据陈旧，不一定是代码坏了

---

#### bybit_failure_policy_builder.py
作用：
- 将系统当前状态映射成 failure / degrade policy
- 说明什么是 hard stop，什么是 degrade
- 属于“策略解释器 / 安全说明书”

当前版本：
- 已集成 business event 解释
- 当前版本应为 `v3`

重要说明：
- `healthy_no_business_events_yet` 是允许的健康空态
- 不能把它当作“业务事件链路坏了”

---

#### bybit_readonly_final_summary.py
作用：
- 生成人工最容易读的最终汇总文件
- 汇总 readiness、freshness、business_event_status、latest_cycle、latest_packet、latest_verdict

当前版本：
- 已集成 business event 状态
- 当前版本应为 `v4`

---

#### bybit_next_phase_handoff.py
作用：
- 生成“下一阶段交接说明”
- 说明当前阶段完成了什么、不能做什么、下一步建议是什么

当前版本：
- 已集成 business event 状态和策略边界
- 当前版本应为 `v3`

---

#### bybit_readonly_audit.py
作用：
- 做跨文件一致性检查
- 检查版本、引用、状态、上下游契约是否匹配
- 属于最终一致性审计器

当前版本：
- 已接入 business event state / runtime / summary / handoff
- 当前版本应为 `v2`

重要说明：
- 修改任何 version / ref 字段后，最容易在这里暴露不一致

---

## 4. Business Event 链路说明

### 4.1 D22.1 基础归一化 / 契约检查

#### bybit_business_event_ingestion_smoke.py
作用：
- 用 fixture 或模拟输入验证 business event 归一化逻辑
- 先证明 event schema 能通

#### bybit_business_event_contract_check.py
作用：
- 检查 D22.1 的输出字段是否符合预期
- 确保 schema、fingerprint、payload 等字段完整

---

### 4.2 D22.2 从 ws jsonl 提取真实 business rows

#### bybit_business_event_extract_from_ws_jsonl.py
作用：
- 从 ws jsonl 中筛出真正的 business-topic 消息
- 将 auth / subscribe / 控制面消息排除

重要说明：
- 现在常见结果是 `business_row_count = 0`
- 在当前阶段这不是错误，只代表 아직没有真实业务消息出现

---

#### bybit_business_event_ingestion_from_ws.py
作用：
- 将 extract 出来的 business rows 归一化为统一 business events
- 输出 from_ws 的 latest / dated 报告

重要说明：
- `normalized_count = 0` 可以是健康状态

---

#### bybit_business_event_runtime_facts.py
作用：
- 对 business events from ws 生成 runtime facts
- 输出 topic_counts / event_type_counts / last_event_ts_ms / has_business_events

---

#### bybit_business_event_runtime_contract_check.py
作用：
- 检查 from_ws ingestion 与 runtime facts 的契约一致性

---

### 4.3 D22.3 business event state

#### bybit_business_event_state_resolver.py
作用：
- 结合 business_event_runtime_facts + ws_runtime_facts
- 把 business event 侧归类成有限状态

当前关键状态：
- `healthy_no_business_events_yet`
- `healthy_business_events_present`
- `stale_or_missing_business_event_feed`

重要说明：
- `healthy_no_business_events_yet` 是“健康空态”
- 表示接入成功，但还没看到真实业务事件

---

#### bybit_business_event_state_contract_check.py
作用：
- 对 business event state 输出做契约检查

---

## 5. 当前状态理解重点

### 5.1 什么叫健康但为空
以下情况在当前阶段是允许且正常的：

- positions = 0
- order_history = 0
- execution_history = 0
- ws signal_strength = control_only
- business_topic_event_count = 0
- business_event_state = healthy_no_business_events_yet

这些都**不是代码故障**。

---

### 5.2 什么情况常导致验收失败
最常见不是代码坏，而是**数据过期**：

- snapshot 超过 freshness 时间窗
- ws_smoke 超时
- ws_runtime_facts 超时
- preflight 超时
- payload_freshness 变 stale

出现这种情况，优先处理方式是：

1. 刷新 full readonly chain
2. 再跑 acceptance / runtime / summary / audit
3. 不要第一反应去改代码

---

## 6. 推荐人工刷新顺序

### 6.1 刷新 D21/D22 主链路
推荐顺序：

1. `bybit_failure_policy_builder.py`
2. `bybit_full_readonly_observer_cycle.py`
3. `bybit_observer_acceptance_check.py`
4. `bybit_runtime_state_resolver.py`
5. `bybit_readonly_final_summary.py`
6. `bybit_next_phase_handoff.py`
7. `bybit_readonly_audit.py`

---

### 6.2 如果 business event 侧也要刷新
补跑：

1. `bybit_business_event_extract_from_ws_jsonl.py`
2. `bybit_business_event_ingestion_from_ws.py`
3. `bybit_business_event_runtime_facts.py`
4. `bybit_business_event_runtime_contract_check.py`
5. `bybit_business_event_state_resolver.py`
6. `bybit_business_event_state_contract_check.py`
7. 再回到 runtime / summary / handoff / audit

---

## 7. 改动时的同步注意事项

### 7.1 改 version 时
如果你改这些文件版本号，通常要同步 audit：

- runtime_state_resolver
- readonly_final_summary
- next_phase_handoff
- failure_policy_builder
- business_event_state_resolver

---

### 7.2 改 ref 字段时
如果改这些引用字段名，通常要同步：

- decision packet
- verdict
- final summary
- audit

例如：
- packet 引 snapshot ts
- verdict 引 packet ts
- summary 引 packet/verdict/business_event_state
- audit 做 cross-check

---

### 7.3 改状态枚举时
如果改这些状态值，需要同步多个文件：

- `overall_runtime_state`
- `business_event_state`
- `observer_state`
- `signal_strength`
- `listener_health`

尤其要同步：

- runtime_state_resolver.py
- failure_policy_builder.py
- readonly_final_summary.py
- next_phase_handoff.py
- readonly_audit.py

---

## 8. 当前版本基线

以当前阶段为准：

- failure policy: v3
- runtime state: v5
- final summary: v4
- handoff: v3
- readonly audit: v2
- business event state: v1

如果后续升级，务必同步 audit 规则。

---

## 9. 后续建议

当前最推荐的下阶段方向仍然是：

1. persistent business-event ingestion model
2. event-driven state updater from WS into runtime facts
3. latest-file consistency auditor / contract checker
4. AI query budget and governance layer
5. model router v2
6. demo/paper execution gate
7. supervised live trading gate

---

## 10. 最后结论

当前系统是：

- **生产级只读观察器**
- **带 business-event 状态分类**
- **不是交易执行系统**
- **不是 AI 自主交易系统**
- **不能把“空业务事件”误判成“系统损坏”**

