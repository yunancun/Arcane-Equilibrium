# OpenClaw / Bybit AI Agent Trading System
<!-- Git 日志 — 项目入口。主日志见 CLAUDE.md -->

AI Agent 自动交易系统 — 自主扫描 650+ 交易对，智能部署策略，双重执行（Paper + Bybit Demo）。

---

## 🖥️ GUI 访问（Tailscale 网络内）

| 地址 | 功能 |
|------|------|
| **[http://trade-core:8000](http://trade-core:8000)** | **统一控制台**（登录后进入 4 Tab 视图） |
| [http://trade-core:3000](http://trade-core:3000) | Grafana 运营监控仪表盘 |
| [https://trade-core.tail358794.ts.net](https://trade-core.tail358794.ts.net) | OpenClaw Gateway |

### 统一控制台 Tab

| Tab | 内容 |
|-----|------|
| 控制台 / Dashboard | 系统状态 + Paper Trading + 章节状态 |
| 📊 K线图表 / Charts | TradingView K线 + 信号标记 + 策略面板 |
| 📈 监控 / Grafana | PnL 曲线 + 交易记录 + 系统健康 |
| OpenClaw | OpenClaw Gateway 控制 |

---

## 当前状态 (2026-03-30 Round 2 冷酷功能审核后)

```
系统模式:     read_only（不变）
执行权限:     disabled / not_granted（不变）
测试:         1,930+（含 46 治理 Hub + 92 集成 + 45 Scout + 15 学习晋升 + 28 Ollama/L1 + 21 Edge Filter + 23 参数修复 · 2 跳过）
API 路由:     126+ 条（含 8 治理 + 5 Scout 端点）
信号规则:     8 条（4入场 + 2退出 + 1regime + 1divergence）
策略:         5 类（Grid + MA + BB Reversion + BB Breakout + FundingRate Delta-Neutral）
市场扫描:     650+ 交易对每 5 分钟全扫描
自动部署:     最优 5 品种自动匹配策略
执行模式:     双重执行（Paper Engine + Bybit Demo sandbox）
治理:         GovernanceHub 已集成 · SM-01/SM-02/SM-04/EX-04 接入运行时 · fail-closed 已验证
Scout:        ScoutAgent + MessageBus 已接入 PipelineBridge（Plan A2 本地代理模式）
学习晋升:     L1→L2 自动晋升已接通（PipelineBridge → promote_tier()）
L1 本地推理:  Ollama HTTP 客户端 + Qwen 3.5 27B（L1 triage + pre-trade edge filter 就绪）
胜率修复:     ★ 4/4 根因已修复（edge filter + 止损加宽 + limit order + squeeze 乘数）
接入率:       19/22 = 86%（Batch 4 审计修正 · 仅 3 模组真正 STANDALONE）
合规度:       ~88%
```

**★ Round 2 冷酷功能审核结论（2026-03-30）**

代码完成度 ~75%，但**业务功能真正能用 = 32%**。

| 环节 | 完成度 | 关键缺失 |
|------|--------|----------|
| 自动扫描 | 85% | Scout 情报无消费者 |
| 策略选择 | 40% | 无 AI、无回测、无动态仓位 |
| AI 风险评估 | 20% | H1-H5 AI 层完全断开 |
| 下单 | 70% | OMS SM-03 未串联 |
| 止损 | 75% | 缺交易所条件单双重防线 |
| 学习 | 10% | 无知识提取/模式发现 |
| 进化 | 5% | PaperLiveGate 未部署 |

**亮点**：治理 fail-closed 一流 · P0/P1/P2 风控真实拒绝 · 异常处理零 except:pass · 1930+ 测试

**关键缺失**：4/6 Agent 未实现 · Conductor 零调用 · MessageBus 零订阅者 · L2 仅手动触发 · 策略无 alpha

**详细报告**：`docs/governance_dev/audits/2026-03-30--round2_cold_functional_audit.md`
**修复计划**：`docs/governance_dev/2026-03-30--round2_fix_plan_batches_7_12.md`

**已完成**: A-L + 策略工具包 + 管线桥接 + 全系统审核 + GUI 三层 + 自主交易 Agent + Phase 2 治理模組 + Phase 3 GovernanceHub 集成 + Round 2 Scout 集成 + Learning 自动晋升 + L1 本地推理 + Pre-trade Edge Filter + 0% 胜率四根因全修复

**★ 下一步：Round 2 修复计划（Batch 7-12）**

6 个 Batch，预估 10 个 Cowork Session（2-3 周），目标 32% → 85%+ 功能完成度。

| Batch | 内容 | 完成度 |
|-------|------|--------|
| 7 | Conductor 事件循环 + Strategist Agent | 32→50% |
| 8 | Guardian Agent + 动态风控 | 50→62% |
| 9 | Perception Plane 激活 + Analyst Agent (L1) | 62→72% |
| 10 | L2 学习自动化 + OMS 串联 | 72→80% |
| 11 | Executor Agent + 交易所条件单 | 80→85% |
| 12 | Paper→Live 门禁 + 端到端验证 | 85→88% |

**务实修复计划**：[`docs/governance_dev/2026-03-30--round2_pragmatic_fix_plan.md`](docs/governance_dev/2026-03-30--round2_pragmatic_fix_plan.md)

---

## 项目结构

```
srv/
├── CLAUDE.md                      ← ★ 项目完整上下文
├── docs/                          ← 工程文档（20+ 份日志/审核/设计）
├── program_code/
│   ├── exchange_connectors/
│   │   └── bybit_connector/
│   │       └── control_api_v1/    ← FastAPI 121+ 路由 + 1,566 测试
│   │           ├── app/
│   │           │   ├── governance_hub.py         ← ★ 治理中枢（4 SM 编排 + 跨 SM 级联）
│   │           │   ├── governance_routes.py      ← 8 治理 API 端点
│   │           │   ├── scout_routes.py          ← 5 Scout REST 端点（OpenClaw 推送入口）
│   │           │   ├── multi_agent_framework.py ← ScoutAgent + MessageBus + Conductor
│   │           │   ├── ollama_client.py         ← Ollama HTTP 客户端（L1 本地推理）
│   │           │   ├── pipeline_bridge.py       ← 管线桥接器（治理 gate + Scout 本地扫描）
│   │           │   ├── stop_manager.py          ← 止损管理器（→ local_model_tools）
│   │           │   ├── bybit_demo_connector.py  ← Bybit Demo 连接器
│   │           │   ├── grafana_data_writer.py   ← Grafana 数据写入
│   │           │   ├── telegram_alerter.py      ← Telegram 告警
│   │           │   └── static/                  ← GUI (login/console/trading)
│   │           └── tests/
│   ├── local_model_tools/         ← 策略工具包 + 218 测试
│   │   ├── kline_manager.py       ← K线聚合 + REST 引导
│   │   ├── indicator_engine.py    ← 7 指标协调
│   │   ├── signal_generator.py    ← 8 信号规则
│   │   ├── strategies/            ← 5 策略
│   │   ├── stop_manager.py        ← Hard/Trailing/Time Stop + ATR 仓位
│   │   └── strategy_orchestrator.py
│   ├── governance/                ← Phase 2 治理状态机（授权/风控/租约/对账/审计）
│   ├── ai_agents/                 ← H1-H5 AI 治理层
│   ├── risk_control/              ← H0 本地判断
│   └── trade_executor/            ← I 决策租约
├── docker_projects/
│   ├── monitoring_services/       ← Grafana + 5 仪表盘
│   └── trading_services/          ← PostgreSQL
└── helper_scripts/
    ├── start_paper_trading.sh     ← 一键启动
    ├── cron_observer_cycle.sh     ← Observer 自动化
    └── maintenance_scripts/       ← 清理 / 检查脚本
```

---

## Phase 2 治理模組 (T2.01–T2.23)

21 个治理模组全部实现，覆盖 4 个核心状态机 + 17 个扩展模组：

| 类别 | 模组 | 规格 |
|------|------|------|
| 核心状态机 | T2.01 授权状态机、T2.02 风控状态机、T2.03 决策租约、T2.04 对账引擎 | SM-01/SM-02/SM-04/EX-04 |
| 扩展模组 | T2.05–T2.23（OMS、审计持久化、Scout Agent、组合风控、事件模型、感知数据面、学习门控等） | EX-01/EX-02/EX-05/EX-06/DOC-01/DOC-06 |

**关键指标：** 1,522 测试全通过 · 52,211 行代码 · 100% 双语注释 · fail-closed 设计 · 线程安全

**详细报告：** `docs/governance_dev/phase2_execution/`（执行总览 + PM 品质审核 + TW 注释审核 + 23 份变更日志）

---

## 16 条根原则（DOC-01 项目宪法 §5.1–§5.16，不可违背）

**V1 原版（§5.1–§5.10）：**

1. **单一写入口** — 所有订单/执行动作通过唯一受控入口，禁止研究/GUI/脚本直接写入交易所
2. **读写分离** — 研究/推理/学习/GUI/报告：只读或建议。写入权限极度受限、可审计、可锁定
3. **AI 输出 ≠ 即时命令** — AI 输出为建议/租约/解释，必须经 Decision Lease（带时效、可撤销）→ 本地复核 → 执行
4. **策略不能绕过风控** — 所有交易意图必须经 Guardian 审批
5. **生存 > 利润** — 先判断"不会螺旋崩溃"，再判断"能否盈利"
6. **失败默认收缩** — 不确定时默认保守：不开新仓、降频率、降风险、reduce-only
7. **学习 ≠ 改写 Live** — 学习平面与 Live 平面隔离，结果只能产出假设/证据/候选参数/变更提案
8. **交易可解释** — 每笔交易必须可重建：为什么、何时、风控审批、授权、执行、结果
9. **交易所灾难保护** — 本地止损 + 交易所条件单双重防线（DOC-01 §5.9）
10. **认知诚实** — 所有结论必须区分：事实 / 推断 / 假设。外部数据（新闻/情绪）默认推断级

**V2 新增（§5.11–§5.16）：**

11. **Agent 最大自主权** — P0/P1 硬边界内，Agent 完全自主决定：币种、策略、参数、时机。Operator 只设硬边界
12. **持续进化** — 系统必须从交易行为中自动学习，新策略 Paper 验证通过后自动进入 Live
13. **AI 资源成本感知** — 每次 AI 调用计费。cost_edge_ratio ≥ 0.8 → 建议关仓
14. **零外部成本可运行** — 基础运营仅需 L0+L1（Ollama + 免费搜索），云端 AI = 增强层
15. **多 Agent 协作** — OpenClaw 指挥官 + 6 Agent。正式对象通信（非自由文本）。冲突由指挥官按优先级仲裁
16. **组合级风险意识** — 监控关联曝险、策略重叠持仓、资金分配合理性、大盘下行时总曝险收缩

**优先级序：** 账户生存 > 风控治理 > 系统健康 > 审计可追溯 > 人类终审 > 真实 Net PnL > 自主能力进化

---

## 治理架构总览

```
[H0 本地门控]     零成本确定性判断（健康/资格/风险包络）— 永远第一道
[SM-01 授权]      8 状态 · 16 转换 · fail-closed · 终态不可回流
[SM-04 风控]      6 级风险（NORMAL→CIRCUIT_BREAK）· 升级自动/降级需审批
[SM-02 决策租约]   9 状态 · TTL 自动到期 · AI→Lease→复核→执行
[SM-03 OMS]       11 状态订单生命周期 · 对账前不能标记完成
[EX-04 对账引擎]   5 类结果（MATCH/MISMATCH/MISSING）· 触发风控升级
[EX-06 多Agent]    OpenClaw Conductor + Scout/Strategist/Guardian/Analyst/Executor
[EX-05 学习]       L1→L5 五级门控 · 逐级解锁能力 · L5 需 Operator 审批
[EX-07 感知面]     FACT/INFERENCE/HYPOTHESIS 认知标记 · 新鲜度追踪
[DOC-07 审计]      append-only JSONL · 不可修改不可删除 · 自动轮转
```

---

## 工程目标 vs 实现完成度（2026-03-30 TW 工程審核）

### 22 份治理文件合规矩阵

| 规格 | 要求 | 模组 | 代码 | 接入 | 缺口 |
|------|------|------|------|------|------|
| **SM-01** 授权状态机 | 8态/16转/fail-closed/终态不回流 | authorization_state_machine.py | ✅ 完整 | ✅ GovernanceHub | — |
| **SM-02** 决策租约 | 9态/TTL自动到期/租约≠订单 | decision_lease_state_machine.py | ✅ 完整 | ✅ GovernanceHub | — |
| **SM-03** OMS 执行 | 11态订单生命周期/对账前不完成 | oms_state_machine.py | ✅ 完整 | ⬜ 未接入 | Paper 引擎用独立状态名 |
| **SM-04** 风控状态机 | 6级风险/升级自动/降级需审批 | risk_governor_state_machine.py | ✅ 完整 | ✅ GovernanceHub | — |
| **EX-01** 风控边界 | P0/P1/P2 三层 + 组合风控 | risk_manager.py + portfolio_risk_control.py | ✅ 完整 | ⚠ 部分 | 组合风控未接入 |
| **EX-02** OMS 执行边界 | 单一执行入口/授权前置 | oms_state_machine.py + paper_trading_engine.py | ✅ 完整 | ⚠ 部分 | SM-03 未串联 |
| **EX-03** 控制面边界 | system_mode/execution_state 强制 | main_legacy.py（嵌入式） | ⚠ 部分 | ⬜ | 模式变更不传播到治理模组 |
| **EX-04** 对账边界 | 5类结果/自动冻结/审计触发 | reconciliation_engine.py | ✅ 完整 | ✅ GovernanceHub | — |
| **EX-05** 学习边界 | L1→L5 五级门控/自动晋升 | learning_tier_gate.py | ✅ 完整 | ⬜ 未接入 | 主流程从未调用 check_promotion() |
| **EX-06** 多Agent编排 | 6 Agent + Conductor + 正式消息 | multi_agent_framework.py + scout_routes.py | ✅ Scout接入 | ✅ PipelineBridge + REST | ScoutAgent 运行时接入，其馀 4 Agent 待实作 |
| **EX-07** 感知面 | FACT/INFERENCE/HYPOTHESIS 标记 | perception_data_plane.py | ✅ 完整 | ⬜ 未接入 | 市场数据未包装 PerceptionDataObject |
| **DOC-01** 项目宪法 | 16条根原则/6 Agent 角色 | 全系统 | ✅ 已记录 | ⚠ 部分 | 仅 1/6 Agent 实现 |
| **DOC-02** 边界定义 | 层间职责/治理链路 | governance_hub.py | ✅ 完整 | ✅ | — |
| **DOC-03** 字段状态规范 | 枚举/状态值一致性 | 各 SM types 文件 | ✅ 完整 | ✅ | — |
| **DOC-04** Agent能力蓝图 | A-J 能力目标 | 全系统 | ⚠ 部分 | — | 见下方 A-J 完成度 |
| **DOC-05** 真相源矩阵 | 数据源所有权/可信级 | data_source_enforcer.py | ✅ 完整 | ✅ | — |
| **DOC-06** 变更治理 | L1/L2/L3 变更分级 | change_audit_log.py | ✅ 完整 | ⬜ 未接入 | 未与 GovernanceHub 联动 |
| **DOC-07** 审计/事故/熔断 | append-only/不可删/自动轮转 | audit_persistence.py | ✅ 完整 | ✅ GovernanceHub | — |
| **DOC-08** 实施桥梁 | Phase 对照/迁移路径 | governance_dev/ 文档 | ✅ 文档 | — | — |

### A-J 能力目标完成度（DOC-04 蓝图 vs 当前）

| 目标 | 描述 | 完成度 | 关键缺失 |
|------|------|--------|----------|
| A | 自主交易执行 | 65% | AI 治理层仍被绕过（is_authorized 已接但为新加） |
| B | 成本收益感知 | 55% | AI 成本追踪框架在但未实际累计 |
| C | 计算路径智能分级 | 35% | L0+L1 实现，L2 Sonnet/Opus 未接入主链路 |
| D | 自我感知 | 40% | 健康门正常，但 GovernanceHub 状态未暴露到 GUI |
| E | 持续学习 | 15% | E1 观察记录已接，L2-L5 门控未调用 |
| F | 日/周报告 | 30% | 路由存在，无自动化 Cron |
| G | Agent 自主交易 | 60% | 连续亏损暂停已接，但缺多 Agent 协作 |
| H | 对抗性止损 | 65% | ATR 动态止损 + 交易所条件单保护未实现 |
| I | AI 注意力税 | 10% | 框架设计存在，等 AI 咨询接入后生效 |
| J | GUI 控制台 | 80% | 10-Tab 完成，治理仪表盘待加 |

### 剩余缺口（按优先级）

**Critical — 阻塞系统完整性：**

| ID | 缺口 | 现状 |
|----|------|------|
| GAP-C1 | 治理 gate 仍为 warning-only（is_authorized 不拒绝订单） | GovernanceHub 已接入但需确认 fail-closed 生效 |
| GAP-C2 | 跨 SM 级联回调未自动触发（手动调用） | Hub 内实现了回调逻辑但非事件驱动 |
| GAP-C3 | 多Agent系统 ScoutAgent 已接入（需 6 个） | ScoutAgent + MessageBus 已 WIRED，缺 Conductor + 4 Agent |

**High — 影响核心功能：**

| ID | 缺口 |
|----|------|
| GAP-H1 | OMS 状态机（SM-03）未串联到 Paper Trading Engine |
| GAP-H2 | 学习门控（EX-05）主流程未调用 check_promotion() |
| GAP-H3 | 感知面（EX-07）市场数据未包装 PerceptionDataObject |
| GAP-H4 | 控制面 system_mode 变更未传播到 GovernanceHub |
| GAP-H5 | Paper→Live 门控未接入授权工作流 |
| GAP-H6 | TTL 执行器未定期调用（过期租约不会自动终止） |

**Medium：** 影子决策构建器、交易归因、事件队列、组合风控接入、变更审计与审计持久化厘清

### 接入率校准（Batch 4 重新审计 · 2026-03-30）

```
已接入运行时（WIRED · 19/22）:
  ── Phase 3 基础（11 模组）──
  ✅ governance_hub.py             — 4 核心 SM 编排 + 跨 SM 级联 + 审计
  ✅ governance_routes.py          — 8 治理 API 端点
  ✅ risk_manager.py               — 仓位大小 / P0/P1 风控
  ✅ pipeline_bridge.py            — 策略→治理 gate→订单→执行→观察→晋升
  ✅ paper_trading_engine.py       — 订单管理 + is_authorized + acquire_lease
  ✅ market_data_dispatcher.py     — WebSocket 行情分发
  ✅ market_regime.py              — 多时间框架 regime 检测
  ✅ data_source_enforcer.py       — 数据源分类
  ✅ perception_data_plane.py      — 认知标记框架（内部已接）
  ✅ audit_persistence.py          — GovernanceHub 审计写盘
  ✅ reconciliation_engine.py      — GovernanceHub.reconcile() 调用
  ── Round 2 Batch 3 新增（2 模组）──
  ✅ multi_agent_framework.py      — ScoutAgent + MessageBus 接入 PipelineBridge + scout_routes REST
  ✅ trade_attribution.py          — TradeAttributionEngine 接入 PipelineBridge._emit_round_trip()
  ── Batch 4 审计发现已接入（6 模组，原标记 STANDALONE 实为误差）──
  ✅ learning_tier_gate.py         — 注入 ENGINE + GovernanceHub + PipelineBridge 自动晋升
  ✅ ttl_enforcer.py               — 实例化 + 5s daemon sweep + expiry callback
  ✅ protective_order_manager.py   — 注入 ENGINE（自动创建保护性止损单）
  ✅ portfolio_risk_control.py     — 注入 RISK_MANAGER（关联曝险 + 仓位检查）
  ✅ recovery_approval_gate.py     — 实例化（恢复审批门禁）
  ✅ change_audit_log.py           — 注入 GovernanceHub + RiskManager + ENGINE
  ── 共享但非独立模组 ──
  ✅ shadow_decision_builder.py    — 导入 + ShadowDecisionConsumer 创建 + API 路由

真正独立存在（STANDALONE · 3/22）:
  ⬜ oms_state_machine.py          ← SM-03 未串联到 Paper Trading Engine（用独立状态名）
  ⬜ paper_live_gate.py            ← Paper→Live 门控未接入授权工作流
  ⬜ scout_routes.py               ← 代码已就绪，独立于 paper trading 运行时

接入率:  19/22 = 86%（Batch 4 审计后 · 从误标 55% 修正）
合规度:  ~88%
```

### 下一步优先级（继续推进路线图）

**★ 最高优先：修正 0% 胜率（需 1-2 sessions）**

R1 根因分析结论：0% 胜率非 bug，是**风控参数结构性错配**。

| 根因 | 影响 | 修复 |
|------|------|------|
| 3% 追踪止损太紧 | 40-60% 盈利被市场噪音吃掉 | 加宽至 5% 或 ATR 动态计算 |
| 0.11% 手续费（双向 taker） | 每笔需立即 +0.11% 才保本 | 入场改 limit order（maker 0.02%） |
| Squeeze regime 0.3x 时间乘数 | 14h 强制平仓，均值回归未完成 | 调整为 1.0x |
| 无交易前 edge 检查 | 数学不可行的交易也被执行 | 添加 edge > 1.5× fees 过滤器 |

**Phase 4: 多 Agent 推进（需 3-4 sessions）**

1. **Strategist Agent** — 消费 ScoutAgent 情报，产出 TradeIntent，接入 PipelineBridge 替代硬编码策略选择
2. **Guardian Agent** — 消费 EventAlert，动态调整风控参数，与 GovernanceHub.SM-04 联动
3. **Analyst Agent** — 消费 round_trip_complete，驱动 TradeAttribution + Learning Tier 推进
4. **Executor Agent** — 包装 PaperTradingEngine.submit_order()，提供执行质量反馈
5. **Conductor 实例化** — 在 phase2_strategy_routes.py 创建 Conductor 单例，注册全部 Agent，驱动 dispatch_market_event

**Phase 5: 学习管线打通（✅ 已部分完成）**

1. ~~**Learning Tier Gate 接入**~~ ✅ Batch 4 已完成 — PipelineBridge._emit_round_trip() → _try_learning_promotion() → promote_tier()
2. **L2 触发条件** — observations ≥ 500 + win_rate ≥ 20%（当前 0%）→ 需先修正策略胜率
3. **L2→L3 需 Analyst 产出 PatternInsight** — 依赖 Phase 4 完成 Analyst Agent
4. **L4/L5 需 Operator 审批** — 接入 GovernanceHub 授权流

**Phase 6: Paper→Live 准备（需 2+ sessions）**

1. **OMS 串联** — Paper Trading Engine 使用 SM-03 11态生命周期
2. **Paper-Live Gate** — paper_live_gate.py 接入授权工作流
3. **TTL 执行器** — 定期调用，自动终止过期租约
4. **Demo 模式稳定性** — 在 Bybit Demo sandbox 积累足够交易记录

---

## OpenClaw 联合开发路线图

### 当前集成状态（Plan A2）

OpenClaw 与 BybitOpenClaw 通过以下方式互联：

```
┌─────────────┐                    ┌─────────────────────┐
│  OpenClaw   │ ── REST POST ──▶  │  scout_routes.py    │
│  (中枢)     │   /scout/market-  │  (5 端点 · Token 认证)│
│             │   signal          │         │            │
│  Gateway    │   /scout/event-   │         ▼            │
│  :18789     │   alert           │  ScoutAgent          │
└─────────────┘                    │    + MessageBus      │
                                   │         │            │
┌─────────────┐                    │         ▼            │
│  Bybit API  │ ── WebSocket ──▶  │  PipelineBridge     │
│  (行情)     │   price events    │  (on_tick 本地扫描)   │
└─────────────┘                    └─────────────────────┘
```

- **外部情报通道**: OpenClaw → `POST /scout/market-signal` + `POST /scout/event-alert` → ScoutAgent → MessageBus
- **本地市场通道**: Bybit WebSocket → PipelineBridge.on_tick → `_invoke_scout_scan()` (300s 间隔) → ScoutAgent → MessageBus
- **双通道汇聚**: MessageBus → Strategist (intel_object) + Guardian (event_alert)

### OpenClaw 侧需开发

1. **OpenClaw Skill: bybit-scout-push** — 定期扫描新闻/事件，格式化为 IntelObject/EventAlert，POST 到 BybitOpenClaw
2. **OpenClaw Skill: bybit-monitor** — 监控 BybitOpenClaw 健康状态（GET /scout/status），异常时 Telegram 告警
3. **OpenClaw Cron** — 每 30 分钟触发 bybit-scout-push（新闻扫描），每 24 小时触发事件日历检查
4. **认证** — OpenClaw 存储 API Token（`OPENCLAW_API_TOKEN` 环境变量，不可硬编码）

### BybitOpenClaw 侧后续开发

1. **Conductor → OpenClaw 反向通信** — Conductor.broadcast_directive() 通过 webhook 推送到 OpenClaw Gateway
2. **策略建议回传** — Analyst 产出 strategy_proposal → OpenClaw 审核 → SYSTEM_DIRECTIVE 下发
3. **AI 计算预算协调** — OpenClaw 管理 L1.5/L2 云端 AI 配额，BybitOpenClaw 本地 L0/L1
4. **共享 Memory** — OpenClaw Memory 存储交易观察/教训，BybitOpenClaw 可查询

### 联合开发协作流程

```
1. 开发者在 trade-core 使用 Claude Code（SSH/tmux）开发 BybitOpenClaw
2. 开发者在 Cowork 使用 PM 批次分配开发 OpenClaw 技能
3. 两侧通过 REST API + Token 认证互联
4. 测试流程：
   a. BybitOpenClaw 单元测试 → pytest（1800+ tests）
   b. OpenClaw 技能测试 → OpenClaw 内置测试
   c. 集成测试 → 手动触发 POST /scout/market-signal 验证端到端
5. 版本对齐：BybitOpenClaw 的 scout_routes API 版本 = v1，OpenClaw skill 需匹配
```

---

## 硬边界（永远不可违背）

```python
system_mode            = "read_only"      # 不可改
execution_state        = "disabled"       # 不可改
execution_authority    = "not_granted"    # 不可改
live_execution_allowed = False            # 不可改
```

---

## 部署

```bash
# API 服务器（systemd，开机自启）
systemctl --user status openclaw-trading-api    # 端口 8000
systemctl --user status openclaw-gateway        # OpenClaw + Tailscale HTTPS

# Grafana
cd docker_projects/monitoring_services && docker compose up -d   # 端口 3000

# 一键启动 Paper Trading
bash helper_scripts/start_paper_trading.sh
```

---

## 参考文件

| 类别 | 位置 |
|------|------|
| 22 份治理文件（SPEC 源） | Cowork `01_source_documents/` |
| Phase 2 执行总览 + 审核报告 | `docs/governance_dev/phase2_execution/` |
| Phase 3 集成指南 + 安全审核 | `docs/governance_dev/phase3_integration/` |
| T2.01–T2.23 变更日志 | `docs/governance_dev/changelogs/` |
| 治理文件提取参考（8 份） | `docs/governance_dev/governance_extracts/` |
| 完整项目日志 | `CLAUDE.md` |

GitHub: [yunancun/BybitOpenClaw](https://github.com/yunancun/BybitOpenClaw)
