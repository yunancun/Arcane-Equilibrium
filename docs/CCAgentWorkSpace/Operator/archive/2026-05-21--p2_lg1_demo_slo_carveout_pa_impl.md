# P2-LG1-DEMO-SLO-CARVEOUT — PA spec + Rust skeleton + Grafana JSON

**Date**: 2026-05-21
**Author**: PA
**Trigger**: E5 F1 audit verdict 2026-05-21 推薦選項 B（accept variance + SLO carve-out）
**Source**: `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-21--p1_lg1_demo_sla_violation_hotpath_audit.md`
**Status**: SPEC + Rust skeleton + Grafana JSON 全 land；待 E1 hot path 接線

---

## 1. 交付清單

| # | 路徑 | 行數 | Status |
|---|---|---|---|
| 1 | `docs/execution_plan/2026-05-21--p2_lg1_demo_slo_carveout_spec.md` | 429 | SPEC READY |
| 2 | `rust/openclaw_core/src/hot_path_metrics/mod.rs` | 23 | LAND |
| 3 | `rust/openclaw_core/src/hot_path_metrics/h0_latency.rs` | 380 | LAND |
| 4 | `rust/openclaw_core/src/lib.rs` `pub mod hot_path_metrics` | +6 | LAND |
| 5 | `rust/Cargo.toml` workspace `hdrhistogram = "7"` | +4 | LAND |
| 6 | `rust/openclaw_core/Cargo.toml` `hdrhistogram = { workspace = true }` | +3 | LAND |
| 7 | `docs/grafana/dashboards/h0_latency_distribution.json` | 182 | LAND |

**驗證**：
- `cargo check -p openclaw_core` PASS（8.66s; hdrhistogram 7.5.4 download + compile clean）
- `cargo check --target aarch64-apple-darwin -p openclaw_core` PASS（5.89s）
- `cargo check -p openclaw_engine` PASS（16.27s；core 改動不破 engine dep）
- `cargo test --release -p openclaw_core hot_path_metrics::h0_latency` → **8 PASS / 0 fail / 0.02s**
- Grafana JSON parse PASS（panels=5, templating_vars=1）

---

## 2. 設計選擇

### 2.1 派工 prompt 三處 PA 更正

| # | Prompt 原文 | 問題 | PA 拍板 |
|---|---|---|---|
| 1 | module path `rust/openclaw_engine/src/hot_path_metrics/` | `h0_gate.rs` 住 `openclaw_core` crate 不在 `openclaw_engine`；engine 無法被 core 看到（workspace dep 單向 core → engine） | 改 `rust/openclaw_core/src/hot_path_metrics/` |
| 2 | `Cargo.toml 加 hdrhistogram = "7"` 未指定 crate | 加 workspace + openclaw_core/Cargo.toml | LAND（spec §3.2） |
| 3 | §4 用 `EngineMode` enum | 既有 `effective_engine_mode` 回 `&'static str` 5 種；新引 enum 雙頭 source-of-truth | API 收 `&'static str`，不引 enum（spec §3.6） |

### 2.2 核心 API（spec §3.3）

```rust
pub struct H0LatencyRecorder { /* parking_lot::Mutex<inner> */ }

impl H0LatencyRecorder {
    pub fn new() -> Self;
    pub fn record(&self, latency_us: u64, engine_mode: &'static str);
    pub fn summary(&self, engine_mode: &'static str, recorded_at_ms: u64) -> Option<H0LatencySummary>;
    pub fn all_summaries(&self, recorded_at_ms: u64) -> Vec<H0LatencySummary>;
    pub fn reset(&self, engine_mode: &'static str);
    pub fn reset_all(&self, now_ms: u64);
    pub fn last_reset_ms(&self) -> u64;
}

pub struct H0LatencySummary {
    pub engine_mode: &'static str,
    pub count: u64,
    pub p50_us: u64,
    pub p99_us: u64,
    pub p999_us: u64,
    pub max_us: u64,
    pub recorded_at_ms: u64,
}
```

**設計決策**：
- `recorded_at_ms` 由 caller 傳入而不在 recorder 內取 `now_ms()` — 避免 inner 模組引 chrono dep，且 caller（status_report）已有 now_ms helper
- summary read 也走 Mutex（不用 RwLock）— HdrHistogram value_at_quantile 需短暫鎖；E5 baseline H0 hot path 4.86ns + 預估 Mutex unconstested 30-40ns 合計 < 50ns AC-3 邊界
- 未知 engine_mode silently skip — 防 caller 拼錯字串導致 hot path panic（spec §3 防禦）
- 5 mode histogram 預先建構 — 不 lazy（避免 record 路徑首次 lock contention）

### 2.3 HdrHistogram 參數

`Histogram::<u64>::new_with_bounds(1, 10_000_000, 3)`:
- low=1us：最小有意義 latency 邊界
- high=10s：遠超 E5 觀察 max 5ms（spec §3.4）
- sig_figs=3：1‰ 解析度；spec AC-2 ±1% 容差有 10× headroom
- 預估 footprint：~256KB/instance × 5 mode ≈ 1.3MB（vs engine RSS 148MB 0.9%）

### 2.4 Reset cadence（spec §3.5）

- 1h reset：對齊 EdgeEstimatorScheduler；reset 操作 ~10us，由 status_report cadence 觸發
- 不在 hot path（status_report 為 control plane）
- `last_reset_ms` field 在 inner 持有；status_report 比較 `now_ms() - last_reset_ms > 3600_000` 觸發 `reset_all(now_ms)`

---

## 3. Grafana panel 描述

5 panel 結構（spec §5.3）：

| ID | Type | Field | Width / Position |
|---|---|---|---|
| 1 | gauge | p50_us | 6 cols, top row |
| 2 | gauge | p99_us | 6 cols, top row |
| 3 | gauge | p999_us | 6 cols, top row |
| 4 | gauge | max_us | 6 cols, top row |
| 5 | heatmap | p50/p99/p999/max time-series 30d (log-scale Y) | 24 cols, second row |

Threshold 配色：
- p50：green / yellow 100μs / red 1000μs
- p99：green / yellow 1000μs / red 2000μs（spec §6 H0_P99_WARN 1000）
- p999：green / yellow 2000μs / red 5000μs（spec §2.2 design budget ≤ 2000）
- max：green / yellow 5000μs / red 10000μs（spec §6 H0_MAX_WARN 5000 / H0_MAX_FAIL 10000）

Templating var `$engine_mode` 5 值 picker（paper/demo/live/live_demo/live_testnet），預設 demo。

Datasource UID `${DS_PG}` placeholder — runtime deploy 時 operator / E3 binding；spec §11.2 OQ-2。

Alert rules 不嵌 panel JSON — Grafana alert rules API or `helper_scripts/db/audit/h0_latency_alert_eval.py`（spec §6.3）管理。

---

## 4. Test 結果（spec §8 AC-1..AC-5 + 3 補強）

```
test hot_path_metrics::h0_latency::tests::test_all_summaries_5_modes ... ok
test hot_path_metrics::h0_latency::tests::test_alert_threshold_boundaries ... ok
test hot_path_metrics::h0_latency::tests::test_percentile_accuracy ... ok
test hot_path_metrics::h0_latency::tests::test_reset_all_updates_timestamp ... ok
test hot_path_metrics::h0_latency::tests::test_unknown_mode_no_panic ... ok
test hot_path_metrics::h0_latency::tests::test_record_overhead_ns ... ok
test hot_path_metrics::h0_latency::tests::test_record_1m_no_panic ... ok
test hot_path_metrics::h0_latency::tests::test_reset_clears_count_keeps_buckets ... ok

test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 357 filtered out; finished in 0.02s
```

| Test | 對應 AC | 通過 |
|---|---|---|
| `test_record_1m_no_panic` | AC-1（1M tick 不 panic / 不 OOM）| ✅ |
| `test_percentile_accuracy` | AC-2（p50/p99/p999 ±1% 容差）| ✅ |
| `test_record_overhead_ns` | AC-3（≤ 50ns release / ≤ 1000ns debug）| ✅ |
| `test_all_summaries_5_modes` | AC-4 補強（5 mode 結構正確）| ✅ |
| `test_alert_threshold_boundaries` | AC-5（7 邊界值 max_us 精準反射）| ✅ |
| `test_reset_clears_count_keeps_buckets` | 補強 1（reset 路徑單 mode）| ✅ |
| `test_reset_all_updates_timestamp` | 補強 2（reset_all + last_reset_ms）| ✅ |
| `test_unknown_mode_no_panic` | 補強 3（防禦未知 mode）| ✅ |

**spec 要求 5 test，PA 寫 8 — 3 個補強對 reset 路徑 + 未知 mode 防禦的完整覆蓋**。

---

## 5. E1 hot path 接線 prompt brief（給 PM 派下個 sub-agent）

完整 prompt 已寫在 spec §10。摘要如下：

**Scope**：5 件事（spec §9 PA 留範圍）
1. `H0Gate` struct 加 `metrics_recorder: Option<Arc<H0LatencyRecorder>>` + `engine_mode: &'static str` 兩 field
2. 新增 `H0Gate::with_metrics(config, recorder, engine_mode)` constructor（保留 `H0Gate::new` backward compat）
3. `finalize_blocked` (line 504) + `finalize_allowed` (line 527) 各加 1 行 `record` 呼叫（spec §4.1）
4. `pipeline_ctor.rs:94` `H0Gate::new(...)` 改 `H0Gate::with_metrics(...)`（傳 shared Arc + effective_engine_mode）
5. `status_report.rs:89` 加 5 H0LatencySummary export 進 status JSON + 1h reset 邏輯

**禁區**：
- 不改 `H0LatencyRecorder` API（PA 已 land）
- 不改 SLA 文檔（留下個 doc-update wave）
- 不改 TODO.md（同上）

**驗證**：
- `cargo check --target aarch64-apple-darwin -p {core,engine}` PASS
- `cargo test --release -p openclaw_core hot_path_metrics` PASS（8 test 不破）
- `cargo test --release -p openclaw_engine tick_pipeline` PASS（regression）
- 不在 hot path 引新 alloc 或 lock contention（PR review checklist）

**估算工時**：3-5 小時（pure plumbing；無新算法；E1 熟手 4hr）

---

## 6. Push back / OQ

### 6.1 派工 prompt 三處更正（已寫 spec §11.1）

最大教訓：派工 prompt **module path 寫錯 crate**。`h0_gate.rs` 在 `openclaw_core` 不在 `openclaw_engine`；workspace dep 是 single-direction（engine 看 core，core 看不到 engine）。若 PA 盲信 prompt 在 engine 寫 module，會出現以下兩種 broken pattern：
- pattern A：`finalize_blocked` 直接呼 `engine::hot_path_metrics::record(...)` — cross-crate 反向 dep，workspace 直接拒絕編譯
- pattern B：用 trait callback 從 engine 注入到 core — 過度抽象 + hot path 增加 vtable dispatch 開銷 > 50ns AC-3 邊界
- pattern C：在 engine 維護 standalone metric module 但靠 status_report 額外掃 fillter（不 in-line 接 H0Gate.check）— 失去 sub-tick latency 觀測 granularity，與 spec §3 設計矛盾

**正解**：metric module 必須住 H0Gate 同 crate（openclaw_core）。

### 6.2 OQ for PM（spec §11.2 完整 5 條）

| # | OQ | PA 推薦 |
|---|---|---|
| OQ-1 | status_report H0LatencySummary 寫 `learning.healthcheck_run` 還是新 table？ | **healthcheck_run**（避免 V### migration） |
| OQ-2 | Grafana datasource UID 由誰 binding？ | E1 接線 sub-agent 或 deploy E3 phase |
| OQ-3 | 1h reset 觸發放 status_report 還是獨立 scheduler？ | **status_report**（避免新 scheduler） |
| OQ-4 | live 與 live_demo 二 mode 同 histogram 還是分開？ | **分開**（per 5-string 系統一致） |
| OQ-5 | record overhead 上限 50ns 是否太鬆？ | 50ns = E5 baseline 10× headroom，足夠 |

### 6.3 跨平台 Apple Silicon CI（已驗）

- `cargo check --target aarch64-apple-darwin -p openclaw_core` PASS（5.89s）
- HdrHistogram 7.5.4 pure Rust 無 sys dep（spec §11.3 已 verify）
- E1 接線後 engine target check 也應 PASS（PA 已 verify engine 不被 core 改動 break）

### 6.4 不變式 / 反模式（spec §11.4 摘要）

| 規則 | 違反後果 |
|---|---|
| HdrHistogram 不可在 hot path reset | per-tick reset → mem 爆 |
| Mutex hold 時間 ≤ 50ns（record 路徑） | summary read ≤ 10us 可容忍（status_report 非 tick） |
| engine_mode `&'static str` 不可改 `String` | 每 record alloc → ROI 完全反向 |
| H0Gate::new 不可破 backward compat | 其他 caller / test 預期 None recorder fallback |

---

## 7. Confidence & Risk

**Confidence**：
- HIGH for spec §1-§9 + module 結構 + API + Cargo dep
- HIGH for 8 unit test（全 PASS + 補強）
- HIGH for Apple Silicon cross-platform（驗證通過）
- MEDIUM-HIGH for Grafana JSON（panel 結構 OK；datasource UID placeholder 留 OQ-2 給 deploy phase）
- MEDIUM for §6 alert threshold 邊界數字（5000μs / 10000μs 是 spec §2.2 carve-out 安全 headroom；calibrate 後 future spec amendment 可調）

**Risk grade**：低
- Standalone module，不動 H0Gate 邏輯
- 派 E1 接線時最大風險 = 1 行 `record` 呼叫位置錯（spec §4.1 已寫明 finalize_blocked + finalize_allowed 兩處）
- E2 review checkpoint：record 不在 hot path 新增 alloc / lock contention；H0Gate::new backward compat 不破

**Apple Silicon CI tuple 影響**：0（HdrHistogram pure Rust 已驗）

**硬邊界檢查**：未觸碰 5 hard boundary（live_reserved / Operator auth / OPENCLAW_ALLOW_MAINNET / secret slot / authorization.json）。本 PR 純 observability。

---

## 8. References

- E5 F1 audit: `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-21--p1_lg1_demo_sla_violation_hotpath_audit.md`
- 本 PA spec: `docs/execution_plan/2026-05-21--p2_lg1_demo_slo_carveout_spec.md`
- H0Gate source: `rust/openclaw_core/src/h0_gate.rs:269` (check), :504 (finalize_blocked), :527 (finalize_allowed)
- engine_mode mapping: `rust/openclaw_engine/src/mode_state.rs:38` `effective_engine_mode`
- Grafana panel: `docs/grafana/dashboards/h0_latency_distribution.json`
- Memory cross-ref: `project_mac_deployment_target`（Apple Silicon CI tuple 必含）
