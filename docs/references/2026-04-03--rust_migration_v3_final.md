# OpenClaw Bybit — Rust 遷移總方案 V3-FINAL

**日期**: 2026-04-03
**版本**: V3-FINAL（正式執行依據）
**審查歷程**: V2 草稿 → 四角色審查 → V2.5 六路缺口修復 → V2.5 五角色嚴格論證（21 FAIL） → V3 全部納入
**目標**: Rust 為交易路徑主人，Python 退化為 AI 服務 + GUI 層
**執行方式**: 一步到位 + Week 8 硬決策點 + 灰度驗證

---

# 版本演進與修正記錄

```
V2 (2026-04-03)：初始方案
V2→V2.5 修正（四角色審查 + 六路缺口）：
  PA: 行數實測（22,850 行 vs 原估 12,000）
  FA: 23 個遺漏文件 + 22 個依賴斷裂修復
  E5: 性能數字修正（tick 0.3-1ms 非 15-60ms）
  QC: 浮點分級容差 + golden dataset
  E4: 四層測試遷移計劃
  PM: 14 週路線圖 + 風險增強

V2.5→V3 修正（嚴格論證 21 FAIL）：
  PA-1: tick owner 與 cascade worker 統一為單一 actor
  PA-3: 級聯 all-or-nothing 事務（clone+swap）
  PA-4: socket 從 /tmp 遷至 /run/openclaw/
  PA-5: engine.toml 分冷/熱參數 + SIGHUP 熱加載
  PA-6: CI JSON Schema diff 驗證 shared_types 對齊
  PA-7: Rust 崩潰時 Python 2s 止損接管協議
  FA-1: conftest SM 類→IPC mock fixture + PriceEvent 加入 shared_types
  FA-3: legacy_routes + risk_routes 補入 IPC 改造清單
  FA-4: conftest 15 處斷裂專項改造計劃
  E5-1: mmap 隔離到獨立線程
  E5-3: 刪除 SIMD 主歸因，改為消除 GIL+deepcopy+零鎖
  E5-5: tick P50 標注 Engine-internal only
  E5-6: config 更新機制 ArcSwap<Config>
  QC-1: 信號邊界豁免區按類型分別定義
  QC-2: Python math.fsum() + Rust Kahan 統一補償求和
  QC-4: 極端組指定真實歷史事件 + 人工邊界混合
  QC-5: BOUNDARY_DIVERGENCE 自動升級條件
  PM-1: 提前並行只做零依賴任務
  PM-2: 分層凍結（H0/指標 Phase 2；治理 Phase 3）
  PM-3: No-Go 復用率 ~50%，沉沒 4-5 人週
  PM-4: Phase 0-3 延期影響建模 + Week 9 硬截止
  PM-5: 灰度期確定性路徑完全 code freeze
  PM-6: Phase 0-3 交付 Paper Trading 自動監控
  PM-7: 回滾計劃（runtime <30s / 完全 <10min / W11 演練）
```

---

# 第一部分：最終目標架構

## 1.1 進程模型

```
┌──────────────────────────────────────────────────────────────┐
│  Rust 交易引擎 — openclaw_engine（獨立二進制）                 │
│  tokio async runtime · 單一進程 · 無 GC · 確定性延遲          │
│                                                               │
│  ┌─ WebSocket 層 ──────────────────────────────────────────┐ │
│  │ Bybit WS 訂閱（自己連接，不依賴 Python）                  │ │
│  │ 價格解析 → PriceEvent · 自動重連 + 心跳                   │ │
│  └──────────────────────────────────────────────────────────┘ │
│       ↓                                                       │
│  ┌─ Tick Actor（唯一 SM Owner）───────────────────────────┐  │
│  │  [V3-PA-1] 單一 actor 獨佔所有可變狀態                  │  │
│  │  mpsc channel drain 處理級聯事件 + IPC 指令              │  │
│  │                                                         │  │
│  │  注意力節流 → K 線聚合 → 13 指標 → 8 信號               │  │
│  │  → CognitiveModulator → H0 Gate → 4 SM 級聯             │  │
│  │  → Guardian → StopManager → 組合風控                     │  │
│  │  → 訂單匹配 → 執行計算 → PnL 歸因                       │  │
│  │  → OpportunityTracker 更新                               │  │
│  │                                                         │  │
│  │  每 tick 結束 → ArcSwap snapshot 更新                    │  │
│  └─────────────────────────────────────────────────────────┘  │
│       ↓                                                       │
│  ┌─ 快速通道（優先級最高，不等 AI，不經 Python）──────┐       │
│  │ Risk Governor ≥ DEFENSIVE → 預定義規則 → 直接執行   │       │
│  │ 閃崩 / 保證金危機 → 立即平倉                        │       │
│  └─────────────────────────────────────────────────────┘       │
│       ↓                                                       │
│  ┌─ AI 請求通道（異步，不阻塞 tick actor）────────────┐      │
│  │ Strategist/Analyst/Conductor AI → 發請求到 Python          │
│  │ AI 回覆 → mpsc channel → 下一 tick 周期 drain 處理        │
│  └─────────────────────────────────────────────────────────┘  │
│       ↓                                                       │
│  ┌─ 後台引擎（獨立 tokio task，低優先級）────────────┐       │
│  │ DreamEngine（閒置蒙特卡洛）· BacktestEngine           │     │
│  └─────────────────────────────────────────────────────────┘  │
│       ↓                                                       │
│  ┌─ 持久化線程（獨立，tick actor 不觸碰）────────────┐       │
│  │ [V3-E5-1] JSON debounced write / mmap                │     │
│  │ 審計：JSONL append-only                              │     │
│  └─────────────────────────────────────────────────────────┘  │
│                                                               │
│  IPC：/run/openclaw/engine.sock（[V3-PA-4]）                  │
│  JSON-RPC 2.0 雙向                                            │
└──────────────────────────────────────────────────────────────┘
        ↕ Unix domain socket
┌──────────────────────────────────────────────────────────────┐
│  Python AI + GUI 進程 — FastAPI                               │
│                                                               │
│  AI 服務：Strategist/Analyst/Conductor/Scout AI 推理          │
│  GUI：FastAPI 126+ routes · Operator 指令 → IPC 轉發          │
│  學習：TSR · ExperimentLedger · EvolutionScheduler            │
│  外部：OllamaClient · Claude API · Telegram · Grafana · Bybit│
│  治理（瘦身版）：GovernanceHub 高層業務 · 對賬 · 審計寫入     │
│  [V3-PA-7] 止損接管：Engine 心跳丟失 2s → 本地止損模組啟動   │
└──────────────────────────────────────────────────────────────┘
```

## 1.2 設計原則

1. Rust 擁有整條確定性路徑——WS 到下單，Python 不介入
2. Python 只做 AI 推理 + GUI + 學習系統 + 審計高層邏輯
3. AI 推理不阻塞 tick——請求後繼續，回覆下一周期 drain 消費
4. 兩個進程可獨立重啟——Python 掛了引擎降級 L0 繼續跑
5. 無中間態——不建 PyO3 包裝層，直接到終態（Week 8 決策點保留降級為 PyO3 的選項）
6. **[V3-PA-1] 單一 actor 模式** — tick thread 是所有可變狀態的唯一 owner，級聯/IPC 指令通過 mpsc channel 序列化

## 1.3 GovernanceHub 切分方案

### Rust（GovernanceCore）— 熱路徑 + 確定性級聯
- `is_authorized()` / `acquire_lease()` / `release_lease()`
- `_on_risk_escalation()` — risk→auth→lease→mode 級聯
- `_on_auth_frozen()` — collect lease→revoke all
- `_on_reconciliation_mismatch()` — severity→risk mapping
- `check_risk_and_act()` / `get_risk_level()` / `get_status()`

### Python（GovernanceHub 瘦身版）— 冷路徑 + I/O
- `grant_paper_authorization()` / `request_de_escalation()`
- `handle_incident_auth_action()` · Telegram · ChangeAuditLog

### 級聯 IPC 協議：1 輪 RPC（非 3-4 輪）
```
Python → risk_upgrade(event) → Rust 進程內完成整條級聯鏈
Rust → CascadeResult{auth_change, lease_revoked, mode_update} → Python
Python → 寫審計 + 推 Telegram（非阻塞）
```

### [V3-PA-3] 級聯事務一致性：All-or-Nothing
```rust
fn execute_cascade(&mut self, event: RiskEvent) -> Result<CascadeResult> {
    let snapshot = self.clone_sm_states();  // 臨時副本
    // 在副本上執行全部步驟
    snapshot.risk.escalate(event)?;
    snapshot.auth.restrict_if_needed()?;
    snapshot.lease.revoke_affected()?;
    snapshot.mode.update()?;
    // 全部成功 → commit
    self.commit_sm_states(snapshot);
    Ok(CascadeResult { ... })
    // 任一失敗 → 保持原狀 + CRITICAL alert
}
```

## 1.4 並發模型（Lock 策略）

**[V3-PA-1 統一] Tick Actor 是唯一 SM Owner：**

```
                    ┌──────────────────────────┐
                    │   Tick Actor (sole owner) │
                    │   獨立 tokio runtime      │  ← [V3-E5-4] current_thread runtime
                    │   [V3-E5-6] ArcSwap<Config>│     避免共享 runtime 調度抖動
                    ├──────────────────────────┤
  WS messages ───>  │  on_tick():              │
                    │    drain mpsc channel     │  ← cascade events + IPC commands
                    │    process tick pipeline  │
                    │    update ArcSwap snapshot│  ← GUI 零阻塞讀取
                    └──────────────────────────┘
                         │ mpsc            │ ArcSwap
  Python IPC ──────────>│             GUI/IPC 讀取
  Cascade events ──────>│             (atomic load, ~5ns)
```

| 路徑 | 機制 | 鎖數 |
|------|------|------|
| Tick 處理 | Sole owner 直接讀寫 | 0 |
| 級聯事件 | mpsc→tick drain 序列化 | 0 |
| GUI/IPC 讀取 | ArcSwap atomic load | 0 |
| Python IPC 指令 | mpsc→tick drain→oneshot 回覆 | 0 |
| Config 更新 | **[V3-E5-6]** ArcSwap\<Config\> atomic swap | 0 |
| State 持久化 | **[V3-E5-1]** 獨立線程，crossbeam channel 接收 | 0（tick 不觸碰） |

## 1.5 [V3-PA-5] 配置熱更新

| 類別 | 更新方式 | 需重啟？ |
|------|---------|---------|
| IPC 地址、crate 結構 | 修改 engine.toml 重啟 | 是 |
| cognitive / opportunity / dream 數值 | SIGHUP 或 IPC `reload_config` 指令 | 否 |
| risk 參數（max_stop_loss 等） | IPC `reload_config` 指令 | 否 |
| attention 間隔 | IPC `reload_config` 指令 | 否 |

機制：Engine 收到 SIGHUP / IPC reload → 讀 engine.toml → 構建新 Config → ArcSwap\<Config\>.store()。Tick actor 下一次迭代自動讀到新值。

## 1.6 [V3-PA-7] 崩潰止損接管協議

```
正常運行：Rust Engine 每 30s 推 heartbeat → Python watchdog 記錄
Engine 崩潰：
  T+0s    watchdog 檢測心跳丟失
  T+2s    systemd 重啟 Engine（RestartSec=2）
  T+2s    Python 同步啟動本地止損模組（保留的瘦身版 risk_manager）
  T+3-5s  Engine 重啟完成，Python 止損模組讓位
  最後防線：Bybit 交易所條件單 SL/TP（原則 9 雙重防線，Rust 遷移後仍保持同步）
```

---

# 第二部分：遷移完整清單

## 2.1 實測行數表（PA 逐文件測量）

| 源文件 | 實測行數 | Rust 目標 | 難度 |
|--------|---------|----------|------|
| pipeline_bridge.py | 2,512 | engine/tick_pipeline.rs + intent_processor.rs | 5 |
| paper_trading_engine.py | 2,243 | core/execution.rs + order_match.rs + state_compute.rs + engine/paper_state.rs | 5 |
| governance_hub.py | 1,903 | engine/governance.rs | 4 |
| risk_manager.py | 1,633 | core/risk.rs | 4 |
| backtest_engine.py | 1,352 | core/backtest.rs | 4 |
| signal_generator.py | 1,212 | core/signals.rs | 3 |
| multi_agent_framework.py | 1,104 | core/message_bus.rs | 4 |
| kline_manager.py | 1,055 | core/klines.rs | 3 |
| trade_attribution.py | 958 | core/attribution.rs | 3 |
| risk_governor_sm.py | 858 | core/sm_risk_gov.rs | 3 |
| h0_gate.py | 832 | core/h0_gate.rs | 3 |
| decision_lease_sm.py | 740 | core/sm_lease.rs | 3 |
| authorization_sm.py | 724 | core/sm_auth.rs | 3 |
| oms_sm.py | 693 | core/sm_oms.rs | 3 |
| guardian_agent.py | 580 | core/guardian.rs | 3 |
| portfolio_risk_control.py | 557 | core/portfolio.rs | 3 |
| strategy_orchestrator.py | 508 | engine/orchestrator.rs | 3 |
| indicator_engine.py + indicators/*.py(8) | 461+1,272=1,733 | core/indicators.rs | 2 |
| bybit_ws_listener.py | 460 | engine/ws_client.rs | 4 |
| market_data_dispatcher.py | 431 | engine/dispatcher.rs | 2 |
| stop_manager.py | 319 | core/stop_manager.rs | 2 |
| strategies/*.py(7) | 1,699 | engine/strategies/*.rs | 2 |
| cost_gate.py | 185 | core/risk.rs（子模組） | 2 |
| **待遷移總計** | **22,850** | | |

## 2.2 Rust 行數預算（E5 計算）

| Crate | 對應模組 | Rust 行 |
|-------|---------|---------|
| openclaw_types | 全部類型/enum/struct + serde | 4,500 |
| openclaw_core | 風控/門控/SM/計算 | 8,700 |
| openclaw_engine | 交易引擎主體 | 13,800 |
| 測試代碼 | 單元+集成+property | 5,500 |
| **總計** | | **32,500** |

> 注：V2 的 openclaw_ffi (PyO3) 僅作為 Week 8 No-Go 降級備選，不計入主預算。

## 2.3 文件歸屬完整清單（V2 + FA 補全 23 個）

### 完整刪除（共 ~13,690 行）
```
V2 原有（15 文件）+ FA 補全（11 文件）：
  app/: pipeline_bridge · market_data_dispatcher · bybit_public_ws_listener
        h0_gate · 4 個狀態機
  lmt/: indicator_engine · signal_generator · kline_manager · stop_manager
        strategy_orchestrator · cost_gate
  lmt/indicators/: __init__ · base · atr · bollinger_bands · macd
        moving_averages · rsi · stochastic
  lmt/strategies/: __init__ · base · 5 個策略文件
```

### 部分瘦身（共 ~6,488 行 → ~2,000 行）
```
V2 原有（8 文件）+ FA 補全（3 文件）：
  risk_manager · guardian_agent · paper_trading_engine
  multi_agent_framework · portfolio_risk_control · governance_hub
  trade_attribution · backtest_engine
  lease_ttl_config · market_regime · strategy_auto_deployer
```

### 完全保留
```
V2 原有 + FA 補全（8 文件）：
  __init__ · _path_setup · main_legacy · main_snapshot_stable
  paper_trading_metrics · strategist_models · evolution_engine · market_scanner
  + 全部 Agent 文件 + 全部 routes 文件 + 全部學習/外部連接
```

### 新增 Python（~920 行）
```
ai_service.py (~500) · ipc_client.py (~300) · shared_types.py (~120)
```

### 修改 Python（~1,500 行改動）
```
main.py · runtime_bridge.py（[FA 補全]）
phase2_strategy_routes · paper_trading_routes · governance_routes
backtest_routes · legacy_routes（[V3-FA-3]）· risk_routes（[V3-FA-3]）
```

---

# 第三部分：依賴斷裂修復方案

## 3.1 修復總表（22 個斷裂 → 12 IPC + 9 shared_types + 1 部分瘦身）

| 保留文件 | 斷裂 import | 修復方案 |
|----------|------------|---------|
| governance_hub.py | AuthorizationSM, DecisionLeaseSM | IPC 替代 |
| governance_hub.py | RiskLevel, RiskInitiator | shared_types |
| governance_hub.py | OrderState, OrderInitiator | shared_types |
| governance_routes.py | RiskLevel, RiskInitiator | shared_types |
| paper_trading_engine.py | OMSStateMachine | IPC 替代 |
| paper_trading_engine.py | OrderState, OrderInitiator | shared_types |
| paper_trading_routes.py | MarketDataDispatcher, H0Gate | IPC 替代 |
| paper_trading_routes.py | H0GateConfig | shared_types |
| paper_trading_routes.py | OrderState | shared_types |
| phase2_strategy_routes.py | PipelineBridge, 全部 lmt 模組 | IPC 替代 |
| phase2_strategy_routes.py | StopConfig | shared_types |
| risk_manager.py | H0GateRiskSnapshot | shared_types |
| backtest_routes.py | BacktestEngine | IPC 替代 |
| strategy_auto_deployer.py | strategies/* 實例化 | IPC 部署指令 |
| **[V3-FA-3]** legacy_routes.py | PIPELINE_BRIDGE, _latest_prices | IPC 替代 |
| **[V3-FA-3]** risk_routes.py | RISK_MANAGER (間接) | IPC 替代 |

## 3.2 shared_types.py 設計（~120 行）

| 類型 | 種類 | 來源 |
|------|------|------|
| RiskLevel | IntEnum | risk_governor_sm.py |
| RiskInitiator | str Enum | risk_governor_sm.py |
| OrderState | str Enum | oms_sm.py |
| OrderInitiator | str Enum | oms_sm.py |
| H0GateRiskSnapshot | dataclass | h0_gate.py |
| H0GateConfig | dataclass | h0_gate.py |
| H0GateCheckResult | dataclass | h0_gate.py |
| H0GateHealthSnapshot | dataclass | h0_gate.py |
| StopConfig | dataclass | stop_manager.py |
| **[V3-FA-1]** PriceEvent | dataclass | bybit_ws_listener.py |

### [V3-PA-6] 自動對齊驗證
CI pipeline 新增步驟：
1. Rust 側：`serde_json::to_value(&MyEnum::default())` 導出 JSON Schema
2. Python 側：`pydantic` 或 `dataclasses-json` 導出 JSON Schema
3. CI diff 兩份 Schema → 不一致則 FAIL

## 3.3 [V3-FA-4] conftest.py 專項改造計劃

現有 conftest.py 有 15 處 import 指向「完整刪除」模組：
- 4 SM 類（各 2-5 處）→ **改為 IPC mock fixture**：用 `unittest.mock.MagicMock` 模擬 SM 行為，或啟動 Rust Engine 子進程
- `MarketDataDispatcher` / `BybitPublicWsListener` → **改為 IPC mock**
- `PriceEvent` → **從 shared_types 導入**（[V3-FA-1]）
- `OrderState` / `OrderInitiator` → **從 shared_types 導入**

---

# 第四部分：IPC 協議

## 4.1 通信方式
```
方式：Unix domain socket
路徑：/run/openclaw/engine.sock（[V3-PA-4]，RuntimeDirectory 保護）
協議：JSON-RPC 2.0（\n 分隔）
延遲：Engine-internal ~5-15μs / IPC 往返 ~50-100μs（[V3-E5-5]）
```

## 4.2-4.5 消息格式（同 V2，不變）

## 4.6 超時和降級
```
AI 請求 TTL：Strategist 15s · Analyst 30s · Conductor 10s
超時 → L0 確定性邏輯代替
Python 斷連 → ai_available=false → 全部 L0 · 每 5s 重連 · 告警
[V3-PA-4] socket 被刪除 → Engine 啟動時檢查並重建
           → Python ipc_client 自動重連 + exponential backoff
           → 3 次失敗 → 降級純 Python 模式
```

---

# 第五部分：灰度驗證框架

## 5.1-5.3 架構與影子進程（同 V2，不變）

## 5.4 浮點容差分級標準（QC 設計 + V3 修正）

| 類別 | 容差 | 類型 | 理由 |
|------|------|------|------|
| 簡單聚合指標（SMA/BB/ATR/Donchian/VolumeRatio） | 相對 1e-10 | 相對 | N=200 累加 ≈ 2.2e-14 |
| 遞歸指標（EMA/MACD/RSI/KAMA/ADX/EWMA Vol） | 相對 1e-8 | 相對 | 連乘累積 |
| Hurst 指數 | 絕對 1e-6 | 絕對 | log + 線性回歸 |
| 止損/止盈價格 | 相對 1e-8 或 abs 0.01 USD 取寬 | 混合 | ATR 乘法 + 低價幣保護 |
| PnL 計算 | 絕對 0.01 USD | 絕對 | 交易所結算精度 |
| H0 Gate 5 bool | **嚴格一致** | — | 安全門控 P0 |
| 狀態機轉換 | **嚴格一致** | — | 離散系統 |

### [V3-QC-1] 信號邊界豁免區（按類型分別定義）
| 信號類型 | 豁免帶 | 理由 |
|----------|--------|------|
| RSI/Stochastic 閾值類 | ±0.1% 相對閾值 | 值域 [0,100]，0.1% = ±0.03 合理 |
| MA Cross/MACD 差值類 | ±1e-8 絕對值 | 與遞歸指標容差一致 |
| ATR/BB 距離類 | ±0.01% 相對值 | 價格百分比 |

### [V3-QC-2] 補償求和統一
- **Python**：SMA 計算改用 `math.fsum()`（補償求和）
- **Rust**：SMA 使用 Kahan 補償求和
- **兩端都不用 naive sum()**

### [V3-QC-5] BOUNDARY_DIVERGENCE 自動升級
```
WARNING → FAIL 升級條件：
  連續 1h（60 個 1m tick）BOUNDARY_DIVERGENCE 率 > 5%
  OR 任意 24h 窗口累計 > 50 次
→ 自動暫停灰度 + 觸發人工審查
```

## 5.5 Golden Dataset 規格（QC 設計 + V3 修正）

| 組別 | 內容 | 數量 | 來源 |
|------|------|------|------|
| 穩態 | BTCUSDT 1m K 線 | 3000 根 (~50h)（[V3 上調]） | Phase 1 Paper Trading 自動產出 |
| 極端 | **[V3-QC-4]** 真實歷史事件 | 500 根 | 2024-08-05 日元套利平倉 / 2025-03-12 BTC 閃崩 |
| 邊界 | 人工構造閾值命中 ±1e-9 | 50 根 + 3 組特殊（price=0 / gap>10% / 連續同價 tick） | 手動構造 |

**格式**：JSONL，每行含 ts_ms / kline / indicators / signals / h0_gate / pnl_cumulative。
**對比**：Comparator 獨立進程逐行 diff → FAIL>0 阻斷放權。

## 5.6 灰度後處理
```
驗證通過 → 關閉影子進程 → git tag "pre-rust-cleanup"
→ 保留冗餘 Python 代碼 4 週 → 確認穩定後最終刪除
```

---

# 第六部分：修正後路線圖（14 週 + 提前並行）

## 6.1 [V3-PM-2] 分層凍結
| 凍結層 | 凍結時間 | 內容 |
|--------|---------|------|
| L1：H0/指標/信號/策略 | Phase 2 結束 | indicator_engine / signal_generator / h0_gate / strategies 接口 |
| L2：治理/授權/租約 | Phase 3 結束 | governance_hub / SM 接口（Phase 3 放權框架完成後） |

## 6.2 [V3-PM-1] 提前並行（僅零依賴任務）
| 任務 | 時間 | 交付物 |
|------|------|--------|
| Cargo workspace + CI | Phase 1 Day 1 | rust/Cargo.toml + GitHub Actions cargo test |
| openclaw_types crate | Phase 1 Day 3 | 全部類型編譯通過 |
| L1 接口凍結 | Phase 2 結束 | 凍結文件清單簽核 |
| L2 接口凍結 | Phase 3 結束 | 治理接口凍結 |

> [V3-PM-1] IPC echo 驗證推遲到主開發 W1（不在提前並行期間做，避免 E1 語言切換負擔）。

## 6.3 主開發 14 週

| 週 | 交付物 | Go/No-Go |
|----|--------|----------|
| **W1-2** | IPC 雙端 + shared_types + conftest 改造 + WS 連接 | IPC 1000 msg/s + shared_types CI schema diff PASS |
| **W3-4** | core 上半：indicators(13) + signals(8) + klines + h0_gate + risk + attention + cognitive + opportunity + dream | Golden Dataset 穩態組全部 PASS |
| **W5-6** | core 下半：guardian + execution + order_match + state_compute + portfolio + stop_manager + 4 SM + message_bus + attribution + backtest | SM 轉換窮舉測試 PASS + Golden Dataset 極端組 PASS |
| **W7-8** | engine：tick_pipeline + intent_processor + orchestrator + strategies(5) + governance + paper_state + persistence + audit + fast_track | **Week 8 硬決策點** |
| **W9-10** | Python 改造（7 route 文件 IPC + runtime_bridge + conftest） + IPC 集成測試 | IPC 集成 60 個全 PASS |
| **W11-12** | 灰度驗證（雙寫雙算）+ **[V3-PM-7] W11 回滾演練** | CRITICAL=0 + WARNING<10 連續 7 天 |
| **W13-14** | 穩定觀察 + 冗餘清理 | tag pre-rust-cleanup |

### Week 8 硬決策點（[V3-PM-3]）
- **Go**：Engine 獨立跑完整 Paper Trading → 繼續 W9-14
- **No-Go**：降級 PyO3 方案。**復用率 ~50%**（types + indicators + signals + klines 可復用，engine 層 ~50% 廢棄，沉沒成本 4-5 人週）

### [V3-PM-5] 灰度期凍結規則
- W11-12 期間 Python 確定性路徑**完全 code freeze**
- 僅允許 bug fix（需 E2 審查）
- 非確定性路徑（GUI / Agent / 學習）可繼續但不改 import 接口

## 6.4 [V3-PM-4] Phase 0-3 延期影響

| Phase 0-3 延期 | Rust 啟動推遲 | 總壁鐘 |
|----------------|-------------|--------|
| 0 週（準時） | Week 9 | 23 週 |
| +2 週 | Week 11 | 25 週 |
| +4 週 | Week 13 | 27 週 |
| **≥ +5 週（Week 14 硬截止）** | 重新評估 Rust 必要性 | — |

## 6.5 [V3-PM-6] 前置交付物
Phase 0-3 期間必須額外完成：
- Paper Trading 自動監控告警 bot（使 Rust 開發期運維 <15min/天）
- Golden Dataset 自動產出機制
- Python 確定性路徑 SMA 改用 `math.fsum()`（[V3-QC-2]）

---

# 第七部分：風險矩陣 + 回滾計劃

## 7.1 風險矩陣

| 風險 | 概率 | 影響 | 緩解 |
|------|------|------|------|
| Rust/Python 計算不一致 | 中 | 高 | QC 分級容差 + [V3-QC-2] 統一 fsum/Kahan + 7 天灰度 + Golden Dataset |
| IPC 延遲/丟失 | 中 | 高 | TTL + 超時降級 L0 + [V3-PA-4] /run/openclaw/ + 自動重連 |
| 策略行為差異 | 中 | 高 | [V3-QC-1] 按類型分信號豁免區 + 灰度逐信號對比 |
| Engine 崩潰 | 低 | 高 | systemd RestartSec=2 + [V3-PA-7] Python 2s 止損接管 + 交易所條件單 |
| **[V3] Rust 崩潰時止損空窗** | 低 | 極高 | Python watchdog 2s 啟動本地止損 + 條件單最後防線 |
| 開發超期 | 中 | 中 | Week 8 硬決策點 + 每 2 週 checkpoint |
| Python 代碼持續演進 | 中 | 中 | [V3-PM-2] 分層凍結 + [V3-PM-5] 灰度 code freeze |
| shared_types 漂移 | 中 | 中 | [V3-PA-6] CI JSON Schema diff |
| 依賴斷裂 | 低 | 中 | FA 22 點修復 + [V3-FA-4] conftest 專項 |
| 測試基準線回退 | 中 | 中 | CI：Python≥3500 + cargo test 0 fail + 灰度 diff=0 |
| [V3-PA-3] 級聯半一致 | 低 | 高 | All-or-nothing clone+swap 事務 |
| Phase 0-3 延期 | 中 | 中 | [V3-PM-4] Week 14 硬截止 + 延期影響表 |
| 單人 Operator 瓶頸 | 中 | 中 | [V3-PM-6] Paper Trading 自動監控 |

## 7.2 [V3-PM-7] 回滾計劃

| 場景 | 動作 | SLA |
|------|------|-----|
| **Runtime 回滾**（Engine 不穩定） | watchdog 3-strike → 停 Engine → Python fallback 模式 | <30 秒 |
| **完全回滾**（架構放棄） | git checkout pre-rust-cleanup tag → 重部署 → 移除 shared_types 和 IPC client | <10 分鐘 |
| **灰度回滾**（灰度失敗） | 停 Rust Engine → Python 影子進程升級為主進程 | <1 分鐘 |

**強制規則**：
- W13 tag 之前不刪除任何 Python 原始代碼
- W11 必須演練一次完全回滾（計時，SLA 必須 <10 分鐘）
- 冗餘代碼保留 4 週後才最終刪除

---

# 第八部分：量化總結

## 8.1 代碼量
```
Rust 新增：types 4,500 + core 8,700 + engine 13,800 + tests 5,500 = 32,500 行
Python 變化：52,500 → ~39,000 行
總計：~71,500 行
```

## 8.2 性能（[V3-E5-5] 明確標注 Engine-internal only）

| 指標 | Python 現狀（E5 實測） | Rust 目標 | 提升 | 依據 |
|------|----------------------|-----------|------|------|
| tick P50（Engine-internal） | 0.3-0.5ms | 5-15μs | 30-50x | 消除 GIL + deepcopy + 零鎖（[V3-E5-3] 非 SIMD 主因） |
| tick P99（Engine-internal） | 2-5ms | 50-120μs | 30-40x | kline close 全指標重算，5/13 可 SIMD |
| tick P99.9（Engine-internal） | 5-15ms | 200-500μs | 20-30x | 含 state compile + risk check |
| IPC 往返（不含在 tick 中） | N/A | 50-100μs | — | JSON-RPC serde + socket |
| deepcopy 消除 | 0.8-2ms | 10-30μs（Arc/CoW） | 50-80x | 零拷貝 |
| state persist | 3-8ms 阻塞主線程 | **[V3-E5-1]** 0 on tick, 5-50μs on bg thread | ∞ | mmap 隔離到獨立線程 |
| 記憶體 | ~200-400MB | ~40-80MB | 4-5x | struct 緊湊佈局 |
| **[新]** 快速通道 | 不存在 | tick-to-order <50μs | — | Rust fast-path |
| **[新]** Python 降級容錯 | 不存在 | Rust core 獨立運行 | — | 雙進程 |
| **[新]** Engine 崩潰止損 | 不存在 | [V3-PA-7] Python 2s 接管 | — | 交叉容錯 |

## 8.3 時間投入
```
提前並行：~2 週（Phase 1-3 期間，僅零依賴任務）
主開發：14 週
風險緩衝：+3 週（20%）
總計壁鐘：~17 週（Phase 0-3 準時的情況下）
```

---

# 第九部分：測試遷移計劃

## 9.1 四層測試架構

| 層級 | 數量 | 工具 |
|------|------|------|
| L1 Rust 單元測試 | ~400 | `#[test]` + proptest |
| L2 Rust 集成測試 | ~80 | `tests/` |
| L3 IPC 集成測試 | ~60 | pytest |
| L4 灰度對比 | ~20 場景 | JSONL diff + Comparator |

## 9.2 現有測試處置

| 處置 | 數量 | 說明 |
|------|------|------|
| 刪除 | ~8 | 測試已刪除 Python 內部邏輯 |
| 改 IPC | ~14 | 數據源變 Rust Engine |
| 保留不動 | ~10 | Python 側邏輯 |
| **[V3-FA-4] conftest 改造** | 1（15處） | SM→IPC mock + PriceEvent→shared_types |

## 9.3 基準線
```
遷移前：3,703 Python
遷移後：~3,513 Python + ~480 Rust + 灰度 = ~3,993 total
CI 門檻：Python ≥ 3,500 pass + cargo test 0 fail + 灰度 diff = 0
```

---

# 附錄 A：環境配置（同 V2）

# 附錄 B：systemd 服務（[V3-PA-4] 去硬編碼）
```ini
# /etc/systemd/system/openclaw-engine.service
[Unit]
Description=OpenClaw Trading Engine (Rust)
After=network.target
[Service]
EnvironmentFile=/etc/openclaw/env
ExecStart=${OPENCLAW_BASE_DIR}/rust/target/release/openclaw_engine --config ${OPENCLAW_BASE_DIR}/settings/engine.toml
User=${OPENCLAW_USER}
Restart=always
RestartSec=2
RuntimeDirectory=openclaw
MemoryMax=2G
CPUQuota=400%
Nice=-5
[Install]
WantedBy=multi-user.target
```

# 附錄 C：engine.toml（[V3-PA-5] 完整 + 冷/熱標記）
```toml
# === 冷參數（需重啟）===
[websocket]
url = "wss://stream.bybit.com/v5/public/linear"
reconnect_delay_ms = 3000
heartbeat_interval_ms = 20000

[ipc]
socket_path = "/run/openclaw/engine.sock"
ai_request_ttl_ms = 15000
state_push_interval_ms = 1000

[persistence]
state_file = "runtime/openclaw_bybit_control_state.json"
paper_state_file = "runtime/paper_state.json"
debounce_ms = 5000

# === 熱參數（支持 SIGHUP / IPC reload_config）===
[attention]
dormant_interval_ms = 60000
low_interval_ms = 10000
medium_interval_ms = 3000
high_interval_ms = 500
critical_interval_ms = 0

[risk]
max_stop_loss_pct = 5.0
max_take_profit_pct = 20.0
max_open_positions = 10
max_total_exposure_pct = 30.0

[cognitive]
base_confidence_floor = 0.60
base_qty_ceiling = 1.0
base_stoploss_multiplier = 1.0
base_scan_interval_s = 1800
max_confidence_floor = 0.85
min_confidence_floor = 0.45
min_qty_ceiling = 0.3
max_stoploss_multiplier = 2.0
min_scan_interval_s = 300
max_scan_interval_s = 3600
ema_alpha = 0.3

[opportunity_tracker]
max_tracked = 100
ttl_days = 7
virtual_stoploss_pct = 5.0
virtual_takeprofit_pct = 10.0
estimated_fee_pct = 0.075
min_samples_for_direction = 5

[dream]
candle_window_days = 7
cycles_per_batch = 300
max_cycles_per_idle = 10000
min_cycles_for_confidence = 200
param_grid_size = 10
min_samples_per_param = 30
```

# 附錄 D：Rust 外部依賴（同 V2）

---

# 支撐文件索引

| 文件 | 內容 |
|------|------|
| `docs/references/2026-04-03--rust_migration_master_plan_v2.md` | V2 原始方案（歸檔） |
| `docs/references/2026-04-03--rust_migration_v2.5_consolidated.md` | V2.5 整合版（歸檔） |
| `docs/CCAgentWorkSpace/FA/workspace/reports/2026-04-03--rust_migration_file_coverage_audit.md` | FA 全量文件盤點 |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-03--rust_migration_revised_roadmap.md` | PM 修正路線圖 |
| `docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md` | 認知自適應 SPEC V1.1+R1 |
