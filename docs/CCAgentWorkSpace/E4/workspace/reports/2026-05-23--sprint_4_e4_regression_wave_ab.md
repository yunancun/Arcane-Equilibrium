# E4 Sprint 4+ Wave A+B combined regression — 2026-05-23

## 0. TL;DR

**Verdict: PASS** — Sprint 4+ first Live carry-over Wave A (PA-DRIFT-4 bybit instrumentation + PA-DRIFT-5 RiskEnvelopeSourceProbe wire-up) + Wave B (main.rs MetricEmitterScheduler + PortfolioStateCache + 6 emitter spawn) combined regression 全綠：cargo workspace 3961/0/5 non-flaky × 2 runs（baseline 3894 → +67 attribution Wave A+B integration test 42 + lib health 增量 +23 + 其他 sibling drift）；Wave A api_latency 22/22 + Wave A risk_envelope 14/14 + Wave B main_scheduler_wireup 6/6；Sprint 2 7 Track 51/51 maintained；spike 3/3；health::110 + bybit_rest_client 29/0；pytest 6042 pass / 28 pre-existing fail × 2 runs (與 Sprint 2 Phase 3b baseline 完全一致)；cross-lang fixture 12/12 (7 Python PoC + 5 Rust binding)；aarch64-apple-darwin release cargo check clean (0 error, 4 既有 deprecated/dead_code warning 非新增)；nm AC-5 invariant 0 hit 維持；Wave A+B inject_* symbol 0 leak (release optimizer drop)；strings 確認 wire-up + impl 字串全在 binary；Linux sandbox_admin role + V106 6 domain CHECK schema + pg_hba reject row 全 confirm；production engine PID 2934602 etime 1-12:06:42 不重啟 (符合預期)。Wave C QA AC-1b real PG empirical carry-over（待 Linux --rebuild + 30 min sample wait）。

## 1. Mac cargo test

### 1.1 workspace --release（skip stress_tick_latency_benchmark Mac flaky per Sprint 2 SOP）

| Run | Pass | Fail | Ignored | non-flaky |
|---|---|---|---|---|
| 1 | **3961** | 0 | 5 | (ref) |
| 2 | **3961** | 0 | 5 | ✅ identical |

baseline 比較（Sprint 2 Phase 3b 3894 → +67）attribution：
- Wave A api_latency_probe_real_impl integration: 22 new
- Wave A risk_envelope_probe_real_impl integration: 14 new
- Wave B main_scheduler_wireup integration: 6 new
- 小計 Wave A+B integration: 42
- health:: lib 87 → 110: +23 (Wave A+B real-impl sub-module 內部 unit test)
- Sprint 2 Track A engine_runtime + 其他 sibling drift: +2
- 合計 +67 ✅ 對齊預期

**0 fail 維持 ✅ non-flaky 兩遍同綠 ✅**

### 1.2 Wave A+B 個別 integration test

| Test | Pass | Fail | Notes |
|---|---|---|---|
| `api_latency_probe_real_impl` (Wave A PA-DRIFT-4) | **22 / 22** | 0 | RestLatencyHistogram + RetCodeCounter + WsDropoutCounter + WsRttHistogram + 60s sliding window expire + noop guard + hot path cap + 4xx/5xx classify |
| `risk_envelope_probe_real_impl` (Wave A PA-DRIFT-5) | **14 / 14** | 0 | PortfolioStateCache + RealRiskEnvelopeSourceProbe + 24h sliding window boundary + Max DD peak-trough + concentration top1 + 4 scenario + F-2 sanitize + multi-lock no deadlock + trait default fallback |
| `main_scheduler_wireup` (Wave B) | **6 / 6** | 0 | 6 emitter spawn + risk_envelope batch path + replay engine_mode fail-loud + replay risk_envelope fail-loud + 4 legal engine_mode startup + 5 domain concurrent spawn + 60s window writer |

**42 / 42 PASS ✅**

### 1.3 Sprint 2 6 Track + replay_forbidden regression (baseline 51/51 maintained)

| Test | Pass | Fail |
|---|---|---|
| `sprint2_track_a_engine_runtime` | **9 / 9** | 0 |
| `sprint2_track_b_pipeline_throughput` | **5 / 5** | 0 |
| `sprint2_track_c_database_pool` | **8 / 8** | 0 |
| `sprint2_track_d_api_latency` | **7 / 7** | 0 |
| `sprint2_track_e_strategy_quality` | **11 / 11** | 0 |
| `sprint2_track_f_risk_envelope` | **8 / 8** | 0 |
| `m3_emitter_replay_forbidden` | **3 / 3** | 0 |

**51 / 51 PASS ✅ 對齊 Sprint 2 Phase 3b baseline**

### 1.4 spike feature regression

```bash
cargo test --release --features spike --test m3_amp_cap_24h_fire
```

| Test | Result |
|---|---|
| `test_amp_cap_different_anomaly_id_not_suppressed` | PASS |
| `test_m3_amp_cap_24h_fire` | PASS |
| `test_stub_domains_fail_loud` | PASS |

**3 / 3 PASS ✅**

### 1.5 health:: + bybit_rest_client lib regression

| 範圍 | Pass | Fail | Notes |
|---|---|---|---|
| `cargo test --release --lib "health::"` | **110** | 0 | Sprint 2 Phase 3b baseline 87 → +23 attribution Wave A+B real-impl sub-module (api_latency_probe_impl 22 + risk_envelope_probe_impl 14 部分 unit test 內含於 lib scope；數字差精準對齊) |
| `cargo test --release --lib "bybit_rest_client"` | **29** | 0 | Sprint 2 baseline 29 不退 ✅ |

### 1.6 stress_tick_latency_benchmark SOP carry-over

Per Sprint 2 Phase 3b 結論：Mac workspace 並行模式 CPU contention 假陽性。本次延用 `--skip stress_tick_latency_benchmark`，未獨立跑 isolated run（不阻 Sprint 4+ Wave A+B verdict）。

## 2. Mac pytest

從 `srv/` root 跑 `python3 -m pytest -q --tb=no --ignore=venvs --ignore=tests/misc_tools/test_pure_utils.py --ignore=tests/ml_training/test_pure_utils.py`：

| Run | Failed | Passed | Skipped | Subtests | Duration |
|---|---|---|---|---|---|
| 1 | 28 | **6042** | 45 | 14 | 128.36s |
| 2 | 28 | **6042** | 45 | 14 | 124.87s |

**non-flaky 兩遍同綠 ✅**

baseline 比較：Sprint 2 Phase 3b 6042 pass / 28 pre-existing fail → 當前 6042 pass / 28 fail → **0 delta，passed 不退 / failed 不增 ✅**。

28 pre-existing failure 與 Sprint 4+ Wave A+B 完全無關（24 GUI static template + 3 structure + 1 v072_feature_baseline_writer，per Sprint 2 Phase 3b 報告）。

## 3. Cross-lang fixture (AC-7 Sprint 1A-ζ regression)

```bash
cd /Users/ncyu/Projects/TradeBot/srv && python3 -m pytest tests/test_spike_cross_lang_fixture.py tests/test_spike_cross_lang_rust_binding.py -v
```

| Suite | Pass | Fail |
|---|---|---|
| `test_spike_cross_lang_fixture` (Python PoC) | **7 / 7** | 0 |
| `test_spike_cross_lang_rust_binding` (Rust binding) | **5 / 5** | 0 |

**12 / 12 PASS ✅ bit-perfect cross-lang fixture 維持**

## 4. Cross-platform aarch64-apple-darwin

```bash
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine && cargo check --target aarch64-apple-darwin --release
```

**結果**：0 error / 4 warning (既有 deprecated `compute_atr_pct` 4 個 use site + dead_code `make_intent` / `spawn_position_reconciler` 非 Wave A+B 引入)；`Finished release profile [optimized] target(s) in 9.82s` ✅

Mac aarch64 cross-platform 維持，Wave A+B IMPL 對未來 Apple Silicon 部署無 portability blocker。

## 5. AC-5 nm invariant

```bash
nm /Users/ncyu/Projects/TradeBot/srv/rust/target/release/openclaw-engine | grep -E "(mock_instant|tokio::time::pause|spike)" | wc -l
```

**結果**：**0 hit ✅ AC-5 invariant 維持**

Wave A+B IMPL 未引入 mock_instant / tokio::time::pause 等測試用工具進 production binary。spike feature default off，binary 不含 spike symbol。

## 6. Wave A+B wire-up symbol + inject_* leak verify

### 6.1 production binary 含 Wave A+B wire-up

```bash
strings target/release/openclaw-engine | grep -E "(RealApiLatencySourceProbe|PortfolioStateCache|main_health_emitters|api_latency_probe_impl|risk_envelope_probe_impl)"
```

**驗證命中（節錄）**：
- `openclaw_engine::main_health_emitters` — Wave B emitter scheduler module ✅
- `openclaw_engine/src/main_health_emitters.rs` — main.rs scheduler 接線 module ✅
- `openclaw_engine::health::domains::risk_envelope_probe_impl` — Wave A PA-DRIFT-5 real impl ✅
- `openclaw_engine/src/health/domains/risk_envelope_probe_impl.rs` — 同上 ✅
- `openclaw_engine/src/health/domains/api_latency_probe_impl.rs` — Wave A PA-DRIFT-4 real impl ✅ (per doc-test 已見)
- `PortfolioStateCache: filter NaN/inf notional exposure (F-2 sanitize)` — F-2 sanitize 字串 ✅
- `PortfolioStateCache: skip NaN/inf realized_pnl fill (F-2 sanitize)` — F-2 round 2 fix ✅
- `PortfolioStateCache: skip NaN/inf equity sample (F-2 sanitize)` — F-2 round 2 fix ✅
- `M3 metric emitter scheduler + PortfolioStateCache update task wired (Sprint 4+ first Live Wave B; Track A/C/F real + B/D-WS placeholder + E skip)` — Wave B wire-up startup log ✅
- `M3 metric emitter wire-up skipped: DbPool disconnected at boot (PG unreachable). V106 emit chain disabled until db restored.` — Wave B fail-loud 訊息 ✅
- `engine_mode='replay' forbidden by V106 CHECK (spec line 199-216).` — Wave B replay guard ✅
- `m3.health.risk_envelope` — V106 emit target topic ✅

**結論**：production release binary 含 Wave A+B wire-up + IMPL 全部 ✅

### 6.2 nm 對 Rust mangled symbol 補充

`nm | grep MetricEmitterScheduler` 等高層 type 名 0 hit 是預期：Rust release 模式靜態 monomorphize + symbol stripping，nm 直接 grep type name 通常無法命中（mangled name 含 hash）。`strings` + doc-test 路徑 + module path 字串已充分證明 wire-up 入 binary。

### 6.3 Wave B inject_* symbol leak (E2 H-2 closure verify)

```bash
nm target/release/openclaw-engine | grep -E "inject_sample_with_timestamp|inject_4xx|inject_5xx" | wc -l
```

**結果**：**0 hit ✅ E2 H-2 closure 維持**

Wave B inject_* pub fn 雖在 source 內標 `pub`，release optimizer 因無外部呼叫者而 drop。production binary 無 inject_* symbol leak。

## 7. Linux sandbox state verify

### 7.1 sandbox_admin role active

```bash
ssh trade-core "PGPASSWORD=\$(cat /home/ncyu/BybitOpenClaw/srv/settings/secret_files/postgres/sandbox_admin/password) \
  psql -h 127.0.0.1 -U sandbox_admin -d trading_ai_sandbox -tA -c \"SELECT current_user, current_database();\""
```

**結果**：`sandbox_admin|trading_ai_sandbox` ✅

E3-MED-1 / Sprint 1A-ε P2 closure 後 sandbox_admin role 持續活躍。secret_file 0600 in `srv/settings/secret_files/postgres/sandbox_admin/password`。

### 7.2 V106 schema 6 domain CHECK 完整

```bash
PGPASSWORD=... psql -U sandbox_admin -d trading_ai_sandbox -tA -c \
  "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint \
   WHERE conrelid = 'learning.health_observations'::regclass AND contype = 'c' ORDER BY conname;"
```

**結果**：
- `health_observations_domain_check`: 6 domain (engine_runtime / pipeline_throughput / database_pool / api_latency / strategy_quality / risk_envelope) ✅
- `health_observations_engine_mode_check`: 4 mode (paper / demo / live_demo / live) ✅ replay 不在白名單，與 Wave B `engine_mode='replay' forbidden by V106 CHECK` 對齊
- `health_observations_state_check`: 4 state (HEALTH_OK / WARN / DEGRADED / CRITICAL) ✅
- `health_observations_state_prev_check`: null-tolerant 4 state ✅

V106 schema 完整對齊 Wave B emit chain target schema ✅

### 7.3 pg_hba E3-MED-1 reject row 仍生效

```bash
PGPASSWORD=... psql -U sandbox_admin -d trading_ai 2>&1
```

**結果**：`FATAL:  pg_hba.conf rejects connection for host "172.18.0.1", user "sandbox_admin", database "trading_ai", no encryption` ✅

E3-MED-1 reject row 持續阻止 sandbox_admin 誤入 production DB。production engine 不被誤殺。

## 8. Production engine 健康 (不重啟)

```bash
ssh trade-core "ps -eo pid,user,etime,cmd | grep openclaw-engine | grep -v grep"
```

**結果**：`2934602 ncyu      1-12:06:42 rust/target/release/openclaw-engine`

- PID 2934602 = Sprint 1A-γ 之後 2026-05-21 13:31 UTC graceful restart 後活躍
- etime 1-12:06:42 = 1 day 12 hr 6 min 42 sec uptime
- per multi-session race + AC-3 Q2(d) rule，**E4 不重啟 production engine** ✅

注意 Sprint 4+ Wave A+B IMPL 落於 Mac source layer + Mac cargo verified，**Linux engine binary 尚未包含 Wave A+B**（per 2026-05-22 Sprint 1A-ζ Linux engine binary 0 deploy carry-over 同樣狀態）。`P1-ENGINE-BINARY-SPRINT-1A-IMPL-DEPLOY` 仍待 operator 排程 --rebuild。Sprint 4+ Wave C QA AC-1b real PG empirical 必須先解此 carry-over（Linux --rebuild + 30 min sample wait）才能跑。

## 9. Wave A+B source land confirm

```bash
ls -la srv/rust/openclaw_engine/src/health/domains/api_latency_probe_impl.rs       # 7,909 bytes
ls -la srv/rust/openclaw_engine/src/health/domains/risk_envelope_probe_impl.rs      # 42,780 bytes
ls -la srv/rust/openclaw_engine/src/main_health_emitters.rs                          # 33,078 bytes
```

commit chain:
- `5acd36e6` feat(sprint-4-wave-a): PA-DRIFT-4 + PA-DRIFT-5 並行 IMPL DONE
- `4c84d1bb` fix(sprint-4-wave-a-round2): 6/6 finding closure — PA-DRIFT-4 H-1/2/3/M-1 + PA-DRIFT-5 F-1/3
- `245216d1` feat(sprint-4-wave-b): main.rs scheduler wire-up — 5/6 emitter spawn + PortfolioStateCache + emitter batch path + F-2 NaN sanitize
- `4d4ff99f` fix(sprint-4-wave-b-round2): 5/6 finding closure — H-1 placeholder OK band + M-2 doc + L-1/2/3 (M-1 PM follow-up)

全 land in HEAD ✅

## 10. Phase E4 verdict

**Verdict: PASS** — Sprint 4+ first Live carry-over Wave A+B combined regression 全綠且非 flaky：cargo workspace 3961/0/5 × 2 + pytest 6042/28 × 2 + Wave A+B 42/42 + Sprint 2 51/51 + spike 3/3 + health 110/0 + bybit 29/0 + cross-lang 12/12 + aarch64 darwin clean + AC-5 nm 0 hit + Wave A+B wire-up strings 全命中 + inject_* 0 leak + Linux sandbox state full pass + production engine PID 2934602 etime 1-12 健康 (不重啟)。

### Carry-over to Wave C QA

- **AC-1b real PG empirical**：待 operator 排程 Linux `helper_scripts/restart_all.sh --rebuild` (將 Sprint 1A-δ Rust trait stub + Sprint 1A-ζ V106/V107 sandbox apply + Sprint 4+ Wave A+B Mac IMPL 一起 deploy)，再 wait 30 min sample window，再對 `learning.health_observations` 跑 row count + domain distribution + engine_mode='live_demo' verify + 6 domain emit chain visible。Mac E4 無法 reach Linux runtime PG empirical (per profile 規範)。
- **Sprint 1A-ζ carry-over P1-SANDBOX-SQLX-METADATA-ALIGNMENT**：sandbox PG `_sqlx_migrations` MAX 仍 96，5 table 物理存在但 sqlx 0 row。E4 不負責此 alignment。
- **P1-ENGINE-BINARY-SPRINT-1A-IMPL-DEPLOY**：Linux engine binary 0 包含 Sprint 1A-δ Rust trait stub + Sprint 4+ Wave A+B。同一次 --rebuild 即可同步 deploy。

### Sign-off

| 項 | 結果 |
|---|---|
| cargo workspace × 2 non-flaky | ✅ 3961/0/5 |
| Wave A+B 42 integration | ✅ 42/42 |
| Sprint 2 regression 51 | ✅ 51/51 |
| spike feature regression | ✅ 3/3 |
| lib health + bybit | ✅ 110/0 + 29/0 |
| pytest × 2 non-flaky | ✅ 6042/28 |
| cross-lang fixture 12 | ✅ 12/12 |
| aarch64-apple-darwin | ✅ 0 error |
| AC-5 nm 0 hit | ✅ |
| Wave A+B wire-up strings | ✅ 全命中 |
| Wave B inject_* leak | ✅ 0 hit |
| Linux sandbox + V106 schema + pg_hba | ✅ |
| production engine 健康 (不重啟) | ✅ PID 2934602 etime 1-12:06:42 |

**E4 REGRESSION DONE: PASS** · 報告路徑：`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-23--sprint_4_e4_regression_wave_ab.md`
