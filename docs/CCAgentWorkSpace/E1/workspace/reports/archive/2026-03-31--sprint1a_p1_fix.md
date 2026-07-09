# Sprint 1a P1-1 修復報告：submit_order rejected 時不注入學習信號

**日期**：2026-03-31
**執行者**：E1-Beta（Backend Developer）
**任務**：P1-1 — FA-7 新增塊中，submit_order 返回 rejected_reason 時仍調用 _emit_round_trip()，注入虛假學習信號
**狀態**：完成，待 E2+E4 驗收

---

## 問題背景

E2 審查 FA-7 時發現：`_check_stops()` 中 FA-7 新增的 `_emit_round_trip()` 調用塊，在
`submit_order()` 返回 `rejected_reason`（訂單被 governance/risk 拒絕）時仍無條件執行，
向 PerceptionPlane 注入一個「幽靈交易」學習信號。

具體問題：
- 訂單被拒 = 倉位未真正平倉
- 但 `_emit_round_trip()` 仍被調用 = 告訴學習管線「有一筆止損交易完成了」
- 結果：學習管線積累虛假數據，破壞策略評估的準確性（違反原則 10：認知誠實）

---

## 修改文件清單

| 文件 | 改動類型 |
|------|---------|
| `app/pipeline_bridge.py` | FA-7 塊前加 `_stop_order_rejected` 判斷，整個 try/except 包裹在 `if not _stop_order_rejected:` 內 |
| `local_model_tools/tests/test_pipeline_bridge_coverage.py` | `TestCheckStopsPerceptionPlane` 新增 `test_register_data_not_called_when_order_rejected`（第 5 個測試） |

---

## 修復邏輯

### 核心判斷

```python
# P1-1 Guard: only emit round_trip if the stop order was actually executed.
# P1-1 守衛：只有止損單真正成交才注入學習信號。
_stop_order_rejected = isinstance(result, dict) and bool(
    result.get("rejected_reason")
)
if not _stop_order_rejected:
    try:
        # ... 原有 _emit_round_trip() 調用（縮排+4）
    except Exception as _rt_err:
        # ... 原有 except 塊（縮排+4）
```

### 安全 Fallback 設計

| `result` 類型 | `_stop_order_rejected` | 行為 |
|---|---|---|
| `{"rejected_reason": "..."}` | `True` | 跳過 emit ✅ |
| `{"order": {...}}` (正常成交) | `False` | 執行 emit ✅ |
| `None` | `False` | 執行 emit（安全預設，不丟棄有效數據）✅ |
| 非 dict | `False` | 執行 emit（同上）✅ |

### 注釋變化

原 `# ── FA-7: Inject into Perception Plane via _emit_round_trip ──` 更名為
`# ── FA-7 / Sprint 1a P1-1: ...` 以反映修復歷史。

新增的 P1-1 守衛說明：
- 英文：解釋為何 rejected order 不應觸發學習信號
- 中文：同步說明防止幽靈交易數據污染學習管線

---

## 新增測試設計

```python
def test_register_data_not_called_when_order_rejected(self):
    """
    Sprint 1a P1-1: If submit_order() returns a rejected_reason, the stop
    order was NOT executed — _emit_round_trip() must NOT be called.
    P1-1：若 submit_order() 返回 rejected_reason，止損單未成交，
    不應調用 _emit_round_trip()，防止向學習管線注入虛假數據（幽靈交易）。
    """
```

驗證邏輯：
1. monkey-patch `engine.submit_order` → 返回 `{"rejected_reason": "guardian_rejected: risk limit exceeded"}`
2. patch `bridge._emit_round_trip` 為 `MagicMock()`
3. 調用 `bridge._check_stops()`
4. assert `mock_rt.assert_not_called()` — `_emit_round_trip` 未被調用
5. assert `plane.register_data.assert_not_called()` — `register_data` 同樣未被調用

---

## 測試結果

```
TestCheckStopsPerceptionPlane（5 個測試）：5 passed ✅
全套件：2827 passed（+10 vs baseline 2817），128 failed（全部 pre-existing），0 新增失敗
```

---

## 架構合規確認

- ✅ 原則 10（認知誠實）：不再向學習管線注入未成交的虛假交易數據
- ✅ 原則 5（生存 > 利潤）：fa-7 的 try/except 非致命包裝保留，止損主路徑不受影響
- ✅ 原則 12（持續進化）：真正成交的止損仍會注入學習信號（if not rejected 路徑）
- ✅ 雙語注釋：所有新增代碼含中英文說明
- ✅ Safety fallback：result 非 dict 時預設為成交（不丟棄潛在有效學習數據）
