# Session 3：残留审核问题全量修复

**日期：** 2026-03-27
**范围：** 全系统 A-K 审核 + Phase 2 审核中标记为"DOCUMENTED/NOTED"但实际可修的问题
**结果：** 8 个文件修改，646 测试全通过（+2 测试修复），0 回归

---

## 一、背景

Session 1-2 共修复了 196/214 个审核问题。剩余 18 个被标记为"documented"或"noted"但未实际修复。
本次 Session 3 逐一排查并修复了所有可修的残留问题。

---

## 二、修复清单

### 1. Timestamp `or` 回退模式（6 处）— HIGH

**问题：** `event.get("ts_ms", 0) or time.time() * 1000` 在 ts_ms=0 时会错误地回退到系统时间，掩盖数据质量问题。

**修复：** 改为显式 None/0 检查：
```python
# Before (buggy):
ts_ms = int(event.get("ts_ms", 0) or time.time() * 1000)

# After (correct):
raw_ts = event.get("ts_ms")
ts_ms = int(raw_ts) if raw_ts is not None and raw_ts != 0 else int(time.time() * 1000)
```

**影响文件：**
- `pipeline_bridge.py` — tick 事件时间戳（2 处）
- `kline_manager.py` — K线事件时间戳（2 处）
- `bybit_h1_report_utils.py` — 报告时间戳（1 处）
- `bybit_h_stage_common.py` — 报告时间戳（1 处）
- `funding_rate_arb.py` — 策略时间戳（1 处）

---

### 2. 浮点残余量比较（paper_trading_engine.py）— HIGH

**问题：** `fill_qty == pos["qty"]` 使用精确浮点比较，多次 partial fill 后残余量可能不为零。

**修复：** 改为容差比较（epsilon = 1e-10）：
```python
_QTY_EPS = 1e-10
diff = pos["qty"] - fill_qty
if diff > _QTY_EPS:      # partial close
elif abs(diff) <= _QTY_EPS:  # full close (within tolerance)
else:                     # flip
```

---

### 3. TIF (Time In Force) 执行逻辑（paper_trading_engine.py）— HIGH

**问题：** IOC/FOK/PostOnly 常量已声明但从未在成交逻辑中执行。所有限价单都按 GTC 处理。

**修复：** 在 `submit_order` 中添加 TIF 执行逻辑：
- **PostOnly**：如果限价单会立即成交，取消订单（保证 maker 费率）
- **FOK (Fill-or-Kill)**：如果价格满足条件则全部成交，否则立即取消
- **IOC (Immediate-or-Cancel)**：如果价格满足条件则立即成交，否则取消

---

### 4. Kahan 补偿求和（kline_manager.py）— MEDIUM

**问题：** `volume += v` 和 `turnover += t` 在数千 tick 后会产生浮点漂移（~1 ULP）。

**修复：** 改用 Kahan 补偿求和算法：
```python
# Kahan compensated summation
y = volume - self._vol_comp
t = self.volume + y
self._vol_comp = (t - self.volume) - y
self.volume = t
```

在 `__slots__` 中添加 `_vol_comp` 和 `_turn_comp` 补偿器。

---

### 5. Console 401 刷屏（trading.html）— MEDIUM

**问题：** Token 无效时，每 15 秒发起多个 API 请求全部 401，浏览器控制台和网络面板被刷屏。

**修复：**
- 添加 `_authFailCount` 计数器，连续 3 次 401 后自动停止轮询
- 成功请求时重置计数器
- 更换 Token 时重置计数器并恢复轮询

---

### 6. Volume 追踪范围扩展（pipeline_bridge.py）— MEDIUM

**问题：** `_refresh_kline_volume()` 硬编码只覆盖 BTCUSDT 和 ETHUSDT。

**修复：** 改为动态获取所有已追踪的交易对（`get_tracked_symbols()`），上限 10 个以避免 API 频率限制。

---

### 7. 测试排序缺陷修复（test_api_contract.py）— LOW（bonus）

**问题：** `test_validate_returns_success_envelope` 和 `test_config_change_whitelist` 在与其他测试文件一起运行时因 state_revision 泄漏而 409 失败。

**原因：** `build_client()` 只 reload `main` 模块，没有 reload `main_legacy`（状态存储层），导致前一个测试文件的 state_revision 残留。

**修复：** 在 `build_client()` 中同时 reload `main_legacy` 和 `main`：
```python
from app import main_legacy as legacy_module
importlib.reload(legacy_module)
from app import main as main_module
importlib.reload(main_module)
```

**效果：** 全套测试从 644 passed + 2 failed → **646 passed + 0 failed**。

---

## 三、测试结果

```
全量测试：646 passed, 0 failed, 2 warnings
  - local_model_tools/tests/: 218 passed
  - control_api_v1/tests/:    428 passed（含 2 个原先 flaky 的测试修复）
```

---

## 四、不可修的设计限制（确认并归档）

以下问题经审查确认为架构/外部约束，不需要修复：

| 问题 | 原因 | 状态 |
|------|------|------|
| http_status 始终 None | Anthropic/OpenAI SDK 不暴露 HTTP 状态码 | BY DESIGN |
| WebSocket tick volume=0 | Bybit ticker WS 不提供单笔成交量 | API LIMITATION |
| Observer 手动批次触发 | 架构设计：观察者周期由外部脚本驱动 | BY DESIGN |
| Funding Rate 非 delta-neutral | Phase 4 需要跨品类下单能力 | DEFERRED |

---

## 五、修改文件汇总

| 文件 | 修改内容 |
|------|----------|
| `pipeline_bridge.py` | 时间戳修复 + volume 动态追踪 |
| `kline_manager.py` | 时间戳修复 + Kahan 求和 + __slots__ 扩展 |
| `signal_generator.py` | （时间戳已正确使用 `is not None`，无需修改）|
| `bybit_h1_report_utils.py` | 时间戳修复 |
| `bybit_h_stage_common.py` | 时间戳修复 |
| `funding_rate_arb.py` | 时间戳修复 |
| `paper_trading_engine.py` | 浮点容差 + TIF 执行逻辑 |
| `trading.html` | 401 刷屏修复 |
| `test_api_contract.py` | 测试排序缺陷修复 |
