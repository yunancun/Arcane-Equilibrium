# E4 全程式測試審計報告 / Full-Program Test Audit Report

**日期**：2026-04-12
**審計人**：E4 (Test Engineer)
**範圍**：openclaw_engine (lib + e2e) + openclaw_core (lib) + Python tests

---

## 一、測試基線 / Test Baseline

| 套件 | 通過 | 失敗 | 忽略 |
|------|------|------|------|
| `openclaw_engine` lib | **934** | 0 | 0 |
| `openclaw_engine` e2e (integration + stress + reconciler + audit) | **54** | 0 | 0 |
| `openclaw_core` lib | **366** | 0 | 0 |
| `openclaw_types` lib | **27** | 0 | 0 |
| Python (pytest collected) | **2857** | 0* | 0 |
| **合計** | **4238** | 0 | 0 |

\* Python 有 collection warning（test_app，非代碼問題）。
\*\* e2e 含 4 測試文件：`phase4_integration.rs`(29) + `reconciler_e2e.rs`(18) + `rrc1_audit_tests.rs`(4) + `stress_integration.rs`(3)。

---

## 二、模組覆蓋率矩陣 / Coverage Gap Matrix

### openclaw_engine — 按模組測試密度

| 模組 | 代碼行數 | 測試數 | 密度(tests/kLOC) | 嚴重度 | 備註 |
|------|----------|--------|------------------|--------|------|
| `edge_estimates.rs` | 332 | 14 | 42.2 | OK | ~~原報誤判零測試~~ 實有 14 tests（含 empty/valid/malformed JSON + boundary） |
| `startup.rs` | 960 | 5 | 5.2 | P2-MEDIUM | ~~原報誤判零測試~~ 實有 5 tests，覆蓋不足但非零 |
| `tasks.rs` | 506 | **0** | **0** | **P1-HIGH** | 後台任務調度，含 spawner 邏輯 |
| `pipeline_types.rs` | 170 | **0** | **0** | P2-MEDIUM | 純類型定義，風險較低 |
| `main.rs` | 970 | **0** | **0** | P2-MEDIUM | 組裝入口，難單測但 catch_unwind 路徑未驗 |
| `ipc_server/` | 3,302 | 49 | 14.8 | P2-MEDIUM | handlers.rs 1245 行覆蓋尚可 |
| `database/rest_poller.rs` | 155 | **0** | **0** | **P1-HIGH** | REST 輪詢邏輯零測試 |
| `database/quality_writer.rs` | 109 | **0** | **0** | P2-MEDIUM | 品質寫入器零測試 |
| `claude_teacher/` | 3,825 | 61 | 16.0 | OK | ~~原報誤判零測試~~ 10 文件中 8 個有測試（`#[tokio::test]` 為主，client.rs 注釋誤計修正） |
| `on_tick.rs` | 1,049 | **0** (inline) | **0** | P2-MEDIUM | 透過 tick_pipeline/tests.rs 間接覆蓋 63 tests |
| `orchestrator.rs` | 233 | 5 | 21.5 | OK | 基本功能覆蓋 |
| `fast_track.rs` | 137 | 8 | 58.4 | OK | 所有 risk level 路徑已覆蓋 |
| `position_manager.rs` | 845 | 12 | 14.2 | P2-MEDIUM | 解析測試為主，業務邏輯測試不足 |
| `paper_state.rs` | 839 | 14 | 16.7 | P2-MEDIUM | 含 B-1 回歸測試 |
| `event_consumer/handlers.rs` | 543 | **0** | **0** | **P1-HIGH** | ~~原報遺漏~~ 核心事件分派邏輯零測試 |
| `intent_processor/router.rs` | 499 | **0** | **0** | **P1-HIGH** | ~~原報遺漏~~ 意圖路由器零測試 |
| `position_reconciler/escalation.rs` | 377 | **0** | **0** | P2-MEDIUM | ~~原報遺漏~~ 升降級邏輯零測試 |
| `news/rss.rs` | 179 | **0** | **0** | P2-MEDIUM | ~~原報遺漏~~ RSS feed 解析零測試 |
| `news/cryptopanic.rs` | 137 | **0** | **0** | P2-MEDIUM | ~~原報遺漏~~ CryptoPanic 客戶端零測試 |
| `scanner/runner.rs` | 261 | **0** | **0** | P2-MEDIUM | ~~原報遺漏~~ 掃描器運行器零測試 |
| `database/outcome_backfiller.rs` | 149 | **0** | **0** | P2-MEDIUM | ~~原報遺漏~~ 回填器零測試 |
| `event_consumer/dispatch.rs` | 161 | **0** | **0** | P2-MEDIUM | ~~原報遺漏~~ 事件分派零測試 |
| `market_data_client/types.rs` | 219 | **0** | **0** | P2-MEDIUM | ~~原報遺漏~~ 市場數據類型零測試 |
| `claude_teacher/writer.rs` | 249 | **0** | **0** | P2-MEDIUM | 教師模組寫入器零測試 |

### openclaw_engine — 原報遺漏但有良好覆蓋的模組

| 模組 | 代碼行數 | 測試數 | 密度 | 備註 |
|------|----------|--------|------|------|
| `bybit_rest_client.rs` | 1,172 | 20 | 17.1 | 含 timeout config + transport error + response parsing |
| `ws_client.rs` | 942 | 16 | 17.0 | 消息解析 + backoff 計算 |
| `bybit_private_ws.rs` | 992 | 15 | 15.1 | 私有 WS 消息解析 |
| `multi_interval_ws.rs` | 258 | 8 | 31.0 | 多週期 WS 管理 |
| `persistence.rs` | 362 | 8 | 22.1 | 狀態持久化 |
| `news/` (有測試部分) | 1,906 | 85 | 44.6 | router/severity/dedup/guardian/learning/mock |
| `event_consumer/` (有測試部分) | 1,184+887 | ~25 | ~12 | cooldown + 高層路徑 |

### openclaw_engine — 高測試密度模組（良好）

| 模組 | 代碼行數 | 測試數 | 密度 |
|------|----------|--------|------|
| `config/` | 3,832 | 84 | 21.9 |
| `strategies/` | 4,514 | 82 | 18.2 |
| `tick_pipeline/` | 4,495 | 63 | 14.0 |
| `database/` | 5,350 | 60 | 11.2 |
| `scanner/` | 2,289 | 53 | 23.1 |
| `risk_checks.rs` | 498 | 25 | 50.2 |
| `position_reconciler/` | 1,455 | 33 | 22.7 |
| `intent_processor/` | 1,837 | 36 | 19.6 |

\* tick_pipeline 的 63 tests 包含間接覆蓋 on_tick.rs 邏輯。

### openclaw_core — 所有模組均有測試（良好）

| 模組 | 代碼行數 | 測試數 | 密度 |
|------|----------|--------|------|
| `sm/` | 3,315 | 57 | 17.2 |
| `indicators/` | 1,326 | 35 | 26.4 |
| `signals/` | 1,196 | 30 | 25.1 |
| `h0_gate.rs` | 1,067 | 30 | 28.1 |
| `risk/` | 537 | 22 | 41.0 |
| `klines.rs` | 1,086 | 22 | 20.3 |
| `dream.rs` | 936 | 20 | 21.4 |
| `opportunity.rs` | 861 | 18 | 20.9 |
| `execution.rs` | 346 | 18 | 52.0 |
| `cognitive.rs` | 524 | 13 | 24.8 |
| `cost_gate.rs` | 250 | 11 | 44.0 |
| `guardian.rs` | 314 | 6 | 19.1 |

---

## 三、正常路徑測試評估 / Happy-Path Coverage

### 3.1 策略信號 → 意圖 → 門控 → 訂單 → 成交 → PnL

| 路徑段 | 覆蓋 | 測試位置 | 備註 |
|--------|------|----------|------|
| 策略 `on_tick()` 產生信號 | **PASS** | `strategies/*/tests` (81 tests) | 5 策略各有完整 entry/exit/boundary 測試 |
| Orchestrator 收集 intents | **PASS** | `orchestrator::tests` (5 tests) | dispatch + inactive skip |
| IntentProcessor 門控 | **PASS** | `intent_processor::tests` (36 tests) | cost_gate/guardian/Kelly/D15/governance |
| TickPipeline 訂單執行 | **PASS** | `tick_pipeline::tests` (61 tests) | open/close/fill/stats |
| Paper PnL 計算 | **PASS** | `paper_state::tests` + stress | long/short/accumulate/close |
| 資料庫 fill 寫入 | **PASS** | `database::trading_writer::tests` | batch routing + limits |

**結論**：核心交易管線 happy-path 完整覆蓋。

### 3.2 Kline Bootstrap → 指標 → 信號

| 路徑段 | 覆蓋 | 測試位置 |
|--------|------|----------|
| KlineManager 數據管理 | **PASS** | `klines::tests` (22 tests) |
| IndicatorEngine 計算 | **PASS** | `indicators/tests` (35 tests) |
| SignalEngine 信號生成 | **PASS** | `signals/tests` (30 tests) |

---

## 四、邊界測試評估 / Boundary Tests

### 4.1 已覆蓋的邊界

| 邊界場景 | 測試 | 位置 |
|----------|------|------|
| Zero balance → skip position check | **PASS** | `risk_checks::tests::test_order_zero_balance_position_check` |
| Max positions exceeded | **PASS** | `stress_guardian_rejects_position_count_limit` (e2e) |
| D15 exact boundary allows | **PASS** | `intent_processor::tests::test_d15_global_cap_exact_boundary_allows` |
| D15 cap disabled when zero/negative | **PASS** | 2 tests |
| Entry price zero → no NaN | **PASS** | `rrc1_audit_tests::test_entry_price_zero_does_not_nan` |
| ATR zero → fail-closed | **PASS** | `test_sec11_cost_gate_fail_closed_on_zero_atr` |
| Exactly 5% drop → fast_track | **PASS** | `stress_fast_track_boundary_exactly_5pct_drop` |
| Exactly 90% margin → fast_track | **PASS** | `stress_fast_track_boundary_exactly_90pct_margin` |
| Extreme prices (BTC $1M) | **PASS** | `stress_full_pipeline_extreme_prices` |
| Zero volume ticks | **PASS** | `stress_full_pipeline_zero_volume_ticks` |
| Tiny balance position sizing | **PASS** | `test_position_sizing_tiny_balance` |
| Cooldown exactly at boundary | **PASS** | `event_consumer::cooldown_tests::boundary_at_exactly_cooldown_treated_as_expired` |
| Clock skew (future timestamps) | **PASS** | `future_timestamp_clock_skew_returns_none` |

### 4.2 缺失的邊界測試 **[GAP]**

| 邊界場景 | 嚴重度 | 應新增位置 |
|----------|--------|-----------|
| **Price = 0.0 的 tick** | **P1-HIGH** | `tick_pipeline/tests.rs` — 0 價格可能導致 division by zero |
| **f64::MAX / f64::INFINITY 價格** | P2-MEDIUM | `risk_checks.rs` / `paper_state.rs` |
| **NaN propagation in PnL** | P2-MEDIUM | `paper_state.rs::close_position()` |
| **max_same_direction 正好等於上限** | P2-MEDIUM | `risk_checks.rs` |
| **25 symbols 同時到達 max** | P2-MEDIUM | `orchestrator.rs` — 當前最大壓測 5 symbols |
| **Config 驗證後的邊界值運行** | P2-MEDIUM | 驗證通過的最小/最大值是否能實際運行 |
| ~~Edge estimates 空 JSON / 畸形 JSON~~ | ~~P1-HIGH~~ | ~~已有 14 tests 覆蓋 empty/valid/malformed JSON~~ **[原報誤判，已撤銷]** |
| **Scanner 0 active symbols** | P2-MEDIUM | `scanner/registry.rs` |
| **Notional 正好等於 min_order_notional** | P2-MEDIUM | `intent_processor` |

---

## 五、異常測試評估 / Error Handling Tests

### 5.1 已覆蓋的異常路徑

| 異常場景 | 覆蓋 | 位置 |
|----------|------|------|
| IPC invalid JSON | **PASS** | `ipc_server::tests::test_dispatch_invalid_json` |
| IPC method not found | **PASS** | `ipc_server::tests::test_dispatch_method_not_found` |
| IPC missing version/method | **PASS** | 2 tests |
| Config missing file → defaults | **PASS** | `config::io::tests` |
| Config invalid TOML → error | **PASS** | `config::io::tests` |
| Config validation rollback | **PASS** | `config::store::tests::test_apply_patch_validation_failure_rolls_back` |
| DB pool invalid URL → graceful | **PASS** | `database::pool::tests` |
| DB pool disabled → None | **PASS** | `database::pool::tests` |
| Fallback file rotation | **PASS** | `database::fallback::tests` |
| REST client retCode error | **PASS** | `bybit_rest_client::tests::test_bybit_response_error` |
| REST client deserialization error | **PASS** | `test_deserialize_error_response` |
| WS parse missing fields | **PASS** | `test_parse_kline_item_missing_close`, `test_parse_trade_item_missing_price` |
| Strategy params invalid TOML → defaults | **PASS** | `test_load_strategy_params_invalid_toml_returns_defaults` |
| Submit order invalid side | **PASS** | `event_consumer::tests::test_f_submit_order_invalid_side_rejected` |
| Submit order no price | **PASS** | `test_f_submit_order_no_price_rejected` |
| Submit order while paused | **PASS** | `test_f_submit_order_paused_rejected` |
| Fee charge rejects garbage (NaN/Inf/negative) | **PASS** | `test_paper_state_charge_fee_rejects_garbage` |

### 5.2 缺失的異常測試 **[GAP]**

| 異常場景 | 嚴重度 | 備註 |
|----------|--------|------|
| **REST API timeout 行為** | **P0-CRITICAL** | 硬邊界要求 fail-closed 不重試，但無測試驗證 |
| **WS 斷線重連行為** | **P1-HIGH** | ws_client.rs 有 `test_backoff_calculation`，但無模擬斷線→重連→replay 流程測試 |
| **Live catch_unwind panic recovery** | **P1-HIGH** | main.rs 有 catch_unwind，但無測試驗證 panic 後系統行為 |
| **DB 寫入全失敗（PG down）** | P2-MEDIUM | fallback 有測試，但完整 pipeline 在 DB 全掛時的行為未驗 |
| **Config 熱重載期間 tick 到達** | **P1-HIGH** | ArcSwap 語義正確但無並發測試 |
| **IPC socket 連接風暴** | P2-MEDIUM | 大量並發 IPC 請求未壓測 |
| **News pipeline provider 全部失敗** | P2-MEDIUM | scheduler 容錯邏輯未測 |

---

## 六、並發測試評估 / Concurrency Tests

### 6.1 已有的並發測試

| 場景 | 位置 | 方法 |
|------|------|------|
| ConfigStore 並發 patch | `config::store::tests::test_concurrent_patches_serialise` | 多線程寫入 + 斷言版本序列化 |
| Reconciler 原子 risk level | `position_reconciler::tests` | AtomicU8 repr 穩定性測試 |
| Stress 多 symbol 同時 tick | `stress_multi_symbol_5_coins_simultaneous_ticks` | 5 symbols 交替 tick |
| Stress 100 cycle 翻轉 | `stress_100_cycles_rapid_drift_clean_alternation` | 快速升降級 |
| Stress 50 symbols burst | `stress_50_symbols_simultaneous_drift` | 高並發漂移 |

### 6.2 缺失的並發測試 **[GAP]**

| 場景 | 嚴重度 | 備註 |
|------|--------|------|
| **三管線（Paper/Demo/Live）同時寫 shared state** | **P0-CRITICAL** | 3E-ARCH 架構核心，Vec\<Sender\> 扇出但無三管線同時運行測試 |
| **Scanner symbol 更新時 tick 到達** | **P1-HIGH** | active_symbols 改變可能影響正在處理的 tick |
| **Config hot-reload during on_tick** | **P1-HIGH** | ArcSwap load() vs store() 的語義安全未驗證 |
| **IPC handler 與 tick 並發操作 paper_state** | **P1-HIGH** | 如 import_positions 與 on_tick 同時執行 |
| **多 Provider 同時寫新聞 DB** | P2-MEDIUM | news pipeline 並發寫入 |
| **Reconciler escalation 與 tick fast_track 同時觸發** | P2-MEDIUM | 雙重風控動作衝突 |

---

## 七、回歸測試評估 / Regression Tests

### 7.1 已有回歸測試

| Bug ID | 描述 | 回歸測試 | 位置 |
|--------|------|----------|------|
| **PNL-FIX-1** | 跨 symbol 平倉用錯價格 | **PASS** ✅ | `tick_pipeline/tests.rs:1023` — `test_close_position_at_symbol_market_uses_per_symbol_price` |
| **PNL-FIX-1 fallback** | 無 latest_price 時 fallback | **PASS** ✅ | `tick_pipeline/tests.rs:1083` — `test_close_position_at_symbol_market_fallback_to_entry_when_no_latest_price` |
| **PNL-FIX-2** | 平倉 fee=0 | **PASS** ✅ | `tick_pipeline/tests.rs:1112` — `test_emit_close_fill_charges_real_close_fee` |
| **PNL-FIX-2 validation** | charge_fee 拒絕非法值 | **PASS** ✅ | `tick_pipeline/tests.rs:1209` — `test_paper_state_charge_fee_rejects_garbage` |
| **B-1** | Position import 覆蓋 | **PASS** ✅ | `paper_state.rs:797` — `test_import_positions_seeds_state` |
| **B-2** | execution.fast topic + total_fills | **PASS** ✅ | `bybit_private_ws.rs:788` + `tick_pipeline/tests.rs:494` |
| **3E-ARCH** | emit_close_fill db_mode() | **PASS** ✅ | `tick_pipeline/tests.rs:39` |
| **D6** | 跨引擎故障級聯 | **PASS** ✅ | `event_consumer::tests` — 3 cascade tests |
| **D23** | Reconciler snapshot | **PASS** ✅ | `tick_pipeline/tests.rs:957` |

### 7.2 缺少回歸測試的已知問題 **[GAP]**

| 問題 | 嚴重度 | 備註 |
|------|--------|------|
| **Grid 庫存漂移 P1** | P2-MEDIUM | CLAUDE.md 記載的 grid_trading 問題，無專用回歸測試 |
| **Exchange Kelly P2** | P2-MEDIUM | Kelly 公式用於 exchange 路徑的問題 |
| ~~fast_track 硬編碼 0 的死碼~~ | ~~P2-MEDIUM~~ | **[原報誤判，已修復]**：FIX-03+04（commit `283ae33`）已接入真實 `price_drop_pct`（price_tracker.max_drop_pct()）和 `margin_utilization_pct`（position notional / balance） |
| **paper_state.json 三引擎搶寫** | **P1-HIGH** | `with_kind()` 補設 `pipeline_kind` 字段（commit c9d9bc5），但無回歸測試驗證隔離 |

---

## 八、壓力/性能測試評估 / Stress Tests

### 8.1 現有壓力測試（54 e2e tests 中的壓力/集成測試子集）

| 類別 | 測試數 | 涵蓋場景 |
|------|--------|----------|
| Fast track 風控觸發 | 8 | flash crash / defensive / boundary |
| 多 symbol 並發 | 2 | 5 coins / rapid alternating |
| 策略壓測 | 5 | whipsaw / extreme / squeeze / grid traversal |
| Guardian 拒絕 | 3 | drawdown / direction / position count |
| 止損觸發 | 4 | hard stop / short / multi-position / boundary |
| PnL 序列 | 3 | long/short/zero-sum |
| 全管線壓測 | 3 | volatile / zero-volume / extreme prices |
| Reconciler 壓測 | 4 | 100-cycle / 50-symbol / rapid handler / performance |
| 10K tick 無 panic | 1 | 10,000 ticks 穩定性 |
| Tick 延遲基準 | 1 | 1000 calls <100ms |

### 8.2 壓力測試缺口

| 缺口 | 嚴重度 | 備註 |
|------|--------|------|
| **25 symbols 滿負載 10K ticks** | P2-MEDIUM | 當前最大 5 symbols / 10K ticks，但設計上限 25 |
| **記憶體增長檢測** | P2-MEDIUM | 長時間運行的 ring buffer / HashMap 增長未檢測 |
| **多策略同時開/平倉風暴** | P2-MEDIUM | 現有壓測策略各自獨立 |

---

## 九、關鍵發現彙總 / Key Findings

### P0-CRITICAL（必須修復）

1. ~~**`edge_estimates.rs` 零測試**~~ **[原報誤判，已撤銷]**
   - 核實：實有 332 行 / 14 tests（含 empty/valid/malformed JSON + boundary），`#[tokio::test]` 漏計導致誤報。
   - 狀態：✅ 覆蓋充分，無需修復。

2. **REST API timeout fail-closed 端到端行為無測試**
   - 文件：`rust/openclaw_engine/src/bybit_rest_client.rs`（1,172 行 / 20 tests）
   - 已有：`test_client_timeout_configured`（驗證 timeout 設置）+ `test_get_transport_error_fails_closed`（connection-refused 路徑）
   - 缺失：無模擬 hung server 超時的端到端測試 — 即構建一個掛起 >10s 的 mock server 驗證 client 返回 `Err(Timeout)` 且不重試
   - 風險：硬邊界 #4「timeout → fail-closed 不重試」是架構合規要求

3. **三管線並發寫入無集成測試**
   - 風險：3E-ARCH 核心架構（Paper/Demo/Live 三獨立管線）的並發安全未端到端驗證
   - 修復：新增 e2e 測試模擬三管線同時 tick + 寫 state

### P1-HIGH（應儘快修復）

4. ~~**`startup.rs` 零測試**~~ → **降級 P2**：實有 5 tests（960 行），覆蓋不足但非零
5. **`tasks.rs` 零測試**（506 行）— 後台任務調度
6. **`database/rest_poller.rs` 零測試**（155 行）— REST 資料輪詢
7. **WS 斷線重連全流程無測試** — 只測了 backoff 計算
8. **Live catch_unwind 後行為無測試** — panic 恢復是 Live 安全保障
9. **Config hot-reload + tick 並發無測試** — ArcSwap 語義正確性未驗證
10. **Scanner symbol 更新 + tick 並發** — 活躍 symbol 列表變更的 race condition
11. **paper_state.json 三引擎搶寫的集成回歸缺失** — commit c9d9bc5 的 `with_kind()` 已有 2 個單元回歸（`test_with_kind_sets_pipeline_kind_field` + `test_emit_close_fill_embeds_engine_mode_per_kind`），但無三管線同時寫磁碟的集成測試（併入 P0-3）
12. **`event_consumer/handlers.rs` 零測試**（543 行）— ~~原報遺漏~~ 核心事件分派邏輯完全無覆蓋
13. **`intent_processor/router.rs` 零測試**（499 行）— ~~原報遺漏~~ 意圖路由器完全無覆蓋

### P2-MEDIUM（計劃中修復）

14. ~~`claude_teacher/` 4 個子模組零測試~~ **[原報誤判，已撤銷]** — 實有 10 文件 / 61 tests（`#[tokio::test]` 漏計）
15. `database/quality_writer.rs` 零測試
16. `position_manager.rs` 測試偏重 parsing，業務邏輯不足
17. Price=0.0 tick 行為未測試
18. f64::MAX / f64::INFINITY 在 risk_checks 中的行為
19. NaN 在 PnL 計算中的傳播
20. ~~fast_track 死碼路徑（price_drop_pct=0）~~ **[已修復]**：FIX-03+04（commit `283ae33`）已接入真實輸入
21. `position_reconciler/escalation.rs` 零測試（377 行）— ~~原報遺漏~~ 升降級邏輯
22. `news/rss.rs`（179 行）+ `news/cryptopanic.rs`（137 行）零測試 — ~~原報遺漏~~ 外部 feed 客戶端
23. `scanner/runner.rs` 零測試（261 行）— ~~原報遺漏~~ 掃描器運行器
24. `database/outcome_backfiller.rs` 零測試（149 行）— ~~原報遺漏~~ 回填器
25. `event_consumer/dispatch.rs` 零測試（161 行）— ~~原報遺漏~~ 事件分派
26. `claude_teacher/writer.rs` 零測試（249 行）— 教師模組寫入器
27. `market_data_client/types.rs` 零測試（219 行）— ~~原報遺漏~~ 市場數據類型

---

## 十、測試品質評價 / Quality Assessment

### 優勢

1. **回歸測試紀律優秀**：PNL-FIX-1/2、B-1/B-2 全部有標記明確的回歸測試，帶中英雙語 doc
2. **風控路徑覆蓋完整**：25 risk_checks tests + 32 reconciler tests + 8 fast_track tests = 全路徑
3. **邊界意識強**：zero balance / exact boundary / extreme price 多處覆蓋
4. **壓力測試有深度**：10K tick 穩定性 + 性能基準 + 多 symbol 並發
5. **Config 驗證測試全面**：82 config tests 覆蓋所有驗證規則 + rollback + 並發
6. **策略測試完整**：81 tests，5 策略全覆蓋 entry/exit/params/boundary
7. **中英雙語測試文檔**：符合項目規範

### 弱點

1. **零測試模組實為 16 個**（原報列 12 個，3 個為誤報；自審發現 11 個原報遺漏）：tasks.rs(506) / event_consumer/handlers.rs(543) / intent_processor/router.rs(499) / position_reconciler/escalation.rs(377) / scanner/runner.rs(261) / claude_teacher/writer.rs(249) / market_data_client/types.rs(219) / news/rss.rs(179) / event_consumer/dispatch.rs(161) / rest_poller.rs(155) / database/outcome_backfiller.rs(149) / news/cryptopanic.rs(137) / quality_writer.rs(109) / pipeline_types.rs(170) / main.rs(970) / market_data_client/parsers.rs(158)，共 ~4,842 行無覆蓋
2. **並發測試嚴重不足**：3E-ARCH 三管線架構是核心特性，但並發安全僅 1 個 ConfigStore 測試
3. **異常路徑比例低**：異常測試約佔 15%，正常路徑 70%，邊界 15%，建議異常提升至 25%
4. **無 #[should_panic] / #[ignore] 測試**：沒有任何預期 panic 測試或條件跳過測試
5. **Integration 測試未模擬真實 WS/REST**：所有 e2e 都是構造 PriceEvent 直驅，無網路層模擬

---

## 十一、建議優先修復順序 / Recommended Fix Order

| 優先級 | 工作項 | 預計測試數 | 預計工時 | 備註 |
|--------|--------|-----------|---------|------|
| ~~W22-1~~ | ~~edge_estimates.rs 基本覆蓋~~ | ~~+10~~ | ~~1h~~ | **已撤銷**：實有 14 tests |
| W22-2 | REST timeout fail-closed 測試 | +3 | 2h | P0 |
| W22-3 | 三管線並發 e2e | +3 | 3h | P0 |
| W22-4 | WS 斷線重連模擬 | +5 | 3h | P1 |
| ~~W22-5~~ | ~~startup.rs 可測部分提取~~ | ~~+5~~ | ~~2h~~ | **降為 P2**：已有 5 tests |
| W23-1 | catch_unwind 後行為測試 | +3 | 1h | P1 |
| W23-2 | Config hot-reload 並發 | +3 | 2h | P1 |
| W23-3 | Price=0 / NaN / Inf 邊界 | +8 | 2h | P2 |
| W23-4 | rest_poller + quality_writer | +5 | 1h | P1/P2 |
| ~~W23-5~~ | ~~claude_teacher 子模組~~ | ~~+8~~ | ~~3h~~ | **已撤銷**：實有 61 tests |
| W23-6 | event_consumer/handlers.rs 基本覆蓋 | +8 | 2h | P1（自審新增） |
| W23-7 | intent_processor/router.rs 基本覆蓋 | +5 | 1.5h | P1（���審新增） |
| W24-1 | position_reconciler/escalation.rs | +5 | 1h | P2（自審新增） |
| W24-2 | news/rss.rs + cryptopanic.rs feed 解析 | +6 | 1.5h | P2（自審新增） |
| W24-3 | scanner/runner.rs + outcome_backfiller.rs | +4 | 1h | P2（自審新增） |

**預計新增**：~58 tests（含自審發現的 11 個遺漏模組），完成後總計 ~4296，覆蓋率缺口關閉 75%。

---

## 十二、結論 / Conclusion

系統整體測試健康度 **B+**（良好偏上）。核心交易管線（策略→門控→執行→PnL→風控）覆蓋充分，回歸測試紀律模範。原報 3 個 P0 經核實為 **2 個**（edge_estimates.rs 誤報撤銷）；但自審二輪發現原報遺漏 **11 個零測試模組**（含 handlers.rs 543 行、router.rs 499 行等關鍵文件），實際零覆蓋模組為 **16 個 / ~4,842 行**。P1 從原報 8 個修正為 **9 個**（+2 新增 -1 降級）。剩餘核心風險：(1) 三管線並發安全未端到端驗證；(2) REST hung-server timeout 路徑未測；(3) event_consumer/handlers.rs + intent_processor/router.rs 兩個 >400 行核心文件零覆蓋。建議 W22-W24 分三批修復，預計 ~58 tests / ~16h 可提升至 **A-**。

---

## 十三、核實附錄 / Verification Appendix（2026-04-12 補充）

本節為逐條核實後追加，修正原報告中因 `#[tokio::test]` 漏計導致的系統性錯誤。

### 原報告三大系統性錯誤

1. **`#[tokio::test]` 漏計**：原報只搜索 `#[test]`，遺漏 async 測試宏，導致 edge_estimates（14）、startup（5）、claude_teacher（~62）共 ~81 tests 被誤判為零。
2. **e2e 文件漏計**：只計了 `stress_integration.rs`（29），遺漏 `reconciler_e2e.rs`（18）+ `rrc1_audit_tests.rs`（4）+ `phase4_integration.rs`（3）= 實際 54。
3. **行數快照過時**：多處偏差 100+ 行（strategies/ 差 416 行最大），為代碼持續增長所致。

### 修正後發現統計（含自審二輪）

| 嚴重度 | 原報數量 | 一輪核實 | 自審二輪 | 變更說明 |
|--------|---------|---------|---------|---------|
| P0-CRITICAL | 3 | 2 | **2** | edge_estimates 撤銷，P0-2 描述修正（已有 timeout config test） |
| P1-HIGH | 8 | 7 | **9** | startup 降 P2，+handlers.rs(543行) +router.rs(499行) 新增 |
| P2-MEDIUM | 7 | 6 | **14** | claude_teacher/fast_track 撤銷，+8 個原報遺漏模組 |
| 零測試模組 | 12(3誤報) | 5 | **16** | 自審發現 11 個 >100 行零測試模組原報未列入 |
| 總測試數 | 4229 | 4238 | **4238** | 不變 |

### 自審二輪新增發現

1. **e2e 文件分配寫反**：`stress_integration.rs` 實為 3 tests（非 29），`phase4_integration.rs` 實為 29 tests（非 3）。已修正。
2. **`claude_teacher` 精確計數**：61 tests（非 ~62），`client.rs` 注釋中的 `#[tokio::test]` 被誤計。
3. **P0-2 描述不夠精確**：已有 `test_client_timeout_configured` + `test_get_transport_error_fails_closed`，缺的是 hung-server 端到端超時。
4. **P1-11 部分不準確**：`with_kind()` 有 2 個單元回歸，缺的是三管線並發磁碟寫入（併入 P0-3）。
5. **11 個零測試模組原報完全遺漏**：handlers.rs(543) / router.rs(499) / escalation.rs(377) / runner.rs(261) / writer.rs(249) / types.rs(219) / rss.rs(179) / dispatch.rs(161) / parsers.rs(158) / outcome_backfiller.rs(149) / cryptopanic.rs(137)。
6. **有良好覆蓋但未列入矩陣**：bybit_rest_client.rs(20 tests) / ws_client.rs(16) / bybit_private_ws.rs(15) / multi_interval_ws.rs(8) / persistence.rs(8) / news/ 有測試部分(85 tests) / event_consumer 有測試部分(~25 tests)。

### 修正後測試評級

**B+ → B+**（零測試模組從原報 12 修正為實際 16 個，P0 從 3 降至 2，但新發現的遺漏模組抵消了誤報修正帶來的評級提升。核心交易管線覆蓋仍然充分，但整體零覆蓋代碼量 ~4,842 行高於原報評估）。
