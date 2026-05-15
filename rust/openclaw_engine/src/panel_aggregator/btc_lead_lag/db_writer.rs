use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;

use sqlx::Postgres;
use tokio::sync::RwLock;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

use super::ingest::BtcOrderbookSlot;
use super::producer::BtcLeadLagProducer;
use super::snapshot::{snapshot_to_trait_panel, BtcLeadLagPanelSnapshot};
use super::LEAD_WINDOW_SECS_MAIN;
use crate::database::batch_insert::{exec_single_insert, SingleInsertOutcome};
use crate::database::pool::DbPool;
use crate::ipc_server::BtcLeadLagPanelSlot;

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
    ///
    /// W2-IMPL-1 (2026-05-11) — 新增 `book_slot: BtcOrderbookSlot` 參數：每 60s
    /// tick 前讀取 slot snapshot 作為 `btc_book_imbalance` 寫入（`None` → NaN）。
    /// slot 由 sibling `spawn_btc_orderbook_ingest_task` 從 WS Orderbook event push
    /// 更新（rate ~100 Hz）；本 run_loop 端僅 read（1/60s），無 lock contention。
    pub async fn run_loop(
        mut self,
        db_pool: Arc<DbPool>,
        slot: BtcLeadLagPanelSlot,
        book_slot: BtcOrderbookSlot,
        cancel: CancellationToken,
    ) {
        info!(
            target: "panel_aggregator",
            cohort_size = self.cohort_symbols.len(),
            tick_secs = RUN_LOOP_TICK_SECS,
            "BtcLeadLagProducer run_loop start (W2 sub-task 4 + W2-IMPL-1 orderbook wired)"
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

                    // 3. W2-IMPL-1：先讀 orderbook imbalance slot snapshot
                    //    （read lock < 1µs；ingest task 持 write lock 也 < 1µs）。
                    //    `None` 表 ingest task 尚未收到 fresh event → producer
                    //    寫 NaN 進 snapshot.btc_book_imbalance（NOT 0.0 假值）。
                    let btc_book_imbalance = *book_slot.read().await;

                    // 4. on_tick：calc snapshot（lookahead-free）
                    let snapshot = self.on_tick(
                        snapshot_ts_ms,
                        btc_close,
                        btc_volume,
                        &alt_closes,
                        btc_book_imbalance,
                    );
                    emit_count = emit_count.saturating_add(1);

                    // 5. PG INSERT V088（fail-soft：失敗只計數，slot 仍寫）
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

                    // 6. snapshot → BtcLeadLagPanel adaptor → 寫 slot
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

/// W2 sub-task 4 (E1-δ, 2026-05-11) — 從 `market.klines` 1m table 拉最近 close + volume。
///
/// 取最近 2min 內最新一筆 1m kline（避免 stale data 用過久舊 bar）；
/// 找不到 → None（caller fail-soft skip tick）。
///
/// SQL 對齊 outcome_backfiller.rs `WHERE k.timeframe = '1m'` 命名語義。
async fn fetch_latest_kline_close_volume(pool: &Arc<DbPool>, symbol: &str) -> Option<(f64, f64)> {
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
/// - source_tier TEXT ('cross_asset_btc_lead_lag' or diagnostic variant)
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
    let alt_expected_dir_i16: Vec<i16> = snapshot
        .alt_expected_dir
        .iter()
        .map(|v| *v as i16)
        .collect();

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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::panel_aggregator::btc_lead_lag::{
        create_btc_orderbook_slot, BtcLeadLagProducer, SOURCE_TIER,
    };

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
    ///
    /// W2-IMPL-1 (2026-05-11) — 簽名加 `book_slot` 參數；測試端建一個空 slot。
    #[tokio::test]
    async fn run_loop_responds_to_cancel() {
        let pool = make_disconnected_pool().await;
        let cancel = CancellationToken::new();
        let producer = BtcLeadLagProducer::new(make_cohort());
        let slot = create_btc_lead_lag_panel_slot();
        let book_slot = create_btc_orderbook_slot();

        let cancel_clone = cancel.clone();
        let handle = tokio::spawn(async move {
            producer.run_loop(pool, slot, book_slot, cancel_clone).await;
        });

        // 給 select! 進入等待狀態
        tokio::time::sleep(std::time::Duration::from_millis(20)).await;
        cancel.cancel();

        let result = tokio::time::timeout(std::time::Duration::from_millis(500), handle).await;
        assert!(result.is_ok(), "run_loop must exit on cancel within 500ms");
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
