# Paper/Demo 同步修復 — 10 項分歧根源分析 + 5 項修復
# 2026-03-31 工程日誌

---

## 背景 (Background)

用戶報告 Paper Trading 與 Bybit Demo 數據從未對齊。經全面調查發現 **10 項分歧根源**，
其中 3 項 CRITICAL 級別，每一項都獨立保證兩邊永遠對不上。

---

## 問題分析 (Root Cause Analysis)

### CRITICAL 級別（3 項）

| # | 問題 | 檔案 | 影響 |
|---|------|------|------|
| 1 | `_check_stops()` 止損只平 Paper，不平 Demo | pipeline_bridge.py:775-819 | 每次 trailing/time stop 都在 Demo 留幽靈倉 |
| 2 | Demo 下單失敗被 `logger.debug` 靜默吞掉 | pipeline_bridge.py:750-763 | Paper 有倉 Demo 沒有，分歧不可逆累積 |
| 3 | 對賬引擎參數名 `demo_state=` vs `remote_state=` | governance_hub.py:1063-1066 | TypeError 被 except 吞，對賬從未成功運行 |

### MODERATE 級別（4 項）

| # | 問題 | 影響 |
|---|------|------|
| 4 | Paper 不做 qty 四捨五入，Demo 做 | 倉位大小永遠不同 |
| 5 | Paper 固定 0.05% 滑點，Demo 真實訂單簿 | 成交價永遠不同 |
| 6 | Paper 餘額 10k-100k，Demo 610 USDT | Demo 因餘額不足拒單 |
| 9 | Observer 快照停在 3/22，cron 下游腳本路徑失效 | 對賬無新鮮 Demo 數據 |

### LOW 級別（3 項）

| # | 問題 | 影響 |
|---|------|------|
| 7 | ScheduledReconciler 從未實例化 | 無獨立對賬循環 |
| 8 | 費率模型不同（Paper 固定 vs Demo VIP 等級） | 餘額漸進漂移 |
| 10 | 條件止損單 qty 用未 rounded 的 intent.qty | Demo 殘留碎片倉位 |

---

## 修復內容 (Fixes Applied)

### Fix-1: 止損同步平 Demo 倉位 (CRITICAL-1)
**檔案：** `pipeline_bridge.py` `_check_stops()`

在 Paper 止損單提交後，增加 Demo 平倉邏輯：
- 使用 `reduce_only=True` 確保只平倉不開新倉
- qty 先做 `round_qty_for_exchange()` 確保精度對齊
- Demo 失敗不阻塞 Paper 止損（fail-open，本地止損優先）

### Fix-2: Demo 下單失敗明確標記 (CRITICAL-2)
**檔案：** `pipeline_bridge.py` `_process_pending_intents()`

- 日誌從 `debug` → `WARNING`，明確輸出 "Paper/Demo DIVERGED"
- 新增 `_demo_synced` flag 追蹤同步狀態
- stats 增加 `demo_synced` / `demo_diverged` 計數器

### Fix-3: 對賬引擎參數名 + dataclass 處理 (CRITICAL-3)
**檔案：** `governance_hub.py` `reconcile()`

- `demo_state=` → `remote_state=`（與 ReconciliationEngine.reconcile() 簽名對齊）
- `report.get("severity")` → `report.critical_count`（ReconciliationReport 是 dataclass 不是 dict）
- `report.to_dict()` 轉換後回傳，供下游 API 消費
- 修復後對賬引擎首次真正運行

### Fix-4: 統一 qty 四捨五入 (MODERATE-4)
**檔案：** `bybit_demo_connector.py` + `pipeline_bridge.py`

- 提取 `round_qty_for_exchange()` 為模組級共用函數
- Pipeline bridge 在提交 Paper 引擎**之前**先做 rounding
- Paper 和 Demo 收到完全相同的 qty 值

### Fix-5: 條件止損單用 rounded qty (MODERATE-10)
**檔案：** `pipeline_bridge.py` `_on_position_open()`

- 新增 `actual_qty` 參數（實際提交的 rounded qty）
- 呼叫端傳入 `_submit_qty`（已 rounded）
- 條件止損單 qty 與 Demo 實際倉位大小一致

### 測試修正
**檔案：** `test_governance_hub.py` `test_reconcile_success`

- 之前的斷言 `"ok" in report` 只因對賬壞掉回傳錯誤 dict 才通過
- 更新為 `"overall_result" in report`（正確的 ReconciliationReport 結構）
- 修正 paper_state 測試數據結構（positions: {} 不是 []）

---

## 修改檔案清單

| 檔案 | 變更 |
|------|------|
| `app/pipeline_bridge.py` | +86 行：止損 Demo 同步 + 失敗標記 + qty 統一 + actual_qty 傳遞 |
| `app/governance_hub.py` | 參數名修正 + dataclass→dict 轉換 |
| `app/bybit_demo_connector.py` | +17 行：`round_qty_for_exchange()` 共用函數 |
| `tests/test_governance_hub.py` | 對賬測試斷言更新 |

---

## 測試結果

```
2555 passed / 17 failed（全部 pre-existing）/ 1 skipped / 23 warnings
無新增失敗
```

---

## 未修復項目（已知，非本次範圍）

| # | 問題 | 原因 |
|---|------|------|
| 5 | 成交價差異（滑點模型 vs 真實訂單簿） | 本質差異，無法消除，需接受 |
| 6 | 餘額差異（Paper 10k+ vs Demo 610） | 需要重置 Demo 帳戶或調整 Paper 初始餘額 |
| 7 | ScheduledReconciler 未實例化 | 需要在啟動流程中加入，待後續 |
| 8 | 費率模型差異 | 可忽略，影響極小 |
| 9 | Observer cron 下游腳本路徑失效 | 需要修復 cron 腳本路徑，待後續 |
