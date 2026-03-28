# Session 11 — 市场状态感知止损/止盈/时间调整
# 2026-03-28（夜）
# 重要度：⭐⭐⭐ 策略质量改进

---

## 背景

Session 8 审核发现：regime（市场状态）只用于**入场过滤**，开仓后完全不影响止损和持仓时间。
这意味着系统在 squeeze（压缩）行情里的持仓时间和 trending（趋势）行情里完全一样 —— 不合理。

Session 11 修复：regime 从入场的一次性过滤，升级为**全程止损/止盈/时间动态调整**。

---

## 实现清单

### R1 — 市场状态乘数常量（risk_manager.py）

新增三组乘数表：

```python
REGIME_STOP_MULTIPLIERS = {
    "trending": 1.0,   # 趋势：标准止损
    "volatile": 1.5,   # 高波动：放宽止损（避免噪音平仓）
    "ranging": 0.7,    # 震荡：收紧止损（快速止损快速出场）
    "squeeze": 0.6,    # 压缩：最紧止损（突破失败代价大）
    "unknown": 1.0,    # 未知：中性
}
REGIME_TP_MULTIPLIERS = {
    "trending": 1.5,   # 趋势：让利润奔跑
    "volatile": 0.8,   # 高波动：提前止盈
    "ranging": 0.7,    # 震荡：快速套利出场
    "squeeze": 0.5,    # 压缩：半程止盈（不确定性高）
    "unknown": 1.0,
}
REGIME_TIME_MULTIPLIERS = {
    "trending": 1.5,   # 趋势：持仓更长（48h × 1.5 = 72h）
    "volatile": 0.8,   # 高波动：较快出场
    "ranging": 0.8,    # 震荡：较快出场
    "squeeze": 0.3,    # 压缩：快速出场（48h × 0.3 ≈ 14h）
    "unknown": 1.0,
}
```

**乘数逻辑：**
| regime | 止损 | 止盈 | 持仓时间 |
|--------|------|------|---------|
| trending | 1.0× (标准) | 1.5× (宽) | 72h |
| volatile | 1.5× (宽) | 0.8× (窄) | 38h |
| ranging | 0.7× (紧) | 0.7× (窄) | 38h |
| squeeze | 0.6× (最紧) | 0.5× (最窄) | 14h |
| unknown | 1.0× | 1.0× | 48h |

---

### R1a — compute_dynamic_stop_pct() 新增 regime 参数

**修改：** `compute_dynamic_stop_pct(base_stop_pct, atr_pct, symbol, entry_ts_ms, regime="unknown")`

在 ATR 计算之前先乘 regime 乘数，ATR 的缩放也相应调整。

**文件：** `control_api_v1/app/risk_manager.py`（函数签名 + 2 行）

---

### R1b — check_positions_on_tick() 读取 regime 并应用

**修改三处：**
1. 软止损：读 `pos.get("regime", "unknown")`，传给 `compute_dynamic_stop_pct(..., regime=regime)`
2. 止盈：`tp = effective_take_profit_pct × REGIME_TP_MULTIPLIERS[regime]`
3. 时间止损：`max_hold = resolve_effective_limit(...) × REGIME_TIME_MULTIPLIERS[regime]`

**文件：** `control_api_v1/app/risk_manager.py`（+3 行）

---

### R1c — pipeline_bridge._on_position_open() 写 regime + 调整 StopManager

**新增两项：**

1. **写 regime 到 paper engine 持仓：**
   ```python
   store.mutate(lambda state: (state["positions"][symbol].__setitem__("regime", regime), state)[1])
   ```
   这样 RiskManager 在每次 tick 都能读到 `pos["regime"]`。

2. **StopManager 时间止损按 regime 调整：**
   ```python
   time_stop_hours = 48.0 * REGIME_TIME_MULTIPLIERS.get(regime, 1.0)
   StopConfig(hard_stop_pct=atr_stop_pct, trailing_stop_pct=3.0, time_stop_hours=time_stop_hours)
   ```

**文件：** `control_api_v1/app/pipeline_bridge.py`（+14 行）

---

## 测试结果

新增 8 个测试（`TestRegimeAwareStops`），加入 `test_session9_fixes.py`：

| 测试 | 验证 |
|------|------|
| `test_unknown_regime_is_neutral` | unknown = baseline，无副作用 |
| `test_volatile_widens_stop` | volatile 止损 > ranging 止损 |
| `test_squeeze_is_tightest` | squeeze 是所有 regime 中最紧的 |
| `test_trending_wider_than_ranging` | trending > ranging（数值验证） |
| `test_regime_tp_multipliers_exported` | TP 乘数表存在且 trending > ranging |
| `test_regime_time_multipliers_exported` | 时间乘数表存在且 squeeze 最短 |
| `test_time_stop_adjusted_by_regime` | squeeze × 48h < 48h，trending × 48h > 48h |
| `test_risk_manager_reads_regime_from_position` | 注入 squeeze position，+3% 触发 TP（2%阈值）；trending 不触发（6%阈值） |

33/33 全通过（含之前 25 个）。428/428 control_api 全通过，无回归。

---

## 总测试数

| 套件 | Session 10 | Session 11 |
|------|-----------|------------|
| control_api | 428 | 428 |
| local_model_tools (session9_fixes) | 25 | 33 (+8) |

---

## 审计修复（Session 11 事后核验）

**Bug：`self._engine._store` → `self._engine.store`**

在事后核验时发现：`_on_position_open()` 写 regime 到 paper engine 时访问 `self._engine._store`，
但 `PaperTradingEngine` 的状态存储是公共属性 `self.store`（不带下划线）。
`AttributeError` 被 `except Exception: pass` 静默捕获，导致 regime 实际上从未写入持仓。

修复：改为 `self._engine.store`。已单独提交（commit `0d90f8b`）。

测试仍全通（33+428），此修复是正确性修复，不影响测试行为（测试通过 mock 注入 regime）。

---

## 一句话总结

> Session 11 实现 regime 感知止损：trending 持仓更长/TP 更宽，squeeze 快进快出（14h/半程TP）。
> regime 从开仓时写入 paper engine 持仓，RiskManager 每 tick 读取并动态调整三个维度。
> 事后审计修复 `_store→store`（静默 bug，regime 实际未写入）。33+428 测试全通，无回归。
