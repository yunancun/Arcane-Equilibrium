//! M3 Sprint 4+ first Live PA-DRIFT-5 — `RealRiskEnvelopeSourceProbe` +
//! `PortfolioStateCache` integration test。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   驗證 PA-DRIFT-5 Wave A IMPL（`health/domains/risk_envelope_probe_impl.rs`）
//!   的 5 SSOT calculator accessor 對齊 trait 端 emitter 預期，並覆 user prompt
//!   `## 7. integration test` 列出的 4 個基準場景：
//!     1. mock fills 5 + position 3 → cum_pnl 計算驗
//!     2. mock equity 100 → 90 → 95 → max_dd_pct = 10%
//!     3. mock 3 active position → position_count = 3
//!     4. mock 2 correlated pair → correlation_avg（本 Wave A 端 placeholder 返
//!        0.0；Wave B 端接 calculator 後此 test 端改 expect real value）
//!   並補 5 個額外場景守不退化（24h sliding window cutoff / peak-trough across
//!   curve / concentration sum-zero fail-soft / probe 多次 lock 不死鎖 / probe ↔
//!   cache_handle 共享 Arc）。
//!
//! 主要 test:
//!   - `test_pa_drift_5_scenario_1_mock_fills_5_position_3_cum_pnl_sum`
//!   - `test_pa_drift_5_scenario_2_equity_100_90_95_max_dd_10pct`
//!   - `test_pa_drift_5_scenario_3_three_active_positions`
//!   - `test_pa_drift_5_scenario_4_correlation_placeholder_zero`
//!   - 5 額外退化守 test
//!
//! 依賴:
//!   - `openclaw_engine::health::domains::risk_envelope::RiskEnvelopeSourceProbe`
//!     trait（emitter 端契約）
//!   - `openclaw_engine::health::domains::risk_envelope_probe_impl::{Portfolio-
//!     StateCache, PositionExposure, RealRiskEnvelopeSourceProbe}`（本 Wave A IMPL）
//!
//! 硬邊界:
//!   - 純 Rust 內存 calculator 驗；不接 PG / 不引 cfg(feature = "spike") / 不接
//!     main.rs scheduler（Wave B 工作）。
//!   - emitter wire-up 自身的 V106 row 寫入 / SM observe 等已由 Wave 2 Track F
//!     `sprint2_track_f_risk_envelope` 8 test 守；本 file 只守 probe 端 5 SSOT
//!     calculator accessor 對齊與 cache update 路徑。

use std::sync::Arc;

use parking_lot::Mutex;

use openclaw_engine::health::domains::risk_envelope::RiskEnvelopeSourceProbe;
use openclaw_engine::health::domains::risk_envelope_probe_impl::{
    PortfolioStateCache, PositionExposure, RealRiskEnvelopeSourceProbe,
};

// 24h 毫秒（test 端 sliding window 期望值對齊 production const）。
const SLIDING_WINDOW_24H_MS: u64 = 24 * 60 * 60 * 1000;

// ============================================================
// user prompt §7 scenario 1-4
// ============================================================

/// scenario 1：mock fills 5 + position 3 → cum_pnl 計算驗。
///
/// 為什麼：對齊 task §1 portfolio_cum_pnl 24h sliding window calculator。
/// 5 個 fill 的 sum(realized_pnl) = 8.5；用 probe 端拉取必 8.5；fail-soft 不誤升。
#[test]
fn test_pa_drift_5_scenario_1_mock_fills_5_position_3_cum_pnl_sum() {
    let cache = Arc::new(Mutex::new(PortfolioStateCache::new()));
    let now_ms: u64 = 1_700_000_000_000;
    // 5 fill：sum = 10 + (-5) + 3.5 + 2.0 + (-2.0) = 8.5
    let new_fills = vec![
        (now_ms - 4000, 10.0),
        (now_ms - 3000, -5.0),
        (now_ms - 2000, 3.5),
        (now_ms - 1000, 2.0),
        (now_ms - 500, -2.0),
    ];
    let positions = vec![
        PositionExposure { notional_usd: 100.0 },
        PositionExposure { notional_usd: 200.0 },
        PositionExposure { notional_usd: 150.0 },
    ];
    {
        let mut guard = cache.lock();
        guard.update_from_pipeline_snapshot(now_ms, 1000.0, &new_fills, positions);
    }
    let probe = RealRiskEnvelopeSourceProbe::new(Arc::clone(&cache));

    let cum_pnl = probe.current_portfolio_cum_pnl_24h_usd();
    assert!(
        (cum_pnl - 8.5).abs() < 1e-4,
        "scenario 1：5 fill sum 應 8.5；實得 {}",
        cum_pnl
    );
    assert_eq!(
        probe.current_position_count_active(),
        3,
        "scenario 1：3 position → count=3"
    );
    // 驗 cache telemetry：5 fill history + 1 equity sample。
    let guard = cache.lock();
    assert_eq!(guard.fill_history_len(), 5);
    assert_eq!(guard.equity_history_len(), 1);
}

/// scenario 2：mock equity curve 100 → 90 → 95 → max_dd_pct = 10%。
///
/// 為什麼：對齊 task §2「peak equity → trough equity, max ((peak - trough) /
/// peak × 100)」公式；peak=100, trough=90 → dd=10%。
#[test]
fn test_pa_drift_5_scenario_2_equity_100_90_95_max_dd_10pct() {
    let cache = Arc::new(Mutex::new(PortfolioStateCache::new()));
    let now_ms: u64 = 1_700_000_000_000;
    {
        let mut guard = cache.lock();
        guard.update_from_pipeline_snapshot(now_ms - 2000, 100.0, &[], Vec::new());
        guard.update_from_pipeline_snapshot(now_ms - 1000, 90.0, &[], Vec::new());
        guard.update_from_pipeline_snapshot(now_ms, 95.0, &[], Vec::new());
    }
    let probe = RealRiskEnvelopeSourceProbe::new(Arc::clone(&cache));

    let dd = probe.current_portfolio_max_dd_pct();
    assert!(
        (dd - 10.0).abs() < 1e-4,
        "scenario 2：max_dd 應 10%（(100-90)/100×100）；實得 {}",
        dd
    );
}

/// scenario 3：mock 3 active position → position_count = 3。
///
/// 為什麼：對齊 task §3 reuse 既有 position snapshot active count；本 cache
/// 端走 `latest_exposures.len()`，spec §3.6 + §6.2 反模式 (e) preserved (top1
/// not top_n) 不影響 count 計算。
#[test]
fn test_pa_drift_5_scenario_3_three_active_positions() {
    let cache = Arc::new(Mutex::new(PortfolioStateCache::new()));
    let positions = vec![
        PositionExposure { notional_usd: 100.0 },
        PositionExposure { notional_usd: 200.0 },
        PositionExposure { notional_usd: 150.0 },
    ];
    {
        let mut guard = cache.lock();
        guard.update_from_pipeline_snapshot(1_700_000_000_000, 1000.0, &[], positions);
    }
    let probe = RealRiskEnvelopeSourceProbe::new(Arc::clone(&cache));

    assert_eq!(
        probe.current_position_count_active(),
        3,
        "scenario 3：3 active position → count=3"
    );
}

/// scenario 4：mock 2 correlated pair → correlation_avg。
///
/// 為什麼 placeholder：per dispatch packet §7.5 反模式 (c) + E2 Track F round 2
/// 對抗反問 #2 — portfolio cross-pair correlation rolling window calculator
/// 由 PA 拍板 lookback 後 Wave B IMPL；本 Wave A placeholder 返 0.0 是合法 OK
/// band 對齊，emitter 端 classify 視為 OK。Wave B 接 calculator 後此 test 端
/// 改 expect real value（per `feedback_no_dead_params` fail-soft：placeholder
/// 不致命，Wave B 升級不破壞 contract）。
#[test]
fn test_pa_drift_5_scenario_4_correlation_placeholder_zero() {
    let cache = Arc::new(Mutex::new(PortfolioStateCache::new()));
    // mock 2 correlated pair（exposure 投影；correlation 由 caller 端輸入
    // returns time series，placeholder 不需 returns；只驗 trait method 返 0.0）。
    let positions = vec![
        PositionExposure { notional_usd: 100.0 },
        PositionExposure { notional_usd: 100.0 },
    ];
    {
        let mut guard = cache.lock();
        guard.update_from_pipeline_snapshot(1_700_000_000_000, 1000.0, &[], positions);
    }
    let probe = RealRiskEnvelopeSourceProbe::new(Arc::clone(&cache));

    assert_eq!(
        probe.current_correlation_avg_pairwise(),
        0.0,
        "scenario 4：Wave A placeholder 返 0.0；Wave B 後接 calculator"
    );
}

// ============================================================
// 額外退化守 test
// ============================================================

/// 24h sliding window 截斷：> 24h 外 fill drop，cum_pnl 不誤累計舊樣本。
#[test]
fn test_24h_sliding_window_cutoff_drops_old_fills() {
    let cache = Arc::new(Mutex::new(PortfolioStateCache::new()));
    let now_ms: u64 = 1_700_000_000_000;
    let old_fill_ts = now_ms - 25 * 60 * 60 * 1000; // 25h 前 → 必 drop
    let recent_fill_ts = now_ms - 1000; // 1s 前 → 必保留
    let new_fills = vec![(old_fill_ts, 999.0), (recent_fill_ts, 5.0)];
    {
        let mut guard = cache.lock();
        guard.update_from_pipeline_snapshot(now_ms, 1000.0, &new_fills, Vec::new());
    }
    let probe = RealRiskEnvelopeSourceProbe::new(Arc::clone(&cache));

    let cum_pnl = probe.current_portfolio_cum_pnl_24h_usd();
    assert!(
        (cum_pnl - 5.0).abs() < 1e-4,
        "25h 外舊 fill 必 drop；只 sum 1s 前 5.0；實得 {}",
        cum_pnl
    );
    let guard = cache.lock();
    assert_eq!(
        guard.fill_history_len(),
        1,
        "fill_history 截斷後應只剩 1 個 sample"
    );
}

/// 24h sliding window：邊界值（剛好 24h 整數）— 落於 cutoff 邊界內必保留。
#[test]
fn test_24h_sliding_window_boundary_exact() {
    let cache = Arc::new(Mutex::new(PortfolioStateCache::new()));
    let now_ms: u64 = 1_700_000_000_000;
    let just_inside_ts = now_ms - SLIDING_WINDOW_24H_MS + 1; // 邊界內 1ms
    let just_outside_ts = now_ms.saturating_sub(SLIDING_WINDOW_24H_MS).saturating_sub(1);
    let new_fills = vec![(just_outside_ts, 100.0), (just_inside_ts, 7.0)];
    {
        let mut guard = cache.lock();
        guard.update_from_pipeline_snapshot(now_ms, 1000.0, &new_fills, Vec::new());
    }
    let probe = RealRiskEnvelopeSourceProbe::new(cache);

    let cum_pnl = probe.current_portfolio_cum_pnl_24h_usd();
    assert!(
        (cum_pnl - 7.0).abs() < 1e-4,
        "邊界外 fill 必 drop；只 sum 邊界內 7.0；實得 {}",
        cum_pnl
    );
}

/// max_dd_pct：peak-trough 出現於中段，後續恢復；仍取最大 dd。
#[test]
fn test_max_dd_pct_peak_trough_across_curve() {
    let cache = Arc::new(Mutex::new(PortfolioStateCache::new()));
    let now_ms: u64 = 1_700_000_000_000;
    // 100 → 110（peak）→ 88（trough；dd=20%）→ 95（恢復 dd=13.6%）
    {
        let mut guard = cache.lock();
        guard.update_from_pipeline_snapshot(now_ms - 3000, 100.0, &[], Vec::new());
        guard.update_from_pipeline_snapshot(now_ms - 2000, 110.0, &[], Vec::new());
        guard.update_from_pipeline_snapshot(now_ms - 1000, 88.0, &[], Vec::new());
        guard.update_from_pipeline_snapshot(now_ms, 95.0, &[], Vec::new());
    }
    let probe = RealRiskEnvelopeSourceProbe::new(cache);

    let dd = probe.current_portfolio_max_dd_pct();
    let expected = ((110.0 - 88.0) / 110.0) * 100.0;
    assert!(
        (dd - expected).abs() < 1e-4,
        "max_dd 應 {}（取 110→88 段）；實得 {}",
        expected,
        dd
    );
}

/// concentration_top1_pct：sum=0 / empty cache 全 fail-soft → 0.0 / OK band。
#[test]
fn test_concentration_top1_pct_sum_zero_fail_soft() {
    let cache = Arc::new(Mutex::new(PortfolioStateCache::new()));
    // 推入 0-notional exposures（sum=0 邊界）。
    let positions = vec![
        PositionExposure { notional_usd: 0.0 },
        PositionExposure { notional_usd: 0.0 },
    ];
    {
        let mut guard = cache.lock();
        guard.update_from_pipeline_snapshot(1_700_000_000_000, 1000.0, &[], positions);
    }
    let probe = RealRiskEnvelopeSourceProbe::new(cache);

    let conc = probe.current_concentration_top1_pct();
    assert_eq!(
        conc, 0.0,
        "sum=0 邊界必 fail-soft 返 0.0 對齊 OK band；實得 {}",
        conc
    );
}

/// probe 5 method 並行 read：同 cache 多次 lock 不死鎖。
#[test]
fn test_probe_multiple_lock_no_deadlock_in_one_thread() {
    let cache = Arc::new(Mutex::new(PortfolioStateCache::new()));
    let probe = RealRiskEnvelopeSourceProbe::new(Arc::clone(&cache));
    // 5 method 順序呼叫；每次都拿 lock 後立即釋放。
    let _ = probe.current_portfolio_cum_pnl_24h_usd();
    let _ = probe.current_portfolio_max_dd_pct();
    let _ = probe.current_position_count_active();
    let _ = probe.current_correlation_avg_pairwise();
    let _ = probe.current_concentration_top1_pct();
    // 任何 deadlock / poison 會 panic；走到此處即 PASS。
}

/// 整合場景：5 fill + equity 曲線 + 3 倉位 → 5 metric 同步對齊預期。
#[test]
fn test_integrated_scenario_5_fills_equity_curve_3_positions() {
    let cache = Arc::new(Mutex::new(PortfolioStateCache::new()));
    let now_ms: u64 = 1_700_000_000_000;
    // 1. 推入 equity 曲線 + fill + 倉位
    {
        let mut guard = cache.lock();
        // t-3000: equity=100
        guard.update_from_pipeline_snapshot(now_ms - 3000, 100.0, &[(now_ms - 3500, 5.0)], Vec::new());
        // t-2000: equity=90
        guard.update_from_pipeline_snapshot(
            now_ms - 2000,
            90.0,
            &[(now_ms - 2500, -10.0), (now_ms - 2200, 3.0)],
            Vec::new(),
        );
        // t-1000: equity=95 + 3 倉位開倉
        guard.update_from_pipeline_snapshot(
            now_ms - 1000,
            95.0,
            &[(now_ms - 1100, 2.0)],
            vec![
                PositionExposure { notional_usd: 100.0 },
                PositionExposure { notional_usd: 200.0 },
                PositionExposure { notional_usd: 150.0 },
            ],
        );
        // t now: equity=88（峰回落 → 新 trough；dd 升）
        guard.update_from_pipeline_snapshot(
            now_ms,
            88.0,
            &[(now_ms - 100, -2.0)],
            vec![
                PositionExposure { notional_usd: 100.0 },
                PositionExposure { notional_usd: 200.0 },
                PositionExposure { notional_usd: 150.0 },
            ],
        );
    }
    let probe = RealRiskEnvelopeSourceProbe::new(Arc::clone(&cache));

    // (1) cum_pnl 5 fill sum = 5 + (-10) + 3 + 2 + (-2) = -2
    let cum_pnl = probe.current_portfolio_cum_pnl_24h_usd();
    assert!(
        (cum_pnl - (-2.0)).abs() < 1e-4,
        "5 fill sum 應 -2.0；實得 {}",
        cum_pnl
    );
    // (2) max_dd：equity (100, 90, 95, 88)；peak=100；trough=88 → dd=12%
    let dd = probe.current_portfolio_max_dd_pct();
    assert!(
        (dd - 12.0).abs() < 1e-4,
        "max_dd 應 12%（(100-88)/100×100）；實得 {}",
        dd
    );
    // (3) position_count = 3
    assert_eq!(probe.current_position_count_active(), 3);
    // (4) correlation Wave A placeholder = 0.0
    assert_eq!(probe.current_correlation_avg_pairwise(), 0.0);
    // (5) concentration_top1 = 200 / 450 * 100 ≈ 44.44%
    let conc = probe.current_concentration_top1_pct();
    let expected_conc = 200.0 / 450.0 * 100.0;
    assert!(
        (conc - expected_conc).abs() < 1e-4,
        "concentration_top1 應 {:.4}%；實得 {:.4}",
        expected_conc,
        conc
    );
}

/// emitter 端契約對齊：通過 emitter `RiskEnvelopeEmitter::new(probe)` 路徑可
/// 接 real probe；採樣後 5 metric 對應 cache 值。
#[test]
fn test_emitter_wireup_with_real_probe() {
    use openclaw_engine::health::domains::risk_envelope::RiskEnvelopeEmitter;

    let cache = Arc::new(Mutex::new(PortfolioStateCache::new()));
    {
        let mut guard = cache.lock();
        let now_ms: u64 = 1_700_000_000_000;
        guard.update_from_pipeline_snapshot(
            now_ms,
            95.0,
            &[(now_ms - 500, 8.5)],
            vec![
                PositionExposure { notional_usd: 100.0 },
                PositionExposure { notional_usd: 200.0 },
                PositionExposure { notional_usd: 150.0 },
            ],
        );
    }
    let probe = RealRiskEnvelopeSourceProbe::new(Arc::clone(&cache));
    let emitter = RiskEnvelopeEmitter::new(probe);

    // sample_now 應走 trait method 拉 5 metric；不 panic + 對齊 cache 值。
    let sample = emitter.sample_now().expect("sample_now 應 PASS");
    assert!(
        (sample.portfolio_cum_pnl_24h_usd - 8.5).abs() < 1e-4,
        "emitter 端 cum_pnl 應 8.5；實得 {}",
        sample.portfolio_cum_pnl_24h_usd
    );
    assert_eq!(sample.position_count_active, 3);
    assert_eq!(
        sample.correlation_avg_pairwise, 0.0,
        "Wave A placeholder"
    );
    let expected_conc = 200.0 / 450.0 * 100.0;
    assert!(
        (sample.concentration_top1_pct - expected_conc).abs() < 1e-4,
        "emitter 端 concentration 應 {:.4}%；實得 {:.4}",
        expected_conc,
        sample.concentration_top1_pct
    );
}

// ============================================================
// PA-DRIFT-5 round 1 E2 F-3 fix：batch read helper integration
// ============================================================

/// snapshot_5_metric() batch path 對齊 5 個 current_xxx 個別 accessor；單 thread
/// 下 5 metric 字面相等（per E2 round 1 F-3 fix）。
///
/// 為什麼此 test 必要：
///   - F-3 fix 加 `RiskEnvelopeSourceProbe::snapshot_5_metric()` default method
///     + `RealRiskEnvelopeSourceProbe::snapshot_5_metric()` override；
///     emitter Wave B 接線後可切換走 batch path 避 5-lock gap micro-race window。
///   - 本 test 守 batch path 與 5 個 current_xxx 字面結果相等的 contract；
///     Wave B emitter wire-up 切換時不破壞語意。
#[test]
fn test_real_probe_batch_snapshot_aligns_with_5_current_xxx() {
    use openclaw_engine::health::domains::risk_envelope::RiskEnvelopeSampleSnapshot;

    let cache = Arc::new(Mutex::new(PortfolioStateCache::new()));
    {
        let mut guard = cache.lock();
        let now_ms: u64 = 1_700_000_000_000;
        guard.update_from_pipeline_snapshot(
            now_ms - 1000,
            100.0,
            &[(now_ms - 2000, 10.0), (now_ms - 1500, -2.0)],
            vec![
                PositionExposure { notional_usd: 100.0 },
                PositionExposure { notional_usd: 200.0 },
            ],
        );
        guard.update_from_pipeline_snapshot(
            now_ms,
            85.0,
            &[(now_ms - 100, 3.5)],
            vec![
                PositionExposure { notional_usd: 100.0 },
                PositionExposure { notional_usd: 200.0 },
            ],
        );
    }
    let probe = RealRiskEnvelopeSourceProbe::new(cache);

    let batch: RiskEnvelopeSampleSnapshot = probe.snapshot_5_metric();
    let cum_pnl = probe.current_portfolio_cum_pnl_24h_usd();
    let dd = probe.current_portfolio_max_dd_pct();
    let pos_count = probe.current_position_count_active();
    let corr = probe.current_correlation_avg_pairwise();
    let conc = probe.current_concentration_top1_pct();

    assert!(
        (batch.portfolio_cum_pnl_24h_usd - cum_pnl).abs() < 1e-9,
        "batch cum_pnl {} vs current {}",
        batch.portfolio_cum_pnl_24h_usd,
        cum_pnl
    );
    assert!(
        (batch.portfolio_max_dd_pct - dd).abs() < 1e-9,
        "batch dd {} vs current {}",
        batch.portfolio_max_dd_pct,
        dd
    );
    assert_eq!(batch.position_count_active, pos_count);
    assert!((batch.correlation_avg_pairwise - corr).abs() < 1e-9);
    assert!((batch.concentration_top1_pct - conc).abs() < 1e-9);
}

/// Empty cache 端 batch snapshot 也 fail-soft 返全 0（OK band 對齊）。
#[test]
fn test_real_probe_batch_snapshot_empty_cache_all_zero() {
    let cache = Arc::new(Mutex::new(PortfolioStateCache::new()));
    let probe = RealRiskEnvelopeSourceProbe::new(cache);

    let batch = probe.snapshot_5_metric();
    assert_eq!(batch.portfolio_cum_pnl_24h_usd, 0.0);
    assert_eq!(batch.portfolio_max_dd_pct, 0.0);
    assert_eq!(batch.position_count_active, 0);
    assert_eq!(batch.correlation_avg_pairwise, 0.0);
    assert_eq!(batch.concentration_top1_pct, 0.0);
}

/// 既有 mock trait impl（不 override `snapshot_5_metric`）走 default impl
/// 5 個 current_xxx，字面結果與 override path 等價；backward compat 守。
#[test]
fn test_default_snapshot_5_metric_works_for_non_overriding_impl() {
    /// 內嵌 mock；不 override `snapshot_5_metric`，走 trait default。
    struct StubProbeNoOverride {
        cum_pnl: f64,
        dd: f64,
        count: u32,
        corr: f64,
        conc: f64,
    }
    impl RiskEnvelopeSourceProbe for StubProbeNoOverride {
        fn current_portfolio_cum_pnl_24h_usd(&self) -> f64 {
            self.cum_pnl
        }
        fn current_portfolio_max_dd_pct(&self) -> f64 {
            self.dd
        }
        fn current_position_count_active(&self) -> u32 {
            self.count
        }
        fn current_correlation_avg_pairwise(&self) -> f64 {
            self.corr
        }
        fn current_concentration_top1_pct(&self) -> f64 {
            self.conc
        }
    }

    let stub = StubProbeNoOverride {
        cum_pnl: -125.5,
        dd: 7.3,
        count: 5,
        corr: 0.42,
        conc: 35.8,
    };

    // 走 default impl 端 snapshot_5_metric；應字面對齊個別 accessor
    let batch = stub.snapshot_5_metric();
    assert_eq!(batch.portfolio_cum_pnl_24h_usd, -125.5);
    assert_eq!(batch.portfolio_max_dd_pct, 7.3);
    assert_eq!(batch.position_count_active, 5);
    assert_eq!(batch.correlation_avg_pairwise, 0.42);
    assert_eq!(batch.concentration_top1_pct, 35.8);
}
