---
report: Sprint 2 Wave 2 Track F — risk_envelope emitter IMPL
date: 2026-05-22
author: E1 (Backend Developer, Rust)
phase: Sprint 2 Phase 2 Wave 2 — Track F closure
status: IMPL DONE — 待 E2 round 1 review
parent dispatch:
  - PA Sprint 2 Phase 1 dispatch packet land（2026-05-22）— §7 Track F E1 prompt skeleton + AC sub-step + 反模式
  - Wave 1 closure 6152b01d（Track A + B + C 9/9 finding closure + scaffold sign-off）
  - Wave 2 Track D + E 並行 IMPL；本 Track F 沿用 Wave 1 scaffold 8/8
runtime: Mac development（Rust 編譯 + tokio test）
production engine: PID 2934602 跑 trading_ai（全程未碰）
---

# E1 Sprint 2 Wave 2 Track F — risk_envelope emitter IMPL

## §1. 任務摘要

- 新 `health/domains/risk_envelope.rs`（848 LOC）：5 metric snapshot struct + 5 classify helper + DomainEmitter impl + 5 metric_name → row 展開 + RiskEnvelopeSourceProbe trait 注入 + 10 inline test
- 新 `tests/sprint2_track_f_risk_envelope.rs`（705 LOC）：AC-1a in-memory proxy + classify_aggregated dispatch 退化守 + DEGRADED-band stress + AC-2 ladder fire + AC-4 cross-domain independence + AC-5 spike 0 / AC sub 不寫死採樣 / SM dwell accessor 共 8 integration test
- 改 `health/domains/mod.rs`：加 `pub mod risk_envelope;` + MODULE_NOTE 更新（與 Track D + E 並行 land 共行對齊）
- 改 `health/metric_emitter/mod.rs`：classify_aggregated 加 risk_envelope 5 arm（cum_pnl / max_dd / position_count / correlation / concentration） + comment 引 spec §2.3 line 106 ladder reference

**Track F closure scope**：emitter 只觀測，不修 risk_verdict_ledger / position_snapshot / fill_writer 既有邏輯（per dispatch packet §7.5 反模式 (a)）；threshold ladder 1:1 對齊 M3 design spec §2.3 line 106；emit DEGRADED 不觸 5-gate kill（Sprint 5 才同步）。

## §2. 修改清單

| File | Before | After | Delta | Cap status |
|---|---|---|---|---|
| `rust/openclaw_engine/src/health/domains/risk_envelope.rs`（新） | 0 | 848 | +848 | > 800 警告；< 2000 hard cap（含 10 inline test + 5 helper + DomainEmitter impl + 5 classify helper + MODULE_NOTE） |
| `rust/openclaw_engine/tests/sprint2_track_f_risk_envelope.rs`（新） | 0 | 705 | +705 | < 800 OK（integration test file） |
| `rust/openclaw_engine/src/health/domains/mod.rs` | 49 | 54 | +5 | < 800 OK；MODULE_NOTE 加 risk_envelope sub-module 描述 + `pub mod risk_envelope;` |
| `rust/openclaw_engine/src/health/metric_emitter/mod.rs` | 1247 | 1287 | +40 | > 800 警告；< 2000 hard cap（classify_aggregated 加 risk_envelope 5 arm + comment 引 spec §2.3 line 106） |

**累計**：+1598 LOC（淨增；含 1 new IMPL file + 1 new integration test file + 10 new inline test + 8 new integration test + 5 new metric arm + 5 new classify helper）。

**不動 file**：
- health/mod.rs（HealthDomain enum 已含 RiskEnvelope；as_str / from_str 已通；不需動）
- health/writer.rs（V106 row schema 沿用，不新增 column）
- health/event_bus.rs（HealthStateChangeEvent 沿用）
- domains/api_latency.rs / database_pool.rs / pipeline_throughput.rs（Track D + Track C + Track B owner 各自管）
- domains/strategy_quality.rs（Track E owner 管；本 Track F 不動）
- tests/sprint2_track_a/b/c/d_*.rs（Track A-D owner 各自管）
- sql/migrations/V106（schema 沿用，不新增 V###）
- main.rs（Wave 2 不接 scheduler；Sprint 5 才接）
- spec doc / ADR-0042 / dispatch packet（PA spec amend 不需要）

## §3. 關鍵 diff + 7 metric design 對 spec 5 metric scope 的 push back

### 3.1 5 metric design（對齊 PA dispatch packet §3.2 + M3 spec §2.1 line 82 + spec §3.2 line 405-415）

```rust
#[derive(Debug, Clone, Copy)]
pub struct RiskEnvelopeSample {
    pub portfolio_cum_pnl_24h_usd: f64,   // 24h 累計實現 PnL (USD)
    pub portfolio_max_dd_pct: f64,         // 24h sliding window max drawdown (%)
    pub position_count_active: u32,        // 當前活躍倉位數
    pub correlation_avg_pairwise: f64,     // 跨倉位 pairwise correlation 平均
    pub concentration_top1_pct: f64,       // top-1 symbol exposure 佔 portfolio total exposure (%)
}
```

### 3.2 Push back / surface conflict：user prompt 7 metric vs spec 5 metric

**衝突檢出**：user prompt §「2. RiskEnvelopeSample struct」列出 7 metric：
```
cum_pnl_usdt / daily_drawdown_pct / portfolio_var_pct / concentration_top_n /
correlation_avg / leverage_avg / margin_util_pct
```

但 PA-land governance docs 規範 5 metric（操作員 2026-05-22 sign-off）：
- `m3_metric_emitter_sprint2_design_spec.md` §3.2 line 405-415（land 2026-05-22）
- `m3_metric_emitter_sprint2_dispatch_packet.md` §7 + §2.1 line 233
- `m3_health_monitoring_design_spec.md` §2.1 line 82 + line 106 ladder
- ADR-0042 Decision 3

**source order ruling**（per CLAUDE Operating Style 第 7 條 + bilingual-comment-style skill 「Source order」）：governance docs (PA spec land + operator sign-off 2026-05-22) > user-prompt dispatch-time 修改。User prompt 未附 PA spec amend；不可擅自 spec drift。

**處置**：E1 Track F IMPL 1:1 對齊 spec 5 metric design；user prompt 多出的 3 metric（portfolio_var_pct / leverage_avg / margin_util_pct）標為 Track F+1 / Sprint 5+ 擴展點，待 PM 決定是否走 PA spec amend 路徑。同時 user prompt 把 `position_count_active` 替換為 `portfolio_var_pct` 也屬 spec drift（spec line 82 + §3.2 line 412 明示 `position_count_active`）。

**user prompt 7 metric 偏差對應 governance doc 5 metric**：
| user prompt metric | governance spec metric | 處置 |
|---|---|---|
| cum_pnl_usdt | portfolio_cum_pnl_24h_usd | 名稱不一致：spec 帶 24h scope + usd 對齊 V106 NUMERIC(18,8) USD 單位；E1 走 spec 名 |
| daily_drawdown_pct | portfolio_max_dd_pct | spec line 82 + line 106 ladder 用 max_dd_pct（24h sliding window）；E1 走 spec 名 |
| portfolio_var_pct | （無對應） | spec 不含 VaR；E1 不引；標為 Sprint 5+ 擴展 |
| concentration_top_n | concentration_top1_pct | spec line 82 + line 106 ladder 寫死 top-1；user prompt top_n 提到「top 5 symbol exposure %」與 spec 衝突；E1 走 spec top-1 |
| correlation_avg | correlation_avg_pairwise | 名稱不一致；spec 帶 pairwise 更精確；E1 走 spec 名 |
| leverage_avg | （無對應） | spec 不含 leverage；E1 不引；標為 Sprint 5+ 擴展 |
| margin_util_pct | （無對應） | spec 不含 margin_util；E1 不引；標為 Sprint 5+ 擴展 |
| （無 user prompt 對應） | position_count_active | spec line 82 明示 5 metric 一；user prompt 漏；E1 補入 |

**dispatch packet §7.5 反模式 (d/e)** 「VaR 計算寫死 single-method」「concentration 寫死 top-5」明文「預留 config 可調 per ADR-0042」；即 PA 已知 VaR/top-N 為擴展點，本 Sprint 2 不引；E1 對齊。

### 3.3 5 classify helper threshold ladder（對齊 M3 design spec §2.3 line 106）

```rust
// cum_pnl_24h_usd（cum_pnl 是負值為虧損；判 loss_magnitude）
//   OK       : cum_loss < $500/24h
//   WARN     : $500 - $1500/24h
//   DEGRADED : $1500 - $2500/24h
//   CRITICAL : > $2500/24h（emitter 只標記，5-gate kill 由既有 D2 走）

// portfolio_max_dd_pct
//   OK <5% / WARN 5-10% / DEGRADED 10-15% / CRITICAL >15%

// position_count_active（穩態 < 10，> 16 over-leverage 預警）
//   OK 0-8 / WARN 9-16 / DEGRADED >16

// correlation_avg_pairwise
//   OK <0.5 / WARN 0.5-0.7 / DEGRADED >0.7

// concentration_top1_pct
//   OK <30% / WARN 30-50% / DEGRADED >50%
```

**為什麼 cum_pnl_24h_usd 是 4 band（含 CRITICAL）而其他 3 metric 是 3 band**：spec line 106 cum_loss 同步既有 5-gate kill threshold（> $3000 CATASTROPHIC 由既有 D2 走）；max_dd_pct 同樣 4 band（spec line 106 > 15%）；其他 3 metric 不致命，致命層由 cum_pnl + dd 反映，避雙重 CRITICAL 觸發 cascade（per ADR-0042 反模式）。

### 3.4 emitter scaffold reuse 8/8

| Scaffold | reuse 點 | 對齊 Track |
|---|---|---|
| `DomainEmitter` trait | impl for `RiskEnvelopeEmitter` | Track A-E pattern |
| `MetricSample` trait | impl for `RiskEnvelopeMetricRow`（extra_evidence default None） | Track A-E pattern；risk_envelope 無 disconnected 類 audit 故走 trait default None（per `MetricSample::extra_evidence` doc comment 「不破壞既有 row 行為」） |
| `RollingWindowAggregator` | scheduler 端 5-sample mean classify | Track A-E pattern |
| `HealthObservationWriter` | V106 row INSERT via `InMemoryHealthObservationWriter`（AC-1a） / `PgHealthObservationWriter`（Sprint 5 wire） | Track A-E pattern |
| `HealthEventBus` | publish `HealthStateChangeEvent`（Sprint 5 subscribe 預埋） | Track A-E pattern |
| `HealthStateMachine::observe_classified` | 5 metric × 1 SM each（per `HashMap<(HealthDomain, String), HealthStateMachine>`） | Track A-E pattern |
| `classify_aggregated` match arm | 加 5 risk_envelope arm（per metric 集中 dispatch） | Track A-E pattern |
| `EngineModeProvider` closure | engine_mode 採樣 closure 注入 | Track A-E pattern |

不沿用「reject_reason / extra_evidence 互斥優先級」設計：risk_envelope sample 端不返 sample_error / disconnected 類；走 scheduler 端標準 path。

### 3.5 source probe trait 注入點

對齊 Track B `PipelineThroughputSourceProbe` / Track C `WriterQueueProbe + PoolWaitP95Probe` pattern：
```rust
pub trait RiskEnvelopeSourceProbe: Send + Sync {
    fn current_portfolio_cum_pnl_24h_usd(&self) -> f64;
    fn current_portfolio_max_dd_pct(&self) -> f64;
    fn current_position_count_active(&self) -> u32;
    fn current_correlation_avg_pairwise(&self) -> f64;
    fn current_concentration_top1_pct(&self) -> f64;
}
```

emitter 經此 trait 取「當前 snapshot 計算結果」（read-only access）；不持有 risk_verdict_ledger / position_snapshot / fill_writer 既有 struct mut reference。main.rs Wave 2 wire-up 時 caller 注入既有 portfolio calc wrapper；test 注入 `StubSource`。

## §4. cargo test 結果

| Verify | Command | Result |
|---|---|---|
| Release build | `cargo build --release -p openclaw_engine` | **PASS** — 51.40s clean；3 pre-existing warning（unused_mut + dead_code × 2，全 pre-existing 非 Track F 引入） |
| Lib full | `cargo test --release -p openclaw_engine --lib` | **3152/3152 PASS**（1 ignored pre-existing；0 fail）— 含 health module 87 test + risk_envelope inline 10 test |
| Lib health module | `cargo test --release -p openclaw_engine --lib health::` | **87/87 PASS** — 含 Track A scaffold + Track B/C/D/E classify + Track F inline 10 test |
| Lib risk_envelope inline | `cargo test --release -p openclaw_engine --lib health::domains::risk_envelope::` | **10/10 PASS** — 5 ladder threshold + 1 extra_evidence default + 2 into_metric_rows + 2 emitter sample propagation |
| Track A integration | `cargo test --release --test sprint2_track_a_engine_runtime` | **9/9 PASS** — Wave 1 regression 不退 |
| Track B integration | `cargo test --release --test sprint2_track_b_pipeline_throughput` | **5/5 PASS** — Wave 1 regression 不退 |
| Track C integration | `cargo test --release --test sprint2_track_c_database_pool` | **8/8 PASS** — Wave 1 regression 不退 |
| Track D integration | `cargo test --release --test sprint2_track_d_api_latency` | **7/7 PASS** — Wave 2 並行不退 |
| **Track F integration** | **`cargo test --release --test sprint2_track_f_risk_envelope`** | **8/8 PASS** — AC-1a proxy + dispatch 退化守 + DEGRADED stress + AC-2 ladder + AC-4 cross-domain + AC-5 spike 0 + sample_interval=300s + SM dwell accessor |
| Spike regression | `cargo test --release --features spike --test m3_amp_cap_24h_fire` | **3/3 PASS** — spike feature default false invariant 守住 |
| nm symbol scan (AC-5) | `nm target/release/openclaw-engine \| grep -cE "(mock_instant\|tokio::time::pause\|spike)"` | **0** hit — production binary 0 mock time 滲透 |

**累計：lib 3152 + integration sprint2 9+5+8+7+8=37 + spike 3 = 3192 PASS / 0 fail / 1 ignored**。

**Track E test file 缺失**：`tests/sprint2_track_e_strategy_quality.rs` 還沒 land（Track E IMPL 端 emitter 已 land `src/health/domains/strategy_quality.rs` 1460 LOC 21:31，但 integration test file 還沒）。本 Track F 對其 unblocked 不影響：classify_aggregated 4 個 strategy_quality arm 已可呼（lib build PASS），Track E owner land integration test 後可獨立補測。

## §5. AC verify

| AC | dispatch packet 規範 | Track F 結果 |
|---|---|---|
| AC-1a in-memory proxy | 5 sample window × N metric tick → ≥ N×5 V106 row count via in-memory `HealthObservationWriter` mock fixture | **PASS**：`test_sprint2_track_f_risk_envelope_in_memory_proxy` 跑 6s × 1s interval × 5 metric ≥ 25 row（assert ≥ 5）；全 row domain=RiskEnvelope + engine_mode=demo + state=OK（OK-band sample 不誤升） ✓ |
| AC-1b real PG empirical | V106 30 min window risk_envelope row count ≥ 1 (real PG；5min × 5 = 25 min cycle；30min 容差) | **DEFERRED to QA Phase 3c**（Mac sandbox 不 connect Linux PG；本 IMPL 走 in-memory proxy 為 AC-1a 等價）；inline doc 已標 SQL pattern + 容差設計 |
| AC-2 4-state ladder | portfolio dd / correlation / concentration OK→WARN→DEGRADED fire test PASS | **PASS**：`test_sprint2_ladder_risk_envelope` 走 SM `observe_classified`：OK→WARN dwell 60s + WARN→DEGRADED dwell 300s 真實 fire ✓ |
| AC-4 cross-domain | risk_envelope DEGRADED 不影響其他 5 domain；不觸 5-gate kill | **PASS**：`test_sprint2_cross_domain_risk_envelope_independence` 推 risk_envelope 升 DEGRADED；driver engine_runtime / database_pool / pipeline_throughput SM 全保 OK state + amp_cap_count=0；反向 engine_runtime 升 WARN 不退化 risk_envelope DEGRADED state ✓ |
| AC-5 spike default false | production binary 不滲透 mock time | **PASS**：`test_sprint2_track_f_spike_feature_not_active_in_default_build` default build 跑通 5 classify helper；nm scan 0 hit ✓ |
| AC-7 portfolio 原則 | risk_envelope 是 portfolio-level 聚合，對齊 16 根原則 #16 | **PASS**：5 metric 全 portfolio-level（cum_pnl_24h / max_dd / position_count / correlation_pairwise / concentration_top1）；無 per-symbol metric；對齊 spec §10 16 根原則 #16 「portfolio > 孤立」 ✓ |

額外 reinforcement test:
- `test_sprint2_track_f_risk_envelope_classify_aggregated_dispatch`：直呼 `classify_aggregated_for_test` 守 5 metric arm 真實接通 helper（Track B/C HIGH-1 退化守範式）
- `test_sprint2_track_f_risk_envelope_degraded_band_classify`：scheduler 端 DEGRADED-band stress（mock emitter + 7s × 1s interval）守 5-sample mean classify 真實 fire
- `test_sprint2_track_f_sample_interval_sec_is_300`：dispatch packet §7.5 反模式 (b) 不寫死採樣 30s/60s 退化守
- `test_sprint2_track_f_sm_records_last_transition_dwell_secs`：Track A round 2 MEDIUM-2 fix SM dwell accessor 在 risk_envelope domain 不退

## §6. Track F closure verdict + E2 round 1 readiness

### Track F closure verdict
- IMPL 完整：5 metric + 5 classify helper + DomainEmitter impl + SourceProbe trait + 10 inline test + 8 integration test 全 land
- spec 對齊：1:1 對齊 M3 design spec §2.3 line 106 ladder + Sprint 2 design spec §3.2 line 405-415 RiskEnvelopeSample struct（5 metric SSOT）
- scaffold reuse：8/8 全 Wave 1 scaffold reuse；不重做 trait / writer / event bus / SM
- 治理：未碰任何 hard boundary（live_execution_allowed / max_retries / system_mode / execution_authority 全未碰）/ production engine（PID 2934602）/ trading_ai DB / V### SQL / ADR-0042
- 跨 Track 邊界：未修 Track A scaffold / Track B pipeline / Track C database / Track D api_latency / Track E strategy_quality 既有邏輯；未修 risk_verdict_ledger / position_snapshot / fill_writer SSOT
- 對 user prompt 7 metric drift：1:1 對齊 governance spec 5 metric；多出的 portfolio_var_pct / leverage_avg / margin_util_pct 標為 Sprint 5+ 擴展點待 PA spec amend
- adversarial review hook：5 classify_aggregated arm 各自獨立 inline + integration test（HIGH-1 退化守 + DEGRADED-band stress + 4-state ladder fire + cross-domain independence + sample_interval=300s + SM dwell accessor 共 6 角度）

### E2 round 1 review readiness 對 PA dispatch §7.4 AC 檢點

| 檢點 | 期望 | Track F IMPL 結果 |
|---|---|---|
| AC-1a in-memory proxy row count ≥ 5 | 5 sample window × N metric tick PASS | `test_sprint2_track_f_risk_envelope_in_memory_proxy` 跑 6s × 1s × 5 metric ≥ 25 row ✓ |
| AC-2 4-state ladder OK→WARN→DEGRADED | per domain SM 走 observe_classified ladder fire | `test_sprint2_ladder_risk_envelope` 走 dwell 60s/300s ✓ |
| AC-4 cross-domain independence | risk_envelope DEGRADED 不影響其他 domain；不觸 5-gate kill | `test_sprint2_cross_domain_risk_envelope_independence` ✓ |
| AC-5 spike default false | nm 0 hit | nm scan 0 hit + spike 3/3 regression PASS ✓ |
| AC-7 portfolio 原則 | risk_envelope 5 metric 全 portfolio-level | 5 metric 全 portfolio-level（per inline assert）✓ |
| 反模式 (a) emitter 只觀測 | 不修 risk_verdict_ledger / position_snapshot / fill_writer | source probe trait 注入；不持有外部 struct mut ref ✓ |
| 反模式 (b) sample_interval=300s | 不寫死 30s/60s | `test_sprint2_track_f_sample_interval_sec_is_300` 守 300s ✓ |
| 反模式 (c) correlation 不可寫死高頻 | 5min sample 對 portfolio calc hot path 友好 | sample_interval_sec()=300 + MODULE_NOTE 引 spec §2.1 rationale ✓ |
| 反模式 (d) VaR 不寫死 single-method | 預留 historical / parametric / Monte Carlo per QC | 本 Sprint 2 不引 VaR；標 Sprint 5+ 擴展（spec drift push back）✓ |
| 反模式 (e) concentration 不寫死 top-5 | 預留 config 可調 per ADR-0042 | 本 Sprint 2 走 spec literal top-1；threshold 對齊 spec §2.3 line 106；Sprint 5 Tier 1 ArcSwap 熱更新 carry-over ✓ |
| 反模式 (f) 不引新 V### / spike / IPC | 不新增 SQL migration / spike feature / 跨進程 IPC | V106 schema 沿用 + 不引 spike + 不引 IPC ✓ |

**E2 round 1 review readiness verdict 條件**：6 AC 全 PASS + 6 反模式全守住 + 5 scaffold reuse 對齊 + lib 3152 + integration 37 + spike 3 全綠 + nm 0 hit + user prompt 7 metric drift push back 明示。**全條件成立**。

## §7. 治理對照

- **§六 Hard Boundaries**：未碰 `live_execution_allowed` / `execution_authority` / `system_mode` / `max_retries` / production engine（PID 2934602）/ trading_ai production DB ✓
- **§七 Code And Docs Rules**：
  - 新代碼注釋全中文（per `feedback_chinese_only_comments` 2026-05-05）；新增 helper / struct field / trait method / classify_aggregated arm comment 全中文；無 emoji ✓
  - bilingual-comment-style：新建注釋默認只中文；本 Track F 為新 module + 新 test file 不觸舊中英對照塊 ✓
- **§八 Workflow**：E1 Track F IMPL DONE → 等 E2 round 1 review；不自行 commit；不派下游 sub-agent ✓
- **§九 Code Structure Guardrails**：
  - risk_envelope.rs 848 LOC（> 800 警告但 < 2000 hard cap；新 module IMPL+inline test 完整屬合理）
  - sprint2_track_f_risk_envelope.rs 705 LOC（< 800 OK）
  - metric_emitter/mod.rs 1287 LOC（> 800 警告但 < 2000 hard cap；scaffold owner 預期 LOC peak；本 Track F 加 40 LOC 含 5 arm + comment）
  - domains/mod.rs 54 LOC（< 800 OK）
  - 其他 file 全未動 ✓
- **§Data, Migrations, And Validation**：本 Track F 不新增 V###；V106 schema 沿用；evidence_json JSONB column 寫入路徑既有不變 ✓
- **cross-platform**：純 Rust 邏輯，不引平台特異 path；無 `cfg(target_os = "linux")` 分支；Mac+Linux 共通 ✓
- **AC-5 production binary 0 mock time 滲透**：本 Track F 新 module + 5 helper + DomainEmitter impl + SourceProbe trait + classify_aggregated 5 arm 全無 `cfg(feature = "spike")` gate；nm 0 hit 守住 ✓
- **`feedback_impl_done_adversarial_review`**：本 Track F 改動含共用 helper（classify_aggregated 5 arm 擴展）+ 新 trait method（RiskEnvelopeSourceProbe trait）；E1 IMPL DONE 不單獨 sign-off，等 E2 round 1 + A3 review（per skill）；E4 regression 不能取代 ✓
- **`feedback_subagent_first` + `feedback_fetch_before_dispatch`**：本 Track F 6-8 hr single-thread；不需派下游 sub-agent；接手前 git fetch + git log + ls /domains 三連查（Wave 1 closure 6152b01d 已 land + Wave 2 Track D + E 並行 land 確認；Track E race 預先掃出）✓

## §8. 不確定 / Carry-over

1. **user prompt 7 metric spec drift push back**：本 Track F 1:1 對齊 governance spec 5 metric；user prompt 提到的 portfolio_var_pct / leverage_avg / margin_util_pct / top_n 為 spec drift。PM 應確認：
   - (a) 是否走 PA spec amend 加 3 metric → 走 Wave 3 / Sprint 5 follow-up
   - (b) 不 amend，本 Sprint 2 keep 5 metric scope（與 spec §2.1 line 82 + ADR-0042 對齊）

   **E1 推薦 (b)**：dispatch packet §7.5 反模式 (d/e) 明文「VaR / concentration top-N 預留 config」，PA 已知為擴展點；spec scope 不重 amend。

2. **Track E test file 缺失但 lib build PASS**：Track E IMPL `src/health/domains/strategy_quality.rs` 1460 LOC 21:31 已 land，但 `tests/sprint2_track_e_strategy_quality.rs` 還沒。本 Track F 對其 unblocked（classify_aggregated 4 個 strategy_quality arm 已可呼，lib 3152 PASS）；Track E owner 補 integration test 後可獨立補測。**E2 round 1 不需待 Track E**。

3. **PA spec amend / ADR amend 不需要**：本 Track F IMPL 全 1:1 對齊 PA spec / ADR-0042 / dispatch packet；無 spec drift；無 carry-over PA task。

4. **production wire-up 走 Wave 2 後或 Sprint 5 cascade**（per Track A §7 carry-over）：
   - main.rs 接 `MetricEmitterScheduler::new(emitters=[..., risk_envelope_emitter], ...)` 時 caller 需注入：
     - `RiskEnvelopeSourceProbe` impl 接既有 risk_verdict_ledger / position_snapshot / fill_writer 計算 wrapper（既有計算邏輯，emitter 只讀）
     - 注意：emitter 不直接讀 risk_verdict_ledger / position_snapshot；走 trait 抽象（per dispatch packet §7.5 反模式 (a)）
   - TODO follow-up entry：「W-XX-Y Sprint 2 Wave 2 wire-up RiskEnvelopeSourceProbe 接既有 portfolio calculation（per `docs/agents/todo-maintenance.md` 被動等待 NDay 守則）」追蹤；本 Track F 不直接改 `TODO.md`；待 PM 收口 commit chain 時統一登記。

5. **classify_aggregated risk_envelope 5 arm threshold 由 Sprint 5 Tier 1 ArcSwap 熱更新**（per spec §4.3 規約）：本 Sprint 2 hardcode literal 對齊 spec §2.3 line 106；Sprint 5 cascade IMPL 接 V106 schema `regime_threshold_table` column 後改本 fn 內部即可，不破壞 caller signature。

6. **PG empirical dry-run 未做**：本 Track F 純 Rust IMPL / mock test；不新增 V### / 不動 SQL schema；不需 PG empirical 驗（per `feedback_v_migration_pg_dry_run` 適用範圍是 V### migration with PG reflection；本 Track F 不觸）。

## §9. Operator 下一步

1. **PM 派 E2 round 1 review**：focus on
   - 5 metric design 1:1 對齊 spec §3.2 line 405-415（含 user prompt 7 metric drift push back 接受度）
   - 5 classify helper threshold ladder 1:1 對齊 M3 design spec §2.3 line 106
   - classify_aggregated 加 risk_envelope 5 arm + count 類 (position_count) round 對齊 Track A/E 範式
   - SourceProbe trait 注入設計（emitter 只觀測，不持有 risk_verdict_ledger / position_snapshot / fill_writer mut ref）
   - cum_pnl 4 band（含 CRITICAL）vs 其他 3 metric 3 band 不對稱設計（致命層由 cum_pnl + dd 反映，避雙重 CRITICAL）
   - 8 integration test 是否端到端守 AC-1a + AC-2 + AC-4 + AC-5 + AC-7 充分

2. **A3 review 路徑**：本 Track F 改動含共用 helper（classify_aggregated 5 arm 擴展）+ 新 trait（RiskEnvelopeSourceProbe），per `feedback_impl_done_adversarial_review` 2026-05-09 應 E2 + A3 並行核驗；A3 focus on：
   - 5 metric 名稱對 V106 schema metric_name CHECK enum 對齊（CHECK 在 V106 schema spec §5；本 Track F 不動 V106 schema，但需 E2 確認 metric_name literal 不違 spec）
   - trait method extension 對 production binary 0 mock time 滲透不變式（已 nm 0 hit 守）
   - run_domain_loop merge 路徑是否避免 race（risk_envelope 沿用 Track A-E 既有 path 不退化）

3. **PM 收口 commit chain**：待 E2 round 1 + A3 PASS 後 PM 統一 commit + push（強制鏈 E1→E2→E4→QA→PM）。Wave 2 Track D + E + F 三 Track 同一 commit 或拆三 commit 由 PM 決定。

4. **PM 確認 user prompt 7 metric drift 處置**：本 report §3.2 + §8 carry-over 1 已明示 push back；PM 應 sign-off (a) 走 PA spec amend 或 (b) keep 5 metric scope。

5. **PM / PA 確認 Track E test file 缺失影響**：Track E IMPL 已 land + lib build PASS + classify_aggregated 4 arm 已可呼；Track E owner 補 integration test 是 Track E closure 邊界，不影響本 Track F 收口（per Wave 2 並行設計）。

---

**E1 IMPLEMENTATION DONE: 待 E2 round 1 review（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave2_track_f_risk_envelope.md`）**
