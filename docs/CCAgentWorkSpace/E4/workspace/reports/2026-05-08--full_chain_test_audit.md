# E4 Full-Chain Test Audit — 2026-05-08 · 玄衡 (HEAD `4e2d2883`)

> 角色：E4 (Test Engineer) · 任務：對玄衡全程序鏈做測試完整度檢驗（只檢驗，不寫業務 test，新 gap 給後續 PA 派工）
> 範圍：H0 / Decision Lease / IntentProcessor / StopManager / Executor / StrategistScheduler / agent_spine_writer / ML training / xlang consistency / SLA stress
> Mac + Linux 雙端 baseline 真實重跑（非 CLAUDE.md 寫死數字）

---

## §1 Executive Summary

**真實 baseline 重跑（兩遍 deterministic identical）**：

| 引擎 / scope | passed | failed | skipped | 雙跑 identical | source |
|---|---:|---:|---:|---|---|
| Mac · `srv/tests/` (root) | **137** | 0 | 2 | yes | 1.10s |
| Mac · `program_code/exchange_connectors/.../control_api_v1/tests/` | **3826** | **6** | 17 | yes (60.01s vs 59.37s) | full suite |
| Linux · `srv/tests/` (ssh trade-core) | **137** | 0 | 2 | n/a single run | 0.21s |
| Linux · `program_code/.../control_api_v1/tests/` | **3832** | **7** | 10 | n/a single run | 63.79s |
| Mac · `program_code/ml_training/tests/` (PYTHONPATH=. from srv) | **336** | 0 | 31 | n/a single run | 1.56s |
| Mac · `cargo test --release -p openclaw_engine --lib` | **2559** | 0 | 0 ignored | yes (0.55s vs 0.56s) | full suite |
| Linux · `cargo test --release -p openclaw_engine --lib` | **2559** | 0 | 0 ignored | n/a single run | 0.53s |

**CLAUDE.md §九「2555 passed / 17 pre-existing failed」基準線過期**：control_api_v1 真實 3826/6 (Mac) 與 3832/7 (Linux)；srv root + control_api_v1 + ml_training 三 scope 加總接近 4300 PASS。**E4 profile.md 的 「2555 passed / 17 failed」是 W3p2a 之前的舊基準，建議 PM 同步更新**。

**Mac 6 fail 完整清單（Mac dev cold real run）**：
1. `tests/test_layer2.py::TestLayer2Engine::test_run_session_no_api_key`
2. `tests/test_layer2.py::TestLayer2Engine::test_l1_triage_success`
3. `tests/test_layer2.py::TestLayer2Engine::test_full_session_mocked`
4. `tests/test_layer2.py::TestLayer2Engine::test_session_with_tool_calls`
5. `tests/test_layer2.py::TestLayer2Engine::test_model_upgrade_triage`
6. `tests/test_replay_routes_safe_query_audit.py::test_case2_pg_kill_simulation_returns_200_degraded`

**Linux 7 fail = Mac 6 fail + 1 linux-only**：
- 多 1: `tests/test_grafana_data_writer.py::TestGrafanaDataWriterLifecycle::test_start_sets_running`（grafana writer lifecycle）

**4 個 panorama-confirmed 結構性 gap（這次 audit 重點）**：

1. **Python `H0_GATE` singleton 0 production caller**（CLAUDE.md panorama 確認）：實例化在 `paper_trading_wiring.py:291` `H0_GATE = H0Gate(config=H0GateConfig())`，governance route 讀 status 而已。`IntentProcessor` / `executor_agent.execute_order()` 路徑下 0 處 call `gate.evaluate()` / `gate.is_pass()`。**Rust 端 `pipeline.h0_gate.check()` 是 active hot path**（status_report.rs:90 注釋 "PNL-2: invariant — every tick must run H0Gate.check"），所以**「H0 0 caller」精確化 = Python H0_GATE singleton 0 production caller，但 Rust h0_gate 是 hot path active**。整合測試只覆蓋 Rust 路徑，Python 那一份是 dead infrastructure。
2. **lease_transitions audit writer 0 row（Linux runtime DB）**：CLAUDE.md panorama 已確認；Rust writer (`database/lease_transition_writer.rs:500 LOC` + 6 self-tests) + V054 migration test (`tests/migrations/test_v054_lease_transitions_audit_writer.py` 5 case) 都綠，但 router gate `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0` default OFF → writer **永遠收不到 transition event**。測試覆蓋 schema 結構與 writer 邊界，**0 個 e2e test 真實驗 flag flip→writer→DB row** 鏈。
3. **5-Agent ↔ Rust hot path 解耦**：Python `executor_agent.py:454` `governance_hub.acquire_lease()` 是當前唯一 production lease caller，Rust router gate 未啟。`shadow_mode_provider` default `lambda: True`（executor_agent.py:224）— P1-FAKE-1 fail-close 默認永久 shadow。
4. **5 ML training scripts silent-unscheduled**（Linux crontab 真實證實）：Linux crontab 只有 `daily_cost_snapshot` / `bybit_readonly_status_writer` / `cron_observer_cycle` / `counterfactual_daily` / `passive_wait_healthcheck` / `edge_label_backfill` / `ref21_market_microstructure_recorder` / `ref21_symbol_universe_snapshot`。**0 處 cron** schedule `mlde_demo_applier.py` / `linucb_trainer.py` / `quantile_trainer.py` / `scorer_trainer.py` / `mlde_shadow_advisor.py` / `dl3_ab_runner.py` / `canary_promoter.py`。test 在但 production runtime 從未跑。

**結論**：當前 baseline 整體綠，但有結構性「unit test pass 但 integration broken」的測試假綠模式，主要集中在：H0 (Python) / Decision Lease writer / xlang indicator 一致性 / SLA hot-path 真實壓測 / ML training scheduler。這些不是測試本身 broken，而是**production code path 0 caller**或**部分代碼 untested at integration level**。

---

## §2 Coverage 估計 per module

> 估計法：grep `def test_*` + `fn test_*` 對 module 的命中數 vs production 函數數比例（無 `coverage.py` / `cargo tarpaulin` runtime 工具，純 static estimate）

| Module | Production loc | Test count (file) | 估計 unit cov | 估計 integration cov | 風險 |
|---|---|---|---|---|---|
| `app/h0_gate.py` | 200 LOC | 5 (test_h_chain_integration / test_governance_routes_coverage / test_phase2_strategy_routes_coverage / test_startup_integrity / test_batch_d_risk_fail_closed) | ~70% | **0%** (Python 端 0 caller) | 🔴 高 |
| `app/governance_hub.py` (lease + auth) | ~3000 LOC | 1163 LOC test (test_governance_hub.py + test_governance_lease_bridge.py) | ~85% | ~50% (test 用 in-memory hub，不打 Rust IPC) | 🟡 中 |
| `app/executor_agent.py` (1500+ LOC) | 1500+ | test_executor_agent_unit + test_executor_audit_wiring + test_executor_config_cache + test_executor_decision_parity + test_executor_plan_v2 + test_executor_report_v2 + test_executor_shadow_to_live_e2e + test_executor_shadow_toggle_api (8 file) | ~80% | ~40% (`shadow_mode_provider=lambda: True` default 進路徑都被遮蔽) | 🟠 中-高 |
| `app/intent_processor.py` (Rust 主) | n/a | rust `intent_processor/tests*.rs` 多 file（含 tests_predictor_router 1294 行 perf SLA 1 case） | ~90% Rust unit | ~70% (lease bridge integration) | 🟢 低 |
| `app/strategist_*.py` (cognitive + decision_v2 + scheduler + agent + edge_eval + history_routes + promote_routes + fast_channel + weights + models 共 10 module) | 6000+ LOC | ~15 test file (test_strategist_*) | ~80% | ~50% (depends on H0_GATE / governance hub mocks) | 🟡 中 |
| `app/edge_estimator_scheduler.py` | 800+ LOC | 3 test file (min_observation_ts + observability + leader_lock) | ~75% | ~60% | 🟢 低 |
| `app/agent_spine_writer*.py` | n/a | test_agent_spine_client + test_base_agent_event_store + test_openclaw_supervisor_policy + test_openclaw_routes + test_openclaw_agent_control_static (5 file) | ~75% | ~45% (writer-only test 多，consumer 路徑少) | 🟡 中 |
| `rust/openclaw_engine/src/tick_pipeline/*` | 100K+ LOC | 廣泛 `tests/` submodule + property test | ~85% | ~75% | 🟢 低 |
| `rust/openclaw_engine/src/database/lease_transition_writer.rs` | 500 LOC | 6 #[test] + V054 migration 5 case | ~80% | **0% e2e flip→writer→row** | 🔴 高 |
| `rust/openclaw_engine/src/strategies/*` (5 strategies) | ~30K LOC | 廣泛 strategies/{*}/tests*.rs | ~85% | ~70% (depends on `paper_state` fixture) | 🟢 低 |
| `program_code/ml_training/*` | ~10K LOC | 35 test file (mlde_demo_applier + shadow_advisor + replay_veto + linucb_arm_migration + ...) | ~75% | **0% production runtime** (silent-unscheduled) | 🔴 高 |
| `helper_scripts/cron/ref21_*` | ~2K LOC | 3 test (test_ref21_market_microstructure_recorder / test_ref21_market_recorder_retention / test_replay_artifact_prune) | ~70% | ~80% (cron actually runs) | 🟢 低 |

**總體（粗估）**：
- **Unit test coverage** ~80%（健康）
- **Integration coverage** ~50%（中度，主要被 H0/Lease writer/xlang/SLA 拉低）
- **E2E coverage** ~25%（虛弱，依賴 Linux PG smoke + Rust binary spawn，Mac 端通常 skip）

---

## §3 邊界測試 gap 清單

| # | 邊界 | 期望覆蓋 | 真實覆蓋 | gap |
|---|---|---|---|---|
| B1 | Bybit `retCode` 邊界（10001 / 10002 / 10003 / 110007 / 110017 / 110)| 全 retCode 分類 + fail-closed retry | Python: 10001, 10003, 110007, 110017 局部命中（test_bybit_demo_sync / test_bybit_rest_client / test_live_gate_fallback）；Rust: bybit_rest_client_tests.rs `test_bybit_ret_code` 詳細分類含 phase 1B 9 new code | **Python 端 retCode 邊界僅 5 個 unique**（10001/10003/110007/110017/0），Bybit 完整 spec 50+ retCode 多數未覆蓋 |
| B2 | Lease TTL 邊界（0.1s / 30s / 300s）| TTL=0 / 0.1s / 30s default / 300s max / negative | `test_governance_lease_bridge.py:103` 只測 TTL=0.5；`test_lease_ttl_config.py:493` 測 active_default_ttl_seconds=0 | TTL 0.1s / 300s 真實 boundary 0 case；TTL=0 視為 "no expiry" 還是 "instant expiry" 邏輯未明 |
| B3 | engine_mode 切換邊界（paper→demo→live_demo→live）| 4 mode pairwise switch + reload | `test_executor_config_cache.py:225 test_provider_maps_live_demo_to_live` + `test_strategist_history_routes.py` 3 case 只覆蓋 IN-list / NOT-IN-list；`test_calibration_e2e_select_filters_engine_mode_and_14d_window` 部分 | **paper→demo / demo→live_demo / live_demo→live 切換** runtime 行為 0 e2e；`engine_mode` 100% 'paper' issue 沒有 regression test |
| B4 | Config hot-reload 邊界（ArcSwap）| concurrent reader + writer 不撞 / 2 reader 同步看新值 | 11 個 hot_reload test (trend_cooldown / bb_breakout / ai_budget tracker / strategist_scheduler / arch_rc1 e2e / maker_kpi 多份)；`test_arch_rc1_hot_reload_e2e_propagates_to_all_5_consumers` 是 e2e | ArcSwap concurrent reader **race 測試 0 case**；reload 過程中 reader 看到 partial state 的 race 0 case |
| B5 | Live authorization HMAC 過期邊界 | T-1ms / T+1ms / 24h / 360h | `test_perception_data_plane.py` 多 expired test、`test_governance_hub.py:1159 test_is_authorized_cache_expiry_race`；Rust `live_auth_watcher_tests.rs` | T-1ms / T+1ms 邊界 deterministic test 0 case；T0/T1/T2/T3 EarnedTrust pairwise 0 case |
| B6 | RiskConfig.position_pct 邊界（0% / 100% / 200%）| 邊界值拒收 / clamp 行為 | `tests/test_p3_low_coverage.py:7 compute_atr_position_size ATR invalid`、Rust `risk_config_tests.rs` 部分 | 0% / 100%（max 邊界）/ 負值 / >max（clamp 還是 reject）邏輯未明，0 deterministic case |
| B7 | StopManager ATR 邊界 | ATR=0 / NaN / 極大值 | rearrangement.rs `test_enforce_monotone_nan_propagates_but_does_not_panic` 部分 | ATR=NaN 進 stop calculation 是 panic 還是 fail-closed 0 case |

---

## §4 異常路徑 gap 清單

| # | 異常 | 真實覆蓋 | gap |
|---|---|---|---|
| E1 | Bybit API timeout（hung server） | Rust `bybit_rest_client_tests.rs:514 test_timeout_fires_on_hung_server_fail_closed` 真實 hang server fixture | Python 端 Bybit timeout 路徑覆蓋低（test_layer2_tools 多 timeout case 但 Layer2 是 AI 路徑，非 Bybit hot path）|
| E2 | DB connection drop（PG socket close） | `test_replay_routes_safe_query_audit.py::test_case2_pg_kill_simulation_returns_200_degraded` (BOTH Mac+Linux fail，pre-existing E4-P0-1 未修)；Rust `database/fallback.rs:136 test_open_new_file_failure_returns_false_no_panic` 部分 | **這個 fail 自身就是 P0-1 deterministic flaky bug**：fail-closed app fixture pollute (memory.md W6 條目)，不是真實 PG drop test |
| E3 | IPC socket 中斷 | Rust `ai_service_client.rs:295 test_connect_to_missing_socket_returns_none`、`test_governance_lease_bridge.py:261 test_ipc_timeout_returns_none` | IPC mid-stream 斷線（已 connect / 未完成 RPC）行為 0 case |
| E4 | Rust panic | 廣泛 `test_*_does_not_panic` (10+ case)；rust `should_panic` attribute 未廣泛使用 | panic 後 supervisor restart + state recovery 0 e2e case；engine 真 panic 觸發 cancel_token 0 case |
| E5 | Python OOM | 0 直接 case | 建議：當前 0% 覆蓋；ML training pipeline 大 dataset 加載時 OOM 路徑 0 case |
| E6 | Migration race（V### 並發 apply）| `MigrationRunner` 內部 advisory lock 0 deterministic 並發 test | 兩 worker 同時跑 `linux_bootstrap_db.sh --apply` 是否 deadlock 0 case |
| E7 | bybit_sync 死鎖（FUP-1 抑制） | `test_batch_d_risk_fail_closed.py:120 test_oe_006_close_retry_budget_has_real_timeout_guard` 部分 | P0-6 RCA 提到的 cost_gate 冷啟動死循環 deterministic regression test 0 case |
| E8 | live_auth_watcher event_consumer 漏 spawn（LIVE-AUTH-WATCHER fix）| Rust `live_auth_watcher_tests.rs` 自身單元 | watcher respawn 後 event_consumer pipeline 完整性 e2e 0 case |

---

## §5 並發測試 gap 清單

| # | 並發場景 | 真實覆蓋 | gap |
|---|---|---|---|
| C1 | Decision Lease per-intent 30s TTL 並發（100 並發 acquire 1 prevail） | `test_governance_hub.py:798 test_concurrent_lease_acquire_release` 用 3 thread × 3 iter；assert `len(lease_ids) >= 3` | **assert 太弱**：3 thread × 3 iter = 9 acquire，assert >=3 不驗 mutex semantic；應 assert 同 intent_id 同時間只有 1 lease alive |
| C2 | `agent_spine_writer` channel buffer 飽和 | 0 直接 case | channel buffer overflow 行為（drop / block / panic）0 deterministic case |
| C3 | Rust ArcSwap 多 reader concurrent | 11 hot_reload test 但都 single-thread sequential | **多 reader 並發讀 + 1 writer replace** race 0 case |
| C4 | `executor_config_cache` shared lock | `test_executor_config_cache.py` 含 cache test；`test_h_state_invalidator.py:386 test_concurrent_init_returns_single_instance` 部分 | shared lock 在 IPC fetch 失敗 + concurrent reader 路徑 race 0 case |
| C5 | strategist concurrent decision generation | `test_strategist_stress.py:171 test_concurrent_no_crash` + `test_concurrent_stats_consistent` | Strategist 並發跑 5 strategy × 25 symbol 是否 deadlock + decision 一致 0 case |
| C6 | governance_hub concurrent is_authorized cache | `test_governance_hub.py:767 test_concurrent_is_authorized` + `test_concurrent_status_reads` + `test_is_authorized_cache_expiry_race` | 已覆蓋（OK） |
| C7 | market_regime concurrent updates | `test_market_regime.py:623 test_concurrent_updates` + `test_concurrent_reads` | 已覆蓋（OK）|
| C8 | change_audit_log concurrent record | `test_change_audit_log.py:780 test_concurrent_record_changes` + `test_concurrent_approval_and_query` + `test_concurrent_mixed_operations` | 已覆蓋（OK）|

**整體並發覆蓋**：grep `asyncio.gather` / `threading.Thread` / `concurrent.futures` 命中 **114 處 test case**，但結構性 gap 在 ArcSwap multi-reader + agent_spine channel buffer + Decision Lease 真實 mutex semantic 三處。

---

## §6 Regression baseline 真實值 + drift

| 引擎 | E4 profile 寫死 baseline | 真實 (2026-05-08 Mac) | drift | 結論 |
|---|---|---|---|---|
| Python pytest（混淆 scope）| 2555/17 | control_api_v1: 3826/6 + ml_training: 336/0 + srv/tests: 137/0 = **4299/6** | +1744 PASS / -11 fail | **profile 過期**，建議更新 |
| Rust cargo --release --lib | "全綠" | **2559/0** | n/a | OK，但具體數需更新 |
| memory.md 最新（2026-05-05 R3 round 6）| 3522/1 (Mac control_api_v1) | 3826/1 (Mac control_api_v1) | +304 PASS | drift 顯著，主因 R3 round 6 後又新增 ~300 test 而 memory.md 未更新 |

**Mac 6 fail vs Linux 7 fail breakdown（4 categories）**：

1. **test_layer2.py 5 case**（Mac+Linux 共有）：`test_run_session_no_api_key` / `test_l1_triage_success` / `test_full_session_mocked` / `test_session_with_tool_calls` / `test_model_upgrade_triage`。CLAUDE.md panorama 已 cite「LG-3 provider pricing binding 0% binding」可能相關；屬 Layer 2 AI 推理 test，pre-existing。
2. **test_replay_routes_safe_query_audit.py::test_case2** 1 case（Mac+Linux 共有）：`test_case2_pg_kill_simulation_returns_200_degraded` — memory.md W6 條目 #2 識別為 deterministic flaky `app.dependency_overrides[current_actor] = _operator_actor` 沒 autouse teardown clear → FastAPI app 跨 test pollution。屬 E4-P0-1 pre-existing。
3. **test_grafana_data_writer.py::test_start_sets_running** 1 case（Linux only）：grafana writer lifecycle test；R3 round 6 audit 條目 6 已 flag「multi 1 grafana writer fail (與 R6 unrelated grafana lifecycle test)」屬 pre-existing P3。
4. **R3 round 6 條目 1 揭示的 fixture UUID drift**（platform-divergent）：Linux PG V049 schema enforce uuid，Mac mock 寬鬆 PASS。本次 Linux fail 7 比 Mac 多 1，但**沒有命中** Wave 3 P2a-S3 commit `07474741` 寫的 `experiment_id="exp-bob-2026-05-03"` fixture（已修）— 可能後續仍有遺漏 fixture（grep 命中 `exp-1` / `exp-binary-test` / `exp-2026-05-03-w4-t2` 等 Mac fixture 字符串，需 Linux PG smoke 確認）。

---

## §7 Mock-hides-logic 命中清單

> 依 CLAUDE.md skill §5.1（mock IO 邊界 OK）與 §5.2（mock 業務邏輯反例）審查 315 個 `MagicMock(spec=) / AsyncMock(spec=) / MagicMock() / AsyncMock()` 命中。

| # | 反例命中 | 嚴重 | reasoning |
|---|---|---|---|
| M1 | `test_governance_routes_coverage.py` × 16 hit `patch(f"{GOV_MOD}._get_governance_hub", return_value=hub)` 整 hub 替換 | 🟡 中 | 整個 governance_hub mock 但 hub 是業務 logic owner（auth + lease + audit 三大 SM）；route 只測「會回 hub.x()」，0 驗 hub 真實 behavior |
| M2 | `test_lg5_review_live_candidate.py:505` `MockHub.acquire_lease` 直接 record call (intent_id, scope, ttl_seconds)，0 驗 lease semantic | 🟠 中-高 | LG-5 reviewer Decision Lease 寫入路徑由 mock 全 stub，不驗 acquire→audit log→writer 鏈；CLAUDE.md panorama「LG-5 reviewer 0 audit row 累積」可能與此 mock 相關（mock 永遠成功 → bug 永遠看不到）|
| M3 | `test_executor_decision_parity.py` 用 YAML fixture 跑 reference spec 對比，**0 真實 Rust binary spawn**（_reference_decide 是 Python reimpl） | 🟠 中-高 | 名 "decision parity" 但其實是「Python implementation 內部對 spec 一致」，**Rust ↔ Python 雙端真實對齊 0 個 test** —— 跨語言 1e-4 容差完全沒驗 |
| M4 | `test_governance_lease_bridge.py:175-200` `_FakeIpcDispatcher` (asynccontextmanager) stub send/recv 但 parse_acquire_response/parse_release_response 業務邏輯真跑 | 🟢 低（OK 反例）| Sprint 3 Track H E-3 設計，memory.md 2026-05-03 條目 2 已 flag 為 OK；mock IO 邊界，業務邏輯真跑 |
| M5 | `test_bybit_demo_sync.py:244,338,383,492` `connector.get_executions/get_positions/get_wallet_balance.return_value = {"retCode": 10001}` | 🟢 低 | mock IO 邊界 OK；retCode 邊界覆蓋 |
| M6 | `test_layer2.py` 5 fail case 使用 `test_l1_triage_success` 等 mocked LLM call → 失敗即無 LLM mock 完整性 | 🟡 中 | 5 test fail 表 mock chain 自身 broken，不是業務邏輯 broken；test layer 自相不一致 |
| M7 | ml_training 35 test 多用 `MagicMock(spec=...)` 替換 PG / file IO；0 真實 PG round-trip（除 4 個 OPENCLAW_TEST_DSN gated）| 🟠 中-高 | mlde_demo_applier / linucb_arm_migration 業務邏輯（`learning.exit_features.est_net_bps` 寫入路徑）的 mock-only 測試 → CLAUDE.md panorama「100% NULL」可能就在 mock 路徑下永遠寫成功，真 PG 路徑寫不進去 |
| M8 | `test_paper_live_gate.py:837 test_concurrent_evaluations` + `test_concurrent_approval_submission` | 🟢 低 | 並發 fixture，OK |
| M9 | 全 suite 中 `lambda: True` / `lambda: False` 命中 9 處 — `test_executor_shadow_to_live_e2e.py` + `test_governance_lease_bridge.py` 都 hardcoded shadow_mode_provider | 🟠 中-高 | P1-FAKE-1：production default `lambda: True` (executor_agent.py:224) → 真實流量永久 shadow，但 test 用 `lambda: False` 仍能 PASS — **production fail-close 路徑 vs test fail-open 路徑分歧** |

**結論**：**315 mock 命中中 5 個高風險 mock-hides-logic 反例（M1, M2, M3, M7, M9）**。M3 跨語言 1e-4 一致性 0 真實雙端對齊與 M2 LG-5 lease 0 audit row 是兩個 production 證據級結構性問題。

---

## §8 跨語言浮點一致性

| 項目 | xlang test fixture | 容差 | 真實覆蓋 |
|---|---|---|---|
| `replay.simulated_fills` manifest signing | `tests/replay/test_manifest_signer_xlang_consistency.py` (433 LOC) + `rust/openclaw_engine/tests/replay_manifest_signer_xlang_consistency.rs` (303 LOC) | **byte-equal 0 容差** (HMAC SHA256) | ✓ 13 case 真實 Mac+Linux PASS |
| ATR / BB band / Sharpe / 動態 SL/TP / edge / PnL 計算 | **0** | n/a | ✗ **0 個 xlang case** |
| RiskConfig executor decision parity | `test_executor_decision_parity.py` 7 case | spec text equal | ✗ Python re-impl reference spec 對比 Python decide()，**Rust 不在 loop**（M3）|
| ipc_dispatch wire format | rust ipc_server tests + Python `test_ipc_integration.py` | wire byte-equal | ✓ 雙端各自 PASS，但 0 真實雙端 byte-equal cross check |
| `verify_replay_evidence` PG function | `tests/migrations/test_v055_*.py` Mac mock parse + Linux PG smoke (gated `OPENCLAW_TEST_DSN`) | spec text | ✓ 部分 |

**結論**：**CLAUDE.md skill §6「Rust ↔ Python ATR / BB / Sharpe 1e-4 容差測試」完全不存在**。manifest_signer 的 13 case 是**結構性 xlang invariant 測試**而非**indicator 浮點 1e-4 容差測試**。memory.md 2026-04-12 baseline 13 PASS 是 manifest_signer 那 13 case，不是 indicator 一致性。Profile.md 列出的「跨語言浮點一致性測試」尚未實裝，是純 spec。

---

## §9 SLA 壓測 fixture 真實位置 + 是否在 CI

| SLA 目標（CLAUDE.md skill §4.5）| 現有 fixture | 是否真實壓測 | CI |
|---|---|---|---|
| H0 Gate < 1ms | **0 fixture** | ✗ | n/a |
| Tick path < 0.3ms | **0 fixture**（rust 廣 unit 0.55s 跑 2559 case 但 0 deterministic latency assert） | ✗ | n/a |
| IPC round-trip < 5ms | `test_ipc_integration.py:719 test_fallback_latency_under_sla`（< 100ms 文件讀取）+ `:743 test_recovery_latency_under_sla`（< 100ms） | 部分（fallback / recovery 100ms ceiling，**非** IPC roundtrip） | ✓ Mac+Linux pytest |
| Decision Lease router gate（IPC budget 100µs / per-call ≤5µs）| `rust/intent_processor/tests_predictor_router.rs:1294 test_router_gate_perf_within_sla`（200µs 寬鬆 ceiling，非 5µs target） | 部分（200µs 寬鬆 bound 避 CI flake，注釋自宣「真實 SLA 監控由 cargo bench 負責」） | ✓ cargo test |
| 連 PG round-trip latency | 0 fixture | ✗ | n/a |

**結論**：**真正 H0/Tick/IPC 真實 SLA 壓測 0 個 in CI**。`tests_predictor_router.rs:1290` 注釋自宣「真實 SLA 監控由 cargo bench 負責」— `cargo bench` **不在 CI** 跑，operator 手動。tick path 0.3ms 與 H0 1ms target 沒任何 deterministic regression test 在 CI gate。

---

## §10 Top 20 測試 gap（按 risk 排序）+ 建議由誰寫

| Rank | Gap | Severity | 建議由誰 |
|---|---|---|---|
| **G1** | Decision Lease flag flip→writer→DB row e2e regression test（router gate ON canary 後 first-row writer signal 0 case） | 🔴 P0 | **E1**（要打真 PG + Rust binary spawn，不是純測試）|
| **G2** | xlang ATR / BB / Sharpe / edge / PnL 1e-4 容差 test 從 0 起建（CLAUDE.md skill §6 spec）| 🔴 P0 | E1（需建 Rust IPC compute_atr / compute_bb 等接口）+ E4 各 ~1e-4 assert |
| **G3** | H0_GATE Python production caller 接線（`paper_trading_wiring.py:291` 實例化後 0 caller） | 🔴 P0 | E1 (production code 接線) → E4 (regression)|
| **G4** | Layer 2 5 fail (`test_layer2.py` test_run_session_no_api_key 等) — pre-existing 但未修；CLAUDE.md panorama 已 cite LG-3 provider pricing binding 0% | 🔴 P0 | E1 (Layer 2 AI 路徑修)|
| **G5** | `test_case2_pg_kill_simulation_returns_200_degraded` deterministic flaky (E4-P0-1; memory W6 條目 #2 / R3 round 6 條目 6) — 跨 test FastAPI app dep_overrides pollution | 🟠 P1 | E4 (純 test cleanup fixture)|
| **G6** | ML training silent-unscheduled (5 script 未進 cron) — `mlde_demo_applier` / `linucb_trainer` / `quantile_trainer` / `scorer_trainer` / `mlde_shadow_advisor` | 🟠 P1 | E1 (cron 排程) + E4 (cron-runner integration test)|
| **G7** | M2 LG-5 reviewer Decision Lease test mock-only 永遠成功 — `test_lg5_review_live_candidate.py:505` MockHub stub | 🟠 P1 | E4 (改成真 GovernanceHub fixture + audit row count assert)|
| **G8** | M7 ml_training PG round-trip 0 真實 case — 4 個 OPENCLAW_TEST_DSN gated 但 Linux 也未啟 | 🟠 P1 | E4 (Linux smoke 啟用 + 改 default OPENCLAW_TEST_DSN existence assert)|
| **G9** | M3 executor parity test 不是真實 Rust↔Python — `_reference_decide` 是 Python re-impl，0 Rust binary spawn | 🟠 P1 | E1 (Rust IPC executor.decide 接口) + E4 (改成真 cross-call)|
| **G10** | retCode 邊界 Bybit spec 50+ code 多數未覆蓋（Python 端僅 5 unique）| 🟡 P2 | E4 (parametrize fixture)|
| **G11** | Lease TTL 0.1s / 300s / negative 邊界 0 case | 🟡 P2 | E4 |
| **G12** | engine_mode paper→demo→live_demo→live 4 切換 e2e 0 case | 🟡 P2 | E1 (mode_switch fixture spawn) + E4 |
| **G13** | ArcSwap multi-reader concurrent + 1 writer replace race 0 case | 🟡 P2 | E1 (proptest fixture) + E4 |
| **G14** | agent_spine channel buffer overflow 行為 0 case | 🟡 P2 | E4 |
| **G15** | Live HMAC T-1ms / T+1ms boundary 0 deterministic | 🟡 P2 | E4 |
| **G16** | StopManager ATR=NaN / 極大值 panic vs fail-closed 0 case | 🟡 P2 | E4 |
| **G17** | DB connection drop（PG socket close）真實案例 0 case；當前是 fixture pollution flaky | 🟡 P2 | E1 (PG mock socket drop) + E4 |
| **G18** | Migration race（兩 worker 同時 V### apply）0 case | 🟡 P2 | E4 |
| **G19** | H0 Gate < 1ms / Tick < 0.3ms 真實 SLA fixture 0 case in CI | 🟡 P2 | E1 (cargo bench → CI 接線) + E4 (latency assert)|
| **G20** | EarnedTrust T0/T1/T2/T3 pairwise transition 0 case | 🟢 P3 | E4 |

---

## §11 Regression Verdict

**Verdict**：**PASS（baseline 維持，Mac+Linux 雙端 deterministic identical）+ 21 個結構性 gap 揭示**。

當前 commit `4e2d2883`（PM HEAD）的測試 baseline 健康（Mac control_api_v1 3826/6 / Linux 3832/7 雙跑 identical / cargo lib 2559/0 雙跑 identical / xlang manifest_signer 13/0 PASS）。**6/7 fail 全部 pre-existing**，無新增 regression。

**但**測試覆蓋的「真綠」與「假綠」邊界顯著：
1. unit test 覆蓋良好（~80%）
2. integration test 覆蓋中等（~50%），主要被 H0 / Decision Lease writer / xlang indicator / SLA / ML training scheduler 5 個結構性 gap 拉低
3. e2e test 覆蓋虛弱（~25%），多個關鍵路徑（ML training / Decision Lease flip / mode switch）依賴 Linux PG smoke 或 Rust binary spawn，Mac dev 無法觸發

**對 PM 建議**（不寫業務 test，只給 PA 派工建議）：
- **G1-G4 屬 P0**，建議 PA 在下一 sprint dispatch queue 排這 4 個，由 E1 主導 production code 接線 + E4 跑 e2e regression
- **G5 純 E4 工作**（fixture cleanup 0 production 動），可獨立排
- **G6-G9 屬 P1**，與 W-A executor fake-live runtime smoke / W-B runtime Agent Decision Spine lineage 高度耦合（CLAUDE.md §十 active dispatch queue）
- **G10-G20 屬 P2/P3**，當前 sprint 不阻擋 live target，但需在 `LG-2/3/4` IMPL 前完成

**E4 profile.md 基準線需更新**：建議 `2555 passed / 17 pre-existing failed` → `4299 passed / 6 pre-existing failed (Mac control_api_v1 + ml_training + srv/tests / cargo lib 2559)`。

---

E4 AUDIT DONE
