# Sprint 2 Wave 2 Track E — strategy_quality emitter IMPL

- **日期**: 2026-05-22
- **角色**: E1 (Backend Developer)
- **任務**: Sprint 2 Wave 2 Track E — strategy_quality emitter IMPL (per-strategy SM 25 instance + aggregate SM 0.40 rule)
- **HEAD**: `6f6bbea8` (`feat(sprint-2-wave2): Track D/E/F 3 並行 ALL PASS`)
- **parent spec**: `docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md` §3.2 + §3.4 + §4.4
- **dispatch packet**: `docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md` §6
- **prerequisite**: Wave 1 closure (commit `6152b01d`) + Track A scaffold land

## §0 TL;DR

- Sprint 2 Wave 2 Track E 的 strategy_quality emitter 已寫入指定路徑且 lib mod test (10/10) + integration test (10/10) + Wave 1 + Track D regression 全 PASS。
- Multi-session race 觀察: HEAD `6f6bbea8` 於本 session 開工 2 分鐘前 land Track D/E/F 並行 commit；本 session E1 IMPL 寫入後 working tree 與 HEAD diff = 0，意味著本 session 與並行 E1 instances 寫出完全等價內容，PM 已統一 commit。本 session 不 revert，per `project_multi_session_memory_race` 「commit-first / 不認識改動禁 revert」。
- Track E `signal_count_24h` telemetry-only 設計：5 field 中 4 個有 ladder band；signal_count_24h 走 fallback OK band 對齊 spec line 105 「per-strategy 30d block bootstrap」threshold pending Sprint 5。
- aggregate SM `anomaly_id` 按 target band 分隔 (aggregate__warn / aggregate__degraded / aggregate__critical)：避 same-anomaly 24h cap 阻擋 OK→WARN→DEGRADED ladder。

## §1 任務摘要

per dispatch packet §6 Track E:
- 沿用 Wave 1 scaffold (DomainEmitter / MetricSample / RollingWindowAggregator / writer / SM observe_classified / event_bus) + 獨立 `StrategyQualityScheduler` (per spec §4.4 line 638-643 明文)
- 25 instance per-(strategy, symbol) SM × 4 band metric = 100 SM 實例 + 1 aggregate SM
- aggregate rule `degraded_count / total_count > 0.40 → DEGRADED` (per spec §3.4 line 211)
- sample_interval_sec = 300s (5 min)
- `classify_aggregated` 加 4 個 strategy_quality dispatch arm (per Track C 範式)

## §2 修改清單

| 檔 | LOC | 用途 |
|---|---|---|
| `rust/openclaw_engine/src/health/domains/strategy_quality.rs` | 1489 | 新檔；StrategyQualitySample / StrategyQualityMetricRow / StrategyQualitySourceProbe / StrategyQualityEmitter / StrategyQualityScheduler + 4 classify_band helper + per-pair process + aggregate observe + 10 lib mod test |
| `rust/openclaw_engine/tests/sprint2_track_e_strategy_quality.rs` | 851 | 新檔；10 integration test 含 AC-1a / AC-2 / AC-4 / AC-5 + per_pair_independence / dormant_aggregation / aggregate_sm_0_40_rule / v106_row_carries_strategy_symbol_columns / scheduler_25x4 / scheduler_run_cancel_graceful_shutdown |
| `rust/openclaw_engine/src/health/domains/mod.rs` | +5 | 加 `pub mod strategy_quality` + MODULE_NOTE 更新 (Track D + F 已並行加入 api_latency / risk_envelope) |
| `rust/openclaw_engine/src/health/metric_emitter/mod.rs` | +28 | 在 `classify_aggregated` 加 4 個 strategy_quality dispatch arm (fill_rate_intent_ratio / slippage_bps_p95 / decision_lease_grant_rate / dormant_minutes)；對齊 Track B/C/D/F 範式 |

合計 ~2373 net new LOC。

## §3 關鍵 diff

### 3.1 `StrategyQualitySample` 5 field (per spec §3.2 SSOT)

```rust
#[derive(Debug, Clone)]
pub struct StrategyQualitySample {
    pub strategy_name: String,
    pub symbol: String,
    pub fill_rate_intent_ratio: f64,
    pub slippage_bps_p95: f64,
    pub decision_lease_grant_rate: f64,
    pub dormant_minutes: u32,
    pub signal_count_24h: u32,
}
```

- 與 dispatch prompt §2 文字版（edge_score / win_rate / drawdown_pct / sharpe_30d / fill_rate / dormant_secs / signal_count_30d）drift；以 design spec §3.2 + M3 spec line 81 + 105 為權威 SSOT。
- edge_score / win_rate / drawdown_pct / sharpe_30d 屬 multi-timeframe + cumulative PnL 範疇，per dispatch §6.5 反模式 (g) 預留 multi-timeframe per ADR-0042，**不**寫死 single-window。

### 3.2 4 classify_band helper (per M3 spec line 105 SSOT)

| metric | ladder | CRITICAL band |
|---|---|---|
| fill_rate_intent_ratio | OK > 0.80 / WARN 0.60-0.80 / DEGRADED 0.20-0.60 / CRITICAL < 0.20 | ✓ |
| slippage_bps_p95 | OK < 5 / WARN 5-10 / DEGRADED > 10 | ✗（不雙觸 cascade） |
| decision_lease_grant_rate | OK > 0.70 / WARN 0.50-0.70 / DEGRADED 0.10-0.50 / CRITICAL < 0.10 | ✓ |
| dormant_minutes (u32) | OK < 60 / WARN 60-120 / DEGRADED 120-360 / CRITICAL > 360 | ✓ |
| signal_count_24h | telemetry-only → fallback OK band | -（Sprint 5 block bootstrap） |

### 3.3 `StrategyQualityScheduler::new` 預建 100 SM + 1 aggregate SM

```rust
let mut per_pair_sms = HashMap::new();
for (strategy, symbol) in &pairs {
    for metric in ["fill_rate_intent_ratio", "slippage_bps_p95",
                   "decision_lease_grant_rate", "dormant_minutes"] {
        let key = (strategy.clone(), symbol.clone(), metric.to_string());
        per_pair_sms.insert(
            key.clone(),
            Arc::new(Mutex::new(HealthStateMachine::new(HealthDomain::StrategyQuality))),
        );
        // ... aggregator 同 key 預建
    }
}
let aggregate_sm = Arc::new(Mutex::new(HealthStateMachine::new(HealthDomain::StrategyQuality)));
```

為什麼 pre-create 而非 lazy entry：scheduler hot path sample tick 必觸所有 key（25 × 4 = 100 SM），pre-create 避 race + 性能 + 確定性都優；對比 Track A `run_domain_loop` lazy entry 是 single SM map 場景 fine。

### 3.4 aggregate SM 走 ladder：per-target-band `anomaly_id` 避 cap suppress

```rust
let aggregate_anomaly_id = match aggregate_band {
    HealthState::HealthOk => "strategy_quality__aggregate__ok",
    HealthState::HealthWarn => "strategy_quality__aggregate__warn",
    HealthState::HealthDegraded => "strategy_quality__aggregate__degraded",
    HealthState::HealthCritical => "strategy_quality__aggregate__critical",
};
```

為什麼此設計：SM `try_transition_with_cap` 對 same anomaly_id 24h cap window suppress；若 aggregate SM 走 OK→WARN→DEGRADED 全用同 anomaly_id，第一次 fire 後 24h 內 ladder 升階會被 same-anomaly cap suppress（aggregate SM 永困 WARN 不再升）。per-target-band 分隔解決，對齊 Track C `test_sprint2_ladder_database_pool` 範式（line 437-438「新 anomaly_id 避同 id cap suppress」）。

### 3.5 25 instance SM cap key (strategy, symbol) tuple 分隔 (per packet §6.5 反模式 (e))

```rust
let anomaly_id = format!(
    "strategy_quality__{}__{}__{}",
    strategy, symbol, metric_name
);
```

`test_sprint2_track_e_per_pair_independence` 連續 fire 25 pair × 同 metric_name (`fill_rate_intent_ratio`)，每 pair fire 都成功 = anomaly_id 內嵌 (strategy, symbol) 真實獨立。若 cap key 漏帶 strategy/symbol，第 2 pair 同 metric_name 會被 same-anomaly cap suppress = 嚴重觀測退化。

## §4 cargo test 結果

### Wave 2 Track E (10/10 PASS)

```
running 10 tests
test test_sprint2_cross_domain_strategy_quality_independence ... ok
test test_sprint2_ladder_strategy_quality_per_pair ... ok
test test_sprint2_track_e_aggregate_sm_0_40_rule ... ok
test test_sprint2_track_e_dormant_aggregation ... ok
test test_sprint2_track_e_per_pair_independence ... ok
test test_sprint2_track_e_spike_feature_not_active_in_default_build ... ok
test test_sprint2_track_e_v106_row_carries_strategy_symbol_columns ... ok
test test_sprint2_track_e_scheduler_per_pair_sm_count_25_x_4 ... ok
test test_sprint2_track_e_strategy_quality_in_memory_proxy ... ok
test test_sprint2_track_e_scheduler_run_cancel_graceful_shutdown ... ok

test result: ok. 10 passed; 0 failed; 0 ignored; 0 measured
```

### Wave 1 + Wave 2 Track D regression (Track A + B + C + D + E 全 PASS)

```
Track A engine_runtime:        9/9 PASS
Track B pipeline_throughput:   5/5 PASS
Track C database_pool:         8/8 PASS
Track D api_latency:           7/7 PASS
Track E strategy_quality:     10/10 PASS
合計: 39 integration test PASS
```

### lib mod test (96 health module test PASS)

```
test result: ok. 96 passed; 0 failed; 0 ignored; 0 measured; 3057 filtered out
```

10 個 strategy_quality lib mod test 包含 4 個 classify_band threshold + 2 個 into_metric_rows scenario + 2 個 emitter trait + 1 個 scheduler + 1 個 classify_aggregated arm 退化守。

### nm scan AC-5 spike default false PASS

```
$ nm rust/target/release/openclaw-engine | grep -cE "(mock_instant|tokio::time::pause|spike)"
0
```

0 spike symbol 滲透 production binary。

## §5 AC verify

| AC | Criteria | Verdict |
|---|---|---|
| AC-1a in-memory proxy | row count ≥ 5 per strategy × symbol via in-memory writer | PASS (5 tick × 3 pair × 5 metric = 75 row > 5) |
| AC-2 4-state ladder | per-(strategy, symbol) ladder fire 獨立 | PASS (test_sprint2_ladder_strategy_quality_per_pair) |
| AC-4 cross-domain | strategy_quality DEGRADED 不影響其他 5 domain | PASS (test_sprint2_cross_domain_strategy_quality_independence) |
| AC-5 spike default false | nm 0 hit | PASS |

### Track E 特殊驗

| 驗 | 守 | Verdict |
|---|---|---|
| per_pair_independence | 25 instance SM 各自獨立 cap key | PASS (25 pair × WARN fire 全成功) |
| dormant_aggregation | 4 band 邊界 1:1 對齊 spec line 105 | PASS (60/120/360/361min boundary) |
| aggregate_sm_0_40_rule | ratio > 0.40 升 DEGRADED；ladder 走 WARN 中繼 | PASS (per-target-band anomaly_id) |
| scheduler_25x4 | per_pair_sm_count = 100；aggregate init OK | PASS |
| v106_row_carries_strategy_symbol_columns | strategy_name + symbol 兩 Some | PASS |
| graceful_shutdown | cancel 2s 內 break | PASS |

## §6 治理對照

| 治理項 | 狀態 |
|---|---|
| max_retries / live_execution_allowed / execution_authority / system_mode 不可碰 | PASS (本 file 0 hit) |
| 新 SQL migration 必含 Guard A/B/C | N/A (Track E 不引 V###) |
| 跨平台路徑硬編碼禁 | PASS (0 hit /home/ncyu / /Users/[name]) |
| 新 singleton 必登記 | N/A (本 file 0 mutable singleton) |
| 文件 800 行警告 / 2000 行硬上限 | strategy_quality.rs 1489 LOC (> 800 警告 + < 2000)；test 851 LOC；metric_emitter/mod.rs 1287 LOC (> 800 警告 + < 2000) |
| 注釋默認中文 | PASS (新代碼全中文，英文僅技術詞 / SQL / Rust 符號) |
| MODULE_NOTE | PASS (strategy_quality.rs 含模塊用途 / 主要類函數 / 依賴 / 硬邊界 / 警告) |
| sub-agent IMPL DONE 走 A3+E2 對抗 review | E1 IMPL DONE → 待 E2 review (per packet §9 共用反模式 (h); 本 Sprint 2 emitter 0 GUI 改動 → A3 skip; E2 必 review) |

## §7 不確定之處

1. **Multi-session race 重複工作**：HEAD `6f6bbea8` 在本 session 開工前 2 分鐘 land；本 session E1 IMPL 寫入後 working tree 與 HEAD diff = 0；意味著本 session 與並行 E1 instances 寫出**完全等價內容**。本 session 不 revert 也不重 commit，per `project_multi_session_memory_race`「commit-first / 不認識改動禁 revert」。建議 PA / E2 確認 dispatch 是否誤派重複任務。
2. **dispatch prompt 文字版 vs design spec §3.2 drift**：prompt 提的 7 field (edge_score / win_rate / drawdown_pct / sharpe_30d / fill_rate / dormant_secs / signal_count_30d) 與 design spec 5 field 不對齊；E1 以 spec §3.2 為 SSOT 不採 prompt 文字。**建議 PA 後續 dispatch 應 1:1 引用 spec 條目**，避 prompt 文字版 over-specify drift。
3. **aggregate SM `anomaly_id` 設計 (per-target-band 分隔)**：本 IMPL 走 `aggregate__warn` / `aggregate__degraded` / `aggregate__critical` 避 same-anomaly 24h cap suppress；對齊 Track C ladder test 範式。**建議 E2 review 確認 aggregate SM 與 per-pair SM 的 anomaly_id 設計範式對齊** spec amp cap 24h-suppression 設計意圖。
4. **`signal_count_24h` telemetry-only**：本 IMPL 寫 fallback OK band；待 Sprint 5 block bootstrap re-estimate 才接 SLO threshold。spec §3.2 + M3 spec line 81 列為 metric，但 line 105 SLO table 沒列 threshold，本 IMPL 保守走 telemetry-only 路徑。
5. **main.rs scheduler wire-up**：per packet 設計 Wave 1/2 不接 main.rs；本 IMPL 走 trait probe 注入式設計。production wire-up 由 TODO follow-up 追蹤 (per `StrategyQualitySourceProbe` 警告段)。

## §8 Operator 下一步

1. **E2 round 1 review** Track E:
   - 4 classify_band helper 對齊 M3 spec line 105 SLO 邊界
   - 25 instance SM cap key (strategy, symbol) tuple 分隔不退化
   - aggregate SM 走 per-target-band anomaly_id 避 cap suppress 設計 (對比 Track C ladder 範式)
   - V106 row 帶 strategy_name + symbol 兩列正確 (writer trait + with_strategy / with_symbol builder)
   - `signal_count_24h` telemetry-only fallback band 設計可接受 (Sprint 5 block bootstrap re-estimate carry-over)
2. **E4 regression** 跑 47/47 sprint2 integration test + 96 health lib test，確認 Wave 1 + Wave 2 全 closure 不退化。
3. **QA Phase 3c real PG empirical** 跑 AC-1b (per dispatch packet §6.4)：
   ```sql
   SELECT COUNT(*) FROM learning.health_observations
     WHERE domain='strategy_quality' AND created_at > NOW() - INTERVAL '30 min';
   -- expect ≥ 1 per (strategy, symbol) pair (5min × 5 sample = 25 min cycle; 30min 容差)
   ```
   等 main.rs scheduler 接線後 Phase 3c 才能跑（per Track A §7 carry-over）。
4. **PA review prompt vs spec drift**：dispatch packet §2 文字版 `edge_score / win_rate / ...` 與 design spec §3.2 5 field 不對齊；建議 PA 後續 dispatch packet 1:1 引用 spec 條目。

## §9 file 路徑（絕對）

- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/health/domains/strategy_quality.rs` (1489 LOC)
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/tests/sprint2_track_e_strategy_quality.rs` (851 LOC)
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/health/domains/mod.rs` (+5 line)
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/health/metric_emitter/mod.rs` (+28 line)

---

E1 IMPLEMENTATION DONE: 待 E2 審查 (HEAD `6f6bbea8` 已 land Wave 2 Track D/E/F 並行 commit)
