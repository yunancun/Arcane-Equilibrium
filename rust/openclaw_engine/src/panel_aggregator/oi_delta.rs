//! W-AUDIT-8a Phase B B-2 OI delta panel aggregator (WS-first chunk 2).
//!
//! MODULE_NOTE：本檔是 Sprint N+1 W1 IMPL sub-task 2 的核心 — oi_delta panel
//!   aggregator + V087 panel.oi_delta_panel writer + cohort filter + 1m flush
//!   boundary 邏輯 + 5m/15m/1h sliding window delta 計算。本 sub-task 範圍嚴格
//!   限定 aggregator core + writer（per dispatch v3.7 §3.1 W1-IMPL-β second chunk
//!   ~150-200 LOC），不做 cold-start REST backfill（留 sub-task 3/E1-γ）也不做
//!   WS event_rx subscription wire-up（留 sub-task 3/E1-γ）。
//!
//!   設計重點：
//!   1. `OIDeltaAggregator` 維護 cohort 25 sym 的 sliding window deque per sym
//!      （`(snapshot_ts_ms, oi_abs)` 最近 1h），cohort 不在內的 symbol update
//!      直接 ignored；
//!   2. `on_oi_update(symbol, oi_abs, snapshot_ts_ms)` 是 caller-driven API
//!      （本 sub-task 不訂閱 WS，由整合 sub-task 從 broadcast::Receiver
//!      drain Ticker variant 後呼叫此函數）；
//!   3. flush 走 1m boundary（per spec §3.3 60s 視窗 flush）；
//!   4. INSERT V087 panel.oi_delta_panel 對齊 schema：snapshot_ts_ms BIGINT
//!      + symbol TEXT + oi_abs DOUBLE PRECISION NOT NULL + oi_delta_5m_pct
//!      / 15m_pct / 1h_pct DOUBLE PRECISION NULLABLE + source_tier
//!      'bybit_v5_ws_open_interest'；
//!   5. ON CONFLICT (snapshot_ts_ms, symbol) DO UPDATE — idempotent on retry；
//!   6. delta 算法：sliding window deque lookup oi at (snapshot_ts_ms - window_ms)
//!      用 binary search find closest，window 不足 (history 長度不夠) 回 None
//!      → 寫 NULL → consumer 端 NaN check 後 fail-closed。
//!
//! Spec：docs/execution_plan/2026-05-10--w_audit_8a_phase_b_tier_2_collector_spec.md §3
//! V087 SQL：sql/migrations/V087__panel_oi_delta_panel.sql
//! Trait field 對齊：openclaw_core/src/alpha_surface.rs:159-175 OIDeltaPanel
//! Sister pattern：panel_aggregator/funding_curve.rs (sub-task 1 / E1-α)

use std::collections::{HashMap, HashSet, VecDeque};
use std::sync::Arc;

use sqlx::Postgres;
use tracing::{debug, warn};

use crate::database::batch_insert::{exec_single_insert, SingleInsertOutcome};
use crate::database::pool::DbPool;
use openclaw_core::alpha_surface::OIDeltaPanel;

/// 5 分鐘 window 毫秒（5 * 60 * 1000）。
pub const WINDOW_5M_MS: i64 = 5 * 60 * 1000;
/// 15 分鐘 window 毫秒（15 * 60 * 1000）。
pub const WINDOW_15M_MS: i64 = 15 * 60 * 1000;
/// 1 小時 window 毫秒（60 * 60 * 1000）。
pub const WINDOW_1H_MS: i64 = 60 * 60 * 1000;
/// Sliding window 保留上限（取 1h + 60s 安全邊際；舊資料自動 trim）。
pub const WINDOW_RETAIN_MS: i64 = WINDOW_1H_MS + 60_000;

/// `OIDeltaAggregator` — 25-symbol cohort open interest delta aggregator。
///
/// 不變式（per spec §3.3）：
/// - cohort 是 hardcoded 25-sym snapshot（W1 IMPL 階段）；W-AUDIT-8c phase 改 dynamic
/// - history key 是 symbol、value 是 VecDeque<(snapshot_ts_ms, oi_abs)>
///   保留最近 ~1h 視窗，舊於 cutoff 的 entry 自動 pop_front
/// - non-cohort symbol update → silent ignored（cohort filter）
/// - flush() 寫 PG 用 ON CONFLICT (snapshot_ts_ms, symbol) DO UPDATE
///   滿足 idempotency（同一 snapshot_ts_ms 重 flush 不重複插）
/// - delta 計算：window 內 binary search 找最接近 (current_ts - window_ms) 的 entry，
///   若 history 最舊 entry 比 (current_ts - window_ms) 還新 → window 不足 → None → SQL NULL
pub struct OIDeltaAggregator {
    /// Cohort 25-sym（per spec §3.1，hardcoded W1）；O(1) lookup 用 HashSet。
    cohort: HashSet<String>,
    /// Per-sym sliding window: VecDeque<(snapshot_ts_ms, oi_abs)>，保留 ~1h history。
    /// 設計理由：VecDeque 的 push_back O(1) + pop_front O(1) + 線性 lookup O(N)
    /// 對 N≈3600 (1h × 1Hz update) 仍 sub-millisecond。
    history: HashMap<String, VecDeque<(i64, f64)>>,
    /// PG pool（fail-soft：pool 不可用時 flush 寫入靜默 skip + history 保留）。
    db_pool: Arc<DbPool>,
}

impl OIDeltaAggregator {
    /// 建構 aggregator。
    ///
    /// `cohort_symbols` 是 W1 IMPL hardcoded 25-sym list（per spec §3.1）；
    /// 重複項自動 dedupe（HashSet）。
    pub fn new(db_pool: Arc<DbPool>, cohort_symbols: Vec<String>) -> Self {
        Self {
            cohort: cohort_symbols.into_iter().collect(),
            history: HashMap::new(),
            db_pool,
        }
    }

    /// 處理單筆 OI update。
    ///
    /// `oi_abs` = Bybit V5 tickers stream `openInterest` 原始值（合約張數絕對值）；
    /// `snapshot_ts_ms` = WS event timestamp（ms epoch）。
    ///
    /// 行為：
    /// - non-cohort symbol → silent return（不 buffer、不 log，因 WS Ticker
    ///   volume 大；log 走 cohort drift audit 路徑由 caller 處理）
    /// - cohort symbol → push_back 入 history deque + trim 舊於 (now - 1h - 60s) entry
    pub fn on_oi_update(&mut self, symbol: &str, oi_abs: f64, snapshot_ts_ms: i64) {
        if !self.cohort.contains(symbol) {
            return;
        }
        let window = self
            .history
            .entry(symbol.to_string())
            .or_insert_with(VecDeque::new);
        window.push_back((snapshot_ts_ms, oi_abs));

        // Trim：刪除舊於 (snapshot_ts_ms - WINDOW_RETAIN_MS) 的 entry
        // 保留邊際 60s 確保 1h window lookup 一定找得到 candidate
        let cutoff = snapshot_ts_ms - WINDOW_RETAIN_MS;
        while window
            .front()
            .map(|(t, _)| *t < cutoff)
            .unwrap_or(false)
        {
            window.pop_front();
        }

        debug!(
            target: "panel_aggregator",
            symbol = symbol,
            oi_abs = oi_abs,
            snapshot_ts_ms = snapshot_ts_ms,
            history_len = window.len(),
            "oi update buffered"
        );
    }

    /// 取當前 history 大小（test + observability 用）。
    pub fn history_len(&self) -> usize {
        self.history.len()
    }

    /// 取單一 symbol 的 history deque 長度（test 用）。
    #[cfg(test)]
    pub fn history_len_for(&self, symbol: &str) -> usize {
        self.history.get(symbol).map(|d| d.len()).unwrap_or(0)
    }

    /// 取 cohort 大小（test + observability 用）。
    pub fn cohort_size(&self) -> usize {
        self.cohort.len()
    }

    /// W1 sub-task 3 (E1-γ, 2026-05-11) — 從當前 history 構造 OIDeltaPanel snapshot。
    ///
    /// 設計：caller (panel_subscriber.rs run loop) 在 1m flush boundary
    /// 呼叫此函數取 snapshot 寫 IPC slot；history 不會被 drain（與 funding_curve 不同），
    /// 故 snapshot/flush 順序不影響 history。
    ///
    /// 行為：
    /// - history 空 → 回 None（caller 不更新 slot；既有 panel 保留）
    /// - 對每個 cohort sym 取 history 最後 entry 為 current_oi，算 5m/15m/1h delta
    ///   （window 不足 → NaN）
    /// - 對齊 OIDeltaPanel 不變式：symbols[i] ↔ oi_abs[i] ↔ oi_delta_*_pct[i]
    /// - source_tier = "bybit_v5_ws_open_interest"（與 PG INSERT 保持一致）
    /// - delta None → f64::NAN（OIDeltaPanel.oi_delta_*_pct 為 Vec<f64> 不支援 Option，
    ///   consumer 端必判 NaN 走 fail-closed；對齊 V087 SQL 寫 NULL → consumer NaN check 同語意）
    pub fn snapshot_panel(&self, snapshot_ts_ms: i64) -> Option<OIDeltaPanel> {
        if self.history.is_empty() {
            return None;
        }
        // 對 history iter 順序穩定化：取 key 排序 → 跨 process 一致 + 利於診斷
        let mut entries: Vec<(&String, &VecDeque<(i64, f64)>)> = self.history.iter().collect();
        entries.sort_by(|a, b| a.0.cmp(b.0));

        let mut symbols: Vec<String> = Vec::with_capacity(entries.len());
        let mut oi_abs_vec: Vec<f64> = Vec::with_capacity(entries.len());
        let mut oi_delta_5m_pct: Vec<f64> = Vec::with_capacity(entries.len());
        let mut oi_delta_15m_pct: Vec<f64> = Vec::with_capacity(entries.len());
        let mut oi_delta_1h_pct: Vec<f64> = Vec::with_capacity(entries.len());

        for (sym, hist) in entries {
            let (last_ts, last_oi) = match hist.back().copied() {
                Some(v) => v,
                None => continue, // empty deque (理論不應發生; defensive skip)
            };
            symbols.push(sym.clone());
            oi_abs_vec.push(last_oi);
            // window 不足 → None → 寫 NaN（consumer 端必 NaN check fail-closed）
            oi_delta_5m_pct.push(
                Self::compute_delta_pct(hist, last_ts, last_oi, WINDOW_5M_MS)
                    .unwrap_or(f64::NAN),
            );
            oi_delta_15m_pct.push(
                Self::compute_delta_pct(hist, last_ts, last_oi, WINDOW_15M_MS)
                    .unwrap_or(f64::NAN),
            );
            oi_delta_1h_pct.push(
                Self::compute_delta_pct(hist, last_ts, last_oi, WINDOW_1H_MS)
                    .unwrap_or(f64::NAN),
            );
        }

        if symbols.is_empty() {
            return None;
        }

        Some(OIDeltaPanel {
            symbols,
            oi_delta_5m_pct,
            oi_delta_15m_pct,
            oi_delta_1h_pct,
            oi_abs: oi_abs_vec,
            snapshot_ts_ms,
            source_tier: "bybit_v5_ws_open_interest".to_string(),
        })
    }

    /// 計算 window_ms 對應的 OI delta percent。
    ///
    /// 算法：
    /// 1. 在 history deque 內找第一個 ts ≥ (current_ts - window_ms) 的 entry —
    ///    這是「視窗開始」邊界；視窗內最早可用 baseline。
    /// 2. 若 history 最舊 entry 仍比 (current_ts - window_ms) 新 → window 不足 → None
    /// 3. delta_pct = (current_oi - baseline_oi) / baseline_oi × 100
    ///    baseline 為 0 的特例（理論上 OI 永不為 0）→ None 避免除 0
    fn compute_delta_pct(
        history: &VecDeque<(i64, f64)>,
        current_ts: i64,
        current_oi: f64,
        window_ms: i64,
    ) -> Option<f64> {
        let target_ts = current_ts - window_ms;

        // history 最舊 entry 仍比 target_ts 新 → window 不足
        let oldest_ts = history.front().map(|(t, _)| *t)?;
        if oldest_ts > target_ts {
            return None;
        }

        // 找第一個 ts ≥ target_ts 的 entry 作 baseline
        // VecDeque 是 ts 升序（push_back 入），線性掃 O(N) 對 N≈3600 sub-ms
        let baseline_oi = history
            .iter()
            .find(|(t, _)| *t >= target_ts)
            .map(|(_, oi)| *oi)?;

        if baseline_oi.abs() < f64::EPSILON {
            return None;
        }

        Some((current_oi - baseline_oi) / baseline_oi * 100.0)
    }

    /// Flush history 寫 V087 panel.oi_delta_panel。
    ///
    /// `snapshot_ts_ms` = aggregator caller 給的 flush 時戳（ms epoch）；
    /// 通常是 1m boundary（per spec §3.3 60s 視窗）。同 snapshot 內所有
    /// cohort row 共享同 snapshot_ts_ms（hypertable time column 對齊）。
    ///
    /// 行為：
    /// - history 空 → no-op return (0, 0)（hot path 友好）；
    /// - 對每個 cohort sym，取 history 最後 entry 為 current_oi，
    ///   計算 5m/15m/1h delta（window 不足 → NULL）
    /// - pool 不可用 → 全 row PoolUnavailable 計入 fail_count，history 保留
    ///   （deque trim 由 on_oi_update 自動處理；不主動清）；
    /// - 部分 row INSERT 失敗 → 失敗 row 計入 fail_count，history 仍保留
    ///   （與 funding_curve drain 不同：oi_delta 需 history 持續 maintain
    ///   才能算下個 snapshot delta，不能 drain）；
    /// - 全 row 成功 → history 仍保留供下次 flush。
    ///
    /// 回傳：(成功插入 row 數, 失敗 row 數)。
    pub async fn flush(&mut self, snapshot_ts_ms: i64) -> (usize, usize) {
        if self.history.is_empty() {
            return (0, 0);
        }

        let mut ok_count = 0usize;
        let mut fail_count = 0usize;

        // 取每 sym 的最後 entry 作 current_oi + 算 3 windows delta
        // 構造 (sym, current_oi, d5m, d15m, d1h) 後寫 V087
        let snapshot_rows: Vec<(String, f64, Option<f64>, Option<f64>, Option<f64>)> = self
            .history
            .iter()
            .filter_map(|(sym, hist)| {
                let (last_ts, last_oi) = hist.back().copied()?;
                let d5m = Self::compute_delta_pct(hist, last_ts, last_oi, WINDOW_5M_MS);
                let d15m = Self::compute_delta_pct(hist, last_ts, last_oi, WINDOW_15M_MS);
                let d1h = Self::compute_delta_pct(hist, last_ts, last_oi, WINDOW_1H_MS);
                Some((sym.clone(), last_oi, d5m, d15m, d1h))
            })
            .collect();

        for (symbol, oi_abs, d5m, d15m, d1h) in snapshot_rows {
            let outcome = insert_oi_snapshot(
                &self.db_pool,
                snapshot_ts_ms,
                &symbol,
                oi_abs,
                d5m,
                d15m,
                d1h,
            )
            .await;
            match outcome {
                SingleInsertOutcome::Ok(_) => ok_count += 1,
                SingleInsertOutcome::Failed => {
                    fail_count += 1;
                    warn!(
                        target: "panel_aggregator",
                        snapshot_ts_ms = snapshot_ts_ms,
                        symbol = %symbol,
                        "oi delta snapshot INSERT failed"
                    );
                }
                SingleInsertOutcome::PoolUnavailable => {
                    // pool 不可用全 row 都會回 PoolUnavailable；無 retry 必要，
                    // 留下次 ticker tick + flush 自然恢復（per spec §3.3 fail-soft）。
                    fail_count += 1;
                }
            }
        }

        debug!(
            target: "panel_aggregator",
            snapshot_ts_ms = snapshot_ts_ms,
            ok_count = ok_count,
            fail_count = fail_count,
            "oi delta flush complete"
        );

        (ok_count, fail_count)
    }
}

/// INSERT 單筆 oi delta snapshot 進 V087 panel.oi_delta_panel。
///
/// SQL 對齊 spec §3.2 schema + V087 PG migration：
/// - snapshot_ts_ms BIGINT（hypertable time column）
/// - symbol TEXT
/// - oi_delta_5m_pct DOUBLE PRECISION NULLABLE（None → SQL NULL）
/// - oi_delta_15m_pct DOUBLE PRECISION NULLABLE
/// - oi_delta_1h_pct DOUBLE PRECISION NULLABLE
/// - oi_abs DOUBLE PRECISION NOT NULL
/// - source_tier TEXT 固定 'bybit_v5_ws_open_interest'（覆蓋 V087 default
///   'bybit_v5_public'，per spec §3.3 對齊 funding_curve 'bybit_v5_ws_tickers'
///   命名風格 — 區分 panel collector 來源於 WS open_interest field）
///
/// ON CONFLICT (snapshot_ts_ms, symbol) DO UPDATE：
/// - PK = (snapshot_ts_ms, symbol)；同一 snapshot 重 flush 同 sym 不會 dup
/// - DO UPDATE 場景：aggregator 在同一 snapshot_ts_ms 內 flush 兩次
///   後 flush 的值代表更新的 history state，semantic 上後者勝
pub(crate) async fn insert_oi_snapshot(
    pool: &Arc<DbPool>,
    snapshot_ts_ms: i64,
    symbol: &str,
    oi_abs: f64,
    oi_delta_5m_pct: Option<f64>,
    oi_delta_15m_pct: Option<f64>,
    oi_delta_1h_pct: Option<f64>,
) -> SingleInsertOutcome {
    let query = sqlx::query::<Postgres>(
        "INSERT INTO panel.oi_delta_panel \
         (snapshot_ts_ms, symbol, oi_abs, oi_delta_5m_pct, oi_delta_15m_pct, \
          oi_delta_1h_pct, source_tier) \
         VALUES ($1, $2, $3, $4, $5, $6, $7) \
         ON CONFLICT (snapshot_ts_ms, symbol) DO UPDATE SET \
            oi_abs = EXCLUDED.oi_abs, \
            oi_delta_5m_pct = EXCLUDED.oi_delta_5m_pct, \
            oi_delta_15m_pct = EXCLUDED.oi_delta_15m_pct, \
            oi_delta_1h_pct = EXCLUDED.oi_delta_1h_pct, \
            source_tier = EXCLUDED.source_tier",
    )
    .bind(snapshot_ts_ms)
    .bind(symbol)
    .bind(oi_abs)
    .bind(oi_delta_5m_pct)
    .bind(oi_delta_15m_pct)
    .bind(oi_delta_1h_pct)
    .bind("bybit_v5_ws_open_interest");
    exec_single_insert(pool, "panel.oi_delta_panel", query).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::database::DatabaseConfig;

    /// Build an empty/disconnected DbPool for unit tests — `is_available()` false。
    /// 寫入路徑會 fail-soft 回 PoolUnavailable，不需要真實 PG 連線。
    async fn make_disconnected_pool() -> Arc<DbPool> {
        let cfg = DatabaseConfig {
            database_url: String::new(), // empty → pool=None
            ..Default::default()
        };
        Arc::new(DbPool::connect(&cfg).await)
    }

    /// Helper：build aggregator with 3-sym test cohort（不需 25 sym，邏輯一致）。
    async fn make_aggregator() -> OIDeltaAggregator {
        let pool = make_disconnected_pool().await;
        let cohort = vec![
            "BTCUSDT".to_string(),
            "ETHUSDT".to_string(),
            "SOLUSDT".to_string(),
        ];
        OIDeltaAggregator::new(pool, cohort)
    }

    #[tokio::test]
    async fn test_snapshot_panel_empty_history_returns_none() {
        // PASS：empty history → snapshot_panel 回 None
        let agg = make_aggregator().await;
        assert!(agg.snapshot_panel(1_700_000_060_000).is_none());
    }

    #[tokio::test]
    async fn test_snapshot_panel_history_with_data_returns_some_with_nan_when_window_short() {
        // PASS：history 有 1 entry → snapshot 回 Some 但所有 delta 為 NaN（window 不足）
        let mut agg = make_aggregator().await;
        agg.on_oi_update("BTCUSDT", 12345.6, 1_700_000_000_000);
        let snap = agg
            .snapshot_panel(1_700_000_060_000)
            .expect("snapshot must be Some when history has data");
        assert_eq!(snap.symbols.len(), 1);
        assert_eq!(snap.oi_abs.len(), 1);
        assert_eq!(snap.snapshot_ts_ms, 1_700_000_060_000);
        assert_eq!(snap.source_tier, "bybit_v5_ws_open_interest");
        // 1 entry → 5m/15m/1h window 全不足 → all NaN
        assert!(snap.oi_delta_5m_pct[0].is_nan(), "5m delta should be NaN");
        assert!(snap.oi_delta_15m_pct[0].is_nan(), "15m delta should be NaN");
        assert!(snap.oi_delta_1h_pct[0].is_nan(), "1h delta should be NaN");
    }

    #[tokio::test]
    async fn test_cohort_symbol_oi_update_buffers() {
        // PASS：cohort-symbol oi update → history 更新 + cohort filter
        let mut agg = make_aggregator().await;
        agg.on_oi_update("BTCUSDT", 12345.6, 1_700_000_000_000);
        assert_eq!(agg.history_len(), 1);
        assert_eq!(agg.history_len_for("BTCUSDT"), 1);
        let hist = agg.history.get("BTCUSDT").expect("BTCUSDT must be in history");
        let (ts, oi) = hist.back().unwrap();
        assert_eq!(*ts, 1_700_000_000_000);
        assert!((oi - 12345.6).abs() < 1e-9);
    }

    #[tokio::test]
    async fn test_non_cohort_symbol_ignored() {
        // PASS：non-cohort symbol → history 不變、無 panic
        let mut agg = make_aggregator().await;
        agg.on_oi_update("DOGEUSDT", 999.9, 1_700_000_000_000);
        assert_eq!(agg.history_len(), 0, "non-cohort sym must not enter history");
        // cohort symbol 仍可正常 buffer
        agg.on_oi_update("ETHUSDT", 5000.0, 1_700_000_000_000);
        assert_eq!(agg.history_len(), 1);
    }

    #[tokio::test]
    async fn test_5m_delta_computation_correct() {
        // PASS：sufficient history → compute_delta_pct 算出正確 5m delta
        // baseline_5m_ago = 1000.0；current = 1100.0 → delta = +10.0%
        let mut agg = make_aggregator().await;
        let base_ts = 1_700_000_000_000_i64;
        // 5m 前的 baseline entry
        agg.on_oi_update("BTCUSDT", 1000.0, base_ts);
        // current entry (5 min later)
        let current_ts = base_ts + WINDOW_5M_MS;
        agg.on_oi_update("BTCUSDT", 1100.0, current_ts);

        let hist = agg.history.get("BTCUSDT").unwrap();
        let delta = OIDeltaAggregator::compute_delta_pct(
            hist,
            current_ts,
            1100.0,
            WINDOW_5M_MS,
        );
        assert!(delta.is_some(), "5m window 充足 → must return Some");
        let d = delta.unwrap();
        // (1100 - 1000) / 1000 * 100 = 10.0
        assert!((d - 10.0).abs() < 1e-6, "delta_5m_pct expected ~10.0, got {}", d);
    }

    #[tokio::test]
    async fn test_insufficient_window_returns_none() {
        // PASS：history 不夠長（只有 current entry，無 5m 前 baseline）→ delta = None
        let mut agg = make_aggregator().await;
        let current_ts = 1_700_000_000_000_i64;
        // 只有 current entry，無更早 history
        agg.on_oi_update("BTCUSDT", 1000.0, current_ts);

        let hist = agg.history.get("BTCUSDT").unwrap();
        let delta = OIDeltaAggregator::compute_delta_pct(
            hist,
            current_ts,
            1000.0,
            WINDOW_5M_MS,
        );
        // history 最舊 entry = current_ts；target_ts = current_ts - 5m
        // oldest_ts (current_ts) > target_ts (current_ts - 5m) → None
        assert!(delta.is_none(), "insufficient window must return None");
    }

    #[tokio::test]
    async fn test_flush_empty_history_returns_zero() {
        // PASS：empty history flush → (0, 0) no-op，不觸 PG（hot path 友好）
        let mut agg = make_aggregator().await;
        let (ok, fail) = agg.flush(1_700_000_060_000).await;
        assert_eq!(ok, 0);
        assert_eq!(fail, 0);
    }

    #[tokio::test]
    async fn test_flush_pool_unavailable_history_retained() {
        // PASS：pool 不可用 → 全 row 計入 fail_count；history 仍保留
        // （與 funding_curve drain 不同：oi_delta 需 history maintain 算下個 delta）
        let mut agg = make_aggregator().await;
        agg.on_oi_update("BTCUSDT", 1000.0, 1_700_000_000_000);
        agg.on_oi_update("ETHUSDT", 5000.0, 1_700_000_000_000);
        assert_eq!(agg.history_len(), 2);

        let (ok, fail) = agg.flush(1_700_000_060_000).await;
        assert_eq!(ok, 0, "pool unavailable → 0 ok");
        assert_eq!(fail, 2, "all rows fail (PoolUnavailable counted as fail)");
        // 不同於 funding_curve：history 保留供下次 flush
        assert_eq!(agg.history_len(), 2, "history retained on failed flush");
    }

    #[tokio::test]
    async fn test_window_trim_evicts_old_entries() {
        // PASS：on_oi_update 自動 trim 舊於 (now - 1h - 60s) 的 entry
        let mut agg = make_aggregator().await;
        let very_old_ts = 1_700_000_000_000_i64;
        agg.on_oi_update("BTCUSDT", 1000.0, very_old_ts);
        // 1.5h 後 push 新 entry → trim 應該 evict very_old_ts
        let now_ts = very_old_ts + WINDOW_RETAIN_MS + 1_000;
        agg.on_oi_update("BTCUSDT", 1100.0, now_ts);

        let hist = agg.history.get("BTCUSDT").unwrap();
        assert_eq!(hist.len(), 1, "old entry trimmed");
        assert_eq!(hist.back().unwrap().0, now_ts, "only latest entry remains");
    }

    #[tokio::test]
    async fn test_cohort_size_initialization() {
        // PASS：cohort 初始化大小驗證（dedupe HashSet）
        let pool = make_disconnected_pool().await;
        // 故意送 4 sym 含 1 重複 → cohort 應為 3
        let dup_cohort = vec![
            "BTCUSDT".to_string(),
            "ETHUSDT".to_string(),
            "BTCUSDT".to_string(),
            "SOLUSDT".to_string(),
        ];
        let agg = OIDeltaAggregator::new(pool, dup_cohort);
        assert_eq!(agg.cohort_size(), 3, "duplicate cohort entries deduped");
        assert_eq!(agg.history_len(), 0);
    }

    #[test]
    fn test_insert_sql_locks_v087_columns() {
        // PASS：grep guard — INSERT SQL 必含 V087 schema 7 column + ON CONFLICT
        // 防 sub-task 3 IMPL drift 漏改 SQL
        let src = include_str!("oi_delta.rs");
        for token in [
            "INTO panel.oi_delta_panel",
            "snapshot_ts_ms",
            "symbol",
            "oi_abs",
            "oi_delta_5m_pct",
            "oi_delta_15m_pct",
            "oi_delta_1h_pct",
            "source_tier",
            "ON CONFLICT (snapshot_ts_ms, symbol)",
            "DO UPDATE",
            "bybit_v5_ws_open_interest",
        ] {
            assert!(src.contains(token), "INSERT SQL missing: {token}");
        }
    }
}
