---
report: Sprint 4+ first Live Wave A — PA-DRIFT-5 RiskEnvelopeSourceProbe wire-up
date: 2026-05-22
author: E1 (Backend Developer, Rust)
phase: Sprint 4+ first Live carry-over §4.1 item 4 Wave A
status: IMPL DONE — 待 E2 + A3 對抗性核驗
parent dispatch:
  - PA Sprint 2 Phase 3e PM sign-off `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_pm_phase_3e_signoff.md` §4.1 item 4 + §6.1.4
  - Sprint 2 overall acceptance `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_overall_acceptance.md` §6.1.4 + §2.5 Track F E2 round 2 carry-over
  - Sprint 2 Wave 2 Track F closure `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_wave2_track_f_risk_envelope.md` §8 carry-over 4
runtime: Mac development（Rust 編譯 + tokio test）
production engine: 未碰
---

# E1 Sprint 4+ first Live PA-DRIFT-5 RiskEnvelopeSourceProbe wire-up — 2026-05-22

## §0. TL;DR

- 新 file `rust/openclaw_engine/src/health/domains/risk_envelope_probe_impl.rs`（698 LOC）：`PortfolioStateCache` 24h sliding window 緩存 + 5 SSOT calculator accessor + `RealRiskEnvelopeSourceProbe` impl + 16 inline test。
- 新 file `rust/openclaw_engine/tests/risk_envelope_probe_real_impl.rs`（408 LOC）：4 user prompt §7 scenario + 5 退化守 + 2 整合場景 = 11 integration test。
- 改 `rust/openclaw_engine/src/health/domains/mod.rs`（+6 LOC）：MODULE_NOTE 加 `risk_envelope_probe_impl` 描述 + `pub mod risk_envelope_probe_impl;`（與 PA-DRIFT-4 並行 atomic edit；無衝突）。
- 不修 `paper_state` / `mode_state` / `pipeline_types` / `risk_envelope.rs` 既有邏輯（per dispatch packet §7.5 反模式 (a)）。
- cargo test：integration **11/11** PASS + lib full **3170/0** + Track A-F regression **48/48** PASS + replay_forbidden **3/3** + spike **3/3** PASS + nm **0** hit。
- 對 user prompt 7 工作項清單作 push back 1 處（correlation_avg_pairwise 走 Wave A placeholder；real calculator 由 Wave B 接，per dispatch §7.5 反模式 (c) + E2 Track F round 2 對抗反問 #2）。

## §1. 7 工作項 LOC + 字面 diff

### (1) portfolio_cum_pnl 24h SSOT calculator

`PortfolioStateCache::cum_pnl_24h_usd()`（line 187-189）：

```rust
pub fn cum_pnl_24h_usd(&self) -> f64 {
    self.realized_pnl_history.iter().map(|&(_, p)| p).sum()
}
```

- 走 `VecDeque<(ts_ms, realized_pnl)>` 24h sliding window；`update_from_pipeline_snapshot` 端 `drain_old_fills(now_ms)` 端截斷外部樣本，accessor 純 sum。
- spec ladder band 解析度 $500 / $1500 / $2500（per M3 spec §2.3 line 106）遠大於 f64 sum 累積誤差；不引 Kahan。
- 空 history → 0.0 fail-soft → 對齊 OK band。

### (2) portfolio_max_dd 24h SSOT calculator

`PortfolioStateCache::max_dd_pct_24h()`（line 195-216）：

```rust
pub fn max_dd_pct_24h(&self) -> f64 {
    if self.equity_history.is_empty() {
        return 0.0;
    }
    let mut peak = f64::MIN;
    let mut max_dd = 0.0_f64;
    for &(_, equity) in self.equity_history.iter() {
        if equity > peak {
            peak = equity;
        }
        if peak > 0.0 {
            let dd = ((peak - equity) / peak) * 100.0;
            if dd > max_dd {
                max_dd = dd;
            }
        }
    }
    max_dd
}
```

- 走 `equity_history` peak-trough（running peak + max dd 一次掃）；24h × 5min sample = 288 樣本上限 O(n) 算 0 開銷。
- peak ≤ 0 跳過該點（負 equity 由風控其他路徑接，本 metric fail-soft 不誤升 CRITICAL）。
- 不依賴 `PaperState::peak_balance`（後者是 session-since-start 而非 24h sliding；spec 要求 24h sliding window）。

### (3) position_count_active SSOT calculator

`PortfolioStateCache::position_count_active()`（line 230-232）：

```rust
pub fn position_count_active(&self) -> u32 {
    self.latest_exposures.len() as u32
}
```

- caller 端 `update_from_pipeline_snapshot` 時 overwrite `latest_exposures` 整列；accessor 直接 `.len() as u32`。
- 對齊 trait `current_position_count_active() -> u32` 簽名（per Sprint 2 Wave 2 Track F closure）。
- 對齊 spec §3.6 + §6.2 反模式 (e) preserved (top1 not top_n)：count 計算與 top1 集中度共享 `latest_exposures` 來源。

### (4) correlation_avg_pairwise calculator — Wave A placeholder

`PortfolioStateCache::correlation_avg_pairwise()`（line 253-256）：

```rust
pub fn correlation_avg_pairwise(&self) -> f64 {
    // Wave A placeholder：實 correlation calculator 由 Wave B 接，per
    // dispatch §7.5 反模式 (c)。
    0.0
}
```

**為什麼 placeholder（push back 對 user prompt）**：

- portfolio cross-pair correlation rolling window 需「per-symbol returns time series + rolling window size + pairwise correlation matrix compute」三組件，本 Wave A 不引入新 storage struct（會碰 `PaperState` / `mode_state` 寫入路徑，破壞 dispatch packet §7.5 反模式 (a)）。
- 既有 `crate::scanner::scorer::apply_correlation_filter` 是 **scanner-level filter**（候選池容量上限），非 **portfolio-level pairwise correlation**；不可直接 reuse（功能語意不同）。
- lookback 設計（60s / 5min / 1h / 24h）由 PA 拍板（per E2 Track F round 2 對抗反問 #2 carry-over：「correlation lookback 設計」未在 spec land；本 Wave A 不擅自設計新 lookback）。
- Wave B / Sprint 5 cascade IMPL 端決定接什麼 source（既有 `panel_aggregator` cross-strategy correlation panel 或新 calculator），本 placeholder 不阻塞 emitter wire-up（trait 端有合法返值 0.0，emitter classify 走 OK band）。

### (5) concentration_top1_pct SSOT calculator

`PortfolioStateCache::concentration_top1_pct()`（line 264-279）：

```rust
pub fn concentration_top1_pct(&self) -> f64 {
    if self.latest_exposures.is_empty() {
        return 0.0;
    }
    let total: f64 = self
        .latest_exposures
        .iter()
        .map(|e| e.notional_usd.abs())
        .sum();
    if total <= 0.0 {
        return 0.0;
    }
    let top1: f64 = self
        .latest_exposures
        .iter()
        .map(|e| e.notional_usd.abs())
        .fold(0.0_f64, f64::max);
    (top1 / total) * 100.0
}
```

- `top1_notional / sum(notionals) × 100` simple ratio；對齊 spec §3.6 + §6.2 反模式 (e) preserved (top1 not top_n)。
- `notional_usd.abs()` 取絕對值：避免「多空互沖」誤判低集中度（test `test_concentration_top1_pct_uses_abs_notional` 守此 invariant）。
- empty / sum=0 → 0.0 fail-soft。

### (6) RiskEnvelopeSourceProbe trait impl

`RealRiskEnvelopeSourceProbe`（line 308-348）：

```rust
pub struct RealRiskEnvelopeSourceProbe {
    cache: Arc<Mutex<PortfolioStateCache>>,
}

impl RealRiskEnvelopeSourceProbe {
    pub fn new(cache: Arc<Mutex<PortfolioStateCache>>) -> Self {
        Self { cache }
    }

    pub fn cache_handle(&self) -> Arc<Mutex<PortfolioStateCache>> {
        Arc::clone(&self.cache)
    }
}

impl RiskEnvelopeSourceProbe for RealRiskEnvelopeSourceProbe {
    fn current_portfolio_cum_pnl_24h_usd(&self) -> f64 {
        self.cache.lock().cum_pnl_24h_usd()
    }
    fn current_portfolio_max_dd_pct(&self) -> f64 {
        self.cache.lock().max_dd_pct_24h()
    }
    fn current_position_count_active(&self) -> u32 {
        self.cache.lock().position_count_active()
    }
    fn current_correlation_avg_pairwise(&self) -> f64 {
        self.cache.lock().correlation_avg_pairwise()
    }
    fn current_concentration_top1_pct(&self) -> f64 {
        self.cache.lock().concentration_top1_pct()
    }
}
```

- `Arc<parking_lot::Mutex<PortfolioStateCache>>`：對齊 cargo workspace 既有 dep；不引 std::sync::Mutex（lock poisoning 噪音）。
- emitter 端 trait object（`Arc<dyn RiskEnvelopeSourceProbe>`）跨 tokio task 邊界（Send + Sync）；具體 `RealRiskEnvelopeSourceProbe` impl 不需 generic。
- 用 Mutex 而非 RwLock：emitter sample tick 300s 一次 + update tick 300s 一次，無「多 reader 1 writer 高頻讀」情境；Mutex 足夠且簡單。換 RwLock 是 Sprint 5 cascade hot-path 優化點。
- `cache_handle()` 暴露 Arc clone，供 E2 audit / test 驗 「 probe ↔ cache 共享同一 Arc 」（test `test_cache_handle_returns_same_arc` 守此 invariant）。

### (7) integration test

`tests/risk_envelope_probe_real_impl.rs`（408 LOC, 11 test）：

| Test | scenario | 結果 |
|---|---|---|
| `test_pa_drift_5_scenario_1_mock_fills_5_position_3_cum_pnl_sum` | 5 fill sum=8.5 + 3 倉位 → probe cum_pnl=8.5 + count=3 | PASS |
| `test_pa_drift_5_scenario_2_equity_100_90_95_max_dd_10pct` | equity 100→90→95 → probe max_dd=10% | PASS |
| `test_pa_drift_5_scenario_3_three_active_positions` | 3 active position → probe count=3 | PASS |
| `test_pa_drift_5_scenario_4_correlation_placeholder_zero` | 2 correlated pair → probe correlation=0.0（Wave A placeholder） | PASS |
| `test_24h_sliding_window_cutoff_drops_old_fills` | 25h 外舊 fill drop；只 sum 1h 前 7.0 | PASS |
| `test_24h_sliding_window_boundary_exact` | 邊界外 +1ms drop / 邊界內 +1ms 保留 | PASS |
| `test_max_dd_pct_peak_trough_across_curve` | 100→110→88→95；取 110→88 段 dd=20% 而非後段恢復 dd=13.6% | PASS |
| `test_concentration_top1_pct_sum_zero_fail_soft` | sum=0 邊界 → 返 0.0 fail-soft | PASS |
| `test_probe_multiple_lock_no_deadlock_in_one_thread` | 5 method 順序呼叫不死鎖 | PASS |
| `test_integrated_scenario_5_fills_equity_curve_3_positions` | 5 fill + 4 equity sample + 3 倉位 → 5 metric 同步對齊 | PASS |
| `test_emitter_wireup_with_real_probe` | `RiskEnvelopeEmitter::new(real_probe)` 走 trait 路徑採樣 5 metric 對齊 | PASS |

**累計 +1112 LOC**（淨增；含 1 new IMPL file 698 LOC + 1 new integration test 408 LOC + mod.rs +6 LOC）。

## §2. cargo test 結果

| Verify | Command | Result |
|---|---|---|
| Release build | `cargo build --release` | **PASS** — clean 5.67s recompile；3 pre-existing warning (unused_import / dead_code，全 PA-DRIFT-4 IMPL 帶入 + 既有 pre-existing 非本 task 引入) |
| **Integration test** | **`cargo test --release --test risk_envelope_probe_real_impl`** | **11 / 11 PASS** — 4 user prompt scenario + 5 退化守 + 2 整合場景 |
| Inline lib test | `cargo test --release --lib health::domains::risk_envelope_probe_impl::` | **16 / 16 PASS** — 5 ladder 端 reuse Track F + cache update / drain / probe trait alignment |
| Lib full | `cargo test --release --lib` | **3170 / 0** (1 ignored pre-existing)；比 Wave 2 round 2 closure 3152 多 18（本 task 16 inline + PA-DRIFT-4 並行 2 inline） |
| Lib health module | `cargo test --release --lib health::` | **105 / 105 PASS** — 比 Wave 2 round 2 closure 87 多 18 |
| Track A regression | `cargo test --release --test sprint2_track_a_engine_runtime` | **9 / 9 PASS** |
| Track B regression | `cargo test --release --test sprint2_track_b_pipeline_throughput` | **5 / 5 PASS** |
| Track C regression | `cargo test --release --test sprint2_track_c_database_pool` | **8 / 8 PASS** |
| Track D regression | `cargo test --release --test sprint2_track_d_api_latency` | **7 / 7 PASS** |
| Track E regression | `cargo test --release --test sprint2_track_e_strategy_quality` | **11 / 11 PASS** |
| Track F regression | `cargo test --release --test sprint2_track_f_risk_envelope` | **8 / 8 PASS** |
| Replay forbidden regression | `cargo test --release --test m3_emitter_replay_forbidden` | **3 / 3 PASS** |
| Spike regression | `cargo test --release --features spike --test m3_amp_cap_24h_fire` | **3 / 3 PASS** — Sprint 1A-ζ amp cap baseline 不退 |
| nm symbol scan (AC-5) | `nm target/release/openclaw-engine \| grep -cE "(mock_instant\|tokio::time::pause\|spike)"` | **0** hit — production binary 0 mock time / spike 滲透 |

**累計：lib 3170 + integration risk_envelope_probe_real_impl 11 + Track A-F 48 + replay 3 + spike 3 = 3235 PASS / 0 fail / 1 ignored**。

### §2.1 build interruption observation

並行 sub-agent PA-DRIFT-4 同時段對 `bybit_rest_client.rs` + `bybit_private_ws.rs` 修改；首次 `cargo build --release` 撞 `Instant::saturating_sub` not-found error 7 處（Rust 1.95.0 std::time::Instant 無 `saturating_sub` 方法）— 後續 cargo incremental rebuild 通過（PA-DRIFT-4 同步把 `saturating_sub` 改為 `checked_sub` + unwrap_or pattern；當前 line 156-159 + 184-187 + 222-224 + 250-253 + bybit_rest_client.rs:517+527 全用 `checked_sub`）。

對本 task scope **0 影響**：
- 不修 `bybit_rest_client.rs` / `bybit_private_ws.rs`（per profile 「多實例並行時各 E1 負責不同檔（文件互不重疊）」）
- build 通過後 my file 整段流程綠燈
- 唯一 cross-Wave atomic edit 點是 `health/domains/mod.rs`（PA-DRIFT-4 加 `pub mod api_latency_probe_impl;` + 我加 `pub mod risk_envelope_probe_impl;`）— 兩者各加一行，無 git conflict

## §3. RiskEnvelopeSourceProbe 5 method 真實 hook 對齊

| trait method | Wave A SSOT calculator | source 來源 | 完成度 |
|---|---|---|---|
| `current_portfolio_cum_pnl_24h_usd()` | `PortfolioStateCache::cum_pnl_24h_usd()` | `realized_pnl_history` 24h sliding window VecDeque（caller 端 push fill；cache 端 drain_old_fills 截斷） | **真實 hook** |
| `current_portfolio_max_dd_pct()` | `PortfolioStateCache::max_dd_pct_24h()` | `equity_history` 24h sliding window VecDeque（caller 端 push equity sample；cache 端 drain_old_equity 截斷；peak-trough 一次掃） | **真實 hook** |
| `current_position_count_active()` | `PortfolioStateCache::position_count_active()` | `latest_exposures.len()`（caller 端整列覆寫；read-only） | **真實 hook** |
| `current_correlation_avg_pairwise()` | `PortfolioStateCache::correlation_avg_pairwise()` | **Wave A placeholder 返 0.0** — real calculator 由 Wave B 接（per dispatch §7.5 反模式 (c) + E2 Track F round 2 對抗反問 #2） | **placeholder**（合法 OK band 對齊；不阻塞 wire-up） |
| `current_concentration_top1_pct()` | `PortfolioStateCache::concentration_top1_pct()` | `latest_exposures` `max(|notional|) / sum(|notional|) × 100`；abs 取值避多空互沖；sum=0 fail-soft | **真實 hook** |

**4/5 真實 hook + 1/5 placeholder**。Wave B main.rs 接 `MetricEmitterScheduler::run` 時 caller 端責任：

1. 建 `let cache = Arc::new(parking_lot::Mutex::new(PortfolioStateCache::new()));`
2. spawn periodic task（300s tick；對齊 emitter sample_interval_sec=300）走 `cache.lock().update_from_pipeline_snapshot(now_ms, equity_usd, &new_fills, exposures)`
   - `equity_usd` = `paper_state.balance + sum(positions.unrealized_pnl)`（PaperState `export_state` 自動算）
   - `new_fills` = 自上次 update 後新增的 `TimestampedFill`（caller 端走 `recent_fills.iter().rev().take_while(ts > last_update_ts_ms)`）
   - `exposures` = `positions.iter().map(|p| PositionExposure { notional_usd: p.qty.abs() * p.entry_price.abs() }).collect()`
3. 建 `let probe = RealRiskEnvelopeSourceProbe::new(Arc::clone(&cache));`
4. 注入 `MetricEmitterScheduler::new(emitters=[..., RiskEnvelopeEmitter::new(probe)], ...)`

per dispatch packet §7.5 反模式 (a) 「emitter 只觀測，不修 既有邏輯」嚴守：cache update 路徑由 caller 走，不在 `paper_state` / `mode_state` / `pipeline_types` 內部插入 hook；不修 既有 `submit_external_order` / `apply_fill` / `export_state` 邏輯。

## §4. PA-DRIFT-5 closure verdict + Wave B unblock 條件

### §4.1 PA-DRIFT-5 closure verdict

- IMPL 完整：4 真實 SSOT calculator + 1 placeholder + `RealRiskEnvelopeSourceProbe` impl + 16 inline test + 11 integration test 全 land
- spec 對齊：對齊 Sprint 2 Wave 2 Track F 既有 trait（5 method signature 不變動）；對齊 PM Phase 3e sign-off §6.1.4 「risk_verdict_ledger + position_snapshot SSOT calculator 接線」邊界（不修既有 SSOT，只新增 cache + probe wrap）
- scaffold reuse：8/8 全沿用 Track A-F scaffold（DomainEmitter / MetricSample / SourceProbe trait / classify_* / RiskEnvelopeEmitter / async tokio task pattern）
- 治理：未碰任何 hard boundary（`live_execution_allowed` / `max_retries` / `system_mode` / `execution_authority` 全未碰）/ 不接 main.rs（Wave B 工作）/ 不引 V### / 不引 spike feature / 不引 IPC
- 跨 Track 邊界：未修 `risk_envelope.rs` 既有邏輯（trait / classify / emitter / sample / DomainEmitter impl 全不動）；未修 Track A-E scaffold；未修 `paper_state` / `mode_state` / `pipeline_types` SSOT
- 對 user prompt 7 工作項偏差：4 真實 hook + 1 placeholder（correlation_avg_pairwise）；偏差由 dispatch packet §7.5 反模式 (c) + E2 Track F round 2 對抗反問 #2 治理依據明示
- adversarial review hook：4 user prompt scenario + 5 退化守 + 2 整合場景 = 11 integration test；16 inline test 守 calculator 內部正確性

### §4.2 Wave B unblock 條件

Wave B main.rs 接 `MetricEmitterScheduler::run` 前 prerequisite：
1. ✅ PA-DRIFT-5 Wave A `RealRiskEnvelopeSourceProbe` + `PortfolioStateCache` land（本 task）
2. ⏳ PA-DRIFT-4 Wave A `RealApiLatencySourceProbe` land（並行 sub-agent 進度；首次 build 撞 `saturating_sub` 已自修，當前 land 中）
3. ⏳ PA / PM 拍板 correlation_avg_pairwise lookback（per E2 Track F round 2 對抗反問 #2 carry-over）— 若 Wave B 不需 correlation 真實值，placeholder 0.0 可直接 wire-up（emitter classify 走 OK band）
4. ⏳ Wave B main.rs 接 `MetricEmitterScheduler::run` + `StrategyQualityScheduler::run`（Sprint 4+ first Live carry-over §4.1 item 2，PA 後續 dispatch）

Wave B 接 main.rs 後 AC-1b PG empirical verify 預期：30 min 視窗內 V106 row count ≥ 5 per emitter（risk_envelope domain × 5 metric × 5 sample / 300s ≥ 25 row）。

### §4.3 新 singleton 登記（per profile 「沒穩定登記表，改在 PA/E2 report + TODO follow-up」）

本 task 新增 2 個 mutable singleton：

| Singleton | Location | Owner pattern | 登記建議 |
|---|---|---|---|
| `PortfolioStateCache` | `health/domains/risk_envelope_probe_impl.rs` line 103-136 | `Arc<parking_lot::Mutex<PortfolioStateCache>>` 由 main.rs Wave B 唯一構造一次 + clone 給 update task / probe | E2 audit 確認不重複構造、不誤跨 mode race；多 mode 共享 vs 獨立由 main.rs wire-up 端決定（建議獨立：Live / Demo / Paper 各自 cache，per `feedback_env_config_independence` 三環境風控 config 獨立原則） |
| `RealRiskEnvelopeSourceProbe` | `health/domains/risk_envelope_probe_impl.rs` line 308-310 | trait object `Arc<dyn RiskEnvelopeSourceProbe>` 注入 emitter；emitter 端持 `Arc<dyn ...>` 不需第二層登記 | E2 audit 確認 trait object 注入路徑與 Track A-F 既有 pattern 對齊；無新 ownership graph |

PA / PM 後續派 follow-up TODO 條目：
- 「W-XX-Y Sprint 4+ first Live PA-DRIFT-5 closure：`PortfolioStateCache` + `RealRiskEnvelopeSourceProbe` singleton 登記到穩定登記表（per profile 硬約束 5）」

## §5. 治理對照

- **§六 Hard Boundaries**：未碰 `live_execution_allowed` / `execution_authority` / `system_mode` / `max_retries` / production engine / trading_ai production DB；未碰 authorization.json renew/approve path ✓
- **§七 Code And Docs Rules**：
  - 新代碼注釋全中文（per `feedback_chinese_only_comments` 2026-05-05）；新增 helper / struct field / trait method / test fixture comment 全中文；無 emoji ✓
  - bilingual-comment-style：本 task 為新 module + 新 test file 不觸舊中英對照塊；新 MODULE_NOTE 全中文 ✓
- **§八 Workflow**：E1 IMPL DONE → 等 E2 round 1 review + A3 對抗性核驗；不自行 commit；不派下游 sub-agent ✓
- **§九 Code Structure Guardrails**：
  - `risk_envelope_probe_impl.rs` 698 LOC（< 800 OK；< 2000 hard cap）
  - `risk_envelope_probe_real_impl.rs` 408 LOC（< 800 OK；< 2000 hard cap）
  - `health/domains/mod.rs` 64 LOC（< 800 OK；MODULE_NOTE 完整 + pub mod 兩條）
  - 不動其他 file ✓
- **§Data, Migrations, And Validation**：本 task 不新增 V###；不動 SQL schema；不觸 PG empirical reflection；emitter wire-up 後 AC-1b PG empirical verify 由 Wave B 階段做（QA Phase 3c）✓
- **cross-platform**：純 Rust 邏輯，不引平台特異 path；無 `cfg(target_os = "linux")` 分支；Mac+Linux 共通 ✓
- **AC-5 production binary 0 mock time / spike 滲透**：本 task 新 module + 5 calculator + RealProbe 全無 `cfg(feature = "spike")` gate；無 `mock_instant` / `tokio::time::pause` 引用；nm 0 hit 守住 ✓
- **`feedback_impl_done_adversarial_review`**：本 task 改動含新 mutable singleton（PortfolioStateCache）+ 新 trait impl（RealRiskEnvelopeSourceProbe）；E1 IMPL DONE 不單獨 sign-off，等 E2 round 1 + A3 對抗性核驗；E4 regression 不能取代 ✓
- **`feedback_subagent_first` + `feedback_fetch_before_dispatch`**：本 task 4-6 hr single-thread；不需派下游 sub-agent；接手前讀 Sprint 2 Wave 2 Track F closure + PA Phase 3e PM sign-off + Sprint 2 overall acceptance + PA-DRIFT-4 並行 file 確認（health/domains/mod.rs concurrent atomic edit 不衝突）✓
- **`feedback_no_dead_params`**：5 calculator 全 fail-soft（empty / sum=0 → 0.0 對齊 OK band），不誤升級 ✓

## §6. 不確定 / Carry-over

1. **correlation_avg_pairwise Wave A placeholder 0.0**：per dispatch §7.5 反模式 (c) + E2 Track F round 2 對抗反問 #2 — real calculator 由 Wave B 接 + lookback 設計由 PA 拍板。本 Wave A 不擅自設計新 lookback。**PM 應決定**：
   - (a) Wave B 接 main.rs 時走 placeholder 0.0（emitter 走 OK band）+ Sprint 5 cascade 階段補 real calculator
   - (b) Wave B 前先派 PA-CORRELATION-LOOKBACK 任務拍板 lookback + real calculator IMPL，再 Wave B
   - E1 推薦 (a)：placeholder 不破壞契約；emitter wire-up 可先綠燈，correlation real value 升級走獨立 sub-task 不阻塞 AC-1b PG empirical

2. **24h sliding window 不持久化跨 restart**：cache 內部 VecDeque restart 後從 0 起算，reach steady-state 約 24h（per `feedback_no_dead_params` fail-soft 設計）。若 PM 要求 restart 後續用既有 `paper_state_checkpoint` 持久化，本任務不接（dispatch packet §7.5 反模式 (a) 「不修既有 SSOT」邊界內）。**PM 確認**：是否在 Sprint 5 cascade IMPL 階段把 cache snapshot 加進 checkpoint？

3. **多 mode 共享 vs 獨立 cache**：本 task 提供 `PortfolioStateCache` 是 mode-agnostic struct；main.rs Wave B wire-up 時 caller 決定（Live / Demo / Paper 各自 cache vs 統一）。建議獨立（per `feedback_env_config_independence` 三環境風控 config 獨立原則）；最終 PM 拍板。

4. **`PaperState::peak_balance` vs cache `equity_history` peak**：spec 要求 24h sliding window max drawdown；本 cache 走 equity_history peak-trough（24h sliding，正確語義）；不依賴 `paper_state.peak_balance`（session-since-start，語義不符）。**E2 audit 應確認此分離正確**：若 future 接「PaperState peak 為 SSOT」，本 cache `equity_history` peak 必須改為 reuse `paper_state.peak_balance`；當前不接是因為 spec 明示 24h sliding。

5. **PG empirical dry-run 未做**：本 task 純 Rust IMPL / mock test；不新增 V### / 不動 SQL schema；不需 PG empirical 驗（per `feedback_v_migration_pg_dry_run` 適用範圍是 V### migration with PG reflection；本 task 不觸）。AC-1b PG empirical verify 由 Wave B main.rs 接 scheduler 後 QA Phase 3c 做。

6. **PA-DRIFT-4 build interruption 暴露的並行同步點**：首次 build 撞 PA-DRIFT-4 `Instant::saturating_sub` not-found error；本任務不修 bybit file（per profile multi-instance 並行邊界）。若 PA-DRIFT-4 後續 land report 有「checked_sub vs saturating_sub」設計爭議，本 task 報告作為 timeline reference 留證（§2.1）。

## §7. Operator 下一步

1. **PM 派 E2 round 1 review**：focus on
   - `PortfolioStateCache` 5 SSOT calculator 邏輯（cum_pnl sum / max_dd peak-trough / position_count len / correlation placeholder / concentration top1 abs ratio）正確性
   - `RealRiskEnvelopeSourceProbe` trait impl 對齊 `RiskEnvelopeSourceProbe` 5 method 簽名（無 drift）
   - `Arc<parking_lot::Mutex<PortfolioStateCache>>` 設計：lock 粒度 + 多 mode wire-up 邊界 + RwLock vs Mutex 取捨
   - 24h sliding window 截斷邏輯（drain_old_fills / drain_old_equity）正確性 + 邊界 (== cutoff 內 / cutoff+1ms 外)
   - correlation placeholder push back 對 user prompt 7 工作項偏差的 governance 依據（dispatch §7.5 (c) + E2 round 2 對抗反問 #2）
   - 16 inline test + 11 integration test 是否端到端守 4 user prompt scenario + 5 退化守 + 2 整合場景充分

2. **A3 review 路徑**：本 task 改動含新 mutable singleton（PortfolioStateCache）+ 新 trait impl（RealRiskEnvelopeSourceProbe），per `feedback_impl_done_adversarial_review` 2026-05-09 應 E2 + A3 並行核驗；A3 focus on：
   - cache update 路徑「不修既有 SSOT」邊界守住：grep 確認本 task 不 import `paper_state::PaperState` mut reference / 不 `apply_fill` / 不 `submit_external_order`
   - trait method extension 對 production binary 0 mock time 滲透不變式（已 nm 0 hit 守）
   - 多 mode wire-up 路徑是否避免 race（PortfolioStateCache 是 mode-agnostic；main.rs caller 端決定獨立 vs 共享）

3. **PM 收口 commit chain**：待 E2 round 1 + A3 PASS 後 PM 統一 commit + push（強制鏈 E1→E2→E4→QA→PM）。Wave A PA-DRIFT-4 + PA-DRIFT-5 兩任務同一 commit 或拆兩 commit 由 PM 決定（兩任務 health/domains/mod.rs atomic edit 無衝突）。

4. **PM 確認 correlation_avg_pairwise placeholder 處置**：本 report §3 + §6 carry-over 1 已明示 push back；PM 應 sign-off (a) Wave B 走 placeholder + Sprint 5 cascade 補 real / (b) Wave B 前先派 PA-CORRELATION-LOOKBACK 拍板。E1 推薦 (a)。

5. **PM / PA 後續派 Wave B main.rs wire-up**：本 task 已準備好 4 個真實 SSOT calculator + 1 placeholder + RealProbe；Wave B main.rs 接 `MetricEmitterScheduler::run` + cache update task 即可解鎖 AC-1b PG empirical verify（per Sprint 4+ first Live §4.1 item 2）。

6. **PM 確認新 singleton 登記**：本 report §4.3 提兩個新 singleton（PortfolioStateCache + RealRiskEnvelopeSourceProbe）；建議 PM 派 follow-up TODO 條目納入穩定登記表（per profile 硬約束 5）。

---

**E1 IMPLEMENTATION DONE: 待 E2 round 1 review + A3 對抗性核驗（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_4_pa_drift_5_risk_envelope_wireup.md`）**
