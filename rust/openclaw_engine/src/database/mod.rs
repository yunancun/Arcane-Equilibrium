//! Database module — PostgreSQL/TimescaleDB persistence layer (Phase 1).
//! 資料庫模組 — PostgreSQL/TimescaleDB 持久化層。
//!
//! MODULE_NOTE (EN): Async database layer using sqlx 0.8 (runtime queries, not compile-time macros).
//!   All writes are non-blocking: tick_pipeline sends via bounded mpsc channels, async writer
//!   tasks batch-insert using QueryBuilder::push_values(). JSONL fallback on PG failure.
//!   Pool init is optional — engine runs without PG (graceful degradation).
//! MODULE_NOTE (中): 使用 sqlx 0.8 的異步資料庫層（運行時查詢，非編譯時宏）。
//!   所有寫入非阻塞：tick_pipeline 通過有界 mpsc 通道發送，異步 writer 任務使用
//!   QueryBuilder::push_values() 批量插入。PG 失敗時回退到 JSONL。
//!   Pool 初始化可選 — 無 PG 時引擎正常運行（優雅降級）。

pub mod black_swan_detector;
pub mod context_writer;
pub mod drift_detector;
pub mod experiment_ledger_pg;
pub mod fallback;
pub mod feature_writer;
pub mod market_writer;
pub mod pool;
pub mod quality_writer;
pub mod rest_poller;
pub mod trading_writer;

use openclaw_core::klines::KlineBar;
use serde::Deserialize;

/// Database configuration (added to RuntimeConfig).
/// 資料庫配置（加入 RuntimeConfig）。
#[derive(Debug, Clone, Deserialize)]
pub struct DatabaseConfig {
    /// PostgreSQL connection URL (env OPENCLAW_DATABASE_URL takes precedence).
    /// PG 連接 URL（環境變量 OPENCLAW_DATABASE_URL 優先）。
    #[serde(default = "default_database_url")]
    pub database_url: String,

    /// Connection pool max size / 連接池最大連接數
    #[serde(default = "default_pool_max")]
    pub pool_max_connections: u32,

    /// Connection pool min idle / 連接池最小空閒連接
    #[serde(default = "default_pool_min")]
    pub pool_min_connections: u32,

    /// Connection acquire timeout (ms) / 連接獲取超時（毫秒）
    #[serde(default = "default_connect_timeout")]
    pub connect_timeout_ms: u64,

    /// Market data batch flush interval (ms) — hot / 市場數據批量刷新間隔（熱參數）
    #[serde(default = "default_batch_flush")]
    pub batch_flush_interval_ms: u64,

    /// Feature UPSERT interval (ms) — hot / 特徵 UPSERT 間隔（熱參數）
    #[serde(default = "default_feature_upsert")]
    pub feature_upsert_interval_ms: u64,

    /// PSI drift check interval (seconds) — hot / PSI 漂移檢查間隔（秒，熱參數）
    #[serde(default = "default_drift_check")]
    pub drift_check_interval_secs: u64,

    /// Max consecutive flush failures before JSONL fallback / 最大連續刷新失敗次數
    #[serde(default = "default_max_failures")]
    pub max_flush_failures: u32,

    /// Master switch for DB writes — hot / DB 寫入總開關（熱參數）
    #[serde(default = "default_true")]
    pub db_writes_enabled: bool,

    /// PSI warning threshold / PSI 警告閾值
    #[serde(default = "default_psi_warning")]
    pub psi_warning_threshold: f64,

    /// PSI alert threshold / PSI 警報閾值
    #[serde(default = "default_psi_alert")]
    pub psi_alert_threshold: f64,

    /// ADWIN delta parameter (F2: calibrated for financial data) / ADWIN delta 參數
    #[serde(default = "default_adwin_delta")]
    pub adwin_delta: f64,

    /// ADWIN min observations before detection / ADWIN 最少觀測數
    #[serde(default = "default_adwin_min_width")]
    pub adwin_min_width: u32,

    /// ADWIN consecutive detections required (majority vote) / ADWIN 連續檢測次數（多數票）
    #[serde(default = "default_adwin_consecutive")]
    pub adwin_consecutive_required: u32,

    /// ADWIN burn-in days (log-only, no alerts) / ADWIN 預熱天數（只記錄，不告警）
    #[serde(default = "default_adwin_burnin")]
    pub adwin_burnin_days: u32,
}

fn default_database_url() -> String {
    std::env::var("OPENCLAW_DATABASE_URL").unwrap_or_else(|_| String::new())
}
fn default_pool_max() -> u32 {
    5
}
fn default_pool_min() -> u32 {
    2
}
fn default_connect_timeout() -> u64 {
    5000
}
fn default_batch_flush() -> u64 {
    2000
}
fn default_feature_upsert() -> u64 {
    1000
}
fn default_drift_check() -> u64 {
    300
}
fn default_max_failures() -> u32 {
    3
}
fn default_true() -> bool {
    true
}
fn default_psi_warning() -> f64 {
    0.1
}
fn default_psi_alert() -> f64 {
    0.2
}
fn default_adwin_delta() -> f64 {
    0.05
}
fn default_adwin_min_width() -> u32 {
    100
}
fn default_adwin_consecutive() -> u32 {
    3
}
fn default_adwin_burnin() -> u32 {
    30
}

impl Default for DatabaseConfig {
    fn default() -> Self {
        Self {
            database_url: default_database_url(),
            pool_max_connections: default_pool_max(),
            pool_min_connections: default_pool_min(),
            connect_timeout_ms: default_connect_timeout(),
            batch_flush_interval_ms: default_batch_flush(),
            feature_upsert_interval_ms: default_feature_upsert(),
            drift_check_interval_secs: default_drift_check(),
            max_flush_failures: default_max_failures(),
            db_writes_enabled: default_true(),
            psi_warning_threshold: default_psi_warning(),
            psi_alert_threshold: default_psi_alert(),
            adwin_delta: default_adwin_delta(),
            adwin_min_width: default_adwin_min_width(),
            adwin_consecutive_required: default_adwin_consecutive(),
            adwin_burnin_days: default_adwin_burnin(),
        }
    }
}

/// Messages from tick pipeline to the market data writer task.
/// 從 tick 管線到市場數據寫入任務的消息。
#[derive(Debug, serde::Serialize)]
pub enum MarketDataMsg {
    /// Completed kline bar (on bar close) / 完成的 K 線（收盤時）
    KlineClose {
        symbol: String,
        timeframe: String,
        bar: KlineBar,
    },
    /// 5-second ticker snapshot / 5 秒行情快照
    TickerSnapshot {
        ts_ms: u64,
        symbol: String,
        last_price: f64,
        mark_price: f64,
        index_price: f64,
        best_bid: f64,
        best_ask: f64,
        bid_size: f64,
        ask_size: f64,
        volume_24h: f64,
        turnover_24h: f64,
        spread_bps: f64,
        open_interest: f64,
    },
    /// Orderbook L5 1-minute summary / L5 每分鐘 OB 摘要
    ObSnapshot {
        ts_ms: u64,
        symbol: String,
        imbalance_ratio: f64,
        weighted_mid: f64,
        spread_bps: f64,
        bid_depth_5: f64,
        ask_depth_5: f64,
        depth_ratio: f64,
    },
    /// 1-minute aggregated trades / 每分鐘聚合成交
    TradeAgg1m {
        ts_ms: u64,
        symbol: String,
        buy_volume: f64,
        sell_volume: f64,
        buy_count: i32,
        sell_count: i32,
        large_buy_count: i32,
        large_sell_count: i32,
        vwap: f64,
        max_single_qty: f64,
    },
    /// Liquidation event (F3: was missing) / 清算事件
    Liquidation {
        ts_ms: u64,
        symbol: String,
        side: String,
        qty: f64,
        price: f64,
    },
    /// Funding rate / 資金費率
    FundingRate {
        ts_ms: u64,
        symbol: String,
        funding_rate: f64,
        funding_rate_daily: f64,
    },
    /// Open interest / 未平倉合約
    OpenInterest {
        ts_ms: u64,
        symbol: String,
        open_interest: f64,
        oi_value: f64,
    },
    /// Long-short ratio / 多空比
    LongShortRatio {
        ts_ms: u64,
        symbol: String,
        buy_ratio: f64,
        sell_ratio: f64,
        ratio: f64,
    },
    /// Regime snapshot / Regime 快照
    RegimeSnapshot {
        ts_ms: u64,
        symbol: String,
        timeframe: String,
        regime: String,
        confidence: f64,
    },
    /// Regime transition / Regime 轉換
    RegimeTransition {
        ts_ms: u64,
        symbol: String,
        timeframe: String,
        from_regime: String,
        to_regime: String,
        trigger_reason: String,
    },
}

// ═══════════════════════════════════════════════════════════════════
// Phase 2a: Trading lifecycle messages / 交易生命週期消息
// ═══════════════════════════════════════════════════════════════════

/// Trading lifecycle messages → trading_writer task (Phase 2a).
/// 交易生命週期消息 → trading_writer 任務。
#[derive(Debug, serde::Serialize)]
pub enum TradingMsg {
    /// Signal generated by signal engine / 信號引擎生成的信號
    Signal {
        signal_id: String,
        ts_ms: u64,
        symbol: String,
        strategy_name: String,
        timeframe: String,
        signal_type: String,
        strength: f64,
        context_id: String,
    },
    /// Order intent from strategy / 策略產生的下單意圖
    Intent {
        intent_id: String,
        ts_ms: u64,
        signal_id: String,
        context_id: String,
        symbol: String,
        side: String,
        qty: f64,
        price: f64,
        order_type: String,
        strategy_name: String,
    },
    /// Paper fill result / 紙盤成交結果
    Fill {
        fill_id: String,
        ts_ms: u64,
        order_id: String,
        symbol: String,
        side: String,
        qty: f64,
        price: f64,
        fee: f64,
        realized_pnl: f64,
        strategy_name: String,
        context_id: String,
    },
    /// Position snapshot after fill / 成交後持倉快照
    PositionSnapshot {
        ts_ms: u64,
        symbol: String,
        side: String,
        qty: f64,
        entry_price: f64,
        mark_price: f64,
        unrealized_pnl: f64,
    },
}

/// Decision context snapshot → context_writer task (Phase 2a).
/// 決策上下文快照 → context_writer 任務。
#[derive(Debug)]
pub struct DecisionContextMsg {
    pub context_id: String,
    pub ts_ms: u64,
    pub decision_type: String,
    pub symbol: String,
    pub strategy_name: String,
    // Flat columns / 扁平列
    pub last_price: f64,
    pub spread_bps: f64,
    pub regime_5m: String,
    pub ind_5m_adx: f64,
    pub ind_5m_rsi: f64,
    pub ind_5m_atr_14_pct: f64,
    pub position_side: String,
    pub position_qty: f64,
    pub total_equity: f64,
    pub drawdown_pct: f64,
    // JSONB sections / JSONB 段
    pub indicators_snapshot: serde_json::Value,
    pub position_detail: serde_json::Value,
    pub decision_payload: serde_json::Value,
}

/// Sanitize a float for PG insertion: replace NaN/Inf with None.
/// 清理浮點數用於 PG 插入：替換 NaN/Inf 為 None。
#[inline]
pub fn sanitize_f64(v: f64) -> Option<f64> {
    if v.is_finite() {
        Some(v)
    } else {
        None
    }
}

/// Sanitize a float, returning 0.0 for NaN/Inf (for non-nullable columns).
/// 清理浮點數，NaN/Inf 返回 0.0（用於非空列）。
#[inline]
pub fn sanitize_f64_or_zero(v: f64) -> f64 {
    if v.is_finite() {
        v
    } else {
        0.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_database_config_defaults() {
        let cfg = DatabaseConfig::default();
        assert_eq!(cfg.pool_max_connections, 5);
        assert_eq!(cfg.pool_min_connections, 2);
        assert_eq!(cfg.batch_flush_interval_ms, 2000);
        assert!((cfg.adwin_delta - 0.05).abs() < 1e-10);
        assert_eq!(cfg.adwin_min_width, 100);
        assert_eq!(cfg.adwin_consecutive_required, 3);
        assert_eq!(cfg.adwin_burnin_days, 30);
        assert!(cfg.db_writes_enabled);
    }

    #[test]
    fn test_sanitize_f64() {
        assert_eq!(sanitize_f64(1.5), Some(1.5));
        assert_eq!(sanitize_f64(f64::NAN), None);
        assert_eq!(sanitize_f64(f64::INFINITY), None);
        assert_eq!(sanitize_f64(f64::NEG_INFINITY), None);
    }

    #[test]
    fn test_sanitize_f64_or_zero() {
        assert_eq!(sanitize_f64_or_zero(1.5), 1.5);
        assert_eq!(sanitize_f64_or_zero(f64::NAN), 0.0);
        assert_eq!(sanitize_f64_or_zero(f64::INFINITY), 0.0);
    }
}
