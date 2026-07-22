---
spec: Sprint 5+ StrategyQualityEmitter wire-up design
date: 2026-05-23
author: PA
phase: Sprint 5+ §4.3.1 P1 (Sprint 4+ first Live carry-over)
status: SPEC-DRAFT-V0
parent: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_first_live_carryover_pm_phase_3e_signoff.md §4.3.1
scope: design only; 不 IMPL；不改 既有 strategy_quality.rs / decision_outcomes writer / fill_writer / lease audit；不改 ADR；不 commit；不派下游 sub-agent
non-scope:
  - Rust code 實裝（E1 IMPL phase）
  - 既有 trading.fills / trading.signals / learning.lease_transitions writer 改動
  - 既有 strategy_quality.rs Track E code（Sprint 2 已 land 1580 LOC）
  - main_health_emitters.rs 既有 Track A/B/C/D/F wire-up
  - ADR-0042 / 0040 amend
  - V### 新增
---

# Sprint 5+ §4.3.1 StrategyQualityEmitter wire-up design

## §1 Context (Track E 0 row 例外)

### 1.1 Pre-state 證據（PM Phase 3e §4.1 item 4）

per Sprint 4+ PM Phase 3e sign-off (`2026-05-23--sprint_4_first_live_carryover_pm_phase_3e_signoff.md` §4.1)：

**Production V106 deploy AC-1b real PG empirical 30 min × 5 active domain × 770 row PASS**：
- `engine_runtime` 264 row（30s interval）
- `pipeline_throughput` 220 row（30s interval；placeholder）
- `api_latency` 176 row（60s interval；REST real + WS placeholder）
- `database_pool` 110 row（60s interval）
- `risk_envelope` 20 row（300s interval；real wire + Wave B no-op cache update）
- **`strategy_quality` 0 row** — 已知 Sprint 5+ wire-up scope 例外

### 1.2 0 row 根因（dispatch §NOT in scope）

per Sprint 2 Wave 2 Track E dispatch packet (`2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md` §6) + main_health_emitters.rs line 22-23/349-351/413/441：

- **Sprint 2 Wave 2 Track E IMPL（commit 6f6bbea8 + ffb7ed48 + 4d4ff99f）** 1580 LOC + 851 test LOC，內含：
  - `StrategyQualitySourceProbe` trait（5 method `current_fill_rate_intent_ratio` / `current_slippage_bps_p95` / `current_decision_lease_grant_rate` / `current_dormant_minutes` / `current_signal_count_24h`）
  - `StrategyQualityEmitter`（5 metric 採樣 + 4 ladder classify + 1 telemetry-only signal_count_24h）
  - `StrategyQualityScheduler`（獨立 scheduler；100 SM 實例 + 1 aggregate SM；OBSERVE-4 replay guard + tick guard；degraded_ratio>0.40 aggregate rule）
  - `StubSource` test impl + 12 unit test
- **main_health_emitters.rs Wave B skip per dispatch §NOT in scope** — line 413 註標「Track E skip per dispatch §NOT in scope」；line 441 log literal `"... Track E skip per Sprint 5+ wire-up)"`
- **production binary 內含 Track E code 但無 caller**；scheduler 完全未 spawn → V106 表 `strategy_quality` domain 0 row

### 1.3 與其他 5 domain wire-up 比較

| Domain | Sprint 4+ Wave B wire-up 狀態 | source probe |
|---|---|---|
| engine_runtime | real `build_engine_runtime_emitter` | std::process::id + heartbeat closure |
| pipeline_throughput | placeholder `PlaceholderPipelineThroughputSource` | 5 metric OK band 合法值 hardcode |
| database_pool | real `build_database_pool_emitter` | sqlx Pool + sysinfo Disks + writer/pool_wait placeholder closure |
| api_latency | hybrid `build_real_api_latency_probe` | REST real + WS placeholder |
| risk_envelope | real `build_risk_envelope_emitter` | `RealRiskEnvelopeSourceProbe` + `PortfolioStateCache` Wave B no-op tick |
| **strategy_quality** | **SKIP** | **本 spec 待設計** |

### 1.4 本 spec 設計目標

per Sprint 4+ Wave A PA-DRIFT-5 `RealRiskEnvelopeSourceProbe` + `PortfolioStateCache` pattern：

1. 設計 `RealStrategyQualitySourceProbe`：impl 既有 `StrategyQualitySourceProbe` trait（不改）
2. 設計 `StrategyQualityMetricsCache`：per-(strategy, symbol) cache，5 metric 各自獨立 sliding window / point snapshot
3. 設計 update task：5 min tick（對齊 emitter sample_interval=300s）；query 既有 PG SSOT 表（trading.signals / trading.fills / learning.lease_transitions）
4. 設計 main_health_emitters.rs Wave C wire-up：`build_strategy_quality_scheduler(db_pool, engine_mode_str, cancel) -> Arc<Mutex<StrategyQualityMetricsCache>>` + `spawn_strategy_quality_update_task(cache, db_pool, cancel)`
5. AC 設計（5 條對齊 Sprint 2 Track E AC 範式）
6. Sprint 5+ IMPL phase split（Phase A scaffold + Phase B real PG empirical）

---

## §2 5 metric source 識別

每 metric SSOT calculator 對映 + PG empirical 查詢規範（per `feedback_v_migration_pg_dry_run`：Linux PG empirical 必驗）。

### 2.1 fill_rate_intent_ratio (filled / signal 24h ratio)

**SSOT source**：`trading.signals` + `trading.fills`

**Why this**：per `classify_strategy_quality_fill_rate_intent_ratio` doc line 147「fill rate = filled_count / signal_count」per (strategy, symbol)。

**PG SSOT query（per (strategy, symbol)）**：
```sql
WITH signal_count AS (
    SELECT strategy_name, symbol, COUNT(*) AS sig_n
    FROM trading.signals
    WHERE ts >= NOW() - INTERVAL '24 hours'
      AND signal_type IN ('LONG', 'SHORT')  -- 排除 CLOSE/HOLD
    GROUP BY strategy_name, symbol
),
fill_count AS (
    SELECT strategy_name, symbol, COUNT(*) AS fill_n
    FROM trading.fills
    WHERE ts >= NOW() - INTERVAL '24 hours'
      AND engine_mode IN ('paper', 'demo', 'live_demo', 'live')
    GROUP BY strategy_name, symbol
)
SELECT
    COALESCE(s.strategy_name, f.strategy_name) AS strategy_name,
    COALESCE(s.symbol, f.symbol) AS symbol,
    COALESCE(f.fill_n, 0)::float / NULLIF(COALESCE(s.sig_n, 0), 0) AS fill_rate_intent_ratio
FROM signal_count s
FULL OUTER JOIN fill_count f USING (strategy_name, symbol);
```

**fail-soft 對齊**：signal_count=0 (cold start / 策略 dormant) → return 1.0（per existing trait doc line 424「probe 失敗返 OK-band 值（fill=1.0）」）；不是 0.0 避誤升 CRITICAL（fill < 0.20）。

**Boundary**：
- 1 strategy 在 24h 內 signal 0 條 = cold start → 走 1.0 OK band
- 1 strategy 24h 內 signal 100 + fill 90 → 0.90 OK band（>0.80）
- 1 strategy 24h 內 signal 100 + fill 10 → 0.10 CRITICAL band（<0.20）

### 2.2 slippage_bps_p95 (24h percentile_cont(0.95))

**SSOT source**：`trading.fills.slippage_bps`（V028 added；DOUBLE PRECISION）

**Why this**：per `classify_strategy_quality_slippage_bps_p95` doc line 175-180「slippage = (fill_price - intent_price) / intent_price * 10000 ; p95 24h window」。

**PG SSOT query（per (strategy, symbol)）**：
```sql
SELECT
    strategy_name,
    symbol,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY ABS(slippage_bps)) AS slippage_bps_p95
FROM trading.fills
WHERE ts >= NOW() - INTERVAL '24 hours'
  AND slippage_bps IS NOT NULL
  AND engine_mode IN ('paper', 'demo', 'live_demo', 'live')
  AND strategy_name IS NOT NULL
GROUP BY strategy_name, symbol;
```

**fail-soft 對齊**：fill_count=0 → return 0.0 OK band（per existing trait doc line 424「probe 失敗返 OK-band 值（slippage=0）」）。
**取 |slippage_bps|**：p95 是「絕對偏移」p95；slippage 可能是負（fill 比 intent 好），p95 計算前先取絕對值避負值拉低 p95 誤判 OK。

**Boundary**：
- fill_count=0 → 0.0 OK band
- p95=4.5 bps → OK band（<5）
- p95=7.0 bps → WARN band
- p95=12.0 bps → DEGRADED band（>10）

### 2.3 decision_lease_grant_rate (24h grant rate per strategy)

**SSOT source**：`learning.lease_transitions` (V054 added)

**Why this**：per `classify_strategy_quality_decision_lease_grant_rate` doc line 200-211「lease grant rate = granted_count / requested_count」per strategy。

**設計反問 #1**：`learning.lease_transitions` schema 是 lease state transition 而非「request 計數」表；no direct `requested_count`. Lease state machine 有 9 state（DRAFT / REGISTERED / ACTIVE / BRIDGED / FROZEN / REVOKED / EXPIRED / REJECTED / CONSUMED）。Grant 對應 `to_state IN ('ACTIVE', 'BRIDGED')`，request 對應 `to_state IN ('DRAFT', 'REGISTERED')`（state machine 起點）。

**反問結論**：lease grant rate 走 lease state machine 起點/終點計算：
- requested = `to_state IN ('REGISTERED')`（lease object 登記但尚未 ACTIVE/REJECTED）
- granted = `to_state = 'ACTIVE'`（lease 真實獲准執行）
- rejected = `to_state = 'REJECTED'`（風控拒絕）

**注意**：`learning.lease_transitions` 不含 strategy_name 欄位（schema line 226-241 verified；只有 `context_id`）。需經 `context_id` JOIN trading.signals / trading.intents 反查 strategy_name。**這是真 schema bottleneck**：

```sql
-- 反問 #1 後最簡 SSOT query：
WITH strategy_context AS (
    SELECT DISTINCT context_id, strategy_name, symbol
    FROM trading.signals
    WHERE ts >= NOW() - INTERVAL '24 hours'
      AND strategy_name IS NOT NULL
),
lease_grants AS (
    SELECT
        sc.strategy_name,
        sc.symbol,
        COUNT(*) FILTER (WHERE lt.to_state = 'REGISTERED') AS requested_n,
        COUNT(*) FILTER (WHERE lt.to_state = 'ACTIVE') AS granted_n
    FROM learning.lease_transitions lt
    JOIN strategy_context sc ON lt.context_id = sc.context_id
    WHERE lt.created_at >= NOW() - INTERVAL '24 hours'
      AND lt.engine_mode IN ('paper', 'demo', 'live_demo', 'live_mainnet')
    GROUP BY sc.strategy_name, sc.symbol
)
SELECT
    strategy_name,
    symbol,
    CASE WHEN requested_n > 0
         THEN granted_n::float / requested_n
         ELSE 1.0  -- fail-soft cold start
    END AS decision_lease_grant_rate
FROM lease_grants;
```

**Linux PG empirical 必驗**：
1. `learning.lease_transitions.context_id` 與 `trading.signals.context_id` JOIN 比例（per Sprint 1A-ζ Phase 3a learning.governance_audit_log empirical 教訓）
2. `to_state = 'REGISTERED'` 是否為「request」起點；確認 lease lifecycle SM 起點對映
3. 24h `to_state IN ('REGISTERED', 'ACTIVE', 'REJECTED')` row count per (strategy, symbol) 數量級

**fail-soft 對齊**：requested_count=0 → return 1.0 OK band。

**Boundary**：
- request=10 grant=8 → 0.80 OK band
- request=10 grant=5 → 0.50 WARN band（<0.70）
- request=10 grant=0 → 0.0 CRITICAL band（<0.10）

### 2.4 dormant_minutes (now - last_fill_at minutes)

**SSOT source**：`trading.fills.ts` (MAX per strategy, symbol)

**Why this**：per `classify_strategy_quality_dormant_minutes` doc line 226-242「dormant_minutes = 距上次 fill 的分鐘數」。

**PG SSOT query（per (strategy, symbol)）**：
```sql
SELECT
    strategy_name,
    symbol,
    EXTRACT(EPOCH FROM (NOW() - MAX(ts))) / 60.0 AS dormant_minutes
FROM trading.fills
WHERE engine_mode IN ('paper', 'demo', 'live_demo', 'live')
  AND strategy_name IS NOT NULL
GROUP BY strategy_name, symbol;
```

**fail-soft 對齊**：strategy×symbol pair 從未有 fill (永未 trade) → return 0 OK band（per existing trait doc line 424「probe 失敗返 OK-band 值（dormant=0）」）；不走 6h CRITICAL。

**注意 reframe**：u32 minutes value cap = u32::MAX min ≈ 8166 年；不會 overflow。dormant_minutes=0 = 剛 fill；dormant_minutes>360 (6h) = CRITICAL。

**Boundary**：
- 從未 fill → 0 OK band（fail-soft）
- 剛 fill → 0 OK band
- 90 min 無 fill → WARN
- 5h 無 fill → DEGRADED（>=120 min）
- 7h 無 fill → CRITICAL（>360 min）

### 2.5 signal_count_24h (24h count per strategy×symbol)

**SSOT source**：`trading.signals`

**Why this**：per `classify_strategy_quality_*` line 276「telemetry-only；spec §2.1 line 81 列為 metric 但 SLO band 待 Sprint 5 block bootstrap re-estimate」。

**PG SSOT query**：
```sql
SELECT
    strategy_name,
    symbol,
    COUNT(*) AS signal_count_24h
FROM trading.signals
WHERE ts >= NOW() - INTERVAL '24 hours'
  AND strategy_name IS NOT NULL
  AND signal_type IN ('LONG', 'SHORT')  -- 排除 CLOSE/HOLD
GROUP BY strategy_name, symbol;
```

**fail-soft 對齊**：no row → 0（telemetry only；scheduler 端不經 SM observe，直接寫 V106 row band=OK；per strategy_quality.rs line 842-857 既有邏輯）。

### 2.6 5 metric query 整合 helper

Sprint 5+ IMPL 階段 E1 可選擇兩 path：

**Path A（推薦）**：5 query 一次性合 1 big query（CTE join）→ 1 round-trip 拿 25 row × 5 metric snapshot。優點：低 query 數；缺點：query 複雜。

**Path B**：5 個獨立 query 並行 spawn 5 tokio future + try_join_all → 5 round-trip 但 parallel。優點：query 簡單可獨立 unit test；缺點：5 round-trip latency。

**PA 推薦 Path A**：5 min tick 間隔下 1 round-trip 5-10ms vs 5 round-trip 25-50ms 差異 negligible；query 複雜度由 PA spec literal 對齊保 IMPL drift risk 可控。E2 review 端可驗 query result row 與既有 GUI strategy stats 一致性。

---

## §3 RealStrategyQualitySourceProbe design

### 3.1 25 × StrategyQualityCache per-pair（PortfolioStateCache pattern 對齊）

per Wave A PA-DRIFT-5 `PortfolioStateCache` pattern（risk_envelope_probe_impl.rs line 129-141）：

```rust
// rust/openclaw_engine/src/health/domains/strategy_quality_probe_impl.rs (新)

use std::collections::HashMap;
use std::sync::Arc;
use parking_lot::Mutex;

use super::strategy_quality::StrategyQualitySourceProbe;

/// per-(strategy, symbol) 單一 metric snapshot；update task 端覆寫整 cache，
/// probe 端按需讀。
///
/// 為什麼 5 field 全 owned f64/u32 而非 sliding window:
///   - 5 metric SSOT 全為「24h window aggregate」（fill_rate / slippage_bps_p95
///     / lease_grant_rate / signal_count_24h）或「now - MAX」（dormant_minutes）；
///     PG query 端已完成 aggregation，cache 端只保最新一次 query 結果。
///   - 對比 risk_envelope `PortfolioStateCache` 持 VecDeque sliding window
///     是因為 caller 端 push 增量 fill；本 cache 走 5 min tick query 端 batch
///     pull，無增量 push 語意，不需 sliding window。
///
/// 為什麼 per-(strategy, symbol) 一個 cache instance:
///   - 對齊 既有 `StrategyQualityScheduler` 25 pair × 4 band metric = 100 SM
///     pre-create pattern（strategy_quality.rs line 609-638）。
///   - HashMap 鍵 (String, String) = (strategy_name, symbol)；probe 端 5 trait
///     method 走 HashMap.get(&(strategy, symbol)) 查到對應 cache entry。
#[derive(Debug, Clone, Copy, Default)]
pub struct StrategyQualityMetricsSnapshot {
    pub fill_rate_intent_ratio: f64,
    pub slippage_bps_p95: f64,
    pub decision_lease_grant_rate: f64,
    pub dormant_minutes: u32,
    pub signal_count_24h: u32,
    /// 最後 update wall-clock ms（telemetry / E2 audit）
    pub last_update_ts_ms: u64,
}

/// 25 instance per-(strategy, symbol) 5-metric snapshot cache。
///
/// 為什麼 HashMap 而非 Vec<(String, String, snapshot)>:
///   - probe 端 trait method `current_fill_rate_intent_ratio(strategy, symbol)`
///     需 O(1) lookup；25 pair 雖然 linear scan 也夠快，HashMap 對應既有
///     scheduler `per_pair_sms: HashMap<(strategy, symbol, metric_name), ...>`
///     pattern。
///   - update task 端 5 min tick query 整 HashMap 拍照覆寫（per 設計反問 #2
///     不採增量 update 因 PG aggregate query batch 一次拿完更快）。
pub struct StrategyQualityMetricsCache {
    /// per-(strategy, symbol) 最新 5-metric snapshot。
    /// 為什麼 (strategy, symbol) 鍵對齊 既有 scheduler:
    ///   probe 端 trait 5 method 入參 (strategy, symbol)；HashMap 鍵對齊
    ///   即可直接 lookup；scheduler 端 25 pair pre-create 對應 25 cache entry。
    snapshots: HashMap<(String, String), StrategyQualityMetricsSnapshot>,
    /// telemetry / E2 audit：最後一次 batch update 完成 wall-clock ms。
    last_batch_update_ts_ms: u64,
}

impl StrategyQualityMetricsCache {
    pub fn new() -> Self {
        Self {
            snapshots: HashMap::new(),
            last_batch_update_ts_ms: 0,
        }
    }

    /// 由 update task 端 5 min tick 完整覆寫 25 pair snapshot。
    ///
    /// 為什麼整 batch 覆寫而非增量:
    ///   - 5 PG aggregate query 端 batch 拿完 25 pair × 5 metric；caller 端
    ///     一次 update HashMap 比 25 個小 update lock 更原子。
    ///   - 對比 risk_envelope `update_from_pipeline_snapshot` 是增量 fill push
    ///     + 整列覆寫 latest_exposures；本 cache 純整列覆寫無增量語意。
    ///
    /// F-2 NaN/inf sanitize（對齊 risk_envelope F-2）:
    ///   - update task 端 query 結果若含 NaN/inf（不太可能因 PG aggregate
    ///     回傳 NULL 而非 NaN，caller convert NULL → fail-soft default）→ skip
    ///     該 pair；保留前一次 snapshot 不被污染。
    ///   - 整 batch 5 query 都成功 → 整 HashMap 替換；任一 query fail → cache
    ///     保留 stale 直到下次 tick（fail-soft；不誤升 OK band 為錯誤 placeholder）。
    pub fn update_batch(
        &mut self,
        now_ms: u64,
        snapshots: HashMap<(String, String), StrategyQualityMetricsSnapshot>,
    ) {
        // F-2 sanitize: skip pair 含 NaN/inf
        let sanitized: HashMap<_, _> = snapshots
            .into_iter()
            .filter(|(_, s)| {
                let finite = s.fill_rate_intent_ratio.is_finite()
                    && s.slippage_bps_p95.is_finite()
                    && s.decision_lease_grant_rate.is_finite();
                if !finite {
                    tracing::warn!(
                        target = "m3.health.strategy_quality",
                        "StrategyQualityMetricsCache: skip NaN/inf snapshot (F-2 sanitize)"
                    );
                }
                finite
            })
            .collect();

        self.snapshots = sanitized;
        self.last_batch_update_ts_ms = now_ms;
    }

    /// per-(strategy, symbol) lookup；fail-soft 走 default snapshot（5 OK band 值）。
    ///
    /// 為什麼 default 走 OK band:
    ///   - 對齊 既有 trait doc line 424「probe 失敗返 OK-band 值（fill=1.0 /
    ///     slippage=0 / lease=1.0 / dormant=0 / signal=0）」。
    ///   - cache 未含 pair（25 pair 中某 pair 該 tick query 不返 row；典型情境：
    ///     funding_arb dormant 全策略未 active）→ default OK band。
    pub fn snapshot_for(&self, strategy: &str, symbol: &str) -> StrategyQualityMetricsSnapshot {
        self.snapshots
            .get(&(strategy.to_string(), symbol.to_string()))
            .copied()
            .unwrap_or(StrategyQualityMetricsSnapshot {
                fill_rate_intent_ratio: 1.0,  // OK band（>0.80）
                slippage_bps_p95: 0.0,         // OK band（<5）
                decision_lease_grant_rate: 1.0, // OK band（>0.70）
                dormant_minutes: 0,             // OK band（<60）
                signal_count_24h: 0,            // telemetry-only
                last_update_ts_ms: 0,
            })
    }

    /// telemetry / E2 audit
    pub fn last_batch_update_ts_ms(&self) -> u64 {
        self.last_batch_update_ts_ms
    }

    /// telemetry / E2 audit：active pair 數（cache 內含 row）
    pub fn active_pair_count(&self) -> usize {
        self.snapshots.len()
    }
}

impl Default for StrategyQualityMetricsCache {
    fn default() -> Self {
        Self::new()
    }
}

/// production probe；包 `Arc<parking_lot::Mutex<StrategyQualityMetricsCache>>`。
/// emitter sample 端 `current_*` 呼叫 lookup cache，無 PG query 副作用。
pub struct RealStrategyQualitySourceProbe {
    cache: Arc<Mutex<StrategyQualityMetricsCache>>,
}

impl RealStrategyQualitySourceProbe {
    pub fn new(cache: Arc<Mutex<StrategyQualityMetricsCache>>) -> Self {
        Self { cache }
    }

    /// E2 audit / test helper：拿 cache handle（不 expose mut）。
    pub fn cache_handle(&self) -> Arc<Mutex<StrategyQualityMetricsCache>> {
        Arc::clone(&self.cache)
    }
}

impl StrategyQualitySourceProbe for RealStrategyQualitySourceProbe {
    fn current_fill_rate_intent_ratio(&self, strategy: &str, symbol: &str) -> f64 {
        self.cache.lock().snapshot_for(strategy, symbol).fill_rate_intent_ratio
    }

    fn current_slippage_bps_p95(&self, strategy: &str, symbol: &str) -> f64 {
        self.cache.lock().snapshot_for(strategy, symbol).slippage_bps_p95
    }

    fn current_decision_lease_grant_rate(&self, strategy: &str, symbol: &str) -> f64 {
        self.cache.lock().snapshot_for(strategy, symbol).decision_lease_grant_rate
    }

    fn current_dormant_minutes(&self, strategy: &str, symbol: &str) -> u32 {
        self.cache.lock().snapshot_for(strategy, symbol).dormant_minutes
    }

    fn current_signal_count_24h(&self, strategy: &str, symbol: &str) -> u32 {
        self.cache.lock().snapshot_for(strategy, symbol).signal_count_24h
    }
}
```

### 3.2 Update task 5 min tick（query batch）

per main_health_emitters.rs `spawn_portfolio_state_update_task` Wave B pattern（line 518-567）：

```rust
// rust/openclaw_engine/src/main_health_emitters.rs 新增

/// spawn StrategyQualityMetricsCache update task (300s tick；對齊 strategy_quality
/// emitter sample_interval_sec=300)。
///
/// 為什麼 PG query batch 而非 增量 IPC subscribe（per dispatch §禁忌「不改既有
/// 業務邏輯」）:
///   - 既有 strategy_engine / fill_writer / lease audit 寫端是 batch INSERT；
///     emitter 端只觀測，不擴 IPC channel scope（per PA-DRIFT-5 Wave B 同
///     reasoning）。
///   - 5 min tick × 5 query × 25 pair x ~ 100 ms total latency；對 PG load
///     可忽略（既有 Sprint 1A-γ M11 replay analytics 走過 50+ ms × 5+ query
///     pattern）。
///
/// 為什麼 graceful fail：5 query 任一 fail → 整 batch 不 update cache；保留
/// stale 直到下次 tick；fail-loud warn log（per F-2 sanitize 對齊）。
pub(crate) fn spawn_strategy_quality_update_task(
    cache: Arc<ParkingMutex<StrategyQualityMetricsCache>>,
    db_pool: Arc<DbPool>,
    cancel: &CancellationToken,
) {
    let task_cancel = cancel.clone();
    tokio::spawn(async move {
        info!(
            target = "m3.health.wireup",
            tick_secs = 300,
            "StrategyQualityMetricsCache 300s update task spawning"
        );

        let mut interval = tokio::time::interval(std::time::Duration::from_secs(300));
        interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);

        // 啟動立即跑一次 update（避免首 300s window 全 default OK band）
        // 為什麼立即跑：emitter sample_interval=300s；若 update task 也 300s
        //   後第一次跑，前 300s window V106 row 全 default OK band（fail-soft
        //   但 misleading）；首次 update 立即執行避此空窗。
        let _ = run_strategy_quality_query_batch(&cache, &db_pool).await;

        loop {
            tokio::select! {
                _ = interval.tick() => {
                    if let Err(e) = run_strategy_quality_query_batch(&cache, &db_pool).await {
                        tracing::warn!(
                            target = "m3.health.strategy_quality",
                            error = %e,
                            "StrategyQualityMetricsCache batch update failed; cache stale until next tick"
                        );
                    }
                }
                _ = task_cancel.cancelled() => {
                    info!(
                        target = "m3.health.wireup",
                        "StrategyQualityMetricsCache update task cancelled"
                    );
                    break;
                }
            }
        }
    });
}

/// 跑 1 batch 5 query → 整 HashMap update cache。
///
/// 為什麼分離 helper：test 端可直接呼此 fn 用 mocked PG pool（per既有
/// `RealRiskEnvelopeSourceProbe` test pattern）；spawn 端只負責 tick + cancel。
async fn run_strategy_quality_query_batch(
    cache: &Arc<ParkingMutex<StrategyQualityMetricsCache>>,
    db_pool: &Arc<DbPool>,
) -> Result<(), sqlx::Error> {
    let pool = match db_pool.get() {
        Some(p) => p.clone(),
        None => {
            tracing::warn!(
                target = "m3.health.strategy_quality",
                "StrategyQualityMetricsCache update skip: DbPool disconnected"
            );
            return Ok(());  // fail-soft；不返 Err（PG 暫斷不應 spam warn）
        }
    };

    // Path A: 1 big CTE join query 拿 25 pair × 5 metric snapshot（per §2.6 推薦）
    let rows = sqlx::query_as::<_, StrategyQualityRow>(STRATEGY_QUALITY_BATCH_QUERY)
        .fetch_all(&pool)
        .await?;

    let now_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0);

    let snapshots: HashMap<(String, String), StrategyQualityMetricsSnapshot> = rows
        .into_iter()
        .map(|r| {
            (
                (r.strategy_name, r.symbol),
                StrategyQualityMetricsSnapshot {
                    fill_rate_intent_ratio: r.fill_rate_intent_ratio,
                    slippage_bps_p95: r.slippage_bps_p95,
                    decision_lease_grant_rate: r.decision_lease_grant_rate,
                    dormant_minutes: r.dormant_minutes,
                    signal_count_24h: r.signal_count_24h,
                    last_update_ts_ms: now_ms,
                },
            )
        })
        .collect();

    cache.lock().update_batch(now_ms, snapshots);
    Ok(())
}

#[derive(sqlx::FromRow)]
struct StrategyQualityRow {
    strategy_name: String,
    symbol: String,
    fill_rate_intent_ratio: f64,
    slippage_bps_p95: f64,
    decision_lease_grant_rate: f64,
    dormant_minutes: i32,  // PG EXTRACT EPOCH return numeric -> Rust i32 conversion
    signal_count_24h: i32,
}

/// 25 pair × 5 metric batch query（per §2.6 Path A 整合 SSOT）。
///
/// CTE 結構：
///   sig_count, fill_count, fill_slippage, dormant, lease_grants 5 CTE +
///   FULL OUTER JOIN coalesce 出 25 pair × 5 metric snapshot。
const STRATEGY_QUALITY_BATCH_QUERY: &str = r#"
WITH
sig_count AS (
    SELECT strategy_name, symbol, COUNT(*)::int AS sig_n
    FROM trading.signals
    WHERE ts >= NOW() - INTERVAL '24 hours'
      AND signal_type IN ('LONG', 'SHORT')
      AND strategy_name IS NOT NULL
    GROUP BY strategy_name, symbol
),
fill_count AS (
    SELECT strategy_name, symbol,
        COUNT(*)::int AS fill_n,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY ABS(slippage_bps))
            FILTER (WHERE slippage_bps IS NOT NULL) AS slip_p95
    FROM trading.fills
    WHERE ts >= NOW() - INTERVAL '24 hours'
      AND engine_mode IN ('paper', 'demo', 'live_demo', 'live')
      AND strategy_name IS NOT NULL
    GROUP BY strategy_name, symbol
),
dormant AS (
    SELECT strategy_name, symbol,
        EXTRACT(EPOCH FROM (NOW() - MAX(ts))) / 60.0 AS dormant_min
    FROM trading.fills
    WHERE engine_mode IN ('paper', 'demo', 'live_demo', 'live')
      AND strategy_name IS NOT NULL
    GROUP BY strategy_name, symbol
),
strategy_ctx AS (
    SELECT DISTINCT context_id, strategy_name, symbol
    FROM trading.signals
    WHERE ts >= NOW() - INTERVAL '24 hours'
      AND strategy_name IS NOT NULL
),
lease_grants AS (
    SELECT
        sc.strategy_name, sc.symbol,
        COUNT(*) FILTER (WHERE lt.to_state = 'REGISTERED')::int AS requested_n,
        COUNT(*) FILTER (WHERE lt.to_state = 'ACTIVE')::int AS granted_n
    FROM learning.lease_transitions lt
    JOIN strategy_ctx sc ON lt.context_id = sc.context_id
    WHERE lt.created_at >= NOW() - INTERVAL '24 hours'
      AND lt.engine_mode IN ('paper', 'demo', 'live_demo', 'live_mainnet')
    GROUP BY sc.strategy_name, sc.symbol
)
SELECT
    COALESCE(sc.strategy_name, fc.strategy_name, dm.strategy_name, lg.strategy_name) AS strategy_name,
    COALESCE(sc.symbol, fc.symbol, dm.symbol, lg.symbol) AS symbol,
    CASE WHEN COALESCE(sc.sig_n, 0) > 0
         THEN COALESCE(fc.fill_n, 0)::float / sc.sig_n
         ELSE 1.0  -- fail-soft OK band
    END AS fill_rate_intent_ratio,
    COALESCE(fc.slip_p95, 0.0) AS slippage_bps_p95,
    CASE WHEN COALESCE(lg.requested_n, 0) > 0
         THEN lg.granted_n::float / lg.requested_n
         ELSE 1.0  -- fail-soft OK band
    END AS decision_lease_grant_rate,
    LEAST(COALESCE(dm.dormant_min, 0.0), 2147483647.0)::int AS dormant_minutes,
    COALESCE(sc.sig_n, 0) AS signal_count_24h
FROM sig_count sc
FULL OUTER JOIN fill_count fc USING (strategy_name, symbol)
FULL OUTER JOIN dormant dm USING (strategy_name, symbol)
FULL OUTER JOIN lease_grants lg USING (strategy_name, symbol)
WHERE COALESCE(sc.strategy_name, fc.strategy_name, dm.strategy_name, lg.strategy_name) IS NOT NULL;
"#;
```

### 3.3 設計反問彙整

| # | 反問 | 結論 |
|---|---|---|
| #1 | `learning.lease_transitions` 無 strategy_name 欄位，如何 per (strategy, symbol) 算 lease_grant_rate？ | 經 context_id JOIN `trading.signals` 反查；DISTINCT 提取 24h window context→strategy 對映；schema bottleneck 由 PG JOIN 解 |
| #2 | per-(strategy, symbol) cache 應 sliding window 還是 batch snapshot？ | batch snapshot；5 metric 全為 PG-side 24h aggregate query 結果；增量 push 語意不存在於本 cache scope |
| #3 | update task tick interval 是否需與 emitter sample interval 對齊？ | 對齊 300s；若 update tick 比 sample tick 慢，emitter sample 時拿不到 fresh data 走 fail-soft default OK band 失能；若 update tick 比 sample tick 快，cache 多餘 update 浪費 PG load。300s aligned 是 Pareto-optimal |
| #4 | path A (1 big CTE) vs path B (5 parallel query)？ | Path A 推薦；5 min tick × 1 round-trip 5-10ms vs 5 round-trip 25-50ms 差異 negligible；test 端可獨立 unit test query string + result row parse |
| #5 | cache empty 時 emitter 行為？ | fail-soft default OK band（fill=1.0 / slippage=0 / lease=1.0 / dormant=0 / signal=0）；不誤升 CRITICAL；對齊既有 trait doc line 424 |
| #6 | 25 pair 來源是否硬編碼？ | NO；scheduler caller 端從既有 `event_consumer::SYMBOLS` (5 symbol) × 5 strategy name list 動態生成 pair list；對齊既有 emitter `pairs: Vec<(String, String)>` ctor 參數 |
| #7 | engine_mode 4 值（paper/demo/live_demo/live）filter 是否與既有 5-gate kill 對齊？ | YES；query WHERE engine_mode IN 對齊 V106 CHECK + 既有 trading.fills/intents query 範式；replay 不在 4 值內，對齊 OBSERVE-4 invariant |

---

## §4 main_health_emitters.rs Track E wire-up

### 4.1 wire-up entry fn 設計

per Wave B `build_risk_envelope_emitter` + `spawn_portfolio_state_update_task` pattern：

```rust
// rust/openclaw_engine/src/main_health_emitters.rs 新增 Track E section

use openclaw_engine::health::domains::strategy_quality::{
    StrategyQualityEmitter, StrategyQualityScheduler,
};
use openclaw_engine::health::domains::strategy_quality_probe_impl::{
    RealStrategyQualitySourceProbe, StrategyQualityMetricsCache,
};

// ============================================================
// Track E strategy_quality scheduler — RealStrategyQualitySourceProbe + cache
// ============================================================

/// 構造 25 (strategy, symbol) pair list（per 既有 SYMBOLS 5 × 5 strategy）。
///
/// 為什麼此設計:
///   - 對齊既有 event_consumer::SYMBOLS 5 symbol literal（per main_pipelines.rs
///     TickPipeline 構造端 SYMBOLS 注入 KlineManager）。
///   - 5 strategy literal hardcode 對齊 strategy_params_*.toml 5 [section]：
///     ma_crossover / bb_reversion / bb_breakout / grid_trading / funding_arb。
///   - 25 pair 是 (5 strategy × 5 symbol) cartesian product；某些 pair runtime
///     永遠 inactive（funding_arb × non-funding symbol；emitter 端 fail-soft 走
///     default OK band）。
fn build_strategy_quality_pair_list() -> Vec<(String, String)> {
    const STRATEGIES: &[&str] = &[
        "ma_crossover", "bb_reversion", "bb_breakout", "grid_trading", "funding_arb",
    ];
    let mut pairs = Vec::with_capacity(25);
    for strategy in STRATEGIES {
        for symbol in openclaw_engine::event_consumer::SYMBOLS {
            pairs.push((strategy.to_string(), symbol.to_string()));
        }
    }
    pairs
}

/// 構造 Track E `StrategyQualityScheduler` + 共享 `StrategyQualityMetricsCache` Arc 句柄。
///
/// 返 (scheduler, cache_handle)：caller 同時 spawn scheduler.run + cache update task。
fn build_strategy_quality_scheduler(
    db_pool: &Arc<DbPool>,
    engine_mode: EngineModeProvider,
    event_bus: Arc<HealthEventBus>,
) -> Option<(
    StrategyQualityScheduler,
    Arc<ParkingMutex<StrategyQualityMetricsCache>>,
)> {
    let pg_pool = match db_pool.get() {
        Some(p) => p.clone(),
        None => {
            warn!(
                target = "m3.health.wireup",
                "Track E StrategyQualityScheduler skipped: DbPool disconnected at boot"
            );
            return None;
        }
    };
    let writer: Arc<dyn HealthObservationWriter> =
        Arc::new(PgHealthObservationWriter::new(pg_pool));

    let cache = Arc::new(ParkingMutex::new(StrategyQualityMetricsCache::new()));
    let probe = RealStrategyQualitySourceProbe::new(Arc::clone(&cache));
    let pairs = build_strategy_quality_pair_list();  // 25 pair
    let emitter = StrategyQualityEmitter::new(probe, pairs);
    let scheduler = StrategyQualityScheduler::new(emitter, writer, event_bus, engine_mode);

    Some((scheduler, cache))
}

/// Wave C wire-up entry：spawn `StrategyQualityScheduler.run` + cache update task。
///
/// 為什麼分離 fn 而非合入 `spawn_metric_emitter_scheduler`:
///   - `StrategyQualityScheduler` 是 6 domain 中唯一獨立 scheduler（per spec
///     §4.4 line 638-643；strategy_quality.rs line 542-556）；不沿用
///     `MetricEmitterScheduler::run_domain_loop` 因 25 instance per-(strategy,
///     symbol) SM 與 single-SM 路徑 hash key shape 不同。
///   - main.rs caller 端兩 spawn entry：原 5 emitter 走 `spawn_metric_emitter_scheduler`，
///     Track E 走本 fn；對齊既有 5 emitter wire-up 後 + 加一 entry 不破 5 emitter scope。
///
/// 為什麼複用 event_bus（caller 端傳入）:
///   - 6 domain 共享 1 event_bus（Sprint 5+ cascade subscriber 預埋）；
///     `spawn_metric_emitter_scheduler` 返 (cache, event_bus_arc)；本 fn 接同 event_bus
///     避免分裂 cascade subscribe 兩條鏈。
///
/// OBSERVE-4 propagate Err 不 swallow（per既有 `spawn_metric_emitter_scheduler` 範式）:
///   - scheduler.run 啟動時 OBSERVE-4 guard 撞 replay → Err(ReplaySubprocessForbidden)
///     log error 不 panic；caller 端 tokio task 自然結束。
pub(crate) fn spawn_strategy_quality_scheduler(
    db_pool: &Arc<DbPool>,
    engine_mode_str: &'static str,
    event_bus: Arc<HealthEventBus>,
    cancel: &CancellationToken,
) -> Option<Arc<ParkingMutex<StrategyQualityMetricsCache>>> {
    let mode_str = engine_mode_str.to_string();
    let engine_mode: EngineModeProvider = Arc::new(move || mode_str.clone());

    let (scheduler, cache) =
        build_strategy_quality_scheduler(db_pool, engine_mode, event_bus)?;

    let scheduler_cancel = cancel.clone();
    let mode_for_log = engine_mode_str.to_string();
    tokio::spawn(async move {
        info!(
            target = "m3.health.wireup",
            engine_mode = %mode_for_log,
            domain = "strategy_quality",
            pair_count = 25,
            "Track E StrategyQualityScheduler spawning (independent scheduler; \
             25 (strategy, symbol) pair × 4 band metric SM + 1 telemetry signal_count + 1 aggregate SM)"
        );
        match scheduler.run(scheduler_cancel).await {
            Ok(()) => {
                info!(
                    target = "m3.health.wireup",
                    "Track E StrategyQualityScheduler graceful shutdown"
                );
            }
            Err(M3Error::ReplaySubprocessForbidden) => {
                tracing::error!(
                    target = "m3.health.wireup",
                    "Track E StrategyQualityScheduler OBSERVE-4 guard tripped — \
                     engine_mode='replay' forbidden"
                );
            }
            Err(e) => {
                tracing::error!(
                    target = "m3.health.wireup",
                    error = %e,
                    "Track E StrategyQualityScheduler unexpected error"
                );
            }
        }
    });

    Some(cache)
}
```

### 4.2 main.rs caller 端接線

per main.rs Wave B line 1440-1457 既有 wire-up 範式 + 1 hr 增量改動：

```rust
// main.rs 改動 — Wave B wire-up block 之後直接加 Track E wire-up

let (portfolio_cache, health_event_bus) =
    main_health_emitters::spawn_metric_emitter_scheduler(
        &db_pool,
        cfg_snap_for_pool.database.pool_max_connections,
        &data_dir_mount,
        &shared_client,
        primary_engine_mode,
        &cancel,
    );
drop(cfg_snap_for_pool);
main_health_emitters::spawn_portfolio_state_update_task(portfolio_cache, &cancel);

// === Wave C Track E wire-up（新增 ~10 行）===
let strategy_quality_cache = main_health_emitters::spawn_strategy_quality_scheduler(
    &db_pool,
    primary_engine_mode,
    Arc::clone(&health_event_bus),
    &cancel,
);
if let Some(cache) = strategy_quality_cache {
    main_health_emitters::spawn_strategy_quality_update_task(cache, Arc::clone(&db_pool), &cancel);
    info!(
        target = "m3.health.wireup",
        engine_mode = primary_engine_mode,
        "Track E strategy_quality scheduler + StrategyQualityMetricsCache update task wired \
         (Sprint 5+ Wave C; 25 pair × 5 metric SSOT calculator)"
    );
} else {
    info!(
        target = "m3.health.wireup",
        "Track E strategy_quality skipped (DbPool disconnected at boot)"
    );
}
```

### 4.3 main_health_emitters.rs 既有 log literal update

per main_health_emitters.rs line 441 既有 log `"... Track E skip per Sprint 5+ wire-up)"`：

Wave C 端 IMPL 必同步改寫為 `"... Track E independent scheduler wire-up via spawn_strategy_quality_scheduler)"`（避 log drift；E2 review 必查）。

---

## §5 AC（Acceptance Criteria）

對齊 Sprint 2 Track E AC（dispatch packet §6.4）+ Sprint 4+ Wave A/B AC-1a/AC-1b 拆分契約：

### AC-1a — StrategyQualityMetricsCache in-memory empirical（Wave C scaffold sign-off）

**Test 名**：`tests/sprint5_wave_c_strategy_quality_wireup.rs::test_strategy_quality_cache_in_memory_proxy`

**Pass criteria**：
- 構造 `StrategyQualityMetricsCache` + 推入 25 pair × 5 metric snapshot 模擬資料
- `RealStrategyQualitySourceProbe` 5 trait method × 25 pair × 5 metric = 125 lookup 全 match 推入值
- Empty cache lookup 走 fail-soft default OK band（fill=1.0 / slippage=0 / lease=1.0 / dormant=0 / signal=0）
- F-2 NaN/inf snapshot skip + warn log
- 不需 real PG / 不需 main.rs scheduler 接線

`cargo test --release test_strategy_quality_cache_in_memory_proxy` PASS

### AC-1b — strategy_quality real PG empirical (Wave C 接線後)

**Test 路徑**：Phase 3c QA Linux PG 跑

**Pass criteria**：
- production engine restart 後 30 min sample window
- V106 query `SELECT COUNT(*) FROM learning.health_observations WHERE domain='strategy_quality' AND observed_at > NOW() - INTERVAL '30 minutes'`
- 期望：`COUNT(*) ≥ 25 pair × 5 metric × 1 tick = 125 row`（300s interval / 30 min = 6 tick → 150 row 期望；容差 ≥125 = 5 tick）
- per strategy distinct count ≥ 5（5 strategy 全 emit）
- per symbol distinct count ≥ 5（5 symbol 全 emit）

### AC-2 — 4-state ladder + per-(strategy, symbol) SM 升級驗證

**Test 名**：`tests/sprint5_wave_c_strategy_quality_wireup.rs::test_per_strategy_sm_observe_classified_fire`

**Pass criteria**：
- 沿用 Sprint 2 Track E `tests/sprint2_track_e_strategy_quality.rs` 既有 SM observe 測試
- Wave C 增量驗：cache 推 fill_rate=0.1 (CRITICAL band) → SM observe_classified → V106 row state='CRITICAL'；對齊既有 sprint2_track_e_strategy_quality_in_memory_proxy

### AC-3 — aggregate SM 0.40 threshold rule

**Test 名**：`tests/sprint5_wave_c_strategy_quality_wireup.rs::test_aggregate_sm_degraded_ratio_fire`

**Pass criteria**：
- 沿用 Sprint 2 Track E aggregate test
- Wave C 增量驗：25 pair 中 11 pair (44%) 升 DEGRADED → aggregate SM 升 DEGRADED；10 pair (40%) 維持 OK
- 對齊既有 strategy_quality.rs aggregate rule

### AC-4 — PG query string + result row parse

**Test 名**：`tests/sprint5_wave_c_strategy_quality_wireup.rs::test_strategy_quality_batch_query_parse`

**Pass criteria**：
- Mac mock pytest 不可（per V### dry-run mandatory）
- 改 Linux PG empirical dry-run：
  ```bash
  ssh trade-core "PGPASSWORD=... psql -U trading_ai -h /var/run/postgresql -d trading_ai \
    -c \"<STRATEGY_QUALITY_BATCH_QUERY literal>\""
  ```
- 預期：返 0-25 row（取決於 24h window 內 strategy 活躍程度）
- 5 column 名 + type 對齊 `StrategyQualityRow` sqlx::FromRow derive
- query 跑時間 < 100ms（per PG 300s tick cadence 容差）

### AC-5 — spike default false / production binary 0 mock 滲透

**Test**：cargo build --release; `nm target/release/openclaw_engine | grep -i "strategy_quality.*mock\|spike\|StubSource" | wc -l` 預期 0

### AC-6 — OBSERVE-4 replay subprocess emit forbidden（cross-Wave invariant）

**Test 名**：`tests/sprint5_wave_c_strategy_quality_wireup.rs::test_track_e_observe_4_replay_forbidden`

**Pass criteria**：
- 沿用既有 OBSERVE-4 test pattern（per strategy_quality.rs line 706-708 + 728-737）
- engine_mode_str="replay" 啟動 → scheduler.run 即時 Err(ReplaySubprocessForbidden)；main.rs caller 收到 Err log 但不 panic

---

## §6 Sprint 5+ IMPL phase split

### 6.1 Phase A — scaffold（E1 IMPL + E2 review；6-8 hr）

| 項目 | Owner | Est | 依賴 |
|---|---|---|---|
| 1. `rust/openclaw_engine/src/health/domains/strategy_quality_probe_impl.rs` 新建 200 LOC | E1 | 3 hr | §3.1 spec 字面 |
| 2. `main_health_emitters.rs` 新增 Track E section（80 LOC）：`build_strategy_quality_pair_list` + `build_strategy_quality_scheduler` + `spawn_strategy_quality_scheduler` + `spawn_strategy_quality_update_task` | E1 | 2 hr | §3.2 + §4.1 spec 字面 |
| 3. `main.rs` 增 10 LOC Track E wire-up | E1 | 30 min | §4.2 spec 字面 |
| 4. `tests/sprint5_wave_c_strategy_quality_wireup.rs` 新 8 test（in-memory + cache + SM observe + aggregate + replay forbidden + lookup + NaN skip + cargo lint） | E1 | 2 hr | AC-1a/2/3/6 spec |
| 5. main_health_emitters.rs line 441 log literal 更新 | E1 | 5 min | §4.3 |
| 6. E2 review round 1 → fix → round 2 → APPROVE | E2 | 2 hr | round 1 expected 0-2 finding |

**Phase A AC**：AC-1a PASS + AC-2 PASS + AC-3 PASS + AC-5 PASS + AC-6 PASS

### 6.2 Phase B — production deploy + real PG empirical（QA + operator；2-3 hr）

| 項目 | Owner | Est | 依賴 |
|---|---|---|---|
| 1. AC-4 Linux PG empirical dry-run（query string + 5 column parse + < 100ms verify） | QA | 30 min | Phase A scaffold land |
| 2. production engine restart_all.sh --rebuild + Track E scheduler 確認 alive log | operator | 15 min | Phase A commit + push trade-core |
| 3. AC-1b production V106 30 min sample empirical（≥125 row + 5 strategy × 5 symbol distinct） | QA | 30 min + 30 min wait | engine restart |
| 4. Phase 3e PM sign-off + carry-over routing 收 | PM | 30 min | AC-1b PASS |

**Phase B AC**：AC-1b PASS + AC-4 PASS

### 6.3 Total Sprint 5+ §4.3.1 budget

- Phase A：6-8 hr E1+E2
- Phase B：2-3 hr QA+operator+PM
- **Total：8-11 hr Sprint 5+ §4.3.1 wire-up**

### 6.4 並行可行性

Phase A 與 Sprint 5+ §4.2 4 carry-over（BybitPrivateWs supervisor 改造 / PortfolioStateCache update task wire-up / archive Python singleton re-ingest / dispatch packet 模板）並行：

- §4.2 item 1 (BybitPrivateWs supervisor) — file scope `bybit_private_ws.rs` + `main_health_emitters.rs`；本 spec file scope `strategy_quality_probe_impl.rs (新)` + `main_health_emitters.rs` 增 Track E section → **共用 main_health_emitters.rs**；E1 stagger 5min 或 sequential
- §4.2 item 2 (PortfolioStateCache wire-up) — file scope `main_health_emitters.rs::spawn_portfolio_state_update_task` 替 Wave B no-op 為 PaperState SSOT → **共用 main_health_emitters.rs**；E1 stagger 5min 或 sequential
- §4.2 item 3-4 — 純 doc work；0 conflict

**並行衝突結論**：3 個 E1 task（§4.3.1 + §4.2.1 + §4.2.2）共用 main_health_emitters.rs；建議 sequential E1 或 stagger 5min；E2 round 1 必驗 3 task 不破壞彼此 wire-up entry。

### 6.5 與 Sprint 5+ §4.3 其他 5 follow-up 並行

- §4.3.2 AC-7 cargo bench m3_emitter_cold_start fixture — file scope `benches/` 新 → 0 conflict
- §4.3.3 LOC peak 切檔 — 5 file 切；本 spec file `strategy_quality_probe_impl.rs (新)` 工程估算約 200 LOC（non-blocking），現行唯一 file-size acceptance 為 ≤ 2000 LOC（含 2000），不得僅因大小強拆，因此自身不因行數強制 split
- §4.3.4 F-4 correlation_avg_pairwise real calculator — risk_envelope_probe_impl.rs scope → 0 conflict
- §4.3.5 Track B PipelineThroughput real wire-up — pipeline_throughput.rs scope → 0 conflict
- §4.3.6 Track C writer_queue_depth / pool_wait_p95 — database_pool.rs scope → 0 conflict

---

## §7 §二 16 根原則合規確認

對齊 `srv/CLAUDE.md` §二 16 根原則（DOC-01 V2 SSOT）：

| # | 原則 | Track E wire-up 狀態 |
|---|---|---|
| 1 | 單一寫入口 | ✅ 本 wire-up 0 寫操作 — emitter 端純讀 PG SSOT；不經 IntentProcessor |
| 2 | 讀寫分離 | ✅ probe 端純讀；update task 端純 SELECT query |
| 3 | AI 輸出 ≠ 命令 | ✅ Track E 不產 AI 推理；純 PG empirical metric emit |
| 4 | 策略不繞風控 | ✅ Track E 不改 策略邏輯；不繞風控 |
| 5 | 生存 > 利潤 | ✅ Track E 不改交易行為；只觀測 |
| 6 | 失敗默認收縮 | ✅ fail-soft default OK band（per §3.1）；PG fail 不誤升 alarm |
| 7 | 學習 ≠ 改寫 Live | ✅ Track E 不寫 strategy_engine / fill_writer；純 V106 row INSERT（observability） |
| 8 | 交易可解釋 | ✅ V106 row 5 metric + state + strategy + symbol；可重建 trace |
| 9 | 災難保護 | ✅ Track E DEGRADED 不直接降 LAL Tier（per spec §2.3）；Sprint 5+ M7 才接 |
| 10 | 認知誠實 | ✅ 本 spec 明示「fail-soft default OK band」+ 「placeholder snapshot」反模式禁；E2 review 對抗反問必查 |
| 11 | Agent 最大自主 | ✅ 0 agent 接點；M3 emitter 是 observability layer |
| 12 | 持續進化 | ✅ V106 5 metric × 25 pair 為後續 Phase B/C strategy quality empirical 提供 SSOT |
| 13 | AI 成本感知 | ✅ 0 AI call；純 PG query |
| 14 | 零外部成本可運行 | ✅ PG 是 local infra；無外部 dep |
| 15 | 多 Agent 協作 | ✅ M3 emitter 不破 5 Agent + Conductor 通信契約 |
| 16 | 組合級風險 | ✅ aggregate SM 0.40 ratio 反映「>40% pair degraded → portfolio-level strategy quality issue」對齊原則 16 |

---

## §8 反模式（明示禁止）

per Sprint 2 Track E dispatch packet §6.5 + Wave A PA-DRIFT-5 教訓：

- (a) 改既有 strategy_quality.rs 1580 LOC Sprint 2 已 land 邏輯 — emitter trait + scheduler + classify 5 helper + 100 SM + aggregate 全保留
- (b) 改既有 trading_writer.rs / lease_writer.rs / strategy_engine.rs source 端 — emitter 只觀測；本 wire-up 純 PG query SELECT
- (c) 5 query 寫死高頻（30s / 60s 而非 300s）— 對齊 emitter sample_interval_sec=300 + PG load 預算
- (d) cache 寫 unbounded growth — 整 HashMap 整 batch 覆寫，25 pair upper bound；不 grow
- (e) 25 pair 寫死於 probe impl 內 — 對齊既有 emitter pair list ctor 注入；caller 從 `event_consumer::SYMBOLS` 動態生成
- (f) fail-soft default 走非 OK band 值（如 fill=0.5 而非 1.0）— 對齊既有 trait doc line 424 SSOT
- (g) update task fail 後 silent skip 不 warn log — 必 fail-loud warn（per F-2 sanitize）；cache stale 屬可接受 fail-soft
- (h) signal_count_24h 走 SM observe — telemetry-only；對齊既有 strategy_quality.rs line 842-857 直接寫 V106 row band=OK 不經 SM
- (i) cache update task 串入 PaperState / 既有 IPC channel — 純 PG empirical；不破 既有 risk_verdict_ledger / position_snapshot 寫入路徑
- (j) main_health_emitters.rs line 441 log literal 不同步 update（保留「Track E skip」字面）— E2 review 必查 log drift

---

## §9 Linux PG empirical 驗證清單（Phase B AC-4）

per `feedback_v_migration_pg_dry_run` mandatory：

| # | 驗證項 | 命令 | 預期 |
|---|---|---|---|
| 1 | `learning.lease_transitions.context_id` 真實非空率 | `SELECT COUNT(*) FILTER (WHERE context_id IS NOT NULL) / NULLIF(COUNT(*), 0)::float FROM learning.lease_transitions WHERE created_at > NOW() - INTERVAL '24 hours';` | > 0.5（建議 > 0.8）；若 < 0.5 屬 schema bottleneck 升 P0 |
| 2 | `trading.signals.context_id` 真實非空率 | `SELECT COUNT(*) FILTER (WHERE context_id IS NOT NULL) / NULLIF(COUNT(*), 0)::float FROM trading.signals WHERE ts > NOW() - INTERVAL '24 hours' AND strategy_name IS NOT NULL;` | > 0.8 |
| 3 | `learning.lease_transitions.to_state` value distribution | `SELECT to_state, COUNT(*) FROM learning.lease_transitions WHERE created_at > NOW() - INTERVAL '24 hours' GROUP BY to_state ORDER BY 2 DESC;` | `REGISTERED + ACTIVE > 0`；確認 enum 真實存在 |
| 4 | STRATEGY_QUALITY_BATCH_QUERY 整 query 跑時間 | `EXPLAIN ANALYZE <query literal>;` | < 100 ms total |
| 5 | 25 pair × 5 metric 整 batch result row count | `<query literal>` 跑後 `wc -l` | 0-25 row（取決於 24h 內 strategy 活躍度；funding_arb 預期 0 row） |

---

## §10 Cross-References

- Sprint 4+ first Live carry-over PM Phase 3e sign-off：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_first_live_carryover_pm_phase_3e_signoff.md` §4.3.1
- Sprint 2 Track E IMPL：`srv/rust/openclaw_engine/src/health/domains/strategy_quality.rs`（1580 LOC commit 6f6bbea8 + ffb7ed48 + 4d4ff99f）
- Sprint 2 design spec §3.5：`srv/docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md` line 411-423 + 655-672
- Sprint 2 dispatch packet §6：`srv/docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md` line 348-398
- Wave A PA-DRIFT-5 RealRiskEnvelopeSourceProbe：`srv/rust/openclaw_engine/src/health/domains/risk_envelope_probe_impl.rs`
- Wave B main_health_emitters wire-up：`srv/rust/openclaw_engine/src/main_health_emitters.rs` line 322-330（risk_envelope） + line 518-567（cache update task）
- M-1 Singleton Registry SSOT：`srv/docs/architecture/singleton-registry.md`（Wave C 端 `StrategyQualityMetricsCache` 必登記）
- V106 schema：`srv/sql/migrations/V106__health_observations.sql`
- 既有 SSOT 表：`srv/sql/migrations/V003__trading_agent_tables.sql`（signals/fills/decision_outcomes）+ `V028__fills_execution_slippage.sql`（slippage_bps column）+ `V054__lease_transitions_audit_writer.sql`（lease_transitions）

---

*OpenClaw / Arcane Equilibrium — Sprint 5+ §4.3.1 P1 — StrategyQualityEmitter wire-up design only — 0 IMPL code / 0 V### change / 0 ADR amend / 0 commit*
