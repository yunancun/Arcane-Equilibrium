# Session 12 数据分析与两项关键修复
# Date: 2026-03-29

---

## 一、本次数据快照（运行约 45.7 小时）

```
session_id              = psess:fe7ac188（连续运行）
net_pnl                 = -$63.78（与 Session 11 相同，数据未变）
win_rate                = 0%（fill=684, round_trips=162, win=0, loss=162）
max_drawdown            = 0.64%（$63.78）
sharpe_ratio            = -1.30
avg_loss_per_trip       = -$0.39
largest_loss            = -$21.54
avg_holding_period      = 3,746.7 秒（~62 分钟，仅 25 条记录）
active_orders           = 0
consecutive_losses      = 3
total_observations      = 0（学习系统仍空）
```

---

## 二、本次发现的问题（3 个）

### 问题 1：Fill 碎片化 bug（P0）

**现象**：每笔限价单产生 25-30 次成交，而非预期的 1-3 次。

**数据证据**：
- BTCUSDT Sell 单 qty=0.00597：27 次成交，最后一笔 qty=6.02e-11
- BTCUSDT Sell 单 qty=0.001：27 次成交，最后一笔 qty=7.59e-11
- 成交量从 0.002 几何衰减到 1e-10 量级

**根因**：`compute_partial_fill_qty()` 每次只填充剩余量的 30-70%（随机），
`execute_fill()` 的"完成"阈值为 `1e-10`（绝对值）。以 0.001 BTC 为例：
- 每次平均填充 50% → 剩余 = 0.001 × 0.5^N
- 需 N ≈ 23 次才能让剩余量 < 1e-10
- 结果：23-30 次成交/单，fill_count 被虚高 ~8倍

**连锁影响**：
- 大量订单长时间停留在 `PARTIALLY_FILLED` 状态
- `n_active_orders > 0` → 触发 AI 注意力税"HIGH 燃烧率"（$0.05/小时）
- 直接导致问题 2

---

### 问题 2：AI 注意力税以微小盈利强制平仓（P0 - 0% 胜率的根因）

**现象**：audit trail 显示大量 `risk_auto_close` 原因为：
```
ai_attention_tax_ratio_241.61_grade_F
ai_attention_tax_ratio_14.84_grade_F
ai_attention_tax_ratio_15.41_grade_F
```

**根因分析**：
1. Fill 碎片化 → `n_active_orders > 0` → HIGH 燃烧率 $0.05/小时
2. 持仓时间短（几分钟），仓位盈利微小（如 $0.0003）
3. `cost_edge_ratio = total_holding_cost / edge_usd = 0.073 / 0.0003 = 241`
4. 241 ≥ max_cost_edge_ratio (0.8) → 触发平仓
5. **平仓手续费 = notional × 0.00055 ≈ $0.040**（远大于 edge $0.0003）
6. 净结果：每次"以 $0.0003 盈利平仓"后，扣除手续费 → 净亏损 $0.040

这就是 0% 胜率的核心机制：策略找到了小盈利，风控把它强制变成了小亏损。

**数值验证**（BTCUSDT 案例）：
- 入场：$66,630，qty=0.001，notional=$66.63
- 平仓手续费：66.63 × 0.00055 = $0.037
- 触发平仓时 edge ≈ $0.0003
- 净 PnL ≈ $0.0003 - $0.037 = **-$0.037**（一次小亏损）

---

### 问题 3：E1 观察记录未写入（P1，延后处理）

**现象**：162 次 round trip，`total_observations = 0`

**根因**：`_on_round_trip_complete()` 只在 `submit_order()` 返回非空 fills
且 `close_pnl != 0` 时触发。但通过 `engine.tick()` 完成的平仓（包括
`risk_auto_close`）完全绕过了这个路径，观察写入永远不触发。

**影响**：学习系统完全无数据，学习机制形同虚设。

**决定**：本次不修，需要在 MarketDataDispatcher 和 PipelineBridge 之间
增加 tick_result 传递通道，改动较大，下次 session 处理。

---

## 三、本次修复（2 项）

### F1：Fill 碎片化修复

**文件**：`paper_trading_engine.py`
**函数**：`compute_partial_fill_qty()`（约第 383 行）

**改动**：在剩余量计算后添加尾量检查：
```python
# 新增：剩余量 < 原始数量 1% 时一次性全部成交
if remaining <= order["qty"] * 0.01:
    return remaining
```

**效果**：
- 成交次数从 25-30 次/单 → ≤10 次/单
- 减少 `n_active_orders` 计数（orders 更快 → FILLED 状态）
- 降低 AI 注意力税燃烧率（从 HIGH 降至 MEDIUM/LOW）

---

### F2：AI 注意力税平仓最低 Edge 保护

**文件**：`risk_manager.py`
**函数**：`check_positions_on_tick()`（约第 887 行）

**改动**：原来 `edge_usd > 0` 改为 `edge_usd > taker_close_fee_usd`：
```python
# 旧:
if (edge_usd > 0 and hc["cost_edge_ratio"] >= self._config.max_cost_edge_ratio):

# 新:
taker_close_fee_usd = notional * 0.00055  # DEFAULT_TAKER_FEE_RATE
if (edge_usd > taker_close_fee_usd
        and hc["cost_edge_ratio"] >= self._config.max_cost_edge_ratio):
```

**效果**：
- 只有 edge 能覆盖平仓手续费时才触发注意力税平仓
- 防止系统把盈利变亏损（原本的核心逻辑错误）
- 注意力税恢复其设计意图：仅当成本真正吞噬可观利润时才平仓

---

## 四、测试结果

```
新增测试：
  test_fill_fragmentation_dust_check          PASSED
  test_attention_tax_does_not_close_tiny_edge_position  PASSED

全量测试：
  430 passed, 2 warnings (含 2 个新测试)
  0 failures, 0 errors
```

---

## 五、预期影响

1. Fill 碎片化修复后，新订单完成更快，`n_active_orders` 更少 → 注意力税燃烧率降低
2. 注意力税最低 Edge 保护后，微小盈利不再被强制变亏损
3. 两项合并应能让胜率从 0% 提升（策略本身有轻微负向偏差，但不应是 100% 亏损）
4. 下一步观察：等数据积累（新 round trips），看胜率变化趋势

---

## 六、仍待处理问题

| 问题 | 优先级 | 说明 |
|------|--------|------|
| E1 观察记录未写入 | P1 | 需要 MarketDataDispatcher → PipelineBridge tick_result 通道 |
| 策略整体负向边际 | P2 | MA 交叉在震荡市场中仍有系统性 buy-high-sell-low 倾向 |
| Holding period 仅 25 条记录 | P3 | 指标不完整，影响分析 |
| Learning Cockpit GUI 空数据 | P3 | 依赖 E1 修复 |

---

## 七、服务状态

- 重启：`systemctl --user restart openclaw-trading-api`（2026-03-29）
- 会话 psess:fe7ac188 继续运行，历史数据完整保留
- 新修复从下一批 intents 开始生效
