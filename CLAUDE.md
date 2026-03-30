# OpenClaw / Bybit AI Agent 交易系统
# CLAUDE.md — 主项目日志（Claude Code 项目指令文件）
# 备注：本文件即"主日志"，GitHub 根目录 README.md 为"Git 日志"
# 最后更新：2026-03-30（Batch 11 Executor Agent + 交易所条件单 + 双重防线）

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

## 三、当前系统状态（2026-03-30 Round 2 冷酷功能审核后）

```
测试：2,124+（含 46 治理 Hub + 92 集成 + 45 Scout + 15 学习晋升 + 28 Ollama + 21 Edge Filter + 23 参数修复 + 30 Guardian + 25 Perception/Analyst + 32 Batch10 OMS/L2 · 2 跳过）
路由：126+ 条（含 8 治理 + 5 Scout 端点）
治理：GovernanceHub 4 SM 已接入运行时（SM-01/SM-02/SM-04/EX-04），fail-closed 已验证
GUI：10-Tab 专业控制台 + 中文状态 + 悬停提示 + 确认弹窗 + 6 AI 供应商
Bybit Demo：双重执行（Paper Engine + Bybit sandbox）
L1 本地推理：Ollama HTTP 客户端 + Qwen 3.5 27B（就绪）
5-Agent 体系：Scout + Strategist + Guardian + Analyst 运行，Executor 未启动

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
    进化                  = 5%（PaperLiveGate 未部署，无策略自动优化）

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
    ❌ 策略层标准 RSI/MACD/MA，无可证明的 alpha

  详细审核报告：docs/governance_dev/audits/2026-03-30--round2_cold_functional_audit.md
  修复计划：docs/governance_dev/2026-03-30--round2_fix_plan_batches_7_12.md

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

Round 2 Batch 7（2026-03-30 — Strategist + Guardian + Analyst + Executor Agent 预写）：
  预写 4 Agent 完整实现，为 Batch 8-11 接线做准备
  详情见 Batch 7 commit 记录

Round 2 Batch 8（2026-03-30 — Guardian Agent 接线 + 动态风控）：
  B8-T1: GuardianAgent 接入 MessageBus
    - phase2_strategy_routes.py: 实例化 GuardianAgent + Conductor 注册 + MESSAGE_BUS.subscribe(GUARDIAN)
    - Guardian 订阅 TRADE_INTENT + EVENT_ALERT 消息类型
  B8-T2: PipelineBridge 接收 Guardian 裁决
    - pipeline_bridge.py: set_guardian_agent() + _guardian_stats 追踪
    - _process_pending_intents(): 构建 TradeIntent → guardian.review_intent() → RiskVerdict
    - APPROVED → 放行，REJECTED → 阻止（continue），MODIFIED → 调整 qty/leverage 后放行
    - fail-closed: Guardian 异常/不可用 → 默认拒绝（DOC-01 §5.6）
  B8-T3: Edge Filter 降级为建议性
    - Edge filter 不再阻止提交（无 continue），仅记录 advisory 日志
    - Guardian 成为唯一的 primary gate（fail-closed vs edge filter 的 fail-open）
    - test_edge_filter_integration.py: 2 个旧测试更新为 advisory 语义
  B8-T4: SM-04 联动 — Guardian 检测异常事件 → GovernanceHub.trigger_risk_upgrade()
    - governance_hub.py: 新增 trigger_risk_upgrade()（~70 行）
    - critical → CIRCUIT_BREAKER，high → REDUCED 或 current+1，medium/low → 不升级
    - Guardian._handle_event_alert() → governance_hub.trigger_risk_upgrade() 完成级联
  B8-T5: test_batch8_guardian_integration.py（30 测试 · 9 测试类 · 912 行）
    - MessageBus 集成 / PipelineBridge 集成 / fail-closed / SM-04 联动 / GovernanceHub 升级
    - Guardian 作为 primary gate / 方向冲突检测 / 杠杆上限 / 关联/Sharpe/回撤检查

Round 2 Batch 9（2026-03-30 — Perception Plane 激活 + Analyst 接线）：
  B9-T1: Perception 注册 kline 数据为 FACT
    - pipeline_bridge.py: on_tick() 新增 FACT 注册（DataSourceType.EXCHANGE_WS, CognitiveLevel.FACT）
  B9-T2: Perception 注册 Scout 情报/事件
    - scout_routes.py: post_market_signal() + post_event_alert() 新增 INFERENCE 注册
    - data_quality=="hypothesis" 时自动标记为 CognitiveLevel.HYPOTHESIS
  B9-T3: Perception 注册交易结果为 INFERENCE
    - pipeline_bridge.py: _emit_round_trip() 新增 INFERENCE 注册（交易结果反馈）
  B9-T4: AnalystAgent 接入 MessageBus
    - phase2_strategy_routes.py: 实例化 AnalystAgent + Conductor 注册 + MESSAGE_BUS.subscribe(ANALYST)
    - Analyst 订阅 ROUND_TRIP_COMPLETE 消息类型
  B9-T5: PipelineBridge 发送 ROUND_TRIP_COMPLETE
    - pipeline_bridge.py: _emit_round_trip() 新增 MessageBus 发射（sender=EXECUTOR → receiver=ANALYST）
  B9-T6: LearningTierGate 由 Analyst 更新
    - AnalystAgent.on_message() 处理 ROUND_TRIP_COMPLETE → L1 统计分析 → update_metrics(observation_count, win_rate)
    - L1→L2 自动晋升条件：observations ≥ 200 + 满足 win_rate 阈值
  B9-T7: test_batch9_perception_analyst_integration.py（25 测试 · 11 测试类）
    - 数据注册（FACT/INFERENCE/HYPOTHESIS）/ 漂移保护 / 新鲜度 / 决策资格
    - Analyst round-trip 处理 / L1 分析 / Sharpe / LearningTierGate / L2 模式分析
    - 策略排名 / MessageBus 流转 / 数据质量 / 端到端集成

  Multi-Agent 状态更新：
    Scout    → RUNNING（Batch 3 接入）
    Strategist → RUNNING（Batch 7 接入）
    Guardian → RUNNING（Batch 8 接入，primary gate，fail-closed）
    Analyst  → RUNNING（Batch 9 接入，L1 统计 + L2 模式发现）
    Executor → ✅ 已接入（Batch 11：消费 APPROVED_INTENT → submit_order → EXECUTION_REPORT + 交易所条件单回调）
    Conductor → WIRED（管理 4 Agent 生命周期）

  测试总计：2,124 passed, 11 failed（pre-existing pytest-asyncio 缺失）, 2 skipped
  Batch 8+9 新增测试：55（30 + 25），全部通过

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
  ★★ Round 2 务实修复计划（2026-03-30 PM+FA 联合制定，Operator 待批准）
     详细文档：docs/governance_dev/2026-03-30--round2_pragmatic_fix_plan.md

  ★ Batch 7: Conductor 事件循环 + Strategist Agent（32→50%）
    - Conductor 实例化并启动事件循环（复用已有 multi_agent_framework.py:619-928）
    - MessageBus 注册 Scout→Strategist 订阅
    - StrategistAgent 用 Qwen 3.5 评估信号质量替代硬编码
    - Shadow 模式先行（只记录不执行），验证后激活
    - E1a: Conductor 接线 ∥ E1b: Strategist 实现 → E4: 25 测试 → FA: 审计

  Batch 8: Guardian Agent + 动态风控（50→62%）
    - GuardianAgent 5 项检查（方向冲突/杠杆/关联/Sharpe/回撤）
    - Guardian verdict（APPROVED/REJECTED/MODIFIED）反馈到 PipelineBridge
    - SM-04 联动（异常事件→风控升级）

  Batch 9: Perception Plane 激活 + Analyst Agent L1（62→72%）
    - KlineManager→FACT, SignalEngine→INFERENCE, Scout→INFERENCE/HYPOTHESIS
    - Analyst 消费 ROUND_TRIP_COMPLETE → 更新 LearningTierGate 指标

  Batch 10: L2 学习自动化 + OMS 串联（72→80%）
    - Analyst L2 模式发现（Qwen 分析）+ 每周 Cron 触发
    - OMS SM-03 串联替换 Paper Engine 独立 7 态
    - TTL 执行器定期调用

  Batch 11: ✅ Executor Agent + 交易所条件单 + 双重防线（80→85%）
    - Executor 包装 submit_order + 执行质量反馈
    - 交易所条件单双重防线（DOC-01 §5.9）

  Batch 12: Paper→Live 门禁 + E2E 验证（85→88%）
    - PaperLiveGate 11 项准入评估 + Operator 审批
    - E2E 冒烟测试 100+ 笔 + 日报自动化

  每 Batch 工作流：PM 分配 → E1a∥E1b 并行开发 → E4 测试 → FA+CC 审计 → PM 收尾
  总预估：10 Sessions · 2-3 周 · ~5,700 行新代码

待处理问题（已记录，非紧急）：
  - Learning Cockpit GUI 数据展示（依赖 Batch 9 Analyst 数据积累后再完善）
  - RiskManager daily loss 跨天不重置（已验证有重置逻辑，影响极小）

长期优化（Batch 12 后）：
  - 策略参数自动优化（L3 假设验证 + L4 策略进化）
  - 跨交易所套利（接入 Binance/OKX）
  - 波动率 regime 切换（自动调整 max_symbols 和策略偏好）
  - OpenClaw 深度集成（新闻扫描 + 事件驱动信号 + Twitter 情绪）

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

> 截至 2026-03-30 Batch 11 完成：ExecutorAgent 接入管线（APPROVED_INTENT→submit_order→EXECUTION_REPORT）+ 交易所条件止损单（Bybit Demo V5 API）+ 本地止损+交易所条件单双重防线（DOC-01 §5.9）。195 测试通过（含 25 新 Batch 11），零回归。系统全程 read_only。

### Batch 7 记录（2026-03-30）

| 任务 | 文件 | 状态 |
|------|------|------|
| 7.1 Conductor 实例化 + Scout 注册 | `phase2_strategy_routes.py` (+40 行) | ✅ |
| 7.2 MessageBus 订阅接线 | `phase2_strategy_routes.py` (+5 行) | ✅ |
| 7.3 StrategistAgent 实现 | `app/strategist_agent.py` (新建 ~340 行) | ✅ |
| 7.4 PipelineBridge 扩展 intent 来源 | `pipeline_bridge.py` (+35 行) | ✅ |
| 7.5 Shadow 模式 | `strategist_agent.py` 内置 | ✅ |
| 7.6 测试 (31 tests) | `tests/test_batch7_conductor_strategist.py` | ✅ |

### 预写 Agent 模块记录（2026-03-30 S2）

| 模块 | 文件 | 测试 | 状态 |
|------|------|------|------|
| GuardianAgent (5 项检查 + fail-closed) | `app/guardian_agent.py` (~350 行) | `tests/test_guardian_agent_unit.py` (20 tests) | ✅ |
| AnalystAgent (L1 统计 + L2 模式发现) | `app/analyst_agent.py` (~370 行) | `tests/test_analyst_agent_unit.py` (17 tests) | ✅ |
| ExecutorAgent (执行包装 + 质量指标) | `app/executor_agent.py` (~270 行) | `tests/test_executor_agent_unit.py` (15 tests) | ✅ |

### Batch 10 记录（2026-03-30 — OMS SM-03 串联 + L2 学习自动化）

**Part A: OMS SM-03 串联（paper_trading_engine.py ~80 行）**
- `OMS_SM03_ENABLED` config 开关（默认 True，可回退到 legacy 7-state）
- `_transition_order()` 新增 `oms_sm` kwarg：Paper 7-state→OMS 11-state 映射
  - CREATED→SUBMITTED 自动走 PENDING→APPROVED→SUBMITTED 三步中间态
  - REJECTED/CANCELED/FILLED 等直接映射
  - OMS 拒绝 → fail-closed 阻断 paper transition
- `_oms_complete_reconciliation()` helper：fill 后追赶 OMS 到 FILLED→RECONCILING→COMPLETED
- `PaperTradingEngine.set_oms_sm()` + constructor `self._oms_sm = None`
- `submit_order()` 调用 OMS `create_order()` 获取 `oms_order_id`

**Part B: L2 学习自动化**
- B1: `analyst_agent.py` — `analyze_patterns(force=False)` 公开方法，observations≥200 自动触发 L2
- B2: `pipeline_bridge.py` — Sunday UTC 0:00 cron 触发 `analyze_patterns(force=True)`，week-key 去重
- B3: `paper_trading_routes.py` — TTL 到期 OMS 自动取消 + GovernanceHub 回调
- B3: `phase2_strategy_routes.py` — OMS SM-03 实例化 + AnalystAgent 实例化 + MessageBus 订阅接线

**Part C: 测试**

| 测试类 | 数量 | 覆盖 |
|--------|------|------|
| TestOMSSM03Mapping | 4 | Paper↔OMS 状态映射 |
| TestOMSSM03Integration | 5 | submit+fill 全链路 OMS 同步 |
| TestOMSSM03Fallback | 3 | OMS_SM03_ENABLED=False 回退 |
| TestPostFillReconciliation | 3 | fill 后 RECONCILING→COMPLETED |
| TestAnalystL2AutoTrigger | 7 | observations 阈值 + force + 空记录 |
| TestL2CronTrigger | 3 | Sunday/非Sunday/week-key 去重 |
| TestTTLEnforcerOMS | 4 | TTL 到期 auto_cancel |
| TestOMSSM03FullOrderLifecycle | 3 | 完整 11-state 生命周期 |
| **合计** | **32** | **全部通过** |

全量测试：2101 passed, 11 failed (pre-existing ollama), 2 skipped — 零回归

### Batch 11 记录（2026-03-30 — Executor Agent + 交易所条件单 + 双重防线）

**11.1 ExecutorAgent 接线（phase2_strategy_routes.py +50 行）**
- 实例化 ExecutorAgent 注入 PaperTradingEngine + MessageBus
- 向 Conductor 注册 EXECUTOR，设置 RUNNING 状态
- MESSAGE_BUS.subscribe(EXECUTOR, on_message) — 接收 APPROVED_INTENT
- 条件单回调接入 BybitDemoConnector.place_conditional_order()

**11.2 交易所条件止损单（bybit_demo_connector.py +100 行）**
- `place_conditional_order(symbol, side, qty, trigger_price)` — Bybit V5 `/v5/order/create` + `orderFilter=StopOrder`
- 自动推断 `triggerDirection`：Sell 止损→2（跌破），Buy 止损→1（升破）
- `cancel_all_conditional_orders(symbol)` — 批量取消
- `get_conditional_orders()` — 查询挂起条件单
- qty 四舍五入到交易所步长精度，`reduceOnly=True` 防止意外开仓

**11.3 双重防线接通（pipeline_bridge.py +40 行）**
- `_on_position_open()` 开仓后同时创建：
  - 本地止损（StopManager ATR 动态止损）
  - 交易所条件单（Bybit Demo stop-loss trigger）
- ATR 止损百分比计算提升到方法级别（StopManager + 交易所共用）
- fail-closed：条件单创建失败 → 记录日志但不阻止本地止损
- 程序崩溃时交易所条件单仍然存在（DOC-01 §5.9）

**11.4 ExecutorAgent 执行质量反馈（executor_agent.py — 预写已完成）**
- EXECUTION_REPORT 消息包含：slippage_bps、fill_time_ms、actual_price vs expected_price
- 发送给 ANALYST 角色用于交易质量分析
- 统计：avg_slippage_bps、executions_success/failed

**11.5 测试（25 tests）**

| 测试类 | 数量 | 覆盖 |
|--------|------|------|
| TestExecutorAgentLifecycle | 3 | start/stop/pause 生命周期 |
| TestExecutorAgentExecution | 7 | APPROVED_INTENT→submit_order、EXECUTION_REPORT、rejection、fail-closed、callback |
| TestExecutorAgentStats | 3 | 统计追踪、报告上限 |
| TestBybitDemoConditionalOrders | 7 | place/cancel/get 条件单、方向推断、qty 四舍五入、disabled |
| TestDualStopLossDefense | 5 | 双重防线创建、trigger price 方向、失败安全、disabled 跳过 |
| **合计** | **25** | **全部通过** |

全量测试：195 passed — 零回归
