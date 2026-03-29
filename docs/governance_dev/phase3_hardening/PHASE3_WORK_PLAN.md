# Phase 3 完整工作安排 — 從 72% 到可安全交易
# Phase 3 Work Plan — From 72% Compliance to Safe Trading Readiness

| 欄位 | 值 |
|------|-----|
| **文件 ID** | PHASE3-PLAN-2026-03-30 |
| **制定角色** | PM Project Manager |
| **日期** | 2026-03-30 |
| **輸入** | PM_FA_FULL_COMPLIANCE_AUDIT.md（376 條要求審核結果） |
| **目標** | 合規率從 72% → 95%+，解決所有 Critical/High Gap，達到安全交易準備 |

---

## 一、Phase 3 總覽 / Overview

Phase 3 分為 3 個 Sprint，每個 Sprint 有明確的交付物和退出標準。

```
Sprint 1 (3a)：安全關鍵修復     ← 2-3 sessions，不做這個什麼都別談
Sprint 2 (3b)：操作護欄補全     ← 4-5 sessions，讓系統能在真實環境運行
Sprint 3 (3c)：端對端驗證       ← 2-3 sessions，確認所有組件協同工作
                                   ─────────────────────────
                                   總計：8-11 sessions
```

---

## 二、Sprint 1 (3a)：安全關鍵修復

**目標：** 修復所有阻止安全交易的 Critical Gap
**預計：** 2-3 個 session
**優先級：** 🔴 P0 — 阻塞一切後續工作

---

### T3.01 — SM-03 OMS 狀態機補全

**Gap 來源：** GAP-SM-03-01~07（PM+FA 審核新發現）
**角色：** E2 Core Engineer
**模型：** Opus
**工作量：** 1 session

**具體任務：**

```
1. 新增 3 個狀態到 OrderState enum：
   - CANCEL_REQUESTED  （撤單已發出，等待確認）
   - FAILED            （執行失敗，不可重試）
   - ABORTED           （Operator/上游撤銷）

2. 補全轉換規則（當前缺失的）：
   - SUBMITTED → CANCEL_REQUESTED
   - SUBMITTED → FAILED
   - PARTIALLY_FILLED → CANCEL_REQUESTED
   - PARTIALLY_FILLED → RECONCILING
   - PARTIALLY_FILLED → FAILED
   - PARTIALLY_FILLED → ABORTED
   - CANCEL_REQUESTED → CANCELLED
   - CANCEL_REQUESTED → PARTIALLY_FILLED（撤單失敗繼續成交）
   - CANCEL_REQUESTED → RECONCILING
   - CANCEL_REQUESTED → FAILED
   - FILLED → RECONCILING（★ 強制對賬閘門）
   - RECONCILING → FILLED
   - RECONCILING → CANCELLED
   - RECONCILING → FAILED
   - RECONCILING → COMPLETED
   - FAILED → RECONCILING
   - FAILED → COMPLETED
   - ABORTED → COMPLETED
   - CANCELLED → COMPLETED

3. 強制規則：
   - FILLED → COMPLETED 列入 FORBIDDEN_TRANSITIONS（必須先過 RECONCILING）
   - TERMINAL_STATES 新增 ABORTED

4. 拼寫統一：CANCELED → CANCELLED（與 SM-03 規範一致）

5. 測試要求：
   - 11 狀態全覆蓋
   - 所有允許轉換正確
   - 所有禁止轉換拒絕
   - 終態不可逆
   - 審計欄位完整
```

**驗收標準：**
- [ ] OrderState enum 包含 11 個狀態
- [ ] 所有 SM-03 §6-7 轉換規則已實現
- [ ] FILLED → COMPLETED 被禁止（必須過 RECONCILING）
- [ ] 新增測試 ≥ 30 cases，全部通過
- [ ] 現有 OMS 測試向後相容（更新斷言）

---

### T3.02 — EX-02 冪等保護機制

**Gap 來源：** GAP-EX-02-03（Critical）
**角色：** E2 Core Engineer
**模型：** Sonnet
**工作量：** 0.5 session（可與 T3.01 同 session）

**具體任務：**

```
1. 在 OMS 層新增冪等保護：
   class IdempotencyGuard:
       - execution_id_cache: dict[str, OrderState]  # TTL 24h, max 500
       - check_duplicate(execution_id: str) -> bool
       - register(execution_id: str, state: OrderState)
       - hmac 簽名防篡改

2. 在 pipeline_bridge.py 的訂單提交入口加入：
   if idempotency_guard.check_duplicate(order.execution_id):
       return DuplicateOrderRejected(...)

3. 測試：
   - 重複 execution_id 被拒
   - 不同 execution_id 通過
   - TTL 過期後可重用
   - 併發安全（threading.Lock）
```

**驗收標準：**
- [ ] IdempotencyGuard 類實現
- [ ] pipeline_bridge 入口整合
- [ ] ≥ 8 tests 通過

---

### T3.03 — EX-02 執行風格與意圖枚舉

**Gap 來源：** GAP-EX-02-01, GAP-EX-02-02（High）
**角色：** E2 Core Engineer
**模型：** Sonnet
**工作量：** 0.5 session

**具體任務：**

```
1. 新增 ExecutionIntentType enum：
   NEW_ENTRY, ADD_POSITION, REDUCE_POSITION, FULL_EXIT,
   CANCEL_ORDER, MODIFY_ORDER, PROTECTIVE_ACTION

2. 新增 ExecutionStyle enum：
   PASSIVE_LIMIT, AGGRESSIVE_LIMIT, MARKET_IF_REQUIRED,
   SPLIT_EXECUTION, REDUCE_ONLY

3. 在 OrderObject / ExecutionRequest 中加入：
   - intent_type: ExecutionIntentType
   - execution_style: ExecutionStyle

4. 在 pipeline_bridge / paper_trading_engine 中使用

5. 測試：枚舉正確，訂單攜帶意圖/風格
```

**驗收標準：**
- [ ] 兩個枚舉定義完整
- [ ] 訂單物件包含這兩個欄位
- [ ] ≥ 10 tests 通過

---

### Sprint 1 退出標準

- [ ] SM-03 全部 11 狀態 + 完整轉換 + 測試通過
- [ ] 冪等保護機制上線
- [ ] 執行風格/意圖枚舉整合
- [ ] 所有新增代碼有對應測試
- [ ] 現有測試無回歸（或已更新斷言）
- [ ] git commit + push 完成

---

## 三、Sprint 2 (3b)：操作護欄補全

**目標：** 補全系統在真實環境運行所需的護欄
**預計：** 4-5 個 session
**優先級：** 🟡 P1 — Phase 3 必修

---

### T3.04 — EX-03 Operator Action 正式物件

**Gap 來源：** GAP-EX-03-01~04（High）
**角色：** E2 Core Engineer
**模型：** Sonnet
**工作量：** 1 session

**具體任務：**

```
1. 新增 operator_action.py：

   class OperatorActionType(str, Enum):
       SYSTEM_MODE_CHANGE = "system_mode_change"
       AUTHORIZATION_CHANGE = "authorization_change"
       LEASE_FREEZE = "lease_freeze"
       LEASE_REVOKE = "lease_revoke"
       RISK_REDUCE_ONLY = "risk_reduce_only"
       EMERGENCY_STOP = "emergency_stop"
       MANUAL_REVIEW = "manual_review"
       RECOVERY_APPROVAL = "recovery_approval"
       CHANGE_REQUEST_APPROVAL = "change_request_approval"
       OPERATOR_POSITION_ACTION = "operator_position_action"

   @dataclass
   class OperatorAction:
       action_id: str           # UUID
       action_type: OperatorActionType
       target_object_type: str
       target_object_id: str
       initiated_by: str        # "operator"
       initiated_at_ms: int     # UTC ms
       reason_codes: list[str]
       operator_comment: str
       requires_approval: bool
       audit_event_ref: str

2. 新增 operator_action_routes.py：
   - POST /operator/action — 提交操作（封裝到 OperatorAction）
   - GET /operator/actions — 查詢操作歷史
   - 每個操作走 change_audit_log 記錄

3. 在 main.py 註冊路由

4. 測試：10 種類型覆蓋 + 審計記錄驗證
```

**驗收標準：**
- [ ] 10 種 OperatorActionType 完整
- [ ] OperatorAction 欄位與 EX-03 §18 一致
- [ ] API 路由可用
- [ ] 審計日誌記錄正確
- [ ] ≥ 20 tests 通過

---

### T3.05 — EX-01 WebSocket 斷連保護

**Gap 來源：** GAP-EX-01-01（High）
**角色：** E2 Core Engineer
**模型：** Sonnet
**工作量：** 0.5 session

**具體任務：**

```
1. 在 bybit_public_ws_listener.py 或 market_data_dispatcher.py：
   - 追蹤 last_ws_heartbeat_ms
   - 如果 now - last_ws_heartbeat > 30_000ms：
     → 觸發 risk_governor.escalate(HEALTH_DEGRADED)
     → 觸發 protective_order_manager.place_emergency_stops()
   - WS 恢復後：
     → 移除交易所端止損
     → 恢復本地監控

2. 整合到 health_state 檢查

3. 測試：模擬斷連 → 驗證止損觸發 + 風控升級
```

---

### T3.06 — EX-07 事件日曆系統

**Gap 來源：** GAP-EX-07-01~03（Critical）
**角色：** AI-E + E2
**模型：** Sonnet
**工作量：** 1 session

**具體任務：**

```
1. 新增 event_calendar.py：

   class MarketEventType(str, Enum):
       TOKEN_UNLOCK = "token_unlock"
       NEW_LISTING = "new_listing"
       PROTOCOL_UPGRADE = "protocol_upgrade"
       FOMC_DECISION = "fomc_decision"
       CPI_RELEASE = "cpi_release"
       NFP_RELEASE = "nfp_release"
       EXCHANGE_MAINTENANCE = "exchange_maintenance"

   @dataclass
   class MarketEvent:
       event_id: str
       event_type: MarketEventType
       symbol_affected: str | None  # None = 全市場
       expected_at_ms: int
       cognitive_level: str  # "FACT" or "INFERENCE"
       impact_assessment: str
       guardian_action: str  # "tighten_stops" / "reduce_only" / "pause"

2. EventCalendarManager：
   - load_events() — 從配置/API 載入
   - check_upcoming(window_minutes=60) → list[MarketEvent]
   - trigger_guardian_response(event) → 通知 risk_governor

3. 整合到 market_data_dispatcher 的定期檢查

4. 測試：FOMC 事件 → Guardian 收緊 → 風控升級
```

---

### T3.07 — EX-06 衝突仲裁層

**Gap 來源：** GAP-EX-06-01~03（Critical）
**角色：** AI-E
**模型：** Sonnet
**工作量：** 1 session

**具體任務：**

```
1. 在 multi_agent_framework.py 中新增：

   class ConflictArbitrator:
       PRIORITY_ORDER = [
           AgentRole.GUARDIAN,   # 最高 — 永遠贏
           AgentRole.EXECUTOR,   # 執行中訂單不可被 Strategist 覆蓋
           AgentRole.STRATEGIST, # 策略建議
           AgentRole.ANALYST,    # 學習建議
           AgentRole.SCOUT,      # 情報
       ]

       def arbitrate(self, messages: list[AgentMessage]) -> AgentMessage:
           # Guardian 否決 Strategist 的正式機制
           ...

2. Strategist P0/P1 預提交驗證：
   - 在 Strategist 產生 trade_intent 前檢查是否違反 P0/P1
   - 違反 → 拒絕 + 審計記錄

3. Executor 4 條禁令運行時檢查：
   - 不可修改策略邏輯
   - 不可調整風控參數
   - 不可跳過 Guardian 審核
   - 不可自行決定重試次數

4. 測試：Guardian 否決 Strategist + P0 違規拒絕 + Executor 禁令
```

---

### T3.08 — EX-01 每日損失熔斷 + EX-04 對賬→風控聯動

**Gap 來源：** GAP-EX-01-04, GAP-EX-04-01/03（High/Medium）
**角色：** E2 Core Engineer
**模型：** Sonnet
**工作量：** 0.5 session

**具體任務：**

```
1. risk_manager.py 或 risk_governor 中新增：
   - check_daily_loss_limit(net_daily_pnl, p1_daily_limit)
   - 超過 → 觸發 CIRCUIT_BREAKER

2. reconciliation_engine → risk_governor 聯動：
   - FATAL 差異 → 自動 escalate(CIRCUIT_BREAKER)
   - CRITICAL 差異 → 自動 escalate(DEFENSIVE)
   - MISMATCH_DETECTED → escalate(CAUTIOUS)

3. 測試：日損超限 → 熔斷 + 對賬差異 → 風控升級
```

---

### Sprint 2 退出標準

- [ ] T3.04 OperatorAction 10 種類型 + API + 審計
- [ ] T3.05 WS 斷連 30s 保護
- [ ] T3.06 事件日曆至少支持 7 種事件
- [ ] T3.07 衝突仲裁 + P0/P1 預驗證 + Executor 禁令
- [ ] T3.08 日損熔斷 + 對賬聯動
- [ ] 所有新代碼測試通過
- [ ] git commit + push 完成

---

## 四、Sprint 3 (3c)：端對端驗證

**目標：** 確認所有組件協同工作，產出合規簽收報告
**預計：** 2-3 個 session
**優先級：** 🟢 P2 — Phase 3 收尾

---

### T3.09 — 端對端整合測試

**角色：** E2 + AI-E
**模型：** Sonnet
**工作量：** 1 session

**具體任務：**

```
新增 test_integration_e2e.py，覆蓋以下場景：

場景 1：完整交易生命週期
  授權 ACTIVE → 風控 NORMAL → 租約 ACTIVE → OMS PENDING→APPROVED→
  SUBMITTED→FILLED→RECONCILING→COMPLETED → 審計記錄完整

場景 2：風控熔斷級聯
  日損超限 → CIRCUIT_BREAKER → 授權 FROZEN → 所有租約 EXPIRED →
  OMS 拒絕新訂單 → Operator 介入 → 逐級恢復

場景 3：對賬差異處理
  Paper vs Demo 持倉不一致 → MISMATCH_DETECTED → 風控升級 →
  reduce_only 模式 → Operator 審批恢復

場景 4：WS 斷連恢復
  WS 斷開 >30s → 緊急止損 → 風控 DEFENSIVE →
  WS 恢復 → 移除交易所止損 → Operator 批准降級

場景 5：事件日曆觸發
  FOMC 事件 → Guardian 收緊 → reduce_only → 事件過後 → Operator 恢復

場景 6：冪等保護
  重複 execution_id → 第二次被拒 → 審計記錄 → 無重複訂單

場景 7：Operator Action 全流程
  Operator 提交 emergency_stop → OperatorAction 記錄 →
  風控 CIRCUIT_BREAKER → 所有倉位平倉信號

場景 8：多 Agent 衝突
  Strategist 提議新倉 → Guardian 否決（P0 違規）→ 審計記錄
```

---

### T3.10 — PM 合規簽收報告

**角色：** PM + R1
**模型：** Opus
**工作量：** 1 session

**具體任務：**

```
1. 重新執行 PM_FA_FULL_COMPLIANCE_AUDIT 中所有 Gap 的驗證
2. 逐條確認：
   - Tier 1 Gap（4 項）全部關閉
   - Tier 2 Gap（6 項）全部關閉
   - 整體合規率從 72% 提升到目標值
3. 產出 PHASE3_COMPLETION_REPORT.md
4. 列出 Phase 4（能力激活）的前置條件
5. 更新合規矩陣最終版
```

---

### T3.11 — test_api_contract 斷言更新

**角色：** CC
**模型：** Sonnet
**工作量：** 0.5 session

**具體任務：**

```
1. 更新 test_api_contract.py 中路由數量斷言（新增路由後）
2. 修復 test_risk_governor sleep-based 超時測試
3. 修復 test_market_data 導入問題
4. 確保全量測試套件 0 failure
```

---

### Sprint 3 退出標準

- [ ] 8 個端對端場景全部通過
- [ ] PM 合規簽收報告完成
- [ ] 全量測試 0 failure, 0 error
- [ ] 合規率 ≥ 92%
- [ ] Operator 審閱並批准 Phase 3 完成

---

## 五、依賴圖 / Dependency Graph

```
Sprint 1 (安全關鍵)
  T3.01 SM-03 補全 ──────┐
  T3.02 冪等保護 ─────────┤──→ Sprint 1 Gate
  T3.03 執行枚舉 ─────────┘
                           │
Sprint 2 (操作護欄)        ↓（Sprint 1 完成後開始）
  T3.04 OperatorAction ───┐
  T3.05 WS 保護 ──────────┤
  T3.06 事件日曆 ──────────┤──→ Sprint 2 Gate
  T3.07 衝突仲裁 ──────────┤
  T3.08 熔斷聯動 ──────────┘
                           │
Sprint 3 (驗證)            ↓（Sprint 2 完成後開始）
  T3.09 E2E 測試 ─────────┐
  T3.10 PM 簽收 ──────────┤──→ Phase 3 ✅
  T3.11 測試修復 ──────────┘
```

**Sprint 內部可並行：**
- Sprint 1：T3.01 必須先完成，T3.02+T3.03 可同 session 做
- Sprint 2：T3.04~T3.08 全部獨立，可並行或串行
- Sprint 3：T3.09 依賴 Sprint 2 全部完成

---

## 六、角色分配 / Role Assignment

| 任務 | 主執行 | 審閱 | 模型 |
|------|--------|------|------|
| T3.01 SM-03 補全 | E2 | FA + PM | Opus |
| T3.02 冪等保護 | E2 | FA | Sonnet |
| T3.03 執行枚舉 | E2 | FA | Sonnet |
| T3.04 OperatorAction | E2 | PM | Sonnet |
| T3.05 WS 保護 | E2 | FA | Sonnet |
| T3.06 事件日曆 | AI-E + E2 | FA | Sonnet |
| T3.07 衝突仲裁 | AI-E | E2 + PM | Sonnet |
| T3.08 熔斷聯動 | E2 | FA | Sonnet |
| T3.09 E2E 測試 | E2 + AI-E | PM | Sonnet |
| T3.10 PM 簽收 | PM + R1 | Operator | Opus |
| T3.11 測試修復 | CC | E2 | Sonnet |

---

## 七、執行建議 / Execution Strategy

**Session 分配建議（最高效路徑）：**

```
Session A：T3.01（SM-03 補全）               ← 最高優先，Opus
Session B：T3.02 + T3.03（冪等 + 枚舉）      ← 可並行，Sonnet
           → Sprint 1 Gate ✓

Session C：T3.04（OperatorAction）            ← 獨立
Session D：T3.05 + T3.08（WS 保護 + 熔斷）   ← 可同 session
Session E：T3.06（事件日曆）                   ← 獨立
Session F：T3.07（衝突仲裁）                   ← 獨立
           → Sprint 2 Gate ✓

Session G：T3.09 + T3.11（E2E 測試 + 修復）
Session H：T3.10（PM 簽收）                    ← Opus
           → Phase 3 ✅
```

**最少 session 數：8**（如果並行最大化）
**穩健 session 數：10-11**（留有 buffer）

---

## 八、Phase 4 預覽 / Phase 4 Preview

Phase 3 完成後，系統達到「可安全交易」狀態。Phase 4 是能力激活：

| Task | 描述 | 前置條件 | 工作量 |
|------|------|---------|--------|
| T4.01 | H1-H5 AI 管線接入主路徑 | 勝率 > 20% | XL (4-6s) |
| T4.02 | L0→L2 計算路由啟動 | T4.01 完成 | L (2-3s) |
| T4.03 | 多 Agent Conductor 激活 | T3.07 完成 | L (2-3s) |
| T4.04 | 650+ 符號掃描器上線 | market_regime 驗證 | M (1-2s) |
| T4.05 | 學習管線 L2-L5 啟用 | 勝率 > 20% + 500 觀察 | L (2-3s) |
| T4.06 | DOC-03 字段分類強制 | Phase 3 完成 | M (1s) |
| T4.07 | DOC-05 寫入權限強制 | Phase 3 完成 | M (1s) |
| T4.08 | DOC-06 變更路由自動化 | T3.04 完成 | M (1s) |
| **總計** | | | **12-20 sessions** |

---

## 九、Operator 決策點 / Operator Decisions

1. **批准本計劃？** → 是否同意 Sprint 1→2→3 的順序和內容
2. **立即開始 Sprint 1？** → T3.01（SM-03 補全）是最高優先
3. **並行度？** → 是否允許 session 內並行多個任務
4. **Phase 4 啟動條件？** → 維持「勝率 > 20%」門檻還是調整

---

*制定者：PM 角色 | OpenClaw ByBit 治理項目 | 2026-03-30*
