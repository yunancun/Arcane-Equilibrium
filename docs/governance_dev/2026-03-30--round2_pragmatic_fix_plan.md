# Round 2 务实修复改进计划

**日期**：2026-03-30
**作者**：PM + FA 联合制定
**审批**：Operator
**基线**：Git HEAD `c289105`，功能完成度 32%，代码完成度 ~75%，测试 1,930+
**目标**：功能完成度 32% → 85%+，Paper Trading 可稳定盈利运行

---

## 一、改进目标（按优先级）

### Tier 1：盈利能力（最高优先）

| 目标 | 当前 | 目标值 | 衡量标准 |
|------|------|--------|----------|
| G1. 策略信号有 AI 增强 | 纯 RSI/MACD 硬编码 | Qwen 3.5 pre-trade 评估 + Strategist 选择 | 信号拒绝率 >30%，胜率 >20% |
| G2. 风控有 AI 动态调整 | 静态 P0/P1/P2 参数 | Guardian 根据 regime 动态调整 | 最大回撤 <15%，Sharpe >0.5 |
| G3. 止损双重防线 | 仅本地止损 | 本地 + 交易所条件单 | 程序崩溃时有保护 |

### Tier 2：自主能力（中优先）

| 目标 | 当前 | 目标值 | 衡量标准 |
|------|------|--------|----------|
| G4. Agent 体系运转 | 1/6 Agent（Scout） | 5/6 Agent + Conductor 运行 | MessageBus 消息流 >0 |
| G5. 学习管线打通 | E1 观察记录 | L1→L2 自动晋升 + 模式发现 | 周报含 pattern 洞察 |
| G6. 认知诚实执行 | Perception Plane 零调用 | 所有市场数据标记 FACT/INFERENCE | 100% 信号有认知标签 |

### Tier 3：运营安全（必需但不紧急）

| 目标 | 当前 | 目标值 | 衡量标准 |
|------|------|--------|----------|
| G7. OMS 串联 | Paper Engine 独立 7 态 | SM-03 11 态生命周期统一 | 订单状态一致 |
| G8. Paper→Live 门禁 | PaperLiveGate 未部署 | 11 项准入 + Operator 审批 | 门禁可运行 |
| G9. 端到端测试 | 单元测试为主 | E2E 冒烟测试 100+ 笔 | 全链路验证通过 |

---

## 二、改进要求（硬性约束）

### 不可违背

1. **system_mode = read_only**，不可更改
2. **fail-closed 设计不可破坏**：新代码必须在异常时默认拒绝
3. **现有 1,930+ 测试不可回归**：每个 Batch 完成后全量测试必须通过
4. **零外部成本**：所有 AI 调用仅用 L0（本地）+ L1（Ollama/Qwen 3.5），不用云端 API
5. **渐进式接入**：新 Agent 必须先 shadow 运行（只记录不执行），验证后再激活

### 质量标准

- 每个新模块必须有对应测试文件，覆盖率 >80%
- 每个新文件必须有中英双语 MODULE_NOTE
- 新增 except 必须记录日志，禁止 except:pass
- 所有新 Agent 交互必须经 GovernanceHub 审计

---

## 三、Batch 工作计划（6 个 Batch，每个 1-2 Cowork Session）

### Batch 7：Conductor 事件循环 + Strategist Agent

**目标**：让 5-Agent 消息链路运转起来，Strategist 替代硬编码策略选择

**完成度提升**：32% → 50%（+18%）

#### 改进要求

- Conductor 实例化并启动事件循环（复用已有 `multi_agent_framework.py:619-928` 的完整实现）
- MessageBus 注册 Scout→Strategist 订阅
- StrategistAgent 消费 ScoutAgent 情报，产出 TradeIntent
- StrategistAgent 用 Qwen 3.5 评估信号质量（替代硬编码 confidence）
- Pipeline Bridge on_tick 流程不变，但 intents 来源从 Orchestrator 扩展为 Orchestrator + Strategist

#### 具体任务

| 任务 | 角色 | 文件 | 工作量 | 说明 |
|------|------|------|--------|------|
| 7.1 Conductor 实例化 + 事件循环启动 | E1a | `phase2_strategy_routes.py` (~40行) | 2h | 在 line 127 后创建 Conductor 实例，register Scout，启动 loop |
| 7.2 MessageBus 订阅接线 | E1a | `phase2_strategy_routes.py` (~20行) | 1h | MESSAGE_BUS.subscribe(INTEL_OBJECT, strategist_handler) |
| 7.3 StrategistAgent 实现 | E1b | `app/strategist_agent.py` (新建, ~300行) | 4h | 消费 IntelObject → 调用 Qwen judge_edge() → 产出 TradeIntent |
| 7.4 PipelineBridge 扩展 intent 来源 | E1a | `pipeline_bridge.py` (~30行) | 2h | _process_pending_intents 同时收集 Orchestrator + Strategist intents |
| 7.5 Shadow 模式 | E1b | `strategist_agent.py` (~20行) | 1h | shadow=True 时只记录不产出 intent |
| 7.6 测试 | E4 | `tests/test_batch7_conductor_strategist.py` (新建, ~500行) | 3h | 25 测试 |
| 7.7 审计验收 | FA+CC | 代码审查 | 1h | fail-closed 验证 + 治理合规 |

#### 可并行任务

```
E1a: 7.1 → 7.2 → 7.4（串行，Conductor 接线）
E1b: 7.3 → 7.5（串行，Strategist 实现）
E4:  7.6（在 E1a/E1b 完成主体后开始）
FA:  7.7（E4 完成后审计）

并行度：E1a ∥ E1b，然后 E4，最后 FA
```

#### 验收标准

- [ ] Conductor.start() 在 FastAPI startup 时启动事件循环
- [ ] ScoutAgent 产出的 IntelObject 消息到达 StrategistAgent
- [ ] StrategistAgent 用 Qwen 3.5 judge_edge() 评估信号（Ollama 不可用时 fallback 到本地启发式）
- [ ] Shadow 模式下 Strategist 的 TradeIntent 只记录到审计日志，不进入 PipelineBridge
- [ ] 全量测试 1,930+ 通过（零回归）+ 25 新测试通过

---

### Batch 8：Guardian Agent + 动态风控

**目标**：Guardian 审查每个 TradeIntent，动态调整风控参数

**完成度提升**：50% → 62%（+12%）

#### 改进要求

- GuardianAgent 消费 EventAlert + TradeIntent
- Guardian 对 TradeIntent 做 5 项检查（方向冲突/杠杆上限/关联冲突/Sharpe/回撤）
- Guardian verdict 反馈到 PipelineBridge（APPROVED/REJECTED/MODIFIED）
- Guardian 动态调整风控参数（SM-04 联动）
- Qwen 3.5 用于异常事件风险评估

#### 具体任务

| 任务 | 角色 | 文件 | 工作量 | 说明 |
|------|------|------|--------|------|
| 8.1 GuardianAgent 实现 | E1a | `app/guardian_agent.py` (新建, ~350行) | 4h | 5 项检查 + verdict 产出 |
| 8.2 MessageBus 接线 | E1b | `phase2_strategy_routes.py` (~20行) | 1h | subscribe(TRADE_INTENT, guardian_handler) + subscribe(EVENT_ALERT, guardian_handler) |
| 8.3 PipelineBridge 接收 verdict | E1a | `pipeline_bridge.py` (~40行) | 2h | Guardian REJECTED → 不提交；MODIFIED → 调整数量/杠杆 |
| 8.4 SM-04 联动 | E1b | `guardian_agent.py` + `governance_hub.py` (~30行) | 2h | Guardian 检测异常 → 触发 SM-04 风控升级 |
| 8.5 Qwen 事件评估 | E1a | `guardian_agent.py` (~40行) | 1h | ollama_client.classify(event) → risk_level |
| 8.6 测试 | E4 | `tests/test_batch8_guardian.py` (新建, ~600行) | 3h | 30 测试 |
| 8.7 审计验收 | FA+CC | 代码审查 | 1h | |

#### 可并行任务

```
E1a: 8.1 → 8.3 → 8.5（Guardian 核心 + Bridge 接收 + Qwen）
E1b: 8.2 → 8.4（接线 + SM-04 联动）
E4:  8.6
FA:  8.7

并行度：E1a ∥ E1b
```

#### 验收标准

- [ ] Guardian 收到 TradeIntent 后返回 APPROVED/REJECTED/MODIFIED
- [ ] REJECTED intent 不进入 PipelineBridge.submit_order()
- [ ] MODIFIED intent 的数量/杠杆被调整后再提交
- [ ] Guardian 检测到异常事件时触发 SM-04 风控升级
- [ ] 全量测试通过 + 30 新测试

---

### Batch 9：Perception Plane 激活 + Analyst Agent (L1)

**目标**：所有市场数据标记认知级别，Analyst 开始分析交易结果

**完成度提升**：62% → 72%（+10%）

#### 改进要求

- KlineManager 输出包装为 PerceptionDataObject（FACT 级别）
- SignalEngine 输出标记为 INFERENCE
- ScoutAgent 情报标记为 INFERENCE 或 HYPOTHESIS
- AnalystAgent 消费 ROUND_TRIP_COMPLETE，更新 LearningTierGate 指标
- Analyst 计算滚动胜率、策略排名、regime 适配度

#### 具体任务

| 任务 | 角色 | 文件 | 工作量 | 说明 |
|------|------|------|--------|------|
| 9.1 Perception 接入 KlineManager | E1a | `pipeline_bridge.py` (~30行) | 1h | on_tick 中调用 perception_plane.register_data(kline, FACT) |
| 9.2 Perception 接入 SignalEngine | E1a | `pipeline_bridge.py` (~20行) | 1h | signal 产出后 register_data(signal, INFERENCE) |
| 9.3 Perception 接入 ScoutAgent | E1b | `scout_routes.py` (~20行) | 1h | intel/event 到达时标记认知级别 |
| 9.4 AnalystAgent 实现 | E1b | `app/analyst_agent.py` (新建, ~250行) | 3h | 消费 ROUND_TRIP_COMPLETE → 更新指标 → 策略排名 |
| 9.5 LearningTierGate 指标更新 | E1a | `pipeline_bridge.py` + `analyst_agent.py` (~40行) | 2h | Analyst 每 N 笔交易更新 win_rate/observation_count |
| 9.6 MessageBus 接线 | E1b | `phase2_strategy_routes.py` (~15行) | 0.5h | subscribe(ROUND_TRIP_COMPLETE, analyst_handler) |
| 9.7 测试 | E4 | `tests/test_batch9_perception_analyst.py` (新建, ~500行) | 3h | 25 测试 |
| 9.8 审计验收 | FA+CC | | 1h | |

#### 可并行任务

```
E1a: 9.1 → 9.2 → 9.5（Perception 接入 + 指标更新）
E1b: 9.3 → 9.4 → 9.6（Scout 标记 + Analyst 实现 + 接线）
E4:  9.7
FA:  9.8

并行度：E1a ∥ E1b
```

#### 验收标准

- [ ] 所有 kline 数据被包装为 PerceptionDataObject(FACT)
- [ ] 所有信号被标记为 PerceptionDataObject(INFERENCE)
- [ ] Analyst 收到 round_trip_complete 后更新 LearningTierGate 指标
- [ ] LearningTierGate 的 observations_count 和 win_rate 真实反映交易结果
- [ ] 全量测试通过 + 25 新测试

---

### Batch 10：L2 学习自动化 + OMS 串联

**目标**：L2 模式发现自动运行（每周），OMS 订单状态统一

**完成度提升**：72% → 80%（+8%）

#### 改进要求

- Analyst 积累足够数据后（observations ≥ 200），自动触发 Qwen 模式分析
- Qwen 分析交易结果 → 产出 PatternInsight（哪些 regime+策略组合赢了/输了）
- OMS SM-03 串联到 Paper Trading Engine（替换独立 7 态）
- TTL 执行器定期调用（过期租约自动终止）

#### 具体任务

| 任务 | 角色 | 文件 | 工作量 | 说明 |
|------|------|------|--------|------|
| 10.1 Analyst L2 模式分析 | E1b | `analyst_agent.py` (~100行) | 3h | 积累数据 → Qwen analyze_patterns() → PatternInsight |
| 10.2 Cron 触发器 | E1a | `pipeline_bridge.py` (~30行) | 1h | 每周日 UTC 0:00 触发 Analyst L2 分析 |
| 10.3 OMS 串联 | E1a | `paper_trading_engine.py` (~80行) | 4h | 替换 7 态为 SM-03 11 态，映射状态转换 |
| 10.4 TTL 执行器接通 | E1b | `phase2_strategy_routes.py` (~20行) | 1h | TTL sweep 定期调用，过期租约回调 GovernanceHub |
| 10.5 测试 | E4 | `tests/test_batch10_learning_oms.py` (新建, ~600行) | 3h | 30 测试 |
| 10.6 审计验收 | FA+CC | | 1h | |

#### 可并行任务

```
E1a: 10.2 → 10.3（Cron + OMS 串联）
E1b: 10.1 → 10.4（Analyst L2 + TTL）
E4:  10.5
FA:  10.6

并行度：E1a ∥ E1b
```

#### 验收标准

- [ ] Analyst 在 observations ≥ 200 后自动产出 PatternInsight
- [ ] PatternInsight 包含：winning_patterns, losing_patterns, regime_strategy_matrix
- [ ] OMS SM-03 管理 Paper Engine 订单状态（11 态生命周期）
- [ ] TTL 执行器每 5s 扫描，过期租约自动终止并回调
- [ ] 全量测试通过 + 30 新测试

---

### Batch 11：Executor Agent + 交易所条件单

**目标**：Executor 包装下单，交易所端有止损保护

**完成度提升**：80% → 85%（+5%）

#### 改进要求

- ExecutorAgent 包装 PaperTradingEngine.submit_order()
- Executor 提供执行质量反馈（滑点、填充时间）
- Bybit Demo sandbox 创建交易所条件单（stop-loss）
- 本地止损 + 交易所条件单 = 双重防线（DOC-01 §5.9）

#### 具体任务

| 任务 | 角色 | 文件 | 工作量 | 说明 |
|------|------|------|--------|------|
| 11.1 ExecutorAgent 实现 | E1a | `app/executor_agent.py` (新建, ~200行) | 3h | 包装 submit_order + 执行质量指标 |
| 11.2 交易所条件单 | E1b | `bybit_demo_connector.py` (~60行) | 3h | place_conditional_order(stop_loss) via Bybit V5 API |
| 11.3 双重防线接通 | E1a | `pipeline_bridge.py` (~30行) | 2h | 开仓后同时创建本地止损 + 交易所条件单 |
| 11.4 MessageBus 接线 | E1b | `phase2_strategy_routes.py` (~15行) | 0.5h | subscribe(APPROVED_INTENT, executor_handler) |
| 11.5 测试 | E4 | `tests/test_batch11_executor_exchange.py` (新建, ~500行) | 3h | 25 测试 |
| 11.6 审计验收 | FA+CC | | 1h | |

#### 可并行任务

```
E1a: 11.1 → 11.3（Executor + 双重防线）
E1b: 11.2 → 11.4（交易所条件单 + 接线）
E4:  11.5
FA:  11.6

并行度：E1a ∥ E1b
```

#### 验收标准

- [ ] Executor 收到 APPROVED_INTENT 后调用 submit_order()
- [ ] Executor 产出 EXECUTION_REPORT（含滑点、填充时间）
- [ ] 开仓后交易所端有对应条件单（stop-loss）
- [ ] 本地程序停止时，交易所条件单仍然存在
- [ ] 全量测试通过 + 25 新测试

---

### Batch 12：Paper→Live 门禁 + 端到端验证

**目标**：PaperLiveGate 部署，端到端冒烟测试，系统可观察稳定运行

**完成度提升**：85% → 88%（+3%）

#### 改进要求

- PaperLiveGate 实例化并接入授权工作流
- 11 项门禁标准可评估（duration/trade_count/win_rate/Sharpe/DD/...）
- 端到端冒烟测试：100+ 笔模拟交易全链路
- 自动化日报（Cron + Telegram）
- ChangeAuditLog 与 GovernanceHub 联动

#### 具体任务

| 任务 | 角色 | 文件 | 工作量 | 说明 |
|------|------|------|--------|------|
| 12.1 PaperLiveGate 实例化 | E1a | `phase2_strategy_routes.py` (~30行) | 1h | 创建实例，注入 GovernanceHub |
| 12.2 门禁 API 端点 | E1b | `governance_routes.py` (~40行) | 2h | GET /governance/paper-live-gate/status + POST /governance/paper-live-gate/evaluate |
| 12.3 ChangeAuditLog 联动 | E1a | `governance_hub.py` (~20行) | 1h | 状态变更时写入 ChangeAuditLog |
| 12.4 日报自动化 | E1b | `helper_scripts/cron_daily_report.sh` (新建) | 2h | Cron UTC 0:00 → 生成报告 → Telegram |
| 12.5 E2E 冒烟测试 | E4 | `tests/test_batch12_e2e_smoke.py` (新建, ~800行) | 4h | 100+ 笔模拟交易全链路验证 |
| 12.6 最终审计 | FA+CC+TW | 全系统 | 2h | 完成度重新评估 + 文档更新 |

#### 可并行任务

```
E1a: 12.1 → 12.3（Gate 实例化 + AuditLog）
E1b: 12.2 → 12.4（API + 日报）
E4:  12.5（在 E1a/E1b 完成后开始 E2E 测试）
FA+CC+TW: 12.6（E4 完成后最终审计）

并行度：E1a ∥ E1b → E4 → FA
```

#### 验收标准

- [ ] PaperLiveGate.evaluate_gate() 返回 11 项准入评估结果
- [ ] API 端点可查询门禁状态
- [ ] E2E 冒烟测试 100+ 笔交易全链路通过
- [ ] 日报自动推送到 Telegram
- [ ] ChangeAuditLog 记录所有状态变更
- [ ] 全量测试通过 + 35 新测试（含 E2E）

---

## 四、Cowork Session 工作流编排

### 总体时间线

```
Session 1 ─── Batch 7 前半（Conductor + Strategist 骨架）
Session 2 ─── Batch 7 后半（测试 + 审计 + shadow 验证）
Session 3 ─── Batch 8（Guardian + 动态风控）
Session 4 ─── Batch 9（Perception + Analyst L1）
Session 5 ─── Batch 10 前半（Analyst L2 + OMS 串联开始）
Session 6 ─── Batch 10 后半（OMS 串联完成 + 测试）
Session 7 ─── Batch 11（Executor + 交易所条件单）
Session 8 ─── Batch 12 前半（PaperLiveGate + API + 日报）
Session 9 ─── Batch 12 后半（E2E 冒烟 + 最终审计）
Session 10 ── 缓冲（回归修复 + 参数调优 + 观察期启动）
```

### 每个 Cowork Session 内部分配

```
┌─────────────────────────────────────────────────────────────────┐
│ Session 开始                                                     │
│                                                                   │
│ Phase 0: PM 任务分配（5 min）                                    │
│   PM 读取上一 session 的审计结果，分配本 session 任务             │
│                                                                   │
│ Phase 1: 并行开发（E1a ∥ E1b，2-3h）                            │
│   E1a: 核心模块实现（Conductor/Bridge/Engine 改造）              │
│   E1b: Agent 实现 + 接线（Strategist/Guardian/Analyst/Executor） │
│   ── 独立文件，零冲突 ──                                        │
│                                                                   │
│ Phase 2: 集成 + 测试（E4，1-2h）                                │
│   E4: 编写测试 + 运行全量测试 + 验证零回归                      │
│                                                                   │
│ Phase 3: 审计验收（FA+CC，30min-1h）                            │
│   FA: 架构合规性检查（fail-closed/治理/审计）                    │
│   CC: 16 条根原则合规验证                                        │
│                                                                   │
│ Phase 4: PM 收尾（15 min）                                      │
│   更新 CLAUDE.md + docs/ + Git commit + push                    │
│                                                                   │
│ Session 结束                                                     │
└─────────────────────────────────────────────────────────────────┘
```

### 角色与工具对应

| 角色 | Cowork Agent 映射 | 工具 | 权限 |
|------|-------------------|------|------|
| **PM** | 主 Agent（用户对话） | TodoWrite + Git + docs | 任务分配、进度追踪、文档更新 |
| **E1a** | Sub-Agent（general-purpose） | Read + Write + Edit + Bash | 核心模块代码 |
| **E1b** | Sub-Agent（general-purpose） | Read + Write + Edit + Bash | Agent 代码（独立文件） |
| **E4** | Sub-Agent（general-purpose） | Read + Write + Bash(pytest) | 测试编写 + 运行 |
| **FA** | Sub-Agent（Explore/Plan） | Read + Grep + Glob | 架构审查（只读） |
| **CC** | Sub-Agent（Explore） | Read + Grep | 合规检查（只读） |
| **TW** | Sub-Agent（general-purpose） | Read + Write + Edit | 文档更新 |

### 并行策略

每个 Batch 内部：

```
                    ┌── E1a（核心模块）──┐
PM 分配 ─→ Fork ─→ │                    │ ─→ Join ─→ E4（测试）─→ FA（审计）─→ PM 收尾
                    └── E1b（Agent 实现）─┘
```

跨 Batch 的并行（有限）：

- Batch 7 的 E4 测试可以和 Batch 8 的 E1a/E1b 设计并行（E4 测试 Batch 7 时，E1a/E1b 可以开始读 Batch 8 的依赖文件）
- 但实际 Cowork 单 session 内建议不跨 Batch，避免上下文混乱

---

## 五、最终功能审计标准

### Batch 全部完成后的审计清单

Batch 7-12 全部完成后，进行一次完整的功能审计（与 Round 2 审核相同方法论），验证以下指标：

#### A. 全链路功能验证（必须全部 PASS）

| 编号 | 审计项 | 验证方法 | PASS 标准 |
|------|--------|----------|-----------|
| A1 | 市场扫描→Scout→Strategist | 启动系统，观察 MessageBus 日志 | 5 分钟内有 IntelObject→TradeIntent 消息流 |
| A2 | Strategist→Guardian→Executor | 注入测试信号 | Guardian verdict 正确，Executor 提交订单 |
| A3 | 下单→治理 gate | 提交未授权订单 | 订单被 is_authorized() 拒绝（不是 warning） |
| A4 | 下单→acquire_lease | 提交正常订单 | 租约获取成功，订单执行，租约释放 |
| A5 | 止损双重防线 | 开仓后检查 | 本地止损 + 交易所条件单同时存在 |
| A6 | 学习回调 | 平仓后检查 | E1 观察写入 + Analyst 指标更新 + LearningTierGate 计数 |
| A7 | Perception 标记 | 检查日志 | 所有 kline=FACT，signal=INFERENCE，scout=INFERENCE |
| A8 | OMS 状态一致 | 下单→填充→平仓 | SM-03 状态与 Paper Engine 状态一致 |
| A9 | PaperLiveGate 评估 | 调用 evaluate_gate() | 返回 11 项评估结果（即使未达标也要返回明确数据） |
| A10 | 日报自动化 | 等待 Cron 触发 | Telegram 收到日报 |

#### B. 性能指标验证（目标值）

| 指标 | 最低要求 | 目标值 | 衡量方法 |
|------|----------|--------|----------|
| 胜率 | >15% | >25% | 连续 7 天 Paper Trading 数据 |
| Sharpe | >0.3 | >0.8 | 日收益率计算 |
| 最大回撤 | <25% | <15% | 持续监控 |
| 信号拒绝率 | >20% | >35% | Guardian REJECTED / 总 intent |
| Agent 消息流 | >0 msg/min | >5 msg/min | MessageBus 统计 |
| Perception 覆盖 | >80% | 100% | register_data 调用次数 / 数据流入次数 |
| 测试通过 | 100% | 100% | pytest 全量运行 |
| except:pass | 0 | 0 | grep 搜索 |

#### C. 逐环节完成度重新评估

| 环节 | 审核前 | 目标 | 验证方法 |
|------|--------|------|----------|
| 自动扫描 | 85% | 90% | Scout 情报被 Strategist 消费 |
| 策略选择 | 40% | 70% | Strategist + Qwen AI 评估替代硬编码 |
| AI 风险评估 | 20% | 65% | Guardian + SM-04 联动 + Qwen 事件评估 |
| 下单 | 70% | 85% | OMS 串联 + Executor 包装 |
| 止损 | 75% | 90% | 双重防线（本地 + 交易所） |
| 学习 | 10% | 50% | L1 观察 + L2 模式发现 + 指标更新 |
| 进化 | 5% | 30% | PaperLiveGate 部署 + 策略排名 |

**加权总完成度目标：85%+**

---

## 六、风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| Qwen 3.5 推理质量不足 | 中 | 策略选择退化 | fail-open 设计，Qwen 不可用时回退到本地启发式 |
| Agent 引入新 bug | 中 | 回归 | shadow 模式先行 + 全量回归测试 |
| OMS 串联破坏现有 Paper Engine | 中 | 阻塞 | 分步替换（先 mapping 再完全切换），保留回退路径 |
| 标准技术指标本身无 alpha | 高 | 盈利不达标 | Batch 10 Analyst L2 发现模式 → 策略排名淘汰 |
| Session 时间不够 | 中 | 延期 | 严格 E1a∥E1b 并行 + 预先设计减少 session 内决策 |

---

## 七、文件清单总览

### 新建文件（6 个核心 + 6 个测试 + 1 个脚本）

| 文件 | Batch | 角色 | 预估行数 |
|------|-------|------|----------|
| `app/strategist_agent.py` | 7 | E1b | ~300 |
| `app/guardian_agent.py` | 8 | E1a | ~350 |
| `app/analyst_agent.py` | 9 | E1b | ~350 |
| `app/executor_agent.py` | 11 | E1a | ~200 |
| `tests/test_batch7_conductor_strategist.py` | 7 | E4 | ~500 |
| `tests/test_batch8_guardian.py` | 8 | E4 | ~600 |
| `tests/test_batch9_perception_analyst.py` | 9 | E4 | ~500 |
| `tests/test_batch10_learning_oms.py` | 10 | E4 | ~600 |
| `tests/test_batch11_executor_exchange.py` | 11 | E4 | ~500 |
| `tests/test_batch12_e2e_smoke.py` | 12 | E4 | ~800 |
| `helper_scripts/cron_daily_report.sh` | 12 | E1b | ~50 |

### 修改文件（7 个）

| 文件 | Batch | 改动量 |
|------|-------|--------|
| `phase2_strategy_routes.py` | 7,8,9,10,12 | +150 行（Conductor/Agent 实例化 + 接线） |
| `pipeline_bridge.py` | 7,8,9,10,11 | +150 行（intent 来源扩展 + Perception + verdict 接收 + 条件单） |
| `paper_trading_engine.py` | 10 | +80 行（OMS SM-03 串联） |
| `governance_hub.py` | 8,12 | +40 行（SM-04 联动 + ChangeAuditLog） |
| `governance_routes.py` | 12 | +40 行（PaperLiveGate API） |
| `bybit_demo_connector.py` | 11 | +60 行（交易所条件单） |
| `scout_routes.py` | 9 | +20 行（Perception 标记） |

**总新增**：~2,200 行核心 + ~3,500 行测试 = ~5,700 行

---

*计划结束。PM 建议 Operator 批准后从 Batch 7 开始执行。每个 Batch 独立可测试，中途可暂停。*
