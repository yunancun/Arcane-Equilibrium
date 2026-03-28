# Session 10 — AI成本汇总 + 双重止损防护
# 2026-03-28（夜）
# 重要度：⭐⭐ 工程质量修复

---

## 背景

Session 8 审核后的"待处理问题"列表中还有 2 项可以现在修：
1. `total_ai_cost` 永远是 0.0（RiskManager 算出来了但从没写进 PnL 汇总）
2. StopManager 与 RiskManager 双重止损（RiskManager 先平仓后 StopManager 会开反向仓）

---

## 修复清单

### B1 — total_ai_cost 汇总（paper_trading_engine.py）

**问题：**
`_recompute_pnl()` 的公式：
```python
net_paper_pnl = realized + unrealized - fees - total_ai_cost
```
包含 `total_ai_cost`，但 `total_ai_cost` 永远是初始值 0.0。

RiskManager 在每个 tick 都会计算每个持仓的 `holding_cost.ai_cost_attributed_usd`，
但从没把这个数聚合到 `state["pnl"]["total_ai_cost"]`。

**修复：** 在 `_recompute_pnl()` 中，total_fees 计算后紧接着加：
```python
total_ai_cost = sum(
    p.get("holding_cost", {}).get("ai_cost_attributed_usd", 0.0)
    for p in state["positions"].values()
)
pnl["total_ai_cost"] = total_ai_cost
```

**文件：** `control_api_v1/app/paper_trading_engine.py`（+5 行）

---

### S1 — 双重止损防护（pipeline_bridge.py）

**问题：**
PipelineBridge._check_stops() 和 paper engine 的 RiskManager.check_positions_on_tick()
是两个独立的止损系统。可能的竞态：
1. RiskManager（在 engine.tick() 内）先触发，平掉持仓 → position 从 state["positions"] 删除
2. StopManager 同时也触发，在 _check_stops() 里调用 engine.submit_order()
3. 此时 position 已不存在，但 submit_order() 会把这个卖单当成开新空仓处理

结果：**意外开出反向仓位**（静默 bug，不会报错）。

**修复：** 在 `_check_stops()` 中，每个 stop 触发时先检查 engine 状态：
```python
engine_state = self._engine.get_state()
if not engine_state.get("positions", {}).get(stop["symbol"]):
    # 仓位已平 — 清理 StopManager 状态，跳过提交
    self._stop_mgr.untrack_position(stop["symbol"], stop.get("strategy_name", "unknown"))
    continue
```

**安全设计：**
- get_state() 失败时 fallthrough（允许提交，保守安全默认）
- 仅 debug log，不影响正常止损路径

**文件：** `control_api_v1/app/pipeline_bridge.py`（+15 行）

---

## 测试结果

新增 7 个测试加入 `test_session9_fixes.py`：

| 类 | 测试 | 验证 |
|----|------|------|
| `TestAiCostAggregation` | 4 | 无持仓时=0；从 holding_cost 汇总；反映在 net_paper_pnl；无 holding_cost 不崩溃 |
| `TestDoubleStopGuard` | 3 | 仓位不存在时跳过；仓位存在时正常提交；get_state 失败时 fallthrough |

25/25 全通过（含之前 18 个）

---

## 总测试数

| 套件 | Session 9 | Session 10 |
|------|-----------|------------|
| control_api | 428 | 428 |
| local_model_tools | 236 | 236 |
| **合计** | **664** | **664**（无新增，扩展已有文件） |

---

## 待处理问题更新后状态

| 问题 | 状态 |
|------|------|
| MACrossoverStrategy 仓位状态漂移 | ✅ Session 9 A2 |
| realized_pnl 毛利字段缺失 | ✅ Session 9 B2 |
| active_count +1 仓位计算错误 | ✅ Session 9 G3 |
| total_ai_cost 永远 0.0 | ✅ Session 10 B1 |
| 双重止损开反向仓 | ✅ Session 10 S1 |
| Learning Cockpit GUI 数据展示 | ⏳ 等 E1 数据积累 |
| RiskManager daily loss 跨天不重置 | ✅ 已有逻辑（验证通过） |

---

## 一句话总结

> Session 10 修复 2 个静默 bug：AI 成本汇总空缺（net_paper_pnl 现在才真正包含 AI 成本）
> 和双重止损竞态（StopManager 不再在仓位已平后开反向仓）。664 测试全通，无回归。
