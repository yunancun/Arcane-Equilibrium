# Sprint 5b-3 + 5b-4 報告：apply_ai_consultation 廢棄 + ScoutWorker daemon

**日期**：2026-03-31
**執行者**：E1-Delta（Backend Developer）
**任務**：5b-3（apply_ai_consultation() stub 標記廢棄）+ 5b-4（ScoutWorker 後台定時掃描線程）
**狀態**：全部完成，待 E2+E4 驗收

---

## 修改文件清單

| 文件 | 改動類型 |
|------|---------|
| `app/main_legacy.py` | 新增 `import warnings`；`AIConsultationResultData` 加 `deprecation_notice` 字段；`apply_ai_consultation()` 加 `warnings.warn(DeprecationWarning)` + 返回 `deprecation_notice`；路由 docstring 標記 DEPRECATED |
| `app/scout_worker.py` | 新建 — `ScoutWorker` 類：daemon 線程 + 可中斷睡眠 + stop() + is_alive |
| `app/phase2_strategy_routes.py` | 新增 ScoutWorker 初始化塊（Market Scanner 之後）：`_make_scout_scan_fn()` + `_SCOUT_WORKER.start()` |
| `tests/test_learning_chapter.py` | 新增 `test_ai_consult_response_includes_deprecation_notice` 測試 |
| `tests/test_scout_worker.py` | 新建 — 10 個測試（daemon/stop/scan_fn/error_no_crash/double_start/restart） |

---

## 5b-3：apply_ai_consultation() 廢棄

### 廢棄策略

1. **`import warnings`** 加入 `main_legacy.py` 頂部 import 區塊
2. **`AIConsultationResultData`** 新增可選字段 `deprecation_notice: str | None = None`
   - 用 `Optional` 語義保持向後兼容（現有調用不需傳此字段）
3. **函數頂部** 加 `warnings.warn(DeprecationWarning, stacklevel=2)`
   - `stacklevel=2` 指向 `apply_ai_consultation()` 的調用方（路由函數），而非函數本身
4. **返回 dict** 的 `data` 加 `"deprecation_notice"` 字段，內容指向 `/phase2/strategist/intel-log`
5. **路由 docstring** 標記 `[DEPRECATED]`，雙語說明遷移方向

### 兼容性保證

- 函數簽名不變：`(envelope, actor, packet_id) → tuple[dict, str]`
- 現有調用（`post_review_ai_consult` 路由）不改變
- `AIConsultationResultData(**result["data"])` 繼續工作（新字段有默認值 `None`）
- HTTP 回應 JSON 結構向後兼容（新增字段，未移除任何字段）

### DeprecationWarning 行為

- 通過 HTTP TestClient 調用時，warning 在服務器端發出，**不影響 HTTP 回應狀態碼或 body**
- 若有代碼直接調用 `apply_ai_consultation()` 函數（非 HTTP 路徑），會收到 Python DeprecationWarning
- 測試中用 `warnings.catch_warnings() + simplefilter("ignore")` 過濾，不影響測試輸出

---

## 5b-4：ScoutWorker 後台定時掃描線程

### 架構設計

```
ScoutWorker(scan_fn, interval_seconds=1800)
    ↓ start() → threading.Thread(daemon=True)
    ↓ _run_loop() — 每 1 秒檢查 stop_event（可中斷睡眠）
    ↓ 達到 interval 後 → scan_fn()
    ↓ 異常 → logger.error() → 繼續（不崩潰）
```

### 掃描函數包裝（_make_scout_scan_fn）

```python
opportunities = MARKET_SCANNER.scan()       # 觸發完整掃描
top = sorted(by score)[:5]                  # 取前 5 高分機會
SCOUT_AGENT.produce_intel(                  # 注入 Scout→Strategist 鏈路
    source="ScoutWorker",
    symbols=[...],
    content="top opportunities: ...",
    relevance_score=0.6,
)
```

### 與現有 MarketScanner 的關係

| 層次 | 觸發方式 | 間隔 | 目標 |
|------|---------|------|------|
| `MARKET_SCANNER.start()` 內部循環 | 自動（MarketScanner._run_loop） | 5 分鐘 | `AUTO_DEPLOYER.on_scan_results()` |
| `ScoutWorker` | 外部 wrapper | 30 分鐘 | `SCOUT_AGENT.produce_intel()` → MessageBus → Strategist |

兩者互補，不衝突。

### 初始化失敗處理（Non-fatal）

```python
try:
    _SCOUT_WORKER = ScoutWorker(scan_fn=...)
    _SCOUT_WORKER.start()
except Exception:
    logger.warning("ScoutWorker initialization failed (non-fatal): ...")
    _SCOUT_WORKER = None
```

主程序在 ScoutWorker 不可用時繼續正常運行（情報注入 fail-open）。

---

## 測試結果

### test_scout_worker.py（10 個新測試）

| 測試類 | 測試名 | 結果 |
|--------|--------|------|
| TestScoutWorkerStartsAsDaemon | test_scout_worker_starts_daemon_thread | ✅ |
| TestScoutWorkerStartsAsDaemon | test_scout_worker_thread_name | ✅ |
| TestScoutWorkerStop | test_scout_worker_stops | ✅ |
| TestScoutWorkerStop | test_scout_worker_is_alive_false_after_stop | ✅ |
| TestScoutWorkerCallsScanFn | test_scout_worker_calls_scan_fn | ✅ |
| TestScoutWorkerCallsScanFn | test_scout_worker_calls_scan_fn_multiple_times | ✅ |
| TestScoutWorkerScanErrorNoCrash | test_scout_worker_scan_error_no_crash | ✅ |
| TestScoutWorkerScanErrorNoCrash | test_scout_worker_scan_value_error_no_crash | ✅ |
| TestScoutWorkerDoubleStart | test_scout_worker_double_start_ignored | ✅ |
| TestScoutWorkerDoubleStart | test_scout_worker_start_after_stop_creates_new_thread | ✅ |

### test_learning_chapter.py（1 個新測試）

| 測試名 | 結果 |
|--------|------|
| test_ai_consult_response_includes_deprecation_notice | ✅ |

### 全套測試

```
2609 passed, 18 failed（全部 pre-existing），1 skipped
```

18 個失敗均為預存在問題（test_batch10/test_edge_filter/test_h_chain/test_integration_phase11/test_learning_tier_gate/test_ollama），與本次改動無關。

---

## 架構合規確認

- ✅ ScoutWorker daemon=True（主進程退出自動終止）
- ✅ scan 異常不崩潰 worker（logger.error + continue）
- ✅ stop() 在 ~1 秒內響應（1 秒分段睡眠）
- ✅ double start() 冪等
- ✅ ScoutWorker 初始化失敗 non-fatal（主程序繼續）
- ✅ apply_ai_consultation() 函數簽名不變（向後兼容）
- ✅ 所有新函數/類含中英雙語 docstring
- ✅ fail-closed/fail-open 路徑均有注釋說明原因
