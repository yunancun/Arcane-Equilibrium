//! M3 Sprint 5+ §4.3.1 — StrategyQualitySourceProbe production impl。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per `docs/execution_plan/2026-05-23--sprint5_strategy_quality_wireup_design.md`
//!   §3.1 Sprint 5+ Wave C：本檔負責把 Sprint 2 Wave 2 Track E 完成的
//!   `StrategyQualitySourceProbe` trait 接到真實 PG 計算端，讓
//!   `StrategyQualityEmitter` 經由本 module 暴露 5 個 SSOT-equivalent metric
//!   per-(strategy, symbol) snapshot：
//!     1. fill_rate_intent_ratio （24h fill / signal ratio per strategy×symbol）
//!     2. slippage_bps_p95         （24h percentile_cont(0.95) |slippage_bps|）
//!     3. decision_lease_grant_rate（24h granted / requested per strategy×symbol）
//!     4. dormant_minutes          （now - MAX(ts) 分鐘數 per strategy×symbol）
//!     5. signal_count_24h         （24h signal_count；telemetry-only）
//!
//!   本檔對齊 Sprint 4+ first Live PA-DRIFT-5 Wave A `PortfolioStateCache` +
//!   `RealRiskEnvelopeSourceProbe` 範式（risk_envelope_probe_impl.rs），但 cache
//!   語意有兩個關鍵差異：
//!     - 不持 sliding window：5 metric 全為 PG-side 24h aggregate query 結果，
//!       cache 只保 batch snapshot（無增量 push 語意）。
//!     - per-(strategy, symbol) HashMap 存 25 pair 各自 5 metric snapshot；
//!       不存 portfolio-level scalar。
//!
//!   本檔不修 既有 strategy_quality.rs 1580 LOC Sprint 2 已 land 邏輯（emitter
//!   trait + scheduler + classify + 100 SM + aggregate 全保留）；不修 既有
//!   trading_writer / lease_writer / strategy_engine source 端寫入邏輯（emitter
//!   只觀測，本 wire-up 純 PG query SELECT）。
//!
//! 主要類 / 函數:
//!   - `StrategyQualityMetricsSnapshot`：5 metric f64/u32 + last_update_ts_ms；
//!     Copy + Clone + Debug + Default。
//!   - `StrategyQualityMetricsCache`：per-(strategy, symbol) HashMap 緩存；
//!     `new()` / `update_batch(now_ms, snapshots)` / `snapshot_for(strategy,
//!     symbol)` / telemetry accessor。F-2 NaN/inf sanitize on update_batch。
//!   - `RealStrategyQualitySourceProbe`：impl `StrategyQualitySourceProbe` trait
//!     5 method lookup cache；持 `Arc<parking_lot::Mutex<StrategyQualityMetricsCache>>`；
//!     emitter 端 sample 呼叫即從 cache 讀（fail-soft：cache empty 走 default
//!     OK band 值）。
//!
//! 依賴:
//!   - `parking_lot::Mutex`：cache 端鎖（cargo workspace 既有 dep；與
//!     risk_envelope_probe_impl 範式一致）。
//!   - `super::strategy_quality::StrategyQualitySourceProbe`：本 module impl 的
//!     trait 界面（Sprint 2 Wave 2 Track E 已 land；本 IMPL 不修 trait 簽名）。
//!
//! 硬邊界:
//!   - 不修 strategy_engine / fill_writer / lease audit / trading.signals /
//!     trading.fills / learning.lease_transitions 既有寫入路徑（per spec
//!     §8 反模式 (b)；本檔只 SELECT，不 INSERT/UPDATE/DELETE）。
//!   - 不引 spike feature；production binary 0 mock time 滲透（per AC-5）。
//!   - 不引新 V### / IPC；本檔純 Rust 內存 calculator + PG SELECT，emit V106
//!     row 由既有 `StrategyQualityEmitter` + `StrategyQualityScheduler` 負責。
//!   - cache 內存不跨 restart；restart 後從 empty 起算，首次 300s tick 觸 update
//!     後即可達穩定 25 pair × 5 metric snapshot。
//!   - probe 端 5 method 返 f64/u32 原始值；fail-soft 走 trait doc line 424
//!     既有契約（fill=1.0 / slippage=0 / lease=1.0 / dormant=0 / signal=0）。
//!   - F-2 NaN/inf sanitize：update_batch 端 filter pair 含 NaN/inf 並 fail-loud
//!     warn log；對齊 PA-DRIFT-5 round 2 升級 P1 Wave B condition。
//!
//! 新 singleton 登記注解（per profile「沒穩定登記表，改在 PA/E2 report + TODO
//! follow-up」）:
//!   - `StrategyQualityMetricsCache`：新 mutable cache 結構；main.rs Wave C
//!     wire-up 時 owner 為單一 `Arc<parking_lot::Mutex<StrategyQualityMetricsCache>>`。
//!     E2 audit 時應確認不重複構造、不誤跨 mode race（Live / Demo / Paper 共享
//!     單一 cache，per spec §6 反問 #7 engine_mode 4 值 IN filter 在 PG query 端
//!     處理；非 cache 端隔離）。
//!   - `RealStrategyQualitySourceProbe`：trait impl 端 Arc<dyn> 注入 emitter；
//!     emitter 端是 trait object，多 mode 走多 probe instance 不互相干涉。

use std::collections::HashMap;
use std::sync::Arc;

use parking_lot::Mutex;

use super::strategy_quality::StrategyQualitySourceProbe;

// ============================================================
// StrategyQualityMetricsSnapshot — per-(strategy, symbol) 5 metric 結果
// ============================================================

/// per-(strategy, symbol) 5-metric snapshot；update task 端覆寫整 cache，
/// probe 端按 (strategy, symbol) 鍵讀。
///
/// 為什麼 5 field 全 owned f64/u32 而非 sliding window:
///   - 5 metric SSOT 全為「24h window aggregate」（fill_rate / slippage_bps_p95 /
///     lease_grant_rate / signal_count_24h）或「now - MAX」（dormant_minutes）；
///     PG query 端已完成 aggregation，cache 端只保最新一次 query 結果。
///   - 對比 risk_envelope `PortfolioStateCache` 持 VecDeque sliding window 是
///     因為 caller 端 push 增量 fill；本 cache 走 5 min tick query 端 batch
///     pull，無增量 push 語意，不需 sliding window。
///
/// 為什麼 dormant_minutes 是 f64 而非 u32（per spec §2.4 line 217 + 端點 u32 cap）:
///   - PG EXTRACT(EPOCH FROM ...)/60.0 返 numeric → Rust f64；保留 f64 精度避免
///     提前 round。
///   - emitter 端 classify_strategy_quality_dormant_minutes 取 u32 入參；cache
///     端走 u32 後 emitter snapshot_for 端再對齊 trait API。
///
/// 為什麼 Copy:
///   - 5 metric 全 primitive；cache 端 `snapshot_for` 走 `copied()` zero-cost
///     clone 對齊 emitter 5 trait method 各自 lookup pattern。
#[derive(Debug, Clone, Copy)]
pub struct StrategyQualityMetricsSnapshot {
    /// 24h fill / signal ratio（per spec §2.1）；OK band > 0.80。
    pub fill_rate_intent_ratio: f64,
    /// 24h |slippage_bps| p95（per spec §2.2）；OK band < 5 bps。
    pub slippage_bps_p95: f64,
    /// 24h lease ACTIVE / REGISTERED ratio（per spec §2.3）；OK band > 0.70。
    pub decision_lease_grant_rate: f64,
    /// (now - MAX(ts)) / 60.0 分鐘（per spec §2.4）；u32 cap = 2147483647 min ≈
    /// 4086 年；不會 overflow；OK band < 60 min。
    pub dormant_minutes: u32,
    /// 24h signal_count（per spec §2.5）；telemetry-only；無 SLO band。
    pub signal_count_24h: u32,
    /// 最後一次 update_batch 完成 wall-clock ms（telemetry / E2 audit）。
    pub last_update_ts_ms: u64,
}

impl Default for StrategyQualityMetricsSnapshot {
    /// fail-soft default = 5 OK band 值（per spec §3.1 + trait doc line 424）。
    ///
    /// 為什麼此 5 default 對齊 OK band:
    ///   - cache 未含 (strategy, symbol) pair 時，emitter classify 走 OK；不誤升
    ///     CRITICAL（per `feedback_no_dead_params` fail-soft 對齊「未接線 source
    ///     不應假陽性 alarm」）。
    ///   - fill_rate=1.0 對齊 fill > 0.80 OK band；slippage=0.0 對齊 < 5 bps OK
    ///     band；lease_grant=1.0 對齊 > 0.70 OK band；dormant=0 對齊 < 60 min
    ///     OK band；signal_count=0 telemetry-only。
    fn default() -> Self {
        Self {
            fill_rate_intent_ratio: 1.0,
            slippage_bps_p95: 0.0,
            decision_lease_grant_rate: 1.0,
            dormant_minutes: 0,
            signal_count_24h: 0,
            last_update_ts_ms: 0,
        }
    }
}

// ============================================================
// StrategyQualityMetricsCache — per-(strategy, symbol) HashMap 緩存
// ============================================================

/// 25 instance per-(strategy, symbol) 5-metric snapshot cache。
///
/// 為什麼 HashMap 而非 Vec<(String, String, snapshot)>（per spec §3.1）:
///   - probe 端 trait method `current_fill_rate_intent_ratio(strategy, symbol)`
///     需 O(1) lookup；25 pair 雖然 linear scan 也夠快，HashMap 對應既有
///     scheduler `per_pair_sms: HashMap<(strategy, symbol, metric_name), ...>`
///     pattern 一致。
///   - update task 端 5 min tick PG batch 1 query 拿完 25 pair × 5 metric snapshot
///     後整 HashMap 拍照覆寫（per 設計反問 #2 不採增量 update 因 PG aggregate
///     query batch 一次拿完更快）。
///
/// 為什麼 per-(String, String) 鍵對齊 既有 scheduler:
///   - probe 端 trait 5 method 入參 (strategy, symbol)；HashMap 鍵對齊即可直接
///     lookup；scheduler 端 25 pair pre-create 對應 25 cache entry。
///
/// 為什麼 last_batch_update_ts_ms 在 cache root（不在 snapshot 內）:
///   - cache root 端的 timestamp 反映「整 batch update 完成時刻」；snapshot 內部
///     的 last_update_ts_ms 反映「該 pair snapshot 本身的 update 時刻」。兩者實
///     際相等（整 batch 同 instant 覆寫）；cache root 端版本提供「即使 25 pair
///     都 default」也有 telemetry 可查 fall-back 時點。
pub struct StrategyQualityMetricsCache {
    /// per-(strategy, symbol) 最新 5-metric snapshot。
    snapshots: HashMap<(String, String), StrategyQualityMetricsSnapshot>,
    /// telemetry / E2 audit：最後一次 batch update 完成 wall-clock ms。
    last_batch_update_ts_ms: u64,
}

impl StrategyQualityMetricsCache {
    /// 建立空 cache。production 端 caller 在 main.rs Wave C 接 scheduler wire-up
    /// 時建一個 `Arc<parking_lot::Mutex<StrategyQualityMetricsCache>>` 共享給
    /// probe + update task 端。
    pub fn new() -> Self {
        Self {
            snapshots: HashMap::new(),
            last_batch_update_ts_ms: 0,
        }
    }

    /// 由 update task 端 5 min tick 完整覆寫 25 pair snapshot。
    ///
    /// 為什麼整 batch 覆寫而非增量（per spec §3.1）:
    ///   - 5 PG aggregate query 端 batch 拿完 25 pair × 5 metric；caller 端一次
    ///     update HashMap 比 25 個小 update lock 更原子。
    ///   - 對比 risk_envelope `update_from_pipeline_snapshot` 是增量 fill push +
    ///     整列覆寫 latest_exposures；本 cache 純整列覆寫無增量語意。
    ///
    /// F-2 NaN/inf sanitize（對齊 risk_envelope F-2）:
    ///   - update task 端 query 結果若含 NaN/inf（不太可能因 PG aggregate 回傳
    ///     NULL 而非 NaN，caller convert NULL → fail-soft default）→ skip 該 pair；
    ///     保留前一次 snapshot 不被污染。
    ///   - 任一 pair 含 NaN/inf → 該 pair filter out + fail-loud warn log；其他
    ///     legal pair 仍 land snapshot（per spec §3.1 sanitize 設計）。
    ///   - last_batch_update_ts_ms 仍 advance；對齊 caller 「tick 已執行」語意；
    ///     telemetry 可依此偵測 update task alive。
    pub fn update_batch(
        &mut self,
        now_ms: u64,
        snapshots: HashMap<(String, String), StrategyQualityMetricsSnapshot>,
    ) {
        // F-2 sanitize：skip pair 含 NaN/inf 任一 field；dormant_minutes / signal_count_24h
        // 是 u32 不可能 NaN，只查 3 個 f64 metric。
        let sanitized: HashMap<(String, String), StrategyQualityMetricsSnapshot> = snapshots
            .into_iter()
            .filter(|(key, s)| {
                let finite = s.fill_rate_intent_ratio.is_finite()
                    && s.slippage_bps_p95.is_finite()
                    && s.decision_lease_grant_rate.is_finite();
                if !finite {
                    tracing::warn!(
                        target = "m3.health.strategy_quality",
                        strategy = %key.0,
                        symbol = %key.1,
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

    /// per-(strategy, symbol) lookup；fail-soft 走 default snapshot（5 OK band 值）。
    ///
    /// 為什麼 default 走 OK band（per spec §3.1 + trait doc line 424）:
    ///   - 對齊既有 trait doc「probe 失敗返 OK-band 值（fill=1.0 / slippage=0 /
    ///     lease=1.0 / dormant=0 / signal=0）」。
    ///   - cache 未含 pair（25 pair 中某 pair 該 tick query 不返 row；典型情境：
    ///     funding_arb dormant 全策略未 active）→ default OK band。
    ///   - 不誤升 CRITICAL：cold start cache empty → 25 pair × 5 metric V106 row
    ///     全 OK band；real PG update 首次 tick 後即反映實際 metric。
    pub fn snapshot_for(&self, strategy: &str, symbol: &str) -> StrategyQualityMetricsSnapshot {
        self.snapshots
            .get(&(strategy.to_string(), symbol.to_string()))
            .copied()
            .unwrap_or_default()
    }

    /// telemetry / E2 audit：最後一次 batch update 完成 wall-clock ms。
    pub fn last_batch_update_ts_ms(&self) -> u64 {
        self.last_batch_update_ts_ms
    }

    /// telemetry / E2 audit：active pair 數（cache 內含 row 數）。
    ///
    /// 為什麼 accessor:
    ///   - QA Phase B 端可由 `nm` symbol + integration test 端讀 cache 確認
    ///     update task 工作中（active_pair_count > 0 = 至少 1 pair 有 PG row）。
    ///   - E2 audit 端可驗 active_pair_count ≤ 25（不會超過 pair list 上界）。
    pub fn active_pair_count(&self) -> usize {
        self.snapshots.len()
    }
}

impl Default for StrategyQualityMetricsCache {
    fn default() -> Self {
        Self::new()
    }
}

// ============================================================
// RealStrategyQualitySourceProbe — production probe；impl trait
// ============================================================

/// production probe；包 `Arc<parking_lot::Mutex<StrategyQualityMetricsCache>>`，
/// emitter `sample_now()` 呼叫端從 cache 讀 5 metric snapshot。
///
/// 為什麼 `Arc<Mutex<...>>`:
///   - emitter 端 trait object 跨 tokio task 邊界（Send + Sync）；Arc 提供
///     reference count，Mutex 提供互斥讀寫。
///   - `parking_lot::Mutex` 對齊 cargo workspace 既有 dep；與
///     `RealRiskEnvelopeSourceProbe` 範式一致；不引 std::sync::Mutex 避免 lock
///     poisoning 噪音。
///   - cache update 端（main_health_emitters.rs spawn_strategy_quality_update_task）
///     與 probe 端（emitter sample）共享同一 Arc；lock 時段都 < 1ms（5 calculator
///     純 HashMap lookup）。
///
/// 為什麼非 RwLock:
///   - emitter sample tick 是 300s 一次；update tick 是 300s 一次；不存在「多
///     reader 1 writer 的高頻讀」情境；Mutex 足夠且實作簡單。
///   - 換 RwLock 是 Sprint 5+ cascade 階段 hot-path 優化點，不在本 Phase A scope。
pub struct RealStrategyQualitySourceProbe {
    cache: Arc<Mutex<StrategyQualityMetricsCache>>,
}

impl RealStrategyQualitySourceProbe {
    /// 建立 probe；caller 端注入共享 cache 句柄。
    ///
    /// 為什麼 `Arc<Mutex<...>>` 而非 generic:
    ///   - probe 是 trait object（`Arc<dyn StrategyQualitySourceProbe>`）；具體
    ///     struct 不需 generic 泛化。
    ///   - main_health_emitters.rs Wave C wire-up 時建 `Arc<Mutex<
    ///     StrategyQualityMetricsCache>>` 一次，clone 給 update task + probe；
    ///     不需引入第二層抽象。
    pub fn new(cache: Arc<Mutex<StrategyQualityMetricsCache>>) -> Self {
        Self { cache }
    }

    /// E2 audit / test helper：直接拿 cache 句柄（不 expose mut 給外部寫入；
    /// 寫入由 `StrategyQualityMetricsCache::update_batch` 走）。
    pub fn cache_handle(&self) -> Arc<Mutex<StrategyQualityMetricsCache>> {
        Arc::clone(&self.cache)
    }
}

impl StrategyQualitySourceProbe for RealStrategyQualitySourceProbe {
    fn current_fill_rate_intent_ratio(&self, strategy: &str, symbol: &str) -> f64 {
        self.cache
            .lock()
            .snapshot_for(strategy, symbol)
            .fill_rate_intent_ratio
    }

    fn current_slippage_bps_p95(&self, strategy: &str, symbol: &str) -> f64 {
        self.cache
            .lock()
            .snapshot_for(strategy, symbol)
            .slippage_bps_p95
    }

    fn current_decision_lease_grant_rate(&self, strategy: &str, symbol: &str) -> f64 {
        self.cache
            .lock()
            .snapshot_for(strategy, symbol)
            .decision_lease_grant_rate
    }

    fn current_dormant_minutes(&self, strategy: &str, symbol: &str) -> u32 {
        self.cache
            .lock()
            .snapshot_for(strategy, symbol)
            .dormant_minutes
    }

    fn current_signal_count_24h(&self, strategy: &str, symbol: &str) -> u32 {
        self.cache
            .lock()
            .snapshot_for(strategy, symbol)
            .signal_count_24h
    }
}

// ============================================================
// 測試
// ============================================================

#[cfg(test)]
mod tests {
    use super::*;

    /// (1) cache empty 走 fail-soft default OK band（per spec AC-1a + §3.1）。
    #[test]
    fn test_cache_empty_returns_default_ok_band() {
        let cache = StrategyQualityMetricsCache::new();
        let snap = cache.snapshot_for("ma_crossover", "BTCUSDT");
        // 5 metric 全 OK band 值（per Default impl）
        assert_eq!(snap.fill_rate_intent_ratio, 1.0, "fill_rate default OK band");
        assert_eq!(snap.slippage_bps_p95, 0.0, "slippage default OK band");
        assert_eq!(
            snap.decision_lease_grant_rate, 1.0,
            "lease_grant default OK band"
        );
        assert_eq!(snap.dormant_minutes, 0, "dormant default OK band");
        assert_eq!(snap.signal_count_24h, 0, "signal_count default 0");
        assert_eq!(snap.last_update_ts_ms, 0, "default last_update_ts_ms = 0");
        assert_eq!(cache.active_pair_count(), 0);
        assert_eq!(cache.last_batch_update_ts_ms(), 0);
    }

    /// (2) update_batch 25 pair × 5 metric 拍照覆寫 + per-pair lookup 正確。
    #[test]
    fn test_update_batch_25_pair_lookup_aligns() {
        let mut cache = StrategyQualityMetricsCache::new();
        let now_ms: u64 = 1_700_000_000_000;
        let mut snapshots: HashMap<(String, String), StrategyQualityMetricsSnapshot> =
            HashMap::new();
        // 推 2 pair 入 cache。
        snapshots.insert(
            ("ma_crossover".to_string(), "BTCUSDT".to_string()),
            StrategyQualityMetricsSnapshot {
                fill_rate_intent_ratio: 0.90,
                slippage_bps_p95: 3.5,
                decision_lease_grant_rate: 0.85,
                dormant_minutes: 30,
                signal_count_24h: 50,
                last_update_ts_ms: now_ms,
            },
        );
        snapshots.insert(
            ("grid_trading".to_string(), "ETHUSDT".to_string()),
            StrategyQualityMetricsSnapshot {
                fill_rate_intent_ratio: 0.10,
                slippage_bps_p95: 12.0,
                decision_lease_grant_rate: 0.05,
                dormant_minutes: 420,
                signal_count_24h: 5,
                last_update_ts_ms: now_ms,
            },
        );

        cache.update_batch(now_ms, snapshots);
        assert_eq!(cache.active_pair_count(), 2);
        assert_eq!(cache.last_batch_update_ts_ms(), now_ms);

        // pair 1：ma_crossover × BTCUSDT OK band。
        let s1 = cache.snapshot_for("ma_crossover", "BTCUSDT");
        assert!((s1.fill_rate_intent_ratio - 0.90).abs() < 1e-9);
        assert!((s1.slippage_bps_p95 - 3.5).abs() < 1e-9);
        assert_eq!(s1.dormant_minutes, 30);
        assert_eq!(s1.signal_count_24h, 50);

        // pair 2：grid_trading × ETHUSDT CRITICAL band。
        let s2 = cache.snapshot_for("grid_trading", "ETHUSDT");
        assert!((s2.fill_rate_intent_ratio - 0.10).abs() < 1e-9);
        assert!((s2.slippage_bps_p95 - 12.0).abs() < 1e-9);
        assert!((s2.decision_lease_grant_rate - 0.05).abs() < 1e-9);
        assert_eq!(s2.dormant_minutes, 420);

        // pair 3（未推入）走 default OK band。
        let s3 = cache.snapshot_for("funding_arb", "DOGEUSDT");
        assert_eq!(s3.fill_rate_intent_ratio, 1.0);
        assert_eq!(s3.dormant_minutes, 0);
    }

    /// (3) F-2 sanitize：NaN snapshot 必 skip + 不污染其他 pair（per spec §3.1）。
    #[test]
    fn test_f2_sanitize_skips_nan_snapshot() {
        let mut cache = StrategyQualityMetricsCache::new();
        let now_ms: u64 = 1_700_000_000_000;
        let mut snapshots: HashMap<(String, String), StrategyQualityMetricsSnapshot> =
            HashMap::new();
        // 1 個 legal pair。
        snapshots.insert(
            ("ma_crossover".to_string(), "BTCUSDT".to_string()),
            StrategyQualityMetricsSnapshot {
                fill_rate_intent_ratio: 0.85,
                slippage_bps_p95: 4.0,
                decision_lease_grant_rate: 0.75,
                dormant_minutes: 10,
                signal_count_24h: 30,
                last_update_ts_ms: now_ms,
            },
        );
        // 1 個 NaN fill_rate pair → 必 filter。
        snapshots.insert(
            ("bb_breakout".to_string(), "BTCUSDT".to_string()),
            StrategyQualityMetricsSnapshot {
                fill_rate_intent_ratio: f64::NAN,
                slippage_bps_p95: 5.0,
                decision_lease_grant_rate: 0.8,
                dormant_minutes: 20,
                signal_count_24h: 40,
                last_update_ts_ms: now_ms,
            },
        );
        // 1 個 inf slippage pair → 必 filter。
        snapshots.insert(
            ("grid_trading".to_string(), "SOLUSDT".to_string()),
            StrategyQualityMetricsSnapshot {
                fill_rate_intent_ratio: 0.9,
                slippage_bps_p95: f64::INFINITY,
                decision_lease_grant_rate: 0.7,
                dormant_minutes: 5,
                signal_count_24h: 20,
                last_update_ts_ms: now_ms,
            },
        );
        // 1 個 -inf lease_grant pair → 必 filter。
        snapshots.insert(
            ("funding_arb".to_string(), "XRPUSDT".to_string()),
            StrategyQualityMetricsSnapshot {
                fill_rate_intent_ratio: 0.95,
                slippage_bps_p95: 2.0,
                decision_lease_grant_rate: f64::NEG_INFINITY,
                dormant_minutes: 0,
                signal_count_24h: 10,
                last_update_ts_ms: now_ms,
            },
        );

        cache.update_batch(now_ms, snapshots);
        // 只應留 1 個 legal pair；3 個 NaN/inf pair 必 filter。
        assert_eq!(
            cache.active_pair_count(),
            1,
            "F-2 sanitize 後只剩 1 legal pair"
        );
        // last_batch_update_ts_ms 仍 advance（telemetry 對齊 caller 「tick 已執行」）。
        assert_eq!(cache.last_batch_update_ts_ms(), now_ms);

        // legal pair 仍可 lookup。
        let s = cache.snapshot_for("ma_crossover", "BTCUSDT");
        assert!((s.fill_rate_intent_ratio - 0.85).abs() < 1e-9);
        // NaN/inf 3 pair 走 fail-soft default OK band（未被污染）。
        let bb = cache.snapshot_for("bb_breakout", "BTCUSDT");
        assert_eq!(bb.fill_rate_intent_ratio, 1.0);
        assert!(bb.fill_rate_intent_ratio.is_finite());
    }

    /// (4) RealStrategyQualitySourceProbe：5 trait method 對齊 cache 端輸出。
    #[test]
    fn test_real_probe_5_methods_align_with_cache() {
        let cache = Arc::new(Mutex::new(StrategyQualityMetricsCache::new()));
        // 推入測試資料。
        {
            let mut guard = cache.lock();
            let now_ms: u64 = 1_700_000_000_000;
            let mut snapshots: HashMap<
                (String, String),
                StrategyQualityMetricsSnapshot,
            > = HashMap::new();
            snapshots.insert(
                ("ma_crossover".to_string(), "BTCUSDT".to_string()),
                StrategyQualityMetricsSnapshot {
                    fill_rate_intent_ratio: 0.75,
                    slippage_bps_p95: 6.0,
                    decision_lease_grant_rate: 0.60,
                    dormant_minutes: 90,
                    signal_count_24h: 25,
                    last_update_ts_ms: now_ms,
                },
            );
            guard.update_batch(now_ms, snapshots);
        }
        let probe = RealStrategyQualitySourceProbe::new(cache);

        // 5 trait method 對應 5 metric 值。
        assert!(
            (probe.current_fill_rate_intent_ratio("ma_crossover", "BTCUSDT") - 0.75).abs()
                < 1e-9,
            "probe fill_rate 應 0.75"
        );
        assert!(
            (probe.current_slippage_bps_p95("ma_crossover", "BTCUSDT") - 6.0).abs() < 1e-9,
            "probe slippage_bps_p95 應 6.0"
        );
        assert!(
            (probe.current_decision_lease_grant_rate("ma_crossover", "BTCUSDT") - 0.60).abs()
                < 1e-9,
            "probe lease_grant 應 0.60"
        );
        assert_eq!(
            probe.current_dormant_minutes("ma_crossover", "BTCUSDT"),
            90
        );
        assert_eq!(
            probe.current_signal_count_24h("ma_crossover", "BTCUSDT"),
            25
        );

        // 未推入 pair 走 fail-soft default OK band。
        assert_eq!(
            probe.current_fill_rate_intent_ratio("funding_arb", "DOGEUSDT"),
            1.0,
            "未推入 pair → default fail-soft OK"
        );
        assert_eq!(
            probe.current_dormant_minutes("funding_arb", "DOGEUSDT"),
            0
        );
    }

    /// (5) cache_handle audit：返同一 Arc 不重新建構（per E2 audit helper）。
    #[test]
    fn test_cache_handle_returns_same_arc() {
        let cache = Arc::new(Mutex::new(StrategyQualityMetricsCache::new()));
        let probe = RealStrategyQualitySourceProbe::new(Arc::clone(&cache));
        let handle1 = probe.cache_handle();
        let handle2 = probe.cache_handle();
        assert!(
            Arc::ptr_eq(&handle1, &handle2),
            "cache_handle 必返同一 Arc 句柄"
        );
        assert!(
            Arc::ptr_eq(&handle1, &cache),
            "cache_handle 必對齊 probe 構造時的 Arc"
        );
    }

    /// (6) probe 多次 lock 同 cache 不死鎖（telemetry sanity）。
    #[test]
    fn test_real_probe_multiple_lock_not_deadlock() {
        let cache = Arc::new(Mutex::new(StrategyQualityMetricsCache::new()));
        let probe = RealStrategyQualitySourceProbe::new(Arc::clone(&cache));
        // 5 method 順序呼叫；每次都拿 lock 後立即釋放。
        let _ = probe.current_fill_rate_intent_ratio("ma_crossover", "BTCUSDT");
        let _ = probe.current_slippage_bps_p95("ma_crossover", "BTCUSDT");
        let _ = probe.current_decision_lease_grant_rate("ma_crossover", "BTCUSDT");
        let _ = probe.current_dormant_minutes("ma_crossover", "BTCUSDT");
        let _ = probe.current_signal_count_24h("ma_crossover", "BTCUSDT");
    }

    /// (7) update_batch 二次覆寫：第二次拍照取代第一次（無 sliding window 語意）。
    #[test]
    fn test_update_batch_second_call_replaces_first() {
        let mut cache = StrategyQualityMetricsCache::new();
        let t1: u64 = 1_700_000_000_000;
        let t2: u64 = t1 + 300_000; // 300s 後

        // 第 1 tick：1 pair。
        let mut s1: HashMap<(String, String), StrategyQualityMetricsSnapshot> =
            HashMap::new();
        s1.insert(
            ("ma_crossover".to_string(), "BTCUSDT".to_string()),
            StrategyQualityMetricsSnapshot {
                fill_rate_intent_ratio: 0.5,
                slippage_bps_p95: 8.0,
                decision_lease_grant_rate: 0.4,
                dormant_minutes: 50,
                signal_count_24h: 20,
                last_update_ts_ms: t1,
            },
        );
        cache.update_batch(t1, s1);
        assert_eq!(cache.active_pair_count(), 1);
        assert!(
            (cache.snapshot_for("ma_crossover", "BTCUSDT").fill_rate_intent_ratio - 0.5).abs()
                < 1e-9
        );

        // 第 2 tick：完全不同的 pair；第 1 tick 的 ma_crossover 必被取代。
        let mut s2: HashMap<(String, String), StrategyQualityMetricsSnapshot> =
            HashMap::new();
        s2.insert(
            ("grid_trading".to_string(), "ETHUSDT".to_string()),
            StrategyQualityMetricsSnapshot {
                fill_rate_intent_ratio: 0.95,
                slippage_bps_p95: 1.0,
                decision_lease_grant_rate: 0.95,
                dormant_minutes: 2,
                signal_count_24h: 100,
                last_update_ts_ms: t2,
            },
        );
        cache.update_batch(t2, s2);

        // 整列覆寫：第 1 tick 的 pair 必消失，只剩第 2 tick 的 grid_trading × ETHUSDT。
        assert_eq!(cache.active_pair_count(), 1);
        assert_eq!(cache.last_batch_update_ts_ms(), t2);
        let after = cache.snapshot_for("ma_crossover", "BTCUSDT");
        assert_eq!(
            after.fill_rate_intent_ratio, 1.0,
            "第 1 tick pair 必被覆寫，走 default OK"
        );
        let grid = cache.snapshot_for("grid_trading", "ETHUSDT");
        assert!((grid.fill_rate_intent_ratio - 0.95).abs() < 1e-9);
    }
}
