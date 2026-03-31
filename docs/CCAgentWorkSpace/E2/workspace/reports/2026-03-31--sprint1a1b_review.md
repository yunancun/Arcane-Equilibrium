# E2 Code Review Report: Wave 6 Sprint 1a + 1b
# E2 代碼審查報告：Wave 6 Sprint 1a + 1b

**審查日期**: 2026-03-31
**審查員**: E2（Code Reviewer）
**任務範圍**:
- Sprint 1a（FA-7）: `pipeline_bridge._check_stops()` 新增 `_emit_round_trip()` 注入 + 4 個測試
- Sprint 1b（1B-2 + TD-3 + TD-4）: `governance_routes.py` freshness 字段 + `strategist_agent.py` 兩項修復 + 對應測試
**審查文件**:
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/pipeline_bridge.py`
- `program_code/local_model_tools/tests/test_pipeline_bridge_coverage.py`（TestCheckStopsPerceptionPlane）
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_agent.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_governance_routes_coverage.py`（TestGetH0GateStatusFreshnessFields）
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_agent.py`（TestH1CooldownLRUCap）

---

## 一、總體結論

```
Sprint 1a（FA-7）:   ⚠️  CONDITIONAL PASS — 1 個 P1 問題需修復後方可 commit
Sprint 1b（1B-2/TD-3/TD-4）:  ✅  PASS — 可進入 E4 回歸
```

---

## 二、Sprint 1a 審查（FA-7 — pipeline_bridge._check_stops() Perception Plane 注入）

### 2.1 審查矩陣

| 審查項目 | 結論 |
|---------|------|
| `_emit_round_trip()` 在 `submit_order()` 之後 | ✅ PASS |
| `try/except` 包裹（non-fatal） | ✅ PASS |
| `except Exception as _rt_err` + `logger.warning`（非 pass） | ✅ PASS |
| `perception_plane is None` 路徑安全 | ✅ PASS |
| PnL 計算方向正確（多頭 Sell / 空頭 Buy） | ✅ PASS |
| **submit_order 返回 rejection 時是否跳過 _emit_round_trip** | ❌ **P1 FAIL** |
| 中英雙語注釋 | ✅ PASS |
| 無新增 `except: pass`（靜默吞異常） | ✅ PASS（L885 `except Exception: pass` 為 pre-existing，有說明注釋） |

### 2.2 P1 問題：`_emit_round_trip()` 在 stop order rejected 時仍被調用

**位置**: `pipeline_bridge.py` L888–L986

**問題描述**:
`_check_stops()` 的 FA-7 塊在 `submit_order()` 之後無條件調用 `_emit_round_trip()`，
未檢查 `result.get("rejected_reason")`。

```python
result = self._engine.submit_order(...)          # L888 — result 儲存但從未檢查
with self._lock:
    self._stats["stops_triggered"] += 1          # L896 — 無條件遞增
...
try:
    ...
    self._emit_round_trip(...)                   # L974 — 無條件調用
```

**問題後果**:
若 `submit_order()` 返回 `{"rejected_reason": "risk_limit", ...}`（不 raise），系統仍會：
1. 錯誤遞增 `stops_triggered`（stop 未真正觸發）
2. 注入虛假的平倉學習信號至 PerceptionPlane（學習錯誤信息）

**備註**: `stops_triggered++` 的無條件遞增是 pre-existing 設計，但 FA-7 的學習注入敏感性更高——
學習管線注入假信號（「已以 $59000 平倉」但實際上訂單被拒）比計數器偏差影響更嚴重。

**建議修復（E1-Beta）**:
在 FA-7 `try:` 塊之前，加入 rejected_reason 檢查：

```python
# FA-7: skip learning injection if stop order was rejected
# FA-7: 止損單被拒絕時跳過學習管線注入（避免虛假信號）
_stop_rejected = (
    isinstance(result, dict) and bool(result.get("rejected_reason"))
)
if not _stop_rejected:
    try:
        ...
        self._emit_round_trip(...)
    except Exception as _rt_err:
        ...
```

**預估修復時間**: 10 分鐘

### 2.3 pre-existing `except Exception: pass`（L885）

```python
except Exception:
    pass  # If state read fails, proceed with stop order (safe default)
```

此 `except: pass` 是 pre-existing 代碼，保護狀態讀取（位置已平倉 → 跳過止損），
有說明注釋。錯誤語義為「讀取失敗時繼續提交止損」（safe default）。
E2 追蹤為 P2，本次 Sprint 1a 未引入，不計為 Sprint 1a 問題。

### 2.4 PnL 方向驗證

```python
if stop["side"] == "Sell":
    _close_pnl = (_exit_price - _entry_price) * _qty   # 多頭平倉：正常盈虧
else:
    _close_pnl = (_entry_price - _exit_price) * _qty   # 空頭平倉：反向
```

- 多頭止損：`Sell`，exit < entry → `(_exit - _entry) * qty < 0`（虧損為負）✅
- 空頭止損：`Buy`，exit > entry → `(_entry - _exit) * qty < 0`（虧損為負）✅
- 公式正確，與業務語義一致。

### 2.5 雙語注釋合規

- ✅ FA-7 塊頂部：中英雙語，引用原則 12，解釋 7 個回調職責
- ✅ PnL 計算注釋：解釋 side 方向語義（Sell=多頭，Buy=空頭）
- ✅ except 路徑：「非致命：不允許學習管線注入阻擋止損單」
- ✅ 出場價格 fallback 注釋：優先 current_price，fallback market_prices

### 2.6 測試覆蓋確認

| 測試名稱 | 覆蓋場景 | 實測結果 |
|---------|---------|---------|
| `test_register_data_called_on_stop_loss_close` | 多頭 hard stop → register_data 被調用 | ✅ PASS |
| `test_register_data_not_called_when_perception_plane_none` | plane=None → 不崩潰，stop 仍執行 | ✅ PASS |
| `test_register_data_called_on_time_stop_close` | 時間止損 → register_data 被調用 | ✅ PASS |
| `test_pnl_calculation_correct_for_long_position` | 多頭止損 PnL < 0 | ✅ PASS |

**缺失測試（P2 追蹤，非阻斷）**:
- 空頭止損（Buy side）PnL 符號驗證
- `submit_order()` 返回 rejected_reason 時，`_emit_round_trip()` 是否應跳過（P1 問題的測試）

---

## 三、Sprint 1b 審查（1B-2 + TD-3 + TD-4）

### 3.1 審查矩陣

| 審查項目 | 結論 |
|---------|------|
| `freshness_age_ms` 計算正確（now_ms - latest_ts） | ✅ PASS |
| `getattr` 安全鏈防 AttributeError（_price_ts / _config / max_data_age_ms） | ✅ PASS |
| `isinstance(raw_price_ts, dict)` mock 防護 | ✅ PASS |
| freshness_score 線性衰減（0.0–1.0） | ✅ PASS |
| freshness_age_ms=None 時 freshness_score=None（認知誠實，原則 10） | ✅ PASS |
| HTTPException 穿透（except HTTPException: raise） | ✅ PASS |
| 無新增安全漏洞（只讀端點） | ✅ PASS |
| TD-3：`except Exception: pass` → `logger.warning` | ✅ PASS |
| TD-3：非致命路徑繼續（不 re-raise） | ✅ PASS |
| TD-4：LRU cap 觸發時機（`>= _H1_COOLDOWN_MAX_SIZE`） | ✅ PASS |
| TD-4：清理策略（過期條目優先，30s window） | ✅ PASS |
| TD-4：熱路徑（len < 1000）零額外開銷 | ✅ PASS |
| 中英雙語注釋（freshness + TD-4） | ✅ PASS |

### 3.2 1B-2 freshness 字段詳細驗證

**getattr 安全鏈**:
```python
raw_price_ts = getattr(gate, "_price_ts", None)
price_ts_dict: dict = raw_price_ts if isinstance(raw_price_ts, dict) else {}
raw_max_age = getattr(getattr(gate, "_config", None), "max_data_age_ms", 1000)
max_age_ms: int = raw_max_age if isinstance(raw_max_age, int) and raw_max_age > 0 else 1000
```

- `getattr(gate, "_price_ts", None)` — 屬性不存在時返回 None ✅
- `isinstance(raw_price_ts, dict)` — mock 可能返回 MagicMock，此處正確過濾 ✅
- `getattr(None, "max_data_age_ms", 1000)` — Python 允許，返回 default 1000 ✅
- `isinstance(raw_max_age, int) and raw_max_age > 0` — 防止 MagicMock 或 0 除零 ✅

**freshness_score 計算**:
- `max(0.0, 1.0 - age_ms / max_age_ms)` — age > max → score = 0.0（不負）✅
- freshness_age_ms 可能為負數（系統時鐘回撥）：此時 `freshness_score > 1.0`，但 `1 - freshness_age_ms / max_age_ms` 會大於 1.0，不被 `max(0.0, ...)` 截斷。P2 觀察：可加 `min(1.0, max(0.0, ...))` 但功能影響極小（clock skew 邊界情況）。

### 3.3 TD-3 驗證

**修復前（pre-existing 問題）**:
```python
except Exception:
    pass  # silent swallow
```

**修復後**:
```python
except Exception as e:
    # TD-3: Log cost tracking failures instead of silently swallowing them.
    logger.warning(
        "H5 cost record failed for model l1_9b: %s / H5 成本記錄失敗", e
    )
```

- `except Exception as e` 正確捕獲（有具名異常）✅
- `logger.warning` 使用 `%s` 格式化（防日誌注入）✅
- 不 re-raise：符合 H5 非致命語義 ✅

### 3.4 TD-4 驗證

**cap 設定**:
```python
_H1_COOLDOWN_MAX_SIZE: int = 1000
```

**觸發邏輯**:
```python
if len(self._h1_cooldown) >= self._H1_COOLDOWN_MAX_SIZE:
    expired_keys = [sym for sym, ts in self._h1_cooldown.items() if now - ts >= 30.0]
    for sym in expired_keys: del self._h1_cooldown[sym]
```

- 觸發條件：`>= 1000`，不是 `> 1000`，正確（防止 dict 超出 cap 後才清理）✅
- 清理策略：過期條目（> 30s），語義正確（業務上這些 key 已無冷卻期意義）✅
- 熱路徑：`len < 1000` 時直接跳過整個 if 塊，零額外開銷 ✅
- 最壞情況（1000 個全為新鮮條目）：清理 0 個 → dict 在插入後為 1001。P2 觀察：若需嚴格上限，可額外加 fallback eviction（但 650 symbol 場景下 1000 容量足夠，不需要）。

### 3.5 測試覆蓋確認

**freshness 測試（TestGetH0GateStatusFreshnessFields）**:

| 測試名稱 | 覆蓋場景 | 實測結果 |
|---------|---------|---------|
| `test_freshness_fields_present_when_gate_has_price_data` | 有 tick 數據 → freshness 三字段在位 | ✅ PASS |
| `test_freshness_age_ms_is_none_when_no_price_data` | 空 _price_ts → None 字段 | ✅ PASS |
| `test_h0_gate_unavailable_raises_503` | gate=None → 503 | ✅ PASS |

**TD-4 測試（TestH1CooldownLRUCap）**:

| 測試名稱 | 覆蓋場景 | 實測結果 |
|---------|---------|---------|
| `test_cooldown_dict_does_not_grow_beyond_cap_with_expired_entries` | cap+10 過期條目 → 清理後 ≤ 2 | ✅ PASS |
| `test_cooldown_not_triggered_below_cap` | 5 條目 → 正常插入，無清理 | ✅ PASS |

**缺失測試（P2 追蹤，非阻斷）**:
- freshness：`_price_ts` 屬性完全不存在（del 路徑）的測試（`_make_gate(price_ts=None)` 方法存在但未被任何測試使用）
- TD-4：1000 個全新鮮條目時 dict size = 1001 的邊界行為測試

---

## 四、問題清單

### P1 問題（阻斷 commit）

#### P1-1：`_check_stops()` FA-7 在 submit_order 返回 rejected_reason 時仍調用 `_emit_round_trip()`

- **文件**: `pipeline_bridge.py` L888–L986
- **問題**: result 未檢查 rejected_reason，虛假學習信號注入 PerceptionPlane
- **修復**: 在 FA-7 try 塊之前加 `if isinstance(result, dict) and result.get("rejected_reason"): skip _emit_round_trip`
- **補測試**: 1 個測試驗證 submit_order=rejected 時 plane.register_data 未被調用
- **預估**: 15 分鐘（含測試）

### P2 問題（非阻斷，建議追蹤）

#### P2-1：FA-7 缺少空頭止損 PnL 符號測試
- 測試 4 只覆蓋多頭（Sell），空頭（Buy side）無 PnL 符號測試

#### P2-2：freshness 缺少 `_price_ts` del 覆蓋路徑測試
- `_make_gate(price_ts=None)` 方法已定義但無測試使用它

#### P2-3：freshness_score 未做 `min(1.0, ...)` 截斷（時鐘回撥邊界）
- 系統時鐘回撥時 `freshness_age_ms < 0`，score > 1.0

#### P2-4（繼承）：`except Exception: pass` at L885（pre-existing，狀態讀取失敗時跳過雙重止損檢查）
- 有注釋說明 intent，但 P2 追蹤改為 `logger.debug`

---

## 五、測試執行結果

```bash
# Sprint 1a
python3 -m pytest program_code/local_model_tools/tests/test_pipeline_bridge_coverage.py::TestCheckStopsPerceptionPlane -v
→ 4 passed in 0.95s  ✅

# Sprint 1b freshness
python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_governance_routes_coverage.py::TestGetH0GateStatusFreshnessFields -v
→ 3 passed in 0.25s  ✅

# Sprint 1b TD-4
python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_agent.py::TestH1CooldownLRUCap -v
→ 2 passed in 0.03s  ✅
```

---

## 六、最終結論

```
Sprint 1a（FA-7）:   ⚠️  CONDITIONAL PASS
  → 1 個 P1（result 未檢查 rejected_reason 即調用 _emit_round_trip）
  → E1-Beta 修復 + 補 1 個測試後，E2 確認，進入 E4

Sprint 1b（1B-2 + TD-3 + TD-4）:  ✅  PASS，可直接進入 E4
  → 所有審查項通過，4 P2 非阻斷觀察已記錄

建議工作流：E1-Beta 修復 Sprint 1a P1 → E2 確認修復 → Sprint 1a+1b 合併 E4 回歸
```
