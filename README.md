# OpenClaw / Bybit AI Agent Trading System
<!-- Git 日志 — 项目入口。主日志见 CLAUDE.md -->

AI Agent 自动交易系统 — 自主扫描 650+ 交易对，智能部署策略，双重执行（Paper + Bybit Demo）。

---

## 🖥️ GUI 访问（Tailscale 网络内）

| 地址 | 功能 |
|------|------|
| **[http://trade-core:8000](http://trade-core:8000)** | **统一控制台**（登录后进入 11 Tab 视图） |
| [http://trade-core:3000](http://trade-core:3000) | Grafana 运营监控仪表盘 |
| [https://trade-core.tail358794.ts.net](https://trade-core.tail358794.ts.net) | OpenClaw Gateway |

### 统一控制台 Tab（11 Tab，左→右）

| Tab | 内容 |
|-----|------|
| 📊 系统总览 / Overview | 系统状态 + 章节状态 + Paper Trading 概览 |
| 🔒 实盘交易 / Live | **锁定占位**（前置条件 8 项 + Phase 路线图，Phase 4 后开放） |
| 🧪 测试交易 / Test | **子 Tab 包装器**：纸面交易 / Bybit Demo（iframe 独立加载） |
| 📈 K线图表 / Charts | TradingView K线 + 信号标记 + 策略面板 |
| ⚙ 策略中心 / Strategy | 策略部署 + 扫描器 + 品种管理 |
| 🛡 风控止损 / Risk | P0/P1/P2 风控参数 + 止损配置 |
| 🤖 AI 引擎 / AI | Layer2Engine + 模型选择 + 成本追踪 |
| 📖 学习系统 / Learning | Learning Cockpit + 观察统计 + 晋升状态 |
| ⚖ 治理控制 / Governance | GovernanceHub 4 SM + 授权 + 租约 + 对账 |
| 🔍 监控 / Monitor | Grafana 嵌入 + 系统健康 |
| ⚙ 设置 / Settings | 参数配置 + 计划重启（弹窗修复）|

---

## 当前状态 (2026-04-03 · Phase R-04 完成，Week 8 决策点就绪)

```
系统模式:     demo_only（Operator 授权 2026-03-31 · 仅限 Paper + Bybit Demo）
执行权限:     disabled / not_granted（live 前必须保持）· live_execution_allowed = False
测试:         3,839 Py passed + 555 Rust passed（全绿 0 failed · 0 errors）
API 路由:     131+ 条（含 8 治理 + 5 Scout + 4 实验 + 2 进化端点）
代码:         ~67,000 行（Python ~50k + Rust ~17k）
策略:         5 类 × 双实现（Python + Rust）
三品类:       ✅ linear / spot / inverse 全部就绪
治理:         GovernanceHub (Python) + GovernanceCore (Rust) · fail-closed 已验证
Rust 引擎:    ✅ R-00~R-06 完成 · R-07 灰度工具就绪
              IPC: file-read (pipeline_snapshot.json) + 53 IPC 集成测试 + 回滚 SLA <100ms
              灰度: CanaryRecord + Comparator (3 层容差) + Watchdog (3 振回滚) + Drill 脚本
              tick 延迟: <100μs 可达（E5 评估 ~7-25μs 正常路径）
Phase 0-3:    ✅ 全部完成 + L1/L2 接口冻结
Rust R-00~04: ✅ 全部完成（R-05 Week 8 决策点待评估）
认证安全:     ✅ HttpOnly cookie + 安全 HTTP 响应头 + XSS 修复
L1 本地推理:  Ollama 9B（think=False，~1.9s）/ 27B（复杂任务，AnalystAgent）
5-Agent:      Scout + Strategist + Guardian + Analyst + Executor 全部运行
安全评级:     0 CRITICAL / 0 HIGH（E3 Rust 审计 2026-04-03）
```

**完成度（2026-04-03 · Phase R-04 后校准）**

| 维度 | 已完成 | 总量 | 进度 |
|------|--------|------|------|
| 代码量 | ~65,000 行（Py 50k + Rs 15k） | ~73,000 行 | 88% |
| 业务功能 | — | — | 95% |
| 工时 | ~62d | ~147d | 42% |
| 测试 | 4,220（Py 3703 + Rs 517） | ~4,500 | 94% |

| 环节 | 完成度 | 说明 |
|------|--------|------|
| 自动扫描 | 90% | ScoutWorker 30min 定时扫描已接通 |
| 策略选择 | 50% | Regime-aware 策略选择已实现（C4）；ATR 双窗口保守估计 |
| AI 风险评估 | 60% | H1-H5 全部接通 + 成本感知入场门槛（cost_gate） |
| 下单 | 85% | 治理 gate + OMS SM-03 已串联 |
| 止损 | 80% | ATR 动态止损 + 追踪止损成本约束；缺交易所条件单双重防线 |
| 学习 | 30% | E1 观察 + L2 自动触发 + Sunday cron；L3-L5 待推进 |
| 进化 | 35% | EvolutionEngine + Scheduler 完成；学习反馈闭环待接通 |

**亮点**：治理 fail-closed 一流 · P0/P1/P2 风控真实拒绝 · 4,220 测试 · 5 Agent 运行 · Rust 引擎 tick <100μs · 6 角色审计通过 · QC 量化审查驱动

**开发路线图**

| Phase | 内容 | 状态 |
|-------|------|------|
| 0 | Batch 9B-9D 学习闭环 + 管线连通 + 策略 Edge 验证 | ✅ 完成 |
| 1 | Agent 感知工具箱 + 认知三模组 + R-00 并行 | ✅ 完成 |
| 2 | 策略 V2 + Agent 整合 + L1 接口冻结 | ✅ 完成 |
| 3 | Claude API + 四阶段放权 + L2 接口冻结 | ✅ 完成 |
| **R-00~R-04** | **Rust 引擎：types + IPC + core 24 模组 + engine 12 模组** | **✅ 完成** |
| **R-05** | **★ Week 8 硬决策点（Go/No-Go）** | **🔄 待评估** |
| R-06 | Python IPC 改造（W9-10） | ⬜ 待开始 |
| R-07 | 灰度验证 + 稳定观察（W11-14） | ⬜ 待开始 |
| Live | Paper Trading 21 天 + Live 准备 | ⬜ 待开始 |

**详细报告**：`docs/governance_dev/audits/` 目录下各审计报告

---

## 项目结构

```
srv/
├── CLAUDE.md                      ← ★ 项目完整上下文
├── docs/                          ← 工程文档（20+ 份日志/审核/设计）
├── program_code/
│   ├── exchange_connectors/
│   │   └── bybit_connector/
│   │       └── control_api_v1/    ← FastAPI 126+ 路由 + 3,700+ 测试
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
│   ├── local_model_tools/         ← 策略工具包 + 策略/指标/信号引擎
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
├── rust/                          ← ★ Rust 交易引擎（R-00~R-04）
│   ├── Cargo.toml                 ← Workspace: 4 crates
│   ├── openclaw_types/            ← 10 shared types + serde (36 tests)
│   ├── openclaw_core/             ← 24 modules: SM/indicators/signals/risk/backtest (403 tests)
│   ├── openclaw_engine/           ← 12+ modules: tick pipeline/strategies/paper state/canary (116 tests)
│   ├── openclaw_pyo3/             ← PyO3 cdylib bridge
│   └── schemas/                   ← Golden JSON schema (10 types)
├── helper_scripts/
│   ├── start_paper_trading.sh     ← 一键启动
│   ├── cron_observer_cycle.sh     ← Observer 自动化
│   ├── cron_daily_report.sh       ← 日报 → Telegram（UTC 0:00）
│   └── maintenance_scripts/       ← 清理 / 检查脚本
└── docs/
    ├── rust_migration/            ← 8 阶段执行文件（R-00~R-07）
    └── worklogs/                  ← Session 工作日志
```

---

## Phase 2 治理模組 (T2.01–T2.23)

21 个治理模组全部实现，覆盖 4 个核心状态机 + 17 个扩展模组：

| 类别 | 模组 | 规格 |
|------|------|------|
| 核心状态机 | T2.01 授权状态机、T2.02 风控状态机、T2.03 决策租约、T2.04 对账引擎 | SM-01/SM-02/SM-04/EX-04 |
| 扩展模组 | T2.05–T2.23（OMS、审计持久化、Scout Agent、组合风控、事件模型、感知数据面、学习门控等） | EX-01/EX-02/EX-05/EX-06/DOC-01/DOC-06 |

**关键指标：** 4,220 测试通过（Py 3703 + Rs 517）· ~65,000 行代码（Py+Rs）· 100% 双语注释 · fail-closed 设计 · 线程安全（Py）/ 零锁 single-owner（Rs）

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
12. **持续进化** — 系统必须从交易行为中自动学习（当前 demo 阶段：Paper 验证→参数进化，live 自动部署待 Phase 3 放权框架）
13. **AI 资源成本感知** — 每次 AI 调用计费。cost_edge_ratio ≥ 0.8 → 建议关仓
14. **零外部成本可运行** — 基础运营仅需 L0+L1（Ollama + 免费搜索），云端 AI = 增强层
15. **多 Agent 协作** — 5 Agent（Scout/Strategist/Guardian/Analyst/Executor）+ Conductor 编排，正式对象通信
16. **组合级风险意识** — 监控关联曝险、策略重叠持仓、资金分配合理性、大盘下行时总曝险收缩

**优先级序：** 账户生存 > 风控治理 > 系统健康 > 审计可追溯 > 人类终审 > 真实 Net PnL > 自主能力进化

**实施准则：** 认知调制 ≠ 能力限制 — Agent 压力下更审慎的方式是提高决策门槛，不是关闭能力。虚拟稀缺性被明确否决。（衍生自原则 #11）

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

## 工程目标 vs 实现完成度（2026-04-03 更新）

### 22 份治理文件合规矩阵

| 规格 | 要求 | 代码 | 接入 |
|------|------|------|------|
| **SM-01** 授权状态机 | 8态/16转/fail-closed | ✅ | ✅ GovernanceHub |
| **SM-02** 决策租约 | 9态/TTL自动到期 | ✅ | ✅ GovernanceHub |
| **SM-03** OMS 执行 | 11态订单生命周期 | ✅ | ✅ Paper Engine 映射 |
| **SM-04** 风控状态机 | 6级风险 | ✅ | ✅ GovernanceHub |
| **EX-01** 风控边界 | P0/P1/P2 三层 | ✅ | ✅ |
| **EX-02** OMS 执行边界 | 单一执行入口 | ✅ | ✅ SM-03 串联 |
| **EX-04** 对账边界 | 5类结果 | ✅ | ✅ GovernanceHub |
| **EX-05** 学习边界 | L1→L5 五级门控 | ✅ | ✅ 自动晋升接入 |
| **EX-06** 多Agent编排 | 5 Agent + Conductor | ✅ | ✅ 5 Agent 运行 |
| **DOC-07** 审计 | append-only JSONL | ✅ | ✅ GovernanceHub |

**接入率: 20/22 = 91%** · 合规度 ~90%

未接入：`paper_live_gate.py`（Paper→Live 门控）、`scout_routes.py`（独立于 paper trading 运行时）

### A-J 能力目标完成度

| 目标 | 描述 | 完成度 | 说明 |
|------|------|--------|------|
| A | 自主交易执行 | 70% | 治理 gate fail-closed + 5 Agent + OMS 串联 |
| B | 成本收益感知 | 65% | AI 成本追踪 + 成本感知入场门槛（cost_gate） + round-trip 真实费用 |
| C | 计算路径智能分级 | 40% | L0+L1 实现，L2 框架就绪 |
| D | 自我感知 | 50% | H0 Gate + GovernanceHub 状态 API |
| E | 持续学习 | 35% | E1 观察 + L2 自动触发 + Evolution；L3-L5 待推进 |
| F | 日/周报告 | 35% | 路由存在 + daily cron |
| G | Agent 自主交易 | 65% | 5 Agent 运行 + Conductor 编排 |
| H | 对抗性止损 | 75% | ATR 双窗口 + 追踪止损成本约束；缺交易所条件单 |
| I | AI 注意力税 | 15% | 框架设计存在 |
| J | GUI 控制台 | 85% | 11-Tab 完成 |

### 剩余重点缺口

| 优先级 | 缺口 |
|--------|------|
| P0 | 学习反馈闭环未接入决策路径（Batch 9B U-01） |
| P0 | 进化参数自动重部署（Batch 9B U-02） |
| P1 | 交易所条件单 SL/TP（原则 9 双重防线） |
| P1 | H0 Gate shadow 模式观察 |
| P1 | Scanner→Deployer 自动接通 |
| P2 | Paper→Live 门控接入授权工作流 |
| P2 | L5 meta-learning 未实现 |

详细任务清单见 `TODO.md`（Batch 9B-9D）

---

## OpenClaw 集成

> OpenClaw 定位：通信+运维层，不碰交易决策。Python 本地 = 交易 Agent 核心。

### 当前集成架构

```
┌─────────────┐                    ┌─────────────────────┐
│  OpenClaw   │ ── REST POST ──▶  │  scout_routes.py    │
│  (中枢)     │   /scout/market-  │  (5 端点 · Token 认证)│
│  Gateway    │   signal + alert  │         ▼            │
│  :18789     │                    │  ScoutAgent+MessageBus│
└─────────────┘                    │         ▼            │
┌─────────────┐                    │  PipelineBridge     │
│  Bybit API  │ ── WebSocket ──▶  │  (on_tick 本地扫描)   │
└─────────────┘                    └─────────────────────┘
```

### 后续整合计划（非紧急）

| ID | 内容 | 优先级 |
|----|------|--------|
| OC-1 | Webhook 告警通道（异常→OpenClaw→Telegram） | 高 |
| OC-2 | Telegram 通道配置 | 高 |
| OC-3 | 多通道分级告警（P0→紧急群 / P1→常规群） | 中 |
| OC-4 | MCP PostgreSQL 接入（自然语言查交易数据） | 中 |
| OC-5 | Cron 精细化健康心跳（待 OpenClaw --exec flag） | 低 |
| OC-6 | Sub-agent 异步回测（周频 Evolution 网格搜索） | 低 |
| WS-1 | FastAPI WebSocket/SSE 实时推送（替代 30s 轮询） | 中 |

详细方案见 `TODO.md` "OpenClaw 深度整合" 章节

---

## 硬边界（永远不可违背）

```python
system_mode            = "demo_only"      # Operator 授权 2026-03-31（Paper + Bybit Demo only）
execution_state        = "disabled"       # 不可改（live 前必须保持）
execution_authority    = "not_granted"    # 不可改（live 前必须保持）
live_execution_allowed = False            # 不可改（live 防护硬边界）
```

---

## 部署

**跨平台**：项目必须随时可部署至 macOS（路径不硬编码 / LLM 抽象 / systemd→launchd 可迁移 / 无 Linux-only 依赖）。详见 CLAUDE.md §七。

```bash
# API 服务器（Linux: systemd，开机自启；macOS: launchd 可迁移）
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
| 完整项目指令 | `CLAUDE.md` |
| 当前工作计划 | `TODO.md` |
| 审计报告 | `docs/governance_dev/audits/` |
| QC 量化审查 | `docs/CCAgentWorkSpace/QC/workspace/reports/` |
| 工作日志 | `docs/worklogs/` |
| 变更历史 | `docs/CLAUDE_CHANGELOG.md` |
| 治理文件（SPEC 源） | Cowork `01_source_documents/` |
| Phase 2/3 执行记录 | `docs/governance_dev/phase2_execution/` / `phase3_integration/` |

GitHub: [yunancun/BybitOpenClaw](https://github.com/yunancun/BybitOpenClaw)
