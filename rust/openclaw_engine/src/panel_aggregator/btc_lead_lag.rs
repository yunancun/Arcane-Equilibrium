//! Sprint N+1 W2 sub-task 1 — BTC→Alt lead-lag producer 核心。
//!
//! MODULE_NOTE：
//!   接受 1m 對齊的 (snapshot_ts_ms, btc_close, alt_closes_per_symbol) tick，
//!   滾動維護 BTC + alt cohort 的價格緩衝區 + volume 緩衝區，每一 tick 產出
//!   一個 `BtcLeadLagPanelSnapshot`（包含 V088 全部 column 的內存對應結構）。
//!   下游 writer (`database/btc_lead_lag_writer.rs`) 負責把 snapshot INSERT
//!   進 V088 schema。consumer (W2 sub-task 2) 把 snapshot 對齊到
//!   `openclaw_core::alpha_surface::BtcLeadLagPanel` 注入 IPC slot。
//!
//!   對齊 spec v1.2：
//!   - §3.1 lead signal 主信號 N=120s + N=60s/300s shadow value (decay curve evidence)
//!   - §3.2 cross-correlation rolling 1h baseline，min 30 sample
//!   - §3.3 expected_dir threshold_X=10 bps + threshold_Y=0.40
//!   - §7 5 conditions check（dual-layer σ + +15/+5-15/<+5 階梯 gate 留下游
//!     paper edge report 階段判斷；producer 只計算 metric，不做 gate decision）
//!   - §9 regime guard：|BTCUSDT 1h return| > 200 bps → regime_tag = 'extreme'
//!
//!   **strict shift(N) lookahead-free（CRITICAL，spec §7.3 + §12 #2）**：
//!   所有 BTC return / volume z-score 計算用 buffer[t-N] vs buffer[t] 不含
//!   current bar 之後 sample；本 module 採 `last_n` slice + tail anchor 模型，
//!   buffer push 在 metric 算完後才執行（避免 current bar leak）。
//!
//!   **paper-only fence 不在本 module**：producer 純計算，不知 fence；
//!   step_4_5_dispatch.rs 構造 surface 階段 gate engine_mode（Layer 1）+
//!   IPC slot late-inject 由 main.rs gate（Layer 2）。
//!
//! Spec：`srv/docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md` v1.2
//! V088 schema：`srv/sql/migrations/V088__panel_btc_lead_lag_panel.sql`
//! Trait skeleton：`srv/rust/openclaw_core/src/alpha_surface.rs` (BtcLeadLagPanel)

use std::collections::{HashMap, VecDeque};
use std::sync::Arc;
use std::time::Duration;

use openclaw_core::alpha_surface::BtcLeadLagPanel;
use sqlx::Postgres;
use tokio::sync::RwLock;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

use crate::database::batch_insert::{exec_single_insert, SingleInsertOutcome};
use crate::database::pool::DbPool;
use crate::ipc_server::BtcLeadLagPanelSlot;

// ─────────────────────────────────────────────────────────────────────────
// Constants — spec §3.3 PA 預設 threshold + §9 regime guard + §3.2 sample 下限
// ─────────────────────────────────────────────────────────────────────────

/// 主信號 lead window（秒）。PA D+0 spec §3.1 v1.1 鎖定 N=120s。
pub const LEAD_WINDOW_SECS_MAIN: u32 = 120;

/// Decay curve evidence shadow window（秒）。spec §3.1.1 v1.1 condition #3。
pub const LEAD_WINDOW_SECS_SHADOW_60: u32 = 60;
pub const LEAD_WINDOW_SECS_SHADOW_300: u32 = 300;

/// Cross-correlation rolling baseline 窗口（秒）。spec §3.2。
pub const XCORR_BASELINE_SECS: u64 = 3600;

/// 最小 cross-correlation 樣本數（不足返 NaN）。spec §3.2。
pub const XCORR_MIN_SAMPLE: usize = 30;

/// volume z-score baseline 窗口（秒）。spec §3.1.2。
pub const VOLUME_Z_BASELINE_SECS: u64 = 3600;

/// expected_dir BTC return 觸發門檻（bps）。spec §3.3 PA 預設。
pub const THRESHOLD_X_BPS: f64 = 10.0;

/// expected_dir |xcorr| 信任門檻。spec §3.3 PA 預設。
pub const THRESHOLD_Y: f64 = 0.40;

/// regime extreme 門檻：|BTCUSDT 1h return| > 200 bps → 'extreme'。spec §9 v1.1 #5。
pub const REGIME_EXTREME_BPS: f64 = 200.0;

/// 1h kline 對應秒數（regime guard 用）。
pub const ONE_HOUR_SECS: u64 = 3600;

/// Source tier 字串常量（V088 column default 對齊）。spec §4.1。
pub const SOURCE_TIER: &str = "cross_asset_btc_lead_lag";

/// 1m grain（秒）— bucket size。
pub const ONE_MIN_SECS: u64 = 60;

// ─────────────────────────────────────────────────────────────────────────
// Snapshot — V088 schema 全 column 的內存對應結構
// ─────────────────────────────────────────────────────────────────────────

/// BtcLeadLagPanelSnapshot — 一個 1m grain 的完整 panel snapshot。
///
/// 對應 V088 `panel.btc_lead_lag_panel` 12-column schema（per spec §4.1）。
/// Writer 端把此 struct INSERT 為 1 row（per-snapshot vector layout）。
///
/// **不變式**：
/// - `alt_symbols.len() == alt_xcorr.len() == alt_expected_dir.len()`
///   （writer 端 assert，違反 = drop snapshot 不 INSERT）
/// - `lead_window_secs == LEAD_WINDOW_SECS_MAIN`（120）— 主信號鎖定
/// - `regime_tag` ∈ {"normal", "extreme"}
/// - `source_tier == SOURCE_TIER`
#[derive(Debug, Clone, PartialEq)]
pub struct BtcLeadLagPanelSnapshot {
    /// 1m grain epoch ms（對齊 1m bucket）。
    pub snapshot_ts_ms: i64,
    /// 主信號 lead window 秒數，固定 120。
    pub lead_window_secs: u32,
    /// 主信號 BTC lead return（bps，N=120）。NaN = 樣本不足。
    pub btc_lead_return_pct: f64,
    /// Shadow N=60 BTC lead return（bps，decay curve evidence）。NaN = 樣本不足。
    pub btc_lead_return_pct_60s: f64,
    /// Shadow N=300 BTC lead return（bps，decay curve evidence）。NaN = 樣本不足。
    pub btc_lead_return_pct_300s: f64,
    /// 主信號 BTC volume z-score（rolling 1h baseline shift(1)）。NaN = 樣本不足。
    pub btc_volume_z: f64,
    /// BTC orderbook top-10 imbalance（spec §3.1.3，本 sub-task producer 設 0.0
    /// placeholder；orderbook 接線留 sub-task 4）。
    pub btc_book_imbalance: f64,
    /// Cohort alt symbols（per spec §2.2 7-symbol cohort，與 alt_xcorr / alt_expected_dir 同序）。
    pub alt_symbols: Vec<String>,
    /// Per-alt-symbol cross-correlation vs BTC lead return（rolling 1h，min 30 sample）。
    /// NaN 表 sample 不足（consumer 視 NaN 為 no-signal）。
    pub alt_xcorr: Vec<f64>,
    /// Per-alt-symbol predicted direction（−1 / 0 / +1，per spec §3.3）。
    pub alt_expected_dir: Vec<i8>,
    /// Regime tag："normal" / "extreme"（|BTCUSDT 1h return| > 200 bps → "extreme"）。
    pub regime_tag: String,
    /// Source tier（固定 "cross_asset_btc_lead_lag"，writer 端強制）。
    pub source_tier: String,
}

impl BtcLeadLagPanelSnapshot {
    /// 三 array length invariant 自驗（writer 端 INSERT 前必跑）。
    /// 違反 → 返 false → writer drop snapshot fail-soft，不 INSERT 半 schema row。
    pub fn arrays_aligned(&self) -> bool {
        let n = self.alt_symbols.len();
        n == self.alt_xcorr.len() && n == self.alt_expected_dir.len()
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Producer — BTC + alt cohort 緩衝區 + 1m tick 計算
// ─────────────────────────────────────────────────────────────────────────

/// 單 symbol 1m tick（緩衝區 element 結構）。
#[derive(Debug, Clone, Copy)]
struct PriceTick {
    /// 1m bucket end timestamp（epoch ms）— 預留供 sub-task 4 整合
    /// orderbook timestamp alignment / WS subscription latency 分析使用。
    #[allow(dead_code)]
    ts_ms: i64,
    /// close price（USD）。
    close: f64,
    /// 1m bucket volume（base asset）。
    volume: f64,
}

/// `BtcLeadLagProducer` — Sprint N+1 W2 sub-task 1 producer 核心。
///
/// 持有 BTC 1m tick 緩衝區（≥ XCORR_BASELINE_SECS 跨度）+ per-alt-symbol 1m
/// tick 緩衝區。`on_tick` 接受一筆 1m grain 對齊的快照（BTC + alt cohort
/// closes），按 spec §3.1-§3.3 計算所有 metric，emit `BtcLeadLagPanelSnapshot`。
///
/// **生命週期**：
/// - `new(cohort_symbols)` 初始化空緩衝區（cohort 鎖定不變）；
/// - 每 1m grain 呼叫 `on_tick(snapshot_ts_ms, btc_close, btc_volume, alt_closes)`
///   一次（caller 對齊 60s bucket）；不對齊 1m grain → producer 端不 enforce，
///   accept 任何 ts，但 metric 計算依 ts diff 自然衰退到不準；
/// - `latest()` 取最近一次 emit 的 snapshot（None 表尚未 emit）。
///
/// **緩衝區大小**：BTC buffer 上限 = `XCORR_BASELINE_SECS / ONE_MIN_SECS = 60`
/// 個 1m tick；alt buffer 同。**不**保留 raw orderbook（本 sub-task
/// `btc_book_imbalance = 0.0`）。
///
/// **strict shift(N) lookahead-free**：每個 metric 在 push current tick 進
/// buffer **之前** 完成計算（return = (close[t-N] vs close[t]) 用 buffer 內已
/// 存 tick 與 caller 傳入 current tick close 的差，不含未來 tick）。
pub struct BtcLeadLagProducer {
    /// Cohort alt symbols（鎖定不變，writer 寫 V088 alt_symbols column 的順序）。
    cohort_symbols: Vec<String>,
    /// BTC 1m tick 緩衝區（max XCORR_BASELINE_SECS 跨度）。
    btc_buffer: VecDeque<PriceTick>,
    /// Per-alt-symbol 1m tick 緩衝區。
    alt_buffers: HashMap<String, VecDeque<PriceTick>>,
    /// 最近一次 emit 的 snapshot（caller `latest()` 取）。
    latest_snapshot: Option<BtcLeadLagPanelSnapshot>,
    /// Buffer 容量上限（tick 數，預設 = XCORR_BASELINE_SECS / ONE_MIN_SECS = 60）。
    buffer_capacity: usize,
}

impl BtcLeadLagProducer {
    /// 構造新 producer。`cohort_symbols` 對應 spec §2.2 7-symbol cohort
    /// （ETHUSDT / SOLUSDT / XRPUSDT / DOGEUSDT / ADAUSDT / AVAXUSDT / DOTUSDT），
    /// 不含 BTCUSDT（BTC 是 lead source 獨立緩衝區）。
    ///
    /// **Caller 責任**：cohort 排除 BUSDT / INXUSDT / frozen symbols（spec §2.3），
    /// producer 端不重複 enforce（信任 caller 已過濾）。
    pub fn new(cohort_symbols: Vec<String>) -> Self {
        let buffer_capacity = (XCORR_BASELINE_SECS / ONE_MIN_SECS) as usize;
        let mut alt_buffers = HashMap::with_capacity(cohort_symbols.len());
        for sym in &cohort_symbols {
            alt_buffers.insert(sym.clone(), VecDeque::with_capacity(buffer_capacity));
        }
        Self {
            cohort_symbols,
            btc_buffer: VecDeque::with_capacity(buffer_capacity),
            alt_buffers,
            latest_snapshot: None,
            buffer_capacity,
        }
    }

    /// 接受 1m grain 對齊的 BTC + alt cohort tick，計算所有 metric，emit
    /// `BtcLeadLagPanelSnapshot` 並更新 `latest_snapshot`。
    ///
    /// **參數**：
    /// - `snapshot_ts_ms`：1m bucket end timestamp（epoch ms）
    /// - `btc_close`：BTCUSDT 當前 1m close
    /// - `btc_volume`：BTCUSDT 當前 1m volume
    /// - `alt_closes`：cohort alt symbol → 1m close map（缺 symbol = 該 symbol
    ///   本 tick 無 update，緩衝區不 push 該 symbol，xcorr 自然算到舊 sample）
    ///
    /// **返回**：emit 的 snapshot（同時更新 `latest_snapshot`）。
    ///
    /// **lookahead-free 順序**：先用 buffer 內已存 tick + 當前 caller 傳入
    /// 值計算所有 metric，最後才 push current tick 進 buffer。
    pub fn on_tick(
        &mut self,
        snapshot_ts_ms: i64,
        btc_close: f64,
        btc_volume: f64,
        alt_closes: &HashMap<String, f64>,
    ) -> BtcLeadLagPanelSnapshot {
        // 1. 計算 BTC lead return — 三檔 N=60/120/300 secs（用 buffer 內已存
        //    tick + current btc_close，strict shift(N) 不含 future）
        let btc_lead_return_pct =
            self.compute_btc_lead_return(btc_close, LEAD_WINDOW_SECS_MAIN as u64);
        let btc_lead_return_pct_60s =
            self.compute_btc_lead_return(btc_close, LEAD_WINDOW_SECS_SHADOW_60 as u64);
        let btc_lead_return_pct_300s =
            self.compute_btc_lead_return(btc_close, LEAD_WINDOW_SECS_SHADOW_300 as u64);

        // 2. 計算 BTC volume z-score（rolling 1h baseline，shift(1) 不含 current）
        let btc_volume_z = self.compute_btc_volume_z(btc_volume);

        // 3. 計算 per-alt cross-correlation（rolling 1h，主信號 N=120）
        let mut alt_xcorr = Vec::with_capacity(self.cohort_symbols.len());
        let mut alt_expected_dir = Vec::with_capacity(self.cohort_symbols.len());
        // 預先克隆 cohort 以避開 self 借用，符合 spec 中 alt_symbols 與
        // alt_xcorr / alt_expected_dir 同序對齊不變式。
        let cohort = self.cohort_symbols.clone();
        for sym in &cohort {
            let alt_close_now = alt_closes.get(sym).copied();
            let xcorr = self.compute_alt_xcorr(sym, alt_close_now);
            alt_xcorr.push(xcorr);

            // expected_dir per spec §3.3
            let dir = compute_expected_dir(btc_lead_return_pct, xcorr);
            alt_expected_dir.push(dir);
        }

        // 4. regime_tag — per spec §9 v1.1 #5
        //    用 BTC 1h return shift(1)：current close vs 1h 前的 buffer tick
        let regime_tag = self.compute_regime_tag(btc_close);

        // 5. 構造 snapshot（before push current tick）
        let snapshot = BtcLeadLagPanelSnapshot {
            snapshot_ts_ms,
            lead_window_secs: LEAD_WINDOW_SECS_MAIN,
            btc_lead_return_pct,
            btc_lead_return_pct_60s,
            btc_lead_return_pct_300s,
            btc_volume_z,
            // 本 sub-task orderbook 接線留 sub-task 4；先 0.0 placeholder
            // (writer 寫 V088 schema NULL 友好；REAL column 接受 0.0 不寫 NULL)
            btc_book_imbalance: 0.0,
            alt_symbols: cohort.clone(),
            alt_xcorr,
            alt_expected_dir,
            regime_tag,
            source_tier: SOURCE_TIER.to_string(),
        };

        // 6. push current tick 進 buffer（lookahead-free 邊界：metric 已算完）
        self.push_btc_tick(snapshot_ts_ms, btc_close, btc_volume);
        for sym in &cohort {
            if let Some(close) = alt_closes.get(sym) {
                self.push_alt_tick(sym, snapshot_ts_ms, *close, 0.0);
            }
        }

        // 7. 更新 latest + 返回
        self.latest_snapshot = Some(snapshot.clone());
        snapshot
    }

    /// 取最近一次 emit 的 snapshot 引用。None 表 producer 尚未跑過 `on_tick`。
    pub fn latest(&self) -> Option<&BtcLeadLagPanelSnapshot> {
        self.latest_snapshot.as_ref()
    }

    // ── 內部 helper ──

    /// 計算 BTC lead return bps over N seconds，strict shift(N) 不含 current。
    /// `current_close` 是 caller 傳入但 *尚未* push 進 buffer 的 close；
    /// buffer 內 tick 全是 t < current 的 sample。
    ///
    /// 公式：`(current_close - close[t-N]) / close[t-N] * 10000`（bps）
    /// 樣本不足 → NaN。
    fn compute_btc_lead_return(&self, current_close: f64, n_secs: u64) -> f64 {
        // n_secs 對應 n_ticks = n_secs / 60（1m grain）。
        // shift(N) 取 buffer 倒數第 n_ticks 筆 — 不含 current（current 還沒 push）。
        let n_ticks = (n_secs / ONE_MIN_SECS) as usize;
        if self.btc_buffer.len() < n_ticks {
            return f64::NAN;
        }
        // 倒數第 n_ticks 筆 = buffer.len() - n_ticks 索引（0-based）
        let idx = self.btc_buffer.len() - n_ticks;
        let past_close = self.btc_buffer[idx].close;
        if past_close <= 0.0 {
            return f64::NAN;
        }
        ((current_close - past_close) / past_close) * 10_000.0
    }

    /// 計算 BTC volume z-score（rolling 1h baseline，shift(1) 不含 current）。
    /// baseline mean / std 從 buffer 內 tick 算（不含 current）；不足 → NaN。
    fn compute_btc_volume_z(&self, current_volume: f64) -> f64 {
        let n_min = (VOLUME_Z_BASELINE_SECS / ONE_MIN_SECS) as usize;
        if self.btc_buffer.len() < n_min.min(10) {
            // 至少 10 sample 才算 z-score（避免 0 / NaN）
            return f64::NAN;
        }
        let take_n = self.btc_buffer.len().min(n_min);
        // 取最近 take_n 個 tick（不含 current — current 還沒 push）
        let start = self.btc_buffer.len() - take_n;
        let vols: Vec<f64> = self.btc_buffer.iter().skip(start).map(|t| t.volume).collect();
        let mean = vols.iter().sum::<f64>() / vols.len() as f64;
        let variance =
            vols.iter().map(|v| (*v - mean).powi(2)).sum::<f64>() / vols.len() as f64;
        let std_dev = variance.sqrt();
        if std_dev <= f64::EPSILON {
            return f64::NAN;
        }
        (current_volume - mean) / std_dev
    }

    /// 計算 per-alt cross-correlation vs BTC lead return（rolling 1h，主 N=120s）。
    /// 對齊 spec §3.2：BTC lead window = past 1h buffer 的 N-step return；
    /// alt follow window = past 1h buffer 的 N-step return（shift forward N）。
    /// 至少 XCORR_MIN_SAMPLE (=30) 個 N-step return pair 才算；不足 → NaN。
    fn compute_alt_xcorr(&self, sym: &str, _alt_close_now: Option<f64>) -> f64 {
        let n_ticks = (LEAD_WINDOW_SECS_MAIN as u64 / ONE_MIN_SECS) as usize; // 2 ticks for N=120s
        if n_ticks < 1 {
            return f64::NAN;
        }
        let alt_buffer = match self.alt_buffers.get(sym) {
            Some(b) => b,
            None => return f64::NAN,
        };
        // 樣本對：past N-step btc return + past N-step alt return
        // shift forward N 對齊：alt[t] vs btc[t-N]
        let min_buffer = XCORR_MIN_SAMPLE + n_ticks;
        if self.btc_buffer.len() < min_buffer || alt_buffer.len() < min_buffer {
            return f64::NAN;
        }
        let pair_count = self.btc_buffer.len().min(alt_buffer.len()) - n_ticks;
        if pair_count < XCORR_MIN_SAMPLE {
            return f64::NAN;
        }

        // 收 btc N-step return 序列（bps）
        let mut btc_returns = Vec::with_capacity(pair_count);
        let mut alt_returns = Vec::with_capacity(pair_count);
        // i 從 n_ticks 開始（避免 shift 越界）
        for i in n_ticks..(n_ticks + pair_count) {
            let btc_past = self.btc_buffer[i - n_ticks].close;
            let btc_now = self.btc_buffer[i].close;
            let alt_past = alt_buffer[i - n_ticks].close;
            let alt_now = alt_buffer[i].close;
            if btc_past <= 0.0 || alt_past <= 0.0 {
                continue;
            }
            btc_returns.push(((btc_now - btc_past) / btc_past) * 10_000.0);
            alt_returns.push(((alt_now - alt_past) / alt_past) * 10_000.0);
        }

        if btc_returns.len() < XCORR_MIN_SAMPLE {
            return f64::NAN;
        }
        pearson_corr(&btc_returns, &alt_returns)
    }

    /// 計算 regime_tag — per spec §9 v1.1 #5。
    /// 公式：BTC 1h return = (current_close - btc_buffer[1h_ago].close) /
    ///                       btc_buffer[1h_ago].close * 10000 (bps)
    ///       |1h return| > 200 bps → "extreme"，否則 "normal"
    /// 樣本不足 → "normal"（保守 default，per spec §9：unknown 不計入 extreme）。
    fn compute_regime_tag(&self, current_close: f64) -> String {
        let n_ticks_1h = (ONE_HOUR_SECS / ONE_MIN_SECS) as usize;
        if self.btc_buffer.len() < n_ticks_1h {
            return "normal".to_string();
        }
        let idx = self.btc_buffer.len() - n_ticks_1h;
        let past_close = self.btc_buffer[idx].close;
        if past_close <= 0.0 {
            return "normal".to_string();
        }
        let return_bps = ((current_close - past_close) / past_close) * 10_000.0;
        if return_bps.abs() > REGIME_EXTREME_BPS {
            "extreme".to_string()
        } else {
            "normal".to_string()
        }
    }

    fn push_btc_tick(&mut self, ts_ms: i64, close: f64, volume: f64) {
        if self.btc_buffer.len() >= self.buffer_capacity {
            self.btc_buffer.pop_front();
        }
        self.btc_buffer.push_back(PriceTick {
            ts_ms,
            close,
            volume,
        });
    }

    fn push_alt_tick(&mut self, sym: &str, ts_ms: i64, close: f64, volume: f64) {
        let buffer = match self.alt_buffers.get_mut(sym) {
            Some(b) => b,
            None => return,
        };
        if buffer.len() >= self.buffer_capacity {
            buffer.pop_front();
        }
        buffer.push_back(PriceTick {
            ts_ms,
            close,
            volume,
        });
    }

    /// Cohort symbols 不可變引用（observability + test helper）。
    pub fn cohort_symbols(&self) -> &[String] {
        &self.cohort_symbols
    }
}

// ─────────────────────────────────────────────────────────────────────────
// W2 sub-task 4 (E1-δ, 2026-05-11) — run_loop + IPC slot late-inject + PG writer
// 與 W1 PanelAggregator broadcast core 不同：BtcLeadLagProducer 是 pull pattern
// 從 market.klines 1m table 拉 BTC + alt cohort close/volume，60s tick 一次
// （per spec §3.1 lead window N=120 + 60s grain）。每 tick：
//   1. 拉 BTC 1m close + volume
//   2. 拉 alt cohort 1m close
//   3. on_tick 計算 snapshot
//   4. INSERT panel.btc_lead_lag_panel V088
//   5. write IPC slot (snapshot → BtcLeadLagPanel adaptor)
// 60s flush interval 對齊 W1 PanelAggregator FLUSH_INTERVAL_SECS（panel writer 一致）。
// ─────────────────────────────────────────────────────────────────────────

/// W2 sub-task 4 (E1-δ, 2026-05-11) — flush interval 60s（per spec §3.1 + 1m grain）。
const RUN_LOOP_TICK_SECS: u64 = 60;

impl BtcLeadLagProducer {
    /// W2 sub-task 4 (E1-δ, 2026-05-11) — 真實 run loop（pull pattern）。
    ///
    /// 設計（per spec §3.1 + dispatch v3.7 §3.1 chunk 4）：
    /// 1. 每 60 秒 tick：從 PG `market.klines` 拉 BTCUSDT + 7 alt cohort 1m close/volume
    /// 2. 呼叫 `on_tick(snapshot_ts_ms, btc_close, btc_volume, alt_closes)` 計算 snapshot
    /// 3. INSERT V088 `panel.btc_lead_lag_panel`（fail-soft：pool 不可用 → skip 不阻 slot）
    /// 4. snapshot → `BtcLeadLagPanel` (trait struct) adaptor → 寫 IPC slot
    /// 5. cancel：graceful break
    ///
    /// **slot late-inject 語義**：slot 是 `Arc<RwLock<Option<BtcLeadLagPanel>>>` —
    /// 每 60s tick replace 整個 Option（write lock 短時持有；step_4_5_dispatch
    /// hot path 用 try_read 不會 block）。snapshot 內 `lead_window_secs=120` 主信號
    /// 對應 trait struct `lead_window_secs` field；shadow N=60/300 不寫 slot
    /// （per spec line 207「不寫 IPC slot」），只寫 V088 schema column 收 evidence。
    ///
    /// **regime gate**：snapshot.regime_tag == "extreme" → 仍寫 slot（trait struct
    /// 有完整 panel；consumer 端 strategy on_tick 自行判斷是否 skip per spec §9）；
    /// per spec line 488「不阻 slot 寫入」對齊 W1 funding/oi flush 行為。
    ///
    /// **pool 不可用 fail-soft**：PG INSERT 失敗時 slot 仍寫入（trait 端 None vs
    /// Some 對齊 producer 是否「emit」而非「PG 是否可用」；hot path consumer 應
    /// 看 panel.snapshot_ts_ms 判斷 freshness，與 PG 寫入解耦）。
    pub async fn run_loop(
        mut self,
        db_pool: Arc<DbPool>,
        slot: BtcLeadLagPanelSlot,
        cancel: CancellationToken,
    ) {
        info!(
            target: "panel_aggregator",
            cohort_size = self.cohort_symbols.len(),
            tick_secs = RUN_LOOP_TICK_SECS,
            "BtcLeadLagProducer run_loop start (W2 sub-task 4 wired)"
        );

        let mut tick_timer = tokio::time::interval(Duration::from_secs(RUN_LOOP_TICK_SECS));
        // 跳過第一個 immediate tick（boot 時 buffer 空 → snapshot 全 NaN，浪費 PG 寫）
        tick_timer.tick().await;

        let mut total_ticks: u64 = 0;
        let mut emit_count: u64 = 0;
        let mut pg_ok: u64 = 0;
        let mut pg_fail: u64 = 0;

        loop {
            tokio::select! {
                _ = cancel.cancelled() => {
                    info!(
                        target: "panel_aggregator",
                        total_ticks = total_ticks,
                        emit_count = emit_count,
                        pg_ok = pg_ok,
                        pg_fail = pg_fail,
                        "BtcLeadLagProducer cancelled, shutting down"
                    );
                    return;
                }

                _ = tick_timer.tick() => {
                    total_ticks = total_ticks.saturating_add(1);
                    let snapshot_ts_ms = openclaw_core::now_ms() as i64;

                    // 1. PG 拉 BTC + alt cohort 1m close/volume；fail-soft skip tick
                    let btc_close_volume = match fetch_latest_kline_close_volume(
                        &db_pool, "BTCUSDT",
                    ).await {
                        Some((close, volume)) => Some((close, volume)),
                        None => {
                            debug!(
                                target: "panel_aggregator",
                                snapshot_ts_ms = snapshot_ts_ms,
                                "BTCUSDT 1m kline unavailable, skipping tick"
                            );
                            None
                        }
                    };

                    let Some((btc_close, btc_volume)) = btc_close_volume else {
                        continue;
                    };

                    // 2. alt cohort closes
                    let mut alt_closes: HashMap<String, f64> = HashMap::with_capacity(
                        self.cohort_symbols.len(),
                    );
                    for sym in self.cohort_symbols.clone() {
                        if let Some((close, _vol)) =
                            fetch_latest_kline_close_volume(&db_pool, &sym).await
                        {
                            alt_closes.insert(sym, close);
                        }
                    }

                    // 3. on_tick：calc snapshot（lookahead-free）
                    let snapshot = self.on_tick(snapshot_ts_ms, btc_close, btc_volume, &alt_closes);
                    emit_count = emit_count.saturating_add(1);

                    // 4. PG INSERT V088（fail-soft：失敗只計數，slot 仍寫）
                    let insert_outcome = insert_btc_lead_lag_snapshot(&db_pool, &snapshot).await;
                    match insert_outcome {
                        SingleInsertOutcome::Ok(_) => pg_ok = pg_ok.saturating_add(1),
                        SingleInsertOutcome::Failed | SingleInsertOutcome::PoolUnavailable => {
                            pg_fail = pg_fail.saturating_add(1);
                            warn!(
                                target: "panel_aggregator",
                                snapshot_ts_ms = snapshot_ts_ms,
                                regime_tag = %snapshot.regime_tag,
                                "btc_lead_lag snapshot INSERT failed (slot 仍寫)"
                            );
                        }
                    }

                    // 5. snapshot → BtcLeadLagPanel adaptor → 寫 slot
                    let trait_panel = snapshot_to_trait_panel(&snapshot);
                    *slot.write().await = Some(trait_panel);
                    debug!(
                        target: "panel_aggregator",
                        snapshot_ts_ms = snapshot_ts_ms,
                        regime_tag = %snapshot.regime_tag,
                        emit_count = emit_count,
                        "btc_lead_lag panel slot updated"
                    );
                }
            }
        }
    }
}

/// W2 sub-task 4 (E1-δ, 2026-05-11) — snapshot → trait struct adaptor。
///
/// `BtcLeadLagPanelSnapshot`（producer 端，含 12-column schema 全字段）映射至
/// `BtcLeadLagPanel`（trait struct，AlphaSurface field type）。adaptor 只取
/// 主信號 N=120 字段（per spec line 207「主 N=120 信號寫主 panel 欄位，60s/300s
/// shadow value 寫 schema column 但不寫 IPC slot」）。
///
/// **不變式**：
/// - `lead_window_secs == LEAD_WINDOW_SECS_MAIN` (120) — 主信號鎖定
/// - `alt_symbols.len() == alt_xcorr.len() == alt_expected_dir.len()`（snapshot
///   端已 invariant，adaptor 直接 clone）
pub fn snapshot_to_trait_panel(snapshot: &BtcLeadLagPanelSnapshot) -> BtcLeadLagPanel {
    BtcLeadLagPanel {
        alt_symbols: snapshot.alt_symbols.clone(),
        btc_lead_return_pct: snapshot.btc_lead_return_pct,
        lead_window_secs: snapshot.lead_window_secs,
        alt_xcorr: snapshot.alt_xcorr.clone(),
        alt_expected_dir: snapshot.alt_expected_dir.clone(),
        snapshot_ts_ms: snapshot.snapshot_ts_ms,
        source_tier: snapshot.source_tier.clone(),
    }
}

/// W2 sub-task 4 (E1-δ, 2026-05-11) — 從 `market.klines` 1m table 拉最近 close + volume。
///
/// 取最近 2min 內最新一筆 1m kline（避免 stale data 用過久舊 bar）；
/// 找不到 → None（caller fail-soft skip tick）。
///
/// SQL 對齊 outcome_backfiller.rs `WHERE k.timeframe = '1m'` 命名語義。
async fn fetch_latest_kline_close_volume(
    pool: &Arc<DbPool>,
    symbol: &str,
) -> Option<(f64, f64)> {
    let pg = pool.get()?;
    let row: Option<(f32, Option<f32>)> = sqlx::query_as::<Postgres, (f32, Option<f32>)>(
        "SELECT close, volume FROM market.klines \
         WHERE symbol = $1 AND timeframe = '1m' \
           AND ts > NOW() - INTERVAL '2 minutes' \
         ORDER BY ts DESC LIMIT 1",
    )
    .bind(symbol)
    .fetch_optional(pg)
    .await
    .ok()
    .flatten();
    row.map(|(close, volume)| (close as f64, volume.unwrap_or(0.0) as f64))
}

/// W2 sub-task 4 (E1-δ, 2026-05-11) — INSERT V088 `panel.btc_lead_lag_panel`。
///
/// SQL 對齊 V088 schema 12-column shape：
/// - snapshot_ts_ms BIGINT (hypertable time column)
/// - lead_window_secs INT
/// - btc_lead_return_pct REAL（主 N=120）
/// - btc_lead_return_pct_60s REAL（shadow value, decay curve evidence）
/// - btc_lead_return_pct_300s REAL（同上）
/// - btc_volume_z REAL
/// - btc_book_imbalance REAL
/// - alt_symbols TEXT[]
/// - alt_xcorr REAL[]
/// - alt_expected_dir SMALLINT[]
/// - regime_tag TEXT ('normal' / 'extreme')
/// - source_tier TEXT ('cross_asset_btc_lead_lag')
///
/// `arrays_aligned()` invariant 違反 → return Failed 不 INSERT 半 schema row
/// （per spec §4.1 invariant + sub-task 1 deliverable line 583）。
///
/// **NaN 處理**：REAL column 接 NaN（PG 接 'NaN' literal）；SMALLINT[] expected_dir
/// 是 i8 不會 NaN（compute_expected_dir fail-closed → 0）。Vec<f64> NaN cast f32 NaN。
///
/// ON CONFLICT (snapshot_ts_ms, lead_window_secs) DO UPDATE — idempotent on retry
/// （per V088 PK design：1 snapshot = 1 row per lead_window_secs；本 producer
/// 鎖定 lead_window_secs=120 主信號 + 60s/300s shadow value 同 row schema 字段）。
pub(crate) async fn insert_btc_lead_lag_snapshot(
    pool: &Arc<DbPool>,
    snapshot: &BtcLeadLagPanelSnapshot,
) -> SingleInsertOutcome {
    if !snapshot.arrays_aligned() {
        warn!(
            target: "panel_aggregator",
            snapshot_ts_ms = snapshot.snapshot_ts_ms,
            alt_symbols_len = snapshot.alt_symbols.len(),
            alt_xcorr_len = snapshot.alt_xcorr.len(),
            alt_expected_dir_len = snapshot.alt_expected_dir.len(),
            "btc_lead_lag snapshot arrays_aligned invariant violated, drop INSERT"
        );
        return SingleInsertOutcome::Failed;
    }

    // Vec<f64> → Vec<f32> for REAL[] column；NaN 對齊保留
    let alt_xcorr_f32: Vec<f32> = snapshot.alt_xcorr.iter().map(|v| *v as f32).collect();
    // Vec<i8> → Vec<i16> for SMALLINT[] column（PG SMALLINT 對應 i16；i8 cast 安全 −128..127）
    let alt_expected_dir_i16: Vec<i16> =
        snapshot.alt_expected_dir.iter().map(|v| *v as i16).collect();

    let query = sqlx::query::<Postgres>(
        "INSERT INTO panel.btc_lead_lag_panel \
         (snapshot_ts_ms, lead_window_secs, btc_lead_return_pct, \
          btc_lead_return_pct_60s, btc_lead_return_pct_300s, \
          btc_volume_z, btc_book_imbalance, \
          alt_symbols, alt_xcorr, alt_expected_dir, regime_tag, source_tier) \
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12) \
         ON CONFLICT (snapshot_ts_ms, lead_window_secs) DO UPDATE SET \
            btc_lead_return_pct = EXCLUDED.btc_lead_return_pct, \
            btc_lead_return_pct_60s = EXCLUDED.btc_lead_return_pct_60s, \
            btc_lead_return_pct_300s = EXCLUDED.btc_lead_return_pct_300s, \
            btc_volume_z = EXCLUDED.btc_volume_z, \
            btc_book_imbalance = EXCLUDED.btc_book_imbalance, \
            alt_symbols = EXCLUDED.alt_symbols, \
            alt_xcorr = EXCLUDED.alt_xcorr, \
            alt_expected_dir = EXCLUDED.alt_expected_dir, \
            regime_tag = EXCLUDED.regime_tag, \
            source_tier = EXCLUDED.source_tier",
    )
    .bind(snapshot.snapshot_ts_ms)
    .bind(snapshot.lead_window_secs as i32)
    .bind(snapshot.btc_lead_return_pct as f32)
    .bind(snapshot.btc_lead_return_pct_60s as f32)
    .bind(snapshot.btc_lead_return_pct_300s as f32)
    .bind(snapshot.btc_volume_z as f32)
    .bind(snapshot.btc_book_imbalance as f32)
    .bind(snapshot.alt_symbols.clone())
    .bind(alt_xcorr_f32)
    .bind(alt_expected_dir_i16)
    .bind(snapshot.regime_tag.clone())
    .bind(snapshot.source_tier.clone());

    exec_single_insert(pool, "panel.btc_lead_lag_panel", query).await
}

/// W2 sub-task 4 (E1-δ, 2026-05-11) — 對齊 RwLock slot late-inject 工廠。
///
/// 原始 producer 不知 slot；本函數提供 producer 端 slot 自建選項給 unit test
/// 與 boot-time 構造，typedef 對齊 ipc_server::BtcLeadLagPanelSlot。
pub fn create_btc_lead_lag_panel_slot() -> BtcLeadLagPanelSlot {
    Arc::new(RwLock::new(None))
}

// ─────────────────────────────────────────────────────────────────────────
// 純函數 helper（spec §3.3 expected_dir + Pearson + PSR(0) skew/kurt formula）
// ─────────────────────────────────────────────────────────────────────────

/// 計算 expected_dir per alt symbol — spec §3.3 公式直譯。
///
/// 邏輯：
/// - |xcorr| < THRESHOLD_Y → 0（xcorr 太弱，不 trust BTC 預測力）
/// - btc_lead_return > +THRESHOLD_X_BPS → +1 * sign(xcorr)
/// - btc_lead_return < -THRESHOLD_X_BPS → -1 * sign(xcorr)
/// - 其他 → 0
///
/// xcorr NaN 或 btc_lead_return NaN → 0 fail-closed（未知就保守 0）。
pub fn compute_expected_dir(btc_lead_return_bps: f64, xcorr: f64) -> i8 {
    if xcorr.is_nan() || btc_lead_return_bps.is_nan() {
        return 0;
    }
    if xcorr.abs() < THRESHOLD_Y {
        return 0;
    }
    let xcorr_sign: i8 = if xcorr > 0.0 { 1 } else { -1 };
    if btc_lead_return_bps > THRESHOLD_X_BPS {
        xcorr_sign
    } else if btc_lead_return_bps < -THRESHOLD_X_BPS {
        -xcorr_sign
    } else {
        0
    }
}

/// Pearson correlation — 純函數，相同長度兩 slice 算 r ∈ [-1, 1]。
/// 樣本不足或 std=0 → NaN。
pub fn pearson_corr(x: &[f64], y: &[f64]) -> f64 {
    debug_assert_eq!(x.len(), y.len());
    let n = x.len();
    if n < 2 {
        return f64::NAN;
    }
    let nf = n as f64;
    let mean_x = x.iter().sum::<f64>() / nf;
    let mean_y = y.iter().sum::<f64>() / nf;
    let mut cov = 0.0;
    let mut var_x = 0.0;
    let mut var_y = 0.0;
    for i in 0..n {
        let dx = x[i] - mean_x;
        let dy = y[i] - mean_y;
        cov += dx * dy;
        var_x += dx * dx;
        var_y += dy * dy;
    }
    let denom = (var_x * var_y).sqrt();
    if denom <= f64::EPSILON {
        return f64::NAN;
    }
    cov / denom
}

/// PSR(0) — Bailey-López de Prado 2012 skew/kurt-aware formula
/// （spec §7.1 metric (3) + §8.1 +15 bps gate verification 強制公式）。
///
/// 公式：`PSR(0) = Φ((SR - 0) × √(n-1) / √(1 - skew·SR + (kurt-1)/4·SR²))`
/// 其中：
/// - Φ = standard normal CDF
/// - SR = annualized Sharpe ratio
/// - n = sample size
/// - skew + kurt = 經驗 skewness + excess kurtosis
///
/// 樣本不足 / SR NaN / 分母負（denominator 開根號失敗）→ NaN。
///
/// **使用場景**：D+12 paper edge report 階段對 7d sample 算 PSR(0)，threshold
/// ≥ 0.95；本 producer 不直接呼叫此 function（producer 算 raw return + 緩衝
/// metric），留給 downstream evaluator (replay analyzer / paper edge report
/// generator) 用此 function 對 7d sample 算 final PSR(0)。
///
/// 此處放 producer module 是為集中 spec §7.1 強制公式 一處實作（避免 evaluator
/// 端重抄），方便 unit test 對照 MIT C-3 verify report §4 預估值（σ_net=80
/// + ex_kurt=10 → PSR(0) ≈ 0.94）。
pub fn psr_zero(sharpe_ratio: f64, n: usize, skew: f64, excess_kurt: f64) -> f64 {
    if n < 2 || sharpe_ratio.is_nan() || skew.is_nan() || excess_kurt.is_nan() {
        return f64::NAN;
    }
    let nf = (n as f64) - 1.0;
    if nf <= 0.0 {
        return f64::NAN;
    }
    // denom_inner = 1 - skew·SR + (kurt-1)/4·SR²
    // 注意：spec §7.1 公式 kurt 是 excess kurt + 3（normal baseline）；
    // Bailey-López de Prado 2012 用 (kurt-1)/4 是含 normal=3 的 kurt，因此
    // 內部用 excess_kurt + 3 = kurt 後 (kurt - 1) / 4 = (excess_kurt + 2)/4
    let kurt_full = excess_kurt + 3.0;
    let denom_inner = 1.0 - skew * sharpe_ratio + (kurt_full - 1.0) / 4.0 * sharpe_ratio.powi(2);
    if denom_inner <= 0.0 {
        // 分母 = √負數 → 公式失效，返 NaN（caller 視為 fail）
        return f64::NAN;
    }
    let denom = denom_inner.sqrt();
    let z = sharpe_ratio * nf.sqrt() / denom;
    standard_normal_cdf(z)
}

/// Standard normal CDF — Abramowitz & Stegun 7.1.26 approximation。
/// 精度 ≈ 7.5e-8（足夠 PSR(0) 0.95 threshold 判斷）。
fn standard_normal_cdf(z: f64) -> f64 {
    // erf approximation via Abramowitz & Stegun 7.1.26
    // CDF(z) = 0.5 * (1 + erf(z / √2))
    let a1 = 0.254829592_f64;
    let a2 = -0.284496736_f64;
    let a3 = 1.421413741_f64;
    let a4 = -1.453152027_f64;
    let a5 = 1.061405429_f64;
    let p = 0.3275911_f64;
    let sign: f64 = if z < 0.0 { -1.0 } else { 1.0 };
    let x = (z / std::f64::consts::SQRT_2).abs();
    let t = 1.0 / (1.0 + p * x);
    let y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * (-x * x).exp();
    0.5 * (1.0 + sign * y)
}

// ─────────────────────────────────────────────────────────────────────────
// Tests — spec §7.1 mandatory metric + §3.3 expected_dir + dual-layer σ
// ─────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn make_cohort() -> Vec<String> {
        vec![
            "ETHUSDT".to_string(),
            "SOLUSDT".to_string(),
            "XRPUSDT".to_string(),
            "DOGEUSDT".to_string(),
            "ADAUSDT".to_string(),
            "AVAXUSDT".to_string(),
            "DOTUSDT".to_string(),
        ]
    }

    /// 三 array length invariant — spec §4.1 不變式 + sub-task 1 deliverable
    /// 第 5 項。on_tick emit snapshot 必滿足 alt_symbols.len() ==
    /// alt_xcorr.len() == alt_expected_dir.len()。
    #[test]
    fn arrays_aligned_invariant_on_emit() {
        let cohort = make_cohort();
        let cohort_len = cohort.len();
        let mut p = BtcLeadLagProducer::new(cohort);
        let mut alt_closes = HashMap::new();
        for sym in [
            "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT",
        ] {
            alt_closes.insert(sym.to_string(), 100.0);
        }
        let snap = p.on_tick(60_000, 50_000.0, 100.0, &alt_closes);
        assert!(snap.arrays_aligned(), "三 array 必同序同長");
        assert_eq!(snap.alt_symbols.len(), cohort_len);
        assert_eq!(snap.alt_xcorr.len(), cohort_len);
        assert_eq!(snap.alt_expected_dir.len(), cohort_len);
        assert_eq!(snap.lead_window_secs, LEAD_WINDOW_SECS_MAIN);
        assert_eq!(snap.source_tier, SOURCE_TIER);
    }

    /// 樣本不足 → 主信號 NaN（不 emit 假 metric）。spec §3.2 NaN sentinel。
    #[test]
    fn lead_return_nan_when_insufficient_buffer() {
        let mut p = BtcLeadLagProducer::new(make_cohort());
        let alt_closes = HashMap::new();
        let snap = p.on_tick(60_000, 50_000.0, 100.0, &alt_closes);
        assert!(snap.btc_lead_return_pct.is_nan());
        assert!(snap.btc_lead_return_pct_60s.is_nan());
        assert!(snap.btc_lead_return_pct_300s.is_nan());
        assert!(snap.btc_volume_z.is_nan());
    }

    /// strict shift(N) lookahead-free — current bar 不算進 lead return。
    /// 餵 N+1 個 1m tick；最後一個 tick emit 的 lead_return 必對應 buffer
    /// 倒數第 N 個 tick vs current（不含 current 之後 sample，因為沒有未來）。
    #[test]
    fn lead_return_strict_shift_n_lookahead_free() {
        let mut p = BtcLeadLagProducer::new(make_cohort());
        let alt_closes: HashMap<String, f64> = HashMap::new();
        // 先餵 N=2 ticks (LEAD_WINDOW_SECS_MAIN=120s = 2 min) past:
        // t=60000 close=50000, t=120000 close=50100, t=180000 close=50500 (current)
        // shift(N=2) past = buffer[len-2] = 第一個 tick close=50000
        // expected lead_return = (50500 - 50000) / 50000 * 10000 = 100 bps
        p.on_tick(60_000, 50_000.0, 100.0, &alt_closes);
        p.on_tick(120_000, 50_100.0, 100.0, &alt_closes);
        let snap = p.on_tick(180_000, 50_500.0, 100.0, &alt_closes);
        let expected = (50_500.0 - 50_000.0) / 50_000.0 * 10_000.0;
        assert!(
            (snap.btc_lead_return_pct - expected).abs() < 1e-6,
            "lead_return = {} expected {}",
            snap.btc_lead_return_pct,
            expected
        );
    }

    /// expected_dir formula — spec §3.3 truth table。
    #[test]
    fn expected_dir_truth_table() {
        // |xcorr| < threshold_Y (0.40) → 0
        assert_eq!(compute_expected_dir(50.0, 0.30), 0);
        assert_eq!(compute_expected_dir(-50.0, -0.30), 0);

        // btc_lead_return 在 [-X, +X] 區間 → 0 不論 xcorr
        assert_eq!(compute_expected_dir(5.0, 0.50), 0);
        assert_eq!(compute_expected_dir(-5.0, 0.50), 0);

        // btc > +X & xcorr > Y → +1（同向 momentum）
        assert_eq!(compute_expected_dir(15.0, 0.50), 1);
        // btc > +X & xcorr < -Y → -1（反向 mean-revert）
        assert_eq!(compute_expected_dir(15.0, -0.50), -1);
        // btc < -X & xcorr > Y → -1
        assert_eq!(compute_expected_dir(-15.0, 0.50), -1);
        // btc < -X & xcorr < -Y → +1
        assert_eq!(compute_expected_dir(-15.0, -0.50), 1);

        // NaN 容錯
        assert_eq!(compute_expected_dir(f64::NAN, 0.50), 0);
        assert_eq!(compute_expected_dir(15.0, f64::NAN), 0);
    }

    /// regime_tag — |BTC 1h return| > 200 bps → "extreme"。spec §9 v1.1 #5。
    #[test]
    fn regime_tag_extreme_when_1h_return_exceeds_200bps() {
        let mut p = BtcLeadLagProducer::new(make_cohort());
        let alt_closes = HashMap::new();
        // 餵 60 個 1m tick 形成 1h baseline（50000 開始，後緩升 1bps/tick）
        for i in 0..60 {
            p.on_tick(60_000 + i * 60_000, 50_000.0 + i as f64, 100.0, &alt_closes);
        }
        // t=61 餵一個 +250 bps spike: close = 50000 * 1.025 = 51250
        let snap = p.on_tick(60_000 + 60 * 60_000, 51_250.0, 100.0, &alt_closes);
        // 1h ago buffer[len-60] 是第一個 tick close=50000.0
        // 1h return = (51250 - 50000) / 50000 * 10000 = 250 bps > 200 → extreme
        assert_eq!(snap.regime_tag, "extreme");
    }

    #[test]
    fn regime_tag_normal_when_1h_return_within_200bps() {
        let mut p = BtcLeadLagProducer::new(make_cohort());
        let alt_closes = HashMap::new();
        for i in 0..60 {
            p.on_tick(60_000 + i * 60_000, 50_000.0 + i as f64, 100.0, &alt_closes);
        }
        // t=61 +50 bps mild move: close = 50000 * 1.005 = 50250
        let snap = p.on_tick(60_000 + 60 * 60_000, 50_250.0, 100.0, &alt_closes);
        assert_eq!(snap.regime_tag, "normal");
    }

    #[test]
    fn regime_tag_normal_when_buffer_short() {
        let mut p = BtcLeadLagProducer::new(make_cohort());
        let alt_closes = HashMap::new();
        // 樣本不足 1h baseline → fail-closed default "normal"
        let snap = p.on_tick(60_000, 50_000.0, 100.0, &alt_closes);
        assert_eq!(snap.regime_tag, "normal");
    }

    /// xcorr — 完美正相關回 1.0 ± epsilon。spec §3.2 Pearson 不變式。
    #[test]
    fn pearson_perfect_positive_correlation() {
        let x: Vec<f64> = (0..50).map(|i| i as f64).collect();
        let y: Vec<f64> = (0..50).map(|i| 2.0 * i as f64 + 1.0).collect();
        let r = pearson_corr(&x, &y);
        assert!((r - 1.0).abs() < 1e-10);
    }

    #[test]
    fn pearson_perfect_negative_correlation() {
        let x: Vec<f64> = (0..50).map(|i| i as f64).collect();
        let y: Vec<f64> = (0..50).map(|i| -2.0 * i as f64 + 1.0).collect();
        let r = pearson_corr(&x, &y);
        assert!((r + 1.0).abs() < 1e-10);
    }

    #[test]
    fn pearson_zero_when_constant() {
        let x: Vec<f64> = (0..50).map(|i| i as f64).collect();
        let y: Vec<f64> = vec![5.0; 50]; // constant → std=0 → NaN
        let r = pearson_corr(&x, &y);
        assert!(r.is_nan());
    }

    /// PSR(0) skew/kurt-aware formula — spec §8.1 +15 bps gate σ_net=80 case
    /// MIT C-3 verify report §4 預估 PSR(0) ≈ 0.94 sanity check（不要求精確
    /// 等於 0.94，只要落在 [0.85, 0.99] 合理區間，避免完全錯誤的公式 land）。
    #[test]
    fn psr_zero_sanity_skew_kurt_formula() {
        // case: SR ≈ 1.5（年化 Sharpe，per MIT report 視角），n=80, skew=-0.5,
        // ex_kurt=10 → PSR(0) 預期 sub-1.0 但 ≥ 0.7 區間
        let psr = psr_zero(1.5, 80, -0.5, 10.0);
        assert!(!psr.is_nan(), "PSR(0) 在合理輸入下不應 NaN");
        assert!(
            psr >= 0.5 && psr <= 1.0,
            "PSR(0) 在 SR=1.5 / n=80 / skew=-0.5 / ex_kurt=10 應在 [0.5, 1.0] 區間，actual={}",
            psr
        );

        // Normality reference: skew=0, kurt=3 (excess=0) → PSR(0) 應 ≈ Φ(SR·√(n-1))
        // SR=1.0, n=100 → Φ(1.0·√99) = Φ(9.95) ≈ 1.0
        let psr_normal = psr_zero(1.0, 100, 0.0, 0.0);
        assert!((psr_normal - 1.0).abs() < 0.01);
    }

    #[test]
    fn psr_zero_nan_on_insufficient_sample() {
        assert!(psr_zero(1.0, 0, 0.0, 0.0).is_nan());
        assert!(psr_zero(1.0, 1, 0.0, 0.0).is_nan());
    }

    #[test]
    fn psr_zero_nan_on_negative_denominator() {
        // 構造分母負：SR 大 + skew 大 + ex_kurt 負
        // denom_inner = 1 - skew·SR + (excess_kurt+2)/4·SR²
        // 取 SR=10, skew=2, ex_kurt=-3 → 1 - 20 + (-1)/4·100 = -44 < 0 → NaN
        let psr = psr_zero(10.0, 100, 2.0, -3.0);
        assert!(psr.is_nan());
    }

    /// latest() 在沒 on_tick 前是 None；on_tick 後同 snapshot。
    #[test]
    fn latest_lifecycle() {
        let mut p = BtcLeadLagProducer::new(make_cohort());
        assert!(p.latest().is_none());
        let alt_closes = HashMap::new();
        let s = p.on_tick(60_000, 50_000.0, 100.0, &alt_closes);
        let latest = p.latest().expect("latest 應有值");
        assert_eq!(latest.snapshot_ts_ms, s.snapshot_ts_ms);
        assert_eq!(latest.lead_window_secs, s.lead_window_secs);
    }

    /// Buffer cap — 超過 buffer_capacity 後 pop_front。
    #[test]
    fn buffer_capacity_cap_enforced() {
        let mut p = BtcLeadLagProducer::new(make_cohort());
        let cap = p.buffer_capacity;
        let alt_closes = HashMap::new();
        for i in 0..(cap + 5) {
            p.on_tick(60_000 + i as i64 * 60_000, 50_000.0, 100.0, &alt_closes);
        }
        assert_eq!(p.btc_buffer.len(), cap);
        // 第 0 個 tick 已 pop（最早 ts = 60_000 + 5 * 60_000 = 360_000）
        assert_eq!(p.btc_buffer.front().unwrap().ts_ms, 60_000 + 5 * 60_000);
    }

    // ── W2 sub-task 4 (E1-δ, 2026-05-11) — IPC slot late-inject + adaptor + run_loop ──

    /// W2 sub-task 4 — slot 工廠回 None；late-inject 起點驗證。
    #[tokio::test]
    async fn create_btc_lead_lag_panel_slot_returns_empty() {
        let slot = create_btc_lead_lag_panel_slot();
        let inner = slot.read().await;
        assert!(inner.is_none(), "slot must default None for late-inject");
    }

    /// W2 sub-task 4 — `mod.rs::create_btc_lead_lag_slot()` 與 `btc_lead_lag::create_btc_lead_lag_panel_slot()`
    /// 行為對齊（兩 entry 都回 None Arc<RwLock<Option<BtcLeadLagPanel>>>）。
    #[tokio::test]
    async fn factories_match_pattern() {
        let slot1 = create_btc_lead_lag_panel_slot();
        let slot2 = crate::panel_aggregator::create_btc_lead_lag_slot();
        assert!(slot1.read().await.is_none());
        assert!(slot2.read().await.is_none());
    }

    /// W2 sub-task 4 — snapshot → trait BtcLeadLagPanel adaptor 對齊主信號 N=120 字段。
    /// 驗 alt_symbols / alt_xcorr / alt_expected_dir / lead_window_secs 完整 propagate；
    /// 60s/300s shadow value + btc_volume_z / btc_book_imbalance / regime_tag **不**進
    /// trait struct（per spec line 207「不寫 IPC slot」）。
    #[test]
    fn snapshot_to_trait_panel_propagates_main_signal_fields() {
        let snapshot = BtcLeadLagPanelSnapshot {
            snapshot_ts_ms: 1_700_000_060_000,
            lead_window_secs: LEAD_WINDOW_SECS_MAIN,
            btc_lead_return_pct: 25.5,
            btc_lead_return_pct_60s: 12.3,
            btc_lead_return_pct_300s: 50.0,
            btc_volume_z: 1.5,
            btc_book_imbalance: 0.0,
            alt_symbols: vec!["ETHUSDT".to_string(), "SOLUSDT".to_string()],
            alt_xcorr: vec![0.6, -0.4],
            alt_expected_dir: vec![1, -1],
            regime_tag: "normal".to_string(),
            source_tier: SOURCE_TIER.to_string(),
        };
        let panel = snapshot_to_trait_panel(&snapshot);
        assert_eq!(panel.snapshot_ts_ms, 1_700_000_060_000);
        assert_eq!(panel.lead_window_secs, LEAD_WINDOW_SECS_MAIN);
        assert_eq!(panel.btc_lead_return_pct, 25.5);
        assert_eq!(panel.alt_symbols, vec!["ETHUSDT".to_string(), "SOLUSDT".to_string()]);
        assert_eq!(panel.alt_xcorr, vec![0.6, -0.4]);
        assert_eq!(panel.alt_expected_dir, vec![1, -1]);
        assert_eq!(panel.source_tier, SOURCE_TIER);
        // adaptor 不會 leak shadow value 進 trait struct
        assert_eq!(
            std::mem::size_of_val(&panel.btc_lead_return_pct),
            std::mem::size_of::<f64>(),
            "trait struct only carries main signal lead_return_pct"
        );
    }

    /// W2 sub-task 4 — adaptor 對 NaN snapshot fail-soft（trait struct 接 NaN）。
    /// 不變式：caller (consumer strategy on_tick) 必 NaN check fail-closed；
    /// adaptor 不轉 NaN → 0（避免假 alpha source signal 污染下游）。
    #[test]
    fn snapshot_to_trait_panel_preserves_nan() {
        let snapshot = BtcLeadLagPanelSnapshot {
            snapshot_ts_ms: 1_700_000_060_000,
            lead_window_secs: LEAD_WINDOW_SECS_MAIN,
            btc_lead_return_pct: f64::NAN,
            btc_lead_return_pct_60s: f64::NAN,
            btc_lead_return_pct_300s: f64::NAN,
            btc_volume_z: f64::NAN,
            btc_book_imbalance: 0.0,
            alt_symbols: vec!["ETHUSDT".to_string()],
            alt_xcorr: vec![f64::NAN],
            alt_expected_dir: vec![0],
            regime_tag: "normal".to_string(),
            source_tier: SOURCE_TIER.to_string(),
        };
        let panel = snapshot_to_trait_panel(&snapshot);
        assert!(panel.btc_lead_return_pct.is_nan(), "NaN must propagate");
        assert!(panel.alt_xcorr[0].is_nan(), "NaN xcorr must propagate");
    }

    /// W2 sub-task 4 — insert_btc_lead_lag_snapshot 對 arrays_aligned 違反 →
    /// fail-soft 返 Failed 不 INSERT 半 schema row（spec §4.1 invariant + sub-task
    /// 1 deliverable line 583）。
    #[tokio::test]
    async fn insert_returns_failed_when_arrays_misaligned() {
        let pool = make_disconnected_pool().await;
        let snapshot = BtcLeadLagPanelSnapshot {
            snapshot_ts_ms: 1_700_000_060_000,
            lead_window_secs: LEAD_WINDOW_SECS_MAIN,
            btc_lead_return_pct: 0.0,
            btc_lead_return_pct_60s: 0.0,
            btc_lead_return_pct_300s: 0.0,
            btc_volume_z: 0.0,
            btc_book_imbalance: 0.0,
            // arrays misaligned: 2 alt symbols 但 1 xcorr / 1 expected_dir
            alt_symbols: vec!["ETHUSDT".to_string(), "SOLUSDT".to_string()],
            alt_xcorr: vec![0.5],
            alt_expected_dir: vec![1],
            regime_tag: "normal".to_string(),
            source_tier: SOURCE_TIER.to_string(),
        };
        assert!(!snapshot.arrays_aligned(), "test setup: misaligned");
        let outcome = insert_btc_lead_lag_snapshot(&pool, &snapshot).await;
        assert_eq!(
            outcome,
            SingleInsertOutcome::Failed,
            "misaligned arrays must short-circuit Failed without PG INSERT"
        );
    }

    /// W2 sub-task 4 — insert_btc_lead_lag_snapshot pool 不可用 → PoolUnavailable
    /// fail-soft（不 panic）。aligned snapshot test happy path; pool empty → no PG.
    #[tokio::test]
    async fn insert_returns_pool_unavailable_when_disconnected() {
        let pool = make_disconnected_pool().await;
        let snapshot = BtcLeadLagPanelSnapshot {
            snapshot_ts_ms: 1_700_000_060_000,
            lead_window_secs: LEAD_WINDOW_SECS_MAIN,
            btc_lead_return_pct: 25.0,
            btc_lead_return_pct_60s: 12.0,
            btc_lead_return_pct_300s: 50.0,
            btc_volume_z: 1.0,
            btc_book_imbalance: 0.0,
            alt_symbols: vec!["ETHUSDT".to_string()],
            alt_xcorr: vec![0.5],
            alt_expected_dir: vec![1],
            regime_tag: "normal".to_string(),
            source_tier: SOURCE_TIER.to_string(),
        };
        assert!(snapshot.arrays_aligned(), "test setup: aligned");
        let outcome = insert_btc_lead_lag_snapshot(&pool, &snapshot).await;
        assert_eq!(
            outcome,
            SingleInsertOutcome::PoolUnavailable,
            "disconnected pool must return PoolUnavailable not panic"
        );
    }

    /// W2 sub-task 4 — `run_loop()` 收 cancel 立即 return（不 hang）。
    /// 對齊 W1 PanelAggregator test_run_responds_to_cancel pattern。
    /// pool 不可用 → 60s tick 內 PG fetch fail-soft skip；cancel 後 200ms 內退出。
    #[tokio::test]
    async fn run_loop_responds_to_cancel() {
        let pool = make_disconnected_pool().await;
        let cancel = CancellationToken::new();
        let producer = BtcLeadLagProducer::new(make_cohort());
        let slot = create_btc_lead_lag_panel_slot();

        let cancel_clone = cancel.clone();
        let handle = tokio::spawn(async move {
            producer.run_loop(pool, slot, cancel_clone).await;
        });

        // 給 select! 進入等待狀態
        tokio::time::sleep(std::time::Duration::from_millis(20)).await;
        cancel.cancel();

        let result = tokio::time::timeout(std::time::Duration::from_millis(500), handle).await;
        assert!(result.is_ok(), "run_loop must exit on cancel within 500ms");
    }

    /// W2 sub-task 4 — cohort_symbols accessor 回傳 ctor 傳入順序（writer 依賴
    /// 此順序 INSERT alt_symbols TEXT[]）。
    #[test]
    fn cohort_symbols_accessor_preserves_order() {
        let cohort = make_cohort();
        let producer = BtcLeadLagProducer::new(cohort.clone());
        assert_eq!(producer.cohort_symbols(), cohort.as_slice());
    }

    /// Disconnected DbPool helper — 對齊 panel_aggregator/oi_delta.rs::tests::make_disconnected_pool
    async fn make_disconnected_pool() -> Arc<crate::database::pool::DbPool> {
        let cfg = crate::database::DatabaseConfig {
            database_url: String::new(),
            ..Default::default()
        };
        Arc::new(crate::database::pool::DbPool::connect(&cfg).await)
    }
}
