# PM 進度報告 — Wave 5 完成匯報 + 下一步工作安排
# 日期：2026-03-31
# 作者：PM（Project Manager）

---

## 一、Wave 5 完成摘要

### Sprint 0（前置修復，Wave 5 啟動前）
- **完成項目**：G-05（acquire_lease 前置條件補強）+ G-01（AI 日消費上限修復）
- **測試變化**：2555 → 2561 passed（+6）
- **commit**：d57ed05

### Sprint 5a（H1-H3 接通，~13h）
- **完成項目**：
  - 5a-1：Scout→Strategist intel 鏈路驗證（MessageBus.subscribe 3→2 參數 bug 修復）
  - 5a-2：H0Gate blocking 正式接入 pipeline_bridge
  - 5a-3：H1 ThoughtGate 正式接入 StrategistAgent（timeout→heuristic，CC 原則 6 強制）
  - 5a-4：Strategist shadow=False 正式切換（acquire_lease 前置確認）
  - 5a-5：H2 預算門控接入 Strategist（Layer2CostTracker 注入）
  - 5a-6：H3 ModelRouter 路由接入（l1_9b / l1_27b / l2，L2 daemon Thread）
- **測試變化**：2561 → 2594 passed（+33）
- **commit**：ccdff73

### Sprint 5b（H4-H5 + ScoutWorker + 集成測試，~13h）
- **完成項目**：
  - 5b-1：H4 `_validate_ai_output()` 驗證層（confidence ∈ [0,1]，fail-closed → heuristic）
  - 5b-2/6：H5 CostLogger 接入（`record_ollama_call()` + `roi_basis:"paper_simulation_only"` 雙端 marker）
  - 5b-3：`apply_ai_consultation()` 標記 DEPRECATED + deprecation_notice（保持向後兼容）
  - 5b-4：ScoutWorker 後台定時掃描線程（daemon + 1s interruptible sleep + 冪等 start()）
  - 5b-5：原則 14 集成測試（6 個 Mock Ollama 崩潰 → L0 fallback → 交易鏈路不中斷）
- **測試變化**：2594 → 2610 passed（+16）
- **commit**：9478c00

### Wave 5a Position Sizing 重構（同一時期完成）
- 3% risk/trade（上調自 2%）
- 最多 25 個同時部署幣種（上調自 10）
- 動態 qty（每次下單重算，不再啟動時鎖死）
- 智能資本再分配（Portfolio Rebalancer，弱倉釋放給高分新機會）
- **commit**：8223eb9

### Wave 5b Paper/Demo 同步修復（同一時期完成）
- CRITICAL-1：止損同步平 Demo 倉位（reduce_only）
- CRITICAL-2：Demo 下單失敗從 debug→WARNING + "DIVERGED" 明確標記
- CRITICAL-3：governance_hub.reconcile() 參數名 + dataclass→dict（對賬引擎首次真正運行）
- MOD-4：round_qty_for_exchange() 共用函數（Paper/Demo qty 統一）
- MOD-5：條件止損單 qty 與 Demo 一致
- **commit**：包含於 Wave 5 最終文檔同步 commit（f6ae91e）

### 測試基準線演進

| 里程碑 | passed | 變化 |
|--------|--------|------|
| Wave 0-4 完成 | 2555 | 基準 |
| Sprint 0 完成 | 2561 | +6 |
| Sprint 5a 完成 | 2594 | +33 |
| Sprint 5b 完成 | 2610 | +16 |
| **當前基準** | **2610** | **+55 from Wave 5 start** |

---

## 二、當前整體進度評估

### 對照 16 條根原則合規度

| 評估維度 | 狀態 |
|---------|------|
| 原則 1-10（V1 核心）| 全部已實施，安全評級 0 CRITICAL / 0 HIGH |
| 原則 11（Agent 最大自主權）| ✅ H1-H5 接通後 Agent 可完整決策（shadow=False）|
| 原則 12（持續進化）| 部分：學習平面 25%（E1 觀察 + L2 自動觸發，無策略自動優化）|
| 原則 13（AI 成本感知）| ✅ Wave 5 完成，H5 CostLogger + roi_basis 標記 |
| 原則 14（零外部成本可運行）| ✅ L0+L1 完整可用，Ollama 崩潰 → L0 fallback（6 集成測試驗證）|
| 原則 15（多 Agent 協作）| ✅ 5/6 Agent 運行（Scout/Strategist/Guardian/Analyst/Executor）|
| 原則 16（組合級風險意識）| 部分：持倉關聯曝險未實現，Portfolio Rebalancer 已上線 |

### 業務功能完成度（Wave 5 後更新）

| 環節 | 完成度 | 備注 |
|------|--------|------|
| 自動掃描 | 90% | ScoutWorker 30min 定時掃描 + Scout→Strategist 鏈路接通 |
| 策略選擇 | 40% | 標準技術指標，無回測驗證，無可證明 alpha |
| AI 風險評估 | 55% | H0-H5 全部接通，shadow=False，acquire_lease 前置 |
| 下單 | 90% | 治理 gate + OMS + ExecutorAgent |
| 止損 | 90% | 本地 3 類止損 + 交易所條件單雙重防線（Wave 5b 修復 qty 對齊）|
| 學習 | 25% | 無策略自動優化 |
| 進化 | 30% | PaperLiveGate 已部署，無策略自動演化 |
| **整體業務可用** | **≈ 47%** | 較 Wave 4 略升（AI 評估完整接通貢獻）|

**關鍵里程碑**：H1-H5 完整接通是本次 Wave 5 的最大進展，系統已具備「AI 輔助決策 → 風控 gate → 執行」完整鏈路（demo_only 模式）。

---

## 三、下一步工作安排（優先順序）

> 說明：P3 GUI 術語友好化已確認延後（用戶決策，M-of-N 同樣移出），不在本次安排中。

### 優先級 1：Phase 1 Batch 1B — 安全閘補全（~8h，建議下一個 Sprint）

| 任務 | 描述 | 工時 | 角色 |
|------|------|------|------|
| **Cooldown 聯動確認** | H0Gate → RiskManager set_h0_gate 注入路徑驗收（Day 3 已部署，需端到端 smoke test 確認 cooldown 事件完整推送至 H0Gate） | 2h | E4 + PA |
| **數據品質 → 風控降級** | H0Gate freshness_score warn-only 模式正式化，添加 API 端點查詢當前 freshness 狀態（目前 warn-only 未有 Operator 可視度）| 3h | E1 + E1a |
| **H0Gate Operator 可視化** | governance 端點 `/governance/h0-gate/status` 已存在，GUI H0 狀態卡片補充（目前治理 Tab 未顯示）| 2h | E1a |

**工作鏈**：PA 確認 Cooldown 聯動覆蓋範圍 → E1 + E1a 並行 → E2 → E4 → PM 確認

---

### 優先級 2：P2 批次（選擇性，~20h，可分批）

按 PM_review_2026-03-31.md 中 P2 清單，建議優先執行以下 3 項：

| 任務 | 描述 | 工時 | 角色 |
|------|------|------|------|
| P2-6/P2-7/P2-8（風控覆蓋補強）| RiskManager 邊界值 + 極端市況測試 | 6h | E1 + E4 |
| P2-12/P2-15（pipeline_bridge 邊界）| on_tick 邊界用例 + pending_intents 清理邏輯 | 4h | E1 + E4 |
| P2-25（GUI 術語第一批）| 最重要 3-5 個工程術語替換（僅技術詞，不含全面重設計）| 3h | E1a |

---

### 優先級 3：Phase 2 — 回測引擎 MVP（~10天，策略 alpha 驗證）

**前置條件**：Batch 1B 完成 + Paper Trading 累積足夠交易記錄（建議 ≥ 100 筆）

| 任務 | 描述 | 預估 |
|------|------|------|
| L2 模式發現自動化 | Analyst 自動識別反復出現的市場模式 | 5天 |
| 回測引擎 MVP | 歷史 K線回放 + 策略勝率驗證基礎設施 | 5天 |

**負責規劃**：FA（功能規格）+ PA（技術方案）+ E1（實現）

---

### 優先級 4：Paper Trading 觀察期啟動（長期）

**目標**：穩定運行 21 天，積累 Live 前置條件所需數據

- 每日巡檢：`python3 scripts/bybit_runtime_state_resolver.py`
- 關注指標：勝率趨勢、最大回撤、AI 成本邊際效益（cost_edge_ratio）
- 達標門檻：H0Gate 通過率 > 80%，cost_edge_ratio 連續 7 天 ≥ 0.8

---

## 四、風險提示

### R1：策略 Alpha 未驗證（高風險）
- **現狀**：標準 RSI/MACD/MA，無回測，無可證明的 alpha
- **影響**：即使 H1-H5 完整接通，策略本身若無 alpha，Demo 勝率仍可能維持在低位
- **緩解**：Phase 2 回測引擎（優先級 3）是根本解決方案，建議在 21 天觀察期數據積累後立即啟動

### R2：Perception Plane register_data() 仍為零調用（中風險）
- **現狀**：雖然 test_pipeline_bridge 補了測試確認可注入，但生產路徑上仍未真正觸發
- **影響**：學習平面的輸入端數據稀少，L2 學習效果受限
- **緩解**：Batch 1B 確認 Cooldown 聯動時一併核查 register_data() 真實調用路徑

### R3：週期性測試（Cooldown 聯動）尚未端到端驗證（低風險）
- **現狀**：H0Gate Day 3 已部署 set_h0_gate() 注入路徑，但尚無完整 E2E smoke test
- **緩解**：Batch 1B 第一個任務即為此項驗收

### R4：Live 前置條件需 21 天連續觀察（長期約束）
- **說明**：距離 M 章（Supervised Live Gate）仍需 21 天 Paper Trading 穩定觀察 + 策略 alpha 驗證
- **估算**：最快 Phase 1+2（~15天）+ 21 天觀察 = 約 5-6 週後可開始 Live 評估
- **硬邊界**：live_execution_allowed 維持 false，不可縮短觀察期

---

## 五、測試基準確認

```
當前：2610 passed / 18 pre-existing failed / 23 warnings
命令：python3 -m pytest tests/ -q --tb=no
路徑：program_code/exchange_connectors/bybit_connector/control_api_v1/
```

---

*PM — 2026-03-31*
