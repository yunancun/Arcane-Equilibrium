# Wave 6 Sprint 1a FA-7 報告：_check_stops register_data 注入

**日期**：2026-03-31
**執行者**：E1-Beta（Backend Developer）
**任務**：FA-7 — `_check_stops()` 止損路徑缺少 `register_data()` 注入，學習管線永久無止損數據
**狀態**：完成，待 E2+E4 驗收

---

## 問題背景

`pipeline_bridge.py` 的 `_check_stops()` 中，止損觸發後 `submit_order()` 成功，但：
1. **未調用** `_emit_round_trip()` — 7 個學習/歸因回調全部遺漏
2. **未調用** `register_data()` — 感知平面看不到止損事件
3. **未調用** `observation_writer()` — E1 自動觀察缺失
4. **未調用** `auto_deployer.on_trade_result()` — G1 連續虧損追踪缺失
5. `_open_positions` 中的位置元數據沒有被清理

這違反原則 12（持續進化）：系統從未學習到止損事件的存在。

相比之下，意圖路徑（`_on_round_trip_complete`）和 tick 路徑（`on_tick_result`）都已正確調用 `_emit_round_trip()`。

---

## 修改文件清單

| 文件 | 改動類型 |
|------|---------|
| `app/pipeline_bridge.py` | 在 `_check_stops()` stop 提交成功後插入 `_emit_round_trip()` 調用塊（46 行） |
| `local_model_tools/tests/test_pipeline_bridge_coverage.py` | 新增 `TestCheckStopsPerceptionPlane` 類（4 個測試，~130 行） |

---

## 修復細節

### 插入位置

```
_check_stops() 止損觸發流程：
  1. StopManager.check_stops() 返回 triggered list
  2. 防重複止損守衛（engine.get_state() 確認倉位仍存在）
  3. engine.submit_order() — 止損單提交
  4. stats["stops_triggered"] += 1
  5. Demo connector 同步（Wave 5b CRITICAL-1）
  6. Telegram 告警
  7. ★ [新增] _emit_round_trip() — 學習管線注入 ← 插入在此
```

### PnL 計算邏輯

StopManager 的 `stop` dict 包含 `side`（平倉方向）、`entry_price`、`current_price`：
- `stop["side"] == "Sell"` → 原始多頭倉位 → `pnl = (exit - entry) * qty`（止損必為負）
- `stop["side"] == "Buy"` → 原始空頭倉位 → `pnl = (entry - exit) * qty`

`exit_price` 優先使用 `stop["current_price"]`（StopManager 記錄的精確觸發價），
回退到 `market_prices` 快照。

### 設計決策

1. **複用 `_emit_round_trip()` 而非直接調用 `register_data()`**：
   `_emit_round_trip()` 封裝了 7 個學習回調，直接調用可以確保止損路徑與意圖路徑的學習完整度一致。

2. **非致命包裝**：整個注入塊用獨立 `try/except` 包裹，`logger.warning` 記錄失敗，
   不允許學習管線異常阻擋止損單的主路徑（原則 5：生存 > 利潤）。

3. **StopManager 已先刪除觸發倉位**：`check_stops()` 返回前在鎖內 `pop` 已觸發倉位，
   所以 `_emit_round_trip()` 內的 `untrack_position()` 是 no-op（靜默忽略）— 無副作用。

4. **`_open_positions` pop**：`_emit_round_trip()` 會 pop `_open_positions["{strategy}:{symbol}"]`，
   清理 PipelineBridge 端的位置元數據 — 這是之前止損路徑遺漏的另一個清理步驟。

---

## 修復代碼摘要

```python
# FA-7: Inject into Perception Plane via _emit_round_trip
# Principle 12 (Continuous Evolution): every closed position — including
# stop-loss exits — must reach the learning pipeline.
# 原則 12（持續進化）：每個被止損平倉的倉位都必須進入學習管線。
try:
    _stop_symbol = stop["symbol"]
    _stop_strategy = stop.get("strategy_name", "unknown")
    _exit_price = float(stop.get("current_price") or market_prices.get(_stop_symbol, 0.0))
    _entry_price = float(stop.get("entry_price", 0.0))
    _qty = float(stop.get("qty", 0.0))
    if stop["side"] == "Sell":
        _close_pnl = (_exit_price - _entry_price) * _qty
    else:
        _close_pnl = (_entry_price - _exit_price) * _qty
    self._emit_round_trip(
        symbol=_stop_symbol,
        strategy_name=_stop_strategy,
        exit_price=_exit_price,
        close_pnl=_close_pnl,
    )
except Exception as _rt_err:
    logger.warning("Stop-loss round-trip emit error (non-fatal): %s %s / ...", ...)
```

---

## 測試設計

新增 `TestCheckStopsPerceptionPlane` 類（`test_pipeline_bridge_coverage.py`）：

| 測試名 | 場景 | 驗證點 |
|--------|------|--------|
| `test_register_data_called_on_stop_loss_close` | hard_stop 主路徑，perception_plane mock | `register_data.called is True` |
| `test_register_data_not_called_when_perception_plane_none` | perception_plane = None | 無 AttributeError，stop order 仍提交 |
| `test_register_data_called_on_time_stop_close` | time_stop 路徑（ETHUSDT） | `register_data.called is True` |
| `test_pnl_calculation_correct_for_long_position` | 長倉止損（exit < entry），用 `wraps` 攔截 | `close_pnl < 0`（虧損符號正確） |

---

## 測試結果

```
4 passed（TestCheckStopsPerceptionPlane 全部通過）
主套件：2624 passed, 17 failed（全部 pre-existing）, 1 skipped
基準維持 2624（new tests 在 local_model_tools/tests/，已含於 2624）
```

---

## 架構合規確認

- ✅ 原則 12（持續進化）：止損平倉事件現在進入學習管線
- ✅ 原則 5（生存 > 利潤）：注入塊 try/except 包裹，不阻擋止損主路徑
- ✅ 原則 10（認知誠實）：PnL 方向基於真實止損方向計算，不假設
- ✅ 雙語注釋規範：所有新代碼含中英文說明
- ✅ 測試 4 項：主路徑 / None 防護 / time stop / PnL 符號，全部通過
