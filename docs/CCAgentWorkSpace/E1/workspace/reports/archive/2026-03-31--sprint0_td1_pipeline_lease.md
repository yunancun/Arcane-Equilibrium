# Wave 6 Sprint 0 TD-1 報告：pipeline_bridge Decision Lease 插入

**日期**：2026-03-31
**執行者**：E1-Alpha（Backend Developer）
**任務**：TD-1 — `pipeline_bridge._process_pending_intents()` 在 Guardian 批准後插入 `acquire_lease()`
**狀態**：完成，待 E2+E4 驗收

---

## 問題背景

`pipeline_bridge.py` 的 `_process_pending_intents()` 中，Guardian 批准 TradeIntent 後直接調用 `submit_order()`，
違反根原則 3（AI 輸出 ≠ 即時命令）。`ExecutorAgent` 路徑（G-05）已有 `acquire_lease()`，但 `pipeline_bridge`
的直接執行路徑沒有。

---

## 修改文件清單

| 文件 | 行號 | 改動類型 |
|------|------|---------|
| `app/pipeline_bridge.py` | ~691–734（插入後） | 新增 `acquire_lease()` 調用塊（40 行） |
| `tests/test_edge_filter_integration.py` | 739–940（追加） | 新增 `TestPipelineBridgeDecisionLease` 測試類（4 個測試） |

---

## 修復細節

### 插入位置

```
_process_pending_intents() 流程：
  1. H0Gate 門控（~line 515-540）
  2. GovernanceHub.is_authorized() 檢查（~line 543-557）
  3. Guardian review：REJECTED → continue；MODIFIED → 修改 qty；APPROVED → fall-through
  4. ★ [新增] acquire_lease() 門控（~line 691-734）← 插入在此，覆蓋 APPROVED + MODIFIED 兩路徑
  5. 邊界過濾器（advisory，非阻塞）
  6. submit_order()（~line 701 之前的原位置，現為 line ~745）
```

APPROVED 和 MODIFIED 分支都會 fall-through 到同一位置，只需插入一次即可覆蓋兩種情況。

### fail-open / fail-closed 設計

```python
if self._governance_hub is not None:
    # governance_hub is None → fail-open（向後兼容，無 Hub 時不阻塞）
    _lease_id = self._governance_hub.acquire_lease(
        intent_id=..., scope="TRADE_ENTRY", ttl_seconds=30
    )
    if _lease_id is None:
        # fail-closed：Hub 存在但拒絕 → 跳過此 intent（DOC-01 §5.6）
        continue
    # acquire_lease 異常也會被 except 捕獲 → fail-closed
```

### intent_id 構建

`StrategyIntent` 物件（由 `type(...)` 動態創建）沒有 `intent_id` 屬性：

```python
_intent_id_for_lease = (
    getattr(intent, "intent_id", None)
    or f"pb-{intent.symbol}-{intent.side}-{id(intent)}"
)
```

### intents_lease_failed 計數器

使用 `.get("intents_lease_failed", 0) + 1` 安全遞增，不在 `__init__` 初始化（防止破壞現有測試斷言）。

---

## 測試設計

在 `tests/test_edge_filter_integration.py` 末尾追加 `TestPipelineBridgeDecisionLease` 類：

| 測試名 | 場景 | 預期結果 |
|--------|------|---------|
| `test_td1_no_hub_fail_open_submit_proceeds` | `governance_hub is None` | `submit_order` 被調用（fail-open） |
| `test_td1_acquire_lease_none_fail_closed_submit_blocked` | `acquire_lease()` 返回 `None` | `submit_order` **不**調用；`intents_lease_failed >= 1` |
| `test_td1_acquire_lease_success_submit_proceeds` | `acquire_lease()` 返回 `"lease-abc-12345"` | `submit_order` 被調用；lease 以 `TRADE_ENTRY` scope 調用 |
| `test_td1_acquire_lease_exception_fail_closed` | `acquire_lease()` 拋出 `RuntimeError` | `submit_order` **不**調用；`intents_lease_failed >= 1`；不崩潰 |

---

## 測試結果

```
4 passed（TestPipelineBridgeDecisionLease 全部通過）
全套：2614 passed, 17 failed（全部 pre-existing）, 1 skipped
基準從 2610 升至 2614（+4 新測試）
```

---

## 架構合規確認

- ✅ 根原則 3（AI 輸出 ≠ 即時命令）：Guardian 批准後必須申請 Decision Lease 才能執行
- ✅ 根原則 6（失敗默認收縮）：Hub 存在但 lease 申請失敗 → fail-closed，不執行
- ✅ 向後兼容：`governance_hub is None` → fail-open，不阻塞現有系統
- ✅ 與 G-05 ExecutorAgent 設計一致（兩層行為：None=fail-open，lease_id=None=fail-closed）
- ✅ 所有新代碼含中英雙語注釋
- ✅ `acquire_lease()` 異常路徑有獨立 except 塊（不吞異常，記 logger.error）
- ✅ `intents_lease_failed` 計數器可在 `get_stats()` 中查詢，便於監控
