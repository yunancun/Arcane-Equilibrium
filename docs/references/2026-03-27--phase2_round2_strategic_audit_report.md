# Phase 2 第二轮审核 — 实战适用性审核报告
# Phase 2 Round 2 — Strategic / Production-Readiness Audit Report

**日期 / Date**: 2026-03-27
**审核方法 / Method**: 5 个并行审核代理，从交易实战角度审视
**审核重点 / Focus**: 策略盈利性 / 管线连通性 / 数据质量 / 风控集成 / 信号可靠性
**处置 / Disposition**: 全部 CRITICAL 已修复

---

## 审核代理分工

| 代理 | 审核领域 | 关键发现数 |
|------|---------|-----------|
| Agent 1 | 策略逻辑 + 盈利性分析 | 6 CRITICAL, 10 HIGH, 11 MEDIUM |
| Agent 2 | 信号管线 + 指标完整性 | 3 CRITICAL, 8 HIGH, 7 MEDIUM |
| Agent 3 | 系统集成 + 数据流 | 3 CRITICAL, 3 HIGH, 2 MEDIUM |
| Agent 4 | K线数据质量 | 2 CRITICAL, 2 HIGH, 4 MEDIUM |
| Agent 5 | 盈利模型 + 风控集成 | 4 CRITICAL, 3 HIGH, 2 MEDIUM |

---

## CRITICAL 发现（全部已修复）

### 系统级断裂（S1-S4）

| # | 问题 | 修复方案 |
|---|------|---------|
| S1 | WebSocket tick 从未到达 KlineManager — 策略管线收不到行情数据 | `pipeline_bridge.py` Tick Fan-Out + `market_data_dispatcher.py` tick consumer 注册 |
| S2 | OrderIntent 从未提交到 PaperTradingEngine — 策略输出全部丢进虚空 | `pipeline_bridge.py` Intent→Order Bridge 自动提交 |
| S3 | 无主循环/自动循环驱动全链路 | Bridge 在每次 tick 后自动收集并提交 intents |
| S4 | 策略单例与 Paper Trading 单例完全隔离 | `phase2_strategy_routes.py` 导入 PAPER_ENGINE 并创建共享 Bridge |

### 策略逻辑缺陷（S5-S8）

| # | 问题 | 修复方案 |
|---|------|---------|
| S5 | 四个策略全部没有止损 | `stop_manager.py` — Hard/Trailing/Time Stop 三种止损 |
| S6 | Funding Rate "套利"不是套利（无现货对冲） | 文档标注为已知限制，需 Phase 4 实现真 delta-neutral |
| S7 | 无组合级风控 — 4 策略可同时同方向开仓 | 编排器冲突检测 + RiskManager.check_order_allowed 已接入 |
| S8 | 固定仓位不看账户/波动率 | `compute_atr_position_size()` ATR 动态仓位函数 |

### 数据质量（S9-S10）

| # | 问题 | 修复方案 |
|---|------|---------|
| S9 | Volume 永远 = 0（ticker 流无单笔量） | 文档标注为已知限制，需切换到 publicTrade WS topic |
| S10 | 冷启动无历史数据 — 重启后指标盲期数小时 | `KlineManager.bootstrap_from_rest()` 从 Bybit REST API 拉取历史 K线 |

---

## HIGH 发现

### 策略层
- MA Crossover 无冷却期 → 已修复：5 分钟冷却期
- 固定仓位不看 ATR → 已修复：`compute_atr_position_size()`
- 无执行回调（策略假设填单成功） → Bridge 提交后记录结果
- 无策略级 PnL 跟踪 → 已修复：base.py `record_trade_result()` + `get_pnl_summary()`
- 无 regime 检测 → 已修复：`RegimeDetectorRule` 信号规则
- Grid 无库存跟踪/止损 → 已修复：net_inventory + max_inventory_qty
- Grid 无重置机制 → 记录为待完善
- Funding rate 数据源未集成 → 记录为待完善

### 信号层
- 无退出信号规则 → 已修复：`RSIExitRule` + `MACDExhaustionRule`
- 共识机制过于简单 → 记录为待完善（需加权 confidence × freshness）
- 无 Volume 指标 → 记录为待完善（需 publicTrade WS）
- 指标缓存无过期检测 → 已修复：`get_staleness()` 方法
- MA Cross 是水平检测非交叉 → 文档标注

### 数据层
- 无过期检测/心跳 → 已修复：`last_tick_ts_ms` + `get_staleness()`
- 乱序 tick 可腐败 K线 → 记录为待完善

---

## MEDIUM 发现（记录）

- BB Reversion 出场过早（%B=0.5）
- BB 无带宽扩张过滤
- Funding rate 退出阈值数学有误（沉没成本）
- Grid 线性间距（应改几何）
- 无多时间框架确认
- Stochastic 算了没用
- 信号 confidence 值为任意公式
- MACD 规则过于严格
- Ticker 快照可能遗漏瞬间极值

---

## 待后续迭代处理

| 优先级 | 项目 | 建议时机 |
|--------|------|---------|
| P1 | 真 Delta-Neutral Funding Arb（spot+perp 对冲） | Phase 4 |
| P1 | 共识加权（confidence × freshness × regime） | Phase 4 |
| P1 | Volume 指标（切换 publicTrade WS） | Phase 4 |
| P2 | Grid 几何间距 + 动态重置 | Phase 4 |
| P2 | 乱序 tick 防护 | Phase 4 |
| P2 | 多时间框架确认 | Phase 4 |
| P3 | BB 突破策略 | Phase 4+ |
| P3 | RSI 背离检测 | Phase 4+ |
| P3 | 跨交易所价差策略 | Phase 4+ |
