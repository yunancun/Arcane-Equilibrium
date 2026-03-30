# OpenClaw / Bybit AI Agent 交易系统
# CLAUDE.md — 主项目日志（Claude Code 项目指令文件）
# 备注：本文件即"主日志"，GitHub 根目录 README.md 为"Git 日志"
# 最后更新：2026-03-30（TW 工程審核 — Phase 3 GovernanceHub 集成 + 缺口校准）

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

## 三、当前系统状态（2026-03-30 TW 工程審核）

```
测试：1,566 全通过（含 46 治理 Hub 测试 + 92 集成测试 · 2 跳过）
路由：121+ 条（113 原有 + 8 治理 API 端点）
治理：GovernanceHub 已实例化，4 核心 SM 已接入运行时（SM-01/SM-02/SM-04/EX-04）
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

Session 10 修复（2项）：
  B1: _recompute_pnl() 从 positions[].holding_cost.ai_cost_attributed_usd 汇总 total_ai_cost（此前永远是 0.0）
  S1: PipelineBridge._check_stops() 提交止损单前先验证仓位是否还在，防止 RiskManager 已平仓时 StopManager 错误开出反向仓

Session 11 改进（1项）：
  R1: regime 感知止损/止盈/时间三维调整
    - REGIME_STOP/TP/TIME_MULTIPLIERS 三组乘数常量（risk_manager.py）
    - compute_dynamic_stop_pct() 新增 regime 参数（volatile→1.5×, squeeze→0.6×）
    - check_positions_on_tick() 止盈和时间止损均按 regime 缩放
    - _on_position_open() 将 regime 写入 paper engine 持仓，StopManager time_stop 按 regime 调整
    - squeeze 时间止损约 14h，trending 约 72h（相比默认 48h）
    - 事后审计修复：_store → store（静默 AttributeError 导致 regime 未实际写入，已修复）

Session 12 修复（4项）：
  F1: compute_partial_fill_qty() 添加尾量检查（remaining < 1% of qty → 一次性成交）
    - 修复 fill 碎片化：25-30 次成交/单 → ≤10 次/单
    - 连锁效果：n_active_orders 减少 → AI 注意力税燃烧率从 HIGH 降至 MEDIUM/LOW
  F2: check_positions_on_tick() 注意力税平仓添加最低 edge 保护
    - edge_usd > 0 改为 edge_usd > taker_close_fee_usd（notional × 0.00055）
    - 修复 0% 胜率根因：微小盈利（如 $0.0003）触发平仓，扣手续费后净亏损
  E1a: PipelineBridge._on_round_trip_complete() 重构为 _emit_round_trip()
    - 提取核心逻辑，intent 路径和 tick 路径共用
  E1b: PipelineBridge.on_tick_result() 新增 + MarketDataDispatcher 传递 tick_result
    - tick 路径平仓（risk_auto_close/时间止损/软止损）现在也触发 E1 观察记录
    - 通过 fill 方向与 _open_positions 对比检测平仓，计算 close_pnl 写入观察

Session 12 GUI 修复（5项）：
  G1: tab-paper 活跃订单过滤器修复（paper_order_working/paper_order_partially_filled）
    - 原状态名 'new'/'partially_filled'/'open' 与引擎实际状态不符，导致订单列表永远为空
  G2: tab-paper 行情价格小数位自适应（<$0.01=6位，<$1=4位，>=$1=2位）
    - 修复便宜代币（如 ONT=$0.37）显示为 $0.00 的问题
  G3: tab-paper 成交历史时间戳修复（ts_ms → filled_at → timestamp 优先序）
  G4: tab-paper 余额显示改为当前余额（从 metrics.current_balance 更新，非固定初始值）
  G5: tab-demo Paper vs Demo 对比修复（提取 result.list[0] 才能读到 totalRealizedPL 等字段）
    - 新增性能指标折叠区（Total Equity/Available Balance/Margin Rate/PnL）
    - 移除 /strategy/demo/status 404 回退路径（不存在该端点）
  G6: tab-learning 概览计数修复（从 /learning/feed → totals 读取，非 /learning/overview）
    - loadFeed() 改用 observations_recent / lessons_recent 数组，空时显示总计数

Phase 3 治理集成（2026-03-30，另一 session 完成）：
  T3-1: governance_hub.py（819 行）— 中央治理编排层
    - GovernanceHub 类：RLock 保护的跨 SM 操作
    - 实例化 SM-01/SM-02/SM-04/EX-04 四个核心状态机
    - 跨 SM 级联回调：风控升级→授权收缩/冻结，对账异常→风控升级，授权冻结→吊销所有活租约
    - 100ms TTL 热路径缓存（is_authorized 高频调用优化）
    - 审计写盘（JSONL，0o600 权限）
  T3-2: governance_routes.py（525 行）— 8 个治理 API 端点
    - GET /governance/status · GET /governance/auth/status · POST /governance/auth/approve
    - GET /governance/risk/level · POST /governance/risk/override
    - POST /governance/reconcile · GET /governance/leases · POST /governance/health-check
    - Operator 角色验证 + 输入 HTML 消毒 + 通用错误消息
  T3-3: 集成接入点
    - PaperTradingEngine.submit_order() → is_authorized() + acquire_lease()
    - RiskManager.check_pre_trade_gate() → is_authorized()
    - PipelineBridge.on_tick() → is_authorized()
    - paper_trading_routes.py → GovernanceHub 单例实例化
  T3-4: 安全审核 — 9 项 CRITICAL/HIGH 修复
    - Operator 角色验证（/auth/approve, /risk/override）
    - 审计文件 chmod 0o600
    - 输入消毒防存储型 XSS
    - 原子性 auth check + lease create（防竞态）
    - 通用错误消息（防信息泄露）
    - 实际调用 SM 转换（之前是 stub）
  T3-5: RiskGovernorStateMachine.get_status() 死锁修复
    - 嵌套锁获取导致死锁 → 直接访问 _state.level
  合规度提升：~28% → ~65%（4 核心 SM 从 standalone 变为 wired）

决策：win_rate > 20% 前不接入 AI 咨询（C1/I1/A1），避免在随机决策上叠加AI成本

Round 2 Cowork 审计（2026-03-30）：
  三路并行验证：测试 + 代码级整合验证 + Gap 殘留分析
  测试基准：1798 passed, 0 failed, 2 skipped（与 Round 1 完全吻合）
  七大整合点全部代码级确认接入：
    1. GovernanceHub 注入 — ✅ paper_trading_routes:167,289-290
    2. is_authorized() fail-closed — ✅ paper_trading_engine:898-917
    3. acquire_lease() fail-closed — ✅ paper_trading_engine:962-986
    4. SM 跨级联 — ✅ governance_hub:936-979
    5. Portfolio Risk Control — ✅ risk_manager:749
    6. ProtectiveOrderManager — ✅ paper_trading_engine:1403
    7. Governance REST (18 端点) — ✅ governance_routes 完整註冊
  治理合规率：65% → 88%（+23%）
  Phase 0 Gap 解决率：15/17（88%）
  剩馀長期 Gap：Multi-Agent（僅 Scout）+ Learning L2-L5（佔位符）

Round 2 Batch 3（2026-03-30 Plan A2 — ScoutAgent as OpenClaw local proxy）：
  方案：ScoutAgent 作为 OpenClaw 本地代理
    - OpenClaw 通过 REST 推送外部情报（新闻/事件/情绪）
    - ScoutAgent 处理本地 Bybit 市场数据（成交量/资金费率/regime）
    - 双通道统一汇入 MessageBus → Strategist/Guardian
  新增文件：
    - scout_routes.py（667 行）— 5 端点 REST API（Token 认证）
      POST /scout/market-signal — OpenClaw 推送市场信号
      POST /scout/event-alert  — OpenClaw 推送事件警报
      GET  /scout/status       — 获取 ScoutAgent + MessageBus 状态
      GET  /scout/intel        — 查询最近情报对象
      GET  /scout/alerts       — 查询最近事件警报
    - test_scout_integration.py（1122 行 · 45 测试）
  修改文件：
    - phase2_strategy_routes.py — 初始化 ScoutAgent + MessageBus + 注入 PipelineBridge + 接线 scout_routes
    - pipeline_bridge.py — set_scout_agent/set_message_bus + _invoke_scout_scan（300s 间隔）+ 成交量异常检测 + 资金费率尖峰检测
    - main.py — 注册 scout_router
  Multi-Agent 接入：multi_agent_framework.py 从 STANDALONE → WIRED（ScoutAgent + MessageBus 已接入运行时）
  EX-06 合规度提升：ScoutAgent 实际接入 PipelineBridge on_tick + REST 双通道
  接入率：12/22 = 55%（从 11/22 = 50% 提升）

Round 2 Batch 4（2026-03-30 — Learning 自动晋升 + 接入率审计修正 + 0% 胜率根因分析）：
  B4-T1 (E1b): 接通 Learning 自动晋升管线
    - pipeline_bridge.py: 新增 _learning_tier_gate 属性 + set_learning_tier_gate() + _learning_stats 追踪
    - pipeline_bridge.py: 新增 _try_learning_promotion() 方法（70 行）— 每次 round-trip 后自动检查晋升
    - pipeline_bridge.py: _emit_round_trip() 末尾调用 _try_learning_promotion(close_pnl)
    - phase2_strategy_routes.py: 注入 LEARNING_TIER_GATE 到 PipelineBridge
    - L1→L2 条件：observations ≥ 500 + win_rate ≥ 20%
  B4-T2 (TW): 接入率重新审计
    - 原标 12/22 = 55% → 实际 19/22 = 86%
    - 7 个模组原标 STANDALONE 实已在 paper_trading_routes.py 中实例化并注入：
      learning_tier_gate / ttl_enforcer / protective_order_manager / portfolio_risk_control /
      recovery_approval_gate / shadow_decision_builder / change_audit_log
    - 真正 STANDALONE 仅 3 个：oms_state_machine / paper_live_gate / scout_routes
  B4-T3 (R1): 0% 胜率根因分析
    - 根因非 bug，是风控参数结构性错配：
      1. 3% 追踪止损太紧（crypto 正常波动 1-3%，止损被噪音触发）
      2. 0.11% 手续费（双向 taker）要求每笔立即 +0.11% 才保本
      3. squeeze regime 0.3x 时间乘数 → 14h 强制平仓（均值回归需 24-48h）
      4. 无交易前 edge 检查（数学不可行的交易也被执行）
    - 推荐修复：加宽止损至 5%/ATR动态 + 入场改 limit order + squeeze 乘数改 1.0x + 添加 edge 过滤
  B4-T4 (E4): 新增 test_learning_promotion_integration.py（15 测试全通过）
  接入率：19/22 = 86%（Batch 4 审计修正 · 从误标 55% 更正）

Round 2 Batch 5-C（2026-03-30 — L1 本地推理管道验证 · Ollama/Qwen 3.5 接入）：
  基础设施：Ollama 已完整部署并优化，API http://127.0.0.1:11434，模型 qwen3.5:27b-q4_K_M
  C-T1 (E1a): 新建 ollama_client.py（~350 行）
    - OllamaClient 类：HTTP 调用 /api/generate + /api/chat，可配模型/超时/temperature
    - OllamaConfig 数据类：支持环境变量 OLLAMA_BASE_URL / OLLAMA_MODEL / OLLAMA_TIMEOUT
    - OllamaResponse 数据类：text + latency + eval_count + tokens_per_second + cost_usd=0.0
    - 便捷方法：classify()（情绪分类）+ judge_edge()（交易 edge 判断，为方向 B 预留）
    - is_available()：连通性检测 + 模型匹配 + 60s TTL 缓存
    - 线程安全单例 get_ollama_client() + reset_ollama_client()
  C-T2 (E1b): 改造 layer2_tools.py
    - LocalLLMWebSearchProvider.is_available()：subprocess → get_ollama_client().is_available()
    - LocalLLMSearchProvider.is_available()：subprocess → get_ollama_client().is_available()
    - LocalLLMSearchProvider.search()：subprocess.run(["ollama","run","llama3.2",...]) → client.generate()
    - 模型从硬编码 llama3.2 改为可配（默认 qwen3.5:27b-q4_K_M）
  C-T3 (E1a): 改造 layer2_engine.py — L1 triage 本地 fallback
    - 新增 L1_LOCAL_TRIAGE_PROMPT 常量
    - l1_triage(): Anthropic client=None 时回退到 _l1_triage_local()
    - 新增 _l1_triage_local() 方法（~75 行）：Ollama 生成 + JSON 解析 + 自由文本启发式 + 超时处理
    - 成本归零：triage_cost_usd=0.0 + triage_source="local_ollama"
  C-T4 (E4): 新增 test_ollama_integration.py（28 测试）
    - TestOllamaClient（15）：HTTP mock / 超时 / 重试 / 分类 / edge 判断 / 单例 / 环境变量
    - TestLocalLLMSearchProvider（3）：搜索委托 / 可用性委托 / 错误处理
    - TestL1TriageLocalFallback（8）：fallback 触发 / JSON 解析 / 自由文本启发 / Ollama 不可用 / 超时
    - TestOllamaResponseProperties（2）：tokens/s 计算 / 零值边界

Round 2 Batch 6（2026-03-30 — ★ 0% 胜率四根因全修复）：
  B6-T1 (E1a): 加宽追踪止损
    - phase2_strategy_routes.py: StopConfig trailing_stop_pct 3.0 → 5.0
    - pipeline_bridge.py: 动态追踪止损 = max(5%, min(15%, 2×ATR/价格×100))
    - 原因：3% 太紧，加密货币正常波动 1-3%，噪音频繁触发止损
  B6-T2 (E1b): 入场改 limit order
    - local_model_tools/strategies/base.py: OrderIntent default order_type "market" → "limit"
    - pipeline_bridge.py: limit 单无明确价格时自动填入当前市场价
    - 原因：taker 双邊 0.055% × 2 = 0.11% 回合费用 → maker 0.02% × 2 = 0.04%，节省 ~66%
  B6-T3 (E1a): squeeze 时间乘数 0.3 → 1.0
    - risk_manager.py: REGIME_TIME_MULTIPLIERS["squeeze"] 0.3 → 1.0
    - 原因：均值回归策略需 24-48h 完成，0.3x 导致 14h 强制平仓
  B6-T4 (E4): 新增 test_winrate_param_fixes.py（23 测试）
    - TestTrailingStopWidened（5）/ TestLimitOrderDefault（4）/ TestSqueezeTimeMultiplier（5）
    - TestFeeImpactCalculation（4）/ TestB6IntegrationScenarios（2）/ TestRegressionNoOldBrokenBehavior（3）
  0% 胜率根因修复状态：4/4 全部修复
    #1 追踪止损太紧 ✅ → 动态 max(5%, 2×ATR)
    #2 taker 手续费过高 ✅ → limit order (maker fee)
    #3 squeeze 强制平仓 ✅ → 乘数 1.0x（允许 48h）
    #4 无 edge 过滤 ✅ → Qwen pre-trade edge filter（Batch 5-B）

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
  ✅ B2/G3/A2 三项 bug 修复 + 18 项验证测试（2026-03-28 Session 9）
  ✅ B1/S1 两项修复 + 7 项验证测试（2026-03-28 Session 10）
  ✅ R1 regime 感知止损/止盈/时间三维调整 + 8 项验证测试（2026-03-28 Session 11）
  ✅ Phase 2 治理模組 T2.01–T2.23 全部实现（2026-03-29）— 21 模组 · 1,522 测试 · 52,211 行代码
  ✅ Phase 2 PM 品质审核通过（2026-03-29）— 整体评级 4/5 · 0 个 P0 blocker
  ✅ Phase 2 TW 註釋品質審核通过（2026-03-30）— 評級 9.5/10 · 100% 雙語覆蓋 · 0 Critical
  ✅ Phase 3 GovernanceHub 集成（2026-03-30）— Hub 819行 + 8路由 525行 + 4SM接入 + 安全审核 9项修复
  ✅ Phase 3 RiskGovernor 死锁修复（2026-03-30）— get_status() 嵌套锁 → 直接属性访问
  ✅ 合规度校准（2026-03-30 TW 审核）— ~28% → ~65%，接入率 7/22 → 11/22
  ✅ Round 2 Cowork Phase 0 审计（2026-03-30）— 三路并行验证 · 合规率 65%→88%
  Paper Trading 数据继续积累（等胜率数据；新规则+学习机制运行中）
  等胜率 > 20% 后：接入 AI 咨询（C1/I1/A1）
  Paper Trading + Bybit Demo 数据对比分析
  GUI 细节打磨（移动端适配 / 图表增强 / 实时 PnL 折线图）

待处理问题（已记录，非紧急）：
  - ✅ MACrossoverStrategy 双边持仓状态漂移 → 已修复（Session 9 A2: on_fill 链路）
  - ✅ realized_pnl 毛利问题 → 已修复（Session 9 B2: net_realized_pnl 字段）
  - ✅ StrategyAutoDeployer active_count +1 → 已修复（Session 9 G3: | {symbol}）
  - ✅ StopManager 与 RiskManager 双重止损 → 已修复（Session 10 S1: _check_stops 仓位验证）
  - ✅ regime 只过滤入场、不影响止损/持仓时间 → 已修复（Session 11 R1: 三维乘数）
  - Learning Cockpit GUI 数据展示（依赖 E1 数据积累后再完善）
  - RiskManager daily loss 跨天不重置（已验证有重置逻辑，影响极小）

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

### 交接与索引

| 内容 | 文件位置 |
|------|---------|
| GUI 交接文档（Control API v1 + GUI v1 阶段交接） | `docs/handoffs/2026-03-25_api_gui_handoff/` |
| 文档目录规范 + 全量索引 | `docs/README.md` |

---

## 十三、一句话状态

> 截至 2026-03-30 Round 2 Cowork 审计：Phase 3 GovernanceHub 已集成（七大整合点代码级确认 · 1798 测试全通过 · 治理合规率 65%→88%）。121+ 路由，接入率 7/22→11/22。Phase 0 Gap 解决率 15/17（88%）。剩馀長期缺口：Multi-Agent（僅 Scout）+ Learning L2-L5（佔位符）。系统全程 read_only / disabled / not_granted。
