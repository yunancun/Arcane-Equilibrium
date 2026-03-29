# Phase 0 重啟審計報告
# Phase 0 Restart Audit Report
**日期：** 2026-03-30
**角色：** PM (Project Manager)
**範圍：** 22 份治理文件 × 完整源碼合規審計
**目的：** 從零重新評估合規狀態，重新定義 Phase 編號

---

## 一、22 份治理文件清單 / 22 Governance Documents

| # | 編號 | 名稱 | 版本 | 類別 |
|---|------|------|------|------|
| 1 | DOC-01 | 項目憲法與根原則 | V2 | 組織 |
| 2 | DOC-02 | 邊界定義 | V2 | 組織 |
| 3 | DOC-03 | 字段級與狀態級規範 | V1.1 | 組織 |
| 4 | DOC-04 | Agent 能力藍圖 | V2 | 組織 |
| 5 | DOC-05 | 真相源與所有權矩陣 | V1.1 | 組織 |
| 6 | DOC-06 | 變更治理 | V2 | 組織 |
| 7 | DOC-07 | 審計事故與熔斷政策 | V1.1 | 組織 |
| 8 | DOC-08 | 實施橋樑 | V1 | 組織 |
| 9 | DOC-NAV | 治理文件導航 | V3 | 組織 |
| 10 | EX-01 | 風控邊界定義 | V2 | 技術 |
| 11 | EX-02 | OMS 與執行正式邊界 | V1 | 技術 |
| 12 | EX-03 | 控制平面正式邊界 | V1 | 技術 |
| 13 | EX-04 | 對賬正式邊界 | V1 | 技術 |
| 14 | EX-05 | 學習邊界 | V2 | 技術 |
| 15 | EX-06 | 多 Agent 編排邊界 | V1 | 技術 |
| 16 | EX-07 | 感知平面邊界 | V1 | 技術 |
| 17 | SM-01 | 授權狀態機 | V1 | 狀態機 |
| 18 | SM-02 | 決策租約狀態機 | V1 | 狀態機 |
| 19 | SM-03 | 執行狀態機 | V1.1 | 狀態機 |
| 20 | SM-04 | 風控狀態機 | V1 | 狀態機 |
| 21 | HIST-01 | 核心設計總綱 | V1 | 參考 |
| 22 | HIST-02 | 治理設計交付包 | V1 | 參考 |

---

## 二、整體合規度矩陣 / Overall Compliance Matrix

| 分類 | 文件數 | ✅ 已實現 | ⚠️ 部分 | ❌ 缺失 | 合規率 |
|------|--------|-----------|---------|---------|--------|
| DOC（組織/營運） | 9 | 35% | 45% | 20% | ~58% |
| EX（技術邊界） | 7 | 45% | 35% | 20% | ~63% |
| SM（狀態機） | 4 | 75% | 20% | 5% | ~85% |
| HIST（參考） | 2 | N/A | — | — | 參考用 |
| **整體** | **22** | **~48%** | **~35%** | **~17%** | **~65%** |

**對比上次 Phase 0（2026-03-29）：28% → 65%（+37%），主要因為 4 個 SM + 治理集線器 + 對賬引擎 + 事件模型已實現。**

---

## 三、Gap 逐項分析 / Gap-by-Gap Analysis

### 🔴 CRITICAL（阻塞生產部署）

#### GAP-C1：治理閘門非致命 — 訂單繞過 H1-H5
- **來源：** DOC-01 §5.3, §5.4, SM-01, SM-02, EX-03
- **要求：** Decision Lease → Authorization → Risk Check → Execute。每一層為 fail-closed 強制閘門。
- **現狀：** `paper_trading_engine.py:847` 和 `pipeline_bridge.py:281` 中 `governance_hub.is_authorized()` 為 **非致命**（`logger.warning` + 繼續執行）。SM-02 Decision Lease `acquire_lease` 同理。
- **影響：** 整個治理管線被繞過。任何訂單都可以在無授權/無租約情況下提交。
- **修復：** 改 `is_authorized()` 為 fail-closed（返回 False 時拒絕訂單）；`acquire_lease` 失敗時阻止提交。
- **工作量：** M（1-2 sessions）— 邏輯已在，僅需改為強制

#### GAP-C2：跨狀態機級聯未在運行時啟用
- **來源：** SM-01/02/03/04 交叉, GovernanceHub
- **要求：** Risk ≥ CIRCUIT_BREAKER → Auth FROZEN → Lease revoke_all → Order ABORTED
- **現狀：** `governance_hub.py` 定義了級聯規則（line 1-50 docstring），但 GovernanceHub 未被 `main.py` 初始化注入到 PaperEngine/PipelineBridge 的啟動流程。`set_governance_hub()` 方法存在但未被調用。
- **影響：** 四個 SM 各自獨立運行，無級聯。Risk 狀態升級時不會凍結授權，不會撤銷租約。
- **修復：** 在 `main.py` / 啟動流程中實例化 GovernanceHub，注入到 PaperEngine 和 PipelineBridge。
- **工作量：** M（1-2 sessions）

#### GAP-C3：Multi-Agent 體系僅有 Scout
- **來源：** EX-06, DOC-04, DOC-01 §5.15
- **要求：** 6 個 Agent（Scout/Strategist/Guardian/Analyst/Executor）+ OpenClaw Conductor
- **現狀：** `multi_agent_framework.py`（927 行）定義了完整的 `AgentRole` enum（6 角色）和消息總線，但只實現了 `ScoutAgent` 類（354 行以下）。其餘 5 個 Agent 角色無具體實現。
- **影響：** 無正式 Strategist（決策者）、無 Guardian（風控 Agent）、無 Conductor 編排。功能由 `pipeline_bridge.py` + `risk_manager.py` 非正式承擔。
- **修復：** 在 multi_agent_framework 中實現剩餘 5 個 Agent 角色，並接入消息總線。
- **工作量：** XL（4-6 sessions）

### 🟠 HIGH（Phase 1 前必須修復）

#### GAP-H1：學習管線 L2-L5 未接入
- **來源：** EX-05, DOC-01 §5.12
- **要求：** L1 復盤 → L2 模式發現 → L3 假設生成 → L4 策略進化 → L5 元學習
- **現狀：** L1（trade_attribution.py 寫 Observation）已運行。`learning_tier_gate.py` 定義了 L1-L5 門控條件但 L2-L5 邏輯為佔位符。
- **影響：** 系統無法從交易結果中自主學習和進化。
- **工作量：** XL（3-4 sessions）

#### GAP-H2：Portfolio 級風控缺失
- **來源：** DOC-01 §5.16, EX-01
- **要求：** 相關性矩陣、行業集中度、策略重疊監控、全場回撤上限
- **現狀：** `portfolio_risk_control.py` 存在，有 rolling correlation matrix 框架，但未接入實時交易管線。`risk_manager.py` 僅做單倉位風控。
- **影響：** 多倉位同方向暴露不受限制。
- **工作量：** L（2-3 sessions）

#### GAP-H3：審計持久化不完整
- **來源：** DOC-07, DOC-01 §5.8
- **要求：** 不可變審計日誌 + transition_id + trigger_event_id + approved_by + 持久化到磁碟
- **現狀：** 所有 SM 內建 `_audit_log` 列表（記憶體），GovernanceHub 可持久化 JSON，但主流程未啟用持久化寫入。
- **影響：** 重啟後審計丟失。
- **工作量：** S（1 session）

#### GAP-H4：事故→狀態機集成
- **來源：** DOC-07, SM cross
- **要求：** IncidentEvent 觸發 SM 轉換（如 severity=CRITICAL → Auth FROZEN）
- **現狀：** `incident_event_model.py` 已定義 9 類差異和嚴重度。`governance_hub.py` 有對接位，但 incident 到 SM 自動聯動尚未完成。
- **影響：** 對賬發現重大差異時不會自動觸發風控升級。
- **工作量：** M（1-2 sessions）

#### GAP-H5：Paper→Live Gate 正式條件
- **來源：** EX-05, DOC-08
- **要求：** 4 週 + 500 trades + 正收益 + 30% 勝率 + Sharpe > 0.5
- **現狀：** `paper_live_gate.py` 存在，有條件框架，但閾值需確認是否與治理文件一致。
- **影響：** Paper→Live 切換可能不符合規範條件。
- **工作量：** S（0.5 session）

### 🟡 MEDIUM（Phase 2 期間修復）

| ID | Gap | 來源 | 現狀 | 工作量 |
|----|-----|------|------|--------|
| GAP-M1 | 認知誠實強制執行（unmarked inference 應阻止交易） | DOC-01 §5.10, EX-07 | perception_data_plane.py 有 fact/inference 標記，但無阻止邏輯 | S |
| GAP-M2 | 變更審計日誌（WHO/WHEN/APPROVAL 持久化） | DOC-06 | 部分實現於 SM audit_log，無統一持久化 | M |
| GAP-M3 | 交易所保護性訂單（最終防線） | DOC-01 §5.9 | protective_order_manager.py 存在但未接入 Bybit API | L |
| GAP-M4 | H0 Gate 應為 fail-closed | DOC-02 | h0_gate 存在但部分 check 為 warning-only | S |
| GAP-M5 | 恢復審批門控（recovery_approval_gate） | SM cross | recovery_approval_gate.py 存在，需確認啟用狀態 | S |
| GAP-M6 | 掃描器週期最小限制 | DOC-02 | 未強制 5 分鐘最小間隔 | S |
| GAP-M7 | OMS RECONCILING 閘門 | SM-03 | oms_state_machine.py 有 RECONCILING 但轉換邏輯需驗證 | S |
| GAP-M8 | TTL Enforcer 啟用 | SM cross | ttl_enforcer.py 存在，需確認主流程調用 | S |

### 🟢 LOW（Phase 3 或延後）

| ID | Gap | 來源 | 工作量 |
|----|-----|------|--------|
| GAP-L1 | 交易歸因精度（運氣 vs 判斷分離） | DOC-01 §5.8 | M |
| GAP-L2 | .orig 備份文件清理 | 代碼清潔 | S |
| GAP-L3 | governance/ 頂級目錄僅有 __init__.py（實際代碼在 control_api_v1/app/） | 架構整理 | L |
| GAP-L4 | AI 成本追蹤完整性（cloud API cost → net_pnl） | DOC-01 §5.13 | M |

---

## 四、關鍵發現摘要 / Key Findings Summary

### 進展顯著（對比 2026-03-29 首次 Phase 0）

| 模組 | 首次 Phase 0 | 本次 Phase 0 | 變化 |
|------|-------------|-------------|------|
| SM-01 授權 | ❌ 完全缺失 | ✅ 701 行完整實現 | 新建 |
| SM-02 決策租約 | ❌ Schema 佔位 | ✅ 717 行完整實現 | 新建 |
| SM-03 OMS | ⚠️ 7 狀態 | ✅ 670 行 11 狀態 | 補完 |
| SM-04 風控 | ⚠️ 二元 | ✅ 835 行 6 狀態 | 重寫 |
| GovernanceHub | ❌ 不存在 | ✅ 852 行級聯邏輯 | 新建 |
| ReconciliationEngine | ❌ 完全缺失 | ✅ 882 行完整實現 | 新建 |
| IncidentEventModel | ❌ 不存在 | ✅ 事故分類模型 | 新建 |
| TTL Enforcer | ❌ 不存在 | ✅ 過期強制守護 | 新建 |
| RecoveryApprovalGate | ❌ 不存在 | ✅ 恢復需審批 | 新建 |
| ProtectiveOrderMgr | ❌ 不存在 | ✅ 保護性訂單管理 | 新建 |
| PerceptionDataPlane | ❌ 不存在 | ✅ 587 行 fact/inference | 新建 |
| MultiAgentFramework | ❌ 不存在 | ⚠️ 927 行（僅 Scout） | 新建 |

### 核心問題：「模組存在但未接入」

最大的發現是：大量治理模組已經寫好（~6,000 行新代碼），但**未被主流程啟用**。具體而言：
1. GovernanceHub 未注入 PaperEngine/PipelineBridge 啟動
2. `is_authorized()` 檢查為 warning-only
3. 5 個 Agent 角色無實現
4. TTL Enforcer、RecoveryApprovalGate 未在主流程調用
5. Portfolio Risk Control 未接入

---

## 五、重新定義 Phase 編號 / Revised Phase Definitions

基於審計結果，以下是重新定義的 Phase：

### Phase 0：觀察模式（read_only）✅ 已達標
- 系統在 read_only/paper 模式下運行
- H0 Gate 存在（即使非強制）
- 基本風控（單倉位級）運行中
- Paper Engine 正常運作
- **當前狀態：通過**

### Phase 1：治理接入（Governance Wiring）🔴 未達標
**目標：** 讓已實現的治理模組在運行時生效
**任務：**

| # | 任務 | 對應 Gap | 工作量 | 優先級 |
|---|------|----------|--------|--------|
| T1.01 | GovernanceHub 啟動注入 — main.py 實例化 Hub 並注入 PE/PB | GAP-C2 | M | P0 |
| T1.02 | is_authorized() 改為 fail-closed | GAP-C1 | S | P0 |
| T1.03 | acquire_lease() 改為強制（無 lease 不可下單） | GAP-C1 | S | P0 |
| T1.04 | 審計日誌持久化啟用 | GAP-H3 | S | P1 |
| T1.05 | Incident→SM 自動級聯 | GAP-H4 | M | P1 |
| T1.06 | TTL Enforcer 在主流程啟用 | GAP-M8 | S | P1 |
| T1.07 | H0 Gate fail-closed 強化 | GAP-M4 | S | P1 |
| T1.08 | Paper→Live Gate 閾值對齊治理文件 | GAP-H5 | S | P2 |

**預估：3-4 sessions（1-2 週）**
**Phase 1 完成標準：** 所有訂單必須通過 Auth→Lease→Risk→Execute 鏈。任何一環失敗則訂單被拒。

### Phase 2：風控強化（Risk Hardening）
**目標：** Portfolio 級風控 + 保護性訂單 + 認知誠實強制
**任務：**

| # | 任務 | 對應 Gap | 工作量 |
|---|------|----------|--------|
| T2.01 | Portfolio 級風控接入實時管線 | GAP-H2 | L |
| T2.02 | 認知誠實：unmarked inference 阻止交易 | GAP-M1 | S |
| T2.03 | 保護性訂單接入 Bybit API | GAP-M3 | L |
| T2.04 | 變更審計統一持久化 | GAP-M2 | M |
| T2.05 | 恢復審批門控啟用 | GAP-M5 | S |
| T2.06 | OMS RECONCILING 轉換驗證 | GAP-M7 | S |
| T2.07 | 掃描器最小間隔強制 | GAP-M6 | S |

**預估：4-6 sessions（2-3 週）**

### Phase 3：多 Agent 體系（Multi-Agent System）
**目標：** 實現完整的 6 Agent + Conductor 架構
**任務：**

| # | 任務 | 對應 Gap | 工作量 |
|---|------|----------|--------|
| T3.01 | StrategistAgent 實現 + 消息總線接入 | GAP-C3 | L |
| T3.02 | GuardianAgent（封裝 RiskManager）| GAP-C3 | M |
| T3.03 | ExecutorAgent（封裝 PaperEngine）| GAP-C3 | M |
| T3.04 | AnalystAgent（接入 L1 歸因數據）| GAP-C3 | L |
| T3.05 | OpenClaw Conductor 編排邏輯 | GAP-C3 | L |
| T3.06 | Agent 故障隔離 + Dead Letter | EX-06 | M |

**預估：6-8 sessions（3-4 週）**

### Phase 4：學習進化（Learning Evolution）
**目標：** L2-L5 學習管線 + 模型漂移檢測
**任務：**

| # | 任務 | 對應 Gap | 工作量 |
|---|------|----------|--------|
| T4.01 | L2 模式發現引擎 | GAP-H1 | L |
| T4.02 | L3 假設生成 + 影子測試 | GAP-H1 | L |
| T4.03 | L4 策略進化 + 自動部署 | GAP-H1 | XL |
| T4.04 | L5 元學習框架 | GAP-H1 | XL |
| T4.05 | 模型漂移偵測 + 回滾 | EX-05 | M |
| T4.06 | AI 成本完整追蹤（cloud API → net_pnl）| GAP-L4 | M |
| T4.07 | 交易歸因精度提升 | GAP-L1 | M |

**預估：8-10 sessions（4-5 週）**

### Phase 5：架構整理 + 生產準備
**目標：** 代碼結構整理 + 全面集成測試 + 生產就緒
**任務：** governance/ 目錄整理、備份文件清理、全面 E2E 測試、文檔更新

**預估：2-3 sessions（1 週）**

---

## 六、總時程估計 / Total Timeline

| Phase | 內容 | 預估時間 | 累計 |
|-------|------|----------|------|
| Phase 0 | 觀察模式 | ✅ 已達標 | — |
| Phase 1 | 治理接入 | 1-2 週 | 2 週 |
| Phase 2 | 風控強化 | 2-3 週 | 5 週 |
| Phase 3 | 多 Agent | 3-4 週 | 9 週 |
| Phase 4 | 學習進化 | 4-5 週 | 14 週 |
| Phase 5 | 生產準備 | 1 週 | 15 週 |

**總計約 15 週至完全合規。**
**最快 Paper Trading 安全運行（Phase 1 完成）：2 週。**
**最快 Demo Trading 安全運行（Phase 2 完成）：5 週。**

---

## 七、風險與建議 / Risks & Recommendations

1. **最大風險：治理模組存在但未啟用。** 給人「已實現」的錯覺，但實際訂單流不受任何治理約束。Phase 1 必須優先解決。

2. **Agent 架構選擇：** 當前 multi_agent_framework.py 已有完整的消息總線和角色定義。建議在此基礎上擴展，而非重寫。

3. **測試覆蓋：** 治理模組有獨立單元測試（432 全通過），但缺少集成測試驗證「管線端到端治理強制」。Phase 1 應包含集成測試。

4. **並行執行建議：** Phase 1 和 Phase 2 的部分任務可以並行（T1.04-T1.08 和 T2.01 無相依）。Phase 3 的 T3.01-T3.04 可以並行開發。

---

## 八、Operator 決策項 / Decisions for Operator

1. **Phase 編號方案是否接受？**（Phase 0-5 五階段）
2. **Phase 1 立即啟動？**（治理接入，預估 1-2 週）
3. **是否接受 Phase 1 的 P0 任務順序？**（T1.01→T1.02→T1.03 為最高優先）
4. **Phase 3（Multi-Agent）是否可以與 Phase 2 部分並行？**

---

*報告由 PM（via Cowork）於 2026-03-30 產出*
*基於 3 個平行審計 Agent 的結果綜合而成*
