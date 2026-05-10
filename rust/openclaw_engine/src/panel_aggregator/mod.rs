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

pub use btc_lead_lag::BtcLeadLagProducer;
pub use funding_curve::FundingCurveAggregator;
pub use oi_delta::OIDeltaAggregator;

use std::sync::Arc;

use tokio_util::sync::CancellationToken;
use tracing::info;

use crate::database::pool::DbPool;

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
    /// 預留供 sub-task 3 WS subscription wire-up 後使用。
    #[allow(dead_code)]
    cancel: CancellationToken,
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
    ) -> Self {
        let funding_curve_aggregator =
            FundingCurveAggregator::new(db_pool.clone(), cohort_symbols.clone());
        let oi_delta_aggregator = OIDeltaAggregator::new(db_pool.clone(), cohort_symbols);
        Self {
            funding_curve_aggregator,
            oi_delta_aggregator,
            db_pool,
            cancel,
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

    /// run_loop placeholder — 下游 sub-task 3 (E1-γ) 加 WS subscription +
    /// 60s flush timer 真實邏輯。
    ///
    /// 預期最終 shape（per W1 spec §2.3 + §3.3）：
    /// ```ignore
    /// pub async fn run(
    ///     mut self,
    ///     mut event_rx: broadcast::Receiver<PriceEvent>,
    /// ) {
    ///     let mut flush_timer = tokio::time::interval(Duration::from_secs(60));
    ///     loop {
    ///         tokio::select! {
    ///             _ = self.cancel.cancelled() => break,
    ///             _ = flush_timer.tick() => {
    ///                 let snapshot_ts_ms = now_ms() as i64;
    ///                 self.funding_curve_aggregator.flush(snapshot_ts_ms).await;
    ///                 self.oi_delta_aggregator.flush(snapshot_ts_ms).await;
    ///             }
    ///             event = event_rx.recv() => match event {
    ///                 Ok(ev) if ev.event_kind == Some(PriceEventKind::Ticker) => {
    ///                     if let (Some(fr), Some(nf)) = (ev.funding_rate, ev.next_funding_ms) {
    ///                         self.funding_curve_aggregator.on_funding_update(&ev.symbol, fr, nf);
    ///                     }
    ///                     if let Some(oi) = ev.open_interest {
    ///                         self.oi_delta_aggregator.on_oi_update(&ev.symbol, oi, ev.ts_ms as i64);
    ///                     }
    ///                 }
    ///                 // ... handle Lagged / Closed / non-Ticker ...
    ///             }
    ///         }
    ///     }
    /// }
    /// ```
    ///
    /// 本 sub-task 階段 placeholder：log 進入 + 等 cancel 即退出（不訂閱 WS、
    /// 不 flush）。允許整合 test 觀測 PanelAggregator 構造 + cancel 路徑通暢。
    pub async fn run_placeholder(self) {
        info!(
            target: "panel_aggregator",
            funding_curve_cohort_size = self.funding_curve_aggregator.cohort_size(),
            oi_delta_cohort_size = self.oi_delta_aggregator.cohort_size(),
            "PanelAggregator placeholder start (sub-task 1+2 skeleton; \
             WS subscription land in sub-task 3)"
        );
        self.cancel.cancelled().await;
        info!(
            target: "panel_aggregator",
            "PanelAggregator placeholder cancelled, shutting down"
        );
    }
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

    #[tokio::test]
    async fn test_panel_aggregator_constructs_with_cohort() {
        // PASS：PanelAggregator 建構 + funding_curve + oi_delta aggregator
        // cohort 大小對齊（兩 aggregator 共享同 cohort 25-sym snapshot）
        let pool = make_disconnected_pool().await;
        let cancel = CancellationToken::new();
        let cohort = vec!["BTCUSDT".to_string(), "ETHUSDT".to_string()];
        let agg = PanelAggregator::new(pool, cohort, cancel);
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
        let mut agg = PanelAggregator::new(pool, cohort, cancel);
        agg.funding_curve_mut()
            .on_funding_update("BTCUSDT", 0.0001, 1_700_000_000_000);
        assert_eq!(agg.funding_curve().buffer_len(), 1);
    }

    #[tokio::test]
    async fn test_oi_delta_mut_accessor_dispatch() {
        // PASS：oi_delta_mut() 可 dispatch on_oi_update 進 history
        // 驗 sub-task 3 整合 dispatch path 不 broken (mirror funding_curve test)
        let pool = make_disconnected_pool().await;
        let cancel = CancellationToken::new();
        let cohort = vec!["BTCUSDT".to_string()];
        let mut agg = PanelAggregator::new(pool, cohort, cancel);
        agg.oi_delta_mut()
            .on_oi_update("BTCUSDT", 12345.6, 1_700_000_000_000);
        assert_eq!(agg.oi_delta().history_len(), 1);
    }

    #[tokio::test]
    async fn test_run_placeholder_responds_to_cancel() {
        // PASS：run_placeholder 收 cancel 立即退出（< 100ms）
        // 驗 cancel token 接線正確；防 sub-task 3 wire-up 時忘了傳 cancel
        let pool = make_disconnected_pool().await;
        let cancel = CancellationToken::new();
        let agg = PanelAggregator::new(pool, vec![], cancel.clone());

        let handle = tokio::spawn(async move {
            agg.run_placeholder().await;
        });

        // 給點時間進入 cancelled().await
        tokio::time::sleep(std::time::Duration::from_millis(20)).await;
        cancel.cancel();

        // 應在 200ms 內退出（cancel 觸發 + log + return）
        let result = tokio::time::timeout(std::time::Duration::from_millis(200), handle).await;
        assert!(result.is_ok(), "run_placeholder must exit on cancel");
    }
}
