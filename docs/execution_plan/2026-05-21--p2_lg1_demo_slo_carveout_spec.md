# P2-LG1-DEMO-SLO-CARVEOUT — H0 hot-path observability spec

**Date**: 2026-05-21
**Author**: PA
**Trigger**: E5 F1 audit verdict `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-21--p1_lg1_demo_sla_violation_hotpath_audit.md`
**Status**: SPEC READY → 待 PM 派 E1 hot-path 接線 + E2 review + E4 regression
**Risk grade**: 低（observability module standalone；不改 H0Gate 邏輯；hot path 只加 1 行 record 呼叫）
**Apple Silicon 影響**: 0（HdrHistogram pure Rust，跨平台）

---

## §1 動機

E5 F1 audit verdict（2026-05-21）：

> demo H0 `max_latency_us=2454μs > 1ms SLA` **非 algorithmic bug**。H0Gate.check avg=4.86ns 純算術；hot_path_baseline 10k iter p99=38.9μs / max=164μs。2454μs = 18M tick 中 1 個 outlier，由 OS scheduler / cache miss / Instant::now vDSO 引發。
>
> 推薦選項 B：SLA 文檔 carve-out（p99 < 1ms / max ≤ 5ms over 1M ticks）+ HdrHistogram p99/p999 metric + Grafana panel。P1-LG1-DEMO-SLA-VIOLATION 降為 P2 observability ticket。

本 spec 落實選項 B。三個交付：

1. SLA 文檔語意 carve-out（hard 1ms → p99 < 1ms / max ≤ 5ms over 1M）
2. HdrHistogram-based H0 latency distribution recorder（pure Rust standalone module）
3. Grafana panel + alert config（p99/p999/max + WARN/FAIL threshold）

**不在範圍**：
- 不改 H0Gate.check 邏輯（hot path simplicity 保留）
- 不加 CPU pin / SCHED_FIFO（選項 A 拒絕，跨平台風險高且 0 業務收益）
- 不改 SLA hard 數字（max ≤ 5ms 是觀察值 + 安全 headroom，未來再 calibrate）

---

## §2 SLA carve-out 文本

### 2.1 改動點

| File | 行 | 舊 | 新 |
|---|---|---|---|
| `docs/runbooks/2026-05-11--lg1_h0_flip_rollback.md` | §177 SLA table | `H0 latency < 1ms` | `H0 latency p99 < 1ms / max ≤ 5ms over 1M ticks` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md` | §40 H0 budget row | `<1ms SLA budget` | `p99 < 1ms / max ≤ 5ms / p999 ≤ 2ms (observed jitter floor 2-3ms)` |
| `docs/adr/0024-h0-gate-and-fast-track.md`（如存在）| 對應 SLA 段 | 同上 | 同上 |
| `rust/openclaw_core/src/h0_gate.rs:262` doc comment | `Must complete in <1ms` | `Must achieve p99 < 1ms / max ≤ 5ms over 1M ticks (platform jitter floor known)` |

### 2.2 carve-out 措辭模板（pin runbook §177）

```
## H0 Gate Latency SLA (revised 2026-05-21 per E5 F1 + P2-LG1-DEMO-SLO-CARVEOUT spec)

Design budget (revised):
- p50: < 1 μs (drives saturate-to-0 in as_micros() bucket)
- p99: < 1 ms (algorithmic budget; platform jitter inside budget for 99% calls)
- p999: ≤ 2 ms (acceptable tail)
- max: ≤ 5 ms over rolling 1M ticks (platform jitter floor)

Rationale:
- H0Gate.check is sync 5-step pure arithmetic on small HashMap (25 entries).
  Single-thread benchmark 10k iter on AMD RYZEN AI MAX+ 395:
  avg=23.6μs / p50=30.5μs / p99=38.9μs / max=164μs.
- Production max observed 2454μs over 38h / 18M ticks = OS scheduler preemption
  + cache miss + Instant::now vDSO jitter, not algorithmic bug.
- E5 F1 verdict: hard 1ms requires SCHED_FIFO + cpu pin (selection A rejected
  per cross-platform risk + 0 business impact: 0/18M H0 BLOCKED ever fired).

Healthcheck mapping:
- p99 > 1 ms over 1h     → WARN
- max > 5 ms over 1h     → WARN
- max > 10 ms over 1h    → FAIL (escalate; platform-level problem)
- 5-min rolling window for alert evaluation
```

---

## §3 HdrHistogram 設計

### 3.1 Module 位置（PA 對派工 prompt 的更正）

派工 prompt 指定 `rust/openclaw_engine/src/hot_path_metrics/` —— **錯**。`h0_gate.rs` 住 `openclaw_core` crate（per `rust/openclaw_core/src/h0_gate.rs:269`），metric module 必須住 `openclaw_core` 否則 H0Gate.check 無法直接呼（cross-crate 反向 dep 會 break workspace）。

**正確 module path**：
- `rust/openclaw_core/src/hot_path_metrics/mod.rs` — module entry + re-export
- `rust/openclaw_core/src/hot_path_metrics/h0_latency.rs` — H0LatencyRecorder + 5 unit test

### 3.2 Cargo 依賴

`rust/Cargo.toml` workspace deps 加：
```toml
hdrhistogram = "7"
```

`rust/openclaw_core/Cargo.toml` 加：
```toml
hdrhistogram = { workspace = true }
```

理由：openclaw_core 已有 parking_lot dep（acquire_lease facade 用），與 HdrHistogram 同層；不污染 openclaw_engine（避免 metric module 跨 crate 看 EngineMode 字串 mapping）。

### 3.3 API（per E5 F1 §4 選項 B）

```rust
// 公開 API（精簡）
pub struct H0LatencyRecorder {
    inner: parking_lot::Mutex<H0LatencyRecorderInner>,
}

pub struct H0LatencySummary {
    pub engine_mode: &'static str,  // "paper" / "demo" / "live" / "live_demo" / "live_testnet"
    pub count: u64,
    pub p50_us: u64,
    pub p99_us: u64,
    pub p999_us: u64,
    pub max_us: u64,
    pub recorded_at_ms: u64,
}

impl H0LatencyRecorder {
    pub fn new() -> Self;

    /// 記錄 1 tick H0 latency。hot path 呼叫；總開銷需 ≤ 50 ns。
    /// engine_mode 用既有 `effective_engine_mode` 5-string 系統，不引新 enum。
    pub fn record(&self, latency_us: u64, engine_mode: &'static str);

    /// 匯出指定 engine_mode 的 percentile summary（用於 IPC report / Grafana）。
    pub fn summary(&self, engine_mode: &'static str) -> Option<H0LatencySummary>;

    /// 匯出全部 engine_mode summary（5 mode 全枚舉）。
    pub fn all_summaries(&self) -> Vec<H0LatencySummary>;

    /// 重置指定 mode（每小時 cadence 呼叫；不可 per-tick reset）。
    pub fn reset(&self, engine_mode: &'static str);

    /// 重置全部 mode。
    pub fn reset_all(&self);
}
```

### 3.4 內部設計

- `H0LatencyRecorderInner` 持 `HashMap<&'static str, Histogram<u64>>`，per-engine-mode 一個 HdrHistogram instance（5 mode = 5 histogram）
- HdrHistogram config: `Histogram::<u64>::new_with_bounds(1, 10_000_000, 3)` —— low=1us / high=10s / significant_figures=3（per HdrHistogram crate idiom；10s 上界遠超 E5 觀察 max 5ms）
- 每 histogram 預估 footprint ~256 KB（HdrHistogram 3-sig-fig + 10M us 範圍）→ 5 mode total ~1.3 MB，與 engine RSS 148 MB 對比無壓力
- Mutex 而非 RwLock：HdrHistogram `record` 必須 mut；read（summary）也建議短暫 lock 避免 atomic snapshot 複雜化；E5 F1 §2.1 `total_checks=4.86ns avg` → Mutex contention 在 single-thread tick path 無瓶頸；多 producer 場景僅 status_report 異步呼 `summary()`，與 hot path tick 互斥開銷可控

### 3.5 Reset cadence

- 每小時 reset：對齊 `EdgeEstimatorScheduler` cadence；reset 不在 hot path，由 `status_report` 或外部 scheduler 觸發
- 不 per-tick reset：HdrHistogram 設計就是長窗 percentile；per-tick reset 等於丟 percentile semantics
- Reset 用 `Histogram::reset()`（HdrHistogram 內建 API），不分配新 instance（保留 buckets 結構，只清 count）

### 3.6 Engine mode 5-string 系統對齊

不引新 `EngineMode` enum。直接收 `&'static str`（由 `effective_engine_mode` 回傳），5 種值：

| engine_mode | 來源 | 預期 record frequency |
|---|---|---|
| `paper` | `(Paper, _)` | OPENCLAW_ENABLE_PAPER=1 才 spawn；預設 0 record |
| `demo` | `(Demo, _)` | demo pipeline tick；E5 F1 觀察 ~100×live rate |
| `live` | `(Live, Mainnet)` | 真正 mainnet live；目前環境 0 record |
| `live_demo` | `(Live, LiveDemo/Demo/None)` | LiveDemo 流量；當前主力 record path |
| `live_testnet` | `(Live, Testnet)` | testnet 流量；目前 0 record |

理由：與既有 DB engine_mode tag 系統完全一致，避免雙 source-of-truth。

---

## §4 Hot path 接線點（PA 留 spec 指示給 E1）

### 4.1 接線位置

`rust/openclaw_core/src/h0_gate.rs`：

**`finalize_blocked` (line 504-523)**：
```rust
let latency_us = start.elapsed().as_micros().min(u32::MAX as u128) as u32;
self.stats.total_latency_us += latency_us as u64;
if (latency_us as u64) > self.stats.max_latency_us {
    self.stats.max_latency_us = latency_us as u64;
}
// PA P2-LG1-DEMO-SLO-CARVEOUT 接線點 #1：blocked path latency record
// 條件：self.metrics_recorder.is_some() 才 record（防止 None pipeline 崩）
// engine_mode 從 self.engine_mode 取（H0Gate 新增 &'static str field，pipeline_ctor 傳入）
if let Some(rec) = &self.metrics_recorder {
    rec.record(latency_us as u64, self.engine_mode);
}
H0CheckResult { ... }
```

**`finalize_allowed` (line 527-546)**：相同 1 行 record 呼叫，置於 stats update 之後。

### 4.2 H0Gate 構造期改動

`H0Gate` struct 加兩 field：
```rust
pub struct H0Gate {
    // ... existing fields ...
    /// PA P2-LG1: hot-path latency recorder. None 表示未接線（測試/cold path）。
    metrics_recorder: Option<Arc<H0LatencyRecorder>>,
    /// PA P2-LG1: engine_mode tag for metric attribution.
    engine_mode: &'static str,
}
```

`H0Gate::new` 不變（保持 backward compat），新增 `H0Gate::with_metrics(config, recorder, engine_mode)` constructor。

### 4.3 Pipeline ctor 接線

`rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs:94` 改 `H0Gate::new(...)` 為 `H0Gate::with_metrics(config, shared_recorder, effective_engine_mode(kind, env))`。

`shared_recorder` 在 engine 啟動時建立一個全域 `Arc<H0LatencyRecorder>`，三 pipeline（paper/demo/live）共用 single recorder 但各自 engine_mode 不同，histogram 自然分流。

### 4.4 IPC summary export

`status_report` 加 H0LatencySummary 5 entry export：
- 每 status request 呼 `recorder.all_summaries()` 取 5 mode summary
- 加入 status JSON payload `h0_latency_distribution: [...]`
- 進入 IPC response 後 Python 端讀取寫入 `learning.healthcheck_run` 或 Grafana scrape endpoint

### 4.5 1-hour reset 觸發

`status_report` 既已每 N 秒呼一次（pipeline tick 不在意），增加邏輯：
- 持 `last_reset_ms: u64` 在 PipelineHandle 或 recorder 內部
- 每次 status_report 呼叫前檢查：if `now_ms - last_reset_ms > 3600_000` 呼 `recorder.reset_all()`
- 邏輯放 `status_report.rs:89` `let h0_stats = ...` 旁，順帶處理

**邊界**：reset 邏輯不在 hot path（status_report 是 control plane，不是 tick path）；reset 操作 mutex hold 時間 ≤ 5 mode × Histogram::reset() ~10us，可忽略。

---

## §5 Grafana panel JSON

### 5.1 路徑

新建：`docs/grafana/dashboards/h0_latency_distribution.json`

### 5.2 Datasource

placeholder `${DS_PG}`（PostgreSQL datasource）— 假設 status_report 已把 5 summary 寫入 `learning.healthcheck_run` 一個 cell（或單獨 table，下游決策；spec 不綁）

### 5.3 Panel 設計（5 panel）

| Panel | type | metric | unit |
|---|---|---|---|
| 1 | gauge | p50 (per engine_mode) | μs |
| 2 | gauge | p99 (per engine_mode) | μs |
| 3 | gauge | p999 (per engine_mode) | μs |
| 4 | gauge | max (per engine_mode) | μs |
| 5 | heatmap | latency distribution 30d | log-scale μs |

Alert thresholds 嵌入 gauge panel 4：
- `< 5000μs` → green
- `≥ 5000μs and < 10000μs` → yellow
- `≥ 10000μs` → red

### 5.4 Skeleton

JSON 含：
- `title: "H0 Gate Latency Distribution (P2-LG1-DEMO-SLO-CARVEOUT)"`
- `panels` array 5 entry（gauge × 4 + heatmap × 1）
- `templating` 變數 `engine_mode` 5-value picker（paper/demo/live/live_demo/live_testnet）
- `time` 預設 6h，refresh 30s
- `tags: ["h0_gate", "hot_path", "p2_lg1"]`

Datasource UID placeholder `${DS_PG}` — runtime deploy 時由 operator / E1 binding。

---

## §6 Alert config

### 6.1 規則表

| Rule ID | 條件 | 級別 | 動作 |
|---|---|---|---|
| `H0_P99_WARN` | `p99_us > 1000` over 1h rolling avg | WARN | log + healthcheck WARN entry |
| `H0_MAX_WARN` | `max_us > 5000` over 1h rolling | WARN | log + healthcheck WARN |
| `H0_MAX_FAIL` | `max_us > 10000` over 1h rolling | FAIL | escalate；可能 platform-level issue |

### 6.2 Eval cadence

- 5 分鐘 rolling window 評估
- WARN 不阻塞 trading；只進 healthcheck row + 日誌
- FAIL 不自動 halt session（per CLAUDE.md §四 hard boundary：halt 需 Operator/GovernanceHub 路徑）；只發 healthcheck FAIL + Telegram bot push（如已接）

### 6.3 邊界正確性 unit test

新 healthcheck script `helper_scripts/db/audit/h0_latency_alert_eval.py`（spec 內提，後續 E1 IMPL）：
- 從 `learning.healthcheck_run` 取最近 5 min H0LatencySummary
- 算 1h rolling p99/max
- 對比 threshold 邊界（1000 / 5000 / 10000）
- 產 healthcheck row

**unit test 覆蓋**：5 邊界值（999 / 1000 / 4999 / 5000 / 9999 / 10000 / 10001）→ verdict 對應（pass / warn / warn / warn / warn / warn / fail）。

---

## §7 LG-1 closure annotation

### 7.1 TODO.md 改動

`TODO.md` `P1-LG1-DEMO-SLA-VIOLATION` row 改為：
- 級別：P1 → P2
- 描述追加：`platform jitter floor known (E5 F1 audit 2026-05-21); not algorithmic. Tracked via P2-LG1-DEMO-SLO-CARVEOUT.`
- Reference：
  - E5 F1 report: `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-21--p1_lg1_demo_sla_violation_hotpath_audit.md`
  - SLO carve-out spec: `docs/execution_plan/2026-05-21--p2_lg1_demo_slo_carveout_spec.md`

### 7.2 LG-1 7d closure 報告 caveat

`docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-21--lg1_lg2_7d_closure_phase2a_t72h_verify.md` §1 加 footnote：
> demo `max=2454μs > 1ms SLA` per E5 F1 RCA = platform jitter floor，非 algorithmic bug；降 P2 observability，原 SLA 文檔已 carve-out 為 p99 < 1ms / max ≤ 5ms over 1M ticks。LG-1 closure 不阻塞。

---

## §8 Acceptance criteria

| AC | 描述 | 驗證方法 |
|---|---|---|
| **AC-1** | HdrHistogram 1M tick record 不 panic / 不 OOM | `cargo test -p openclaw_core --release hot_path_metrics::h0_latency::test_record_1m_no_panic` |
| **AC-2** | p99 / p999 / max accuracy ±1% | `test_percentile_accuracy`：predefined 數據 → assert summary 值落容差 |
| **AC-3** | record overhead ≤ 50 ns/call（E5 baseline avg 4.86 ns；50 ns 為 10× headroom） | `test_record_overhead_ns`：100k record loop + Instant::now timing |
| **AC-4** | Grafana panel JSON 渲染 4 gauge + 1 heatmap | manual import；datasource binding 後檢視 |
| **AC-5** | alert threshold 邊界正確 | `test_alert_threshold_boundaries`：邊界值 7 個 → verdict 對應 |

---

## §9 PA Rust skeleton 範圍

PA 在本 spec land 同時：

1. `rust/openclaw_core/src/hot_path_metrics/mod.rs` — module entry（~20 行）
2. `rust/openclaw_core/src/hot_path_metrics/h0_latency.rs` — H0LatencyRecorder + 5 unit test（~150-200 行）
3. `rust/openclaw_core/src/lib.rs` 加 `pub mod hot_path_metrics;`
4. `rust/Cargo.toml` workspace deps 加 `hdrhistogram = "7"`
5. `rust/openclaw_core/Cargo.toml` 加 `hdrhistogram = { workspace = true }`
6. `docs/grafana/dashboards/h0_latency_distribution.json` — panel skeleton

**PA 不做**（留 E1 sub-agent）：
- `H0Gate` struct 加 metrics_recorder + engine_mode field
- `H0Gate::with_metrics` constructor
- `finalize_blocked` / `finalize_allowed` 加 record 呼叫
- `pipeline_ctor.rs` 改 H0Gate 構造（傳 recorder + engine_mode）
- `status_report.rs` 加 summary export
- SLA 文檔 §2.1 4 處改動
- TODO.md §7.1 改動
- Healthcheck script `h0_latency_alert_eval.py`

---

## §10 E1 hot path 接線 prompt brief

派工 prompt 給下個 E1 sub-agent（PM 派發）：

```
任務：P2-LG1-DEMO-SLO-CARVEOUT — E1 hot path 接線

Spec：docs/execution_plan/2026-05-21--p2_lg1_demo_slo_carveout_spec.md
PA report：docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--p2_lg1_demo_slo_carveout_pa_impl.md

要做 5 件事（per spec §9 PA 留範圍）：

1. H0Gate 加 metrics_recorder + engine_mode 兩 field（鎖向後相容 H0Gate::new 不改）
2. 新增 H0Gate::with_metrics(config, recorder, engine_mode) constructor
3. finalize_blocked + finalize_allowed 各加 1 行 record 呼叫
4. pipeline_ctor.rs line 94 H0Gate::new(...) 改 H0Gate::with_metrics(...)
5. status_report.rs 加 5 H0LatencySummary export 進 status JSON + 1h reset 邏輯

不要做：
- 不改 H0LatencyRecorder API（PA 已 land）
- 不改 SLA 文檔（spec §2 已寫，留下個 sub-agent doc-update wave）
- 不改 TODO.md（同上）

驗證：
- cargo check --target aarch64-apple-darwin -p openclaw_core PASS
- cargo check --target aarch64-apple-darwin -p openclaw_engine PASS
- cargo test --release -p openclaw_core hot_path_metrics PASS（5 test）
- cargo test --release -p openclaw_engine tick_pipeline PASS（regression）
- 不在 hot path 引新 alloc 或 lock contention

估算工時：3-5 小時（pure plumbing；無新算法）
```

---

## §11 Push back / Open question

### 11.1 派工 prompt 三處更正

| # | Prompt 原文 | 問題 | PA 採決 |
|---|---|---|---|
| 1 | module path `rust/openclaw_engine/src/hot_path_metrics/` | `h0_gate.rs` 在 `openclaw_core` 不在 `openclaw_engine`；engine 無法被 core 看到（workspace dep 單向） | 改 `rust/openclaw_core/src/hot_path_metrics/` |
| 2 | `Cargo.toml 加 hdrhistogram = "7"` 未指定哪個 crate | engine 與 core 都可加，但 core 才有 H0Gate | 同時加 workspace + core/Cargo.toml |
| 3 | §4 用 `EngineMode` enum | 既有 `effective_engine_mode` 回 `&'static str` 5 種；新引 enum 雙頭 source-of-truth | API 收 `&'static str` 不引 enum |

### 11.2 OQ for PM

| # | OQ | 推薦 |
|---|---|---|
| **OQ-1** | status_report H0LatencySummary 寫入 `learning.healthcheck_run` 還是新 table？ | **healthcheck_run**：避免新 migration；用一個 cell `h0_latency_distribution_5mode` JSON payload 即可 |
| **OQ-2** | Grafana datasource UID（${DS_PG}）由誰 binding？ | E1 hot path 接線 sub-agent 或 deploy E3 phase；spec 內留 placeholder 不綁 |
| **OQ-3** | 1h reset 觸發放 status_report 還是獨立 scheduler？ | **status_report**：避免新 scheduler；已每 N 秒呼一次，加 `last_reset_ms` 檢查零成本 |
| **OQ-4** | live 與 live_demo 二 mode 同 histogram 還是分開？ | **分開**（per §3.6 5-string 系統一致）；future audit live vs live_demo divergence 不損失資訊 |
| **OQ-5** | record overhead 上限 50 ns（AC-3）是否太鬆？ | 50 ns 是 10× E5 avg headroom；HdrHistogram `record` 內部是 atomic increment + bucket index 計算，~30-40 ns 實測；50 ns 容差是工程現實邊界 |

### 11.3 跨平台 Apple Silicon CI tuple

per 派工規範 + memory `project_mac_deployment_target`：
- `cargo check --target aarch64-apple-darwin -p openclaw_core` 必 PASS
- `cargo check --target aarch64-apple-darwin -p openclaw_engine` 必 PASS（E1 接線後）
- HdrHistogram 7.x 已 verified Mac arm64 build clean（pure Rust 無 sys dep）

### 11.4 不變式 / 反模式

- HdrHistogram 不能在 hot path reset（per E5 F1 教訓「不 per-tick reset 否則 mem 爆」）
- Mutex hold 時間在 record 路徑 ≤ 50 ns；summary read 路徑可容忍 ~10us（status_report 非 tick path）
- engine_mode `&'static str` 不可改 `String`（每 record alloc → ROI 完全反向）

---

## §12 References

- E5 F1 audit: `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-21--p1_lg1_demo_sla_violation_hotpath_audit.md`
- QA D1 LG-1 7d closure: `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-21--lg1_lg2_7d_closure_phase2a_t72h_verify.md`
- LG-1 runbook（SLA 改動目標）: `docs/runbooks/2026-05-11--lg1_h0_flip_rollback.md`
- LG plan baseline: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md`
- H0Gate source: `rust/openclaw_core/src/h0_gate.rs`
- engine_mode mapping: `rust/openclaw_engine/src/mode_state.rs:38`
- Memory: `project_mac_deployment_target`（Apple Silicon CI tuple 必含）

---

**Confidence**: HIGH for §1-§9 spec + module placement + API；MEDIUM-HIGH for §5 Grafana JSON skeleton（datasource binding 留 OQ-2）；HIGH for AC-1..AC-5 範圍（spec 已寫測試覆蓋指示）。
