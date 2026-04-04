# CLAUDE_CHANGELOG.md — 開發歷史歸檔

> 從 CLAUDE.md 遷出的 Wave/Sprint/Batch 歷史記錄。新 session 不需要讀此文件，僅供回顧歷史時查閱。
> 最後更新：2026-04-04

### R-CUT Phase 3 Go/No-Go RC-14~RC-15（2026-04-04）

- **RC-14** Go/No-Go 7/7 PASS：新 binary 編譯+重啟，201K tick replay 壓測通過
  - RSS 2.1MB | P50=27μs P95=28μs P99=29μs | 0 crash | 5 fills in 4.97s
- **RC-15** Go/No-Go 評估報告完成
- Rust 引擎正式成為唯一 tick 處理引擎

### R-CUT Phase 2 最小切換 RC-10~RC-13（2026-04-04）

- **RC-10** Python tick_pipeline 停用：2 處 activate() 註釋掉，PIPELINE_BRIDGE 保留供 API/GUI
- **RC-11** Category A dead code 刪除：4 files / 1,003 行（shadow_decision_tracker, dream_engine, opportunity_tracker, strategy_health_monitor）
- **RC-12** 全量測試驗證 4507 全綠零回歸
- **RC-13** E2 + E4 PASS
- 註：原估 187 files 實為 Category B+C，需 R-IPC API 路由遷移後才能大規模清理

### R-CUT Phase 1 策略補齊 RC-01~RC-09（2026-04-04）

- **RC-01** MA Crossover Hurst regime filter：mean_reverting/random_walk 市場阻止入場，cold-start 安全
- **RC-02** MA Crossover multi-TF：EMA of sma_50 (alpha=0.01) 作為 4h 趨勢代理，方向不符阻止入場
- **RC-03** BB Breakout 參數可配置化：squeeze_bw/expansion_bw/volume_threshold 從 const 改為 pub 欄位
- **RC-04** 所有策略 on_rejection() 回滾：prev_* 快照 + 恢復，Strategy trait 新增 default no-op
- **RC-05** 所有策略 on_fill() 回調：trait default no-op，tick_pipeline 接線完成
- **RC-06** Grid Trading geometric spacing + health check + auto-rebalance：GridSpacingMode enum + GridHealth + 200-tick 健康檢查
- **RC-07** BB Reversion limit order 真實實現：use_limit + limit_offset_bps，策略端 REAL（execution 層 Phase 2）
- **RC-08** StrategyParams trait + ParamRange 定義：Phase 3a stub，param_ranges()/validate()
- **RC-09** E2 APPROVE + E4 4507 全綠 + QA Audit CONDITIONAL PASS（0 FAKE features）
- Orchestrator 新增 strategies_mut()，tick_pipeline 改為逐策略處理含 rejection/fill 回調
- Canary watchdog test fix：grace_period=0 修復 test_missing_file_triggers_crash
- 測試基準線：Python 3877 / Rust 592 / Canary 38 = **4507** (+62)

### Rust Cutover Decision + Comprehensive Indicator Alignment（2026-04-04 · commits 2a253d9, 69b03aa, 5ed077b）

- **Operator 決策：放棄修 Python V2，全力 Rust** — QA 嚴格審計 Python V2 真實成熟度 62/100，6 項功能 FAKE/DEAD/UNREACHABLE
- **Replay Mode B**：tick_duration_us + feed_replay_tick() 100% 複用 on_tick，201K tick 完整回放驗證
- **ADX Bug 修復**：Python ADX 返回 DX 而非 ADX — 補 Wilder 平滑第三步
- **Comparator 大幅改進**：key 映射（66 keys）、bar-close filter、paper_state skip、容差放寬（1e-6/1e-2/5e-2）
- **Rust 指標對齊**：Hurst 安全修復（P0）、KAMA SMA seed、IndicatorSnapshot +3（sma_50/ema_26/atr_5）、conservative_atr
- **Rust 策略強化**：BB Breakout ATR trailing stop + regime exit（mean_reverting/random_walk）
- **Python 指標修復**：KAMA per-step SC、Stochastic Fast→Slow、signal_generator 9x NoneType guard
- **Rust 引擎完整度確認**：99.9% 獨立，零 Python 依賴，16 指標 / 8 信號 / 4 策略 / Guardian / Governance
- TODO 全面重構：新增 R-CUT（Rust 切換）和 R-IPC（IPC 擴展）階段，Kelly/FundingArb 雙腿延後到 Phase 2/1

---

### Cold-Start Fix + Phase 0a DDL Draft（2026-04-04 · commit f6ab650）

- **3-STRIKE 崩潰修復**：根因分析確認為 Cold Start Jitter（非代碼 bug），watchdog threshold 45s + grace-period 120s + Rust 引擎 force_write 初始快照
- **Go/No-Go 文檔更新**：INC-001 事件記錄 + 判定條件細化（穩態 0 崩潰，啟動寬限期不計）
- **Phase 0a DDL 草稿**：6 檔案 / 43 表 / 8 Schema / 29 hypertable（conditional）/ V001-V005 遷移框架
- **PYO3-1 推遲**：接口錯位（Rust distill→cycle_data vs Python→IntelObject），推遲到 Phase 2 Decision Context
- E2 審查 5 項修正（index_price NULL bug、scorer VIEW 注釋、unused import、table count、注釋一致性）+ E4 全綠 3839+36

---

### Tech Debt Zero + Engine Launch（2026-04-03 · Session 11 final）

- Rust StateWriter atomic write（.tmp → rename）防止 IPC 讀半寫
- 3 文件 DEPRECATED 標記（governance_hub / paper_trading_engine / strategy_auto_deployer）
- 4 個 IPC 測試修復（Rust reader mock for pipeline_stats + session_status envelope）
- Watchdog threshold 30s→60s（防假告警）
- **Rust 引擎灰度模式啟動**：5 symbols × 4 strategies，Go/No-Go 2026-04-10

---

### R07-1 Replay Runner + Accelerated Canary Plan（2026-04-03 · Session 11）

**replay_runner.py**：歷史回放取代即時灰度（22 天 → ~7 天）
- Bybit REST API 分頁獲取歷史 1m K 線 → 4 tick/bar 合成
- Python KlineManager + IndicatorEngine + SignalEngine 全管線回放
- 已驗證：7 天 × 5 幣種 = 201,600 ticks，300 秒完成
- 輸出 shadow_results.jsonl 匹配 canary schema V1.0.0

**R-07 代碼全部完成**：replay_runner + CanaryRecord + Comparator + Watchdog + Rollback Drill
**剩餘工作**：啟動 Rust 引擎即時灰度 7 天 → Go/No-Go → 正式完成

---

### Test Debt Zero — All 28 Failures + 17 Errors Resolved（2026-04-03 · Session 11）

**28 failed + 17 errors → 0 failed, 0 errors, 3839 passed（+45 淨增）**
- 7 類過期測試斷言（E/F/H/I/K/M/N）：operator config 改變後測試未同步
- 4 類測試隔離缺陷（B/C/D/G）：mock 不完整、config 未隔離、event loop 缺失
- 2 類基礎設施（A: pytest-asyncio 安裝、L: importlib→標準 import）
- 1 類實現追蹤（J: L2 dispatch 從 Thread 改為 model_router）
- FA 確認 + E1 並行修復 + E4 全量回歸驗證

---

### R-07 Canary Tooling — Comparator + Watchdog + Rollback（2026-04-03 · Session 11）

**R07-3 Canary Comparator:**
- `canary_schema.py`：JSONL schema contract (V1.0.0) + 3-tier tolerance mapping + validation
- `canary_comparator.py`：tick-level comparison (indicators, signals, paper state, intents) + boundary divergence escalation (V3-QC-5) + CLI + daily reports

**R07-6 Engine Watchdog:**
- `engine_watchdog.py`：snapshot freshness monitor + crash/recovery detection + 3-strike rollback rule + CLI + status API helper

**R07-5 Rollback Drill:**
- `rollback_drill.sh`：8-step rehearsal script (stop engine → verify fallback → git checkout → restart → health check) + SLA timing + dry-run mode

**35 tests all PASS** covering: schema (5) + comparator (14) + watchdog (11) + integration (5)

---

### R-06 Python IPC Integration Complete（2026-04-03 · Session 11）

**R06-D conftest IPC mock fixtures:**
- 新增 5 個 pytest fixtures（rust_snapshot_dir, rust_reader_available/unavailable, patch 版本）
- SAMPLE_PIPELINE_SNAPSHOT 共享測試數據
- 12 處 SM import TODO 標記保留（SM 仍為 Python，R-07+ 處理）

**R06-E IPC 集成測試 53 個：**
- test_ipc_state_reader.py：14 個基礎讀取器測試（Session 10）
- test_ipc_integration.py：39 個（reader supplement + route logic + source tag + edge cases + rollback simulation）

**R06-F 回滾預演：**
- TestRollbackSimulation 6 個測試：crash → fallback → recovery lifecycle
- SLA 驗證：fallback < 100ms（要求 < 30s）

**R-06 Go/No-Go 門控全部通過：**
- 4/7 routes IPC 改造完成（3 個有意 defer）
- 53 IPC 測試全 PASS
- Python 3794 pass ≥ 3500 基準
- 回滾 SLA < 100ms
- conftest fixtures 已加入

**測試基準線：** Python 3794 passed / 28 failed / 17 errors / 1 skipped + Rust 552 passed / 0 failed

---

### R-05 Engine Integration + Bybit API Compatibility（2026-04-03）

**Engine Live Wiring:**
- main.rs 接入 TickPipeline（替換 placeholder event consumer）
- 5 幣種（BTC/ETH/SOL/XRP/DOGE）× 4 策略（MA/BB-Rev/BB-Break/Grid）
- Paper auth 啟動自動授予 + 定期 status report + JSON/JSONL 持久化
- 10 分鐘 Bybit Live WS 實測：38,389 ticks, 8 fills, 零崩潰
- Fix: check_stops 跨幣種價格污染（BTC price 更新 ETH best_price）
- Fix: Strategy trait 加 Send bound（tokio::spawn 兼容）
- Fix: rustls ring crypto provider 安裝

**29 壓力集成測試（stress_integration.rs）：**
- Fast track 緊急通道（CloseAll/Reduce/Pause + 5%/90% 邊界）
- 多幣種混合（5 幣 500 ticks + 快速交替 1000 ticks）
- 策略邊界（whipsaw/oversold/false squeeze/breakout/grid traversal）
- Guardian + Governance（drawdown/conflict/position limit/no auth）
- 止損邊界 + 管線吞吐（10k ticks + 26.9μs release tick latency）
- PnL 正確性 + 持久化驗證

**QC 數學模型審查：45+ 公式 APPROVED（3 MINOR 非阻塞備註）**

**9 項 Bybit API 兼容性修復：**
1. [CRITICAL] qty_step 精確取整（替代硬編碼 3dp）
2. [CRITICAL] minOrderQty/maxOrderQty/minNotional 驗證
3. [CRITICAL] positionIdx 包含在所有非 spot 訂單中
4. [HIGH] kline confirm 欄位檢查（只處理已確認 K 線）
5. [HIGH] API rate limit 頭部讀取 + 預請求限流
6. [HIGH] 止損價格方向感知取整（long floor / short ceil）
7. [MEDIUM] HTTP vs Bybit retCode 區分（errorType 字段）
8. [MEDIUM] 指數退避重試（瞬態錯誤自動重試）
9. [MEDIUM] accountType 動態檢測（替代硬編碼 UNIFIED）
- 額外：Registry linear 優先（spot 不再覆蓋 linear instrument info）

**V2 Bybit Demo Live 驗證：BTC+ETH 端到端下單 PASS，帳戶模式檢測 PASS**

**測試基準線：3,741 Py (+38 新) + 548 Rust (+31 新) = 4,289 total, 零回歸**

---

### Phase R-04 完成 — Engine 完整交易路徑（2026-04-03）

**Batch 1（核心管線）：**
- `tick_pipeline.rs`：on_tick 6 步編排 + KlineManager→IndicatorEngine→SignalEngine→策略→執行→止損
- `intent_processor.rs`：H0→Guardian→CostGate→Governance→OMS 意圖處理管線
- `fast_track.rs`：緊急路徑（CircuitBreaker→CloseAll / Defensive→ReduceToHalf）

**Batch 2（5 策略）：**
- `strategies/ma_crossover.rs`：KAMA + ADX≥20 + 5min cooldown
- `strategies/bb_reversion.rs`：%B<0+RSI<30 入場 / %B 0.2-0.8 出場
- `strategies/bb_breakout.rs`：壓縮→擴張+Volume≥1.5x+Donchian 確認
- `strategies/grid_trading.rs`：OU 動態間距 + 2×fee floor + 庫存上限
- `strategies/funding_arb.rs`：delta 中性 + 34bps 成本模型 + 72h 最大持倉（等 R-06 IPC 接入資金費率）

**Batch 3（狀態+持久化）：**
- `paper_state.rs`：持倉追蹤 + 止損檢查 + PnL 計算 + 狀態導出
- `persistence.rs`：JSON debounced write + JSONL append-only 審計

**API 適配：**
- `IndicatorSnapshot` 添加 `Default` derive
- `snapshot_to_input()` 適配器：IndicatorSnapshot（nested）→ IndicatorInput（flat）
- 策略 cooldown 修復：首次交易允許通過（`last_trade_ms > 0` guard）

**測試基準線：** Rust 517 (376 core + 8 golden + 19 extreme + 78 engine + 36 types)

---

### Phase R-03 完成 — core 下半：SM + 執行 + 回測（2026-04-03）

**Batch 1（4 SM 狀態機）：**
- `sm/auth.rs`（601 行）：8 狀態 + 16 遷移 + 7 禁止 + 5 守衛 + 過期守護（15 tests）
- `sm/lease.rs`（538 行）：9 狀態 + 18 遷移 + 12 禁止 + revoke_all_live（14 tests）
- `sm/risk_gov.rs`（583 行）：6 級風控 + 23 遷移 + 自動升級 + 持有時間守衛 + 6 級約束（14 tests）
- `sm/oms.rs`（548 行）：11 態訂單生命週期 + 16 遷移 + 12 禁止 + 對賬（11 tests）
- `sm/mod.rs`（90 行）：TransitionRecord + SmError + now_ms

**Batch 2（GovernanceCore 級聯）：**
- `governance_core.rs`（490 行）：all-or-nothing risk→auth→lease 級聯 + evaluate_and_cascade + 紙盤授權（12 tests）

**Batch 3（確定性檢查 + 執行）：**
- `guardian.rs`（270 行）：4 項確定性風控檢查 + 裁決邏輯（7 tests）
- `execution.rs`（262 行）：滑點分層 + 成交價 + 手續費 + 損益（16 tests）
- `order_match.rs`（267 行）：限價單匹配 + 部分成交率（10 tests）

**Batch 4（組合 + 止損 + 消息 + 歸因）：**
- `portfolio.rs`（331 行）：Pearson 相關 + 3 層檢查 + 組合指標（7 tests）
- `stop_manager.rs`（325 行）：hard/trailing/time 3 止損 + ATR 倉位計算（14 tests）
- `message_bus.rs`（257 行）：6 角色消息路由 + 衝突解決（6 tests）
- `attribution.rs`（235 行）：6 因子分解 + 聚合（9 tests）

**Batch 5（回測引擎）：**
- `backtest.rs`（438 行）：逐 K 線回放 + SignalGenerator trait + Sharpe/drawdown（9 tests）

**Batch 6（極端組測試）：**
- `tests/golden_extreme.rs`（287 行）：SM 級聯壓力 + 執行邊界 + 止損邊界 + 組合極端（19 tests）

**測試基準線：** Rust 468 (376 core + 8 golden + 19 extreme + 29 engine + 36 types) · Python 3703/24/17 零回歸

---

### Phase R-02 完成 — core 上半：感知 + 認知 + 風控（2026-04-03）

**Batch 1（小型獨立模組）：**
- `attention.rs`：5 級注意力（Dormant→Critical）+ 波動性跳動檢測 + 訂單接近度（11 tests）
- `cognitive.rs`：CognitiveModulator EMA 平滑 + R1-5 連虧忽略 + dream blend（13 tests）
- `opportunity.rs`：OpportunityTracker 虛擬 PnL + 2x fee + 遺憾方向判定（18 tests）
- `dream.rs`：DreamEngine 蒙特卡洛 + binomial test + 重入鎖（20 tests）

**Batch 2（中型模組）：**
- `klines.rs`：KlineManager 多時間框架聚合 + Kahan 補償求和（18 tests）
- `h0_gate.rs`：H0Gate 5 項門控 fail-fast + shadow mode + <1ms SLA（30 tests）

**Batch 3（13 指標引擎）：**
- `indicators/` 拆分 5 文件：trend(SMA/EMA/MACD/KAMA/Donchian) + momentum(RSI/Stoch/ADX) + volatility(BB/ATR/Hurst/EWMA) + volume(VolumeRatio)
- Kahan 求和：SMA/KAMA/ADX/VolumeRatio/RSI [V3-QC-2]（33 tests）

**Batch 4（信號 + 風控）：**
- `signals/`：8 規則（RSI OB/OS, MA Cross, BB Reversion, MACD, exits, divergence, regime）+ QC 邊界豁免 + SignalEngine 共識（30 tests）
- `cost_gate.rs`：5 級成本分層 + ATR vs 成本門檻（11 tests）
- `risk/`：RiskConfig P0/P1/P2 + 動態止損(ATR+regime) + 8 優先級 tick 檢查 + PriceHistoryTracker（45 tests）

**Batch 5（Golden Dataset）：**
- `tests/golden_dataset.rs`：合成數據 13 指標交叉驗證 + Kahan 精度 + 確定性再現（8 tests）
- `helper_scripts/golden_dataset_gen.py`：Python 對照生成器

**審查：** E2 CONDITIONAL→PASS（移除 opportunity.rs 未用 next_id）· E4 PASS 零回歸
**測試：** Rust 302 passed（+237 vs R-01）/ Python 3703 passed（不變）

---

### Phase R-01 完成 — IPC + shared_types + WS + Workspace 統一（2026-04-03）

**Batch 0 — Rust workspace 合併：**
- PA 評估後建立 `openclaw_pyo3` 獨立 crate（cdylib），隔離 PyO3 extension-module
- 從 `srv/rust/` 遷移 ContextDistiller + HedgingEngine 到 workspace
- 4 crates 統一：openclaw_types / openclaw_core / openclaw_engine / openclaw_pyo3
- `maturin develop --release` 驗證 Python `import openclaw_core` 不變

**R01-1~4 Rust Engine 模組：**
- `config.rs`：ArcSwap<RuntimeConfig> 熱加載 + 冷/熱參數分類 + TOML 解析（7 tests）
- `ipc_server.rs`：Unix domain socket JSON-RPC 2.0 server + 5 方法 handler（11 tests）
- `ws_client.rs`：Bybit WS client + 指數退避重連 + PriceEvent 推送（9 tests）
- `main.rs`：tokio multi-thread runtime + SIGHUP 配置重載 + 優雅關機（2 tests）

**R01-5~7 Python IPC 層：**
- `shared_types.py`：10 types（4 enum + 5 dataclass + PriceEvent），與 Rust 1:1 對齊
- `ipc_client.py`：EngineIPCClient + 自動重連 + 3 次失敗降級 + per-method TTL
- `ai_service.py`：AIService（5 agent handler stubs）+ AIServiceListener（Unix socket 服務端）

**R01-8~9 測試基礎設施：**
- conftest.py：shared_types 導入重定向 + SM 類標記 `TODO R-06`
- Golden schema (`schemas/shared_types.json`) + `schema_diff.py` 驗證 + CI 集成

**審查修復（E2 + E5）：**
- CRITICAL：StopConfig Rust `time_stop_minutes` → `time_stop_hours` + `atr_multiplier` 三方對齊
- HIGH：ai_service.py 從 length-prefix 統一為 newline-delimited 協議
- MEDIUM：ipc_client.py `ping()` 修正匹配 Rust `"pong"` 回應
- E5：ws_client.rs `extract_symbol_from_topic` 零分配 rsplit + ipc_client assert→explicit check

**測試：** Rust 65 passed / Python 3703 passed / 24 failed / 17 errors（零回歸）

---

### Phase 3 完成 — Claude API + 四階段放權 + HedgingEngine Rust（2026-04-03）

**Sub-phase 3A（Claude API 閉環）：**
- **3-1** APIBudgetManager：月度預算 $50 + per-tier 冷卻（l1_5=1800s, l2=3600s） + 持久化
- **3-2** ModelRouter 四級路由：l1_9b / l1_27b / l1_5 / l2 + 升級/阻止條件 + budget_checker 回調
- **3-3** Claude→TSR 閉環：knowledge_update 寫入 TruthSourceRegistry + confidence cap（0.90/0.85）+ prompt 查詢 TSR
- **3-5** PnL Attribution API：4 個只讀端點（summary/strategy/skill-ratio/trade）

**Sub-phase 3B（新模組 + 放權）：**
- **3-4** HedgingEngine **Rust+PyO3**：組合 delta 計算 + 對沖建議（linear/spot/inverse）
- **3-6** OB Imbalance：calculate_ob_imbalance + get_ob_signal 整合到 microstructure_builder
- **3-7** DelegationFramework：四階段遞進放權（FULL_HUMAN→AI_SUGGEST→AI_ACT_VETO→FULL_AI）+ 自動降級

**E5 修復（Phase 2 補跑）：** UTF-8 安全截斷 + paired_state 還原 + HurstHysteresis 提取 + L1 凍結
**審查：** E2 全部 PASS · E4 零回歸 3703/24/17

---

### E5 優化修復 + L1 凍結（2026-04-03）

- **E5-1** context_distiller.rs UTF-8 安全截斷：`summary[..80]` → `summary.chars().take(80).collect()`，防止中文 panic
- **E5-2** funding_rate_arb.py `_paired_state` 重啟還原：`restore_persistent_state()` 補齊 PairedExecutionState 反序列化
- **E5-3** HurstHysteresis 提取：從 market_regime.py（814→706 行）獨立為 hurst_hysteresis.py（129 行）
- **2-L1** L1 接口凍結：`git tag l1-interface-freeze`，Operator 簽核確認
- E2 審查：3/3 PASS · E4 回歸：3704 passed / 23 failed / 17 errors（+1 pass, -1 fail vs 基準）

---

### Phase 2 完成 — 策略 V2 + Agent 整合 + Rust 基礎設施（2026-04-03）

**策略 V2 升級（5 個策略全部完成）：**
- **2-1**：MA_Crossover V2 — KAMA + ADX>20 過濾 + 多時間框架確認
- **2-2**：BB_Reversion V2 — RSI<30 確認 + Hurst Regime 感知（trending 不交易）
- **2-3**：BB_Breakout V2 — Volume ratio>1.5 + Donchian 確認 + ATR trailing stop
- **2-4**：FundingRateArb V2 — PairedExecutionState + filled_qty 回滾（非 requested_qty）
- **2-5**：GridTrading V2 — OU 動態間距（σ/√θ + 2×fee_pct 下限）
- **2-6**：Regime Detection — HurstHysteresis（6 bar 確認）+ EWMA Vol 三維 regime

**Agent 整合（3 個任務）：**
- **2-7**：Strategist 雙軌 — 快速通道/正常通道 + _emergency_mode 競態保護 + CognitiveModulator 閉環
- **2-8**：ContextDistiller — **Rust+PyO3 首個模組** · Mutex 線程安全 · 4 區塊壓縮（market/portfolio/health/events）
- **2-9**：Ollama prompt 模板 — 結構化 JSON + cognitive/dream 欄位 + plain-text fallback

**Rust 基礎設施（R-00-mini）：**
- Cargo workspace (`Cargo.toml`) + `rust/openclaw_core/` crate
- PyO3 0.24 + maturin 構建 → Python 可直接 `import openclaw_core`
- 決策：新獨立模組 Rust+PyO3，修改現有文件繼續 Python

**測試基準**：3703 passed / 24 failed / 17 errors（+1 fail 為 pre-existing async 環境問題）
**業務完成度**：82% → ~93%

---

### Phase 1 完成 — Agent 感知工具箱 + 認知三模組（2026-04-03）

**新建模組（8 個文件）：**
- **1-1**：PositionSizer（已在 0B-3 完成）
- **1-2**：strategy_health_monitor.py — CUSUM 漂移檢測 + rolling Sharpe + 15 連虧硬性兜底
- **1-3**：ewma_vol_estimator.py — EWMA 波動率估計 + vol regime 分類
- **1-4**：hurst_exponent.py — R/S 重標極差分析 + 趨勢/均值回歸分類
- **1-5**：indicators/extended.py — KAMA + ADX + Hurst + EWMA Vol + Volume Ratio + Donchian
- **1-6**：cognitive_modulator.py — L0 決策門檻調製（[Q1] max 單因子 + [Q6] EMA α=0.3）
- **1-7**：opportunity_tracker.py — 虛擬 PnL 追蹤（[Q2] 2x fee + [Q3] 歸一化 + [R1-8] ≥5 樣本）
- **1-8**：dream_engine.py — 蒙特卡洛模擬（[Q4] ≥30 輪 + [Q5] binomial test）
- **1-9**：local_llm_client.py — ABC + OllamaProvider + LMStudioProvider
- **1-10**：shadow_decision_tracker.py — 四階段退出條件比較

**附帶修復**：SMA 改用 math.fsum()（V3-QC-2）+ indicator_engine.py 注冊 6 個新指標
**測試基準**：3704 passed / 23 failed / 17 errors（無回歸）
**業務完成度**：72% → 82%

---

### Phase 0-A + 0-B 完成 — 學習閉環 + 策略 Edge 驗證（2026-04-03）

**Phase 0-A（學習閉環 + 管線連通）：**
- **0A-1**：學習反饋閉環 — StrategistAgent.get_strategy_weight() + PipelineBridge 門控前應用學習權重
- **0A-2**：進化參數自動重部署 — evolution_routes.set_auto_deployer() B13 閉環
- **0A-3**：H0 Gate shadow 觀察模式 — shadow_mode 旗標 + _check_shadow() + shadow stats/log
- **0A-4**：Scanner→Deployer 驗證 — 確認已完整接通（無需修改）
- **0A-5**：Backtest 生產環境啟用 — AutoDeployer.set_backtest_engine() + 部署前回測驗證
- **0A-6**：L2 觸發門檻 50→20 — 加速 AI 模式發現反饋

**Phase 0-B（策略 Edge 驗證）：**
- **0B-1**：FundingRateArb 精算 — 滑點建模 + 基差風險追蹤 + 多周期攤薄 + get_cost_summary()
- **0B-2**：交易所 SL/TP 雙重防線 — SL 5% + TP 8%（PipelineBridge + Executor callback）
- **0B-3**：Kelly 資本配置 — position_sizer.py（Kelly 四層計算）+ tab-ai.html Kelly 卡片 + API 端點

**新建文件**：position_sizer.py（~306 行）
**測試基準**：3704 passed / 23 failed / 17 errors（改善 +1 pass / -1 fail）
**業務完成度**：52% → 72%

---

### Rust 遷移 V3-FINAL + 階段拆分 + 全路線圖定稿（2026-04-03）

- **Rust 遷移 V3-FINAL** 五角色三輪審查通過（V2→V2.5→嚴格論證 21 FAIL→V3 全部納入）
- 32,500 行 Rust · 14 週主開發 · Single-owner actor 零鎖 · QC 分級浮點容差
- Week 8 硬決策點（Go/No-Go · 50% 復用降級路徑）
- 8 個階段執行文件 `docs/rust_migration/R-00~R-07`，每個自包含上下文+進度追蹤
- 全路線圖定稿：Phase 0-3（功能 7 週）→ Phase R（Rust 14 週）→ 灰度 → Live
- Phase 1-3 新增里程碑：R-00 提前並行 · L1 接口凍結（Phase 2 結束）· L2 凍結（Phase 3 結束）
- 16 Agent profiles 已升級 Rust/認知自適應技能
- Live 前置條件新增：Rust 遷移完成或 PyO3 降級穩定

---

### 文檔治理 + 系統快照 + 根原則校準（2026-04-03 · commits 97e152c → edf4627）

**文檔治理（6 commits）：**
- README.md 全面更新：狀態日期→04-03、測試 3440→3704、業務完成度 45%→52%、Phase 路線圖重排
- 修正 "6 Agent" → "5 Agent + Conductor"（CLAUDE.md / README.md / CC profile / governance_extracts）
- 原則 #12 加 demo 階段說明（live 自動部署待 Phase 3 放權框架）
- 新增實施準則：認知調製 ≠ 能力限制（衍生自原則 #11，否決代謝模型和內部經濟體）
- 明確 Bybit 專攻決策：Binance 排除當前開發範圍，僅作超長期可能方向
- 5 個 governance_extracts 標記 OUTDATED + 指向權威文件
- SYSTEM_STATUS_REPORT.md 歸檔到 docs/references/
- 跨平台部署說明加入 README（macOS 遷移路徑）

**系統快照（1 commit）：**
- 生成 SYSTEM_SNAPSHOT.md（8 章節：結構樹 / 15 模組簽名 / 啟動流程 / 數據流 / 線程架構 / 性能路徑 / 配置管理 / 外部依賴）
- 供外部 Claude session 分析系統架構

**跨平台兼容性審計（2 commits，by user）：**
- CLAUDE.md §七新增跨平台強制規則（路徑不硬編碼 / LLM 抽象 / systemd→launchd / 依賴管理）
- XP-1~4 P0 審計任務完成

**其他（by user）：**
- 中期路線圖 Phase 0-3 制定（7 週 · 4-Agent 分析）
- Agent 認知自適應 SPEC V1.1+R1（見下方獨立條目）
- 16 Agent workspace profiles 升級

---

### Agent 認知自適應 SPEC V1.1+R1 五角色審查通過（2026-04-03）

**內容**：V3 報告補充規範，三個 L0 新模組的完整設計（零 API 成本，純本地計算）

- **CognitiveModulator**（0.5d）：根據歷史表現動態調整 confidence floor / qty ceiling / SL multiplier / scan interval
- **OpportunityTracker**（1.0d）：追蹤被 Scout/Strategist/Guardian 篩掉的機會虛擬 PnL → 遺憾歸因
- **DreamEngine**（2.0d）：閒置時用真實 K 線跑蒙特卡洛模擬 → 參數優化建議

**五角色審查（PM/PA/FA/E5/QC）+ 兩輪審計**：
- QC 數學修正 6 項：多因子取 max（防隱性停機）· 虛擬 PnL 扣 fee（防系統性高估）· 歸一化遺憾方向 · 每參數 ≥30 輪模擬 · binomial test 置信度 · EMA 平滑
- E5 代碼修正 6 項：拆分 _compute_*() · bullets_dodged 重命名 · _flush_closed · 緩存 · threading.Lock · 隨機方向
- Round 1 修正 10 項：scan 雙向 · 緩存失效 · 防重入 · asyncio.to_thread · 連虧忽略負向 · import 頂層 · 估時調整 · 最少 5 樣本 · fee 注釋 · 可選 seed
- 最終判定：5/5 APPROVE
- 開發位置：Phase 1 並行組 B（1.10/1.11/1.12），總計 3.5d，不影響關鍵路徑
- SPEC 文件：`docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md`

---

## Wave 進度總表（§十三.4 遷出）

```
Wave 0：✅ P0（5 項）全部完成 + P1（5 項）全部完成（E2+E4 通過）
Wave 1：✅ PA-4.3 DI 統一（26 Depends）+ HTTPException 穿透（E2+E4 通過）
Wave 2：✅ P0-8/P1-1/P1-2/P1-6/P1-8/P1-9/P1-13/P1-18 全部完成（E2+E4 通過）
Wave 3a：✅ P0-NEW-1/2/3 全部完成（E2+E4 通過，commit c6a8845）
Wave 3b：✅ P1-NEW-1~7 全部完成（E2+E4 通過，commit 2eda4ec）
Wave 3c：✅ P1-4/P1-10/P1-17 完成（E2+E4 通過，commit bf75254）
P1-16：✅ Day 1+2+3 全部完成，已 merge（commit 03a5b29）
Wave 4 Sprint 4a：✅ P2-NEW-1/2/6（commit a2f4c70）
Wave 4 Sprint 4b：✅ P2-NEW-3/4 + P3-TECH-1/2/3（commit 6c80bc9）
Wave 4 Sprint 4c：✅ P2-NEW-7/8（commit 448f1e7）
Wave 4 Sprint 4d：✅ FA-2/3/4（commit 9cc134a）
Wave 4 Sprint 4e：✅ P2-NEW-9 + P2-NEW-5（commit 87c2651）
Wave 5a：✅ Position Sizing 重構 — 3% risk + 動態 qty + 智能資本再分配（commit 8223eb9）
Wave 5b：✅ Paper/Demo 同步修復 — 3 CRITICAL + 2 MODERATE
Wave 5 Sprint 0：✅ G-05 acquire_lease + G-01 AI daily cap $15→$2（commit d57ed05）
Wave 5 Sprint 5a：✅ H0 blocking + H1 ThoughtGate + shadow=False + H2/H3 ModelRouter（commit ccdff73）
Wave 5 Sprint 5b：✅ H4 validate_output + H5 record_ollama_call + ScoutWorker + P14 集成測試（commit 9478c00）
Wave 6 Sprint 0：✅ TD-1 pipeline_bridge acquire_lease（原則 3 缺口）（commit aafb18b）
Wave 6 Sprint 1a：✅ FA-7 _check_stops 學習管線注入（原則 12）（commit 8f123a7）
Wave 6 Sprint 1b：✅ 1B-1~4 Cooldown + freshness + cost_tracker + LRU cap（commit 8f123a7）
Wave 6 Sprint 2：✅ P2-6/7/8 risk bounds + P2-12/15 pipeline edge（commit 43dd2f5）
Cleanup Sprint：✅ H0 stale→False + GovernanceHub API + startup integrity + MessageBus load tests（commit 973c595）
Phase 2 Batch 2A：✅ TruthSourceRegistry + Agent 集成 + 46 測試（commit cf7ef5d）
Phase 2 Batch 2B：✅ BacktestEngine MVP + 57 測試（commit cf7ef5d）
Phase 2 Batch 2C：✅ _register_pattern_claims 接通 + backtest_routes + 決策權重集成（commit 5794db1）
Demo 停止補強：✅ cancel_all_orders() + 停止序列改進（commit 2fba698）
Wave 7：✅ Demo 同步修復 — Paper 內部平倉 Demo 同步 + stop_session 自動清倉（commit ab31353）
Wave 7a：✅ Spot 品類啟用 — SPOT-1~5（commit 054d1ae）
方案 A：✅ SymbolCategoryRegistry — 啟動時 API 批量填充（commit a0f87b6）
Wave 7b：✅ Inverse 品類完善 — INV-1~5，32 個測試，動態滑點
Phase 3 Batch 3A：✅ ExperimentLedger + ExperimentRoutes + EvolutionEngine — 88 新測試，3289 passed
Phase 3 Batch 3B+3A-4：✅ TruthSourceRegistry 持久化 + auto_seed + EvolutionRoutes — 3310 passed
Phase 3 Batch 3C：✅ 排程器 daemon + GUI 實驗/進化 dashboard — 3330 passed
Governance Auth 修復：✅ get_status() + /session/reauth + startup 自動補授（commit d065453）
April 1 Audit Batch 1-6：✅ 8 份審計 + 6 批次全部完成 — 3387 passed
Batch 7 積壓清掃：✅ 8 並行 Agent — 3440 passed
main_legacy.py 重構 Wave A-D：✅ 5265→423 行（-92%），拆出 8 模塊，3005 tests 零回歸
Wave 8 PA 實況檢查：✅ 69 項審計交叉驗證 → 38/39 項修復，+148 新測試達 3637+
```

---

## §三 詳細開發記錄（按時間順序）

### Round 2 冷酷功能審核（2026-03-30）

代碼完成度 ≈ 80%，業務功能真正能用 ≈ 45%

逐環節完成度：
- 自動掃描 = 90%（ScoutWorker 30min 定時掃描 + Scout→Strategist bus 鏈路已接通）
- 策略選擇 = 40%（標準技術指標，無 AI、無回測、無動態倉位）
- AI 風險評估 = 55%（H0+H1+H2+H3+H4+H5 全部接通）
- 下單 = 90%（治理 gate + OMS SM-03 + ExecutorAgent 包裝）
- 止損 = 90%（本地 3 類止損 + 交易所條件單雙重防線）
- 學習 = 25%（E1 觀察 + L2 自動觸發 + Sunday cron）
- 進化 = 30%（PaperLiveGate 已部署，無策略自動優化）

關鍵發現：
- ✅ 治理 fail-closed 一流 / P0/P1/P2 風控真實執行 / 異常處理防禦性
- ✅ 5/6 Agent 已實現 / ExecutorAgent 接入管線 / L2 自動觸發
- ❌ Perception Plane register_data() 零調用
- ❌ 策略層標準 RSI/MACD/MA，無可證明的 alpha

詳細報告：docs/governance_dev/audits/2026-03-30--round2_cold_functional_audit.md

### Phase 0 Cowork Round 2.5 審計（2026-03-31）

- P0 修復：MessageBus.subscribe() 3→2 參數 bug / layer2_engine "not worth" 文本解析 bug
- 287 條治理規格 Gap 分析：76% 已實施（67A + 18B + 8C + 2D）
- 關鍵缺失：H0 Gate / 回測引擎 / L3-L5 學習
- 詳細報告：docs/governance_dev/audits/2026-03-31--gap_analysis_287_specs.md

### 7-Agent 全系統審計（2026-03-31）

規模：71 測試文件 / 2,480 測試用例 / 53 app 模組 / 全 HTML/JS/CSS
發現：71 項問題（去重）· P0: 8 / P1: 18 / P2: 29 / P3: 16

4 個 CRITICAL 問題（全部已修復）：
1. /openclaw/{path} 反向代理添加認證
2. _require_operator_role() isinstance 類型錯誤
3. GovernanceHub=None 時 submit_order() fail-closed
4. Guardian=None 時 pipeline_bridge.py fail-closed

合規度 CC B 級 / 安全評級 0 CRITICAL / 0 HIGH / 2 MEDIUM / 3 LOW

### Wave 5a Position Sizing 重構（2026-03-31）

- risk_per_trade_pct 2%→3%（每筆最大虧損 = 總額 3%）
- max_symbols 10→25
- 動態 qty + 智能資本再分配 + risk/stop 反推名義金額

### Wave 5b Paper/Demo 同步修復（2026-03-31）

3 CRITICAL + 2 MODERATE：止損同步 / 失敗標記 / 對賬參數名 / qty 統一 / 條件止損 qty

### Wave 5 Sprint 0 BLOCKER 修復（2026-03-31 · commit d57ed05）

- G-05：executor_agent.py 插入 acquire_lease()（原則 3 硬違反修復）
- G-01：DEFAULT_DAILY_HARD_CAP_USD 15.0→2.0

### Wave 5 Sprint 5a H1-H5 核心接通（2026-03-31 · commit ccdff73）

Scout→Strategist bus 鏈路 / H0 blocking / H1 ThoughtGate MVP / shadow=False / H2 預算 / H3 ModelRouter

### Wave 5 Sprint 5b Agent 落地完善（2026-03-31 · commit 9478c00）

H4 AI 輸出驗證 / H5 CostLogger / apply_ai_consultation DEPRECATED / ScoutWorker daemon / P14 集成測試

### Wave 6 Sprint 0-2（2026-03-31）

- Sprint 0：pipeline_bridge acquire_lease（原則 3 缺口）
- Sprint 1a：_check_stops 學習管線注入（原則 12）
- Sprint 1b：Cooldown smoke test + freshness API + cost_tracker + LRU cap
- Sprint 2：RiskManager qty/price bounds + pipeline edge + collect DEPRECATED + GUI null fix

### Cleanup Sprint（2026-03-31 · commit 973c595）

H0 stale→False / GovernanceHub.is_globally_enabled() / startup integrity check / MessageBus load tests

### Phase 2 Batch 2A-2C（2026-03-31 ~ 2026-04-01）

- 2A：TruthSourceRegistry + AnalystAgent/StrategistAgent 集成 + 46 測試
- 2B：BacktestEngine MVP（純函數指標 + _BacktestKlineAdapter + 57 測試）
- 2C：_register_pattern_claims 接通 + backtest_routes API + 決策權重集成

### Demo 停止清倉補強 + Wave 7 Demo 同步（2026-04-01）

- cancel_all_orders()（普通單 + 條件單）
- Paper 內部平倉 Demo 同步：_sync_close_to_demo() / stop_session 雙遍歷清倉

### Wave 7a Spot + 方案 A SymbolCategoryRegistry + Wave 7b Inverse（2026-04-01）

- Spot 品類：SPOT-1~5 全通（634 幣對）
- SymbolCategoryRegistry：啟動時 API 批量填充 + 運行時部署更新雙層架構
- Inverse 品類：INV-1~5 全通（27 幣對）+ 動態滑點分級

### Phase 3 Batch 3A-3C（2026-04-01）

- 3A：ExperimentLedger + ExperimentRoutes + EvolutionEngine（88 新測試）
- 3B+3A-4：TruthSourceRegistry 持久化 + auto_seed + EvolutionRoutes
- 3C：EvolutionScheduler daemon（週進化 + 小時清理）+ GUI dashboard

### Governance Auth 重啟丟失修復（2026-04-01 · commit d065453）

根因：GovernanceHub 授權為純記憶體狀態，重啟後歸零
修復：get_status() auth_pending_approval + /session/reauth 端點 + startup 自動補授

### April 1 全系統審計 + 6 Batch 修復（2026-04-01）

審計：AI-E(B+) / E5(54項) / E4(3310/96files/~68%) / E3(0C/1H/5M/4L) / CC(A-,14/16) / FA(52%) / TW(82.5%) / R4(12項)
Batch 1-6 全部完成：知識閉環 / BacktestEngine 285x / L2 快取 / HttpOnly cookie / 鎖縮窄

### Batch 7 積壓清掃（2026-04-01）

pipeline_bridge 拆分 / Conductor 編排 / 194 logger %s / Pydantic 驗證 / MODULE_NOTE 補全

### main_legacy.py 重構 Wave A-D（2026-04-01）

```
Wave A：state_models + state_compiler + state_store = -1210 行（5265→4056）
Wave B：auth + state_helpers = -297 行（4099→3802）
Wave C：control_ops + pnl_ops + learning_ops = -2363 行（3802→1439）
Wave D：legacy_routes = -1016 行（1439→423）
總計：-92%，拆出 8 模塊，3005 tests 零回歸
```

### Wave 8 PA 實況檢查 + 並行修復（2026-04-01）

PA 交叉驗證：69 項審計結果逐一比對代碼（29 確認/10 部分/20 已修/10 誤報）
6 軌道並行 × 2 批次 = 38/39 項完成
- Wave 8A 安全+正確性（8 項）
- Wave 8B 代碼質量（12 項）
- Wave 8C 架構改進（7 項）：strategist 1152→780 行拆 4 模組
- Wave 8D 文檔清理（5 項）
- B3+B4 核心拆分：on_tick 4 子方法 + mutator 5 子函數
commits: 533a71a + 4782c96 + 6b494a6 · +148 新測試

### FA 完成度與 GAP 審核（2026-04-01）

代碼完成度 ~80%，業務功能真正能用 ~52%
7 項關鍵 GAP：
- P0-GAP-1：學習反饋閉環斷開
- P0-GAP-2：進化參數不自動重部署
- P1-GAP-3：H0 Gate warn-only
- P1-GAP-4：交易所條件單未實作
- P1-GAP-5：MarketScanner → Deployer 未接通
- P1-GAP-6：Backtest 生產環境未啟用
- P2-GAP-7：L2 觸發門檻過高
詳細報告：docs/governance_dev/audits/2026-04-01--fa_completion_gap_audit.md

### P0 ~ Wave 3c 修復記錄（2026-03-31）

- P0 修復（5 E1 並行）：governance_routes isinstance / pipeline_bridge Guardian=None / paper_engine Hub=None / openclaw_proxy 認證 / layer2_engine negation
- Wave 0 P1：ollama max_retries=0 / subprocess 分隔符 / 日誌路徑 / 憑證緩存 / 日誌注入修復
- Wave 1：DI 統一（26 Depends）+ HTTPException 穿透
- Wave 2：compile_state cache / auth 速率限制 / XSS / governance env var / 測試覆蓋補強
- Wave 3a：/reconcile 角色驗證 / detail=str(e)→固定字串
- Wave 3b：proxy header 過濾 / WeakKeyDict / asyncio.Lock / token 統一 / _OC_HOST 緩存
- Wave 3c：lease expires_at_ms / PerceptionPlane 測試 / is_authorized 鎖修復

### H0 Gate（P1-16）三天實現（2026-03-31）

- Day 1：h0_gate.py 651 行，5 個確定性 check，SLA <5μs
- Day 2：H0HealthWorker 背景線程，40 測試，SLA <0.5ms avg
- Day 3：Pipeline/Routes/Risk 集成，18 集成測試

### GUI + Ollama 優化（2026-03-31）

- Paper+Demo 合併為「測試交易」子 Tab + 「實盤交易」鎖定占位 Tab
- think=False 修復：9B 8.7s→1.9s，27B 21s→9.9s
- 模型分配：9B 快速路徑 / 27B 複雜任務 / ScoutWorker daemon
- 後台市場流常駐 / 週報雙層（Ollama + Claude L2）

---

## §十一 已完成的路線圖（歷史歸檔）

```
已完成摘要：
  ✅ A-L 全部章節 + 策略工具包 + 管線橋接 + 全系統審核
  ✅ GUI 三層架構 + 11-Tab 專業控制台
  ✅ 自主交易 Agent（市場掃描器 650 符號 + 策略自動部署）
  ✅ Phase 2 治理模組 T2.01–T2.23（21 模組 · 1,522 測試）
  ✅ Phase 3 GovernanceHub 集成（4SM 接入 + 安全審核）
  ✅ Round 2 Batch 3-12 全部完成（5 Agent + OMS + PaperLiveGate + E2E）
  ✅ L1 本地推理（Ollama + Qwen 3.5）+ 0% 勝率四根因全修復
  ✅ 7-Agent 全系統審計（71 項問題 · 4 CRITICAL · 全部修復）
  ✅ Wave 0-8 全部完成
  ✅ Phase 1-3 開發路線圖全部完成
  ✅ main_legacy.py 重構完成（-92%）

開發路線圖 v2（已完成）：
  Phase 1: H0 Gate ✅ + Cooldown 聯動 ✅
  Phase 2: TruthSourceRegistry ✅ + BacktestEngine ✅
  Phase 3: ExperimentLedger ✅ + EvolutionEngine ✅ + EvolutionScheduler ✅
```
