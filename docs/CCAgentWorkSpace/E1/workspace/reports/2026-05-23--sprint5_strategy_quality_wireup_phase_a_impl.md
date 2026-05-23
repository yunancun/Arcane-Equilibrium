# E1 IMPL — Sprint 5+ §4.3.1 StrategyQualityEmitter wire-up Phase A scaffold

- Date: 2026-05-23
- Owner: E1 (single-thread)
- Task: Sprint 5+ §4.3.1 Phase A Track E strategy_quality real PG wire-up scaffold（解 Sprint 4+ AC-1b 0 row 例外）
- Parent dispatch: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_strategy_quality_wireup_design.md`
- Parent spec: `docs/execution_plan/2026-05-23--sprint5_strategy_quality_wireup_design.md`
- Status: **IMPL DONE — awaiting E2 + A3 parallel review**
- Estimated budget: 6-8 hr; Actual: ~3 hr

## §1 任務摘要

per Sprint 4+ PM Phase 3e §4.1 item 4 揭露：6 active domain V106 30 min sample window 中 `strategy_quality` 0 row 是已知例外（main_health_emitters.rs Wave B `Track E skip per dispatch §NOT in scope`）。本 IMPL 為 Sprint 5+ §4.3.1 Phase A scaffold：

- 新 file `rust/openclaw_engine/src/health/domains/strategy_quality_probe_impl.rs`（656 LOC：3 struct + 5 trait method + 7 unit test）— `RealStrategyQualitySourceProbe` + `StrategyQualityMetricsCache` per-(strategy, symbol) HashMap 緩存。
- `rust/openclaw_engine/src/main_health_emitters.rs` 新增 Track E section（+571 LOC：5 fn + 1 big CTE join query const + 3 unit test）。
- `rust/openclaw_engine/src/main.rs` Track E caller wire-up（+34 LOC）。
- `rust/openclaw_engine/src/health/domains/mod.rs` 新增 mod 登記（2 LOC）。

Production binary 含 Track E 全 symbol；0 mock/spike 滲透；F-2 NaN/inf sanitize land；OBSERVE-4 replay guard 範式對齊既有 5 emitter wire-up。

## §2 修改清單

| 檔 | 改動 | LOC 變動 | 性質 |
|---|---|---|---|
| `rust/openclaw_engine/src/health/domains/strategy_quality_probe_impl.rs` | 新建 | 0 → **656** | 新檔 IMPL；7 unit test |
| `rust/openclaw_engine/src/main_health_emitters.rs` | 加 Track E section | 652 → **1223** | 範式擴展；3 inline test |
| `rust/openclaw_engine/src/main.rs` | 加 Track E caller wire-up block | +34 LOC（1437-1490） | caller 接線；保留既有 5 emitter wire-up |
| `rust/openclaw_engine/src/health/domains/mod.rs` | 加 `pub mod strategy_quality_probe_impl;` + MODULE_NOTE 段落 | +12 LOC | mod 登記 |

**LOC 警示**：`main_health_emitters.rs` 1223 LOC 超 §九 800 警告線（但 < 2000 hard cap）。建議 E2 review 端決定是否要切檔（候選：抽 Track E section 700 LOC 到 `main_health_emitters_strategy_quality.rs` sibling file）。本 IMPL 不切（避免 dispatch §禁忌「不擴大範圍」+ E2 風險判斷）。**push back PM 拍板**。

## §3 關鍵 diff（spec 字面對照）

### 3.1 `StrategyQualityMetricsSnapshot` struct（per spec §3.1 line 290-298）

```rust
#[derive(Debug, Clone, Copy)]
pub struct StrategyQualityMetricsSnapshot {
    pub fill_rate_intent_ratio: f64,
    pub slippage_bps_p95: f64,
    pub decision_lease_grant_rate: f64,
    pub dormant_minutes: u32,
    pub signal_count_24h: u32,
    pub last_update_ts_ms: u64,
}
```

對齊 spec line 290-298；6 field（5 metric + 1 telemetry ts）；Copy + Clone + Debug + Default。Default impl 走 spec line 380-386 fail-soft OK band（fill=1.0 / slippage=0 / lease=1.0 / dormant=0 / signal=0）。

### 3.2 `StrategyQualityMetricsCache::update_batch` F-2 sanitize（per spec §3.1 line 336-365）

```rust
pub fn update_batch(
    &mut self,
    now_ms: u64,
    snapshots: HashMap<(String, String), StrategyQualityMetricsSnapshot>,
) {
    let sanitized: HashMap<(String, String), StrategyQualityMetricsSnapshot> = snapshots
        .into_iter()
        .filter(|(key, s)| {
            let finite = s.fill_rate_intent_ratio.is_finite()
                && s.slippage_bps_p95.is_finite()
                && s.decision_lease_grant_rate.is_finite();
            if !finite {
                tracing::warn!(
                    target = "m3.health.strategy_quality",
                    strategy = %key.0, symbol = %key.1,
                    fill_rate = s.fill_rate_intent_ratio,
                    slippage = s.slippage_bps_p95,
                    lease_grant = s.decision_lease_grant_rate,
                    "StrategyQualityMetricsCache: skip NaN/inf snapshot \
                     (F-2 sanitize per spec §3.1)"
                );
            }
            finite
        })
        .collect();
    self.snapshots = sanitized;
    self.last_batch_update_ts_ms = now_ms;
}
```

對齊 PA-DRIFT-5 round 2 升級 P1 F-2 範式；3 f64 field 全 finite check；NaN/inf pair filter + fail-loud warn log + last_batch_update_ts_ms advance（caller tick 已執行語意保留）。

### 3.3 `STRATEGY_QUALITY_BATCH_QUERY` const（per spec §3.2 line 578-643）

5 CTE join：`sig_count` / `fill_count`（with slip_p95）/ `dormant` / `strategy_ctx`（DISTINCT context_id JOIN）/ `lease_grants`（state machine REGISTERED / ACTIVE）。

關鍵 spec literal 對齊：
- `engine_mode IN ('paper', 'demo', 'live_demo', 'live')` 對齊 V106 CHECK 4 值（fills/dormant 端）
- `engine_mode IN ('paper', 'demo', 'live_demo', 'live_mainnet')` 對齊 lease_transitions schema（per spec §3.2 line 621；lease_mainnet 字串保留）
- `signal_type IN ('LONG', 'SHORT')` 排除 CLOSE/HOLD
- `percentile_cont(0.95) WITHIN GROUP (ORDER BY ABS(slippage_bps))` p95 絕對 slippage
- `EXTRACT(EPOCH FROM (NOW() - MAX(ts))) / 60.0` dormant minute
- `CASE WHEN sig_n > 0 THEN fill_n / sig_n ELSE 1.0 END` fail-soft OK band
- `LEAST(COALESCE(dm.dormant_min, 0.0), 2147483647.0)::int` u32 cap 防 overflow

### 3.4 `spawn_strategy_quality_update_task` 啟動立即跑（per spec §3.2 line 483-487）

```rust
// 啟動立即跑一次 update（避免首 300s window 全 default OK band）。
if let Err(e) = run_strategy_quality_query_batch(&cache, &db_pool).await { ... }

let mut interval = tokio::time::interval(std::time::Duration::from_secs(300));
interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
// tokio interval 第 1 tick 立即觸發；用 first_tick consume 對齊「啟動立即
// 跑 + 之後 300s 等 1 個完整週期」語意。
interval.tick().await;

loop { tokio::select! { ... } }
```

對齊 spec line 483-487 設計；用 `interval.tick().await` consume 第 1 個立即 tick（tokio interval default 即時觸發第一次）避免「啟動立即跑 + 立即又跑」雙觸發。

### 3.5 main.rs caller wire-up（per spec §4.2 line 808-844）

```rust
let strategy_quality_cache = main_health_emitters::spawn_strategy_quality_scheduler(
    &db_pool,
    primary_engine_mode,
    std::sync::Arc::clone(&health_event_bus),
    &cancel,
);
if let Some(cache) = strategy_quality_cache {
    main_health_emitters::spawn_strategy_quality_update_task(
        cache,
        std::sync::Arc::clone(&db_pool),
        &cancel,
    );
    info!(...);
} else {
    info!(... "Track E strategy_quality skipped (DbPool disconnected at boot)");
}
```

**關鍵 caller 改動**：`let (portfolio_cache, _health_event_bus)` 改為 `let (portfolio_cache, health_event_bus)` — 移除 underscore 因 Track E spawn 需 Arc::clone event_bus。**這不是「順手優化」**，是 dependency requirement（health_event_bus 之前無 caller 用，現在 Track E 需要）。

## §4 治理對照

| §二 16 根原則 | Track E wire-up | 狀態 |
|---|---|---|
| 1. 單一寫入口 | 本 wire-up 0 寫操作；emitter 純讀 PG SSOT | ✅ |
| 2. 讀寫分離 | probe + update task 純 SELECT；不經 IntentProcessor | ✅ |
| 3. AI 輸出 ≠ 命令 | Track E 不產 AI 推理；純 metric emit | ✅ |
| 4. 策略不繞風控 | Track E 不改 策略邏輯；不繞風控 | ✅ |
| 5. 生存 > 利潤 | 不改交易行為；只觀測 | ✅ |
| 6. 失敗默認收縮 | fail-soft default OK band（Default impl）；PG fail cache stale | ✅ |
| 7. 學習 ≠ 改寫 Live | 不寫 strategy_engine / fill_writer；純 V106 INSERT | ✅ |
| 8. 交易可解釋 | V106 row 含 strategy + symbol + 5 metric；可重建 trace | ✅ |
| 9. 災難保護 | DEGRADED 不直接降 LAL Tier（Sprint 5+ M7 才接） | ✅ |
| 10. 認知誠實 | fail-soft default 明示；NaN/inf 必 fail-loud warn | ✅ |
| 11. Agent 最大自主 | 0 agent 接點；M3 emitter 是 observability layer | ✅ |
| 12. 持續進化 | 為 Phase B/C strategy quality empirical 提供 V106 SSOT | ✅ |
| 13. AI 成本感知 | 0 AI call；純 PG query | ✅ |
| 14. 零外部成本可運行 | PG local infra；無外部 dep | ✅ |
| 15. 多 Agent 協作 | 不破 5 Agent + Conductor 通信契約 | ✅ |
| 16. 組合級風險 | aggregate SM 0.40 ratio 反映 portfolio-level（既有 strategy_quality.rs） | ✅ |

**反模式自查（per spec §8）**：

- (a) 改既有 strategy_quality.rs 1580 LOC Sprint 2 邏輯：**NO**（只 import trait + emitter + scheduler）
- (b) 改 trading_writer / lease_writer / strategy_engine：**NO**（純 SELECT query）
- (c) 5 query 寫死高頻 30s/60s：**NO**（300s tick 對齊 emitter sample_interval）
- (d) cache unbounded growth：**NO**（25 pair upper bound；整 HashMap 覆寫不 grow）
- (e) 25 pair 寫死於 probe impl：**NO**（caller 端 `build_strategy_quality_pair_list` 從 `STRATEGY_QUALITY_STRATEGIES` × `event_consumer::SYMBOLS` 動態生成）
- (f) fail-soft default 走非 OK band：**NO**（Default impl 5 OK band 字面對齊 trait doc line 424）
- (g) update task fail silent skip：**NO**（必 `tracing::warn!` fail-loud）
- (h) signal_count_24h 走 SM observe：**NO**（既有 strategy_quality.rs line 842-857 直接寫 V106 row band=OK；本 wire-up 不改 emitter）
- (i) cache update task 串入 PaperState / 既有 IPC channel：**NO**（純 PG SELECT；獨立 update task）
- (j) main_health_emitters.rs Wave B `Track E skip` log literal 不更新：**已 update MODULE_NOTE 段落** ✓；spawn_metric_emitter_scheduler 內 `Track E skip per dispatch §NOT in scope` 註解保留作 historical context（既有 5 emitter wire-up `info!` log literal `Track E skip per Sprint 5+ wire-up` **仍存**，因該 emitter 統計只 5 emitter 不含 Track E；Track E 由獨立 `spawn_strategy_quality_scheduler` 接，log literal 自帶 `Track E StrategyQualityScheduler spawning`。E2 review 端可判斷是否要進一步合併 log 描述）

## §5 cargo test 結果

| 命令 | 結果 |
|---|---|
| `cargo build --release` | PASS（無 error；2 pre-existing warning） |
| `cargo test --release --lib strategy_quality_probe_impl` | **7 / 7 PASS** — 新 unit test |
| `cargo test --release --lib` | **3184 / 3184 PASS**（baseline 3177 + 7 new；對比 sibling baseline 3510 — 含本 7 new + sibling §4.2.1 / Wave B regression baseline） |
| `cargo test --release --bin openclaw-engine main_health_emitters` | **5 / 5 PASS**（3 new Track E + 2 既有） |
| `cargo test --release` (全 suite) | **3522 / 3522 PASS / 0 FAIL / 4 ignored**（vs `2026-05-23--sprint_4_wave_b_main_scheduler_wireup` 報告 3510 baseline + 7 probe_impl + 3 main_health_emitters + 2 PA-DRIFT-4 sibling 附帶 = 3522 ✓ 對應；ignored 從 1 incremented to 4 due to sibling integration tests skip patterns） |

## §6 binary symbol verify (AC-5)

`strings /Users/ncyu/Projects/TradeBot/srv/rust/target/release/openclaw-engine` 抓 Track E 關鍵 symbol：

- ✓ `Track E strategy_quality scheduler + StrategyQualityMetricsCache update task wired (Sprint 5+ ...`
- ✓ `Track E StrategyQualityScheduler spawning (independent scheduler; 25 (strategy, symbol) pair ...`
- ✓ `Track E StrategyQualityScheduler graceful shutdown`
- ✓ `Track E StrategyQualityScheduler OBSERVE-4 guard tripped — engine_mode='replay' forbidden`
- ✓ `StrategyQualityMetricsCache 300s update task spawning (Sprint 5+ §4.3.1 Phase A Wave C; 1 big CTE join query × 25 pair × 5 metric)`
- ✓ `StrategyQualityMetricsCache update skip: DbPool disconnected`
- ✓ `StrategyQualityMetricsCache: skip NaN/inf snapshot (F-2 sanitize per spec §3.1)` （F-2 sanitize land）
- ✓ `openclaw_engine::health::domains::strategy_quality_probe_impl` module path embedded

**0 mock / 0 spike 滲透**：`strings | grep mock|spike|StubSource` 在 strategy_quality 路徑無命中（其他模塊 pre-existing `shadow_mock_v1` / cryptopanic mock regex / spike-scope error msg 與 Track E 無關）。

## §7 不確定之處 + push back

### 7.1 LOC §九 governance 800 警告線

**`main_health_emitters.rs` 1223 LOC** 超 §九 800 警告線（但 < 2000 hard cap）。

選項 (A)：本 IMPL 不切（避免 dispatch §禁忌「不擴大範圍」；PM/E2 拍板）。  
選項 (B)：抽 Track E ~570 LOC 到 `main_health_emitters_strategy_quality.rs` sibling file，main_health_emitters.rs 回到 ~650 LOC。

**E1 推薦 (A)** 因：
- 既有 5 emitter wire-up + Track E 都是 wire-up 範式同類，分散到 sibling file 反而破壞「wire-up entry 集中」設計意圖
- 800 → 2000 之間是「警告」非「強制」；E2 review 可基於整體可讀性判斷
- 本 IMPL 純 spec literal land；切檔屬 governance refactor 應另案

需 PM/E2 拍板。

### 7.2 `interval.tick().await` 啟動立即跑語意

tokio `tokio::time::interval::tick()` default 第 1 tick 立即觸發（per docs）；本 IMPL 用：

```rust
// 啟動立即跑（手動）
let _ = run_strategy_quality_query_batch(&cache, &db_pool).await;
// interval.tick().await consume 第 1 個立即 tick 避免雙觸發
interval.tick().await;
loop { tokio::select! { ... interval.tick() ... } }
```

對齊 spec line 483-487「啟動立即跑」+ 避免實際雙觸發。E2 review 可驗此 race-window-free 設計；若 E2 認為應走 `MissedTickBehavior::Skip` + 不手動先跑，請拍板。

### 7.3 lease_transitions engine_mode 'live_mainnet' literal

per spec §3.2 line 621 + §3.2 line 982-983 query literal，`lease_transitions` 表的 engine_mode column 用 `'live_mainnet'`（區別於 fills/dormant 用 `'live'`）。本 IMPL 字面對齊 spec。

**Linux PG empirical 必驗（AC-4）**：跑 `SELECT DISTINCT engine_mode FROM learning.lease_transitions WHERE created_at > NOW() - INTERVAL '24 hours';` 確認 `live_mainnet` 是 lease_transitions 端真實 enum 值；若 PG 實際是 `live` 而非 `live_mainnet`，本 query 24h JOIN 端 lease_grants CTE 將返 0 row → `decision_lease_grant_rate` fail-soft OK band 全 1.0（不誤升但 telemetry 失能）。

### 7.4 sibling §4.2.1 BybitPrivateWs supervisor 改造 partial WIP

開工時 baseline `cargo build --release` 因 sibling session 在 §4.2.1 WIP 中（修了 `bybit_private_ws.rs` + `startup/private_ws.rs` 但 `main_health_emitters.rs` 部分 caller 未同步），出現 E0061/E0063 compile error。我**未動 sibling WIP**（per multi-session race protocol），只在我的 Track E 改動範圍內：

- `main.rs` caller wire-up 從 `_health_event_bus` 改為 `health_event_bus` — 因為 Track E 需用，這是 dependency
- `main.rs` caller wire-up 區段對齊 sibling 已加的 `&shared_ws_dropout, &shared_ws_rtt` arguments — 因為 spawn_metric_emitter_scheduler signature 已被 sibling 改

最終 binary build clean。但 sibling §4.2.1 IMPL 完成度需 PM 二次驗收（不在本 task scope）。

### 7.5 25 pair Cartesian product 含 inactive pair

per spec §6 反問 #6 + §3.1 line 374「未推入 pair → default OK band」：

- 25 pair = 5 strategy × 5 symbol cartesian product
- 某些 pair runtime 永遠 inactive：funding_arb × non-funding 對（如 DOGEUSDT）；grid_trading 部分 symbol 也可能 inactive

inactive pair → emitter sample 走 fail-soft default OK band → V106 row 仍寫（OK state；signal_count=0）。**production V106 30 min sample window 將見 125 row（25 pair × 5 metric × 1 tick）但其中部分 row 是 default OK band 不反映實際**。

E2 review + QA AC-1b 須意識：125 row 並非全部 reflect production metric；inactive pair 屬「fail-soft 設計」而非「IMPL bug」。

## §8 下游 A3 + E2 並行 review 重點

per `feedback_impl_done_adversarial_review`：高風險 IMPL（main_health_emitters.rs 共用區邊界擴大 + 5 CTE PG query 複雜度）必派 A3 + E2 並行核驗。

### 8.1 A3（quant adversarial）重點 3 點

1. **fail-soft default OK band 真偽**：25 pair 中 inactive pair 全走 default OK band；運維端是否會誤判「全策略健康」？需 QA 端 AC-1b 30 min sample 後再跑 per-strategy distinct query 驗 5 strategy distinct ≥ 5 / 5 symbol distinct ≥ 5（active emitter 必反映在 V106 row）
2. **lease_transitions JOIN context_id 真實性**：spec §9 Linux PG empirical 列 5 驗證項；A3 必跑 #1 `learning.lease_transitions.context_id` 真實非空率 > 0.5（建議 > 0.8）；若 < 0.5 則 lease_grant_rate metric 全走 fail-soft 1.0 OK band，metric 失能
3. **dormant_minutes u32 cap overflow**：query LEAST cap 2147483647（i32::MAX 約 4086 年），Rust `.max(0) as u32` 轉型；無 overflow 但若 dormant > 60 min 走 WARN ladder 是設計意圖。**A3 驗 cap 邏輯與 SM ladder 對應**

### 8.2 E2（code review）重點

1. **main_health_emitters.rs 1223 LOC 800 警告線**（§7.1 push back）— 拍板切檔 OR 維持
2. **`interval.tick().await` consume first tick 語意**（§7.2）— 拍板 race-window-free 設計
3. **fail-soft default vs OBSERVE-4 cross-cut**：cache empty + engine_mode='replay' 同時撞時，scheduler.run startup OBSERVE-4 guard Err 早於 emitter sample（不衝突），但 E2 必驗
4. **STRATEGY_QUALITY_STRATEGIES const vs 既有 sprint2_track_e_strategy_quality.rs `make_25_pairs()` "grid"/"ma"** 字串差異是設計分歧；production 端用 toml 正名（ma_crossover / grid_trading）；test fixture 是簡化字串。E2 確認 production wire-up 端用 toml 正名（本 IMPL ✓）
5. **memory.md sibling race**：本任務開工時 memory.md 1.3 MB 超 limit；E1 memory 追加會在 commit-first 流程下由 PM 統一處理

### 8.3 Phase B production deploy readiness verdict

**Phase A scaffold READY for E2 + A3 review → 通過後 PM commit → 部署 Linux runtime → QA Phase B AC-4 + AC-1b empirical**

Phase B 預期 path：
1. PM commit 5 file changes（含 mod.rs / probe_impl.rs / main_health_emitters.rs / main.rs）
2. Linux `restart_all.sh --rebuild` 觸發 engine 重建 + auto-migrate（V106 不需新 migration）
3. QA Phase B AC-4 Linux PG empirical：dry-run `STRATEGY_QUALITY_BATCH_QUERY` < 100ms + 5 column parse
4. QA AC-1b 30 min sample window：`SELECT COUNT(*) FROM learning.health_observations WHERE domain='strategy_quality' AND observed_at > NOW() - INTERVAL '30 minutes';` ≥ 125 row（5 tick × 25 pair × 5 metric）+ per-strategy distinct ≥ 5 + per-symbol distinct ≥ 5

**production trade effect = 0**；Track E 是 observability layer only；無 ML/Strategist/Executor 寫端接點。

## §9 Operator 下一步

1. **PM 派 A3 + E2 parallel review**（per feedback_impl_done_adversarial_review；本 IMPL 共用區邊界擴大 + 5 CTE PG query 複雜度 = 高風險自評）
2. **PM 拍板 §7.1 LOC governance**（main_health_emitters.rs 1223 LOC 是否切檔）
3. **PM 拍板 §7.2 + §7.3** spec literal align（lease_transitions live_mainnet 字面 + interval.tick consume first 語意）
4. **A3 + E2 round 1 review** → fix → round 2 → APPROVE → **PM commit**
5. **Linux deploy via `restart_all.sh --rebuild`**（per `reference_restart_script` + `feedback_restart_rebuild_flag_scope`）
6. **QA AC-4 + AC-1b empirical**（Linux PG real query 跑時間 + 30 min sample window row count）
7. **PM Phase B sign-off**（V106 strategy_quality domain 從 0 row → ≥125 row 解 Sprint 4+ §4.1 item 4 carry-over）

---

**E1 IMPLEMENTATION DONE**：待 E2 + A3 並行 review（report path：`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint5_strategy_quality_wireup_phase_a_impl.md`）。
