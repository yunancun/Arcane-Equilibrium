---
report: PA design — Sprint 5+ Wave 1 §8.5 §4.3.2-6 M3 follow-up
date: 2026-05-23
author: PA
phase: Sprint 5+ Wave 1 (per Stage F §8.5 carry-over)
status: DESIGN-DONE
parent: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--stage_a_to_e_overall_acceptance.md §8.5
spec_artifacts:
  - docs/execution_plan/specs/2026-05-23--sprint5_wave1_4_3_2_ac7_m3_cold_start_bench.md
  - docs/execution_plan/specs/2026-05-23--sprint5_wave1_4_3_4_f4_correlation_real_calculator.md
  - docs/execution_plan/specs/2026-05-23--sprint5_wave1_4_3_5_6_track_b_c_real_probes.md
risk_grade: 中
---

# §1 Executive Summary

per operator 拍板「5 項全頃 dispatch」+ §8.5 carry-over：

- **§4.3.2 AC-7 cold start bench**：SSOT 校正 — 非 Linux x86_64 cross-language fixture（Sprint 1B AC-7，已 Mac aarch64 5/5 FULL PASS commit `9cf0fe82`），而是 **Sprint 2 AC-7 `MetricEmitterScheduler` first tick < 50ms wall-clock cargo bench**（per `2026-05-22--m3_metric_emitter_sprint2_design_spec.md` line 841）。3-4 hr E1。
- **§4.3.3 LOC peak 切檔**：simplified Phase B defer 建議（**本 PA design 不寫 IMPL spec**；E1 在 §4.3.4-6 IMPL 時順手 refactor）。
- **§4.3.4 F-4 correlation_avg_pairwise real calculator**：PA 拍板 lookback=1h；Pearson outer-join two-pointer；6-8 hr E1。
- **§4.3.5 Track B PipelineThroughput real probe**：4/5 metric wire-up（ipc_p99 延 Sprint 5++）；ws_client + SignalEngine 新增 `WsStats` + `SignalStats` atomic counter；8-10 hr E1。
- **§4.3.6 Track C database_pool real probe**：writer_queue 走 mpsc Sender capacity；pool_wait_p95 走自建 300-sample sliding window histogram；4-5 hr E1。

**Total 4 IMPL item**：~1175 LOC / 21-27 hr E1（**§4.3.3 LOC 切檔 defer Phase B IMPL-driven，本 design 不 dispatch IMPL spec**）。

**Push back operator prompt 措辭**：
1. AC-7 描述「Linux x86_64 Rust binding bit-perfect」與 §8.5 SSOT 不符；§8.5 item 2 真意是 Sprint 2 cold start bench 而非 Sprint 1B cross-language fixture。
2. F-4 IMPL spec 範疇與 §4.2 item 2 PortfolioStateCache update task wire-up **有重疊接口**（`update_from_pipeline_snapshot` 新加 `per_symbol_mid_prices` 參數）；派發時必標明順序「F-4 先 land；§4.2 item 2 後續對齊新 signature」。
3. Track B `current_ipc_roundtrip_ms_p99()` source 端設計獨立工作量（IPC stats infrastructure），延 Sprint 5++ 派發；本 Track B IMPL 走 OK band placeholder + TODO 追蹤。

---

# §2 §4.3.2 AC-7 cold start bench 設計（spec: ac7_m3_cold_start_bench.md）

## §2.1 SSOT 校正

| 名稱 | SSOT | 狀態 |
|---|---|---|
| Sprint 1B AC-7 cross-language fixture | spike scope spec §AC-7 + sprint2 phase 3b report §4.2 | **FULL PASS** Mac aarch64 5/5（無 Linux x86_64 deploy 依賴 — spike feature gate test，dev 端跑）|
| **Sprint 2 AC-7 cold start bench** | m3 metric emitter sprint2 design spec line 841 | **PENDING IMPL** — `benches/m3_emitter_cold_start.rs` 0 file |

§8.5 item 2 = 後者。

## §2.2 設計重點

- `MetricEmitterScheduler::new + run` first tick < 50ms wall-clock budget
- mock writer + mock emitter（不引 sysinfo / sqlx / WS / portfolio cache 避量測污染）
- `Arc<tokio::sync::Notify>` 注入 writer，writer 收到第一 row 時 `notify_one()`
- plain `fn main()` + `Instant` + 0 criterion dev-dep（對齊既有 `hot_path_baseline.rs` / `intent_processor_exposure.rs` 範式）
- Mac aarch64 + Linux x86_64 各跑 1 次 bench output

**4 AC**：
1. bench file + cargo bench --no-run clean
2. first tick < 50ms（Mac + Linux 均驗，100 iter mean + p99）
3. 0 criterion dep
4. Cargo.toml `[[bench]]` entry 新增

**LOC**：~155 LOC / **3-4 hr E1**

---

# §3 §4.3.3 LOC 切檔（Phase B defer 建議）

per `srv/CLAUDE.md` §九 + acceptance report §8.5 item 3：

| file | LOC | 警告線 800 | hard cap 2000 |
|---|---|---|---|
| `main_health_emitters.rs` | 1223 | ⚠️ over | ✓ within |
| `bybit_rest_client.rs` | 1367 | ⚠️ over | ✓ within |
| `bybit_private_ws.rs` | 1750 | ⚠️ over | ✓ within |
| `risk_envelope.rs` | 904 | ⚠️ over | ✓ within |
| `risk_envelope_probe_impl.rs` | 958 | ⚠️ over | ✓ within |

**PA simplified suggest**（不寫 IMPL spec；E1 在 §4.3.4-6 IMPL 階段順手 refactor）：

## §3.1 main_health_emitters.rs 1223 LOC

**defer Phase B IMPL-driven refactor 機會**：
- §4.3.5 Track B real probe IMPL 會在此檔加 `build_pipeline_throughput_emitter` 改造 + `RealPipelineThroughputSource` 注入
- §4.3.6 Track C real probe 同改 `build_database_pool_emitter`
- E1 在 §4.3.5/6 IMPL 時可順手拆 `track_a_engine_runtime.rs` / `track_b_pipeline.rs` / `track_c_database.rs` / `track_d_api_latency.rs` / `track_e_strategy_quality.rs` / `track_f_risk_envelope.rs` 6 submodule，每個 ~200 LOC

## §3.2 bybit_rest_client.rs 1367 LOC

defer Phase B：不在本 Wave 1 scope；建議 Sprint 5+ Wave 2 拆 `rest_orders.rs` / `rest_account.rs` / `rest_market.rs` / `rest_instruments.rs` 4 submodule

## §3.3 bybit_private_ws.rs 1750 LOC

defer Phase B：Sprint 5+ §4.2 item 1 supervisor signature 改造**時**順手拆；建議拆 `ws_connection.rs` / `ws_subscriptions.rs` / `ws_message_dispatch.rs` / `ws_supervisor.rs` 4 submodule

## §3.4 risk_envelope.rs 904 LOC + risk_envelope_probe_impl.rs 958 LOC

defer Phase B：§4.3.4 F-4 real calculator IMPL **會在 probe_impl 加 ~280 LOC**（變 ~1238 LOC）→ E1 IMPL 時必須先拆，建議拆 `risk_envelope_probe_impl.rs` → `portfolio_state_cache.rs` + `correlation_calculator.rs` + `real_probe.rs` 3 submodule

## §3.5 拍板

§4.3.3 LOC 切檔：**defer Phase B IMPL-driven**；E1 在 §4.3.4-6 IMPL 時依「自然 refactor 邊界」順手拆檔；PA 不寫獨立 IMPL spec。

---

# §4 §4.3.4 F-4 correlation real calculator 設計（spec: f4_correlation_real_calculator.md）

## §4.1 PA 拍板 lookback window

per Wave A E2 Track F round 2 對抗反問 #2 carry-over「lookback 設計（60s? 5min? 1h? 24h?）由 PA 拍板」：

**PA 拍板：lookback_window_ms = 3_600_000（1h）**

理由：
- 60s 太短 → sample 過少 noise 大
- 5min 對齊 RollingWindowAggregator 但 sample 數 < 30 不穩
- **1h 對齊 24h 1/24 採樣密度；每對 sample ≥ 30 達 Pearson 推薦下限**
- 24h 太慢，sample 過稀

per `feedback_indicator_lookahead_bias` 例外：本 metric 是觀測指標（不用於信號生成），不需 shift(1) lag returns。

## §4.2 設計重點

- `PortfolioStateCache` 新增 `per_symbol_returns_history: HashMap<String, VecDeque<(u64, f64)>>` field
- `update_from_pipeline_snapshot` 加 `per_symbol_mid_prices: &HashMap<String, f64>` 新參數（signature change）
- `correlation_avg_pairwise()` 走真實 Pearson outer-join two-pointer calculator
- F-2 NaN/inf sanitize 對齊 Wave A pattern（mid_price ≤ 0 / NaN / inf skip + warn log）
- `MIN_PAIRWISE_SAMPLES = 5` 對齊 RollingWindowAggregator 5-sample 設計
- 返 `|r| 平均`（絕對值平均；per spec §2.3 「correlation_avg_pairwise」語意）

## §4.3 Signature change 副作用

`update_from_pipeline_snapshot` 加新參數 — caller 端必同步：
1. 既有 7 unit test（line 519-595）→ 傳空 HashMap 不影響既有 4 metric 行為
2. main_health_emitters.rs PortfolioStateCache update task（**§4.2 item 2 scope**）→ 派發時 explicit 標明「F-4 先 land；§4.2 item 2 對齊新 signature」

## §4.4 4 AC

1. field 加（grep ≥ 10 hit）
2. correlation calculator real + unit test（≥ 5 test：empty / single / identical / inverse / 5-symbol pairwise）
3. NaN/inf/<=0 mid_price sanitize 對齊 F-2
4. production deploy 後 V106 `risk_envelope` domain `correlation_avg_pairwise` row MAX > 0

**LOC**：~280 LOC / **6-8 hr E1**

---

# §5 §4.3.5 Track B real probe 設計（spec: 4_3_5_6_track_b_c_real_probes.md §2）

## §5.1 設計重點

source 端 stats **全不存在**（ws_client / SignalEngine 0 counter）— 走「最小入侵」atomic counter struct 範式：

| metric | source 設計 | 工作量 |
|---|---|---|
| `current_ws_tick_rate_per_sec()` | `WsStats.total_tick_count` AtomicU64 + emitter 端 delta/elapsed 計算 | ws_client/stats.rs 新 + dispatch.rs hook |
| `current_ws_heartbeat_lag_ms()` | `WsStats.last_tick_ms` AtomicU64 | 同上 inc_tick 端寫入 |
| `current_ws_subscription_drift_count()` | `expected_topic_count() - actual_topic_count()` closure | ws_client/mod.rs `subscriptions: Vec<String>` 暴露 |
| `current_strategy_signal_rate_per_min()` | `SignalStats.signals_emitted_total` AtomicU64 + delta/elapsed 計算 | tick_pipeline/signals/stats.rs 新 + step_3_signals.rs hook |
| `current_ipc_roundtrip_ms_p99()` | **Sprint 5++ carry-over**（IPC stats infrastructure 獨立工作量）| OK band placeholder 1.0ms + TODO entry |

## §5.2 hot path 影響

- AtomicU64 `Ordering::Relaxed` → 0 sync overhead（counter 非 lock-acquire 語意）
- Option<Arc<WsStats>> field 注入 → 既有 caller 不傳 stats 時走 `None` fallback placeholder
- E5 `cargo bench --bench hot_path_baseline` 不退要 AC-4

## §5.3 4 AC（合 §4.3.6）

詳見 §6.3。

**LOC**：~375 LOC / **8-10 hr E1**

---

# §6 §4.3.6 Track C database_pool real probe 設計（spec: 4_3_5_6_track_b_c_real_probes.md §3）

## §6.1 設計重點

| metric | source 設計 | 工作量 |
|---|---|---|
| `writer_queue_probe` | tokio mpsc `Sender.capacity()` 返剩餘 permits → `MAX_CAP - capacity = depth`；market_tx 由 `Sender` 改 `Arc<Sender>`（其他 caller 不感知，Arc deref 透明） | writer_queue_stats.rs 新 + tasks.rs market_tx wrap |
| `pool_wait_p95_probe` | sqlx 0.8 未暴 → 自建 300-sample sliding window histogram；`pool_acquire_with_stats(pool, stats)` helper 包裝 `Pool.acquire()` | pool_wait_stats.rs 新 + database/pool.rs helper |

**Migration plan**：本 IMPL **不**強制全 caller 切 helper；只 market_writer / trading_writer 兩 hot-path 切換 — 保 p95 樣本量足夠 + 範圍最小化。

## §6.2 lock 時段

- `WriterQueueStats.current_depth()` 不需 lock（Sender.capacity() 自帶 atomic）
- `PoolWaitStats.p95_ms()` parking_lot::Mutex 持有 ~50us（VecDeque 拷 + sort）— 5min sample 一次接受
- `record_wait_ms` parking_lot::Mutex 持有 < 10us（push_back + pop_front）

## §6.3 AC（4 條合 §4.3.5）

| AC# | 描述 |
|---|---|
| **AC-1** | Track B 4 metric real probe wire-up（ws_tick_rate / heartbeat_lag / subscription_drift / signal_rate）；ipc_p99 維持 placeholder |
| **AC-2** | Track C 2 metric real probe wire-up（writer_queue / pool_wait_p95） |
| **AC-3** | production deploy 後 V106 row 非全 placeholder |
| **AC-4** | hot-path 0 性能退化（`cargo bench --bench hot_path_baseline` 不退）|

**LOC**：~190 LOC / **4-5 hr E1**

---

# §7 4 items combined Sprint 5+ IMPL phase split（並行派發）

## §7.1 4 並行 sub-agent 派發計劃

per `feedback_subagent_first` + `feedback_fetch_before_dispatch`：

| Wave 1 Track | Owner | spec | LOC | 估時 | 並行 |
|---|---|---|---|---|---|
| §4.3.2 AC-7 cold start bench | E1 (rust E1) | ac7_m3_cold_start_bench.md | ~155 | 3-4 hr | 並行 |
| §4.3.4 F-4 correlation real | E1 並行 | f4_correlation_real_calculator.md | ~280 | 6-8 hr | 並行 |
| §4.3.5 Track B real probe | E1 並行 | 4_3_5_6_track_b_c §2 | ~375 | 8-10 hr | 並行 |
| §4.3.6 Track C real probe | E1 並行 | 4_3_5_6_track_b_c §3 | ~190 | 4-5 hr | 並行 |

**Total**：~1000 LOC（IMPL 部分）+ ~175 LOC（test/bench）= **~1175 LOC / 21-27 hr 並行（wall-clock 1-1.5 day）**

## §7.2 並行性檢查

| Track 對 | 文件交集 | 並行可行 |
|---|---|---|
| AC-7 cold start ↔ F-4 correlation | 0 交集（benches/ vs domains/） | ✓ |
| AC-7 cold start ↔ Track B real probe | 0 交集 | ✓ |
| AC-7 cold start ↔ Track C real probe | 0 交集 | ✓ |
| F-4 correlation ↔ Track B | 0 交集（risk_envelope_probe_impl vs pipeline_throughput_probe_impl） | ✓ |
| F-4 correlation ↔ Track C | 0 交集 | ✓ |
| Track B ↔ Track C | `tasks.rs` + `main_health_emitters.rs` 兩處共改 — **MEDIUM 衝突可能** | ⚠️ |

**Track B ↔ Track C 衝突 mitigation**：
1. `tasks.rs` line 484 market_tx Arc 包裝由 Track C 負責；Track B 不碰 tasks.rs
2. `main_health_emitters.rs` 6 build_* fn 各自獨立；Track B 改 `build_pipeline_throughput_emitter`；Track C 改 `build_database_pool_emitter`；merge 不衝突（同檔不同 fn）

**Conductor 提醒**：派發 Track B + Track C sub-agent 時，**explicit 告知**「`main_health_emitters.rs` 改不同 build_* fn；不要連帶改其他 5 build_* fn」。

## §7.3 Phase B LOC refactor 順手機會

E1 在 §4.3.5 IMPL 時 main_health_emitters.rs 增 ~20 LOC → 變 ~1243 LOC（更超 800 警告線）。建議 E1 **在 §4.3.5 + §4.3.6 wire-up 同 PR** 順手拆檔（per §3.1 Phase B simplified suggest）：

- 拆 `main_health_emitters/track_a_engine_runtime.rs` ~250 LOC
- 拆 `main_health_emitters/track_b_pipeline.rs` ~250 LOC
- 拆 `main_health_emitters/track_c_database.rs` ~250 LOC
- 拆 `main_health_emitters/track_d_api_latency.rs` ~280 LOC
- 拆 `main_health_emitters/track_e_strategy_quality.rs` ~150 LOC（Stage E B-3 部分）
- 拆 `main_health_emitters/track_f_risk_envelope.rs` ~150 LOC
- 拆 `main_health_emitters/mod.rs` ~150 LOC（spawn entry + glue）

或 E1 視 IMPL 進度判斷：**若 21-27 hr 額度已用盡**，refactor 延 Sprint 5++ 獨立 sub-agent 派發。

F-4 correlation IMPL 同 — risk_envelope_probe_impl.rs +280 LOC 變 ~1238 LOC，E1 IMPL 時順手拆 `portfolio_state_cache.rs` + `correlation_calculator.rs` + `real_probe.rs` 3 submodule。

## §7.4 IMPL 順序 dependency

| dependency | from → to |
|---|---|
| §4.3.4 F-4 `update_from_pipeline_snapshot` signature change | §4.2 item 2 PortfolioStateCache update task wire-up（**另一 Sprint 5+ carry-over**）|
| §4.3.5 Track B `WsStats / SignalStats` 注入 | ws_client / SignalEngine constructor 既有 caller 兼容 |
| §4.3.6 Track C market_tx Arc 包裝 | tasks.rs 既有 caller 兼容 |

**派發指示**：
1. §4.3.4 F-4 IMPL 完成後，**update §4.2 item 2 dispatch packet** 標明「caller 必傳 `per_symbol_mid_prices: &HashMap<String, f64>`」
2. §4.3.5 Track B 派發 explicit 告知「ws_client / SignalEngine 加 Option field，既有 caller 不傳 stats 走 None fallback」
3. §4.3.6 Track C 派發 explicit 告知「market_tx 由 Sender 改 Arc<Sender>；caller 端 send! 透明」

---

# §8 Dispatch readiness verdict + E2 重點審查 5 條

## §8.1 Dispatch Readiness

**4 IMPL items DISPATCH-READY**（§4.3.3 LOC 切檔 **defer Phase B IMPL-driven，本 design 不單獨 dispatch IMPL spec**）：

| Item | Dispatch | 阻塞 |
|---|---|---|
| §4.3.2 AC-7 cold start bench | ✓ READY | 0 |
| §4.3.4 F-4 correlation real | ✓ READY | 0（§4.2 item 2 為下游同步，非阻塞 F-4 IMPL） |
| §4.3.5 Track B real probe | ✓ READY | 0 |
| §4.3.6 Track C real probe | ✓ READY | 0（與 Track B 文件交集已 mitigation §7.2） |
| §4.3.3 LOC 切檔 | DEFER Phase B | E1 在 §4.3.5/6 IMPL 時順手 refactor |

## §8.2 E2 重點審查 5 條

per `feedback_impl_done_adversarial_review` 強制 E2 + A3 並行核驗：

1. **AC-7 cold start bench 計時邊界**：`t0` 必在 scheduler `new` 前；`t1` 必在 writer notify 收到後；6 emitter spawn 順序 + mock writer notify_one 不漏；Mac+Linux p99 < 50ms 兩平台均驗
2. **F-4 algorithm 正確性**：5 對 calculator unit test 必涵蓋 empty / single / identical r=1 / inverse r=-1 / 5-symbol pairwise；驗 outer-join `pair_by_timestamp` two-pointer + Pearson `clamp(-1, 1)`
3. **F-4 NaN/inf sanitize**：mid_price ≤ 0 / NaN / inf 走 warn + skip，對齊 Wave A F-2 pattern；不可 silent 0 跳過（會變 fake-success；per `feedback_no_dead_params`）
4. **Track B AtomicU64 ordering**：tick counter / signal counter `Ordering::Relaxed`；E2 確認 hot path 0 sync overhead；E5 `hot_path_baseline` 不退 AC-4
5. **Track C mpsc Sender capacity 語意**：`Sender.capacity()` 返**剩餘 permits**（非總容量）；`MAX_CAP - capacity = in-flight depth`；E2 不要弄反（弄反會永遠返「最大容量」誤觸 DEGRADED）

## §8.3 16 根原則合規（4 IMPL items 合一）

| # | 原則 | 合規 |
|---|---|---|
| 1-9 | trading hard rails | ✓ 4 items 全 observability metric，0 trading 路徑滲透 |
| 4 | 策略不繞風控 | ✓ metric 觀測，不繞 Guardian |
| 10 | 認知誠實 | ✓ placeholder 升真實值，0 fake-success；F-2 sanitize 對齊 |
| 14 | 零外部成本可運行 | ✓ 0 新外部 dep（AtomicU64 / parking_lot / async_trait 全 existing dep）|
| 16 | 組合級風險 | ✓ F-4 correlation_avg_pairwise 是組合級風險核心指標 |

**0 BLOCKER；A 級合規**。

## §8.4 Hard boundary clean check

```
grep "execution_state|execution_authority|live_execution_allowed|decision_lease_emitted|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization.json" \
  <spec dirs + design files>
= 0 hit
```

4 IMPL items 不觸碰任何 hard boundary。

---

# §9 完成回報

1. **§4.3.2 AC-7 cold start bench** 設計 + 4 AC + Mac+Linux 跑 bench SOP：spec `2026-05-23--sprint5_wave1_4_3_2_ac7_m3_cold_start_bench.md` land；**SSOT 校正 push back** operator prompt 措辭（非 Sprint 1B cross-language fixture）
2. **§4.3.4 F-4 correlation real calculator** 設計 + PA 拍板 lookback=1h + Pearson outer-join two-pointer + 7 unit test：spec `2026-05-23--sprint5_wave1_4_3_4_f4_correlation_real_calculator.md` land；~280 LOC / 6-8 hr E1
3. **§4.3.5 + §4.3.6 Track B + Track C real probes** 設計 + ws_client/SignalEngine atomic counter + mpsc capacity + pool_wait histogram：spec `2026-05-23--sprint5_wave1_4_3_5_6_track_b_c_real_probes.md` land；Track B ~375 LOC / 8-10 hr + Track C ~190 LOC / 4-5 hr
4. **4 items combined dispatch readiness + Phase B E1 IMPL split**：4 並行 sub-agent / wall-clock 1-1.5 day / ~1175 LOC / 21-27 hr；Track B ↔ Track C 文件交集 mitigation 已 §7.2 spec；**§4.3.3 LOC 切檔 defer Phase B IMPL-driven**（本 design 不單獨 dispatch IMPL spec，E1 在 §4.3.5/6 IMPL 時順手 refactor）

## §9.1 待 PM / operator 拍板項

1. **operator 確認**：4 IMPL items 是否一波 dispatch（per operator brief 「5 項全頃 dispatch」）或分先後（如 AC-7 + F-4 一波，Track B + C 二波）
2. **PM 拍板**：F-4 IMPL 與 §4.2 item 2 wire-up 順序 — 推薦「F-4 先 land；§4.2 item 2 dispatch packet 後續 update」（per §7.4 dependency）
3. **operator 確認**：§4.3.3 LOC 切檔是否依本 PA 建議 defer Phase B IMPL-driven，或要求另派 sub-agent 獨立 refactor

## §9.2 不在本 PA design scope

- §4.3.3 LOC 切檔 IMPL spec（per operator brief「defer Phase B IMPL-driven」）
- §4.2 item 2 PortfolioStateCache update task wire-up（另一 Sprint 5+ carry-over）
- §4.4 production 監測 follow-up 4 items（屬 PA + QA threshold amend 工作）
- §8.7 PA-DRIFT-6 governance follow-up audit（屬 PA + E1 routing 至 Wave C）

---

**END OF PA design — Sprint 5+ Wave 1 §8.5 §4.3.2-6 M3 follow-up**

PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_wave1_m3_follow_up_design.md
