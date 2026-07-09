# Sprint 1b 報告：1B-2 H0Gate Freshness API + TD-3 Silent Exception + TD-4 LRU Cap

**日期**：2026-03-31
**執行者**：E1-Gamma（Backend Developer）
**任務**：Wave 6 Sprint 1b — 1B-2 + TD-3 + TD-4（三個並行修復）
**狀態**：全部完成，待 E2+E4 驗收

---

## 修改文件清單

| 文件 | 改動類型 |
|------|---------|
| `app/governance_routes.py` | 新增 `import time` + h0-gate/status 端點擴充 freshness 字段 |
| `app/strategist_agent.py` | TD-3 except Exception 靜默修復 + TD-4 _h1_cooldown LRU cap |
| `tests/test_governance_routes_coverage.py` | 新增 `TestGetH0GateStatusFreshnessFields`（3 測試） |
| `tests/test_strategist_agent.py` | 新增 `TestH1CooldownLRUCap`（2 測試） |

---

## 任務一：1B-2 H0Gate freshness API 擴充

### 實現位置

`app/governance_routes.py`：

1. **新增 `import time`**（頂部，之前缺失）

2. **h0-gate/status 端點**（`get_h0_gate_status()`）：
   - 在返回 dict 之前計算三個新字段：
     - `freshness_age_ms`：最新 tick 到現在的毫秒數（None = 無數據）
     - `freshness_score`：線性衰減分數 0.0–1.0（None = 無數據）
     - `data_quality_warn_only`：固定 `True`（freshness 目前為 warn-only 模式）
   - 邏輯：讀取 `gate._price_ts`（symbol→ms 字典），取最新時間戳，計算 age

### 關鍵設計決策

- **`isinstance(raw_price_ts, dict)` 守衛**：`getattr(gate, "_price_ts", {})` 在 Mock 物件上會返回 MagicMock 而非 `{}`，導致 `max(MagicMock().values())` 拋出 `ValueError`。必須用 `isinstance` 確認是真實 dict。
- **`isinstance(raw_max_age, int)` 守衛**：同理，MagicMock._config.max_data_age_ms 是 MagicMock，非整數，必須 isinstance 判斷才能用，否則除法出錯。
- **freshness_age_ms = None when no data**：認知誠實（根原則 10），不偽造數據。
- **data_quality_warn_only 固定 True**：反映當前管線狀態（H0 freshness 目前是 warn-only 而非 blocking）。

### 中英雙語注釋

已在端點函數中加入：
- 功能說明（何時計算、為什麼暴露這些字段）
- isinstance 守衛的說明（為什麼不能直接信任 getattr）
- freshness_score 計算公式說明

---

## 任務二：TD-3 H5 cost_tracker 靜默異常修復

### 實現位置

`app/strategist_agent.py` line ~489（`_handle_intel()` 中的 H5 cost tracking 路徑）：

**修改前：**
```python
except Exception:
    pass
```

**修改後：**
```python
except Exception as e:
    logger.warning(
        "H5 cost record failed for model l1_9b: %s / H5 成本記錄失敗", e
    )
```

### 合規確認

- ✅ 成本記錄失敗仍為非致命（不阻止評估，根原則 13 觀察性要求）
- ✅ 改為 warning log 替代靜默吞異常（可追蹤問題）
- ✅ `except Exception as e` 捕獲所有異常類型（與 Pass 版等效，但不靜默）

---

## 任務三：TD-4 _h1_cooldown LRU cap

### 實現位置

`app/strategist_agent.py`，`_h1_check_cooldown()` 方法及其前的類常量：

**新增類常量：**
```python
_H1_COOLDOWN_MAX_SIZE: int = 1000
```

**_h1_check_cooldown() 新增容量守衛（Method A — 過期清理）：**
```python
if len(self._h1_cooldown) >= self._H1_COOLDOWN_MAX_SIZE:
    expired_keys = [sym for sym, ts in self._h1_cooldown.items() if now - ts >= 30.0]
    for sym in expired_keys:
        del self._h1_cooldown[sym]
    if expired_keys:
        logger.debug("TD-4 _h1_cooldown evicted %d expired entries ...", ...)
```

### 設計決策

- **選方案 A（過期清理）而非 B（LRU OrderedDict）**：過期條目已無業務價值，清理語義正確且直觀；OrderedDict 強制淘汰最近最少使用的幣種可能誤刪仍在冷卻期的有效條目。
- **懶觸發（只在達上限時清理）**：保持正常情況下熱路徑 O(1)，不引入每次調用的遍歷開銷。
- **`debug` 而非 `warning` 日誌**：容量清理是正常維護行為，不是異常，用 debug 避免 operator 告警噪音。
- **`_H1_COOLDOWN_MAX_SIZE` 為類常量**：易於測試覆蓋（可在測試中通過 `agent._H1_COOLDOWN_MAX_SIZE` 讀取）。

### 中英雙語注釋

已加入：
- 類常量說明（容量上限存在原因）
- 容量守衛原因（記憶體安全保護）
- 方案選擇說明（為何選方案 A）
- 懶觸發設計說明

---

## 測試結果

### 新增測試

| 測試類別 | 測試數 | 結果 |
|---------|--------|------|
| `TestGetH0GateStatusFreshnessFields`（1B-2）| 3 | 全通過 |
| `TestH1CooldownLRUCap`（TD-4）| 2 | 全通過 |
| TD-3 無獨立測試（行為變更為日誌，無返回值）| — | — |
| **新增測試小計** | **5** | **全通過** |

### 全套測試

| 指標 | 數值 |
|------|------|
| passed | **2624**（基準 2614 + 10 淨增，含本 Sprint 5 新增 + 其他 Sprint 未計入的 5 個）|
| failed | 17（全部為 pre-existing，`test_ollama_integration`/`test_integration_phase11`/`test_learning_tier_gate`）|
| skipped | 1（pre-existing）|

---

## 意外發現與規格偏差

1. **`time` 模塊缺失**：`governance_routes.py` 之前未 import `time`，導致 1B-2 無法實現。已補加 `import time` 到文件頂部標準庫 import 區。

2. **MagicMock 陷阱（getattr 默認值無效）**：`getattr(mock_obj, "_price_ts", {})` 返回 `MagicMock()` 而非 `{}`，因為 MagicMock 自動創建所有屬性訪問。必須 `isinstance(result, dict)` 才能安全使用。這是現有測試破壞的根本原因，也是需要記入 memory 的重要教訓。

3. **現有 test_h0_gate.py 測試**：原有 3 個 `TestGovernanceRoutesH0GateStatus` 測試在我的初版代碼下失敗（MagicMock 陷阱），修復 isinstance 守衛後全部恢復通過。

4. **TD-3 測試**：TD-3 是純行為變更（`pass` → `logger.warning()`），沒有可觀察的返回值或計數器變化，無法編寫有意義的單元測試而不引入對日誌調用的脆弱 mock。決定不補此測試，不增加技術債。

---

## 架構合規確認

- ✅ 1B-2：freshness_age_ms/freshness_score 在無數據時為 None（認知誠實，根原則 10）
- ✅ 1B-2：data_quality_warn_only=True 反映當前管線真實狀態（不偽裝 blocking）
- ✅ TD-3：成本記錄失敗仍為非致命，用 warning log 而非 pass（根原則 13 觀察性要求）
- ✅ TD-4：_h1_cooldown 有界，防止 650+ 幣種掃描場景下記憶體無限增長
- ✅ 所有新增代碼含中英雙語注釋
- ✅ 測試數從 2614 升至 2624，不低於基準
