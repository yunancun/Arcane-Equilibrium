# E2 Code Review Report: Wave 6 Sprint 0 TD-1
# E2 代碼審查報告：Wave 6 Sprint 0 TD-1

**審查日期**: 2026-03-31
**審查員**: E2（Code Reviewer）
**任務範圍**: TD-1 pipeline_bridge acquire_lease 門控（Principle 3：AI output ≠ immediate command）
**修改文件**: `app/pipeline_bridge.py`（acquire_lease 門控插入）、`tests/test_edge_filter_integration.py`（TestPipelineBridgeDecisionLease 新增）
**測試基準**: 2609 passed（Sprint 5b 後）→ 2614 passed（Sprint 0 TD-1 後，+4 新增）

---

## 一、審查摘要

| 審查項目 | 結論 |
|---------|------|
| 架構合規：acquire_lease 在 submit_order 之前 | ✅ PASS |
| fail-open 路徑（hub=None） | ✅ PASS |
| fail-closed 路徑（lease=None） | ✅ PASS |
| fail-closed 路徑（acquire_lease 拋出異常） | ✅ PASS |
| APPROVED + MODIFIED 兩分支均覆蓋 | ✅ PASS |
| intents_lease_failed 計數器 | ✅ PASS（功能正確，P2 初始化不一致見下） |
| 雙語注釋合規 | ✅ PASS |
| 安全審查 | ✅ PASS |
| 測試合規（4 個新測試，全部通過） | ✅ PASS |

**總體結論：✅ PASS（可進入 E4 回歸）**

---

## 二、架構驗證

### 代碼位置確認（pipeline_bridge.py L691–L733）

```
Guardian 裁定
  ├── REJECTED → continue（不進入 acquire_lease）
  ├── MODIFIED → 調整 qty/leverage，fall-through → acquire_lease 門控 ✅
  └── APPROVED → fall-through → acquire_lease 門控 ✅

acquire_lease 門控（L697–L733）：
  ├── governance_hub is None → 跳過整個 if 塊，直接到 submit_order（fail-open）✅
  ├── acquire_lease() 返回 None → intents_lease_failed++ → continue（fail-closed）✅
  └── acquire_lease() 拋出異常 → except Exception → logger.error → intents_lease_failed++ → continue（fail-closed）✅

submit_order() 調用（L745）：僅在所有門控全部通過後到達 ✅
```

### 關鍵設計確認

- **APPROVED 和 MODIFIED 共用同一個 acquire_lease 門控**：兩者均 fall-through 到 L697，不存在任何 submit_order 的旁路路徑。
- **Guardian 不可用路徑（L666）**：直接 `continue`，不進入 acquire_lease 塊，符合 fail-closed 語義。
- **異常消息格式**：`logger.error("... (%s) / ...", _lease_err)`，異常細節僅進入日誌，不暴露到外部響應，符合安全規範。

---

## 三、雙語注釋合規

### pipeline_bridge.py 新插入塊（L691–L733）

- ✅ 代碼塊頂部有中英雙語說明（L691–L696）：
  - 英文：`H6: Acquire Decision Lease before execution (Principle 3: AI output ≠ command)`
  - 中文：`H6：執行前申請 Decision Lease，確保 Guardian 批准不直接等於執行命令（根原則 3）`
- ✅ fail-open 語義有注釋：`fail-open when governance_hub is None (backward compat, no hub deployed)` + 中文對應
- ✅ fail-closed 語義有注釋：`fail-closed: Guardian approved but lease acquisition failed` + `DOC-01 §5.6` 規格引用
- ✅ 異常 fail-closed 路徑有注釋：`Lease acquisition error → fail-closed (DOC-01 §5.6)` + 中文說明「不允許在治理狀態不明時執行」

### tests/test_edge_filter_integration.py 新增類（L740–L973）

- ✅ 類級 docstring：中英雙語，說明 4 種設計場景，引用根原則 3（DOC-01 §5.3）
- ✅ 工具函數 `_make_bridge_with_guardian_approved()`：中英雙語 docstring
- ✅ 工具函數 `_make_mock_governance_hub()`：中英雙語 docstring + Args 說明
- ✅ 所有 4 個測試方法：中英雙語 docstring，說明測試場景和驗證目標
- ✅ 關鍵斷言均有 inline comment 中英說明

---

## 四、安全審查

- ✅ 無 SQL 操作，無字符串拼接注入風險
- ✅ 異常處理：無 `except: pass`；兩個 except 路徑均有 `logger.error(...)` 並使用 `%s` 格式化（不使用 f-string 防日誌注入）
- ✅ 異常詳細信息（`_lease_err`）僅進入日誌，未暴露到外部
- ✅ 無 HTTPException 路徑（pipeline_bridge 為內部模塊，不涉及 HTTP 層）
- ✅ 異常作為 `logger.error` 的最後一個 `%s` 參數傳入，不拼接到字符串

---

## 五、測試覆蓋確認

| 測試名稱 | 覆蓋場景 | 結果 |
|---------|---------|------|
| `test_td1_no_hub_fail_open_submit_proceeds` | hub=None → fail-open，submit_order 被調用 | ✅ PASS |
| `test_td1_acquire_lease_none_fail_closed_submit_blocked` | lease=None → fail-closed，submit_order 不調用 + 計數器遞增 | ✅ PASS |
| `test_td1_acquire_lease_success_submit_proceeds` | lease='lease-abc-12345' → submit_order 被調用 + scope='TRADE_ENTRY' 確認 | ✅ PASS |
| `test_td1_acquire_lease_exception_fail_closed` | RuntimeError → fail-closed，不崩潰，submit_order 不調用 + 計數器遞增 | ✅ PASS |

**實際執行結果**（`python3 -m pytest tests/test_edge_filter_integration.py::TestPipelineBridgeDecisionLease -v`）：
```
4 passed in 0.03s
```

### 測試覆蓋補充觀察

- ✅ TRADE_ENTRY scope 在 Test 3 中有顯式 `assert "TRADE_ENTRY" in str(call_kwargs)` 驗證
- ✅ `intents_lease_failed` 計數器在 Test 2 和 Test 4 均有驗證
- ✅ Test 4 驗證異常不導致 `_process_pending_intents()` 崩潰（重要：outer loop 不中斷）

---

## 六、WARN 項目

### WARN-1（P2）：`intents_lease_failed` 未在 `__init__` 中預初始化

**位置**：`pipeline_bridge.py L114`（`self._stats = {...}` 初始化塊）

**問題**：其他 stats（`ticks_received`, `intents_submitted`, `intents_accepted`, `intents_rejected`, `stops_triggered`, `errors`, `last_tick_ts_ms`）均在 `__init__` 中初始化為 `0`，而 `intents_lease_failed` 使用 `self._stats.get("intents_lease_failed", 0) + 1` 懶更新模式，直到第一次 lease 失敗前不出現在 `get_stats()` 返回值中。

**影響**：
- 功能正確（`.get()` 防 KeyError）
- 測試正確（`stats.get("intents_lease_failed", 0) >= 1`）
- **但** GUI/API 消費 `get_stats()` 的代碼若 hardcode 期待所有 stats key 始終存在，會得到 `None`（若未用 `.get()`）

**建議修復**（P2）：在 `self._stats` 初始化塊（L114）添加 `"intents_lease_failed": 0`，並將代碼中的 `.get("intents_lease_failed", 0) + 1` 改為 `+= 1`（與其他計數器一致）。預估修復時間：5 分鐘。

---

## 七、最終結論

**✅ PASS（可進入 E4 回歸）**

所有強制審查項全部通過：
- 架構合規：PASS（acquire_lease 確實在 submit_order 之前，APPROVED/MODIFIED 兩分支均覆蓋）
- fail-open（hub=None）：PASS（向後兼容設計正確）
- fail-closed（lease=None）：PASS（continue + 計數器遞增）
- fail-closed（異常）：PASS（try/except + logger.error + continue，不吞異常）
- 雙語注釋合規：PASS（代碼塊 + 測試類均有完整中英雙語）
- 安全審查：PASS（無 SQL/命令注入，無 except:pass，異常不暴露外部）
- 測試合規：PASS（4 個新測試全部通過，覆蓋所有設計場景）

1 個 WARN 項（P2 追蹤，非阻斷）：`intents_lease_failed` 未在 `__init__` 預初始化。
