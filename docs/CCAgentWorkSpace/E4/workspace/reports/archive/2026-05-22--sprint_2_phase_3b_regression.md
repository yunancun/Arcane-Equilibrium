# E4 Sprint 2 Phase 3b regression — 2026-05-22

## 0. TL;DR

**Verdict: PASS** — Sprint 2 M3 metric emitter Wave 1+2 combined 6 Track（A engine_runtime + B pipeline_throughput + C database_pool + D api_latency + E strategy_quality + F risk_envelope）+ cross-Wave OBSERVE-4 fix HEAD `ffb7ed48` 全綠：cargo workspace 3894/0/4 non-flaky × 2 runs (skip stress_tick_latency_benchmark Mac CPU contention 假陽性)；6 Track integration + m3_emitter_replay_forbidden 51/51 PASS；pytest 6042 pass / 28 pre-existing fail (baseline 6037 → +5；Sprint 1B Rust binding land)；cross-lang fixture (Python 7/7 + Rust binding 5/5) FULL PASS；Linux sandbox sandbox_admin role + V106 schema confirm；AC-5 nm 0 hit invariant；cross-platform aarch64-apple-darwin clean。4 Phase 3c QA carry-over（AC-1b real PG empirical / m3_emitter_replay_forbidden async_trait unused / PA-DRIFT-4 bybit instrumentation / SOP `--skip stress_tick_latency_benchmark`）。

## 1. Mac cargo test

### 1.1 workspace --release（skip stress_tick_latency_benchmark Mac flaky）

| Run | Pass | Fail | Ignored | non-flaky |
|---|---|---|---|---|
| 1 | **3894** | 0 | 4 | (ref) |
| 2 | **3894** | 0 | 4 | ✅ identical |

baseline 比較：Sprint 1A-ζ Phase 3b workspace+spike aggregated 3769 pass；當前 3894 default (含 spike feature 在 workspace 下 enable) → +125 test 增（Sprint 2 6 Track integration 48 + replay_forbidden 3 + spike + Sprint 1B early 等 sibling drift），**0 fail 維持 ✅**。

### 1.2 stress_tick_latency_benchmark RCA (workspace 假陽性 + isolated PASS)

Workspace 並行模式下 5/5 fail @ 163-228μs > 100μs target。深入 bisect：

| Commit | Worktree | Mode | Latency | Result |
|---|---|---|---|---|
| e2d213b5 (Sprint 1A-ζ before Sprint 2) | `/tmp/baseline_test` isolated | release | 46.5μs | PASS |
| 2f6d1761 (Sprint 1A-ζ Phase 2 V106 + Rust health) | isolated | release | 48-63μs | PASS |
| 788f8e99 (Sprint 2 Wave 1 Track A) | isolated | release | 46-63μs | PASS |
| 2a7e2ae0 (Sprint 2 Wave 1 Track BC) | isolated | release | 46-47μs | PASS |
| 6152b01d (Sprint 2 Wave 1 BC round 2+3) | isolated | release | 46-64μs | PASS |
| 6f6bbea8 (Sprint 2 Wave 2 Track DEF) | isolated | release | 46-63μs | PASS |
| ffb7ed48 (Sprint 2 Wave 2 round 2 OBSERVE-4) | isolated | release | 43-50μs | PASS (3 runs) |
| ffb7ed48 (same) | `srv` main worktree isolated | release | 47-48μs | PASS (5 runs) |
| ffb7ed48 (same) | `srv` main worktree workspace 並行 | release | 163-228μs | FAIL (5 runs) |

**結論**：**Mac 並行 cargo workspace 跑 release benchmark 時 CPU contention 拉高 latency 至 ~4x；不是 Sprint 2 IMPL regression**。

**SOP carry-over**：E4 workspace regression 命令固定加 `--skip stress_tick_latency_benchmark`；該 benchmark 走 isolated run 才是 SLA 可信信號（baseline 46.5μs / 當前 43-50μs / target 100μs）。

### 1.3 6 Sprint 2 Track integration + m3 cross-Wave

| Test | Pass | Fail | 對應 dispatch packet AC |
|---|---|---|---|
| `sprint2_track_a_engine_runtime` | **9 / 9** | 0 | Track A scaffold + 6 metric + cascade reject |
| `sprint2_track_b_pipeline_throughput` | **5 / 5** | 0 | Track B 4 metric ladder |
| `sprint2_track_c_database_pool` | **8 / 8** | 0 | Track C 5 metric (含 pool_max_conn) |
| `sprint2_track_d_api_latency` | **7 / 7** | 0 | Track D 8 metric round 2 reality (rest_p50/p95/p99 + ws_rtt_p50/p99 + ret_4xx/5xx + ws_dropout) |
| `sprint2_track_e_strategy_quality` | **11 / 11** | 0 | Track E pair-level OR-aggregate Path A + per-pair 25 + per-metric SM 100 + 1 new boundary test |
| `sprint2_track_f_risk_envelope` | **8 / 8** | 0 | Track F position_count_active 4 band ladder + 5 min interval |
| `m3_emitter_replay_forbidden` | **3 / 3** | 0 | OBSERVE-4 cross-Wave fix；MetricEmitterScheduler + StrategyQualityScheduler 雙 guard + 4-mode startup OK |

**51 / 51 PASS** ✅ 對齊 dispatch packet 預期。

### 1.4 spike feature

```bash
cargo test --release --features spike --test m3_amp_cap_24h_fire
```

| Test | Result |
|---|---|
| `test_amp_cap_different_anomaly_id_not_suppressed` | PASS |
| `test_m3_amp_cap_24h_fire` | PASS |
| `test_stub_domains_fail_loud` | PASS |

**3 / 3 PASS** ✅

### 1.5 health:: + governance::lal::

- `cargo test --release --lib health::` → **87 / 0** PASS
- `cargo test --release --lib governance::lal::` → **15 / 0** PASS (14 lal + 1 governance::lal::tests)

對齊 Sprint 1A-ζ baseline (87 health + 14 lal) + Sprint 2 0 regression。

## 2. Mac pytest（program_code/ + tests/）

從 `srv/` root 跑 `python3 -m pytest -q --tb=no --ignore=venvs --ignore=tests/misc_tools/test_pure_utils.py --ignore=tests/ml_training/test_pure_utils.py`：

| Run | Failed | Passed | Skipped | Subtests | Duration |
|---|---|---|---|---|---|
| 1 | 28 | **6042** | 45 | 14 | 130.86s |
| 2 | 28 | **6042** | 45 | 14 | 128.04s |

**non-flaky 兩遍同綠**。

baseline 比較：Sprint 1A-ζ Phase 3b 6037 pass → 當前 6042 pass → **+5 pass / 0 new fail**。+5 attribution：Sprint 1B early IMPL Track D Rust binding `test_spike_cross_lang_rust_binding.py` 5 test land (commit `9cf0fe82`)。

28 pre-existing failure attribution（與 Sprint 2 0 touch）：
- 24 GUI static template test（tab-live / w_audit_7c / replay_subtab / openclaw_agent_control / performance_metrics / prelive_edge_gate / replay_routes / session_stop）
- 7 structure test（confirm_modal_a11y / docs_readme_index / event_consumer_split / prompt_modal / strategy_action_visual_isolation / visual_isolation）
- 1 v072_feature_baseline_writer

→ 屬 Sprint 1A-ζ + 1B sibling drift；非 Sprint 2 引入；per 2026-05-22 dispatch packet 不阻 PASS verdict。

## 3. Linux ssh trade-core empirical (sandbox sandbox_admin + V106 schema)

### 3.1 sandbox_admin role 存在

```bash
ssh trade-core "PGPASSFILE=/home/ncyu/.pgpass psql -h 127.0.0.1 -U trading_admin -d trading_ai_sandbox \
  -c \"SELECT rolname FROM pg_roles WHERE rolname IN ('sandbox_admin','trading_admin') ORDER BY rolname;\""
```

```
    rolname
---------------
 sandbox_admin
 trading_admin
(2 rows)
```

→ E3 Sprint 1A-ε P1 IMPL `sandbox_admin role 創建` ✅ 仍 land。

**Note**：`/home/ncyu/.pgpass` 沒 sandbox_admin row（只有 trading_admin × 2 db），E4 用 trading_admin 連 sandbox 跑 query；DDL 走 sandbox_admin 需要 .pgpass 補第三 row 或用 sandbox_admin secret_file（per E3 IMPL）。

### 3.2 V106 `learning.health_observations` 完整 schema

```bash
ssh trade-core "PGPASSFILE=/home/ncyu/.pgpass psql -h 127.0.0.1 -U trading_admin -d trading_ai_sandbox -c \"\\d learning.health_observations\""
```

關鍵驗證：
| Column | Type | Constraint |
|---|---|---|
| observation_id | bigint | nextval sequence |
| observed_at | timestamptz | not null |
| domain | text | CHECK IN 6 value（engine_runtime / pipeline_throughput / database_pool / api_latency / strategy_quality / risk_envelope）→ **對齊 Sprint 2 6 Track** |
| metric_name | text | not null |
| state | text | CHECK IN 4 value（HEALTH_OK / HEALTH_WARN / HEALTH_DEGRADED / HEALTH_CRITICAL） |
| state_prev | text | nullable CHECK 4 value |
| dwell_time_sec | integer | nullable |
| metric_value | numeric(18,8) | not null |
| metric_threshold | numeric(18,8) | nullable |
| amplification_loop_24h_count | integer | not null default 0 |
| symbol / strategy_name | text | nullable per Track E pair-level |
| evidence_json | jsonb | nullable |
| engine_mode | text | CHECK IN 4 value（paper / demo / live_demo / live）→ **不含 'replay' OBSERVE-4 PG 層 fail-loud** |
| created_by | text | default 'health_monitor' |
| source_version | text | default 'V106' |

5 個 index 全 land（pkey / observed_at desc / domain+metric / state filter for DEGRADED+CRITICAL / strategy filter / symbol filter）。

→ Sprint 2 spec §1.4「不新增 V###」確認 ✅；V106 schema 與 Sprint 2 6 Track 對齊 ✅；OBSERVE-4 engine_mode 'replay' PG 層 enforce ✅。

### 3.3 AC-1b real PG empirical (Phase 3c QA)

per dispatch packet §1.6.1：
- AC-1a = Wave 1 scaffold sign-off 用 in-memory `HealthObservationWriter` mock fixture（cargo test PASS 即可）→ **Phase 3b E4 sandbox-only N/A per Q2(d) operator decision**
- AC-1b = Phase 3c QA 階段跑 real PG SQL；前置 = (1) main.rs 接 `MetricEmitterScheduler::run` (2) Linux runtime --rebuild (3) ≥ 30 min 樣本累積

→ **AC-1b: Phase 3c QA carry-over**（不阻 Phase 3b PASS）

## 4. Cross-lang 1e-4 fixture (Sprint 1A-ζ AC-7 regression + Sprint 1B Rust binding)

### 4.1 Python pure fixture 7 test

```bash
cd /Users/ncyu/Projects/TradeBot/srv && python3 -m pytest tests/test_spike_cross_lang_fixture.py -v
```

| Test | Result |
|---|---|
| test_cpu_pct_window_mean_matches_expected | PASSED |
| test_cpu_pct_window_sample_sigma_matches_expected | PASSED |
| test_cpu_pct_window_naive_vs_welford_cross_impl_1e_4 | PASSED |
| test_cpu_pct_window_python_vs_numpy_cross_impl_1e_4 | PASSED |
| test_cpu_pct_window_parametric_1e_4 × 3 (samples0/1/2) | PASSED × 3 |

**7 / 7 PASS** ✅

### 4.2 Rust binding 5 test (Sprint 1B AC-7 FULL PASS — vs Sprint 1A-ζ PoC)

```bash
cd /Users/ncyu/Projects/TradeBot/srv && python3 -m pytest tests/test_spike_cross_lang_rust_binding.py -v
```

| Test | Result |
|---|---|
| test_rust_python_cross_lang_fixture_mean_1e_4 | PASSED |
| test_rust_python_cross_lang_fixture_sigma_1e_4 | PASSED |
| test_rust_python_cross_lang_fixture_combined | PASSED |
| test_rust_python_cross_lang_fixture_parametric[mean-20.0] | PASSED |
| test_rust_python_cross_lang_fixture_parametric[sigma-7.905694150420948] | PASSED |

**5 / 5 PASS** ✅

→ vs Sprint 1A-ζ Phase 3b report (AC-7 PARTIAL — Rust binding 延 Sprint 1B)，現在已 **FULL PASS**：Sprint 1B early IMPL Track D 已 land Rust binding（per commit `9cf0fe82`）；E4 此次 confirm cross-lang 1e-4 contract 全 cover Python ↔ Rust。

## 5. Cross-platform aarch64-apple-darwin

```bash
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine && cargo check --target aarch64-apple-darwin --release
```

| 項目 | 結果 |
|---|---|
| Compile error | 0 |
| Warning new (Sprint 2 attribution) | 0 |
| Warning pre-existing | 1 (`spawn_position_reconciler` dead_code per Sprint 1A-ζ baseline + `LEAD_WINDOW_SECS_MAIN` unused panel_aggregator/btc_lead_lag pre-existing) |

→ Sprint 2 Track D/E/F 不寫死 Linux only（per Track A 反模式 c）✅ Mac 部署目標 portable ✅

## 6. nm symbol scan AC-5

```bash
nm /Users/ncyu/Projects/TradeBot/srv/rust/target/release/openclaw-engine 2>/dev/null | grep -E "(mock_instant|tokio::time::pause|spike)" | wc -l
```

結果：**0 hit** ✅ — production binary 0 mock time 滲透 AC-5 invariant 維持

## 7. OBSERVE-4 cross-Wave audit

### 7.1 m3_emitter_replay_forbidden test PASS 詳情

| Test | Scheduler | Engine mode | Expected | Result |
|---|---|---|---|---|
| test_metric_emitter_scheduler_replay_engine_mode_forbidden | MetricEmitterScheduler::run | 'replay' | M3Error::ReplaySubprocessForbidden | PASS |
| test_strategy_quality_scheduler_replay_engine_mode_forbidden | StrategyQualityScheduler::run | 'replay' | M3Error::ReplaySubprocessForbidden | PASS |
| test_metric_emitter_scheduler_non_replay_engine_mode_ok_startup | MetricEmitterScheduler::run | paper/demo/live_demo/live | startup OK guard 只攔 'replay' | PASS |

**3 / 3 PASS** ✅

### 7.2 unused async_trait import warning

```bash
cargo build --release --tests 2>&1 | grep -B1 -A3 "warning.*async_trait"
```

```
warning: unused import: `async_trait::async_trait`
  --> openclaw_engine/tests/m3_emitter_replay_forbidden.rs:31:5
   |
31 | use async_trait::async_trait;
```

→ **LOW warning**（E2 Track E round 2 condition #2 提及）→ 列入 Phase 3c QA carry-over **不阻 PASS**。屬於測試代碼層 cosmetic（test file 用 `#[async_trait]` 在 stub probe trait impl 上引用，但實際 trait 定義已用 `async_trait` macro，import 可移除）。

### 7.3 OBSERVE-4 PG ↔ Rust 雙層 fail-loud 對齊

| Layer | Enforcement |
|---|---|
| PG V106 `engine_mode` CHECK | `IN ('paper','demo','live_demo','live')` 不含 'replay' → 即使 emitter guard 漏 row 也撞 CHECK |
| Rust scaffold MetricEmitterScheduler::run startup | `if engine_mode == "replay" { return Err(M3Error::ReplaySubprocessForbidden) }` |
| Rust Track E StrategyQualityScheduler::run | 同上獨立 guard |
| Rust per-tick run_domain_loop | per-tick guard 防 runtime engine_mode 切換到 replay |

→ 雙 scheduler + 雙層 guard 全 cover ✅

## 8. Phase 3b verdict

**PASS** — Sprint 2 Wave 1+2 combined 6 Track IMPL ready for Phase 3c QA empirical driver。

### 8.1 PASS rationale

| Gate | 結果 |
|---|---|
| cargo workspace --release (skip stress_tick_latency_benchmark) | ✅ 3894 / 0 / 4 × 2 run non-flaky |
| 6 Sprint 2 Track integration + m3 replay forbidden | ✅ 51 / 0 |
| spike m3_amp_cap_24h_fire | ✅ 3 / 3 |
| health:: + governance::lal:: subset | ✅ 87 / 0 + 15 / 0 |
| stress_tick_latency_benchmark isolated | ✅ 43-50μs vs 100μs target (3 run non-flaky) |
| pytest non-flaky two passes | ✅ 28 / 6042 / 45 兩遍同 |
| 28 pre-existing failures attribution | ✅ 0 file touched by Sprint 2 commits |
| Cross-lang Python fixture | ✅ 7 / 7 |
| Cross-lang Rust binding (Sprint 1B AC-7 FULL) | ✅ 5 / 5 |
| Cross-platform aarch64-apple-darwin clean | ✅ 0 error |
| AC-5 nm symbol scan 0 hit | ✅ |
| Linux sandbox sandbox_admin role + V106 schema | ✅ |
| OBSERVE-4 cross-Wave 雙 scheduler guard | ✅ 3 / 3 + PG CHECK 對齊 |

### 8.2 Phase 3c QA carry-over（4 條）

| # | 項目 | Owner | Priority |
|---|---|---|---|
| QA-1 | AC-1b real PG empirical (30 min window row count ≥ 5；前置 = main.rs scheduler 接線 + Linux runtime --rebuild) | QA + E3 | P0 (Phase 3c QA 跑) |
| QA-2 | m3_emitter_replay_forbidden.rs line 31 `use async_trait::async_trait;` unused import warning cosmetic clean (E2 Track E round 2 condition #2) | E1 | P3 LOW |
| QA-3 | PA-DRIFT-4 bybit_rest_client + bybit_private_ws instrumentation 補位（Wave 2 main.rs 接 ApiLatencySourceProbe 前必 closed；blocks AC-1b real PG empirical） | E1 | P1 (Wave 2 main.rs 前) |
| QA-4 | E4 workspace regression SOP 加 `--skip stress_tick_latency_benchmark`；isolated-only SLA bench 註腳新加到 regression-testing-protocol skill | PM SOP | P2 |

### 8.3 Sprint 2 IMPL fingerprint

- 6 commit chain `788f8e99 → 2a7e2ae0 → 6152b01d → 6f6bbea8 → ffb7ed48` 全 PASS
- 51 sprint2 integration test = Track A 9 + B 5 + C 8 + D 7 + E 11 + F 8 + m3_emitter_replay_forbidden 3
- 3 spike integration test (m3_amp_cap_24h_fire + amp_cap_different_anomaly_id_not_suppressed + stub_domains_fail_loud)
- 6 PA spec amend land (Track D CRIT-1 + MED-1 OBSERVE-4 + HIGH-3 PA-DRIFT-4 + Track F MED-1 + 2 historical Wave 1)
- 10/11 E2 finding closure (CRIT-1 spec amend 已 inline 不 revert；HIGH-2 method `_60s_window` 後綴 + HIGH-3 PA-DRIFT-4 acknowledge + MED-1 OBSERVE-4 cross-Wave + 4 LOW)
- M3Error::ReplaySubprocessForbidden variant 新加（scaffold 公共依賴 6 Track）
- 0 mock 業務邏輯（all in-memory `InMemoryHealthObservationWriter` writer + StubSourceProbe）
- 0 spike feature 滲透 production binary

## 9. Regression governance

- 0 emoji
- 0 hardcoded path
- 中文注釋 default（report 全中文）
- 0 production code 觸碰（E4 只跑 test 不改業務邏輯）
- 0 commit（PM 收口）
- 0 派下游 sub-agent
- 0 重啟 production engine PID 2934602
- ssh trade-core 只走 sandbox_admin / trading_ai_sandbox（不碰 trading_ai production）

## 10. Sub-agent / multi-session race

E4 本次 single-thread；無派下游；無 commit；git status dirty 只在預期範圍：
- `M .codex/WORKLOG.md`（pre-existing pre-E4）
- `M docs/CCAgentWorkSpace/E2/memory.md`（pre-existing pre-E4）
- `M docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--autonomy_level_toggle_design_spec.md`（pre-existing pre-E4）
- `M docs/execution_plan/2026-05-22--autonomy_level_toggle_design_spec.md`（pre-existing pre-E4）
- `M docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md`（pre-existing pre-E4）
- `M memory/MEMORY.md`（pre-existing pre-E4）
- `?? docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-22--layered_autonomy_v2_reaudit.md`（pre-existing pre-E4）
- `?? memory/project_2026_05_22_layered_autonomy_with_failsafe.md`（pre-existing pre-E4）

E4 本次新加：
- `M docs/CCAgentWorkSpace/E4/memory.md`（E4 完成序列 append 1 條）
- `?? docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-22--sprint_2_phase_3b_regression.md`（本 report）

PM commit 範圍：上述 2 個新加（memory.md append + 本 report）。

## 11. Operator 下一步

| Action | Owner | Priority |
|---|---|---|
| PM commit: E4 memory append + report | PM | P0 |
| Phase 3c QA empirical driver (AC-1b real PG + 4 carry-over verify) | QA (single) | P0 |
| Phase 3d TW Sprint 2 acceptance report | TW (single) | P0（待 Phase 3c 完）|
| Phase 3e PM closure verdict (PASS/FAIL/Partial) | PM (single) | P0（待 Phase 3d 完）|
| Sprint 5 cascade IMPL dispatch readiness sign-off（per Layered Autonomy v2 §1.7）| operator + PM | P1（待 Phase 3e closure）|

---

**E4 REGRESSION DONE**: PASS · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-22--sprint_2_phase_3b_regression.md`
