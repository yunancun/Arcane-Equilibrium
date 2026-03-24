> **Canonical path note / 规范路径说明**  
> Business-events real implementations now live under:  
> `program_code/market_data_processor/bybit_business_events/`  
> Legacy entry files remain under:  
> `program_code/exchange_connectors/bybit_connector/scripts/`  
> as compatibility wrappers during migration.

# Bybit Connector Script Index

## Important Chapter Note

本索引文档在持续维护中，后续章节归位应以 **Revision 2 正式章节树** 为准。

特别说明：
- G = 真实业务事件验证层
- J = Transition Engine Skeleton
- K = Paper / Demo Gate

历史上部分脚本在开发过程中曾使用过临时编号（例如 G4.x、G5、G6），  
这些临时编号现已废弃，不能再视为正式章节。

请同时参考：
- `docs/REVISION2_CHAPTER_REALIGNMENT_NOTE.md`

## Scope
本文档用于人工维护 `exchange_connectors/bybit_connector` 下的多阶段脚本与相关说明。

当前维护口径：
- 早期工程记录中，很多脚本是按 D 线（例如 D21 / D22 / D23）逐步推进的
- 但后续正式归位与章节理解，应以 **Revision 2 正式章节树** 为准
- 因此阅读本索引时，不应再把旧的临时编号或旧的 D 线阶段名，直接等同于当前正式章节

目标：
- 让维护者快速知道每个脚本的职责
- 明确上下游依赖
- 明确 latest 文件产物
- 明确脚本所属的正式章节语境
- 减少未来人工修改时误伤主链路或误解章节位置

---

## Reading Rule For Maintainers

阅读本索引时，请优先遵守以下口径：

1. **正式章节优先**
   - G = 真实业务事件验证层
   - J = Transition Engine Skeleton
   - K = Paper / Demo Gate

2. **旧编号只做历史参考**
   - 开发过程中曾出现过 G4.x、G5、G6 等临时编号
   - 这些编号已经废弃，不能再当成正式章节

3. **D 线记录是历史推进顺序，不是当前唯一章节依据**
   - D21 / D22 / D23 等记录对理解历史很有帮助
   - 但当前正式归位必须以 Revision 2 正式章节树和 `REVISION2_CHAPTER_REALIGNMENT_NOTE.md` 为准

4. **注释、索引、工程记录三者冲突时**
   - 先看正式章节说明文档
   - 再看脚本头注释
   - 最后再回看旧工程日志中的历史编号

---

# 一、主链路总览

## D21 readonly observer hardened
主目标：
- 完成只读观察链路
- 建立 snapshot / ws / packet / verdict / acceptance / runtime / summary / audit 闭环
- 严格保证 `system_mode = read_only`

核心主链路：

1. `bybit_private_account_check.py`
2. `bybit_private_positions_check.py`
3. `bybit_private_order_history_check.py`
4. `bybit_private_execution_history_check.py`
5. `bybit_private_rest_preflight_guard.py`
6. `bybit_snapshot_to_postgres.py`
7. `bybit_normalize_latest_snapshot_to_postgres.py`
8. `bybit_ws_smoke_to_postgres.py`
9. `bybit_observer_pipeline.py`
10. `bybit_observer_acceptance_check.py`
11. `bybit_runtime_state_resolver.py`
12. `bybit_readonly_final_summary.py`
13. `bybit_next_phase_handoff.py`
14. `bybit_readonly_audit.py`

---

## D22 business-event integration
主目标：
- 引入 business-event 抽取 / 归一化 / 运行态判断
- 明确“健康但暂无业务事件”和“业务事件链路失效”之间的区别
- 将 business event state 接入 runtime / policy / summary / handoff / audit

核心链路：

1. `bybit_business_event_ingestion_smoke.py`
2. `bybit_business_event_contract_check.py`
3. `bybit_business_event_extract_from_ws_jsonl.py`
4. `bybit_business_event_ingestion_from_ws.py`
5. `bybit_business_event_runtime_facts.py`
6. `bybit_business_event_runtime_contract_check.py`
7. `bybit_business_event_state_resolver.py`
8. `bybit_business_event_state_contract_check.py`

---

# 二、D21 脚本说明

## 1. _bybit_latest_wrapper.py
**作用**
- 提供 latest / dated 输出写入的通用辅助能力

**系统角色**
- 不是业务判断脚本
- 是多个脚本稳定写 `latest.json` / `dated.json` 的基础能力层

**维护注意**
- 不应在这里加入业务逻辑
- 这里只做通用写文件封装更安全

---

## 2. bybit_private_account_check.py
**作用**
- 读取 Bybit 私有账户只读信息
- 输出 account latest 检查结果

**上游**
- API 凭据 / Bybit 私有 REST

**下游**
- `bybit_private_rest_preflight_guard.py`
- `bybit_snapshot_to_postgres.py`
- `bybit_full_readonly_observer_cycle.py`

**关键产物**
- account latest json

**维护注意**
- 必须保持 read_only 语义
- 不得引入任何下单相关逻辑

---

## 3. bybit_private_positions_check.py
**作用**
- 读取 positions
- 输出只读检查结果

**下游**
- guard / snapshot / observer cycle

---

## 4. bybit_private_order_history_check.py
**作用**
- 读取 order history
- 输出只读检查结果

**下游**
- guard / snapshot / observer cycle

---

## 5. bybit_private_execution_history_check.py
**作用**
- 读取 execution history（spot / linear）
- 输出执行历史快照

**下游**
- guard / snapshot / observer cycle

---

## 6. bybit_private_rest_preflight_guard.py
**作用**
- 对 account / positions / order_history / execution_history 进行继续执行前校验
- 决定 downstream 是否允许继续

**下游**
- `bybit_full_readonly_observer_cycle.py`
- `bybit_runtime_state_resolver.py`
- `bybit_failure_policy_builder.py`

**关键字段**
- `allowed_to_continue`
- `failed_count`
- `checks`

**维护注意**
- guard 的输出结构不能随便改
- cycle 对 guard stdout 的解析非常敏感

---

## 7. bybit_snapshot_to_postgres.py
**作用**
- 汇总 private REST latest 文件
- 形成统一 snapshot
- 落 latest / dated，并写入 Postgres 原始快照

**关键产物**
- `bybit_system_snapshot_latest.json`

**维护注意**
- `payload_time_summary` 很关键
- audit / acceptance / runtime 都依赖 freshness 判断

---

## 8. bybit_normalize_latest_snapshot_to_postgres.py
**作用**
- 把 snapshot 进一步拆表、归一化入库

**定位**
- 原始 snapshot 之后的结构化落库步骤

---

## 9. bybit_ws_smoke_to_postgres.py
**作用**
- 做一次私有 WS smoke test
- 验证 auth / subscribe 最基本链路正常
- 将原始事件写入 Postgres

**维护注意**
- smoke test 不是 persistent listener
- 不能把 smoke 成功误判为业务事件已就绪

---

## 10. bybit_build_ws_runtime_facts.py
**作用**
- 从 persistent ws listener 状态推导运行时事实
- 给 observer verdict / runtime / summary 提供 ws 健康信息

**关键字段**
- `listener_health`
- `connection_state`
- `signal_strength`
- `business_topic_event_count`

---

## 11. bybit_build_decision_packet.py
**作用**
- 把 snapshot + ws runtime + preflight 汇总为 packet
- 供 verdict 层消费

**维护注意**
- 当前仍是 observer-first
- `should_query_ai` 目前应保持 false

---

## 12. bybit_decision_packet_to_postgres.py
**作用**
- packet 落库

---

## 13. bybit_build_observer_verdict.py
**作用**
- 基于 packet 生成 observer verdict
- 明确系统当前只能 `OBSERVE_ONLY`

**关键字段**
- `verdict_code`
- `execution_allowed`
- `should_query_ai`
- `urgency`

---

## 14. bybit_observer_verdict_to_postgres.py
**作用**
- verdict 落库

---

## 15. bybit_full_readonly_observer_cycle.py
**作用**
- 串行执行 D21 readonly observer 主链路
- 保留每步 stage 结果
- 输出 cycle latest

**阶段结构**
- private_rest x4
- guard x1
- post_guard x4

**关键字段**
- `overall_ok`
- `steps`
- guard step 内的 `parsed_guard`

**维护注意**
- 这是骨架脚本之一
- 改 stdout 解析时要非常谨慎

---

## 16. bybit_observer_acceptance_check.py
**作用**
- 对当前 observer 结果做验收
- 判断本轮 readonly observer 是否通过

**维护注意**
- freshness 失败不一定是代码坏了，有可能只是太久没刷新

---

## 17. bybit_runtime_state_resolver.py
**作用**
- 汇总 acceptance / packet / verdict / ws / preflight / snapshot / business_event_state
- 输出统一 runtime state

**当前版本**
- v5

**维护注意**
- 状态枚举改动必须同步 summary / policy / audit / handoff

---

## 18. bybit_failure_policy_builder.py
**作用**
- 构建系统的 hard stop / degrade policy
- 对 runtime / acceptance / packet / verdict / business_event_state 做策略解释

**当前版本**
- v3

**维护注意**
- “healthy empty business-event feed” 不能误判成故障
- 也不能误判成已经具备 event-driven trading readiness

---

## 19. bybit_readonly_final_summary.py
**作用**
- 生成最终阶段摘要
- 供人工查看当前系统状态

**当前版本**
- v4

---

## 20. bybit_next_phase_handoff.py
**作用**
- 给下一阶段开发做交接
- 说明当前完成度、边界、限制和下一步顺序

**当前版本**
- v3

---

## 21. bybit_readonly_audit.py
**作用**
- 做全链路一致性审计
- 重点检查版本、引用关系、freshness、business event state 一致性

**当前版本**
- v2

**维护注意**
- 非常适合在每次改完脚本后最后执行
- 属于当前人工维护最重要的“收口脚本”之一

---

# 三、D22 脚本说明

## 22. bybit_business_event_ingestion_smoke.py
**作用**
- 用 fixture / smoke 数据验证 business-event 归一化链路最小可用

---

## 23. bybit_business_event_contract_check.py
**作用**
- 检查 smoke 输出结构是否符合约定

---

## 24. bybit_business_event_extract_from_ws_jsonl.py
**作用**
- 从 ws jsonl 中抽取 business-topic 消息

**维护注意**
- 当前如果 WS 中没有真实业务消息，`business_row_count = 0` 是正常现象

---

## 25. bybit_business_event_ingestion_from_ws.py
**作用**
- 将抽取出的 WS business messages 归一化为 business events

---

## 26. bybit_business_event_runtime_facts.py
**作用**
- 汇总 business events，形成运行时 facts

**关键字段**
- `normalized_count`
- `topic_counts`
- `event_type_counts`
- `has_business_events`

---

## 27. bybit_business_event_runtime_contract_check.py
**作用**
- 校验 business event runtime facts 结构正确

---

## 28. bybit_business_event_state_resolver.py
**作用**
- 把 business event runtime facts 和 ws runtime facts 结合
- 输出 business-event 健康状态分类

**关键状态**
- `healthy_no_business_events_yet`
- `healthy_business_events_present`
- `stale_or_missing_business_event_feed`

**维护注意**
- `healthy_no_business_events_yet` 是关键“健康空态”
- 不能误判为坏，也不能当成 active trading ready

---

## 29. bybit_business_event_state_contract_check.py
**作用**
- 对 business event state 输出做合同校验


## 30. bybit_latest_consistency_check.py
**作用**
- 横向检查 snapshot / packet / verdict / runtime / summary / handoff / audit / business_event_state 之间是否一致
- 用于发现 latest 文件刷新不同步的问题

**典型检查**
- packet 引用的 snapshot ts 是否等于 snapshot 最新 ts
- verdict 引用的 packet ts 是否等于 packet 最新 ts
- runtime / summary / handoff 的 business_event_state 是否一致
- summary 引用的 latest packet / verdict ts 是否一致

**维护注意**
- 这是 D22.6 的最终一致性检查器
- 任何字段名改动都必须同步这里

---

# 四、当前最重要的人工维护顺序

每次改完核心脚本，推荐按下面顺序检查：


1. 先做语法检查  
   - `python3 -m py_compile ...`

2. 再跑 readonly 主链路  
   - `bybit_failure_policy_builder.py`
   - `bybit_full_readonly_observer_cycle.py`
   - `bybit_observer_acceptance_check.py`

3. 再跑集成状态层  
   - `bybit_runtime_state_resolver.py`
   - `bybit_readonly_final_summary.py`
   - `bybit_next_phase_handoff.py`
   - `bybit_readonly_audit.py`

4. 如果在做 business event 相关开发，再补跑  
   - `bybit_business_event_extract_from_ws_jsonl.py`
   - `bybit_business_event_ingestion_from_ws.py`
   - `bybit_business_event_runtime_facts.py`
   - `bybit_business_event_runtime_contract_check.py`
   - `bybit_business_event_state_resolver.py`
   - `bybit_business_event_state_contract_check.py`

5. 最后人工重点查看以下 latest 文件  
   - `runtime/bybit/bybit_runtime_state_latest.json`
   - `runtime/bybit/bybit_readonly_final_summary_latest.json`
   - `runtime/bybit/bybit_next_phase_handoff_latest.json`
   - `runtime/bybit/bybit_readonly_audit_latest.json`
   - `runtime/bybit/business_events/bybit_business_event_state_latest.json`

---

# 五、当前维护原则

- `read_only` 是硬边界，任何情况下都不能误开 execution
- `healthy_no_business_events_yet` 代表“健康空态”，不是故障
- `control_only` 代表 WS 连接层健康，不代表已经有可交易业务事件
- freshness 变 stale，很多时候只是因为时间过去了，不一定是代码坏了
- 改版本号时，必须同步修改 summary / audit / handoff / policy / runtime 等引用处
- 改 latest 文件字段名时，必须检查所有下游读取脚本

---

# 六、建议

后续如果你还会继续扩展 D23 / D24：
- 不要只靠脚本头注释
- 保持这个 `SCRIPT_INDEX.md` 持续更新
- 每新增一个核心脚本，就补三项：
  1. 作用
  2. 上下游依赖
  3. latest 产物

---

## G1 新增：Replay Harness / Fixtures

### bybit_business_event_fixture_pack_builder.py
**作用**
- 生成 G1 用的 wallet / order / execution / position 四类非空 fixture pack
- 为后续 replay 与非空事件验证提供稳定输入

### bybit_business_event_fixture_pack_contract_check.py
**作用**
- 校验 fixture pack 结构、版本、topic 覆盖是否正确

### bybit_business_event_replay_harness.py
**作用**
- 读取 fixture pack
- 生成隔离目录下的标准化 replay 输出
- 用于验证非空 business event 回放路径

**维护注意**
- 当前 replay 输出放在 `runtime/bybit/business_events/replay/`
- 目的是避免污染现有 readonly observer 主链 latest

### bybit_business_event_replay_contract_check.py
**作用**
- 校验 replay 输出是否为非空、topic 是否齐全、fingerprint 是否唯一
- 为后续 G2 / G3 提供基线


---

### Canonical path note / 规范路径说明（readonly_observer_pipeline）

The real implementation files for the readonly observer pipeline now live under:

`program_code/exchange_connectors/bybit_connector/readonly_observer_pipeline/`

The legacy entrypoints under:

`program_code/exchange_connectors/bybit_connector/scripts/`

are compatibility wrappers kept for backward compatibility during migration.

<!-- P7C_DECISION_LEASE_BATCH1_CANONICAL_START -->
## Decision-lease batch1 canonical path update (2026-03-24)

Canonical implementation path for the migrated batch1 core schema/preflight files is now:

`program_code/trade_executor/bybit_decision_lease/`

Legacy compatibility entrypoints are intentionally preserved under:

`program_code/exchange_connectors/bybit_connector/scripts/`

Those legacy files are now compatibility wrappers and should not be treated as the primary implementation source for the files listed below.

### Migrated files
- `bybit_decision_lease_chapter_contract_check.py`
- `bybit_decision_lease_chapter_final_audit.py`
- `bybit_decision_lease_chapter_handoff.py`
- `bybit_decision_lease_chapter_summary.py`
- `bybit_decision_lease_final_audit.py`
- `bybit_decision_lease_preflight.py`
- `bybit_decision_lease_preflight_contract_check.py`
- `bybit_decision_lease_schema.py`
- `bybit_decision_lease_schema_contract_check.py`

### Migration rule
- canonical implementation: `program_code/trade_executor/bybit_decision_lease/`
- compatibility wrapper: `program_code/exchange_connectors/bybit_connector/scripts/`
- new edits should target the canonical implementation first
<!-- P7C_DECISION_LEASE_BATCH1_CANONICAL_END -->

<!-- P7E_DECISION_LEASE_BATCH2_2026_03_24 -->
## Canonical path update — decision_lease batch2 (2026-03-24)
The following scripts now live canonically under `program_code/trade_executor/bybit_decision_lease/`.
Legacy files under `program_code/exchange_connectors/bybit_connector/scripts/` are compatibility wrappers only.

- `bybit_decision_lease_consume_contract_check.py` → `program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_consume_contract_check.py`
- `bybit_decision_lease_consume_final_audit.py` → `program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_consume_final_audit.py`
- `bybit_decision_lease_consume_gate.py` → `program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_consume_gate.py`
- `bybit_decision_lease_consume_gate_contract_check.py` → `program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_consume_gate_contract_check.py`
- `bybit_decision_lease_consume_policy.py` → `program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_consume_policy.py`
- `bybit_decision_lease_consume_policy_contract_check.py` → `program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_consume_policy_contract_check.py`
- `bybit_decision_lease_replay_contract_check.py` → `program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_replay_contract_check.py`
- `bybit_decision_lease_replay_final_audit.py` → `program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_replay_final_audit.py`
- `bybit_decision_lease_replay_guard.py` → `program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_replay_guard.py`
- `bybit_decision_lease_replay_guard_contract_check.py` → `program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_replay_guard_contract_check.py`
- `bybit_decision_lease_replay_policy.py` → `program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_replay_policy.py`
- `bybit_decision_lease_replay_policy_contract_check.py` → `program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_replay_policy_contract_check.py`
- `bybit_decision_lease_shadow_audit.py` → `program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_shadow_audit.py`
- `bybit_decision_lease_shadow_contract_check.py` → `program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_shadow_contract_check.py`
- `bybit_decision_lease_shadow_issue.py` → `program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_shadow_issue.py`
- `bybit_decision_lease_shadow_issue_contract_check.py` → `program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_shadow_issue_contract_check.py`

<!-- CANONICAL_PATH_NOTE_DECISION_LEASE_BATCH3 -->
## Canonical Path Update / 规范路径更新（Decision Lease Batch3）

The following `decision_lease` batch3 files now use the canonical directory:

`program_code/trade_executor/bybit_decision_lease/`

Files included in this batch:

- bybit_decision_lease_adaptive_ttl.py
- bybit_decision_lease_adaptive_ttl_contract_check.py
- bybit_decision_lease_approval_bridge.py
- bybit_decision_lease_approval_bridge_contract_check.py
- bybit_decision_lease_approval_bridge_final_audit.py
- bybit_decision_lease_friction_contract_check.py
- bybit_decision_lease_friction_final_audit.py
- bybit_decision_lease_friction_metrics.py
- bybit_decision_lease_friction_metrics_contract_check.py

Legacy entrypoints under `program_code/exchange_connectors/bybit_connector/scripts/`
are retained as compatibility wrappers only.
<!-- /CANONICAL_PATH_NOTE_DECISION_LEASE_BATCH3 -->

<!-- CANONICAL_PATH_NOTE_DECISION_LEASE_BATCH4 -->
## Canonical Path Update / 规范路径更新（Decision Lease Batch4）

The following `decision_lease` batch4 files now use the canonical directory:

`program_code/trade_executor/bybit_decision_lease/`

Files included in this batch:

- bybit_execution_authority_aggregator.py
- bybit_execution_authority_aggregator_contract_check.py
- bybit_execution_authority_aggregator_final_audit.py
- bybit_manual_approval_packet.py
- bybit_manual_approval_packet_contract_check.py
- bybit_manual_approval_packet_final_audit.py
- bybit_operator_ack_shadow.py
- bybit_operator_ack_shadow_contract_check.py
- bybit_operator_ack_shadow_final_audit.py

Legacy entrypoints under `program_code/exchange_connectors/bybit_connector/scripts/`
are retained as compatibility wrappers only.
<!-- /CANONICAL_PATH_NOTE_DECISION_LEASE_BATCH4 -->

<!-- CANONICAL_PATH_NOTE_DECISION_LEASE_FINAL -->
## Canonical Path Update / 规范路径更新（Decision Lease Final）

`decision_lease` canonical migration is now complete.

Canonical directory:
`program_code/trade_executor/bybit_decision_lease/`

The final migrated file is:
- bybit_decision_lease_contract_check.py

Legacy flat-script entries under
`program_code/exchange_connectors/bybit_connector/scripts/`
remain compatibility wrappers only.
<!-- /CANONICAL_PATH_NOTE_DECISION_LEASE_FINAL -->

## Canonical Path Update / 规范路径更新（Thought Gate Batch 1）

The first `thought_gate_and_ai_governance` batch has been migrated to:

`program_code/ai_agents/bybit_thought_gate/`

Batch:
- model_router

Canonical real files moved in this batch:
- bybit_model_router_contract_check.py
- bybit_model_router_decision.py
- bybit_model_router_decision_contract_check.py
- bybit_model_router_final_audit.py
- bybit_model_router_policy.py
- bybit_model_router_policy_contract_check.py
- bybit_model_router_runtime.py
- bybit_model_router_runtime_contract_check.py

Legacy flat-script paths remain compatibility wrappers during transition.

## Canonical Path Update / 规范路径更新（Thought Gate Batch 2）

The second `thought_gate_and_ai_governance` batch has been migrated to:

`program_code/ai_agents/bybit_thought_gate/`

Batch:
- compute_governor

Canonical real files moved in this batch:
- bybit_compute_governor_contract_check.py
- bybit_compute_governor_final_audit.py
- bybit_compute_governor_gate.py
- bybit_compute_governor_gate_contract_check.py
- bybit_compute_governor_policy.py
- bybit_compute_governor_policy_contract_check.py
- bybit_compute_governor_runtime.py
- bybit_compute_governor_runtime_contract_check.py

Legacy flat-script paths remain compatibility wrappers during transition.

## Canonical Path Update / 规范路径更新（Thought Gate Batch 3）

The third `thought_gate_and_ai_governance` batch has been migrated to:

`program_code/ai_agents/bybit_thought_gate/`

Batch:
- query_budget

Canonical real files moved in this batch:
- bybit_query_budget_final_audit.py
- bybit_query_budget_final_audit_contract_check.py
- bybit_query_budget_gate.py
- bybit_query_budget_gate_contract_check.py
- bybit_query_budget_policy.py
- bybit_query_budget_policy_contract_check.py
- bybit_query_budget_runtime.py
- bybit_query_budget_runtime_contract_check.py

Legacy flat-script paths remain compatibility wrappers during transition.

## Canonical Path Update / 规范路径更新（Thought Gate Batch 4）

The fourth `thought_gate_and_ai_governance` batch has been migrated to:

`program_code/ai_agents/bybit_thought_gate/`

Batch:
- ai_request_response_core

Canonical real files moved in this batch:
- bybit_ai_governed_decision.py
- bybit_ai_governed_decision_contract_check.py
- bybit_ai_invocation_attempt_builder.py
- bybit_ai_invocation_attempt_contract_check.py
- bybit_ai_prompt_prep_builder.py
- bybit_ai_prompt_prep_contract_check.py
- bybit_ai_prompt_prep_tighten.py
- bybit_ai_request_envelope_builder.py
- bybit_ai_request_envelope_contract_check.py
- bybit_ai_response_check.py
- bybit_ai_response_check_builder.py
- bybit_ai_response_check_contract_check.py
- bybit_ai_route_selector_builder.py
- bybit_ai_route_selector_contract_check.py

Legacy flat-script paths remain compatibility wrappers during transition.

## Canonical Path Update / 规范路径更新（Thought Gate Batch 5）

The fifth `thought_gate_and_ai_governance` batch has been migrated to:

`program_code/ai_agents/bybit_thought_gate/`

Batch:
- ai_governance_cost

Canonical real files moved in this batch:
- bybit_ai_cost_governance_contract_check.py
- bybit_ai_cost_governance_final_audit.py
- bybit_ai_cost_log.py
- bybit_ai_cost_log_contract_check.py
- bybit_ai_governance_audit.py
- bybit_ai_governance_audit_contract_check.py

Legacy flat-script paths remain compatibility wrappers during transition.

## Canonical Path Update / 规范路径更新（Thought Gate Batch 6）

The sixth `thought_gate_and_ai_governance` batch has been migrated to:

`program_code/ai_agents/bybit_thought_gate/`

Batch:
- thought_gate_outputs

Canonical real files moved in this batch:
- bybit_thought_gate_acceptance_suite.py
- bybit_thought_gate_contract_check.py
- bybit_thought_gate_decision_builder.py
- bybit_thought_gate_decision_contract_check.py
- bybit_thought_gate_final_audit.py
- bybit_thought_gate_handoff.py
- bybit_thought_gate_input_builder.py
- bybit_thought_gate_input_contract_check.py
- bybit_thought_gate_policy_builder.py
- bybit_thought_gate_policy_contract_check.py
- bybit_thought_gate_regression_summary.py

Legacy flat-script paths remain compatibility wrappers during transition.

> Canonical path note: exchange_io batch4 misc_io_support has moved to `program_code/exchange_connectors/bybit_connector/io_and_persistence/`. Legacy flat files under `scripts/` are compatibility wrappers.

> Canonical path note: exchange_io batch2 snapshot_and_postgres has moved to `program_code/exchange_connectors/bybit_connector/io_and_persistence/`. Legacy flat files under `scripts/` are compatibility wrappers.
