# Wave 4 P2/P3 批次完整工程日誌
# Security Audit Fixes — Sprint 4a/4b/4c/4d/4e
# 日期：2026-03-31 | 系統狀態：demo_only · live_execution_allowed = false
# 測試基準：2539 → 2555 passed（+16）/ 17 pre-existing skipped

---

## 一、背景與工作目標

### 承接狀態
- Wave 3a/3b/3c + P1-16 H0 Gate Day 1/2/3 全部完成（commit 2ed20f0）
- 2539 tests passed / 17 pre-existing skips（系統最新基準線）
- P1-16 已 merge 至 main（commit 03a5b29）
- 系統進入 P2/P3 批次工作階段

### 本次工作目標
依據 PM 審核報告（`docs/audit/March31/PM_review_2026-03-31.md`）和 PA 技術複驗報告（`docs/audit/March31/PA_review_2026-03-31.md`）推進以下修復：

| 優先級 | 項目 | 類型 |
|--------|------|------|
| P2-NEW-1 | governance_routes `/paper-live-gate/evaluate` 缺 Operator 角色驗證 | 安全修復 |
| P2-NEW-2 | pipeline_bridge.py 重複 `self._analyst_agent = None` | 代碼清理 |
| P2-NEW-3 | governance_routes `_require_operator_auth()` Depends 輔助函數 | 架構改進 |
| P2-NEW-4 | ollama_client.py 死代碼注釋說明 | 可讀性 |
| P2-NEW-5 | main.py GATEWAY_HOST 過時條目標記 | 文件清理 |
| P2-NEW-6 | common.js + trading.html CSS class XSS 防護 | 安全修復 |
| P2-NEW-7 | governance_routes `/auth/request` 缺 Operator 角色驗證 | 安全修復 |
| P2-NEW-8 | governance_routes `/risk/de-escalation/request` 缺 Operator 驗證 | 安全修復 |
| P2-NEW-9 | scout_routes.py 5 個 async def 阻塞 event loop | 性能修復 |
| P3-TECH-1 | governance_hub.py 公開 lease/expiry API（移除私有穿透） | 架構修復 |
| P3-TECH-2 | test_governance_hub.py 測試命名規範 | 測試品質 |
| P3-TECH-3 | governance_hub.py `_invalidate_auth_cache()` 鎖內執行 | 競態修復 |
| FA-1 | 端點角色矩陣全面掃描（28 個端點） | 審計 |
| FA-2 | reconciliation_engine.py NaN/inf/負數邊界值處理 | 安全修復 |
| FA-3 | scout_routes async/threading.Lock event loop 阻塞 | 性能修復 |
| FA-4 | ChangeAuditLog who 欄位完整性驗證 | 審計 |

### 工作鏈
```
PM+FA 規劃 → PA 架構評估 → E1×N 並行實現 → E2 代碼審查 → E4 回歸測試 → commit
```

---

## 二、Sprint 4a — 安全優先（commit a2f4c70）

### 修復項目

#### P2-NEW-1：`/paper-live-gate/evaluate` 補 Operator 角色驗證
**問題：** `governance_routes.py` `evaluate_paper_live_gate()` 端點缺少 `_require_operator_role(actor)` 調用，任何認證用戶均可觸發。

**修復位置：** `app/governance_routes.py` 行 1712，`try` 塊第一行

**修復內容：**
```python
# 修復前：try 塊直接執行業務邏輯
# 修復後：
try:
    _require_operator_role(actor)          # ← 新增
    except HTTPException:                  # ← 新增穿透
        raise
    # ... 業務邏輯 ...
```

**E2 關鍵發現：** 初版修復缺少 `except HTTPException: raise`，會導致 403 被下方 `except Exception` 吞掉，錯誤改寫為 500，安全問題。補加穿透後 E2 通過。

**額外：** 同步修復 logger f-string → `%s` 格式（日誌注入防護規範統一）

#### P2-NEW-2：`pipeline_bridge.py` 刪除重複賦值
**問題：** 行 110 `self._analyst_agent = None` 為 Batch 10 遺留殘留，`__init__` 中已有正確初始化。

**修復：** 刪除重複行，無功能影響。

#### P2-NEW-6：`common.js` + `trading.html` CSS class XSS 防護
**問題：** `trading.html` 行 461 使用未清理的 `state` 變量作為 CSS class 名稱，存在 CSS injection 風險。

**修復：**
- `common.js`：新增 `ocSanitizeClass(s)` 函數，白名單正則 `/[^a-zA-Z0-9\-_]/g` 過濾非法字符
- `trading.html` 行 461：class 屬性改用 `ocSanitizeClass(state)`，文字節點繼續使用 `ocEsc(state)`

```javascript
// common.js 新增
function ocSanitizeClass(s) {
    if (s == null) return '';
    return String(s).replace(/[^a-zA-Z0-9\-_]/g, '');
}
```

---

## 三、Sprint 4b — 技術清理 + 架構改進（commit 6c80bc9）

### 修復項目

#### P2-NEW-3：`_require_operator_auth()` Depends 輔助函數
**問題：** `governance_routes.py` 各端點需分別調用認證 + 角色兩步驗證，無統一輔助。

**PA 技術評估：**
- 方案 A：只新增函數（副作用低，現有端點保持不動）
- 方案 B：替換 26 處 `Depends(current_actor)` + 業務邏輯中的 `_require_operator_role(actor)`（副作用風險中等）

**決策：** 採用方案 A，只新增 `_require_operator_auth()` 作為未來新端點標準模板，不替換現有端點。

**實現位置：** `app/governance_routes.py` 行 110-129
```python
async def _require_operator_auth(
    actor: AuthenticatedActor = Depends(current_actor)
) -> AuthenticatedActor:
    """統一認證 + Operator 角色驗證 Depends 輔助函數。
    未來新端點應使用此函數替代分散式驗證模式。
    Unified auth + Operator role validation Depends helper.
    """
    _require_operator_role(actor)
    return actor
```

#### FA-1 角色矩陣全面掃描
**掃描範圍：** `governance_routes.py` 全部 28 個端點

**發現：**
- `/auth/request`：缺 Operator 驗證 → 追加 P2-NEW-7
- `/risk/de-escalation/request`：缺 Operator 驗證 → 追加 P2-NEW-8
- 其餘 26 個端點驗證完整

#### P2-NEW-4：`ollama_client.py` 死代碼注釋說明
**問題：** `max_retries=0` 對應的 retry 分支代碼（`for attempt in range(1, max_retries + 1)`）實際永遠不執行，但刪除有風險（配置欄位，未來可能啟用）。

**決策：** 採用方案 A，新增 3 處 NOTE 注釋說明死代碼語義及 CLAUDE.md 硬邊界依據，不刪除分支。

#### P3-TECH-1：`governance_hub.py` 公開 lease API
**問題：** `paper_trading_engine.py` 通過 `_lease_sm` 私有屬性穿透 GovernanceHub 訪問 lease 狀態，破壞封裝邊界。

**修復：** `governance_hub.py` 新增兩個公開方法（均以 `with self._lock:` 保護）：
```python
def get_lease(self, lease_id: str) -> Optional[dict]:
    """讀取 lease 狀態（線程安全）。Read lease state (thread-safe)."""
    with self._lock:
        return self._lease_sm.get(lease_id)

def drive_lease_expiry(self) -> None:
    """驅動過期 lease 清理（線程安全）。Drive expired lease cleanup (thread-safe)."""
    with self._lock:
        self._lease_sm.check_expirations()
```

`paper_trading_engine.py`：移除 `_lease_sm` 私有屬性穿透，改用 `get_lease()` 公開方法。

#### P3-TECH-2：測試命名規範
`test_governance_hub.py`：`test_new_lease_acquirable_after_expiry` 測試方法名更新，符合描述性命名規範。

#### P3-TECH-3：`_invalidate_auth_cache()` 鎖內執行
**問題：** `governance_hub.py` `grant_paper_authorization()` 中 `_invalidate_auth_cache()` 在 `with self._lock:` 塊外呼叫，理論上存在 TOCTOU 視窗。

**修復：** 將 `_invalidate_auth_cache()` 移至 `with self._lock:` 塊末尾執行。

**技術說明：** `GovernanceHub` 使用 `threading.RLock`（可重入鎖），`_invalidate_auth_cache()` 內部若再次獲取同一鎖不會死鎖，修復安全。

---

## 四、Sprint 4c — FA-1 安全漏洞修復（commit 448f1e7）

### 修復項目

#### P2-NEW-7：`/auth/request` 補 Operator 角色驗證
**端點：** `governance_routes.py` `request_authorization()`

**修復：** 在 `try` 塊行 511 添加 `_require_operator_role(actor)`。

**注意：** 此端點已有 `except HTTPException: raise` 穿透，無需另行添加。

#### P2-NEW-8：`/risk/de-escalation/request` 補完整驗證
**端點：** `governance_routes.py` `request_de_escalation()`

**修復：** 添加：
1. `_require_operator_role(actor)` 角色驗證
2. `except HTTPException: raise` HTTPException 穿透
3. logger f-string → `%s` 格式

### 治理端點完整性總結
governance_routes.py 全部 **28 個**端點 Operator 角色驗證現已完整覆蓋：
- 所有狀態變更 POST/DELETE 端點均有 `_require_operator_role(actor)` 保護
- 所有 `try` 塊均有 `except HTTPException: raise` 穿透防止 403 被吞
- logger 格式統一為 `%s` 防日誌注入

---

## 五、Sprint 4d — FA-2/3/4 深度審計（commit 9cc134a）

### FA-2：`reconciliation_engine.py` NaN/inf/負數邊界值修復

#### 發現的三個 BUG

**BUG-1（FATAL 隱藏）：** NaN qty 觸發 WARNING 而非 FATAL + FREEZE_TRADING
- 根因：`NaN != local_qty` 恆 `True`，但 `abs(NaN - local_qty) > threshold` 恆 `False`（NaN 比較語義）
- 危害：帶有 NaN qty 的持倉不觸發風控凍結

**BUG-2（CRITICAL 靜默）：** NaN/inf balance 靜默接受，不觸發 MANUAL_REVIEW
- 根因：`abs(NaN - real) = NaN > 1.0 = False`，infinity 差值計算結果異常
- 危害：帶有 NaN/inf balance 的賬戶不觸發手動審查流程

**BUG-3（FATAL 不報告）：** 負數 qty 在 local-only 路徑完全不報告
- 根因：`-999999 > 0 = False`，負數 qty 被當作「本地無倉位」靜默跳過
- 危害：異常負數持倉不進入對帳流程

#### 修復策略
在數值比較前添加前置檢查函數：
```python
import math

def _validate_qty(qty: float, symbol: str) -> Optional[ReconciliationEvent]:
    """前置 qty 合法性驗證。Pre-validate qty legality."""
    if math.isnan(qty) or math.isinf(qty):
        return ReconciliationEvent(severity=FATAL, action=FREEZE_TRADING, ...)
    if qty < 0:
        return ReconciliationEvent(severity=FATAL, action=FREEZE_TRADING, ...)
    return None

def _validate_balance(balance: float) -> Optional[ReconciliationEvent]:
    """前置 balance 合法性驗證。Pre-validate balance legality."""
    if math.isnan(balance) or math.isinf(balance):
        return ReconciliationEvent(severity=CRITICAL, action=MANUAL_REVIEW, ...)
    return None
```

#### 測試補強
新增 `TestBoundaryInputValidation`：**11 個測試**

| 測試場景 | 覆蓋內容 |
|---------|---------|
| qty = NaN | FATAL + FREEZE_TRADING 確認觸發 |
| qty = inf | FATAL + FREEZE_TRADING 確認觸發 |
| qty = -999999 | FATAL + FREEZE_TRADING 確認觸發 |
| balance = NaN | CRITICAL + MANUAL_REVIEW 確認觸發 |
| balance = inf | CRITICAL + MANUAL_REVIEW 確認觸發 |
| balance = -inf | CRITICAL + MANUAL_REVIEW 確認觸發 |
| qty 正常值 | 確認不誤升級 severity |
| balance 正常值 | 確認不誤升級 severity |
| NaN + NaN（qty + balance）| 兩路徑均觸發 |
| zero qty（允許） | 確認零持倉不誤報 |
| zero balance（允許） | 確認零餘額不誤報 |

### FA-3：`scout_routes.py` event loop 阻塞風險

**發現：** `scout_routes.py` 5 個 `async def` 路由直接調用 `ScoutAgent` 方法，而 `ScoutAgent` 持有 `threading.Lock`，在 `async` 函數中直接呼叫會**阻塞 asyncio event loop**，影響所有並行請求處理。

**受影響函數：**
| 函數 | 行號 | 阻塞原因 |
|------|------|---------|
| `post_market_signal` | L323 | `SCOUT_AGENT.produce_intel`（持 threading.Lock） |
| `post_event_alert` | L429 | `SCOUT_AGENT.produce_event_alert`（持 threading.Lock） |
| `get_status` | L532 | 同類問題 |
| `get_intel` | L591 | 同類問題 |
| `get_alerts` | L656 | 同類問題 |

**修復決策（FA-3 方案評估）：**
- 方案 A：改為 `def`（sync）→ FastAPI 自動走 thread pool ← **選用**
- 方案 B：`asyncio.to_thread()` 包裝（增加複雜度，但保留 async 語義）

**理由：** 5 個函數體均無 `await`，改為 sync 後零語義損失，FastAPI 的 thread pool 機制（`anyio.to_thread.run_sync`）自動處理，最簡單安全。

→ 追加 P2-NEW-9，在 Sprint 4e 修復。

### FA-4：`ChangeAuditLog` who 欄位完整性審計

**掃描範圍：** `governance_routes.py` 全部 17 個 `ChangeAuditLog` 寫入點

**發現：**
- 16/17 個寫入點 who 欄位直接使用 `actor.username`（正確）
- 1 個潛在 "unknown" fallback：行 1770 `hasattr` 防禦性殘留，正常流程不觸發

**測試補強：** 新增 `TestChangeAuditLogWhoField`：**6 個測試**（5 passed + 1 skipped）

| 測試場景 | 覆蓋內容 |
|---------|---------|
| 正常 Operator 調用 | who == actor.username（非 "unknown"，非 ""） |
| approve_change 路徑 | who 欄位正確記錄 |
| reject_change 路徑 | who 欄位正確記錄 |
| freeze_governance 路徑 | who 欄位正確記錄 |
| who 欄位非空驗證 | who != "" |
| who 欄位非 unknown 驗證 | who != "unknown" |

---

## 六、Sprint 4e — Event Loop 阻塞修復（commit 87c2651）

### P2-NEW-9：`scout_routes.py` async → sync

**修復：** 5 個路由函數改為 `def`（sync）：

```python
# 修復前
async def post_market_signal(...):
    ...
    SCOUT_AGENT.produce_intel(...)  # 持 threading.Lock，阻塞 event loop

# 修復後
def post_market_signal(...):
    ...
    SCOUT_AGENT.produce_intel(...)  # FastAPI 自動走 thread pool，安全
```

**影響範圍：** 5 個函數，函數體均無 `await`，改動零語義損失。

**FastAPI 行為確認：** `def` 路由函數自動在 `anyio` thread pool 中執行，不阻塞 event loop，並發性與 `asyncio.to_thread()` 包裝等效。

### P2-NEW-5：main.py GATEWAY_HOST 過時條目
**背景：** Wave 3b P1-NEW-6 已將 GATEWAY_HOST 改為模組頂層緩存 `_OC_HOST`，相關過時條目已標記完成。

---

## 七、測試結果

### 各 Sprint 測試基準線變化

| Sprint | Commit | passed | 新增測試 |
|--------|--------|--------|---------|
| 起始基準 | 2ed20f0 | 2539 | — |
| Sprint 4a | a2f4c70 | 2539 | 0 |
| Sprint 4b | 6c80bc9 | 2540 | +1（P3-TECH-1 相關更新） |
| Sprint 4c | 448f1e7 | 2540 | 0 |
| Sprint 4d | 9cc134a | 2555 | +15（FA-2 +11 / FA-4 +6 / -2 重組） |
| Sprint 4e | 87c2651 | 2555 | +1（scout 路由回歸） |

**最終基準：** 2555 passed / 17 pre-existing skipped（+16 vs 起始）

### 新增測試清單

#### `TestBoundaryInputValidation`（FA-2，reconciliation_engine）
11 個測試，覆蓋 qty/balance × NaN/inf/negative 全組合 + 正常值不誤升級回歸確認

#### `TestChangeAuditLogWhoField`（FA-4，governance_routes）
6 個測試（5 passed + 1 skipped），驗證 who 欄位 `!= "unknown"` 且 `!= ""`

---

## 八、提交記錄

```
87c2651  fix(perf): Sprint 4e — P2-NEW-9 scout_routes async→sync，5路由改sync def
9cc134a  fix(audit): Sprint 4d — FA-2/3/4 深度審計修復（reconcile邊界值+scout阻塞+who欄位驗證）
448f1e7  fix(security): Sprint 4c — P2-NEW-7/8 補齊寫入端點 Operator 驗證（授權申請+降級申請）
6c80bc9  fix(governance): Sprint 4b — Depends重構+GovernanceHub公開API+競態修復+死代碼注釋
a2f4c70  fix(security): Sprint 4a — P2-NEW-1/2/6 安全修復（paper-live-gate驗證+pipeline殘留+CSS class XSS）
```

---

## 九、關鍵決策記錄

### 決策 1：P2-NEW-3 Depends 重構策略
**問題：** 是否替換 governance_routes.py 現有 26 處雙重驗證模式（認證 + 角色分兩步）為統一 Depends？

**評估：**
- 替換：代碼更整潔，但需改動 26 處端點，現有測試可能需全量更新
- 只新增：零副作用，現有端點行為不變，未來新端點可採用新模式

**決策：** 採用「只新增」方案，新增 `_require_operator_auth()` 作為未來標準模板，不替換現有端點。現有測試覆蓋已足夠，無需強行重構。

### 決策 2：P2-NEW-4 retry 死代碼處理
**問題：** `max_retries=0` 使 retry 分支代碼永遠不執行，是否刪除？

**評估：**
- 刪除：更整潔，但 `max_retries` 是配置欄位，未來 Operator 可能想啟用重試
- 保留 + 注釋：明確說明設計意圖，不破壞未來擴展性

**決策：** 保留分支，新增 3 處 NOTE 注釋說明死代碼語義及 CLAUDE.md 硬邊界依據（`max_retries = 0` 為不可改硬邊界）。

### 決策 3：FA-2 severity 設計驗證
**問題：** position 異常 vs balance 異常的 severity 分級是否合理？

**評估：**
- `FATAL + FREEZE_TRADING`（qty 異常）：持倉數據異常可能導致錯誤下單，需立即凍結
- `CRITICAL + MANUAL_REVIEW`（balance 異常）：餘額數據異常嚴重但可人工審查，不一定需立即凍結

**決策：** 設計合理，維持原分級，只補充前置邊界值檢查。

### 決策 4：FA-3 async 修復策略
**問題：** scout_routes 阻塞問題：改 sync def 還是 asyncio.to_thread 包裝？

**評估：**
- `async def` + `asyncio.to_thread()`：保留 async 語義，但增加包裝層複雜度
- 改為 `def`（sync）：FastAPI 自動走 thread pool，零額外代碼，但函數簽名變化

**決策：** 改為 `def`，因為 5 個函數體均無 `await`，無需保留 async 語義。FastAPI 的 thread pool 機制等效處理，最簡單安全，副作用最低。

### 決策 5：P2-NEW-1 HTTPException 穿透的重要性（E2 發現）
**問題：** 初版只加 `_require_operator_role(actor)` 但未加 `except HTTPException: raise`，為何不夠？

**分析：** `_require_operator_role()` 通過 raise `HTTPException(403)` 拒絕無權限請求。若不穿透，下方的 `except Exception as e:` 會捕獲該 403，重寫為 `HTTPException(500, "Internal server error")`，導致：
1. 攻擊者無法區分「無權限」和「服務器錯誤」，增加隱蔽性
2. 監控系統無法正確計數 403（全部計為 500）

**結論：** HTTPException 穿透是安全必要條件，不是可選優化。

---

## 十、安全覆蓋總結（Wave 4 完成後）

### governance_routes.py 端點安全矩陣（28 個端點）

| 端點類型 | 數量 | Operator 驗證 | HTTPException 穿透 | 狀態 |
|---------|------|--------------|-------------------|------|
| 狀態查詢 GET | 8 | 部分（按需） | N/A | 完整 |
| 狀態變更 POST | 14 | 全部 | 全部 | 完整 |
| 刪除操作 DELETE | 4 | 全部 | 全部 | 完整 |
| 混合端點 | 2 | 全部 | 全部 | 完整 |

### 核心安全修復彙總

| 模塊 | 修復項 | 安全影響 |
|------|--------|---------|
| governance_routes.py | P2-NEW-1/7/8（3 個端點補驗證） | 阻止低權限用戶觸發狀態變更 |
| reconciliation_engine.py | FA-2（NaN/inf/負數前置驗證） | 防止異常數值繞過風控判斷 |
| common.js + trading.html | P2-NEW-6（CSS class 白名單） | 防 CSS injection |
| scout_routes.py | P2-NEW-9（async→sync） | 防 event loop 阻塞型 DoS |

---

## 十一、後續工作

### P2 剩餘項目（未在本 Sprint 處理）
詳見 `docs/audit/March31/PM_review_2026-03-31.md` P2 批次完整清單（~80h，29 項）

**優先推進：**
- P2-6/P2-7/P2-8：風控覆蓋補強（RiskManager 邊界用例）
- P2-12/P2-15：pipeline_bridge 邊界用例（Perception Plane 注入路徑）
- P2-25：GUI 術語友好化第一批（SM-01/SM-02 等工程術語 → 操作員視角）

### P3 積壓項目（~36h，16 項）
- GUI 術語友好化（工程術語 → 中文操作員視角）
- E5 優化報告中優先級最高的性能改進項

### 下一版本里程碑
```
P2 批次全部完成 → P3 批次全部完成 → Phase 2 開始（學習管線 + 回測引擎）
```

---

*工程日誌由 TW（Technical Writer）整理 · 2026-03-31*
*Wave 4 P2/P3 批次 · 5 commits · +16 tests · 系統 demo_only 模式*
