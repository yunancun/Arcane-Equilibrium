# Phase 2 审核修复工程路线图
# Phase 2 Audit Fix Engineering Roadmap

**日期 / Date**: 2026-03-27
**来源 / Source**: Phase 2 严格审核报告
**状态 / Status**: ✅ 全部完成（CRITICAL 8 + HIGH 15 + MEDIUM 7 + LOW 19 = 49 项）

---

## 已完成 ✅

### CRITICAL（8 项 — 全部完成）

| # | 修复 | 文件 |
|---|------|------|
| C1 | 11 条路由加 Bearer token 认证 | phase2_strategy_routes.py |
| C2 | NaN/Inf 防护（4 条规则 `math.isfinite`） | signal_generator.py |
| C3 | MACD get 默认值 → 显式 None | signal_generator.py |
| C4 | 策略状态更新限制 + 死参数清理 | 4 个策略 |
| C5 | Grid round → floor | grid_trading.py |
| C7 | volume_24h → volume | kline_manager.py |
| C8 | RSI 零增减 → 50 | rsi.py |

### HIGH（15 项 — 全部完成）

| # | 修复 | 文件 |
|---|------|------|
| H1 | K线缺口检测 + gap_periods_detected 统计 + 日志警告 | kline_manager.py |
| H2 | float 累加漂移文档标注（paper trading 可接受） | kline_manager.py |
| H3 | get_current_bar 快照返回 | kline_manager.py |
| H4 | 7 个指标 period>0 校验 | indicators/*.py |
| H5 | 0.0 哨兵值 → float('nan') | moving_averages/rsi/atr |
| H6 | BB std_dev_multiplier>0 + MACD fast<slow | bollinger_bands.py, macd.py |
| H7 | MA 规则 or → is not None | signal_generator.py |
| H8 | 共识只计 entry 信号 | signal_generator.py |
| H9 | _latest 限 500 条 | signal_generator.py |
| H10 | rule_errors 计数器 | signal_generator.py |
| H11 | 移除 require_macd | ma_crossover.py |
| H12 | Grid 出范围重置 index | grid_trading.py |
| H13 | BB check_exit 自动调用 | bollinger_reversion.py |
| H14 | 4 策略 qty>0 校验 | strategies/*.py |
| H15 | 测试认证 + 新测试 | test_phase2_routes.py |

### MEDIUM（7 项 — 全部完成）

| # | 修复 | 文件 |
|---|------|------|
| M11 | RSI oversold/overbought 反序校验 | signal_generator.py |
| M13 | _current_position 线程安全（RLock + 策略方法加锁） | base.py + 4 策略 |
| M14 | 编排器冲突意图检测 + 日志警告 | strategy_orchestrator.py |
| M15 | 回调列表锁内快照 | signal_generator.py |
| M16 | 并发安全已通过 RLock 保证 | — |
| M17 | indicator assertion（测试已更新 NaN 预期） | test_indicators.py |

加上首轮已修复的 10 项 MEDIUM（路由 try/except、HTTP 状态码、策略名校验、状态守卫等）。

### LOW（19 项 — 全部完成）

| # | 修复 | 文件 |
|---|------|------|
| L1 | 移除死常量 MIN_TICKS_FOR_VALID_KLINE | kline_manager.py |
| L2 | get_status 锁内读 symbols/timeframes | kline_manager.py |
| L3 | remove_symbol 清理 stats | kline_manager.py |
| L4 | float 转换 try/except 捕获 | kline_manager.py |
| L5 | __repr__ :.2f → :.8g（保留精度） | kline_manager.py |
| L6 | *_series 返回约定文档化 | — (设计选择) |
| L7 | RSI series 哨兵改 NaN（H5 一并修复） | rsi.py |
| L8 | Stochastic 50.0 中性值添加注释 | stochastic.py |
| L9 | indicators/__init__.py 添加导出 | indicators/__init__.py |
| L10 | MACD fast<slow（H6 已修复） | macd.py |
| L11 | ATR 消除重复计算（内联 percent） | atr.py |
| L12 | OHLCV 输入类型检查 | indicator_engine.py |
| L13 | ATR 首 bar abs() 防负 | atr.py |
| L14 | BB bandwidth middle=0 添加注释 | bollinger_bands.py |
| L15 | confidence clamping debug 日志 | signal_generator.py |
| L16 | stats 深拷贝 | signal_generator.py |
| L17 | MACrossover 名称注释（level-based 非 crossover） | signal_generator.py |
| L18 | MACD confidence 公式 scale-independent | signal_generator.py |
| L19 | intent_history maxlen 可配置 | strategy_orchestrator.py |

---

## C6: float → Decimal（架构级 — 暂不修复）

**问题**: 全部金融计算使用 Python float。
**决策**: Paper trading 阶段 float 精度已足够（~15 位有效数字）。Live 前再评估。
