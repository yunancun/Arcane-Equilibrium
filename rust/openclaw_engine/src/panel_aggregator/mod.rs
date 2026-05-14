//! Sprint N+1 W1 + W2 panel_aggregator — cross-asset panel producer namespace。
//!
//! MODULE_NOTE：
//!   panel_aggregator 是 Sprint N+1 W1 (Phase B Tier 2) + W2 (A4-C BTC→Alt
//!   lead-lag) 的 cross-asset / cross-strategy panel collector + producer
//!   命名空間。本模組統一 host:
//!   - W1 sub-task 1 (E1-α)：funding_curve aggregator + V085 writer
//!     + PanelAggregator skeleton (broadcast core)
//!   - W1 sub-task 2 (本 PR / E1-β)：oi_delta_panel aggregator + V087 writer
//!     + PanelAggregator wire (oi_delta_aggregator + oi_delta_mut accessor)
//!   - W1 sub-task 3 (E1-γ)：WS subscription + main.rs broadcast migration
//!     + step_4_5 surface dispatch wire + cold-start REST backfill
//!   - W2 sub-task 1 (E1-δ)：BTC→Alt lead-lag producer + V088 writer
//!     （並行 sub-agent 另派；本模組 declare `btc_lead_lag` namespace
//!     由 W2 sub-agent 自行 land）
//!
//! 設計約束：
//! - **Producer 端職責分流**：funding/oi 從 既有 WS event stream 訂閱（broadcast
//!   pattern, sub-task 3 wire-up）；btc_lead_lag 走 KlineManager pull pattern
//!   （W2 sub-agent IMPL）。共用 panel.* PG schema + Rust IPC slot 雙寫。
//! - **Writer separate concern**：producer 計算 snapshot；writer
//!   (`database/btc_lead_lag_writer.rs` 等) 負責 sqlx INSERT；分檔讓 producer
//!   可獨立 unit test 不依賴 PG。本 PR funding_curve 簡化為「aggregator + writer
//!   同檔」（V085 寫入邏輯極簡 5-column INSERT，分檔過度設計）。
//! - **Paper-only fence 由 caller 控制**：本 producer 不知 paper-only fence；
//!   step_4_5_dispatch.rs 構造 surface 階段 gate engine_mode；
//!   `BtcLeadLagPanelSlot` IPC slot late-inject 由 main.rs 控制 spawn 條件。
//!
//! 不變式：
//! - cohort 25 sym 必為 SymbolRegistry strict subset（per W1 spec §2.1 line 91）；
//!   funding_curve aggregator 透過 cohort filter 強制執行
//! - V085 / V087 / V088 三 panel 表各自獨立；任一 sub-task 寫入 fail 不影響
//!   其他 panel 的 producer / consumer 路徑
//!
//! Spec：
//! - W1 spec v1.1 (BB WS-first revision):
//!   `srv/docs/execution_plan/2026-05-10--w_audit_8a_phase_b_tier_2_collector_spec.md`
//! - W2 spec v1.2:
//!   `srv/docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md`
//! - V085 SQL: `srv/sql/migrations/V085__panel_funding_curve.sql`
//! - V087 SQL: `srv/sql/migrations/V087__panel_oi_delta_panel.sql`

pub mod btc_lead_lag;
pub mod funding_curve;
pub mod oi_delta;

pub use btc_lead_lag::{should_spawn_btc_lead_lag_producer, BtcLeadLagProducer};
// W2-IMPL-1 (2026-05-11) — orderbook 接線完整 re-export：BtcOrderbookSlot typedef +
// create_btc_orderbook_slot 工廠 + spawn_btc_orderbook_ingest_task async task。
// （sibling W2-IMPL-2 sub-agent 早先預先 re-export create_btc_orderbook_slot 工廠
// 滿足 producer.run_loop 簽名 stub；本 IMPL-1 補完 ingest task 與 slot 公共型別。）
pub use btc_lead_lag::{
    create_btc_orderbook_slot, spawn_btc_orderbook_ingest_task, BtcOrderbookSlot,
};
pub use funding_curve::FundingCurveAggregator;
pub use oi_delta::OIDeltaAggregator;

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;

use openclaw_core::now_ms;
use openclaw_types::{PriceEvent, PriceEventKind};
use tokio::sync::{mpsc, RwLock};
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

use crate::database::pool::DbPool;
use crate::ipc_server::{BtcLeadLagPanelSlot, FundingCurvePanelSlot, OIDeltaPanelSlot};
use crate::market_data_client::MarketDataClient;

/// W1 sub-task 3 (E1-γ, 2026-05-11) — flush 視窗 60 秒，per spec §2.3 + §3.3。
const FLUSH_INTERVAL_SECS: u64 = 60;
/// W1 sub-task 3 (E1-γ, 2026-05-11) — broadcast::Sender 容量、若 lag >= 此值
/// log warn 並繼續（panel data 是 cross-section snapshot，lag 偶發容忍）。
const PANEL_LAG_WARN_THRESHOLD: u64 = 64;

/// `PanelAggregator` — Tier 2 panel collector 主協調者（broadcast core skeleton）。
///
/// 設計目標：
/// - 一個 PanelAggregator instance 持有所有 Tier 2 sub-aggregator（funding_curve
///   + oi_delta + 未來 BTC lead-lag W2 producer 整合點）
/// - run_loop() 訂閱單一 WS broadcast::Receiver<PriceEvent>，dispatch event 給
///   所有 sub-aggregator（funding_rate field → funding_curve；open_interest
///   field → oi_delta；下游 sub-task wire-up）
/// - 共享 cancel: CancellationToken 對齊 RE-2 supervisor graceful shutdown
///
/// 本 sub-task 1 階段：
/// - skeleton only — 持有 funding_curve aggregator + db_pool + cancel
/// - run_placeholder() 是 placeholder，下游 sub-task 加 WS subscription +
///   60s flush timer
/// - public API 暴露 funding_curve_mut() 供 sub-task 2/3 wire-up + 整合 test
pub struct PanelAggregator {
    funding_curve_aggregator: FundingCurveAggregator,
    /// W1 sub-task 2 (E1-β) — OI delta panel aggregator wire。
    ///
    /// 與 funding_curve 共用 cohort + db_pool；run_loop 內 dispatch
    /// `PriceEventKind::Ticker.open_interest` field 給 `oi_delta_aggregator`
    /// （sub-task 3 wire-up）。flush 走同 60s timer，snapshot_ts_ms 對齊。
    oi_delta_aggregator: OIDeltaAggregator,
    /// PG pool（fail-soft：pool 不可用時 sub-aggregator 自行降級）。
    /// 預留供未來 sub-aggregator（btc_lead_lag）共用 pool 句柄。
    #[allow(dead_code)]
    db_pool: Arc<DbPool>,
    /// Cancel token — 與 RE-2 supervisor 共享，graceful shutdown 觸發 run_loop break。
    cancel: CancellationToken,
    /// W1 sub-task 3 (E1-γ, 2026-05-11) — IPC slot for funding curve panel
    /// late-injection（hot path 讀寫 RwLock）。
    /// `RwLock::write()` replace 整個 Option<FundingCurveSnapshot>。
    funding_curve_slot: FundingCurvePanelSlot,
    /// W1 sub-task 3 (E1-γ, 2026-05-11) — IPC slot for OI delta panel late-injection。
    oi_delta_slot: OIDeltaPanelSlot,
    /// W1 P0 fix (2026-05-11 ~01:00 UTC) — per-symbol partial funding state cache。
    ///
    /// 解 root cause：Bybit V5 ticker WS delta 只夾帶 changed field；funding_rate
    /// 只在 8h 結算時刻變動，故大部分 ticker delta 兩個 field 皆 None。原 event
    /// handler 用 `(Some, Some)` guard 拒絕所有 delta，僅 initial snapshot 通過 →
    /// 25 syms 中 ≤10 受惠（且只 1 row 入 buffer，flush drain 後永遠不再寫）。
    ///
    /// 設計：每 sym 維護 latest known (rate, next_ms)；event handler 只更新 cache，
    /// flush_timer arm 從 cache 為 cohort 全 sym repopulate inner aggregator buffer。
    /// flush 後 buffer drain 不影響 cache（cache 仍持有 8h 內 latest 已知值）。
    /// 結果：每 60s flush 為 cohort 全 sym 寫一 row（前提收過 initial snapshot）。
    funding_partial_state: HashMap<String, (Option<f64>, Option<i64>)>,
}

impl PanelAggregator {
    /// 建構 panel aggregator skeleton。
    ///
    /// `db_pool`：共享 PG pool（fail-soft）
    /// `cohort_symbols`：cohort 25-sym hardcoded snapshot（per W1 spec §2.1）；
    ///   會 clone 兩份分別給 funding_curve + oi_delta aggregator（兩者邏輯獨立
    ///   持有自己的 HashSet cohort filter；clone 成本一次性 25-string）。
    /// `cancel`：與 RE-2 supervisor 共享 cancel token
    pub fn new(
        db_pool: Arc<DbPool>,
        cohort_symbols: Vec<String>,
        cancel: CancellationToken,
        funding_curve_slot: FundingCurvePanelSlot,
        oi_delta_slot: OIDeltaPanelSlot,
    ) -> Self {
        let funding_curve_aggregator =
            FundingCurveAggregator::new(db_pool.clone(), cohort_symbols.clone());
        let oi_delta_aggregator = OIDeltaAggregator::new(db_pool.clone(), cohort_symbols);
        Self {
            funding_curve_aggregator,
            oi_delta_aggregator,
            db_pool,
            cancel,
            funding_curve_slot,
            oi_delta_slot,
            funding_partial_state: HashMap::new(),
        }
    }

    /// 取 funding_curve aggregator 可變引用（供 sub-task 2/3 wire-up + 整合 test）。
    ///
    /// 設計理由：sub-task 3 把 WS broadcast::Receiver<PriceEvent> drain Ticker
    /// variant 後，需呼叫 `aggregator.on_funding_update(symbol, rate, next_ts)`；
    /// 透過 mut ref 可在 PanelAggregator 上層 select! 內 cleanly dispatch。
    pub fn funding_curve_mut(&mut self) -> &mut FundingCurveAggregator {
        &mut self.funding_curve_aggregator
    }

    /// 取 funding_curve aggregator 不可變引用（test + observability 用）。
    pub fn funding_curve(&self) -> &FundingCurveAggregator {
        &self.funding_curve_aggregator
    }

    /// 取 oi_delta aggregator 可變引用（供 sub-task 3 wire-up + 整合 test）。
    ///
    /// 設計理由：sub-task 3 把 WS broadcast::Receiver<PriceEvent> drain Ticker
    /// variant 後，需呼叫 `aggregator.on_oi_update(symbol, oi_abs, snapshot_ts_ms)`；
    /// `PriceEvent.open_interest: Option<f64>` is None 時 dispatch 端 skip，
    /// Some 時轉呼叫此 mut ref。
    pub fn oi_delta_mut(&mut self) -> &mut OIDeltaAggregator {
        &mut self.oi_delta_aggregator
    }

    /// 取 oi_delta aggregator 不可變引用（test + observability 用）。
    pub fn oi_delta(&self) -> &OIDeltaAggregator {
        &self.oi_delta_aggregator
    }

    /// W-AUDIT-8a Phase B B-2：startup-only OI REST backfill。
    ///
    /// WS tickers 只給 current openInterest；5m/15m/1h delta 的 baseline 需在
    /// 啟動時用 Bybit `/v5/market/open-interest` 補一次。失敗採 fail-soft：
    /// 對應 symbol 仍會由 WS 更新 `oi_abs`，但 window 不足時 delta 為 NaN，
    /// bb_breakout 按 `oi_panel_unavailable` fail-closed。
    pub async fn cold_start_oi_backfill(&mut self, market_client: &MarketDataClient) {
        const INTERVALS: [&str; 3] = ["5min", "15min", "1h"];
        let cohort: Vec<String> = self
            .oi_delta_aggregator
            .cohort_symbols_sorted()
            .into_iter()
            .collect();
        if cohort.is_empty() {
            return;
        }

        let batch = market_client
            .get_open_interest_batch("linear", &cohort, &INTERVALS, Some(2))
            .await;
        let mut grouped: HashMap<String, Vec<(i64, f64)>> = HashMap::new();
        let mut ok_requests = 0usize;
        let mut failed_requests = 0usize;

        for (symbol, interval, result) in batch {
            match result {
                Ok(records) => {
                    ok_requests += 1;
                    let rows = grouped.entry(symbol.clone()).or_default();
                    for record in records {
                        let ts = record.timestamp.parse::<i64>().unwrap_or(0);
                        rows.push((ts, record.open_interest));
                    }
                    debug!(
                        target: "panel_aggregator",
                        symbol = %symbol,
                        interval = %interval,
                        "OI cold-start interval backfilled"
                    );
                }
                Err(e) => {
                    failed_requests += 1;
                    warn!(
                        target: "panel_aggregator",
                        symbol = %symbol,
                        interval = %interval,
                        error = ?e,
                        "OI cold-start interval backfill failed"
                    );
                }
            }
        }

        let mut seeded_points = 0usize;
        for (symbol, points) in grouped {
            seeded_points += self
                .oi_delta_aggregator
                .seed_history_points(&symbol, points);
        }

        info!(
            target: "panel_aggregator",
            ok_requests = ok_requests,
            failed_requests = failed_requests,
            seeded_points = seeded_points,
            "OI cold-start backfill complete"
        );
    }

    /// W1 P0 fix (2026-05-11) — funding partial state cache 大小（observability 用）。
    pub fn funding_partial_state_size(&self) -> usize {
        self.funding_partial_state.len()
    }

    /// W1 P0 fix (2026-05-11) — funding partial state 取單 sym（test only）。
    #[cfg(test)]
    pub(crate) fn funding_partial_state_get(
        &self,
        sym: &str,
    ) -> Option<(Option<f64>, Option<i64>)> {
        self.funding_partial_state.get(sym).copied()
    }

    /// W1 P0 fix (2026-05-11) — partial event ingest（test + future hot path）。
    ///
    /// 模擬 event handler `evt = event_rx.recv()` arm 內 partial state update 邏輯。
    /// 任一 field Some 即 update cache 同位置；兩 field 皆 None silent return。
    pub fn ingest_funding_partial(
        &mut self,
        sym: &str,
        rate: Option<f64>,
        next_funding_ms: Option<i64>,
    ) {
        if rate.is_none() && next_funding_ms.is_none() {
            return;
        }
        let entry = self
            .funding_partial_state
            .entry(sym.to_string())
            .or_insert((None, None));
        if rate.is_some() {
            entry.0 = rate;
        }
        if next_funding_ms.is_some() {
            entry.1 = next_funding_ms;
        }
    }

    /// W1 P0 fix (2026-05-11) — flush_timer arm 內 cache→buffer repopulate 邏輯
    /// 抽 helper（test + future maintenance）。
    pub fn repopulate_funding_buffer_from_cache(&mut self) -> usize {
        let mut pushed = 0usize;
        // 為 borrow checker 收集 (sym, rate, next_ms) tuple 後再 dispatch
        let ready: Vec<(String, f64, i64)> = self
            .funding_partial_state
            .iter()
            .filter_map(|(sym, (r_opt, n_opt))| match (*r_opt, *n_opt) {
                (Some(r), Some(n)) => Some((sym.clone(), r, n)),
                _ => None,
            })
            .collect();
        for (sym, rate, next_ms) in ready {
            self.funding_curve_aggregator
                .on_funding_update(&sym, rate, next_ms);
            pushed += 1;
        }
        pushed
    }

    /// W1 sub-task 3 (E1-γ, 2026-05-11) — 真實 run loop。
    ///
    /// 設計（per W1 spec §2.3 + §3.3 + dispatch v3.7 §3.1 chunk 3）：
    /// 1. 訂閱單一 panel mpsc::Receiver<Arc<PriceEvent>>（main_fanout 額外 arm
    ///    fan out 給 panel；既有 paper/demo/live arm 不變）
    /// 2. 60s flush timer：snapshot funding_curve + oi_delta 寫 IPC slot →
    ///    flush 各自寫 PG（funding_curve drain buffer / oi_delta 保留 history）
    /// 3. event drain：Ticker variant → dispatch funding_rate + open_interest
    /// 4. cancel：graceful break
    ///
    /// 順序保證：snapshot **先於** flush 呼叫（funding_curve.flush 會 drain
    /// buffer，先 snapshot 才能取得本視窗內容；oi_delta.flush 不 drain，順序
    /// 不影響但對齊 funding_curve 行為一致）。
    pub async fn run(mut self, mut event_rx: mpsc::Receiver<Arc<PriceEvent>>) {
        info!(
            target: "panel_aggregator",
            funding_curve_cohort_size = self.funding_curve_aggregator.cohort_size(),
            oi_delta_cohort_size = self.oi_delta_aggregator.cohort_size(),
            "PanelAggregator run loop start (W1 sub-task 3 wired)"
        );

        let mut flush_timer = tokio::time::interval(Duration::from_secs(FLUSH_INTERVAL_SECS));
        // 跳過第一個 immediate tick（避免啟動時即 flush 空 buffer）
        flush_timer.tick().await;

        let mut total_events: u64 = 0;
        let mut funding_updates: u64 = 0;
        let mut oi_updates: u64 = 0;
        let mut flush_cycles: u64 = 0;

        loop {
            tokio::select! {
                _ = self.cancel.cancelled() => {
                    info!(
                        target: "panel_aggregator",
                        total_events = total_events,
                        funding_updates = funding_updates,
                        oi_updates = oi_updates,
                        flush_cycles = flush_cycles,
                        "PanelAggregator cancelled, shutting down"
                    );
                    return;
                }

                _ = flush_timer.tick() => {
                    let snapshot_ts_ms = now_ms() as i64;

                    // W1 P0 fix (2026-05-11)：每 flush 用 partial cache repopulate buffer。
                    // 因 Bybit V5 ticker delta 不夾帶 unchanged funding_rate（只 8h 結算才有），
                    // 原 event handler `(Some, Some)` guard 拒絕大部分 delta，改 cache 後
                    // cohort 全 sym（已 receive initial snapshot 者）每 flush 寫一 row。
                    let cache_pushed = self.repopulate_funding_buffer_from_cache();
                    if cache_pushed > 0 {
                        debug!(
                            target: "panel_aggregator",
                            snapshot_ts_ms = snapshot_ts_ms,
                            cache_pushed = cache_pushed,
                            cache_size = self.funding_partial_state.len(),
                            "funding partial cache repopulated buffer"
                        );
                    }

                    // ── funding_curve：snapshot 先（buffer 即將被 drain），slot 寫，flush ──
                    if let Some(snapshot) = self.funding_curve_aggregator.snapshot_panel(snapshot_ts_ms) {
                        let snapshot_size = snapshot.symbols.len();
                        *self.funding_curve_slot.write().await = Some(snapshot);
                        debug!(
                            target: "panel_aggregator",
                            snapshot_ts_ms = snapshot_ts_ms,
                            symbols = snapshot_size,
                            "funding_curve panel slot updated"
                        );
                    }
                    let (fc_ok, fc_fail) = self.funding_curve_aggregator.flush(snapshot_ts_ms).await;

                    // ── oi_delta：snapshot 與 flush 順序不關鍵（history 不 drain）──
                    if let Some(snapshot) = self.oi_delta_aggregator.snapshot_panel(snapshot_ts_ms) {
                        let snapshot_size = snapshot.symbols.len();
                        *self.oi_delta_slot.write().await = Some(snapshot);
                        debug!(
                            target: "panel_aggregator",
                            snapshot_ts_ms = snapshot_ts_ms,
                            symbols = snapshot_size,
                            "oi_delta panel slot updated"
                        );
                    }
                    let (oi_ok, oi_fail) = self.oi_delta_aggregator.flush(snapshot_ts_ms).await;

                    flush_cycles = flush_cycles.saturating_add(1);
                    info!(
                        target: "panel_aggregator",
                        snapshot_ts_ms = snapshot_ts_ms,
                        cycle = flush_cycles,
                        funding_ok = fc_ok,
                        funding_fail = fc_fail,
                        oi_ok = oi_ok,
                        oi_fail = oi_fail,
                        "panel flush cycle complete"
                    );
                }

                evt = event_rx.recv() => {
                    match evt {
                        Some(price_event) => {
                            total_events = total_events.saturating_add(1);
                            // 只處理 Ticker variant；其他 variant（Trade / Orderbook / Kline）
                            // 不含 funding/OI panel 所需 field，silent drop（per spec §2.3 + §3.3）
                            if price_event.event_kind == Some(PriceEventKind::Ticker) {
                                // W1 P0 fix (2026-05-11)：partial state cache，避開 Bybit V5
                                // ticker delta 只夾帶 changed field 的丟失（funding_rate
                                // 多 ticker 為 None，cache 持有 8h 內 latest 已知值）。
                                let touched = price_event.funding_rate.is_some()
                                    || price_event.next_funding_ms.is_some();
                                if touched {
                                    self.ingest_funding_partial(
                                        &price_event.symbol,
                                        price_event.funding_rate,
                                        price_event.next_funding_ms,
                                    );
                                    funding_updates = funding_updates.saturating_add(1);
                                }
                                // OI update：open_interest 有就更新
                                if let Some(oi) = price_event.open_interest {
                                    self.oi_delta_aggregator.on_oi_update(
                                        &price_event.symbol,
                                        oi,
                                        price_event.ts_ms as i64,
                                    );
                                    oi_updates = oi_updates.saturating_add(1);
                                }
                            }
                        }
                        None => {
                            // upstream channel closed → 上游 fan-out drop sender，
                            // 退出 loop（與其他 pipeline arm 一致語意）
                            warn!(
                                target: "panel_aggregator",
                                total_events = total_events,
                                "panel event channel closed, shutting down"
                            );
                            return;
                        }
                    }
                    // PANEL_LAG_WARN_THRESHOLD：監測 channel lag；若 cap 接近滿載 log warn
                    let len = event_rx.len() as u64;
                    if len >= PANEL_LAG_WARN_THRESHOLD {
                        warn!(
                            target: "panel_aggregator",
                            channel_len = len,
                            "panel event channel lagging"
                        );
                    }
                }
            }
        }
    }
}

/// W1 sub-task 3 (E1-γ, 2026-05-11) — IPC slot 工廠。
///
/// main.rs 在 IpcServer detach 前呼叫此函數產生 slot pair 給 IpcServer 持有，
/// 同時 clone Arc 給 PanelAggregator 寫入。typedef 已在 ipc_server::slots 定義。
pub fn create_panel_slots() -> (FundingCurvePanelSlot, OIDeltaPanelSlot) {
    (Arc::new(RwLock::new(None)), Arc::new(RwLock::new(None)))
}

/// W2 sub-task 4 (E1-δ, 2026-05-11) — BtcLeadLag IPC slot 工廠。
///
/// main.rs 在 IpcServer detach 前呼叫此函數產生 slot 給 IpcServer 持有，
/// 同時 clone Arc 給 BtcLeadLagProducer 寫入 + clone Arc 給 TickPipeline
/// step_4_5_dispatch 讀取。typedef 已在 `ipc_server::slots::BtcLeadLagPanelSlot`
/// 定義。對齊 `create_panel_slots` 命名 + 行為 pattern。
pub fn create_btc_lead_lag_slot() -> BtcLeadLagPanelSlot {
    Arc::new(RwLock::new(None))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::database::DatabaseConfig;

    async fn make_disconnected_pool() -> Arc<DbPool> {
        let cfg = DatabaseConfig {
            database_url: String::new(),
            ..Default::default()
        };
        Arc::new(DbPool::connect(&cfg).await)
    }

    fn make_slots() -> (FundingCurvePanelSlot, OIDeltaPanelSlot) {
        create_panel_slots()
    }

    #[tokio::test]
    async fn test_panel_aggregator_constructs_with_cohort() {
        // PASS：PanelAggregator 建構 + funding_curve + oi_delta aggregator
        // cohort 大小對齊（兩 aggregator 共享同 cohort 25-sym snapshot）
        let pool = make_disconnected_pool().await;
        let cancel = CancellationToken::new();
        let cohort = vec!["BTCUSDT".to_string(), "ETHUSDT".to_string()];
        let (fc_slot, oi_slot) = make_slots();
        let agg = PanelAggregator::new(pool, cohort, cancel, fc_slot, oi_slot);
        assert_eq!(agg.funding_curve().cohort_size(), 2);
        assert_eq!(agg.funding_curve().buffer_len(), 0);
        assert_eq!(agg.oi_delta().cohort_size(), 2);
        assert_eq!(agg.oi_delta().history_len(), 0);
    }

    #[tokio::test]
    async fn test_funding_curve_mut_accessor_dispatch() {
        // PASS：funding_curve_mut() 可 dispatch on_funding_update 進 buffer
        // 驗 sub-task 3 整合 dispatch path 不 broken
        let pool = make_disconnected_pool().await;
        let cancel = CancellationToken::new();
        let cohort = vec!["BTCUSDT".to_string()];
        let (fc_slot, oi_slot) = make_slots();
        let mut agg = PanelAggregator::new(pool, cohort, cancel, fc_slot, oi_slot);
        agg.funding_curve_mut()
            .on_funding_update("BTCUSDT", 0.0001, 1_700_000_000_000);
        assert_eq!(agg.funding_curve().buffer_len(), 1);
    }

    #[tokio::test]
    async fn test_funding_partial_state_initial_snapshot_both_some() {
        // PASS：W1 P0 fix — initial snapshot 兩 field 都 Some → cache 完整 +
        // repopulate 後 inner buffer 含該 sym
        let pool = make_disconnected_pool().await;
        let cancel = CancellationToken::new();
        let cohort = vec!["BTCUSDT".to_string()];
        let (fc_slot, oi_slot) = make_slots();
        let mut agg = PanelAggregator::new(pool, cohort, cancel, fc_slot, oi_slot);
        agg.ingest_funding_partial("BTCUSDT", Some(0.0001), Some(1_700_000_000_000));
        assert_eq!(
            agg.funding_partial_state_get("BTCUSDT"),
            Some((Some(0.0001), Some(1_700_000_000_000)))
        );
        let pushed = agg.repopulate_funding_buffer_from_cache();
        assert_eq!(pushed, 1);
        assert_eq!(agg.funding_curve().buffer_len(), 1);
    }

    #[tokio::test]
    async fn test_funding_partial_state_delta_only_rate() {
        // PASS：W1 P0 fix — 第一個 event 只 rate（無 next_ms）→ cache rate-only，
        // repopulate 不 push（缺 next_ms）；第二個 event 補 next_ms → cache 全 +
        // repopulate 後 inner buffer 入庫
        let pool = make_disconnected_pool().await;
        let cancel = CancellationToken::new();
        let cohort = vec!["BTCUSDT".to_string()];
        let (fc_slot, oi_slot) = make_slots();
        let mut agg = PanelAggregator::new(pool, cohort, cancel, fc_slot, oi_slot);
        // event 1: 只 rate
        agg.ingest_funding_partial("BTCUSDT", Some(0.0001), None);
        assert_eq!(
            agg.funding_partial_state_get("BTCUSDT"),
            Some((Some(0.0001), None))
        );
        let pushed1 = agg.repopulate_funding_buffer_from_cache();
        assert_eq!(pushed1, 0); // 缺 next_ms 不 push
        assert_eq!(agg.funding_curve().buffer_len(), 0);
        // event 2: 補 next_ms（不動 rate）
        agg.ingest_funding_partial("BTCUSDT", None, Some(1_700_000_000_000));
        assert_eq!(
            agg.funding_partial_state_get("BTCUSDT"),
            Some((Some(0.0001), Some(1_700_000_000_000)))
        );
        let pushed2 = agg.repopulate_funding_buffer_from_cache();
        assert_eq!(pushed2, 1); // 全齊 push
        assert_eq!(agg.funding_curve().buffer_len(), 1);
    }

    #[tokio::test]
    async fn test_funding_partial_state_persistence_across_repopulate() {
        // PASS：W1 P0 fix — cache 不隨 repopulate（或 inner flush drain）清空；
        // 模擬：snapshot → repopulate → flush drain inner buffer → repopulate
        // 仍 push 同 sym（每 60s flush 為 cohort 全 sym 寫一 row 的關鍵不變式）
        let pool = make_disconnected_pool().await;
        let cancel = CancellationToken::new();
        let cohort = vec!["BTCUSDT".to_string()];
        let (fc_slot, oi_slot) = make_slots();
        let mut agg = PanelAggregator::new(pool, cohort, cancel, fc_slot, oi_slot);
        agg.ingest_funding_partial("BTCUSDT", Some(0.0001), Some(1_700_000_000_000));
        // first cycle
        let pushed1 = agg.repopulate_funding_buffer_from_cache();
        assert_eq!(pushed1, 1);
        // simulate inner flush drain
        let _ = agg.funding_curve_mut().flush(1_700_000_001_000).await;
        assert_eq!(agg.funding_curve().buffer_len(), 0);
        // 不再 ingest，下個 cycle 仍能 repopulate（cache 仍有值）
        let pushed2 = agg.repopulate_funding_buffer_from_cache();
        assert_eq!(pushed2, 1);
        assert_eq!(agg.funding_curve().buffer_len(), 1);
    }

    #[tokio::test]
    async fn test_funding_partial_state_no_op_for_both_none() {
        // PASS：W1 P0 fix — event 兩 field 都 None → 不建 cache entry（避免 cache
        // 為 cohort 外或無 funding sym 無界長大）
        let pool = make_disconnected_pool().await;
        let cancel = CancellationToken::new();
        let cohort = vec!["BTCUSDT".to_string()];
        let (fc_slot, oi_slot) = make_slots();
        let mut agg = PanelAggregator::new(pool, cohort, cancel, fc_slot, oi_slot);
        agg.ingest_funding_partial("BTCUSDT", None, None);
        assert_eq!(agg.funding_partial_state_size(), 0);
    }

    #[tokio::test]
    async fn test_oi_delta_mut_accessor_dispatch() {
        // PASS：oi_delta_mut() 可 dispatch on_oi_update 進 history
        // 驗 sub-task 3 整合 dispatch path 不 broken (mirror funding_curve test)
        let pool = make_disconnected_pool().await;
        let cancel = CancellationToken::new();
        let cohort = vec!["BTCUSDT".to_string()];
        let (fc_slot, oi_slot) = make_slots();
        let mut agg = PanelAggregator::new(pool, cohort, cancel, fc_slot, oi_slot);
        agg.oi_delta_mut()
            .on_oi_update("BTCUSDT", 12345.6, 1_700_000_000_000);
        assert_eq!(agg.oi_delta().history_len(), 1);
    }

    #[tokio::test]
    async fn test_run_responds_to_cancel() {
        // PASS：run loop 收 cancel 立即退出（< 200ms）
        // 驗 cancel token 接線正確；防 sub-task 3 wire-up 後忘了傳 cancel
        let pool = make_disconnected_pool().await;
        let cancel = CancellationToken::new();
        let (fc_slot, oi_slot) = make_slots();
        let agg = PanelAggregator::new(pool, vec![], cancel.clone(), fc_slot, oi_slot);

        // 建一個空的 mpsc receiver 給 run loop（不送任何 event）
        let (_event_tx, event_rx) = mpsc::channel::<Arc<PriceEvent>>(8);

        let handle = tokio::spawn(async move {
            agg.run(event_rx).await;
        });

        // 給點時間進入 select! 等狀態
        tokio::time::sleep(std::time::Duration::from_millis(20)).await;
        cancel.cancel();

        // 應在 200ms 內退出（cancel 觸發 + log + return）
        let result = tokio::time::timeout(std::time::Duration::from_millis(200), handle).await;
        assert!(result.is_ok(), "run loop must exit on cancel within 200ms");
    }

    #[tokio::test]
    async fn test_run_dispatch_ticker_to_aggregators() {
        // PASS：run loop 收 Ticker variant 後 dispatch funding_rate + open_interest
        // 到對應 aggregator buffer/history。flush 由 60s timer 觸發本 test 不驗。
        // 改驗 slot 直接寫 — 但 60s timer 太久；改驗 send Ticker 後立即 cancel，
        // dispatch 應已發生（aggregator buffer 增長透過 flush 後驗，但 run 消耗 self
        // 故無法驗 buffer；改用 slot None observation：60s 內 cancel → slot 仍 None）。
        let pool = make_disconnected_pool().await;
        let cancel = CancellationToken::new();
        let cohort = vec!["BTCUSDT".to_string()];
        let (fc_slot, oi_slot) = make_slots();
        let agg = PanelAggregator::new(
            pool,
            cohort,
            cancel.clone(),
            fc_slot.clone(),
            oi_slot.clone(),
        );

        let (event_tx, event_rx) = mpsc::channel::<Arc<PriceEvent>>(8);

        let handle = tokio::spawn(async move {
            agg.run(event_rx).await;
        });

        // 送一個 cohort symbol 的 Ticker event 含 funding_rate + open_interest
        let mut ev = PriceEvent::new("BTCUSDT".to_string(), 65000.0, 1_700_000_000_000);
        ev.event_kind = Some(PriceEventKind::Ticker);
        ev.funding_rate = Some(0.0001);
        ev.next_funding_ms = Some(1_700_000_028_800_000);
        ev.open_interest = Some(12345.6);
        event_tx
            .send(Arc::new(ev))
            .await
            .expect("send must succeed");

        // 送 non-Ticker event：應 silent drop
        let mut trade_ev = PriceEvent::new("BTCUSDT".to_string(), 65001.0, 1_700_000_001_000);
        trade_ev.event_kind = Some(PriceEventKind::Trade);
        event_tx
            .send(Arc::new(trade_ev))
            .await
            .expect("send 2 must succeed");

        // 等 dispatch 處理 + cancel
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;
        cancel.cancel();

        let result = tokio::time::timeout(std::time::Duration::from_millis(200), handle).await;
        assert!(result.is_ok(), "run must exit on cancel after dispatch");

        // 60s 未到 → slot 仍 None（驗證 flush 沒在 cancel 之間誤觸）
        assert!(
            fc_slot.read().await.is_none(),
            "slot updated only on flush tick"
        );
        assert!(
            oi_slot.read().await.is_none(),
            "slot updated only on flush tick"
        );
    }

    #[test]
    fn test_create_panel_slots_returns_empty() {
        // PASS：create_panel_slots() 回 (None, None) tuple — late-inject 起點
        let (fc_slot, oi_slot) = create_panel_slots();
        // 同步 try_read 驗 None
        assert!(fc_slot.try_read().expect("no contention").is_none());
        assert!(oi_slot.try_read().expect("no contention").is_none());
    }
}
