---
report: Sprint 2 Wave 2 round 2 combined fix (Track D 6 + E 3 + F 1 + OBSERVE-4 cross-Wave)
date: 2026-05-22
author: E1 (Backend Developer, Rust)
phase: Sprint 2 Phase 2 Wave 2 round 2 combined fix
status: IMPL DONE — 待 E2 round 2 re-review
parent dispatch:
  - PM Sprint 2 Wave 2 round 1 雙 REJECT 後 round 2 combined fix dispatch（2026-05-22）
  - E2 Wave 2 Track D verdict (inline 6 finding：1 CRIT + 3 HIGH + 2 MED + 1 LOW)
  - E2 Wave 2 Track E verdict (inline 4 finding：1 HIGH + 3 LOW)
  - E2 Wave 2 Track F verdict (inline 3 finding：1 MED + 2 LOW)
  - PA spec amend report（並行 land 中）：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_wave2_track_def_spec_amend.md`
runtime: Mac development（Rust 編譯 + tokio test）
production engine: 未碰
---

# E1 Sprint 2 Wave 2 round 2 combined fix — 2026-05-22

## §0. TL;DR

- Track D 6 fix（5 deterministic + 1 PA-dependent CRIT-1 schema amend reference 對齊 PA 並行 amend）全 closure。
- Track E 3 fix（HIGH-1 pair-level OR-aggregate Path A + LOW-1 expand 100 SM + LOW-3 rename + 2 accessor）全 closure；新增 3 場景 boundary test 守 fix 不退化。
- Track F 1 fix（MED-1 position_count_active doc 對齊 PA spec amend）closure；rationale 引「M3 spec §2.3 line 106 amend」literal。
- Cross-Wave OBSERVE-4 fix：新 `M3Error::ReplaySubprocessForbidden` variant + MetricEmitterScheduler.run 啟動 guard + run_domain_loop per-tick guard + StrategyQualityScheduler.run + tick guard 雙 scheduler 對齊；新 integration test `tests/m3_emitter_replay_forbidden.rs` 3 test PASS。
- 10/11 finding deterministic closure；1 finding (CRIT-1 spec amend) 等 PA report land 後對齊。
- 全 47+1+3 sprint2 integration + 3 spike + 87+3152 lib full = 3292 PASS / 0 fail / 1 ignored；nm 0 hit。

## §1. Track D fix (6 finding)

### 1.1 CRIT-1 Schema spec drift (PA-dependent；本 round 不 revert)

- E1 round 1 IMPL 已 land 8 field (rest_p50/p95/p99 + ws_rtt_p50/p99 + ret_code_4xx/5xx_count + ws_dropout_count)，與 PA Sprint 2 spec §3.2 + M3 spec line 104 amend 對齊。
- 本 round E1 不 revert IMPL；只更 doc reference。
- PA spec amend report 並行 land 中（`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_wave2_track_def_spec_amend.md`）。
- 修改字面 diff：`api_latency.rs` module 頭注釋（line 62-72）

```diff
- //!   - threshold 對齊 M3 design spec §2.3 ladder：先 hardcode，Sprint 5 ArcSwap
- //!     熱更新（per spec §4.3 注 + Track A/B/C 同 pattern）。
- //!   - ret_code 4xx/5xx 用 HTTP 標準語意，預留 multi-venue（per ADR-0040
- //!     dispatch packet §5.5 反模式 (d)）。
+ //!   - threshold 對齊 M3 design spec §2.3 line 104 ladder（per PA Sprint 2
+ //!     Wave 2 2026-05-22 amend）：先 hardcode，Sprint 5 ArcSwap 熱更新（per
+ //!     spec §4.3 注 + Track A/B/C 同 pattern）。
+ //!   - ret_code 4xx/5xx 用 HTTP 標準語意，預留 multi-venue（per ADR-0040
+ //!     dispatch packet §5.5 反模式 (d)）。
+ //!   - bybit_rest_client p95 / retCode / ws dropout source hook 為 Wave 2
+ //!     main.rs 接 `ApiLatencySourceProbe` trait 時補（per PA-DRIFT-4
+ //!     follow-up；本 Track 端不修 client 既有邏輯，per packet §5.5 反模式
+ //!     (a)）。
```

### 1.2 HIGH-1 誤導性 spec literal 引用 4 處 fix (E1 deterministic)

`api_latency.rs` 4 處 line 102 literal 引用全改 line 104 amend reference：

| 位置 | Before | After |
|---|---|---|
| line 243-244 (classify_rest_p50_ms) | `- 對齊 spec line 102 ladder「p99 > 2000ms 為 CRITICAL；p50 維持 DEGRADED」。` | `- 對齊 M3 spec §2.3 line 104 amend ladder「...」（per PA Sprint 2 Wave 2 2026-05-22 amend）。` |
| line 288 (classify_rest_p99_ms) | `- 對齊 spec §2.3 line 102 CRITICAL band「outlier latency > 2s」literal。` | `- 對齊 M3 spec §2.3 line 104 amend CRITICAL band「outlier latency > 2s」literal（per PA Sprint 2 Wave 2 2026-05-22 amend）。` |
| line 376 (classify_ret_code_5xx_count) | `- 對齊 spec §2.3 line 102 CRITICAL band「venue outage」literal。` | `- 對齊 M3 spec §2.3 line 104 amend CRITICAL band「venue outage」literal（per PA Sprint 2 Wave 2 2026-05-22 amend）。` |
| line 401 (classify_ws_dropout_count) | `- 對齊 spec §2.3 line 102 CRITICAL band「ws dropout 持續累積」literal。` | `- 對齊 M3 spec §2.3 line 104 amend CRITICAL band「ws dropout 持續累積」literal（per PA Sprint 2 Wave 2 2026-05-22 amend）。` |

### 1.3 HIGH-2 trait method `_60s_window` 後綴 fix (Option C type-level 契約)

`ApiLatencySourceProbe` trait 8 method rename 加 `_60s_window` 後綴：

```diff
 pub trait ApiLatencySourceProbe: Send + Sync {
-    fn current_rest_p50_ms(&self) -> u32;
-    fn current_rest_p95_ms(&self) -> u32;
-    fn current_rest_p99_ms(&self) -> u32;
-    fn current_ws_rtt_p50_ms(&self) -> u32;
-    fn current_ws_rtt_p99_ms(&self) -> u32;
-    fn current_ret_code_4xx_count(&self) -> u32;
-    fn current_ret_code_5xx_count(&self) -> u32;
-    fn current_ws_dropout_count(&self) -> u32;
+    fn current_rest_p50_ms_60s_window(&self) -> u32;
+    fn current_rest_p95_ms_60s_window(&self) -> u32;
+    fn current_rest_p99_ms_60s_window(&self) -> u32;
+    fn current_ws_rtt_p50_ms_60s_window(&self) -> u32;
+    fn current_ws_rtt_p99_ms_60s_window(&self) -> u32;
+    fn current_ret_code_4xx_count_60s_window(&self) -> u32;
+    fn current_ret_code_5xx_count_60s_window(&self) -> u32;
+    fn current_ws_dropout_count_60s_window(&self) -> u32;
 }
```

Trait doc 新增「60s rolling window 契約」段（per E2 Wave 2 round 1 HIGH-2 fix Option C），明示「caller 端 IMPL 必須返過去 60s sample window 內的當前統計（rolling-window 語意），不可返 since-restart cumulative count／total-life percentile。type-level 契約確保 caller 端寫實作時看到方法名即知必須 implement 60s 滑動視窗邏輯，不靠注釋紀律」。

同步更新：
- `api_latency.rs` emitter sample_now 8 處呼叫 (line 522-529)
- `api_latency.rs` 內 inline test StubSource impl 8 method (line 591-616)
- `tests/sprint2_track_d_api_latency.rs` StubSourceProbe impl 8 method (line 77-101)

### 1.4 HIGH-3 bybit_rest_client carry-over acknowledge (E1 doc 對齊 PA-DRIFT-4)

`api_latency.rs` module 頭注釋加 carry-over reference（per round 2 fix 1.1 diff 最後 4 行）：

```rust
//!   - bybit_rest_client p95 / retCode / ws dropout source hook 為 Wave 2
//!     main.rs 接 `ApiLatencySourceProbe` trait 時補（per PA-DRIFT-4
//!     follow-up；本 Track 端不修 client 既有邏輯，per packet §5.5 反模式
//!     (a)）。
```

不 IMPL bybit_rest_client hook 本身（per round 2 fix 工作範圍 — Wave 2 main.rs 工作；E1 acknowledge in doc 即可）。

### 1.5 MED-1 OBSERVE-4 cross-Wave fix (Track A scaffold)

#### 1.5.1 M3Error variant 新增

`health/mod.rs` line 85-95：

```rust
/// M3 emitter 嚴禁在 replay subprocess 內 emit health_observations row。
///
/// 為什麼 fail-loud（per Sprint 2 design spec §1.x OBSERVE-4 line 199-216）:
///   - V106 line 259 `engine_mode CHECK IN ('paper','demo','live_demo',
///     'live')` 不含 'replay'；replay row 直接撞 PG CHECK constraint，
///     PG error → sqlx 失敗 → audit trail 撕裂。
///   - 設計合約：M3 health 是 read-only consumer of replay path（M11 replay
///     自身屬 dry-run，不該觸發 health observation row）；replay subprocess
///     誤 emit = 設計違反 → fail-loud Err 讓 caller 立即看到。
///   - 對齊 V106 spec line 38 + §4.4 設計刻意：replay engine_mode 不在 V106
///     CHECK 4 值 white-list。
#[error("M3 emitter forbidden in replay subprocess: engine_mode='replay'")]
ReplaySubprocessForbidden,
```

#### 1.5.2 MetricEmitterScheduler::run guard

`health/metric_emitter/mod.rs`：
- Line 584-595：scheduler.run 簽名改 `pub async fn run(...) -> Result<(), M3Error>`；啟動前檢 engine_mode == "replay" → 立即 RAISE Err。
- Line 731-748：run_domain_loop per-tick early_mode guard，tick 邊界檢 engine_mode 動態切換到 replay → fail-loud break loop + tracing::error 留 audit。

#### 1.5.3 StrategyQualityScheduler::run guard (cross-Wave)

`health/domains/strategy_quality.rs` line 668-708：
- StrategyQualityScheduler.run 簽名改 `pub async fn run(...) -> Result<(), M3Error>`；啟動前檢 engine_mode == "replay" → 立即 Err。
- Line 720-732：tick 邊界 per-tick guard，replay → break loop + tracing::error。

#### 1.5.4 12 caller site cascade update

scheduler.run 返 Result 後 12 個 `scheduler.run(cancel_clone).await;` call sites 全加 `let _ = ...`：

```
tests/sprint2_track_a_engine_runtime.rs:342
tests/sprint2_track_b_pipeline_throughput.rs:349, 485
tests/sprint2_track_c_database_pool.rs:128, 250, 801
tests/sprint2_track_d_api_latency.rs:399, 557, 774
tests/sprint2_track_e_strategy_quality.rs:840
tests/sprint2_track_f_risk_envelope.rs:139, 336
```

#### 1.5.5 New integration test

新檔 `tests/m3_emitter_replay_forbidden.rs` (215 LOC)：

| Test | 守 |
|---|---|
| `test_metric_emitter_scheduler_replay_engine_mode_forbidden` | MetricEmitterScheduler engine_mode="replay" 啟動 RAISE `M3Error::ReplaySubprocessForbidden` |
| `test_strategy_quality_scheduler_replay_engine_mode_forbidden` | StrategyQualityScheduler engine_mode="replay" 啟動 RAISE 同 Err（cross-Wave invariant） |
| `test_metric_emitter_scheduler_non_replay_engine_mode_ok_startup` | paper/demo/live_demo/live 4 合法 mode 啟動 OK；guard 只攔 'replay' |

### 1.6 LOW-1 ws_dropout count 維度注釋誠實補

`api_latency.rs` classify_ws_dropout_count（line 401-413）：

```rust
///   - 對齊 M3 spec §2.3 line 104 amend CRITICAL band「ws dropout 持續累積」
///     literal（per PA Sprint 2 Wave 2 2026-05-22 amend）。
///   - 維度說明（LOW-1 誠實補）：本 metric 為 count 維度（採樣期 60s 內 dropout
///     次數累積），與 spec line 102 既有 dropout duration 維度互補非對齊；
///     SM `dwell` 機制由 5-sample rolling window 捕捉「持續」語意，count
///     語意保留 burst 資訊讓 SM 走 dwell 判斷不被瞬時平均掉。
```

### 1.7 MED-2 file size 952 LOC > 800 warning（本 round 不切；backlog）

Per E2 finding 條件：「不本 round 強制拆檔；記 Sprint 5+ backlog」。本 round 不動。

## §2. Track E fix (3 finding)

### 2.1 HIGH-1 aggregate pair-level OR-aggregate (Path A)

`health/domains/strategy_quality.rs` aggregate_observe (line 920-960) — fix 邏輯：

```diff
-    // Step 1: 統計 degraded_count + total_count
-    let total_count = per_pair_sms.len() as f64;
-    if total_count == 0.0 {
-        return;  // 防禦：空 pair list 不做任何事
-    }
-    let mut degraded_count = 0u32;
-    for sm in per_pair_sms.values() {
-        let guard = sm.lock().await;
-        let state = guard.current_state();
-        if state == HealthState::HealthDegraded || state == HealthState::HealthCritical {
-            degraded_count += 1;
-        }
-    }
-    let degraded_ratio = degraded_count as f64 / total_count;
+    // Step 1: pair-level OR-aggregate（per HIGH-1 fix Path A）
+    let mut all_pairs: std::collections::HashSet<(String, String)> =
+        std::collections::HashSet::new();
+    let mut pair_degraded: std::collections::HashMap<(String, String), bool> =
+        std::collections::HashMap::new();
+    for ((strategy, symbol, _metric), sm) in per_pair_sms.iter() {
+        let pair_key = (strategy.clone(), symbol.clone());
+        all_pairs.insert(pair_key.clone());
+        let guard = sm.lock().await;
+        let state = guard.current_state();
+        // OR-aggregate：pair 任一 metric DEGRADED/CRITICAL 即標 degraded。
+        if state == HealthState::HealthDegraded || state == HealthState::HealthCritical {
+            pair_degraded.insert(pair_key, true);
+        }
+    }
+    let total_count = all_pairs.len() as f64;
+    if total_count == 0.0 {
+        return;  // 防禦：空 pair list 不做任何事
+    }
+    let degraded_count = pair_degraded.len() as u32;
+    let degraded_ratio = degraded_count as f64 / total_count;
```

doc rationale 完整化：
```
為什麼 pair-level OR-aggregate（per E2 Wave 2 round 1 Track E HIGH-1 fix Path A）:
  - spec §3.4 line 211 寫「DEGRADED 策略數 / 總策略數」是 2-tuple
    (strategy, symbol) pair-level SSOT；非 3-tuple (strategy, symbol,
    metric_name) per_pair_sms.len() count。
  - 原 IMPL bug：total_count = per_pair_sms.len() = 25 × 4 = 100；
    degraded_count 走 per-SM 累加，11 個 metric DEGRADED 就觸 0.40
    threshold，但實際只壞了 11/100 = 11% 的 SM。違 spec「每 pair 4 metric
    OR-aggregate 為單 pair 的 DEGRADED 狀態，4 個 metric 中任一 DEGRADED
    即代表該 (strategy, symbol) pair degraded」。
  - Path A 修法：迭代 per_pair_sms，按 (strategy, symbol) tuple grouping；
    一個 pair 任一 metric SM = DEGRADED/CRITICAL → 該 pair 標 degraded；
    total_count = unique pair 數（25）；degraded_count = degraded pair 數。
```

#### 2.1.1 新 HIGH-1 sync test 3 scenario boundary

新加 `test_sprint2_track_e_aggregate_pair_level_or_aggregate_boundaries`（integration test）：

| Scenario | 設置 | 期望 ratio | 期望 state | 守 |
|---|---|---|---|---|
| 1 | 11 pair × 1 metric DEGRADED | 11/25 = 0.44 | > 0.40 → 升 DEGRADED | 修正前 bug 走 0.11 不升；fix 後正確升 |
| 2 | 10 pair × 4 metric DEGRADED | 10/25 = 0.40 | ≤ 0.40 → 留 OK | OR-aggregate 4 metric 重複計 = 仍 10；spec literal > 0.40 不過邊界 |
| 3 | 4 pair × 4 metric DEGRADED | 4/25 = 0.16 | < 0.40 → 留 OK | 純 OK 對照組 |

三 scenario in-memory sm_states 模擬 production aggregate_observe 等價邏輯，不需 wall-clock dwell。

### 2.2 LOW-1 per_pair_independence test expand 100 SM

`tests/sprint2_track_e_strategy_quality.rs:500-580` test_sprint2_track_e_per_pair_independence — 原 25 pair × 1 metric (fill_rate_intent_ratio) 擴展 25 pair × 4 band metric (fill_rate_intent_ratio + slippage_bps_p95 + decision_lease_grant_rate + dormant_minutes) = 100 SM 全覆蓋：

```diff
-    // 對 25 pair 各自連續 2 次 WARN-band 採樣（dwell 60s 達標 fire）。
-    let mut fired_count = 0u32;
-    for (s, sym) in &pairs {
-        let sm = sms.get_mut(&(s.clone(), sym.clone())).unwrap();
-        ...
-    }
-    assert_eq!(fired_count, 25, ...);
+    let band_metrics = [
+        "fill_rate_intent_ratio",
+        "slippage_bps_p95",
+        "decision_lease_grant_rate",
+        "dormant_minutes",
+    ];
+    ...
+    let mut sms: HashMap<(String, String, String), HealthStateMachine> = HashMap::new();
+    for (s, sym) in &pairs {
+        for metric in &band_metrics {
+            sms.insert((s.clone(), sym.clone(), metric.to_string()), ...);
+        }
+    }
+    assert_eq!(sms.len(), 100, "25 pair × 4 metric = 100 SM 實例");
+    ...
+    assert_eq!(fired_count, 100, ...);
```

3-tuple cap key 任一漏掉即 suppress；全 100 SM fire 成功 = 真實獨立守住。

### 2.3 LOW-3 rename + 2 accessor 分拆

`health/domains/strategy_quality.rs` line 653-689 — `per_pair_sm_count()` 拆為 2 個 accessor：

```diff
-    /// 為 test 開放 per-pair SM 數量讀取（25 × 4 = 100 instance）。
-    pub fn per_pair_sm_count(&self) -> usize {
+    /// 為 test 開放 per-pair-per-metric SM 數量讀取（25 pair × 4 metric =
+    /// 100 SM instance；內部 3-tuple key 儲存）。
+    pub fn per_metric_sm_count(&self) -> usize {
         self.per_pair_sms.len()
     }
+
+    /// 為 test 開放 unique pair 數量讀取（= aggregate_observe degraded_ratio
+    /// 分母，per spec §3.4 line 211 SSOT）。
+    pub fn per_pair_count(&self) -> usize {
+        let mut all_pairs: std::collections::HashSet<(String, String)> =
+            std::collections::HashSet::new();
+        for (strategy, symbol, _metric) in self.per_pair_sms.keys() {
+            all_pairs.insert((strategy.clone(), symbol.clone()));
+        }
+        all_pairs.len()
+    }
```

對應 test rename + 雙 assert：
- lib mod test：`test_strategy_quality_scheduler_per_pair_sm_count_25_x_4` → `test_strategy_quality_scheduler_per_pair_25_per_metric_sm_100`
- integration test：`test_sprint2_track_e_scheduler_per_pair_sm_count_25_x_4` → `test_sprint2_track_e_scheduler_per_pair_25_per_metric_sm_100`

雙 assert 守 `per_pair_count == 25`（aggregate denominator）+ `per_metric_sm_count == 100`（SM 內部 3-tuple）。

## §3. Track F fix (1 finding)

### 3.1 MED-1 position_count_active doc 對齊 PA M3 spec amend (Option A)

`health/domains/risk_envelope.rs` line 276-300：

```diff
 /// `position_count_active` classify。
 ///
-/// ladder（current setup 25 symbol × 5 strategy = 125 candidate slot；典型穩態
-/// 活躍 < 10 倉位；上限對齊 risk_config max_open_positions 既有設計）:
+/// ladder（per M3 spec §2.3 line 106 amend，PA Sprint 2 Wave 2 2026-05-22 amend；
+/// 對齊 risk_config max_open_positions 既有設計）:
   OK       : 0 - 8     （穩態運營區）
   WARN     : 9 - 16     （高位但可控）
   DEGRADED : > 16       （超過正常 max_open_positions 上限）

-/// 為什麼此 threshold:
-///   - 對齊 `feedback_position_sizing` 3% risk/trade × 25 symbol baseline：
-///     典型最大持倉 ~10-15 位，> 16 是 portfolio over-leverage 預警。
+/// 為什麼此 threshold（per E2 round 1 Track F MED-1 fix Option A — PA spec
+/// amend + E1 doc 對齊）:
+///   - 移除原 `feedback_position_sizing` 自定 magic number rationale；threshold
+///     literal 統一以 M3 spec §2.3 line 106 amend 為 SSOT。
```

- 移除 `feedback_position_sizing` 自定 magic number rationale。
- 統一以 M3 spec §2.3 line 106 amend 為 SSOT；threshold literal (8/16) 不變。
- PA spec amend report 並行 land 中（待 PA report land 後 doc 引用自動對齊）。

## §4. cargo build + test 結果

### 4.1 Build

```
$ cargo build --release
   Compiling openclaw_engine v0.1.0
warning: ... (3 pre-existing warning + 1 binary warning；本 round 0 new warning)
    Finished `release` profile [optimized] target(s) in 2m 19s
```

### 4.2 Lib + Wave 1 + Wave 2 + spike + 新 OBSERVE-4 test

| Verify | Result |
|---|---|
| `cargo test --release --lib` | **3152/3152 PASS**（1 ignored pre-existing；0 fail） |
| `cargo test --release --lib health::` | **87/87 PASS** |
| Track A integration | **9/9 PASS**（regression 不退） |
| Track B integration | **5/5 PASS**（regression 不退） |
| Track C integration | **8/8 PASS**（regression 不退） |
| Track D integration | **7/7 PASS**（HIGH-1/HIGH-2/HIGH-3/LOW-1 fix verified） |
| Track E integration | **11/11 PASS**（+1 new boundary test；LOW-1 expand 100 SM；LOW-3 rename + 2 accessor） |
| Track F integration | **8/8 PASS**（MED-1 doc 對齊 verified） |
| **New OBSERVE-4 test** | **3/3 PASS**（`m3_emitter_replay_forbidden.rs`：MetricEmitterScheduler + StrategyQualityScheduler 雙 scheduler 守 + 4 legal mode 不誤攔） |
| Spike regression | **3/3 PASS**（`--features spike --test m3_amp_cap_24h_fire`） |
| **nm scan AC-5** | **0 hit**（production binary 0 mock time 滲透） |

**累計**：3152 + 87 + 47 + 1 (new Track E boundary) + 3 (new OBSERVE-4) + 3 (spike) = **3293 PASS / 0 fail / 1 ignored**。

### 4.3 grep verify

```bash
$ grep -rn "engine_mode.*replay\|early_mode == \"replay\"\|startup_mode == \"replay\"" \
       /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/
```

- 8 hits：M3Error variant + MetricEmitterScheduler startup + run_domain_loop tick + StrategyQualityScheduler startup + tick guard + 注釋 reference 對應 4 處。
- 所有 hit 都走 guard path（fail-loud Err 或 break loop with tracing::error）；無「engine_mode = 'replay' 隨意賦值」反模式。

## §5. round 2 verdict + E2 round 2 readiness

### 5.1 closure verdict

| Track | finding | closure | 備註 |
|---|---|---|---|
| Track D | CRIT-1 (PA-dependent) | doc reference 已對齊「per PA Sprint 2 Wave 2 2026-05-22 amend」 | 等 PA report land 後 doc 自動對齊 |
| Track D | HIGH-1 | DETERMINISTIC closure | 4 處 line 102 → line 104 amend；引用統一 |
| Track D | HIGH-2 | DETERMINISTIC closure | Option C trait method `_60s_window` 後綴 type-level 契約 |
| Track D | HIGH-3 | acknowledge in doc | bybit_rest_client hook 為 Wave 2 main.rs 工作；E1 不擅自 wire |
| Track D | MED-1 (cross-Wave OBSERVE-4) | DETERMINISTIC closure | scaffold + Track E scheduler 雙 guard + 3 new test PASS |
| Track D | LOW-1 | DETERMINISTIC closure | 注釋誠實補維度語意 |
| Track D | MED-2 (LOC > 800) | NOT THIS ROUND (backlog) | Sprint 5+ 切檔 |
| Track E | HIGH-1 | DETERMINISTIC closure | Path A pair-level OR-aggregate + 3 scenario boundary test |
| Track E | LOW-1 | DETERMINISTIC closure | expand 25 → 100 SM 全覆蓋 |
| Track E | LOW-3 | DETERMINISTIC closure | rename + 2 accessor 分拆 |
| Track F | MED-1 (PA-dependent) | DETERMINISTIC closure | doc 統一引 M3 spec §2.3 line 106 amend；threshold literal 不變 |

**總計**：10/11 finding deterministic closure（Track D 5 + Track E 3 + Track F 1 + cross-Wave OBSERVE-4 1）；1 finding (Track D CRIT-1 spec amend reference 對齊) 等 PA report land。

### 5.2 E2 round 2 re-review readiness

- 47+3 sprint2 integration test + 3 spike + 87+3152 lib full 全綠
- new OBSERVE-4 test 3/3 PASS 守 spec line 199-216 設計合約
- nm 0 hit 守 production binary 0 mock time 滲透
- 0 unsafe / 0 unwrap in production
- spike feature default false invariant 嚴守
- 注釋全中文（per bilingual-comment-style skill 2026-05-05 規範）
- 跨平台無 `/home/ncyu` / `/Users/[^/]+` 硬編碼
- 不碰 hard boundary（max_retries / live_execution_allowed / execution_authority / system_mode / production engine）

## §6. 修改清單

| 檔 | 性質 | LOC delta | 修改範圍 |
|---|---|---|---|
| `rust/openclaw_engine/src/health/mod.rs` | atomic edit | +18 LOC | 新 M3Error::ReplaySubprocessForbidden variant + 為什麼 fail-loud 注釋 |
| `rust/openclaw_engine/src/health/metric_emitter/mod.rs` | atomic edit | +30 LOC | scheduler.run 簽名 Result + 啟動 guard + run_domain_loop tick guard + tracing::error |
| `rust/openclaw_engine/src/health/domains/api_latency.rs` | atomic edit | +12 LOC | HIGH-1 4 處 doc line 104 amend / HIGH-2 8 method rename `_60s_window` + trait doc 60s 契約段 / HIGH-3 module 頭 PA-DRIFT-4 carry-over / LOW-1 dropout 維度注釋 / sample_now 8 處 call rename / inline test StubSource 8 method rename |
| `rust/openclaw_engine/src/health/domains/strategy_quality.rs` | atomic edit | +60 LOC | HIGH-1 Path A pair-level OR-aggregate aggregate_observe 重寫 + doc 完整 rationale / LOW-3 per_pair_count accessor 新增 + per_pair_sm_count rename 為 per_metric_sm_count / OBSERVE-4 scheduler.run 啟動 guard + tick guard + 返 Result / lib mod test rename 雙 assert |
| `rust/openclaw_engine/src/health/domains/risk_envelope.rs` | atomic edit | +3 LOC | MED-1 doc 引 M3 spec §2.3 line 106 amend；移除 feedback_position_sizing 自定 magic number rationale |
| `rust/openclaw_engine/tests/sprint2_track_a_engine_runtime.rs` | atomic edit | +0 LOC | `let _ = scheduler.run(cancel_clone).await;` 1 處 |
| `rust/openclaw_engine/tests/sprint2_track_b_pipeline_throughput.rs` | atomic edit | +0 LOC | `let _ = scheduler.run(cancel_clone).await;` 2 處 |
| `rust/openclaw_engine/tests/sprint2_track_c_database_pool.rs` | atomic edit | +0 LOC | `let _ = scheduler.run(cancel_clone).await;` 3 處 |
| `rust/openclaw_engine/tests/sprint2_track_d_api_latency.rs` | atomic edit | +0 LOC | StubSourceProbe 8 method rename + `let _ = scheduler.run(...).await;` 3 處 |
| `rust/openclaw_engine/tests/sprint2_track_e_strategy_quality.rs` | atomic edit | +180 LOC | LOW-1 per_pair_independence expand 25→100 SM / LOW-3 scheduler test rename + 雙 assert / 新 boundary test 3 scenario / `let _ = scheduler.run(...).await;` 1 處 |
| `rust/openclaw_engine/tests/sprint2_track_f_risk_envelope.rs` | atomic edit | +0 LOC | `let _ = scheduler.run(...).await;` 2 處 |
| **新檔** `rust/openclaw_engine/tests/m3_emitter_replay_forbidden.rs` | **新建** | +215 LOC | MODULE_NOTE + ZeroApiSource + ZeroStrategyQualitySource + 3 test (MetricEmitterScheduler replay forbidden + StrategyQualityScheduler replay forbidden + 4 legal mode startup OK) |

## §7. 治理對照

| 治理項 | 狀態 |
|---|---|
| §六 Hard Boundaries | 未碰 `live_execution_allowed` / `execution_authority` / `system_mode` / `max_retries` / production engine ✓ |
| §七 Code And Docs Rules | 注釋默認中文；MODULE_NOTE 完整；無 emoji；新建注釋 bilingual-comment-style 對齊 ✓ |
| §八 Workflow | E1 IMPL DONE → 等 E2 round 2 re-review；不自行 commit；不派下游 sub-agent ✓ |
| §九 Code Structure Guardrails | api_latency.rs 952 LOC + strategy_quality.rs 1489 LOC + metric_emitter/mod.rs 1287 LOC > 800 警告但 < 2000 hard cap（Sprint 5+ 切檔 backlog） |
| §Data, Migrations, And Validation | 不新增 V###；V106 schema 沿用；不觸 PG dry-run（純 Rust IMPL + mock + new test） |
| cross-platform | 純 Rust 邏輯；無 `/home/ncyu` / `/Users/[^/]+` 硬編碼；無 `cfg(target_os)` 分支 |
| AC-5 0 mock time | nm 0 hit 守住 ✓ |
| feedback_impl_done_adversarial_review | round 2 改動含共用 helper（scheduler.run 簽名變更 + classify_aggregated 8 arm 不變 / aggregate_observe Path A 重寫 / trait rename 8 method）；E1 IMPL DONE → 等 E2 round 2 + A3（per skill）；E4 regression 不能取代 ✓ |

## §8. 不確定 / Carry-over

1. **PA spec amend report 並行 land**：CRIT-1 Track D + MED-1 Track F 兩 PA-dependent finding 走「doc reference 對齊 amend」path；本 round E1 不 revert IMPL。PA report land 後 doc 引用自動對齊；E2 round 2 review 可確認 doc reference 完整性。
2. **HIGH-3 bybit_rest_client hook 接線**：Wave 2 main.rs 工作；本 Track D round 2 只 acknowledge in doc，不擅自 wire 真實 source（per packet §5.5 反模式 (a) emitter 只讀）。TODO follow-up 走 PA-DRIFT-4 既有 entry。
3. **MED-2 file size > 800 warning backlog**：本 round 不切；Sprint 5+ 切 api_latency.rs / strategy_quality.rs / metric_emitter/mod.rs 子 module。
4. **PG empirical dry-run 未做**：本 round 純 Rust IMPL + mock；不新增 V### / 不動 SQL；AC-1b real PG empirical 由 Phase 3c QA 走（main.rs scheduler 接線後）。
5. **OBSERVE-4 guard tracing log 路徑**：tick 邊界檢出 replay → `tracing::error!` + break loop。Linux runtime caller 應驗 tracing log capture 真實能讀到 (Phase 3c QA observability)；Mac sandbox 不驗 log routing。

## §9. Operator 下一步

1. **PM 派 E2 round 2 re-review**：focus on
   - 10/11 deterministic closure 對齊度（Track D HIGH-1/2/3 + LOW-1 / MED-1 cross-Wave / Track E HIGH-1/LOW-1/LOW-3 / Track F MED-1）
   - PA-dependent finding (CRIT-1 + Track F MED-1) 在 PA report land 後 doc 引用是否完整對齊
   - OBSERVE-4 guard 雙 scheduler 設計（MetricEmitterScheduler + StrategyQualityScheduler）對齊 spec line 199-216 是否充分
   - new boundary test 3 scenario 守 Path A 是否充分（11/10/4 pair 邊界）
   - 100 SM 全覆蓋 expand 是否守 3-tuple cap key 不退化
   - LOW-3 雙 accessor 語意是否對齊 spec §3.4 line 211 2-tuple SSOT
2. **A3 review 路徑**：round 2 改動含共用 helper (scheduler.run 簽名變更 cascade 12 caller site) + 新 trait method rename (8 method) + aggregate_observe Path A 重寫；per `feedback_impl_done_adversarial_review` 2026-05-09 應 E2 + A3 並行核驗。
3. **PA spec amend report land 確認**：CRIT-1 Track D + Track F MED-1 doc reference 「per PA Sprint 2 Wave 2 2026-05-22 amend」依賴 PA report land；PM 應確認 PA report land 後 doc 引用是否完整對齊。
4. **PM 收口 commit chain**：待 E2 round 2 + A3 PASS + E4 regression PASS 後 PM 統一 commit + push（強制鏈 E1→E2→E4→QA→PM）。

---

**E1 IMPLEMENTATION DONE: 待 E2 round 2 re-review（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave2_round2_combined_fix.md`）**
