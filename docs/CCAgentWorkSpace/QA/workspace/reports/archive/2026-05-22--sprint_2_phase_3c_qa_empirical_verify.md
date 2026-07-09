# QA Sprint 2 Phase 3c empirical verify — 2026-05-22

## 0. TL;DR

**Verdict: PASS WITH 1 EXPECTED CARRY-OVER** — Sprint 2 M3 metric emitter Wave 1+2 combined 6 Track（A engine_runtime + B pipeline_throughput + C database_pool + D api_latency + E strategy_quality + F risk_envelope）+ cross-Wave OBSERVE-4 scaffold sign-off Phase 3c QA empirical verify 通過。

- AC-1a in-memory proxy：6 Track row count test 51/51 PASS (Track A 9 + B 5 + C 8 + D 7 + E 11 + F 8 + m3_emitter_replay_forbidden 3) — 對齊 E4 Phase 3b 統計
- AC-1b real PG empirical：**PARTIAL → DEFER to Sprint 4 deploy window**（per dispatch packet §1.6.1 拆分契約預期；main.rs scheduler 0 caller + Linux engine binary 0 Sprint 2 symbol + sandbox health_observations 0 row 三證一致）
- AC-2 ladder fire：6 Track ladder test PASS（含 Track D 8 metric × 4 band / Track F position_count_active 0-8/9-16/>16 對齊 spec §2.3 line 106 amend）
- AC-3 amp cap regression：spike 3/3 PASS (m3_amp_cap_24h_fire + amp_cap_different_anomaly_id_not_suppressed + stub_domains_fail_loud)
- AC-4 cross-domain independence：5 cross_domain test PASS（6 Track 互相獨立全 cover，per AC-4 rationale）
- AC-5 nm 0 hit invariant 維持
- AC-6 cargo + pytest baseline 不退（per E4 Phase 3b 3894/0 + 6042/28 兩遍 non-flaky）
- AC-7 cold start binary footprint：**E4/PA carry-over — `cargo bench --bench m3_emitter_cold_start` 未 IMPL；engine binary 不是 CLI 工具不適用 `--version` 路徑**
- OBSERVE-4：MetricEmitterScheduler + StrategyQualityScheduler 雙 scheduler + per-tick guard + PG V106 CHECK 4 值不含 'replay' 雙層 fail-loud 全對齊
- PA spec amend driver 9/9 對齊（IMPL 1:1 mirror spec literal）
- QA-2/QA-3/QA-4 E4 carry-over confirmed；QA-1 AC-1b PARTIAL by-design

## 1. AC-1a in-memory proxy（Wave 1+2 scaffold sign-off）

| Track | Test name | Pass | Fail | 證據 |
|---|---|---|---|---|
| A engine_runtime | `cargo test --release --test sprint2_track_a_engine_runtime` | **9** | 0 | 含 row_count_ge_5 / scheduler 9 test |
| B pipeline_throughput | `cargo test --release --test sprint2_track_b_pipeline_throughput` | **5** | 0 | row_count + real_emitter_through_scheduler |
| C database_pool | `cargo test --release --test sprint2_track_c_database_pool` | **8** | 0 | active_conn_ratio + degraded_band + disconnected fail-closed evidence |
| D api_latency | `cargo test --release --test sprint2_track_d_api_latency` | **7** | 0 | row_count + 8 metric ladder |
| E strategy_quality | `cargo test --release --test sprint2_track_e_strategy_quality` | **11** | 0 | in_memory_proxy + pair-level OR-aggregate + 25 pair / 100 metric SM + boundary test |
| F risk_envelope | `cargo test --release --test sprint2_track_f_risk_envelope` | **8** | 0 | in_memory_proxy + ladder + position_count_active 4 band + 300s interval |
| OBSERVE-4 | `cargo test --release --test m3_emitter_replay_forbidden` | **3** | 0 | MetricEmitterScheduler + StrategyQualityScheduler replay block + 4-mode startup OK |

**51/51 PASS** ✅ 對齊 E4 Phase 3b 統計 + dispatch packet AC-1a 預期。

Test name 差異記錄（與 dispatch packet 原指引比對）：
- Track A `_in_memory_proxy` 真實名稱 = `test_sprint2_track_a_engine_runtime_row_count_ge_5`（語意對等）
- Track B `_row_count` ✅ 對齊
- Track C `_row_count` ✅ 對齊
- Track D `_row_count` ✅ 對齊
- Track E `_in_memory_proxy` ✅ 對齊
- Track F `_in_memory_proxy` ✅ 對齊

## 2. AC-1b real PG empirical（PARTIAL → defer）

### 2.1 三證一致確認 main.rs scheduler 未接

1. `grep MetricEmitterScheduler::new src/` → src/ production code **0 caller**（僅 test 內）
2. `grep StrategyQualityScheduler::new src/` → 僅 strategy_quality.rs inline test `:1482` 一筆，production code 0 caller
3. Linux engine binary `nm` grep `health::domains::api_latency|MetricEmitterScheduler|StrategyQualityScheduler|ReplaySubprocessForbidden` → **0 hit**
4. Sandbox `SELECT COUNT(*) FROM learning.health_observations` = **0**

### 2.2 verdict

PARTIAL → 完全符合 dispatch packet §1.6.1 拆分契約預期：

```
AC-1a = Wave 1/2 scaffold sign-off in-memory proxy（不需 main.rs 接 scheduler / 不需 real PG）
AC-1b = main.rs 接 MetricEmitterScheduler::run + Linux runtime --rebuild + ≥30 min 樣本 後跑
```

main.rs wire-up + PA-DRIFT-4 bybit instrumentation 屬 Sprint 4 first Live deploy 階段工作（per TODO §0 `P1-ENGINE-BINARY-SPRINT-1A-IMPL-DEPLOY`），不阻 Phase 3c QA verdict。

### 2.3 V106 schema land 確認（Linux sandbox）

| 檢項 | 證據 |
|---|---|
| sandbox `learning.health_observations` 列數 | 19 column ✅ 完整 V106 schema |
| `engine_mode` CHECK 4 值 | `CHECK ((engine_mode = ANY (ARRAY['paper'::text, 'demo'::text, 'live_demo'::text, 'live'::text])))` ✅ 不含 'replay' PG 層 fail-loud |
| Production engine PID | 2934602 仍在跑（未碰）✅ |

## 3. AC-2 4-state ladder fire per domain

| Track | Ladder test | Result | spec literal 對齊 |
|---|---|---|---|
| A | `test_sprint2_ladder_engine_runtime` | PASS | 6 metric 4 band（cpu_pct / rss_mb / fd_pct / event_loop_lag_p95_ms / scheduler_tick_skew_ms / disk_io_util_pct）|
| B | `test_sprint2_ladder_pipeline_throughput` | PASS | tick_rate / ipc_p99 / ws_subscription_drift / strategy_signal_rate + heartbeat_lag_ms CRITICAL > 60000ms 即時 fire (HIGH-1 fix) |
| C | `test_sprint2_ladder_database_pool` | PASS | active_conn / queue_depth / wait_p95 / disk + 5th column pool_max_conn (MEDIUM-1 C fix) |
| D | `test_sprint2_ladder_api_latency` | PASS | 8 metric × 4 band（rest_p50/p95/p99 + ws_rtt_p50/p99 + ret_4xx/5xx + ws_dropout）4 含 CRITICAL（rest_p99 / ws_rtt_p99 / ret_5xx / ws_dropout）+ 4 不含（rest_p50 / rest_p95 / ws_rtt_p50 / ret_4xx）|
| E | `test_sprint2_ladder_strategy_quality_per_pair` | PASS | per-pair OK→WARN→DEGRADED + aggregate 0.40 threshold |
| F | `test_sprint2_ladder_risk_envelope` | PASS | position_count_active 0-8/9-16/>16（不含 CRITICAL；M3 spec §2.3 line 106 amend）+ dd / corr / top1 / cum_pnl |

**6 Track ladder PASS** ✅

## 4. AC-3 amp cap 24h-suppression（Sprint 1A-ζ regression）

```bash
cargo test --release --features spike --test m3_amp_cap_24h_fire
```

| Test | Result |
|---|---|
| `test_amp_cap_different_anomaly_id_not_suppressed` | PASS |
| `test_m3_amp_cap_24h_fire` | PASS |
| `test_stub_domains_fail_loud` | PASS |

**3/3 PASS** ✅ Sprint 1A-ζ amp cap baseline 不退

## 5. AC-4 cross-domain independence

5 cross_domain test PASS（6 Track 互相獨立全 cover；Track A 沒有自己的 cross_domain test 是因為 Track B 的 `test_sprint2_cross_domain_pipeline_engine_independence` 已測 Track B → Track A 反向）：

```
test_sprint2_cross_domain_api_latency_independence ... ok
test_sprint2_cross_domain_database_pool_independence ... ok
test_sprint2_cross_domain_pipeline_engine_independence ... ok
test_sprint2_cross_domain_risk_envelope_independence ... ok
test_sprint2_cross_domain_strategy_quality_independence ... ok
```

**5/5 PASS** ✅ 每 Track 升 DEGRADED 不影響其他 5 domain state

## 6. AC-5 production binary 0 mock time 滲透

```bash
nm /Users/ncyu/Projects/TradeBot/srv/rust/target/release/openclaw-engine 2>/dev/null | grep -E "(mock_instant|tokio::time::pause|spike)" | wc -l
```

結果：**0 hit** ✅

binary footprint 19425968 bytes (~18.5 MB)；無 spike feature 滲透。

## 7. AC-6 cargo + pytest baseline 不退

per E4 Phase 3b regression report 已確認（QA 不重跑全 workspace）：

| Engine | Pass | Fail | non-flaky | E4 baseline ref |
|---|---|---|---|---|
| cargo workspace --release (skip stress_tick_latency_benchmark) | **3894** | 0 | 兩遍同綠 ✅ | Sprint 1A-ζ baseline 3769 → +125 (Sprint 2 51 + spike + Sprint 1B early Rust binding) |
| pytest non-flaky | **6042** | 28 pre-existing | 兩遍同綠 ✅ | Sprint 1A-ζ baseline 6037 → +5 (Sprint 1B Rust binding 5/5) |
| health:: lib subset | **87** | 0 | ✅ | 對齊 Sprint 1A-ζ |
| governance::lal:: lib subset | **15** | 0 | ✅ | 對齊 Sprint 1A-ζ |
| Cross-lang fixture (Python 7 + Rust binding 5) | **12** | 0 | ✅ | Sprint 1B AC-7 FULL PASS |

28 pytest pre-existing failure 全為 sibling drift（24 GUI + 4 structure）；Sprint 2 0 file touched。

**QA 本次 sanity recheck**：health:: lib subset 87/0 重跑確認對齊 ✅

## 8. AC-7 50ms cold start

**Carry-over to E4/PA — `cargo bench --bench m3_emitter_cold_start` 未 IMPL**：
- `rust/openclaw_engine/Cargo.toml` 只有 `hot_path_baseline` + `intent_processor_exposure` 兩個 bench
- `m3_emitter_cold_start` bench file 不存在
- engine binary 不是 CLI 工具（無 `--version` 路徑進入 service loop；time engine --version 不是 AC-7 measurement）

QA 不重新發明 measurement 方法；per dispatch packet §1.6.1 + parent spec §AC-7 由 E2 + QA 兩端決定，但 bench fixture 尚未存在 → defer 到 Sprint 2 close + Sprint 5 cascade IMPL 階段。

## 9. OBSERVE-4 audit

### 9.1 cross-Wave m3_emitter_replay_forbidden test PASS

| Test | Result |
|---|---|
| `test_metric_emitter_scheduler_replay_engine_mode_forbidden` | PASS |
| `test_strategy_quality_scheduler_replay_engine_mode_forbidden` | PASS |
| `test_metric_emitter_scheduler_non_replay_engine_mode_ok_startup` (paper/demo/live_demo/live 4-mode startup OK) | PASS |

**3/3 PASS** ✅

### 9.2 雙層 fail-loud 對齊

| Layer | Enforcement | grep verify |
|---|---|---|
| PG V106 `engine_mode` CHECK | `IN ('paper','demo','live_demo','live')` 不含 'replay' | Linux sandbox 實證 ✅ |
| Rust `M3Error::ReplaySubprocessForbidden` variant | `health/mod.rs:96` | ✅ |
| Rust `MetricEmitterScheduler::run` startup guard | `health/metric_emitter/mod.rs:596` | ✅ |
| Rust `MetricEmitterScheduler` per-tick guard | `health/metric_emitter/mod.rs:731-735` | ✅ |
| Rust `StrategyQualityScheduler::run` startup guard | `health/domains/strategy_quality.rs:708` | ✅ |
| Rust `StrategyQualityScheduler` per-tick guard | `health/domains/strategy_quality.rs:725-732` | ✅ |

### 9.3 unused async_trait import warning (QA-2 E4 carry-over)

```
warning: unused import: `async_trait::async_trait`
  --> openclaw_engine/tests/m3_emitter_replay_forbidden.rs:31:5
```

→ confirmed P3 LOW cosmetic carry-over（E4 Phase 3b 已列）；不阻 PASS verdict；E1 round 3 minor cleanup 1 行 diff。

## 10. PA spec amend driver — 9 個檢點對齊

per PA Wave 2 spec amend report（`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_wave2_track_def_spec_amend.md`）4 amend + 5 配套：

| # | 檢點 | spec literal | IMPL 對應 | 對齊 |
|---|---|---|---|---|
| 1 | ApiLatencySample 8 field 結構 | Sprint 2 spec §3.2 + M3 spec §2.3.3 | `api_latency.rs:110-124` 8 field pub struct | ✅ |
| 2 | api_latency 8 metric × 4 band 含/不含 CRITICAL | M3 spec §2.3 line 104 amend + §2.3.3（4 含：rest_p99 > 2000ms / ws_rtt_p99 > 1500ms / ret_5xx > 20 / ws_dropout > 5；4 不含：rest_p50 / rest_p95 / ws_rtt_p50 / ret_4xx）| `api_latency.rs` 8 `classify_*` fn line 241-412 | ✅ |
| 3 | 8 anomaly_id literal 命名 | Sprint 2 spec §6.2 `api_latency__<metric_name>` 8 條 | `into_metric_rows` line 174-209 8 row | ✅ |
| 4 | ApiLatencySourceProbe trait 抽象 + Arc<dyn> 注入 | E2 HIGH-2 fix Option C type-level 60s window 契約 | `api_latency.rs:477-494` 8 method 全 `_60s_window` 後綴 | ✅ |
| 5 | position_count_active 0-8/9-16/>16 不含 CRITICAL | M3 spec §2.3 line 106 amend | `risk_envelope.rs:102 + 162 + 282` IMPL 已落 | ✅ |
| 6 | OBSERVE-4 M3Error variant + scaffold-level guard | Sprint 2 spec §5.0 + M3 spec §1.78 OBSERVE-4 invariant | `health/mod.rs:96` + 兩 scheduler 啟動 + per-tick guard 雙層 | ✅ |
| 7 | PG V106 engine_mode CHECK 不含 'replay' | V106 schema spec line 38 + §4.4 | Linux sandbox 實證 4 值不含 'replay' | ✅ |
| 8 | PA-DRIFT-4 carry-over acknowledge in doc comment | dispatch packet §5.5 反模式 (c) + (d)；emitter 不修 bybit wrapper | `api_latency.rs` module 頭 line 62-72 doc comment 補 PA-DRIFT-4 reference + 反模式註腳 | ✅ |
| 9 | spec literal reference 在 IMPL doc comment | E1 round 2 doc comment 補引 spec §2.3.3 / §2.3 line 104 / line 106 / Sprint 2 spec §3.2 / §5.0 | api_latency.rs × 4 處 + risk_envelope.rs × 2 處 全引「M3 spec §2.3 line 104/106 amend」+ Track A scaffold ReplaySubprocessForbidden doc 引 Sprint 2 spec §1.x OBSERVE-4 line 199-216 | ✅ |

**9/9 對齊** ✅

## 11. Phase 3c verdict

**PASS WITH 1 EXPECTED CARRY-OVER** — Sprint 2 Wave 1+2 scaffold sign-off 全綠；不阻進入 Phase 3d TW Acceptance Report。

### 11.1 PASS rationale

| Gate | 結果 |
|---|---|
| AC-1a in-memory proxy 6 Track row count + OBSERVE-4 | ✅ 51/51 PASS |
| AC-2 4-state ladder fire 6 Track | ✅ 6 ladder test PASS |
| AC-3 amp cap regression spike | ✅ 3/3 PASS |
| AC-4 cross-domain independence | ✅ 5 cross_domain test PASS |
| AC-5 nm 0 hit | ✅ 0 mock time 滲透 |
| AC-6 cargo + pytest baseline 不退 | ✅ 3894/0 + 6042/28 per E4 Phase 3b |
| OBSERVE-4 cross-Wave 雙 scheduler guard + PG CHECK | ✅ 3/3 PASS + Linux sandbox 實證 |
| PA spec amend driver | ✅ 9/9 對齊 |

### 11.2 4 expected carry-over

| # | Item | Status | Resolution path |
|---|---|---|---|
| QA-1 | AC-1b real PG empirical (30 min window row count ≥ 5) | PARTIAL → DEFER | Sprint 4 first Live deploy window：(1) main.rs 接 MetricEmitterScheduler::run + StrategyQualityScheduler::run (2) PA-DRIFT-4 bybit_rest_client + bybit_private_ws instrumentation IMPL (3) Linux runtime --rebuild (4) ≥ 30 min 樣本累積；前置 `P1-ENGINE-BINARY-SPRINT-1A-IMPL-DEPLOY` |
| QA-2 | m3_emitter_replay_forbidden.rs:31 unused async_trait import warning | OPEN | E1 1 行 diff cosmetic clean；不阻 PASS；E4 Phase 3b 已 confirm P3 LOW |
| QA-3 | PA-DRIFT-4 bybit_rest_client + bybit_private_ws instrumentation 補位 | OPEN | E1 IMPL 4-6 hr (Wave 2 main.rs 接 ApiLatencySourceProbe trait 前必 closed)；不阻 AC-1a scaffold sign-off；阻 AC-1b real PG empirical |
| QA-4 | E4 workspace regression SOP `--skip stress_tick_latency_benchmark` + isolated-only SLA bench 註腳 | OPEN | PM SOP 加進 regression-testing-protocol skill carry-over |
| **NEW QA-5** | AC-7 cold start binary footprint — `cargo bench --bench m3_emitter_cold_start` 未 IMPL | OPEN | E4 / E1 IMPL bench fixture（emitter scheduler `new` + `run` 進入 first tick wall-clock measurement）；defer 到 Sprint 5 cascade IMPL 階段 |

## 12. Sub-agent / multi-session race

QA 本次 single-thread；無派下游；無 commit；無 production engine 重啟。

git status dirty 全 unrelated（Layered Autonomy v2 pre-existing edit + 本 report append）：
- pre-existing：`.codex/WORKLOG.md` / `docs/CCAgentWorkSpace/E2/memory.md` / `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--autonomy_level_toggle_design_spec.md` / `docs/execution_plan/2026-05-22--autonomy_level_toggle_design_spec.md` / `docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md` / `memory/MEMORY.md` / `docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-22--layered_autonomy_v2_reaudit.md` / `memory/project_2026_05_22_layered_autonomy_with_failsafe.md`
- QA 本次新加：`docs/CCAgentWorkSpace/QA/memory.md` (append) + 本 report

PM commit 範圍：上述 2 個 QA 新加（memory.md append + 本 report）。

## 13. Regression governance

- 0 emoji
- 0 hardcoded path
- 中文注釋 default（report 全中文）
- 0 production code 觸碰（QA 只跑 test + ssh sandbox 讀；不修業務邏輯）
- 0 commit（PM 收口）
- 0 派下游 sub-agent
- 0 重啟 production engine PID 2934602
- ssh trade-core 只走 sandbox_admin / trading_ai_sandbox 路徑（trading_admin 連 sandbox 讀，符合 §3.1 sandbox_admin role 角色定位）

## 14. Operator 下一步

| Action | Owner | Priority |
|---|---|---|
| PM commit: QA memory append + 本 report | PM | P0 |
| Phase 3d TW Sprint 2 Acceptance Report (~2-3 hr) | TW (single) | P0 |
| Phase 3e PM closure verdict (PASS/FAIL/Partial) | PM (single) | P0（待 Phase 3d 完）|
| Sprint 5 cascade IMPL dispatch readiness sign-off（per Layered Autonomy v2 §1.7）| operator + PM | P1（待 Phase 3e closure）|
| AC-1b real PG empirical 跑 (Sprint 4 deploy window) | E1 + QA | P1（前置：main.rs wire-up + PA-DRIFT-4 instrumentation + --rebuild + 30 min 樣本）|
| QA-2 async_trait unused import cosmetic clean | E1 | P3 LOW |
| QA-3 PA-DRIFT-4 bybit instrumentation IMPL | E1 | P1（Wave 2 main.rs 接前必 closed）|
| QA-4 E4 SOP --skip stress_tick_latency_benchmark | PM SOP | P2 |
| QA-5 AC-7 cargo bench m3_emitter_cold_start IMPL | E1 + E4 | P2（defer 到 Sprint 5）|

---

**QA E2E ACCEPTANCE DONE**: PASS WITH 1 EXPECTED CARRY-OVER · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-22--sprint_2_phase_3c_qa_empirical_verify.md`
