# E4 Memory — 工作記憶

## 項目上下文（2026-04-01）

- 當前 Phase：Phase 3 Batch 3A 完成
- 測試基準：**3310 passed / 21 failed / 17 errors**（3349 collected）
- Pre-existing failures：17（與 March 31 一致）
- New failures：4 FAILED + 17 ERRORS（回歸問題）
- 系統模式：demo_only

## 工作記憶

### 2026-04-26 Wave 3 G2-06 bb_breakout 永久 disable 回歸驗證

**結論：E4 PASS**

**測試結果：**
- Linux baseline (HEAD 8946e47, 不含 G2-06)：**2138 passed / 0 failed**（與 TODO L10 完全一致）
- Mac local cargo test --release（含 G2-06 5 行 Rust comment）：**2138 passed / 0 failed**（兩遍同綠 = 非 flaky）
- Mac cargo check：0 new warning（9 既有 warnings 與 G2-06 無關）
- Mac cargo doc + rendered HTML 驗證：`pub enum BbBreakoutProfile` 上方 `///` doc + `//` G2-06 plain block + `#[derive]` 排列下，rustdoc 完整保留 Conservative/Balanced/Aggressive/嚴格/寬鬆/當前生產 — `//` plain 不汙染 ✓
- Mac local Python 3.12 兩遍 healthcheck 函數測試：
  - `_read_bb_breakout_active_from_toml()` → `(False, "ok")` 同綠
  - `[18] check_disabled_strategy_inventory()` → PASS `disabled strategies: bb_breakout, funding_arb (active count=3: ...)` 同綠
  - `[12] check_bb_breakout_post_deadlock_fix(StubCur)` → PASS `disabled by G2-06 ... fill check skipped` 同綠（StubCur execute() 故意 raise — 證 active=false 早 return SQL 不執行 ✓）
- Python ast.parse: passive_wait_healthcheck.py / bb_breakout_threshold_sweep.py 兩檔 OK
- TOML 三環境 grep: demo/paper/live 全部 `[bb_breakout].active = false` + 雙語 G2-06 disable comment 模板一致

**3 條 non-blocking drift 觀察（PM commit 時可選 sweep）：**

1. **CLAUDE.md L488 §十一 一句話狀態「17 check」**：實測 main() 內 19 次 check_*() 呼叫（含 [Xa]/[Xb] 18，加 [18] 後 19）— 過期，但 §十一 是 2026-04-24 採集快照，G6-04 §三 drift 規則範圍但**不在 E1 任務界內**
2. **CLAUDE.md L82 「engine lib 1939 → 1980 passed」**：應為 2138（已 baseline）
3. **paper.toml `[funding_arb].active = true`**：demo/live 都 disabled 但 paper 仍 active —— 獨立 drift（per G-2 結案 2026-04-18 殘留），G2-06 範疇外，E1 沒擴大正確

**設計亮點 / 學到的事：**
- E1 §3.4「合法 orphan comment」風險點獨立驗證為真：rustdoc 仍 attach `///` doc 到 enum，`//` plain block 不汙染 — 但**驗證需要 cargo doc + 渲染 HTML grep**，光 cargo check 0 warning 不夠
- StubCur 反向 mock guard：故意 raise execute() 來**證明** active=false 時 SQL 路徑根本不執行，比 mock 業務邏輯更乾淨
- [18] disabled_strategy_inventory 只讀 demo TOML 是 Phase 1a 局限（paper/live 各自 disabled 看不到）— 適合當前 scope，未來可加 [19]/[20]
- baseline 數字源優先級：**TODO L10（2138）> Linux cargo 實測（2138）> CLAUDE.md §三 內各種中段數字（1939/1980 過期）**；E4 驗 baseline 必跑命令拿真數字，不信 CLAUDE.md 寫死

**派發鏈說明：** PM 直接從 E1 派 E4 跳過 E2 review，但本 E4 報告對 E2 必查 5 點（TOML 同方向 / [12] 不擴張 / [18] 純 observability / Rust doc-attribute / drift 規則）全部驗了一遍，等同 E2 + E4 合一通過。

**Working tree 狀態：** 所有 G2-06 改動仍 Mac local，Linux HEAD 8946e47（不含 G2-06）— 採 Mac local 直驗 + Linux baseline grep 雙路徑驗證。

**報告位置：** `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-26--g2_06_disable_regression.md`

---

### 2026-04-26 Wave 3 G8-02 ExecutorAgent decision parity 回歸驗證

**結論：E4 Pass with conditions**

**測試結果：**
- G8-02 testfile 獨立：5 passed / 2 skipped / agree=70/70 (100%) — 不 flaky（兩次同綠）
- control_api_v1 子集 baseline：2749→**2754 passed**（+5），35 pre-existing failed 不變（與 G8-02 無關）
- Rust engine lib：2138 / 0 fail 不變（G8-02 不動 Rust 代碼）

**35 pre-existing failed root cause（與 G8-02 無關，建議 PM 開新 ticket）：**
- `test_executor_shadow_toggle_api.py`（17）+ `test_strategist_promote_api.py`（18）
- 獨立跑 → 全綠；與 G8-02 + 兩檔組合 40 個一起跑 → 全綠
- 全量跑時 fail = test ordering pollution（推測 module-scope fixture 或 STORE / shadow_mode_provider singleton mutation）

**4 大 WARN（PM 必須清楚理解，oversell 風險）：**

1. **G8-02 是 Python runtime ↔ Rust schema spec parity，不是 Python ↔ Rust runtime parity**
   - `_reference_decide()` 是純 Python function 寫的 schema intent
   - 完全不打 Rust 引擎（無 cargo run / IPC dispatch / Rust deserialize 驗）
   - testfile line 35-40 自己 honest 標明：「it is *not* a re-implementation of Rust runtime, **it *is* the schema's intent**」
   - 真 Rust runtime parity 屬 G3-08

2. **70 case 100% agree 是邏輯上的必然，非 statistical confidence**
   - 兩邊都只判一個 bool（shadow_mode）
   - max_position_pct / per_symbol_cap 全 case 不 gate（Wave-3 scope，golden_15 自承「Rust catches」）
   - 95% binary threshold 寫進 test 是 future-proof（將來 shadow_mode 邏輯增複雜時的 regression 邊界）

3. **「synthetic_replay」術語 misleading**
   - 40 case 並非真實 `decision_outcomes` table dump
   - 是 procedurally generated boundary cases（隨機 ~20 symbol，shadow_mode true/false 各半）
   - PA RFC Q2 若定義廣義 synthetic OK，否則需與 PA 對齊

4. **E1 fixture 行數 self-report 誤差**：報 661 / 實 838

**Mock 邊界（PASS）：**
- ExecutorConfigCache._inject_snapshot_for_tests() 繞 IPC socket — OK
- paper_trading_routes._ipc_command 用 _IpcCallRecorder — OK
- ExecutorAgent.execute_order() / _execute_via_ipc() / shadow_mode_provider lambda chain 全真跑 — OK
- 不算 mock 業務邏輯

**Conditions（PM 合併前釐清）：**
1. close-out 報告 / TODO 條目加註 G8-02 不是真 runtime parity
2. synthetic_replay 術語校準
3. G3-08 必須補 cargo `tests/executor_parity_test.rs` 真 IPC dispatch
4. 35 pre-existing failed test isolation 開新 ticket
5. 教訓：fixture self-report 行數 PA/E2 必做 sanity check

**報告位置：** `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-26--wave3_g8_02_regression.md`

---

### 2026-04-24 全程序範圍測試檢驗（full-chain testing audit）

**結論：A-（優秀）— 測試充分，但 CI 完全不存在 + 6 個 error-path 缺口阻塞 Live**

**覆蓋面快照（grep-based，非實跑）：**
- Rust engine inline：149 檔 / ~2,103 `#[test]`/`#[tokio::test]`（對應 §三 lib 1980 passed 基準，差值為 `#[ignore]` / feature-gated）
- Rust engine integration：`tests/*.rs` 7 檔 / **85 測**（stress 35 / reconciler_e2e 19 / edge_predictor_ort ~10 / micro_profit_fix 7 / migrations 5 / phase4 3 / rrc1 ~6）
- Python pytest：121 檔 / **~3,006** 測（控制 API 93/2687 + ml_training 26/292 + audit+local_model_tools 2/31；與 §十一 pytest 2996 承襲基準吻合）
- Healthcheck：`passive_wait_healthcheck.py` 12 checks（[1]~[12]，[8] shadow_exits L2-5 TOML 主動診斷 / [10] 4/17 post-mortem / [11] EDGE-DIAG-1 Phase 3 auto-gate / [12] FIX-26 驗收）
- **CI：0 workflow 檔**（`.github/workflows/` 不存在）
- **獨立 smoke 腳本：0**（canary `test_canary.py` 未驗；rollback_drill.sh 是 operational）

**5 項評估維度結果：**
1. 正常路徑：A-（tick_pipeline 120 測 / 策略 5 個全備 / 5-Agent 齊 / Decision Lease + Auth + hot-reload 完整）
2. 邊界：B+（qty=0/HMAC/leader lock 已覆蓋；funding_rate 極端 / ATR NaN/Inf / balance=0 / UTC 時邊界 / auth TTL=exp 未補）
3. 異常：B-（REST fail-closed 齊；但 **WS 斷線止損 / DB 斷線 / IPC 超時 / config 破損熱重載 / authorization 篡改 / intents writer 失敗** 全缺）
4. 並發：A-（leader lock multiprocess 齊 / Reconciler 100-cycle + 50 symbols + 20 rapid 齊；ArcSwap torn-read + IPC 多 worker 共享 slot 缺）
5. 回歸：A-（FIX-26 7測 + FA-PHANTOM-1/2 + MICRO-PROFIT 7 + PNL-FIX 隱含 + RUST-DOUBLE-PREFIX healthcheck 守門；STRATEGY-CLOSE-TAG-FIX `strip_phys_lock_prefix` 缺 unit）

**Top 10 Blocking Gaps（排序對齊 Live 日期 W24 末 ~2026-05-23）：**
1. **[P0] CI 完全不存在**（`.github/workflows/` 缺）
2. **[P0] ExecutorAgent shadow→live 切換契約無測**（阻 G-1）
3. **[P1] WS 斷線期間止損安全性**（§四 E-1）
4. **[P1] PostgreSQL 斷線期間 Rust writer 行為**（§四 E-2）
5. **[P1] trading.intents 寫失敗 unit regression**（只靠 healthcheck [10]）
6. **[P1] authorization 簽名篡改 engine 行為**（§四 E-10）
7. **[P1] ArcSwap torn-read under tick spike**（§五 C-1）
8. **[P1] 21d demo 穩定 aggregate healthcheck**（違 §七「被動等待必附 check」）
9. **[P1] PostOnly maker fill rate healthcheck**（違 §七）
10. **[P2] STRATEGY-CLOSE-TAG-FIX `strip_phys_lock_prefix` unit regression**

**關鍵對齊：**
- 12 healthcheck 對應 §三 active 被動等待 90%；H-1/H-2/H-3 違 §七 新被動等待規則，必補
- Python stop_manager.py 已退役（3E-ARCH 後）— 2026-04-01 報告敘述「319 LOC」過期
- IPC handlers inline 0 測，但 `ipc_server/tests/` sub-dir 覆蓋（dispatch 10 / config 8 / risk 7 / budget 7）— 分位正常

**報告位置：** `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-24--full_chain_testing_audit.md`

---

### 2026-04-01 全程序測試審計

**結論：PASS（有條件）— 整體進步顯著，但有 4 個新回歸需修復**
- 測試文件：71 → 96（+25）
- 測試 cases：~2,480 → 3,349（+869）
- passed：~2,480 → 3,310（+830）
- 估算覆蓋率：~62% → ~68%（+6pp）
- 關鍵改善：pipeline_bridge 15%→50%，governance_routes 10%→45%，ws_listener 20%→65%，demo_connector 8%→60%
- 新增回歸：4 FAILED（h0_gate sync、inverse leverage、session9 count、strategies OrderIntent）+ 17 ERRORS（session9 import）
- 最大缺口：strategy_auto_deployer 685 LOC 零測試、bybit_demo_sync 269 LOC 僅 1 間接
- 報告位置：docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-01--testing_audit.md + docs/audit/April01/E4_testing_report_2026-04-01.md

### 2026-03-31 Sprint 5b 全量回歸

**結論：PASS**
- 總計：2610 passed, 17 failed（全部 pre-existing）, 1 skipped
- 收集：2628 tests collected
- 執行時間：~59.65s
- 目標 ≥ 2600：✅ 達成（2610 passed）
- 17 pre-existing failures 清單與預期完全一致，無新增 failure
- 測試基準更新：**2610 passed**（較上次 2599 +11）

**新增測試（相較上次基準 2599）：+11 tests**
- test_h_chain_integration.py（TestPrinciple14OllamaFallback × 6）：全部 PASS
- test_scout_worker.py（× 10）：全部 PASS
- roi_basis / cost_tracker / ollama_call 標記測試（7 個）：全部 PASS

### 2026-03-31 Sprint 5b-5 根原則 14 集成測試（Principle 14 Ollama Fallback）

**結論：PASS**
- 新增測試：6（TestPrinciple14OllamaFallback）
- 文件位置：`tests/test_h_chain_integration.py`
- 全量回歸：2599 passed, 17/18 failed（全部 pre-existing），1 skipped
- 目標 ≥ 2576 + 6 = 2582：✅ 達成（2599 passed）

**6 個測試行為驗證：**
1. `test_ollama_unavailable_strategist_uses_heuristic`：is_available=False → judge_edge 不被調用，heuristic_evaluations 遞增
2. `test_ollama_unavailable_h1_budget_check_passes`：cost_tracker=None → _h1_check_budget() 返回 True（fail-open）
3. `test_ollama_unavailable_pipeline_bridge_processes_intents`：PipelineBridge._process_pending_intents() 無 Ollama 時不崩潰
4. `test_ollama_unavailable_h0_gate_still_blocks_bad_intents`：H0 Gate 確定性邏輯不依賴 Ollama，freshness check 仍阻擋
5. `test_ollama_unavailable_executor_still_applies_fail_closed`：acquire_lease()=None → ExecutorAgent 拒絕執行（原則 3 不依賴 Ollama）
6. `test_ollama_crash_mid_evaluation_falls_back`：_ai_evaluate 中 ConnectionError → catch + heuristic fallback + error 計數

**關鍵發現：**
- PipelineBridge 需要 3 個必填位置參數（kline_manager/indicator_engine/signal_engine）
- 所有降級邏輯均在 _evaluate_edge() 中正確實現（is_available=False 或異常均走 heuristic）
- H0 Gate 完全不依賴 Ollama（純確定性）
- ExecutorAgent 的 Principle 3 執行與 Ollama 狀態無關

**測試基準更新：2599 passed**（較上次 2576 +23）

### 2026-03-31 Sprint 5a 回歸（Position Sizing + Paper/Demo Sync）

**結論：PASS**
- 總計：2576 passed, 17 failed（pre-existing）, 1 skipped
- 收集：2594 tests collected
- 執行時間：~37.60s
- 目標 ≥ 2575：✅ 達成（2576 passed）
- 17 pre-existing failures 清單與預期完全一致，無新增 failure

**新增測試（相較上次基準 2561）：+15 tests**
- test_strategist_agent.py：15 tests（TestScoutStrategistChain 2 + TestH1ThoughtGate 11 + TestStrategistShadowFalse 2）
- H0 Gate 測試（test_h0_gate.py）：94 tests，全部通過

**已知 pre-existing failures（17 個，全部歸屬明確）：**
- test_batch10_learning_oms.py（2）：TestL2CronTrigger（asyncio event loop deprecation）
- test_edge_filter_integration.py（1）：test_edge_filter_respects_timeout
- test_integration_phase11.py（2）：TestEngineTierEnforcement（L1 reject submit/cancel）
- test_learning_tier_gate.py（1）：test_l1_capabilities
- test_ollama_integration.py（11）：LocalLLMSearchProvider（3）+ L1TriageLocalFallback（8）

### 2026-03-31 Sprint 0 回歸（G-05 + G-01）

**結論：PASS**
- 總計：2561 passed, 17 failed（pre-existing）, 1 skipped
- G-05 TestExecutorAgentDecisionLease：6/6 PASS（test_26～test_31）
- G-01 test_layer2.py：79/79 PASS
- 17 pre-existing failures 清單與預期完全一致，無新增 failure

**重要教訓：**
- pytest 收集 `test_app` 時有 PytestCollectionWarning（fastapi app instance，非真正問題）
- Pydantic V1 deprecated warnings 在 scout_routes.py（不影響功能）

### 2026-03-31 Wave 6 Sprint 0 TD-1 全量回歸（pipeline_bridge acquire_lease）

**結論：PASS**
- 總計：2614 passed, 17 failed（全部 pre-existing）, 1 skipped
- 收集：2632 tests collected
- 執行時間：~63.27s
- 目標 ≥ 2614：✅ 達成（2614 passed）
- 17 pre-existing failures 清單與預期完全一致，無新增 failure
- 測試基準更新：**2614 passed**（較上次 2610 +4）

**4 個 TestPipelineBridgeDecisionLease 測試（全部 PASS）：**
1. `test_td1_no_hub_fail_open_submit_proceeds`：hub=None → fail-open，submit 繼續
2. `test_td1_acquire_lease_none_fail_closed_submit_blocked`：acquire_lease()=None → fail-closed，submit 阻擋
3. `test_td1_acquire_lease_success_submit_proceeds`：acquire_lease() 成功 → submit 繼續
4. `test_td1_acquire_lease_exception_fail_closed`：acquire_lease() 拋異常 → fail-closed，submit 阻擋

**位置：** `tests/test_edge_filter_integration.py::TestPipelineBridgeDecisionLease`

### 2026-03-31 Wave 6 Sprint 1b 1B-1 Cooldown 聯動煙霧測試

**結論：PASS**
- 5 個測試全部 PASS（test_h0_gate_cooldown_integration.py）
- 全量回歸：2624 passed, 17 failed（全部 pre-existing）, 1 skipped（第二次穩定跑，無新增 failure）
- 目標 ≥ 2614：✅ 達成（2624 passed）
- 測試基準更新：**2619 passed**（保守估計：2614 + 5 新增；最新穩定跑 2624 但有測試順序影響波動）

**5 個新增測試（TestH0GateCooldownIntegration）：**
1. `test_risk_manager_pushes_cooldown_to_h0gate`：RiskManager 3連敗 → mock H0Gate.update_risk() 被調用，snapshot.cooldown_until > now ✅
2. `test_h0gate_blocks_during_cooldown`：update_risk(future cooldown) → check() allowed=False, check_name="cooldown" ✅
3. `test_h0gate_allows_after_cooldown_expires`：update_risk(past cooldown) → check() allowed=True ✅
4. `test_h0gate_cooldown_zero_does_not_block`：cooldown_until_ts_ms=0 → check() allowed=True ✅
5. `test_h0gate_cooldown_check_includes_reason`：blocked → reason.lower() contains "cooldown", check_name="cooldown" ✅

**關鍵發現：**
- H0Gate.check() 冷卻期判斷邏輯：`cooldown_until > 0 and now_ms < cooldown_until` → 正確
- RiskManager.record_fill_result() 在 consecutive_losses >= cooldown_count 時呼叫 H0Gate.update_risk()，保留現有 open_position_count/total_exposure_pct/kill_switch_active 不變 → 設計正確
- test_h0_gate.py::TestGovernanceRoutesH0GateStatus 在全量跑時偶發 3 失敗（模組狀態干擾），單獨跑全部通過，為 pre-existing 間歇性問題，與本 Sprint 無關

## 報告索引

| 日期 | 任務 | 文件位置 |
|------|------|---------|
| 2026-04-26 | Wave 3 G2-06 bb_breakout 永久 disable 回歸驗證（E4 PASS / Rust 2138 不變兩遍 / Mac local Python 3.12 兩遍 healthcheck 同綠 / cargo doc 證 //G2-06 plain 不汙染 ///doc / 3 條 non-blocking drift） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-26--g2_06_disable_regression.md` |
| 2026-04-26 | Wave 3 G8-02 ExecutorAgent decision parity 回歸驗證（E4 Pass with conditions / +5 passed / Rust 2138 不變 / 4 WARN oversell 風險） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-26--wave3_g8_02_regression.md` |
| 2026-04-24 | Full-chain Testing Audit（Rust 2103 inline + 85 integration / Python 3006 / HC 12 checks / CI 0 / Top 10 gaps） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-24--full_chain_testing_audit.md` |
| 2026-04-01 | 全程序測試覆蓋評估（3310 passed / 96 test files / 18 無測模塊） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-01--testing_audit.md` |
| 2026-03-31 | Wave 6 Sprint 1b 1B-1 Cooldown 聯動煙霧測試（5 tests，2624 passed） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint1b_cooldown_smoketest.md` |
| 2026-03-31 | Wave 6 Sprint 0 TD-1 全量回歸（2614 passed，acquire_lease 修復驗收） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint0_td1_regression.md` |
| 2026-03-31 | Sprint 5b 全量回歸（2610 passed，Sprint 5b 最終驗收） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint5b_regression.md` |
| 2026-03-31 | Sprint 5b-5 根原則 14 集成測試（Principle 14 Ollama Fallback，6 tests） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint5b_p14_tests.md` |
| 2026-03-31 | Sprint 5a 全量回歸（Position Sizing + Paper/Demo Sync） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint5a_regression.md` |
| 2026-03-31 | Sprint 0 全量回歸（G-05 + G-01） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint0_regression.md` |
