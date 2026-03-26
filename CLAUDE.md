# OpenClaw / Bybit AI Agent 交易系统
# CLAUDE.md — Claude Code 项目记忆文件
# 最后更新：2026-03-26（含 API/GUI 章节，全量历史整合版）

---

## 一、项目完整定位

### 这是什么

本项目是一个**长期进化型 AI Agent 自动交易系统**，以 OpenClaw 为中枢、Bybit 为主交易所、Binance 为辅助交易所。

它**不是**：
- 一个简单的自动下单脚本
- 一个只会执行固定策略的 bot
- 一个人工盯盘辅助工具

它**是**：
> 一个可以自主完成交易决策与执行、对成本与收益有清晰感知、能够感知自身硬件/软件/网络状态、能够持续学习并越做越好、在严格风控框架下逐步赢得更高自主权的 AI 交易 Agent 平台。

人类 Operator 的角色不是盯盘手动下单，而是：**不定时检查、审阅、矫正、批准关键步骤、推动策略演进**。

---

### 系统最终形态

```
[市场数据 / 账户事实 / 事件流]
        ↓
[H0 本地确定性判断内核]
  ← 本地极速：freshness、health、资格、风险包络、费用边际
        ↓ 通过才继续
[H1-H5 AI 治理层]
  ← 值得问 AI 时才问；预算受控；模型路由智能分级
        ↓
[I Decision Lease 层]
  ← AI 输出变成带时效、可撤销、可审计的决策租约
        ↓ 本地复核通过
[执行适配层]
  ← Bybit 真实下单/撤单/改单/回报处理
        ↓
[学习 / 自我感知 / 经营报告层]
  ← 每次结果归因 → 更新经验 → 改进下次判断
```

---

### 核心能力目标（完整版）

**A. 自主交易执行（在严格门控下）**
- 能自动完成下单、撤单、改单、持仓管理
- 必须先通过本地 H0 判断 → AI 治理 → Decision Lease → 执行门
- 不能跳过任何门，不能因为"行情来了就直接下"

**B. 成本与收益感知**
- 必须追踪 net PnL，不能只看 gross PnL
- 必须纳入：AI API 调用成本、Bybit 手续费、滑点估算、设备折旧、电费、基础设施成本
- 每一笔决策都要能问：扣完所有真实成本后，这笔还有没有正期望？

**C. 计算路径智能分级**
- 不是每次都调用云端大模型
- 按判断复杂度分级：
  - 纯本地确定性计算（H0，最低延迟，零成本）
  - 本地小模型推理（中等复杂度，低延迟）
  - 云端 API 大模型（高价值判断，有预算限制）
- 每次调用都有成本记账，纳入 net PnL 计算

**D. 自我感知能力（Self-Observability）**
- 硬件感知：CPU 使用率、内存压力、磁盘 I/O
- 网络感知：REST 延迟、WebSocket 稳定性、公网出口 IP、丢包率
- 软件感知：哪个模块在拖慢整体、数据库查询延迟、脚本执行时间
- 能判断"当前系统状态是否适合交易"——系统不健康时主动降级或暂停

**E. 持续学习能力（越做越好）**
- 记录每次决策的完整上下文：市场状态 + 判断理由 + 执行结果
- 对结果做归因：是策略问题、时机问题、执行问题、还是成本问题
- 生成可检验的假设：在某种市场条件 X 下，策略 Y 的历史胜率是 Z%
- 提出实验方案：以小仓位验证未经验证的假设
- 学习结果沉淀为可复用的"经验记忆"，影响下次判断
- **严格边界：学习 ≠ 自作主张。Agent 不能自动改 live 配置、不能自动放开执行权限、不能自动修改代码上线**

**F. 日/周/月经营报告**
- 一目了然看清：这段时间赚了还是亏了？
- 分解：哪些交易赚钱 / 哪些亏钱 / 哪些成本可以优化
- 错误归因：是市场判断错 / 时机错 / 执行差 / 成本过高
- 可优化建议：明确指出下一步改进方向

**G. GUI Operator Console + Learning Cockpit**
- 不是 shell 替代品，是真正的运营驾驶舱
- 人类 Operator 通过 GUI 看见系统、控制系统、理解系统
- 覆盖：状态总览 / 控制中心 / 自我感知 / 经营收益 / 审计记录 / 学习驾驶舱
- GUI → Control API → 底层 Agent 逻辑（不是直接调 shell）

---

## 二、不可违背的根原则

### 原则 1：看 net PnL，不看 gross PnL
每笔收益必须扣除：AI API 成本、手续费、滑点、设备折旧、基础设施成本。

### 原则 2：本地先做，AI 只做高价值部分
- 凡是可结构化、可计算、时效敏感的判断 → 本地 H0 先做
- AI 负责：regime 识别、冲突解释、资本激进度建议、高价值 review
- 一次 AI 调用的输出应尽量变成可复用资产（lease / 适用条件 / 失效条件）

### 原则 3：AI 输出不能当即时命令
流程：AI 判断 → Decision Lease（带时效、可撤销）→ 本地复核 → 执行适配层

### 原则 4：权限按表现赢得，不按时间自动升级
- 不能全局放权
- 只在已验证有效的子场景局部放权
- 更聪明 ≠ 更莽；在优势区间更大胆，在非优势区间更保守

### 原则 5：先系统健康，后市场判断
系统自身不健康时（网络抖动、数据过期、计算拥堵），再好的机会也不值得行动。

### 原则 6：失败默认收缩
任何关键输入缺失、冲突、过时或不可信，全部 fail-closed，不猜测。

### 原则 7：学习不等于自作主张
Agent 可以：观察、记忆、总结、提假设、提实验方案。
Agent 不可以：自动改 live 配置、自动开放执行权限、自动修改代码上线。

### 原则 8：所有结论区分事实 / 推断 / 假设
防止 Agent 乱归因、把推断当事实汇报。

---

## 三、当前系统状态（截至 2026-03-26，L 章 API/GUI 层完成）

```
准确定位：
  production-grade readonly observer
  + governed AI observation chain
  + shadow decision control plane
  + learning system API/GUI layer (L 章存储层 + 人工录入 + 审批界面)
  + Control API v1（约85%完成）
  + GUI Operator Console（约80%完成）

Runtime 硬状态：
  system_mode             = read_only
  execution_state         = disabled
  execution_authority     = not_granted
  decision_lease_emitted  = false
  live_execution_allowed  = false
```

---

## 四、正式章节树（Revision 2，当前最新状态）

```
A-C  基础层 / OpenClaw 模型层 / 接入前治理      ✅ 完成
D    Readonly Observer 主链                     ✅ 完成（稳定）
E    Business Event Classification              ✅ 完成
F    Event-Driven Transition Scaffold           ✅ 完成
G    真实业务事件验证层                          ✅ 正式收口
H0   Local Deterministic Judgment Core          ✅ 完成（path 治理清理）
H1   thought_gate                               ✅ 完成（canonical，no-call 语义已接受）
H2   query_budget                               ✅ 完成（canonical）
H3   model_router v2                            ✅ 完成（canonical）
H4   compute governor                           ✅ 完成（canonical）
H5   AI cost logging / governance audit         ✅ 完成（canonical）
I1-I9  decision lease shadow control plane      ✅ 全部完成（shadow-only）
I10  chapter summary / final audit              ✅ 完成（shadow control plane closed）
J    Transition Engine Skeleton                 ✅ functional_closeout_ready_shadow_only
K    Paper / Demo Gate                          ✅ functional_closeout_ready_design_only_gate_closed
     Control API v1                             🔵 约90%完成（分支 feature/openclaw-bybit-control-api-gui-v1-rc2）
     GUI Operator Console v1                    🔵 约90%完成（同分支，含 Learning Cockpit + Net PnL Dashboard）
L    Learning / Self-Observability / Net PnL    🔵 API/GUI 层已完成（Agent 自动化管线待建）
M    Supervised Live Gate                       ⬜ 未开始
N    Constrained Autonomous Live                ⬜ 未开始
```

**⚠️ 重要：任何章节"完成/闭环/closeout ready"都不等于 live 放权。当前执行权限仍未授予。**

---

## 五、Control API 与 GUI 当前状态

### Control API（分支：feature/openclaw-bybit-control-api-gui-v1-rc2）

**代码位置：** `program_code/exchange_connectors/bybit_connector/control_api_v1/`

**已完成：**
- 统一响应 envelope（含 `snapshot_id` / `state_revision` / `source_context` / `audit_ref`）
- 认证 / 授权层（Bearer token，role/scope 体系）
- 已可用 GET 接口：`/system/overview` / `source-context` / `product-families` / `control-plane` / `audit-summary` / `learning/feed` / `learning/experiments` / `learning/net-pnl` / `learning/overview` / `learning/hypotheses`
- 已可用 POST 接口：`demo/validate` / `demo/arm` / `safe-recheck-bundle` / `input/config-change` / `input/manual-note` / `input/observation` / `input/lesson` / `input/hypothesis` / `input/experiment` / `input/pnl-period-snapshot` / `learning/hypothesis/{id}/verdict` / `learning/experiment/{id}/approve` / `learning/experiment/{id}/complete`
- runtime snapshot bridge（GUI 可看到 runtime-aware 事实层）
- Control API RC2 合同审核通过（无 P0 级阻断问题）

**API 合同版本：** `openclaw_bybit_control_api_v1_rc2@v1`
**状态字典版本：** `openclaw_bybit_state_dictionary@v1`（RC2 伴随补丁已定义）

**待完成（非阻断）：**
- 产品族配置写接口深化
- business/income 更深数据源接入
- 最终部署封板
- 与 OpenClaw 主线深度整合

### GUI Operator Console

**已完成：**
- 真实调用 API（非静态 mock）
- 主控制台区块：连接区、summary、运行模式控制、经营摘要、来源上下文、健康摘要、产品族配置、快捷动作、审计
- 关键动作二次确认弹窗
- 产品族配置区（spot / margin / perp_linear / perp_inverse / options / other_derivatives_reserved）
- 长期开关预留区（Observe Only / Demo Reserved / Demo Enabled / Live Locked / Emergency Relock 等）
- Learning Cockpit（学习驾驶舱）：Observation / Lesson / Hypothesis / Experiment 四标签 + 输入表单 + 审批按钮
- Net PnL Dashboard（净 PnL 仪表盘）：日度 PnL / 成本分解 / 周期趋势 / 快照保存
- 中文主表达 + 英文辅助，概念提示默认折叠

**GUI 关键文档（repo 内）：**
```
docs/handoffs/2026-03-25_api_gui_handoff/
  API_GUI_FULL_ENGINEERING_REPORT_2026-03-26.md
  API_GUI_LIGHT_CLOSEOUT_2026-03-26.md
  API_GUI_STAGE_COMPLETION_README_2026-03-26.md
  API_GUI_STAGE_CLOSEOUT_CHECKLIST_2026-03-26.md
  GUI_OPENCLAW_PORTAL_PRELAYOUT_2026-03-26.md
  LONG_TERM_SWITCHES_PRESET_2026-03-26.md
```

---

## 六、系统架构总览

```
[数据与观察层]
  Bybit readonly REST（account/positions/orders/executions）
  persistent WS listener v2
  snapshot → Postgres
  decision packet v4 → observer verdict v4
  acceptance / runtime state / failure policy

[H0 本地确定性判断内核]  ← 极低延迟，零 AI 成本
  freshness / staleness
  runtime health / REST / WS / DB health
  execution permission / system mode
  position / order / execution 事实
  fee / spread / slippage / minimum edge
  exposure / kill switch / circuit breaker
  → 输出：trade_eligibility + AI 升级前置筛选

[H1-H5 AI 治理层]  ← 值得时才问 AI
  H1 thought_gate（合法 no-call 已接受为终态）
  H2 query_budget
  H3 model_router v2（本地 / 云端智能路由）
  H4 compute governor（anti-abuse, max_retries=0）
  H5 AI cost logging（纳入 net PnL）

[I Decision Lease 层]  ← shadow-only，未 live
  lease schema / freshness / validity
  revoke / supersede / expiry
  risk-integrated lease consumption
  operator ack / approval bridge

[J Transition Engine Skeleton]  ← shadow-only closeout
[K Paper / Demo Gate]          ← design-only gate closed

[Control API v1]  ← GUI 的后端
  FastAPI + Pydantic v2
  /api/v1/system/* / /control/* / /input/* / /learning/*

[GUI Operator Console + Learning Cockpit]
  Operator 通过 GUI 控制、感知、学习系统

[L 学习 / 自我感知 / Net PnL]  ← 待正式开始
[M Supervised Live Gate]        ← 待开始
[N Constrained Autonomous Live] ← 待开始
```

---

## 七、产品族与能力层

### 产品族（所有开关设计必须按此组织）
```
spot               现货
margin             保证金
perp_linear        线性永续
perp_inverse       反向永续
options            期权
other_derivatives_reserved  其他衍生品（预留）
```

### OpenClaw 能力层（按交易所权限 × Agent 工程能力）
```
unsupported        不支持
observe_only       仅观察
shadow_ready       影子就绪
demo_ready         模拟就绪
live_guarded_ready 受限实盘就绪
live_ready         正式实盘就绪
```

### 执行动作权限（需要分别控制）
```
new_order          新建订单
cancel             撤销订单
amend              修改订单
reduce_only        只减仓
increase_position  加仓
close_position     平仓
leverage_change    杠杆调整
borrow             借款
transfer           划转
```

---

## 八、硬边界（永远不能违背）

```python
system_mode             = "read_only"      # 不可改
execution_state         = "disabled"       # 不可改
execution_authority     = "not_granted"    # 不可改
decision_lease_emitted  = False            # 不可改
max_retries             = 0                # 不可改

# 仍是硬错误：
# - should_call_ai=true 但 invocation 没发生
# - Bybit API timeout / retCode != 0
# - public fetch_errors
# - execution authority 意外被授予
# - 为了让红灯变绿而伪造 AI 调用或伪造交易活动
# - 自动改 live 配置
# - 自动放开 execution authority
```

---

## 九、重要技术记录

### Legal no-call 语义（全系统已接受）
```python
route_plan       = route_skip
selected_ai_tier = none
should_call_ai   = false
# → 合法 observation terminal path，不是失败
```

### Legal idle account 语义（全系统已接受）
```python
system_mode = read_only, execution_state = disabled
position_count = 0, order_count = 0, execution_count = 0
# → no_open_positions / no recent orders / WS control-only = info/idle，不是 blocker
```

### Authoritative checkers
```bash
# H 章
helper_scripts/maintenance_scripts/bybit_connector/run_i10_canonical_h_chain_recheck.sh
# I 章
helper_scripts/maintenance_scripts/bybit_connector/run_i10_canonical_decision_lease_recheck.sh
# ⚠️ run_i10_clean_recheck.sh 是 legacy，头部已加 warning
```

### 三类问题区分法
| 类型 | 现象 | 解法 |
|---|---|---|
| 代码真坏了 | 逻辑错误、字段缺失 | 修代码 |
| latest 是旧的 | 日期是几天前 | 重跑 canonical chain |
| runner 看错路径 | 旧文件名/旧绝对路径 | 修 runner |

### 已知文件名修正
| 旧名（失效） | 当前正确名 |
|---|---|
| `bybit_local_risk_envelope_builder.py` | `bybit_local_risk_envelope_gate.py` |
| `bybit_local_trade_eligibility_handoff.py` | `bybit_local_trade_eligibility_handoff_builder.py` |
| `bybit_local_judgment_contract_check.py` | `bybit_local_judgment_final_audit_contract_check.py` |

---

## 十、GitHub 与本地路径

```
GitHub repo:    yunancun/BybitOpenClaw
本地主工作树:   /home/ncyu/BybitOpenClaw/srv
                /home/ncyu/srv  ← symlink，运行时沿用此路径

本地-only（不进 Git）：
  settings/          真实 env / secrets / service config
  trading_services/  .env / runtime / connector_logs / decision_packets / verdicts
```

**工作流：GitHub-first**
- 已 push 代码优先从 GitHub 直接读
- runtime / latest / json / env 等本地-only 才用 shell 读

---

## 十一、每次恢复工作时的启动检查

```bash
# 1. 确认 git 状态与分支
git status && git log --oneline -5

# 2. 确认 H 链健康
bash helper_scripts/maintenance_scripts/bybit_connector/run_i10_canonical_h_chain_recheck.sh

# 3. 确认 I 链健康
bash helper_scripts/maintenance_scripts/bybit_connector/run_i10_canonical_decision_lease_recheck.sh

# 4. 确认主 runtime 安全
python3 scripts/bybit_observer_acceptance_check.py
python3 scripts/bybit_runtime_state_resolver.py
```

---

## 十二、每写一个新脚本的标准规范

1. 头部写 `MODULE_NOTE` 注释（**中英双语，详细**）
2. 输出 `latest` + `dated` 两份文件
3. 补 `contract check`
4. 必要时补 `consistency / final audit`
5. 更新 `SCRIPT_INDEX.md`

---

## 十三、Shell 命令工作方式要求

- 每轮只给 1 小组命令（1-2 个逻辑动作）
- 明确标注：只检查 / 只读 / 会修改 / 会写文件 / 会 commit / 会 push
- 每轮明确告知用户贴哪几个 marker 段落
- 不要一次给太多命令
- 稳定一轮后再建议 commit + push

---

## 十四、后续推进顺序

```
L 章 API/GUI 层已完成：
  ✅ Observation Feed / Lessons Memory / Hypothesis Queue / Experiment Queue
  ✅ Net PnL Dashboard（日度 PnL / 成本分解 / 周期快照趋势）
  ✅ GUI Learning Cockpit 四标签 + 输入表单 + 审批流
  ✅ 30 个测试用例全部通过

当前主线：
  → L 章 Agent 端自动化学习管线（自动观察 / 自动经验生成 / 自动假设提出）
  → 产品族配置写接口深化
  → business/income 更深数据源接入
  → 与 OpenClaw 主线深度整合

之后：
  M 章：Supervised Live Gate（需 G-K 主干完成）
  N 章：Constrained Autonomous Live

Live design 前置条件（进入 M/N 前必须核验）：
  - freshness 真正闭合方式
  - recent trade 字段补全
  - provider pricing table 正式绑定
  - latency / ttl / consume timing 达到真实 live 需要
  - authority grant contract 设计
  - execution adapter contract 设计
```

---

## 十五、历史编号映射（防混淆）

| 历史临时编号 | 正式章节 |
|---|---|
| D21 readonly observer hardened | D |
| D22 business-event classification | E |
| D23 event-driven scaffold | F |
| 临时 G1/G2/G3 | G |
| 临时 G4.x | J |
| 临时 G5/G6 | K |

J/K 内部旧 G4.x/G5.x 命名是历史 debt，已完成 functional closeout，不再继续深挖。

---

## 十六、一句话版当前状态

> 截至 2026-03-26：A-K 全部 functional closeout；L 章 API/GUI 层已完成（Observation / Lesson / Hypothesis / Experiment / Net PnL，30 测试全通过），Agent 端自动化学习管线待建。Control API v1 约 90%、GUI v1 约 90%。系统全程 read_only / disabled / not_granted。下一步：L 章 Agent 自动化管线 → M 章 Supervised Live Gate。
