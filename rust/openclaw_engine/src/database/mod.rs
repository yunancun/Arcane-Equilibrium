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

pub mod agent_spine_writer;
pub mod aggregators;
pub mod batch_insert;
pub mod black_swan_detector;
pub mod context_writer;
pub mod decision_feature_evaluation_writer;
pub mod decision_feature_writer;
pub mod drift_detector;
pub mod exit_feature_schema;
pub mod exit_feature_writer;
pub mod experiment_ledger_pg;
pub mod fallback;
pub mod feature_writer;
pub mod lease_transition_writer;
pub mod market_writer;
pub mod migrations;
pub mod outcome_backfiller;
pub mod pool;
pub mod quality_writer;
pub mod rest_poller;
pub mod shadow_exit_writer;
pub mod shadow_fill_writer;
pub mod trading_writer;

use openclaw_core::klines::KlineBar;
use serde::Deserialize;
use std::sync::atomic::{AtomicU64, Ordering};

use crate::secret_env;

/// Database configuration (added to RuntimeConfig).
/// 資料庫配置（加入 RuntimeConfig）。
#[derive(Debug, Clone, Deserialize)]
pub struct DatabaseConfig {
    /// PostgreSQL connection URL (OPENCLAW_DATABASE_URL or OPENCLAW_DATABASE_URL_FILE takes precedence).
    /// PG 連接 URL（OPENCLAW_DATABASE_URL 或 OPENCLAW_DATABASE_URL_FILE 優先）。
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
    secret_env::var_or_file("OPENCLAW_DATABASE_URL").unwrap_or_default()
}
fn default_pool_max() -> u32 {
    20
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
    // GAP: Liquidation variant removed 2026-04-06 — Bybit V5 `liquidation.{symbol}`
    // topic poisoned the entire WS connection (commit 29fc1ef) and no downstream
    // consumer exists. The market.liquidations PG table is reserved for re-enable
    // after the topic is verified safe and a real consumer materializes.
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
        /// Engine mode: "paper", "demo", or "live" / 引擎模式
        engine_mode: String,
        /// Strategy metadata snapshot — populates trading.intents.details
        /// (FUP-8: satisfy root principle #8 "trades must be explainable").
        /// 策略詮釋快照，寫入 trading.intents.details（根原則 #8 交易可解釋）。
        details: Option<serde_json::Value>,
    },
    /// Fill result (paper/demo/live) / 成交結果（紙盤/演示/實盤）
    Fill {
        fill_id: String,
        ts_ms: u64,
        order_id: String,
        symbol: String,
        side: String,
        qty: f64,
        price: f64,
        fee: f64,
        /// Effective taker fee rate at execution time (Bybit per-symbol).
        /// 成交時的有效 taker 費率（Bybit per-symbol）。
        fee_rate: f64,
        /// Dispatch-time execution reference price. For taker orders this is
        /// same-side BBO (Buy→ask, Sell→bid); fallback sources are tagged.
        /// 送單時刻執行參考價。taker 使用同側 BBO；fallback 以 source 標記。
        reference_price: Option<f64>,
        /// Timestamp of the reference price in milliseconds.
        /// 參考價時間戳（毫秒）。
        reference_ts_ms: Option<u64>,
        /// Reference source, e.g. "bbo_same_side" or "dispatch_last_fallback".
        /// 參考價來源。
        reference_source: Option<String>,
        /// Signed adverse execution slippage in bps. Positive is worse.
        /// 有符號 adverse execution slippage（bps），正值代表更差。
        slippage_bps: Option<f64>,
        /// Liquidity role of this fill: maker/taker/unknown/paper_sim.
        /// 成交流動性角色。
        liquidity_role: Option<String>,
        /// Time between order registration and execution update.
        /// 從訂單註冊到成交推送的延遲。
        fill_latency_ms: Option<u64>,
        realized_pnl: f64,
        strategy_name: String,
        context_id: String,
        /// EDGE-P3-1 R2: context_id of the entry that opened this position.
        /// Populated on close fills (pulled from PaperPosition.entry_context_id);
        /// empty string on open fills. Persisted to trading.fills.entry_context_id
        /// as the ML training JOIN key to learning.decision_features.
        /// EDGE-P3-1 R2：開此倉 entry 的 context_id；平倉 fill 填入，開倉 fill 為空。
        entry_context_id: String,
        /// Engine mode: "paper", "demo", or "live" / 引擎模式
        engine_mode: String,
        /// INFRA-PREBUILD-1 Part A (2026-04-23): ExitSource tag from Combine
        /// Layer — populated on close fills only. None = open fill OR legacy
        /// exit path not routed through Combine Layer (HARD STOP / TRAILING /
        /// TIME / TAKE PROFIT / DRAWDOWN / CONSECUTIVE LOSS / DAILY LOSS —
        /// per DUAL-TRACK-EXIT-1 design these are P0 hard-stops, not
        /// physical-lock optimisations, so they bypass Combine Layer).
        /// Some(tag) = "Physical" | "Hybrid" | "ML" | "Disabled"
        /// (stable dictionary aligned with `combine_layer::ExitSource::as_tag`
        /// and `trading.fills.exit_source` CHECK constraint in V021).
        /// Phase 1a always "Physical" on PHYS-LOCK path (ml_opt=None).
        /// INFRA-PREBUILD-1 A 部（2026-04-23）：Combine Layer 的 ExitSource 標籤，
        /// 僅在 close fill 時填入。None = open fill 或未走 Combine Layer 的
        /// 退場路徑（HARD STOP / TRAILING / TIME / TP / DRAWDOWN / CONSECUTIVE
        /// LOSS / DAILY LOSS 皆為 P0 硬止損，DUAL-TRACK-EXIT-1 設計上 bypass
        /// Combine Layer）。Some 值為 "Physical" / "Hybrid" / "ML" /
        /// "Disabled"，與 V021 fills CHECK 字典對齊。Phase 1a PHYS-LOCK 路徑
        /// 恆為 "Physical"（ml_opt=None）。
        exit_source: Option<String>,
        /// V033 (2026-04-29) — Free-text close reason. Companion field to
        /// `strategy_name` which is now restricted to 5 entry-strategy enum
        /// values (ma_crossover/bb_reversion/bb_breakout/grid_trading/funding_arb)
        /// + system paths (unattributed:bybit_auto / risk_close:halt_session).
        ///
        /// - Entry path → `None` (always; entry fills carry no exit semantics).
        /// - Close path → `Some(reason)` populated by
        ///   `helpers::build_close_tags(entry_strategy, reason)` and equivalent
        ///   call sites (W1-T2: 16 emit points). Examples: "TRAILING STOP: peak
        ///   8.46% - current 6.46% = ...", "phys_lock_gate4_giveback",
        ///   "ma_reverse_cross", "fast_track".
        ///
        /// W1-T2: close emitters normalize legacy close tags through
        /// `build_close_tags_from_legacy`; entry fills still write `None`.
        ///
        /// V033（2026-04-29）— 自由文字退場原因。strategy_name 同步收斂為
        /// 5 個入場策略 enum 名 + 系統路徑。entry path 永 None；close path 由
        /// `build_close_tags_from_legacy` 等 close emitter 產出；entry fill
        /// 仍寫 None。
        exit_reason: Option<String>,
    },
    /// Funding settlement from exchange execution stream.
    /// 交易所 execution stream 推送的資金費結算。
    FundingSettlement {
        settlement_id: String,
        ts_ms: u64,
        exec_id: String,
        symbol: String,
        side: String,
        amount: f64,
        fee_currency: String,
        exec_value: f64,
        exec_price: f64,
        exec_qty: f64,
        strategy_name: String,
        engine_mode: String,
        raw: Option<serde_json::Value>,
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
        /// Engine mode: "paper", "demo", or "live" / 引擎模式
        engine_mode: String,
    },
    /// Exchange order record — emitted when order enters Working state on exchange.
    /// 訂單進入交易所 Working 狀態時發出，寫入 trading.orders。
    Order {
        order_id: String,
        ts_ms: u64,
        symbol: String,
        /// "Buy" or "Sell" / 買或賣
        side: String,
        /// "Market" or "Limit" / 市價或限價
        order_type: String,
        /// Bybit timeInForce, e.g. "GTC" / "PostOnly" / Bybit timeInForce。
        time_in_force: Option<String>,
        qty: f64,
        strategy_name: String,
        /// True if this is a close/reduce order / 是否為平倉單
        is_close: bool,
        /// Engine mode: "paper", "demo", or "live" / 引擎模式
        engine_mode: String,
    },
    /// Order status transition — emitted on fill, cancel, or rejection.
    /// 訂單狀態轉換事件，成交 / 撤銷 / 拒絕時發出，寫入 trading.order_state_changes。
    OrderStateChange {
        order_id: String,
        ts_ms: u64,
        from_status: Option<String>,
        to_status: String,
        filled_qty: Option<f64>,
        avg_price: Option<f64>,
        reason: Option<String>,
        /// Engine mode: "paper", "demo", or "live" / 引擎模式
        engine_mode: String,
    },
    /// Guardian risk verdict for a trade intent (DB-RW: missing wiring fix).
    /// Guardian 對交易意圖的風控裁定（DB-RW：補充缺失的接線）。
    RiskVerdict {
        verdict_id: String,
        ts_ms: u64,
        intent_id: String,
        context_id: String,
        symbol: String,
        /// "Approved", "Modified", or "Rejected" / 批准、修改或拒絕
        verdict: String,
        risk_score: f64,
        risk_level: Option<String>,
        checks_passed: Vec<String>,
        checks_failed: Vec<String>,
        reasons: Vec<String>,
        modified_qty: Option<f64>,
        /// Engine mode: "paper", "demo", or "live" / 引擎模式
        engine_mode: String,
    },
    /// Scanner cycle snapshot for audit attribution.
    /// Scanner 掃描週期快照，用於審計與交易歸因。
    ScannerSnapshot {
        scan_id: String,
        ts_ms: u64,
        active_symbols: Vec<String>,
        added: Vec<String>,
        removed: Vec<String>,
        rejected_count: i64,
        scan_duration_ms: i64,
        candidates: serde_json::Value,
        config: serde_json::Value,
    },
    /// Advisory scanner decay evidence. This is never a close/reduce command.
    /// scanner decay advisory evidence；絕不是平倉/減倉命令。
    ScannerOpportunityDecay {
        decay: crate::scanner::types::OpportunityDecay,
    },
}

static TRADING_WRITER_DROP_TOTAL: AtomicU64 = AtomicU64::new(0);

pub fn trading_writer_drop_total() -> u64 {
    TRADING_WRITER_DROP_TOTAL.load(Ordering::Relaxed)
}

pub fn try_send_trading_msg(
    tx: &tokio::sync::mpsc::Sender<TradingMsg>,
    msg: TradingMsg,
    label: &'static str,
) -> bool {
    match tx.try_send(msg) {
        Ok(()) => true,
        Err(e) => {
            let total = TRADING_WRITER_DROP_TOTAL.fetch_add(1, Ordering::Relaxed) + 1;
            tracing::warn!(
                label = label,
                total_dropped = total,
                error = %e,
                "trading writer channel send failed — row not queued \
                 / trading writer channel 發送失敗 — row 未入隊"
            );
            false
        }
    }
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
    /// Engine mode: "paper", "demo", or "live" / 引擎模式
    pub engine_mode: String,
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
    // 4-18 / Phase 4 wiring columns (V009 ADD + V003 news columns).
    // 4-18 / Phase 4 接線欄位（V009 新增 + V003 既有新聞欄位）。
    // Producer wiring lives in W4 sweep; here we only expose the consumer-side
    // capability. Default None → INSERT writes SQL NULL.
    // Producer 接線由 W4 sweep 處理；本處僅暴露 consumer 側寫入能力，
    // 預設 None → INSERT 寫 SQL NULL。
    /// V009 ADD: FK-ish link to claude_directive emission (nullable).
    /// V009 新增：關聯到 Claude 指令發射（可空）。
    pub claude_directive_id: Option<i32>,
    /// V009 ADD: LinUCB arm identifier chosen at decision time.
    /// V009 新增：決策時刻選中的 LinUCB arm 標識。
    pub linucb_arm_id: Option<String>,
    /// V009 ADD: LinUCB upper confidence bound at selection (REAL → f64).
    /// V009 新增：選擇時的 LinUCB 置信上界（REAL → f64）。
    pub linucb_confidence_bound: Option<f64>,
    /// V003 existing: news severity (0.0–1.0 scale).
    /// V003 既有：新聞嚴重度（0.0–1.0 尺度）。
    pub news_severity: Option<f32>,
    /// V003 existing: hours since last major news event.
    /// V003 既有：距上次重大新聞的小時數。
    pub hours_since_last_major_news: Option<f64>,
}

/// Decision feature snapshot → decision_feature_writer task (EDGE-P3-1 Step 7a).
/// 決策特徵快照 → decision_feature_writer 任務。
///
/// Each message produces one row in `learning.decision_features` (PK=context_id).
/// `label_net_edge_bps` starts NULL and is populated later by
/// `edge_label_backfill.py` once the position closes. The training loop in
/// `program_code/ml_training/parquet_etl.py::load_training_data()` only returns
/// labelled rows, so partial inserts are safe.
/// 每條訊息在 `learning.decision_features` 產生一列（PK=context_id）。
/// `label_net_edge_bps` 初為 NULL，由 `edge_label_backfill.py` 於倉位結算後填入。
#[derive(Debug)]
pub struct DecisionFeatureMsg {
    pub context_id: String,
    pub ts_ms: u64,
    /// "paper" | "demo" | "live" — isolates training per engine.
    /// "paper" | "demo" | "live" — 按引擎隔離訓練集。
    pub engine_mode: String,
    pub strategy_name: String,
    pub symbol: String,
    /// +1 long / -1 short (short i8 maps to SQL SMALLINT).
    /// +1 多 / -1 空 (i8 → SQL SMALLINT)。
    pub side: i8,
    /// Schema version tag ("v1"); matches `FEATURE_SCHEMA_VERSION`.
    /// Schema 版本標記 ("v1")，與 `FEATURE_SCHEMA_VERSION` 同。
    pub feature_schema_version: String,
    /// sha256 of ordered feature-name list — detects train/serve skew.
    /// 特徵名有序列表 sha256，偵測 train/serve 漂移。
    pub feature_schema_hash: String,
    /// Stage 0: alias for schema hash. Stage 2 (ML-MIT) splits when formula drifts.
    /// Stage 0: 與 schema_hash 相同。Stage 2 ML-MIT 公式漂移時分叉。
    pub feature_definition_hash: String,
    /// Pre-serialized JSONB produced by `FeatureVectorV1::to_jsonb()`.
    /// Kept as String to avoid re-parsing on the hot path; the writer passes
    /// it through `sqlx::types::Json::<serde_json::Value>` once.
    /// `FeatureVectorV1::to_jsonb()` 預序列化字串；writer 走一次 JSONB cast。
    pub features_jsonb: String,

    // ── W-AUDIT-4b-M3 (2026-05-09): negative-label carrier fields ──
    // Producer 端 `emit_decision_feature_intent_rejected` 在 governance / cost-gate
    // reject path 寫入下列三欄。Writer 端依 `label_close_tag.is_some()` 分流：
    //   Some → reject 變體 INSERT（連 label 三欄 + label_filled_at = NOW()）
    //   None → intent-only 變體 INSERT（保 V017 default NULL，由 backfill 補）
    //
    // 三欄全 None / false 即為 M1 success-path 的 intent-only emit（向後相容）。
    /// Reject 路徑的 close_tag 字串（固定 "rejected_governance"）。
    /// `Some` 觸發 writer reject 變體 INSERT；`None` 走 intent-only 路徑（V017 default）。
    pub label_close_tag: Option<String>,
    /// Reject 路徑的 net_edge_bps（reject 沒成交，固定 0.0）。
    /// 與 `label_close_tag` 配對；`None` 走 intent-only（V017 default NULL）。
    pub label_net_edge_bps: Option<f64>,
    /// Writer 是否用 server-side `now()` 寫 `label_filled_at` 欄位。
    /// `true` → reject 路徑（emit 時間戳對 backfill 無意義，用 NOW() 標記寫入時刻）
    /// `false` → intent-only 路徑（label_filled_at 保 NULL，待 backfill 回填）
    pub label_filled_at_now: bool,

    // ── W6-3c V086 (2026-05-10): governance reject/close reason enum 兩欄 ──
    // Producer 端 `emit_decision_feature_intent_rejected` 在 reject path 把
    // free-form `reject_reason: &str` 映射為 V086 §4.1 12 enum 之一寫進
    // `reject_reason_code`；`close_reason_code` 在 reject path 永遠 None
    // （V086 §3 互斥不變式：reject_reason_code IS NOT NULL ⇔ close_reason_code IS NULL）。
    //
    // intent-only path：兩欄全 None；後續 close 走 backfill / W6-3d Python 端
    // dual-write 到 close_reason_code。
    //
    // Source spec：
    //   - PA W6-3b enum spec final §4.1（12 reject + 14 close）
    //     docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_3b_enum_spec_final_pa_decision.md
    //   - V086 SQL CHECK constraint chk_reject_reason_code_enum / chk_close_reason_code_enum
    //     sql/migrations/V086__governance_reject_close_reason_code.sql
    //   - reject_reason_code mapping function
    //     intent_processor::reject_reason_code::map_reject_reason_to_code
    /// V086 12 reject enum 之一（11 + reject_other catch-all）。
    /// `Some` 觸發 writer reject 變體 INSERT；`None` 走 intent-only 路徑。
    /// 與 `close_reason_code` 互斥（per V086 §3 不變式）。
    pub reject_reason_code: Option<String>,
    /// V086 14 close enum 之一（13 + close_other catch-all）。
    /// 當前 producer reject path 永遠 None；future close path 由 W6-3d Python
    /// 端 `edge_label_backfill.py` dual-write，或在 fill 後在 close handler 寫入。
    pub close_reason_code: Option<String>,
}

/// Decision feature evaluation snapshot → decision_feature_evaluation_writer task
/// (W-AUDIT-4b-M1 split, V082).
/// 決策特徵評估快照 → decision_feature_evaluation_writer 任務（W-AUDIT-4b-M1 拆表）。
///
/// 每條訊息在 `learning.decision_features_evaluations` 產生一列
/// (PK=evaluation_id BIGSERIAL)。與 `DecisionFeatureMsg` 不同，此訊息對應每次
/// `evaluate_predictor_gate` 評估（無論該 intent 是否真實 emit），用作 producer
/// 偵錯與 gate 行為觀測。**禁作 ML training data**：pool 含 reject path 污染。
///
/// 與 `DecisionFeatureMsg` 主要差異：
///   - 無 dedup（同 context_id 可多次 evaluate；BIGSERIAL PK）
///   - 攜 `evaluation_outcome`（PredictorAction 結果字串）
///   - 攜 `evidence_source_tier`（CLAUDE.md §九 Non-training surfaces 標準）
///   - 攜 optional `entry_context_id`（M2 trigger 鋪路；當前一律 NULL）
///
/// Spec: docs/CCAgentWorkSpace/PA/workspace/reports/
///       2026-05-09--full_dispatch_engineering_plan.md §2.5 B-M1
///       sql/migrations/V082__decision_features_evaluations_split.sql
#[derive(Debug)]
pub struct DecisionFeatureEvaluationMsg {
    pub context_id: String,
    pub ts_ms: u64,
    /// "paper" | "demo" | "live" | "live_demo"
    pub engine_mode: String,
    pub strategy_name: String,
    pub symbol: String,
    /// +1 long / -1 short (i8 → SQL SMALLINT)
    pub side: i8,
    pub feature_schema_version: String,
    pub feature_schema_hash: String,
    pub feature_definition_hash: String,
    pub features_jsonb: String,
    /// V082 §CHECK：accept | reject | reject_add | shadow_fill |
    /// fallback_use_legacy | fallback_fail_closed | use_legacy_no_predictor
    /// PredictorAction 結果字串（V082 CHECK enum）
    pub evaluation_outcome: String,
    /// V082 §CHECK：evaluation_log | shadow_synthetic
    /// CLAUDE.md §九 Non-training surfaces 標準
    pub evidence_source_tier: String,
    /// M2 trigger 鋪路欄位；M1 producer 一律 None
    pub entry_context_id: Option<String>,
}

/// Shadow-fill snapshot → shadow_fill_writer task (EDGE-P3-1 Step 7c).
/// ε-greedy paper exploration fill (§7.3 Step 7, F4+U3): predictor rejected on
/// cost but the exploration coin flip passed, so a synthetic observation row
/// lands in `learning.decision_shadow_fills`. These rows are permanently
/// excluded from label backfill (see `parquet_etl.py` §5.1 WHERE clause) and
/// DB-level CHECK keeps them paper-only.
/// Shadow-fill 快照 → shadow_fill_writer（EDGE-P3-1 Step 7c）。
/// ε-greedy paper 探索 fill：預測器拒絕但探索通過時，合成觀測列寫入
/// `learning.decision_shadow_fills`；永久排除於 label 回填（§5.1 WHERE），
/// DB CHECK 保證 paper-only。
#[derive(Debug)]
pub struct ShadowFillMsg {
    pub context_id: String,
    pub ts_ms: u64,
    /// Always "paper" — enforced by V017 DDL CHECK. Writer logs+skips if
    /// anything else leaks through (second-line defense).
    /// 固定為 "paper"（V017 DDL CHECK 強制）；writer 亦檢測（第二道防線）。
    pub engine_mode: String,
    pub strategy_name: String,
    pub symbol: String,
    /// +1 long / -1 short (i8 → SQL SMALLINT).
    /// +1 多 / -1 空 (i8 → SQL SMALLINT)。
    pub side: i8,
    /// Pre-serialized JSONB from `FeatureVectorV1::to_jsonb()`.
    /// `FeatureVectorV1::to_jsonb()` 預序列化字串。
    pub features_jsonb: String,
    /// Quantile forecasts from the predictor at gate eval time.
    /// gate 評估時預測器輸出的 quantile forecast。
    pub predicted_q10: f32,
    pub predicted_q50: f32,
    pub predicted_q90: f32,
    /// Round-trip cost in bps at open (fee + slippage).
    /// 開倉時來回成本（費率 + 滑點），單位 bps。
    pub cost_bps_at_open: f64,
}

/// Exit feature row → exit_feature_writer task (EXIT-FEATURES-TABLE-1).
/// DUAL-TRACK-EXIT-1 Track P/L feature label written on every position exit.
/// 退場特徵列 → exit_feature_writer 任務。每筆退場寫入一列。
///
/// Each message produces one row in `learning.exit_features` (PK=(context_id, ts)).
/// `context_id` is the entry context_id — pairs with `learning.decision_features`
/// (PK=context_id) for ML training joins (entry snapshot ↔ exit trajectory).
/// 每條訊息在 `learning.exit_features` 產生一列（PK=(context_id, ts)）。
/// context_id 為開倉時的 context_id，與 `learning.decision_features` 配對，
/// 供 ML 訓練以 JOIN 合併 entry snapshot 與 exit trajectory。
///
/// Spec: docs/worklogs/2026-04-18-2--exit_features_table_design.md
#[derive(Debug, Clone)]
pub struct ExitFeatureRow {
    /// Aligned with entry-time decision_features.context_id.
    /// 與開倉 decision_features.context_id 對齊。
    pub context_id: String,
    /// Exit timestamp (ms since epoch) / 退場時刻（毫秒）
    pub ts_ms: i64,
    /// "paper" | "demo" | "live_demo" | "live" / 引擎模式
    pub engine_mode: String,
    pub strategy_name: String,
    pub symbol: String,
    /// +1 long / -1 short (i16 maps to SQL SMALLINT).
    /// +1 多 / -1 空。
    pub side: i16,

    // ── 7-dim Track P features / 7 維 Track P 特徵 ─────────────
    /// Estimated net edge at exit (bps) — from JS edge_estimates + cost_gate.
    /// 退場時估計 net edge (bps)。
    pub est_net_bps: Option<f32>,
    /// Max favorable pnl since entry (%). Tracked tick-by-tick on PaperPosition.
    /// 自開倉以來 max favorable pnl 百分比。
    pub peak_pnl_pct: Option<f32>,
    /// ATR / price at exit / 當時 ATR/price
    pub atr_pct: Option<f32>,
    /// (peak - current) / ATR — normalized giveback / 歸一化回吐幅度
    pub giveback_atr_norm: Option<f32>,
    /// Ms since peak was reached / 自 peak 達到以來的毫秒數
    pub time_since_peak_ms: Option<i64>,
    /// Short-window price rate-of-change (default 300 ms) / 短窗 ROC
    pub price_roc_short: Option<f32>,
    /// Seconds since entry fill / 自 entry 以來的秒數
    pub entry_age_secs: Option<f32>,

    // ── Exit meta / 退場元數據 ────────────────────────────────
    /// 'Physical' | 'Hybrid' | 'ML-shadow' | 'TimeStop' | 'HardStop' ...
    pub exit_source: Option<String>,
    /// Specific trigger rule name (e.g. 'PHYS-LOCK', 'COST-EDGE').
    /// 具體觸發規則名。
    pub exit_trigger_rule: Option<String>,
    /// Ex-post realized net bps (label vs est_net_bps prediction).
    /// 實際成交 net bps，作為 est_net_bps 的 ex-post label。
    pub realized_net_bps: Option<f32>,

    // ── Provenance / 來源可追溯 ────────────────────────────────
    /// Schema version tag ("v1.0") / Schema 版本標記
    pub feature_schema_version: String,
    /// Hash of the ordered feature-name list — detects schema drift.
    /// 欄位結構 hash，偵測 schema 漂移。
    pub feature_schema_hash: String,
}

/// Combine Layer exit-time shadow observation row → shadow_exit_writer.
/// Combine Layer 退場時刻 shadow 觀測列 → shadow_exit_writer。
///
/// INFRA-PREBUILD-1 Part A (2026-04-23): Phase 2 shadow mode writes one row
/// per close fill when `RiskConfig.exit.shadow_enabled=true`, capturing the
/// divergence (or agreement) between Track P physical-only decision and the
/// Combine Layer output that also considered (mock or real) ML inference.
///
/// Target table: `learning.decision_shadow_exits` (V021 migration).
/// Pure observation — never enters label backfill. Distinct from
/// `decision_shadow_fills` (V017, entry-time ε-greedy, paper-only).
///
/// INFRA-PREBUILD-1 A 部（2026-04-23）：Phase 2 shadow mode 下，每筆退場 fill
/// 寫一列到 `learning.decision_shadow_exits`，記錄純 Track P 決策 vs
/// Combine Layer（含 mock/real ML inference）的一致性或分歧。純觀測，
/// 不入 label 回填；與 V017 的 `decision_shadow_fills`（entry-time ε-greedy、
/// paper-only）語意不同。
#[derive(Debug, Clone)]
pub struct ShadowExitMsg {
    /// Entry-time context_id / 開倉 context_id
    pub context_id: String,
    /// Close fill timestamp (ms since epoch) / 退場時刻（毫秒）
    pub ts_ms: i64,
    /// 'paper' | 'demo' | 'live' | 'live_demo' — unlike shadow_fills V017
    /// this accepts demo (主力驗證環境). CHECK constraint enforces.
    /// 'paper'/'demo'/'live'/'live_demo' — 與 V017 shadow_fills 不同，
    /// 本表接受 demo（主力驗證環境）；CHECK 在 DB 層守。
    pub engine_mode: String,
    pub strategy_name: String,
    pub symbol: String,
    /// +1 long / -1 short (i16 → SMALLINT)
    pub side: i16,

    // ── Track P physical-only decision / Track P 純物理層決策 ──
    /// 'Lock' | 'Hold' — what Track P alone would have produced.
    /// 'Lock' | 'Hold' — 僅 Track P 會產生的結果。
    pub physical_action: String,
    /// Trigger reason (e.g. 'phys_lock_gate4_giveback') or None for Hold.
    /// 觸發原因字串；Hold 時可能為 None。
    pub physical_reason: Option<String>,

    // ── ML inference snapshot (None when ml_opt=None) ──
    /// None = Phase 1a default / ML disabled / model not loaded.
    /// 非空 = Phase 2 shadow mock 或真實 ONNX.
    pub ml_model_id: Option<String>,
    pub ml_score: Option<f64>,
    pub ml_age_secs: Option<i64>,
    pub ml_confidence: Option<f64>,

    // ── Combine Layer final decision / Combine Layer 最終決策 ──
    /// 'Physical' | 'Hybrid' | 'ML' | 'Disabled'
    pub exit_source: String,
    /// TRUE when Combine output != what Physical-only would have produced.
    /// Key audit metric for Phase 2 shadow agreement ratio target ≥60%.
    /// TRUE 當 Combine 結果 ≠ Physical-only 結果；Phase 2 一致性目標 ≥60%。
    pub disagreed: bool,
    /// Human-readable reason when disagreed=true (may be None when agreed).
    /// 分歧原因（disagreed=true 時）；一致時可為 None。
    pub disagreement_reason: Option<String>,

    // ── Combine config snapshot at decision time (debug on demotion) ──
    pub ml_confirm_threshold: Option<f64>,
    pub ml_override_high: Option<f64>,
    pub ml_veto_low: Option<f64>,
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
        assert_eq!(cfg.pool_max_connections, 20);
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
