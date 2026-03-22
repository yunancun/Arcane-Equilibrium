# Revision 2 Chapter Realignment Note

## Purpose
本文档用于说明：
- 当前工程应以 **Revision 2 正式章节树** 为准
- 最近一批脚本在开发过程中曾使用过临时编号
- 这些临时编号已经废弃，后续维护时必须按正式章节理解

---

# 一、正式章节树（当前有效）

后续维护与施工顺序，应按以下正式主线理解：

- A-C：基础层 / OpenClaw 模型层 / 接入前治理
- D：Readonly Observer 主链
- E：Business Event Classification
- F：Event-Driven Transition Scaffold
- G：真实业务事件验证层
- H：AI 治理
- I：Decision Lease
- J：Transition Engine Skeleton
- K：Paper / Demo Gate
- L：Learning / Self-Observability / Net PnL
- 后续才是 M / N

---

# 二、已完成与未完成的大框架理解

## 当前已完成的大段
- A-F 已完成
- 其中包括：
  - readonly observer infrastructure
  - business-event classification
  - event-driven scaffold

## 当前正在推进 / 已部分展开
- G：真实业务事件验证层
- J：Transition Engine Skeleton（已提前做出一部分 skeleton）
- K：Paper / Demo Gate（已提前做出一部分 design/skeleton）

## 当前尚未正式开始的关键大段
- H：AI 治理
- I：Decision Lease
- L：Learning / Self-Observability / Net PnL（正式大段尚未开始）

---

# 三、最近这批脚本的正式归位

## 1. G 章：真实业务事件验证层
这一组脚本仍属于 G 章，方向正确：
- replay fixtures / fixture pack
- replay harness
- 非空业务事件正向语义验证
- 负向阻断验证
- consistency / regression 检查

典型脚本族：
- bybit_business_event_fixture_pack*
- bybit_business_event_replay*
- bybit_event_replay_state*
- bybit_event_replay_phase*
- bybit_event_replay_transition_input*
- bybit_event_replay_transition_decider*
- bybit_event_replay_transition_outcome*
- bybit_event_replay_transition_consistency*
- bybit_business_event_negative_fixture_pack*
- bybit_business_event_negative_replay*
- bybit_event_replay_block_chain*

说明：
- 这些脚本属于验证层
- 不属于 transition engine 本体
- 不属于 paper/demo gate
- 输出必须与主 runtime 隔离

---

## 2. J 章：Transition Engine Skeleton
这一组脚本开发过程中曾被临时写成 G4.x，但该编号已经废弃。
后续应统一理解为 J 章：

典型脚本族：
- bybit_transition_engine_replay_matrix*
- bybit_transition_engine_audit_trail*
- bybit_transition_rule_layer*
- bybit_transition_state_graph*
- bybit_transition_engine_summary*
- bybit_transition_engine_handoff*
- bybit_transition_engine_final_audit*
- bybit_transition_engine_checkpoint*

说明：
- 这些脚本是在做 transition engine skeleton
- 不是 G 章验证层
- 不是 live execution
- 当前仍只是 skeleton，不代表 transition engine 已完成

---

## 3. K 章：Paper / Demo Gate
这一组脚本开发过程中曾被临时写成 G5 / G6，但这些临时编号已经废弃。
后续应统一理解为 K 章：

典型脚本族：
- bybit_demo_gate_contract*
- bybit_demo_gate_readiness*
- bybit_demo_paper_adapter_skeleton*
- bybit_paper_order_lifecycle_skeleton*
- bybit_paper_position_balance_projection_skeleton*
- bybit_pretrade_risk_integration_skeleton*
- bybit_demo_gate_summary*
- bybit_demo_gate_handoff*
- bybit_demo_gate_final_audit*
- bybit_simulator_adapter_contract*（若后续落地创建）

说明：
- 这些脚本属于 paper/demo gate 设计层或 skeleton 层
- 不代表 gate 已开放
- 不代表 paper execution 已可运行
- 更不代表 live execution 可以开启

---

# 四、当前必须坚持的理解边界

- 主系统当前仍必须保持 `read_only`
- `execution_state` 必须继续保持 `disabled`
- G 章 replay / negative / consistency 输出不得污染主 runtime
- J 章当前只是 transition engine skeleton
- K 章当前只是 paper/demo gate design/skeleton
- 任何 future demo/paper enable 都不等于 live execution enable

---

# 五、后续维护规则

1. 新脚本注释必须优先标注 **正式章节**
2. 不得再继续扩张旧的临时编号（如 G5、G6、G4.7 这类写法）
3. 若历史日志提到旧临时编号，必须以本说明文档和 Revision 2 正式章节树为准
4. 若后续确需改文件名 / stage / latest 路径，必须单独做兼容性评估，不可在注释修正时顺手混改

