# OpenClaw / Bybit AI Agent 交易系统
# CLAUDE.md — 主项目日志（Claude Code 项目指令文件）
# 备注：本文件即"主日志"，GitHub 根目录 README.md 为"Git 日志"
# 最后更新：2026-03-27

---

## 一、项目定位

长期进化型 AI Agent 自动交易系统。OpenClaw 为中枢、Bybit 为主交易所。

> Agent 自主完成交易决策与执行，对成本与收益有清晰感知，能感知自身状态，能持续学习，在严格风控框架下逐步赢得更高自主权。

人类 Operator 角色：不定时检查、审阅、矫正、批准关键步骤、推动策略演进。

**系统管线：** 市场数据 → H0 本地判断 → H1-H5 AI 治理 → I Decision Lease → 执行适配层 → 学习/归因

**详细能力目标（A-J）见：** `docs/references/2026-03-27--system_reference_handbook.md` 第一章

---

## 二、不可违背的根原则

1. **看 net PnL，不看 gross PnL** — 每笔扣除 AI 成本、手续费、滑点、设备折旧
2. **本地先做，AI 只做高价值部分** — H0 先做，AI 负责 regime 识别等高价值判断
3. **AI 输出不能当即时命令** — AI → Decision Lease（带时效、可撤销）→ 本地复核 → 执行
4. **权限按表现赢得** — 不全局放权，只在已验证的子场景局部放权
5. **先系统健康，后市场判断** — 系统不健康时不行动
6. **失败默认收缩** — fail-closed，不猜测
7. **学习 ≠ 自作主张** — Agent 不能自动改 live 配置、放开权限、修改代码上线
8. **所有结论区分事实 / 推断 / 假设** — 防止乱归因
9. **Agent 最大自主权** — 在风控硬上限内，Agent 自主决定：交易品种、策略类型、仓位大小、入场时机、出场时机。用户只设硬止损上限，不干预具体交易决策

---

## 三、当前系统状态（2026-03-27）

```
测试：646 全通过（218 local_model_tools + 428 control_api）
路由：109 条（+5: login, demo/status, demo/balance, demo/positions, trading page）
GUI：统一控制台 4 Tab（Dashboard + K线图表 + Grafana 监控 + OpenClaw）
Bybit Demo：双重执行（Paper Engine + Bybit sandbox）

Runtime 硬状态：
  system_mode             = read_only
  execution_state         = disabled
  execution_authority     = not_granted
  decision_lease_emitted  = false
  live_execution_allowed  = false
```

---

## 四、章节树

```
A-C  基础层 / OpenClaw 模型层 / 接入前治理      ✅ 完成
D    Readonly Observer 主链                     ✅ 完成
E    Business Event Classification              ✅ 完成
F    Event-Driven Transition Scaffold           ✅ 完成
G    真实业务事件验证层                          ✅ 收口
H0   Local Deterministic Judgment Core          ✅ 完成
H1-H5 AI 治理层                                ✅ 完成
I1-I10 Decision Lease shadow control plane      ✅ 完成（shadow-only）
J    Transition Engine Skeleton                 ✅ shadow-only closeout
K    Paper / Demo Gate                          ✅ design-only gate closed
     Control API v1                             ✅ 104 路由，安全加固完成
     GUI Operator Console v1                    ✅ Learning Cockpit + Net PnL + Paper Trading + 统一控制台
L    Learning / Self-Observability / Net PnL    ✅ 全部完成
     Paper Trading Engine Beta                  ✅ 24 路由 + 影子决策 + 性能指标
     Layer 2 AI 推理引擎                        ✅ 5 模块 + 9 路由 + 79 测试
     全品类风控框架                              ✅ 4 轮审核（P0/P1/P2 + 对抗性止损 + AI 注意力税）
     Phase 2 本地策略工具包                      ✅ 严格审核（K线+6指标+信号+4策略+编排器+11路由）
     Phase 3 管线桥接+止损+信号增强              ✅ 完成（管线接通+StopManager+Regime检测+3新规则+历史K线引导）
     全系统审核 A-K 修复                         ✅ 完成（7C+19H+28M+16L 全修 + 路径统一 + I章去重 + mutator 3x→1x）
     GUI 三层架构                                ✅ 完成（Grafana 监控 + TradingView K线 + Bybit Demo 双重执行 + 登录系统）
     自主交易 Agent                              ✅ 完成（市场扫描器 650 符号 + 策略自动部署 + 多币种支持）
M    Supervised Live Gate                       ⬜ 未开始
N    Constrained Autonomous Live                ⬜ 未开始
```

**⚠️ 任何章节"完成"都不等于 live 放权。执行权限仍未授予。**

---

## 五、架构总览

```
[数据与观察层]           Bybit REST + WS → Postgres + Observer
[H0 本地判断内核]        freshness / health / eligibility / risk envelope
[H1-H5 AI 治理层]       thought_gate / budget / model_router / governor / cost_logging
[I Decision Lease]       shadow-only lease schema + revoke + expiry
[Control API v1]         FastAPI 104 路由（/system /control /input /learning /paper /strategy）
[GUI + Learning]         Operator Console + Learning Cockpit + Paper Trading Dashboard
[Paper Trading Engine]   7 状态生命周期 / 成交模拟 / PnL 计算
[Layer 2 AI 推理]        L0 确定性 → L1 Haiku → L2 Sonnet/Opus + 4 层搜索降级
[风控框架]               P0/P1/P2 三层 + 对抗性止损 + AI 注意力税
[Phase 2 策略]           KlineManager → IndicatorEngine → SignalEngine → 4 策略 → Orchestrator
[Phase 3 管线桥接]           PipelineBridge: Tick Fan-Out + Intent→Order + 执行回调
[止损管理器]                 StopManager: Hard/Trailing/Time Stop + ATR 动态仓位
```

**详细架构 + 各层子模块说明见：** `docs/references/2026-03-27--system_reference_handbook.md`

---

## 六、硬边界（永远不能违背）

```python
system_mode             = "read_only"      # 不可改
execution_state         = "disabled"       # 不可改
execution_authority     = "not_granted"    # 不可改
decision_lease_emitted  = False            # 不可改
max_retries             = 0                # 不可改

# 硬错误：
# - should_call_ai=true 但 invocation 没发生
# - Bybit API timeout / retCode != 0
# - execution authority 意外被授予
# - 伪造 AI 调用或交易活动
# - 自动改 live 配置 / 自动放开 execution authority
```

---

## 七、重要技术记录

### Legal no-call 语义
```python
route_plan = route_skip, should_call_ai = false
# → 合法 observation terminal path，不是失败
```

### Legal idle account 语义
```python
position_count = 0, order_count = 0
# → info/idle，不是 blocker
```

### Authoritative checkers
```bash
# H 链
helper_scripts/maintenance_scripts/bybit_connector/run_i10_canonical_h_chain_recheck.sh
# I 链
helper_scripts/maintenance_scripts/bybit_connector/run_i10_canonical_decision_lease_recheck.sh
```

### 已知文件名修正
| 旧名 | 当前正确名 |
|---|---|
| `bybit_local_risk_envelope_builder.py` | `bybit_local_risk_envelope_gate.py` |
| `bybit_local_trade_eligibility_handoff.py` | `bybit_local_trade_eligibility_handoff_builder.py` |
| `bybit_local_judgment_contract_check.py` | `bybit_local_judgment_final_audit_contract_check.py` |

---

## 八、GitHub 与本地路径

```
GitHub repo:    yunancun/BybitOpenClaw
本地主工作树:   /home/ncyu/BybitOpenClaw/srv
                /home/ncyu/srv  ← symlink

本地-only（不进 Git）：
  settings/          真实 env / secrets
  trading_services/  .env / runtime / connector_logs / decision_packets
```

**工作流：GitHub-first** — 已 push 代码从 GitHub 读，runtime/latest 等本地-only 才用 shell

---

## 九、启动检查

```bash
git status && git log --oneline -5
bash helper_scripts/maintenance_scripts/bybit_connector/run_i10_canonical_h_chain_recheck.sh
bash helper_scripts/maintenance_scripts/bybit_connector/run_i10_canonical_decision_lease_recheck.sh
python3 scripts/bybit_observer_acceptance_check.py
python3 scripts/bybit_runtime_state_resolver.py
```

---

## 十、代码与文档规范

### 新脚本规范
1. 头部 `MODULE_NOTE`（中英双语）
2. 输出 `latest` + `dated` 两份文件
3. 补 `contract check`
4. 更新 `SCRIPT_INDEX.md`

### docs/ 文档规范
1. 文件放对应分类目录（`worklogs/` / `handoffs/` / `decisions/` / `references/`），禁止放 `docs/` 根
2. 命名：`YYYY-MM-DD--功能描述.md`
3. **每次新增必须更新 `docs/README.md` 底部索引**
4. 中文为主 + 英文辅助
5. 完整规范见 `docs/README.md`

---

## 十一、后续推进顺序

```
已完成：
  ✅ A-L 全部章节
  ✅ Paper Trading Engine Beta（24 路由 + 影子决策 + 性能指标）
  ✅ Layer 2 AI 推理引擎（9 路由 + 79 测试）
  ✅ 全品类风控框架（9 路由 + 78 测试 + 4 轮审核）
  ✅ Phase 2 本地策略工具包（11 路由 + 215 测试 + 严格审核）
  ✅ Phase 3 管线桥接+止损+信号增强（8 新文件 + 23 新测试 + 640 总测试）
  ✅ 全系统 A-K 审核修复（7C+19H+28M+16L + 路径统一 + I章去重 + mutator 3x→1x）
  ✅ 路线图 B-I（cron + 加权共识 + volume + Grid 几何 + regime 过滤 + 持久化 + Delta-Neutral）
  ✅ Telegram 告警 + BB Breakout + RSI Divergence + AI Consultation + 远程访问指南
  ✅ GUI 三层架构（Grafana + TradingView + Bybit Demo + 登录系统 + 统一控制台 4 Tab）
  ✅ 自主交易 Agent（市场扫描器 650 符号 + 策略自动部署 5 品种 + Bybit Demo 同步）

下一步（按优先级）：
  GUI 美化完善（面板细节 / 交互优化 / 移动端适配）
  Paper Trading + Bybit Demo 数据对比分析

长期优化（自主交易 Agent 持续改进）：
  - 扫描器策略匹配优化：不只选 trend，根据市场状态平衡 funding_arb / grid / reversion
  - 策略动态退出：连续亏损 N 次自动停用 + 机会消失时移除
  - 仓位智能分配：高分机会分配更大仓位（ATR 动态 + score 加权）
  - 多策略同币种：同一币种可同时跑 Grid + Trend（不同策略类型互补）
  - 策略表现追踪：每个自动部署的策略独立 PnL，定期排名淘汰末位
  - 扫描器学习：记录历史扫描→部署→结果，优化分类评分模型
  - Funding Rate 专扫：独立高频扫描 funding rate（每小时），不等 5 分钟周期
  - 跨交易所套利：接入 Binance 扫描，发现 Bybit-Binance 价差
  - 波动率 regime 切换：市场整体波动率变化时自动调整 max_symbols 和策略偏好

之后：
  M 章：Supervised Live Gate（需先积累 paper trading 数据）
  N 章：Constrained Autonomous Live

Live 前置条件（M/N 前必须核验）：
  - paper trading 数据积累（至少运行数周）
  - 风控框架实测验证
  - freshness 闭合 / recent trade 补全
  - provider pricing table 正式绑定
  - authority grant contract + execution adapter contract
  - 远程访问安全方案（HTTPS + CSP）
```

---

## 十二、参考文档指针

以下内容已从 CLAUDE.md 移出到独立文件。需要时请读取对应文件。

| 内容 | 文件位置 |
|------|---------|
| **系统参考手册**（能力目标 A-J / API 路由列表 / 安全加固 / Paper Trading / GUI / 产品族 / 订单类型 / 风控详细 / 止损设计 / AI 注意力税 / 能力层 / 权限 / 部署 / 历史编号） | `docs/references/2026-03-27--system_reference_handbook.md` |
| 全品类风控框架设计 | `docs/references/2026-03-27--phase1_risk_framework_and_agent_autonomy_design.md` |
| Phase 2 审核报告 | `docs/references/2026-03-27--phase2_strict_audit_report.md` |
| Phase 2 修复路线图 | `docs/references/2026-03-27--phase2_audit_fix_roadmap.md` |
| Phase 2 工程日志 | `docs/worklogs/control_api_gui/2026-03-27--phase2_local_strategy_toolkit_engineering_log.md` |
| Phase 2 第二轮审核报告 | `docs/references/2026-03-27--phase2_round2_strategic_audit_report.md` |
| Phase 3 工程日志 | `docs/worklogs/control_api_gui/2026-03-27--phase3_pipeline_bridge_engineering_log.md` |
| 全系统 A-K 审核报告 | `docs/references/2026-03-27--full_system_audit_A_to_K.md` |
| 全系统审核修复工程日志 | `docs/worklogs/control_api_gui/2026-03-27--full_system_audit_fix_engineering_log.md` |
| Layer 2 实现计划 | `docs/references/2026-03-27--layer2_ai_reasoning_engine_implementation_plan.md` |
| 本地交易逻辑审查 | `docs/references/2026-03-27--local_trading_logic_audit_and_strategy_plan.md` |
| GUI 交接文档 | `docs/handoffs/2026-03-25_api_gui_handoff/` |
| 路线图 B-I 工程日志 | `docs/worklogs/control_api_gui/2026-03-27--roadmap_B_to_I_engineering_log.md` |
| GUI 三层架构工程日志 | `docs/worklogs/control_api_gui/2026-03-27--gui_three_layer_implementation.md` |
| 自主交易 Agent 工程日志 | `docs/worklogs/control_api_gui/2026-03-27--autonomous_agent_scanner_deployer.md` |
| Session 2 总结 | `docs/worklogs/control_api_gui/2026-03-27--session2_audit_fix_and_agent_autonomy.md` |
| Session 3 残留审核修复 | `docs/worklogs/control_api_gui/2026-03-27--session3_remaining_audit_fixes.md` |
| 文档目录规范 + 全量索引 | `docs/README.md` |

---

## 十三、一句话状态

> 截至 2026-03-27：全系统完成。646 测试（0 失败），111 路由，8 信号规则。全部审核问题已修复（214/214）。自主交易 Agent 已上线：扫描 650 个 Bybit 交易对 → 自动部署 5 个策略到最优品种。GUI 三层架构（Grafana + TradingView + Bybit Demo）。Paper Trading + Bybit Demo 双重执行。系统全程 read_only / disabled / not_granted。
