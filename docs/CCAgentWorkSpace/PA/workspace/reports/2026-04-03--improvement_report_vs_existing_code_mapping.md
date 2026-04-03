# PA 映射分析：V3 改善報告 vs 現有代碼

**日期**: 2026-04-03
**分析對象**: `docs/references/2026-04-03--openclaw_improvement_report_v3_final.md`
**方法**: 逐模組搜索現有代碼，比對功能覆蓋度

---

## 一、模組映射總表

| # | 報告模組 | 報告 Phase | 報告估時 | 現有對應 | 狀態 | 實際工作量 | 備註 |
|---|---------|-----------|---------|---------|------|-----------|------|
| 1 | **PositionSizer** (§5.1) | 1.1 | 1d | `strategy_auto_deployer._compute_qty()` + `stop_manager.compute_atr_position_size()` | 🔧 需擴展 | 0.5d | Kelly fraction 和 risk parity 需新增，ATR-based 和 risk% 已有 |
| 2 | **StrategyHealthMonitor** (§5.2) | 1.2 | 1d | `strategy_auto_deployer._consecutive_losses` + `paper_live_gate._check_consecutive_losses()` | 🔧 需擴展 | 0.5-1d | 連續虧損追蹤已有，CUSUM + rolling Sharpe/win_rate 需新增 |
| 3 | **EWMAVolEstimator** (§5.3) | 1.3 | 0.5d | 無 | 🆕 全新 | 0.5d | 估時合理。indicator_engine 有 EMA 但無 EWMA 波動率 |
| 4 | **Hurst Exponent** (§5.4) | 1.4 | 0.5d | 無 | 🆕 全新 | 0.5d | 估時合理。純數學函數，代碼已在報告中寫好 |
| 5 | **HedgingEngine** (§5.5) | 3.4 | 1.5d | `funding_rate_arb.py` (delta-neutral 雙腿) | 🔧 需擴展 | 1d | FundingRateArb 已有 delta-neutral，但無通用 portfolio delta 計算 |
| 6 | **PnLAttributor** (§5.6) | 3.5 | 2d | `trade_attribution.py` (958 行) | ⚠️ 衝突 | 0.5d | **已有更複雜的 TradeAttributionEngine（6 因子分解: timing/direction/regime/risk/execution/luck）**，報告的簡版反而是降級 |
| 7 | **ContextDistiller** (§4.2) | 2.8 | 1d | 無 | 🆕 全新 | 1d | 估時合理。API 調用時的上下文壓縮 |
| 8 | **APIBudgetManager** (§4.4) | 3.1 | 1.5d | `layer2_cost_tracker.py` (674 行) + `h1_thought_gate.py` | 🔧 需擴展 | 0.5d | **已有日預算（$2 hard cap）+ H1 budget gate + 持久化**。缺月度預算和 L1.5/L2 分 tier 冷卻 |
| 9 | **LocalLLMClient 抽象** (§4.5) | 1.8 | 0.5d | `ollama_client.py` (506 行, OllamaConfig + OllamaClient) | 🔧 需擴展 | 0.5d | Ollama 實現完整（generate/chat/is_available），缺 ABC 抽象和 LM Studio 適配 |
| 10 | **Strategist 雙軌** (§3.3) | 2.7 | 2d | 無（RiskManager 有 pressure/suggestion 但無快速通道） | 🆕 全新 | 2d | 估時合理。需在 StrategistAgent 內新增 emergency_mode + priority queue |
| 11 | **四階段放權** (§2) | 3.7 | 2d | `paper_live_gate.py` (PaperLiveGateConfig 11 項評估) + GovernanceHub SM-01 授權 | 🔧 需擴展 | 1.5d | PaperLiveGate 做二元（通過/不通過），報告要四階段遞進（監控→P2調參→完整P2→策略創造）+ 自動降級 |
| 12 | **Paired Execution** (§3.5) | 2.4 | 4d | `funding_rate_arb.py` 雙腿 intent（perp + spot） | 🔧 需擴展 | 3d | 已有同時生成兩腿 intent 的邏輯，但無原子提交/回滾/部分成交處理 |
| 13 | **Kill Switch** (§1.2) | — | — | `bybit_local_risk_envelope_gate.py` KILL_SWITCH_ENV | ✅ 已有 | 0 | 環境變量 kill switch 已實現，blocking_reasons 中會阻止 |
| 14 | **Risk Governor** (§9 圖) | — | — | `risk_manager.py` pressure-based suggestion（normal/caution/reduce_activity）+ GovernanceHub risk levels | 🔧 需擴展 | 1d | 已有壓力→建議映射，但不是報告要的 DEFENSIVE/CIRCUIT_BREAKER 四級分層 + 自動動作 |
| 15 | **Indicator Engine 擴展** (§6.6) | 1.5 | 1.5d | `indicator_engine.py` (461 行) 已有 ATR/RSI/MACD/BB/SMA/EMA/Stoch | 🔧 需擴展 | 1.5d | 缺 KAMA/ADX/Donchian/Volume Ratio，需各寫獨立 indicator |
| 16 | **策略升級 V2** (§6.1-6.5) | 2.1-2.5 | 9.5d | 5 個策略各已有 V1 | 🔧 需擴展 | 8d | MA→KAMA+ADX; BB→RSI+Regime; Funding→Paired; Grid→OU。每個需 Paper 驗證 |
| 17 | **Regime Detection 升級** (§2.6) | 2.6 | 2d | `analyst_agent.py` 有 regime 字段 + `strategist_agent._apply_regime_weights()` | 🔧 需擴展 | 1.5d | 已有 regime→策略權重映射，缺 Hurst-based 確認 + HurstHysteresis 滯後保護 |
| 18 | **學習反饋閉環修復** (§7) | 1.6 | 0.5d | `strategist_agent._apply_pattern_insight()` 已定義 | ⚠️ 衝突 | 0.5d | **P0-GAP-1 已記錄**：方法存在但從未在決策路徑被調用。報告正確識別了這個 gap |
| 19 | **Evolution→Deploy** (§7) | 1.7 | 0.5d | `strategy_auto_deployer.apply_evolution_result()` + `evolution_routes.py` 自動觸發 | ✅ 已有 | 0 | **Wave 8B 已接通**（B13 連接），Sharpe>1.0 自動 apply |
| 20 | **影子決策追蹤** (§1.9) | 1.9 | 0.5d | `shadow_decision_builder.py` + paper_trading_engine shadow_decisions 列表 | 🔧 需擴展 | 0.5d | 已有 shadow decision 基礎設施，缺階段 1 退出條件所需的「影子 Sharpe > 實際 80%」追蹤 |
| 21 | **Strategist Prompt 模板** | 2.9 | 1.5d | StrategistAgent 使用 Ollama 但 prompt 是硬編碼 | 🔧 需擴展 | 1.5d | 估時合理 |
| 22 | **OB Imbalance + Orderbook WS** | 3.6 | 2d | `bybit_public_microstructure_builder.py` 有 orderbook 相關 | 🔧 需擴展 | 2d | 有 microstructure 基礎，缺 WS 實時訂閱和 imbalance 計算 |
| 23 | **Claude API Client** | 3.1 | 1.5d | `layer2_engine.py` 已有 Claude API 調用 | 🔧 需擴展 | 0.5d | L2 引擎已接 Claude，缺獨立客戶端 + L1.5 Sonnet 路由 |
| 24 | **L1→L2 路由** | 3.2 | 1d | `h3_model_router` (complexity→model) + `layer2_engine` | 🔧 需擴展 | 0.5d | 三級路由已有（l1_9b/l1_27b/l2），缺 L1.5 Sonnet 中間層 |
| 25 | **Claude→TSR 閉環** | 3.3 | 1d | TSR + L2 engine 各自存在但未互通 | 🆕 全新 | 1d | Claude 輸出→TSR register 路徑確實不存在 |

---

## 二、匯總統計

| 狀態 | 數量 | 報告估時合計 | 實際估時合計 |
|------|------|------------|------------|
| ✅ 已有 | 2 | ~0.5d | 0d |
| 🔧 需擴展 | 16 | ~26.5d | ~17.5d |
| 🆕 全新 | 5 | ~5d | ~5d |
| ⚠️ 衝突 | 2 | ~2.5d | ~1d |
| **合計** | **25** | **~36d** | **~23.5d** |

**結論：報告估 36 工作日，實際需 ~24 工作日（節省 ~33%）**。主要節省來自報告低估了現有系統的成熟度。

---

## 三、關鍵衝突分析

### 衝突 1：PnLAttributor vs TradeAttributionEngine

報告 §5.6 的 `PnLAttributor` 是簡單的三維聚合（by_strategy / by_symbol / by_hour）。
現有 `trade_attribution.py`（958 行）是完整的六因子歸因引擎：timing_skill / direction_skill / regime_awareness / risk_management / execution_quality / luck。

**決策建議**：不實現報告的簡版。在現有 TradeAttributionEngine 上增加聚合視圖 API 即可。

### 衝突 2：學習反饋閉環

報告 §7 指出 TSR insights 需注入 `_make_shadow_decision()` 的 confidence 調整。
實際上 `_apply_pattern_insight()` 已存在於 StrategistAgent 中，問題是**調用路徑斷開**（P0-GAP-1 已記錄）。修復的是接線問題而非重新設計。

**決策建議**：修 P0-GAP-1 即可，不需要報告描述的重新設計。

---

## 四、關鍵整合風險

### 4.1 數據流差異

| 報告假設 | 實際數據流 | 風險 |
|---------|-----------|------|
| Strategist 從 PositionSizer 讀 qty 建議 | 當前 deployer._compute_qty() 在部署時計算 | PositionSizer 需注入 StrategistAgent，非 deployer |
| EWMAVol 持續更新 | 當前無 tick-level 回報率計算 | 需在 pipeline_bridge.on_tick() 中注入更新點 |
| Hurst 每 100 bars 更新 | 當前無觸發點 | 需掛 indicator_engine 的 kline_close 回調 |
| StrategyHealthMonitor 收到每筆交易回報 | 當前 round_trip emit 給 learning pipeline | 需在 _emit_round_trip 後補一個 health_monitor.update() 調用 |

### 4.2 文件大小限制風險

| 文件 | 當前行數 | 報告新增會影響 | 風險 |
|------|---------|-------------|------|
| `risk_manager.py` | 1633 行 | Risk Governor 升級 | **超 1200 行硬上限**。需先拆分再增強 |
| `trade_attribution.py` | 958 行 | PnLAttributor（建議不做） | 接近 800 行警告線 |
| `strategist_agent.py` | ~780 行（Wave 8C 剛拆完） | 雙軌 + prompt 模板 | 可能再超 800 行警告線 |
| `pipeline_bridge.py` | 已拆子方法 | EWMAVol/Hurst/Health 注入 | setter 數量持續增長，考慮 plugin 模式 |

### 4.3 架構層衝突

1. **Risk Governor vs RiskManager**：報告要 DEFENSIVE/CIRCUIT_BREAKER 四級自動動作（reduce_all 50%/close_all），現有 RiskManager 只做 suggestion（advisory）。如果改為自動執行，需要走 Strategist→Guardian→Executor 管線，不能繞過原則 3（AI 輸出 ≠ 即時命令）。但報告明確說這是「硬性層，不經 Agent」——**這和原則 3 有張力**。建議：Risk Governor 自動動作限定在 P0 級（kill switch 級別），P1 以下仍走 Agent。

2. **Strategist 快速通道**：報告的 MappingProxyType 保護 + emergency_mode 原子標誌設計合理，但當前 StrategistAgent 是單線程（on_message 同步處理）。如果要真正並發快速/正常通道，需要改為 async 或雙線程架構。

3. **APIBudgetManager vs Layer2CostTracker**：不應新建 APIBudgetManager，應擴展現有 Layer2CostTracker。它已有日預算、持久化、cost_edge_ratio 計算。加月度重置 + tier 分離冷卻即可。

---

## 五、Phase 優先級重排建議

報告的 Phase 1-3 順序基本合理，但有調整空間：

### 最高 ROI（先做）
1. **學習反饋閉環修復**（1.6，0.5d）— P0-GAP-1 修復，接通已有的 _apply_pattern_insight
2. **EWMAVolEstimator**（1.3，0.5d）— 全新但代碼已寫好，直接用
3. **Hurst Exponent**（1.4，0.5d）— 同上
4. **Indicator Engine 擴展**（1.5，1.5d）— ADX/KAMA 是策略 V2 的前置
5. **PositionSizer 擴展**（1.1，0.5d）— 在現有 _compute_qty 上加 Kelly

### 中等 ROI
6. **StrategyHealthMonitor CUSUM**（1.2，0.5-1d）
7. **Regime Detection + Hurst 整合**（2.6，1.5d）
8. **MA_Crossover V2**（2.1，3d）— 最常用策略，優先升級
9. **四階段放權框架**（3.7，1.5d）— 治理進化必要

### 低 ROI 或可推遲
10. **Strategist 雙軌**（2.7，2d）— 高複雜度，Demo 階段不急
11. **Paired Execution**（2.4，3d）— funding arb 已有雙腿，原子回滾可後補
12. **OB Imbalance + WS**（3.6，2d）— P2 功能
13. **HedgingEngine**（3.4，1d）— P2 功能

---

## 六、結論

1. 報告的架構設計質量高（Agent-Centric 工具箱、雙層決策、四階段放權），但**高估了需要從頭建的工作量**。
2. 25 個模組/功能中，2 個已有、16 個需擴展、5 個全新、2 個有衝突。
3. 最大的風險不是代碼量而是**整合複雜度**——新模組的數據注入點分散在 pipeline_bridge/strategist/indicator_engine/risk_manager 四個地方。
4. **risk_manager.py 已超 1200 行硬上限**，任何新增功能前必須先拆分。
5. 報告的 PnLAttributor 是現有 TradeAttributionEngine 的降級版本，建議跳過。
6. 報告的 APIBudgetManager 應合併到現有 Layer2CostTracker，不另建模組。
