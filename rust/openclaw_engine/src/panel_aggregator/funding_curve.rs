//! W-AUDIT-8a Phase B B-1 funding curve aggregator (WS-first chunk 1).
//!
//! MODULE_NOTE：本檔是 Sprint N+1 W1 IMPL sub-task 1 的核心 — funding curve
//!   aggregator + V085 panel.funding_rates_panel writer + cohort filter +
//!   1m flush boundary 邏輯。本 sub-task 範圍嚴格限定 broadcast core 框架 +
//!   funding_curve writer（per dispatch v3.7 §3.1 W1-IMPL-α first chunk
//!   ~150-200 LOC），不做 oi_delta（留 sub-task 2/E1-β）也不做 WS event_rx
//!   subscription wire-up（留 sub-task 3/E1-γ）。
//!
//!   設計重點：
//!   1. `FundingCurveAggregator` 維護 cohort 25 sym 的 (rate, next_funding_ms)
//!      buffer，cohort 不在內的 symbol update 直接 ignored；
//!   2. `on_funding_update(symbol, rate_raw, next_ts)` 是 caller-driven API
//!      （本 sub-task 不訂閱 WS，由整合 sub-task 從 broadcast::Receiver
//!      drain Ticker variant 後呼叫此函數）；
//!   3. flush 走 1m boundary（per spec §2.3 60s 視窗 flush）；
//!   4. INSERT V085 panel.funding_rates_panel 對齊 schema：snapshot_ts_ms
//!      BIGINT + symbol TEXT + funding_rate_bps DOUBLE PRECISION（rate × 10000）
//!      + next_funding_ms BIGINT + source_tier 'bybit_v5_ws_tickers'；
//!   5. ON CONFLICT (snapshot_ts_ms, symbol) DO UPDATE — idempotent on retry。
//!
//! Spec：docs/execution_plan/2026-05-10--w_audit_8a_phase_b_tier_2_collector_spec.md §2
//! V085 SQL：sql/migrations/V085__panel_funding_curve.sql
//! Trait field 對齊：openclaw_core/src/alpha_surface.rs:127-140 FundingCurveSnapshot

use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use sqlx::Postgres;
use tracing::{debug, warn};

use crate::database::batch_insert::{exec_single_insert, SingleInsertOutcome};
use crate::database::pool::DbPool;
use openclaw_core::alpha_surface::FundingCurveSnapshot;

/// `FundingCurveAggregator` — 25-symbol cohort funding rate aggregator。
///
/// 不變式（per spec §2.3）：
/// - cohort 是 hardcoded 25-sym snapshot（W1 IMPL 階段）；W-AUDIT-8c phase 改 dynamic
/// - buffer key 是 symbol、value 是 (funding_rate_bps, next_funding_ms)
///   funding_rate_bps = WS broadcast raw rate × 10000（per spec §2.3 line 180）
/// - non-cohort symbol update → silent ignored（cohort filter）
/// - flush() 寫 PG 用 ON CONFLICT (snapshot_ts_ms, symbol) DO UPDATE
///   滿足 idempotency（同一 snapshot_ts_ms 重 flush 不重複插）
pub struct FundingCurveAggregator {
    /// Cohort 25-sym（per spec §2.1，hardcoded W1）；O(1) lookup 用 HashSet。
    cohort: HashSet<String>,
    /// Buffer：symbol → (funding_rate_bps, next_funding_ms)。
    /// 每次 on_funding_update overwrite latest（同 sym 多次 update 取最後）。
    buffer: HashMap<String, (f64, i64)>,
    /// PG pool（fail-soft：pool 不可用時 flush 寫入靜默 skip + buffer 保留）。
    db_pool: Arc<DbPool>,
}

impl FundingCurveAggregator {
    /// 建構 aggregator。
    ///
    /// `cohort_symbols` 是 W1 IMPL hardcoded 25-sym list（per spec §2.1）；
    /// 重複項自動 dedupe（HashSet）。
    pub fn new(db_pool: Arc<DbPool>, cohort_symbols: Vec<String>) -> Self {
        Self {
            cohort: cohort_symbols.into_iter().collect(),
            buffer: HashMap::new(),
            db_pool,
        }
    }

    /// 處理單筆 funding update。
    ///
    /// `rate_raw` = Bybit V5 tickers stream `fundingRate` 原始值（小數，
    /// 例 0.0001 = 1 bps）；本函數 ×10000 轉 bps 入 buffer。
    /// `next_funding_ms` = Bybit V5 tickers stream `nextFundingTime`（ms epoch）。
    ///
    /// non-cohort symbol → silent return（不 buffer、不 log，因 WS Ticker
    /// volume 大；log 走 cohort drift audit 路徑由 caller 處理）。
    pub fn on_funding_update(&mut self, symbol: &str, rate_raw: f64, next_funding_ms: i64) {
        if !self.cohort.contains(symbol) {
            return;
        }
        let funding_rate_bps = rate_raw * 10000.0;
        self.buffer
            .insert(symbol.to_string(), (funding_rate_bps, next_funding_ms));
        debug!(
            target: "panel_aggregator",
            symbol = symbol,
            funding_rate_bps = funding_rate_bps,
            next_funding_ms = next_funding_ms,
            "funding update buffered"
        );
    }

    /// 取當前 buffer 大小（test + observability 用）。
    pub fn buffer_len(&self) -> usize {
        self.buffer.len()
    }

    /// 取 cohort 大小（test + observability 用）。
    pub fn cohort_size(&self) -> usize {
        self.cohort.len()
    }

    /// W1 sub-task 3 (E1-γ, 2026-05-11) — 從當前 buffer 構造 FundingCurveSnapshot。
    ///
    /// 設計：caller (panel_subscriber.rs run loop) 在 1m flush boundary
    /// **先**呼叫此函數取 snapshot，**再**呼叫 `flush()` 把 buffer 寫 PG。
    /// 順序重要：`flush()` 會 drain buffer，先 snapshot 後 flush 才能取得本 snapshot 內容。
    ///
    /// 行為：
    /// - buffer 空 → 回 None（caller 不更新 slot；既有 panel 保留）
    /// - buffer 有資料 → 構造 same-index `Vec<String>` / `Vec<f64>` / `Vec<i64>`
    ///   對齊 `FundingCurveSnapshot` 不變式（symbols[i] ↔ funding_rates_bps[i] ↔ next_funding_ms[i]）
    /// - source_tier = "bybit_v5_ws_tickers"（與 PG INSERT 保持一致）
    pub fn snapshot_panel(&self, snapshot_ts_ms: i64) -> Option<FundingCurveSnapshot> {
        if self.buffer.is_empty() {
            return None;
        }
        // 對 buffer iter 順序穩定化：取 key 排序 → 跨 process 一致 + 利於診斷
        let mut entries: Vec<(&String, &(f64, i64))> = self.buffer.iter().collect();
        entries.sort_by(|a, b| a.0.cmp(b.0));

        let mut symbols: Vec<String> = Vec::with_capacity(entries.len());
        let mut funding_rates_bps: Vec<f64> = Vec::with_capacity(entries.len());
        let mut next_funding_ms: Vec<i64> = Vec::with_capacity(entries.len());
        for (sym, (rate_bps, next_ms)) in entries {
            symbols.push(sym.clone());
            funding_rates_bps.push(*rate_bps);
            next_funding_ms.push(*next_ms);
        }
        Some(FundingCurveSnapshot {
            symbols,
            funding_rates_bps,
            next_funding_ms,
            snapshot_ts_ms,
            source_tier: "bybit_v5_ws_tickers".to_string(),
        })
    }

    /// Flush buffer 寫 V085 panel.funding_rates_panel。
    ///
    /// `snapshot_ts_ms` = aggregator caller 給的 flush 時戳（ms epoch）；
    /// 通常是 1m boundary（per spec §2.3 60s 視窗）。同 snapshot 內所有
    /// cohort row 共享同 snapshot_ts_ms（hypertable time column 對齊）。
    ///
    /// 行為：
    /// - buffer 空 → no-op return Ok(0)（hot path 友好）；
    /// - pool 不可用 → 全 row PoolUnavailable，buffer 保留待下次 flush；
    /// - 部分 row INSERT 失敗 → 失敗 row 計入 failed_rows 回傳，**不**
    ///   保留 buffer（spec §2.3 失敗 mode：log ERROR + 下個 ticker tick 自動恢復；
    ///   保留 buffer 會導致 stale data 寫入下個 snapshot_ts_ms 雙寫衝突）；
    /// - 全 row 成功 → buffer 清空。
    ///
    /// 回傳：(成功插入 row 數, 失敗 row 數)。
    pub async fn flush(&mut self, snapshot_ts_ms: i64) -> (usize, usize) {
        if self.buffer.is_empty() {
            return (0, 0);
        }

        // 取 buffer snapshot 後就清空，避免 INSERT 期間並發 on_funding_update
        // 寫入下個 snapshot 的資料污染本次 flush。
        let rows: Vec<(String, f64, i64)> = self
            .buffer
            .drain()
            .map(|(sym, (rate_bps, next_ms))| (sym, rate_bps, next_ms))
            .collect();

        let mut ok_count = 0usize;
        let mut fail_count = 0usize;

        for (symbol, funding_rate_bps, next_funding_ms) in rows {
            let outcome = insert_funding_snapshot(
                &self.db_pool,
                snapshot_ts_ms,
                &symbol,
                funding_rate_bps,
                next_funding_ms,
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
                        "funding snapshot INSERT failed"
                    );
                }
                SingleInsertOutcome::PoolUnavailable => {
                    // pool 不可用全 row 都會回 PoolUnavailable；無 retry 必要，
                    // 留下次 ticker tick + flush 自然恢復（per spec §2.3 fail-soft）。
                    fail_count += 1;
                }
            }
        }

        debug!(
            target: "panel_aggregator",
            snapshot_ts_ms = snapshot_ts_ms,
            ok_count = ok_count,
            fail_count = fail_count,
            "funding curve flush complete"
        );

        (ok_count, fail_count)
    }
}

/// INSERT 單筆 funding snapshot 進 V085 panel.funding_rates_panel。
///
/// SQL 對齊 spec §2.2 schema + V085 PG migration：
/// - snapshot_ts_ms BIGINT（hypertable time column）
/// - symbol TEXT
/// - funding_rate_bps DOUBLE PRECISION（caller 端已 ×10000 轉 bps）
/// - next_funding_ms BIGINT
/// - source_tier TEXT 固定 'bybit_v5_ws_tickers'（覆蓋 V085 default
///   'bybit_v5_public'，per spec §2.3 line 211）
///
/// ON CONFLICT (snapshot_ts_ms, symbol) DO UPDATE：
/// - PK = (snapshot_ts_ms, symbol)；同一 snapshot 重 flush 同 sym 不會 dup
/// - DO UPDATE 場景：aggregator 在同一 snapshot_ts_ms 內 flush 兩次
///   （理論上不該發生，但 ON CONFLICT DO UPDATE 比 DO NOTHING 更語意正確：
///   後 flush 的值代表更新的 buffer state）
pub(crate) async fn insert_funding_snapshot(
    pool: &Arc<DbPool>,
    snapshot_ts_ms: i64,
    symbol: &str,
    funding_rate_bps: f64,
    next_funding_ms: i64,
) -> SingleInsertOutcome {
    let query = sqlx::query::<Postgres>(
        "INSERT INTO panel.funding_rates_panel \
         (snapshot_ts_ms, symbol, funding_rate_bps, next_funding_ms, source_tier) \
         VALUES ($1, $2, $3, $4, $5) \
         ON CONFLICT (snapshot_ts_ms, symbol) DO UPDATE SET \
            funding_rate_bps = EXCLUDED.funding_rate_bps, \
            next_funding_ms = EXCLUDED.next_funding_ms, \
            source_tier = EXCLUDED.source_tier",
    )
    .bind(snapshot_ts_ms)
    .bind(symbol)
    .bind(funding_rate_bps)
    .bind(next_funding_ms)
    .bind("bybit_v5_ws_tickers");
    exec_single_insert(pool, "panel.funding_rates_panel", query).await
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
    async fn make_aggregator() -> FundingCurveAggregator {
        let pool = make_disconnected_pool().await;
        let cohort = vec![
            "BTCUSDT".to_string(),
            "ETHUSDT".to_string(),
            "SOLUSDT".to_string(),
        ];
        FundingCurveAggregator::new(pool, cohort)
    }

    #[tokio::test]
    async fn test_cohort_symbol_funding_update_buffers() {
        // PASS：cohort-symbol funding update → buffer 更新（rate × 10000 入 bps）
        let mut agg = make_aggregator().await;
        agg.on_funding_update("BTCUSDT", 0.0001, 1_700_000_000_000);
        assert_eq!(agg.buffer_len(), 1);
        let entry = agg.buffer.get("BTCUSDT").expect("BTCUSDT must be buffered");
        // 0.0001 raw → 1.0 bps（per spec §2.3 line 180）
        assert!((entry.0 - 1.0).abs() < 1e-9, "rate × 10000 conversion");
        assert_eq!(entry.1, 1_700_000_000_000);
    }

    #[tokio::test]
    async fn test_non_cohort_symbol_ignored() {
        // PASS：non-cohort symbol → buffer 不變、無 panic
        let mut agg = make_aggregator().await;
        agg.on_funding_update("DOGEUSDT", 0.0002, 1_700_000_000_000);
        assert_eq!(agg.buffer_len(), 0, "non-cohort sym must not enter buffer");
        // cohort symbol 仍可正常 buffer
        agg.on_funding_update("ETHUSDT", 0.00005, 1_700_000_000_000);
        assert_eq!(agg.buffer_len(), 1);
    }

    #[tokio::test]
    async fn test_same_symbol_overwrite_keeps_latest() {
        // PASS：同 symbol 多次 update → buffer 覆蓋為 latest（per spec §2.3
        // buffer.insert(...) 語意；同 sym 多次 ticker tick 取最新 funding rate）
        let mut agg = make_aggregator().await;
        agg.on_funding_update("BTCUSDT", 0.0001, 1_700_000_000_000);
        agg.on_funding_update("BTCUSDT", 0.0002, 1_700_000_001_000);
        assert_eq!(agg.buffer_len(), 1);
        let entry = agg.buffer.get("BTCUSDT").unwrap();
        assert!((entry.0 - 2.0).abs() < 1e-9, "latest 0.0002 → 2.0 bps");
        assert_eq!(entry.1, 1_700_000_001_000);
    }

    #[tokio::test]
    async fn test_flush_empty_buffer_returns_zero() {
        // PASS：empty buffer flush → (0, 0) no-op，不觸 PG（hot path 友好）
        let mut agg = make_aggregator().await;
        let (ok, fail) = agg.flush(1_700_000_060_000).await;
        assert_eq!(ok, 0);
        assert_eq!(fail, 0);
    }

    #[tokio::test]
    async fn test_flush_pool_unavailable_buffer_drained() {
        // PASS：pool 不可用 → 全 row 計入 fail_count；buffer 仍被 drain
        // （per IMPL doc：buffer drain 是 snapshot 隔離設計，不 retry，
        // 留下個 ticker tick + flush 恢復）
        let mut agg = make_aggregator().await;
        agg.on_funding_update("BTCUSDT", 0.0001, 1_700_000_000_000);
        agg.on_funding_update("ETHUSDT", 0.0002, 1_700_000_000_000);
        assert_eq!(agg.buffer_len(), 2);

        let (ok, fail) = agg.flush(1_700_000_060_000).await;
        assert_eq!(ok, 0, "pool unavailable → 0 ok");
        assert_eq!(fail, 2, "all rows fail (PoolUnavailable counted as fail)");
        assert_eq!(agg.buffer_len(), 0, "buffer drained on flush");
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
        let agg = FundingCurveAggregator::new(pool, dup_cohort);
        assert_eq!(agg.cohort_size(), 3, "duplicate cohort entries deduped");
        assert_eq!(agg.buffer_len(), 0);
    }

    #[tokio::test]
    async fn test_snapshot_panel_empty_buffer_returns_none() {
        // PASS：empty buffer → snapshot_panel 回 None（caller 不更新 slot）
        let agg = make_aggregator().await;
        assert!(agg.snapshot_panel(1_700_000_060_000).is_none());
    }

    #[tokio::test]
    async fn test_snapshot_panel_buffer_has_data_returns_some() {
        // PASS：buffer 有資料 → 回 Some(FundingCurveSnapshot)；symbols/rates/next 同 index 對齊
        let mut agg = make_aggregator().await;
        agg.on_funding_update("BTCUSDT", 0.0001, 1_700_000_028_800_000);
        agg.on_funding_update("ETHUSDT", 0.0002, 1_700_000_028_800_000);

        let snap = agg
            .snapshot_panel(1_700_000_060_000)
            .expect("snapshot must be Some when buffer has data");
        assert_eq!(snap.symbols.len(), 2);
        assert_eq!(snap.funding_rates_bps.len(), 2);
        assert_eq!(snap.next_funding_ms.len(), 2);
        assert_eq!(snap.snapshot_ts_ms, 1_700_000_060_000);
        assert_eq!(snap.source_tier, "bybit_v5_ws_tickers");

        // 驗 symbols 排序穩定（HashMap iter 不穩 → snapshot_panel 內 sort）
        // 同 index 對齊驗：symbols[i] / funding_rates_bps[i] / next_funding_ms[i]
        for (i, sym) in snap.symbols.iter().enumerate() {
            assert!(sym == "BTCUSDT" || sym == "ETHUSDT");
            // BTCUSDT 0.0001 → 1.0 bps；ETHUSDT 0.0002 → 2.0 bps
            let expected_rate = if sym == "BTCUSDT" { 1.0 } else { 2.0 };
            assert!(
                (snap.funding_rates_bps[i] - expected_rate).abs() < 1e-9,
                "rate alignment for sym {}",
                sym
            );
            assert_eq!(snap.next_funding_ms[i], 1_700_000_028_800_000);
        }
    }

    #[test]
    fn test_insert_sql_locks_v085_columns() {
        // PASS：grep guard — INSERT SQL 必含 V085 schema 5 column + ON CONFLICT
        // 防 sub-task 2/3 IMPL drift 漏改 SQL
        let src = include_str!("funding_curve.rs");
        for token in [
            "INTO panel.funding_rates_panel",
            "snapshot_ts_ms",
            "symbol",
            "funding_rate_bps",
            "next_funding_ms",
            "source_tier",
            "ON CONFLICT (snapshot_ts_ms, symbol)",
            "DO UPDATE",
            "bybit_v5_ws_tickers",
        ] {
            assert!(src.contains(token), "INSERT SQL missing: {token}");
        }
    }
}
