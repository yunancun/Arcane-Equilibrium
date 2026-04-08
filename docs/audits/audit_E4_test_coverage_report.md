# E4 測試覆蓋與品質審計報告

**日期：** 2026-04-05  
**審計員：** E4（測試工程師）  
**範圍：** 全倉庫 Rust + Python 測試基線、覆蓋缺口、品質評估  

---

## 一、測試基線總覽

| 語言 | 測試數量 | 通過 | 失敗 | 通過率 |
|------|---------|------|------|--------|
| Rust（lib tests） | 799 | 799 | 0 | 100% |
| Rust（integration tests） | 27+ golden | 19 golden pass | **29 stress_integration 編譯失敗** | -- |
| Python | 3,882 | 3,858 | **22** | 99.4% |
| **合計** | **~4,708** | **~4,676** | **~22+29** | -- |

### Rust 分佈
| Crate | Lib Tests | Integration Tests |
|-------|-----------|-------------------|
| openclaw_core | 384 | 27（golden_dataset 8 + golden_extreme 19）|
| openclaw_engine | 379 | **29（stress_integration — 編譯失敗）** + 4（rrc1_audit）|
| openclaw_types | 36 | 0 |
| openclaw_pyo3 | -- | **PyO3 鏈接錯誤，無法編譯測試** |

### Python 分佈
| 模組分區 | 測試數量 | 失敗 |
|----------|---------|------|
| control_api_v1/tests/ | 3,346 | 20 |
| local_model_tools/tests/ | 494 | 0 |
| ml_training/tests/ | 42 | 2 |

---

## 二、P0 問題（必須立即修復）

### P0-1: stress_integration.rs 編譯失敗（29 個測試不可用）
- **位置：** `rust/openclaw_engine/tests/stress_integration.rs:319,339,361,377`
- **原因：** `IntentProcessor::process()` 簽名從 3 參數改為 4 參數（新增 `atr: f64`），但 stress_integration.rs 未同步更新
- **影響：** 29 個壓力集成測試（flash crash、drawdown breach、position limits、stop triggers 等極端場景）全部無法運行
- **嚴重性：** **P0** — 這些是系統最關鍵的安全網測試，涵蓋極端市場條件下的行為驗證

### P0-2: test_grafana_data_writer.py 全面失敗（20 個測試）
- **位置：** `program_code/.../tests/test_grafana_data_writer.py`
- **影響：** Grafana 數據寫入（PnL/Tickers/Health/Fills/Snapshot）全部測試紅
- **嚴重性：** **P0** — 回歸問題，之前應該是綠的

### P0-3: test_label_generator.py 2 個失敗
- **位置：** `program_code/ml_training/tests/test_label_generator.py`
- **失敗用例：** `test_generate_labels_extreme_detection`, `test_generate_labels_zero_atr_uses_floor`
- **嚴重性：** **P0** — 標籤生成是 ML 訓練管線的基礎

### P0-4: test_market_data.py 1 個失敗
- **位置：** `test_market_feed_status_not_initialized`
- **嚴重性：** P1

---

## 三、模組級覆蓋分析

### 3.1 Rust — openclaw_core（24 模組）

| 模組 | 行數 | 內聯測試 | 覆蓋評價 | 缺口 |
|------|------|---------|---------|------|
| h0_gate.rs | ~350 | 30 | ★★★★★ | 全面：shadow mode/cooldown/health/risk/freshness |
| klines.rs | ~300 | 22 | ★★★★★ | KlineStore CRUD + 邊界 |
| dream.rs | ~250 | 20 | ★★★★☆ | 缺：並發壓力 |
| execution.rs | ~200 | 18 | ★★★★☆ | 基本覆蓋，缺 fee 異常 |
| opportunity.rs | ~200 | 18 | ★★★★☆ | 評分+排序+過濾 |
| governance_core.rs | ~200 | 12 | ★★★★☆ | 級聯 all-or-nothing |
| signals/rules.rs | ~150 | 20 | ★★★★☆ | 信號規則引擎 |
| signals/mod.rs | ~100 | 10 | ★★★☆☆ | 缺：空信號列表 |
| risk/checks.rs | ~200 | 22 | ★★★★★ | 全面 P0/P1/P2 風控檢查 |
| risk/stops.rs | ~100 | 8 | ★★★☆☆ | 缺：price exactly at stop 邊界 |
| risk/price_tracker.rs | ~100 | 10 | ★★★★☆ | - |
| risk/config.rs | ~80 | 5 | ★★★☆☆ | 缺：非法值反序列化 |
| sm/auth.rs | ~120 | 14 | ★★★★☆ | 狀態機轉移 |
| sm/lease.rs | ~100 | 10 | ★★★★☆ | TTL + acquire/release |
| sm/oms.rs | ~100 | 13 | ★★★★☆ | 訂單管理狀態機 |
| sm/risk_gov.rs | ~100 | 15 | ★★★★☆ | 風控治理狀態機 |
| **sm/mod.rs** | **90** | **0** | **★☆☆☆☆** | **無測試 — 狀態機調度邏輯** |
| indicators/* | ~400 | 32 | ★★★★☆ | trend/momentum/volatility/volume 各有測試 |
| stop_manager.rs | ~120 | 14 | ★★★★☆ | Hard/Trailing/Time Stop |
| portfolio.rs | ~100 | 10 | ★★★★☆ | - |
| order_match.rs | ~80 | 11 | ★★★★☆ | - |
| message_bus.rs | ~80 | 7 | ★★★☆☆ | 缺：滿佇列行為 |
| attention.rs | ~120 | 11 | ★★★★☆ | 含 infinite distance 測試 |
| cognitive.rs | ~120 | 13 | ★★★★☆ | - |
| attribution.rs | ~80 | 10 | ★★★☆☆ | - |
| backtest.rs | ~100 | 9 | ★★★☆☆ | 缺：空數據集 |
| cost_gate.rs | ~80 | 11 | ★★★★☆ | 含 confidence 門檻 |
| guardian.rs | ~60 | 6 | ★★★☆☆ | 基本覆蓋 |

**Golden Tests（openclaw_core/tests/）：**
- `golden_dataset.rs`（8 tests）：Python-Rust 一致性驗證，確定性合成數據
- `golden_extreme.rs`（19 tests）：極端值（zero price/fill、negative returns、very small qty）

### 3.2 Rust — openclaw_engine（34 模組）

| 模組 | 行數 | 內聯測試 | 覆蓋評價 | 缺口 |
|------|------|---------|---------|------|
| **event_consumer.rs** | **957** | **0** | **★☆☆☆☆** | **最大文件，零測試** — WS 事件消費/分發邏輯 |
| **main.rs** | **946** | **0** | **★☆☆☆☆** | **零測試** — 啟動/配置/通道初始化 |
| tick_pipeline.rs | ~200 | 8 | ★★★☆☆ | 有 rrc1 外部測試 |
| intent_processor.rs | ~250 | 9 | ★★★☆☆ | **stress_integration 編譯壞** |
| order_manager.rs | ~250 | 20 | ★★★★☆ | 批次訂單+重試 |
| position_manager.rs | ~200 | 12 | ★★★★☆ | - |
| account_manager.rs | ~200 | 16 | ★★★★☆ | - |
| paper_state.rs | ~200 | 12 | ★★★★☆ | paper 成交模擬 |
| ws_client.rs | ~250 | 16 | ★★★★☆ | WS 連接/重連/心跳 |
| multi_interval_ws.rs | ~200 | 9 | ★★★☆☆ | 多時間框架 WS |
| market_data_client.rs | ~250 | 18 | ★★★★☆ | REST 市場數據 |
| instrument_info.rs | ~200 | 16 | ★★★★☆ | - |
| strategies/ma_crossover.rs | ~200 | 18 | ★★★★★ | 含 param update/ranges |
| strategies/grid_trading.rs | ~200 | 16 | ★★★★☆ | - |
| strategies/bb_breakout.rs | ~150 | 11 | ★★★★☆ | - |
| strategies/bb_reversion.rs | ~120 | 9 | ★★★☆☆ | - |
| strategies/funding_arb.rs | ~100 | 7 | ★★★☆☆ | - |
| **strategies/mod.rs** | **110** | **0** | **★☆☆☆☆** | **Strategy trait 派發邏輯，零測試** |
| config.rs | ~150 | 8 | ★★★☆☆ | 配置反序列化 |
| fast_track.rs | ~100 | 8 | ★★★★☆ | 緊急通道 |
| orchestrator.rs | ~100 | 5 | ★★★☆☆ | 策略編排 |
| feature_collector.rs | ~120 | 6 | ★★★☆☆ | 34-dim 特徵收集 |
| ml/kelly_sizer.rs | ~100 | 6 | ★★★☆☆ | Kelly 資本配置 |
| ml/scorer.rs | ~80 | 4 | ★★★☆☆ | 3-tier 降級 |
| ml/model_manager.rs | ~80 | 3 | ★★☆☆☆ | ONNX hot-swap |
| database/drift_detector.rs | ~200 | 15 | ★★★★☆ | PSI + ADWIN + NaN 處理 |
| database/black_swan_detector.rs | ~150 | 6 | ★★★☆☆ | 4 信號投票 |
| database/market_writer.rs | ~100 | 3 | ★★☆☆☆ | 只有基本寫入 |
| database/trading_writer.rs | ~80 | 3 | ★★☆☆☆ | 缺：失敗回滾 |
| database/feature_writer.rs | ~80 | 2 | ★★☆☆☆ | UPSERT 基本 |
| database/context_writer.rs | ~80 | 3 | ★★☆☆☆ | - |
| database/fallback.rs | ~60 | 2 | ★★☆☆☆ | JSONL fallback |
| **database/rest_poller.rs** | **153** | **0** | **★☆☆☆☆** | **零測試** — funding/OI/LSR 輪詢 |
| **database/quality_writer.rs** | **104** | **0** | **★☆☆☆☆** | **零測試** — 數據品質監控 |
| **pipeline_types.rs** | **147** | **0** | **★☆☆☆☆** | **零測試** — 管線類型定義 |
| ipc_server.rs | ~100 | 3 | ★★☆☆☆ | IPC 命令處理 |
| bybit_rest_client.rs | ~200 | 14 | ★★★★☆ | REST 客戶端 |
| bybit_private_ws.rs | ~150 | 13 | ★★★★☆ | 私有 WS |
| platform_client.rs | ~120 | 8 | ★★★☆☆ | - |
| spot_margin_client.rs | ~120 | 13 | ★★★★☆ | - |
| leverage_token_client.rs | ~100 | 9 | ★★★☆☆ | - |
| batch_order_manager.rs | ~80 | 10 | ★★★★☆ | - |
| persistence.rs | ~60 | 3 | ★★☆☆☆ | - |
| execution_listener.rs | ~50 | 1 | ★☆☆☆☆ | 只有基本 |

### 3.3 Python — control_api_v1/app/（~60 個業務模組）

**有直接或間接測試的模組（覆蓋良好）：**

| 模組 | 測試數量 | 覆蓋評價 |
|------|---------|---------|
| governance_hub | 62 | ★★★★★ |
| risk_manager | 95 | ★★★★★ |
| h0_gate | 94 | ★★★★★ |
| authorization_state_machine | 73 | ★★★★★ |
| decision_lease_state_machine | 58 | ★★★★★ |
| layer2 (engine+routes+types) | 79 | ★★★★☆ |
| paper_trading (engine+routes) | 58+46 | ★★★★☆ |
| governance_routes | 110 | ★★★★★ |
| data_source_enforcer | 58 | ★★★★☆ |
| truth_source_registry | 55 | ★★★★☆ |
| reconciliation_engine | 55 | ★★★★☆ |
| pipeline_bridge (indirect) | 84+34+17 | ★★★★☆ |
| executor_agent (indirect) | 31+14 | ★★★☆☆ |
| guardian_agent (indirect) | 28+30 | ★★★☆☆ |

**無測試的大型模組（>200 行）：** 共 ~62 個模組無直接 test 文件

| 模組 | 行數 | 風險 |
|------|------|------|
| layer2_engine.py | 730 | **HIGH** — AI 推理引擎核心 |
| ai_service.py | 729 | **HIGH** — AI 服務調度 |
| guardian_agent.py | 580 | MEDIUM（有間接測試 58 個） |
| ipc_client.py | 560 | **HIGH** — Rust IPC 通信 |
| executor_agent.py | 508 | MEDIUM（有間接測試 45 個） |
| main_legacy.py | 434 | MEDIUM — 啟動+singleton |
| pipeline_bridge.py | 55 | LOW（thin wrapper，有間接測試 135 個） |
| governance_routes.py | ~300 | LOW（有 110 個路由測試） |

### 3.4 Python — local_model_tools/（~15 個模組）

| 模組 | 有測試 | 測試數 | 缺口 |
|------|--------|-------|------|
| strategies | Y | 46 | - |
| indicators | Y | 58 | - |
| backtest_engine | Y | 60 | - |
| signal_generator | Y | 38 | - |
| kline_manager | Y | 36 | - |
| pipeline_bridge | Y | 84 | - |
| stop_manager | Y | 17 | - |
| market_scanner | Y | 16 | - |
| strategy_auto_deployer | Y | 40 | - |
| strategy_orchestrator | Y | 18 | - |
| cost_gate | Y | 22 | - |
| atr_dual_window | Y | 18 | - |
| session9_fixes | Y | 33 | - |
| **indicator_engine** | **N** | 0 | **472 行，零直接測試** |
| **evolution_engine** | **N** | 0 | **567 行，零直接測試** |
| **position_sizer** | **N** | 0 | **315 行，零直接測試** |
| **cognitive_modulator** | **N** | 0 | **193 行，零直接測試** |
| **local_llm_client** | **N** | 0 | **251 行，零直接測試** |

### 3.5 Python — ml_training/（~8 個模組）

| 模組 | 有測試 | 測試數 | 缺口 |
|------|--------|-------|------|
| thompson_sampling | Y（間接）| 8 | test_thompson.py |
| optuna_optimizer | Y（間接）| 8 | test_optuna.py |
| cpcv_validator | Y（間接）| 10 | test_cpcv.py |
| label_generator | Y | 5 | **2 個失敗** |
| parquet_etl | Y | 3 | - |
| integration | Y | 3 | - |
| leakage_check | Y | 5 | - |
| **scorer_trainer** | **N** | 0 | **173 行，零直接測試** |
| **onnx_exporter** | **N** | 0 | **119 行，零直接測試** |
| **calibration** | **N** | 0 | **81 行，零直接測試** |

---

## 四、八維度品質評估

### 4.1 正常路徑（Happy Path）測試 — ★★★★☆ 良好

**優點：**
- 所有 5 個策略均有完整 happy path 測試（ma_crossover 18 / grid_trading 16 / bb_breakout 11 / bb_reversion 9 / funding_arb 7）
- 治理管線全鏈路（auth → lease → risk_gov → oms）狀態機轉移覆蓋完整
- Paper Trading 生命週期（open → fill → close → PnL）有 58+46 個測試
- H0 Gate 全 5 維度（freshness/health/eligibility/risk/cooldown）均有測試

**缺口：**
- event_consumer.rs（957 行）無任何測試 — WS 事件→管線分發的核心邏輯
- AI 推理鏈（layer2_engine 730 行 + ai_service 729 行）無直接測試

### 4.2 邊界測試（Boundary/Edge Case）— ★★★★☆ 良好

**優點：**
- golden_extreme.rs 包含 19 個極端值測試（zero price、zero fill qty、negative returns、very small qty、single-element arrays）
- drift_detector.rs 包含 NaN 跳過測試（`test_histogram_nan_skipped`）
- database/mod.rs 有 `sanitize_f64` 和 `sanitize_f64_zero` 處理 NaN/Inf
- indicators 有空數據保護（volatility.rs 過濾 price <= 0）
- H0 Gate 有 cooldown 計時器邊界測試

**缺口：**
- 缺少 f64::MAX/f64::MIN 系統性邊界測試
- order_manager: 缺少零數量訂單邊界
- klines: 缺少時間戳溢出測試
- Kelly sizer: 缺少 win_rate=0 和 win_rate=1 邊界

### 4.3 異常/錯誤路徑測試 — ★★★☆☆ 尚可

**優點：**
- 429 個 Python 測試包含 `pytest.raises`/`assertRaises`/error 相關斷言
- H0 Gate fail-closed 測試完整
- GovernanceCore 級聯 all-or-nothing 失敗測試
- Cost Gate 低信心/低 EV 拒絕測試
- 121/144 個 Python 測試文件包含某種錯誤路徑測試

**缺口：**
- Rust 無 `#[should_panic]` 測試 — 缺少 panic 路徑驗證
- database writers 缺少：DB 連接失敗、寫入超時、部分寫入回滾
- WS 客戶端缺少：連接超時、認證失敗、消息格式損壞
- IPC server 缺少：通道滿、反序列化失敗

### 4.4 並發測試 — ★★★☆☆ 尚可

**優點：**
- `test_pipeline_bridge_concurrency.py`（17 個測試）— 專項並發測試：concurrent on_tick + concurrent setter + deadlock 檢測
- `test_message_bus_load.py`（11 個測試）— 消息總線負載
- Rust 有 27 個 `#[tokio::test]` 異步測試
- threading.Thread + timeout 模式用於死鎖檢測

**缺口：**
- Rust 缺少 Arc+Mutex 競態條件測試（model_manager、drift_detector 使用了 Arc 但無並發測試）
- 無多線程寫入 database 的競態測試
- 無 WS 重連期間的消息丟失測試
- 無 IPC channel 滿/背壓測試

### 4.5 回歸測試 — ★★★★☆ 良好

**優點：**
- `rrc1_audit_tests.rs`（4 個測試）— 明確標註為 E4 審計發現的覆蓋缺口補丁
- `test_session9_fixes.py`（33 個測試）— Session 9 修復的回歸測試
- `test_winrate_param_fixes.py`（23 個測試）— 參數修復回歸
- `test_stop_manager_edge.py`（10 個測試）— StopManager 邊界回歸
- `test_risk_manager_edge.py`（8 個測試）— RiskManager 邊界回歸
- `test_paper_trading_engine_edge.py`（4 個測試）— PTE 邊界回歸

**缺口：**
- **stress_integration.rs 編譯壞** — 之前修復的 29 個壓力場景無法驗證回歸
- 缺少 realized_pnl 修復（Session 9c）的專項回歸測試
- 缺少 signals flush overflow 修復（batch chunking）的回歸測試

### 4.6 測試品質（斷言有效性）— ★★★★☆ 良好

**優點：**
- 平均每個 Python 測試 ~2.0 個斷言（70 assertions / 35 tests in e2e_smoke）
- Rust 測試大量使用 `assert_eq!` + 描述性 message（如 `assert_eq!(stats.total_checks, 20, "H0Gate should run on every tick")`）
- Golden tests 用確定性數據驗證 Python-Rust 一致性 — 高品質
- 無發現 "空測試"（只 run 不 assert 的情況）

**缺口：**
- 部分 Python 測試使用 `assert response.status_code == 200` 但不驗證 response body 內容
- ML 測試缺少數值精度驗證（如 `assert abs(result - expected) < epsilon`）

### 4.7 集成測試 — ★★★★☆ 良好

**優點：**
- `test_batch12_e2e_smoke.py`（35 個測試）— 全鏈路冒煙：Scout→Strategist→Guardian→Executor→Stop→Learning
- `test_h_chain_integration.py`（6 個測試）— H0→H1→...→H5 治理鏈
- `test_integration_phase2/5/7/8/9/10/11.py` — 各 Phase 集成測試
- `test_edge_filter_integration.py`（25 個）— Edge Filter 管線
- `test_learning_promotion_integration.py`（15 個）— 學習→升級管線
- `golden_dataset.rs` — Rust-Python 跨語言一致性
- `ml_training/tests/test_integration.py`（3 個）— Optuna→TS→CPCV 管線

**缺口：**
- 缺少完整的 Tick → Intent → Order → Fill → PnL → DB 寫入端到端 Rust 測試
- 缺少 WS 重連 → 數據恢復 → 管線恢復集成測試
- 缺少 Python API → IPC → Rust Engine 跨進程集成測試

### 4.8 PyO3 橋接測試 — ★☆☆☆☆ 缺失

- openclaw_pyo3 crate 因 PyO3 鏈接錯誤無法編譯測試
- 39 個 Python 方法的橋接正確性無自動化驗證
- 僅靠 GUI demo endpoints 間接驗證

---

## 五、覆蓋缺口優先級排序

### 優先級 P0（阻塞性 — 立即修復）

| # | 問題 | 影響 | 建議修復 |
|---|------|------|---------|
| 1 | stress_integration.rs 編譯壞 | 29 個極端場景測試不可用 | 更新 process() 調用為 4 參數 |
| 2 | test_grafana_data_writer 20 個失敗 | Grafana 數據管線回歸 | 修復接口變更 |
| 3 | test_label_generator 2 個失敗 | ML 標籤管線回歸 | 修復邏輯或測試 |

### 優先級 P1（高風險缺口 — 本週修復）

| # | 缺口 | 風險 | 建議新增測試數 |
|---|------|------|---------------|
| 1 | event_consumer.rs 957 行零測試 | 事件分發邏輯無驗證 | +15 |
| 2 | layer2_engine.py 730 行零測試 | AI 推理核心無驗證 | +10 |
| 3 | ai_service.py 729 行零測試 | AI 服務調度無驗證 | +8 |
| 4 | ipc_client.py 560 行零測試 | Rust 通信無驗證 | +10 |
| 5 | strategies/mod.rs 110 行零測試 | Strategy trait 派發無驗證 | +5 |
| 6 | database writers 缺失敗回滾測試 | DB 寫入安全無驗證 | +8 |

### 優先級 P2（改善性 — 下個 Sprint）

| # | 缺口 | 建議新增測試數 |
|---|------|---------------|
| 1 | evolution_engine.py 567 行零測試 | +8 |
| 2 | indicator_engine.py 472 行零測試 | +6 |
| 3 | position_sizer.py 315 行零測試 | +5 |
| 4 | scorer_trainer.py 173 行零測試 | +5 |
| 5 | rest_poller.rs 153 行零測試 | +5 |
| 6 | quality_writer.rs 104 行零測試 | +3 |
| 7 | sm/mod.rs 90 行零測試 | +4 |
| 8 | pipeline_types.rs 147 行零測試 | +3 |
| 9 | PyO3 橋接測試基礎設施 | +10 |
| 10 | Rust panic 路徑（#[should_panic]）| +8 |
| 11 | Arc/Mutex 並發安全測試 | +6 |
| 12 | WS 重連集成測試 | +5 |

---

## 六、測試基礎設施評估

### 優點
- Rust 使用 `cargo test` 原生框架，零外部依賴
- Python 使用 pytest + unittest.mock，成熟穩定
- Golden test 基礎設施（Python-Rust 一致性）設計優秀
- conftest.py 提供共享 fixtures，減少重複

### 問題
1. **PyO3 測試不可用** — 需要特殊的 Python 環境配置才能鏈接
2. **無覆蓋率工具** — 沒有 `cargo-tarpaulin` 或 `pytest-cov` 集成
3. **無 CI/CD** — 測試僅靠手動運行，無自動回歸門檻
4. **Rust integration tests 與 lib tests 分離** — stress_integration 編譯壞但 lib tests 全綠，容易遺漏

---

## 七、總結與建議

### 整體評分：★★★★☆（4.0/5.0）

**數量充足（4,708 個測試），品質中上，但存在關鍵盲點。**

| 維度 | 評分 | 備註 |
|------|------|------|
| 正常路徑 | ★★★★☆ | 策略/治理/風控覆蓋完整 |
| 邊界測試 | ★★★★☆ | golden_extreme 設計優秀，但系統性不足 |
| 異常路徑 | ★★★☆☆ | Python 尚可，Rust 缺 panic 路徑 |
| 並發安全 | ★★★☆☆ | 有專項測試但覆蓋不足 |
| 回歸測試 | ★★★★☆ | 有明確回歸標記的測試 |
| 測試品質 | ★★★★☆ | 斷言有效，無空測試 |
| 集成測試 | ★★★★☆ | E2E 冒煙+分 Phase 集成 |
| PyO3 橋接 | ★☆☆☆☆ | 基礎設施缺失 |

### 最緊急行動項
1. **修復 stress_integration.rs**（P0，預估 10 分鐘）
2. **修復 test_grafana_data_writer 回歸**（P0，預估 30 分鐘）
3. **修復 test_label_generator 回歸**（P0，預估 15 分鐘）
4. **為 event_consumer.rs 補充測試**（P1，預估 2 小時）
5. **集成 pytest-cov + cargo-tarpaulin**（P2，預估 1 小時）

---

**E4 審計結論：** 測試體系整體健康，關鍵模組（策略/風控/治理）覆蓋良好。但存在 3 個 P0 回歸問題需立即修復，以及 6 個大型模組（共 ~3,600 行）完全無測試，構成隱性風險。建議優先修復 P0 後，按 P1 清單補充缺口。
