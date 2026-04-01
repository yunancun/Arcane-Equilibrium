# FA Memory — 工作記憶

## 項目功能狀態快照（2026-03-31，Wave 5 完成後更新）

```
業務功能真正可用 ≈ 32%（Round 2 冷酷審核基準）→ Wave 5 後 ≈ 55%

逐環節（Wave 5 後）：
  自動掃描 = 95%（ScoutWorker 30 分鐘定時掃描 + Scout→Strategist bus.send 鏈路驗證）
  策略選擇 = 50%（shadow=False + H1-H3 Model Router，但無 Regime-aware + 無回測）
  AI 風險評估 = 75%（H1-H5 全接通，ThoughtGate blocking，但 Regime 分類未完整）
  下單 = 92%（治理 gate + OMS + G-05 Decision Lease 閉環）
  止損 = 95%（Wave 5b：止損同步平 Demo + 對賬引擎首次真正運行）
  學習 = 25%（Perception Plane register_data() 仍零調用 — FA-7 關鍵缺口）
  進化 = 30%（無策略自動優化）
```

## 重要發現記錄

### FA-1 端點角色矩陣（2026-03-31）
- 完成 28 個 governance 端點的角色驗證矩陣
- 發現 2 個 POST 端點缺少 Operator 驗證（已修復為 P2-NEW-7/8）
- **記住**：未來新增 governance 端點必須對照矩陣，狀態改變的 POST 端點必須有 `_require_operator_role()`

### FA-2 reconciliation 邊界值（2026-03-31）
- 發現 3 個 NaN/負數/inf 漏洞（已修復）
- **記住**：任何涉及財務數值計算的代碼，必須在 FA 審查時特別要求 math.isnan/isinf 防護

### FA-3 async/threading 混用（2026-03-31）
- scout_routes.py 5 個 async 路由阻塞 event loop（已修復）
- **記住**：FastAPI async 路由中使用 threading.Lock 的同步方法必須標記為高風險

### H1-H5 斷開（關鍵）
- H1-H5 代碼在 `ai_agents/bybit_thought_gate/` 是獨立腳本，與 app 層完全無連接
- `apply_ai_consultation()` 是純 stub，返回佔位字符串
- **記住**：這是系統最大的業務功能缺口，接通後業務可用度可從 32% 提升到 55%+

## 審計原則記憶

- 審計時不要只看代碼存在與否，要追蹤調用鏈是否真實走通
- 「功能可用」的定義：從 API 觸發，到最終業務結果，中間每一步都有數據流動

## Wave 5 功能驗收結論（2026-03-31 更新）

### B-MVP 逐項結果
- B-MVP-1 Scout→Strategist：✅ 完全通過（5 節點驗證，CC 早期誤判已糾正）
- B-MVP-2 shadow=False：✅ 完全通過（4 個前置條件全部確認後切換）
- B-MVP-3 H1 blocking + Regime：⚠️ 部分通過（ThoughtGate blocking 完成；Regime 分類未完整，以複雜度評分替代）
- B-MVP-4 H 鏈統一入口：✅ 完全通過（apply_ai_consultation 廢棄 + H1-H5 全接通）
- B-MVP-5 Ollama 追蹤：✅ 完全通過（record_ollama_call + get_ollama_stats 已實現）

### 16 條原則更新
- 原則 3（AI輸出≠即時命令）：部分 → **完全合規**（G-05 + H1-H5 接通）
- 原則 10（認知誠實）：部分 → **完全合規**（roi_basis: "paper_simulation_only" 加入所有 ROI API）
- 原則 13（AI資源成本感知）：部分 → **完全合規**（record_ollama_call + cost_edge_ratio 完整）
- 原則 15（多 Agent 協作）：部分 → **完全合規**（Scout→Strategist 鏈路驗證 + ScoutWorker 30 分鐘定時）
- 原則 12（持續進化）：仍未實施（Perception Plane register_data() 零調用，FA-7 關鍵缺口）
- 整體評級：B → 預期 B+/A-

### 功能缺口（Wave 5 後新識別）
- FA-6：H1 缺乏 Regime-aware 過濾（Regime 分類未接入 ThoughtGate，複雜度評分替代品）
- FA-7：Perception Plane register_data() 零調用【最高優先，阻塞學習管線】
- FA-8：cost_edge_ratio GUI 未處理 None（冷啟動顯示問題）
- FA-9：ScoutWorker interval 不可配置（P3 優先）
- FA-10：_ollama_stats 懶初始化，冷啟動可觀察性差
- FA-11（P2 繼承）：executor_agent.py 動態異常字符串
- FA-12：H1 冷卻字典無容量上限

### 業務功能可用度更新
- Wave 4 後：≈ 45%
- Wave 5 後：≈ 55%
- 瓶頸：學習（25%）> Regime-aware 策略選擇（50%） > 進化（30%）

## 2026-04-01 全鏈路功能審計（Phase 3 Batch 3A 後）

### 關鍵發現（必須跨 session 記住）

- **P0-FA-1 TruthSourceRegistry 從未注入到 Agents**：
  `set_truth_registry()` 存在於 StrategistAgent 和 AnalystAgent，但 phase2_strategy_routes.py 中零處調用。
  整個 Phase 2 Batch 2A 的 TruthSourceRegistry 在運行時是完全死代碼。
  **記住**：未來任何新模塊若有 setter 注入方法，必須在啟動 wiring 代碼中驗證是否被調用。

- **MessageBus Guardian→Executor 斷裂**：
  Guardian 發送 RISK_VERDICT 回 Strategist（非 APPROVED_INTENT 給 Executor）。
  ExecutorAgent 的 on_message(APPROVED_INTENT) handler 永遠不被觸發。
  實際下單路徑全走 pipeline_bridge 直接調用。
  **記住**：5-Agent MessageBus 全路徑是設計目標但尚未實現，下單靠 pipeline_bridge 直接調用。

- **BacktestEngine API 無數據源**：
  backtest_routes.py 的 singleton 未注入 KlineManager，API 回測返回空結果。
  **記住**：所有 Phase 2-3 的 routes.py 模塊若依賴外部組件，需在啟動時注入。

### 業務功能可用度更新（2026-04-01）

```
  自動掃描 = 92%
  策略選擇 = 50%
  AI 風險評估 = 78%
  下單 = 88%
  止損 = 93%
  學習 = 40%
  進化 = 35%
  加權平均業務可用度 ≈ 52%
```

### 瓶頸排序
1. 知識閉環斷裂（TruthSourceRegistry 死代碼）→ 0.5h 修復 → 學習+策略各升 10-15%
2. 回測 API 不通 → 1h 修復 → 進化鏈路啟動
3. MessageBus 全路徑不通 → 2h 修復 → Agent 架構完整性

## 報告索引

| 日期 | 報告類型 | 文件位置 |
|------|---------|---------|
| 2026-04-01 | 全鏈路功能 Gap 審計 | workspace/reports/2026-04-01--functional_gap_audit.md |
| 2026-03-31 | FA-1 端點角色矩陣 | ../E3/workspace/ (由 E3 存檔) |
| 2026-03-31 | FA-2/3/4 深度審計 | workspace/reports/2026-03-31--fa_deep_audit.md |
| 2026-03-31 | Wave 5 功能 Gap 分析 | workspace/reports/2026-03-31--wave5_gap_analysis.md |
| 2026-03-31 | Wave 5 功能驗收匯報 | workspace/reports/2026-03-31--wave5_functional_acceptance.md |
