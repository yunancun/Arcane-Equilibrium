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
use std::path::PathBuf;
use tracing::{info, warn};

/// MUST-FIX-1 / 2 Round 2（2026-05-19/20）：test-only 全 crate 共用的
/// env-mutating test 互鎖。
///
/// 為什麼必要：cargo test 默認多執行緒；`std::env::set_var` / `remove_var`
/// 是 process 全局，halt_audit::tests 與 tick_pipeline::tests::halt_ttl 兩處
/// 都會操作 OPENCLAW_HALT_AUDIT_LOG / OPENCLAW_DATA_DIR。
/// 兩 module 內各自宣告 Mutex 等於兩個獨立鎖，跨 module 仍互踩；本鎖放這裡
/// 提供 cross-module 串行入口。
///
/// 路徑選擇：放在已 pub(crate) 的 paper_state_restore module，
/// 不增加新 module；cfg(test) 限定，prod build 無代價。
#[cfg(test)]
pub(crate) static ENV_TEST_MUTEX: std::sync::Mutex<()> = std::sync::Mutex::new(());

/// 取 ENV_TEST_MUTEX，poisoned 時用 into_inner 強解（test 場景不影響 prod）。
#[cfg(test)]
pub(crate) fn env_test_lock() -> std::sync::MutexGuard<'static, ()> {
    ENV_TEST_MUTEX.lock().unwrap_or_else(|p| p.into_inner())
}

/// EN: Restore cumulative paper_state counters for the given pipeline from
///     `trading.fills`. Runs once at engine boot before the first tick. The
///     query is filtered by `engine_mode` so each of the three parallel
///     engines (paper / demo / live) restores only its own history.
///
/// Fail-soft contract:
/// - `audit_pool = None` → no-op + info log (cold start / PG disabled).
/// - SQL error → warn log + counters stay at zero. Engine must always boot even
///   if Postgres is unreachable.
/// - Success → info log with the restored values so operators can confirm the
///   GUI "total realized PnL" / "total fees" numbers survived a restart.
///
/// 中文: 為指定管線從 `trading.fills` 還原 paper_state 累計指標。啟動時執行
///       一次，發生在首個 tick 之前。以 `engine_mode` 過濾讓 paper/demo/live
///       三條並行引擎各自僅還原自己的歷史。
///
/// Fail-soft 合約：
/// - audit_pool=None → no-op + info log（冷啟動 / PG 停用）
/// - SQL 錯誤 → warn log，計數器保持 0。引擎必須一定能啟動。
/// - 成功 → info log 紀錄還原值，讓 operator 確認重啟後 GUI「累計已實現 PnL /
///   手續費」沒歸零。
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

/// MUST-FIX-2 Round 2（2026-05-19/20）：從 `pipeline_snapshot_<kind>.json` 還原
/// `halt_kind` / `halt_set_ts_ms`，讓 P0-ENGINE-HALTSESSION-STUCK-FIX 的 TTL
/// 起點跨 restart 不重置（AC A-4）。
///
/// 為什麼必要：Round 1 `pipeline_ctor.rs` 初始化 halt 狀態為 None / 0；
/// snapshot 寫入端 `commands.rs::snapshot()` 已把 halt_kind / halt_set_ts_ms
/// 序列化進 `mode_snapshots[kind].halt_kind` 與 `.halt_set_ts_ms` 兩處（亦
/// 鏡像進 `PipelineSnapshot::halt_set_ts_ms` 頂層），但沒有 boot-time 還原路徑
/// → 重啟後 24h TTL 起點被誤重置成 boot wall-clock，違反 spec AC A-4。
///
/// Fail-soft 合約：
/// - data_dir 不存在 / snapshot 檔不存在 / 讀檔失敗 / 解析失敗 / mode_snapshots
///   無對應 kind / halt_kind=null → 全部視為「冷啟動」，pipeline halt 狀態維持
///   ctor 預設（None / 0），不阻塞 boot
/// - 任何錯誤透過 `tracing::warn!` 紀錄，operator 可在事故時排查
/// - 不擔保 halt_set_ts_ms 為「未來時間」做時鐘倒流檢查 —— 由 on_tick 內
///   `saturating_sub` 保護（test_clock_skew_no_panic）
///
/// 還原路徑（最小變更）：
///   1. snapshot path = `${OPENCLAW_DATA_DIR}/pipeline_snapshot_<kind_tag>.json`
///      （與 bootstrap.rs 寫入路徑對齊）
///   2. 解析為 `PipelineSnapshot`
///   3. 讀 `mode_snapshots[kind_tag].halt_kind` + `.halt_set_ts_ms`
///   4. 若 halt_kind=Some(kind)，寫回 `pipeline.halt_kind` / `pipeline.halt_set_ts_ms`；
///      同步重置 paper_paused / session_halted 為 snapshot 內值（避免人為
///      Resume 後 restart 卻又被 halt re-engage 的不一致；Round 1 snapshot
///      也把 paper_paused 寫進 ModeStateSnapshot 但 restore 端不讀）
///
/// 注意：本路徑不寫 halt_audit forensic 行 —— restore 是「延續既有 halt」非
/// 「新 halt」。原 set 行已在事故發生時寫過，restore 不重複。
pub(crate) async fn restore_halt_state_from_snapshot(pipeline: &mut TickPipeline) {
    let data_dir = std::env::var("OPENCLAW_DATA_DIR").unwrap_or_else(|_| "/tmp/openclaw".into());
    let kind_tag = pipeline.pipeline_kind.db_mode(); // "paper" | "demo" | "live"
    let snapshot_path = PathBuf::from(&data_dir).join(format!("pipeline_snapshot_{kind_tag}.json"));

    if !snapshot_path.exists() {
        info!(
            kind = %pipeline.pipeline_kind,
            path = %snapshot_path.display(),
            "halt-restore: no per-engine snapshot — cold start \
             / 無前次 snapshot，halt 狀態冷啟動"
        );
        return;
    }

    let content = match std::fs::read_to_string(&snapshot_path) {
        Ok(c) => c,
        Err(e) => {
            warn!(
                kind = %pipeline.pipeline_kind,
                path = %snapshot_path.display(),
                error = %e,
                "halt-restore: read failed; cold-start halt state (fail-soft) \
                 / 讀檔失敗，halt 狀態冷啟動"
            );
            return;
        }
    };

    // 用寬鬆解析：仍嘗試 PipelineSnapshot，但任一字段 missing 不致命；
    // 為避免 PipelineSnapshot 內其他 field 解析失敗誤殺整個 halt 還原，
    // 改用 serde_json::Value 抓 mode_snapshots → kind_tag → halt_kind / halt_set_ts_ms。
    let value: serde_json::Value = match serde_json::from_str(&content) {
        Ok(v) => v,
        Err(e) => {
            warn!(
                kind = %pipeline.pipeline_kind,
                path = %snapshot_path.display(),
                error = %e,
                "halt-restore: JSON parse failed; cold-start halt state (fail-soft) \
                 / JSON 解析失敗，halt 狀態冷啟動"
            );
            return;
        }
    };

    let mode_snap = value
        .get("mode_snapshots")
        .and_then(|m| m.get(kind_tag));
    let mode_snap = match mode_snap {
        Some(v) => v,
        None => {
            info!(
                kind = %pipeline.pipeline_kind,
                "halt-restore: mode_snapshots missing kind entry — cold start \
                 / 快照無對應 kind 條目，halt 狀態冷啟動"
            );
            return;
        }
    };

    // halt_kind: Option<HaltKind> 序列化為 "daily_loss"|"session_drawdown"|"other"|null
    let halt_kind_raw = mode_snap.get("halt_kind");
    let halt_kind: Option<crate::halt_audit::HaltKind> = match halt_kind_raw {
        None | Some(serde_json::Value::Null) => None,
        Some(v) => serde_json::from_value(v.clone()).unwrap_or_else(|e| {
            warn!(
                kind = %pipeline.pipeline_kind,
                halt_kind_raw = %v,
                error = %e,
                "halt-restore: halt_kind unrecognized; cold-start halt state \
                 / halt_kind 無法解析，halt 狀態冷啟動"
            );
            None
        }),
    };

    let halt_set_ts_ms = mode_snap
        .get("halt_set_ts_ms")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);

    let snap_paper_paused = mode_snap
        .get("paper_paused")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let snap_session_halted = mode_snap
        .get("session_halted")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);

    // 還原規則：
    // - halt_kind=Some + halt_set_ts_ms>0 → 視為「延續既有 halt」，
    //   同步 paper_paused/session_halted 為 snapshot 值
    // - halt_kind=None → 不動 pipeline（ctor 預設 None / 0），紀錄 info
    match halt_kind {
        Some(k) if halt_set_ts_ms > 0 => {
            pipeline.halt_kind = Some(k);
            pipeline.halt_set_ts_ms = halt_set_ts_ms;
            // paper_paused 與 session_halted 也由 snapshot 還原 —— 否則
            // ctor 預設 false 會跟 halt_kind=Some 不一致。
            pipeline.paper_paused = snap_paper_paused;
            pipeline.session_halted = snap_session_halted;
            info!(
                kind = %pipeline.pipeline_kind,
                halt_kind = k.as_str(),
                halt_set_ts_ms,
                paper_paused = snap_paper_paused,
                session_halted = snap_session_halted,
                "halt-restore: halt state restored from snapshot \
                 / 已從 snapshot 還原 halt 狀態（TTL 起點延續）"
            );
        }
        Some(k) => {
            // halt_kind 存在但 set_ts=0：不一致；保守當冷啟動
            warn!(
                kind = %pipeline.pipeline_kind,
                halt_kind = k.as_str(),
                "halt-restore: halt_kind set but halt_set_ts_ms=0; cold-start (fail-soft) \
                 / halt_kind 有值但 set_ts=0，視為冷啟動"
            );
        }
        None => {
            info!(
                kind = %pipeline.pipeline_kind,
                "halt-restore: snapshot halt_kind=None — no active halt to restore \
                 / 快照 halt_kind=None，無 active halt 待還原"
            );
        }
    }
}
