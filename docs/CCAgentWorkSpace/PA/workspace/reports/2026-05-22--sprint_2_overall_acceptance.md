---
report: Sprint 2 — M3 metric emitter Overall Acceptance Report
date: 2026-05-22
author: TW (Technical Writer)
phase: Sprint 2 Phase 3d (Wave 1+2 IMPL Acceptance)
sprint: Sprint 2 (M3 metric emitter 6 Track × Wave 1+2 + cross-Wave OBSERVE-4)
status: SIGNED-OFF-PENDING-PM
verdict: PASS WITH 5 CARRY-OVER（待 PM Phase 3e 拍板）
sprint_5_gate: PENDING per Phase 3e PM closure（cascade IMPL dispatch readiness sign-off）
parent specs:
  - srv/docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md (PA Sprint 2 design spec)
  - srv/docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md (PA dispatch packet)
  - srv/docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md (M3 design spec; PA amend §2.3 line 102/103/104/106 + §2.3.1/§2.3.2/§2.3.3)
  - srv/docs/adr/0042-m3-health-monitoring.md (governance authority；不 amend)
  - srv/docs/adr/0040-multi-venue-extensibility.md (api_latency 預留 multi-venue；不 amend)
parent reports:
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_readiness_signoff.md (Phase 1 readiness sign-off)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_wave1_m3_spec_amend.md (Wave 1 spec amend — 4 finding)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_wave1_packet_ac1_split_fix.md (AC-1a/AC-1b 拆分契約)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_wave2_track_def_spec_amend.md (Wave 2 spec amend — 4 finding)
  - srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave1_track_a_engine_runtime.md (Track A round 1 scaffold)
  - srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave1_track_a_round2_fix.md (Track A round 2 fix)
  - srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave1_round2_combined_fix.md (Wave 1 Track A/B/C round 2 combined)
  - srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave1_round3_pa_dependent_fix.md (Wave 1 Track B/C round 3 PA-dep)
  - srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave2_track_d_api_latency.md (Track D round 1 IMPL)
  - srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave2_track_e_strategy_quality.md (Track E round 1 IMPL)
  - srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave2_track_f_risk_envelope.md (Track F round 1 IMPL)
  - srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave2_round2_combined_fix.md (Wave 2 Track D/E/F round 2 combined + OBSERVE-4 cross-Wave)
  - srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-22--sprint_2_phase_3b_regression.md (Phase 3b regression)
  - srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-22--sprint_2_phase_3c_qa_empirical_verify.md (Phase 3c QA empirical verify)
scope: Sprint 2 Overall Acceptance Report 彙整 Phase 0-3c 全部 verdict；TW 不下 verdict（最終 verdict by PM Phase 3e）；列 AC-1a/1b/2/3/4/5/6/7 + OBSERVE-4 9 條 acceptance criteria 結果；6 Track A/B/C/D/E/F 各自 acceptance；cross-cutting ADR / 16 原則 / Production Safety / multi-session race；Lessons Learned 6 條；carry-over 分 Sprint 4+ first Live / Sprint 5+ cascade / Doc+lint 三類；Phase 3e PM sign-off 待拍板項
non-scope:
  - 不改業務邏輯（health/mod.rs / metric_emitter/mod.rs / domains/*.rs / writer.rs / event_bus.rs 全未碰）
  - 不寫 spec patch（5 carry-over 走 Sprint 4+ deploy window / Sprint 5+ cascade IMPL / E1 cosmetic clean）
  - 不 commit（PM 收口統一）
  - 不派下游 sub-agent
  - 中文為主，無 emoji
---

# Sprint 2 — M3 metric emitter Overall Acceptance Report

## §1 Executive Summary

### 1.1 Sprint 2 範圍與目的

Sprint 2 為 M3 metric emitter IMPL Sprint，落地 ADR-0042 Decision 3 規範的 6 個 health domain（engine_runtime / pipeline_throughput / database_pool / api_latency / strategy_quality / risk_envelope）的 metric emitter scaffold，採 5-sample rolling window + 4-state ladder（OK / WARN / DEGRADED / CRITICAL）+ amp cap 24h-suppression。Sprint 1A-ζ 已完成 spike Track B 的 V106 schema + state machine 骨架 + amp cap 嚴格 fire 語意；Sprint 2 擴 6 domain 全展開 + cross-Wave OBSERVE-4 replay subprocess fail-loud guard。

operator 2026-05-22 task brief 簽收 3 條決策：
- **D1**：採 `sysinfo` crate（跨平台 + Mac 部署目標 per `project_mac_deployment_target`）取代 procfs + sysctl 拼接
- **D2**：與 Sprint 1B mid 3 carry-over（PA-DRIFT-1/2 + E3-MED-2）並行運行
- **D3**：Sprint 2 Track A 含 Sprint 5 cascade reject log emit minimal IMPL（V106 row INSERT with `evidence_json={"reject_reason": "..."}`；不接 Slack / Console badge / halt strategy / 降 LAL Tier）

Sprint 2 6 Track 拆 Wave 1 (Track A/B/C 3 並行) + Wave 2 (Track D/E/F 3 並行)；Track A 為 scaffold owner（trait + writer + event bus + observe_classified API + sysinfo + EngineRuntimeEmitter + D3 cascade reject）24h 內 land 公共依賴後 Track B/C/D/E/F 沿用。

### 1.2 結果摘要

| 維度 | 結果 |
|---|---|
| **Verdict（TW 彙整）** | **PASS WITH 5 CARRY-OVER**（待 PM Phase 3e 拍板）|
| **AC pass 率** | 7 PASS / 1 PARTIAL DEFER / 1 OPEN-CARRY-OVER（AC-7 cargo bench fixture 未 IMPL）|
| **Sprint 5 cascade IMPL dispatch readiness gate** | **PENDING per Phase 3e PM closure** |
| **Critical schema gap discovered** | 0（V106 schema 沿用；engine_mode CHECK IN ('paper','demo','live_demo','live') 不含 'replay' 為設計刻意 fail-loud baseline）|
| **ADR ↔ spec ↔ IMPL 三層不對齊** | 0（ADR-0042 governance authority 不 amend；M3 design spec §2.3 + Sprint 2 spec §3.2 + 6 Track IMPL 9/9 對齊）|
| **Hard boundary 違反** | 0（emitter 不創新 order 寫入口 / 不寫 live state / 不繞 Decision Lease / not 動 5-gate）|
| **multi-session memory race** | 0（commit chain `81a2caeb → 788f8e99 → 2a7e2ae0 → 6152b01d → 6f6bbea8 → ffb7ed48 → 4d7d12c9 → be70da06` 8 commit clean；7 commit Phase 2-3a + 1 commit Phase 3b + 1 commit Phase 3c sequential）|
| **Sub-agent ceiling** | Phase 2 Wave 1 peak 6-7 並行（Track A/B/C 3 + Sprint 1B mid 0-3 + PM）；其餘階段全 healthy 餘量 |
| **Wall-clock** | 1 wall-clock day high-density dispatch（2026-05-22；vs Phase 1 estimate 1-1.5 week）|

### 1.3 Sprint 2 為 Sprint 5+ cascade IMPL 提供的 runtime confidence

- **6 Track scaffold 結構穩定**：DomainEmitter trait + RollingWindowAggregator + HealthObservationWriter + HealthEventBus + MetricEmitterScheduler 共用 API；Track B-F 沿用同 trait 抽象不重做
- **OBSERVE-4 cross-Wave invariant 物理上強制**：M3Error::ReplaySubprocessForbidden variant + 雙 scheduler（MetricEmitterScheduler + StrategyQualityScheduler）+ startup guard + per-tick guard + V106 engine_mode CHECK 不含 'replay' = 雙層 fail-loud（Rust + PG）
- **D3 cascade reject log emit minimal IMPL 對齊 V106 spec §1.1**：amp_cap_>=2_fail_closed + amp_cap_same_anomaly_24h_suppress 兩 reason 由 `infer_reject_reason` helper 推斷（DRY）；Track B-F 沿用同邏輯不重複 inline
- **5 strategy × 25 symbol pair-level OR-aggregate Path A 落地**：strategy_quality 100 SM (25 pair × 4 metric) + 1 aggregate SM；spec §3.4 line 211「DEGRADED 策略數 / 總策略數」對齊 pair-level 2-tuple SSOT 非 3-tuple SM count
- **6 Track integration test 51/51 PASS + 8 commit deterministic closure**：cargo workspace 3894/0 + pytest 6042/28 + cross-lang Python 7/7 + Rust binding 5/5；Sprint 5 cascade IMPL 可直接沿用 6 Track scaffold + 接 main.rs scheduler + bybit instrumentation

---

## §2 Phase 0-3c chronology + verdict

### 2.1 Phase 1 — PA refine + dispatch packet（PA single / 2-3 hr / 0.5 day）

PA single-thread land：

| Deliverable | 內容 |
|---|---|
| Sprint 2 readiness sign-off | D1/D2/D3 整合 + 6 Track 派發 readiness OPEN with carry-over conditions + Sub-agent ceiling 預警（Phase 2 Wave 1 peak 6-7 並行為唯一 tight 階段）|
| Sprint 2 design spec | parent spec +130-150 行（§0 TL;DR rewrite + §3 Decisions Finalized + §4 IMPL plan adjust + §8.1/§8.2/§9.3 update）|
| Sprint 2 dispatch packet | ~370 行 6 Track 派發包 + Wave 拆分 + Phase chain estimate + 9 元素齊（spec ref / AC ref / cross-V### dep / file path / SOP ref / memory race mitigation / Chinese comment mandate / disconnect recovery / acceptance gate）|

commit `81a2caeb` PA Phase 1 readiness + dispatch packet land。

### 2.2 Phase 2 Wave 1 — E1 × 3 並行（Track A/B/C / 18-24 hr 並行 / 3 day wall-clock 預計，實際 D0 same-day 高密度）

per packet §2-§4，Wave 1 Track A 為 scaffold owner，B/C 沿用：

| Track | Module | File | 結果 |
|---|---|---|---|
| **Track A** | engine_runtime baseline 升級 + D3 cascade reject | `rust/Cargo.toml` + `rust/openclaw_engine/Cargo.toml` (sysinfo "0.32" 工作區依賴) + `health/metric_emitter/mod.rs` (964 LOC scaffold 含 DomainEmitter trait + RollingWindowAggregator + EngineRuntimeEmitter + 6 metric classify helper + 8 unit test) + `health/writer.rs` (464 LOC HealthObservationWriter trait + PgHealthObservationWriter + InMemoryHealthObservationWriter) + `health/event_bus.rs` (202 LOC HealthEventBus + HealthStateChangeEvent + HealthEventSubscriber) + `health/mod.rs` 升級 (+272 LOC observe_classified + try_dwell_then_transition + try_recovery_dwell + 5 new SM field) + `tests/sprint2_track_a_engine_runtime.rs` 5 integration test | Round 1 IMPL DONE：scaffold 7 element 全 land；6 metric × 5 sample = 30 row tick；D3 cascade reject 2 reason emit V106 row evidence_json |
| **Track B** | pipeline_throughput | `health/domains/pipeline_throughput.rs` (新) + `health/domains/mod.rs` (新) + `tests/sprint2_track_b_pipeline_throughput.rs` (新) | Round 1 IMPL DONE：5 metric (tick_rate / ipc_p99 / heartbeat_lag_ms / drift_count / signal_rate) ladder helper |
| **Track C** | database_pool | `health/domains/database_pool.rs` (新) + `tests/sprint2_track_c_database_pool.rs` (新) | Round 1 IMPL DONE：4 metric (active_conn / wait_ms_p95 / queue_depth / disk_used_pct) ladder helper |

commit chain `788f8e99` (Wave 1 Track A scaffold) + `2a7e2ae0` (Wave 1 Track B/C 並行)。

### 2.3 Phase 3a Wave 1 round 1-2（E2 × 3 並行 / Track A/B/C / 4-6 hr）

| Track | E2 round 1 finding | round 2 fix | Round 2 verdict |
|---|---|---|---|
| **Track A** | E2 round 1 REJECT (3 HIGH + 2 MEDIUM + 1 LOW)：HIGH-1 D3 cascade reject_reason false positive（same anomaly + count=2 場景誤標 fail-closed；guard 順序混淆）+ HIGH-2 recovery dwell anchor 升階方向不對稱清理（5 domain 通用 bug）+ HIGH-3/LOW-1 AC-1 spec drift not in scope（PA 並行修）+ MEDIUM-1 async lock held across await + MEDIUM-2 dwell_time_sec hardcoded 0 + LOW-2 cosmetic | E1 round 2 5 deterministic fix land：(1) is_anomaly_capped pub accessor + infer_reject_reason pub helper（DRY，Track B-F 沿用）(2) observe_classified 升階 5 條 + 同 state 高 band 採樣 reset recovery_band_seen_at (3) Err 分支前 drop lock guard (4) dwell_time_sec wire-up state_entered_at 真實值 (5) cosmetic 冗餘 reset 移除 | E2 round 2 **APPROVE** (inline final response) |
| **Track B** | E2 round 1 REJECT (HIGH-1 heartbeat_lag CRITICAL band drift 60-120s 改 DEGRADED 違 spec line 102 SSOT + HIGH-2「持續 2min」semantic 與 §3.3 60s SM dwell 混淆 + MEDIUM-1 drift+signal threshold unilateral spec drift + 2 LOW) | E1 round 2 1 deterministic fix (HIGH-1 revert `> 60_000 → CRITICAL`)；3 PA-dependent fix（HIGH-2 doc 注釋對齊 §2.3.1 / MEDIUM-1 doc 引 §2.3 line 102 amend / LOW）由 PA spec amend land 後 E1 round 3 對齊 | E2 round 2 **APPROVE** (inline) |
| **Track C** | E2 round 1 REJECT (HIGH-1 classify_aggregated 漏 database_pool 3 arm 全 fallback OK band + HIGH-2 test 無 state band assert + MEDIUM-1 pool_max_conn 5th column drift Path A vs Path B 未決 + MEDIUM-2 probe wire-up + MEDIUM-3 disconnected fail-closed Path A vs Path B 未決 + LOW) | E1 round 2 3 deterministic fix (HIGH-1 classify_aggregated 加 3 arm + HIGH-2 assert + MEDIUM-2 doc TODO follow-up)；2 PA-dependent (MEDIUM-1 pool_max_conn 5th column + MEDIUM-3 disconnected fail-closed OK band) round 3 對齊 | E2 round 2 **APPROVE** (inline) |

PA Wave 1 spec amend land 同時段（commit `6152b01d`）：

| Finding | PA 修法 |
|---|---|
| Track B HIGH-1 heartbeat CRITICAL | M3 spec §2.3 line 102 + §2.3.1 確認 `> 60_000 ms → CRITICAL` 即時 fire 為 SSOT 重申，不 amend ladder 數值 |
| Track B HIGH-2「持續 2min」semantic | Path A 採納：M3 spec §2.3.1 新節 clarify「metric classify ≠ SM band dwell；measurement window ≠ dwell time」；line 102「持續 2min」literal 為 v5.7 非規範性 carry-over；真規範值 = §3.3 line 165 SM OK→WARN dwell 60s（不改 SM dwell 數值）|
| Track B MEDIUM-1 drift+signal threshold | M3 spec §2.3 line 102 ladder 補 2 metric threshold（drift 0/1-2/3+ + signal_rate ≥0.5/0.1-0.5/<0.1）+ Sprint 2 spec §4.3 classify_band_from_mean 函數示例補 2 metric arm |
| Track C MEDIUM-1 pool_max_conn | Path A 採納：Sprint 2 spec §3.2 `DatabasePoolSample` 4 field → 5 field（含 pg_pool_max_conn: u32）；max 由 caller 注入（DatabaseConfig::pool_max_connections）；sqlx PgPool 未暴露 max accessor，emitter 不可強行 hack |
| Track C MEDIUM-3 disconnected fail-closed | Path A 採納：M3 spec §2.3.2 新節 database_pool disconnected handling — fail-closed OK band（不誤升 CRITICAL 避激進 cascade 副作用；真實 PG 斷線由 cascade event 接：engine_runtime PID dead / pipeline_throughput WS dropout / 既有 5-gate kill）+ disconnected evidence_json 寫 `{"pool_status": "disconnected"}` 留 audit |

同時段 PA Wave 1 packet AC-1 split fix land（per E2 round 1 HIGH-3 / LOW-1）：

- AC-1a = Wave 1 scaffold sign-off in-memory `HealthObservationWriter` mock fixture（cargo test PASS 即可）
- AC-1b = Wave 2+ real PG empirical（前置 main.rs scheduler 接線 + Linux runtime --rebuild + ≥30 min 樣本）
- 6 Track AC-1 全拆 a/b 拆分；Track A 明示 6 metric × 5 sample = 30 V106 row tick；其餘 Track N×5 row pattern 不寫死 metric 個數
- design spec §AC-1 SQL verify pattern 不動（仍為 AC-1b 權威 verify pattern）

E1 round 3 PA-dependent fix（Track B 2 + Track C 3）closure 完整 land commit `6152b01d`（Wave 1 BC round 2+3）。

### 2.4 Phase 2 Wave 2 — E1 × 3 並行（Track D/E/F / 20-28 hr 並行 / 3 day wall-clock 預計，實際 D0 same-day 高密度）

per packet §5-§7，Wave 2 沿用 Wave 1 scaffold 8/8：

| Track | Module | File | 結果 |
|---|---|---|---|
| **Track D** | api_latency | `health/domains/api_latency.rs` (952 LOC 含 8 classify helper + 8 inline unit test + StubSource + emitter struct + impl) + `tests/sprint2_track_d_api_latency.rs` (823 LOC) + `health/metric_emitter/mod.rs` classify_aggregated 加 8 個 api_latency arm | Round 1 IMPL DONE：ApiLatencySample 8 field (rest_p50/p95/p99 + ws_rtt_p50/p99 + ret_4xx/5xx + ws_dropout)；4 含 CRITICAL（rest_p99 / ws_rtt_p99 / ret_5xx / ws_dropout）+ 4 不含（rest_p50 / rest_p95 / ws_rtt_p50 / ret_4xx）；對齊 Sprint 2 spec §3.2 + M3 spec §2.3 line 104 amend SSOT |
| **Track E** | strategy_quality（最高工時） | `health/domains/strategy_quality.rs` (1489 LOC 含 StrategyQualitySample / StrategyQualityEmitter / StrategyQualityScheduler + 4 classify_band helper + per-pair process + aggregate observe + 10 lib mod test) + `tests/sprint2_track_e_strategy_quality.rs` (851 LOC 含 10 integration test) | Round 1 IMPL DONE：5 field (fill_rate_intent_ratio + slippage_bps_p95 + decision_lease_grant_rate + dormant_minutes + signal_count_24h)；4 metric ladder + signal_count_24h telemetry-only fallback OK band；25 pair × 4 metric = 100 SM + 1 aggregate SM；aggregate rule `degraded_count / total_count > 0.40 → DEGRADED`；獨立 `StrategyQualityScheduler`（per spec §4.4 line 638-643 明文）|
| **Track F** | risk_envelope | `health/domains/risk_envelope.rs` (848 LOC 含 5 metric snapshot struct + 5 classify helper + DomainEmitter impl + RiskEnvelopeSourceProbe trait 注入 + 10 inline test) + `tests/sprint2_track_f_risk_envelope.rs` (705 LOC 含 8 integration test) + `health/metric_emitter/mod.rs` classify_aggregated 加 risk_envelope 5 arm | Round 1 IMPL DONE：RiskEnvelopeSample 5 field (cum_pnl / max_dd / position_count_active / corr_avg / concentration_top1)；ladder 1:1 對齊 M3 spec §2.3 line 106；Track F 對 user prompt 7 metric 版本 push back（governance docs SSOT 5 metric；多 3 metric portfolio_var_pct / leverage_avg / margin_util_pct 標 Track F+1 / Sprint 5+ 擴展點待 PM 決定 PA spec amend 路徑）|

commit `6f6bbea8` (Wave 2 Track D/E/F 並行)。

### 2.5 Phase 3a Wave 2 round 1-2（E2 × 3 並行 / Track D/E/F / 4-6 hr）

| Track | E2 round 1 finding | round 2 fix | Round 2 verdict |
|---|---|---|---|
| **Track D** | E2 round 1 REJECT (CRIT-1 + 3 HIGH + 2 MED + 1 LOW)：CRIT-1 `ApiLatencySample` 5→8 field schema drift（E1 IMPL 已 land 8 field 但 spec literal 5 field）+ HIGH-1 4 處誤導性 spec literal 引用（line 102 vs line 104 amend）+ HIGH-2 trait method `_60s_window` 後綴 Option C type-level 60s window 契約 + HIGH-3 bybit_rest_client + bybit_private_ws prerequisite false（grep verify 0 hit）+ MED-1 OBSERVE-4 replay subprocess guard 升 Track A scaffold contract + MED-2 file 952 LOC > 800 警告 + LOW-1 ws_dropout count 維度注釋 | E1 round 2 6 fix 全 closure：(1) CRIT-1 spec amend land 後 doc comment 對齊（IMPL 不 revert；PA spec amend report 並行 land）(2) HIGH-1 4 處 line 102 改 line 104 amend reference (3) HIGH-2 trait 8 method 加 `_60s_window` 後綴 + emitter sample_now 8 處呼叫對齊 + StubSourceProbe 對齊 (4) HIGH-3 module 頭注釋加 PA-DRIFT-4 follow-up reference acknowledge（不 IMPL bybit hook 本身）(5) MED-1 OBSERVE-4 fix 接 Track A scaffold round X (6) LOW-1 注釋誠實補維度說明 | E2 round 2 **APPROVE-WITH-CONDITIONS**（per Wave 2 spec amend + carry-over）|
| **Track E** | E2 round 1 REJECT (1 HIGH + 3 LOW)：HIGH-1 aggregate `total_count / degraded_count` 走 3-tuple per_pair_sms.len() 而非 2-tuple (strategy, symbol) pair-level OR-aggregate（11 metric DEGRADED 觸 0.40 threshold 但實際只壞 11/100 = 11% SM）+ LOW-1 per_pair_independence test 只測 25 pair × 1 metric 不測 100 SM + LOW-2 anomaly_id by-band 命名 + LOW-3 `per_pair_sm_count()` 名稱誤導 + 2 accessor 分拆 | E1 round 2 3 deterministic fix + 3 boundary test land：(1) HIGH-1 aggregate pair-level OR-aggregate Path A 修法（迭代 per_pair_sms 按 (strategy, symbol) tuple grouping；一個 pair 任一 metric SM = DEGRADED/CRITICAL → 該 pair 標 degraded；total_count = unique pair 數 25；degraded_count = degraded pair 數）+ 3 boundary test 守 fix 不退化（11 pair × 1 metric → ratio 0.44 升 DEGRADED / 10 pair × 4 metric → ratio 0.40 留 OK / 4 pair × 4 metric → ratio 0.16 留 OK）(2) LOW-1 expand 25 pair × 4 band metric = 100 SM 全覆蓋 (3) LOW-3 `per_pair_sm_count` 拆 `per_metric_sm_count` + `pair_count` 2 accessor | E2 round 2 **APPROVE-WITH-CONDITIONS** |
| **Track F** | E2 round 1 APPROVE-WITH-CONDITIONS (1 MED + 2 LOW)：MED-1 `position_count_active` threshold ladder 未在 spec literal land（IMPL 數值 OK 0-8 / WARN 9-16 / DEGRADED >16 對齊 risk_config max_open_positions=16 上限預期但缺 spec SSOT 認可）+ 2 LOW | E1 round 2 1 doc fix：MED-1 doc comment 補引 `M3 spec §2.3 line 106 amend` literal reference（PA spec amend land 後對齊）+ 2 LOW closure | E2 round 2 **APPROVE-WITH-CONDITIONS** |

PA Wave 2 spec amend land 同時段（commit `ffb7ed48`）：

| Finding | PA 修法 |
|---|---|
| Track D CRIT-1 ApiLatency 5→8 field | M3 spec §2.3 line 104 ladder 由 5-metric 改 8-metric 全 4 band literal + §2.3.3 新節「api_latency 8 metric 結構 — Track D Sprint 2 amend」+ Sprint 2 spec §3.2 ApiLatencySample 5→8 field + §6.2 anomaly_id 命名表 api_latency row 2 例 → 8 literal |
| Track D MED-1 OBSERVE-4 replay guard | Sprint 2 spec §5.0 新節「OBSERVE-4 invariant — engine_mode replay subprocess emit forbidden」+ dispatch packet §1.7 Track A scaffold contract 加 row「OBSERVE-4 replay subprocess guard ~20 LOC」+ Track A scaffold round X IMPL：`M3Error::ReplaySubprocessForbidden` variant + `HealthObservationWriter::write` 入口 guard + 雙 scheduler startup + per-tick guard + `tests/m3_emitter_replay_forbidden.rs` 新 test |
| Track D HIGH-3 bybit prerequisite + PA-DRIFT-4 | dispatch packet §5.1 prerequisite 由「既有 hook」改為「hook 不存在（grep verify 0 hit）→ PA-DRIFT-4 follow-up」+ §1.2 Sprint 1B mid 3 carry-over table 升 4 row（新增 PA-DRIFT-4 entry：bybit_rest_client + bybit_private_ws wrapper 層 instrumentation 4-6 hr E1 IMPL；Wave 2 main.rs 接 ApiLatencySourceProbe trait 前必 closed；blocks AC-1b real PG empirical，不阻 AC-1a scaffold sign-off）+ 反模式 (c) (d) 補 emitter 不修 bybit wrapper / trait 抽象不直接 import bybit client |
| Track F MED-1 position_count_active ladder | M3 spec §2.3 line 106 risk_envelope row 全 4 band 補 `position_count_active 0-8 / 9-16 / >16` literal + CRITICAL band 不含 position_count_active 註腳（位數本身不致命，致命層由 cum_pnl / dd / concentration 反映；對齊 risk_config max_open_positions 16 上限）+ dispatch packet §7.4 AC-2 補 position_count_active ladder fire test 範圍 |

E1 Wave 2 round 2 combined fix land：Track D 6 fix + Track E 3 fix + Track F 1 fix + Cross-Wave OBSERVE-4 fix（Track A scaffold round X：M3Error::ReplaySubprocessForbidden variant + MetricEmitterScheduler.run startup guard + run_domain_loop per-tick guard + StrategyQualityScheduler.run + tick guard 雙 scheduler 對齊 + 12 caller site cascade update `let _ = ...` + 新 integration test `tests/m3_emitter_replay_forbidden.rs` 3 test PASS）。

commit chain `ffb7ed48` (Wave 2 round 2 + OBSERVE-4 cross-Wave fix) + `4d7d12c9` (Phase 3b E4 regression closure)。

### 2.6 Phase 3b — E4 regression（E4 single / 4-6 hr / 0.5 day）

| 維度 | 結果 |
|---|---|
| `cargo test --workspace --release` (skip `stress_tick_latency_benchmark` Mac flaky) | **3894 / 0 / 4 ignored × 2 runs non-flaky** |
| `cargo test --release --test sprint2_track_a_engine_runtime` | **9 / 9 PASS** |
| `cargo test --release --test sprint2_track_b_pipeline_throughput` | **5 / 5 PASS** |
| `cargo test --release --test sprint2_track_c_database_pool` | **8 / 8 PASS** |
| `cargo test --release --test sprint2_track_d_api_latency` | **7 / 7 PASS** |
| `cargo test --release --test sprint2_track_e_strategy_quality` | **11 / 11 PASS** |
| `cargo test --release --test sprint2_track_f_risk_envelope` | **8 / 8 PASS** |
| `cargo test --release --test m3_emitter_replay_forbidden` | **3 / 3 PASS** |
| 6 Track + cross-Wave OBSERVE-4 合計 | **51 / 51 PASS** |
| `cargo test --release --features spike --test m3_amp_cap_24h_fire` | **3 / 3 PASS** (Sprint 1A-ζ baseline 不退) |
| `cargo test --release --lib health::` | **87 / 0 PASS** (Sprint 1A-ζ 10 + Sprint 2 77) |
| `cargo test --release --lib governance::lal::` | **15 / 0 PASS** (Sprint 1A-ζ baseline 不退) |
| `cargo check --target aarch64-apple-darwin --release` | clean (0 error / 0 new warning / 1 pre-existing dead_code unrelated) |
| Mac `pytest -q --tb=no` (non-flaky two runs) | **6042 pass / 28 pre-existing fail / 45 skipped**（兩遍同；vs Sprint 1A-ζ baseline 6037 → +5 Sprint 1B Rust binding land）|
| AC-7 cross-lang Python fixture | **7 / 7 PASS** |
| AC-7 cross-lang Rust binding | **5 / 5 PASS** (vs Sprint 1A-ζ PoC 級已升 FULL PASS) |
| nm symbol scan AC-5 | **0 hit** (`mock_instant|tokio::time::pause|spike` production binary 0 滲透) |
| `stress_tick_latency_benchmark` isolated (bisect) | **43-50μs** vs target 100μs (3 run non-flaky)；workspace 並行模式 CPU contention 拉至 163-228μs 屬假陽性 → SOP carry-over `--skip stress_tick_latency_benchmark` |
| Linux sandbox sandbox_admin role + V106 schema 確認 | E3 Sprint 1A-ε P1 IMPL sandbox_admin role 仍 land；V106 19 column 完整 + engine_mode CHECK 4 值 (paper/demo/live_demo/live) 不含 'replay' PG 層 fail-loud |

**Phase 3b verdict**：**PASS** — Sprint 2 Wave 1+2 combined 6 Track + cross-Wave OBSERVE-4 ready for Phase 3c QA empirical driver.

### 2.7 Phase 3c — QA empirical verify（QA single / 4-6 hr / 0.5 day）

per Sprint 2 design spec §7 AC-1a/AC-1b/AC-2/AC-3/AC-4/AC-5/AC-6/AC-7 + OBSERVE-4：

| AC | Spec literal | Empirical 結果 | Verdict |
|---|---|---|---|
| **AC-1a** | in-memory `HealthObservationWriter` mock fixture cargo test 5-sample window × N metric tick ≥ N×5 row | 6 Track integration test 51/51 PASS（Track A 9 + B 5 + C 8 + D 7 + E 11 + F 8 + replay_forbidden 3）對齊 dispatch packet AC-1a 預期 | **PASS** |
| **AC-1b** | Phase 3c QA 跑 real PG SQL；30 min window engine_runtime row count ≥ 5 | PARTIAL → **DEFER to Sprint 4 first Live deploy window**：三證一致確認 main.rs scheduler 未接（`grep MetricEmitterScheduler::new src/` production code 0 caller / Linux engine binary nm grep 0 hit / sandbox health_observations COUNT(*) = 0）；前置 = (1) main.rs 接 `MetricEmitterScheduler::run` + `StrategyQualityScheduler::run` (2) PA-DRIFT-4 bybit_rest_client + bybit_private_ws instrumentation IMPL (3) Linux runtime --rebuild (4) ≥ 30 min 樣本累積 | **PARTIAL** (符合 dispatch packet §1.6.1 拆分契約預期) |
| **AC-2** | 6 Track 4-state ladder fire（OK→WARN dwell 60s + WARN→DEGRADED dwell 5min real fire） | 6 ladder test PASS：Track A 6 metric × 4 band + Track B 4 metric ladder + heartbeat_lag_ms CRITICAL > 60000ms 即時 fire + Track C 5 metric (含 pool_max_conn 5th column) + Track D 8 metric × 4 band（4 含 CRITICAL）+ Track E per-pair OK→WARN→DEGRADED + aggregate 0.40 threshold + Track F position_count_active 0-8/9-16/>16 對齊 M3 spec §2.3 line 106 amend + dd / corr / top1 / cum_pnl | **PASS** |
| **AC-3** | amp cap 24h-suppression regression（spike Track B baseline 不退） | spike test 3/3 PASS：test_amp_cap_different_anomaly_id_not_suppressed + test_m3_amp_cap_24h_fire + test_stub_domains_fail_loud | **PASS** |
| **AC-4** | cross-domain independence（每 Track 升 DEGRADED 不影響其他 5 domain state） | 5 cross_domain test PASS：test_sprint2_cross_domain_api_latency_independence + test_sprint2_cross_domain_database_pool_independence + test_sprint2_cross_domain_pipeline_engine_independence + test_sprint2_cross_domain_risk_envelope_independence + test_sprint2_cross_domain_strategy_quality_independence | **PASS** |
| **AC-5** | production binary 0 mock time 滲透（`nm ... | grep mock_instant|tokio::time::pause|spike | wc -l = 0`） | nm scan 0 hit；strings scan 0 hit；binary footprint 19425968 bytes (~18.5 MB) 0 spike feature 滲透 | **PASS** |
| **AC-6** | cargo + pytest baseline 不退 | per E4 Phase 3b report 已確認：cargo workspace 3894/0 + pytest 6042/28 兩遍 non-flaky + health:: 87/0 + governance::lal:: 15/0 + cross-lang Python 7/7 + Rust binding 5/5；QA 本次 sanity recheck health:: 87/0 重跑確認對齊 | **PASS** |
| **AC-7** | cold start binary footprint `cargo bench --bench m3_emitter_cold_start` 進入 first tick ≤ 50ms | **OPEN-CARRY-OVER**：`rust/openclaw_engine/Cargo.toml` 只有 `hot_path_baseline` + `intent_processor_exposure` 兩 bench；`m3_emitter_cold_start` bench file 不存在；engine binary 不是 CLI 工具（無 `--version` 路徑進入 service loop；time engine --version 不是 AC-7 measurement）；QA 不重新發明 measurement 方法 → defer 到 Sprint 5 cascade IMPL 階段 IMPL bench fixture | **OPEN** |
| **OBSERVE-4** | M3 emitter 嚴禁在 replay subprocess 內 emit health_observations row；PG V106 engine_mode CHECK 不含 'replay' + Rust scaffold double scheduler startup + per-tick guard | m3_emitter_replay_forbidden 3/3 PASS：test_metric_emitter_scheduler_replay_engine_mode_forbidden + test_strategy_quality_scheduler_replay_engine_mode_forbidden + test_metric_emitter_scheduler_non_replay_engine_mode_ok_startup（paper/demo/live_demo/live 4-mode startup OK）+ Linux sandbox 實證 V106 engine_mode CHECK 4 值不含 'replay' | **PASS** |

QA 4 carry-over confirmed + 1 NEW QA-5（AC-7 bench fixture）：

| # | Item | Status | Resolution path |
|---|---|---|---|
| QA-1 | AC-1b real PG empirical (30 min window row count ≥ 5) | PARTIAL → DEFER | Sprint 4 first Live deploy window |
| QA-2 | m3_emitter_replay_forbidden.rs:31 unused async_trait import warning | OPEN (P3 LOW cosmetic) | E1 1 行 diff cosmetic clean |
| QA-3 | PA-DRIFT-4 bybit_rest_client + bybit_private_ws instrumentation 補位 | OPEN (P1) | E1 IMPL 4-6 hr；Wave 2 main.rs 接 ApiLatencySourceProbe trait 前必 closed；不阻 AC-1a scaffold sign-off；阻 AC-1b real PG empirical |
| QA-4 | E4 workspace regression SOP `--skip stress_tick_latency_benchmark` | OPEN (P2) | PM SOP 加進 regression-testing-protocol skill |
| **QA-5** | AC-7 `cargo bench --bench m3_emitter_cold_start` 未 IMPL | OPEN (P2) | E4 / E1 IMPL bench fixture；defer 到 Sprint 5 cascade IMPL 階段 |

PA spec amend driver 9 個檢點對齊 9/9（per QA Phase 3c report §10）：

1. ApiLatencySample 8 field 結構：`api_latency.rs:110-124` ✅
2. api_latency 8 metric × 4 band 含/不含 CRITICAL：8 classify_* fn line 241-412 ✅
3. 8 anomaly_id literal 命名 `api_latency__<metric_name>`：into_metric_rows line 174-209 ✅
4. ApiLatencySourceProbe trait 抽象 + Arc<dyn> 注入 + 8 method `_60s_window` 後綴：line 477-494 ✅
5. position_count_active 0-8/9-16/>16 不含 CRITICAL：risk_envelope.rs:102 + 162 + 282 ✅
6. OBSERVE-4 M3Error variant + scaffold-level guard：health/mod.rs:96 + 雙 scheduler startup + per-tick guard 雙層 ✅
7. PG V106 engine_mode CHECK 不含 'replay'：Linux sandbox 實證 ✅
8. PA-DRIFT-4 carry-over acknowledge in doc comment：api_latency.rs module 頭 line 62-72 ✅
9. spec literal reference 在 IMPL doc comment：api_latency.rs × 4 處 + risk_envelope.rs × 2 處 全引 M3 spec §2.3 line 104/106 amend reference + Track A scaffold ReplaySubprocessForbidden doc 引 Sprint 2 spec §1.x OBSERVE-4 ✅

commit `be70da06` (Phase 3c QA empirical closure)。

**Phase 3c verdict**：**PASS WITH 1 EXPECTED CARRY-OVER**（AC-1b PARTIAL by-design per dispatch packet §1.6.1 拆分契約預期；不阻進入 Phase 3d TW Acceptance Report）。

---

## §3 6 Track Acceptance

### 3.1 Track A — engine_runtime baseline 升級 + scaffold owner + D3 cascade reject

**Acceptance verdict**：**PASS**（per Phase 3b E4 regression + Phase 3c QA empirical）

| Item | 結果 |
|---|---|
| sysinfo "0.32" workspace 依賴 land | rust/Cargo.toml + rust/openclaw_engine/Cargo.toml；MSRV 1.74 對齊本機 rustc 1.95；跨平台原生 Mac+Linux（per `project_mac_deployment_target`）；Cargo.lock 自動更新 14 transitive dep |
| Track A scaffold 7 item 全 land（Track B-F unblock 條件）| DomainEmitter trait + MetricSample trait + RollingWindowAggregator (5 sample Bessel sigma) + HealthObservationWriter trait + InMemoryHealthObservationWriter + PgHealthObservationWriter + HealthEventBus + HealthStateChangeEvent + HealthEventSubscriber + observe_classified API + previous_state / state_entered_at / domain accessor + MetricEmitterScheduler tokio task wrapper + EngineModeProvider closure type |
| EngineRuntimeEmitter 6 metric（per Sprint 2 spec §3.2）| cpu_pct (sysinfo backed) / rss_mb / fd_pct / event_loop_lag_p95_ms / scheduler_tick_skew_ms / disk_io_util_pct；6 metric × 5 sample = 30 V106 row tick；Mac sysctl + Linux procfs fallback (`feedback_cross_platform`) |
| D3 cascade reject log emit minimal IMPL（per operator D3 decision）| `run_domain_loop` Ok(false) 分支推斷 reject_reason；`infer_reject_reason` pub helper（DRY，Track B-F 沿用）；2 reason：`amp_cap_>=2_fail_closed` + `amp_cap_same_anomaly_24h_suppress`；V106 row INSERT with evidence_json；不接 Slack / Console badge / halt strategy / 降 LAL Tier（Sprint 5/7/8 才接）|
| HealthStateMachine 升級 7 transition（per spec §5.1）| 升階 OK→WARN dwell 60s（對齊 §3.3 line 165 SSOT）+ WARN→DEGRADED dwell 5min + DEGRADED→CRITICAL dwell 5min + 降階 WARN→OK dwell 15min recovery + DEGRADED→WARN dwell 30min recovery + flap suppression 24h 內 3 次 lock 至 WARN + amp cap 3 guard 嚴格 fire 語意 |
| cross-Wave OBSERVE-4 scaffold round X land | `M3Error::ReplaySubprocessForbidden` variant + MetricEmitterScheduler.run startup guard + run_domain_loop per-tick guard + StrategyQualityScheduler.run + tick guard 雙 scheduler 對齊 + 12 caller site cascade `let _ = ...` + `tests/m3_emitter_replay_forbidden.rs` 3 test PASS + V106 PG CHECK 雙層 fail-loud |
| Integration test `sprint2_track_a_engine_runtime` | **9 / 9 PASS** |

**E2 review verdict**：round 1 REJECT 6 finding → E1 round 2 5 deterministic fix → round 2 APPROVE。
**QA empirical**：AC-1a in-memory proxy PASS + AC-2 ladder PASS + AC-3 spike regression PASS + AC-5 nm 0 hit。
**LOC**：metric_emitter/mod.rs 1324 LOC + writer.rs 464 LOC + event_bus.rs 202 LOC + health/mod.rs 990 LOC（升級 +272）= scaffold ~2280 LOC（含 8 unit test + 5 integration test；超 packet §1.7 估 500 LOC scaffold IMPL，因含完整 ladder transition matrix + EngineRuntimeEmitter sysinfo 接線 + cross-Wave OBSERVE-4 fix）。

### 3.2 Track B — pipeline_throughput

**Acceptance verdict**：**PASS**

| Item | 結果 |
|---|---|
| `health/domains/pipeline_throughput.rs` 5 metric | tick_rate (per_sec) / ipc_roundtrip_ms_p99 / heartbeat_lag_ms / ws_subscription_drift_count / strategy_signal_rate_per_min |
| ladder 對齊 M3 spec §2.3 line 102 amend | OK / WARN / DEGRADED / CRITICAL 4 band 全 5 metric land；heartbeat_lag_ms `> 60_000 ms → CRITICAL` 即時 fire（per E2 round 1 HIGH-1 revert）+ drift threshold `0/1-2/3+` + signal_rate `≥0.5/0.1-0.5/<0.1`（per PA Wave 1 spec amend MEDIUM-1 ladder land） |
| metric classify ≠ SM band dwell 區分（per §2.3.1 new section）| classify helper 即時返 band；SM dwell 60s/5min 由 observe_classified 走 ladder transition；不在 classify 內混雜 dwell 邏輯 |
| sample_now wire-up | StubSourceProbe 注入；Track B 不接 production probe（屬 Wave 2 main.rs 接 PipelineThroughputSourceProbe trait 階段 carry-over） |
| Integration test `sprint2_track_b_pipeline_throughput` | **5 / 5 PASS** |

**E2 review verdict**：round 1 REJECT (HIGH-1 + HIGH-2 + MEDIUM-1 + 2 LOW) → E1 round 2 1 deterministic + 3 PA-dependent → PA spec amend land 後 E1 round 3 doc 對齊 → round 2 APPROVE。
**QA empirical**：AC-2 ladder fire PASS + AC-4 cross-domain independence PASS。

### 3.3 Track C — database_pool

**Acceptance verdict**：**PASS**

| Item | 結果 |
|---|---|
| `health/domains/database_pool.rs` 5 metric | pg_pool_active_conn_ratio (active/pool_max) + pg_pool_wait_ms_p95 + pg_writer_queue_depth + disk_data_dir_used_pct + pg_pool_max_conn (telemetry-only 5th column per PA Wave 1 spec amend MEDIUM-1 C Path A) |
| DatabasePoolSample 5 field（per PA spec amend）| `pg_pool_max_conn: u32` 由 caller 注入（DatabaseConfig::pool_max_connections）；sqlx PgPool 未暴露 max accessor，emitter 不可強行 hack |
| disconnected fail-closed OK band（per PA Wave 1 spec amend MEDIUM-3 Path A）| max=0 → ratio 不計算 → OK band；disconnected evidence_json 寫 `{"pool_status": "disconnected"}` 留 audit trail；不誤升 CRITICAL 避激進 cascade 副作用（真實 PG 斷線由 cascade event 接：engine_runtime PID dead / pipeline_throughput WS dropout / 既有 5-gate kill） |
| classify_aggregated 補 3 arm（per E2 round 1 HIGH-1 fix）| `(HealthDomain::DatabasePool, "pg_pool_wait_ms_p95")` + `(HealthDomain::DatabasePool, "pg_writer_queue_depth")` + `(HealthDomain::DatabasePool, "disk_data_dir_used_pct")`；補 `pg_pool_active_conn_ratio` 1 arm（per E1 round 3 PA-dependent fix）= 4 arm 全展開 |
| classify_aggregated `mean.round() as u32` cast（per Track A round 2 MEDIUM-2 fix DRY pattern）| count 類 metric mean=2.8 round=3 為 DEGRADED；truncate=2 誤歸 WARN |
| Integration test `sprint2_track_c_database_pool` | **8 / 8 PASS**（含 disconnected fail-closed evidence + DEGRADED-band stress + cross-domain independence） |

**E2 review verdict**：round 1 REJECT (HIGH-1 + HIGH-2 + MEDIUM-1 + MEDIUM-2 + MEDIUM-3 + LOW) → E1 round 2 3 deterministic + 2 PA-dependent → PA spec amend land 後 E1 round 3 5th column 接入 + disconnected fail-closed 路徑 land → round 2 APPROVE。
**QA empirical**：AC-2 ladder fire PASS + AC-4 cross-domain independence PASS + disconnected fail-closed OK band 對齊 V106 spec §1.1 fail-closed 設計。

### 3.4 Track D — api_latency

**Acceptance verdict**：**PASS WITH 1 CARRY-OVER**（PA-DRIFT-4 bybit_rest_client + bybit_private_ws instrumentation 屬 Wave 2 main.rs 接 ApiLatencySourceProbe trait 前必 closed；不阻 AC-1a scaffold sign-off；阻 AC-1b real PG empirical）

| Item | 結果 |
|---|---|
| `health/domains/api_latency.rs` 8 field（per Sprint 2 spec §3.2 + M3 spec §2.3 line 104 amend）| rest_p50_ms / rest_p95_ms / rest_p99_ms / ws_rtt_p50_ms / ws_rtt_p99_ms / ret_code_4xx_count / ret_code_5xx_count / ws_dropout_count；8 metric × 4 band ladder |
| 4 含 CRITICAL：rest_p99 > 2000ms / ws_rtt_p99 > 1500ms / ret_5xx > 20 / ws_dropout > 5 | 反映 outlier / venue fault / 持續斷線 — 即時 fail-closed cascade 預警語意（per ADR-0042 Decision 3）|
| 4 不含 CRITICAL：rest_p50 / rest_p95 / ws_rtt_p50 / ret_4xx | 反映常態退化 — 不誤升 CRITICAL，由 5xx / p99 / dropout 三 metric 走 cascade gate 即足；對齊 Track B 同 pattern（heartbeat / ipc 走 CRITICAL；tick_rate / drift / signal 不走 CRITICAL）|
| ApiLatencySourceProbe trait + Arc<dyn> 注入 | 8 method 全加 `_60s_window` 後綴（per E2 round 1 HIGH-2 Option C type-level 契約 fix）：caller 端 IMPL 必須返過去 60s sample window 內的當前統計（rolling-window 語意），不可返 since-restart cumulative count / total-life percentile；type-level 契約 enforce 不靠注釋紀律 |
| 8 anomaly_id literal 命名 | `api_latency__rest_p50_ms` / `api_latency__rest_p95_ms` / `api_latency__rest_p99_ms` / `api_latency__ws_rtt_p50_ms` / `api_latency__ws_rtt_p99_ms` / `api_latency__ret_code_4xx_count` / `api_latency__ret_code_5xx_count` / `api_latency__ws_dropout_count` |
| ret_code 4xx/5xx 用 HTTP 標準語意 | 預留 multi-venue per ADR-0040 + dispatch packet §5.5 反模式 (d)（trait 抽象不直接 import bybit client） |
| PA-DRIFT-4 follow-up acknowledge in module 頭注釋 | bybit_rest_client + bybit_private_ws p95 / retCode / ws dropout source hook 為 Wave 2 main.rs 接 ApiLatencySourceProbe trait 時補；本 Track 端不修 client 既有邏輯（per packet §5.5 反模式 (a) (c)）|
| Integration test `sprint2_track_d_api_latency` | **7 / 7 PASS** |

**E2 review verdict**：round 1 REJECT (CRIT-1 + 3 HIGH + 2 MED + 1 LOW) → E1 round 2 5 deterministic + 1 PA-dependent → PA Wave 2 spec amend land 後 doc comment 對齊 → round 2 APPROVE-WITH-CONDITIONS。
**QA empirical**：AC-2 8 metric × 4 band ladder PASS + AC-1a in-memory proxy 8 metric × 5 sample = 40 row PASS + PA-DRIFT-4 acknowledge in doc comment 9/9 對齊 ✅。

### 3.5 Track E — strategy_quality（最高工時）

**Acceptance verdict**：**PASS**

| Item | 結果 |
|---|---|
| `health/domains/strategy_quality.rs` 5 field（per Sprint 2 spec §3.2 + M3 spec §2.1 line 82）| strategy_name (String) + symbol (String) + fill_rate_intent_ratio + slippage_bps_p95 + decision_lease_grant_rate + dormant_minutes (u32) + signal_count_24h (u32) |
| 4 metric × 4 band classify helper | fill_rate_intent_ratio OK > 0.80 / WARN 0.60-0.80 / DEGRADED 0.20-0.60 / CRITICAL < 0.20 + slippage_bps_p95 OK < 5 / WARN 5-10 / DEGRADED > 10（不雙觸 cascade）+ decision_lease_grant_rate OK > 0.70 / WARN 0.50-0.70 / DEGRADED 0.10-0.50 / CRITICAL < 0.10 + dormant_minutes OK < 60 / WARN 60-120 / DEGRADED 120-360 / CRITICAL > 360 |
| signal_count_24h telemetry-only fallback OK band | 對齊 M3 spec line 105「per-strategy 30d block bootstrap」threshold pending Sprint 5 |
| 25 pair × 4 metric = 100 SM + 1 aggregate SM | StrategyQualityScheduler::new 預建 per_pair_sms HashMap 3-tuple (strategy, symbol, metric) → SM；aggregate SM 獨立 |
| aggregate rule pair-level OR-aggregate Path A（per E2 round 1 HIGH-1 fix）| spec §3.4 line 211「DEGRADED 策略數 / 總策略數」是 2-tuple (strategy, symbol) pair-level SSOT 非 3-tuple per_pair_sms.len() count；fix 修法：迭代 per_pair_sms 按 (strategy, symbol) tuple grouping；一個 pair 任一 metric SM = DEGRADED/CRITICAL → 該 pair 標 degraded；total_count = unique pair 數 25；degraded_count = degraded pair 數；DEGRADED 0.40 threshold 對 unique pair 數而非 SM 總數 |
| 3 boundary test 守 HIGH-1 fix 不退化 | (1) 11 pair × 1 metric DEGRADED → ratio 11/25 = 0.44 > 0.40 升 DEGRADED (2) 10 pair × 4 metric DEGRADED → ratio 10/25 = 0.40 ≤ 0.40 留 OK（OR-aggregate 4 metric 重複計仍 10）(3) 4 pair × 4 metric DEGRADED → ratio 4/25 = 0.16 < 0.40 留 OK |
| aggregate SM anomaly_id by-band 命名 | aggregate__warn / aggregate__degraded / aggregate__critical 三條獨立 cap；避 same-anomaly 24h cap 阻擋 OK→WARN→DEGRADED ladder |
| 獨立 StrategyQualityScheduler（per spec §4.4 line 638-643 明文）| sample_interval_sec = 300s (5 min)；獨立 cancel token；OBSERVE-4 startup + per-tick guard 與 MetricEmitterScheduler 對齊 |
| per_pair_independence test expand 100 SM 全覆蓋（per E2 round 1 LOW-1 fix）| 25 pair × 4 band metric = 100 SM 全 fire 成功 = 真實獨立守住 |
| `per_pair_sm_count` 拆 `per_metric_sm_count` + `pair_count` 2 accessor（per E2 round 1 LOW-3 fix）| 名稱誤導 closure |
| Integration test `sprint2_track_e_strategy_quality` | **11 / 11 PASS** |

**E2 review verdict**：round 1 REJECT (1 HIGH + 3 LOW) → E1 round 2 3 deterministic + 3 boundary test → round 2 APPROVE-WITH-CONDITIONS。
**QA empirical**：AC-2 per-pair + aggregate 0.40 threshold PASS + AC-4 cross-domain independence PASS + OBSERVE-4 StrategyQualityScheduler replay block PASS。
**LOC**：strategy_quality.rs 1489 LOC + test 851 LOC = ~2340 LOC（含 10 lib mod test + 11 integration test；> 800 警告，< 2000 hard cap）。

### 3.6 Track F — risk_envelope

**Acceptance verdict**：**PASS WITH 1 CARRY-OVER**（PA-DRIFT-5 RiskEnvelopeSourceProbe wire-up 屬 Wave 2 main.rs 接線階段 carry-over；risk_verdict_ledger + position_snapshot SSOT calculator 接線）

| Item | 結果 |
|---|---|
| `health/domains/risk_envelope.rs` 5 field（per Sprint 2 spec §3.2 + M3 spec §2.1 line 82 + line 106 amend）| portfolio_cum_pnl_24h_usd + portfolio_max_dd_pct + position_count_active (u32) + correlation_avg_pairwise + concentration_top1_pct |
| ladder 1:1 對齊 M3 spec §2.3 line 106 amend | position_count_active OK 0-8 / WARN 9-16 / DEGRADED > 16（不含 CRITICAL；對齊 risk_config max_open_positions 16 上限）+ cum_pnl / max_dd / corr / top1 全 4 band（含 CRITICAL）|
| position_count_active 不含 CRITICAL band 註腳 | 位數本身不致命，致命層由 cum_pnl / dd / concentration 反映；對齊 PA Wave 2 spec amend MEDIUM-1 拍板 |
| RiskEnvelopeSourceProbe trait + Arc<dyn> 注入 | StubSourceProbe 注入；production probe 待 PA-DRIFT-5 Wave 2 main.rs 接 risk_verdict_ledger + position_snapshot SSOT calculator |
| Track F push back vs user prompt 7 metric | governance docs SSOT 5 metric（PA Sprint 2 spec §3.2 + M3 spec §2.1 line 82 + ADR-0042 Decision 3 + dispatch packet §7 + §2.1 line 233 land 2026-05-22）；user prompt 多 3 metric (portfolio_var_pct / leverage_avg / margin_util_pct) + 把 position_count_active 替換為 portfolio_var_pct 屬 spec drift；Track F IMPL 1:1 對齊 spec 5 metric design；多 3 metric 標 Track F+1 / Sprint 5+ 擴展點待 PM 決定 PA spec amend 路徑 |
| sample_interval_sec | 300s (5 min；與 Track E 對齊；不 1s tight loop 避過量 V106 row 寫入 + 對齊 risk_verdict_ledger 更新節奏) |
| emit DEGRADED 不觸 5-gate kill | Track F closure scope：emitter 只觀測，不修 risk_verdict_ledger / position_snapshot / fill_writer 既有邏輯（per dispatch packet §7.5 反模式 (a)）；threshold ladder 1:1 對齊 M3 spec §2.3 line 106；Sprint 5 才同步降 LAL Tier / halt strategy / 5-gate kill |
| Integration test `sprint2_track_f_risk_envelope` | **8 / 8 PASS** |

**E2 review verdict**：round 1 APPROVE-WITH-CONDITIONS (1 MED + 2 LOW) → E1 round 2 1 doc fix → round 2 APPROVE-WITH-CONDITIONS。
**QA empirical**：AC-2 position_count_active 0-8/9-16/>16 ladder + dd/corr/top1/cum_pnl PASS + AC-4 cross-domain independence PASS。
**LOC**：risk_envelope.rs 848 LOC + test 705 LOC = ~1553 LOC（> 800 警告，< 2000 hard cap）。

---

## §4 Cross-cutting Acceptance

### 4.1 ADR alignment（ADR-0042 + ADR-0040 不 amend）

| ADR | 對齊 verdict | 證據 |
|---|---|---|
| **ADR-0042** M3 health domain taxonomy 6 enum + 4-state ladder + amp cap | ✅ aligned；governance authority 不 amend | V106 CHECK enum 6 domain + Rust HealthDomain enum 6 variant + Sprint 2 spec §3.2 6 Track × DomainEmitter trait + M3 design spec §2.1 + §2.3 三方一致；Decision 3 (6 domain) + Decision 4 (amp cap 嚴格 fire 語意) + Decision 6 (cascade reject log) Sprint 2 D3 minimal IMPL 對齊 |
| **ADR-0040** multi-venue extensibility | ✅ aligned；不 amend | Track D api_latency 8 field 用 HTTP 標準語意（ret_code 4xx/5xx）+ trait 抽象 Arc<dyn ApiLatencySourceProbe> + 8 method `_60s_window` 後綴 type-level 契約 = 預留 multi-venue 不繞 Bybit-primary |
| **ADR-0034** M1 LAL Layered Approval Lease | ✅ aligned；Sprint 2 D3 cascade reject 不繞 LAL | Track A D3 cascade reject log emit minimal IMPL 不接 halt strategy / 不降 LAL Tier；Sprint 5/7/8 才接（per operator D3 decision）|
| **ADR-0044** M7 decay enforced single authority | ✅ aligned；M3 emitter 不寫 decay_signals / strategy_lifecycle | M3 是 observation layer，emit V106 row 不寫 M7 decay state；對齊 Sprint 1A-ζ M11 dedup contract baseline |

PA Wave 1+2 spec amend 全 M3 design spec §2.3 line 102/103/104/106 ladder 細化 + §2.3.1/§2.3.2/§2.3.3 新節 + Sprint 2 spec §3.2/§4.3/§5.0/§6.2 patch + dispatch packet §1.7 OBSERVE-4 + §5.x / §7.x AC patch；ADR-0042 governance authority 0 amend；ADR governance scope 維持 v1.0。

### 4.2 PA spec amend 9/9 對齊 + AC-1a/AC-1b 拆分契約

PA spec amend driver 9 個檢點對齊 9/9（per QA Phase 3c report §10）：

| # | 檢點 | spec literal | IMPL 對應 | 對齊 |
|---|---|---|---|---|
| 1 | ApiLatencySample 8 field 結構 | Sprint 2 spec §3.2 + M3 spec §2.3.3 | `api_latency.rs:110-124` | ✅ |
| 2 | api_latency 8 metric × 4 band 含/不含 CRITICAL | M3 spec §2.3 line 104 amend + §2.3.3 | 8 `classify_*` fn line 241-412 | ✅ |
| 3 | 8 anomaly_id literal 命名 | Sprint 2 spec §6.2 | `into_metric_rows` line 174-209 | ✅ |
| 4 | ApiLatencySourceProbe trait + Arc<dyn> + 8 method `_60s_window` 後綴 | E2 HIGH-2 Option C type-level 契約 | `api_latency.rs:477-494` | ✅ |
| 5 | position_count_active 0-8/9-16/>16 不含 CRITICAL | M3 spec §2.3 line 106 amend | `risk_envelope.rs:102 + 162 + 282` | ✅ |
| 6 | OBSERVE-4 M3Error variant + scaffold-level guard | Sprint 2 spec §5.0 + M3 spec §1.78 OBSERVE-4 invariant | `health/mod.rs:96` + 雙 scheduler startup + per-tick guard | ✅ |
| 7 | PG V106 engine_mode CHECK 不含 'replay' | V106 schema spec line 38 + §4.4 | Linux sandbox 實證 4 值 | ✅ |
| 8 | PA-DRIFT-4 carry-over acknowledge in doc comment | dispatch packet §5.5 反模式 (c)(d) | api_latency.rs module 頭 line 62-72 | ✅ |
| 9 | spec literal reference 在 IMPL doc comment | E1 round 2 doc comment | api_latency.rs × 4 處 + risk_envelope.rs × 2 處 全引 spec amend reference | ✅ |

AC-1a / AC-1b 拆分契約（per PA Wave 1 packet AC-1 split fix）：

- **AC-1a**（Wave 1/2 scaffold sign-off）：cargo test `test_sprint2_track_*` PASS；in-memory `HealthObservationWriter` mock fixture 驅動 5 sample window × N metric tick → ≥ N×5 V106 row written 至 mock writer；不需 main.rs scheduler 接線 / 不需 real PG。Track A 明示 6 metric × 5 sample = 30 row tick；其餘 Track N×5 row pattern 不寫死 metric 個數避綁定 E1 IMPL choice。
- **AC-1b**（Sprint 4+ first Live real PG empirical）：Phase 3c QA 跑 real PG SQL；前置 = (1) main.rs 接 `MetricEmitterScheduler::run` + `StrategyQualityScheduler::run` (2) PA-DRIFT-4 bybit_rest_client + bybit_private_ws instrumentation IMPL (3) Linux runtime --rebuild (4) ≥ 30 min 樣本累積；scaffold sign-off 不 block；6 Track 並行 sign-off 不繞此前置。

### 4.3 OBSERVE-4 cross-Wave invariant

**OBSERVE-4 design intent**：M3 emitter 嚴禁在 replay subprocess 內 emit health_observations row。

**為什麼 fail-loud**（per Sprint 2 design spec §5.0 + M3 spec §1.78 OBSERVE-4 invariant line 199-216）：

- V106 line 259 `engine_mode CHECK IN ('paper','demo','live_demo','live')` 不含 'replay'；replay row 直接撞 PG CHECK constraint，PG error → sqlx 失敗 → audit trail 撕裂
- 設計合約：M3 health 是 read-only consumer of replay path（M11 replay 自身屬 dry-run，不該觸發 health observation row）；replay subprocess 誤 emit = 設計違反 → fail-loud Err 讓 caller 立即看到
- 對齊 V106 spec line 38 + §4.4 設計刻意：replay engine_mode 不在 V106 CHECK 4 值 white-list

**雙層 fail-loud enforcement**：

| Layer | Enforcement | grep verify |
|---|---|---|
| PG V106 `engine_mode` CHECK | `IN ('paper','demo','live_demo','live')` 不含 'replay' | Linux sandbox 實證 ✅ |
| Rust `M3Error::ReplaySubprocessForbidden` variant | `health/mod.rs:96` | ✅ |
| Rust `MetricEmitterScheduler::run` startup guard | `health/metric_emitter/mod.rs:596` | ✅ |
| Rust `MetricEmitterScheduler` per-tick guard | `health/metric_emitter/mod.rs:731-735` | ✅ |
| Rust `StrategyQualityScheduler::run` startup guard | `health/domains/strategy_quality.rs:708` | ✅ |
| Rust `StrategyQualityScheduler` per-tick guard | `health/domains/strategy_quality.rs:725-732` | ✅ |

**OBSERVE-4 by scaffold 統一 enforce**：scaffold-level guard 必在 6 Track 共用 writer 入口（DRY 原則），Track D/E/F 不獨立 guard。Track A scaffold round X land `M3Error::ReplaySubprocessForbidden` variant + 雙 scheduler startup + per-tick guard + 12 caller site cascade update + `tests/m3_emitter_replay_forbidden.rs` 3 integration test PASS。

### 4.4 Production Safety

| Item | 結果 |
|---|---|
| 0 `unsafe` block in production path | ✅ 6 Track + scaffold 全 safe Rust |
| 0 `unwrap()` in production happy path | ✅ Err 分支前 drop lock guard（per Track A round 2 MEDIUM-1 fix DRY pattern；observe_at `if let Some(seen)` 結構取代 unwrap）|
| 0 panic on happy path | ✅ cargo workspace 3894/0 fail；6 Track integration 51/51 PASS；OBSERVE-4 fail-loud 走 Err 不 panic |
| spike feature `--features spike` default off | ✅ `Cargo.toml [features] default = []` / `spike = []`；production binary `cargo build --release` 不帶 `--features spike` → mock time + test harness 0 滲透 production code path |
| production engine 不重啟 | ✅ PID 2934602 跑 trading_ai (全程未碰)；sandbox-only verify per Q2(d) operator decision；real PG empirical AC-1b 延 Sprint 4 first Live deploy window |
| AC-5 production binary 0 mock time 滲透 | ✅ nm symbol scan `grep -E "(mock_instant|tokio::time::pause|spike)" | wc -l = 0`；strings scan 0 hit；binary footprint 19425968 bytes (~18.5 MB) |
| 0 hardcoded path | ✅ `feedback_cross_platform`：sysinfo 0.32 跨平台原生 Mac+Linux；唯一 platform-specific path `read_open_fd_count` 在 Mac 走 fallback 返 0 fail-closed，不破 cross-platform 部署；cargo check --target aarch64-apple-darwin --release clean 0 error |
| 0 hard boundary 觸碰 | ✅ M3 emitter 不創新 order 寫入口 / 不寫 live state / 不繞 Decision Lease / 不動 5-gate / 不寫 authorization.json / 不動 risk_verdict_ledger SSOT calculator |

### 4.5 16 根原則 cross-check（spike 範圍對齊）

per CLAUDE.md §二 16 條根原則：

| # | 原則 | Sprint 2 對齊 |
|---|---|---|
| 1 | 單一寫入口 | Sprint 2 不創新 order 寫入口；V106 writer 唯一入口 + OBSERVE-4 guard 強化 ✅ |
| 2 | 讀寫分離 | M3 emitter 只讀 metric / write V106 audit row；不寫 live state ✅ |
| 3 | AI ≠ 命令 | M3 emitter 是 pure metric observation + classify rule；無 AI 介入 ✅ |
| 4 | 策略不繞風控 | M3 emitter 不繞 Guardian；emit DEGRADED 不觸 5-gate kill；Sprint 5 才同步降 LAL Tier ✅ |
| 5 | 生存 > 利潤 | position_count_active 不含 CRITICAL band（避位數誤升 CRITICAL 觸過激 cascade）+ disconnected fail-closed OK band（不誤升 CRITICAL）✅ |
| 6 | 失敗默認收縮 | OBSERVE-4 guard fail-loud（replay subprocess emit 拒收）+ amp cap 嚴格 fire 語意 3 guard + disconnected fail-closed OK band + cascade catch separation ✅ |
| 7 | 學習 ≠ live | M3 emitter 不寫 live state；V106 audit row 不影響 trading 路徑 ✅ |
| 8 | 交易可解釋 | D3 cascade reject log emit minimal IMPL 寫 V106 row evidence_json reject_reason；audit trail 完整 ✅ |
| 9 | 雙重防線 | OBSERVE-4 雙層 fail-loud（PG V106 CHECK + Rust scaffold guard）；amp cap 3 guard 嚴格 fire 語意 ✅ |
| 10 | 事實 / 推斷 / 假設分離 | 6 Track IMPL report 寫「empirical evidence = ...」/「inferred from = ...」/「assumed = ...」三分；Track F push back vs user prompt 7 metric 揭露 governance docs SSOT 與 prompt drift ✅ |
| 11 | P0/P1 內自主 | Sprint 2 不擴 P0/P1 邊界 ✅ |
| 12 | evidence-based 演化 | PA spec amend 9/9 driven by E2 round 1 finding empirical；Track E aggregate pair-level OR-aggregate Path A 由 E2 catch 真實 bug 揭露 ✅ |
| 13 | cost 感知 | 8 metric × 60s sample + 5 metric × 300s sample 不額外 hot path；ratio classify 一 sample 一次計算 ✅ |
| 14 | 零外部成本 | Sprint 2 全 self-hosted；sysinfo 0.32 crates.io 公開；無 vendor 依賴 ✅ |
| 15 | 多 agent 形式化 | Sprint 2 chain：PA Phase 1 × 1 + E1 × 6 Track 並行 + E2 × 6 Track 並行 + E4 Phase 3b × 1 + QA Phase 3c × 1 + TW Phase 3d × 1 + PM Phase 3e（pending）= 形式化 chain 對齊 CLAUDE.md §八 ✅ |
| 16 | portfolio > 孤立 trade | risk_envelope 5 metric (position_count_active + corr + top1 + dd + cum_pnl) 全 portfolio metric 同時觀測 ✅ |

**結論**：16/16 對齊；Sprint 2 0 violation。

### 4.6 Multi-Session Race Mitigation（per `feedback_fetch_before_dispatch` + `project_multi_session_memory_race`）

| Phase | 並行 sub-agent | 主會話 | Race 結果 |
|---|---|---|---|
| Phase 1 | PA single | PM | 0 race |
| Phase 2 Wave 1 | Track A/B/C E1 並行（3）+ Sprint 1B mid 0-3 並行 | PM | 0 race（git commit --only narrow staging + working_branch hint 隔絕；Track A scaffold owner 24h 內 land 公共依賴 + stagger 5min dispatch）|
| Phase 3a Wave 1 | Track A/B/C E2 並行（3）+ PA spec amend single | PM | 0 race（Phase 2 結束才 Phase 3a 起跑 + PA spec amend land 中 E1 round 3 待 PA land 後對齊）|
| Phase 2 Wave 2 | Track D/E/F E1 並行（3）| PM | 0 race（Track E 觀察 HEAD `6f6bbea8` 於本 session 開工 2 分鐘前 land Track D/E/F 並行 commit；本 session E1 IMPL 寫入後 working tree 與 HEAD diff = 0，意味本 session 與並行 E1 instances 寫出完全等價內容；commit-first / 不認識改動禁 revert 紀律守住）|
| Phase 3a Wave 2 | Track D/E/F E2 並行（3）+ PA Wave 2 spec amend single | PM | 0 race |
| Phase 3b-3d | E4 / QA / TW single 各串行 | PM | 0 race |

**7 sub-agent ceiling** check：Phase 2 Wave 1 + Wave 2 不同步（peak 3 並行 / max 6-7 sub-agent within frame 屬 Wave 1 唯一 tight 階段）；其餘階段全 healthy 餘量。

---

## §5 Lessons Learned

### 5.1 E2 對抗性 review catch 真實 bug

per `feedback_impl_done_adversarial_review` 2026-05-09 + Sprint 1A-ζ Phase 3a Track B/C 範式延續：

| Track | E2 round 1 catch 真實 bug | 若 E4 regression 單獨跑會否 catch |
|---|---|---|
| Track A HIGH-1 D3 cascade reject_reason false positive | guard 1（same anomaly suppress）優先於 guard 3（fail-closed >=2）邏輯；same anomaly + count=2 場景應回 guard 1 reason `amp_cap_same_anomaly_24h_suppress` 不應誤標 `amp_cap_>=2_fail_closed` | NO — E4 regression test 不檢 evidence_json reject_reason literal；單跑 cargo test 看 row count + state band 全 PASS |
| Track A HIGH-2 recovery dwell anchor 升階方向不對稱清理（5 domain 通用 bug）| observe_classified 升階 5 條 + 同 state 高 band 採樣 reset recovery_band_seen_at；原 IMPL 只在降階 reset，升階時 stale anchor 殘留導致下次升階後降階 recovery dwell 從 stale anchor 起算 | NO — E4 regression 不模擬 升階 → 降階 → 升階 → 降階 多次往返 sequence；單跑 ladder fire test 只測 OK→WARN→DEGRADED 線性升階 |
| Track D CRIT-1 ApiLatencySample 5→8 field schema drift | E1 IMPL 已 land 8 field 但 Sprint 2 spec §3.2 + M3 spec §2.3 line 104 仍 5 field literal；對齊路徑 = PA Wave 2 spec amend land 8 metric × 4 band 全規範 | E4 regression catch（cargo test FAIL 對齊舊 5 field）但不會自動 amend spec；PA 介入仲裁是否 revert IMPL 或 amend spec |
| Track E HIGH-1 aggregate pair-level OR-aggregate denominator | spec §3.4 line 211「DEGRADED 策略數 / 總策略數」是 2-tuple (strategy, symbol) pair-level SSOT 非 3-tuple per_pair_sms.len() count；原 IMPL bug：total_count = 100 (25 × 4)；degraded_count 走 per-SM 累加，11 個 metric DEGRADED 就觸 0.40 threshold，但實際只壞了 11/100 = 11% 的 SM | NO — E4 regression 不檢 aggregate denominator 語意；單跑 aggregate fire test 只測「ratio > 0.40 升 DEGRADED」boolean 結果 |

**結論**：E2 對抗式 review 與 E4 regression test **互補**而非可替代。Sprint 2 Wave 1+2 round 1 共 catch 16+ finding（Track A 6 + Track B 5 + Track C 6 + Track D 7 + Track E 4 + Track F 3）；全 round 2 IMPL closure；無 carry-over CRITICAL / HIGH 至 Phase 3b/3c。

### 5.2 PA spec amend 配合 E1 round 2 重要性（Track C 流程 vs Track D drift 對比）

**Track C 流程**（spec drift caught early by E2 round 1）：

- E2 round 1 REJECT MEDIUM-1 pool_max_conn 5th column drift / MEDIUM-3 disconnected fail-closed Path A vs B 未決 → 2 條 spec-dependent finding
- PA Wave 1 spec amend land Path A（5th column + fail-closed OK band）
- E1 round 3 PA-dependent fix：5th column 接入 + disconnected evidence_json 寫入路徑
- E2 round 2 APPROVE

**Track D drift**（spec drift caught late by E2 round 1 CRIT-1）：

- E1 round 1 IMPL 已 land 8 field（reality）但 Sprint 2 spec §3.2 + M3 spec §2.3 line 104 仍 5 field literal（governance source of truth）
- E2 round 1 catch CRIT-1 schema drift；E1 IMPL 不 revert 路徑 = spec 對齊 IMPL（PA Wave 2 spec amend land 8 metric × 4 band 全規範）
- PA-DRIFT-4 bybit instrumentation prerequisite false（grep verify 0 hit）catch late at E2 round 1

**對比結論**：

- 早期 PA spec amend caught by E2 round 1 = 對齊代價低（E1 round 3 PA-dependent fix ~0.5 hr doc comment + 接入 5th column ~1 hr）
- 晚期 spec drift = 對齊代價高（PA Wave 2 spec amend ~1-1.5 hr land 2 file 7 edit + dispatch packet 5 edit + E1 round 2 6 fix combined）
- 治本：dispatch packet land 前 PA + E1 IMPL prototype catch spec ↔ IMPL drift；Sprint 5 cascade IMPL 前 PA → E1 IMPL prototype 一輪試跑（per Sprint 1A-ζ IMPL Prototype Spike 範式延續）

### 5.3 OBSERVE-4 cross-Wave invariant 由 scaffold 統一 enforce

**為什麼 OBSERVE-4 屬 Track A scaffold round X（per Wave 2 spec amend MEDIUM-1 fix）**：

- E2 round 1 Track D catch MEDIUM-1：OBSERVE-4 replay subprocess guard 真實存在於 Sprint 2 spec line 199-216；但 dispatch packet §1.7 Track A scaffold contract 漏列 guard 為必交付項
- 修法：屬 Track A scaffold round X 工作；新 test `tests/m3_emitter_replay_forbidden.rs` 屬 E4 regression suite；scaffold guard 必在 6 Track 共用 writer 入口（DRY 原則），Track D/E/F 不獨立 guard
- IMPL：`M3Error::ReplaySubprocessForbidden` variant + `HealthObservationWriter::write` 入口 guard + 雙 scheduler（MetricEmitterScheduler + StrategyQualityScheduler）startup + per-tick guard + 12 caller site cascade update `let _ = ...` + 3 integration test PASS + V106 PG CHECK 雙層 fail-loud

**結論**：cross-Wave invariant 由 scaffold 統一 enforce（DRY），不重複 inline 邏輯且不漏 Track。Sprint 5 cascade IMPL 沿用此 pattern：cascade reject log emit / 降 LAL Tier / halt strategy / 5-gate kill 全走 Track A scaffold 入口，不在 6 Track inline。

### 5.4 Sub-agent IMPL DONE 必走 A3+E2 對抗性核驗 + ceiling 預警紀律

per `feedback_impl_done_adversarial_review` 2026-05-09 + `feedback_fetch_before_dispatch` 2026-04-24：

- Wave 1+2 6 Track E1 round 1 IMPL DONE → E2 round 1 catch 16+ finding（含 1 CRIT + 5 HIGH + 多 MEDIUM/LOW）→ E1 round 2 修補全 closure
- E4 regression 不能取代 E2 adversarial review（per §5.1 Track A HIGH-1/HIGH-2 + Track E HIGH-1 證明 E4 不會單獨 catch）
- Phase 2 Wave 1 peak 6-7 並行 sub-agent（Track A/B/C E1 × 3 + Sprint 1B mid 0-3 carry-over）為唯一 tight 階段；嚴守 stagger 5min dispatch + 不接受第 4 個並行請求；Wave 2 Wave 1 closure 後才開派 Track D/E/F

**結論**：Sprint 2 0 race / 0 commit drift / 0 git index race；對齊 Sprint 1A-ζ multi-session race protocol enforcement 範式。

### 5.5 Track F push back vs user prompt 7 metric — governance docs SSOT 紀律

**Track F E1 IMPL 對 user prompt 7 metric 版本 push back**：

- user prompt §「2. RiskEnvelopeSample struct」列 7 metric：cum_pnl_usdt / daily_drawdown_pct / portfolio_var_pct / concentration_top_n / correlation_avg / leverage_avg / margin_util_pct
- governance docs SSOT 5 metric（operator 2026-05-22 sign-off）：portfolio_cum_pnl_24h_usd / portfolio_max_dd_pct / position_count_active / correlation_avg_pairwise / concentration_top1_pct
- source order ruling per CLAUDE Operating Style 第 7 條 + `bilingual-comment-style` skill 「Source order」：governance docs (PA spec land + operator sign-off 2026-05-22) > user-prompt dispatch-time 修改
- 處置：Track F IMPL 1:1 對齊 spec 5 metric design；多 3 metric（portfolio_var_pct / leverage_avg / margin_util_pct）+ position_count_active 替換為 portfolio_var_pct 標 Track F+1 / Sprint 5+ 擴展點待 PM 決定 PA spec amend 路徑

**結論**：sub-agent 對 dispatch-time 修改 push back 揭露 governance docs SSOT 與 prompt drift；CLAUDE Operating Style 第 7 條（surface conflicts, choose newer or better-tested pattern）+ Source order skill 落地正確。Sprint 5 cascade IMPL 若要擴 7 metric 必走 PA spec amend 路徑（M3 spec §2.3 line 106 ladder + Sprint 2 spec §3.2 + ADR-0042 Decision 3 6 domain set 是否擴 risk_envelope sub-domain 由 PA + operator 拍板）。

### 5.6 Linux PG empirical AC-1b 拆分契約紀律

per `feedback_v_migration_pg_dry_run` 2026-05-05 + Sprint 1A-ζ V055 5-round loop precedent + Sprint 2 PA Wave 1 packet AC-1 split fix：

- AC-1a in-memory mock fixture cargo test PASS = Wave 1/2 scaffold sign-off 充分條件（不需 main.rs scheduler 接線 / 不需 real PG）
- AC-1b real PG empirical（30 min window row count ≥ 5）= Sprint 4 first Live deploy window 工作；前置 = main.rs wire-up + PA-DRIFT-4 bybit instrumentation + Linux runtime --rebuild + 30 min 樣本累積
- 三證一致確認 main.rs scheduler 未接：`grep MetricEmitterScheduler::new src/` production code 0 caller / Linux engine binary nm grep 0 hit / sandbox health_observations COUNT(*) = 0

**結論**：AC-1a / AC-1b 拆分契約為 Sprint 2 scaffold sign-off 與 Sprint 4 first Live real PG empirical 之間正確 boundary。Sprint 5 cascade IMPL 階段 main.rs 接 scheduler + PA-DRIFT-4 instrumentation 補位後才能跑 AC-1b real PG empirical；scaffold sign-off 不繞此前置。

---

## §6 Carry-over to Sprint 4+ / Sprint 5+

### 6.1 Sprint 4 first Live carry-over（4 條 P0 / P1）

| # | Item | Owner | Priority | 估時 | 阻塞 |
|---|---|---|---|---|---|
| **6.1.1** | **AC-1b real PG empirical**（30 min window engine_runtime row count ≥ 5；6 Track 全 N×5 row pattern empirical）| QA + E3 + E1 | P0 (Sprint 4 first Live deploy 時) | ~30 min 樣本累積 + 1 hr QA verify | 前置 6.1.2 + 6.1.3 + 6.1.4 |
| **6.1.2** | **main.rs scheduler 接線**（MetricEmitterScheduler::run + StrategyQualityScheduler::run；engine startup wire-up；EngineModeProvider closure 注入；CancellationToken 接 engine shutdown signal）| E1 | P0 (Sprint 4 first Live deploy 時) | 3-4 hr E1 IMPL + ~0.5 hr E2 review | 不阻 scaffold sign-off；阻 AC-1b real PG empirical |
| **6.1.3** | **PA-DRIFT-4 bybit_rest_client + bybit_private_ws instrumentation 補位**（5 工作項：(1) bybit_rest_client p50/p95/p99 latency tracker rolling 60s window (2) bybit_rest_client retCode 4xx/5xx counter rolling 60s window (3) bybit_private_ws RTT p50/p99 tracker (4) bybit_private_ws dropout counter (5) `ApiLatencySourceProbe` impl 接 bybit wrapper instrumentation）| E1 | P1 (Wave 2 main.rs 接 ApiLatencySourceProbe trait 前必 closed) | 4-6 hr E1 IMPL + 1 hr E2 review | 阻 AC-1b real PG empirical；不阻 AC-1a scaffold sign-off |
| **6.1.4** | **PA-DRIFT-5 RiskEnvelopeSourceProbe wire-up**（risk_verdict_ledger + position_snapshot SSOT calculator 接線；不修 risk_verdict_ledger 既有邏輯 per dispatch packet §7.5 反模式 (a)；只走 trait 抽象 + Arc<dyn> 注入）| E1 | P1 (Wave 2 main.rs 接 RiskEnvelopeSourceProbe trait 前必 closed) | 4-6 hr E1 IMPL + 1 hr E2 review | 阻 AC-1b real PG empirical；不阻 AC-1a scaffold sign-off |

**Sprint 4 deploy 順序**：6.1.2 main.rs wire-up + 6.1.3 PA-DRIFT-4 + 6.1.4 PA-DRIFT-5 並行 IMPL → engine restart_all --rebuild Linux runtime → ≥30 min 樣本累積 → 6.1.1 QA AC-1b real PG empirical verify。

### 6.2 Sprint 5+ cascade IMPL carry-over（4 條 P1 / P2）

| # | Item | Owner | Priority | 估時 | 阻塞 |
|---|---|---|---|---|---|
| **6.2.1** | **AC-7 cargo bench `m3_emitter_cold_start` fixture IMPL**（emitter scheduler `new` + `run` 進入 first tick wall-clock measurement；target ≤ 50ms cold start；rust/openclaw_engine/Cargo.toml 加 bench 入口）| E4 + E1 | P2 (Sprint 5 cascade IMPL 階段) | 3-4 hr bench fixture IMPL + 1 hr threshold tuning | 不阻 Sprint 5 cascade IMPL |
| **6.2.2** | **OBSERVE-4 fail-loud channel 統一**（per Track E E2 round 2 carry-over；6 Track 共用 fail-loud channel；scaffold-level guard 強化）| E1 | P1 (Sprint 5 cascade IMPL) | 4-6 hr E1 IMPL + 1 hr E2 review | 不阻 Sprint 5 cascade IMPL |
| **6.2.3** | **LOC peak 切檔**（api_latency.rs 952 LOC / strategy_quality.rs 1489 LOC / metric_emitter/mod.rs 1287-1324 LOC；全 > 800 警告 + < 2000 hard cap；Sprint 5 cascade IMPL 加 reject channel + halt strategy + 降 LAL Tier 路徑後預期 LOC 增）| E1 + E2 | P2 (Sprint 5 cascade IMPL) | 6-8 hr 重構 + 2 hr E2 review | 不阻 Sprint 5 cascade IMPL；Sprint 5 IMPL 前判斷是否觸 2000 hard cap |
| **6.2.4** | **Sprint 5 cascade reject log emit minimal 升級** = D3 minimal IMPL 升 full cascade（接 Slack notification + Console badge UI + halt strategy + 降 LAL Tier per AMD-2026-05-21-01 Layered Autonomy v2 §1.7）| E1 + GUI (A3) + E2 | P1 (Sprint 5 cascade IMPL) | 12-18 hr E1 IMPL + 8-10 hr GUI + 2 hr E2 review | Sprint 5 cascade IMPL dispatch readiness gate 開啟後 |

### 6.3 Doc + lint carry-over（3 條 P2 / P3）

| # | Item | Owner | Priority | 估時 |
|---|---|---|---|---|
| **6.3.1** | **m3_emitter_replay_forbidden.rs:31 unused `async_trait::async_trait` import warning cosmetic clean**（E2 Track E round 2 condition #2 + E4 Phase 3b QA-2 + QA Phase 3c QA-2 三方 confirm P3 LOW）| E1 | P3 LOW | 1 行 diff + 1 commit |
| **6.3.2** | **E4 workspace regression SOP `--skip stress_tick_latency_benchmark`**（isolated-only SLA bench 註腳新加到 `regression-testing-protocol` skill；E4 Phase 3b QA-4 carry-over）| PM SOP + TW | P2 | 0.5 hr skill patch + TW 註腳 |
| **6.3.3** | **注釋 spec reference 雙引述**（Track E E2 round 2 carry-over：spec §3.4 line 211 雙引述 spec §3.4 + spec line 669；補 doc comment 精準 line number reference）| E1 + TW | P3 LOW | 0.5 hr doc comment cleanup |

---

## §7 Sign-off

### 7.1 TW report write status

- **TW write DONE**：本報告 land path `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_overall_acceptance.md`
- **TW 不下 verdict**（per task 禁忌 + Sprint 1A-ζ Phase 3d 範式延續）；本報告彙整 Phase 0-3c 全部 verdict + carry-over；最終 verdict by PM Phase 3e

### 7.2 PM sign-off section（pending Phase 3e PM closure）

| # | Phase 3e 待 PM 拍板項 | 依據 |
|---|---|---|
| 1 | **Final verdict**：PASS WITH 5 CARRY-OVER（採 spec §5.1 PASS condition + Phase 3c QA report §11.1 PASS rationale 8/8 gate 全綠 + AC-1b PARTIAL by-design + AC-7 OPEN-CARRY-OVER）| Sprint 2 design spec §7 AC matrix + Phase 3c QA report §11 |
| 2 | **Sprint 5 cascade IMPL dispatch readiness gate**：OPEN（per Sprint 2 PASS verdict + Phase 3b E4 + Phase 3c QA + TW Phase 3d 彙整）vs DEFER（等 Sprint 4 first Live AC-1b empirical 確認）二選一 | Phase 3c QA report §14 Operator 下一步 + AMD-2026-05-21-01 v2 Layered Autonomy §1.7 |
| 3 | **5 carry-over 派發**：(a) Sprint 4+ first Live 4 條（6.1.1 AC-1b + 6.1.2 main.rs wire-up + 6.1.3 PA-DRIFT-4 + 6.1.4 PA-DRIFT-5）(b) Sprint 5+ cascade IMPL 4 條（6.2.1 AC-7 bench + 6.2.2 OBSERVE-4 fail-loud channel + 6.2.3 LOC peak 切檔 + 6.2.4 Sprint 5 cascade full IMPL）(c) Doc + lint 3 條（6.3.1 async_trait unused + 6.3.2 SOP skill patch + 6.3.3 注釋 spec reference）| §6.1 + §6.2 + §6.3 |
| 4 | **AC-1b PARTIAL 處置**：接受 by-design DEFER to Sprint 4 first Live deploy window（per dispatch packet §1.6.1 拆分契約預期）| Phase 3c QA report §2.2 verdict |
| 5 | **AC-7 OPEN-CARRY-OVER 處置**：接受 defer to Sprint 5 cascade IMPL 階段 IMPL bench fixture（QA 不重新發明 measurement 方法）| Phase 3c QA report §8 + §11.2 QA-5 |
| 6 | **TODO.md update**：Sprint 2 closure 條目 + 5 carry-over 條目 + Sprint 5 cascade IMPL dispatch readiness gate 條目 | per `docs/agents/todo-maintenance.md` |
| 7 | **PM commit**：本 TW report + TW memory append（PM 收口統一）| per CLAUDE.md §Git And Sync narrow staging |

### 7.3 Sign-off chain status

```
本報告 land (TW Phase 3d write DONE)                          ✅ 完成
        ↓
PM Phase 3e closure verdict + Sprint 5 cascade IMPL 派發 sign-off    ⏳ pending PM
        ↓
operator 親手 sign-off Sprint 5 cascade IMPL 派發 readiness          ⏳ pending operator
        ↓
Sprint 4 first Live deploy window AC-1b real PG empirical            ⏳ pending Sprint 4 deploy
```

### 7.4 Sprint 2 IMPL fingerprint

- 8 commit chain `81a2caeb → 788f8e99 → 2a7e2ae0 → 6152b01d → 6f6bbea8 → ffb7ed48 → 4d7d12c9 → be70da06` 全 PASS
- 51 sprint2 integration test = Track A 9 + B 5 + C 8 + D 7 + E 11 + F 8 + m3_emitter_replay_forbidden 3
- 3 spike integration test (m3_amp_cap_24h_fire + amp_cap_different_anomaly_id_not_suppressed + stub_domains_fail_loud) regression PASS（Sprint 1A-ζ baseline 不退）
- 8 PA spec amend land：Wave 1 4 amend（Track B HIGH-2 + MEDIUM-1 + Track C MEDIUM-1 + MEDIUM-3）+ Wave 2 4 amend（Track D CRIT-1 + MED-1 OBSERVE-4 + HIGH-3 PA-DRIFT-4 + Track F MED-1）+ packet AC-1a/AC-1b split fix
- 16+/16+ E2 finding closure（Wave 1 + Wave 2 round 1 catch 16+ finding；round 2 全 closure）
- M3Error::ReplaySubprocessForbidden variant 新加（scaffold 公共依賴 6 Track）
- 0 mock 業務邏輯（all in-memory `InMemoryHealthObservationWriter` writer + StubSourceProbe）
- 0 spike feature 滲透 production binary（nm 0 hit）
- 0 hard boundary 觸碰（不創新 order 寫入口 / 不寫 live state / 不繞 Decision Lease / 不動 5-gate / 不寫 authorization.json）

---

## §8 Appendix — Sprint 2 artifact + cross-reference 索引

### 8.1 Sprint 2 commit chain

| Commit | Phase | 內容 |
|---|---|---|
| `81a2caeb` | Phase 1 | PA Phase 1 readiness sign-off + dispatch packet land |
| `788f8e99` | Phase 2 Wave 1 | Track A scaffold IMPL（sysinfo "0.32" + DomainEmitter trait + RollingWindowAggregator + HealthObservationWriter + HealthEventBus + observe_classified + EngineRuntimeEmitter + D3 cascade reject）|
| `2a7e2ae0` | Phase 2 Wave 1 | Track B + Track C 並行 IMPL（pipeline_throughput + database_pool）|
| `6152b01d` | Phase 3a Wave 1 | Track A E2 round 1 REJECT → round 2 5 fix；Track B + Track C round 2 + round 3 PA-dependent fix；PA Wave 1 spec amend land（4 finding + AC-1a/AC-1b 拆分）|
| `6f6bbea8` | Phase 2 Wave 2 | Track D + Track E + Track F 3 並行 IMPL（api_latency + strategy_quality + risk_envelope）|
| `ffb7ed48` | Phase 3a Wave 2 | Wave 2 round 2 combined fix（Track D 6 + Track E 3 + Track F 1）+ Cross-Wave OBSERVE-4 fix（Track A scaffold round X：M3Error::ReplaySubprocessForbidden + 雙 scheduler guard + 12 caller site cascade + replay_forbidden test）；PA Wave 2 spec amend land |
| `4d7d12c9` | Phase 3b | E4 regression closure（cargo workspace 3894/0 + 6 Track integration 51/51 + cross-lang + cross-platform + nm 0 hit + Linux sandbox verify）|
| `be70da06` | Phase 3c | QA empirical closure（AC-1a/2/3/4/5/6 PASS + AC-1b PARTIAL DEFER + AC-7 OPEN-CARRY-OVER + OBSERVE-4 PASS + PA spec amend 9/9 對齊）|

### 8.2 Sprint 2 artifact 路徑索引

| Path | 用途 |
|---|---|
| `srv/rust/Cargo.toml` | workspace `sysinfo = "0.32"` 依賴 |
| `srv/rust/openclaw_engine/Cargo.toml` | `sysinfo = { workspace = true }` dep 引 |
| `srv/rust/openclaw_engine/src/health/mod.rs` | HealthStateMachine 升級 + observe_classified + try_dwell_then_transition + try_recovery_dwell + M3Error::ReplaySubprocessForbidden variant（line 96）|
| `srv/rust/openclaw_engine/src/health/metric_emitter/mod.rs` | DomainEmitter trait + MetricSample trait + RollingWindowAggregator + EngineRuntimeEmitter + classify_aggregated dispatch（22 arm）+ MetricEmitterScheduler + EngineModeProvider + OBSERVE-4 startup guard + per-tick guard + D3 cascade reject infer_reject_reason helper |
| `srv/rust/openclaw_engine/src/health/writer.rs` | HealthObservationWriter trait + PgHealthObservationWriter + InMemoryHealthObservationWriter + HealthObservationRow |
| `srv/rust/openclaw_engine/src/health/event_bus.rs` | HealthEventBus + HealthStateChangeEvent + HealthEventSubscriber |
| `srv/rust/openclaw_engine/src/health/domains/mod.rs` | sub-module 入口（pub mod pipeline_throughput / database_pool / api_latency / strategy_quality / risk_envelope）+ MODULE_NOTE |
| `srv/rust/openclaw_engine/src/health/domains/pipeline_throughput.rs` | PipelineThroughputEmitter + 5 metric classify helper + StubSourceProbe + inline test |
| `srv/rust/openclaw_engine/src/health/domains/database_pool.rs` | DatabasePoolEmitter + 5 metric classify helper（含 pool_max_conn 5th column + disconnected fail-closed OK band）+ StubSourceProbe + inline test |
| `srv/rust/openclaw_engine/src/health/domains/api_latency.rs` | ApiLatencyEmitter + 8 metric classify helper + ApiLatencySourceProbe trait（8 method `_60s_window` 後綴）+ StubSourceProbe + inline test |
| `srv/rust/openclaw_engine/src/health/domains/strategy_quality.rs` | StrategyQualityEmitter + 4 metric classify helper + StrategyQualitySourceProbe trait + StrategyQualityScheduler（獨立 scheduler；25 pair × 4 metric = 100 SM + 1 aggregate SM；pair-level OR-aggregate Path A）+ inline test |
| `srv/rust/openclaw_engine/src/health/domains/risk_envelope.rs` | RiskEnvelopeEmitter + 5 metric classify helper + RiskEnvelopeSourceProbe trait + StubSourceProbe + inline test |
| `srv/rust/openclaw_engine/tests/sprint2_track_a_engine_runtime.rs` | Track A 9 integration test（含 ladder / cascade reject / row count / scheduler）|
| `srv/rust/openclaw_engine/tests/sprint2_track_b_pipeline_throughput.rs` | Track B 5 integration test |
| `srv/rust/openclaw_engine/tests/sprint2_track_c_database_pool.rs` | Track C 8 integration test（含 disconnected fail-closed evidence + DEGRADED-band stress）|
| `srv/rust/openclaw_engine/tests/sprint2_track_d_api_latency.rs` | Track D 7 integration test（含 8 metric ladder） |
| `srv/rust/openclaw_engine/tests/sprint2_track_e_strategy_quality.rs` | Track E 11 integration test（含 pair-level OR-aggregate 3 boundary test + 100 SM independence）|
| `srv/rust/openclaw_engine/tests/sprint2_track_f_risk_envelope.rs` | Track F 8 integration test（含 position_count_active 4 band ladder）|
| `srv/rust/openclaw_engine/tests/m3_emitter_replay_forbidden.rs` | Cross-Wave OBSERVE-4 3 integration test（雙 scheduler replay block + 4-mode startup OK）|

### 8.3 Sprint 2 report 路徑索引

| Phase | Report path |
|---|---|
| Phase 1 PA readiness sign-off | `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_readiness_signoff.md` |
| Phase 3a PA Wave 1 spec amend | `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_wave1_m3_spec_amend.md` |
| Phase 3a PA Wave 1 packet AC-1 split fix | `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_wave1_packet_ac1_split_fix.md` |
| Phase 3a PA Wave 2 spec amend | `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_wave2_track_def_spec_amend.md` |
| Phase 2 Wave 1 Track A round 1 | `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave1_track_a_engine_runtime.md` |
| Phase 3a Track A round 2 fix | `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave1_track_a_round2_fix.md` |
| Phase 3a Wave 1 round 2 combined fix（Track A scaffold + Track B/C round 2）| `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave1_round2_combined_fix.md` |
| Phase 3a Wave 1 round 3 PA-dependent fix（Track B/C round 3）| `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave1_round3_pa_dependent_fix.md` |
| Phase 2 Wave 2 Track D | `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave2_track_d_api_latency.md` |
| Phase 2 Wave 2 Track E | `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave2_track_e_strategy_quality.md` |
| Phase 2 Wave 2 Track F | `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave2_track_f_risk_envelope.md` |
| Phase 3a Wave 2 round 2 combined fix（Track D 6 + E 3 + F 1 + OBSERVE-4 cross-Wave）| `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave2_round2_combined_fix.md` |
| Phase 3b E4 regression | `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-22--sprint_2_phase_3b_regression.md` |
| Phase 3c QA empirical | `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-22--sprint_2_phase_3c_qa_empirical_verify.md` |
| **Phase 3d TW Overall Acceptance**（本報告）| `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_overall_acceptance.md` |

### 8.4 spec doc 路徑索引

| Spec | Path |
|---|---|
| Sprint 2 design spec | `srv/docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md` |
| Sprint 2 dispatch packet | `srv/docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md` |
| M3 health monitoring design spec（含 §2.3 line 102/103/104/106 amend + §2.3.1/§2.3.2/§2.3.3 新節）| `srv/docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md` |
| V106 schema spec | `srv/docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md` |
| ADR-0042 M3 health monitoring（governance authority；不 amend）| `srv/docs/adr/0042-m3-health-monitoring.md` |
| ADR-0040 multi-venue extensibility（不 amend）| `srv/docs/adr/0040-multi-venue-extensibility.md` |
| ADR-0034 M1 LAL Layered Approval Lease（Sprint 5 cascade IMPL 接降 LAL Tier）| `srv/docs/adr/0034-decision-lease-layered-approval-lal.md` |
| ADR-0044 M7 decay enforced single authority（M3 emitter 不寫 decay_signals）| `srv/docs/adr/0044-m7-decay-enforced-single-authority.md` |
| AMD-2026-05-21-01 Layered Autonomy v2（§1.7 Sprint 5 cascade IMPL 派發 readiness gate）| `srv/docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md` |

---

**END Sprint 2 — M3 metric emitter Overall Acceptance Report**

**TW Phase 3d DONE** — report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_overall_acceptance.md`

**Phase 3e PM sign-off pending** — 待 PM 拍板 §7.2 7 條 sign-off item + 最終 verdict + Sprint 5 cascade IMPL 派發 readiness gate
