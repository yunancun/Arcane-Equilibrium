# OpenClaw / Bybit AI Agent 交易系统
# CLAUDE.md — Claude Code 项目指令文件
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

---

## 三、当前系统状态（2026-03-27）

```
测试：640 全通过（214 local_model_tools + 426 control_api）
路由：104 条

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

下一步（按优先级）：
  远程安全访问方案（SSH 隧道 / Tailscale / Cloudflare Tunnel）
  Telegram 告警通道 / 自动循环 cron / AI 咨询接通 H 链

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
| 文档目录规范 + 全量索引 | `docs/README.md` |

---

## 十三、一句话状态

> 截至 2026-03-27：A-L + Phase 2 + Phase 3 + 全系统 A-K 审核修复全部完成。640 测试，104 路由，7 信号规则。管线已接通。系统性问题已清零（路径统一 / I章去重-750行 / mutator 3x→1x / SHA256 / stage 标签）。系统全程 read_only / disabled / not_granted。下一步：远程安全访问 → Telegram → cron → Beta 数据积累 → M 章。
