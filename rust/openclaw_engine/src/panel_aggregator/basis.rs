//! P2-BASIS-PANEL-INFRA — perp-index basis aggregator（mirror funding_curve.rs）。
//!
//! MODULE_NOTE：
//!   模塊用途：訂閱既有 WS tickers.{sym} broadcast 取 perp last_price + index_price，
//!     每 60s flush 一批 basis snapshot 寫 V115 panel.basis_panel，作為 A1
//!     funding_short_v2 candidate Stage 0R offline replay 的 point-in-time basis
//!     歷史序列來源。
//!   主要類/函數：
//!     - `BasisAggregator`：cohort 過濾 + latest-value cache + flush writer。
//!     - `on_ticker_update(symbol, last_price, index_price)`：caller-driven，
//!       PanelAggregator::run event drain 內呼叫（mirror funding_curve）。
//!     - `flush(snapshot_ts_ms)`：對 cohort 算 signed basis_pct 寫 PG。
//!     - `insert_basis_snapshot(...)`：單筆 ON CONFLICT DO UPDATE INSERT。
//!   依賴：DbPool / exec_single_insert / sqlx Postgres。
//!   freshness：basis_panel staleness 走既有 Python `[66] check_panel_freshness`
//!     table-driven 框架（與 sister panel funding_rates_panel / oi_delta_panel 同
//!     路徑），不在 Rust 自含 freshness fn（spec round 2 E2 裁決）。
//!   硬邊界：
//!     - basis_pct = (perp_last_price / index_price - 1) * 100 **SIGNED**；分子必
//!       為 last_price（**非 mark_price**），逐位對齊 strategy live path
//!       `funding_short_v2/mod.rs:155` 的 ctx.price=last_price，否則 Stage 0R replay
//!       與 live 不可比。
//!     - fail-closed：index_price ≤ 0 或缺失 → **不寫 row**（不寫 0、不寫 NULL），
//!       否則 0 basis 會被誤判為「完美無溢價」反而開倉（spec §2.2）。
//!     - latest-value cache 跨 sparse index frame：WS index_price 只在 snapshot
//!       frame 帶（~1/8 frame），delta frame 缺 → 保留上一已知 index（對齊
//!       funding_curve sparse cache 範式）；從未收過有效 index 的 sym 不入 cache。
//!     - 無 IPC slot（per spec §6.4 #5）：A1 strategy live path 已用 in-memory
//!       index_prices cache 即時算 basis；basis_panel 純為 offline replay 服務。
//!
//! Spec：docs/execution_plan/specs/2026-05-29--basis-panel-infra-spec.md §4
//! V115 SQL：sql/migrations/V115__panel_basis_panel.sql
//! strategy parity：rust/openclaw_engine/src/strategies/funding_short_v2/mod.rs:155

use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use sqlx::Postgres;
use tracing::{debug, warn};

use crate::database::batch_insert::{exec_single_insert, SingleInsertOutcome};
use crate::database::pool::DbPool;

/// `BasisAggregator` — cohort perp-index basis aggregator。
///
/// 不變式（per spec §4.1）：
/// - cohort 與 funding_curve/oi_delta 共用同一 25-sym SSOT（spec §4.4 避
///   self-imposed scarcity）；non-cohort symbol update → silent ignored。
/// - `latest` 持每 sym 的 (last_price, index_price) latest-known；index_price 只在
///   有效（>0）frame 更新，sparse delta frame 缺 index → 保留上一已知 index。
/// - 從未收過有效 index 的 sym **不入 cache**（fail-closed，避寫假 basis）。
/// - flush 用 ON CONFLICT (snapshot_ts_ms, symbol) DO UPDATE 滿足 idempotency。
pub struct BasisAggregator {
    /// Cohort（與 funding_curve/oi_delta 同 SSOT）；O(1) lookup 用 HashSet。
    cohort: HashSet<String>,
    /// latest-value cache：symbol → (last_price, index_price latest-known)。
    /// 只有「收過 ≥1 有效 index（>0）snapshot」的 sym 才入 map（fail-closed）；
    /// last_price 每 frame 更新，index_price 只在 Some(ip>0) 時更新（sparse 保留）。
    latest: HashMap<String, (f64, f64)>,
    /// PG pool（fail-soft：pool 不可用時 flush 寫入靜默 skip + cache 保留）。
    db_pool: Arc<DbPool>,
}

impl BasisAggregator {
    /// 建構 aggregator。
    ///
    /// `cohort_symbols` 與 funding_curve/oi_delta 共用同一 cohort（spec §4.4 SSOT，
    /// 不另建 list）；重複項自動 dedupe（HashSet）。
    pub fn new(db_pool: Arc<DbPool>, cohort_symbols: Vec<String>) -> Self {
        Self {
            cohort: cohort_symbols.into_iter().collect(),
            latest: HashMap::new(),
            db_pool,
        }
    }

    /// 處理單筆 ticker update（caller-driven，PanelAggregator::run event drain 內呼叫）。
    ///
    /// `last_price` = Bybit V5 tickers stream `lastPrice`（PriceEvent.last_price，
    /// 即 strategy ctx.price，basis 分子）；每 frame 更新。
    /// `index_price` = Bybit V5 tickers stream `indexPrice`（PriceEvent.index_price，
    /// basis 分母）；只在 snapshot frame 帶 Some，delta frame 為 None。
    ///
    /// latest-value cache 範式（spec §4.1，對齊 funding_curve sparse cache）：
    /// - index_price Some(ip>0) → 更新 (last, ip)（last + index 同步刷新）。
    /// - index_price None / ≤0 但已有 cache → 只刷新 last，保留上一已知 index。
    /// - index_price None / ≤0 且從未有有效 index → **不入 cache**（fail-closed，
    ///   避免在 flush 用假 / 缺失 index 算出污染性 basis）。
    /// - non-cohort symbol → silent return（WS Ticker volume 大，不 log）。
    pub fn on_ticker_update(&mut self, symbol: &str, last_price: f64, index_price: Option<f64>) {
        if !self.cohort.contains(symbol) {
            return;
        }
        match (index_price, self.latest.get(symbol)) {
            // 有效 index frame：last + index 同步更新。
            (Some(ip), _) if ip > 0.0 => {
                self.latest.insert(symbol.to_string(), (last_price, ip));
                debug!(
                    target: "panel_aggregator",
                    symbol = symbol,
                    last_price = last_price,
                    index_price = ip,
                    "basis ticker update buffered (index refreshed)"
                );
            }
            // index 缺失 / ≤0，但已有 cache：只刷新 last，保留 last-known index。
            (_, Some(&(_, prev_ip))) => {
                self.latest.insert(symbol.to_string(), (last_price, prev_ip));
            }
            // 從未收過有效 index → 不入 cache（fail-closed）。
            _ => {}
        }
    }

    /// 取當前 cache 大小（test + observability 用）。
    pub fn cache_len(&self) -> usize {
        self.latest.len()
    }

    /// 取 cohort 大小（test + observability 用）。
    pub fn cohort_size(&self) -> usize {
        self.cohort.len()
    }

    /// Flush cache 為 cohort 全 sym 寫 V115 panel.basis_panel。
    ///
    /// `snapshot_ts_ms` = flush 時戳（ms epoch，60s boundary）；同 snapshot 內所有
    /// cohort row 共享同 snapshot_ts_ms（hypertable time column 對齊）。
    ///
    /// 行為（mirror funding_curve flush + fail-closed 加嚴）：
    /// - cache 空 → no-op return (0, 0)（hot path 友好）；
    /// - **cache 不 drain**：basis 是 latest-value cache 範式（對齊 funding partial
    ///   state cache），index 只在 sparse snapshot frame 到，cache 須跨 flush 保留
    ///   last-known index，否則下個 flush 因無新 index 全 sym 漏寫。每 60s 為「收過
    ///   ≥1 有效 index」的 cohort sym 寫一 row。
    /// - 每 sym：basis_pct = (last / index - 1) * 100 **SIGNED**（cache 已保證 index>0
    ///   才入庫，無除零）；INSERT 一 row；
    /// - pool 不可用 → 全 row PoolUnavailable 計入 fail，cache 保留待下次。
    ///
    /// 回傳：(成功插入 row 數, 失敗 row 數)。
    pub async fn flush(&mut self, snapshot_ts_ms: i64) -> (usize, usize) {
        if self.latest.is_empty() {
            return (0, 0);
        }

        // 取 cache snapshot（不 drain）；排序穩定化跨 process 一致 + 利於診斷。
        let mut entries: Vec<(String, f64, f64)> = self
            .latest
            .iter()
            .map(|(sym, &(last, index))| (sym.clone(), last, index))
            .collect();
        entries.sort_by(|a, b| a.0.cmp(&b.0));

        let mut ok_count = 0usize;
        let mut fail_count = 0usize;

        for (symbol, last_price, index_price) in entries {
            // 防禦性 fail-closed：cache 不變式已保證 index>0，但雙重防線避免任何
            // 上游 bug 寫入 ≤0 index 污染 replay（spec §2.2：index≤0 不寫 row）。
            if index_price <= 0.0 {
                warn!(
                    target: "panel_aggregator",
                    symbol = %symbol,
                    index_price = index_price,
                    "basis flush skip: index_price <= 0 (fail-closed, no row)"
                );
                continue;
            }
            // signed basis（panel 存方向資訊；consumer 取 abs 比 gate，spec §2.1）。
            // 公式逐位對齊 funding_short_v2/mod.rs:155 strategy live（strategy 端
            // 取 abs，panel 存 signed；分子 = last_price 非 mark_price）。
            let basis_pct = (last_price / index_price - 1.0) * 100.0;
            let outcome = insert_basis_snapshot(
                &self.db_pool,
                snapshot_ts_ms,
                &symbol,
                last_price,
                index_price,
                basis_pct,
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
                        "basis snapshot INSERT failed"
                    );
                }
                SingleInsertOutcome::PoolUnavailable => {
                    // pool 不可用全 row 都會回 PoolUnavailable；cache 保留，
                    // 下次 flush 自然恢復（fail-soft，對齊 funding_curve）。
                    fail_count += 1;
                }
            }
        }

        debug!(
            target: "panel_aggregator",
            snapshot_ts_ms = snapshot_ts_ms,
            ok_count = ok_count,
            fail_count = fail_count,
            cache_size = self.latest.len(),
            "basis panel flush complete"
        );

        (ok_count, fail_count)
    }
}

/// INSERT 單筆 basis snapshot 進 V115 panel.basis_panel。
///
/// SQL 對齊 spec §3.1 schema + V115 PG migration：
/// - snapshot_ts_ms BIGINT（hypertable time column）
/// - symbol TEXT
/// - perp_last_price DOUBLE PRECISION（分子，last_price 非 mark_price）
/// - index_price DOUBLE PRECISION（分母，caller 已保證 >0）
/// - basis_pct DOUBLE PRECISION（(last/index-1)*100 SIGNED）
/// - source_tier TEXT 固定 'bybit_v5_ws_tickers'（basis 全 WS 衍生）
///
/// ON CONFLICT (snapshot_ts_ms, symbol) DO UPDATE：
/// - PK = (snapshot_ts_ms, symbol)；同一 snapshot 重 flush 同 sym 不會 dup（idempotent）。
/// - DO UPDATE 取後 flush 的值（代表更新的 cache state），語意正確優於 DO NOTHING。
pub(crate) async fn insert_basis_snapshot(
    pool: &Arc<DbPool>,
    snapshot_ts_ms: i64,
    symbol: &str,
    perp_last_price: f64,
    index_price: f64,
    basis_pct: f64,
) -> SingleInsertOutcome {
    let query = sqlx::query::<Postgres>(
        "INSERT INTO panel.basis_panel \
         (snapshot_ts_ms, symbol, perp_last_price, index_price, basis_pct, source_tier) \
         VALUES ($1, $2, $3, $4, $5, $6) \
         ON CONFLICT (snapshot_ts_ms, symbol) DO UPDATE SET \
            perp_last_price = EXCLUDED.perp_last_price, \
            index_price = EXCLUDED.index_price, \
            basis_pct = EXCLUDED.basis_pct, \
            source_tier = EXCLUDED.source_tier",
    )
    .bind(snapshot_ts_ms)
    .bind(symbol)
    .bind(perp_last_price)
    .bind(index_price)
    .bind(basis_pct)
    .bind("bybit_v5_ws_tickers");
    exec_single_insert(pool, "panel.basis_panel", query).await
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
    async fn make_aggregator() -> BasisAggregator {
        let pool = make_disconnected_pool().await;
        let cohort = vec![
            "BTCUSDT".to_string(),
            "ETHUSDT".to_string(),
            "SOLUSDT".to_string(),
        ];
        BasisAggregator::new(pool, cohort)
    }

    #[tokio::test]
    async fn test_basis_formula_parity_signed() {
        // PASS：basis 公式逐位對齊 strategy live (funding_short_v2/mod.rs:155)。
        // strategy 端取 abs；panel 存 signed。已知 (last, index) → expected signed pct。
        // 65100 / 65000 - 1 = 0.001538... → ×100 = 0.15384... %（perp 升水，正）
        let last = 65_100.0_f64;
        let index = 65_000.0_f64;
        let basis = (last / index - 1.0) * 100.0;
        let expected = (65_100.0 / 65_000.0 - 1.0) * 100.0;
        assert!((basis - expected).abs() < 1e-12);
        assert!(basis > 0.0, "perp 升水 → signed basis 為正");

        // perp 貼水（last < index）→ signed basis 為負（panel 保方向資訊）。
        let last_disc = 64_900.0_f64;
        let basis_disc = (last_disc / index - 1.0) * 100.0;
        assert!(basis_disc < 0.0, "perp 貼水 → signed basis 為負");

        // 對齊 strategy abs 行為：consumer 取 abs 後比 gate。
        // strategy compute_basis_pct(65100, Some(65000)) = ((65100/65000)-1).abs()*100
        let strategy_abs = ((last / index) - 1.0).abs() * 100.0;
        assert!((basis.abs() - strategy_abs).abs() < 1e-12, "panel signed.abs() == strategy abs");
    }

    #[tokio::test]
    async fn test_cohort_ticker_update_buffers_with_valid_index() {
        // PASS：cohort sym + 有效 index → cache 更新 (last, index)
        let mut agg = make_aggregator().await;
        agg.on_ticker_update("BTCUSDT", 65_000.0, Some(64_990.0));
        assert_eq!(agg.cache_len(), 1);
    }

    #[tokio::test]
    async fn test_non_cohort_symbol_ignored() {
        // PASS：non-cohort symbol → cache 不變、無 panic
        let mut agg = make_aggregator().await;
        agg.on_ticker_update("DOGEUSDT", 0.1, Some(0.1));
        assert_eq!(agg.cache_len(), 0, "non-cohort sym must not enter cache");
        agg.on_ticker_update("ETHUSDT", 3_500.0, Some(3_499.0));
        assert_eq!(agg.cache_len(), 1);
    }

    #[tokio::test]
    async fn test_fail_closed_never_seen_index_not_cached() {
        // PASS：fail-closed — 從未收過有效 index 的 sym → 不入 cache
        // （即使 last_price 有值；避免用缺失 index 算假 basis）
        let mut agg = make_aggregator().await;
        agg.on_ticker_update("BTCUSDT", 65_000.0, None);
        assert_eq!(agg.cache_len(), 0, "never-seen-index sym must not enter cache");
        // index ≤ 0 同樣不入 cache（fail-closed）
        agg.on_ticker_update("BTCUSDT", 65_000.0, Some(0.0));
        assert_eq!(agg.cache_len(), 0, "index<=0 must not enter cache");
        agg.on_ticker_update("BTCUSDT", 65_000.0, Some(-1.0));
        assert_eq!(agg.cache_len(), 0, "negative index must not enter cache");
    }

    #[tokio::test]
    async fn test_latest_value_cache_sparse_index_frame() {
        // PASS：latest-value cache 跨 sparse index frame（spec §4.1 核心不變式）。
        // frame 1：snapshot frame 帶有效 index → 入 cache (65000, 64990)
        // frame 2：delta frame 缺 index（None）→ 只刷新 last，保留上一已知 index
        let mut agg = make_aggregator().await;
        agg.on_ticker_update("BTCUSDT", 65_000.0, Some(64_990.0));
        assert_eq!(agg.cache_len(), 1);
        let (last1, idx1) = *agg.latest.get("BTCUSDT").unwrap();
        assert!((last1 - 65_000.0).abs() < 1e-9);
        assert!((idx1 - 64_990.0).abs() < 1e-9);

        // delta frame：last 變 65050，index None → index 保留 64990
        agg.on_ticker_update("BTCUSDT", 65_050.0, None);
        let (last2, idx2) = *agg.latest.get("BTCUSDT").unwrap();
        assert!((last2 - 65_050.0).abs() < 1e-9, "last refreshed on delta frame");
        assert!((idx2 - 64_990.0).abs() < 1e-9, "index preserved (last-known) across sparse frame");

        // 下個有效 index snapshot frame → index 刷新
        agg.on_ticker_update("BTCUSDT", 65_060.0, Some(65_055.0));
        let (last3, idx3) = *agg.latest.get("BTCUSDT").unwrap();
        assert!((last3 - 65_060.0).abs() < 1e-9);
        assert!((idx3 - 65_055.0).abs() < 1e-9, "index refreshed on next valid snapshot frame");
    }

    #[tokio::test]
    async fn test_flush_empty_cache_returns_zero() {
        // PASS：empty cache flush → (0, 0) no-op，不觸 PG（hot path 友好）
        let mut agg = make_aggregator().await;
        let (ok, fail) = agg.flush(1_700_000_060_000).await;
        assert_eq!(ok, 0);
        assert_eq!(fail, 0);
    }

    #[tokio::test]
    async fn test_flush_pool_unavailable_cache_retained() {
        // PASS：pool 不可用 → 全 row 計入 fail_count；**cache 保留**（不 drain）。
        // 這是 basis latest-value cache 範式的關鍵：cache 須跨 flush 保留 last-known
        // index（對齊 funding partial state cache），否則下個 flush 全漏寫。
        let mut agg = make_aggregator().await;
        agg.on_ticker_update("BTCUSDT", 65_000.0, Some(64_990.0));
        agg.on_ticker_update("ETHUSDT", 3_500.0, Some(3_499.0));
        assert_eq!(agg.cache_len(), 2);

        let (ok, fail) = agg.flush(1_700_000_060_000).await;
        assert_eq!(ok, 0, "pool unavailable → 0 ok");
        assert_eq!(fail, 2, "all rows fail (PoolUnavailable counted as fail)");
        assert_eq!(agg.cache_len(), 2, "cache retained across flush (latest-value 範式)");

        // 下個 flush 即使無新 ticker update 仍能寫（cache 持 last-known）。
        let (ok2, fail2) = agg.flush(1_700_000_120_000).await;
        assert_eq!(ok2, 0);
        assert_eq!(fail2, 2, "cache still flushable next cycle without new update");
    }

    #[tokio::test]
    async fn test_cohort_size_initialization_dedupe() {
        // PASS：cohort 初始化大小驗證（dedupe HashSet，共用 SSOT cohort）
        let pool = make_disconnected_pool().await;
        let dup_cohort = vec![
            "BTCUSDT".to_string(),
            "ETHUSDT".to_string(),
            "BTCUSDT".to_string(),
            "SOLUSDT".to_string(),
        ];
        let agg = BasisAggregator::new(pool, dup_cohort);
        assert_eq!(agg.cohort_size(), 3, "duplicate cohort entries deduped");
        assert_eq!(agg.cache_len(), 0);
    }

    #[test]
    fn test_insert_sql_locks_v115_columns() {
        // PASS：grep guard — INSERT SQL 必含 V115 schema 6 column + ON CONFLICT。
        // 防後續 IMPL drift 漏改 SQL（mirror funding_curve test_insert_sql_locks）。
        let src = include_str!("basis.rs");
        for token in [
            "INTO panel.basis_panel",
            "snapshot_ts_ms",
            "symbol",
            "perp_last_price",
            "index_price",
            "basis_pct",
            "source_tier",
            "ON CONFLICT (snapshot_ts_ms, symbol)",
            "DO UPDATE",
            "bybit_v5_ws_tickers",
        ] {
            assert!(src.contains(token), "INSERT SQL missing: {token}");
        }
    }

    #[test]
    fn test_basis_formula_uses_last_price_not_mark() {
        // PASS：source guard — 公式分子必為 perp last_price（非 mark price），
        // 對齊 strategy live ctx.price=last_price 保 replay parity（spec §6.5 #1）。
        let src = include_str!("basis.rs");
        // flush 計算公式必出現 (last_price / index_price - 1.0) * 100.0（signed）
        assert!(
            src.contains("(last_price / index_price - 1.0) * 100.0"),
            "basis formula must be signed (last/index - 1)*100 using last_price"
        );
        // on_ticker_update 簽名必收 last_price + index_price（無 mark 入參）；
        // PriceEvent 本無 mark price field（parser 不解析），結構性保證分子用 last。
        assert!(
            src.contains("pub fn on_ticker_update(&mut self, symbol: &str, last_price: f64, index_price: Option<f64>)"),
            "on_ticker_update must take last_price + index_price (no mark input)"
        );
        // INSERT 必綁 perp_last_price column（V115 schema 無 mark column）。
        assert!(
            src.contains("perp_last_price"),
            "INSERT must bind perp_last_price column"
        );
    }
}
