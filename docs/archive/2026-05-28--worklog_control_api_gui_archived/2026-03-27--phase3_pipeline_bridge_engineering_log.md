# Phase 3: Pipeline Bridge + Stop Manager + Signal Enhancement — 完整工程日志
# Phase 3: Pipeline Bridge + Stop Manager + Signal Enhancement — Complete Engineering Log

**日期 / Date**: 2026-03-27
**状态 / Status**: 已完成
**测试 / Tests**: 640 全通过（214 local_model_tools + 426 control_api）

---

## 一、背景与目标

Phase 2 严格审核后发现的第二轮审核（实战适用性审核）揭示了 10 个 CRITICAL 级问题：
- 策略管线与纸上交易管线完全断裂（S1-S4）
- 策略无止损（S5）、无动态仓位（S8）、无 regime 检测
- 冷启动无历史数据（S10）

Phase 3 目标：解决全部 CRITICAL + 关键 HIGH 问题。

---

## 二、实现清单

### Phase 3a — 管线接通（最关键）

| 模块 | 文件 | 说明 |
|------|------|------|
| Pipeline Bridge | `pipeline_bridge.py`（新建） | Tick Fan-Out + Intent→Order Bridge，连接策略管线与 Paper Trading |
| Dispatcher 扩展 | `market_data_dispatcher.py` | 添加 `register_tick_consumer()` + tick fan-out 到消费者 |
| 单例接通 | `phase2_strategy_routes.py` | 导入 PAPER_ENGINE + 创建 PipelineBridge 实例 |
| Session 联动 | `paper_trading_routes.py` | market-feed/start 时注册 Bridge + activate，stop 时 deactivate |

### Phase 3a — 数据引导

| 模块 | 文件 | 说明 |
|------|------|------|
| 历史 K线引导 | `kline_manager.py` | `bootstrap_from_rest()` 从 Bybit REST API `/v5/market/kline` 拉取历史 |
| 数据过期检测 | `kline_manager.py` | `get_staleness()` + `last_tick_ts_ms` 追踪 |

### Phase 3b — 止损 + 仓位

| 模块 | 文件 | 说明 |
|------|------|------|
| StopManager | `stop_manager.py`（新建） | Hard Stop / Trailing Stop / Time Stop |
| ATR 动态仓位 | `stop_manager.py` | `compute_atr_position_size()` |
| Grid 库存止损 | `grid_trading.py` | `_net_inventory` + `_max_inventory_qty` + 库存限制 |

### Phase 3c — 信号质量

| 模块 | 文件 | 说明 |
|------|------|------|
| Regime 检测 | `signal_generator.py` | `RegimeDetectorRule` — 趋势/震荡/挤压/波动 分类 |
| RSI 退出 | `signal_generator.py` | `RSIExitRule` — RSI 回穿极端值时发出平仓信号 |
| MACD 衰竭 | `signal_generator.py` | `MACDExhaustionRule` — 柱状图收缩发出平仓信号 |
| 默认规则集 | `signal_generator.py` | 从 4 条扩展到 7 条（4 入场 + 2 退出 + 1 regime） |

### Phase 3d — 策略增强

| 模块 | 文件 | 说明 |
|------|------|------|
| MA 冷却期 | `ma_crossover.py` | 5 分钟冷却期防 whipsaw |
| Grid 库存 | `grid_trading.py` | 库存跟踪 + 最大库存止损 |
| PnL 跟踪 | `strategies/base.py` | `record_trade_result()` + `get_pnl_summary()` |

### 测试

| 文件 | 测试数 |
|------|--------|
| `test_stop_manager.py`（新建） | 18 |
| `test_pipeline_bridge.py`（新建） | 5 |
| 已有测试更新 | 适配新规则数 7、冷却期等 |

---

## 三、数据流（修复后）

```
Bybit WebSocket (tickers.BTCUSDT)
  → BybitPublicWsListener
    → MarketDataDispatcher._on_price_event()
      → 注意力评估 + 节流
        → _trigger_tick()
          → PaperTradingEngine.tick()     [订单成交模拟]
          → PipelineBridge.on_tick()       [NEW — 管线桥接]
            → KlineManager.on_price_event()  [K线聚合]
              → [K线闭合] → IndicatorEngine  [指标计算]
                → [指标更新] → SignalEngine   [7 条规则评估]
                  → [信号] → Orchestrator     [分发到策略]
                    → 策略产生 OrderIntent
            → Orchestrator.dispatch_tick()    [tick 策略: Grid]
            → Bridge._process_pending_intents() [收集意图]
              → PaperTradingEngine.submit_order() [提交订单]
                → RiskManager.check_order_allowed() [风控门]
```

---

## 四、新建文件

| 文件 | 行数 | 用途 |
|------|------|------|
| `app/pipeline_bridge.py` | ~190 | 管线桥接器 |
| `local_model_tools/stop_manager.py` | ~280 | 止损管理器 + ATR 仓位 |
| `tests/test_stop_manager.py` | ~130 | 止损测试 |
| `tests/test_pipeline_bridge.py` | ~80 | 桥接器测试 |

## 五、修改文件（27 个，+1490 -1135 行）

详见 `git diff --stat HEAD`

---

## 六、当前状态

```
测试：640 全通过（214 + 426）
路由：104 条
信号规则：7 条（4 入场 + 2 退出 + 1 regime）
新模块：pipeline_bridge + stop_manager
system_mode = read_only    ← 不变
execution_state = disabled ← 不变
```
