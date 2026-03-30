# OpenClaw / Bybit AI Agent 交易系统
# CLAUDE.md — 主项目日志（Claude Code 项目指令文件）
# 备注：本文件即"主日志"，GitHub 根目录 README.md 为"Git 日志"
# 最后更新：2026-03-31（Phase 0 Round 2.5 审计 · 2 P0 修复 · 287-spec gap 分析 · 4-Phase 路线图）

---

## 一、项目定位

长期进化型 AI Agent 自动交易系统。OpenClaw 为中枢、Bybit 为主交易所。

> Agent 自主完成交易决策与执行，对成本与收益有清晰感知，能感知自身状态，能持续学习，在严格风控框架下逐步赢得更高自主权。

人类 Operator 角色：不定时检查、审阅、矫正、批准关键步骤、推动策略演进。

**系统管线：** 市场数据 → H0 本地判断 → H1-H5 AI 治理 → I Decision Lease → 执行适配层 → 学习/归因

**详细能力目标（A-J）见：** `docs/references/2026-03-27--system_reference_handbook.md` 第一章

---

## 二、16 条根原则（DOC-01 项目宪法 §5.1–§5.16，不可违背）

**V1 原版（§5.1–§5.10）：**
1. **单一写入口** — 所有订单/执行动作通过唯一受控入口
2. **读写分离** — 研究/GUI/学习：只读。写入权限极度受限、可审计、可锁定
3. **AI 输出 ≠ 即时命令** — AI → Decision Lease（带时效、可撤销）→ 本地复核 → 执行
4. **策略不能绕过风控** — 所有交易意图必须经 Guardian 审批
5. **生存 > 利润** — 先判断"不会螺旋崩溃"，再判断"能否盈利"
6. **失败默认收缩** — 不确定时默认保守：不开新仓、降频率、降风险
7. **学习 ≠ 改写 Live** — 学习平面与 Live 平面隔离
8. **交易可解释** — 每笔交易必须可重建：为什么、何时、风控审批、授权、执行、结果
9. **交易所灾难保护** — 本地止损 + 交易所条件单双重防线
10. **认知诚实** — 所有结论区分事实 / 推断 / 假设

**V2 新增（§5.11–§5.16）：**
11. **Agent 最大自主权** — P0/P1 硬边界内，Agent 完全自主决定：币种、策略、参数、时机
12. **持续进化** — 系统必须从交易行为中自动学习
13. **AI 资源成本感知** — 每次 AI 调用计费，cost_edge_ratio ≥ 0.8 → 建议关仓
14. **零外部成本可运行** — 基础运营仅需 L0+L1（Ollama + 免费搜索）
15. **多 Agent 协作** — OpenClaw 指挥官 + 6 Agent，正式对象通信
16. **组合级风险意识** — 监控关联曝险、策略重叠持仓、资金分配合理性

**优先级序：** 账户生存 > 风控治理 > 系统健康 > 审计可追溯 > 人类终审 > 真实 Net PnL > 自主能力进化

---

## 三、当前系统状态（2026-03-31 Phase 0 Cowork Round 2.5 审计后）

```
测试：2,227 passed / 0 failed / 2 skipped（Phase 0 审计修复后基准线）
路由：126+ 条（含 8 治理 + 5 Scout 端点）
治理：GovernanceHub 4 SM 已接入运行时（SM-01/SM-02/SM-04/EX-04），fail-closed 已验证
GUI：10-Tab 专业控制台 + 中文状态 + 悬停提示 + 确认弹窗 + 6 AI 供应商
Bybit Demo：双重执行（Paper Engine + Bybit sandbox）
L1 本地推理：Ollama HTTP 客户端 + Qwen 3.5 27B（就绪）
5-Agent 体系：Scout + Strategist + Guardian + Analyst + Executor 全部运行（Phase 0 修复 AnalystAgent subscribe bug）

★ Round 2 冷酷功能审核结论（2026-03-30 PM 4 路并行代码级审计）：

  代码完成度            ≈ 75%
  业务功能真正能用      ≈ 32%（自动扫描→策略→风险→下单→止损→学习→进化 全链路评估）

  逐环节完成度：
    自动扫描              = 85%（650+ 对全扫描可用，Scout 情报无消费者）
    策略选择              = 40%（标准技术指标，无 AI、无回测、无动态仓位）
    AI 风险评估           = 20%（H0 规则引擎强，H1-H5 AI 层完全断开）
    下单                  = 90%（治理 gate + OMS SM-03 + ExecutorAgent 包装，Batch 11）
    止损                  = 90%（本地 3 类止损 + 交易所条件单双重防线，Batch 11）
    学习                  = 25%（E1 观察 + L2 自动触发 + Sunday cron，Batch 10）
    进化                  = 30%（PaperLiveGate 已部署，11 项准入评估 + API 端点 + 日报自动化，无策略自动优化）

  关键发现：
    ✅ 治理 fail-closed 一流（is_authorized 真实拒绝订单，acquire_lease fail-closed）
    ✅ P0/P1/P2 风控真实执行（check_order_allowed 返回 False 阻止订单）
    ✅ 异常处理防御性、核心代码零 except:pass
    ✅ 5/6 Agent 已实现（Scout/Strategist/Guardian/Analyst/Executor，仅 Conductor 编排待完善）
    ✅ Conductor 注册 5 个 Agent，MessageBus 有多订阅者
    ✅ ExecutorAgent 接入管线：APPROVED_INTENT→submit_order()→EXECUTION_REPORT（Batch 11）
    ✅ L2 AI Engine 自动触发（Batch 10：observations≥200 auto + Sunday cron）
    ❌ Perception Plane register_data() 零调用
    ✅ OMS SM-03 已串联（Batch 10：Paper 7-state→OMS 11-state 映射，fail-closed）
    ✅ PaperLiveGate 已部署（Batch 12：11 项准入评估 + GET/POST API + ChangeAuditLog 联动）
    ✅ E2E 冒烟测试 35 项（A1-A10 审计项全覆盖，Batch 12）
    ✅ 日报自动化（cron_daily_report.sh → Telegram，UTC 0:00）
    ❌ 策略层标准 RSI/MACD/MA，无可证明的 alpha

  详细审核报告：docs/governance_dev/audits/2026-03-30--round2_cold_functional_audit.md
  修复计划：docs/governance_dev/2026-03-30--round2_fix_plan_batches_7_12.md

★ Phase 0 Cowork Round 2.5 审计（2026-03-31 · 3-agent 并行审计）：
  P0 修复：MessageBus.subscribe() 3→2 参数 bug（AnalystAgent 静默失败）
  P0 修复：layer2_engine "not worth" 文本解析 bug（"worth" 子串匹配，新增否定模式排除）
  P1 修复：3 个 Ollama 测试（大小写不符 + 错误消息 + 逻辑修复）
  清理：6 处 except-swallowing（governance_hub / pipeline_bridge / risk_routes 添加日志）
  287 条治理规格 Gap 分析：76% 已实施（67A + 18B + 8C + 2D）
  关键缺失：H0 Gate（DOC-02 指定 <1ms 确定性门控）· 回测引擎 · L3-L5 学习
  4-Phase 开发路线图已制定（详见 §11）
  详细报告：docs/governance_dev/audits/2026-03-31--gap_analysis_287_specs.md

历史 Batch 3-12 + Session 8-12 + Phase 3 详细记录已归档至：
  → docs/worklogs/control_api_gui/2026-03-31--round2_batch_records_archive.md

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
     Phase 2 治理模組 T2.01–T2.23               ✅ 完成（21 模组 + PM/TW 双审核通过）
     Phase 3 GovernanceHub 集成                  ✅ 完成（Hub+8路由+4SM接入+安全审核+46测试）
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
[GovernanceHub]          ★ SM-01授权 + SM-04风控 + SM-02租约 + EX-04对账（跨SM级联）
[H1-H5 AI 治理层]       thought_gate / budget / model_router / governor / cost_logging
[I Decision Lease]       GovernanceHub.acquire_lease() / release_lease()
[Control API v1]         FastAPI 121+ 路由（含 /governance 8 端点）
[GUI + Learning]         Operator Console + Learning Cockpit + Paper Trading Dashboard
[Paper Trading Engine]   7 状态生命周期 / 成交模拟 / PnL / 治理 gate 接入
[Layer 2 AI 推理]        L0 确定性 → L1 Haiku → L2 Sonnet/Opus + 4 层搜索降级
[风控框架]               P0/P1/P2 三层 + 对抗性止损 + AI 注意力税
[Phase 2 策略]           KlineManager → IndicatorEngine → SignalEngine → 4 策略 → Orchestrator
[管线桥接]               PipelineBridge: Tick Fan-Out + Intent→Order + 治理 gate + 执行回调
[止损管理器]             StopManager: Hard/Trailing/Time Stop + ATR 动态仓位
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

## 十一、后续推进顺序（2026-03-31 287-Spec Gap 分析后更新）

```
已完成摘要：
  ✅ A-L 全部章节 + 策略工具包 + 管线桥接 + 全系统审核
  ✅ GUI 三层架构 + 10-Tab 专业控制台
  ✅ 自主交易 Agent（市场扫描器 650 符号 + 策略自动部署）
  ✅ Phase 2 治理模組 T2.01–T2.23（21 模组 · 1,522 测试）
  ✅ Phase 3 GovernanceHub 集成（4SM 接入 + 安全审核 9 项修复）
  ✅ Round 2 Batch 3-12 全部完成（5 Agent 接入 + OMS + PaperLiveGate + E2E）
  ✅ L1 本地推理（Ollama + Qwen 3.5）+ 0% 胜率四根因全修复
  ✅ Phase 0 Round 2.5 审计（2,227 tests · 2 P0 + 1 P1 修复 · 287-spec gap 分析）

★★ 开发路线图 v2（基于 287 条治理规格 Gap 分析，PM+FA 联合制定）：

  Phase 1: 安全闸补全 + 稳定性（预估 5 天）
    ★ Batch 1A: H0 Gate 确定性门控（DOC-02 · <1ms SLA · Live 前必须）
    Batch 1B: Cooldown 联动 + M-of-N 签名验证 + 数据品质→风控降级
    无外部依赖，可立即开始

  Phase 2: 学习管线 + 回测（预估 10 天）
    Batch 2A: L2 模式发现自动化 + Truth Source Registry 形式化
    Batch 2B: 回测引擎 MVP（策略 alpha 验证基础设施）
    目标：系统能从交易历史自动学习 + 验证策略有效性

  Phase 3: 进化能力（预估 15 天）
    Batch 3A: L3 假设与实验管线 + L4 策略进化
    Batch 3B: 策略 Alpha 验证 + SM-04 延迟 SLA 压测
    目标：参数自动优化 + 新策略生成 + 压力测试

  Phase 4: Paper Trading 观察 + Live 准备（5 + 21 天）
    Paper Trading 稳定运行 21 天观察期
    Live 前置条件核验 + Supervised Live Gate
    ★ SM-01 授权 TTL 分级设计（与 Learning Tier 挂钩）：
      授权 TTL 应随学习层级晋升自动延长，降低操作负担同时保留安全边界
      L1-L2（初期 live）  = 24h   — 严格监督，强制每日 checkpoint
      L3（稳定运行 30d+） = 72h   — 已积累足够记录，降低手动频率
      L4（高胜率长期）    = 7d    — 信任已建立，weekly 确认即可
      L5（完全成熟）      = 30d   — Agent 自主权最大化（原则 #11）+ 到期前通知提醒
      实现要点：grant_paper_authorization() / /auth/request TTL 参数改为读取
      LearningTierGate.current_tier → 查表得 TTL；Operator 仍可手动覆盖
      Dead Man's Switch 语义保留：不续期 = 自然停止，无需手动 kill

  详细路线图：docs/governance_dev/audits/ 及 Cowork 输出 OpenClaw_Development_Roadmap_v2.md

待处理问题（已记录，非紧急）：
  - Learning Cockpit GUI 数据展示（依赖 Analyst 数据积累）
  - RiskManager daily loss 跨天不重置（已验证有重置逻辑，影响极小）

长期优化（Phase 4 后）：
  - L5 元学习（自我校准 + 盲点识别）
  - 跨交易所套利（接入 Binance/OKX）
  - OpenClaw 深度集成（新闻扫描 + 事件驱动信号）

之后：
  M 章：Supervised Live Gate（需先积累 paper trading 数据）
  N 章：Constrained Autonomous Live

Live 前置条件（M/N 前必须核验）：
  - Paper Trading 稳定运行至少 21 天
  - H0 Gate 确定性门控已实施并验证
  - 风控框架实测验证 + 回测引擎验证策略 alpha
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
| ★ **Round 2 Batch 3-12 + Session 8-12 详细记录归档** | `docs/worklogs/control_api_gui/2026-03-31--round2_batch_records_archive.md` |
| ★ GUI 10-Tab 全面重构（common.js+8新Tab+双层解释） | `docs/worklogs/control_api_gui/2026-03-27--gui_10tab_restructure.md` |
| ★★ Session 4 GUI 专业控制台（6 commits+17 files+3964 行+6 AI 供应商） | `docs/worklogs/control_api_gui/2026-03-27--session4_gui_10tab_professional_console.md` |
| Session 5 管线启动验证 + OpenClaw 能力深挖 + 服务自动重启确认 | `docs/worklogs/control_api_gui/2026-03-27--session5_pipeline_launch_and_openclaw_analysis.md` |
| ★ Session 6 半天数据分析：胜率0%根因 + 4项修复（扫描器+置信度+.orig stub+DB表） | `docs/worklogs/control_api_gui/2026-03-28--session6_halfday_data_analysis_and_fixes.md` |
| ★★ Session 7 系统全面审核 + 5项修复（市场流自动重启+regime过滤+trend cap+时间驱动+confidence） | `docs/worklogs/control_api_gui/2026-03-28--session7_system_audit_and_fixes.md` |
| ★★★ Session 8 A-J 全面功能审核报告（胜率0%根因/学习系统空置/止损未接入） | `docs/worklogs/control_api_gui/2026-03-28--session8_functional_audit_report.md` |

### 治理开发（governance_dev/）

| 内容 | 文件位置 |
|------|---------|
| **Phase 2 执行总览**（21 模组矩阵 + 关键指标） | `docs/governance_dev/phase2_execution/T2_EXECUTION_SUMMARY.md` |
| Phase 2 PM 品质审核报告（T2.01–T2.23） | `docs/governance_dev/phase2_execution/T2_PM_QUALITY_AUDIT_REPORT.md` |
| Phase 2 TW 註釋品質審核報告 | `docs/governance_dev/phase2_execution/T2_TW_COMMENT_AUDIT_REPORT.md` |
| T2.01–T2.23 变更日志（23 份） | `docs/governance_dev/changelogs/` |
| Phase 3 集成指南（双语·API参考·部署步骤） | `docs/governance_dev/phase3_integration/T3_GOVERNANCE_INTEGRATION_GUIDE.md` |
| Phase 3 代码审核报告 | `docs/governance_dev/phase3_integration/PHASE3_CODE_REVIEW_REPORT.md` |
| Phase 3 安全审核报告 | `docs/governance_dev/phase3_integration/SECURITY_AUDIT_PHASE3.md` |
| Phase 3 FA 集成设计 | `docs/governance_dev/phase3_integration/T3.01_FA_INTEGRATION_DESIGN.md` |
| 治理文件提取（8 份参考文档） | `docs/governance_dev/governance_extracts/` |
| Phase 0 接手报告（4 份） | `docs/governance_dev/phase0_takeover/` |
| Phase 1 差距分析（2 份） | `docs/governance_dev/phase1_gap_analysis/` |
| ★ **287-Spec Gap 分析（Phase 0 Round 2.5）** | `docs/governance_dev/audits/2026-03-31--gap_analysis_287_specs.md` |
| 287 条规格完整列表 | `docs/governance_dev/audits/2026-03-31--spec_requirements_287.md` |

### 交接与索引

| 内容 | 文件位置 |
|------|---------|
| GUI 交接文档（Control API v1 + GUI v1 阶段交接） | `docs/handoffs/2026-03-25_api_gui_handoff/` |
| 文档目录规范 + 全量索引 | `docs/README.md` |

---

## 十三、一句话状态

> 截至 2026-03-31 Phase 0 Round 2.5 审计完成：2,227 tests passed / 0 failed，2 个 P0 bug 修复（MessageBus subscribe arity + text parsing），287 条治理规格 76% 已实施，4-Phase 开发路线图已制定（H0 Gate 为最高优先）。系统全程 read_only。
