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

## 当前状态 (2026-03-30)

```
系统模式:     read_only（不变）
执行权限:     disabled / not_granted（不变）
测试:         432 control_api + 1,522 governance = 全通过
API 路由:     113 条
信号规则:     8 条（4入场 + 2退出 + 1regime + 1divergence）
策略:         5 类（Grid + MA + BB Reversion + BB Breakout + FundingRate Delta-Neutral）
市场扫描:     650+ 交易对每 5 分钟全扫描
自动部署:     最优 5 品种自动匹配策略
执行模式:     双重执行（Paper Engine + Bybit Demo sandbox）
治理模組:     21 个 Phase 2 模组全部实现并通过审核（T2.01–T2.23）
代码规模:     52,211 行（29,624 实现 + 22,587 测试）
```

**已完成**: A-L + 策略工具包 + 管线桥接 + 全系统审核 + GUI 三层 + 自主交易 Agent + **Phase 2 治理模組 (T2.01–T2.23)**

---

## 项目结构

```
srv/
├── CLAUDE.md                      ← ★ 项目完整上下文
├── docs/                          ← 工程文档（20+ 份日志/审核/设计）
├── program_code/
│   ├── exchange_connectors/
│   │   └── bybit_connector/
│   │       └── control_api_v1/    ← FastAPI 109 路由 + 426 测试
│   │           ├── app/
│   │           │   ├── pipeline_bridge.py       ← 管线桥接器
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

## FA 缺口分析（2026-03-30 架构审核）

> **关键发现：21 个治理模组代码品质优秀（PM 4/5 · TW 9.5/10），但大部分尚未接入运行时主管线。**

### Critical（阻塞系统完整性）

| ID | 缺口 | 模组 | 现状 |
|----|------|------|------|
| GAP-1 | 授权状态机未实例化到运行时 | SM-01 | 代码完整，仅在测试中使用 |
| GAP-2 | 决策租约未实例化到运行时 | SM-02 | 同上 |
| GAP-3 | OMS 状态机未接入 Paper Trading Engine | SM-03 | Paper 引擎使用独立状态名，未走 11 态生命周期 |
| GAP-4 | 对账引擎未在订单完成时调用 | EX-04 | 引擎完整，无集成点 |
| GAP-5 | 学习层级门控从未被调用 | EX-05 | L1→L5 逻辑完整，主流程无调用 |
| GAP-6 | 多Agent框架仅有类定义，无 Conductor 实例 | EX-06 | 消息类完整，无编排实例 |
| GAP-7 | 感知数据面未包装市场数据 | EX-07 | 框架完整，管线传入原始 tick |

### High（影响核心功能）

| ID | 缺口 | 影响 |
|----|------|------|
| GAP-8 | 控制面 system_mode 变更未传播到治理模组 | 授权/风控不知系统模式切换 |
| GAP-9 | Paper→Live 门控未接入授权工作流 | 门控逻辑存在但无人检查 |
| GAP-10 | TTL 执行器未定期调用 | 过期决策租约不会自动终止 |
| GAP-11 | 审计回调未全局注册 | 状态机生成记录但未写盘 |

### Medium

| ID | 缺口 |
|----|------|
| GAP-12 | 影子决策构建器未接入决策租约 BRIDGED 状态 |
| GAP-13 | 风控升级事件未触发授权收缩 |
| GAP-14 | 交易归因模组未在成交时调用 |

### Low

| ID | 缺口 |
|----|------|
| GAP-15 | 事件模型未建立事件队列 |
| GAP-16 | 变更审计日志与审计持久化职责待厘清 |

---

## 进度校准（2026-03-30 FA 评估）

```
已接入运行时（WIRED）:
  ✅ risk_manager.py          — 仓位大小/P0/P1 风控
  ✅ pipeline_bridge.py       — 策略→订单→执行→观察
  ✅ paper_trading_engine.py  — 订单管理 + 成交模拟 + PnL
  ✅ market_data_dispatcher.py — WebSocket 行情分发
  ✅ market_regime.py          — 多时间框架 regime 检测
  ✅ data_source_enforcer.py   — 数据源分类
  ✅ perception_data_plane.py  — 认知标记框架（内部已接）

独立存在（STANDALONE，代码完整但未接入主管线）:
  ⬜ authorization_state_machine.py   ← GAP-1
  ⬜ risk_governor_state_machine.py   ← 代码已完成，需创建 ControlPlaneGovernance 服务
  ⬜ decision_lease_state_machine.py  ← GAP-2
  ⬜ oms_state_machine.py             ← GAP-3
  ⬜ reconciliation_engine.py         ← GAP-4
  ⬜ learning_tier_gate.py            ← GAP-5
  ⬜ multi_agent_framework.py         ← GAP-6
  ⬜ audit_persistence.py             ← GAP-11
  ⬜ paper_live_gate.py               ← GAP-9
  ⬜ ttl_enforcer.py                  ← GAP-10
  ⬜ trade_attribution.py             ← GAP-14
  ⬜ protective_order_manager.py
  ⬜ portfolio_risk_control.py
  ⬜ recovery_approval_gate.py
  ⬜ shadow_decision_builder.py

接入率:  7/22 = 32%（模组已全部实现，接入是下一阶段重点）
```

**下一步（Phase 3 集成优先级）：**

1. 创建 `ControlPlaneGovernance` 服务类 — 实例化 SM-01/SM-04，注册审计回调
2. 接入 OMS 状态机到 Paper Trading Engine — 统一订单生命周期
3. 对账引擎接入订单完成路径 — 成交后自动对账
4. 决策租约接入 pipeline_bridge — AI 输出走正式租约流程
5. 创建治理事件总线 — 风控升级 → 授权收缩 → TTL 强制

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
| T2.01–T2.23 变更日志 | `docs/governance_dev/changelogs/` |
| 完整项目日志 | `CLAUDE.md` |

GitHub: [yunancun/BybitOpenClaw](https://github.com/yunancun/BybitOpenClaw)
