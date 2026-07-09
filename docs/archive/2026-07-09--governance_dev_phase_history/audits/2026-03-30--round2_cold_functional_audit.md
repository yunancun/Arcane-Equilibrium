# OpenClaw Bybit AI Trading System — Round 2 严格冷酷功能审核报告

**审核日期**: 2026-03-30
**审核人**: PM (Cowork)，基于 4 路并行代码级深度扫描
**代码基线**: Git HEAD `2a6c2e0` (Round 2 Batch 5-B + Batch 6)
**审核范围**: 全部核心模块 ~52,000 行代码，1,930+ 测试

---

## 任务 1：严格冷酷的功能审核

### 最终目标定义

一个能**自主盈利**的 AI 交易系统，完整链路：

```
自动扫描 → 策略选择 → AI风险评估 → 下单 → 止损 → 学习 → 进化
```

### 总体完成度：32%

> 这不是代码完成度（代码约 75%），这是**业务功能真正能用**的完成度。

---

### 逐环节审核

#### 1. 自动扫描 — 完成度 85%（✅ 实际可用）

| 项目 | 状态 | 证据 |
|------|------|------|
| 650+ 交易对每 5 分钟全扫描 | ✅ 运行中 | `strategy_auto_deployer.py` 市场扫描器 |
| 成交量异常检测 | ✅ 接入 | `pipeline_bridge.py` `_invoke_scout_scan()` 300s 间隔 |
| 资金费率尖峰检测 | ✅ 接入 | `pipeline_bridge.py` funding rate spike detection |
| Regime 检测（trending/ranging/squeeze） | ✅ 接入 | `market_regime.py` 多时间框架 |
| ScoutAgent REST 双通道 | ✅ 代码就绪 | `scout_routes.py` 5 端点，Token 认证 |
| **缺失**：ScoutAgent 发出的情报**无人消费** | ❌ | `MessageBus._subscribers` = 空列表，Scout 说话但没人听 |

**冷酷评价**：扫描层是整个系统最成熟的部分。能扫到机会，但情报只传到本地策略引擎，AI 增强层完全断开。

---

#### 2. 策略选择 — 完成度 40%（⚠️ 能用但无 AI 增强）

| 项目 | 状态 | 证据 |
|------|------|------|
| 5 类策略（Grid/MA/BB Rev/BB Break/FundingRate） | ✅ 实现 | `strategies/` 目录 |
| 信号规则 8 条（RSI/MACD/MA/BB/Regime） | ✅ 运行 | `signal_generator.py` |
| 策略自动部署（最优 5 品种） | ✅ 运行 | `strategy_auto_deployer.py` |
| Regime 过滤（ranging/squeeze/unknown 禁入） | ✅ 已修复 | `ma_crossover.py` lines 118-125 |
| **缺失**：策略选择纯靠硬编码权重，无 AI 参与 | ❌ | Strategist Agent 不存在，策略匹配是静态规则 |
| **缺失**：无回测验证，信号胜率未知 | ❌ | 信号 confidence 是数学公式，不是历史验证 |
| **缺失**：无 Kelly/动态仓位算法 | ❌ | 仓位大小 = 固定 max_pos × multiplier |

**冷酷评价**：策略层用的是教科书级技术指标（RSI/MACD/MA），这些指标被上百万交易者使用，**没有任何可证明的 alpha**。没有回测结果、没有 Sharpe ratio、没有 win rate 验证。系统能交易，但和"AI 自主盈利系统"有本质差距。

---

#### 3. AI 风险评估 — 完成度 20%（❌ AI 层基本断开）

| 项目 | 状态 | 证据 |
|------|------|------|
| H0 本地确定性判断 | ✅ 运行 | `risk_manager.py` P0/P1/P2 三层，fail-closed |
| GovernanceHub 4 SM 编排 | ✅ 运行 | `governance_hub.py` SM-01/02/04/EX-04 接入 |
| is_authorized() 真实拒绝订单 | ✅ 已验证 | `paper_trading_engine.py` lines 927-945 |
| acquire_lease() fail-closed | ✅ 已验证 | `paper_trading_engine.py` lines 991-1014 |
| **缺失**：L2 AI Engine 从未被主管线自动调用 | ❌ | 只有手动 `POST /layer2/trigger` 才触发 |
| **缺失**：Guardian Agent 不存在 | ❌ | 无动态风控参数调整 |
| **缺失**：Qwen edge filter 是 fail-open 设计 | ⚠️ | Ollama 不可用时返回 True（放行所有交易） |
| **缺失**：Perception Plane 从未接收市场数据 | ❌ | `register_data()` 零调用，认知诚实未执行 |

**冷酷评价**：H0 本地风控是实打实的，P0/P1/P2 限制确实会拒绝订单。但这只是**防御层**，不产生 alpha。AI 治理层（H1-H5）的代码完整，但从未被主管线自动调用。系统的"AI 风险评估"实际上是一个**规则引擎**，不是 AI。

---

#### 4. 下单 — 完成度 70%（✅ 能用，有治理 gate）

| 项目 | 状态 | 证据 |
|------|------|------|
| Paper Trading Engine 7 态生命周期 | ✅ 运行 | `paper_trading_engine.py` |
| 治理 gate（授权 + 租约） | ✅ 实际拒绝 | lines 902-1014 |
| Limit order 优先（省手续费） | ✅ Batch 6 修复 | `base.py` default order_type = "limit" |
| 双重执行（Paper + Bybit Demo） | ✅ 接入 | `bybit_demo_connector.py` |
| **缺失**：OMS 11 态状态机未串联 | ❌ | Paper Engine 用独立 7 态，`OMSStateMachine` 从未实例化 |
| **缺失**：Decision Lease 是治理层发的，不是 AI 决策 | ⚠️ | Lease 更像是"通行证"而非"AI 决策包" |

**冷酷评价**：下单链路完整且有治理保护。但 OMS 状态机作为正式的订单生命周期管理器完全被绕过，这意味着对账引擎无法与实际订单状态匹配。

---

#### 5. 止损 — 完成度 75%（✅ 核心功能可用）

| 项目 | 状态 | 证据 |
|------|------|------|
| Hard stop（P1 硬上限） | ✅ 每 tick 检查 | `risk_manager.py` line 820 |
| Trailing stop（动态 ATR） | ✅ Batch 6 加宽 | max(5%, 2×ATR/价格×100) |
| Time stop（regime 调整） | ✅ Session 11 修复 | squeeze 1.0x，trending 1.5x |
| AI 注意力税平仓 | ✅ 有最低 edge 保护 | edge_usd > taker_close_fee_usd |
| 连续亏损自动暂停 | ✅ 10 次阈值 | `strategy_auto_deployer.py` |
| **缺失**：止损失败不升级 | ⚠️ | `pipeline_bridge.py` line 556-557 只记录日志 |
| **缺失**：交易所条件单保护未实现 | ❌ | DOC-01 §5.9 要求双重防线，目前只有本地止损 |

**冷酷评价**：止损机制是系统的亮点之一。Batch 6 修复了最严重的参数问题。但缺少交易所端条件单意味着如果本地程序崩溃，**没有任何保护**。

---

#### 6. 学习 — 完成度 10%（❌ 基本不工作）

| 项目 | 状态 | 证据 |
|------|------|------|
| E1 观察记录（每轮 round-trip 后写入） | ✅ 接入 | `pipeline_bridge.py` `_emit_round_trip()` |
| Trade Attribution（交易归因） | ✅ 接入 | `trade_attribution.py` |
| LearningTierGate 实例化 + 注入 | ✅ | `phase2_strategy_routes.py` line 281 |
| L1→L2 自动晋升检查 | ✅ 代码存在 | `_try_learning_promotion()` |
| **缺失**：晋升指标从未被喂入数据 | ❌ | `update_metrics()` 零调用 |
| **缺失**：L2-L5 门控逻辑 = 占位符 | ❌ | 条件定义了但永远不可能满足 |
| **缺失**：Analyst Agent 不存在 | ❌ | 无人消费观察数据产出洞察 |
| **缺失**：PatternInsight/Hypothesis 验证链路不存在 | ❌ | L3-L5 完全无实现 |

**冷酷评价**：学习系统是整个架构最薄弱的环节。虽然能记录观察数据，但没有任何机制从这些数据中**提取知识**。E1 记录了交易结果，但没有 E2（模式发现）、E3（假设验证）、E4（策略进化）。系统不会从错误中学习，不会进化。

---

#### 7. 进化 — 完成度 5%（❌ 几乎为零）

| 项目 | 状态 | 证据 |
|------|------|------|
| Paper→Live Gate | ❌ 从未实例化 | `paper_live_gate.py` 代码完整但零部署 |
| 策略参数自动优化 | ❌ 不存在 | 参数全部硬编码 |
| 新策略自动发现 | ❌ 不存在 | 只有手动添加的 5 个策略 |
| 表现淘汰机制 | ❌ 不存在 | 无策略排名/淘汰逻辑 |
| Meta-Learning（L5） | ❌ 纯架构 | 需要 Operator 审批但审批端点是死代码 |

**冷酷评价**：进化能力为零。系统无法从历史交易中自动改进策略参数、发现新策略、或淘汰表现差的策略。这是"AI 自主盈利系统"最关键的缺失。

---

### 完成度汇总

| 环节 | 目标 | 当前 | 完成度 | 关键缺失 |
|------|------|------|--------|----------|
| 自动扫描 | 全市场智能扫描 | 650+ 对扫描 + regime | **85%** | Scout 情报无消费者 |
| 策略选择 | AI 驱动策略匹配 | 硬编码规则匹配 | **40%** | 无 AI、无回测、无动态仓位 |
| AI 风险评估 | 多层 AI 治理 | H0 规则引擎 | **20%** | L2 未接入、Guardian 不存在 |
| 下单 | 治理保护下单 | Paper + Demo 双执行 | **70%** | OMS 未串联 |
| 止损 | 双重防线 + 动态调整 | 本地 3 类止损 | **75%** | 缺交易所条件单 |
| 学习 | 持续自我改进 | 仅 E1 观察记录 | **10%** | 无知识提取、无模式发现 |
| 进化 | 自主策略进化 | 无 | **5%** | Paper→Live 未部署、无自动优化 |

**加权总完成度 = 32%**
（权重：扫描 10%、策略 20%、风险 15%、下单 15%、止损 10%、学习 15%、进化 15%）

---

### 5-Agent 体系现状

| Agent | 状态 | 现实 |
|-------|------|------|
| **Scout** | ✅ 运行 | 扫描市场、产出情报，但情报只落在本地策略引擎 |
| **Strategist** | ❌ 未实现 | 类定义不存在，策略选择用硬编码规则 |
| **Guardian** | ❌ 未实现 | 类定义不存在，风控参数不动态调整 |
| **Analyst** | ❌ 未实现 | 类定义不存在，观察数据无人分析 |
| **Executor** | ❌ 未实现 | 类定义不存在，执行质量无反馈 |
| **Conductor** | ❌ 代码完整但从未实例化 | 619-928 行完整实现，零生产调用 |

**MessageBus**：已实例化，`subscribe()` 在生产代码中零调用。Scout 发送消息到空的订阅者列表。

---

### except:pass 审计

在测试文件中发现 1 处 `except: pass`（`test_winrate_param_fixes.py` line 138），核心代码中**零处**。异常处理整体评价为**防御性、fail-closed**，这是系统最大的优点之一。

---

## 任务 2：治理架构融合分析

### 核心问题：GovernanceHub 是独立板块还是深度融合？

**答案：半融合状态。GovernanceHub 与 Paper Trading / Risk Manager 实现了运行时融合，但与 Strategy / Learning / OMS / Perception 完全脱节。**

### 架构关系图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        运行时主管线                                  │
│                                                                     │
│  Market Tick → KlineManager → IndicatorEngine → SignalEngine        │
│       │              │              │                │               │
│       │              │              │                ▼               │
│       │              │              │        StrategyOrchestrator    │
│       │              │              │                │               │
│       │              │              │                ▼               │
│       │         PipelineBridge ◄────────────── OrderIntent          │
│       │              │                                              │
│       │              ├── [1] Perception gate ──► PerceptionPlane    │
│       │              │        ⚠️ 注入但未调用 register_data()       │
│       │              │                                              │
│       │              ├── [2] Governance gate ──► GovernanceHub ◄──┐ │
│       │              │        ✅ is_authorized() 真实拒绝          │ │
│       │              │                                            │ │
│       │              ├── [3] Edge filter ──► OllamaClient         │ │
│       │              │        ⚠️ fail-open（Ollama 不可用=放行）   │ │
│       │              │                                            │ │
│       │              ▼                                            │ │
│       │     PaperTradingEngine.submit_order()                     │ │
│       │              │                                            │ │
│       │              ├── [4] is_authorized() ──────────────────────┘ │
│       │              ├── [5] check_order_allowed() ──► RiskManager   │
│       │              │        ✅ P0/P1/P2 真实拒绝                   │
│       │              ├── [6] acquire_lease() ──► GovernanceHub       │
│       │              │        ✅ fail-closed                          │
│       │              └── [7] execute_fill() → _emit_round_trip()     │
│       │                       │                                      │
│       │                       ├── TradeAttribution ✅                │
│       │                       ├── E1 Observation ✅                  │
│       │                       └── _try_learning_promotion() ⚠️      │
│       │                            （指标从未更新）                   │
│       │                                                              │
│       │    ┌─── check_positions_on_tick() ◄─── 每 tick 调用         │
│       │    │      Hard stop / Soft stop / TP / Time stop / AI tax    │
│       │    │      ✅ 真实产出平仓订单                                │
│       │    └──────────────────────────────────────────────────────── │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                    GovernanceHub 内部                                 │
│                                                                      │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────┐     │
│  │ SM-01    │   │ SM-02    │   │ SM-04    │   │ EX-04        │     │
│  │ 授权 SM  │   │ 租约 SM  │   │ 风控 SM  │   │ 对账引擎     │     │
│  │ ✅ 接入  │   │ ✅ 接入  │   │ ✅ 接入  │   │ ✅ 接入      │     │
│  └────┬─────┘   └────┬─────┘   └────┬─────┘   └──────┬───────┘     │
│       │              │              │                 │              │
│       └──────────────┴──────┬───────┴─────────────────┘              │
│                             │                                        │
│                    跨 SM 级联回调 ✅                                  │
│            风控升级 → 授权收缩/冻结                                   │
│            对账异常 → 风控升级                                        │
│            授权冻结 → 吊销所有活租约                                  │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                    孤立模块（代码完整但未接入）                        │
│                                                                      │
│  ❌ OMS StateMachine (SM-03)   — Paper Engine 用独立 7 态            │
│  ❌ PaperLiveGate              — 从未实例化                          │
│  ❌ Conductor                   — 619-928 行，零生产调用              │
│  ❌ Strategist/Guardian/Analyst/Executor Agent — 类不存在            │
│  ❌ L2 AI Engine               — 只有手动 API 触发                   │
│  ⚠️ PerceptionPlane            — 注入但 register_data() 零调用       │
│  ⚠️ LearningTierGate           — 注入但指标从未更新                  │
│  ⚠️ ChangeAuditLog             — 注入但未与 GovernanceHub 联动       │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 融合程度评估

| 板块 | 与 GovernanceHub 融合度 | 说明 |
|------|------------------------|------|
| **Paper Trading Engine** | ✅ 深度融合 (90%) | is_authorized + acquire_lease + fail-closed |
| **Risk Manager** | ✅ 深度融合 (85%) | check_order_allowed 调用 governance，P0/P1/P2 enforced |
| **Reconciliation Engine** | ✅ 深度融合 (80%) | GovernanceHub.reconcile() 直接调用 |
| **Audit Persistence** | ✅ 深度融合 (80%) | GovernanceHub 审计写盘 JSONL |
| **PipelineBridge** | ⚠️ 表层融合 (50%) | 调用 is_authorized 但不用 acquire_lease |
| **Strategy Layer** | ❌ 未融合 (0%) | 策略完全不感知治理状态 |
| **OMS State Machine** | ❌ 未融合 (0%) | SM-03 完全绕过 |
| **Learning Pipeline** | ❌ 未融合 (0%) | 学习不受治理管控 |
| **Multi-Agent** | ❌ 未融合 (0%) | Conductor 未实例化 |
| **L2 AI Engine** | ❌ 未融合 (0%) | 手动 API only |
| **Perception Plane** | ❌ 未融合 (0%) | register_data 零调用 |

### 是否过度设计？

**是的，存在明显的过度设计：**

1. **OMS 11 态 vs Paper Engine 7 态**：两套订单状态管理并存，永远不会交叉。OMS 的 RECONCILING / COMPLETED 状态在 Paper 模式下完全无意义。建议：Paper 阶段删除 OMS SM，待 Live 模式再引入。

2. **Conductor 完整实现但零使用**：619-928 行的精密代码（冲突仲裁、资源分配、任务分发），但连一个 Agent 都没注册。建议：先实现 Agent，再写 Conductor。

3. **5 级学习门控但 L1 都不工作**：L1→L5 精心设计了 5 级能力解锁，但连 L1 的指标都不更新。建议：先确保 L1 观察数据被真正分析，再谈 L2-L5。

4. **Perception Plane 认知标记**：FACT/INFERENCE/HYPOTHESIS 三级认知标记是好设计，但市场数据从未被包装。这是一个"API 存在但从未被调用"的典型案例。

### 架构改进建议

**Phase A（立即）：砍掉无用连接，加强有用连接**
- 移除 OMS SM 的假接入标记，明确标记为 "Phase Live 预留"
- PipelineBridge 中 Perception gate 改为真正调用 register_data()
- LearningTierGate 接入真实指标更新

**Phase B（短期）：填充缺失 Agent**
- Strategist 优先（替代硬编码策略选择）
- Guardian 次之（动态风控参数调整）
- Conductor 最后（等 3+ Agent 就绪再启用）

**Phase C（中期）：L2 自动触发**
- L2 Engine 从手动 API 改为事件驱动
- 市场异常事件 → 自动触发 L2 分析
- L2 建议 → PipelineBridge 接收

---

## 任务 3：Paper Trading 里程碑预估

### 从现在到稳定盈利 Paper Trading 的路径

**预估总时间：6-10 周**（假设每天 1 个 Cowork session，约 4-6 小时有效工作时间）

### Phase 1：参数验证 + 数据积累（Week 1-2）

> 目标：验证 Batch 6 参数修复效果，积累足够数据

| 任务 | 工作量 | 依赖 |
|------|--------|------|
| 部署 Batch 6 代码到 trade-core | 0.5 天 | 无 |
| 运行 Paper Trading 连续 7 天 | 7 天观察 | 部署完成 |
| 收集胜率、Sharpe、MaxDD 数据 | 数据驱动 | 7 天数据 |
| 分析 edge filter 拒绝率 | 0.5 天 | 数据收集 |
| 调整参数（如果胜率仍 <15%） | 1-2 天 | 数据分析 |

**里程碑判定**：胜率 > 15%，Sharpe > 0.3，MaxDD < 20%

**风险**：如果标准技术指标本身就没有 alpha，参数调整不会有帮助。可能需要回到策略层根本性改造。

### Phase 2：Agent 体系补全（Week 2-4）

> 目标：实现 Strategist + Guardian，让 AI 真正参与决策

| 任务 | 工作量 | 优先级 |
|------|--------|--------|
| **Strategist Agent** 实现 | 3-4 天 | P0 |
| — 消费 ScoutAgent 情报 | | |
| — 产出 TradeIntent（替代硬编码） | | |
| — 接入 PipelineBridge | | |
| **Guardian Agent** 实现 | 2-3 天 | P1 |
| — 消费 EventAlert | | |
| — 动态调整风控参数 | | |
| — 与 SM-04 联动 | | |
| **Conductor 实例化** | 1 天 | P2 |
| — 注册 Scout + Strategist + Guardian | | |
| — 驱动 dispatch_market_event | | |
| **MessageBus 接线** | 0.5 天 | P0 |
| — Scout→Strategist subscribe() | | |
| — Scout→Guardian subscribe() | | |
| 集成测试 | 2 天 | P0 |

**里程碑判定**：3 Agent 运行，MessageBus 有真实消息流，Conductor 分发事件

### Phase 3：L2 AI Engine 接入（Week 4-5）

> 目标：L2 从手动触发变为自动参与

| 任务 | 工作量 | 依赖 |
|------|--------|------|
| L2 Engine 事件驱动改造 | 2 天 | Phase 2 |
| Ollama L1 triage 自动触发 | 1 天 | Ollama 运行 |
| L2 建议 → PipelineBridge 接收 | 1 天 | L2 改造 |
| 成本预算管控（$0 目标 → L1 only） | 0.5 天 | |
| 集成测试 | 1 天 | |

**里程碑判定**：每次重大市场事件自动触发 L1/L2 分析，建议被系统接收

### Phase 4：端到端测试 + OMS 串联（Week 5-7）

> 目标：全链路打通，订单状态一致性

| 任务 | 工作量 | 依赖 |
|------|--------|------|
| OMS SM 串联到 Paper Engine | 3 天 | Phase 1-3 |
| PaperLiveGate 实例化 | 1 天 | |
| PerceptionPlane 接入 market data | 1 天 | |
| TTL 执行器定期调用 | 0.5 天 | |
| ChangeAuditLog 与 GovernanceHub 联动 | 0.5 天 | |
| 端到端冒烟测试（100+ 笔模拟交易） | 2 天 | |
| 回归测试（确保不破坏现有 1930 测试） | 1 天 | |

**里程碑判定**：全部 22/22 模块接入（接入率 100%），端到端测试通过

### Phase 5：稳定运行观察期（Week 7-10）

> 目标：连续运行证明系统稳定

| 任务 | 工作量 | 判定标准 |
|------|--------|----------|
| 连续运行 2 周 Paper Trading | 14 天观察 | 无崩溃、无数据丢失 |
| 每日性能报告（自动化） | 2 天开发 | Cron + Telegram |
| 胜率/Sharpe/DD 持续监控 | 持续 | 胜率 >30%、Sharpe >0.5 |
| 异常场景测试（网络断开、Ollama 宕机） | 2 天 | fail-closed 验证 |
| Bybit Demo vs Paper 对比分析 | 1 天 | 滑点 <0.1% |

**里程碑判定**：14 天连续运行，胜率 >30%，Sharpe >0.5，MaxDD <15%，无系统故障

### 关键风险因素

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 标准技术指标没有 alpha | 高 | 阻塞 | 需要引入 ML/统计套利策略 |
| Ollama/Qwen 推理质量不足 | 中 | 降级 | fall-open 设计已存在 |
| Agent 实现引入新 bug | 中 | 延期 | 严格测试 + 渐进式接入 |
| 市场 regime 变化导致策略失效 | 高 | 降级 | 需要策略自动淘汰机制 |
| Bybit API 限流/变更 | 低 | 延期 | 有 Demo sandbox 隔离 |

### 最诚实的预估

**乐观场景（6 周）**：Batch 6 参数修复有效，胜率提升到 20%+，Agent 实现顺利。

**中性场景（10 周）**：参数修复有限效果，需要 1-2 轮策略迭代，Agent 实现需要调试。

**悲观场景（16+ 周）**：标准技术指标本身没有 alpha，需要根本性重构策略层（引入 ML、统计套利、或链上数据分析）。这是**最可能的真实场景**。

---

## 附录：核心发现清单

### Critical（阻塞盈利）

| ID | 发现 | 影响 |
|----|------|------|
| C1 | 策略层无可证明的 alpha | 系统可能永远不盈利 |
| C2 | 4/6 Agent 未实现 | AI 自主能力为零 |
| C3 | L2 AI Engine 未接入主管线 | AI 增强层完全旁路 |
| C4 | 学习管线不工作 | 系统不从错误中改进 |

### High（影响完整性）

| ID | 发现 | 影响 |
|----|------|------|
| H1 | OMS SM-03 未串联 | 订单状态不一致 |
| H2 | PaperLiveGate 未部署 | 无 Paper→Live 门禁 |
| H3 | MessageBus 零订阅者 | Scout 情报浪费 |
| H4 | Perception Plane 未接入 | 认知诚实原则未执行 |
| H5 | 交易所条件单未实现 | 程序崩溃 = 无止损保护 |

### 亮点（做得好的）

| ID | 发现 |
|----|------|
| S1 | Governance fail-closed 设计一流 |
| S2 | P0/P1/P2 风控真实拒绝订单 |
| S3 | 异常处理防御性、无 except:pass |
| S4 | 650+ 交易对全扫描功能完整 |
| S5 | Batch 6 参数修复方向正确 |
| S6 | 1,930+ 测试覆盖完整 |

---

*报告结束。PM 建议 Operator 优先关注 C1（策略 alpha）和 C2（Agent 体系），这两项决定了系统是否有可能盈利。治理和风控层是优秀的，但保护机制再好，也无法替代交易 alpha。*
