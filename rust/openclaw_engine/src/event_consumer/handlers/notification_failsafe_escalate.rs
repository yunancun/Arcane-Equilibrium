//! MODULE_NOTE
//! 模塊用途：通知 fail-safe in-band 自動升級 handler（P2-PACKET-C-C4-PIPELINE-WIRE）。
//!   三路通知全 fail 1h timeout 後，watcher 經 `PipelineCommand::NotificationFailsafeEscalate`
//!   觸發，由 owner task 在 async context 內呼 `handle_notification_failsafe_escalate`。
//! 主要類/函數：`handle_notification_failsafe_escalate`（入口）、`PrebuiltSnapshots`、
//!   `InBandStopSync`、`NoopFailsafeAudit`、`compute_position_atr`（內部 helper）。
//! 依賴：core `execute_failsafe_escalation`、`TickPipeline`、`DualStateWriter`、
//!   notification_failsafe::{ExchangeStopSync, FailsafeAuditEmitter, ...}。
//! 硬邊界：transition 是收緊風控（Normal→Defensive），不開新倉不碰授權門控；
//!   idempotent（watcher claim-before-await + `from < Defensive` guard 雙層）。
//!
//! 由 `handlers/risk.rs` 純搬移而來（FA gap audit G1，2026-05-29）：risk.rs 當時達
//! 822 行；拆出 C4 escalate handler + 4 helper（~205 LOC）保留聚焦職責及現行
//! 2000 行 review/split 門檻內的空間。**0 邏輯改**，僅機械性搬移 + import 隨遷。

use crate::persistence::DualStateWriter;
use crate::tick_pipeline::TickPipeline;
use tracing::{info, warn};

// P2-PACKET-C-C4-PIPELINE-WIRE — fail-safe in-band escalate handler 依賴。
use crate::notification_failsafe::audit_emitter::PgAuditEmitter;
use crate::notification_failsafe::{
    execute_failsafe_escalation, ExchangeStopError, ExchangeStopSync, FailsafeAuditEmitter,
    FailsafeConfig, PositionSnapshotProvider,
};
use crate::tick_pipeline::StopRequest;
use async_trait::async_trait;
use openclaw_core::sm::risk_gov::{PositionSnapshot, StopAdjustment};
use tokio::sync::mpsc::UnboundedSender;

/// 預建快照 provider — owner task 在呼 `execute_failsafe_escalation` 前先組好
/// ATR 注入的 `Vec<PositionSnapshot>`，避免在 escalation 內部同時借 `pipeline`。
///
/// 為什麼預建而非讓 provider 端拿 kline：`execute_failsafe_escalation` 需
/// `&mut pipeline.governance.risk`，若 provider 內部再借 `pipeline.kline_manager`
/// 會與 `&mut` 衝突。故 handler 先 immutable 借 pipeline 組好 snapshot，再進 escalation。
struct PrebuiltSnapshots(Vec<PositionSnapshot>);
impl PositionSnapshotProvider for PrebuiltSnapshots {
    fn snapshot_positions(&self) -> Vec<PositionSnapshot> {
        self.0.clone()
    }
}

/// Fail-safe 交易所 conditional SL 同步器 — 復用既有 server-side stop 雙軌通道
/// （`stop_request_tx` → bootstrap.rs consumer → `PositionManager::set_trading_stop`）。
///
/// 為什麼不新構 `BybitExchangeStopSync(Arc<PositionManager>)`：owner pipeline 不持
/// PositionManager（私有在 consumer task 內）；新構第二 client 違反單一寫入口。
/// 改 send `StopRequest`，consumer 已驗的雙軌路徑統一處理（含 paper log-only）。
///
/// paper noop（C4 spec §3.2 defense-in-depth）：`engine_mode == "paper"` 時直接回
/// `Ok(())` 不 send StopRequest（雙重保險之第二層；第一層是 watcher loop 結構性不
/// 迭代 paper slot）。即便理論不可達也短路，杜絕 paper 倉位誤打 demo endpoint。
///
/// fire-and-forget 語義：`UnboundedSender::send` 只入 channel 不等交易所回應；
/// 真正的 retCode fail-closed / 不重試由 consumer 端 `set_trading_stop` 既有邏輯把守
/// （Root Principle 9 雙軌、CLAUDE §四 不加隱藏重試）。channel 已關（pipeline 拆解中）
/// 回 `Transport`，escalation 記入 sync_record 不 rollback transition（survival 優先）。
struct InBandStopSync {
    stop_tx: Option<UnboundedSender<StopRequest>>,
    engine_mode: &'static str,
}

#[async_trait]
impl ExchangeStopSync for InBandStopSync {
    async fn sync_stop(&self, adjustment: &StopAdjustment) -> Result<(), ExchangeStopError> {
        // paper noop：結構上 watcher 不會對 paper 發 escalate；此處為第二層短路防禦。
        if self.engine_mode == "paper" {
            return Ok(());
        }
        let Some(ref tx) = self.stop_tx else {
            // server_side_stops 關閉 → 無交易所軌；降為單線本地保護（誠實標記）。
            return Err(ExchangeStopError::Transport(
                "no server-side stop channel (single-rail local-only)".into(),
            ));
        };
        // side：StopAdjustment.side 為 "Buy"/"Sell"；StopRequest.is_long 需 bool。
        let is_long = matches!(adjustment.side, "Buy");
        tx.send(StopRequest {
            symbol: adjustment.symbol.clone(),
            stop_loss: adjustment.new_sl,
            is_long,
        })
        .map_err(|e| ExchangeStopError::Transport(format!("stop channel closed: {e}")))
    }
}

/// 缺 audit pool 時的 noop emitter（fail-soft：audit 是記錄用途，缺 pool 不阻 escalation）。
struct NoopFailsafeAudit;
#[async_trait]
impl FailsafeAuditEmitter for NoopFailsafeAudit {
    async fn emit_auto_escalated(
        &self,
        _payload: serde_json::Value,
    ) -> Result<(), crate::notification_failsafe::FailsafeAuditError> {
        Ok(())
    }
}

/// 從 owner task 的 `kline_manager` 算單一 symbol 的絕對 ATR14。
///
/// 為什麼絕對值（`r.atr`）非百分比（`r.atr_percent`）：`active_lock_profit_per_position`
/// 公式 `new_sl = entry ± atr × buffer` 要求絕對 ATR（risk_gov.rs:296 position-life ATR）。
/// Cold-start < 15 bars → `atr()` 回 `None` → 回 0.0 → 下游 fail-closed 跳過該倉
/// （C4 spec §1.1：缺 ATR → 鎖利空轉但 SM-04 仍升）。
fn compute_position_atr(pipeline: &TickPipeline, symbol: &str) -> f64 {
    pipeline
        .kline_manager
        .get_ohlcv(symbol, "1m", Some(20))
        .and_then(|o| openclaw_core::indicators::atr(&o.high, &o.low, &o.close, 14))
        .map(|r| r.atr)
        .unwrap_or(0.0)
}

/// P2-PACKET-C-C4-PIPELINE-WIRE · 通知三路全 fail 1h timeout 的 in-band 自動升級。
///
/// 由 `loop_handlers::handle_pipeline_command` 攔截 `NotificationFailsafeEscalate`
/// 後在 owner task（async context）內呼叫。流程（C4 spec §1.3）：
///   1. owner task 內組 `Vec<PositionSnapshot>`：倉位源 `paper_state.positions()`（demo/live
///      已確認 fill 的真值），ATR 從 `kline_manager` 算絕對 ATR14；
///   2. 復用 core `execute_failsafe_escalation`：SM-04 transition（`from < Defensive` guard）
///      + `active_lock_profit_per_position` 鎖利 + 逐倉 exchange sync + audit emit；
///   3. exchange sync 走 `InBandStopSync`（既有 server-side stop 雙軌通道，paper noop）；
///   4. audit 走 owner 端 `PgAuditEmitter`（option a：transition/sync 結果就地最完整）；
///   5. `force_write` snapshot；回 report JSON 給 watcher（log，不阻塞）。
///
/// 為什麼倉位源用 `paper_state.positions()` 而非 C3 `RestPositionProvider`：
///   owner task 內 paper_state 是真值且含 ATR 可算來源（kline_manager）；REST 不回 ATR
///   且需額外 round-trip。C3 RestPositionProvider 因此不在主路徑被呼叫（superseded）。
///
/// 硬邊界：transition 是收緊風控（Normal→Defensive），不開新倉不碰授權門控。
/// idempotent：watcher 端 claim-before-await + 此處 `from < Defensive` guard 雙層。
pub(crate) async fn handle_notification_failsafe_escalate(
    reason: String,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
    audit_pool: Option<&sqlx::PgPool>,
) {
    let engine_mode = pipeline.effective_engine_mode();
    let now_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0);

    // Step 1：owner task 內組 ATR 注入 snapshot（倉位源 paper_state，ATR 源 kline_manager）。
    // 倉位 immutable 借完即 collect 成 owned Vec，後續 `&mut governance.risk` 不再衝突。
    let snapshots: Vec<PositionSnapshot> = pipeline
        .paper_state
        .positions()
        .iter()
        .map(|p| {
            let atr = compute_position_atr(pipeline, &p.symbol);
            PositionSnapshot {
                symbol: p.symbol.clone(),
                side: if p.is_long { "Buy" } else { "Sell" },
                entry_price: p.entry_price,
                qty: p.qty,
                // PaperPosition 無 current_sl 欄位 → None（active_lock_profit 不放鬆既有
                // 保護方向的比較此時無 baseline，直接套新鎖利 SL）。
                current_sl: None,
                atr,
            }
        })
        .collect();
    let position_count = snapshots.len();
    let atr_missing = snapshots.iter().filter(|s| s.atr <= 0.0).count();

    // Step 2-4：交易所 sync 通道 + audit emitter 組裝（脫離 pipeline 借用前先取 stop_tx clone）。
    let stop_tx = pipeline.stop_channel().cloned();
    let exchange = InBandStopSync {
        stop_tx,
        engine_mode,
    };
    let provider = PrebuiltSnapshots(snapshots);
    let cfg = FailsafeConfig::default();

    // audit：option a — owner 端 PgAuditEmitter（缺 pool fail-soft noop）。
    let report = if let Some(pool) = audit_pool {
        let audit = PgAuditEmitter::new(pool.clone());
        execute_failsafe_escalation(
            &mut pipeline.governance.risk,
            &provider,
            &exchange,
            &audit,
            &cfg,
            now_ms,
        )
        .await
    } else {
        let audit = NoopFailsafeAudit;
        execute_failsafe_escalation(
            &mut pipeline.governance.risk,
            &provider,
            &exchange,
            &audit,
            &cfg,
            now_ms,
        )
        .await
    };

    // Step 5：snapshot 落盤 + 結構化日誌。
    snapshot_writer.force_write(&pipeline.snapshot());
    info!(
        engine_mode = %engine_mode,
        reason = %reason,
        from = %report.from_level,
        to = %report.to_level,
        transition_succeeded = report.transition_succeeded,
        position_count,
        atr_missing,
        adjustments = report.adjustments_count,
        audit_emitted = report.audit_emitted,
        "notification fail-safe in-band escalate / 通知 fail-safe in-band 升級"
    );
    if atr_missing > 0 {
        // 誠實標記：缺 ATR 倉位鎖利空轉，但 SM-04 仍升（雙重防線降為單線本地）。
        warn!(
            engine_mode = %engine_mode,
            atr_missing,
            position_count,
            "fail-safe: {atr_missing}/{position_count} 倉缺 ATR — 鎖利跳過但 SM-04 已升 \
             / lock-profit skipped for missing-ATR positions, SM-04 still escalated"
        );
    }

    let result = serde_json::to_string(&report)
        .map_err(|e| format!("serialize failsafe report: {e}"));
    let _ = response_tx.send(result);
}
