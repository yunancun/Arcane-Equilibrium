# OpenClaw / Bybit AI Agent 交易系统
# CLAUDE.md — Claude Code 项目记忆文件
# 最后更新：2026-03-27（含 Layer 2 已实现 + 全品类风控框架设计 + Agent 自主交易 + AI 注意力税 + 对抗性止损，全量历史整合版）

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

**G. Agent 自主交易能力（在风控框架下）**
- Agent 自主决定：交易什么品种、用哪种策略、何时开平仓、仓位大小、参数设置
- 支持 Bybit V5 API 全部 6 大交易品类：Spot / Spot Margin / Linear Perpetual / Inverse Perpetual / Futures / Options
- 支持 10+ 种订单类型：Market / Limit / Conditional / TP-SL / Trailing Stop / Reduce Only / Post Only / Iceberg / TWAP / Batch
- 用户只在 global 层面设置止盈止损上限，Agent 在上限内全权操作
- 三层优先级风控：P0 品类专属（用户设）> P1 全局（用户设）> P2 Agent 自适应（Agent 调）
- Agent 不可以：突破用户上限、自行开启未授权品类、关闭硬止损、修改 system_mode

**H. 对抗性市场意识（Anti-Adversarial Trading）**
- 市场存在高频做市商、量化基金 AI Bot、止损猎杀策略
- 止损分两层：硬止损（绝对防线，不可突破）+ 软止损（Agent 评估后决定）
- 止损隐身：永远不在交易所放 stop order，本地 tick() 检查触发
- 反猎杀：ATR 基础 + 随机偏移避开聚集止损位，假突破识别，流动性感知平仓
- 对抗性仓位管理：非标仓位大小、分批入出场、大单 iceberg/TWAP
- 我们的结构性优势：HFT 快但不聪明（规则驱动），Agent 慢但能推理（AI 驱动）+ 止损不可见

**I. AI 注意力税（AI Attention Tax）**
- 每个持仓的真实成本 = 金融成本 + AI 注意力成本
- AI 注意力成本随持仓时间、波动率、监控频率累积
- 持仓有自然衰减压力：cost_edge_ratio 超阈值 → 建议平仓
- 开仓前草算：预估 AI 成本 + 金融成本 > 预估边际 → 不开仓
- Agent 自然偏好低维护策略（Grid、Funding Rate 套利 vs 高维护长持仓）

**J. GUI Operator Console + Learning Cockpit**
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

## 三、当前系统状态（截至 2026-03-27，Layer 2 已实现 + 全品类风控框架设计完成）

```
准确定位：
  production-grade readonly observer
  + governed AI observation chain
  + shadow decision control plane
  + learning system 全栈完成（存储层 + 手动录入 + 自动学习管线 + 审核队列 GUI）
  + Control API v1（84 条路由，安全加固已完成）
  + GUI Operator Console v1（含 Learning Cockpit 5 标签 + Net PnL + Paper Trading Dashboard）
  + Paper Trading Engine Beta（24 条纸上交易路由，7 状态订单生命周期，成交模拟，PnL 计算）
  + Beta 管线完善（实时行情 + 自动桥接 + 影子决策管线 + 性能指标）
  + 统一控制台（/console，融合 Trading Dashboard + OpenClaw + AI 成本追踪）
  + systemd 服务化（API 服务器开机自启 + 崩溃自动重启）
  + 安全加固已完成（Token 管理 / hmac / CORS / 速率限制 / 文本限制 / 幂等 TTL）
  + Layer 2 AI 推理引擎（已实现 + 审核修复：SSRF 防护 + metrics 重写 + cost tracker race fix + adaptive 强制执行）
  + 全品类风控框架（已实现 + 4 轮审核：三层 P0/P1/P2 + 对抗性止损 + AI 注意力税 + 9 路由）

测试：405 个全部通过

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
     Control API v1                             ✅ 完成（75 路由，安全加固完成）
     GUI Operator Console v1                    ✅ 完成（含 Learning Cockpit + Net PnL + Paper Trading + 统一控制台）
L    Learning / Self-Observability / Net PnL    ✅ 全部完成（存储 + 手动录入 + 自动学习管线 + 审核队列 + 安全加固）
     Paper Trading Engine Beta                  ✅ 完成（24 路由，影子决策 + 性能指标 + 实时行情 + 自动桥接）
     OpenClaw 融合                              ✅ 完成（统一控制台 + AI 成本追踪 + systemd 服务化）
     Layer 2 AI 推理引擎                        ✅ 完成 + 审核修复（5 模块 + 9 路由 + 79 测试 + SSRF 防护 + 成本追踪 race fix + 指标重写 + adaptive 强制执行）
     全品类风控框架                              ✅ 完成 + 4 轮审核（三层 P0/P1/P2 + 9 路由 + 78 测试 + 对抗性止损 + AI 注意力税）
M    Supervised Live Gate                       ⬜ 未开始（需先完成 Paper Trading beta 运行 + 数据积累）
N    Constrained Autonomous Live                ⬜ 未开始
```

**⚠️ 重要：任何章节"完成/闭环/closeout ready"都不等于 live 放权。当前执行权限仍未授予。**

---

## 五、Control API 与 GUI 当前状态

### Control API（main 分支）

**代码位置：** `program_code/exchange_connectors/bybit_connector/control_api_v1/`

**已完成：**
- 统一响应 envelope（含 `snapshot_id` / `state_revision` / `source_context` / `audit_ref`）
- 认证 / 授权层（Bearer token + hmac 常数时间比较，role/scope 体系）
- 已可用 GET 接口（31 条）：`/system/overview` / `chapter-status` / `control-plane` / `capability-matrix` / `product-families` / `business/daily` / `business/summary` / `health` / `audit-summary` / `source-context` / `learning/overview` / `learning/hypotheses` / `learning/feed` / `learning/experiments` / `learning/net-pnl` / `learning/review-queue` / `paper/session/status` / `paper/orders` / `paper/positions` / `paper/fills` / `paper/pnl` / `paper/audit-trail` / `paper/export` / `paper/shadow/history` / `paper/shadow/decisions` / `paper/metrics` / `paper/ai-cost` / `paper/market-feed/status` / `console`
- 已可用 POST 接口（44 条）：`demo/validate` / `demo/arm` / `demo/enable` / `demo/relock` / `safe-recheck-bundle` / `recheck/j-canonical` / `recheck/k-canonical` / `recheck/j-closeout` / `recheck/k-closeout` / `input/config-change` / `input/cost` / `input/event` / `input/manual-note` / `input/observation` / `input/lesson` / `input/hypothesis` / `input/experiment` / `input/pnl-entry` / `input/pnl-period-snapshot` / `learning/hypothesis/{id}/verdict` / `learning/experiment/{id}/approve` / `learning/experiment/{id}/complete` / `learning/auto/scan-observations` / `learning/auto/scan-lessons` / `learning/auto/scan-hypotheses` / `learning/review/{id}/decide` / `learning/review/{id}/ai-consult` / `control/product-family/{family}/config` / `paper/session/start` / `paper/session/pause` / `paper/session/resume` / `paper/session/stop` / `paper/order/submit` / `paper/order/cancel` / `paper/tick` / `paper/shadow/feed` / `paper/market-feed/start` / `paper/market-feed/stop` / `paper/market-feed/add-symbol` / `paper/market-feed/remove-symbol`
- runtime snapshot bridge（GUI 可看到 runtime-aware 事实层）
- Control API RC2 合同审核通过（无 P0 级阻断问题）

**安全加固已完成：**
- API Token：自动生成 + 文件保存 + 重置指南（不再有硬编码默认值）
- Token 比较：`hmac.compare_digest()` 常数时间比较
- 状态文件权限：每次写入后 `chmod 0o600`
- CORS 中间件：通过 `OPENCLAW_CORS_ORIGINS` 配置
- 速率限制：slowapi 中间件，默认 120/min/IP（通过 `OPENCLAW_RATE_LIMIT` 配置）
- 文本长度限制：title ≤200 / detail ≤2000 / reason ≤500
- 幂等缓存 TTL：24h 过期 + 500 条上限自动清理
- `.gitignore` 排除 `.secrets/` / `runtime/` / `__pycache__/`

**API 合同版本：** `openclaw_bybit_control_api_v1_rc2@v1`
**状态字典版本：** `openclaw_bybit_state_dictionary@v1`（RC2 伴随补丁已定义）

**Paper Trading Engine Beta：**
- 独立模块：`app/paper_trading_engine.py` + `app/paper_trading_routes.py`
- 独立状态文件：`OPENCLAW_PAPER_STATE_FILE`（与主控制状态完全隔离）
- 7 状态订单生命周期（基于 K 章骨架）：created → submitted → working → partially_filled → filled/canceled/rejected
- 成交模拟：market order（含滑点 0.05%）+ limit order（价格穿越成交）
- 手续费：taker 0.055% / maker 0.02%（Bybit 永续线性默认值）
- 持仓投影：开仓/加仓/减仓/平仓/翻转
- PnL 计算：realized + unrealized - fees - ai_cost = net_paper_pnl
- 影子决策管线：`shadow_decision_builder.py`（影子决策构建 + 消费 + 文件馈送）
- 性能指标：`paper_trading_metrics.py`（胜率 / 最大回撤 / Sharpe / 持仓时长 / AI 效率）
- 实时行情：`bybit_public_ws_listener.py` + `market_data_dispatcher.py`（自适应注意力过滤）
- 自动桥接：`auto_bridge_observer_to_runtime_snapshot.py`（Observer → Runtime Snapshot）
- 所有响应携带 `is_simulated: true` + `data_category: paper_simulated`

**OpenClaw 融合：**
- 统一控制台：`/console`（Trading Dashboard + OpenClaw Gateway 状态 + AI 成本侧边栏）
- AI 成本追踪：`GET /api/v1/paper/ai-cost`（复用 `openclaw gateway usage-cost`，零 AI 成本）
- OpenClaw 定位：通信层（消息推送 / 成本追踪 / 定时任务），非 Agent 大脑
- Canvas 对接：`~/.openclaw/canvas/index.html` → iframe 指向统一控制台

**部署与服务化：**
- systemd 用户服务：`openclaw-trading-api.service`（开机自启 + 崩溃重启）
- 绑定 `127.0.0.1:8000`（仅本地），远程访问通过 SSH 隧道
- 管理：`systemctl --user {status|restart|stop} openclaw-trading-api`

**待完成（非阻断）：**
- 远程安全访问方案实施（SSH 隧道 / Tailscale / Cloudflare Tunnel）
- Layer 2 AI 推理循环设计与实现（三层架构：L0 确定性 / L1 轻量评估 / L2 深度推理）
- Telegram 告警通道（接 OpenClaw channels）
- 自动循环 cron（observer cycle → shadow decision → paper order → fill tick）
- AI 咨询接通 H 链（当前为 stub，接 H1-H5 后可真实调 AI）
- 产品族配置写接口深化
- CSP 安全头部署（如果开放公网访问）

### GUI Operator Console

**已完成：**
- 真实调用 API（非静态 mock），并发 fetch 10 个端点
- 主控制台区块：连接区、summary、运行模式控制、经营摘要、来源上下文、健康摘要、产品族配置、快捷动作、审计
- 关键动作二次确认弹窗
- 产品族配置区（spot / margin / perp_linear / perp_inverse / options / other_derivatives_reserved）
- 长期开关预留区（Observe Only / Demo Reserved / Demo Enabled / Live Locked / Emergency Relock 等）
- Learning Cockpit（学习驾驶舱）：5 个标签页
  - Observation / Lesson / Hypothesis / Experiment — 手动输入表单 + 审批按钮
  - **审核队列 / Review Queue** — 自动学习管线审核（扫描按钮 + 审核包卡片 + 后果分析 + AI 咨询）
- Net PnL Dashboard（净 PnL 仪表盘）：日度 PnL / 成本分解 / 周期趋势 / 快照保存
- **Paper Trading Dashboard（纸上交易仪表盘）**：
  - Session 控制（Start / Pause / Resume / Stop）
  - Paper PnL 卡片（已实现 / 未实现 / 手续费 / 净值）
  - 持仓表格 / 订单列表 / 成交历史 / 审计记录
  - 订单提交表单（Symbol / Side / Type / Qty / Price）
  - 蓝色边框视觉风格 + "模拟数据" 警告横幅
- **统一控制台（`/console`）**：
  - 左侧边栏：AI 成本（今日/30天）、Paper PnL、Session、系统健康（API + OpenClaw Gateway）
  - Tab 1：Trading Dashboard（iframe 嵌入）
  - Tab 2：OpenClaw Control（新窗口打开按钮 + Gateway 状态面板，因 X-Frame-Options 限制无法 iframe）
  - 15 秒自动刷新，实时时钟
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

**近期关键讨论与设计文档位置（2026-03-26 ~ 03-27）：**
```
docs/references/
  2026-03-27--phase1_risk_framework_and_agent_autonomy_design.md
    → ★★ 全品类风控框架完整设计（三层 P0/P1/P2 + 6 品类 + 对抗性止损 + AI 注意力税 + Agent 自主交易）
  2026-03-27--local_trading_logic_audit_and_strategy_plan.md
    → ★ 本地交易逻辑审查报告（安全审查 + 覆盖缺口 + 盈利评估 + ABCD 策略计划）
  2026-03-27--layer2_ai_reasoning_engine_implementation_plan.md
    → Layer 2 实现计划（4 层搜索 + 模型升级 + 自适应预算 + 9 路由 + GUI）— 已实现

docs/worklogs/control_api_gui/
  2026-03-27--layer2_ai_engine_design_session.md
    → 本轮设计工作记录：搜索 Provider 调研 + 架构决策 + 成本控制设计
  2026-03-26--brainstorm_layer2_ai_reasoning_engine.md
    → Layer 2 初步 brainstorm：三层架构 + Agent 循环 + 工具箱
  2026-03-26--brainstorm_openclaw_agent_architecture.md
    → OpenClaw 定位决策：通信层非大脑 + Agent 智能化架构讨论
  2026-03-26--openclaw_fusion_console_systemd_服务化.md
    → OpenClaw 融合 + 统一控制台 + systemd + 远程访问方案对比
  2026-03-26--beta_pipeline_shadow_decision_metrics.md
    → Beta 管线完善：影子决策 + 性能指标 + 实时行情 + 自动桥接（248 测试）
  2026-03-26--paper_trading_engine_完整工程日志.md
    → Paper Trading Engine 完整工程日志（引擎核心 + 14 路由 + GUI + 43 测试）
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
  /api/v1/system/* / /control/* / /input/* / /learning/* / /paper/*

[GUI Operator Console + Learning Cockpit + Paper Trading]
  Operator 通过 GUI 控制、感知、学习系统、模拟交易

[L 学习 / 自我感知 / Net PnL]  ← 全部完成（存储 + 手动 + 自动管线 + 审核队列）

[Paper Trading Engine]  ← MVP 完成
  独立模块：paper_trading_engine.py + paper_trading_routes.py
  7 状态订单生命周期 / 成交模拟 / 持仓投影 / PnL 计算
  独立状态文件，与主控制状态隔离
  所有数据标记 is_simulated=true

[OpenClaw Gateway 融合层]      ← 通信层（非大脑）
  消息推送（Telegram 等） / AI 成本追踪 / 定时任务 / Canvas 仪表盘
  统一控制台 /console（Trading Dashboard + OpenClaw + AI Cost）

[systemd 服务化]
  openclaw-gateway.service      ← OpenClaw Gateway（端口 18789）
  openclaw-trading-api.service  ← Control API（端口 8000，开机自启）

[Layer 2 AI 推理引擎]          ← 已实现（327 测试通过）
  三层架构：L0 确定性 → L1 Haiku triage → L2 Sonnet/Opus Agent 循环
  4 层搜索降级：Perplexity → 本地LLM+web-pilot → 本地LLM → DuckDuckGo
  搜索后模型升级判断（Haiku triage → Sonnet 或 Opus）
  自适应预算（根据 AI ROI 动态调整，$15/天硬上限）
  PnL 归因回填 → 学习 AI 花费是否划算
  9 条路由，GUI AI Budget 控制卡片

[全品类风控框架]               ← 设计完成，待编码
  三层优先级：P0 品类专属（用户设）> P1 全局（用户设）> P2 Agent 自适应（Agent 调）
  Bybit V5 全 6 品类支持：spot / spot_margin / linear / inverse / futures / options
  10+ 种订单类型：market / limit / conditional / TP-SL / trailing / reduce_only / iceberg / TWAP / batch
  对抗性止损：软止损（Agent 评估）+ 硬止损（绝对防线）+ 止损隐身 + 假突破识别
  AI 注意力税：持仓真实成本 = 金融成本 + AI 监控成本 → cost_edge_ratio → 自然衰减压力
  Agent 自主交易：自主选择品种/策略/参数/时机，用户只设全局上限
  已实现 9 条路由（84 → 93），78 个测试，4 轮审核通过

[M Supervised Live Gate]        ← 待开始（需先积累 paper trading 数据）
[N Constrained Autonomous Live] ← 待开始
```

---

## 七、产品族与能力层

### 产品族（所有开关设计必须按此组织）
```
spot               现货（无杠杆、无爆仓、最安全）
margin             现货保证金（有杠杆、有借贷利息、有爆仓）
perp_linear        线性永续 USDT/USDC（杠杆 1-125x、funding rate、主战场）
perp_inverse       反向永续（以币结算、杠杆、funding rate）
options            期权（买方亏损有限、卖方风险无限、Greeks 风险）
other_derivatives_reserved  其他衍生品 / 期货（有到期日、预留）
```

### Bybit V5 API 全量订单类型（Agent 可用）
```
market             市价单（即时成交，有滑点）
limit              限价单（GTC/IOC/FOK/PostOnly）
conditional        条件触发单（triggerPrice 触发后执行）
tp_sl_order        订单级止盈止损（takeProfit/stopLoss 参数附加在订单上）
tp_sl_position     持仓级止盈止损（/v5/position/trading-stop）
trailing_stop      追踪止损（动态跟踪价格）
reduce_only        仅减仓标记（防止意外加仓）
post_only          仅挂单标记（保证 maker fee）
iceberg            冰山单（隐藏大单意图）
twap               时间加权均价（均匀分布执行）
batch              批量下单（1-10 单/次）
```

### 保证金模式
```
cross              共享全账户余额（一仓爆仓影响全部）
isolated           每仓位独立保证金（爆仓仅损失该仓位）
portfolio          组合保证金（跨品种对冲减少保证金）
```

### 持仓模式
```
one_way            单向持仓（同品种只能持一个方向）
hedge              双向持仓（可同时持多空）
```

### 三层优先级风控（P0 > P1 > P2）
```
P0 品类专属风控    用户按品类单独设置，覆盖 P1（只能更严格）
P1 全局风控        用户设置的全局上限，适用于所有品类
P2 Agent 自适应    Agent 在 P0/P1 有效上限内自主调整（只能收紧）
合并规则：effective = min(P0 ?? P1, P1)，Agent P2 在 effective 内收紧
```

### 对抗性止损设计
```
硬止损 (Hard Stop)  P1 全局上限，绝对防线，价到即关
                    永远不放在交易所 order book 上
                    本地 tick() 检查触发，市价平仓

软止损 (Soft Stop)  Agent 评估后决定
                    价格进入止损区域 → L1 快速评估：
                    渐进下跌 vs 瞬间刺穿？Order book 深度？
                    相关资产同步异动 vs 孤立异动？
                    Agent 决定：平仓 / 持有 / 收紧 / 放宽

反猎杀措施：
  ATR 基础 + 随机偏移 → 避开聚集止损位
  假突破识别 → 疑似猎杀时 soft stop 不触发
  流动性感知平仓 → 薄 book 用 TWAP 拆分
  非标仓位大小 → 避免模式被预测
```

### AI 注意力税（AI Attention Tax）
```
每个持仓真实成本 = 金融成本 + AI 注意力成本
  金融成本：手续费 + 滑点 + funding rate + 保证金机会成本
  AI 注意力成本：持仓存在一天 AI 多监控一天（草算 $0.003-$0.100/h）

cost_edge_ratio = total_holding_cost / initial_expected_edge
  A (<0.2): 成本可忽略
  B (<0.4): 健康
  C (<0.6): 需关注
  D (<0.8): 建议平仓
  F (≥0.8): 持有已不划算

效果：赚钱仓位也有保质期 / Agent 偏好低维护策略 / AI 预算紧时仓位自然收缩
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

## 十二-b、docs/ 文档目录规范

**所有向 `docs/` 写入文件的操作必须遵守以下规则（无例外）：**

1. 文件必须放入对应分类目录（`worklogs/` / `handoffs/` / `decisions/` / `incidents/` / `references/`），**禁止**直接放在 `docs/` 根目录
2. 文件命名格式：`YYYY-MM-DD--功能描述.扩展名`（同天多份加时间：`YYYY-MM-DD--HHmm--描述`）
3. **每次新增文件后必须更新 `docs/README.md` 底部的文档索引**
4. 日志必须人类可读，中文为主 + 英文辅助，简洁有上下文
5. 完整规范见 `docs/README.md`

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
已完成：
  ✅ L 章全部完成（学习管线 + 安全加固 8 项）
  ✅ Paper Trading Engine Beta（24 路由 + 7 状态生命周期 + 影子决策 + 性能指标 + GUI）
  ✅ Beta 管线完善（实时行情系统 + Observer 自动桥接 + 影子决策管线 + 高级性能指标）
  ✅ OpenClaw 融合（统一控制台 /console + AI 成本追踪 + Canvas 对接）
  ✅ systemd 服务化（API 服务器开机自启 + 崩溃自动重启）
  ✅ Layer 2 AI 推理引擎已实现（5 模块 + 79 测试 + 9 路由 + Agent 循环 + 4 层搜索降级）
  ✅ 405 个测试用例全部通过，93 条路由
  ✅ 全品类风控框架完成 + 4 轮严格审核（2026-03-27）

  Phase 1 完成明细：
    Phase 1a ✅ 安全修复 S1-S5
    Phase 1b ✅ 三层优先级风控 P0/P1/P2（完善 + 审核）
    Phase 1c ✅ 对抗性止损（ATR + 反聚集 + spike 检测 + 抑制次数限制）
    Phase 1d ✅ AI 注意力税（holding_cost + cost_edge_ratio + 效率等级）
    Phase 1e ✅ Paper Engine 订单类型扩展（conditional / TP-SL / TIF / reduce_only）
    4 轮审核 ✅ 25+ 问题修复（含 CRITICAL: flip PnL 双重计算，HIGH: 敞口忽略挂单等）
    工程日志：docs/worklogs/control_api_gui/2026-03-27--phase1_final_audited_engineering_log.md

下一步（按优先级）：

  ★ 本地策略补齐（Phase 2）
    → 本地技术指标引擎（K 线聚合 + MA/RSI/BB/MACD/ATR）
    → Funding Rate 套利信号器
    → Bollinger Band 均值回归
    → Grid Trading（网格交易）
    → Agent Strategy Orchestrator（自主选择/组合/启停策略）

  远程安全访问方案
    → SSH 隧道（最简，已可用）
    → Tailscale / Cloudflare Tunnel / Caddy（待选定）

  Telegram 告警通道 / 自动循环 cron / AI 咨询接通 H 链

之后：
  M 章：Supervised Live Gate（需先积累 paper trading 数据）
  N 章：Constrained Autonomous Live

Live design 前置条件（进入 M/N 前必须核验）：
  - paper trading beta 数据积累足够（至少运行数周）
  - 全品类风控框架实测验证（三层优先级 + 对抗性止损 + AI 注意力税）
  - freshness 真正闭合方式
  - recent trade 字段补全
  - provider pricing table 正式绑定
  - latency / ttl / consume timing 达到真实 live 需要
  - authority grant contract 设计
  - execution adapter contract 设计
  - 远程访问安全方案已部署（HTTPS + CSP 安全头）
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

> 截至 2026-03-27：A-L 全部完成 + Paper Trading Engine Beta + OpenClaw 融合 + systemd 服务化 + **Layer 2 AI 推理引擎已实现**（79 测试 + 9 路由）+ **全品类风控框架已实现并经过 4 轮严格审核**（三层 P0/P1/P2 + 对抗性止损 + AI 注意力税 + 78 测试 + 9 路由 + 25 问题修复 + atomic write + spike 抑制限制 + pending order exposure）。405 测试全通过，93 条路由。系统全程 read_only / disabled / not_granted。Pre-Phase1 代码审核完成（metrics 重写 + SSRF + race fix）。下一步：Phase 2 本地策略补齐（技术指标引擎 + Funding Rate + Bollinger + Grid + Strategy Orchestrator）→ Beta 运行数据积累 → M 章。
