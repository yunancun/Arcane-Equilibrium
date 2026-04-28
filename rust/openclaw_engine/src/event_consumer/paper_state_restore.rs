//! QoL-1: Paper state counter restoration from trading.fills.
//! QoL-1：從 trading.fills 還原 paper_state 累計指標。
//!
//! MODULE_NOTE (EN): Extracted from event_consumer/mod.rs (file-size discipline,
//!   matches governor_cooldown.rs precedent). Wraps the fail-soft boot-time
//!   restore of cumulative paper_state counters (total_realized_pnl / total_fees
//!   / trade_count) for a specific engine_mode ("paper" / "demo" / "live"). The
//!   DB query lives on `PaperState::restore_from_db`; this helper glues the
//!   audit pool + logging so mod.rs can call it in one line.
//! MODULE_NOTE (中): 從 event_consumer/mod.rs 抽出（檔案大小紀律，沿用
//!   governor_cooldown.rs 的樣式）。封裝啟動時 fail-soft 還原 paper_state
//!   累計指標（total_realized_pnl / total_fees / trade_count），按
//!   engine_mode（paper/demo/live）三引擎隔離。SQL 本身在
//!   `PaperState::restore_from_db`，本 helper 負責串接 audit pool 與日誌，
//!   讓 mod.rs 只剩一行呼叫。

use crate::tick_pipeline::TickPipeline;
use tracing::{info, warn};

/// EN: Restore cumulative paper_state counters for the given pipeline from
///     `trading.fills`. Runs once at engine boot before the first tick. The
///     query is filtered by `engine_mode` so each of the three parallel
///     engines (paper / demo / live) restores only its own history.
///
///     Fail-soft contract:
///       * `audit_pool = None` → no-op + info log (cold start / PG disabled).
///       * SQL error           → warn log + counters stay at zero. Engine must
///                               always boot even if Postgres is unreachable.
///       * Success             → info log with the restored values so operators
///                               can confirm the GUI "total realized PnL" /
///                               "total fees" numbers survived a restart.
///
/// 中文: 為指定管線從 `trading.fills` 還原 paper_state 累計指標。啟動時執行
///       一次，發生在首個 tick 之前。以 `engine_mode` 過濾讓 paper/demo/live
///       三條並行引擎各自僅還原自己的歷史。
///
///       Fail-soft 合約：
///         * audit_pool=None → no-op + info log（冷啟動 / PG 停用）
///         * SQL 錯誤        → warn log，計數器保持 0。引擎必須一定能啟動。
///         * 成功            → info log 紀錄還原值，讓 operator 確認重啟後
///                             GUI「累計已實現 PnL / 手續費」沒歸零。
pub(crate) async fn restore_paper_counters(
    pipeline: &mut TickPipeline,
    audit_pool: Option<&sqlx::PgPool>,
) {
    // Endpoint-aware tag: live + LiveDemo resolves to "live_demo" so we only
    // restore rows that belong to this pipeline's endpoint (no mixing with
    // real-mainnet "live" history).
    // endpoint 感知標籤：Live + LiveDemo 解析為 "live_demo"，只還原真正屬於
    // 本管線端點的 fills（不會撈到 mainnet "live" 歷史）。
    let em = pipeline.effective_engine_mode();
    let kind = pipeline.pipeline_kind;
    let pool = match audit_pool {
        Some(p) => p,
        None => {
            info!(
                kind = %kind,
                engine_mode = em,
                "QoL-1: no audit pool — paper_state counters start at zero (cold start) \
                 / 無審計 pool，累計指標從零開始（冷啟動）"
            );
            return;
        }
    };
    match pipeline.paper_state.restore_from_db(pool, em).await {
        Ok(()) => {
            info!(
                kind = %kind,
                engine_mode = em,
                total_realized_pnl = pipeline.paper_state.total_realized_pnl(),
                total_fees = pipeline.paper_state.total_fees(),
                total_funding_pnl = pipeline.paper_state.total_funding_pnl(),
                trade_count = pipeline.paper_state.trade_count(),
                "QoL-1: paper_state counters restored from trading.fills + funding ledger \
                 / 已從 trading.fills + funding ledger 還原 paper_state 累計指標"
            );
        }
        Err(e) => {
            warn!(
                kind = %kind,
                engine_mode = em,
                error = %e,
                "QoL-1: paper_state counter restore failed; starting with zero counters \
                 (fail-soft) / 還原累計指標失敗，以零計數器啟動（fail-soft）"
            );
        }
    }

    // P1-5 A2: restore peak_balance + session_start_ts from the dedicated
    // checkpoint table so cross-restart drawdown continuity survives. Must run
    // AFTER `restore_from_db` so `apply_restored_counters` has already brought
    // peak_balance up to `restored_balance`; restore_checkpoint then takes the
    // max of that and the stored peak. Cold start / post-reset (no row) falls
    // through to existing behaviour (peak = restored_balance).
    // P1-5 A2：還原 peak_balance + session_start_ts 以維持跨重啟 drawdown 連續性。
    // 必須在 restore_from_db 之後執行（restore_checkpoint 取 max）；冷啟動
    // 或 reset 後（無 row）維持既有行為（peak = restored_balance）。
    match crate::paper_state::checkpoint::load_checkpoint(pool, em).await {
        Ok(Some((peak, session_start_ts_ms))) => {
            pipeline
                .paper_state
                .restore_checkpoint(peak, session_start_ts_ms);
            info!(
                kind = %kind,
                engine_mode = em,
                restored_peak = peak,
                effective_peak = pipeline.paper_state.peak_balance(),
                session_start_ts_ms,
                drawdown_pct = pipeline.paper_state.drawdown_pct(),
                "P1-5 A2: peak_balance restored from paper_state_checkpoint \
                 / 已從 checkpoint 還原 peak_balance（跨重啟 drawdown 連續）"
            );
        }
        Ok(None) => {
            info!(
                kind = %kind,
                engine_mode = em,
                peak = pipeline.paper_state.peak_balance(),
                "P1-5 A2: no checkpoint row — cold start / post-reset \
                 / 無 checkpoint row，視為冷啟動或剛 reset"
            );
        }
        Err(e) => {
            warn!(
                kind = %kind,
                engine_mode = em,
                error = %e,
                "P1-5 A2: checkpoint load failed; drawdown continuity disabled this session \
                 (fail-soft) / checkpoint 載入失敗，此次 session 無 drawdown 連續性"
            );
        }
    }
}
