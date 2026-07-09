# FA 審計報告：Rust 遷移方案文件覆蓋完整性

**日期**: 2026-04-03
**審計對象**: `docs/references/2026-04-03--rust_migration_master_plan_v2.md` §2.4
**審計範圍**: app/ (79 files) + local_model_tools/ (26 files) = 105 個 Python 文件
**發現**: 36 個文件未被分類（app/ 9 個 + local_model_tools/ 17 個 + indicators/ 8 個 + strategies/ 2 個）

---

## 一、遺漏文件完整清單

### app/ 目錄遺漏（9 個）

| 文件 | 行數 | 用途 | 建議歸屬 | 理由 |
|------|------|------|----------|------|
| `__init__.py` | 1 | 包聲明 | **完全保留** | 1 行，Python 包必需，Rust 不影響 |
| `_path_setup.py` | 46 | sys.path 注入，使 route 能 import local_model_tools | **完全保留** | 純基礎設施，Python 側仍需要引用 local_model_tools（學習/進化模組保留） |
| `lease_ttl_config.py` | 470 | SM-02 租約 TTL 配置 SSOT + 驗證器 + 審計 | **部分瘦身** | TTL 數值定義遷移到 Rust `types/config.rs`，Python 側保留驗證器和審計報告功能供 GUI 使用 |
| `main_legacy.py` | 422 | FastAPI 核心單例（settings / app / limiter） | **完全保留** | Python 進程的核心入口，所有 route 依賴此文件，不涉及交易路徑 |
| `main_snapshot_stable.py` | 14 | 兼容性入口，re-export main.app | **完全保留** | 14 行兼容層，無計算邏輯 |
| `market_regime.py` | 586 | MarketRegime 枚舉 + 多時框檢測 + RegimeTracker | **部分瘦身** | 純計算部分（regime 檢測算法）遷移到 Rust `core/cognitive.rs`；枚舉定義和 Tracker 歷史查詢保留供 AI Agent 使用 |
| `paper_trading_metrics.py` | 438 | 勝率/回撤/Sharpe/盈虧比計算 | **完全保留** | 純讀取函數，從 PaperState 計算統計指標，供 GUI 和 Beta 評估。無寫入、無交易路徑依賴 |
| `runtime_bridge.py` | 186 | Runtime 快照橋接層，讀取外部 JSON 快照 | **修改 Python** | 遷移後需改為通過 IPC 從 Rust Engine 讀取狀態，取代文件讀取方式 |
| `strategist_models.py` | 167 | StrategistAgent 資料模型 + 啟發式評估 | **完全保留** | 純數據定義 + 純函數，依賴 multi_agent_framework（部分瘦身但保留 enum/dataclass），不涉及交易路徑 |

### local_model_tools/ 根目錄遺漏（4 個）

| 文件 | 行數 | 用途 | 建議歸屬 | 理由 |
|------|------|------|----------|------|
| `__init__.py` | 22 | 包聲明 + 安全不變量注釋 | **完全保留** | 包結構必需 |
| `cost_gate.py` | 185 | 成本感知入場門檻（ATR% vs 手續費） | **完整刪除** | 純確定性規則，屬於交易路徑的入場過濾。遷移到 Rust `core/risk.rs` 中的 cost_gate 子模組 |
| `evolution_engine.py` | 567 | 策略參數網格搜索優化引擎 | **完全保留** | 依賴 backtest_engine（部分瘦身後保留空殼或改為 IPC 調用）。原則 7 隔離設計，僅在回測沙箱中運行，不接觸交易路徑 |
| `market_scanner.py` | 335 | 全市場掃描器（Bybit REST API 掃描 ticker） | **完全保留** | 使用 Bybit REST API（urllib），不依賴任何待刪除模組。為 Scout/StrategyAutoDeployer 提供機會發現 |
| `strategy_auto_deployer.py` | 932 | 自動部署策略實例 | **部分瘦身** | 策略實例化邏輯（import strategies/*）遷移後需改為通過 IPC 發送部署指令到 Rust Engine。保留部署決策邏輯和停用判斷 |

### local_model_tools/indicators/ 遺漏（8 個）

| 文件 | 行數 | 用途 | 建議歸屬 | 理由 |
|------|------|------|----------|------|
| `__init__.py` | 21 | 指標包聲明，re-export 全部指標類 | **完整刪除** | 隨 indicator_engine 一起遷移，Rust `core/indicators.rs` 覆蓋 |
| `base.py` | 89 | 指標抽象基類（ABC） | **完整刪除** | Rust 用 trait 替代，遷移到 `core/indicators.rs` |
| `atr.py` | 222 | ATR 計算 | **完整刪除** | 遷移到 Rust `core/indicators.rs` |
| `bollinger_bands.py` | 177 | 布林帶計算 | **完整刪除** | 遷移到 Rust `core/indicators.rs` |
| `macd.py` | 168 | MACD 計算 | **完整刪除** | 遷移到 Rust `core/indicators.rs` |
| `moving_averages.py` | 261 | SMA/EMA 計算 | **完整刪除** | 遷移到 Rust `core/indicators.rs` |
| `rsi.py` | 194 | RSI 計算 | **完整刪除** | 遷移到 Rust `core/indicators.rs` |
| `stochastic.py` | 140 | 隨機振盪指標計算 | **完整刪除** | 遷移到 Rust `core/indicators.rs` |

### local_model_tools/strategies/ 遺漏（2 個）

| 文件 | 行數 | 用途 | 建議歸屬 | 理由 |
|------|------|------|----------|------|
| `__init__.py` | 16 | 策略包聲明 | **完整刪除** | 隨策略文件一起遷移 |
| `base.py` | 392 | StrategyBase 抽象基類（生命週期、狀態管理） | **完整刪除** | Rust 用 trait 替代，遷移到 `engine/strategies/mod.rs` |

---

## 二、遺漏文件行數統計

| 歸屬類別 | 文件數 | 行數 | 方案原始行數 | 修正後行數 |
|----------|--------|------|-------------|-----------|
| 完整刪除（新增） | 11 | 1,690 | ~12,000 | ~13,690 |
| 部分瘦身（新增） | 3 | 1,988 | ~4,500 | ~6,488 |
| 完全保留（新增） | 8 | 1,650 | 未計 | +1,650 |
| 修改 Python（新增） | 1 | 186 | ~1,500 | ~1,686 |
| **遺漏合計** | **23** | **5,514** | | |

> 注：indicators/ 下 8 個文件合計 1,272 行，strategies/ 下 2 個文件合計 408 行。
> 方案 §2.4 用 `local_model_tools/strategies/*.py（5 個策略文件）` 概括了 5 個具體策略，但遺漏了 `base.py` 和 `__init__.py`。
> 方案完全未提及 `indicators/` 子目錄，但 §2.1 提及 indicator_engine.py 包含 "7 指標"，實際上這些指標實現在獨立文件中。

---

## 三、依賴斷裂修復方案

### 3.1 已分類文件的依賴斷裂（方案已知，需明確修復策略）

| 保留/瘦身的文件 | 依賴的刪除文件 | 斷裂類型 | 修復方案 |
|----------------|--------------|----------|---------|
| `governance_hub.py`（部分瘦身） | `authorization_state_machine.py` | 類導入（AuthorizationStateMachine） | **(c) 保留 Python 枚舉/常量定義薄文件**：只保留 enum + dataclass 供 Python 側使用，狀態機邏輯由 Rust 擁有，Python 讀取狀態通過 IPC |
| `governance_hub.py`（部分瘦身） | `risk_governor_state_machine.py` | 枚舉導入（RiskLevel, RiskInitiator） | **(b) 保留 Python 薄包裝**：提取 RiskLevel/RiskInitiator 枚舉到 `types/` 共享模組，兩側共用 |
| `governance_hub.py`（部分瘦身） | `decision_lease_state_machine.py` | 類導入（DecisionLeaseStateMachine） | **(c) 同 authorization_state_machine 方案** |
| `governance_hub.py`（部分瘦身） | `oms_state_machine.py` | 枚舉導入（OrderState, OrderInitiator） | **(b) 保留 Python 薄包裝**：提取枚舉到共享模組 |
| `governance_routes.py`（修改） | `risk_governor_state_machine.py` | 枚舉導入（RiskLevel, RiskInitiator） | **(b) 同上，使用共享枚舉模組** |
| `paper_trading_engine.py`（部分瘦身） | `oms_state_machine.py` | 類+枚舉導入 | **(b) 共享枚舉 + IPC 讀取 OMS 狀態** |
| `paper_trading_routes.py`（修改） | `market_data_dispatcher.py` | 類導入（MarketDataDispatcher） | **(a) 改為 IPC 讀取**：route 通過 IPC 從 Rust Engine 獲取 dispatcher 狀態 |
| `paper_trading_routes.py`（修改） | `h0_gate.py` | 類導入（H0Gate, H0HealthWorker） | **(a) 改為 IPC 讀取**：H0 狀態從 Rust 推送，Python 只讀 |
| `paper_trading_routes.py`（修改） | `oms_state_machine.py` | 枚舉導入 | **(b) 共享枚舉模組** |
| `phase2_strategy_routes.py`（修改） | `pipeline_bridge.py` | 類導入（PipelineBridge） | **(a) 改為 IPC**：策略控制指令通過 IPC 發送到 Rust Engine |
| `phase2_strategy_routes.py`（修改） | `oms_state_machine.py` | 類導入（OMSStateMachine） | **(a) IPC + (b) 枚舉薄包裝** |
| `phase2_strategy_routes.py`（修改） | 全部 local_model_tools 刪除模組 | 6 個直接導入 | **(a) 完全改為 IPC**：所有策略/指標/信號操作由 Rust 處理，route 只做 IPC 轉發 |
| `risk_manager.py`（部分瘦身） | `h0_gate.py` | 數據類導入（H0GateRiskSnapshot） | **(b) 薄包裝**：將 H0GateRiskSnapshot dataclass 提取到共享類型模組 |

### 3.2 遺漏文件的依賴斷裂（新發現）

| 保留/瘦身的文件 | 依賴的刪除文件 | 斷裂類型 | 修復方案 |
|----------------|--------------|----------|---------|
| `grafana_data_writer.py`（完全保留） | `kline_manager` + `pipeline_bridge`（構造函數注入） | 運行時依賴（Any 類型） | **(a) 改為 IPC 讀取**：健康狀態數據從 Rust Engine 的 state_update 推送中獲取。構造函數改接 IPC client |
| `strategy_auto_deployer.py`（部分瘦身） | `strategies/*.py`（5 個策略 import） | 延遲導入 | **(a) 改為 IPC**：部署指令通過 IPC 發送，策略實例化在 Rust 側完成 |
| `strategy_auto_deployer.py`（部分瘦身） | `kline_manager`（構造函數注入） | 運行時依賴 | **(a) 改為 IPC**：K 線數據通過 IPC 從 Rust 讀取 |
| `evolution_engine.py`（完全保留） | `backtest_engine.py`（部分瘦身→空殼或刪除） | 直接 import | **(a) 改為 IPC**：回測請求發送到 Rust Engine，結果通過 IPC 返回。或 **(b) 保留 Python backtest_engine 薄包裝**，內部通過 IPC 調用 Rust 回測 |

### 3.3 建議：新增共享枚舉模組

多個斷裂的根因是 Python 側仍需使用 Rust 側的枚舉/數據類。建議新增：

```python
# app/shared_types.py（~200 行）
# 從各刪除文件提取的枚舉和數據類，供 Python 側使用

class RiskLevel(str, Enum): ...          # 原 risk_governor_state_machine.py
class RiskInitiator(str, Enum): ...      # 原 risk_governor_state_machine.py
class OrderState(str, Enum): ...         # 原 oms_state_machine.py
class OrderInitiator(str, Enum): ...     # 原 oms_state_machine.py
class H0GateRiskSnapshot: ...            # 原 h0_gate.py
# ... 其他需要的類型
```

這比保留多個空殼文件更乾淨。Python 枚舉值必須與 Rust `openclaw_types` 中的定義完全對齊。

---

## 四、測試影響評估

### 4.1 按刪除模組統計

| 刪除模組 | 關聯測試文件數 | 影響級別 |
|----------|-------------|---------|
| pipeline_bridge | 28 | **極高** — 最多測試依賴，含多個 integration test |
| kline_manager | 23 | **極高** — 指標/策略/回測測試鏈的起點 |
| indicator_engine | 18 | **高** — 所有策略測試間接依賴 |
| stop_manager | 14 | **高** — 風控相關測試鏈 |
| h0_gate | 8 | **中** — 有專門的 unit + integration test |
| authorization_state_machine | 7 | **中** |
| decision_lease_state_machine | 7 | **中** |
| risk_governor_state_machine | 7 | **中** |
| signal_generator | 5 | **中** |
| oms_state_machine | 5 | **中** |
| strategy_orchestrator | 4 | **低** |
| market_data_dispatcher | 2 | **低** |
| bybit_public_ws_listener | 2 | **低** |

**去重後受影響的測試文件總數**：53 個（部分文件依賴多個刪除模組）

### 4.2 修復策略

| 策略 | 適用場景 | 預估工作量 |
|------|---------|-----------|
| **刪除並重寫為 Rust 測試** | 純計算測試（指標/信號/K線/狀態機） | ~30 個，Week 3-8 隨 Rust 開發同步 |
| **改為 IPC 集成測試** | Pipeline/Engine 端到端測試 | ~15 個，Week 9-10 灰度期 |
| **保留但 mock 替換** | Python 側測試依賴已刪除模組的 mock | ~8 個，Week 9 Python 改造時 |

### 4.3 灰度期測試保障

方案 §5.2 已定義影子進程保留模組，在灰度期（Week 9-10）原 Python 測試仍可運行。灰度結束後再正式刪除。

---

## 五、FA 結論與建議

### 5.1 方案 §2.4 修正建議

1. **indicators/ 子目錄必須補入「完整刪除」清單**（8 個文件，1,272 行）。方案提及 indicator_engine 但漏掉了實際的指標實現文件。

2. **strategies/base.py 和 strategies/__init__.py 必須補入「完整刪除」清單**（2 個文件，408 行）。方案寫 `strategies/*.py（5 個策略文件）` 但實際有 7 個文件。

3. **cost_gate.py 必須補入「完整刪除」清單**（185 行），其為 Batch 9A 新增的確定性入場門檻，完全屬於交易路徑。

4. **新增 3 個「部分瘦身」文件**：lease_ttl_config.py、market_regime.py、strategy_auto_deployer.py。

5. **新增 1 個「修改 Python」文件**：runtime_bridge.py（需改為 IPC 讀取）。

6. **方案應新增 `app/shared_types.py`（~200 行）到「新增 Python」清單**，作為 Python 側的枚舉/數據類共享模組。

### 5.2 Rust 行數修正

```
原方案：  core ~7,080 + engine ~5,600 + types ~850 = ~13,530 行
修正後：  core ~7,080 + engine ~5,600 + types ~850 + indicators ~1,272 = ~13,530 行
          （indicators 實現已被 core/indicators.rs ~500 行包含，但源碼實為 1,272 行）
```

indicators.rs 估計 ~500 行偏低。7 個指標類的 Python 實現共 1,272 行，即使 Rust 更緊湊，至少需要 ~700-800 行。

### 5.3 風險提示

- **pipeline_bridge 是最高風險刪除目標**：28 個測試依賴，2,512 行，是整個交易管線的編排核心。灰度驗證必須重點覆蓋。
- **evolution_engine → backtest_engine 依賴鏈**：evolution_engine 保留但 backtest_engine 空殼化，需要明確 IPC 替代方案。
- **grafana_data_writer 的運行時注入**：使用 `Any` 類型注入 kline_manager 和 pipeline_bridge，靜態分析無法捕捉此斷裂，需運行時測試覆蓋。
