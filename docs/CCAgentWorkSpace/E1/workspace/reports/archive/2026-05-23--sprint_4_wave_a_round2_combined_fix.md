---
report: Sprint 4+ Wave A round 2 combined fix — PA-DRIFT-4 (4 finding) + PA-DRIFT-5 (2 finding)
date: 2026-05-23
author: E1 (Backend Developer, Rust)
phase: Sprint 4+ first Live Wave A — E2 round 1 REJECT/APPROVE-WITH-CONDITIONS 修
status: IMPL DONE — 待 E2 round 2 review
parent dispatch:
  - PM Sprint 4+ Wave A round 2 combined fix dispatch (operator prompt 2026-05-23)
  - E2 PA-DRIFT-4 round 1 verdict (inline; 1 HIGH BLOCKER + 2 HIGH + 3 MED + 3 LOW)
  - E2 PA-DRIFT-5 round 1 verdict (inline; APPROVE-WITH-CONDITIONS 2 MED + 2 LOW)
  - E1 PA-DRIFT-4 round 1 IMPL `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint_4_pa_drift_4_bybit_instrumentation.md`
  - E1 PA-DRIFT-5 round 1 IMPL `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_4_pa_drift_5_risk_envelope_wireup.md`
runtime: Mac development（cargo build + cargo test）
production engine: 未碰
---

# E1 Sprint 4+ Wave A round 2 combined fix — 2026-05-23

## §0. TL;DR

合計 **6 finding combined fix**：

**PA-DRIFT-4 (4 finding)**：
- H-1 BLOCKER：noop retCode 5 個（110001/110008/110010/110043/170213）誤計 5xx → 加 `is_noop_retcode` helper + `record_for_error` 端 noop guard
- H-2：60s rolling window expire 0 test → 4 instrumentation 各加 `inject_sample_with_timestamp` test-only accessor + 4 boundary test
- H-3：retCode counter 觀測覆蓋率 < 50% → 觀測從 `_checked` 下沉到 `get`/`post` 內部；raw caller 也自動計入
- M-1：checked_sub fallback 注釋誤導 → 補 boot < 60s edge case 行為說明

**PA-DRIFT-5 (2 finding)**：
- F-1 (MED)：cap=100k comment 失誤 → 改注釋為「24h × push rate 隱式上限；無顯式 cap」(選項 a)
- F-3 (MED Wave B 前必修)：5-lock gap micro-race window → trait 加 default `snapshot_5_metric()` + `RealRiskEnvelopeSourceProbe` override 走 batch read（一次 lock）

cargo test：**3499 PASS / 0 FAIL / 4 ignored**（含 22 new + regression 不退）。nm AC-5 0 hit 守住。

## §1. PA-DRIFT-4 fix (4 finding)

### 1.1 H-1 BLOCKER fix — noop retCode 不計 4xx 也不計 5xx

**位置**：`rust/openclaw_engine/src/bybit_rest_client.rs:544-602`

**Bug**：原 `record_for_error` 對 `BybitApiError::Business` 任何 retCode 不屬 6 個 client fault → 全計 5xx；包含 noop 集合 110001 OrderNotFound / 110008 OrderCompletedOrCancelled / 110010 OrderAlreadyCancelled / 110043 LeverageNotModified / 170213 OrderNotExistSpot。違 ADR-0042 Decision 3 cascade gate = venue fault only 語意。

**Fix**：

```rust
pub fn record_for_error(&self, err: &BybitApiError) {
    match err {
        BybitApiError::Business { ret_code, .. } => {
            // noop guard：lifecycle race / 已套用設定 等「動作已完成」碼
            // 非 venue fault；直接跳過計數（per ADR-0042 cascade gate 語意）。
            if Self::is_noop_retcode(*ret_code) {
                return;
            }
            if Self::is_client_fault_retcode(*ret_code) {
                self.record_4xx();
            } else {
                self.record_5xx();
            }
        }
        _ => {}
    }
}

fn is_noop_retcode(ret_code: i64) -> bool {
    BybitRetCode::from_code(ret_code)
        .map(|c| c.is_noop())
        .unwrap_or(false)
}
```

**為什麼引用 `BybitRetCode::is_noop()` SSOT**：
- noop 集合已在 `BybitRetCode` enum 字典端 line 704-713 定義；復用同一 SSOT 避雙處飄移
- 未識別 retCode（不在 enum）→ `from_code` 返 `None` → 預設 `false`：保守對映為 venue fault（5xx），符合「未知 = venue fault」cascade 守則

LOC：+33 LOC（含 helper + doc 注釋 + noop guard）。

### 1.2 H-2 fix — 60s rolling window expire boundary 4 test

**位置**：4 個 instrumentation 各加 test-only accessor + 4 boundary test

**Bug**：既有 15 test 全 instant record + instant read；trait method name `_60s_window` 是 type-level contract 但 IMPL `samples.retain(|t| *t >= cutoff)` expire 邏輯從未實證跑過。

**Fix（兩階段）**：

#### Phase A: 4 instrumentation 加 `inject_sample_with_timestamp` test-only accessor

```rust
// bybit_rest_client.rs:434-446 (RestLatencyHistogram)
#[doc(hidden)]
pub fn inject_sample_with_timestamp(&self, ts: Instant, latency_ms: u64) {
    if let Ok(mut samples) = self.samples.lock() {
        samples.push((ts, latency_ms));
    }
}

// bybit_rest_client.rs:546-568 (RetCodeCounter inject_4xx + inject_5xx)
#[doc(hidden)]
pub fn inject_4xx_with_timestamp(&self, ts: Instant) { ... }

#[doc(hidden)]
pub fn inject_5xx_with_timestamp(&self, ts: Instant) { ... }

// bybit_private_ws.rs:193-204 (WsRttHistogram) + bybit_private_ws.rs:273-283 (WsDropoutCounter)
#[doc(hidden)]
pub fn inject_sample_with_timestamp(&self, ts: Instant[, ms: u64]) { ... }
```

**設計決定（與 `#[cfg(test)]` 取捨）**：

最初用 `#[cfg(test)]` cfg gate；compile 失敗 — integration test (`tests/api_latency_probe_real_impl.rs`) 是 **外部 crate**，看不到 cfg(test) 端方法。三選擇：
1. `pub` + `#[doc(hidden)]`：production 仍編譯但 rustdoc 不呈現；release build optimizer 端因無 production caller → 自動 drop（**已驗證 nm 0 hit `inject_*` symbol**）
2. `cfg(any(test, feature = "testutil"))`：引入新 feature flag；改動範圍擴大
3. 把 boundary test 移到 src 端 unit test：需要 重排 test file 結構

選 (1) 最小改動 + AC-5 守住：
- 加 `#[doc(hidden)]` 註明 test-only；emitter / probe production 路徑不調用（grep 確認 0 call site）
- nm scan AC-5 守則檢 `mock_instant` / `tokio::time::pause` / `spike` 三關鍵字；`inject_*` 不撞
- release build linker 端因 reachability analysis 自動 drop（nm 0 hit 實證）

#### Phase B: 4 boundary test 補完

`tests/api_latency_probe_real_impl.rs:444-589` 加 4 個 boundary test（每 instrumentation 一個）：

```rust
#[test]
fn test_rest_latency_60s_window_expire_boundary() {
    let histogram = RestLatencyHistogram::new();
    let now = Instant::now();
    histogram.inject_sample_with_timestamp(now.checked_sub(Duration::from_secs(61))..., 100);
    histogram.inject_sample_with_timestamp(now.checked_sub(Duration::from_secs(59))..., 200);
    histogram.inject_sample_with_timestamp(now, 300);
    assert_eq!(histogram.sample_count(), 2, "61s 外 sample 應 expire");
    let (p50, p95, p99) = histogram.percentile_triple();
    assert_eq!(p50, 200);  // sorted [200, 300]，p50 = sorted[0]
    assert_eq!(p95, 300);
    assert_eq!(p99, 300);
}

// 同模式：test_ws_rtt_60s_window_expire_boundary
// 同模式：test_ret_code_counter_60s_window_expire_boundary (4xx + 5xx 各驗)
// 同模式：test_ws_dropout_60s_window_expire_boundary
```

LOC：+90 LOC instrumentation accessor + +180 LOC boundary test。

### 1.3 H-3 fix — retCode 觀測下沉至 `get`/`post` 內部

**位置**：`bybit_rest_client.rs:1076-1101` (get) + `1130-1156` (post) + `_checked` 端簡化

**Bug**：原 `record_for_error` 只在 `_checked` 端呼；account_manager:267/342, position_manager:203, instrument_info:194/349 等 raw caller 走 `client.get(...)` + 手動檢 retCode → bypass observer，覆蓋率 < 50%。

**Fix（推薦方案 A：觀測下沉到 get/post 內部）**：

```rust
// get 端 hot path
self.update_rate_limit(&resp);
self.update_group_rate_limit(path, &resp);
let body = resp.text().await?;
let parsed: BybitResponse = serde_json::from_str(&body)?;
let elapsed_ms = call_start.elapsed().as_millis().min(u64::MAX as u128) as u64;
self.latency_histogram.record_latency(elapsed_ms);

// PA-DRIFT-4 round 1 H-3 fix：retCode 觀測下沉至 `get` / `post` 內部。
// 為什麼這裡而非 `_checked`：account_manager / position_manager /
// instrument_info 等 raw caller 走 `client.get(...)` 後手動檢 retCode（不
// 走 `_checked`），若觀測停在 `_checked` 端會 bypass > 50% caller 流量。
if !parsed.is_ok() {
    self.ret_code_counter.record_for_error(&BybitApiError::Business {
        ret_code: parsed.ret_code,
        ret_msg: parsed.ret_msg.clone(),
        response: serde_json::to_value(&parsed).unwrap_or_default(),
    });
}
Ok(parsed)
```

**`_checked` 端不再重複 record**（避雙重計）：

```rust
pub async fn get_checked(...) -> BybitResult<BybitResponse> {
    self.get(path, params).await?.into_result()
}
```

LOC：+20 LOC (get + post 各 10 LOC observer) - 8 LOC (`_checked` 簡化)。

**新 test**：`test_raw_caller_pattern_records_via_internal_observer`：模擬 raw caller 流程 3 venue fault + 1 client fault + 1 noop 注入，驗 counter 對齊（5xx=3 / 4xx=1 / noop=0）。

### 1.4 M-1 fix — checked_sub fallback 注釋

**位置**：`bybit_rest_client.rs:366-389` (record_latency cap 觸發注釋)

**Fix**：

```rust
// `checked_sub.unwrap_or(now)` fallback 語意（per E2 round 1 M-1 fix）：
//   - process boot > 60s normal path：cutoff = now - 60s，正常 retain
//     過濾 60s 外 sample。
//   - process boot < 60s edge case：Instant 算術下溢時 checked_sub 返
//     None；fallback cutoff = now，**所有歷史 sample 被 filter 掉**
//     （極端短期過渡；60s 後恢復正常 60s rolling window 語意）。
//   - 不會洩漏 sample（fail-safe 保守清空 < 不誤保留過期）；無實際業
//     務 bug — 8192 cap 已先確保緩衝不 unbounded。
```

LOC：+11 LOC（純注釋；無 code 改動）。

## §2. PA-DRIFT-5 fix (2 finding)

### 2.1 F-1 (MED) fix — cap=100k comment 失誤

**位置**：`risk_envelope_probe_impl.rs:114-129` (PortfolioStateCache cap 段注釋)

**Bug**：原注釋自稱 `cap = 100k`，但 code 無顯式 cap，僅靠 24h `drain_old_fills` / `drain_old_equity` 隱式上限。

**Fix（選 a：改 comment）**：

```rust
/// 為什麼無顯式 cap（per PA-DRIFT-5 round 1 E2 F-1 fix）:
///   - 上限 = 「24h × caller push rate」隱式上限；不設顯式 cap。
///     - 預期 fill push rate ≪ 1/s（策略 throttle + 風控 max_open_positions）；
///       上限 ≈ 86400 sample；多策略 burst 上限 ≈ 數十 k。
///     - equity push rate = caller 端 emitter sample_interval=300s tick；
///       上限 = 24h / 300s = 288 sample。
///   - 為什麼不設顯式 cap：sliding window `drain_old_fills` / `drain_old_equity`
///     在每次 `update_from_pipeline_snapshot` 端執行；24h 外 sample 自然 drain，
///     不會 unbounded。
///   - 若 caller 端 burst push（>> 1 fill/s 持續 24h）導致 sample 累積，本檔不
///     設顯式 cap 保護；caller 端責任（per dispatch packet §7.5 反模式 (a)：
///     emitter 不重做 risk_config 載入；burst 防禦由 caller 端 throttle）。
///   - Sprint 5 cascade IMPL 後若 emitter wire-up 端發現 burst pattern，可在
///     caller 端加 throttle；或在本檔加顯式 cap follow-up（PA Sprint 5 spec
///     amend）。
```

LOC：+10 LOC（純注釋）。

**為什麼選 (a) 改 comment 而非 (b) 加顯式 cap**：
- (b) 加顯式 cap 屬於業務邏輯改動 — 需 PA 拍板 cap 數值 + caller 端 burst handling 設計
- 24h drain 已是天然 fail-soft；caller 端走 emitter 300s tick + throttle 自然不會撞 cap
- F-1 是 MED 不是 BLOCKER；推薦 30 min comment fix 對齊「最小改動範圍」原則

### 2.2 F-3 (MED Wave B 前必修) fix — batch read helper

**位置**：
- `risk_envelope.rs:402-449` (trait default method + RiskEnvelopeSampleSnapshot struct)
- `risk_envelope_probe_impl.rs:345-370` (cache 端 snapshot_5_metric) + `:433-452` (RealProbe override)

**Bug**：5 trait method 各拿 5 次 lock；update 介入 5-lock gap 會產生 5-metric snapshot inconsistency micro-race window（如 PnL 已更新但 position_count 仍舊）。

**Fix**：

#### Trait 加 default snapshot method + Snapshot struct

```rust
pub trait RiskEnvelopeSourceProbe: Send + Sync {
    fn current_portfolio_cum_pnl_24h_usd(&self) -> f64;
    fn current_portfolio_max_dd_pct(&self) -> f64;
    fn current_position_count_active(&self) -> u32;
    fn current_correlation_avg_pairwise(&self) -> f64;
    fn current_concentration_top1_pct(&self) -> f64;

    /// batch read helper：一次取得 5 metric snapshot（per PA-DRIFT-5 round 1
    /// E2 F-3 fix）。
    ///
    /// 為什麼 default 而非 required：既有 mock / test fixture（如 StubSource /
    /// MockMutexRiskProbe）已 impl trait；強制要求新 method 會破壞 backward
    /// compat。default 走 5 個 current_xxx 結果語意等價（單 thread test 無
    /// race）。production RealRiskEnvelopeSourceProbe override 走 batch。
    fn snapshot_5_metric(&self) -> RiskEnvelopeSampleSnapshot {
        RiskEnvelopeSampleSnapshot {
            portfolio_cum_pnl_24h_usd: self.current_portfolio_cum_pnl_24h_usd(),
            portfolio_max_dd_pct: self.current_portfolio_max_dd_pct(),
            position_count_active: self.current_position_count_active(),
            correlation_avg_pairwise: self.current_correlation_avg_pairwise(),
            concentration_top1_pct: self.current_concentration_top1_pct(),
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct RiskEnvelopeSampleSnapshot {
    pub portfolio_cum_pnl_24h_usd: f64,
    pub portfolio_max_dd_pct: f64,
    pub position_count_active: u32,
    pub correlation_avg_pairwise: f64,
    pub concentration_top1_pct: f64,
}
```

#### `PortfolioStateCache::snapshot_5_metric()` 走 5 calculator 一次拍照

```rust
pub fn snapshot_5_metric(&self) -> RiskEnvelopeSampleSnapshot {
    RiskEnvelopeSampleSnapshot {
        portfolio_cum_pnl_24h_usd: self.cum_pnl_24h_usd(),
        portfolio_max_dd_pct: self.max_dd_pct_24h(),
        position_count_active: self.position_count_active(),
        correlation_avg_pairwise: self.correlation_avg_pairwise(),
        concentration_top1_pct: self.concentration_top1_pct(),
    }
}
```

#### `RealRiskEnvelopeSourceProbe::snapshot_5_metric()` override 走 batch（一次 lock）

```rust
impl RiskEnvelopeSourceProbe for RealRiskEnvelopeSourceProbe {
    fn current_portfolio_cum_pnl_24h_usd(&self) -> f64 { self.cache.lock().cum_pnl_24h_usd() }
    // ... 4 個既有 individual accessor 保留不變
    fn current_concentration_top1_pct(&self) -> f64 { self.cache.lock().concentration_top1_pct() }

    /// override default：一次 lock + batch 走 5 calculator，避免 5-lock gap micro-race。
    fn snapshot_5_metric(&self) -> RiskEnvelopeSampleSnapshot {
        self.cache.lock().snapshot_5_metric()
    }
}
```

**設計原則**：
- 保留 5 個 individual accessor（backward compat trait API + 既有 unit test 不破壞）
- batch 是 additional method；emitter Wave B 接 main.rs 前**不改 emitter**（per scope 限制：emitter sample_now 端切換 batch path 是 Wave B 工作）
- 既有 `StubSource` / `MockMutexRiskProbe` 等 mock 自動走 default impl 5 個 current_xxx；不需改

LOC：+47 LOC trait (default method + struct + doc) + +25 LOC cache 端 method + +12 LOC RealProbe override = +84 LOC IMPL。

**新 test 3 個**：
- inline `test_cache_snapshot_5_metric_aligns_with_individual_accessors`
- inline `test_real_probe_snapshot_5_metric_aligns_with_5_current_xxx`
- integration `test_real_probe_batch_snapshot_aligns_with_5_current_xxx`
- integration `test_real_probe_batch_snapshot_empty_cache_all_zero`
- integration `test_default_snapshot_5_metric_works_for_non_overriding_impl`（守 backward compat）

## §3. cargo test 結果

| Verify | Command | Result |
|---|---|---|
| **Release build** | `cargo build --release` | **PASS** — 26.89s recompile；3 pre-existing warning 不變；本 round 0 new warning |
| **PA-DRIFT-4 integration** | `cargo test --release --test api_latency_probe_real_impl` | **22 / 22 PASS** — 15 baseline + 2 noop guard + 4 boundary + 1 raw caller |
| **PA-DRIFT-5 integration** | `cargo test --release --test risk_envelope_probe_real_impl` | **14 / 14 PASS** — 11 baseline + 2 batch read + 1 default impl backward compat |
| **bybit_rest_client lib** | `cargo test --release --lib bybit_rest_client` | **29 / 29 PASS** |
| **health lib unit** | `cargo test --release --lib health::` | **107 / 107 PASS**（比 baseline 105 多 2 個本 round 加的 inline test） |
| **lib full** | `cargo test --release --lib` | **3172 / 0 / 1 ignored**（比 baseline 3170 多 2 inline test） |
| Track A regression | `cargo test --release --test sprint2_track_a_engine_runtime` | **9 / 9 PASS** |
| Track B regression | `cargo test --release --test sprint2_track_b_pipeline_throughput` | **5 / 5 PASS** |
| Track C regression | `cargo test --release --test sprint2_track_c_database_pool` | **8 / 8 PASS** |
| Track D regression | `cargo test --release --test sprint2_track_d_api_latency` | **7 / 7 PASS** |
| Track E regression | `cargo test --release --test sprint2_track_e_strategy_quality` | **11 / 11 PASS** |
| Track F regression | `cargo test --release --test sprint2_track_f_risk_envelope` | **8 / 8 PASS** |
| Replay forbidden | `cargo test --release --test m3_emitter_replay_forbidden` | **3 / 3 PASS** |
| Spike feature | `cargo test --release --features spike --test m3_amp_cap_24h_fire` | **3 / 3 PASS** |
| **AC-5 nm scan** | `nm openclaw-engine \| grep -cE "(mock_instant\|tokio::time::pause\|spike)"` | **0** hit ✓ |
| **inject_* symbol leak** | `nm openclaw-engine \| grep -cE "inject_sample_with_timestamp\|inject_4xx\|inject_5xx"` | **0** hit ✓（release build optimizer drop unused pub method） |
| **cargo test 全套** | `cargo test --release` 累計 | **3499 PASS / 0 FAIL / 4 ignored** |

## §4. 修改清單（字面 diff 摘要）

| File | 性質 | 改動 LOC | 摘要 |
|---|---|---|---|
| `rust/openclaw_engine/src/bybit_rest_client.rs` | extend | 1272→1367 (+95) | H-1 noop helper + noop guard / H-2 RestLatencyHistogram + RetCodeCounter 各 inject_*_with_timestamp / H-3 get/post 內部 observer + _checked 簡化 / M-1 注釋修正 |
| `rust/openclaw_engine/src/bybit_private_ws.rs` | extend | 1693→1718 (+25) | H-2 WsRttHistogram + WsDropoutCounter 各 inject_sample_with_timestamp test-only accessor |
| `rust/openclaw_engine/src/health/domains/risk_envelope.rs` | extend | 849→896 (+47) | F-3 trait default `snapshot_5_metric()` method + 新 struct `RiskEnvelopeSampleSnapshot` |
| `rust/openclaw_engine/src/health/domains/risk_envelope_probe_impl.rs` | extend | 698→822 (+124) | F-1 cap comment fix (a 選項) / F-3 PortfolioStateCache::snapshot_5_metric + RealProbe override + 2 inline test |
| `rust/openclaw_engine/tests/api_latency_probe_real_impl.rs` | extend | 350→622 (+272) | 新增 7 test：2 noop guard + 4 boundary + 1 raw caller pattern；改 1 既有 test（110001 → 110003 避 noop） |
| `rust/openclaw_engine/tests/risk_envelope_probe_real_impl.rs` | extend | 408→535 (+127) | 新增 3 integration test：batch aligns / empty all-zero / default impl backward compat |

**不動 file**：
- `health/domains/api_latency.rs` / `api_latency_probe_impl.rs`（不修 trait 簽名 / emitter struct / sample shape）
- `metric_emitter/mod.rs` / `main.rs`（per scope：Wave B 工作）
- 不改 既有 REST get/post / WS reconnect 業務邏輯（只 wrap instrumentation）
- 不引 V### SQL / spike feature / GUI

## §5. 治理對照

| 項目 | 狀態 |
|---|---|
| **§六 Hard Boundaries** | 未碰 `live_execution_allowed` / `execution_authority` / `system_mode` / `max_retries` / production engine / trading_ai DB / V### SQL ✓ |
| **§七 Code And Docs Rules** | 新代碼注釋全中文（per `feedback_chinese_only_comments` 2026-05-05）；觸及既有 bilingual block 不主動清；無 emoji ✓ |
| **§八 Workflow** | E1 IMPL DONE → 等 E2 round 2 review；不自行 commit；不派下游 sub-agent ✓ |
| **§九 Code Structure Guardrails** | bybit_rest_client.rs 1367 LOC > 800 警告但 < 2000 hard cap；bybit_private_ws.rs 1718 LOC 同；risk_envelope.rs 896 LOC 同；risk_envelope_probe_impl.rs 822 LOC 跨 800 警告（本 round +124 主要是 inline test + cap comment 擴；< 2000）；test file 不計 cap |
| **§Data, Migrations, And Validation** | 本 round 不新增 V###；純 Rust IMPL；不觸 PG dry-run（per `feedback_v_migration_pg_dry_run` 適用範圍是 V### migration with PG reflection） ✓ |
| **cross-platform** | 純 Rust 邏輯；不引平台特異 path；Instant::checked_sub Mac+Linux 共通 ✓ |
| **AC-5 production binary 0 mock time 滲透** | nm 0 hit 守住；本 round 0 spike feature gate；`inject_*` pub + `#[doc(hidden)]` 但 release build optimizer 自動 drop（nm 0 hit `inject_*` 實證） ✓ |
| **`feedback_impl_done_adversarial_review`** | 本 round 改動 = 4 extend file（+291 LOC）+ 2 test file extend（+399 LOC）；屬「IPC 邊界擴大 + 共用 helper」邊緣場景（新 1 pub struct `RiskEnvelopeSampleSnapshot` + 1 trait default method + 5 test-only pub accessor）；E2 round 2 review 應確認 |
| **反模式對齊（per packet §5.5）** | (a) 不修 既有 REST/WS 業務邏輯 ✓ / (b) 不修 reconnect 邏輯 ✓ / (c) emitter trait extension 不破壞既有 source probe impl backward compat ✓ / (d) ret_code 用 HTTP 標準語意 (4xx/5xx) + noop guard ✓ / (e) 不引 V### / spike / IPC ✓ |

## §6. 不確定 / Carry-over

1. **risk_envelope_probe_impl.rs 822 LOC > 800 警告**：本 round +124 LOC 主要是新 inline test（2 個 ~60 LOC）+ F-1 cap comment 擴 + F-3 cache method + RealProbe override + doc 注釋；< 2000 hard cap。是否需 split：建議**不切**（既有 unit test 區段約 350 LOC 屬 file 內部 cohesion；split test 反破壞 inline test colocation）；E2 round 2 應確認。

2. **`inject_*` pub + `#[doc(hidden)]` vs `#[cfg(test)]` 取捨**：選擇前者因 integration test crate visibility 需要 + AC-5 nm 不撞守則 + release build optimizer 自動 drop（nm 0 hit 實證）。E2 round 2 應確認此設計是否需在 `#[doc(hidden)]` 旁加 `#[deprecated(note = "test-only; production callers prohibited")]` 或類似 lint guard 增強 production caller 檢測。

3. **既有 test `test_ret_code_counter_4xx_5xx_classify` 改動**：H-1 fix 後 110001 OrderNotFound 屬 noop 不計 5xx；既有 test 用 110001/110007/110049 → 改為 110003/110007/110049（後者全非 noop）。屬於語意正確的 test update（test 反映新 invariant），非破壞性改動；E2 round 2 應確認此 test update 對齊 noop 集合定義。

4. **emitter sample_now 端 Wave B 切換 batch path**：F-3 trait extension 完成；emitter Wave B 接 main.rs 前可走 `source.snapshot_5_metric()` 替代 5 個 current_xxx。本 round per scope **不改 emitter**（emitter sample 端切換是 Wave B 工作）。E2 round 2 應確認此 scope split 合理。

5. **H-3 `_checked` 端不再 record，是否影響既有 caller**：grep 確認 `_checked` caller（platform_client.rs 等）流程不變 — `into_result()` 仍把 retCode != 0 轉 Business error；只是不再雙重 record。原 IMPL 端 `_checked` record 是雙重計（`get`/`post` 也 record + `_checked` 再 record）— 雙重計反讓 `_checked` 比 raw caller 數值高 2 倍（原 bug）；本 fix 修正此偏差。

6. **`#[doc(hidden)]` pub method symbol 在 cargo doc**：rustdoc 不呈現 (`#[doc(hidden)]` 守則)；但 IDE auto-complete / `cargo doc --document-private-items` 仍可能呈現。E2 round 2 應確認此屬可接受 trade-off vs 引入新 feature flag 的維護成本。

## §7. round 2 verdict + E2 round 2 readiness

### 7.1 closure verdict

**PA-DRIFT-4 round 2 IMPL DONE — 4/4 finding fixed**：

| Finding | Status | 證明 |
|---|---|---|
| H-1 BLOCKER noop retCode 誤計 5xx | ✅ FIXED | `record_for_error` + noop guard + `is_noop_retcode` helper + 2 integration test (`skips_noop_retcodes` + `noop_does_not_affect_real_venue_fault`) |
| H-2 60s expire boundary 0 test | ✅ FIXED | 4 instrumentation 各加 `inject_sample_with_timestamp` + 4 boundary test (rest_latency / ws_rtt / ret_code_4xx_5xx 雙桶 / ws_dropout) |
| H-3 retCode counter 觀測覆蓋率 < 50% | ✅ FIXED | 觀測下沉 `get`/`post` 內部 + `_checked` 簡化 + integration test (`raw_caller_pattern_records_via_internal_observer`) |
| M-1 checked_sub fallback 注釋誤導 | ✅ FIXED | 補 boot < 60s edge case 行為說明（11 LOC 注釋） |

**PA-DRIFT-5 round 2 IMPL DONE — 2/2 finding fixed**：

| Finding | Status | 證明 |
|---|---|---|
| F-1 cap=100k comment 失誤 | ✅ FIXED | 改注釋為「24h × push rate 隱式上限；無顯式 cap」（選項 a） |
| F-3 batch read helper for race window | ✅ FIXED | trait default + `RiskEnvelopeSampleSnapshot` struct + `PortfolioStateCache::snapshot_5_metric` + `RealRiskEnvelopeSourceProbe::snapshot_5_metric` override + 5 test（2 inline + 3 integration） |

### 7.2 E2 round 2 readiness

**E2 round 2 focus on**：
- H-1 noop guard 對映 `BybitRetCode::is_noop()` SSOT 是否完整覆蓋所有應 skip retCode（per Bybit API ref line 1273-1287 noop column）
- H-2 boundary test cover 度（59s 內 / 61s 外）是否充分守 60s rolling window semantics；`inject_*` pub + `#[doc(hidden)]` 設計是否可接受
- H-3 `_checked` 簡化後既有 caller 流程不變的 grep 驗證（不雙重計）
- M-1 注釋修正是否完整對齊新 boot < 60s edge case 行為
- F-1 comment fix (選項 a) 是否符合 PA 設計意圖；burst push 防禦邊界是否清晰
- F-3 trait extension default method 設計：backward compat（既有 mock 走 default）+ override 路徑（RealProbe 走 batch）是否符合「最小破壞 + 提供 race window 修復」目標
- risk_envelope_probe_impl.rs 822 LOC > 800 警告是否需 split
- 反模式 (a)-(e) 5 條對齊是否完整

**A3 review 路徑**：本 round 不動 GUI / IPC / 寫操作 trading hot path（只擴 observer / batch helper）；不主動派 A3。若 E2 round 2 認定 trait extension 屬「IPC 邊界擴大」（per `feedback_impl_done_adversarial_review`），可派 A3 對抗性核驗。

### 7.3 Wave B unblock 進度

`MetricEmitterScheduler::run` 接 main.rs 前置：
1. ✅ PA-DRIFT-4 round 1 IMPL（Wave A 4-6 hr 已 closed）
2. ✅ **PA-DRIFT-4 round 2 fix — 本 round closed**
3. ✅ PA-DRIFT-5 round 1 IMPL（Wave A 已 closed）
4. ✅ **PA-DRIFT-5 round 2 fix — 本 round closed**
5. ⏳ E2 round 2 review APPROVE
6. ⏳ Wave B main.rs 接 scheduler dispatch（PA 後續派）
7. ⏳ Linux runtime `--rebuild` + ≥ 30 min 樣本累積（Phase 3c QA AC-1b 前置）

**AC-1b unblock 進度**：Wave A 完整 closed（PA-DRIFT-4 + PA-DRIFT-5 兩條 round 2 fix all done），剩 main.rs Wave B + Linux deploy + 30min wait + Phase 3c QA。

## §8. Operator 下一步

1. **PM 派 E2 round 2 review**：focus §7.2 list。
2. **PM 收口 commit chain**：待 E2 round 2 PASS + E4 regression PASS 後 PM 統一 commit + push（強制鏈 E1→E2→E4→QA→PM）。
3. **A3 review 路徑（per `feedback_impl_done_adversarial_review` 2026-05-09）**：本 round trait extension + observer 下沉屬 IPC 邊界擴大 + 共用 helper 邊緣；若 E2 round 2 認定需 A3 並行核驗，可派；E1 不主動派下游。
4. **PA Sprint 2 acceptance §AC-1b unblock 更新**：建議 PM 在 acceptance report 標註 Wave A 兩條 round 2 all done（PA-DRIFT-4 4/4 + PA-DRIFT-5 2/2），下一步等 E2 round 2 + Wave B dispatch。

---

**E1 IMPLEMENTATION DONE: 待 E2 round 2 review（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint_4_wave_a_round2_combined_fix.md`）**
