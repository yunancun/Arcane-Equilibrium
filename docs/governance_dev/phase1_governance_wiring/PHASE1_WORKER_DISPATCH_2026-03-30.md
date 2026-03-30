# Phase 1 Worker 工作流分配表
# Phase 1 Worker Dispatch & Workflow

**日期：** 2026-03-30
**作者：** PM (via Cowork PM)
**對應任務書：** PHASE1_TASK_BOOK_2026-03-30.md

---

## 一、Worker 對話配置（推薦 5 對話方案）

### Worker-1：FA（架構師）

**角色：** FA
**Git identity：** `Nancun (via Cowork FA)`
**職責：** 架構設計、接口規範、依賴驗證

**任務隊列（按順序）：**

| 順序 | Task ID | 輸出 | 交付給 |
|------|---------|------|--------|
| 1 | T1.01 架構驗證 | Import 順序驗證報告 + 注入方案 | Worker-2 (E1b-A) |
| 2 | T1.04 設計 | AuditPipeline 整合架構文件 | Worker-4 (E1b-C) |
| 3 | T1.05 設計 | Incident→SM 事件映射表 | Worker-4 (E1b-C) |

**Worker Prompt 補充：**
```
你是 FA（架構師），負責 Phase 1 的架構設計。

你的任務（按順序）：

【任務 1】T1.01 架構驗證
- 驗證 `phase2_strategy_routes.py` 能否 import `paper_trading_routes.GOV_HUB` 而不產生循環依賴
- 測試方法：在 Python 中嘗試 import 鏈
- 輸出：注入方案（直接 import 或延遲注入）+ 風險評估
- 文件：`app/phase2_strategy_routes.py`, `app/paper_trading_routes.py`

【任務 2】T1.04 AuditPipeline 設計
- 設計 GovernanceHub 與 AuditPipeline 的整合方案
- 需要確認：
  - GovernanceHub._ensure_initialized() 中 SM 的 audit_callback 如何替換為 AuditPipeline 回調
  - AuditPipeline 何時實例化（在 GOV_HUB 之前還是之後）
  - 文件寫入路徑配置
- 輸出：整合架構文件（含時序圖）

【任務 3】T1.05 Incident 級聯設計
- 設計 IncidentPolicy 的回調連接方案
- 映射表：EventSeverity → SM actions（對照 incident_event_model.py:237-265 的 severity→action 映射）
- 確認 ReconciliationEngine 如何觸發 IncidentPolicy
- 輸出：事件映射表 + 連接方案

完成後 git commit + push，並在 02_audit_reports/ 留副本。
```

---

### Worker-2：E1b-A（修改工程師 A — 接入類）

**角色：** E1b
**Git identity：** `Nancun (via Cowork E1b-A)`
**職責：** GovernanceHub 接入 + TTL 啟動

**任務隊列：**

| 順序 | Task ID | 前置條件 | 修改文件 |
|------|---------|---------|---------|
| 1 | T1.01 實現 | Worker-1 完成 T1.01 架構驗證 | `phase2_strategy_routes.py` |
| 2 | T1.06 實現 | T1.01 完成 | `paper_trading_routes.py` 或 `governance_hub.py` |

**Worker Prompt 補充：**
```
你是 E1b-A（修改工程師），負責 Phase 1 的治理接入。

【任務 1】T1.01 — PipelineBridge GovernanceHub 注入
- 等待 FA 的架構驗證結果
- 在 `phase2_strategy_routes.py` 第 201 行之後，注入 GovernanceHub 到 PIPELINE_BRIDGE
- 參考方案：
  from .paper_trading_routes import GOV_HUB as _GOV_HUB_REF
  if _GOV_HUB_REF is not None:
      PIPELINE_BRIDGE.set_governance_hub(_GOV_HUB_REF)
- 新增測試：驗證 PIPELINE_BRIDGE._governance_hub is not None
- 運行全部測試確認無回歸

【任務 2】T1.06 — TTL Enforcer daemon 啟動
- 在 GovernanceHub 初始化後啟動 TTL Enforcer daemon
- 連接 expiry_callback → GovernanceHub 的 lease/auth 過期處理
- 確保 shutdown hook 調用 stop_daemon_sweep()
- 運行全部測試確認無回歸

完成後 git commit + push。
```

---

### Worker-3：E1b-B（修改工程師 B — fail-closed 類）

**角色：** E1b + E3
**Git identity：** `Nancun (via Cowork E1b-B)`
**職責：** fail-closed 修改 + 安全審核

**任務隊列（可立即開始，無前置依賴）：**

| 順序 | Task ID | 修改文件 |
|------|---------|---------|
| 1 | T1.02 實現 | `paper_trading_engine.py:907-916` |
| 2 | T1.03 實現 | `paper_trading_engine.py:853-854`, `risk_manager.py:581-582`, `pipeline_bridge.py:288-289` |
| 3 | T1.07 實現 | `governance_hub.py`（H0 Gate 邊緣情況） |

**Worker Prompt 補充：**
```
你是 E1b-B（修改工程師），負責 Phase 1 的 fail-closed 修改。

【任務 1】T1.02 — acquire_lease() fail-closed
- 文件：`paper_trading_engine.py`，第 907-916 行
- 現狀：acquire_lease() 返回 None 時，訂單繼續（non-fatal）
- 修改：返回 None → 訂單 REJECTED (governance_lease_denied)
         異常 → 訂單 REJECTED (governance_lease_error)
- 保持：無 GovernanceHub 時訂單正常通過（向後兼容）
- 參考任務書中的具體代碼片段
- 新增 3 個測試（deny/error/success）

【任務 2】T1.03 — is_authorized() exception handler fail-closed
- 三處修改：
  1. paper_trading_engine.py:853-854 — exception → 訂單 REJECTED
  2. risk_manager.py:581-582 — exception → return False, "governance_check_error"
  3. pipeline_bridge.py:288-289 — exception → skip intent + stats++
- 所有 logger.warning("... (non-fatal)") → logger.error("... — fail-closed")
- 新增每處 1 個異常注入測試

【任務 3】T1.07 — H0 Gate fail-closed
- 審查 governance_hub.py 中所有返回 True 的路徑
- 確認邊緣情況：SM 部分初始化、cache 過期、線程競爭
- 新增邊緣情況測試

【安全審核（E3 職責）】：
- 完成所有修改後，執行：grep -r "non-fatal" app/
- 確認結果為 0
- 審查是否有任何繞過路徑

完成後 git commit + push。
```

---

### Worker-4：E1b-C（修改工程師 C — 持久化類）

**角色：** E1b
**Git identity：** `Nancun (via Cowork E1b-C)`
**職責：** Audit 持久化 + Incident 級聯

**任務隊列（需等待 FA 設計 + T1.01 完成）：**

| 順序 | Task ID | 前置條件 | 修改文件 |
|------|---------|---------|---------|
| 1 | T1.04 實現 | FA 完成 T1.04 設計 + T1.01 完成 | `paper_trading_routes.py`, `governance_hub.py` |
| 2 | T1.05 實現 | FA 完成 T1.05 設計 + T1.01 完成 | `paper_trading_routes.py`, `governance_hub.py` |

**Worker Prompt 補充：**
```
你是 E1b-C（修改工程師），負責 Phase 1 的持久化和級聯接入。

【任務 1】T1.04 — AuditPipeline 連接
- 等待 FA 的 AuditPipeline 整合架構文件
- 在 paper_trading_routes.py 中：
  1. 創建 AuditPipeline 實例
  2. 為 GovernanceHub 的每個 SM 生成 audit_callback
  3. 確認 SM 狀態轉換寫入磁碟
- 驗證：重啟後用 AuditFileReader.query() 讀取審計記錄
- 運行全部測試

【任務 2】T1.05 — Incident → SM 級聯
- 等待 FA 的事件映射表
- 在 GovernanceHub 初始化後創建 IncidentPolicy 實例
- 連接回調：
  on_auth_action → GovernanceHub auth freeze/restrict
  on_risk_action → GovernanceHub risk escalation
  on_operator_alert → logger.critical + 預留通知擴展
- 連接 ReconciliationEngine → IncidentPolicy.process_event()
- 測試 5 個嚴重度級別的級聯效果

完成後 git commit + push。
```

---

### Worker-5：E4（測試工程師）

**角色：** E4 + CC + R1
**Git identity：** `Nancun (via Cowork E4)`
**職責：** 集成測試 + 合規檢查 + 回歸驗證

**任務隊列：**

| 順序 | Task ID | 前置條件 | 輸出 |
|------|---------|---------|------|
| 1 | T1.08 審核 | 無（可立即開始） | 閾值對齊報告 |
| 2 | T1.09 設計 | 無（可立即開始） | 10 個 E2E 測試用例設計 |
| 3 | T1.09 實現 | T1.01+T1.02+T1.03 完成 | 測試代碼 |
| 4 | 全面回歸 | 所有任務完成 | 回歸測試報告 |

**Worker Prompt 補充：**
```
你是 E4（測試工程師），負責 Phase 1 的測試和合規。

【任務 1】T1.08 — Paper→Live Gate 閾值對齊（CC + R1 角色）
- 讀取治理文件：docs/governance_dev/governance_extracts/ 中的 EX-05 和 DOC-08
- 比對 paper_live_gate.py:PaperLiveGateConfig 的閾值
- 輸出：閾值對齊報告（逐項比對 + 差異標記）

【任務 2】T1.09 — E2E 集成測試設計
- 設計 10 個端到端測試用例（見任務書 T1.09 表格）
- 每個用例包含：前置條件、操作步驟、預期結果、驗證方法
- 可先寫測試框架（@pytest.mark.integration）

【任務 3】T1.09 — E2E 集成測試實現
- 在 test_integration_governance.py 中新增 10 個測試
- 等待 T1.01/T1.02/T1.03 完成後執行
- 全部通過才算完成

【任務 4】全面回歸
- 運行全部 1,707+ 測試
- 輸出回歸測試報告
- 確認 0 失敗

完成後 git commit + push。
```

---

## 二、執行時序圖

```
Week 1 Day 1-2:  Sprint 1（P0 任務）
──────────────────────────────────────────────────────
Worker-1 (FA):     ├─ T1.01 架構驗證 ─┤
                                       ↓
Worker-2 (E1b-A):                      ├─ T1.01 實現 ─┤
                                                       ↓
Worker-3 (E1b-B):  ├── T1.02 lease fail-closed ──┤   │
                   ├── T1.03 auth exception fix ──┤   │
                                                   ↓  ↓
Worker-5 (E4):     ├─ T1.08 閾值審核 ─┤          ├─ T1.09 E2E 測試 ─┤
                   ├─ T1.09 測試設計 ──┤

Week 1 Day 3-5:  Sprint 2（P1 任務）
──────────────────────────────────────────────────────
Worker-1 (FA):     ├─ T1.04 設計 ──┤ ├─ T1.05 設計 ──┤
                                    ↓                  ↓
Worker-4 (E1b-C):                  ├─ T1.04 實現 ──┤ ├─ T1.05 實現 ──┤
Worker-2 (E1b-A):  ├─ T1.06 TTL daemon ─┤

Week 2 Day 1-2:  Sprint 3（P2 + 收尾）
──────────────────────────────────────────────────────
Worker-3 (E1b-B):  ├─ T1.07 H0 Gate ─┤
Worker-5 (E4):     ├─ 全面回歸測試 ──┤ ├─ 回歸報告 ─┤
PM:                                                    ├─ 最終驗收 ─┤
```

---

## 三、Worker 間交接協議

| 交接點 | 來源 Worker | 接收 Worker | 交接內容 | 交接方式 |
|--------|-------------|-------------|---------|---------|
| A1 | Worker-1 (FA) | Worker-2 (E1b-A) | T1.01 注入方案 | Git commit + Operator 轉發 |
| A2 | Worker-1 (FA) | Worker-4 (E1b-C) | T1.04 架構文件 | Git commit + Operator 轉發 |
| A3 | Worker-1 (FA) | Worker-4 (E1b-C) | T1.05 映射表 | Git commit + Operator 轉發 |
| B1 | Worker-2 (E1b-A) | Worker-5 (E4) | T1.01 完成通知 | Operator 確認 |
| B2 | Worker-3 (E1b-B) | Worker-5 (E4) | T1.02+T1.03 完成通知 | Operator 確認 |
| C1 | Worker-5 (E4) | PM | T1.09 全通過 | Git commit + 報告 |
| C2 | Worker-5 (E4) | PM | 回歸報告 | Git commit + 報告 |

**Operator 職責：** 在各 Worker 對話間轉發交接信息和 Git commit hash。

---

## 四、每個 Worker 的啟動 Prompt 模板

複製 `WORKER_PROMPT.md` 到新對話，然後附加：

```
## 本對話角色分配

角色：{ROLE}
Phase：1 — 治理接入
任務書：docs/governance_dev/phase1_governance_wiring/PHASE1_TASK_BOOK_2026-03-30.md
分配表：docs/governance_dev/phase1_governance_wiring/PHASE1_WORKER_DISPATCH_2026-03-30.md

你的任務：
{TASK_LIST}（見分配表中 Worker-{N} 的任務隊列）

啟動步驟：
1. Clone repo + 配置 identity
2. 讀取任務書和分配表
3. 按順序執行任務
4. 每完成一項 git commit + push
5. 報告完成狀態
```

---

*Worker 分配表由 PM（via Cowork PM）於 2026-03-30 產出*
