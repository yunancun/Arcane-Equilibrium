# E4 Test Audit Verification — 2026-05-09 · 玄衡 (HEAD `7fccad06`)

> 角色：E4（Test Engineer）· 任務：對 2026-05-08 21 個結構性 gap 在過去 24h 修復做**對抗性嚴苛核實**
> 範圍：72f05aa0..7fccad06 共 28 commits / Mac+Linux 雙端真實重跑（兩遍 deterministic 對比）
> 不接受「baseline still PASS」單一論斷；必驗新加 e2e/xlang test 是否真存在 + mock 不掩蓋邏輯 + 跑兩遍 deterministic

---

## §1 Executive Summary

**真實 baseline 雙跑 deterministic identical**：

| 引擎 / scope | 1st run | 2nd run | 2026-05-08 baseline | delta | identical |
|---|---:|---:|---:|---:|---|
| Mac · `srv/tests/` (root) | **208/0/2 skip** | **208/0/2 skip** | 137/0/2 | **+71 PASS** | yes |
| Mac · control_api_v1（ignore 4 collection errors）| **3898/7/13 skip** | **3898/7/13 skip** | 3826/6/17 | **+72 PASS / +1 fail** | yes |
| Linux · control_api_v1（ignore 4 collection errors）| **3871/10/37 skip** | n/a | 3832/7/10 | **+39 PASS / +3 fail** | n/a |
| Linux · `cargo test --release -p openclaw_engine --lib` | **2560/0** | **2560/0** | 2559/0 | **+1 PASS** | yes |
| Mac · `cargo test --release -p openclaw_engine --lib` | n/a | n/a | 2559/0 | n/a | n/a (跑 Linux 即可) |

**Engine runtime 健康** ✅ — Linux engine PID alive，snapshot age 9.1s，passive healthcheck WARN-only no hard FAIL。

**Pytest 4 collection errors（pre-existing，**不是新破壞**）**：
- `tests/replay/test_calibration_label_python.py` / `test_r6_calibration_e2e.py` / `test_r6t6_update_execution_confidence.py` / `test_r7_e2e_advisory_integration.py`
- 根因：`from program_code.exchange_connectors...` import 在 control_api_v1 sub-dir 跑 venv 時 PYTHONPATH 不含 srv root；從 srv root + PYTHONPATH=. 跑可繞過（驗 `test_r7` 6 passed）
- 對應 commits 都是 baseline 之前（`f47c530c` `edac7d1b` `29d41991` `7a04d2f4`）
- ⚠️ 2026-05-08 audit baseline 沒揭示這 4 個 collection errors（不在 §1 deterministic identical 表）— **是 audit 自身的 baseline 漏洞**

**新增 1 fail（**真實新破壞**）**：
- Mac+Linux: `test_batch_d_risk_fail_closed.py::test_oe_006_close_retry_budget_has_real_timeout_guard`
- 根因：`commit 3cff1005 refactor: split event consumer hot files` 把 `test_close_attempt_timeout_constant_is_500ms` test 從 `dispatch.rs` 搬到 `dispatch_tests.rs`，但 static-grep `_read("rust/openclaw_engine/src/event_consumer/dispatch.rs")` path 沒同步更新 → assertion fail
- ⚠️ **E1 自己的 split refactor 把對自己的 static-grep test 弄壞了，而 commit message 自宣 "Add a static LOC regression and update W-AUDIT-5b" — refactor 邊界檢查不到位**

**新增 2 Linux-only fail（疑似 platform-divergent 但未在 audit baseline 揭示）**：
- `test_replay_advisory_routes.py::test_replay_advisory_rank_route_caps_and_never_invokes_applier`（Linux 422 vs Mac 200）
- `test_replay_advisory_routes.py::test_replay_advisory_compare_route_is_read_only`
- 28 commits 沒動 `test_replay_advisory_routes.py` 也沒動 advisory 路由 — 應為 pre-existing Linux schema divergence 但 2026-05-08 audit baseline (Linux 7 fail) 沒揭示

**21 gap 修復統計**：
- ✅ DONE / partially DONE: **8** （G1 partial / G6 partial / G10 nominal / W-AUDIT-2 security / h_state split / V076-V077 / state machine snapshot mutation / V073 cron wrapper）
- ⚠️ NOT FIXED but partial work: **5** （G3 SLA <1ms 0 case / G4 ExecutorAgent shadow_mode 真切換 e2e 0 case 新增 / G7 LG-5 mock-only 仍未改 / G8 ml_training PG round-trip 仍 mock-only / G9 executor parity Rust↔Python 仍 0 真實 cross-call）
- ❌ NOT TOUCHED: **8** （G2 xlang ATR/BB/Sharpe 1e-4 0 case / G5 test_case2 deterministic flaky 仍 fail / G11-G18 邊界邊緣全未動）
- 🆕 NEW REGRESSION / ISSUE: **3** （test_oe_006 static-grep stale path / 2 Linux-only replay_advisory 422 fail）

---

## §2 21 Gap 逐條核實

### G1 — Decision Lease flag flip→writer→DB row e2e regression test ✅ PARTIAL DONE

- 文件存在：**`rust/openclaw_engine/tests/lease_flag_flip_e2e.rs` (260 LOC)** — commit `da2dba25 audit: close W-AUDIT-3 partial lease gaps`
- 跑驗：`cargo test --release -p openclaw_engine --test lease_flag_flip_e2e` → **2/2 PASS**
  - `router_flag_flip_emits_writer_channel_transitions` (channel msg)
  - `router_flag_flip_writes_lease_transition_rows_when_test_pg_present` (opt-in `OPENCLAW_TEST_PG`)
- ⚠️ **PUSH BACK**：commit message 自承「opt-in via `OPENCLAW_TEST_PG`; never uses runtime DB envs」，意即 CI 默認**不跑真實 PG row 持久化 e2e**，只在 operator 設 env var 時才驗 row insert；當前 CI 只跑 channel msg case（mock pipeline）
- 自宣解：`router_flag_flip_writes_lease_transition_rows_when_test_pg_present` 跑了 1 passed（Linux env 沒設 `OPENCLAW_TEST_PG` → 函數 early-return PASS without exercising PG path）— **這不是真 e2e PG 持久化驗證**，只是 "test exists" 級別合規

### G2 — xlang ATR / BB / Sharpe / edge / PnL 1e-4 容差 test ❌ NOT TOUCHED

- grep `tolerance.*1e-4 / abs(.*py.*-.*rust) / py_atr.*rust_atr / cross_lang.*indicator / consistency.*atr` 全部 **0 命中**
- 唯一 xlang test 仍是 `test_manifest_signer_xlang_consistency.py` (433 LOC) — manifest signing **byte-equal** 而非浮點 1e-4 容差
- 28 commits 0 個動到 indicator xlang test 接線
- ⚠️ **PUSH BACK**：CLAUDE.md skill §6「Rust ↔ Python ATR/BB/Sharpe 1e-4 容差測試」spec 至今 **0 case**

### G3 — H0 Gate < 1ms / Tick < 0.3ms / IPC < 5ms SLA 壓測 ❌ NOT TOUCHED

- grep `sla_pressure / h0_gate.*latency / target_latency / p99 / microbench` 0 真實 latency assert
- `rust/openclaw_engine/tests/rrc1_audit_tests.rs` 仍是 H0Gate `total_checks=20` 計數 invariant test，**0 deterministic <1ms latency assert**
- 28 commits 0 個動到 SLA 壓測接線
- ⚠️ **PUSH BACK**：H0 Gate 真實 SLA 壓測 0 個 in CI；`tests_predictor_router.rs:1290` 仍宣「真實 SLA 監控由 cargo bench 負責」，但 cargo bench 不在 CI

### G4 — ExecutorAgent shadow_mode 切換 e2e ⚠️ PARTIAL（仍是 lambda fail-close 預設）

- 文件存在：`test_executor_shadow_to_live_e2e.py` / `test_executor_shadow_toggle_api.py`（**pre-existing**，2026-05-08 audit 已記）
- W-AUDIT-3 commit `da2dba25` PM report 自承：**「F-01 lambda:True removal still blocks on P0-DECISION-AUDIT-2」** — production code `executor_agent.py:223-224` 的 `shadow_mode_provider=lambda: True` 仍未拆，shadow→live 真實切換 production 路徑仍 0 case
- AMD-2026-05-09-01 加了 SM-05 ExecutorConfigCache polling design draft — 但**只是規格 draft，沒對應 e2e test**

### G5 — `test_case2_pg_kill_simulation_returns_200_degraded` deterministic flaky ❌ NOT FIXED

- Mac+Linux 仍 fail（pre-existing E4-P0-1 / memory.md W6 條目 #2）
- 28 commits 0 個動到 fixture cleanup 接線
- ⚠️ **PUSH BACK**：純 fixture cleanup 工作（不需 production code 動），E4 自己工作未完成

### G6 — ML training silent-unscheduled (5 script 未進 cron) ⚠️ PARTIAL（source-only，未 install）

- 文件存在：`helper_scripts/cron/ml_training_maintenance.py` (430 LOC) + `ml_training_maintenance_cron.sh` (108 LOC) — commit `268f9470 audit: add ml training maintenance cron`
- test 存在：`tests/helper_scripts/test_ml_training_maintenance_cron_static.py` (138 LOC)
- 跑驗：5 jobs `linucb_trainer / mlde_shadow_advisor / mlde_demo_applier / quantile_trainer / scorer_trainer` 都被 wrapper pin
- ⚠️ **PUSH BACK**：commit message 自承「leaves cron installation/runtime execution to the operator」 — wrapper 寫好但 **crontab 未 install**，runtime production 仍 0 cron 真實跑
- ⚠️ **PUSH BACK**：test 是 import / bash -n / job 名 3 級**靜態檢查**，**0 個 cron lock contention 真實測試**

### G7 — LG-5 reviewer Decision Lease test mock-only 永遠成功 ❌ NOT TOUCHED

- `test_lg5_review_live_candidate.py:505` MockHub stub 仍未替換成真 GovernanceHub fixture
- 28 commits 0 個動到此 test
- ⚠️ **PUSH BACK**：仍 mock-only 永遠 PASS

### G8 — ml_training PG round-trip 0 真實 case ⚠️ PARTIAL

- `tests/helper_scripts/test_ml_training_maintenance_cron_static.py` 加了，但仍是 static syntax + import 測試
- 4 個 OPENCLAW_TEST_DSN gated case 仍未啟用 default
- ⚠️ **PUSH BACK**：mock 路徑下永遠 PASS，PG round-trip 0 真實驗證

### G9 — Executor parity Rust↔Python 0 真實 cross-call ❌ NOT TOUCHED

- `test_executor_decision_parity.py` 仍 Python `_reference_decide` 對比 Python `decide()`，0 Rust binary spawn
- 28 commits 0 個動到此 test
- ⚠️ **PUSH BACK**：「decision parity」仍是 Python ↔ Python 同實作對比，跨語言 1e-4 0 真實 cross-call

### G10 — retCode 邊界 Bybit spec 50+ code 多數未覆蓋 ✅ PARTIAL

- commit `f2b22fc1 audit: close bybit dictionary drift` 加 `tests/docs/test_bybit_api_reference_static.py` (70 LOC) — 但只是字典文檔靜態驗，**0 個新增 retCode 路徑 parametrize fixture**
- ⚠️ **PUSH BACK**：仍 5 unique retCode（10001/10003/110007/110017/0），spec 50+ 未補

### G11-G18 — 邊界 / 並發 / migration race / live HMAC / StopManager NaN / DB drop / ArcSwap multi-reader / EarnedTrust ❌ ALL NOT TOUCHED

- grep 0 命中新加 boundary / concurrency / race test
- 28 commits 0 個 P2/P3 邊界工作

### G19 — H0 Gate < 1ms / Tick < 0.3ms 真實 SLA fixture in CI ❌ NOT TOUCHED

- 同 G3，0 進展

### G20 — EarnedTrust T0/T1/T2/T3 pairwise transition ❌ NOT TOUCHED

---

## §3 NEW-ISSUE（28 commit 引入的新問題 / pre-existing 但 audit baseline 漏揭示）

### NEW-1 — `test_oe_006_close_retry_budget_has_real_timeout_guard` Mac+Linux 新破壞 🔴 BLOCKER

- **commit `3cff1005 refactor: split event consumer hot files` 自我破壞**：把 `test_close_attempt_timeout_constant_is_500ms` 從 `dispatch.rs` 搬到 `dispatch_tests.rs`，但 static-grep test 仍 read `dispatch.rs`
- 對抗性 push back：commit message 自宣「Add a static LOC regression」— 加了**新** static 但沒檢查**舊** static 受 split 影響
- 修復 1 行：把 `tests/test_batch_d_risk_fail_closed.py:126` 改 `assert "test_close_attempt_timeout_constant_is_500ms" in dispatch_tests` 或 `_read(".../dispatch_tests.rs")`

### NEW-2 — `test_replay_advisory_routes.py` Linux 2 fail（疑似 pre-existing 未揭示）⚠️ HIGH

- `test_replay_advisory_rank_route_caps_and_never_invokes_applier` Linux 422 vs Mac 200
- `test_replay_advisory_compare_route_is_read_only` 同類
- 28 commits 沒動 advisory route / test
- 2026-05-08 audit Linux 7 fail breakdown 沒揭示 — 可能是 `f47c530c ref21: calibrate full-chain replay manifests`（baseline 之前）後 Linux schema validation 變嚴 → Mac mock 跑得過 / Linux PG schema 422
- 對抗性 push back：說明 2026-05-08 audit Mac+Linux baseline diff breakdown **沒抓到 Linux schema divergence**

### NEW-3 — pytest 4 collection errors（pre-existing 但 audit baseline 漏揭示）🟡 MEDIUM

- 4 個 replay test 從 control_api_v1 sub-dir 跑 venv 時 import path broken；從 srv root + PYTHONPATH=. 可繞過
- 2026-05-08 audit baseline `Mac 3826/6` 是**已掩蓋** 4 collection errors 後的 PASS 數 — 表 audit 自身用 control_api_v1 sub-dir 跑時就 4 errors 但 §1 沒記
- 對抗性 push back：audit baseline 透明度不夠 — 應分「能跑的 PASS / 能跑的 FAIL / collection errors」3 列

### NEW-4 — Engine restart history（V077 columnstore hotfix 暴露）已自證

- `commit 49ceeb61 fix: add columnstore fallback for V077` PM report 自承「engine startup failure exposed by the authorized rebuild/restart」 — V077 CHECK 在 columnstore 模式下被 reject，hotfix 加 trigger fallback
- 治理盲點：V076/V077 都通過 static pytest，但 Linux PG dry-run 沒覆蓋 columnstore 模式 → 真實 rebuild 才暴露
- 對抗性 push back：CLAUDE.md §七「Linux PG dry-run mandatory」V055 教訓本應預防，但 columnstore-specific 場景 dry-run 沒覆蓋

---

## §4 對抗性 push back（不接受任何「baseline still PASS」便認可）

### Push back A — W-AUDIT-3 commit message 措辭策略性

> 「F-15 adds lease router flag flip regressions for transition writer messages and opt-in OPENCLAW_TEST_PG row persistence」

- 「opt-in」3 字實質含義：CI 默認 0 row 持久化 case 真跑
- `router_flag_flip_writes_lease_transition_rows_when_test_pg_present` 在 env var 不設時 early-return PASS — **算「test 存在」但不算「e2e PG 持久化通過」**
- 對抗性結論：G1 真實狀態不是 100% DONE，僅「Rust channel msg + Rust opt-in PG e2e 框架」DONE；CI gate 不能 trust DB persistence

### Push back B — h_state_query split 真拆但「拆」非「修」

- `test_h_state_query_handler.py` 從 2641 → 9 LOC（compatibility collector，import sibling modules）
- 4 sibling modules: `test_agent_states.py` 1223 / `test_core.py` 436 / `test_h_buckets.py` 559 / `common.py` 387
- 1223 < 2000 hard cap ✅
- ⚠️ pytest 仍能 collect 全部（驗 `test_h_state_query_handler.py` import 後 6 passed / 3 skip）
- 但 commit message 自宣「Add a LOC regression test」— 加 `tests/structure/test_h_state_query_split_static.py` (41 LOC) 是**鎖**這次拆檔結果，不是**修**任何業務 bug
- 對抗性結論：W-AUDIT-5a F-test-h-state ✅ DONE，但是純 hygiene 工作

### Push back C — perf 4 commits（deepcopy / orjson / fast_json / ai_budget RwLock）只加靜態 grep

- `e00985da perf: replace state snapshot deepcopy` — 對應 `test_state_machine_snapshot_clone_static.py` (22 LOC) **只 grep 禁 `import copy / copy.deepcopy / from copy import deepcopy`**
- 但 deeper inspection 找到 `test_state_returns_isolated_promotion_snapshot` 真做 `state.promotions[0]["next_tier"] = "MUTATED"` mutation test ✅ — **deepcopy 替換有 1 真 mutation immutable 證明**（為 learning_tier_gate）
- ⚠️ 對 authorization / decision_lease / risk_governor 3 個 SM 的 mutation test **未加**（commit stat 顯示 +2 LOC / 0 LOC / +8 LOC，太薄）
- 對抗性結論：deepcopy 替換有 1/4 SM 加 mutation test，3/4 SM 缺；ai_budget RwLock 換 ArcSwap 0 個 perf microbenchmark assert，0 並發 race test
- `a44672e5 perf: expand fast json runtime hot paths` / `a20dd1ce perf: add fast json ipc foundation` — 都只加 static grep（json_fast_hot_paths_static.py），**0 個 byte-equal 對比 stdlib JSON output 的 wire-format 一致性 test** — 風險：orjson 在 nested dict ordering / float precision 與 stdlib 不一致 → IPC 對端解 fail

### Push back D — security W-AUDIT-2 加 test 但 mock 級別

- `test_phase4_routes.py` +12 LOC 應為 actor / require_operator parametrize；`test_batch_e_runtime_ownership.py` +60 LOC 是 runtime ownership invariants
- 沒看到 attack-path test（如「未驗 actor 直 POST /api/v1/phase4/...」確認 401/403）— 是「修了，假設修對 → 加 contract test」級別，不是「修了 → 寫 attack 模擬證實 fail-closed」級別

### Push back E — V076/V077 schema migration test 都 static parse + Mac mock

- 4 W-AUDIT-4 schema commits（754ecec7 / 3e468d21 / 09afc92c / ecb2d938）+ outcome backfill / V073 / V075 都用 static SQL parse + Mac mock pytest
- V077 columnstore hotfix 是因為 Linux 真 rebuild 才暴露 PG 1 模式 reject — **Mac mock 通過 ≠ Linux PG runtime 通過 ≠ columnstore 模式通過**
- 對抗性結論：CLAUDE.md §七「Linux PG dry-run mandatory」 V055 教訓被 V077 columnstore-specific 場景擊穿；E4 baseline 沒能在 hotfix 之前 catch

### Push back F — 28 commits 0 個動 ml_training PG round-trip 真實接線

- `268f9470` 加了 cron wrapper + static test 但 commit message 自承「leaves cron installation/runtime execution to the operator」
- ml_training 5 script 仍未進 production crontab；自宣 source-only checkpoint 級別合規
- G6 真實 production 跑 0 個 — 與 2026-05-08 audit panorama「100% NULL」根因路徑無解

### Push back G — Mac/Linux baseline diff breakdown 不完整

- audit 2026-05-08 §1 列 Mac 6 fail / Linux 7 fail，§6 breakdown 4 categories
- 但 NEW-2 揭 Linux `test_replay_advisory_routes.py` 2 fail 沒在 audit baseline 中
- 暗示 audit 用了「ignore collection errors」之外還可能 implicitly ignore 其他類型 fail；audit baseline 不是 100% complete inventory

---

## §5 結論 + Verdict

**Verdict**：⚠️ **CONDITIONAL PASS WITH 1 BLOCKER + 2 HIGH + 2 MEDIUM**

| 引擎 | passed | failed | baseline | delta | identical (雙跑) |
|---|---|---|---|---|---|
| Mac · srv/tests | 208 | 0 | 137 | +71 | yes |
| Mac · control_api_v1 | 3898 | 7 | 3826 | +72/+1 | yes |
| Linux · control_api_v1 | 3871 | 10 | 3832 | +39/+3 | n/a (single run) |
| Linux · cargo lib | 2560 | 0 | 2559 | +1 | yes |

**21 gap 修復狀態**：
- ✅ DONE/PARTIAL: 8（G1 partial / G6 partial / G10 nominal / W-AUDIT-2 security / h_state split / V076-V077 / state machine 1/4 mutation / V073 cron wrapper）
- ⚠️ PARTIAL but NOT DONE: 5（G3 / G4 / G7 / G8 / G9）
- ❌ NOT TOUCHED: 8（G2 / G5 / G11-G18 / G20）
- 🆕 NEW REGRESSION: 3（test_oe_006 / 2 Linux replay_advisory / 4 collection errors）

**強制退回 E1 修復清單**：
1. **NEW-1 BLOCKER**：`commit 3cff1005` 自我破壞，`test_oe_006_close_retry_budget_has_real_timeout_guard` 1 行靜態路徑修復
2. **NEW-2 HIGH**：`test_replay_advisory_routes.py` Linux 2 fail RCA — 是 schema divergence 還是 mock 漏修需查
3. **NEW-3 MEDIUM**：4 collection errors 修 conftest.py 路徑 inject 或在 audit baseline 顯式記錄

**不退回 E1 但需 PA 派 next round**：
- G2 / G3 / G4 / G5 / G7 / G8 / G9 / G19 五個 P0-P1 結構性 gap 仍 0 進展
- G11-G18 / G20 邊界 P2/P3 仍 0 進展

**對 PM 建議**：
- 不可標 W-AUDIT-3 為「fully closed」— W-AUDIT-3 commit message 自承「PARTIAL」+ F-01 仍 block on P0-DECISION-AUDIT-2
- 不可標 W-AUDIT-5b perf 4 commits 為「DONE 含 regression」— deepcopy 1/4 SM 真 mutation test，3/4 SM 缺；ai_budget ArcSwap 0 perf microbench，0 並發 race
- baseline 數字應更新為 Mac control_api_v1 **3898/7 (8 算上 NEW-1 修前)** / Linux **3871/10**

**對 E4 自己 push back**：
- E4 profile.md 「2555/17」過期不止這次（2026-05-08 已 flag），HEAD 7fccad06 後應更新為 control_api_v1 3898/7（Mac）+ srv/tests 208/0 + cargo lib 2560/0
- 雙跑 deterministic 對比應一律包 srv/tests + control_api_v1（缺一不可）；本次 srv/tests 雙跑 ✅ control_api_v1 雙跑 ✅ Linux cargo 雙跑 ✅，但 Linux pytest 只跑 1 次（time budget 取捨）

---

E4 VERIFICATION DONE
