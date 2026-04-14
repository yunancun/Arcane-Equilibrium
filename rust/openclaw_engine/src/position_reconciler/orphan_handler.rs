//! ORPHAN-ADOPT-1 Phase 1: Unified orphan decision + close dispatch.
//! ORPHAN-ADOPT-1 Phase 1：統一孤兒決策 + 平倉分發。
//!
//! MODULE_NOTE (EN): Replaces the "detect-but-do-nothing" behaviour for single
//!   orphans (Bybit has a position, reconciler baseline does not). Runs between
//!   drift classification and `evaluate_actions()`: each Orphan verdict is
//!   funnelled through `handle_orphan()`, which returns a `OrphanDecision`.
//!
//!   Stage A — hard safety (any hit → immediate close):
//!     A1. Liquidation distance too close: |mark - liq| / mark < 10%
//!     A2. Global CircuitBreaker active (risk level ≥ CB)
//!     A3. Notional > max_order_notional_usdt (when cap configured)
//!     A4. Symbol not in scanner active universe
//!
//!   Stage B — soft eval (conservative close only, Phase 1):
//!     B1. All known strategies have non-positive edge on symbol AND
//!         unrealized PnL > 0  → lock-profit close
//!     B2. Anything else ambiguous → conservative close (原則 #6 失敗默認收縮)
//!
//!   Stage C — adopt (DEFERRED to Phase 2):
//!     Real adoption requires synthetic StrategyId + paper_state injection +
//!     StopManager binding + Strategist agent (G-1 R-02) for "same-direction
//!     signal" semantics. Until Phase 2 lands, every would-be-adoption degrades
//!     to `SoftConservative` close with an audit marker.
//!
//!   All close paths dispatch `PipelineCommand::CloseSymbol { hint_is_long,
//!   hint_qty }` — the existing tick_pipeline handler already supports orphan
//!   positions not tracked in paper_state via the hint fields.
//!
//!   Dedup: `pending_orphan_closes: HashMap<String, u64>` in ReconcilerState
//!   suppresses retriggering a close within `ORPHAN_CLOSE_DEDUP_MS` (2 min) so
//!   we don't spam duplicate reduce_only orders while the first one clears.
//!
//! MODULE_NOTE (中): 取代舊的「偵測但不動作」孤兒處理。在分類與 evaluate_actions
//!   之間插入統一決策 handle_orphan，每個 Orphan 走 Stage A 硬安全 → Stage B
//!   軟評估 → Stage C（Phase 2 延後）。Phase 1 所有路徑都收斂到 Close（附清晰
//!   audit reason）。透過既有 CloseSymbol 指令 + hint 參數平倉。2 分鐘去重
//!   避免重複下單。

use super::escalation::ReconcilerState;
use crate::edge_estimates::EdgeEstimates;
use crate::position_manager::PositionInfo;
use crate::scanner::registry::SymbolRegistry;
use crate::tick_pipeline::PipelineCommand;
use openclaw_core::sm::risk_gov::RiskLevel;
use std::sync::Arc;
use tokio::sync::mpsc::UnboundedSender;
use tracing::{info, warn};

/// Minimum safe distance from liquidation price as fraction of mark price.
/// If |mark - liq| / mark < this, Stage A closes immediately.
/// Phase 2 should replace with 5 × ATR (ATR not currently on PositionInfo).
/// 距強平最小安全距離（占 mark price 比例）。低於此值 Stage A 立即平倉。
/// Phase 2 應替換為 5 × ATR（ATR 目前未接入 PositionInfo）。
pub const LIQ_DISTANCE_SAFETY_PCT: f64 = 0.10;

/// Dedup window — suppress repeat orphan close for same (symbol|side) within this ms.
/// Chosen to cover typical exchange ack latency + one 30s reconcile cycle.
/// 去重窗口 — 同一 (symbol|side) 在此時間內不重複下平倉單。涵蓋交易所 ack
/// 延遲 + 一個 30s 對帳週期。
pub const ORPHAN_CLOSE_DEDUP_MS: u64 = 2 * 60 * 1000;

/// Strategy names the handler will probe when checking "any positive edge".
/// Kept in sync with strategies registered in `StrategyFactory`.
/// 檢查「任一正邊際」時會掃描的策略名稱清單，與 StrategyFactory 保持同步。
pub const KNOWN_STRATEGY_NAMES: &[&str] = &[
    "ma_crossover",
    "bb_reversion",
    "bb_breakout",
    "grid_trading",
    "funding_arb",
];

/// Stage that drove the decision (for audit). Phase 1 never emits Adopt.
/// 決策來源階段（用於 audit）。Phase 1 永不輸出 Adopt。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OrphanStage {
    HardSafetyLiqClose,
    HardSafetyCircuitBreaker,
    HardSafetyNotionalCap,
    HardSafetyNotInUniverse,
    SoftLockProfit,
    SoftConservative,
    AdoptDeferredPhase2,
}

impl OrphanStage {
    pub fn as_str(&self) -> &'static str {
        match self {
            OrphanStage::HardSafetyLiqClose => "hard_safety_liq_close",
            OrphanStage::HardSafetyCircuitBreaker => "hard_safety_circuit_breaker",
            OrphanStage::HardSafetyNotionalCap => "hard_safety_notional_cap",
            OrphanStage::HardSafetyNotInUniverse => "hard_safety_not_in_universe",
            OrphanStage::SoftLockProfit => "soft_lock_profit",
            OrphanStage::SoftConservative => "soft_conservative",
            OrphanStage::AdoptDeferredPhase2 => "adopt_deferred_phase2",
        }
    }
}

/// Unified decision returned by `handle_orphan()`.
/// 由 handle_orphan() 返回的統一決策。
#[derive(Debug, Clone, PartialEq)]
pub enum OrphanDecision {
    /// Dispatch CloseSymbol to the tick_pipeline; target reduce_only market.
    /// 向 tick_pipeline 發送 CloseSymbol；目標 reduce_only 市價平倉。
    Close { reason: String, stage: OrphanStage },
    /// Phase 2 only — reserved variant. Phase 1 never returns this.
    /// Phase 2 才會使用的保留變體。Phase 1 不會返回。
    #[allow(dead_code)]
    Adopt { reason: String },
}

/// Per-cycle context for a single orphan decision.
/// 單次孤兒決策的 per-cycle 上下文。
pub struct OrphanContext<'a> {
    pub pos_info: &'a PositionInfo,
    pub current_level: RiskLevel,
    /// max_order_notional_usdt from per-engine RiskConfig; 0 = no cap (skip check).
    /// 來自 per-engine RiskConfig 的名目上限；0 = 不檢查。
    pub max_order_notional_usdt: f64,
    /// Scanner's current active universe (empty slice = skip universe check).
    /// 掃描器當前活躍字集合（空切片 = 跳過檢查）。
    pub active_symbols: &'a [String],
    /// Shared edge estimates; `EdgeEstimates::empty()` disables Stage B1 edge lookup.
    /// 共享邊際估計；空估計集 = 停用 Stage B1 edge lookup。
    pub edge_estimates: &'a EdgeEstimates,
}

/// Long-lived wiring: shared handles the reconciler captures once and reads
/// each cycle. `None` → reconciler runs in legacy mode (no orphan processing).
/// 長期接線：對帳器捕獲一次，每週期讀取。None → 對帳器走舊模式（無孤兒處理）。
#[derive(Clone)]
pub struct OrphanHandlerConfig {
    pub symbol_registry: Arc<SymbolRegistry>,
    pub edge_estimates: Arc<parking_lot::RwLock<EdgeEstimates>>,
    /// Closure that returns the current `max_order_notional_usdt` for this engine.
    /// 回傳當前引擎 max_order_notional_usdt 的閉包。
    pub get_max_notional: Arc<dyn Fn() -> f64 + Send + Sync>,
}

/// Pure decision function — no I/O, no channel sends.
/// 純決策函數 — 無 I/O、無 channel 發送。
pub fn handle_orphan(ctx: &OrphanContext) -> OrphanDecision {
    let pos = ctx.pos_info;

    // ── Stage A1: liquidation distance ────────────────────────────────────
    if pos.liq_price > 0.0 && pos.mark_price > 0.0 {
        let dist_pct = (pos.mark_price - pos.liq_price).abs() / pos.mark_price;
        if dist_pct < LIQ_DISTANCE_SAFETY_PCT {
            return OrphanDecision::Close {
                reason: format!(
                    "liq_distance_pct={:.4} < safety={:.2} (mark={:.4} liq={:.4})",
                    dist_pct, LIQ_DISTANCE_SAFETY_PCT, pos.mark_price, pos.liq_price
                ),
                stage: OrphanStage::HardSafetyLiqClose,
            };
        }
    }

    // ── Stage A2: global CircuitBreaker ───────────────────────────────────
    if ctx.current_level >= RiskLevel::CircuitBreaker {
        return OrphanDecision::Close {
            reason: format!("global risk level={:?} (≥ CircuitBreaker)", ctx.current_level),
            stage: OrphanStage::HardSafetyCircuitBreaker,
        };
    }

    // ── Stage A3: notional cap ────────────────────────────────────────────
    // 0 sentinel = disabled (matches risk_config.rs convention).
    // 0 表示不啟用（與 risk_config.rs 約定一致）。
    if ctx.max_order_notional_usdt > 0.0 {
        let notional = pos.size * pos.mark_price;
        if notional > ctx.max_order_notional_usdt {
            return OrphanDecision::Close {
                reason: format!(
                    "notional={:.2} > max_order_notional={:.2}",
                    notional, ctx.max_order_notional_usdt
                ),
                stage: OrphanStage::HardSafetyNotionalCap,
            };
        }
    }

    // ── Stage A4: scanner universe membership ─────────────────────────────
    // Empty slice = registry unavailable → skip check (fail-open).
    // 空切片 = 註冊表未接入 → 跳過檢查（fail-open）。
    if !ctx.active_symbols.is_empty()
        && !ctx.active_symbols.iter().any(|s| s == &pos.symbol)
    {
        return OrphanDecision::Close {
            reason: format!("symbol {} not in scanner active universe", pos.symbol),
            stage: OrphanStage::HardSafetyNotInUniverse,
        };
    }

    // ── Stage B1: edge-based lock-profit close ────────────────────────────
    // Phase 1 proxy for "no strategy wants this orphan": check if ANY known
    // strategy has positive shrunk edge on this symbol. If NONE do AND we're
    // currently in profit, lock it.
    // Phase 1 代理：檢查是否任一已知策略在該幣種有正 shrunk 邊際。若全部無正邊際
    // 且當前為正盈利 → 鎖利。
    if ctx.edge_estimates.is_populated() {
        let any_positive = KNOWN_STRATEGY_NAMES.iter().any(|strat| {
            ctx.edge_estimates
                .get(strat, &pos.symbol)
                .map(|bps| bps > 0.0)
                .unwrap_or(false)
        });
        if !any_positive && pos.unrealised_pnl > 0.0 {
            return OrphanDecision::Close {
                reason: format!(
                    "no positive-edge strategy on {}; locking unrealised pnl={:.4}",
                    pos.symbol, pos.unrealised_pnl
                ),
                stage: OrphanStage::SoftLockProfit,
            };
        }
    }

    // ── Stage C: adopt deferred → conservative close (Phase 1 default) ────
    // Real adopt requires synthetic StrategyId + paper_state injection +
    // StopManager binding + Strategist agent (G-1 R-02). All absent in Phase 1.
    // 真 Adopt 需 synthetic StrategyId + paper_state 注入 + StopManager 綁定 +
    // Strategist agent (G-1 R-02)。Phase 1 全未具備 → 保守平倉。
    OrphanDecision::Close {
        reason: format!(
            "ambiguous orphan {}|{} qty={} (Phase 2 adopt path deferred; conservative close per 原則 #6)",
            pos.symbol, pos.side, pos.size
        ),
        stage: OrphanStage::SoftConservative,
    }
}

/// Dispatch CloseSymbol for an orphan using hint fields (position not in
/// paper_state). Returns true if command was enqueued.
/// 使用 hint 字段為孤兒分發 CloseSymbol（倉位不在 paper_state 中）。
/// 命令成功入列返回 true。
pub fn dispatch_orphan_close(
    decision: &OrphanDecision,
    pos: &PositionInfo,
    cmd_tx: &UnboundedSender<PipelineCommand>,
) -> bool {
    let (reason, stage_str) = match decision {
        OrphanDecision::Close { reason, stage } => (reason.clone(), stage.as_str()),
        OrphanDecision::Adopt { reason } => (reason.clone(), "adopt_phase2"),
    };
    let hint_is_long = Some(pos.side == "Buy");
    let hint_qty = Some(pos.size);
    match cmd_tx.send(PipelineCommand::CloseSymbol {
        symbol: pos.symbol.clone(),
        hint_is_long,
        hint_qty,
    }) {
        Ok(_) => {
            info!(
                symbol = %pos.symbol,
                side = %pos.side,
                qty = pos.size,
                stage = stage_str,
                reason = %reason,
                "orphan_handled close dispatched / 孤兒處理→平倉已發送"
            );
            true
        }
        Err(e) => {
            warn!(
                error = %e,
                symbol = %pos.symbol,
                stage = stage_str,
                "failed to dispatch orphan close / 孤兒平倉發送失敗"
            );
            false
        }
    }
}

/// Fire-and-forget audit row for orphan_handled events.
/// orphan_handled 事件的 V014 審計（fire-and-forget）。
pub fn spawn_orphan_audit(
    audit_pool: &Option<sqlx::PgPool>,
    decision: &OrphanDecision,
    pos: &PositionInfo,
    engine_label: &str,
) {
    let Some(pool) = audit_pool.clone() else { return };
    let (action_str, stage_str, reason) = match decision {
        OrphanDecision::Close { reason, stage } => ("close", stage.as_str(), reason.clone()),
        OrphanDecision::Adopt { reason } => ("adopt", "phase2", reason.clone()),
    };
    let payload = serde_json::json!({
        "action": action_str,
        "stage": stage_str,
        "symbol": pos.symbol,
        "side": pos.side,
        "qty": pos.size,
        "mark_price": pos.mark_price,
        "liq_price": pos.liq_price,
        "unrealised_pnl": pos.unrealised_pnl,
        "reason": reason,
        "engine": engine_label,
    });
    let engine_owned = engine_label.to_string();
    let ts_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0);
    tokio::spawn(async move {
        if let Err(e) = sqlx::query(
            "INSERT INTO observability.engine_events
             (ts_ms, event_type, source, config_name, old_version, new_version, payload)
             VALUES ($1, $2, $3, $4, NULL, NULL, $5)",
        )
        .bind(ts_ms)
        .bind("orphan_handled")
        .bind("position_reconciler")
        .bind("reconciler.orphan_handler")
        .bind(&payload)
        .execute(&pool)
        .await
        {
            warn!(
                error = %e, engine = %engine_owned,
                "orphan_handled audit insert failed / 孤兒處理審計寫入失敗"
            );
        }
    });
}

/// Return true and stamp the dedup map if this (symbol|side) was NOT
/// dispatched within the last `ORPHAN_CLOSE_DEDUP_MS`. Returns false (skip)
/// if a recent close was already dispatched.
/// 若此 (symbol|side) 在最近 ORPHAN_CLOSE_DEDUP_MS 內未分發過平倉，
/// 返回 true 並戳記去重表。否則返回 false（跳過）。
pub fn check_and_stamp_dedup(
    state: &mut ReconcilerState,
    key: &str,
    now_ms: u64,
) -> bool {
    // Garbage-collect expired entries opportunistically (cheap even at 100s of keys).
    // 順便清理過期記錄（即使幾百個 key 也很輕）。
    state
        .pending_orphan_closes
        .retain(|_, stamped| now_ms.saturating_sub(*stamped) < ORPHAN_CLOSE_DEDUP_MS);

    if let Some(&last) = state.pending_orphan_closes.get(key) {
        if now_ms.saturating_sub(last) < ORPHAN_CLOSE_DEDUP_MS {
            return false;
        }
    }
    state.pending_orphan_closes.insert(key.to_string(), now_ms);
    true
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════
#[cfg(test)]
mod tests {
    use super::*;
    use crate::edge_estimates::EdgeEstimates;

    fn make_pos(
        symbol: &str,
        side: &str,
        size: f64,
        mark: f64,
        liq: f64,
        pnl: f64,
    ) -> PositionInfo {
        PositionInfo {
            symbol: symbol.to_string(),
            side: side.to_string(),
            size,
            avg_price: mark,
            mark_price: mark,
            unrealised_pnl: pnl,
            leverage: 10.0,
            liq_price: liq,
            take_profit: 0.0,
            stop_loss: 0.0,
            position_idx: 0,
            trailing_stop: 0.0,
            position_value: size * mark,
            cum_realised_pnl: 0.0,
            created_time: String::new(),
            updated_time: String::new(),
        }
    }

    fn empty_estimates() -> EdgeEstimates {
        EdgeEstimates::empty()
    }

    /// Stage A1: liq_price within 10% of mark → HardSafetyLiqClose.
    /// Stage A1：liq_price 距 mark < 10% → 硬安全平倉。
    #[test]
    fn stage_a1_liq_distance_triggers_close() {
        let pos = make_pos("BTCUSDT", "Buy", 0.01, 100.0, 95.0, 0.0); // 5% away
        let ee = empty_estimates();
        let active: Vec<String> = vec!["BTCUSDT".into()];
        let ctx = OrphanContext {
            pos_info: &pos,
            current_level: RiskLevel::Normal,
            max_order_notional_usdt: 0.0,
            active_symbols: &active,
            edge_estimates: &ee,
        };
        let decision = handle_orphan(&ctx);
        match decision {
            OrphanDecision::Close { stage, .. } => assert_eq!(stage, OrphanStage::HardSafetyLiqClose),
            other => panic!("expected HardSafetyLiqClose, got {:?}", other),
        }
    }

    /// Stage A1 passes when liq_price is safely far from mark (> 10%).
    /// Stage A1 通過：liq_price 遠離 mark（> 10%）。
    #[test]
    fn stage_a1_safe_liq_does_not_trigger() {
        let pos = make_pos("BTCUSDT", "Buy", 0.01, 100.0, 80.0, 0.0); // 20% away
        let ee = empty_estimates();
        let active: Vec<String> = vec!["BTCUSDT".into()];
        let ctx = OrphanContext {
            pos_info: &pos,
            current_level: RiskLevel::Normal,
            max_order_notional_usdt: 0.0,
            active_symbols: &active,
            edge_estimates: &ee,
        };
        let decision = handle_orphan(&ctx);
        // Should fall through to SoftConservative (Phase 1 default), NOT HardSafetyLiqClose.
        // 應落到 SoftConservative（Phase 1 默認），而非 HardSafetyLiqClose。
        match decision {
            OrphanDecision::Close { stage, .. } => assert_eq!(stage, OrphanStage::SoftConservative),
            other => panic!("expected SoftConservative, got {:?}", other),
        }
    }

    /// Stage A2: RiskLevel ≥ CircuitBreaker → HardSafetyCircuitBreaker.
    /// Stage A2：風控級別 ≥ CB → 硬安全 CB 平倉。
    #[test]
    fn stage_a2_circuit_breaker_triggers() {
        let pos = make_pos("BTCUSDT", "Buy", 0.01, 100.0, 80.0, 0.0);
        let ee = empty_estimates();
        let active: Vec<String> = vec!["BTCUSDT".into()];
        let ctx = OrphanContext {
            pos_info: &pos,
            current_level: RiskLevel::CircuitBreaker,
            max_order_notional_usdt: 0.0,
            active_symbols: &active,
            edge_estimates: &ee,
        };
        let decision = handle_orphan(&ctx);
        match decision {
            OrphanDecision::Close { stage, .. } => assert_eq!(stage, OrphanStage::HardSafetyCircuitBreaker),
            other => panic!("expected HardSafetyCircuitBreaker, got {:?}", other),
        }
    }

    /// Stage A3: notional > max_order_notional_usdt → HardSafetyNotionalCap.
    /// Stage A3：名目超限 → 硬安全名目上限平倉。
    #[test]
    fn stage_a3_notional_cap_triggers() {
        // 0.1 BTC × $50_000 = $5000; cap = $1000 → triggers
        let pos = make_pos("BTCUSDT", "Buy", 0.1, 50_000.0, 40_000.0, 0.0);
        let ee = empty_estimates();
        let active: Vec<String> = vec!["BTCUSDT".into()];
        let ctx = OrphanContext {
            pos_info: &pos,
            current_level: RiskLevel::Normal,
            max_order_notional_usdt: 1_000.0,
            active_symbols: &active,
            edge_estimates: &ee,
        };
        let decision = handle_orphan(&ctx);
        match decision {
            OrphanDecision::Close { stage, .. } => assert_eq!(stage, OrphanStage::HardSafetyNotionalCap),
            other => panic!("expected HardSafetyNotionalCap, got {:?}", other),
        }
    }

    /// Stage A3: max_order_notional_usdt = 0 → disabled (fall through).
    /// Stage A3：max_order_notional_usdt = 0 → 停用（穿過）。
    #[test]
    fn stage_a3_notional_cap_zero_disabled() {
        let pos = make_pos("BTCUSDT", "Buy", 0.1, 50_000.0, 40_000.0, 0.0);
        let ee = empty_estimates();
        let active: Vec<String> = vec!["BTCUSDT".into()];
        let ctx = OrphanContext {
            pos_info: &pos,
            current_level: RiskLevel::Normal,
            max_order_notional_usdt: 0.0,
            active_symbols: &active,
            edge_estimates: &ee,
        };
        let decision = handle_orphan(&ctx);
        match decision {
            OrphanDecision::Close { stage, .. } => assert_eq!(stage, OrphanStage::SoftConservative),
            other => panic!("expected SoftConservative, got {:?}", other),
        }
    }

    /// Stage A4: symbol not in active universe → HardSafetyNotInUniverse.
    /// Stage A4：不在活躍字集合 → 硬安全宇集外平倉。
    #[test]
    fn stage_a4_not_in_universe_triggers() {
        let pos = make_pos("SHIBUSDT", "Buy", 1_000_000.0, 0.00001, 0.0, 0.0);
        let ee = empty_estimates();
        let active: Vec<String> = vec!["BTCUSDT".into(), "ETHUSDT".into()];
        let ctx = OrphanContext {
            pos_info: &pos,
            current_level: RiskLevel::Normal,
            max_order_notional_usdt: 0.0,
            active_symbols: &active,
            edge_estimates: &ee,
        };
        let decision = handle_orphan(&ctx);
        match decision {
            OrphanDecision::Close { stage, .. } => assert_eq!(stage, OrphanStage::HardSafetyNotInUniverse),
            other => panic!("expected HardSafetyNotInUniverse, got {:?}", other),
        }
    }

    /// Stage A4: empty active_symbols slice → skip check (fail-open).
    /// Stage A4：空活躍集合 → 跳過（fail-open）。
    #[test]
    fn stage_a4_empty_universe_skipped() {
        let pos = make_pos("BTCUSDT", "Buy", 0.01, 100.0, 80.0, 0.0);
        let ee = empty_estimates();
        let active: Vec<String> = vec![];
        let ctx = OrphanContext {
            pos_info: &pos,
            current_level: RiskLevel::Normal,
            max_order_notional_usdt: 0.0,
            active_symbols: &active,
            edge_estimates: &ee,
        };
        let decision = handle_orphan(&ctx);
        match decision {
            OrphanDecision::Close { stage, .. } => assert_eq!(stage, OrphanStage::SoftConservative),
            other => panic!("expected SoftConservative, got {:?}", other),
        }
    }

    /// Stage B1: populated estimates, no positive edge, unrealised_pnl > 0 → SoftLockProfit.
    /// Stage B1：有估計、無正邊際、未實現盈利 > 0 → 軟鎖利平倉。
    #[test]
    fn stage_b1_lock_profit_triggers() {
        let pos = make_pos("BTCUSDT", "Buy", 0.01, 100.0, 80.0, 5.0);
        let json = r#"{
            "_meta": {"grand_mean_bps": 0.0},
            "ma_crossover::BTCUSDT": {"shrunk_bps": -2.5, "n": 50},
            "bb_reversion::BTCUSDT": {"shrunk_bps": -1.0, "n": 30}
        }"#;
        let ee = EdgeEstimates::load_from_str(json).unwrap();
        let active: Vec<String> = vec!["BTCUSDT".into()];
        let ctx = OrphanContext {
            pos_info: &pos,
            current_level: RiskLevel::Normal,
            max_order_notional_usdt: 0.0,
            active_symbols: &active,
            edge_estimates: &ee,
        };
        let decision = handle_orphan(&ctx);
        match decision {
            OrphanDecision::Close { stage, .. } => assert_eq!(stage, OrphanStage::SoftLockProfit),
            other => panic!("expected SoftLockProfit, got {:?}", other),
        }
    }

    /// Stage B1: at least one positive edge → do NOT trigger lock-profit.
    /// Stage B1：至少一個正邊際 → 不觸發鎖利。
    #[test]
    fn stage_b1_positive_edge_skips_lock_profit() {
        let pos = make_pos("BTCUSDT", "Buy", 0.01, 100.0, 80.0, 5.0);
        let json = r#"{
            "_meta": {"grand_mean_bps": 0.0},
            "ma_crossover::BTCUSDT": {"shrunk_bps": 3.5, "n": 50}
        }"#;
        let ee = EdgeEstimates::load_from_str(json).unwrap();
        let active: Vec<String> = vec!["BTCUSDT".into()];
        let ctx = OrphanContext {
            pos_info: &pos,
            current_level: RiskLevel::Normal,
            max_order_notional_usdt: 0.0,
            active_symbols: &active,
            edge_estimates: &ee,
        };
        let decision = handle_orphan(&ctx);
        // Falls through to SoftConservative (no adopt infrastructure yet).
        // 穿過到 SoftConservative（尚無 adopt 基建）。
        match decision {
            OrphanDecision::Close { stage, .. } => assert_eq!(stage, OrphanStage::SoftConservative),
            other => panic!("expected SoftConservative, got {:?}", other),
        }
    }

    /// Default path: all Stage A pass, edges non-negative OR pnl ≤ 0 → SoftConservative.
    /// 默認路徑：所有 Stage A 通過、無 lock_profit → 保守平倉。
    #[test]
    fn default_path_soft_conservative() {
        let pos = make_pos("BTCUSDT", "Buy", 0.01, 100.0, 80.0, -3.0); // losing
        let ee = empty_estimates();
        let active: Vec<String> = vec!["BTCUSDT".into()];
        let ctx = OrphanContext {
            pos_info: &pos,
            current_level: RiskLevel::Normal,
            max_order_notional_usdt: 0.0,
            active_symbols: &active,
            edge_estimates: &ee,
        };
        let decision = handle_orphan(&ctx);
        match decision {
            OrphanDecision::Close { stage, .. } => assert_eq!(stage, OrphanStage::SoftConservative),
            other => panic!("expected SoftConservative, got {:?}", other),
        }
    }

    /// Stage A ordering: liq distance takes precedence over CB (fired first).
    /// Stage A 順序：liq 距離優先於 CB（先觸發）。
    #[test]
    fn stage_a_ordering_liq_first() {
        let pos = make_pos("BTCUSDT", "Buy", 0.01, 100.0, 95.0, 0.0); // A1 hits
        let ee = empty_estimates();
        let active: Vec<String> = vec!["BTCUSDT".into()];
        let ctx = OrphanContext {
            pos_info: &pos,
            current_level: RiskLevel::CircuitBreaker, // A2 would also hit
            max_order_notional_usdt: 0.0,
            active_symbols: &active,
            edge_estimates: &ee,
        };
        let decision = handle_orphan(&ctx);
        match decision {
            OrphanDecision::Close { stage, .. } => assert_eq!(stage, OrphanStage::HardSafetyLiqClose),
            other => panic!("expected HardSafetyLiqClose, got {:?}", other),
        }
    }

    /// Dedup: first call returns true, second within window returns false.
    /// 去重：首次 true，窗口內再次 false。
    #[test]
    fn dedup_suppresses_repeat() {
        let mut state = ReconcilerState::new();
        let key = "BTCUSDT|Buy";
        let t0 = 1_000_000u64;
        assert!(check_and_stamp_dedup(&mut state, key, t0));
        // Immediate retry — blocked.
        assert!(!check_and_stamp_dedup(&mut state, key, t0 + 1_000));
        // Still within window.
        assert!(!check_and_stamp_dedup(&mut state, key, t0 + ORPHAN_CLOSE_DEDUP_MS - 1));
        // After window — allowed again.
        assert!(check_and_stamp_dedup(&mut state, key, t0 + ORPHAN_CLOSE_DEDUP_MS + 1));
    }

    /// Dedup keys are independent across symbols.
    /// 不同 key 去重互不影響。
    #[test]
    fn dedup_per_key_independent() {
        let mut state = ReconcilerState::new();
        let t0 = 1_000_000u64;
        assert!(check_and_stamp_dedup(&mut state, "BTCUSDT|Buy", t0));
        assert!(check_and_stamp_dedup(&mut state, "ETHUSDT|Sell", t0 + 100));
        assert!(!check_and_stamp_dedup(&mut state, "BTCUSDT|Buy", t0 + 200));
    }
}
