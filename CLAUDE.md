# OpenClaw / Bybit AI Agent 交易系统
# CLAUDE.md — 主项目日志（Claude Code 项目指令文件）
# 备注：本文件即"主日志"，GitHub 根目录 README.md 为"Git 日志"
# 最后更新：2026-03-28（Session 9）

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

## 三、当前系统状态（2026-03-28 Session 8）

```
测试：646 全通过（428 control_api + 218 local_model_tools）
路由：113 条
GUI：10-Tab 专业控制台 + 中文状态 + 悬停提示 + 确认弹窗 + 6 AI 供应商
Bybit Demo：双重执行（Paper Engine + Bybit sandbox）

Paper Trading 运行状态（2026-03-28 Session 8 审核时）：
  session_id              = psess:fe7ac188（运行中）
  net_pnl                 = -$63.78（运行约25小时）
  胜率                    = 0%（fill=684，round_trips=162，win=0）
  fill_count              = 684

Session 8 全面功能审核（A-J 完成度）：
  A. 自主交易执行          = 60%（交易流通，AI治理层全部绕过）
  B. 成本收益感知          = 50%（手续费追踪，AI成本未纳入net_pnl）
  C. 计算路径智能分级      = 30%（AI引擎存在但主链路从未调用）
  D. 自我感知              = 20%→已验证健康门正常（live系统=passed）
  E. 持续学习              ★ 0%→已修复：E1自动写Observation（每轮trip后）
  F. 日/周报告             = 30%（路由存在，无自动化）
  G. Agent自主交易         = 55%→已修复：G1连续亏损自动暂停（10次阈值）
  H. 对抗性止损            = 60%→已修复：H1 ATR动态止损接入（track_position）
  I. AI注意力税            = 0%（待AI咨询接入后自然实现）
  J. GUI控制台             = 80%（Learning Cockpit空=数据来源空）

Session 8 修复（4项）：
  E1: PipelineBridge每轮round-trip自动写Observation到learning_state
  G1: StrategyAutoDeployer.on_trade_result()连续亏损10次自动暂停策略
  H1: PipelineBridge._on_position_open()调用stop_mgr.track_position(ATR动态止损)
  D1: 确认health_gates正常（live系统全部passed），无需代码修复

Session 9 修复（3项）：
  B2: paper_trading_engine._recompute_pnl() 新增 net_realized_pnl 字段（realized - total_fees）
  G3: strategy_auto_deployer._compute_qty() 修复 active_count +1 bug（改用 | {symbol}）
  A2: 新增 on_fill 回调链路（StrategyBase.on_fill → MACrossoverStrategy 实现 → deployer.notify_fill → PipelineBridge 调用），防止仓位状态漂移

决策：win_rate > 20% 前不接入 AI 咨询（C1/I1/A1），避免在随机决策上叠加AI成本

Scanner 规则（最新）：
  MA Crossover 部署过滤   = 24h涨跌幅 > 40% 跳过
  MA Crossover 置信度     = 0.55（扫描器部署）/ 0.50（默认 BTCUSDT）
  Trend 评分上限          = 100（原无限制，防止压制 funding_arb/grid）
  Unknown regime 入场     = 禁止（新上线品种冷启动保护）
  Market Feed 自动重启    = ✅（服务 restart 后自动恢复，无需手动）

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
     GUI 10-Tab 专业控制台                       ✅ 完成（10 Tab + common.js + 双层解释 + 三层信息密度）
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
  ✅ GUI 10-Tab 专业控制台（已完成）
  ✅ 半天数据分析与策略修复（2026-03-28 Session 6）
  ✅ 系统全面审核 + 5项修复（2026-03-28 Session 7）
  ✅ A-J 全面功能审核 + E1/G1/H1 修复（2026-03-28 Session 8）
  Paper Trading 数据继续积累（等胜率数据；新规则+学习机制运行中）
  等胜率 > 20% 后：接入 AI 咨询（C1/I1/A1）
  Paper Trading + Bybit Demo 数据对比分析
  GUI 细节打磨（移动端适配 / 图表增强 / 实时 PnL 折线图）

待处理问题（已记录，非紧急）：
  - MACrossoverStrategy 双边持仓状态漂移（需 on_fill 回调）
  - StopManager 与 RiskManager 双重止损（需统一 Stop 逻辑）
  - realized_pnl 毛利问题（添加 net_realized_pnl 字段）
  - StrategyAutoDeployer active_count +1（影响小）
  - Learning Cockpit GUI 数据展示（依赖 E1 数据积累后再完善）
  - RiskManager daily loss 跨天不重置（影响小）

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

OpenClaw 开发潜力（通信层 → 信息增强层）：
  第一步（近期）：
    - Telegram 告警接通：交易信号/止损触发/异常推送到手机
    - Cron 日报：每天 UTC 0:00 自动生成持仓/PnL/策略表现日报 → 推送 Telegram
  第二步（数据积累期间）：
    - web-pilot 新闻扫描：每 30 分钟抓 CoinDesk/Bybit 公告 → 情绪打分 → 注入信号引擎
    - 事件驱动信号：FOMC/CPI → 自动降杠杆收紧止损；上币公告 → 提前部署策略
    - Cron 小时简报 → 存入 Memory 知识库积累市场认知
  第三步（长期）：
    - 多 Agent 架构：研究员（新闻收集）+ 监控员（持仓巡检）+ 分析师（策略优化）
    - Twitter/X 情绪信号（xurl skill）→ 与技术信号交叉验证
    - 跨交易所价差监控（web-pilot 抓 Binance/OKX 价格）→ 套利信号
    - Canvas 实时面板：Agent 自主生成可视化仪表盘
    - Browser 自动化：登录 Bybit 网页端核对实际订单/持仓
  OpenClaw 已有能力（v2026.3.24）：
    - 51 内置 skill（8 已就绪），23+ 通信通道，Cron + Heartbeat 定时
    - web-pilot 网页搜索/抓取（免费），Browser 自动化，Memory 向量检索
    - Multi-Agent 路由（隔离工作空间），Canvas A2UI 实时渲染
    - 当前角色：通信层（嘴巴和耳朵），不参与 AI 调用和交易决策

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

### 参考文档（references/）

| 内容 | 文件位置 |
|------|---------|
| **系统参考手册**（能力目标 A-J / API 路由列表 / 安全加固 / Paper Trading / GUI / 产品族 / 订单类型 / 风控详细 / 止损设计 / AI 注意力税 / 能力层 / 权限 / 部署 / 历史编号） | `docs/references/2026-03-27--system_reference_handbook.md` |
| 全品类风控框架设计 | `docs/references/2026-03-27--phase1_risk_framework_and_agent_autonomy_design.md` |
| Phase 2 严格审核报告（8C+15H+25M+19L） | `docs/references/2026-03-27--phase2_strict_audit_report.md` |
| Phase 2 修复路线图 | `docs/references/2026-03-27--phase2_audit_fix_roadmap.md` |
| Phase 2 第二轮审核报告（实战适用性） | `docs/references/2026-03-27--phase2_round2_strategic_audit_report.md` |
| 全系统 A-K 审核报告（7C+19H+28M+16L） | `docs/references/2026-03-27--full_system_audit_A_to_K.md` |
| Layer 2 AI 推理引擎实现计划 | `docs/references/2026-03-27--layer2_ai_reasoning_engine_implementation_plan.md` |
| 本地交易逻辑审查 + 策略补齐计划 | `docs/references/2026-03-27--local_trading_logic_audit_and_strategy_plan.md` |
| 远程访问指南（Tailscale + 安全配置） | `docs/references/2026-03-27--remote_access_guide.md` |

### 工作日志（worklogs/control_api_gui/）— 按时间顺序

| 内容 | 文件位置 |
|------|---------|
| Layer 2 设计会话：Provider 调研 + 4 层降级 + 预算 | `docs/worklogs/control_api_gui/2026-03-27--layer2_ai_engine_design_session.md` |
| Phase 1 早期工程日志（S1-S5 修复 + P0/P1/P2 风控 + 8 路由） | `docs/worklogs/control_api_gui/2026-03-27--phase1_risk_framework_implementation.md` |
| Phase 1 中期工程日志（1-2 轮审核后） | `docs/worklogs/control_api_gui/2026-03-27--phase1_complete_engineering_log.md` |
| ★ Phase 1 最终审核版（4 轮审核 + 25 修复 + 405 测试 + 93 路由） | `docs/worklogs/control_api_gui/2026-03-27--phase1_final_audited_engineering_log.md` |
| Pre-Phase1 审核修复（metrics 重写 + SSRF + race fix） | `docs/worklogs/control_api_gui/2026-03-27--pre_phase1_audit_fixes.md` |
| ★ Phase 2 完整工程日志（K线+6指标+信号+4策略+编排器+11路由） | `docs/worklogs/control_api_gui/2026-03-27--phase2_local_strategy_toolkit_engineering_log.md` |
| Phase 3 工程日志（管线桥接+止损管理器+信号增强） | `docs/worklogs/control_api_gui/2026-03-27--phase3_pipeline_bridge_engineering_log.md` |
| ★ 全系统审核修复工程日志（214/214 问题全修） | `docs/worklogs/control_api_gui/2026-03-27--full_system_audit_fix_engineering_log.md` |
| ★ 路线图 B-I 实现日志（cron+共识+volume+Grid+regime+持久化+Delta-Neutral） | `docs/worklogs/control_api_gui/2026-03-27--roadmap_B_to_I_engineering_log.md` |
| 远程访问 + 安全加固工程日志 | `docs/worklogs/control_api_gui/2026-03-27--remote_access_and_security_hardening.md` |
| GUI 三层架构工程日志（Grafana+TradingView+Demo+登录） | `docs/worklogs/control_api_gui/2026-03-27--gui_three_layer_implementation.md` |
| ★ 自主交易 Agent 工程日志（650 符号扫描+自动部署） | `docs/worklogs/control_api_gui/2026-03-27--autonomous_agent_scanner_deployer.md` |
| ★★ 完整工作日总结（Session 1-2，13 commits，644 测试） | `docs/worklogs/control_api_gui/2026-03-27--full_day_session_summary.md` |
| Session 2 总结（GUI三层+Demo+Agent+R1-R5+第4轮审核） | `docs/worklogs/control_api_gui/2026-03-27--session2_audit_fix_and_agent_autonomy.md` |
| Session 3 残留审核全修（时间戳+浮点容差+Kahan+646测试） | `docs/worklogs/control_api_gui/2026-03-27--session3_remaining_audit_fixes.md` |
| ★ GUI 10-Tab 全面重构（common.js+8新Tab+双层解释） | `docs/worklogs/control_api_gui/2026-03-27--gui_10tab_restructure.md` |
| ★★ Session 4 GUI 专业控制台（6 commits+17 files+3964 行+6 AI 供应商） | `docs/worklogs/control_api_gui/2026-03-27--session4_gui_10tab_professional_console.md` |
| Session 5 管线启动验证 + OpenClaw 能力深挖 + 服务自动重启确认 | `docs/worklogs/control_api_gui/2026-03-27--session5_pipeline_launch_and_openclaw_analysis.md` |
| ★ Session 6 半天数据分析：胜率0%根因 + 4项修复（扫描器+置信度+.orig stub+DB表） | `docs/worklogs/control_api_gui/2026-03-28--session6_halfday_data_analysis_and_fixes.md` |
| ★★ Session 7 系统全面审核 + 5项修复（市场流自动重启+regime过滤+trend cap+时间驱动+confidence） | `docs/worklogs/control_api_gui/2026-03-28--session7_system_audit_and_fixes.md` |
| ★★★ Session 8 A-J 全面功能审核报告（胜率0%根因/学习系统空置/止损未接入） | `docs/worklogs/control_api_gui/2026-03-28--session8_functional_audit_report.md` |

### 交接与索引

| 内容 | 文件位置 |
|------|---------|
| GUI 交接文档（Control API v1 + GUI v1 阶段交接） | `docs/handoffs/2026-03-25_api_gui_handoff/` |
| 文档目录规范 + 全量索引 | `docs/README.md` |

---

## 十三、一句话状态

> 截至 2026-03-28 Session 9：646 测试通过，113 路由。Session 9 修复 3 项：B2 新增 net_realized_pnl 字段（扣费后净实现盈亏）、G3 修复仓位计算 active_count +1 bug（策略分配更准确）、A2 新增 on_fill 回调链路（StrategyBase→MACrossoverStrategy→deployer→bridge），防止 MA 策略仓位状态漂移。系统全程 read_only / disabled / not_granted。待处理问题见第十一章。
