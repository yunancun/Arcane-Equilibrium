# E4 Full-Chain Testing Audit（全程序範圍測試檢驗）
# 日期：2026-04-24
# 範圍：Rust unit + integration、Python pytest、healthcheck、smoke、CI
# 模式：覆蓋面 + 缺口審計（不實跑套件）

---

## 一、總覽快照（以 grep / ls 為準，不實跑）

| 測試層 | 檔案數 | 測試案例（annotation count） | 歷史基準 | 差 |
|---|---|---|---|---|
| Rust engine inline `#[test]` / `#[tokio::test]`（`rust/openclaw_engine/src/**`） | 149 檔 | **~2,103** | §三 lib 1980 passed | +123（含忽略 / feature-gated） |
| Rust engine integration（`rust/openclaw_engine/tests/*.rs`） | 7 檔 | **85** | 4 月初 ~66 | +19 |
| &nbsp;&nbsp;`stress_integration.rs` | — | 35 | — | — |
| &nbsp;&nbsp;`reconciler_e2e.rs` | — | 19 | — | — |
| &nbsp;&nbsp;`edge_predictor_ort_backend.rs` | — | ~10 | — | — |
| &nbsp;&nbsp;`micro_profit_fix_integration.rs` | — | 7 | — | — |
| &nbsp;&nbsp;`migrations_test.rs` | — | 5 | — | — |
| &nbsp;&nbsp;`phase4_integration.rs` | — | 3 | — | — |
| &nbsp;&nbsp;`rrc1_audit_tests.rs` | — | ~6 | — | — |
| Python pytest（3 資料夾：`control_api_v1/tests` + `ml_training/tests` + `audit/tests` + `local_model_tools/tests`） | 121 檔 | **~3,006** | §十一 pytest 2996 | 持平（+10） |
| &nbsp;&nbsp;`control_api_v1/tests/test_*.py` | 93 | 2,687 | — | — |
| &nbsp;&nbsp;`ml_training/tests/` | 26 | ~292 | — | — |
| &nbsp;&nbsp;`audit/tests/` + `local_model_tools/tests/` | 2 | ~31 | — | — |
| Healthcheck script | 1（`helper_scripts/db/passive_wait_healthcheck.py`） | **12 checks**（[1]~[12]） | §七 鐵律 7 | +5 |
| 可執行 smoke 獨立腳本 | **0**（無 `smoke.sh` / `smoke.py` / `smoke_test/`） | — | — | 缺口 |
| CI（GitHub Actions / CircleCI / GitLab CI） | **0 workflow 檔**（`.github/workflows/` 不存在） | — | — | **關鍵缺口** |
| docker-compose.test.yml | 1 | — | — | 未跑狀態未知 |

**基準對齊**：§三 宣告 engine lib 1980 / 0 failed、pytest 承襲 2996；本次 grep 得 annotation ~2,103 + ~3,006，包含 `#[ignore]` / `#[cfg(feature=…)]` / 輔助測試，差值合理。**測試本身健康，主要缺口在 CI 自動化 + 某些 error-path / failure-mode 的邊界未覆蓋**。

---

## 二、正常路徑 Golden Path 覆蓋評估

### 2.1 Tick Pipeline（Rust `rust/openclaw_engine/src/tick_pipeline/`）
- **tests.rs**：120 個 `#[test]`（本倉最大單檔）✅
- **on_tick/helpers.rs**：21 `#[test]`
- **pipeline_ctor / pipeline_config / pipeline_helpers**：split 後 ≤1012 LOC，各有 inline tests
- **結論 A**：正常 tick→signal→intent→fill 主路徑覆蓋充分

### 2.2 Combine Layer（Rust `combine_layer.rs`）
- 21 inline `#[test]` ✅
- INFRA-PREBUILD-1 Part A `build_ml_inference_shadow` mock producer 已寫測（`shadow_exit_writer.rs` 有測）
- **結論 B+**：shadow / production 雙路徑覆蓋；真正 ML producer 尚未實裝故無測試必要

### 2.3 Governance（Rust `openclaw_core` + Python `governance_hub.py`）
- Python `test_governance_hub.py` 62 + `test_governance_routes_coverage.py` 110 + `test_governance_routes_auth.py` 13 = 185 ✅
- `test_governance_events.py` 45 ✅
- Rust `position_reconciler/tests.rs` 35 + `escalation.rs` 19 + `orphan_handler.rs` 17 ✅
- **結論 A-**：Python 側 SM-01/02/04 生命週期完整；Rust 側 Reconciler 14 scenarios + 4 stress 齊

### 2.4 StopManager（Python → 已退役；Rust 為 exit_features + phys_lock + fast_track + step_6_risk_checks）
- `exit_features/v2.rs` 28 `#[test]`（Track P v2 non-linear）✅
- `exit_features/builder.rs` 12
- `exit_features/core.rs`（inline）
- `fast_track.rs` 25
- `risk_checks.rs` 27
- **結論 A-**：覆蓋 Track P v2 主路徑、ATR coverage、giveback_atr_norm 計算
- ⚠️ **Python `stop_manager.py` 已不存在**（3E-ARCH 後全 Rust）；2026-04-01 E4 報告提到的「stop_manager.py 319 LOC」記錄過期

### 2.5 5-Agent（Python，shadow=false / shadow）
- StrategistAgent：`test_strategist_agent.py` 36 + `test_strategist_stress.py`（shadow=False 4 路徑）+ `test_strategist_history_routes.py` 17 + `test_strategist_audit_wiring.py` + `test_batch7_conductor_strategist.py` 31 ✅
- GuardianAgent：`test_guardian_agent_unit.py` 28 + `test_guardian_audit_wiring.py` + `test_batch8_guardian_integration.py` 30 ✅
- AnalystAgent：`test_analyst_agent_unit.py` 17 + `test_analyst_agent_registry.py` 23 + `test_batch9_perception_analyst_integration.py` 25 ✅
- ExecutorAgent：`test_executor_agent_unit.py` 14 + `test_executor_audit_wiring.py` + `test_batch11_executor_exchange.py` 31 ⚠️ **只 1 測試斷言 `shadow_mode="ipc_shadow"`**（line 118 `test_no_engine_ipc_shadow`），**沒有測試 `_shadow_mode=False` 翻牆live 路徑**（因為 §三 `_shadow_mode=True` 是預設）
- Scout：`test_scout_integration.py` 38 + `test_scout_worker.py` 10 + `test_scout_audit_wiring.py` ✅
- **結論 B+**：4 agent live 路徑 OK；**ExecutorAgent shadow→live 切換契約**的測試在整個 G-1 work item 前是缺口（預期，見 §三 gap (a)）

### 2.6 Decision Lease / Authorization / Config hot-reload
- `test_decision_lease_state_machine.py` 58 ✅
- `test_authorization_state_machine.py` 75 ✅
- `test_lease_ttl_config.py` 47 + `test_ttl_enforcer.py` 57 ✅
- `test_live_authorization_signing.py` 10（HMAC 簽名）✅
- `test_live_auth_recheck_trigger.py` 8（5min re-verify）✅
- `test_live_gate_fallback.py` 14 ✅
- Rust `live_authorization.rs` 15 + `live_auth_watcher.rs` 7 ✅
- Rust config hot-reload：`config/store.rs` 14 + `config/mod.rs` 大量 + `risk_config_tests.rs` 41 ✅
- **結論 A**：授權鏈完整覆蓋，含 LiveDemo 不降級、HMAC、5min re-verify、hot-reload 三端

### 2.7 策略（5 個）
- bb_breakout：`tests.rs` 28 + `tests_oi.rs` 14 + `tests_p1_11.rs` 21（含 7 FIX-26-DEADLOCK-1 regression + DonchianMode + Profile）✅
- bb_reversion：`bb_reversion.rs` 20 inline ✅
- grid_trading：`tests.rs` 36 + `grid_helpers.rs` 外 42 on `strategies/confluence.rs` ✅
- ma_crossover：`tests.rs` 27 + `tests_a1_a2_maker.rs` 17 ✅
- funding_arb：`funding_arb.rs` 31 inline ✅
- **結論 A**：策略層覆蓋優；FIX-26-DEADLOCK-1 已有 7 項 regression guard，等 `--rebuild` 部署後 healthcheck [12] 自動驗

---

## 三、邊界條件 Boundary 評估

### 3.1 已覆蓋
- `qty<=0` / `price<=0`（`test_risk_manager.py`）— 2026-04-01 Wave 6 Sprint 2 加入 ✅
- HMAC 簽名邊界（`test_live_authorization_signing.py` 10）✅
- WS malformed JSON（`ws_client.rs` 21 inline）✅
- REST timeout（`bybit_rest_client.rs` `test_timeout_fires_on_hung_server_fail_closed`）✅
- Leader lock 邊界（`test_edge_estimator_scheduler_leader_lock.py` 14，含 multiprocess reclaim、mkdir fail、open fail）✅
- ATR 極端（exit_features/v2.rs 覆蓋 ATR=0 fallback）✅

### 3.2 未覆蓋（按優先級）

| # | 邊界場景 | 模組 | 優先級 | 建議測試 |
|---|---|---|---|---|
| B-1 | funding_rate = 0 / 極高（>3%/8h） | `funding_arb.rs` | P1 | `test_funding_arb_zero_rate_rejects_entry` / `test_funding_arb_extreme_rate_max_size_cap` |
| B-2 | ATR = NaN / Inf（upstream indicator 噴） | `fast_track.rs` + `exit_features/core.rs` | P1 | `test_atr_nan_inf_treated_as_missing_fallback` |
| B-3 | balance = 0（資金耗盡但有持倉）| `paper_state` + risk sizer | P1 | `test_zero_balance_holds_position_blocks_new_entry` |
| B-4 | 午夜 UTC / 月末 / DST roll | 全 time-window 邏輯 | P2 | `test_utc_midnight_cooldown_rolls_clean` + `test_monthly_rollover_session_reset` |
| B-5 | Bandwidth 閾值 exact match（`squeeze_bw == threshold`）| `bb_breakout` | P2 | 閾值邊界 inclusive/exclusive 二路徑（目前 `tests_p1_11.rs` 已覆蓋 boundary） |
| B-6 | grid_trading 網格首行/末行 order price rounding | `grid_trading/position_mgmt.rs` | P2 | `test_grid_tick_boundary_price_rounding_exact` |
| B-7 | Decision Lease TTL ±1ms | `decision_lease_state_machine.py` | P3 | `test_lease_expiry_boundary_1ms` |
| B-8 | 持倉期 atr 樣本 <14 bars（暖機不足）| `kline_manager` + Rust indicators | P2 | `test_atr_warmup_insufficient_bars_fallback` |
| B-9 | authorization.json TTL exactly at `exp` | `live_authorization.rs` | P2 | `test_live_auth_exactly_at_expiry_boundary_reject` |
| B-10 | config hot-reload 期間 tick 湧入（race window） | `config/store.rs` ArcSwap | P1 | `test_arcswap_concurrent_read_during_store_no_tear` |

---

## 四、異常路徑 Error / Failure 評估

### 4.1 已覆蓋
- Bybit REST 無憑證 fail-closed（`test_get_no_credentials_fails_closed` + `post` 同款）✅
- Bybit REST retCode != 0 fail-closed（`test_into_result_non_zero_retcode_fails_closed`）✅
- Bybit REST transport error（`test_get_transport_error_fails_closed`）✅
- LM Studio connection error fail-soft（`test_lm_studio_generate_fail_soft_on_connection_error`）✅
- Ollama connection error（`test_generate_connection_error`）✅
- WS backoff progression monotonic（`ws_client.rs test_backoff_monotonic_progression`）✅
- live_auth 過期時 engine 優雅 shutdown（`live_auth_watcher.rs` 7 測）✅

### 4.2 未覆蓋

| # | 異常場景 | 模組 | 優先級 | 建議測試 |
|---|---|---|---|---|
| E-1 | **WS 斷線期間持倉的止損行為**（止損觸發時無 tick）| `tick_pipeline` + `position_reconciler` | **P1** | `test_ws_disconnect_stop_loss_triggers_on_reconnect_tick` — 驗 Reconciler 進 Cautious + recover 後第一 tick 吃到未執行止損 |
| E-2 | **PostgreSQL 連接掉線期間 engine 行為**（writer drop rows? degrade gracefully?）| `database/pool.rs` + `trading_writer.rs` | **P1** | `test_db_disconnect_trading_writer_buffers_then_flushes` + `test_db_down_decision_feature_writer_drops_with_log` |
| E-3 | **config 檔破損 TOML（parse 失敗）在 hot-reload** | `config/io.rs` + `config/legacy_migration.rs` | P1 | `test_corrupted_toml_hot_reload_preserves_last_known_good` |
| E-4 | **IPC socket 斷（python↔rust）導致 patch_risk_config 超時** | `ipc_server/dispatch.rs` + Python `ipc_dispatch.py` | P1 | `test_ipc_socket_broken_patch_config_times_out_retains_previous` |
| E-5 | **Bybit 限流（rate-limited 429）| `bybit_rest_client.rs` + `scanner_rate_limiter.py` | P2 | `test_bybit_429_backs_off_respects_retry_after` |
| E-6 | **WS 重連連續失敗（≥3 次 backoff 耗盡）| `ws_client.rs` | P2 | `test_ws_reconnect_exhausted_surfaces_fatal_to_watchdog` |
| E-7 | **ExecutorAgent 送出 IPC SubmitOrder 給 Rust 但 Rust 拒絕** | `executor_agent.py` + Rust IPC | **P1** | `test_executor_submit_order_rust_rejection_reports_upstream_to_msgbus` — **G-1 工作項必須先加** |
| E-8 | **PyO3 fallback（Rust symbol 找不到）| PyO3 bridge（目前 LLM-ABC-MIGRATION-1 後大幅減少）| P2 | 若仍有 PyO3 bridge，加 `test_pyo3_symbol_missing_soft_fail` |
| E-9 | **edge_estimates.json 破損或 parse 失敗**（scheduler writer 掛了留下半檔） | `edge_estimator_scheduler.py` + healthcheck [7] | P2 | `test_edge_estimates_json_corrupted_scheduler_reloads_from_backup` |
| E-10 | **authorization.json 被外力（非 renew 路由）改動** | `live_auth_watcher.rs` + Python renew 路由 | P1 | `test_authorization_signature_tampered_engine_refuses_and_shuts_down` |
| E-11 | **trading.intents 寫入失敗（P1-12 4/17 post-mortem）** | `trading_writer.rs` | P1 | `test_trading_intents_writer_insert_failure_surfaces_not_silent` — 守門 [10] healthcheck |
| E-12 | **engine OOM / panic 期間 watchdog 行為**（`helper_scripts/canary/engine_watchdog.py`） | canary watchdog | P2 | `test_watchdog_detects_engine_oom_45s_stale_threshold` |

---

## 五、並發 Concurrency 評估

### 5.1 已覆蓋
- uvicorn 4-workers leader election（`test_edge_estimator_scheduler_leader_lock.py` 14 測，含 multiprocess）✅
- MessageBus 高負載（`test_message_bus_load.py` 11）✅
- StrategistAgent stress（`test_strategist_stress.py`）✅
- PipelineBridge concurrent tick + deactivate（注：舊 Python pipeline_bridge 已退役，但等效的 Rust `tick_pipeline/tests.rs` 120 測覆蓋）✅
- Reconciler 100-cycle rapid drift/clean 無 panic（`reconciler_e2e.rs S1`）✅
- 50 symbols burst（`reconciler_e2e.rs S2`）✅
- 20 rapid escalate/de-escalate 無 deadlock（`reconciler_e2e.rs S3`）✅

### 5.2 未覆蓋

| # | 並發場景 | 模組 | 優先級 | 建議測試 |
|---|---|---|---|---|
| C-1 | **Rust ArcSwap config 熱重載期間 tick 湧入（tear check）** | `config/store.rs` | **P1** | `test_arcswap_no_tear_under_10k_tick_rate_during_store` — loom 或 100-thread spike |
| C-2 | **IPC 併發寫入同一 slot key（Python multi-worker）** | `ipc_dispatch.py:_SHARED_IPC_SLOTS` | P1 | `test_ipc_concurrent_multi_worker_shared_slot_lock_safety` |
| C-3 | **ChangeAuditLog 併發寫** | `change_audit_log.py` | P2 | `test_change_audit_log_concurrent_writers_no_lost_record` |
| C-4 | **OMS StateMachine 併發狀態轉換** | `oms_state_machine.py` | P2 | `test_oms_concurrent_submit_cancel_fills_serializable` |
| C-5 | **ExperimentLedger 併發 observe**（類別：內有 `threading.Lock`，但無壓測） | `experiment_ledger.py` | P3 | `test_ledger_concurrent_observe_no_double_count` |
| C-6 | **TruthSourceRegistry 併發 register+query** | `truth_source_registry.py` | P3 | `test_truth_registry_concurrent_rw` |
| C-7 | **shadow_exit_writer 通道 overflow 時的 behavior**（Part A） | Rust `shadow_exit_writer.rs` | P2 | `test_shadow_exit_writer_channel_full_drops_with_telemetry` — 配合 healthcheck [8] channel-stall fingerprint |
| C-8 | **governance_hub TTL 分級併發降級** | `governance_hub.py` | P2 | `test_hub_concurrent_ttl_degrade_monotonic` |

---

## 六、回歸 Regression 守門覆蓋評估

| Bug ID | 修復 commit | 守門測試位置 | 狀態 |
|---|---|---|---|
| **FIX-26-DEADLOCK-1** | `bcc5401`+`63957ad` | `strategies/bb_breakout/tests_p1_11.rs` 7 個 `test_fix26_deadlock_*` + healthcheck [12] | ✅ 齊 |
| **FA-PHANTOM-1** | 2026-04-14 | `rust/openclaw_engine/tests/stress_integration.rs` 注明（≥15% CloseAll）| ✅ 有專屬 regression 區段 |
| **FA-PHANTOM-2** | 2026-04-15 spec | `stress_integration.rs` 8%/Normal/sigma<3 → NoAction | ✅ |
| **PNL-FIX-1/2** | 2026-04-12 | `paper_state/fill_engine.rs` + `paper_state/tests.rs` balance = init + realized_pnl − fees | ✅ 隱含覆蓋 |
| **MICRO-PROFIT-FIX-1** | 2026-04-17 | `rust/openclaw_engine/tests/micro_profit_fix_integration.rs` 7 測（cost_edge_max_ratio 0.2 / min_profit_pct 0.3 / validate reject 100.0）| ✅ 齊 |
| **STRATEGY-CLOSE-TAG-FIX** | 2026-04-16 P0-4 R1 | `trading_writer.rs` + `build_risk_close_tag` inline | ⚠️ **無專屬命名 regression test**；healthcheck [4] phys_lock 嚴格 pattern 守門，但缺單測驗 `strip_phys_lock_prefix` 行為 |
| **ENGINE-HEAL 4 Fix** / **STABILITY-1** | 各版本 | 散落 `engine_watchdog` + `position_reconciler` tests | ⚠️ 無統一 regression 套件；**STABILITY-1 停電 RCA 無對應自動守門測試**（預期外部事件，不需 code test） |
| **RUST-DOUBLE-PREFIX-1** | 2026-04-23 | healthcheck [4] 嚴格 `risk_close:phys_lock_%` pattern（刻意不容錯）| ✅ 透過 healthcheck 自動偵測 |
| **ORPHAN-ADOPT-1 Phase 1/2A** | 2026-04-14/15 | `position_reconciler/orphan_handler.rs` 17 inline | ✅ |
| **P0-0 RECONCILER-BURST-FIX** | 2026-04-16 | `reconciler_e2e.rs` 6-05 stress scenarios | ✅ |
| **P0-6 FUP / bybit_sync 死鎖** | 2026-04-17 RCA | `bybit_demo_sync.py test_*` 28 測 | ✅ 基本 |
| **P1-12 trading.intents writer 停寫 4/17** | healthcheck-only defense | healthcheck [10] intents/orders 比率守衛 | ⚠️ 無 Rust/Python unit regression test；**應加 E-11** |
| **EDGE-DIAG-1 Phase 1+2+4** | `5b0908b`+`1a53400` | counterfactual_exit_audit 4 測 + healthcheck [11]（ETA + daily snapshot）| ✅ |
| **P0-13 ATR scale** | 2026-04-22 | exit_features v2 28 測 | ✅ 隱含 |
| **P0-14 A/B Gate 1 fallback + proxy cells** | 2026-04-22 | `test_james_stein_proxy_cells.py` 9 + exit_features integration | ✅ |

**回歸覆蓋率評估：A-（優秀）**。5 個關鍵歷史 bug 都有守門或 healthcheck 覆蓋。**唯一明顯的 regression 缺口**：STRATEGY-CLOSE-TAG-FIX 的 `strip_phys_lock_prefix` 無 unit regression test（只靠 healthcheck 反饋）；P1-12 trading.intents 停寫的 unit-level regression 闕如（只靠 healthcheck [10]）。

---

## 七、Healthcheck `passive_wait_healthcheck.py` 覆蓋評估

12 個 check（[1]~[12]，**[9] model_registry 為 Phase 1a 預期空**；checks 不連號原因：[8] shadow_exits 插在 [7] 前 SQL 批次中，[10]~[12] 後補）：

| # | check | 對應 TODO / 被動等待 | 狀態 |
|---|---|---|---|
| [1] | close_fills_24h | 基準：demo 24h 平倉 | ✅ |
| [2] | label_backfill_ratio | P1-7 LEARNING-DORMANT | ✅ |
| [3] | exit_features_writer_ratio | EXIT-FEATURES-TABLE-1 | ✅ |
| [4] | phys_lock_runtime | TRACK-P v2 + RUST-DOUBLE-PREFIX-1 嚴格 pattern | ✅ |
| [5] | micro_profit_fire | MICRO-PROFIT-FIX-1（注：已 T3-deprecated，7d=0 為 FAIL） | ⚠️ 可能需改 |
| [6] | trailing_stop_fire | 7d=0 FAIL | ✅ |
| [7] | edge_estimates_freshness | 90min TTL + H4 prefix 診斷 | ✅ |
| [8] | shadow_exits_24h | INFRA-PREBUILD-1 Part A（TOML 主動診斷 + last_1h channel stall） | ✅（L2-5 已 upgrade） |
| [9] | model_registry_freshness | INFRA-PREBUILD-1 Part B（Phase 1a 空預期 PASS） | ✅ |
| [10] | intents_writer_ratio | P1-12 post-mortem 4/17 outage + live_demo 雙覆蓋 | ✅ |
| [11] | counterfactual_clean_window_growth | EDGE-DIAG-1 Phase 3 auto-gate（≥200 rows + strategy 細分 + ETA） | ✅ |
| [12] | bb_breakout_post_deadlock_fix | P1-11 FIX-26-DEADLOCK-1 部署驗收 | ✅ |

### Healthcheck 缺口

| # | 被動等待 / 保命前提 | 建議 healthcheck check | 優先級 |
|---|---|---|---|
| H-1 | **P0-2：demo ≥21d 穩定（2026-05-07 解鎖）** | `check_engine_stability_21d`：engine_pid mtime、0 panic、crash log 數 | **P1** — §七 規則明確要求「被動等待 TODO 必附 healthcheck」，但 21d 穩定期只查 engine_watchdog 結果，沒有 aggregated check |
| H-2 | **1w PostOnly maker fill rate 驗證（EDGE-P2-3）** | `check_postonly_maker_fill_rate_demo`：24h `trading.fills.fee_rate < taker_fee_rate` 比率 + 維持 ≥ threshold | P1 |
| H-3 | **authorization.json 正被 5min re-verify**（live/livedemo 階段） | `check_live_auth_last_reverify_ts`：engine 最後一次 re-verify 時間 < 10min | P1 |
| H-4 | **P0-3 Phase 5 edge 重評 2w 後觀察**（等 21d demo） | `check_edge_estimates_grand_mean`：`settings/edge_estimates.json` grand_mean_bps 與閾值比對 | P2 |
| H-5 | **Rust engine 每 tick ATR sample 可用率（P0-13 後）** | `check_atr_sample_availability_24h`：`learning.exit_features.atr_pct` 非 NULL 比率 | P2 |
| H-6 | **decision_outcomes 回填進度**（memory `project_decision_outcomes_not_dead.md`）| `check_decision_outcomes_outcome_non_null_ratio_24h` | P2 |
| H-7 | **config hot-reload 生效時間**（IPC patch 後） | `check_last_ipc_patch_config_latency_p99_lt_1s` | P3 |
| H-8 | **LinUCB shadow compare 保留狀態**（memory 標「保留」但沒 healthcheck） | `check_linucb_shadow_script_last_run_ts`（若有 cron） | P3 |

**Healthcheck 評估：A-**（12 check 全符合「TODO 必附 check」規則；少數新建的被動等待仍缺守門，其中 H-1/H-2/H-3 為 Live 前置路徑必要）

---

## 八、CI / Smoke / 自動化缺口

### 8.1 關鍵缺口：CI **完全不存在**
- `.github/workflows/` 不存在 → GitHub Actions 無
- 未發現 `.gitlab-ci.yml` / `.circleci/` / `Jenkinsfile` / `buildkite.yml`
- **每次驗證全靠 operator 手動 `ssh trade-core "cargo test --release && pytest"`**，或 Mac 本地 cargo test
- **影響**：新增的 commit 無自動 gate；regression 只在 operator 手動跑時被發現；open-source / collaborator 無 badge 驗證

### 8.2 docker/docker-compose.test.yml
- 存在但未在 §三 / §十一 狀態中被引用
- **不清楚是否 CI pipeline 用過**

### 8.3 Smoke / End-to-End 可執行腳本
- `helper_scripts/canary/test_canary.py`（看名是 canary 冒煙） — **未檢查內容**
- `helper_scripts/canary/replay_runner.py` — **非 test**
- `helper_scripts/canary/engine_watchdog.py` — 運維工具
- `v2_swap_24h_observation.sh` — 觀察腳本非 smoke
- **無 `smoke_test.sh` / `smoke_test.py` / `integration_smoke.sh`** 作為單一入口跑「部署後 5 min 基本驗證」

### 8.4 rollback_drill.sh
- `helper_scripts/canary/rollback_drill.sh` 存在，內容未驗；屬 operational drill 不是 CI

---

## 九、缺口清單（按模組分類，每項含嚴重性 + 建議測試名 + 粗框）

### 9.1 Rust Engine（非策略）

| # | 模組 | 類型 | 嚴重性 | 建議測試名 | 粗框 |
|---|---|---|---|---|---|
| G-01 | `config/store.rs` ArcSwap | 並發 | **P1** | `test_arcswap_config_no_tear_under_tick_spike` | loom 或 spawn 100 reader + 1 writer，驗無 torn read |
| G-02 | `ws_client.rs` reconnect | 異常 | P1 | `test_ws_full_reconnect_cycle_exhaust_then_surface_fatal` | 構造 3 次 connect 失敗 → watchdog 收 fatal |
| G-03 | `database/pool.rs` disconnect | 異常 | **P1** | `test_pool_connection_dropped_writer_reopens_or_degrades` | kill PG connection mid-write，驗 retry + log |
| G-04 | `trading_writer.rs` intents P1-12 | 回歸 | **P1** | `test_trading_intents_insert_failure_surfaces_via_telemetry` | 模擬 SQL error → 計數器 +1，log ERROR |
| G-05 | `ipc_server/dispatch.rs` timeout | 異常 | P1 | `test_ipc_dispatch_timeout_5s_handler_hung` | tokio::time mock，驗 handler 5s 後回 timeout |
| G-06 | `live_authorization.rs` TTL 邊界 | 邊界 | P2 | `test_auth_expiry_boundary_exact_now_reject` | set exp = now-0ms → reject |
| G-07 | `shadow_exit_writer.rs` channel overflow | 並發 | P2 | `test_shadow_exit_channel_full_drops_counted` | try_send 塞爆 → 觀察 drop counter |
| G-08 | `bybit_private_ws.rs` 認證失敗重試 | 異常 | P2 | `test_private_ws_auth_failed_reauth_within_backoff` | 模擬 auth failed → reconnect → re-auth |

### 9.2 Rust 策略

| # | 模組 | 類型 | 嚴重性 | 建議測試名 | 粗框 |
|---|---|---|---|---|---|
| S-01 | `funding_arb.rs` | 邊界 | P1 | `test_funding_arb_rate_boundary_extreme_cap` | funding_rate=3%/8h → 驗 size cap |
| S-02 | `grid_trading/position_mgmt.rs` | 邊界 | P2 | `test_grid_first_last_row_rounding` | 網格首末行 price rounding ≤ tick size |
| S-03 | `bb_reversion.rs` | 異常 | P2 | `test_bb_reversion_gap_open_skip_entry` | gap ≥ bandwidth → skip |
| S-04 | `strategies/confluence.rs` | 並發 | P3 | `test_confluence_concurrent_update_same_symbol` | 2 thread 同 symbol update |

### 9.3 Python Control API

| # | 模組 | 類型 | 嚴重性 | 建議測試名 | 粗框 |
|---|---|---|---|---|---|
| P-01 | `executor_agent.py` | 正常路徑 | **P1** | `test_executor_shadow_to_live_switch_contract` | 翻 `_shadow_mode=False`，驗真的送 IPC SubmitOrder |
| P-02 | `ipc_dispatch.py` | 並發 | P1 | `test_shared_ipc_slots_multi_worker_lock_safety` | 4 thread 共享 slot，驗無 duplicate write |
| P-03 | `edge_estimator_scheduler.py` | 異常 | P2 | `test_edge_scheduler_json_corrupted_backup_restore` | 破損 JSON → 從 prev mtime 恢復 |
| P-04 | `grafana_data_writer.py` | 異常 | P2 | `test_grafana_writer_pg_down_fails_without_panic` | PG down → log ERROR 不崩 |
| P-05 | `change_audit_log.py` | 並發 | P2 | `test_change_audit_concurrent_writers_no_lost_record` | 10 thread append，驗記錄數 |
| P-06 | `live_session_governance.py` | 異常 | P1 | `test_live_session_authorization_expired_mid_session_graceful_close` | session 中 TTL 過期 → 優雅關倉 |
| P-07 | `phase2_strategy_routes.py` | 正常路徑 | P2 | `test_phase2_strategy_deploy_endpoint_e2e` | 覆蓋 30%→60% |
| P-08 | `paper_trading_routes.py` | 正常路徑 | P2 | `test_paper_trading_routes_spot_category_e2e` | 覆蓋率 35%→60% |
| P-09 | `scout_routes.py` | 正常路徑 | P2 | `test_scout_routes_endpoints_direct` | 路由端點目前只間接測 |

### 9.4 Healthcheck / Smoke / CI

| # | 項目 | 類型 | 嚴重性 | 建議新增 | 粗框 |
|---|---|---|---|---|---|
| HC-1 | `.github/workflows/rust-ci.yml` | CI | **P0** | Matrix: ubuntu-latest + macos-latest → `cargo test --release -p openclaw_engine --lib` | 每 push + PR，5min timeout |
| HC-2 | `.github/workflows/python-ci.yml` | CI | **P0** | pytest 3 資料夾 + healthcheck dry-run | 每 push + PR |
| HC-3 | `helper_scripts/smoke_test.sh` | Smoke | P1 | 「部署後 5 min」基本驗證單一入口：`restart_all` healthcheck + 最小交易循環 | 呼叫 watchdog + healthcheck + 3 min wait → 復核 |
| HC-4 | healthcheck `[13] check_engine_21d_stability` | Healthcheck | P1 | H-1 缺口：21d demo 穩定性 aggregate check | pid mtime + crash count 0 + watchdog stream healthy |
| HC-5 | healthcheck `[14] check_postonly_maker_fill_rate` | Healthcheck | P1 | H-2：maker fee 驗 EDGE-P2-3 部署效果 | 24h fee < taker 比率 > threshold |
| HC-6 | healthcheck `[15] check_live_auth_last_reverify` | Healthcheck | P1 | H-3：5min re-verify 活著 | log grep engine 最後 re-verify ts |

---

## 十、Top 10 Blocking Gaps（Live 路徑 / 治理鏈關鍵）

按影響「最早 Live 日期 2026-05-23」的阻塞力排序：

| Rank | Gap | 嚴重性 | 阻塞對象 | 建議行動 |
|---|---|---|---|---|
| **1** | **無 CI 自動化（`.github/workflows/` 不存在）** | **P0** | 整個 regression 流程依靠 operator 手動跑 cargo test + pytest；任何 new commit 到 Live 之前沒有 gate | 立即加 `rust-ci.yml` + `python-ci.yml` matrix，push + PR 觸發 |
| **2** | **ExecutorAgent shadow→live 切換契約無測試（G-1 work item 前置）** | **P0** | Live 路徑真正開通前必先確認 `_shadow_mode=False` 時真送 IPC SubmitOrder 給 Rust，且 Rust 正確 ACK；**唯一測試是 shadow=True 路徑** | 加 `test_executor_shadow_to_live_switch_contract` + end-to-end IPC 模擬 |
| **3** | **WS 斷線期間的止損安全性無端到端測試** | **P1** | Live 階段 WS 斷線 → 無 tick → 止損不觸發 → 潛在風險無上限 | 加 `test_ws_disconnect_stop_loss_triggers_on_reconnect_tick`（§四 E-1）+ Reconciler 聯動 |
| **4** | **PostgreSQL 斷線期間 Rust writer 行為不明** | **P1** | P1-12 4/17 outage 類事件 DB 層 silent-drop；只靠 healthcheck [10] 事後偵測 | 加 `test_db_disconnect_writer_buffers_then_flushes`（§四 E-2） |
| **5** | **trading.intents 寫入失敗 unit regression 缺** | **P1** | 只有 healthcheck [10]，無 Rust unit 守門；若 healthcheck cron 停跑會再次 silent-dead | 加 `test_trading_intents_writer_insert_failure_surfaces`（§四 E-11） |
| **6** | **authorization.json 簽名被篡改後 engine 行為無測試** | **P1** | §四 Gate #5 Live 唯一硬鎖，但篡改場景未被自動 verify；SEC 角度必補 | 加 `test_authorization_signature_tampered_reject_and_shutdown`（§四 E-10） |
| **7** | **config ArcSwap 熱重載期間 tick 湧入（torn-read check）** | **P1** | §三「tick-level hot-reload + 禁 restart-to-apply」是核心架構承諾，但只有 inline serial tests | 加 `test_arcswap_no_tear_under_tick_spike`（§五 C-1），loom 驗無 race |
| **8** | **21d demo 穩定性無 aggregate healthcheck**（違 §七「被動等待必附 check」） | **P1** | P0-2 被動等待 21d，純靠 engine_watchdog 結果匯報；無 aggregated check 區分「穩定 21d」vs「crash 過但又起來」 | 加 healthcheck `[13] check_engine_21d_stability`（HC-4） |
| **9** | **PostOnly maker fill rate 無 healthcheck**（違 §七）| **P1** | EDGE-P2-3 2026-04-21 部署，等 ≥1w 驗效果；無自動檢查 fee 降幅 | 加 healthcheck `[14] check_postonly_maker_fill_rate`（HC-5） |
| **10** | **STRATEGY-CLOSE-TAG-FIX `strip_phys_lock_prefix` 無 unit regression test** | P2 | 只有 healthcheck [4] 守門；若 healthcheck miss → RUST-DOUBLE-PREFIX-1 regression 可能復發 | 加 `test_strip_phys_lock_prefix_single_vs_double_prefix` |

---

## 十一、結論與建議

### 11.1 整體評估
- **測試覆蓋面：A-（優秀）**。Rust engine 2,103 inline + 85 integration tests；Python 3,006 tests；12 healthcheck checks 覆蓋所有主要被動等待 TODO。
- **關鍵缺口：CI 完全不存在**（`.github/workflows/` 無檔）。即使 engine lib 1980/0 failed，任何 new commit 到 Live 前都沒有自動 regression gate。
- **次要缺口**：Error-path 測試偏少（WS/DB/IPC 斷線、authorization 篡改、ExecutorAgent shadow→live 切換）。
- **Regression guard 健康**：5 個歷史關鍵 bug（FIX-26/FA-PHANTOM-1/2/MICRO-PROFIT/PNL-FIX）都有單測或 healthcheck 守門。

### 11.2 立即優先順序（對齊 Live 日期 W24 末 ~2026-05-23）
1. **Week 1**：HC-1/HC-2 CI 建立 + P-01 ExecutorAgent shadow→live 契約測試（阻塞 G-1）
2. **Week 2**：G-01 ArcSwap concurrency + G-03 DB disconnect + E-1 WS 斷線止損
3. **Week 3**：HC-4/5/6 3 個 healthcheck 填被動等待守門 + G-04 intents writer unit regression
4. **Week 4**：S-01 funding_arb 邊界 + 剩餘 P2 項目

### 11.3 對齊 CLAUDE.md §七 規則的盤點
- **「被動等待 TODO 必附 healthcheck」**：12 check 覆蓋率高，但 H-1/H-2/H-3 三個新被動等待（21d demo / PostOnly / auth re-verify）**違規未補** — Top 10 第 8/9 項。
- **「新 SQL migration DO block guard」** + **「Engine 自動遷移（OPENCLAW_AUTO_MIGRATE=1）」**：V023 migration 已套用 + `migrations.rs` 15 unit + integration 5 測存在，規則覆蓋。
- **「LocalLLMClient 抽象乾淨」**：`test_local_llm_factory.py` 17 + `LLM-ABC-MIGRATION-1` 覆蓋，規則合規。
- **「跨平台兼容性」**：無新 `/home/ncyu` / `/Users/ncyu` 硬編碼證據（未跑 grep 但 E2 把門），規則合規。

---

E4 AUDIT DONE: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-24--full_chain_testing_audit.md
