---
report: E1 IMPL — Sprint 5+ Wave 1 §4.4 production hardening (4 items + AC-1b monthly cron)
date: 2026-05-23
author: E1 (Backend Developer)
phase: Sprint 5+ Wave 1 Phase B-5
parent_dispatch: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_wave1_production_hardening_design.md
status: IMPL-DONE (待 E2 審查 + E4 regression)
build_verify: cargo build --release --lib PASS（2 既有 warning / 0 error）
test_verify: cargo test --release --lib health::domains::api_latency 15/15 PASS（含 2 新 ws_rtt baseline test） + cargo test --release --lib health::metric_emitter 10/10 PASS（含 2 新 open_fd baseline test）
---

# §1 任務摘要

per PA dispatch packet (`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_wave1_production_hardening_design.md`)，落地 §4.4 production hardening 4 items + AC-1b monthly cron：

| Item | Type | 文件 | 狀態 |
|---|---|---|---|
| §4.4.1 HEALTH_WARN ladder amend | Rust code + test | metric_emitter/mod.rs + api_latency.rs | DONE |
| §4.4.2 60s boundary verify SOP | bash + sql | health_60s_boundary_verify.{sh,sql} | DONE |
| §4.4.3 F-2 sanitize monitor | bash (DISABLED-by-default) | health_f2_sanitize_monitor.sh | DONE |
| §4.4.4 AC-1b monthly cron | bash + crontab spec | ac1b_monthly_healthcheck.sh | DONE |
| §4.4.5 SCRIPT_INDEX update | doc | helper_scripts/SCRIPT_INDEX.md | DONE |

# §2 修改清單

## §2.1 Rust files (Phase A)

- `rust/openclaw_engine/src/health/metric_emitter/mod.rs`
  - L346-371: `classify_engine_runtime_open_fd_count` ladder amend
    - **Before**: OK<1024 / WARN 1024-4096 / DEGRADED >4096
    - **After**: OK<3072 / WARN 3072-6144 / DEGRADED >6144
    - 新注釋說明 25 symbol × kline WS + REST pool + IPC + PG pool baseline 1700-1800 fd，OK band 上限 3072 留 ~70% headroom；WARN band 對應「真實 fd leak signal」；DEGRADED 接近 RLIMIT_NOFILE 8192 上限
  - L1308-1330（新加 2 unit test）:
    - `test_open_fd_count_baseline_1800_is_ok` — value=1800 → HealthOk
    - `test_open_fd_count_3500_warn` — value=3500 → HealthWarn

- `rust/openclaw_engine/src/health/domains/api_latency.rs`
  - L303-336: `classify_api_latency_ws_rtt_p50_ms` ladder amend
    - **Before**: OK<50 / WARN 50-150 / DEGRADED >150
    - **After**: OK<170 / WARN 170-300 / DEGRADED >300
    - 新注釋說明 Bybit demo endpoint → trade-core 物理距離常態 150-163ms 為不可逆網路常態；mainnet 切換時須重 calibrate（不留盲區）
  - L244-260: `classify_api_latency_rest_p50_ms` 注釋補 production hardening note（cascade gap 預期行為說明）
  - L275-285: `classify_api_latency_rest_p95_ms` 注釋補 production hardening note
  - L304-317: `classify_api_latency_rest_p99_ms` 注釋補 production hardening note
  - L710-739: existing `test_classify_ws_rtt_p50_ms_thresholds` 對齊新 ladder（OK<170 boundary 改 169/170/300/301）
  - L740-770（新加 2 unit test）:
    - `test_ws_rtt_p50_demo_baseline_163_is_ok` — value=163 → HealthOk
    - `test_ws_rtt_p50_jitter_250_warn` — value=250 → HealthWarn
  - L935-940: 既有 critical case test fixture `ws_rtt_p50_ms: 200` 改 `350`（200ms 新 ladder 落 WARN band 非 DEGRADED；保持本 case「ws_rtt_p50 DEGRADED」原意必用 >300）；加 inline 注釋說明 amend 原因

## §2.2 Bash scripts + SQL (Phase C/D/E)

- `helper_scripts/db/health_60s_boundary_verify.sql` (新檔，~85 行)
  - 3 SQL section：
    - §1 sample inter-arrival check per metric (LAG window function，LIMIT 20)
    - §2 bucket density check (date_trunc minute，LIMIT 30)
    - §3 30min summary (per-metric row count + avg_delta_seconds)
  - 範圍 only api_latency + engine_runtime（60s emitter tick 對齊範疇；不含 risk_envelope 300s tick / pipeline_throughput 30s tick）

- `helper_scripts/db/health_60s_boundary_verify.sh` (新檔，~140 行)
  - venv-aware + secrets load + container psql（mirror passive_wait_healthcheck.sh:79-94 範式）
  - 解析 §1/§2/§3 三 section output verdict：
    - PASS: inter-arrival ∈ [58, 62] AND samples_per_min == 1
    - WARN: inter-arrival ∈ [55, 65] (scheduler jitter)
    - FAIL: out of [55, 65] OR samples_per_min ∉ [1, 2] OR row_count < 25
  - exit 0/1/2 PASS/FAIL/DB-error

- `helper_scripts/db/health_f2_sanitize_monitor.sh` (新檔，~95 行)
  - **DISABLED-BY-DEFAULT** 直到 Sprint 5+ §4.2.2 wireup PaperState SSOT 後 enable（per PA spec §4.4.3）
  - grep-based 而非 PG-based（F-2 sanitize 在 in-process tracing::warn 觸發不寫 V106；engine.log 為唯一 SSOT）
  - cross-platform date：GNU `date -d` (Linux) / BSD `date -v` (Mac) 雙 fallback
  - awk filter `$0 ~ /F-2 sanitize/ && $1 >= cutoff`（ISO8601 timestamp lexicographic compare 與時間序列 monotonic 對齊）
  - OPENCLAW_F2_THRESHOLD=0 default = 任一 fire 即 alert
  - exit 0/1/2 OK/ALERT/log-unreadable

- `helper_scripts/db/ac1b_monthly_healthcheck.sh` (新檔，~125 行)
  - 對齊 passive_wait_healthcheck.sh 範式（secrets load + container psql + sentinel mtime）
  - 6 active domain × ≥5 row in 30 min window check（含 strategy_quality post §4.3.1 wireup）
  - LEFT JOIN expected 確保缺 domain 也出現結果（GROUP BY domain 缺 row → loop 漏 domain → 偽 PASS 反模式防護）
  - sentinel `$OPENCLAW_HEARTBEAT_DIR/ac1b_monthly_healthcheck.last_run` touch（per checks_cron_heartbeat.py 範式）
  - crontab spec `30 3 1 * *` 月初 03:30 UTC（per PA spec §5.2.3 避撞 passive_wait_healthcheck 6h cron）
  - exit 0/1/2 PASS/FAIL/DB-error

## §2.3 SCRIPT_INDEX update

- `helper_scripts/SCRIPT_INDEX.md`
  - L4: 最後更新時間戳 update 為 2026-05-23
  - L6-12: 新增 「2026-05-23 Sprint 5+ Wave 1 §4.4 production hardening」 section 含 4 行 script entry（health_60s_boundary_verify.sh / .sql / health_f2_sanitize_monitor.sh / ac1b_monthly_healthcheck.sh）

# §3 關鍵 diff

## §3.1 open_fd_count ladder (metric_emitter/mod.rs)

```rust
// Before
pub fn classify_engine_runtime_open_fd_count(value: u32) -> HealthState {
    if value > 4096 {
        HealthState::HealthDegraded
    } else if value >= 1024 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

// After
pub fn classify_engine_runtime_open_fd_count(value: u32) -> HealthState {
    if value > 6144 {
        HealthState::HealthDegraded
    } else if value >= 3072 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}
```

## §3.2 ws_rtt_p50_ms ladder (domains/api_latency.rs)

```rust
// Before
pub fn classify_api_latency_ws_rtt_p50_ms(value: u32) -> HealthState {
    if value > 150 {
        HealthState::HealthDegraded
    } else if value >= 50 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

// After
pub fn classify_api_latency_ws_rtt_p50_ms(value: u32) -> HealthState {
    if value > 300 {
        HealthState::HealthDegraded
    } else if value >= 170 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}
```

## §3.3 既有 test fixture amend

```rust
// api_latency.rs L922 — test_api_latency_emitter_critical_sample_propagates
// Before: ws_rtt_p50_ms: 200,
// After:  ws_rtt_p50_ms: 350,
//   為什麼 200 → 350：200ms 新 ladder 落 WARN band 非 DEGRADED；保持本
//   case「ws_rtt_p50 DEGRADED」原意必用 >300
```

# §4 治理對照

## §4.1 16 根本原則 compliance

per PA report §7.3：
- 原則 1 單一寫入口：本 hardening 不改寫入路徑（無 IntentProcessor / submit_intent 涉及）✓
- 原則 4 策略不繞風控：classify ladder 是 health observability 不是 risk gate ✓
- 原則 6 失敗默認收縮：F-2 sanitize 已 fail-loud skip；本 hardening 補 monitoring 對齊保守原則 ✓
- 原則 8 交易可解釋：V106 row 仍含 metric_value + state + state_prev + dwell_time_sec 可追溯 ✓
- 原則 14 零外部成本可運行：grep + psql + bash 全本地 ✓

## §4.2 硬邊界 grep (per profile 啟動序列)

```
execution_state | execution_authority | live_execution_allowed | decision_lease_emitted | max_retries | OPENCLAW_ALLOW_MAINNET | live_reserved | authorization.json
```

本 IMPL **0 觸碰** ✓

## §4.3 注釋規範對齊（bilingual-comment-style skill）

- 新 unit test docstring 中文為主（per skill 「新代碼注釋默認中文」）
- ladder 改動的 doc comment 新增 production hardening note 全中文
- 既有 ladder doc comment 內既有中英對照塊未動（per skill 「Existing bilingual blocks are not cleaned unless touched」）

## §4.4 跨平台兼容（per profile §3）

- `health_f2_sanitize_monitor.sh` GNU date `-d` (Linux) / BSD date `-v` (Mac) cross-platform fallback
- 全 3 script 無硬編碼 `/home/ncyu` / `/Users/ncyu` 路徑；走 `OPENCLAW_BASE_DIR` / `OPENCLAW_SECRETS_ROOT` env override

## §4.5 PA dispatch packet 禁忌核驗

- 不改 60s boundary IMPL（code-level verified per PA-4） ✓
- 不 enable F-2 monitor by default（DISABLED 等 §4.2.2 wireup 後） ✓
- 不 commit ✓
- 不派下游 sub-agent ✓
- 中文為主 / 0 emoji ✓

# §5 build + test 驗證

## §5.1 cargo build --release --lib

```
Finished `release` profile [optimized] target(s) in 24.82s
warning: `openclaw_engine` (lib) generated 2 warnings  ← 既有 warning，非我引入
0 error
```

## §5.2 cargo test --release --lib health::domains::api_latency

```
running 15 tests
test health::domains::api_latency::tests::test_classify_rest_p95_ms_thresholds ... ok
test health::domains::api_latency::tests::test_classify_ret_code_4xx_count_thresholds ... ok
test health::domains::api_latency::tests::test_classify_rest_p99_ms_thresholds ... ok
test health::domains::api_latency::tests::test_classify_rest_p50_ms_thresholds ... ok
test health::domains::api_latency::tests::test_classify_ret_code_5xx_count_thresholds ... ok
test health::domains::api_latency::tests::test_classify_ws_rtt_p99_ms_thresholds ... ok
test health::domains::api_latency::tests::test_ws_rtt_p50_demo_baseline_163_is_ok ... ok       ← 新加
test health::domains::api_latency::tests::test_classify_ws_dropout_count_thresholds ... ok
test health::domains::api_latency::tests::test_classify_ws_rtt_p50_ms_thresholds ... ok        ← 對齊新 ladder
test health::domains::api_latency::tests::test_sample_into_metric_rows_emits_8_rows ... ok
test health::domains::api_latency::tests::test_ws_rtt_p50_jitter_250_warn ... ok                ← 新加
test health::domains::api_latency_probe_impl::tests::test_probe_empty_returns_zero ... ok
test health::domains::api_latency_probe_impl::tests::test_probe_reflects_instrumentation_state ... ok
test health::domains::api_latency::tests::test_api_latency_emitter_critical_sample_propagates ... ok  ← fixture amend
test health::domains::api_latency::tests::test_api_latency_emitter_returns_8_metric_samples ... ok

test result: ok. 15 passed; 0 failed; 0 ignored; 0 measured; 3180 filtered out
```

## §5.3 cargo test --release --lib health::metric_emitter

```
running 10 tests
test health::metric_emitter::tests::test_engine_runtime_sample_classify_cpu_thresholds ... ok
test health::metric_emitter::tests::test_engine_runtime_sample_classify_rss_thresholds ... ok
test health::metric_emitter::tests::test_open_fd_count_3500_warn ... ok                          ← 新加
test health::metric_emitter::tests::test_engine_runtime_sample_heartbeat_dead_critical ... ok
test health::metric_emitter::tests::test_open_fd_count_baseline_1800_is_ok ... ok                ← 新加
test health::metric_emitter::tests::test_engine_runtime_sample_into_metric_rows_6_metrics ... ok
test health::metric_emitter::tests::test_rolling_window_aggregator_5_sample_bessel_sigma_spec_sample ... ok
test health::metric_emitter::tests::test_rolling_window_aggregator_below_capacity_mean_only ... ok
test health::metric_emitter::tests::test_rolling_window_aggregator_overflow_pops_oldest ... ok
test health::metric_emitter::tests::test_rolling_window_aggregator_single_sample_no_sigma ... ok

test result: ok. 10 passed; 0 failed; 0 ignored; 0 measured; 3185 filtered out
```

## §5.4 bash -n syntax PASS

```
60s_boundary_verify.sh: bash -n PASS
f2_sanitize_monitor.sh: bash -n PASS
ac1b_monthly_healthcheck.sh: bash -n PASS
```

# §6 不確定之處 / 副作用識別

## §6.1 build state 觀察（非我引入但需 E2 注意）

verify 過程觀察到既有 working tree（git status `M` + `??`）已有別 session WIP 改動：
- `rust/openclaw_engine/src/health/domains/risk_envelope_probe_impl.rs` (M, +321 line) — §4.3.4 F-4 correlation 加 5th argument 到 `update_from_pipeline_snapshot`，caller `main_health_emitters.rs:580` 未同步
- `rust/openclaw_engine/src/health/domains/pipeline_throughput_probe_impl.rs` (??, 新檔) — 內含 `HealthWarning` typo（應為 `HealthWarn`）
- `rust/openclaw_engine/src/health/domains/mod.rs` 新增 `pub mod database_pool_probe_impl;` declare 但 file 不存在

**影響**：
1. `cargo build --release --bin openclaw-engine`（含 bin link）失敗 → 1 error E0061（risk_envelope 5th arg 缺）
2. `cargo test --release --lib` 反覆跑會牽連 untracked `pipeline_throughput_probe_impl.rs` 的 `HealthWarning` typo + missing `database_pool_probe_impl` module → 3 error E0432/E0583/E0599
3. `cargo build --release --lib` 仍 PASS — lib production code clean

**證明非我引入**：
- 4 ladder amend file (`metric_emitter/mod.rs` + `api_latency.rs`) 純 surgical edit 無 module declare 改
- `cargo build --release --lib` PASS = 我的改動完全 clean compile
- 第一輪 `cargo test --release --lib health::domains::api_latency` 跑 15/15 PASS（含我 2 新 baseline test），第一輪 `cargo test --release --lib health::metric_emitter` 跑 10/10 PASS（含我 2 新 baseline test） — 證明改動正確
- 第二輪 cargo test 失敗是 untracked `pipeline_throughput_probe_impl.rs` 與 `database_pool_probe_impl` 缺檔被 lib test binary compile 牽連

**Operator/PM 建議**：別 session 的 §4.3.4 F-4 / §4.3.5 Track B/C real probes IMPL 尚未 land 完整（caller 未同步 + typo 未修 + module file 未建）；本 §4.4 hardening 已 build PASS 不 block，但完整 cargo test --release --lib（不限 path）跑前須先 land §4.3.4/5 fix。

## §6.2 既有 test fixture amend 影響

`test_api_latency_emitter_critical_sample_propagates` 改 `ws_rtt_p50_ms: 200 → 350`：
- 不影響本 test 邏輯（assert ws_rtt_p50 → DEGRADED 不變）
- 不影響其他 test fixture（grep 結果 200 仍存於 `ws_rtt_p99_ms: 200` 其他 test - 不衝突）

## §6.3 注釋補充三 fn rest_p50/p95/p99

per PA spec §2.3.3「rest_p50/p95/p99 維持 ladder 不變，補注釋」— 已執行。但部分 doc comment 變長（rest_p99 從 11 行擴到 19 行）；對其他 caller 無影響（doc comment 不參與 compile）。

# §7 Operator 下一步

per PA report §7.6 流程：

1. **E2 round 1 review**（per PA §2.5 30 min effort）：確認 ladder 不影響 amp cap / cascade / writer 路徑
   - 重點審查 3 點 (per PA §7.5)：
     - **§2.3.1 open_fd_count baseline 3072 校準依據**：E2 必驗 production 25 symbol 真實 fd footprint Linux empirical（`docker exec engine ls /proc/{pid}/fd/ | wc -l` 應落 1700-1800）；amend 後 1800 必 OK / 3500 必 WARN unit test 全跑
     - **§2.3.2 ws_rtt 170ms baseline 對 demo / live_demo 適用但 mainnet 切換必 recalibrate**：E2 確認注釋有 "mainnet 切換 sprint 開新 calibrate ladder" warning；不留盲區（已落地於 ws_rtt_p50 doc comment「Live mainnet endpoint 物理距離可能不同；mainnet 切換時須重 calibrate ladder」）
     - **§5.2.2 AC-1b script PGPASSWORD vs PG_PASSWORD 變量名一致性**：E2 grep `PG_PASSWORD` 應全 `PGPASSWORD`（傳統 libpq env var 名）；已落地 ac1b_monthly_healthcheck.sh 全用 `PGPASSWORD`

2. **E4 regression**（per PA §2.5 30 min）：cargo test --release lib 全跑（先解 §6.1 §4.3.4/5 untracked WIP 後跑 full lib test）

3. **operator deploy + crontab install**（per PA §6.1 Phase F 30 min）：
   - rebuild engine（`bash helper_scripts/restart_all.sh --rebuild`）+ 6h Linux empirical 重驗 open_fd / ws_rtt ladder 不再誤觸（per PA §7.6 expected post-deploy: open_fd_count 711 row WARN → 全 OK；ws_rtt_p50_ms 47 row WARN → 全 OK）
   - crontab install (per PA §5.2.3)：`30 3 1 * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/db/ac1b_monthly_healthcheck.sh >>/tmp/openclaw/logs/ac1b_monthly_healthcheck.cron.log 2>&1`
   - F-2 monitor crontab spec **不 install**（DISABLED-by-default 等 §4.2.2 wireup 後）

4. **PM 統一 commit + push**（per E1→E2→E4→QA→PM 鏈）

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint5_wave1_4_4_production_hardening_impl.md`）

---

# §8 Round 2 Fix Log（2026-05-23）

per E2-5 round 1 review RETURN-TO-E1（1 HIGH + 3 MEDIUM + 2 LOW；E2-5 verdict 由 PM 主對話收）：

## §8.1 HIGH-1 fix — `tests/sprint2_track_d_api_latency.rs`

| 行 | Before | After |
|---|---|---|
| 711-713 docstring | `ws_p50=200 DEGRADED` | `ws_p50=350 DEGRADED (>300 per Sprint 5+ Wave 1 §4.4 amend)` |
| 742 fixture | `ws_rtt_p50_ms: 200, // DEGRADED (>150)` | `ws_rtt_p50_ms: 350, // DEGRADED (>300 per §4.4 amend)` |

為什麼必修：§4.4 ladder amend 後 ws_p50=200 落 **WARN band** 非 DEGRADED；docstring + fixture 仍寫舊 DEGRADED 會誤導 reviewer + 在「全 4 DEGRADED + 4 CRITICAL」testname 語義下與 fixture 行為脫節（assert 仍會 PASS 因為 contains check 是 metric_name 不是 state，但語意保證已破）。

驗證：`cargo test --release --test sprint2_track_d_api_latency` 7/7 PASS（含 `test_sprint2_track_d_api_latency_degraded_band_classify`）。

## §8.2 MEDIUM-1 fix — `helper_scripts/db/ac1b_monthly_healthcheck.sh`

env var convention drift（對齊 `passive_wait_healthcheck/checks_cron_heartbeat.py` mainstream）：

| 點 | Before | After |
|---|---|---|
| L34 docstring | `OPENCLAW_HEARTBEAT_DIR (default: /tmp/openclaw/cron_heartbeat)` | `OPENCLAW_CRON_HEARTBEAT_DIR (default: $OPENCLAW_DATA_DIR/cron_heartbeat → /tmp/openclaw/cron_heartbeat)` + `OPENCLAW_DATA_DIR` parent fallback 變量說明 |
| L44 var name + fallback | `SENTINEL_DIR="${OPENCLAW_HEARTBEAT_DIR:-/tmp/openclaw/cron_heartbeat}"` | `DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"` + `SENTINEL_DIR="${OPENCLAW_CRON_HEARTBEAT_DIR:-$DATA_DIR/cron_heartbeat}"` + 注釋對齊 `checks_cron_heartbeat.py:45-48` |
| L136 sentinel filename | `ac1b_monthly_healthcheck.last_run` | `ac1b_monthly_healthcheck.last_fire` + 為什麼此命名注釋（避被 cron_heartbeat WARN-by-default check 漏接） |

為什麼必修：`checks_cron_heartbeat.py:39` `_DEFAULT_HEARTBEAT_SUBDIR = "cron_heartbeat"` + `:6` doc-comment `<name>.last_fire` + `test_cron_heartbeat_healthchecks.py:74,253,283` 全用 `OPENCLAW_CRON_HEARTBEAT_DIR` + `.last_fire`；`OPENCLAW_HEARTBEAT_DIR` 是新引入的 drift 變量名，sentinel 走 `.last_run` 偏離既有 WARN-by-default health check 模式 → 即使 cron fire sentinel，passive_wait_healthcheck check 也認不到。

## §8.3 MEDIUM-2 fix — `helper_scripts/db/health_60s_boundary_verify.sh`

bash numeric check 反 `2>/dev/null` 抑制（反 except:pass 反模式 per `feedback_working_principles` 「誠實報告測試」）：

§2 samples_per_min 段 + §3 30min_summary 段同時改：

```bash
# Before（兩段都有）:
elif [[ -n "$samples" && "$samples" -gt 2 ]] 2>/dev/null; then
if [[ -z "$row_count" || "$row_count" -lt 25 ]] 2>/dev/null; then

# After:
if [[ ! "$samples" =~ ^[0-9]+$ ]]; then
  echo "[FAIL] §2 ... samples_per_min='$samples' (非數字；SQL parse 漏接 or column drift)"
  FAIL_COUNT=$((FAIL_COUNT + 1))
elif (( samples > 2 )); then ...

if [[ ! "$row_count" =~ ^[0-9]+$ ]]; then
  echo "[FAIL] §3 ... row_count='$row_count' (非數字；SQL parse 漏接 or column drift)"
  FAIL_COUNT=$((FAIL_COUNT + 1))
elif (( row_count < 25 )); then ...
```

為什麼必修：原 `2>/dev/null` 抑制把「非數字」靜默歸 OK band；SQL parse 漏接（NULL column / column drift）會被埋掉 → fail-loud 原則破。改為顯式 regex check + 非數字必 FAIL（fail loud）。

## §8.4 MEDIUM-3 fix — `docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md`

§2.3.3 「設計理由」段尾補「Sprint 5+ Wave 1 §4.4 amend（2026-05-23）」section：

- L144 `ws_rtt_p50_ms` row：OK<50/WARN 50-150/DEGRADED>150 → **OK<170/WARN 170-300/DEGRADED>300**
- 補 `engine_runtime.engine_open_fd` ladder amend：OK<1024/WARN 1024-4096/DEGRADED>4096 → **OK<3072/WARN 3072-6144/DEGRADED>6144**
- 兩條 amend 附 Linux 6h empirical 1700-1800 fd / 150-163ms ws_rtt baseline rationale + mainnet recalibrate 警示

為什麼必修：spec 是 SSOT；ladder code amend 後 spec 仍寫舊值 → 未來 reviewer 不知哪邊權威 → drift 累積。

## §8.5 LOW-1 fix — `helper_scripts/db/ac1b_monthly_healthcheck.sh:18` crontab spec doc-comment

| Before | After |
|---|---|
| `30 3 1 * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/db/ac1b_monthly_healthcheck.sh` | `30 3 1 * * ${OPENCLAW_BASE_DIR:-/home/ncyu/BybitOpenClaw/srv}/helper_scripts/db/ac1b_monthly_healthcheck.sh` + 為什麼此抽象注釋 |

為什麼修：避硬編碼 `/home/ncyu` 阻礙未來 Apple Silicon Mac 部署（per CLAUDE §六 跨平台 portability mandate）。

## §8.6 LOW-2 fix — `docs/CCAgentWorkSpace/Operator/2026-05-23--sprint5_wave1_production_hardening_design.md`

front-matter `status` 加 round 2 amendment note + 指向 canonical PA dispatch packet + design spec §2.3.3 為 SSOT；不再同步 ladder 數字。

為什麼修：Operator workspace mirror 不是 SSOT；不標 deprecated/redirect 會造成「兩處 ladder 不一致 → 不知哪邊權威」。

## §8.7 驗證結果

| 驗證項 | 結果 |
|---|---|
| `bash -n ac1b_monthly_healthcheck.sh` | PASS |
| `bash -n health_60s_boundary_verify.sh` | PASS |
| `cargo test --release --test sprint2_track_d_api_latency` | 7 passed; 0 failed |
| `cargo test --release --lib health::domains::api_latency` | 15 passed; 0 failed |
| `cargo test --release --lib health::metric_emitter` | 10 passed; 0 failed |

## §8.8 修改清單（round 2）

| 檔 | 修改類型 | 行 |
|---|---|---|
| `rust/openclaw_engine/tests/sprint2_track_d_api_latency.rs` | HIGH-1 docstring + fixture | 711-713, 742 |
| `helper_scripts/db/ac1b_monthly_healthcheck.sh` | MEDIUM-1 env var + sentinel | 18 crontab spec, 34 docstring, 44 var name+fallback, 132-138 comment+filename |
| `helper_scripts/db/health_60s_boundary_verify.sh` | MEDIUM-2 numeric check | 124-148（§2 samples_per_min + §3 30min_summary 兩段 regex + fail-loud） |
| `docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md` | MEDIUM-3 ladder + amend | 144 ws_rtt_p50 row + 155 後新加 「Sprint 5+ Wave 1 §4.4 amend」 section |
| `docs/CCAgentWorkSpace/Operator/2026-05-23--sprint5_wave1_production_hardening_design.md` | LOW-2 mirror amendment note | 6-13 front-matter |

## §8.9 E2 round 2 readiness

預期 E2 round 2 重點審查：

1. **HIGH-1 確認**：docstring `ws_p50=350` 與 fixture `ws_rtt_p50_ms: 350` 一致；test_name `_degraded_band_classify` 語義對齊 fixture 全 8 metric DEGRADED/CRITICAL。
2. **MEDIUM-1 確認**：grep `OPENCLAW_CRON_HEARTBEAT_DIR` + `.last_fire` 全 ac1b script + checks_cron_heartbeat.py convention 同步；不再使用 `OPENCLAW_HEARTBEAT_DIR` / `.last_run` drift 命名。
3. **MEDIUM-2 確認**：`2>/dev/null` 已從兩處 numeric check 移除；非數字 sample 路徑必 FAIL 而非靜默歸 OK。
4. **MEDIUM-3 確認**：spec L144 ladder + open_fd amend note 與 code（metric_emitter/mod.rs L346-371 + api_latency.rs L303-336）一致。
5. **LOW 確認**：跨平台 portability + Operator mirror redirect note。
6. **業務邏輯 0 改動**：cargo test 全 PASS = round 1 行為不變。

E1 ROUND 2 FIX DONE: 待 E2 round 2 審查（同 report path 內 §8 round 2 fix log）
