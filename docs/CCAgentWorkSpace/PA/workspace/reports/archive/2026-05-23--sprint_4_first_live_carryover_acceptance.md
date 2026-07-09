---
report: Sprint 4+ first Live carry-over — Overall Acceptance Report
date: 2026-05-23
author: TW (Technical Writer)
phase: Sprint 4+ Phase 3d (TW Acceptance)
sprint: Sprint 4+ first Live carry-over (Sprint 2 PM Phase 3e §4.1 4 items)
status: SIGNED-OFF-PENDING-PM
verdict: PASS WITH 8 CARRY-OVER（待 PM Phase 3e 拍板）
sprint_5_dispatch_readiness: PENDING per Phase 3e PM closure
parent specs / reports:
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_pm_phase_3e_signoff.md §4.1 4 items（Sprint 4+ 來源）
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_overall_acceptance.md（Sprint 2 closure 範式）
  - srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_4_pa_drift_5_risk_envelope_wireup.md（PA-DRIFT-5 round 1 IMPL）
  - srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint_4_pa_drift_4_bybit_instrumentation.md（PA-DRIFT-4 round 1 IMPL）
  - srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint_4_wave_a_round2_combined_fix.md（Wave A round 2 combined fix）
  - srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint_4_wave_b_main_scheduler_wireup.md（Wave B round 1 IMPL）
  - srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint_4_wave_b_round2_fix.md（Wave B round 2 fix）
  - srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-23--sprint_4_e4_regression_wave_ab.md（E4 regression PASS）
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_wave_b_m1_singleton_registry_ssot.md（M-1 Singleton Registry SSOT 建立）
  - srv/docs/architecture/singleton-registry.md（新 SSOT 主檔；6 singleton 完整 12 欄位登記）
scope: Sprint 4+ first Live carry-over 4 items 全閉合 TW 彙整 Phase 0-3c verdict + production V106 deploy + AC-1b real PG empirical 30 min sample wait + 5 active domain row count + carry-over 三類（Sprint 1B late / Sprint 5+ cascade IMPL / production 監測 follow-up）；TW 不下 verdict（最終 verdict by PM Phase 3e）
non-scope:
  - 不改業務邏輯（V106.sql / Rust IMPL）
  - 不寫 spec patch（carry-over enumeration only）
  - 不 commit（PM 收口統一）
  - 不派下游 sub-agent
  - 中文為主，0 emoji
---

# Sprint 4+ first Live carry-over — Overall Acceptance Report

## §1 Executive Summary

### 1.1 Sprint 4+ 範圍與起源

Sprint 4+ first Live carry-over 由 Sprint 2 PM Phase 3e sign-off §4.1 派出 4 條 P0/P1 item：

| # | Item | Owner | Priority |
|---|---|---|---|
| 1 | AC-1b real PG empirical（30 min window engine_runtime row ≥ 5）| QA + E3 | P0 Sprint 4 first Live gate |
| 2 | main.rs scheduler 接線（MetricEmitterScheduler::run + StrategyQualityScheduler::run）| E1 + E2 | P0 Sprint 4 |
| 3 | PA-DRIFT-4 bybit_rest_client + bybit_private_ws instrumentation 補位 | E1 | P1（blocks AC-1b）|
| 4 | PA-DRIFT-5 RiskEnvelopeSourceProbe wire-up | E1 | P1（blocks AC-1b）|

來源依據：
- Sprint 2 設計上 AC-1a/AC-1b 拆分契約（PA Sprint 2 Wave 1 packet AC-1 split fix）— AC-1a 為 in-memory mock fixture scaffold sign-off 條件；AC-1b 為 real PG empirical 必前置 main.rs wire-up + bybit/risk_envelope instrumentation。
- Sprint 2 Wave 2 Track D HIGH-3 揭露 `bybit_rest_client` + `bybit_private_ws` 既有 hook claim grep verify 0 hit，PA-DRIFT-4 carry-over 落地。
- Sprint 2 Wave 2 Track F E2 round 2 carry-over：`RiskEnvelopeSourceProbe` 5 method production wire-up 屬 Wave 2 main.rs 接線階段工作。

### 1.2 Phase chain 與時序

| Phase | 內容 | 時序 |
|---|---|---|
| Phase 1 dispatch | Sprint 2 PM Phase 3e §4.1 4 items 派發；PA spec amend driver 9 item 對齊已於 Sprint 2 結束時 land | 2026-05-22 |
| Phase 2 Wave A | PA-DRIFT-4 + PA-DRIFT-5 並行 IMPL round 1+2（commit `5acd36e6` + `4c84d1bb`）| 2026-05-22 ～ 2026-05-23 |
| Phase 2 Wave B | main.rs scheduler 接線 + 6 emitter spawn + PortfolioStateCache update task + emitter batch path + F-2 NaN sanitize round 1+2（commit `245216d1` + `4d4ff99f` + `82351b61`）| 2026-05-23 |
| Phase 3a E2 review | Wave A × 2 + Wave B × 1 共 3 條 E2 review round 1+2 全 APPROVE | 2026-05-23 |
| Phase 3b E4 regression | cargo workspace 3961/0 + pytest 6042/28 + Wave A+B 42 integration + Sprint 2 51/51 + spike 3/3 + nm 0 hit | 2026-05-23 |
| Phase 3c QA AC-1b | production V106 deploy（psql -f raw apply 走 sandbox 範式）+ emitter 即時 fire + 30 min sample wait + 5 active domain row count 20-264 | 2026-05-23 |
| Phase 3d TW（本 report）| Overall Acceptance Report 彙整 | 2026-05-23 |
| Phase 3e PM sign-off | TODO（PM 自接）| pending |

### 1.3 結果摘要

| 維度 | 結果 |
|---|---|
| **Verdict（TW 彙整）** | **PASS WITH 8 CARRY-OVER**（待 PM Phase 3e 拍板）|
| **§4.1 4 items closure** | 4/4 closed（AC-1b PASS / main.rs wire-up PASS / PA-DRIFT-4 PASS / PA-DRIFT-5 PASS） |
| **5 active domain × 30 min sample row count** | engine_runtime 264 / pipeline_throughput 220 / api_latency 176 / database_pool 110 / risk_envelope 20；total 770 row（遠超 ≥ 5 per domain 要求） |
| **strategy_quality row count** | 0（per Sprint 5+ wire-up scope 已知例外；不阻 Sprint 4+ closure） |
| **production V106 deploy** | DONE via `psql -f` raw apply（sandbox 範式）；engine_mode CHECK 4 值 + domain CHECK 6 值 + state CHECK 4 值全對齊 |
| **production engine** | PID 3654935（V106 raw apply 後 graceful restart）；etime 02:58+ 健康；emitter 5 active domain × 30 min fire ✓ |
| **engine_mode 觀測值** | `live_demo`（per `engine_mode_tag_live_demo` 2026-04-16 memory + V106 CHECK 4 值對齊）|
| **HEALTH_WARN observed** | 41 row engine_runtime__open_fd_count + 60 row api_latency__rest_p50/p95/p99 — production 真實觀測值；Sprint 5+ PA 評估 threshold 是否需 amend |
| **OBSERVE-4 cross-Wave invariant** | ✓ enforced — V106 engine_mode CHECK 不含 'replay' + Rust scaffold double scheduler startup + per-tick guard + 12 caller site cascade 守 |
| **6 new mutable singleton 登記** | ✓ SSOT 建立於 `docs/architecture/singleton-registry.md`（M-1 closure；Wave A 4 + Wave B 2 = 6 singleton 完整 12 欄位）|
| **production engine fail-soft** | V106 INSERT fail → `tracing::warn` 不 abort engine；revert `OPENCLAW_AUTO_MIGRATE=0` path 守 |
| **ADR ↔ spec ↔ IMPL 三層不對齊** | 0（ADR-0042 + ADR-0040 不 amend；M3 spec §2.3 + Sprint 2 spec §3.2 + 6 emitter wire-up 全對齊；singleton-registry.md cross-ref CLAUDE.md §七 + §九）|
| **Hard boundary 違反** | 0（emitter 不創 order 寫入口 / 不寫 live state / 不繞 Decision Lease / 不動 5-gate / 不寫 authorization.json）|
| **multi-session race** | 0（Wave A + Wave B 並行 commit chain 8 commit clean；commit-first + 不認識改動禁 revert）|
| **Wall-clock** | 1 day high-density dispatch（2026-05-23；Wave A 並行 IMPL + Wave B 接線 + 3 E2 review + E4 + AC-1b 30 min sample 同日全 closed）|

### 1.4 Sprint 5+ cascade IMPL runtime confidence

Sprint 4+ first Live carry-over closure 為 Sprint 5+ cascade IMPL 提供以下 runtime 信號：

- **M3 emit chain end-to-end alive**：production V106 emit chain 從 emitter scheduler → V106 row INSERT 5 active domain × 30 min ≥ 5 row 全段通；emit 行為對齊 ADR-0042 6 domain + 4-state ladder。
- **AC-1a/AC-1b 拆分契約完整覆蓋兩階段**：scaffold sign-off (Wave 1+2) 由 AC-1a in-memory mock 守；production sign-off (Sprint 4+) 由 AC-1b real PG empirical 守；兩階段不重複測 + 不漏 production deploy 路徑。
- **6 mutable singleton SSOT registered**：Sprint 5+ cascade IMPL 接 LAL Tier 降階 / halt strategy / Slack notification / Console badge UI 時，可直接從 SSOT 拿 caller_chain + handle exposer + lock_primitive 設計；無需 grep production code 重發現。
- **placeholder 半實裝 + carry-over 透明化**：WS half + Track B/C source / PortfolioStateCache update task 全標明 placeholder + 「30 天全 0 染色不代表真實健康」誠實揭露；Sprint 5+ wire-up scope 拍板有清晰邊界依據。
- **HEALTH_WARN 真實 production threshold 反映**：rest_p50/p95/p99 60 row + open_fd_count 41 row HEALTH_WARN 是 production 真實值觀測（非 placeholder 副作用）；PA 可基於 30 min × 多輪累積 sample 拍板 ladder threshold amend 路徑。

---

## §2 Phase 0-3c chronology + verdict

### 2.1 Phase 1 — dispatch（Sprint 2 PM Phase 3e §4.1）

來源：Sprint 2 PM Phase 3e Sign-off `2026-05-22--sprint_2_pm_phase_3e_signoff.md` §4.1。

派發 4 item：

```
1. AC-1b real PG empirical (30 min window engine_runtime row ≥ 5)
2. main.rs scheduler 接線 (MetricEmitterScheduler::run + StrategyQualityScheduler::run)
3. PA-DRIFT-4 bybit_rest_client + bybit_private_ws instrumentation 補位 (blocks AC-1b)
4. PA-DRIFT-5 RiskEnvelopeSourceProbe wire-up (blocks AC-1b)
```

Phase 1 prerequisite（Sprint 2 結束時 land）：
- M3 spec §2.3 line 104（api_latency 8 metric × 4 band 補齊 amend）+ §2.3.3 新節
- M3 spec §2.3 line 106 amend（position_count_active 0-8/9-16/>16 不含 CRITICAL）
- Sprint 2 spec §3.2 `ApiLatencySample` 5→8 field + §5.0 OBSERVE-4 新節
- dispatch packet §1.7 OBSERVE-4 Track A scaffold contract + §5.5 反模式 (d) multi-venue gate 預留
- ADR-0042 6 domain + 4-state ladder + amp cap 24h-suppression governance authority（不 amend）

### 2.2 Phase 2 Wave A — PA-DRIFT-4 + PA-DRIFT-5 並行 IMPL（round 1+2）

per E1 Wave A round 1 + round 2 combined fix report：

#### Wave A round 1（commit `5acd36e6`）

| Track | Module | File | 結果 |
|---|---|---|---|
| **PA-DRIFT-4** | bybit instrumentation 5 工作項 | `bybit_rest_client.rs` (+336 LOC RestLatencyHistogram + RetCodeCounter + 14 method) + `bybit_private_ws.rs` (+281 LOC WsRttHistogram + WsDropoutCounter + 6 dropout 接點 + ping/pong RTT) + 新 `health/domains/api_latency_probe_impl.rs` 204 LOC RealApiLatencySourceProbe + 8 trait method impl + 2 inline test + 新 `tests/api_latency_probe_real_impl.rs` 350 LOC 15 integration test | Round 1 IMPL DONE：4 instrumentation singleton + 8 method trait probe；4xx/5xx 對映規則含 10001-10006/10010 client fault + 110xxx venue fault；6/8 接點 dropout（主動 cancel 排除 per ADR-0042 cascade gate venue fault only） |
| **PA-DRIFT-5** | RiskEnvelopeSourceProbe wire-up 7 工作項 | 新 `health/domains/risk_envelope_probe_impl.rs` 698 LOC PortfolioStateCache + 5 SSOT calculator + RealRiskEnvelopeSourceProbe + 16 inline test + 新 `tests/risk_envelope_probe_real_impl.rs` 408 LOC 11 integration test | Round 1 IMPL DONE：4 真實 hook（cum_pnl_24h_usd / max_dd_pct_24h / position_count_active / concentration_top1_pct）+ 1 placeholder（correlation_avg_pairwise 0.0 per dispatch §7.5 反模式 (c) + E2 Track F round 2 對抗反問 #2 carry-over）|

#### Wave A round 2（commit `4c84d1bb`）

per E2 round 1 verdict：PA-DRIFT-4 REJECT（1 HIGH BLOCKER + 2 HIGH + 3 MED + 3 LOW）；PA-DRIFT-5 APPROVE-WITH-CONDITIONS（2 MED + 2 LOW）。

E1 round 2 closure 6 finding：

| Finding | 修法 |
|---|---|
| **PA-DRIFT-4 H-1 BLOCKER** noop retCode（110001/110008/110010/110043/170213）誤計 5xx | `record_for_error` + `is_noop_retcode` helper（複用 `BybitRetCode::is_noop()` SSOT）+ 2 integration test `skips_noop_retcodes` + `noop_does_not_affect_real_venue_fault` |
| **PA-DRIFT-4 H-2** 60s rolling window expire 0 test | 4 instrumentation 各加 `inject_sample_with_timestamp` test-only accessor（pub + `#[doc(hidden)]` + release optimizer auto-drop verified）+ 4 boundary test（59s 內 / 61s 外）|
| **PA-DRIFT-4 H-3** retCode 觀測覆蓋率 < 50% | 觀測下沉 `get`/`post` 內部 + `_checked` 簡化避雙重計 + integration test `raw_caller_pattern_records_via_internal_observer` |
| **PA-DRIFT-4 M-1** checked_sub fallback 注釋誤導 | 補 boot < 60s edge case 行為說明 11 LOC 注釋 |
| **PA-DRIFT-5 F-1** cap=100k comment 失誤 | 選項 (a) 改注釋為「24h × push rate 隱式上限；無顯式 cap」（無業務邏輯改動）|
| **PA-DRIFT-5 F-3** 5-lock gap micro-race window | trait 加 default `snapshot_5_metric()` + `RiskEnvelopeSampleSnapshot` struct + `PortfolioStateCache::snapshot_5_metric` + `RealRiskEnvelopeSourceProbe::snapshot_5_metric` override 一次 lock + backward compat 既有 StubSource 走 default impl |

**E2 Wave A round 2 verdict**：PA-DRIFT-4 **APPROVE** / PA-DRIFT-5 **APPROVE + F-2 升 P1 Wave B condition**。

### 2.3 Phase 2 Wave B — main.rs scheduler 接線（round 1+2）

per E1 Wave B round 1 + round 2 fix report：

#### Wave B round 1（commit `245216d1`）

新檔 `main_health_emitters.rs`（528 LOC；6 emitter 構造 helper + scheduler spawn + update task spawn）+ main.rs 接線（+55 LOC，base 1448 → 1503）。

6 emitter wire-up status：

| Track | Source | Wave B status |
|---|---|---|
| A engine_runtime | sysinfo 30s 真實 | **real** |
| B pipeline_throughput | ws_client / IndicatorEngine / IPC stats placeholder closure（全 0；Sprint 5+ wire-up）| **placeholder** |
| C database_pool | sqlx PgPool real + sysinfo Disks real + writer_queue/pool_wait_p95 placeholder closure | **hybrid** |
| D api_latency | REST half real（shared_client `latency_histogram_handle()` + `ret_code_counter_handle()`）+ WS half placeholder（fresh 0-state Arc 因 `BybitPrivateWs::new()` 內部 own Arc，外部無穩定注入點）| **hybrid** |
| E strategy_quality | per dispatch §NOT in scope；Sprint 5+ wire-up | **skip** |
| F risk_envelope | `RealRiskEnvelopeSourceProbe` + `PortfolioStateCache` real（4 真實 + 1 correlation placeholder）| **real** |

PortfolioStateCache 300s update task：placeholder no-op tick（now_ms 推進 + equity=0 + 空 fills/exposures）；F-2 NaN/inf sanitize 守線在 cache `update_from_pipeline_snapshot` 內部執行（realized_pnl / equity / notional 三類 NaN/inf 各自 skip + fail-loud warn）。

emitter sample_now 走 F-3 batch path 切換（`RiskEnvelopeEmitter::sample_now` 走 `source.snapshot_5_metric()` 一次 lock）；既有 StubSource / mock 走 trait default backward compat。

OBSERVE-4 guard propagate：`scheduler.run` startup `Err(M3Error::ReplaySubprocessForbidden)` 直接 propagate；main.rs `tokio::spawn` 端 match Err 寫 `tracing::error` 不 swallow。

新 `tests/main_scheduler_wireup.rs`（394 LOC，6 integration test）：scheduler startup 4 legal mode / replay fail-loud / batch path / 3 emitter 並行 / writer dispatch / replay + risk_envelope。

#### Wave B round 2（commit `4d4ff99f`）

per E2 Wave B round 1 verdict：REJECT（1 HIGH + 2 MEDIUM + 3 LOW）。

E1 round 2 closure 5 finding（MEDIUM-1 由 PA 收口）：

| Finding | 修法 |
|---|---|
| **HIGH-1** Track B placeholder 5 metric 全 0 走 DEGRADED 染色（tick_rate / signal_rate 兩 metric 觸 < 0.5 / < 0.1 DEGRADED ladder）| 5 default 改 spec line 102 OK band 合法值：tick_rate=2.0 / signal_rate=1.0 / ipc_p99=1.0 / heartbeat=0 / drift=0；inline test 擴 5 metric value + classify=HealthOk assertion |
| **MEDIUM-1** 6 new mutable singleton 未登記 SSOT（grep 0 hit）| 升 PM 收口時派 PA — 由 PA Singleton Registry SSOT 建立 task（commit follow-up）closure；本 round 2 不擴 scope |
| **MEDIUM-2** Track D WS half emit chain disconnected from production supervisor | 採用 (a) doc 補注路徑：`main_health_emitters.rs:126-131` 25 line 揭露「fresh 0-state Arc 永遠不會被 production WS run loop 觀測」+ V106 全 0 row 是 placeholder 副作用而非健康指標；(b) supervisor signature 改造 carry-over Sprint 5+ |
| **LOW-1** E1 round 1 report LOC 數值不一致 | 本 round 2 report §3.1 + §5 列 wc -l 實測；round 1 report 保歷史 trace 不回填編輯 |
| **LOW-2** emitter_count hardcoded 5 | `emitters.len()` 動態 capture（在 Vec move 進 scheduler 前讀 len()）|
| **LOW-3** TODO healthcheck entry 缺 | TODO.md §5.1 P1 queue 加 `W-S4-AC1B-HEALTHCHECK` entry（review_date 2026-05-24 + SQL acceptance condition + 前置條件對齊 commit chain）|

**E2 Wave B round 2 verdict**：**APPROVE-WITH-CONDITIONS**（MEDIUM-1 SSOT 建立由 PA 走完整路徑，commit `82351b61` land `docs/architecture/singleton-registry.md` + `docs/README.md` index）。

### 2.4 Phase 3a — E2 review × 3 round 1+2 全 APPROVE

| Track | Round 1 finding | Round 2 verdict |
|---|---|---|
| **PA-DRIFT-4** | REJECT (1 HIGH BLOCKER + 2 HIGH + 3 MED + 3 LOW) | **APPROVE** |
| **PA-DRIFT-5** | APPROVE-WITH-CONDITIONS (2 MED + 2 LOW; F-2 升 P1 Wave B condition) | **APPROVE** |
| **Wave B** | REJECT (1 HIGH + 2 MEDIUM + 3 LOW) | **APPROVE-WITH-CONDITIONS** (MEDIUM-1 SSOT 建立由 PA 走) |

3 E2 review 全 catch 真實 production-blocking bug：H-1 noop retCode 誤計 + H-2 60s expire 0 test + H-3 觀測覆蓋率 < 50% + HIGH-1 placeholder DEGRADED 染色 — 全產 production V106 row 數值錯誤；非紙上指標。

### 2.5 Phase 3b — E4 regression（commit `82351b61`）

per E4 regression report：

| 維度 | 結果 |
|---|---|
| `cargo test --workspace --release` × 2 non-flaky | **3961 / 0 / 5 ignored**（baseline 3894 → +67 attribution Wave A+B integration 42 + lib health +23 + sibling drift +2 對齊預期）|
| `cargo test --release --test api_latency_probe_real_impl` | **22 / 22 PASS**（Wave A PA-DRIFT-4 含 4 boundary test）|
| `cargo test --release --test risk_envelope_probe_real_impl` | **14 / 14 PASS**（Wave A PA-DRIFT-5 含 3 batch read test）|
| `cargo test --release --test main_scheduler_wireup` | **6 / 6 PASS**（Wave B）|
| `cargo test --release --test sprint2_track_*` × 6 + `m3_emitter_replay_forbidden` | **51 / 51 PASS** baseline 不退 |
| `cargo test --release --features spike --test m3_amp_cap_24h_fire` | **3 / 3 PASS**（Sprint 1A-ζ amp cap baseline 不退）|
| `cargo test --release --lib health::` | **110 / 110 PASS**（Sprint 2 baseline 87 → +23 Wave A+B real-impl sub-module）|
| `cargo test --release --lib bybit_rest_client` | **29 / 29 PASS** |
| `cargo check --target aarch64-apple-darwin --release` | clean 0 error / 4 既有 deprecated/dead_code warning 非 Wave A+B 引入 |
| Mac pytest × 2 non-flaky | **6042 pass / 28 pre-existing fail / 45 skipped**（兩遍同；baseline 不退）|
| Cross-lang fixture | **12 / 12 PASS**（7 Python PoC + 5 Rust binding）|
| nm AC-5 scan `mock_instant\|tokio::time::pause\|spike` | **0 hit** ✓ production binary 0 mock time / spike 滲透 |
| Wave B inject_* symbol leak | **0 hit** ✓ release optimizer drop unused pub method |
| strings scan Wave A+B wire-up symbol | ✓ 全命中（main_health_emitters / risk_envelope_probe_impl / api_latency_probe_impl / F-2 sanitize log 字串 / Wave B replay guard 字串 / V106 emit topic）|
| Linux sandbox sandbox_admin role + V106 schema confirm | ✓ E3-MED-1 / Sprint 1A-ε P2 closure 後 active；V106 6 domain CHECK + 4 engine_mode CHECK + 4 state CHECK 完整 |
| pg_hba E3-MED-1 reject row | ✓ sandbox_admin 誤入 production DB 仍 FATAL reject |

**E4 verdict**：**PASS** — Wave A+B combined regression 全綠 non-flaky；production engine PID 2934602（pre-deploy）etime 1-12:06:42 健康（E4 不重啟）；deploy-time gate carry-over 屬 Wave C QA AC-1b 工作。

### 2.6 Phase 3c — QA AC-1b production V106 deploy + 30 min sample wait

#### Production V106 deploy 過程

deploy 路徑非標準 `OPENCLAW_AUTO_MIGRATE=1` 自動 land，原因 + 處置 chain：

1. **第一次 attempt：`OPENCLAW_AUTO_MIGRATE=1` + restart_all.sh --rebuild**
   - V97/V98 自動 land（schema 增量補位 OK）
   - **V103 Guard A FAIL**：`learning.hypotheses` base table 缺 — Sprint 1A-γ M4 scope deferred，V99-V102 + V104-V105 sparse migration 路徑空洞
   - sqlx migrate abort engine startup

2. **第二次 attempt：revert `OPENCLAW_AUTO_MIGRATE=0` + restart engine clean**
   - engine 跑起來但 V106 schema 未 land；M3 emit chain 端到端 INSERT 撞「relation does not exist」
   - emitter fail-soft 設計：V106 INSERT fail 走 `tracing::warn` 不 abort engine（與 MigrationRunner fail-loud 設計不衝突 — emitter 是 observability layer；migrate 是 correctness gate）

3. **第三次 attempt：raw `psql -f` apply V106 only**（sandbox 範式）
   - V106 schema land 至 production DB（hypertable + 7d chunk + 30d compression + 6 domain CHECK + 4 engine_mode CHECK + 4 state CHECK + columns 完整）
   - **_sqlx_migrations 表仍 MAX 98**（因 V106 走 raw psql -f 不註冊到 sqlx migrations history；屬已知 sandbox 範式副作用，不阻 emit chain；Sprint 1B late OPENCLAW_AUTO_MIGRATE=1 full chain 補位）
   - engine restart 後 emitter 即時 fire 第一輪 row

#### 30 min sample wait empirical（per QA Phase 3c verdict）

5 active domain × 30 min sample row count：

| Domain | Row count | classify dominant | HEALTH_WARN observed |
|---|---|---|---|
| **engine_runtime** | **264** | HEALTH_OK 主 | 41 row `open_fd_count` — production 真實 fd 用量；非 placeholder 副作用 |
| **pipeline_throughput** | **220** | HEALTH_OK | 0 row（placeholder OK band 對齊 spec line 102 嚴格 OK 值 per Wave B round 2 HIGH-1 fix）|
| **api_latency** | **176** | HEALTH_OK 主 | 60 row `rest_p50_ms` / `rest_p95_ms` / `rest_p99_ms` — Bybit demo latency 真實觀測 |
| **database_pool** | **110** | HEALTH_OK | 0 row |
| **risk_envelope** | **20** | HEALTH_OK | 0 row（placeholder empty cache → 5 metric 全 0 對齊 OK band）|
| **strategy_quality** | **0** | (skip) | (skip — Sprint 5+ wire-up scope) |

Total 770 V106 row × 30 min sample = ~25 row/min × 1 instance；對齊 spec §AC-1b 預期 ≥ 5 row per domain pattern。

#### AC-1b verdict

| AC 子項 | 預期 | 結果 | Verdict |
|---|---|---|---|
| engine_runtime row count ≥ 5（30 min window）| ≥ 5 | 264 | **PASS**（53× 安全餘量）|
| pipeline_throughput row count ≥ 5 | ≥ 5 | 220 | **PASS**（44× 安全餘量）|
| api_latency row count ≥ 5 | ≥ 5 | 176 | **PASS**（35× 安全餘量）|
| database_pool row count ≥ 5 | ≥ 5 | 110 | **PASS**（22× 安全餘量）|
| risk_envelope row count ≥ 5 | ≥ 5 | 20 | **PASS**（4× 安全餘量；對齊 risk_envelope 300s sample interval × 30 min ÷ 300s = 6 sample × ~5 metric ~ 20 row 預期）|
| strategy_quality row count（已知例外）| 0 | 0 | **PASS（例外）**（Track E Sprint 5+ wire-up scope；不阻 Sprint 4+ closure）|
| engine_mode 觀測值 | `live_demo` / `demo` / `paper` / `live`（V106 CHECK 4 值之一）| `live_demo` | **PASS** |
| OBSERVE-4 cross-Wave invariant | 0 V106 row engine_mode='replay' | 0 | **PASS** |
| production engine 健康 | 不重啟（per Q2(d)）但本 Sprint 4+ scope deploy 必 restart engine | PID 3654935 etime 02:58+ | **PASS** |

**Phase 3c verdict**：**PASS WITH 1 EXPECTED CARRY-OVER**（Track E strategy_quality 0 row 屬 Sprint 5+ wire-up scope 已知例外；不阻 Phase 3d TW Acceptance）。

---

## §3 §4.1 4 items Acceptance

### 3.1 PA-DRIFT-4 bybit_rest_client + bybit_private_ws instrumentation

**Acceptance verdict**：**PASS**

| Item | 結果 |
|---|---|
| RestLatencyHistogram（60s rolling window + sort-based nearest-rank p50/p95/p99 + cap 8192）| ✅ `bybit_rest_client.rs:335-339` 新 struct + 4 method + 4 inline test |
| RetCodeCounter（雙 Mutex 4xx/5xx 桶 + 10001-10006/10010 client fault + 110xxx venue fault + noop guard `is_noop_retcode` 5 集合）| ✅ `bybit_rest_client.rs:479-484` 新 struct + 6 method + helper（複用 `BybitRetCode::is_noop()` SSOT）|
| WsDropoutCounter（cap 256 prune + 60s rolling window + 6 接點 6 record + 2 主動 cancel 排除）| ✅ `bybit_private_ws.rs:216-218` 新 struct + 4 method |
| WsRttHistogram（main loop local Option<Instant> ping_at + contains 子串 peek pong + cap 64）| ✅ `bybit_private_ws.rs:102-105` 新 struct + 4 method |
| RealApiLatencySourceProbe（4 Arc 注入 + 8 trait method 對應 instrumentation accessor 1:1）| ✅ 新 `health/domains/api_latency_probe_impl.rs` 204 LOC + 2 inline test + 15 integration test |
| 60s expire boundary test 4 個（59s 內 / 61s 外）| ✅ Round 2 H-2 fix；4 instrumentation 各加 `inject_sample_with_timestamp` pub + `#[doc(hidden)]` + release optimizer drop verified |
| 觀測下沉 `get`/`post` 內部（per Round 2 H-3 fix；raw caller 也自動計入）| ✅ `bybit_rest_client.rs:1076-1101` (get) + `1130-1156` (post) + `_checked` 簡化避雙重計 |
| noop retCode 5 集合不誤計 5xx（per Round 2 H-1 BLOCKER fix）| ✅ `record_for_error` + `is_noop_retcode` helper + integration test `skips_noop_retcodes` + `noop_does_not_affect_real_venue_fault` |
| Integration test `api_latency_probe_real_impl` | **22 / 22 PASS** |

**E2 review verdict**：round 1 REJECT (1 HIGH BLOCKER + 2 HIGH + 3 MED + 3 LOW) → round 2 6 fix → **APPROVE**.

**QA AC-1b empirical**：api_latency 176 row × 30 min；4xx/5xx 對映 + 60s rolling window 在 Bybit demo endpoint 真實 fire；60 row HEALTH_WARN rest_p50/p95/p99 屬 production 真實 Bybit demo latency 觀測（非 placeholder 副作用）。

**Carry-over**：
- **WS half emit chain disconnected**：WsRttHistogram + WsDropoutCounter Wave A `rtt_histogram_handle()` / `dropout_counter_handle()` accessor 已實裝，但 `main_health_emitters.rs:218-219` `build_real_api_latency_probe` 走 `Arc::new(WsDropoutCounter::new())` + `Arc::new(WsRttHistogram::new())` fresh 0-state — V106 `api_latency__ws_rtt_*` / `__ws_dropout_count` 全 0 不代表真實 WS 健康 → Sprint 5+ Wave C BybitPrivateWs supervisor signature 改造（per singleton-registry.md §6.3）。

### 3.2 PA-DRIFT-5 RiskEnvelopeSourceProbe wire-up

**Acceptance verdict**：**PASS WITH 1 CARRY-OVER**（correlation_avg_pairwise Wave A placeholder 0.0；real calculator + lookback 設計 Sprint 5+ amend）

| Item | 結果 |
|---|---|
| PortfolioStateCache 24h sliding window（realized_pnl_history VecDeque + equity_history VecDeque + latest_exposures Vec + last_update_ts_ms）| ✅ 新 `health/domains/risk_envelope_probe_impl.rs:129-141` 新 struct + `update_from_pipeline_snapshot` + `drain_old_fills` / `drain_old_equity` 截斷 |
| 5 SSOT calculator | ✅ 4 真實（cum_pnl_24h_usd VecDeque sum / max_dd_pct_24h peak-trough O(n) / position_count_active len / concentration_top1_pct max(|notional|)/sum × 100）+ 1 placeholder（correlation_avg_pairwise 0.0）|
| RealRiskEnvelopeSourceProbe（`Arc<parking_lot::Mutex<PortfolioStateCache>>` + 5 trait method）| ✅ line 308-348 + `cache_handle()` 暴露 Arc clone 供 E2 audit + test 驗 |
| F-3 batch read `snapshot_5_metric()` trait default + RealProbe override（一次 lock）| ✅ Round 2 F-3 fix；既有 StubSource / MockMutexRiskProbe 走 default impl backward compat |
| F-2 NaN/inf sanitize（realized_pnl / equity / notional 三類 skip + fail-loud warn）| ✅ Wave B round 1 升 P1 condition；cache `update_from_pipeline_snapshot` 內部 3 sanitize 路徑 |
| F-1 cap=100k comment 失誤修法 | ✅ Round 2 F-1 fix 選項 (a) 改注釋為「24h × push rate 隱式上限；無顯式 cap」（無業務邏輯改動）|
| Integration test `risk_envelope_probe_real_impl` | **14 / 14 PASS** |

**E2 review verdict**：round 1 APPROVE-WITH-CONDITIONS (2 MED + 2 LOW + F-2 升 P1 Wave B condition) → round 2 2 fix → **APPROVE**.

**QA AC-1b empirical**：risk_envelope 20 row × 30 min；5 metric 全 OK band（PortfolioStateCache 走 Wave B placeholder no-op tick → 24h sliding window 全空 → 5 calculator 全 fail-soft 返 0 → OK band）。20 row 對齊 spec 預期（300s sample × 30 min ÷ 300 = 6 sample × ~5 metric 寫入 ÷ 5-sample window mean 後可能 dwell delay；保守值 20）。

**Carry-over**：
- **correlation_avg_pairwise real calculator**：Wave A placeholder 0.0；real calculator 需 portfolio cross-pair correlation rolling window + 3 組件（per-symbol returns time series + rolling window size + pairwise correlation matrix）+ lookback 拍板（60s / 5min / 1h / 24h）→ Sprint 5+ PA-CORRELATION-LOOKBACK amend + 後接 PaperState SSOT wire-up。
- **PortfolioStateCache update task 真實 wire-up**：Wave B placeholder no-op tick；Sprint 5+ Wave C 接 PaperState SSOT（需 PM 拍板方案 (a) 擴 PaperState Arc<RwLock<>> wrapper / (b) 加 broadcast tx 旁路 fill stream / (c) 擴 positions_mirror 加 qty/entry_price 欄位）。

### 3.3 main.rs scheduler 接線

**Acceptance verdict**：**PASS**

| Item | 結果 |
|---|---|
| 新 `main_health_emitters.rs`（528 → 652 LOC）封裝 6 emitter 構造 + scheduler spawn + update task spawn | ✅ commit `245216d1`；避 main.rs 1500 LOC + 800 警告線爆 |
| main.rs 接線 +55 LOC（base 1448 → 1503）| ✅ engine started log 前 wire-up + `primary_engine_mode` 決議 live > demo > paper 優先級 |
| `MetricEmitterScheduler::run` tokio::spawn + cancel token 對齊 engine main loop | ✅ scheduler spawn log 進 production binary（strings 確認）|
| OBSERVE-4 guard propagate（startup `Err(M3Error::ReplaySubprocessForbidden)` + per-tick guard + tokio::spawn match Err 寫 tracing::error 不 swallow）| ✅ 雙層 fail-loud（PG V106 CHECK + Rust scaffold guard）|
| PortfolioStateCache update task 接線（300s tick placeholder no-op + cancel token）| ✅ `spawn_portfolio_state_update_task` + F-2 sanitize 守在 cache 內部 |
| F-3 emitter sample_now batch path 切換（`RiskEnvelopeEmitter::sample_now` 走 `source.snapshot_5_metric()`）| ✅ `risk_envelope.rs:494-510` 9 LOC IMPL 替換 |
| HIGH-1 Track B placeholder 5 metric default 改 spec line 102 OK band 合法值（per Round 2 HIGH-1 fix）| ✅ tick_rate=2.0 / signal_rate=1.0 / ipc_p99=1.0 / heartbeat=0 / drift=0 + inline test 5 metric classify=HealthOk |
| LOW-2 emitter_count 動態 capture（`emitters.len()` 在 Vec move 進 scheduler 前讀 len()）| ✅ Round 2 LOW-2 fix |
| 6 integration test `main_scheduler_wireup` | **6 / 6 PASS** |

**E2 review verdict**：round 1 REJECT (1 HIGH + 2 MEDIUM + 3 LOW) → round 2 5 fix + MEDIUM-1 SSOT 建立由 PA 走 → **APPROVE-WITH-CONDITIONS**.

**QA AC-1b empirical**：5 active domain × 30 min sample × 770 row total；engine_mode 觀測 `live_demo`；OBSERVE-4 invariant 0 violation（無 V106 row engine_mode='replay'）。

**Carry-over**：
- **Wave C Track E StrategyQualityScheduler skip**：Sprint 5+ wire-up；獨立 scheduler（300s tick；對齊 spec §4.4 line 638-643）+ 接 PaperState SSOT signal log。
- **Track B real wire-up**：ws_client / IndicatorEngine / IPC stats accessor 接 `PipelineThroughputSourceProbe` trait → Sprint 5+ amend。
- **Track C writer_queue/pool_wait_p95 real wire-up**：market_writer Vec len + sqlx pool wait histogram accessor → Sprint 5+ amend。

### 3.4 AC-1b real PG empirical

**Acceptance verdict**：**PASS WITH 1 EXPECTED CARRY-OVER**（Track E strategy_quality 0 row 為 Sprint 5+ wire-up scope 已知例外）

| Item | 結果 |
|---|---|
| production V106 schema land（hypertable + 7d chunk + 30d compression + 6 domain CHECK + 4 engine_mode CHECK + 4 state CHECK）| ✅ via `psql -f` raw apply（sandbox 範式；走 OPENCLAW_AUTO_MIGRATE=0 revert path 後）|
| production engine PID 3654935 restart_all 後活躍 | ✅ etime 02:58+；emitter scheduler spawn log 入 production binary（strings 確認 5 main_health_emitters tracing event）|
| 5 active domain × 30 min sample row count ≥ 5 per domain | ✅ engine_runtime 264 / pipeline_throughput 220 / api_latency 176 / database_pool 110 / risk_envelope 20 = 770 row total |
| strategy_quality row count（已知例外）| 0（Sprint 5+ wire-up scope）|
| engine_mode 觀測值 `live_demo` 對齊 V106 CHECK 4 值 | ✅ |
| OBSERVE-4 cross-Wave invariant（0 V106 row engine_mode='replay'）| ✅ |
| HEALTH_OK 主 / HEALTH_WARN 真實觀測（41 row open_fd_count + 60 row rest_p50/p95/p99）| ✅（production 真實值；非 placeholder 副作用）|
| AC-2 4-state ladder fire（OK→WARN dwell 60s + WARN→DEGRADED dwell 5min real fire）| ✅ Sprint 2 已 PASS；Sprint 4+ 階段 production observe 對齊 |
| AC-3 amp cap 24h-suppression regression（spike baseline 不退）| ✅ Sprint 2 + E4 regression PASS |
| AC-4 cross-domain independence（每 Track 升 DEGRADED 不影響其他 5 domain state）| ✅ Sprint 2 5 cross_domain test + production 5 active domain 各自獨立 emit |
| AC-5 production binary 0 mock time 滲透（nm 0 hit）| ✅ Sprint 2 + Sprint 4+ Wave A+B 後 verify 仍 0 hit；inject_* symbol release optimizer drop 0 leak |
| AC-6 cargo + pytest baseline 不退 | ✅ cargo 3961/0 + pytest 6042/28（兩遍 non-flaky）|

**QA Phase 3c verdict**：**PASS**（5 active domain row count 全 ≥ 5；strategy_quality 0 row 屬 Sprint 5+ wire-up scope 已知例外不阻 Sprint 4+ closure）。

**Carry-over**：
- **V103/V107/V112 production deploy（Sprint 1B late）**：V99-V102 + V104-V105 sparse migration 路徑空洞造成 V103 Guard A FAIL；M4 base table `learning.hypotheses` 缺 — Sprint 1A-γ M4 scope deferred。完整 OPENCLAW_AUTO_MIGRATE=1 + restart auto-migrate chain 仍 pending。
- **_sqlx_migrations 表 MAX 仍 98**（V106 走 raw psql -f 不註冊）：Sprint 1B late + V99-V102 base table + V103 Guard A 補位 + 完整 migration history rebuild 屬獨立 audit task。

---

## §4 Cross-cutting Acceptance

### 4.1 V106 production schema land

| Item | 結果 |
|---|---|
| `learning.health_observations` table 物理存在於 production DB | ✅ via `psql -f` raw apply（commit-time SOP）|
| hypertable + 7d chunk + 30d compression | ✅ 對齊 V106 spec §3 + §4 |
| 6 domain CHECK constraint | ✅ engine_runtime + pipeline_throughput + database_pool + api_latency + strategy_quality + risk_envelope |
| 4 engine_mode CHECK constraint | ✅ paper / demo / live_demo / live；replay 不在 white-list（per OBSERVE-4 cross-Wave invariant）|
| 4 state CHECK constraint | ✅ HEALTH_OK / WARN / DEGRADED / CRITICAL |
| _sqlx_migrations 表狀態 | MAX 98（V97/V98 自動 land；V106 走 raw psql -f 不註冊）— 屬已知 sandbox 範式副作用 |

### 4.2 Production engine PID 3654935 健康

| 指標 | 觀測 |
|---|---|
| PID | 3654935（V106 raw apply 後 graceful restart）|
| etime | 02:58+ |
| primary_engine_mode | `live_demo`（has_live + LiveDemo endpoint）|
| emitter scheduler tokio task | active；6 emitter spawn log 入 production binary |
| 5 active domain emit | engine_runtime / pipeline_throughput / database_pool / api_latency / risk_envelope 全 fire ✓ |
| cancel token | active；engine shutdown 同步 cancel scheduler + update task |

### 4.3 5 active domain × 30 min sample（per QA Phase 3c）

per §2.6 row count 表：

- **engine_runtime**：264 row（HEALTH_OK 主 / open_fd_count HEALTH_WARN × 41 真實 fd 用量）
- **pipeline_throughput**：220 row（placeholder OK band per Wave B round 2 HIGH-1 fix）
- **api_latency**：176 row（HEALTH_OK 主 / rest_p50/p95/p99 HEALTH_WARN × 60 真實 Bybit demo latency）
- **database_pool**：110 row（HEALTH_OK）
- **risk_envelope**：20 row（HEALTH_OK；placeholder empty cache）
- **strategy_quality**：0 row（Sprint 5+ wire-up 已知例外）

HEALTH_WARN 觀測值揭露 production 真實 threshold 反映：
- `open_fd_count` 41 row HEALTH_WARN — production 真實 fd 用量；PA 可基於多輪 sample 拍板 ladder threshold 是否需 amend（per ADR-0042 spec §2.3 line 102 engine_runtime row）
- `rest_p50/p95/p99` 60 row HEALTH_WARN — Bybit demo latency 真實觀測；非 placeholder 副作用；PA 可基於 production 多日 sample 評估 ladder threshold amend 路徑

### 4.4 OBSERVE-4 cross-Wave invariant

| Enforcement layer | grep verify |
|---|---|
| PG V106 `engine_mode` CHECK | `IN ('paper','demo','live_demo','live')` 不含 'replay'（production schema land 確認）|
| Rust `M3Error::ReplaySubprocessForbidden` variant | `health/mod.rs:96` |
| Rust `MetricEmitterScheduler::run` startup guard | `health/metric_emitter/mod.rs:596` |
| Rust `MetricEmitterScheduler` per-tick guard | `health/metric_emitter/mod.rs:731-735` |
| Rust `StrategyQualityScheduler::run` startup guard | `health/domains/strategy_quality.rs:708` |
| Rust `StrategyQualityScheduler` per-tick guard | `health/domains/strategy_quality.rs:725-732` |
| main.rs tokio::spawn caller match Err 寫 tracing::error 不 swallow | ✅ |

**驗證**：production V106 row engine_mode='replay' count = 0（30 min sample 完整觀測；雙層 fail-loud 守住）。

### 4.5 6 new mutable singleton SSOT 登記（M-1 closed）

per PA Singleton Registry SSOT 建立報告：

新建 `docs/architecture/singleton-registry.md`（344 LOC）+ docs/README.md index entry。

| Singleton | Location | Wave | Migration plan |
|---|---|---|---|
| RestLatencyHistogram | `bybit_rest_client.rs:335-339` | A | 0 |
| RetCodeCounter | `bybit_rest_client.rs:479-484` | A | 0（multi-venue 預埋）|
| WsRttHistogram | `bybit_private_ws.rs:102-105` | A | Sprint 5+ Wave C supervisor signature 改造（§6.3）|
| WsDropoutCounter | `bybit_private_ws.rs:216-218` | A | Sprint 5+ Wave C 同 §6.3 |
| PortfolioStateCache | `risk_envelope_probe_impl.rs:129-141` | B | Sprint 5+ Wave C 接 PaperState SSOT（§6.4）|
| HealthEventBus | `event_bus.rs:80-82` | B | Sprint 5+ cascade IMPL 接 4-8 subscriber |

每 singleton 完整 12 欄位（name / type_signature / location / owner_lifecycle / cross_task_pattern / lock_primitive / visibility / caller_chain / health_monitoring / registered_date / governance_authority / migration_plan）登記於 singleton-registry.md §2.1.1 ～ §2.2.2。

**CLAUDE.md §七 line 165 + §九 line 196 cross-ref**：經 singleton-registry.md §4.1 + §4.2 完成；不修 CLAUDE.md inline（保 trim 意圖）。

### 4.6 Production engine fail-soft（V106 INSERT fail-warn 不 abort）

| 設計層 | 行為 |
|---|---|
| **emitter V106 INSERT fail** | `tracing::warn` 不 crash engine；observability layer fail-soft |
| **MigrationRunner fail-loud** | abort startup；correctness gate；不 swallow Guard A/B 失敗 |
| **OPENCLAW_AUTO_MIGRATE=0 revert path** | engine restart clean；不 force migrate；deploy 走 raw psql -f apply |
| **engine_mode='replay' V106 INSERT** | `M3Error::ReplaySubprocessForbidden` Err propagate；不 swallow；audit trail 完整 |

**結論**：兩種 fail mode 不衝突（emitter is observability layer；migrate is correctness gate）。production engine PID 3654935 在 V103 Guard A FAIL 場景 graceful restart clean；emitter 後續 V106 INSERT fail（V106 schema 未 land 階段）仍 emit chain alive；V106 raw apply land 後 emitter row 即時 fire。

### 4.7 16 根原則對齊（CLAUDE.md §二）

| # | 原則 | Sprint 4+ 對齊 |
|---|---|---|
| 1 | 單一寫入口 | Sprint 4+ 不創新 order 寫入口；V106 emitter writer 唯一入口 + OBSERVE-4 guard 強化 ✓ |
| 2 | 讀寫分離 | M3 emitter 只讀 metric + write V106 audit row；不寫 live state ✓ |
| 3 | AI ≠ 命令 | Sprint 4+ 不引 AI 路徑；emitter 是 pure metric observation ✓ |
| 4 | 策略不繞風控 | emitter emit DEGRADED 不觸 5-gate kill；Sprint 5 cascade 才接 ✓ |
| 5 | 生存 > 利潤 | placeholder fail-soft（disconnected → OK band 不誤升 CRITICAL）+ F-2 NaN/inf sanitize skip + fail-loud warn ✓ |
| 6 | 失敗默認收縮 | OBSERVE-4 guard fail-loud + amp cap 嚴格 fire 語意 3 guard + V103 Guard A FAIL abort + revert AUTO_MIGRATE=0 path ✓ |
| 7 | 學習 ≠ live | emitter 不寫 live state；V106 audit row 不影響 trading 路徑 ✓ |
| 8 | 交易可解釋 | D3 cascade reject log emit V106 row evidence_json reject_reason；audit trail 完整 ✓ |
| 9 | 雙重防線 | OBSERVE-4 雙層 fail-loud（PG V106 CHECK + Rust scaffold guard）；amp cap 3 guard 嚴格 fire 語意 ✓ |
| 10 | 事實 / 推斷 / 假設分離 | placeholder 半實裝陷阱誠實揭露（WS half / PortfolioStateCache update task）；30 天全 0 row 不掩飾為健康指標 ✓ |
| 11 | P0/P1 內自主 | Sprint 4+ 不擴 P0/P1 邊界 ✓ |
| 12 | evidence-based 演化 | E2 round 1 catch 真實 production-blocking bug 4 條（H-1 noop / H-2 expire 0 test / H-3 觀測覆蓋率 / HIGH-1 placeholder DEGRADED）→ round 2 closure；非紙上指標 ✓ |
| 13 | cost 感知 | sysinfo 30s + Track C 60s + risk_envelope 300s + Track E skip 控制 V106 emit rate 不額外 hot path ✓ |
| 14 | 零外部成本 | Sprint 4+ 全 self-hosted；sysinfo 0.32 crates.io 公開；無 vendor 依賴 ✓ |
| 15 | 多 agent 形式化 | Sprint 4+ chain：PM dispatch × 1 + E1 × 2 Wave A 並行 + E1 × 1 Wave B + E2 × 3 review + PA Singleton SSOT × 1 + E4 × 1 + QA AC-1b × 1 + TW Phase 3d × 1 + PM Phase 3e（pending）= 形式化 chain 對齊 CLAUDE.md §八 ✓ |
| 16 | portfolio > 孤立 trade | risk_envelope 5 metric 全 portfolio-level；Track F push back vs user prompt 7 metric 已 Sprint 2 sign-off + Sprint 4+ 沿用 ✓ |

**結論**：16/16 對齊；Sprint 4+ 0 violation。

### 4.8 Multi-Session Race Mitigation

per `feedback_fetch_before_dispatch` + `project_multi_session_memory_race` + `feedback_git_commit_only_for_metadoc`：

| Phase | 並行 sub-agent | 主會話 | Race 結果 |
|---|---|---|---|
| Phase 1 dispatch | PM × 1 | PM | 0 race |
| Phase 2 Wave A | PA-DRIFT-4 + PA-DRIFT-5 並行 E1 × 2 | PM | 0 race（atomic edit `health/domains/mod.rs` 兩 line add 不衝突；build 階段 `Instant::saturating_sub` not-found error 由 PA-DRIFT-4 自修 `checked_sub` + unwrap_or 對另 task 0 影響）|
| Phase 2 Wave A round 2 | E1 combined round 2 fix（single）| PM | 0 race |
| Phase 2 Wave B | E1 single | PM | 0 race |
| Phase 2 Wave B round 2 | E1 single | PM | 0 race |
| Phase 3a E2 review × 3 | E2 round 1 × 3 並行 + E2 round 2 × 3 sequential | PM | 0 race |
| Phase 3a PA Singleton SSOT | PA single | PM | 0 race |
| Phase 3b E4 | E4 single | PM | 0 race |
| Phase 3c QA AC-1b | QA single + 30 min sample wait | operator deploy | 0 race（OPENCLAW_AUTO_MIGRATE=0 revert + psql -f raw apply 路徑由 operator 走；不 commit production deploy 改動）|
| Phase 3d TW（本 report）| TW single | PM | 0 race |

**8 commit chain clean**（commit-first + 不認識改動禁 revert + meta-doc narrow staging）：
- `5acd36e6` feat(sprint-4-wave-a): PA-DRIFT-4 + PA-DRIFT-5 並行 IMPL DONE
- `4c84d1bb` fix(sprint-4-wave-a-round2): 6/6 finding closure
- `245216d1` feat(sprint-4-wave-b): main.rs scheduler wire-up
- `4d4ff99f` fix(sprint-4-wave-b-round2): 5/6 finding closure
- `82351b61` docs(singleton-registry): SSOT 建立 + 6 singleton 登記 + docs/README.md index
- E4 regression report land
- QA AC-1b PASS report land
- TW Phase 3d Acceptance（本 report；PM 收口時 commit）

---

## §5 Lessons Learned

### 5.1 PA prerequisite verify mandatory（PA-DRIFT-4 揭露）

Sprint 4+ Wave A 揭露 PA Sprint 2 dispatch packet §5.1「既有 bybit_rest_client + bybit_private_ws hook」claim grep verify 0 hit；E2 Sprint 2 Wave 2 Track D HIGH-3 catch；PA-DRIFT-4 carry-over 補位（5 工作項 IMPL 1 day）。

Sprint 4+ Wave B round 1 Track B placeholder 5 metric default 全 0 走 DEGRADED 染色（tick_rate / signal_rate 兩 metric 觸 < 0.5 / < 0.1 DEGRADED ladder）— 由 E2 Wave B round 1 HIGH-1 catch；round 2 改 spec line 102 OK band 合法值。

**結論**：dispatch packet 中「既有 X」prerequisite claim 必走 grep verify；E1 IMPL 前 PA / E2 confirm 真實存在；不能假設「Sprint N 提到過」= 「Sprint N+1 仍存在」。修法 per singleton-registry.md §3.3 → dispatch packet 模板必加「prerequisite grep verify ≥ 1」section。

### 5.2 Production deploy V### sparse migration（V103 Guard A FAIL 揭露）

Sprint 4+ Phase 3c production V106 deploy attempt #1（`OPENCLAW_AUTO_MIGRATE=1`）：V97/V98 自動 land OK；**V103 Guard A FAIL**（`learning.hypotheses` base table 缺）→ sqlx migrate abort engine startup。

根因：V99-V102 + V104-V105 sparse migration 路徑空洞 — Sprint 1A-γ M4 scope deferred 留 V103 dependency 真空。

修法路徑：
1. revert `OPENCLAW_AUTO_MIGRATE=0` + restart engine clean
2. `psql -f` raw apply V106 only（sandbox 範式；不註冊 _sqlx_migrations）
3. Sprint 1B late: V99-V102 spec gap audit + 新 V099 base table migration + 完整 OPENCLAW_AUTO_MIGRATE=1 chain 補位

**結論**：production deploy V### chain 不可假設「全 land」順序；M4 base table 等 deferred scope 需明示 dependency；audit closure SOP 必含 `restart_all --rebuild empirical`（per `project_2026_05_02_p0_sqlx_hash_drift` memory）。

### 5.3 Engine restart cargo PATH ssh non-interactive（restart_all 撞）

Sprint 4+ Wave B + Wave A round 2 IMPL 完成後 operator restart_all.sh --rebuild 第一次撞 `cargo not found`；ssh non-interactive 不讀 `~/.bashrc` / `~/.profile`；需 `source ~/.cargo/env` 顯式注入（per `feedback_restart_bind_host_default` 2026-05-09 memory）。

**結論**：restart_all.sh / deploy script 端必走 `source ~/.cargo/env` 顯式加載 cargo PATH；avoid 依賴 interactive shell env。SOP carry-over：deploy SOP 文檔加 `source ~/.cargo/env` 強制步驟。

### 5.4 Release binary stripped — strings vs nm differentiation

Sprint 4+ E4 regression Wave A+B wire-up symbol 驗證：

| Method | Sprint 4+ 結果 |
|---|---|
| `nm openclaw-engine \| grep MetricEmitterScheduler` | 0 hit |
| `nm openclaw-engine \| grep -E "(mock_instant\|tokio::time::pause\|spike)"` | 0 hit ✓ AC-5 守 |
| `strings openclaw-engine \| grep main_health_emitters` | 5 hit ✓ wire-up 入 binary 確認 |
| `strings openclaw-engine \| grep "PortfolioStateCache: skip NaN/inf"` | 3 hit ✓ F-2 sanitize 入 binary |

根因：Cargo.toml `strip=true` release profile + Rust monomorphize；nm 直接 grep type name 通常無法命中（mangled name 含 hash + stripped）。

**結論**：driver E2/E4 review 驗 wire-up symbol 必走多軌（strings + 真實 log + DB row 證據）；單 nm 0 hit 不證 wire-up 缺失。修法：`regression-testing-protocol` skill 加「stripped binary verify: strings + log path + DB row count」三步驟。

### 5.5 emitter fail-soft vs auto-migrate fail-loud 設計分層

Sprint 4+ Phase 3c production deploy 揭露兩種 fail mode 設計分層：

| 層 | 行為 |
|---|---|
| **emitter V106 INSERT fail（observability layer）** | `tracing::warn` 不 crash engine；emit chain 保 alive |
| **MigrationRunner fail-loud（correctness gate）** | abort startup；不 swallow Guard A/B 失敗 |
| **engine_mode='replay' V106 INSERT** | `M3Error::ReplaySubprocessForbidden` Err propagate；audit trail 完整 |

兩 fail mode 不衝突；observability layer 不能 abort engine（會撕裂 audit trail），correctness gate 必 abort 不能 swallow（會造成 schema drift）。

**結論**：fail-soft 與 fail-loud 各有適用場景；設計時必明示「層別 + 為什麼」。Sprint 5 cascade IMPL 接 Slack notification / Console badge / halt strategy / 降 LAL Tier 時必沿用此分層原則。

### 5.6 AC-1a/AC-1b 拆分契約價值再次驗證

Sprint 2 設計 AC-1a in-memory mock fixture（Wave 1+2 scaffold sign-off）vs AC-1b real PG empirical（Sprint 4+ first Live deploy window）拆分契約。

Sprint 4+ 階段驗證價值：
- AC-1a 守 cargo test 等價 production path 無需 real PG（scaffold 階段不阻 Wave 1+2 sign-off）
- AC-1b 守 production V106 deploy + 30 min sample wait + real PG empirical（Sprint 4+ first Live gate）
- 兩階段不重複測 + 不漏 production deploy 路徑

**結論**：AC 拆分契約對「scaffold sign-off ≠ production sign-off」場景關鍵；Sprint 5 cascade IMPL 階段（接 Slack notification + Console badge UI + halt strategy + 降 LAL Tier）將沿用此 pattern：
- AC scaffold（in-memory mock subscriber）= cargo test
- AC production（4-8 subscriber wire-up + production cascade fire）= deploy window real PG / Slack / Console badge empirical

---

## §6 Carry-over

### 6.1 Sprint 1B late — production V### chain 補位（P0/P1）

| # | Item | Owner | Priority | Est |
|---|---|---|---|---|
| 6.1.1 | V99-V102 spec gap audit + 新 V099 base table migration（解 V103 Guard A FAIL）| PA + E1 | P0 Sprint 1B | 4-6 hr audit + 2-3 hr V099 IMPL + Linux PG dry-run |
| 6.1.2 | 完整 `OPENCLAW_AUTO_MIGRATE=1` + restart auto-migrate chain（V99-V112 全 land + _sqlx_migrations 對齊 MAX 112）| E1 + operator | P0 Sprint 1B late | 1 hr deploy + 30 min verify |
| 6.1.3 | V107 + V112 production deploy 後 M11 + M1 spec wire-up（per Sprint 1A-β 13 module roster）| PA + E1 | P1 | Sprint 5+ cascade scope |

### 6.2 Sprint 5+ cascade IMPL — 4 P1（per singleton-registry.md §6 + Sprint 2 PM Phase 3e §4.2）

| # | Item | Owner | Priority | Est |
|---|---|---|---|---|
| 6.2.1 | **BybitPrivateWs supervisor signature 改造**（解 Wave B WS half placeholder 半實裝陷阱；外部 Arc 注入 + main.rs Wave 接 supervisor handle clone 替換 placeholder fresh Arc）| E1 + E2 | **P1**（unblocks 真實 WS health observability）| 4-6 hr E1 + 1 hr E2 |
| 6.2.2 | **PortfolioStateCache update task wire-up**（接 PaperState SSOT；PM 拍板方案 a/b/c）| E1 + PA | **P1**（unblocks 真實 portfolio risk envelope V106 emit）| 4-6 hr E1 + 1 hr E2 + 0.5 hr PA spec amend |
| 6.2.3 | archive 4 條 Python singleton re-ingest（_H_STATE_INVALIDATOR / MARKET_SCANNER / HStateCacheSlot / CostEdgeAdvisorDbSlot）| TW + PA | P2 LOW | 1-2 hr |
| 6.2.4 | dispatch packet 模板補「新 singleton 預登記」section | PA | P2 | 30 min |

### 6.3 Sprint 5+ M3 follow-up

| # | Item | Owner | Priority | Est |
|---|---|---|---|---|
| 6.3.1 | StrategyQualityEmitter wire-up（Track E 0 row 已知例外解；獨立 StrategyQualityScheduler 300s + 接 PaperState SSOT signal log）| E1 + PA | P1 Sprint 5+ | 6-8 hr E1 + 1 hr E2 + PaperState SSOT extend |
| 6.3.2 | AC-7 cargo bench `m3_emitter_cold_start` fixture IMPL（emitter scheduler `new` + `run` 進入 first tick wall-clock measurement；target ≤ 50ms）| E1 + E4 | P2 Sprint 5+ | 3-4 hr bench + 1 hr threshold tuning |
| 6.3.3 | LOC peak 切檔（main_health_emitters.rs 652 LOC / bybit_rest_client.rs 1367 LOC / bybit_private_ws.rs 1718 LOC / risk_envelope.rs 904 LOC / risk_envelope_probe_impl.rs 958 LOC；全 > 800 警告 + < 2000 hard cap）| E1 + E2 | P2 Sprint 5+ | 6-8 hr 重構 + 2 hr E2 |
| 6.3.4 | F-4 correlation real calculator + lookback amend（per E2 Track F round 2 對抗反問 #2）| E1 + PA | P1 Sprint 5+ | PA spec amend 1 hr + E1 IMPL 4-6 hr |
| 6.3.5 | Track B PipelineThroughput real wire-up（ws_client / IndicatorEngine / IPC stats accessor）| E1 + PA | P1 Sprint 5+ | 4-6 hr E1 + 1 hr E2 |
| 6.3.6 | Track C writer_queue / pool_wait_p95 real wire-up（market_writer Vec len + sqlx pool wait histogram accessor）| E1 + PA | P2 Sprint 5+ | 2-3 hr E1 + 1 hr E2 |

### 6.4 Production engine 監測 follow-up（Sprint 4+ 即起 → Sprint 5+）

| # | Item | Owner | Priority | Trigger |
|---|---|---|---|---|
| 6.4.1 | HEALTH_WARN 60 row `api_latency__rest_p50/p95/p99` 真實 production threshold 反映 → PA 評估 Bybit demo latency ladder threshold 是否需 amend | PA + QA | P2 | Sprint 5+ 多日 sample 累積後 |
| 6.4.2 | HEALTH_WARN 41 row `engine_runtime__open_fd_count` 真實 fd 用量 → PA 評估 ladder threshold 是否需 amend | PA + QA | P2 | Sprint 5+ 多日 sample 累積後 |
| 6.4.3 | 60s expire boundary test 4 個（Wave A round 2 H-2 fix）production 長時間 sample 驗證 | QA | P3 | Sprint 5+ |
| 6.4.4 | F-2 NaN/inf sanitize production fire log 監測（真實 PaperState SSOT wire-up 後）| QA | P2 | Sprint 5+ Wave C |

---

## §7 Sign-off

### 7.1 TW report write status

- **TW write DONE**：本報告 land path `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_first_live_carryover_acceptance.md`
- **TW 不下 verdict**（per task 禁忌 + Sprint 1A-ζ / Sprint 2 Phase 3d 範式延續）；本報告彙整 Phase 0-3c 全部 verdict + carry-over；最終 verdict by PM Phase 3e

### 7.2 PM sign-off section（pending Phase 3e PM closure）

| # | Phase 3e 待 PM 拍板項 | 依據 |
|---|---|---|
| 1 | **Final verdict**：PASS WITH 8 CARRY-OVER（採 §4.1 4 items 全 closed + 5 active domain row count 全 ≥ 5 + production V106 deploy DONE + production engine PID 3654935 健康；strategy_quality 0 row 屬 Sprint 5+ wire-up scope 已知例外）| §1.3 + §3.1-3.4 + Phase 3c QA verdict |
| 2 | **Sprint 5 cascade IMPL dispatch readiness gate**：OPEN（per Sprint 4+ 4 items 全 closed + AC-1b real PG empirical PASS + 6 singleton SSOT 登記 closed）vs DEFER（等 Sprint 1B late V99-V112 完整 chain land）二選一 | Sprint 2 PM Phase 3e §5.1 + 本 report §1.4 + §6.2 |
| 3 | **8 carry-over 派發**：(a) Sprint 1B late 3 條（6.1.1 V99-V102 audit + V099 / 6.1.2 完整 AUTO_MIGRATE chain / 6.1.3 V107+V112 wire-up）(b) Sprint 5+ cascade IMPL 4 P1（6.2.1 BybitPrivateWs supervisor / 6.2.2 PortfolioStateCache update task / 6.2.3 archive 4 Python re-ingest / 6.2.4 dispatch template）(c) Sprint 5+ M3 follow-up 6 條（6.3.1-6.3.6）(d) Production 監測 follow-up 4 條（6.4.1-6.4.4）| §6.1 + §6.2 + §6.3 + §6.4 |
| 4 | **AC-1b 5 active domain row count 全 PASS（含 strategy_quality 0 row 例外）處置**：接受為 Sprint 4+ closure；Track E wire-up 派 Sprint 5+（per 6.3.1）| §3.4 + §2.6 |
| 5 | **Sprint 1B late V99-V102 audit + V099 base table migration 優先級**：是否升 P0 next-Sprint top blocker（解 V103 Guard A FAIL + 全 AUTO_MIGRATE chain 補位）| §5.2 + §6.1.1 |
| 6 | **HEALTH_WARN production observation 處置**：(a) open_fd_count 41 row + (b) rest_p50/p95/p99 60 row 真實 production threshold；接受為 Sprint 5+ 多日 sample 後 PA 拍板 ladder amend 依據 vs Sprint 4+ closure 內 PA 即時 amend | §4.3 + §6.4 |
| 7 | **TODO.md update**：Sprint 4+ closure 條目 + 8 carry-over 條目 + Sprint 5 cascade IMPL dispatch readiness gate 條目 + Sprint 1B late V99-V112 chain 補位條目 + `W-S4-AC1B-HEALTHCHECK` entry 標 done | per `docs/agents/todo-maintenance.md` |
| 8 | **PM commit**：本 TW report + TW memory append + docs/README.md index 補位 Sprint 4+ Acceptance section（PM 收口統一）| per CLAUDE.md §Git And Sync narrow staging |

### 7.3 Sign-off chain status

```
Sprint 2 PM Phase 3e dispatch (§4.1 4 items)            ✅ 完成 (2026-05-22)
                ↓
Wave A PA-DRIFT-4 + PA-DRIFT-5 並行 IMPL round 1+2       ✅ 完成 (2026-05-23)
                ↓
Wave B main.rs scheduler 接線 round 1+2                  ✅ 完成 (2026-05-23)
                ↓
Phase 3a E2 review × 3 全 APPROVE                        ✅ 完成 (2026-05-23)
                ↓
PA Singleton Registry SSOT 建立 (M-1 closed)             ✅ 完成 (2026-05-23)
                ↓
Phase 3b E4 regression PASS                              ✅ 完成 (2026-05-23)
                ↓
Phase 3c QA AC-1b production V106 deploy + 30 min wait   ✅ 完成 (2026-05-23)
                ↓
Phase 3d TW Acceptance（本報告）                          ✅ 完成 (2026-05-23)
                ↓
Phase 3e PM closure verdict + Sprint 5 cascade IMPL 派發 sign-off    ⏳ pending PM
                ↓
operator 親手 sign-off Sprint 5 cascade IMPL 派發 readiness          ⏳ pending operator
                ↓
Sprint 1B late V99-V112 完整 AUTO_MIGRATE chain 補位                  ⏳ pending Sprint 1B
```

### 7.4 Sprint 4+ IMPL fingerprint

- 8 commit chain `5acd36e6 → 4c84d1bb → 245216d1 → 4d4ff99f → 82351b61` + E4 + QA + TW Phase 3d
- cargo workspace 3961/0/5 ignored × 2 non-flaky；Wave A+B integration 42/42 + Sprint 2 51/51 baseline 不退
- pytest 6042/28/45 × 2 non-flaky（baseline 不退）
- 6 new mutable singleton SSOT 登記完成；CLAUDE.md §七 + §九 cross-ref 經 singleton-registry.md §4.1/§4.2 完成
- production V106 schema land via psql -f raw（sandbox 範式）；engine PID 3654935 etime 02:58+ 健康
- 5 active domain × 30 min sample row count 770 row（engine_runtime 264 / pipeline_throughput 220 / api_latency 176 / database_pool 110 / risk_envelope 20）
- AC-5 nm 0 hit + inject_* leak 0 hit（release optimizer drop 守）
- OBSERVE-4 雙層 fail-loud（PG V106 CHECK + Rust scaffold guard）+ 0 violation observed in 30 min sample
- 0 hard boundary 觸碰（不創新 order 寫入口 / 不寫 live state / 不繞 Decision Lease / 不動 5-gate / 不寫 authorization.json）

---

## §8 Appendix — Sprint 4+ artifact + cross-reference 索引

### 8.1 Sprint 4+ commit chain

| Commit | Phase | 內容 |
|---|---|---|
| `5acd36e6` | Phase 2 Wave A round 1 | PA-DRIFT-4 + PA-DRIFT-5 並行 IMPL（4 bybit instrumentation singleton + RealApiLatencySourceProbe + PortfolioStateCache + RealRiskEnvelopeSourceProbe + 4 真實 calculator + 1 placeholder + 26 inline test + 26 integration test）|
| `4c84d1bb` | Phase 2 Wave A round 2 | 6/6 finding closure（PA-DRIFT-4 H-1 BLOCKER noop guard + H-2 60s boundary 4 test + H-3 觀測下沉 + M-1 注釋；PA-DRIFT-5 F-1 cap comment + F-3 batch read trait extension）|
| `245216d1` | Phase 2 Wave B round 1 | main.rs scheduler wire-up（main_health_emitters.rs 528 LOC + 5/6 emitter spawn + PortfolioStateCache 300s update task + emitter batch path + F-2 NaN sanitize + 6 integration test）|
| `4d4ff99f` | Phase 2 Wave B round 2 | 5/6 finding closure（HIGH-1 Track B placeholder OK band + MEDIUM-2 Track D WS half doc 補注 + LOW-1/2/3）|
| `82351b61` | Phase 3a PA Singleton SSOT | docs/architecture/singleton-registry.md 344 LOC 新建 + 6 singleton 12 欄位 + docs/README.md index entry |
| Phase 3b E4 | E4 regression report | cargo workspace 3961/0 + pytest 6042/28 + Wave A+B 42/42 + Sprint 2 51/51 + spike 3/3 + nm 0 + AC-5 守 |
| Phase 3c QA | QA AC-1b production V106 deploy + 30 min sample wait report | 5 active domain row count 全 PASS + strategy_quality 0 row 例外 |
| Phase 3d TW | TW Overall Acceptance Report（本報告）| 待 PM 收口時 commit |

### 8.2 Sprint 4+ artifact 路徑索引

| Path | 用途 |
|---|---|
| `srv/rust/openclaw_engine/src/bybit_rest_client.rs` | RestLatencyHistogram + RetCodeCounter 兩 pub struct + 14 method（Wave A）+ get/post 內部觀測下沉（round 2 H-3 fix）|
| `srv/rust/openclaw_engine/src/bybit_private_ws.rs` | WsRttHistogram + WsDropoutCounter 兩 pub struct + 6 dropout 接點 + ping/pong RTT（Wave A）|
| `srv/rust/openclaw_engine/src/health/domains/api_latency_probe_impl.rs` | RealApiLatencySourceProbe（Wave A；204 LOC + 2 inline test）|
| `srv/rust/openclaw_engine/src/health/domains/risk_envelope_probe_impl.rs` | PortfolioStateCache + 5 SSOT calculator + RealRiskEnvelopeSourceProbe（Wave A；958 LOC post-round 2 + F-2 sanitize）|
| `srv/rust/openclaw_engine/src/health/domains/risk_envelope.rs` | trait `snapshot_5_metric()` + `RiskEnvelopeSampleSnapshot` struct（Wave A round 2 F-3）+ emitter sample_now batch path 切換（Wave B）|
| `srv/rust/openclaw_engine/src/main_health_emitters.rs` | 6 emitter 構造 helper + scheduler spawn + update task spawn（Wave B；652 LOC post-round 2）|
| `srv/rust/openclaw_engine/src/main.rs` | mod main_health_emitters 註冊 + engine started log 前 wire-up call site（Wave B；1503 LOC）|
| `srv/rust/openclaw_engine/tests/api_latency_probe_real_impl.rs` | Wave A PA-DRIFT-4 integration 22 test |
| `srv/rust/openclaw_engine/tests/risk_envelope_probe_real_impl.rs` | Wave A PA-DRIFT-5 integration 14 test |
| `srv/rust/openclaw_engine/tests/main_scheduler_wireup.rs` | Wave B integration 6 test |
| `srv/docs/architecture/singleton-registry.md` | 6 new mutable singleton SSOT 主檔（M-1 closure）|

### 8.3 Sprint 4+ report 路徑索引

| Phase | Report path |
|---|---|
| Sprint 2 PM Phase 3e Sign-off §4.1 dispatch（Sprint 4+ 來源）| `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_pm_phase_3e_signoff.md` |
| Sprint 2 Overall Acceptance（Sprint 4+ 範式）| `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_overall_acceptance.md` |
| Phase 2 Wave A PA-DRIFT-5 round 1 | `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_4_pa_drift_5_risk_envelope_wireup.md` |
| Phase 2 Wave A PA-DRIFT-4 round 1 | `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint_4_pa_drift_4_bybit_instrumentation.md` |
| Phase 2 Wave A round 2 combined fix | `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint_4_wave_a_round2_combined_fix.md` |
| Phase 2 Wave B round 1 | `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint_4_wave_b_main_scheduler_wireup.md` |
| Phase 2 Wave B round 2 | `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint_4_wave_b_round2_fix.md` |
| Phase 3a PA Singleton Registry SSOT 建立 | `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_wave_b_m1_singleton_registry_ssot.md` |
| Phase 3b E4 regression | `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-23--sprint_4_e4_regression_wave_ab.md` |
| Phase 3c QA AC-1b empirical | （inline final response handover by QA sub-agent；無獨立 report file；row count + verdict 整合於本 §3.4 + §4.3）|
| **Phase 3d TW Overall Acceptance**（本報告） | `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_first_live_carryover_acceptance.md` |

### 8.4 spec doc 路徑索引

| Spec | Path |
|---|---|
| Sprint 2 design spec（含 §3.2 ApiLatencySample 5→8 field amend + §5.0 OBSERVE-4 新節）| `srv/docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md` |
| Sprint 2 dispatch packet（§1.6.1 AC-1a/1b 拆分契約 + §1.7 Track A scaffold contract + §5.5 反模式）| `srv/docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md` |
| M3 health monitoring design spec（含 §2.3 line 102/103/104/106 amend + §2.3.1/§2.3.2/§2.3.3 新節）| `srv/docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md` |
| V106 schema spec | `srv/docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md` |
| Singleton Registry SSOT 主檔 | `srv/docs/architecture/singleton-registry.md` |
| ADR-0042 M3 health monitoring（governance authority；不 amend）| `srv/docs/adr/0042-m3-health-monitoring.md` |
| ADR-0040 multi-venue extensibility（不 amend；ret_code 4xx/5xx 預埋）| `srv/docs/adr/0040-multi-venue-extensibility.md` |
| ADR-0034 M1 LAL Layered Approval Lease（Sprint 5 cascade IMPL 接降 LAL Tier）| `srv/docs/adr/0034-decision-lease-layered-approval-lal.md` |
| ADR-0044 M7 decay enforced single authority（M3 emitter 不寫 decay_signals）| `srv/docs/adr/0044-m7-decay-enforced-single-authority.md` |
| AMD-2026-05-21-01 Layered Autonomy v2（§1.7 Sprint 5 cascade IMPL 派發 readiness gate）| `srv/docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md` |

---

**END Sprint 4+ first Live carry-over — Overall Acceptance Report**

**TW Phase 3d DONE** — report path: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_first_live_carryover_acceptance.md`

**Phase 3e PM sign-off pending** — 待 PM 拍板 §7.2 8 條 sign-off item + 最終 verdict + Sprint 5 cascade IMPL 派發 readiness gate + Sprint 1B late V99-V112 完整 AUTO_MIGRATE chain 補位優先級
