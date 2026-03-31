# FA 報告：Wave 5 功能驗收匯報

**日期**：2026-03-31
**審計師**：FA（Functional Auditor）
**基準版本**：Wave 4 Sprint 4e 完成後，2555 tests passed
**驗收後基準**：2610 tests passed（Wave 5 Sprint 0+5a+5b 全部完成，18 pre-existing failures）
**參考文件**：
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-03-31--wave5_plan_b_multiagent.md`
- `docs/CCAgentWorkSpace/CC/memory.md`
- `docs/CCAgentWorkSpace/E1/memory.md`（各 Sprint 關鍵發現）
- `docs/CCAgentWorkSpace/E2/memory.md`（各 Sprint 審查結論）
- `CLAUDE.md §三` 當前系統狀態

---

## 一、Wave 5 B-MVP 逐項驗收

### B-MVP-1：Scout→Strategist 情報鏈路
**原計劃**：produce_intel() → bus.send(STRATEGIST) → on_message() → 鏈路接通

**驗收結論：✅ 通過**

完整 5 節點驗證結果（E1-Alpha Sprint 5a-1）：

| 節點 | 位置 | 狀態 |
|------|------|------|
| ScoutAgent.produce_intel() → bus.send() | multi_agent_framework.py:428-436 | ✅ 已存在 |
| pipeline_bridge 調用 produce_intel()，relevance_score 達標 | pipeline_bridge.py:903,909 | ✅ vol_ratio>2.0 → 0.4 > threshold 0.3 |
| phase2_strategy_routes 訂閱 STRATEGIST | phase2_strategy_routes.py:167 | ✅ 已存在 |
| strategist_agent.on_message() 路由 INTEL_OBJECT → _handle_intel() | strategist_agent.py:276-277 | ✅ 已存在 |
| _handle_intel() 遞增 intel_received 計數器 | strategist_agent.py:293 | ✅ 可觀察 |

補充說明：CC 早期審查報告曾錯誤認定此為死代碼，Sprint 5a-1 代碼審計後確認鏈路完整。新增 TestScoutStrategistChain 兩個集成測試驗證。

---

### B-MVP-2：Strategist shadow=False 切換
**原計劃**：Strategist 從記錄日誌（shadow=True）改為真實產生 TradeIntent

**驗收結論：✅ 通過（帶條件）**

前置條件全部確認後執行切換（E1-Alpha Sprint 5a-4）：

| 前置條件 | 確認狀態 |
|---------|---------|
| G-05：ExecutorAgent 插入 acquire_lease()，fail-closed | ✅ Sprint 0 完成 |
| H0 Gate blocking：allowed=False 時 continue，不提交 intent | ✅ Sprint 5a-2 完成 |
| Guardian gate：intent → GuardianAgent 審查 | ✅ Wave 3 Pipeline 已驗證 |
| collect_pending_intents() 存在 | ✅ strategist_agent.py:536 |

phase2_strategy_routes.py 的 StrategistConfig(shadow=True) 已改為 shadow=False，附帶 14 行雙語注釋說明所有前置條件。

**待觀察**：shadow=False 後 TradeIntent 是否在 650 符號全掃場景下爆炸，max_pending_intents=50 截斷需監控。

---

### B-MVP-3：H1 ThoughtGate blocking + Regime 分類
**原計劃**：H1 從 advisory-only 改為 blocking gate；加入 Regime 分類邏輯

**驗收結論：⚠️ 部分通過**

**H1 ThoughtGate（blocking）：已實現 ✅**

三個 gate 均正確實現（E1-Beta Sprint 5a-3/5a-5）：

| Gate | 功能 | 降級行為 |
|------|------|---------|
| _h1_check_budget() | 每日 AI 預算門控（$2.00 硬上限，G-01 已修復） | 超限 → _heuristic_evaluate()，不 allow-all |
| _h1_complexity_score() | 複雜度評分（relevance + 多符號 + urgency） | 低複雜度跳過 AI 調用 |
| _h1_check_cooldown() | 30 秒冷卻期，symbol 粒度 | 在冷卻中 → _heuristic_evaluate() |

原則 6（失敗默認收縮）合規：所有 should_call_ai=False 路徑均走 _heuristic_evaluate()，無 allow-all。

**H1 Regime 分類：未完整實現 ⚠️**

PM 計劃中的「Regime 分類」在 Sprint 5a-3 實現中以「複雜度評分」替代，非獨立的市場 Regime 識別（多空/橫盤/高波動分類）。現有代碼中 Regime 判斷仍在 pipeline_bridge.py 的 _detect_market_regime()，未與 H1 gate 集成形成 Regime-aware 閘門。

**功能缺口（FA-6）**：H1 缺乏 Regime-aware 過濾，牛市/熊市不同策略的閾值調整邏輯尚未接入 ThoughtGate。

---

### B-MVP-4：H 鏈統一入口
**原計劃**：apply_ai_consultation() stub 廢棄 or H1-H5 接通形成統一入口

**驗收結論：✅ 通過（雙路徑均完成）**

**apply_ai_consultation() 廢棄（E1-Delta Sprint 5b-3）：**
- 添加 warnings.warn(DeprecationWarning) 標記
- AIConsultationResultData 新增 deprecation_notice Optional 字段
- 返回值含廢棄說明，指向 /phase2/strategist/intel-log
- 路由 docstring 標記 [DEPRECATED]
- 向後兼容：函數簽名不變，現有調用不崩潰

**H1-H5 接通（Sprint 5a + 5b）：**

| H 層 | 實現位置 | 狀態 |
|------|---------|------|
| H1 ThoughtGate（預算/複雜度/冷卻） | strategist_agent.py | ✅ |
| H2 預算門控注入（cost_tracker） | phase2_strategy_routes.py | ✅ |
| H3 ModelRouter（9B/27B/L2 路由） | strategist_agent.py + threading | ✅ |
| H4 AI 輸出驗證（confidence 範圍） | strategist_agent._validate_ai_output() | ✅ |
| H5 Ollama 成本追蹤（record_ollama_call） | layer2_cost_tracker.py | ✅ |

H1-H5 薄層均已接通 StrategistAgent 評估管線，形成完整 H 鏈。

---

### B-MVP-5：Ollama 調用追蹤（record_ollama_call）
**原計劃**：L1 Ollama 免費但調用次數/延遲未追蹤，補入 Layer2CostTracker

**驗收結論：✅ 通過**

實現位置（E1-Gamma Sprint 5b-2/6）：

| 新增項目 | 位置 | 功能 |
|---------|------|------|
| record_ollama_call(model, duration_ms, prompt_tokens) | layer2_cost_tracker.py | 記錄調用次數 + 延遲到記憶體 |
| get_ollama_stats() | layer2_cost_tracker.py | 返回每模型統計 |
| H5 集成調用 | strategist_agent._ai_evaluate() | 成功 eval 後 record_ollama_call("l1_9b", ...) |
| ollama_calls_tracked 計數器 | strategist_agent._stats | 可觀察 |

設計細節：_ollama_stats 懶初始化（不在 __init__），保持現有測試不破壞。

---

## 二、16 條根原則對照更新（Wave 5 後）

基準：Wave 4 完成後，CC 評定 B 級（11 完全合規，4 部分合規，1 未實施）

### 原則評級變化

| 原則 | Wave 4 狀態 | Wave 5 後 | 說明 |
|------|------------|----------|------|
| 原則 3（AI輸出≠即時命令） | 部分合規 | **升為完全合規** ✅ | G-05 修復後 ExecutorAgent 插入 acquire_lease()，H1-H5 全部接通 GovernanceHub 管線 |
| 原則 5（生存>利潤） | 完全合規 | 完全合規 ✅ | G-01 修復後每日硬上限正確為 $2.00 |
| 原則 6（失敗默認收縮） | 完全合規 | 完全合規 ✅ | H1/H4 所有失敗路徑均走 heuristic，無 allow-all |
| 原則 10（認知誠實） | 部分合規 | **升為完全合規** ✅ | roi_basis:"paper_simulation_only" 已加入所有 ROI 相關 API 回應 |
| 原則 13（AI資源成本感知） | 部分合規 | **升為完全合規** ✅ | record_ollama_call + get_cost_edge_ratio() + Layer2CostTracker 完整實現 |
| 原則 15（多 Agent 協作） | 部分合規 | **升為完全合規** ✅ | Scout→Strategist bus.send 鏈路確認 + shadow=False + ScoutWorker 30 分鐘定時掃描 |
| 原則 12（持續進化） | 未實施 | **仍為未實施** ❌ | L2 觸發機制存在，但 Perception Plane register_data() 零調用，學習管線輸入數據仍為零 |
| 原則 16（組合級風險意識） | 部分合規 | 部分合規 ⚠️ | Wave 5a Position Sizing 重構（3%/trade + 25 symbols + 智能資本再分配），但跨幣種關聯曝險監控尚未實施 |
| 原則 11（Agent 最大自主權） | 完全合規 | 完全合規 ✅ | P0/P1 硬邊界下 Agent 完全自主，未改變 |
| 原則 14（零外部成本可運行） | 完全合規 | 完全合規 ✅ | Principle 14 集成測試新增（Sprint 5b），純 L0 模式驗證通過 |

**波後評級預測：B+ 或 A-**（原則 3/10/13/15 從部分升完全，原則 12 仍是唯一未實施）

### 評級升降總結

- **升為完全合規**：原則 3、10、13、15（共 4 條）
- **保持完全合規**：原則 1、2、4、5、6、7、8、9、11、14（共 10 條）
- **保持部分合規**：原則 16
- **仍未實施**：原則 12

---

## 三、Wave 5 後功能缺口識別

### 業務鏈路完整度評估（Wave 5 後更新）

| 環節 | Wave 4 後 | Wave 5 後 | 說明 |
|------|----------|----------|------|
| 自動掃描 | 90% | **95%** | ScoutWorker 30 分鐘定時掃描 + produce_intel() 注入鏈路驗證 |
| 策略選擇 | 40% | **50%** | Strategist shadow=False + H1-H3 Model Router，但仍無 AI 驅動的策略參數優化 |
| AI 風險評估 | 55% | **75%** | H1-H5 全接通，ThoughtGate blocking + 成本追蹤 + AI 輸出驗證 + Regime 感知部分缺失 |
| 下單 | 90% | **92%** | G-05 Decision Lease 完整閉環（acquire_lease → submit_order → fail-closed） |
| 止損 | 90% | **95%** | Wave 5b：止損同步平 Demo 倉位 + 對賬引擎首次真正運行 + qty 統一 |
| 學習 | 25% | **25%** | 無改善，Perception Plane register_data() 仍為零調用 |
| 進化 | 30% | **30%** | 無改善，無策略自動優化 |
| **整體** | **~45%** | **~55%** | 明顯提升，但學習/進化環節仍是瓶頸 |

### 已識別功能缺口（FA 視角，Wave 5 後）

**FA-6【MEDIUM】：H1 缺乏 Regime-aware 過濾**
- 現有 H1 ThoughtGate 以複雜度評分決定是否調用 AI，未讀取 _detect_market_regime() 結果
- 牛市/熊市環境下，同一策略的 AI 介入閾值應不同
- 影響：AI 資源使用效率次優
- 修復方向：H1 gate 接入 PipelineBridge 的 _current_regime 狀態，調整複雜度閾值

**FA-7【BLOCKER for learning】：Perception Plane register_data() 零調用**
- 學習系統的數據輸入層（PerceptionPlane）完全未接入生產代碼
- L2 觀察觸發（observations >= 200）從未真正觸發
- 影響：原則 12 無法合規，學習/進化環節永遠停在 25-30%
- 修復方向：pipeline_bridge.py 在每個 trade 生命週期事件（open/close/stop）中調用 register_data()

**FA-8【MEDIUM】：cost_edge_ratio 數據充足性問題**
- get_cost_edge_ratio() 在 data_days < ADAPTIVE_MIN_DAYS 時返回 ratio=None（設計正確，認知誠實）
- 但 GUI 的 cost_edge_ratio 顯示未處理 None（可能顯示 "null" 或崩潰）
- 影響：Operator 無法獲得有效的 AI 成本效益評估
- 修復方向：GUI tab-ai.html 增加 N/A 顯示邏輯

**FA-9【LOW】：ScoutWorker interval 不可運行時配置**
- interval_seconds=1800 硬編碼（E2 WARN-2）
- 快速回測/測試場景無法縮短掃描間隔
- 修復方向：SCOUT_WORKER_INTERVAL_SECONDS 環境變量覆蓋（P3 優先）

**FA-10【MEDIUM】：_ollama_stats 懶初始化缺乏可觀察性**
- record_ollama_call() 首次調用前，get_ollama_stats() 返回空 dict
- GUI 學習 Tab 的 Ollama 統計在冷啟動後第一個週期不可見
- 修復方向：__init__ 中初始化 _ollama_stats = {}（E2 WARN-1）

**FA-11【P2 繼承】：executor_agent.py 動態異常字符串**
- error=f"Execution error: {e}" 在外層 exception 捕獲路徑（E2 Sprint 0 WARN）
- 違反第 Wave 3a P0-NEW-3 修復原則（異常細節不應暴露）
- 修復方向：改為固定字符串 "Internal execution error"，動態信息僅進 logger

**FA-12【LOW】：H1 冷卻字典無容量上限**
- _h1_cooldown 字典記錄每個 symbol 的最後評估時間
- 650 符號場景下記憶體可控，但長期運行後無清理機制
- 修復方向：LRU cap（建議 1000 條）或定期清理（E2 WARN-2）

---

## 四、波 5a + 5b 附加功能驗收

Wave 5 包含兩個 CLAUDE.md §三 中記錄的額外項目，非 PM 計劃 B-MVP 範圍內：

### Wave 5a：Position Sizing 重構

**驗收結論：✅ 通過**

| 項目 | 變更 | FA 確認 |
|------|------|--------|
| risk_per_trade_pct | 2% → 3% | ✅ 符合用戶偏好（memory feedback_position_sizing.md） |
| max_symbols | 10 → 25 | ✅ 符合用戶偏好 |
| 動態 qty 計算 | 啟動時鎖死 → 每次下單重算 | ✅ 正確，避免資本規模變化後 qty 過時 |
| 智能資本再分配 | 新增 Portfolio Rebalancer | ✅ 槽位滿時評估持倉保留價值，符合原則 11（Agent 自主） |
| sizing 公式 | risk/stop 反推名義金額 | ✅ 比除以 active_symbols 數更精確 |

### Wave 5b：Paper/Demo 同步修復

**驗收結論：✅ 通過（解決了長期存在的對賬引擎失效問題）**

| 修復項 | 重要性 | FA 確認 |
|--------|--------|--------|
| CRITICAL-1：止損同步平 Demo 倉位（reduce_only） | 關鍵 | ✅ 止損後 Paper/Demo 狀態不再分歧 |
| CRITICAL-2：Demo 下單失敗標記 DIVERGED | 重要 | ✅ 分歧可觀察，Operator 可干預 |
| CRITICAL-3：reconcile() 參數名 + dataclass→dict | 關鍵 | ✅ 對賬引擎首次真正運行（之前因 TypeError 從未成功） |
| MOD-4：round_qty_for_exchange() 共用函數 | 中等 | ✅ qty 一致性保證 |
| MOD-5：_on_position_open() 用 actual_qty | 中等 | ✅ 條件止損單 qty 與 Demo 對齊 |

---

## 五、下一步功能規格建議

### P3 批次優先功能（GUI 術語友好化）

**FA 視角驗收標準建議**：

1. **術語友好化（P3-GUI-1）**
   - 驗收標準：GUI 中 SM-01/SM-02/SM-04/EX-04/Decision Lease 等工程術語全部替換為中文操作員語言
   - 可接受範圍：系統設置 Tab 可保留技術術語（面向工程師），交易 Tab / 風控 Tab 不可
   - 測試方法：A3（UX Auditor）逐 Tab 驗收，評分 ≥ 7.5/10（當前 6.2/10）

2. **學習系統英文化修復（P3-GUI-2）**
   - 驗收標準：學習 Tab 6 個核心指標全部提供中文標籤（可保留英文原名作括注）
   - 測試方法：非技術背景 Operator 能理解每個指標的含義

### Phase 1 Batch 1B 功能規格

**FA 驗收標準建議（來自 287-Spec Gap 分析）**：

**Batch 1B-1：Cooldown 聯動**
- 驗收標準：RiskManager 觸發 cooldown 事件後，H0Gate.update_risk() 接收並反映在下一次 H0Gate.check() 結果
- 邊界用例：cooldown 期間 H0Gate 不應允許同方向的新 TradeIntent
- 測試要求：至少 5 個集成測試（trigger → gate → blocked 全鏈）

**Batch 1B-2：M-of-N 簽名驗證**
- 驗收標準：高金額訂單（> $100）需要 M-of-N Operator 確認方可通過 GovernanceHub
- 邊界用例：N 個簽名者全部不響應時，系統走 fail-closed（不執行，不掛起）
- 測試要求：timeout 路徑 + 簽名不足路徑 + 正常路徑

**Batch 1B-3：數據品質降級**
- 驗收標準：KlineManager 檢測到數據品質不足（< 3 天）時，自動降低 risk_per_trade_pct
- 邊界用例：品質恢復後，風控參數應自動恢復（不永久降級）
- 測試要求：mock data_days=1 → 驗證 risk_pct 降低；mock data_days=10 → 驗證恢復

### Phase 2 學習管線修復（FA 最高優先建議）

**FA-7 修復是 Phase 2 前置條件**，在學習管線輸入數據不為零之前，Phase 2 的任何工作都是在空轉：

- **FA 驗收標準**：pip_bridge.py 在 position_close 事件發生後，PerceptionPlane.register_data() 有真實調用
- **可觀察性要求**：L2 observation count 在一個交易週期後至少遞增 1
- **回歸測試**：test_perception_plane_register_data_on_trade_close（至少 3 個場景）

---

## 六、總結

### Wave 5 總體功能驗收：✅ 條件通過

5 個 B-MVP 核心項目：4 個完全通過，1 個部分通過（B-MVP-3 Regime 分類未完整實現）。

兩個 Sprint 0 前置阻塞項（G-01 $15→$2、G-05 acquire_lease）均已修復，原則 3 從部分合規升為完全合規。

測試基準從 2555 升至 2610（+55 個新測試），覆蓋了完整的 H1-H5 管線、ScoutWorker、H0Gate blocking、shadow=False、Decision Lease 等核心路徑。

### 業務功能可用度

| 時間點 | 估計值 |
|--------|--------|
| Wave 4 完成後 | ≈ 45% |
| Wave 5 完成後 | **≈ 55%** |
| 達到 80%+ 需完成 | Phase 2 學習管線（FA-7 + L3-L5）+ 策略 Alpha 驗證 |

### 關鍵瓶頸（FA 最終判斷）

1. **學習環節（25%）是整體業務鏈路的最大瓶頸**：所有後續進化能力都依賴此環節輸入真實數據
2. **Regime-aware H1（FA-6）**：當前 H1 以複雜度替代 Regime，是策略選擇層（50%）提升的限制因素
3. **Paper Trading 觀察期（尚未開始計時）**：21 天觀察期是進入 Supervised Live Gate 的必要條件，越早讓觀察期開始越好

---

*FA 簽字：已閱讀所有參考文件（PM Wave 5 計劃 + CC/E1/E2 記憶 + 各 Sprint 報告），本報告結論基於代碼審計事實，非架構假設。*
