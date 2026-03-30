# Phase 1 任務書：治理接入（Governance Wiring）
# Phase 1 Task Book: Governance Wiring

**版本：** V1.0
**日期：** 2026-03-30
**作者：** PM (via Cowork PM)
**狀態：** ACTIVE
**Phase 完成標準：** 所有訂單必須通過 Auth → Lease → Risk → Execute 鏈，任何一環失敗則訂單被拒。

---

## 修正：Phase 0 審計報告偏差

經代碼逐行驗證，Phase 0 審計報告（GAP-C2）描述有偏差：

| 審計報告描述 | 實際代碼狀態 |
|-------------|-------------|
| GovernanceHub 未注入 PaperEngine | ✅ **已注入**（`paper_trading_routes.py:70`） |
| GovernanceHub 未注入 RiskManager | ✅ **已注入**（`paper_trading_routes.py:71`） |
| GovernanceHub 未注入 PipelineBridge | ❌ **確認未注入**（`set_governance_hub()` 存在但未被調用） |
| `is_authorized()` 為 warning-only | ⚠️ **部分正確** — PE 和 PB 已拒絕訂單，但 exception handler 為 non-fatal |
| `acquire_lease()` 為 warning-only | ❌ **確認 non-fatal** — lease 失敗時訂單繼續執行 |

**修正後的 GAP 重新定義：**

| GAP ID | 真實問題 | 嚴重度 |
|--------|---------|--------|
| GAP-C1a | PipelineBridge 未注入 GovernanceHub（`phase2_strategy_routes.py:193` 後缺少注入） | CRITICAL |
| GAP-C1b | `acquire_lease()` 失敗時訂單繼續（`paper_trading_engine.py:907-916`，無 lease 不阻止下單） | CRITICAL |
| GAP-C1c | 所有 `is_authorized()` exception handler 為 non-fatal（`logger.warning` + 繼續） | HIGH |
| GAP-C1d | 所有 `acquire_lease()` exception handler 為 non-fatal | HIGH |
| GAP-C2 | TTL Enforcer daemon 未在主流程啟動 | HIGH |
| GAP-C3 | Incident → SM 自動級聯未在主流程啟用 | HIGH |
| GAP-C4 | 審計日誌持久化未在 SM 啟動時連接 AuditPipeline | HIGH |
| GAP-C5 | H0 Gate 部分 check 為 warning-only | MEDIUM |
| GAP-C6 | Paper→Live Gate 閾值需對齊治理文件 | MEDIUM |

---

## 任務總覽

| Task ID | 任務名稱 | 優先級 | 工作量 | 依賴 | 狀態 |
|---------|---------|--------|--------|------|------|
| T1.01 | PipelineBridge GovernanceHub 注入 | P0 | S | 無 | 🔴 |
| T1.02 | acquire_lease() 改為 fail-closed | P0 | S | 無 | 🔴 |
| T1.03 | is_authorized() exception handler 改為 fail-closed | P0 | S | 無 | 🔴 |
| T1.04 | AuditPipeline 連接 SM 回調 + 持久化啟用 | P1 | M | T1.01 | 🔴 |
| T1.05 | Incident → SM 自動級聯啟用 | P1 | M | T1.01 | 🔴 |
| T1.06 | TTL Enforcer daemon 啟動 | P1 | S | T1.01 | 🔴 |
| T1.07 | H0 Gate fail-closed 強化 | P2 | S | T1.03 | 🔴 |
| T1.08 | Paper→Live Gate 閾值對齊 | P2 | S | 無 | 🔴 |
| T1.09 | Phase 1 集成測試（E2E governance pipeline） | P0 | L | T1.01-T1.03 | 🔴 |

---

## 任務詳情

---

### T1.01 — PipelineBridge GovernanceHub 注入

**優先級：** P0（最高）
**工作量：** S（0.5 session）
**依賴：** 無
**對應 GAP：** GAP-C1a

#### 問題描述

`PipelineBridge` 在 `phase2_strategy_routes.py:193-201` 初始化時未注入 `GovernanceHub`。
雖然 `PipelineBridge.set_governance_hub()` 方法已存在（`pipeline_bridge.py:125-127`），但從未被調用。
結果：PipelineBridge 的 `self._governance_hub` 始終為 `None`，`on_tick()` 中的治理檢查為 no-op。

#### 修改目標

在 `phase2_strategy_routes.py` 中 `PIPELINE_BRIDGE` 初始化後，注入已在 `paper_trading_routes.py` 中實例化的 `GOV_HUB`。

#### 具體修改

**文件 1：** `app/phase2_strategy_routes.py`
- **位置：** 第 201 行之後（`PIPELINE_BRIDGE` 創建之後）
- **動作：** 添加 GovernanceHub 注入
```python
# 在 PIPELINE_BRIDGE = PipelineBridge(...) 之後添加：
from .paper_trading_routes import GOV_HUB as _GOV_HUB_REF  # noqa: E402
if _GOV_HUB_REF is not None:
    PIPELINE_BRIDGE.set_governance_hub(_GOV_HUB_REF)
    logger.info("GovernanceHub injected into PipelineBridge")
```

#### 驗收標準

1. `PIPELINE_BRIDGE._governance_hub` 不為 `None`
2. `pipeline_bridge.py:278-290` 中的 `is_authorized()` 檢查生效
3. 現有單元測試全部通過（`pytest tests/ -x`）
4. 新增測試：`test_pipeline_bridge_governance_injection`

#### 角色分配

| 步驟 | 角色 | 動作 |
|------|------|------|
| 1 | FA | 確認注入方式不引入循環依賴；設計測試接口 |
| 2 | E1b | 實現代碼修改 |
| 3 | E2 | Code Review（循環依賴、啟動順序） |
| 4 | E4 | 執行測試 + 新增注入驗證測試 |

---

### T1.02 — acquire_lease() 改為 fail-closed

**優先級：** P0
**工作量：** S（0.5 session）
**依賴：** 無
**對應 GAP：** GAP-C1b

#### 問題描述

`paper_trading_engine.py:907-916`：`acquire_lease()` 返回 `None` 時，訂單繼續執行（僅跳過 lease 記錄）。
治理規範要求：**無 Decision Lease 不可下單**（DOC-01 §5.4, SM-02）。

#### 現有代碼（問題段）

```python
# paper_trading_engine.py:907-916
if self._governance_hub:
    try:
        lease_id = self._governance_hub.acquire_lease(order["order_id"], scope={"symbol": symbol, "side": side})
        if lease_id:
            order["governance_lease_id"] = lease_id
            self._audit(state, "governance_lease_acquired", f"{order['order_id']} lease={lease_id}")
    except Exception:
        import logging as _log
        _log.warning("Governance lease acquisition failed (non-fatal)")
```

#### 修改目標

`acquire_lease()` 返回 `None` 或拋出異常時，訂單必須被拒絕（fail-closed）。

#### 具體修改

**文件 1：** `app/paper_trading_engine.py`
- **位置：** 第 907-916 行
- **動作：** 改為 fail-closed

```python
# paper_trading_engine.py — acquire_lease fail-closed
if self._governance_hub:
    try:
        lease_id = self._governance_hub.acquire_lease(
            order["order_id"], scope={"symbol": symbol, "side": side}
        )
        if not lease_id:
            _transition_order(order, ORDER_STATE_REJECTED)
            order["reject_reason"] = "governance_lease_denied"
            state["orders"].append(order)
            result["order"] = order
            result["rejected_reason"] = "governance_lease_denied"
            self._audit(state, "order_governance_lease_denied",
                        f"{symbol} {side} lease denied — fail-closed")
            return state
        order["governance_lease_id"] = lease_id
        self._audit(state, "governance_lease_acquired",
                    f"{order['order_id']} lease={lease_id}")
    except Exception as exc:
        _transition_order(order, ORDER_STATE_REJECTED)
        order["reject_reason"] = "governance_lease_error"
        state["orders"].append(order)
        result["order"] = order
        result["rejected_reason"] = "governance_lease_error"
        self._audit(state, "order_governance_lease_error",
                    f"{symbol} {side} lease error: {exc} — fail-closed")
        return state
```

**文件 2：** `app/pipeline_bridge.py`（如有 acquire_lease 調用也需同步修改）
- 驗證 PipelineBridge 中是否有類似 non-fatal 模式，同步修改

#### 驗收標準

1. 無 GovernanceHub 時：訂單正常通過（向後兼容）
2. 有 GovernanceHub 且 `acquire_lease()` 返回 `None`：訂單 REJECTED，reason=`governance_lease_denied`
3. 有 GovernanceHub 且 `acquire_lease()` 拋出異常：訂單 REJECTED，reason=`governance_lease_error`
4. 審計日誌記錄拒絕事件
5. 現有測試通過 + 新增 3 個測試（deny/error/success）

#### 角色分配

| 步驟 | 角色 | 動作 |
|------|------|------|
| 1 | E1b | 實現 fail-closed 修改 |
| 2 | E3 | 安全審核（確認無繞過路徑） |
| 3 | E2 | Code Review |
| 4 | E4 | 單元測試 + 回歸測試 |

---

### T1.03 — is_authorized() exception handler 改為 fail-closed

**優先級：** P0
**工作量：** S（0.5 session）
**依賴：** 無
**對應 GAP：** GAP-C1c, GAP-C1d

#### 問題描述

三處 `is_authorized()` 的 exception handler 為 `logger.warning("... (non-fatal)")`，意味著 GovernanceHub 內部異常時訂單仍可通過。

#### 受影響位置

| 文件 | 行號 | 正常路徑 | 異常路徑（問題） |
|------|------|---------|----------------|
| `paper_trading_engine.py` | 853-854 | ✅ 拒絕訂單 | ❌ warning + 繼續 |
| `risk_manager.py` | 581-582 | ✅ return False | ❌ warning + 繼續 |
| `pipeline_bridge.py` | 288-289 | ✅ skip intent | ❌ warning + 繼續 |

#### 修改目標

所有 exception handler 改為 fail-closed：異常時與正常 `False` 返回走相同拒絕路徑。

#### 具體修改

**文件 1：** `app/paper_trading_engine.py:853-854`
```python
# 原：except Exception: logger.warning("... (non-fatal)")
# 改為：
except Exception as exc:
    _transition_order(order, ORDER_STATE_REJECTED)
    order["reject_reason"] = "governance_check_error"
    state["orders"].append(order)
    result["order"] = order
    result["rejected_reason"] = "governance_check_error"
    self._audit(state, "order_governance_error",
                f"{symbol} {side} governance error: {exc} — fail-closed")
    return state
```

**文件 2：** `app/risk_manager.py:581-582`
```python
# 原：except Exception: logger.warning("... (non-fatal)")
# 改為：
except Exception as exc:
    logger.error("Governance is_authorized error — fail-closed: %s", exc)
    return False, "governance_check_error"
```

**文件 3：** `app/pipeline_bridge.py:288-289`
```python
# 原：except Exception: logger.warning("... (non-fatal)")
# 改為：
except Exception as exc:
    logger.error("Governance is_authorized error — fail-closed: %s", exc)
    with self._lock:
        self._stats["intents_rejected"] += 1
    continue
```

#### 驗收標準

1. 三處 exception handler 均改為 fail-closed
2. 異常時行為與 `is_authorized()` 返回 `False` 一致
3. 錯誤以 `logger.error` 記錄（非 warning）
4. 審計日誌包含異常詳情
5. 現有測試通過 + 每處新增 1 個異常測試

#### 角色分配

| 步驟 | 角色 | 動作 |
|------|------|------|
| 1 | E1b | 修改三處 exception handler |
| 2 | E3 | 安全審核：確認零繞過路徑 |
| 3 | E2 | Code Review |
| 4 | E4 | 單元測試（注入異常模擬） |

---

### T1.04 — AuditPipeline 連接 SM 回調 + 持久化啟用

**優先級：** P1
**工作量：** M（1 session）
**依賴：** T1.01 完成
**對應 GAP：** GAP-C4（原 GAP-H3）

#### 問題描述

`audit_persistence.py` 提供了完整的 `AuditPipeline` 類（含 `make_callback(source)` 方法），可生成回調函數供 SM 使用。
但 `paper_trading_routes.py` 初始化 `GovernanceHub` 時未創建 `AuditPipeline`，SM 的 audit 回調僅寫入記憶體 `_audit_log` 列表。

#### 具體修改

**文件 1：** `app/paper_trading_routes.py`
- 在 `GOV_HUB` 初始化區塊中添加 `AuditPipeline` 創建和連接
- `AuditPipeline.make_callback("governance_hub")` 傳入 GovernanceHub
- 確保 GovernanceHub 在初始化 SM 時將 audit_callback 傳遞給各 SM

**文件 2：** `app/governance_hub.py`
- 確認 `_ensure_initialized()` 中各 SM 的 `audit_callback` 參數被正確設置
- 如需要，添加 `set_audit_pipeline(pipeline)` 方法

#### 驗收標準

1. SM 狀態轉換寫入磁碟 JSON Lines 文件
2. 審計文件位於 `runtime/governance_audit/` 目錄
3. 重啟後審計記錄可讀取（`AuditFileReader.query()`）
4. 日誌包含 `transition_id`, `trigger_event_id`, `approved_by`
5. 文件自動輪轉（每日 / 50MB）

#### 角色分配

| 步驟 | 角色 | 動作 |
|------|------|------|
| 1 | FA | 設計 AuditPipeline 整合架構（回調鏈） |
| 2 | E1b | 實現連接代碼 |
| 3 | E2 | Code Review（I/O 性能、flush 策略） |
| 4 | E4 | 驗證持久化 + 讀取測試 |

---

### T1.05 — Incident → SM 自動級聯啟用

**優先級：** P1
**工作量：** M（1 session）
**依賴：** T1.01 完成
**對應 GAP：** GAP-C3（原 GAP-H4）

#### 問題描述

`incident_event_model.py:IncidentPolicy` 接受回調：`on_auth_action`, `on_risk_action`, `on_operator_alert`。
`governance_hub.py` 有級聯方法：`_on_risk_escalation()`, `_on_reconciliation_mismatch()`, `_on_auth_frozen()`。
但 `IncidentPolicy` 未在主流程中實例化，回調未連接。

#### 具體修改

**文件 1：** `app/paper_trading_routes.py` 或 `app/governance_hub.py`
- 在 GovernanceHub 初始化後創建 `IncidentPolicy` 實例
- 連接回調：
  - `on_auth_action` → GovernanceHub 的 auth freeze/restrict 方法
  - `on_risk_action` → GovernanceHub 的 risk escalation 方法
  - `on_operator_alert` → 日誌 + 未來擴展到通知系統

**文件 2：** `app/reconciliation_engine.py`（如未連接）
- 確保對賬發現差異時調用 `IncidentPolicy.process_event()`

#### 驗收標準

1. CRITICAL_INCIDENT → Auth FROZEN + Risk CIRCUIT_BREAKER + 所有 Lease 撤銷
2. INCIDENT → Auth FROZEN + Risk DEFENSIVE
3. NEAR_MISS → Auth RESTRICTED + Risk REDUCED
4. 對賬 MISMATCH_MAJOR → 自動觸發 INCIDENT 事件
5. 級聯審計完整記錄

#### 角色分配

| 步驟 | 角色 | 動作 |
|------|------|------|
| 1 | FA | 設計事件→級聯映射表 |
| 2 | E1b | 實現連接和級聯邏輯 |
| 3 | E3 | 安全審核（確認無死鎖、無誤觸發） |
| 4 | E4 | 級聯場景測試（5 個嚴重度級別） |

---

### T1.06 — TTL Enforcer daemon 啟動

**優先級：** P1
**工作量：** S（0.5 session）
**依賴：** T1.01 完成
**對應 GAP：** GAP-C2（原 GAP-M8）

#### 問題描述

`ttl_enforcer.py:TTLEnforcer` 有 `start_daemon_sweep()` 方法（5 秒間隔掃描過期條目），但未在主流程中啟動。過期的 Lease/Auth 不會被自動清理。

#### 具體修改

**文件 1：** `app/paper_trading_routes.py` 或 `app/governance_hub.py`
- 在 GovernanceHub 初始化後，啟動 TTL Enforcer daemon
- 連接 expiry_callback 到 GovernanceHub（過期 Lease 自動撤銷、過期 Auth 自動凍結）

#### 驗收標準

1. TTL Enforcer daemon 在 GovernanceHub 啟動後自動運行
2. Decision Lease ACTIVE 超過 30 秒自動過期
3. Authorization PENDING_APPROVAL 超過 24 小時自動拒絕
4. 過期事件記入審計日誌
5. daemon 在 shutdown 時正確停止（`stop_daemon_sweep()`）

#### 角色分配

| 步驟 | 角色 | 動作 |
|------|------|------|
| 1 | E1b | 啟動 daemon + 連接回調 |
| 2 | E2 | Code Review（線程安全、shutdown） |
| 3 | E4 | TTL 過期場景測試 |

---

### T1.07 — H0 Gate fail-closed 強化

**優先級：** P2
**工作量：** S（0.5 session）
**依賴：** T1.03 完成
**對應 GAP：** GAP-C5（原 GAP-M4）

#### 問題描述

H0 Gate（系統健康檢查）部分檢查項為 warning-only，未阻止交易。需逐項確認並改為 fail-closed。

#### 具體修改

- 審查 `governance_hub.py` 中 H0 相關檢查
- 確認所有 health check 失敗時 `is_authorized()` 返回 `False`
- 特別關注：初始化失敗、SM 不可用、模式不匹配等邊緣情況

#### 驗收標準

1. GovernanceHub 未初始化 → `is_authorized()` 返回 `False`（已實現，確認）
2. 任何 SM 不可用 → 返回 `False`
3. mode == FROZEN → 返回 `False`（已實現）
4. 新增邊緣情況測試

#### 角色分配

| 步驟 | 角色 | 動作 |
|------|------|------|
| 1 | CC | 合規檢查：逐項對照 DOC-02 |
| 2 | E1b | 修改不合規項 |
| 3 | E4 | 邊緣情況測試 |

---

### T1.08 — Paper→Live Gate 閾值對齊

**優先級：** P2
**工作量：** S（0.5 session）
**依賴：** 無
**對應 GAP：** GAP-C6（原 GAP-H5）

#### 問題描述

`paper_live_gate.py:PaperLiveGateConfig` 定義了閾值，需確認與治理文件（EX-05, DOC-08）一致。

#### 當前閾值（代碼）

| 參數 | 代碼值 | 治理文件要求 | 一致？ |
|------|--------|-------------|--------|
| min_paper_duration_weeks | 4 | 待確認 | ? |
| min_trades | 500 | 待確認 | ? |
| min_win_rate_percent | 30.0 | 待確認 | ? |
| min_sharpe_ratio | 0.5 | 待確認 | ? |
| min_profit_factor | 1.2 | 待確認 | ? |
| min_audit_trail_completeness | 99.0% | 待確認 | ? |
| max_reconciliation_mismatch | 0.1% | 待確認 | ? |
| max_consecutive_losses | 10 | 待確認 | ? |

#### 具體修改

**文件 1：** 讀取 `01_source_documents/` 中 EX-05 和 DOC-08 的相關章節
**文件 2：** 比對並修正 `paper_live_gate.py` 中的 `PaperLiveGateConfig` 默認值

#### 驗收標準

1. 每個閾值有治理文件條文出處
2. 不一致項已修正
3. 修正記錄在代碼註釋中（引用文件編號和章節）

#### 角色分配

| 步驟 | 角色 | 動作 |
|------|------|------|
| 1 | CC | 讀取治理文件，提取閾值要求 |
| 2 | R1 | 交叉驗證閾值一致性 |
| 3 | E1b | 修改不一致項 |
| 4 | E4 | 閾值邊界測試 |

---

### T1.09 — Phase 1 集成測試（E2E governance pipeline）

**優先級：** P0
**工作量：** L（1-2 sessions）
**依賴：** T1.01, T1.02, T1.03 完成
**對應 GAP：** 測試缺口

#### 問題描述

現有集成測試僅 8 個（`test_integration_governance.py`），缺少端到端治理管線測試。Phase 1 的修改（fail-closed）必須有 E2E 測試驗證。

#### 新增測試用例

| 測試 ID | 測試場景 | 預期結果 |
|---------|---------|---------|
| IT-01 | 正常流程：Auth ACTIVE → Lease 獲取 → Risk OK → 訂單通過 | 訂單 FILLED |
| IT-02 | Auth 未激活 → 下單 | 訂單 REJECTED (governance_not_authorized) |
| IT-03 | Auth ACTIVE 但 Lease 獲取失敗 → 下單 | 訂單 REJECTED (governance_lease_denied) |
| IT-04 | 下單中途 Risk 升級到 CIRCUIT_BREAKER | Auth FROZEN + Lease 撤銷 + 訂單 ABORTED |
| IT-05 | GovernanceHub `is_authorized()` 拋出異常 | 訂單 REJECTED (governance_check_error) |
| IT-06 | PipelineBridge 中 GovernanceHub 拒絕 intent | Intent 被 skip，stats 計數 +1 |
| IT-07 | 對賬發現 MISMATCH_MAJOR → 級聯 | Risk 升級 + Auth FROZEN |
| IT-08 | Lease TTL 過期 → 自動清理 | Lease 標記 EXPIRED，相關訂單不可續用 |
| IT-09 | CRITICAL_INCIDENT → 全級聯 | Auth FROZEN + Risk CB + Lease revoke_all |
| IT-10 | 恢復流程：FROZEN → recovery_approval → RESTRICTED | 需 Operator 審批 + 觀察期 |

#### 角色分配

| 步驟 | 角色 | 動作 |
|------|------|------|
| 1 | E4 | 設計 10 個 E2E 測試用例 |
| 2 | E4 | 實現測試（在 `test_integration_governance.py` 中新增） |
| 3 | E2 | Review 測試覆蓋率 |
| 4 | PM | 驗收測試全通過 |

---

## 工作流編排

### Sprint 1（T1.01 + T1.02 + T1.03 — 並行，P0）

```
         ┌─ T1.01 PipelineBridge 注入 ─┐
         │   FA → E1b → E2 → E4        │
         │                               │
START ───┼─ T1.02 Lease fail-closed ────┼──→ T1.09 集成測試
         │   E1b → E3 → E2 → E4        │    E4 → E2 → PM 驗收
         │                               │
         └─ T1.03 Auth exception fix ───┘
             E1b → E3 → E2 → E4
```

**三項可完全並行**，因為修改文件不重疊：
- T1.01：`phase2_strategy_routes.py`
- T1.02：`paper_trading_engine.py`（acquire_lease 段）
- T1.03：`paper_trading_engine.py`（is_authorized 段）+ `risk_manager.py` + `pipeline_bridge.py`

⚠️ T1.02 和 T1.03 在 `paper_trading_engine.py` 中有小重疊（相鄰代碼段），但修改區域不同，可由同一 Worker 處理。

### Sprint 2（T1.04 + T1.05 + T1.06 — 並行，P1）

```
         ┌─ T1.04 AuditPipeline 持久化 ─┐
         │   FA → E1b → E2 → E4          │
         │                                 │
T1.01 ───┼─ T1.05 Incident 級聯 ─────────┼──→ Sprint 3
完成     │   FA → E1b → E3 → E4          │
         │                                 │
         └─ T1.06 TTL Enforcer daemon ───┘
             E1b → E2 → E4
```

### Sprint 3（T1.07 + T1.08 — 並行，P2）

```
         ┌─ T1.07 H0 Gate 強化 ──────┐
         │   CC → E1b → E4            │
T1.03 ───┤                            ├──→ PM 最終驗收
完成     └─ T1.08 Paper→Live 對齊 ───┘
             CC → R1 → E1b → E4
```

---

## Worker 對話分配建議

### 最佳方案：5 個 Worker 對話

| Worker 對話 | 角色 | 負責任務 | 理由 |
|-------------|------|---------|------|
| Worker-FA | FA（架構師） | T1.01 設計、T1.04 設計、T1.05 設計 | 統一架構視角 |
| Worker-E1b-A | E1b（修改工程師 A） | T1.01 + T1.06 | PipelineBridge 注入 + TTL 啟動（同一啟動區域） |
| Worker-E1b-B | E1b（修改工程師 B） | T1.02 + T1.03 | PE/RM/PB fail-closed（同一錯誤處理模式） |
| Worker-E1b-C | E1b（修改工程師 C） | T1.04 + T1.05 | Audit + Incident 持久化（同一接入模式） |
| Worker-E4 | E4（測試工程師） | T1.09 + 所有任務回歸 | 統一測試視角 |

### 最小方案：3 個 Worker 對話

| Worker 對話 | 角色 | 負責任務 |
|-------------|------|---------|
| Worker-A | FA + E1b | T1.01 → T1.04 → T1.05 → T1.06（架構 + 接入） |
| Worker-B | E1b + E3 | T1.02 → T1.03 → T1.07（fail-closed + 安全） |
| Worker-C | E4 + CC + R1 | T1.09 + T1.08 + 所有回歸測試 |

---

## 風險與緩解

| 風險 | 影響 | 緩解 |
|------|------|------|
| T1.01 循環依賴（phase2_strategy_routes ← paper_trading_routes） | 啟動失敗 | FA 預先驗證 import 順序 |
| T1.02 fail-closed 導致所有訂單被拒（Lease SM 未正確初始化） | 系統停擺 | T1.09 IT-01 驗證正常路徑 |
| T1.03 修改多文件 exception handler，遺漏某處 | 安全漏洞 | E3 安全審核 + `grep -r "non-fatal"` |
| T1.05 Incident 級聯誤觸發 | 交易中斷 | E3 審核觸發閾值 + 觀察模式先行 |

---

## Phase 1 完成標準（PM 驗收清單）

- [ ] T1.09 全部 10 個集成測試通過
- [ ] `grep -r "non-fatal" app/` 返回 0 結果
- [ ] PipelineBridge 治理檢查生效（IT-06 通過）
- [ ] Lease 失敗 → 訂單拒絕（IT-03 通過）
- [ ] Risk CIRCUIT_BREAKER → 全級聯（IT-04 通過）
- [ ] TTL Enforcer daemon 運行中
- [ ] 審計日誌持久化到磁碟
- [ ] 現有 1,707 個測試全部通過
- [ ] Operator 最終確認

---

*Phase 1 任務書由 PM（via Cowork PM）於 2026-03-30 產出*
*基於代碼逐行驗證，修正了 Phase 0 審計報告中的偏差*
