---
report: Sprint 4+ first Live Wave B round 2 fix — E2 round 1 REJECT 後 1 HIGH + 2 MEDIUM + 3 LOW closure
date: 2026-05-23
author: E1 (Backend Developer, Rust)
phase: Sprint 4+ first Live Wave B — E1 round 1 IMPL DONE → E2 round 1 REJECT → E1 round 2 fix
status: ROUND 2 FIX DONE — 待 E2 round 2 review
parent dispatch:
  - PM Sprint 4+ Wave B round 2 dispatch（operator prompt 2026-05-23）
  - E2 Wave B round 1 verdict（inline；1 HIGH + 2 MEDIUM + 3 LOW）
  - E1 Wave B round 1 IMPL `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint_4_wave_b_main_scheduler_wireup.md`
runtime: Mac development（cargo build + cargo test）
production engine: 未碰
---

# E1 Sprint 4+ Wave B round 2 fix — 2026-05-23

## §0. TL;DR

E2 round 1 REJECT 5 條 finding 本 round 2 全 closed：
- **HIGH-1**：Track B placeholder 5 metric 從全 0 改 spec line 102 OK band 合法值（tick_rate=2.0 / signal_rate=1.0 / heartbeat=0 / drift=0 / ipc_p99=1.0）；inline test 擴 5 metric classify=HealthOk assertion；模塊 doc 補 rationale。
- **MEDIUM-2**：Track D WS half doc 補 ⚠️ 「emit chain disconnected from production supervisor」誠實揭露；E1 round 1 report 措辭修正在本 round 2 report §6.4 反映。
- **LOW-1**：本 round 2 report §5 重新 wc -l 實測 LOC + round 1 report 誤差表對齊。
- **LOW-2**：`emitter_count` log 從 hardcoded 5 改為 `emitters.len()` 動態。
- **LOW-3**：TODO.md §5.1 P1 queue 加 `W-S4-AC1B-HEALTHCHECK` entry（review_date 2026-05-24，SQL acceptance condition 完整）。

cargo test：**3510 PASS / 0 FAIL / 4 ignored**（與 round 1 baseline 完全持平不退）。HIGH-1 inline test 新增「5 metric classify=HealthOk」5 條 assertion 並入既有 test framework；total test count 不變（合併到單一 test fn）。strings scan mock_instant/tokio::time::pause = 0 + spike enum literal = 1（baseline 對齊）；nm scan = 0 hit 守 AC-5。

## §1. HIGH-1 Track B placeholder OK band fix

### 1.1 Bug 根因（E2 round 1 catch 詳）

E2 round 1 揭露：`main_health_emitters.rs:93-112` `PlaceholderPipelineThroughputSource` 5 metric default 全 0；但 classify ladder 對 0 值的回傳並非 HealthOk：

| metric | classify fn | value=0 結果 | spec line 102 OK band 期望 |
|---|---|---|---|
| tick_rate | `classify_pipeline_throughput_ws_tick_rate` (line 203) | `< 0.5 → DEGRADED` | `> 1.0 → OK` |
| signal_rate | `classify_pipeline_throughput_signal_rate` (line 293) | `< 0.1 → DEGRADED` | `>= 0.5 → OK` |
| heartbeat_lag_ms | `classify_pipeline_throughput_heartbeat_lag_ms` (line 237) | `<= 30000 → OK` ✓ | `<= 30000 → OK` |
| subscription_drift | `classify_pipeline_throughput_subscription_drift` (line 264) | `= 0 → OK` ✓ | `= 0 → OK` |
| ipc_p99 | `classify_pipeline_throughput_ipc_roundtrip_ms_p99` (line 314) | `< 5.0 → OK` ✓ | `< 5.0 → OK` |

**結論**：5 metric 內 **2 個（tick_rate / signal_rate）** value=0 → DEGRADED；30 天 V106 row 連續走 DEGRADED 染色；module doc 自稱「OK band 不誤升」與 IMPL 衝突。其餘 3 metric value=0 已對齊 OK band 合法值（heartbeat / drift / ipc）；但 emitter 端 5 metric 全部寫 V106 row，2 metric 染色 = `pipeline_throughput` domain row 整體記為 DEGRADED 級。

### 1.2 Fix 推薦 (a) — 5 metric 改 spec line 102 OK band 合法值

per dispatch §HIGH-1 推薦 (a) `placeholder OK band 對齊 spec line 102 literal`。本 round 採用嚴格 OK 值，留 boundary 緩衝避抖動：

| metric | round 1 default | round 2 default | classify 結果 | spec line 102 對齊 |
|---|---|---|---|---|
| `current_ws_tick_rate_per_sec` | `0.0` (DEGRADED) | **`2.0`** | OK band (>=1.0) | OK band「tick rate > 1/sec/symbol」嚴格 OK 留 1.0 緩衝 |
| `current_ws_heartbeat_lag_ms` | `0` (OK) | `0` | OK band (<=30000) | OK band 心跳節奏正常；原已合法 |
| `current_ws_subscription_drift_count` | `0` (OK) | `0` | OK band (=0) | OK band「subscription_drift = 0」明文；原已合法 |
| `current_strategy_signal_rate_per_min` | `0.0` (DEGRADED) | **`1.0`** | OK band (>=0.5) | OK band「signal_rate >= 0.5」嚴格 OK 留 0.5 緩衝 |
| `current_ipc_roundtrip_ms_p99` | `0.0` (OK) | **`1.0`** | OK band (<5.0) | OK band「ipc p99 < 5ms」；dispatch 給「10」實際走 DEGRADED ladder（line 314 `> 10 → DEGRADED`），本 round 採用嚴格 OK 值 1.0 |

**為什麼 ipc_p99 改 1.0 而非 dispatch 給的 10**：

dispatch §HIGH-1 (a) 範例「ipc_roundtrip_ms_p99=10」對齊 spec line 102 OK band 文字「ipc p99 < 5ms」嚴格 ladder 走 `> 10 → DEGRADED`；如果採用 10 則 ipc_p99 metric 染 DEGRADED 而非 OK，等於用 fix 引入新 bug。本 round 採用嚴格 OK 值 1.0（與 tick_rate=2.0 / signal_rate=1.0 同設計：留 boundary 緩衝避 5.0 邊界 jitter）。此偏離 dispatch 給的 literal 但對齊 dispatch §HIGH-1 設計意圖「placeholder OK band 對齊 spec line 102」。

### 1.3 main_health_emitters.rs LOC diff

| 項 | round 1 IMPL | round 2 fix | 差 |
|---|---|---|---|
| 模塊 doc Track B 邊界註腳 | 「placeholder probe（全返 0；Sprint 5+ wire-up）」 | 「placeholder probe（5 metric default 走 spec line 102 OK band 合法值，避誤升 DEGRADED；Sprint 5+ wire-up 接 ws_client / IndicatorEngine / IPC real metric；per round 2 HIGH-1 fix 2026-05-23）」 | doc 補注 +3 line |
| `PlaceholderPipelineThroughputSource` 段 doc | 約 13 line（rationale）| 約 46 line（補 round 2 HIGH-1 fix rationale + ladder 對照 + 5 default 值表）| +33 line |
| 5 metric default value | 全 0 | 2.0 / 0 / 0 / 1.0 / 1.0 | 2 value 改（tick_rate + signal_rate）+ 1 value 改（ipc_p99 從 0.0 改 1.0）|
| 5 metric inline doc | 1 line 每 metric | 3 line 每 metric（補 spec line 102 對齊 rationale + Sprint 5+ wire-up 接線分工）| +約 10 line |
| inline test `test_placeholder_pipeline_throughput_returns_zero` | 5 line（assert_eq 0/0/0/0/0）| 改名 `test_placeholder_pipeline_throughput_default_in_ok_band` + 擴 5 metric value assertion + 5 metric classify=HealthOk assertion | +約 50 line |

**main_health_emitters.rs**：528 LOC（round 1）→ **652 LOC**（round 2 +124）

### 1.4 inline test 守 5 metric 走 OK band

新 test `test_placeholder_pipeline_throughput_default_in_ok_band`：

```rust
// 5 default 值對齊 spec line 102 OK band 合法值（無 boundary 抖動）
assert_eq!(p.current_ws_tick_rate_per_sec(), 2.0);
assert_eq!(p.current_ws_heartbeat_lag_ms(), 0);
assert_eq!(p.current_ws_subscription_drift_count(), 0);
assert_eq!(p.current_strategy_signal_rate_per_min(), 1.0);
assert_eq!(p.current_ipc_roundtrip_ms_p99(), 1.0);

// 5 metric classify 結果 全 HealthOk（不誤升 DEGRADED/WARN）
assert_eq!(classify_pipeline_throughput_ws_tick_rate(2.0), HealthState::HealthOk, ...);
assert_eq!(classify_pipeline_throughput_heartbeat_lag_ms(0), HealthState::HealthOk, ...);
assert_eq!(classify_pipeline_throughput_subscription_drift(0), HealthState::HealthOk, ...);
assert_eq!(classify_pipeline_throughput_signal_rate(1.0), HealthState::HealthOk, ...);
assert_eq!(classify_pipeline_throughput_ipc_roundtrip_ms_p99(1.0), HealthState::HealthOk, ...);
```

verify command：`cargo test --release --bin openclaw-engine main_health_emitters::tests::test_placeholder_pipeline_throughput_default_in_ok_band`
result：**1 / 1 PASS** ✓

## §2. MEDIUM-2 Track D WS half disconnect doc 補注

### 2.1 main_health_emitters.rs:126-131 ⚠️ doc 補注（per round 2 MEDIUM-2 fix）

走 dispatch §MEDIUM-2 (a) `短期 doc 補注`（本 round 推薦）；(b) Sprint 5+ amend supervisor signature 屬 carry-over。

新增 ⚠️ doc 段（約 25 line）涵蓋：

1. **問題揭露**：`bybit_private_ws.rs:577-585` Wave A 已實裝 `dropout_counter_handle()` / `rtt_histogram_handle()` accessor，但本 module 沒呼叫；每次 `build_real_api_latency_probe` fresh `Arc::new(WsDropoutCounter::new())` + `Arc::new(WsRttHistogram::new())` 0-state instance。
2. **後果**：30 天 V106 row `api_latency__ws_rtt_p50_ms` / `__ws_rtt_p99_ms` / `__ws_dropout_count` 全 0 染色；此「全 0」**不是** production WS 健康指標反映「無 dropout / 低 latency」，而是 emit chain 從 production BybitPrivateWs supervisor 完全 disconnect 的副作用（fresh 0-state Arc 永遠不會被 production WS run loop 觀測 + accumulate）。
3. **誠實揭露 vs round 1 doc 措辭**：round 1 doc 自稱「OK band 不誤升」可能誤導 reviewer 推論「Track D WS half 實裝正確只是 0 觀測值」；事實是 placeholder OK band 對齊 spec line 104 OK band literal 是 placeholder 副作用，與 supervisor metric 0 連線。
4. **Wave B 走 (a) doc 補注 + Sprint 5+ carry-over**：本 round 不接 supervisor handle（needs `BybitPrivateWs::new()` signature 改為「caller 注入 external Arc」pattern；per `bybit_private_ws.rs:564-565` 既有 code「Arc::new(WsDropoutCounter::new())」在 struct 內部 own，外部無穩定 share Arc handle）；Sprint 5+ amend BybitPrivateWs supervisor signature 改造 + main.rs Wave 接時拿 supervisor handle clone 替換 placeholder fresh Arc。
5. **健康行為**：Wave C QA Phase 3c AC-1b 30 min 樣本 wait 端 operator 須意識到 4 row（ws_rtt_p50_ms / ws_rtt_p99_ms / ws_dropout_count + 衍生 classify=OK）**不是真實 WS 觀測**，是 placeholder 副作用；Sprint 5+ wire-up 接 supervisor 後 V106 row 才反映 production WS metric。

### 2.2 E1 round 1 report 措辭修正反映

E1 round 1 report `2026-05-23--sprint_4_wave_b_main_scheduler_wireup.md` §1.2 / §6.4 / §7 item 2 涉及 Track D WS half placeholder 文字（`§1.2` 走「real wire-up `+ ret_code_counter_handle()` Arc）+ WS half placeholder（`Arc::new(WsDropoutCounter::new())` + `Arc::new(WsRttHistogram::new())`）」/ `§7 item 2`「BybitPrivateWs 在 startup/private_ws.rs supervisor 內每次 attempt 重建」）原文措辭已點出「placeholder」+「supervisor 內部重建」+「無穩定 Arc 注入點」三事實；round 1 對「全 0 OK band」誤稱「不誤升」實際是 placeholder 副作用，不是 OK band 觀測值。

**round 2 修正措辭**（在本 round 2 report 反映；round 1 report 不回填編輯避「歷史 report 編輯」）:

| round 1 措辭 | round 2 修正措辭 |
|---|---|
| 「全 placeholder：4 個 0-state instance；REST 半邊 fallback」 | 「fresh 0-state instance；emit chain 從 production BybitPrivateWs supervisor disconnect；30 天 V106 row 全 0 染色是 placeholder 副作用而非 disconnect from supervisor metric；Sprint 5+ amend supervisor signature」 |
| 「OK band 不誤升」 | 「placeholder OK band 對齊 spec；emit chain disconnected from production supervisor」 |
| 「不誤升」 | 「placeholder 寫 0-state value；非真實 supervisor metric」 |

未來 Wave C / Sprint 5+ 文件統一用後者措辭。

## §3. LOW-1/2/3 fixes

### 3.1 LOW-1 report LOC 對齊

E1 round 1 report §0 / §5 LOC 數字與 wc -l 實測差異：

| File | round 1 report | round 1 wc -l | round 1 報告誤差 | round 2 修正 |
|---|---|---|---|---|
| `main_health_emitters.rs` | 478 LOC | 528 LOC | -50（report 漏算 inline test 2 個 + 5 個 wireup tracing event log line）| **528 LOC**（本 round 2 report §5 對齊）|
| `risk_envelope.rs` | 896→904（+8） | 908 LOC | round 1 base 896 是 PA-DRIFT-5 round 2 land 後值；round 1 IMPL +12 actual 落 908；report 報 +8 漏 4 line（額外 doc）| **+12 actual**（base 896 → 908）|
| `risk_envelope_probe_impl.rs` | 822→896（+74） | 958 LOC | round 1 base 822 是 PA-DRIFT-5 round 2 land 後值；round 1 IMPL +136 actual 落 958（含 F-2 sanitize 3 inline test）；report 報 +74 漏 62 line（doc + 3 inline test）| **+136 actual**（base 822 → 958）|
| `tests/main_scheduler_wireup.rs` | +295 LOC | 394 LOC | round 1 +295 是 net IMPL；report 漏 99 line（doc + 6 test fn body）| **394 LOC**（含 doc + 6 test body）|
| `main.rs` | 1448→1500（+52） | 1503 LOC | round 1 base 1448 → 1503 actual +55；report 報 +52 漏 3 line | **+55 actual**（base 1448 → 1503）|

round 2 修正以本 report §5 為準；round 1 report 不回填編輯保歷史 trace 完整。

### 3.2 LOW-2 emitter_count 動態

`main_health_emitters.rs:360` log `emitter_count=5` hardcoded → 改 `emitter_count = emitters.len()` 動態。

**diff**：

```diff
+    // 為什麼 emitter_count 動態計算（per round 2 LOW-2 fix；原 round 1 hardcoded
+    // = 5，Sprint 5+ Track E wire-up 後會 drift）:
+    //   - emitters vec 構造後 length = 當前實際 spawn emitter 數；Sprint 5+ Track
+    //     E StrategyQualityEmitter wire-up 後 vec.push 自動反映。
+    //   - 對齊 §九 反模式「assert/log 數值 hardcoded 會 drift」。
+    let emitter_count_for_log = emitters.len();
     let scheduler =
         MetricEmitterScheduler::new(emitters, writer, Arc::clone(&event_bus), engine_mode);
     ...
     tokio::spawn(async move {
         info!(
             target = "m3.health.wireup",
             engine_mode = %mode_for_log,
-            emitter_count = 5,
+            emitter_count = emitter_count_for_log,
             "M3 MetricEmitterScheduler spawning ..."
         );
```

**為什麼提前在 spawn 外 capture `emitters.len()`**：`emitters` Vec move 進 `MetricEmitterScheduler::new` 後 borrow 不可用；在 move 前 read len() 存 closure capture。

### 3.3 LOW-3 TODO healthcheck entry

`TODO.md §5.1 P1 queue` 加新 row（per `docs/agents/todo-maintenance.md` Passive waits 模板）：

```
| `W-S4-AC1B-HEALTHCHECK` | 2 | Sprint 4+ Wave C QA Phase 3c AC-1b 30 min sample
wait healthcheck — V106 emit chain real PG empirical 驗證；本 Wave B 9/9 子目標 1
⏳ healthcheck（Wave C deploy 後 land；per E1 round 2 Wave B fix report §3 LOW-3）|
Owner: QA + PM；Acceptance: SQL `SELECT domain, COUNT(*) FROM learning.health_
observations WHERE created_at > NOW() - INTERVAL '30 min' GROUP BY domain` ≥ 5
row per active domain（engine_runtime + database_pool + api_latency + risk_
envelope + pipeline_throughput placeholder OK band）；review_date 2026-05-24
（Linux `--rebuild` + 30 min wait 後）；前置：E2 round 2 PASS + E4 regression
PASS + PM commit + Linux deploy；Track E strategy_quality 0 row（per Sprint 5+
wire-up scope；本 healthcheck 不查 strategy_quality）|
```

對齊 `todo-maintenance.md` §Passive waits「healthcheck + scheduled review date + acceptance condition」三要素。

## §4. cargo test result（Wave A regression 不退）

| Verify | Command | Result | round 1 baseline | round 2 |
|---|---|---|---|---|
| Release build | `cargo build --release` | **PASS** — 12.78s | 27.25s | PASS |
| **HIGH-1 inline test** | `cargo test --release --bin openclaw-engine main_health_emitters::tests::` | **2 / 2 PASS** | 2/2 PASS | 不退 |
| **main_scheduler_wireup integration** | `cargo test --release --test main_scheduler_wireup` | **6 / 6 PASS** | 6/6 PASS | 不退 |
| health lib unit | `cargo test --release --lib health::` | **110 / 110 PASS** | 110/110 | 不退 |
| PA-DRIFT-4 regression | `cargo test --release --test api_latency_probe_real_impl` | **22 / 22 PASS** | 22/22 | 不退 |
| PA-DRIFT-5 regression | `cargo test --release --test risk_envelope_probe_real_impl` | **14 / 14 PASS** | 14/14 | 不退 |
| Sprint 2 Track B regression | `cargo test --release --test sprint2_track_b_pipeline_throughput` | **5 / 5 PASS** | 5/5 | 不退 |
| Spike feature m3 cap | `cargo test --release --features spike --test m3_amp_cap_24h_fire` | **3 / 3 PASS** | 3/3 | 不退 |
| **cargo test 全套（無 spike）** | `cargo test --release` 累計 | **3510 PASS / 0 FAIL / 4 ignored** | 3510/0/4 | **完全持平不退** |
| **AC-5 nm scan** | `nm openclaw-engine \| grep -E "(mock_instant\|tokio::time::pause\|spike)" \| wc -l` | **0** ✓ | 0 | 守 |
| AC-5 strings mock | `strings openclaw-engine \| grep -cE "(mock_instant\|tokio::time::pause)"` | **0** ✓ | 0 | 守 |
| AC-5 strings spike | `strings openclaw-engine \| grep -cE "spike"` | **1**（M3Error enum literal「domain not implemented in spike scope:」非 feature symbol）| 1 | 守 |

**結論**：3510 PASS 完全持平 round 1 baseline；HIGH-1 inline test 5 metric classify assertion 並入既有 `test_placeholder_pipeline_throughput_default_in_ok_band`（改名 from `test_returns_zero` + 擴 body），test count 不變但 coverage 提升；Wave A / Wave 1+2 / spike regression 全綠。

## §5. 修改清單（本 round 2）

| File | 性質 | 改動 LOC | round 1 → round 2 | 摘要 |
|---|---|---|---|---|
| `rust/openclaw_engine/src/main_health_emitters.rs` | extend | **+124** | 528 → 652 | HIGH-1 5 default 改 OK band 合法值 + module doc 補注 + Placeholder 段 doc rationale 擴 + 5 metric inline doc 擴 + inline test 改名 + 擴 5 metric classify assertion + MEDIUM-2 Track D WS half ⚠️ doc 補注 + LOW-2 emitter_count 動態 capture |
| `TODO.md` | extend | +1 row | 429 → 430 | LOW-3 §5.1 P1 queue 加 `W-S4-AC1B-HEALTHCHECK` entry |

**不動 file**：
- `risk_envelope.rs` / `risk_envelope_probe_impl.rs`（round 1 已 land；round 2 不擴 scope）
- `tests/main_scheduler_wireup.rs`（round 1 6 test 不需擴；本 round HIGH-1 fix coverage 由 inline test 守 placeholder default value）
- `main.rs`（round 1 接線完成；本 round 不擴 scope）
- `bybit_rest_client.rs` / `bybit_private_ws.rs`（per dispatch §禁忌 + MEDIUM-2 採用 (a) doc 補注路徑；supervisor signature 改造留 Sprint 5+ carry-over）

## §6. 治理對照（round 2）

| 項目 | 狀態 |
|---|---|
| **§六 Hard Boundaries** | 未碰 `live_execution_allowed` / `execution_authority` / `system_mode` / `max_retries` / production engine / trading_ai DB / V### SQL ✓ |
| **§七 Code And Docs Rules** | 新代碼注釋全中文（per `feedback_chinese_only_comments` 2026-05-05）；觸及既有 bilingual block 不主動清；無 emoji ✓；MEDIUM-2 doc 補 ⚠️ 屬「invariant + boundary why」對齊 `bilingual-comment-style` 規範 |
| **§八 Workflow** | E1 round 2 fix DONE → 等 E2 round 2 review；不自行 commit；不派下游 sub-agent ✓ |
| **§九 Code Structure Guardrails** | `main_health_emitters.rs` 652 LOC（< 800 OK；HIGH-1 + MEDIUM-2 doc 擴是 round 2 fix 必要 trace；無業務邏輯擴張）|
| **AC-5 production binary 0 mock time 滲透** | nm scan 0 hit + strings mock_instant/tokio::time::pause = 0 + spike enum literal 1 hit 非 feature symbol；對齊 round 1 baseline ✓ |
| **HIGH-1 fix 對齊 spec line 102 literal** | tick_rate=2.0 / signal_rate=1.0 走嚴格 OK；heartbeat=0 / drift=0 / ipc=1.0 對齊 OK band 明文 ✓ |
| **MEDIUM-2 (a) doc 補注 + (b) Sprint 5+ carry-over** | ✓；不改 bybit_private_ws supervisor signature；doc ⚠️ 段揭露 placeholder 副作用 |
| **LOW-1 LOC 對齊 wc -l 實測** | 本 round 2 report §5 列實測值；round 1 report 不回填編輯保歷史 trace ✓ |
| **LOW-2 emitter_count 動態** | `emitters.len()` 動態 capture；對齊 §九 反模式 ✓ |
| **LOW-3 TODO healthcheck entry** | TODO.md §5.1 加 `W-S4-AC1B-HEALTHCHECK`；對齊 `todo-maintenance.md` Passive waits 模板 ✓ |
| **反模式對齊**（per dispatch §禁忌） | (a) 不改 既有 bybit_rest_client/bybit_private_ws 業務邏輯 ✓ / (b) 不改 既有 risk_verdict_ledger/position_snapshot 寫入邏輯 ✓ / (c) 不引 V### / spike / IPC ✓ / (d) 不 commit ✓ / (e) 不派下游 sub-agent ✓ / (f) 中文為主 0 emoji ✓ / (g) 0 unsafe / 0 unwrap in production ✓ / (h) spike feature default false invariant 嚴守 ✓ |

## §7. round 2 verdict + E2 round 2 readiness + Wave C unblock 進度

### 7.1 round 2 verdict

| E2 round 1 finding | 狀態 | 證據 |
|---|---|---|
| **HIGH-1**：Track B placeholder 5 metric 全 0 走 DEGRADED 染色 | ✅ **CLOSED** | 5 default 改 OK band 合法值（tick_rate=2.0 / signal_rate=1.0 / ipc=1.0；heartbeat=0 / drift=0 原已合法）+ inline test 5 metric classify=HealthOk PASS |
| **MEDIUM-1**：6 new mutable singleton 未登記到 SSOT | ⏳ **PM 收口時派 PA** | per dispatch `NOT in scope`；本 round 不處理 |
| **MEDIUM-2**：Track D WS half emit chain disconnected from supervisor | ✅ **CLOSED (a) doc 補注路徑** | main_health_emitters.rs:126-131 ⚠️ doc 段 25 line + 本 report §6.4 措辭修正；(b) Sprint 5+ amend supervisor signature carry-over |
| **LOW-1**：E1 round 1 report LOC 數值不一致 | ✅ **CLOSED** | 本 round 2 report §3.1 + §5 列 wc -l 實測；round 1 report 保歷史 trace 不回填編輯 |
| **LOW-2**：emitter_count hardcoded 5 | ✅ **CLOSED** | `emitters.len()` 動態 capture；diff 反映 LOC +6 |
| **LOW-3**：TODO healthcheck entry 缺 | ✅ **CLOSED** | TODO.md §5.1 P1 queue 加 `W-S4-AC1B-HEALTHCHECK` entry（review_date 2026-05-24 + SQL acceptance 完整 + 前置條件對齊 commit chain）|

### 7.2 E2 round 2 readiness

| 項目 | 狀態 |
|---|---|
| HIGH-1 + MEDIUM-2 + LOW-1/2/3 五 finding closed | ✅ |
| cargo test 全綠不退（3510 PASS）| ✅ |
| Wave A regression 不退 | ✅（API latency 22 + risk envelope 14 + Sprint 2 Track B 5 + spike 3）|
| AC-5 production binary 0 mock time 守 | ✅（nm 0 + strings 0）|
| 反模式 (a)-(h) 8 條對齊 | ✅ |
| 治理 (§六/§七/§八/§九/§Data) 對齊 | ✅ |
| 不 commit + 不派下游 sub-agent | ✅ |

**結論**：本 round 2 fix 5 條 finding 全 closed；E2 round 2 review 可立即開始；HIGH-1 採用嚴格 OK 值 + inline test 守；MEDIUM-2 採用 (a) doc 補注路徑 + Sprint 5+ amend carry-over；3 LOW 全 closed。

### 7.3 Wave C unblock 進度

| 條件 | 狀態 |
|---|---|
| 1. Wave A round 2 PA-DRIFT-4 + PA-DRIFT-5 兩條 finding all closed（commit 4c84d1bb） | ✅ |
| 2. Wave B round 1 IMPL DONE | ✅ |
| 3. E2 Wave B round 1 review → REJECT 5 finding | ✅（round 1 catch verdict）|
| 4. E1 Wave B round 2 fix DONE（本 round） | ✅ |
| 5. E2 Wave B round 2 review APPROVE | ⏳ 待 E2 |
| 6. MEDIUM-1 singleton 登記（PM 派 PA） | ⏳ PM 收口時 |
| 7. E4 regression（cargo test 3510 PASS Mac + Linux release build） | ⏳ E4 |
| 8. PM 統一 commit + push（強制鏈 E1→E2→E4→QA→PM） | ⏳ PM |
| 9. Linux runtime `--rebuild` + 30 min 樣本累積 | ⏳ Operator |
| 10. Wave C QA Phase 3c AC-1b PG empirical 驗證 + sign-off | ⏳ QA + PM |

## §8. Operator 下一步

1. **PM 派 E2 round 2 review**：focus on
   - `main_health_emitters.rs` HIGH-1 fix 5 default 合理性（嚴格 OK 值 vs spec line 102 boundary）
   - `main_health_emitters.rs` MEDIUM-2 ⚠️ doc 補注完整性（揭露 supervisor disconnect 副作用）
   - inline test 5 metric classify=HealthOk assertion 正確性
   - LOW-2 emitter_count 動態 capture 邏輯（emitters.len() 提前在 move 前讀取）
   - TODO `W-S4-AC1B-HEALTHCHECK` entry 對齊 `todo-maintenance.md` Passive waits 模板

2. **PM 收口時 PA follow-up**：
   - MEDIUM-1 6 new mutable singleton 登記到穩定登記表（per profile 硬約束 5；本 round 2 不擴 scope per dispatch `NOT in scope`）
   - Sprint 5+ Track E StrategyQualityEmitter wire-up 接 PaperState SSOT
   - Sprint 5+ Track B PipelineThroughput real wire-up（接 ws_client / IndicatorEngine / IPC stats accessor）
   - Sprint 5+ Track C writer_queue / pool_wait_p95 real wire-up（market_writer Vec len + sqlx pool wait histogram）
   - Sprint 5+ Track D WS half amend BybitPrivateWs supervisor signature 改外部 Arc 注入 pattern
   - F-4 risk_envelope correlation real calculator（lookback amend）

3. **PM 收口 commit chain**：待 E2 round 2 PASS + E4 regression PASS 後 PM 統一 commit + push（強制鏈 E1→E2→E4→QA→PM）。

4. **Wave C QA Phase 3c**：commit/push + Linux `--rebuild` + 30 min 樣本 wait 後 QA AC-1b PG empirical 驗證（`W-S4-AC1B-HEALTHCHECK` entry）。

---

**E1 IMPLEMENTATION DONE: 待 E2 round 2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint_4_wave_b_round2_fix.md`）**
