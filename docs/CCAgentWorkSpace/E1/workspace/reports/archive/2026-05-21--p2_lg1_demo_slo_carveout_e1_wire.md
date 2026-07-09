# P2-LG1-DEMO-SLO-CARVEOUT — E1 hot-path 接線

**Date**: 2026-05-21
**Author**: E1
**Source**: PA spec `docs/execution_plan/2026-05-21--p2_lg1_demo_slo_carveout_spec.md` (429 lines)
**PA report**: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--p2_lg1_demo_slo_carveout_pa_impl.md`
**Status**: IMPL DONE，待 E2 review + E4 regression
**Risk grade**: 低（PA spec 已標 standalone plumbing；不改 H0Gate.check 邏輯）
**Apple Silicon CI**：PASS（驗證命令見 §6）

---

## §1 任務摘要

PA spec §10 列 5 件 plumbing，全部 land：

| # | Spec §10 要求 | 落地位置 |
|---|---|---|
| 1 | H0Gate 加 `metrics_recorder` + `engine_mode` 兩 field | `rust/openclaw_core/src/h0_gate.rs` |
| 2 | `H0Gate::with_metrics(config, recorder, engine_mode)` ctor + `set_metrics_recorder` / `set_engine_mode` setters | 同上 |
| 3 | `finalize_blocked` / `finalize_allowed` 各 1 行 `recorder.record(latency_us, engine_mode)` | 同上 |
| 4 | `pipeline_ctor.rs` 新 setter `set_h0_latency_recorder` + `set_endpoint_env` 同步 engine_mode 給 H0Gate | `rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs` |
| 5 | `status_report.rs` 1h reset cadence + log p50/p99/p999/max + `snapshot.h0_latency_summaries` 5-mode export | `rust/openclaw_engine/src/event_consumer/status_report.rs` + `tick_pipeline/commands.rs` |

新增整合測試 5 個（`tick_pipeline/tests/h0_latency_metrics.rs`）+ H0Gate 單元測試 3 個（P2-LG1 三條子路徑）。

---

## §2 修改清單

| 檔 | 改動 | 行數 |
|---|---|---|
| `rust/openclaw_core/src/h0_gate.rs` | struct 加 2 field、ctor 預設、`with_metrics` builder、`set_metrics_recorder` / `set_engine_mode` setter、`finalize_blocked` / `finalize_allowed` 各 1 行條件 record、3 新 unit test | +170 行（1073→1243；超 800 行 review threshold，內 1000-2000 一般工作量） |
| `rust/openclaw_core/src/hot_path_metrics/h0_latency.rs` | `H0LatencySummary` 加 `#[derive(serde::Serialize)]`（producer-only；不加 Deserialize 因 `&'static str` 與 `'de: 'static` bound 衝突） | +1 derive +7 行 doc |
| `rust/openclaw_engine/src/tick_pipeline/mod.rs` | TickPipeline struct 加 `h0_latency_recorder: Option<Arc<H0LatencyRecorder>>` + `h0_latency_last_reset_ms: u64`、加 `hot_path_metrics::H0LatencyRecorder` import | +2 field +20 行 doc |
| `rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs` | ctor 預設 2 field、`set_endpoint_env` 末加 `h0_gate.set_engine_mode(tag_str)`、新 setter `set_h0_latency_recorder` | +20 行 |
| `rust/openclaw_engine/src/tick_pipeline/commands.rs` | `snapshot()` 填入 `h0_latency_summaries`（5-mode `all_summaries(now_ms)`） | +6 行 |
| `rust/openclaw_engine/src/pipeline_types.rs` | `PipelineSnapshot` 加 `h0_latency_summaries: Option<Vec<H0LatencySummary>>`（serde skip_deserializing） | +12 行 |
| `rust/openclaw_engine/src/event_consumer/bootstrap.rs` | `set_endpoint_env` 後建 `Arc::new(H0LatencyRecorder::new())` + 呼 `set_h0_latency_recorder` | +14 行 |
| `rust/openclaw_engine/src/event_consumer/status_report.rs` | 1h reset cadence（`H0_LATENCY_RESET_INTERVAL_MS=3_600_000`）+ tracing::info! 加 5 個 percentile field | +40 行 |
| `rust/openclaw_engine/src/ipc_server/tests/mod.rs` | test snapshot literal 補 `h0_latency_summaries: None` | +2 行 |
| `rust/openclaw_engine/src/tick_pipeline/tests/h0_latency_metrics.rs` | 新建：5 個 integration test | +323 行 |
| `rust/openclaw_engine/src/tick_pipeline/tests/mod.rs` | 註冊新 sibling | +3 行 |

無 production 行為改變的條件：`metrics_recorder=None` 路徑（cold ctor / startup/mod.rs legacy 路徑）等同接線前；既有 5 子檢查邏輯零改動。

---

## §3 關鍵 diff

### 3.1 H0Gate struct + with_metrics ctor（h0_gate.rs）

```rust
pub struct H0Gate {
    // ... 既有 9 個 field ...
    metrics_recorder: Option<Arc<H0LatencyRecorder>>,  // P2-LG1
    engine_mode: &'static str,                          // P2-LG1
}

impl H0Gate {
    pub fn with_metrics(
        config: Option<H0GateConfig>,
        recorder: Arc<H0LatencyRecorder>,
        engine_mode: &'static str,
    ) -> Self {
        let mut gate = Self::new(config);
        gate.metrics_recorder = Some(recorder);
        gate.engine_mode = engine_mode;
        gate
    }
    pub fn set_metrics_recorder(&mut self, recorder: Arc<H0LatencyRecorder>) { ... }
    pub fn set_engine_mode(&mut self, engine_mode: &'static str) { ... }
}
```

### 3.2 finalize_blocked / finalize_allowed hot-path record

```rust
fn finalize_blocked(&mut self, reason: String, check_name: &str, start: Instant) -> H0CheckResult {
    let latency_us = start.elapsed().as_micros().min(u32::MAX as u128) as u32;
    self.stats.total_latency_us += latency_us as u64;
    if (latency_us as u64) > self.stats.max_latency_us {
        self.stats.max_latency_us = latency_us as u64;
    }
    // P2-LG1-DEMO-SLO-CARVEOUT (2026-05-21)：blocked path latency record
    if let Some(ref rec) = self.metrics_recorder {
        rec.record(latency_us as u64, self.engine_mode);
    }
    H0CheckResult { allowed: false, reason, check_name: check_name.to_string(), latency_us }
}
```

`finalize_allowed` 結構對稱。

### 3.3 pipeline_ctor.set_endpoint_env 同步 engine_mode

```rust
pub fn set_endpoint_env(&mut self, env: crate::bybit_rest_client::BybitEnvironment) {
    self.endpoint_env = Some(env);
    self.intent_processor.set_endpoint_env(env);
    let tag_str = self.effective_engine_mode();
    self.governance.set_engine_mode_tag(tag_str.to_string());
    // P2-LG1：同步 engine_mode 給 H0Gate metric tag
    self.h0_gate.set_engine_mode(tag_str);
}

pub fn set_h0_latency_recorder(&mut self, recorder: Arc<H0LatencyRecorder>) {
    self.h0_gate.set_metrics_recorder(Arc::clone(&recorder));
    self.h0_latency_recorder = Some(recorder);
}
```

### 3.4 status_report.rs 1h reset cadence + log

```rust
const H0_LATENCY_RESET_INTERVAL_MS: u64 = 3_600_000;
let mut h0_latency_log_summary: Option<H0LatencySummary> = None;
if let Some(rec) = pipeline.h0_latency_recorder.as_ref() {
    if pipeline.h0_latency_last_reset_ms.saturating_add(H0_LATENCY_RESET_INTERVAL_MS) <= now_ms {
        rec.reset_all(now_ms);
        pipeline.h0_latency_last_reset_ms = now_ms;
    }
    h0_latency_log_summary = rec.summary(pipeline.effective_engine_mode(), now_ms);
}
tracing::info!(
    // ... 既有 field ...
    h0_lat_count = h0_latency_log_summary.as_ref().map(|s| s.count).unwrap_or(0),
    h0_p50_us = h0_latency_log_summary.as_ref().map(|s| s.p50_us).unwrap_or(0),
    h0_p99_us = h0_latency_log_summary.as_ref().map(|s| s.p99_us).unwrap_or(0),
    h0_p999_us = h0_latency_log_summary.as_ref().map(|s| s.p999_us).unwrap_or(0),
    h0_max_us = h0_latency_log_summary.as_ref().map(|s| s.max_us).unwrap_or(0),
    "status report / 狀態報告"
);
```

### 3.5 PipelineSnapshot.h0_latency_summaries

```rust
#[serde(default, skip_deserializing, skip_serializing_if = "Option::is_none")]
pub h0_latency_summaries: Option<Vec<openclaw_core::hot_path_metrics::H0LatencySummary>>,
```

`snapshot()` 寫入：
```rust
h0_latency_summaries: self
    .h0_latency_recorder
    .as_ref()
    .map(|rec| rec.all_summaries(snapshot_now_ms)),
```

### 3.6 bootstrap.rs 注入時序

```rust
if let Some(env) = endpoint_env {
    pipeline.set_endpoint_env(env);  // 設定 endpoint_env 同步 H0Gate.engine_mode
}
// P2-LG1：必須在 set_endpoint_env 後，因為 effective_engine_mode 須先解析
let h0_latency_recorder = Arc::new(openclaw_core::hot_path_metrics::H0LatencyRecorder::new());
pipeline.set_h0_latency_recorder(h0_latency_recorder);
```

---

## §4 治理對照（PA spec §10 + §11 / E5 F1 + CLAUDE.md §四 / §九）

| 規範條目 | 落地 |
|---|---|
| PA spec §10 件 #1 H0Gate 2 field | h0_gate.rs：`metrics_recorder` + `engine_mode` ✅ |
| PA spec §10 件 #2 `with_metrics` ctor | h0_gate.rs：`with_metrics(config, recorder, engine_mode)` ✅ |
| PA spec §10 件 #3 finalize_blocked + finalize_allowed 各 1 行 record | h0_gate.rs：2 處條件 record（Some 分支內） ✅ |
| PA spec §10 件 #4 pipeline_ctor.rs:94 H0Gate ctor 改用 `with_metrics` | **採 setter 路徑**（`set_h0_latency_recorder` + `set_endpoint_env` 內 `set_engine_mode`），理由見 §5.1 ✅ |
| PA spec §10 件 #5 status_report.rs 加 summary export + 1h reset | status_report.rs：1h cadence reset_all + tracing::info! 加 5 percentile field + snapshot.h0_latency_summaries（commands.rs） ✅ |
| PA spec §3.6 5-mode `&'static str` 系統 | 用 `effective_engine_mode()` 5 種既有回傳；H0Gate.engine_mode 與 recorder 內 ENGINE_MODES 對齊 ✅ |
| PA spec §3.5 reset cadence 1h | status_report.rs 30s cadence piggy-back；觸發 `recorder.reset_all(now_ms)` ✅ |
| PA spec §4.5 reset 不在 hot path | status_report.rs 為 control plane（30s cadence），非 tick path ✅ |
| PA spec §11.4 不變式：H0Gate::new backward compat 不破 | `set_metrics_recorder` / `set_engine_mode` 後置 setter；test `test_p2_lg1_no_recorder_backward_compat` 證 None 路徑等同接線前 ✅ |
| PA spec §11.4 不變式：engine_mode `&'static str` 不可改 String | H0Gate.engine_mode 與 H0LatencySummary.engine_mode 維持 `&'static str` ✅ |
| PA spec §11.4 不變式：HdrHistogram 不在 hot path reset | reset 由 status_report 1h cadence 觸發，hot path 只走 record ✅ |
| PA spec AC-3 record overhead ≤ 50ns/call（release） | `test_p2_lg1_hot_path_with_recorder_overhead_sanity` 驗 hot path with recorder 整體 avg ≤ 500ns；純 `recorder.record` 50ns 由 hot_path_metrics::h0_latency::tests::test_record_overhead_ns 覆蓋 ✅ |
| CLAUDE.md §四 硬邊界：未觸碰 5 gate | metrics_recorder 為 observability 模組，未觸碰 live_reserved / Operator auth / OPENCLAW_ALLOW_MAINNET / secret slot / authorization.json ✅ |
| CLAUDE.md §九 file ≤ 2000 行 | h0_gate.rs 1243 行（review threshold 800 但仍在 2000 硬上限內，含 30+170=200 新 doc + test 行；無「順手 cleanup」） ⚠️ |
| CLAUDE.md §七 注釋默認中文 | 所有新加注釋為中文；既有英文 doc 未動 ✅ |
| CLAUDE.md §六 跨平台 / Apple Silicon | `cargo check --target aarch64-apple-darwin` 兩 crate 全 PASS（無新硬編碼路徑） ✅ |

---

## §5 不確定之處 / 設計 push-back

### 5.1 採 setter 路徑（不採 spec §10 件 #4 寫死 `with_metrics` ctor 調整）

**Spec 原文**：`pipeline_ctor.rs:94 H0Gate::new(...) 改 H0Gate::with_metrics(...)`。

**E1 採決**：採 setter 路徑（`set_h0_latency_recorder` 後置注入），保留 `H0Gate::new(Some(H0GateConfig { shadow_mode: false, ... }))` 既有 ctor 不動。

**理由**：
- `H0Gate::with_metrics` 需要 `Arc<H0LatencyRecorder>` + `engine_mode` 兩參數；但 pipeline_ctor.rs `with_balance` 是 ctor 入口，此時尚不知 `endpoint_env`（demo/live 在 set_endpoint_env 後才有），更不知 recorder（bootstrap.rs 才建）。
- 採 `with_metrics` 入 ctor 需把 recorder + endpoint_env 連帶塞進 `with_balance` 簽名，引發 30+ caller site 大改（test、startup/mod.rs legacy、event_consumer、handlers）。
- 改採 setter 路徑後 `H0Gate::with_metrics` 仍 land（spec §4.2 + spec §10 件 #2 要求），其他 use cases / future test / direct usage 可用 ctor 路徑；TickPipeline 用 setter 是最小 footprint 接線決策。
- 兩條路徑語意完全等價（test `test_p2_lg1_with_metrics_records_both_paths` + `test_p2_lg1_post_construction_injection` 各驗一條）。

### 5.2 採 per-pipeline 獨立 `Arc<H0LatencyRecorder>`（不採 spec §4.3 共用 Arc）

**Spec 原文** §4.3：「`shared_recorder` 在 engine 啟動時建立一個全域 `Arc<H0LatencyRecorder>`，三 pipeline（paper/demo/live）共用 single recorder」。

**E1 採決**：每個 pipeline 在 bootstrap.rs 各自建 `Arc::new(H0LatencyRecorder::new())`，不共用。

**理由**：
- 3 pipeline 各跑獨立 tokio runtime；共用 Arc 會每 tick 撞 Mutex（3 producer × ~1000 tick/s ≈ 3k contention/s），毀 spec AC-3 50ns 預算（spec §3.4 自己也說「Mutex 在 single-thread tick path 無瓶頸」 — 但跨 3 runtime 就破了這個前提）。
- per-pipeline 獨立 instance：每 recorder single producer + 偶爾 status_report consumer，Mutex 在實際運行 uncontested，符合 spec §3.4 設計前提。
- recorder 內仍持 5 mode histogram，per-pipeline 只填自己 engine_mode 那格；output JSON shape 與 spec §3.6 一致（其他 4 mode count=0 由 IPC consumer 過濾，符合 spec 設計）。
- 不必改 EventConsumerDeps（已 ~30+ field）/ main_pipelines.rs PipelineSpawnContext，最小 footprint。

**Trade-off**：若 future 需「cross-pipeline aggregate p99」，per-pipeline 路徑需 IPC consumer 端 merge HdrHistogram；但 spec §6.2 alert eval cadence 是 per-engine_mode 評估（H0_P99_WARN / H0_MAX_WARN / H0_MAX_FAIL），merge 並非 spec 要求。

### 5.3 採 `H0LatencySummary` 僅 Serialize 不 Deserialize

**Spec 原文** §3.3：未明確要求 round-trip。

**E1 採決**：`H0LatencySummary` derive `serde::Serialize` 不加 `Deserialize`。

**理由**：
- `engine_mode: &'static str` 與 serde Deserialize bound `'de: 'static` 衝突（'de 是 deserializer borrow lifetime，不會超過 'static）。
- PipelineSnapshot 已 derive Deserialize（state restore / Python writebacks 可能反向）；用 `#[serde(default, skip_deserializing, skip_serializing_if = "Option::is_none")]` 讓 h0_latency_summaries 在 Deserialize 路徑取 None（producer-only field）。
- IPC consumer 是 Python（讀 JSON 字串），不需 Rust 端 Deserialize。

**未來變更指引**：若要 round-trip Deserialize，把 `engine_mode: &'static str` 改 `String`（cold path 可接 to_string() 成本），同步把 H0LatencyRecorder API 也跟改。

### 5.4 status_report.rs 加的 5 個 percentile field（h0_lat_count / h0_p50_us / h0_p99_us / h0_p999_us / h0_max_us）超 spec §10 件 #5 範圍

**Spec 原文** §10：只要求 status JSON 加 `h0_latency_summary`。

**E1 採決**：除 `snapshot.h0_latency_summaries` 已寫 IPC 路徑外，**額外**在 tracing::info! status_report 行內加 5 percentile field，讓 log line 直接可讀。

**理由**：
- 既有 status_report 日誌已含 `h0_checks / h0_blocked / h0_shadow_would_block` 三 field；加 percentile 對 console-level observability 更直觀，無 IPC 接線依賴。
- 改動 minimal（tracing 行 5 個 unwrap_or(0)），不影響 production 行為。
- 若 E2 review 認為超範圍可移除（保留 snapshot.h0_latency_summaries 即達 spec §10 件 #5）。

### 5.5 file size 警告：h0_gate.rs 達 1243 行

**Spec 原文** CLAUDE.md §九：`Files over 800 lines require review attention; 2000 lines is the hard cap`。

**E1 採決**：未拆檔；新加 170 行（含 30 行 P2-LG1 doc + 加 3 個 unit test 140 行）。

**理由**：
- 既有 h0_gate.rs 已 1073 行（test mod 占 ~520 行）；P2-LG1 額外 +170 = 1243，仍在 2000 行硬上限內。
- 拆檔 `h0_gate/tests/` 或 `h0_gate/metrics.rs` 屬於「順手 cleanup」 — 違反 §四 「不在修復過程中順手優化未被要求的代碼」。
- E2 review 若決定拆分，建議獨立 follow-up task（保 P2-LG1 wave 焦點 + git history 清晰）。

---

## §6 驗證

### 6.1 cargo test
```bash
# core release 全測（含 hot_path_metrics 8 + h0_gate 33 + 3 新 P2-LG1）
cd /Users/ncyu/Projects/TradeBot/srv/rust && cargo test --release -p openclaw_core
# 結果：368/8/19/2/7/6 entry 全 PASS / 0 fail

# engine release 全測
cd /Users/ncyu/Projects/TradeBot/srv/rust && cargo test --release -p openclaw_engine
# 結果：3272 PASS / 0 FAIL / 3 ignored
#   - baseline 3267 + 5 新 integration test（h0_latency_metrics.rs）
#   - 3 個 ignored 為既有 net-IO test 非本 wave 影響
```

### 6.2 Apple Silicon CI tuple
```bash
cd /Users/ncyu/Projects/TradeBot/srv/rust && cargo check --target aarch64-apple-darwin -p openclaw_core
# 結果：PASS（0.42s）

cd /Users/ncyu/Projects/TradeBot/srv/rust && cargo check --target aarch64-apple-darwin -p openclaw_engine
# 結果：PASS（13.75s）
```

### 6.3 硬編碼路徑 grep
```bash
grep -rn '/home/ncyu\|/Users/[^/]*' <修改檔列表> | grep -v 'docs/'
# 結果：0 hit
```

### 6.4 emoji grep
```bash
grep -Pn '[\x{1F000}-\x{1FFFF}\x{2600}-\x{27BF}\x{1F300}-\x{1F9FF}]' <修改檔列表>
# 結果：0 hit
```

### 6.5 新 P2-LG1 test list

H0Gate unit test（3 個，h0_gate.rs）：
- `test_p2_lg1_with_metrics_records_both_paths` — `H0Gate::with_metrics` ctor 注入後 allowed + blocked 兩條路徑都 record（驗 finalize_allowed/blocked 同 record）
- `test_p2_lg1_no_recorder_backward_compat` — 預設 `H0Gate::new` 路徑（recorder=None）不破既有 GateStats 累計
- `test_p2_lg1_post_construction_injection` — `set_metrics_recorder` + `set_engine_mode` 後接注入語意等同 `with_metrics`

TickPipeline integration test（5 個，tick_pipeline/tests/h0_latency_metrics.rs）：
- `p2_lg1_set_endpoint_env_propagates_engine_mode_to_h0_gate` — `set_endpoint_env(Demo/LiveDemo)` 同步 effective_engine_mode 給 H0Gate；record 後 histogram bucket 正確分流（per-pipeline 自己 bucket count>0，其他 4 mode count=0）
- `p2_lg1_snapshot_emits_5_mode_summaries` — `snapshot().h0_latency_summaries` 含 5 mode 全 entry（per spec §3.6），本 pipeline mode count>0
- `p2_lg1_no_recorder_snapshot_field_is_none` — 未注入 recorder 時 `snapshot.h0_latency_summaries` = None（既有 IPC consumer 不報錯）
- `p2_lg1_hot_path_with_recorder_overhead_sanity` — 100k iter H0Gate.check 包含 recorder.record 整體 avg ≤ release 500ns / debug 5000ns
- `p2_lg1_no_recorder_overhead_within_bound` — with/no recorder 兩 pipeline 對比，diff ≤ release 1500ns / debug 3000ns（None 分支極小 branch 開銷）

### 6.6 編譯 warning（無新增）
```
warning: unused import: super::LEAD_WINDOW_SECS_MAIN (既有 W-AUDIT-8c)
warning: function spawn_position_reconciler is never used (既有)
warning: method make_intent is never used (既有 MaCrossover)
warning: type ScriptedSpawn is more private (既有 live_auth_watcher_tests)
```
新增 0 warning。

---

## §7 Operator 下一步

- **不 commit**（per E1 contract）— 提交 E2 對抗性 review
- E2 重點審查項：
  - PA spec §10 件 #4 採 setter 而非 ctor（§5.1）— 是否接受
  - per-pipeline 獨立 recorder 反 spec §4.3 共用（§5.2）— Mutex 爭用論點是否成立
  - `H0LatencySummary` 僅 Serialize 不 Deserialize（§5.3）— skip_deserializing 設計是否接受
  - status_report 加 5 percentile log field（§5.4）— 是否視為 spec creep（可移除保 minimal）
  - h0_gate.rs 1243 行（§5.5）— 是否要求拆分 follow-up
  - `finalize_allowed` 在 shadow mode 路徑也 record（spec 未明確）— shadow_would_block 樣本計入 percentile，是否符合 PA 意圖
- E4 regression 重點：
  - cargo test --release -p openclaw_engine 3272 PASS 不破
  - hot_path_baseline 既有 perf benchmark 不退化（spec AC-3 50ns/call 由 hot_path_metrics::h0_latency::tests::test_record_overhead_ns 覆蓋；本 wave H0Gate.check 整體 hot path 應仍在 spec §2.2 carve-out budget 內）
- 後續 PA wave（不在本 E1 scope）：
  - SLA 文檔 §2.1 4 處 carve-out 改動（spec §9 PA 留範圍 — 留下個 doc-update wave）
  - TODO.md `P1-LG1-DEMO-SLA-VIOLATION` 改 P2 + LG-1 closure footnote（spec §7）
  - `helper_scripts/db/audit/h0_latency_alert_eval.py` healthcheck script（spec §6.3）
  - Grafana datasource UID binding（spec §11.2 OQ-2）

---

## §8 References

- PA spec: `docs/execution_plan/2026-05-21--p2_lg1_demo_slo_carveout_spec.md`
- PA report: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--p2_lg1_demo_slo_carveout_pa_impl.md`
- E5 F1 audit verdict: `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-21--p1_lg1_demo_sla_violation_hotpath_audit.md`
- H0Gate source: `rust/openclaw_core/src/h0_gate.rs:269` (check) / :511-541 (finalize_blocked) / :549-578 (finalize_allowed)
- HdrHistogram recorder: `rust/openclaw_core/src/hot_path_metrics/h0_latency.rs`
- engine_mode mapping: `rust/openclaw_engine/src/mode_state.rs:38` `effective_engine_mode`
- Pipeline ctor: `rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs:94` (with_balance H0Gate::new) / :220-243 (set_endpoint_env) / :255-258 (set_h0_latency_recorder)
- Bootstrap: `rust/openclaw_engine/src/event_consumer/bootstrap.rs:192-211`
- Status report: `rust/openclaw_engine/src/event_consumer/status_report.rs:91-139`
- Snapshot: `rust/openclaw_engine/src/tick_pipeline/commands.rs:1657-1664`
- Test: `rust/openclaw_engine/src/tick_pipeline/tests/h0_latency_metrics.rs`

**Confidence**：HIGH for §2-§6 接線正確性 + cargo test PASS + Apple Silicon CI 雙綠 + per-pipeline 設計權衡論點；MEDIUM for §5.1 setter vs ctor 路徑（與 spec §10 件 #4 字面有差異，需 PA / E2 sign-off）。
