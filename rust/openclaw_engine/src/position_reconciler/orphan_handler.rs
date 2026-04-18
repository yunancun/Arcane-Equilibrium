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
//!     A4. REMOVED — scanner universe gating moved to tick_pipeline (SCANNER-GATE)
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
use std::collections::HashMap;
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

/// ORPHAN-ADOPT-1 Phase 2A: strategy label written to `PaperPosition.owner_strategy`
/// for positions adopted from external orphan detection. Intentionally NOT in
/// `KNOWN_STRATEGY_NAMES` — B1/B2 edge probes skip it, preventing self-reference
/// on an already-adopted position (which has no independent edge estimate anyway).
/// ORPHAN-ADOPT-1 Phase 2A：外部孤兒 adopt 後寫入 PaperPosition.owner_strategy 的
/// 合成策略標籤。刻意不加入 KNOWN_STRATEGY_NAMES，避免 B1/B2 edge 掃描對已 adopt
/// 倉位自我引用（它本身並沒有獨立 edge 樣本）。
pub const ORPHAN_ADOPTED_STRATEGY: &str = "orphan_adopted";

/// DUST-EVICTION-GAP-1 / P1-8 (2026-04-17): label written to `PaperPosition.owner_strategy`
/// when a bybit_sync eviction candidate has `qty * ref_price < spec.min_notional`. The
/// position is retained in paper_state (NOT removed + NOT close-dispatched) because the
/// exchange would reject any close with retCode=170124. Kept out of KNOWN_STRATEGY_NAMES so
/// no strategy opens follow-on entries on them. Listed in `SYNTHETIC_OWNER_LABELS`, so every
/// subsequent tick runs `retriage_synthetic_owner` — the moment price moves above
/// `min_notional` AND symbol is in the scanner universe, ownership auto-flips to the first
/// KNOWN_STRATEGY_NAMES entry; if it's not in the universe when that happens, a CloseSymbol
/// is auto-dispatched. No restart and no operator action required (§原則 #11).
/// Silent drift guard: engine state continues to know the position exists — the reconciler's
/// position mirror matches exchange, preventing the "engine thinks flat, exchange has dust"
/// divergence that would violate §憲法 #9.
/// DUST-EVICTION-GAP-1 / P1-8：bybit_sync 驅逐候選倉位名義值低於交易所最小值時的合成
/// 策略標籤。保留在 paper_state（不移除、不派平倉），因交易所會以 retCode=170124 拒單。
/// 刻意不入 KNOWN_STRATEGY_NAMES，但列於 SYNTHETIC_OWNER_LABELS，每 tick 走
/// retriage_synthetic_owner：價格回升到 ≥ min_notional 且在 scanner universe 即自動升級；
/// 不在 universe 則自動派 CloseSymbol。不需 operator 介入或重啟（§原則 #11）。
pub const DUST_FROZEN_STRATEGY: &str = "orphan_frozen";

/// Stage that drove the decision (for audit). Phase 2A emits Adopt via `AdoptPositiveEdge`.
/// `AdoptDeferredPhase2` retained as a dead-but-reserved taxonomy for back-compat with
/// external analytics that previously consumed the Phase 1 audit events.
/// 決策來源階段（用於 audit）。Phase 2A 透過 AdoptPositiveEdge 輸出 Adopt。
/// AdoptDeferredPhase2 保留為 dead 變體以相容舊的 audit 分類。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OrphanStage {
    HardSafetyLiqClose,
    HardSafetyCircuitBreaker,
    HardSafetyNotionalCap,
    HardSafetyNotInUniverse,
    SoftLockProfit,
    SoftConservative,
    AdoptDeferredPhase2,
    /// Phase 2A: at least one known strategy has positive shrunk edge on symbol.
    /// Phase 2A：至少一個已知策略在此 symbol 有正 shrunk edge。
    AdoptPositiveEdge,
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
            OrphanStage::AdoptPositiveEdge => "adopt_positive_edge",
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
    /// Phase 2A: dispatch AdoptOrphan to inject the exchange-reported position
    /// into PaperState as `owner_strategy = "orphan_adopted"`. Stage guarantees
    /// at least one known strategy has positive shrunk edge on the symbol;
    /// `triggering_strategy` captures which one, so downstream analytics can
    /// attribute adopted PnL back to the edge that authorised the adoption
    /// without parsing `reason` text.
    /// Phase 2A：分發 AdoptOrphan，注入 PaperState（owner_strategy="orphan_adopted"）。
    /// triggering_strategy 紀錄觸發正邊際的策略名，供下游 PnL 歸因使用。
    Adopt {
        reason: String,
        stage: OrphanStage,
        triggering_strategy: String,
    },
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
    /// ORPHAN-ADOPT-1 FUP: per-engine mirror of PaperState positions
    /// (`symbol → is_long`). Read before classification to suppress the
    /// reconciler's own fresh-fill false-positive Orphans: if the engine
    /// already owns the candidate `(symbol, is_long)`, the position is NOT
    /// an orphan — it is the engine's in-flight open/accumulate that the
    /// 30 s baseline simply hasn't caught up to yet. Default handle (empty
    /// map) disables the check — reconciler falls back to Phase 1 closure
    /// semantics, matching pre-fix behavior.
    /// ORPHAN-ADOPT-1 FUP：對應引擎的 PaperState 持倉鏡像（`symbol → is_long`）。
    /// 分類前先讀鏡像抑制「引擎自家剛開倉」的假 Orphan：若鏡像已持有
    /// `(symbol, is_long)`，代表那是引擎自己剛下的單，只是 30s baseline
    /// 還沒追上，不是外部孤兒。預設空 handle 停用本檢查，行為回退到
    /// Phase 1 的平倉語義。
    pub engine_positions_mirror: Arc<parking_lot::RwLock<HashMap<String, bool>>>,
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
            reason: format!(
                "global risk level={:?} (≥ CircuitBreaker)",
                ctx.current_level
            ),
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

    // ── Stage A4: REMOVED (SCANNER-GATE fix) ───────────────────────────────
    // Scanner rotation ≠ orphan. Orphan = restart-leftover only. New opens are
    // now gated at the tick_pipeline level (SymbolRegistry check before intent
    // dispatch), so a position that the engine chose to open should never be
    // force-closed just because the scanner rotated the symbol out. The enum
    // variant `HardSafetyNotInUniverse` is kept for DB backward compat.
    // 掃描器輪替 ≠ 孤兒。孤兒僅指重啟後遺留的舊倉位。新開倉已在 tick_pipeline
    // 層由 SymbolRegistry 門控，引擎主動開的倉不應因掃描器輪替而被強平。
    // enum 變體保留以相容歷史 DB 資料。

    // ── Stage B: edge-based branch (Phase 2A)─────────────────────────────
    // B2 (Phase 2A): if ANY known strategy has positive shrunk edge on this
    //   symbol → Adopt. Edge is a per-symbol metric, NOT a directional
    //   signal — exchange-reported side is preserved. Once injected into
    //   PaperState, StopManager bounds downside (global StopConfig applies).
    // B1 (legacy lock-profit): if no strategy has positive edge AND position
    //   is currently in profit → close to lock unrealised PnL. Falls through
    //   to Stage C only when unprofitable with no positive-edge strategy.
    // B2（Phase 2A）：任一已知策略在此 symbol 有正 shrunk edge → Adopt。
    //   邊際是 per-symbol 指標（非方向訊號），保留交易所回報方向；注入
    //   PaperState 後由 StopManager 接管下行風險（全局 StopConfig 套用）。
    // B1（既有鎖利）：全部無正邊際且當前正盈利 → 鎖利平倉。無正邊際且虧損
    //   時才落到 Stage C 保守處理。
    if ctx.edge_estimates.is_populated() {
        let winning = KNOWN_STRATEGY_NAMES.iter().find(|strat| {
            ctx.edge_estimates
                .get(strat, &pos.symbol)
                .map(|bps| bps > 0.0)
                .unwrap_or(false)
        });
        if let Some(strat) = winning {
            // Safe: predicate above already proved Some(bps) && bps > 0.0.
            // 安全：上面謂詞已確認 Some(bps) && bps > 0.0。
            let bps = ctx.edge_estimates.get(strat, &pos.symbol).unwrap_or(0.0);
            return OrphanDecision::Adopt {
                reason: format!(
                    "positive-edge strategy {} on {} shrunk_bps={:.2}; adopting exchange position",
                    strat, pos.symbol, bps
                ),
                stage: OrphanStage::AdoptPositiveEdge,
                triggering_strategy: (*strat).to_string(),
            };
        }
        if pos.unrealised_pnl > 0.0 {
            return OrphanDecision::Close {
                reason: format!(
                    "no positive-edge strategy on {}; locking unrealised pnl={:.4}",
                    pos.symbol, pos.unrealised_pnl
                ),
                stage: OrphanStage::SoftLockProfit,
            };
        }
    }

    // ── Stage C: conservative close (unprofitable / no edge data) ─────────
    // No positive-edge strategy AND position not profitable (or edge table
    // empty). 原則 #6 失敗默認收縮 → SoftConservative close.
    // 無正邊際且未盈利（或 edge 表未填充）→ 原則 #6 失敗默認收縮 → 保守平倉。
    OrphanDecision::Close {
        reason: format!(
            "ambiguous orphan {}|{} qty={} (no positive-edge strategy & not in profit; conservative close per 原則 #6)",
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
        // Adopt decisions must go through `dispatch_orphan_adopt` (T4).
        // Returning false here (not Err) lets the caller drop the verdict
        // cleanly rather than re-closing the position by mistake.
        // Adopt 決策必須走 dispatch_orphan_adopt（T4）。此處回 false（非 Err）
        // 讓呼叫端乾淨捨棄 verdict，避免誤平倉。
        OrphanDecision::Adopt { reason, stage, .. } => {
            warn!(
                symbol = %pos.symbol,
                stage = stage.as_str(),
                reason = %reason,
                "dispatch_orphan_close invoked with Adopt decision — routing mismatch / dispatch_orphan_close 收到 Adopt 決策（路由錯誤）"
            );
            return false;
        }
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

/// ORPHAN-ADOPT-1 Phase 2A: dispatch `PipelineCommand::AdoptOrphan` so the
/// event_consumer injects the exchange-reported orphan into `paper_state`
/// as `owner_strategy = "orphan_adopted"`. Caller must have already resolved
/// the decision to `OrphanDecision::Adopt`; non-Adopt decisions return false
/// without touching the channel.
/// Uses `pos.avg_price` as the entry_price (Bybit's per-position average cost)
/// — adopt must not fabricate a synthetic entry; StopManager uses this as the
/// reference for trailing / hard-stop calculations.
/// ORPHAN-ADOPT-1 Phase 2A：派發 PipelineCommand::AdoptOrphan，讓 event_consumer
/// 將交易所孤兒注入 paper_state（owner_strategy="orphan_adopted"）。entry_price
/// 取 pos.avg_price（Bybit 每倉平均成本）— 不得偽造合成進場價。
pub fn dispatch_orphan_adopt(
    decision: &OrphanDecision,
    pos: &PositionInfo,
    cmd_tx: &UnboundedSender<PipelineCommand>,
) -> bool {
    let (reason, stage_str) = match decision {
        OrphanDecision::Adopt { reason, stage, .. } => (reason.clone(), stage.as_str()),
        OrphanDecision::Close { reason, stage } => {
            warn!(
                symbol = %pos.symbol,
                stage = stage.as_str(),
                reason = %reason,
                "dispatch_orphan_adopt invoked with Close decision — routing mismatch / dispatch_orphan_adopt 收到 Close 決策（路由錯誤）"
            );
            return false;
        }
    };
    let is_long = pos.side == "Buy";
    let ts_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0);
    let owner_strategy = match decision {
        OrphanDecision::Adopt {
            triggering_strategy,
            ..
        } => Some(triggering_strategy.clone()),
        _ => None,
    };
    match cmd_tx.send(PipelineCommand::AdoptOrphan {
        symbol: pos.symbol.clone(),
        is_long,
        qty: pos.size,
        entry_price: pos.avg_price,
        ts_ms,
        owner_strategy,
    }) {
        Ok(_) => {
            info!(
                symbol = %pos.symbol,
                side = %pos.side,
                qty = pos.size,
                entry = pos.avg_price,
                stage = stage_str,
                reason = %reason,
                "orphan_handled adopt dispatched / 孤兒處理→接管已發送"
            );
            true
        }
        Err(e) => {
            warn!(
                error = %e,
                symbol = %pos.symbol,
                stage = stage_str,
                "failed to dispatch orphan adopt / 孤兒接管發送失敗"
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
    let Some(pool) = audit_pool.clone() else {
        return;
    };
    // ORPHAN-ADOPT-1 Phase 2A audit schema:
    //   owner_strategy      — label written to PaperPosition.owner_strategy.
    //                         Some("orphan_adopted") for Adopt, None for Close.
    //   triggering_strategy — positive-edge strategy that authorised the Adopt
    //                         (downstream PnL attribution). None for Close.
    // ORPHAN-ADOPT-1 Phase 2A audit 欄位：
    //   owner_strategy → PaperPosition.owner_strategy 標籤（Adopt 時為 "orphan_adopted"）
    //   triggering_strategy → 授權 adopt 的正邊際策略（Close 為 null）
    let (action_str, stage_str, reason, owner_strategy, triggering_strategy) = match decision {
        OrphanDecision::Close { reason, stage } => {
            ("close", stage.as_str(), reason.clone(), None, None)
        }
        OrphanDecision::Adopt {
            reason,
            stage,
            triggering_strategy,
        } => (
            "adopt",
            stage.as_str(),
            reason.clone(),
            Some(ORPHAN_ADOPTED_STRATEGY),
            Some(triggering_strategy.clone()),
        ),
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
        "owner_strategy": owner_strategy,
        "triggering_strategy": triggering_strategy,
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
pub fn check_and_stamp_dedup(state: &mut ReconcilerState, key: &str, now_ms: u64) -> bool {
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
            OrphanDecision::Close { stage, .. } => {
                assert_eq!(stage, OrphanStage::HardSafetyLiqClose)
            }
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
            OrphanDecision::Close { stage, .. } => {
                assert_eq!(stage, OrphanStage::HardSafetyCircuitBreaker)
            }
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
            OrphanDecision::Close { stage, .. } => {
                assert_eq!(stage, OrphanStage::HardSafetyNotionalCap)
            }
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

    /// Stage A4 REMOVED: symbol not in universe no longer triggers close.
    /// Orphan = restart-leftover only; scanner rotation handled upstream.
    /// Stage A4 已移除：非活躍交易對不再觸發平倉。孤兒僅指重啟遺留；掃描器輪替由上游處理。
    #[test]
    fn stage_a4_removed_not_in_universe_falls_through() {
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
            OrphanDecision::Close { stage, .. } => assert_eq!(stage, OrphanStage::SoftConservative),
            other => panic!("expected SoftConservative (A4 removed), got {:?}", other),
        }
    }

    /// A4 removal: empty active_symbols still passes through to SoftConservative.
    /// A4 移除：空活躍集合仍落到 SoftConservative。
    #[test]
    fn stage_a4_empty_universe_still_passes() {
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

    // ════════════════════════════════════════════════════════════════════════
    // ORPHAN-ADOPT-1 Phase 2A test matrix / Phase 2A 測試矩陣
    // ════════════════════════════════════════════════════════════════════════

    /// Phase 2A #1: Buy-side orphan + ma_crossover positive edge → Adopt.
    /// Triggering strategy is captured; stage is `AdoptPositiveEdge`; direction
    /// is inherited from the exchange-reported side (Buy → is_long would be true).
    /// Phase 2A #1：Buy 孤兒 + 正邊際 → Adopt；保留交易所方向；
    /// triggering_strategy 紀錄為 ma_crossover。
    #[test]
    fn stage_b2_positive_edge_adopts_long() {
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
        match decision {
            OrphanDecision::Adopt {
                stage,
                triggering_strategy,
                ..
            } => {
                assert_eq!(stage, OrphanStage::AdoptPositiveEdge);
                assert_eq!(triggering_strategy, "ma_crossover");
            }
            other => panic!("expected Adopt(AdoptPositiveEdge), got {:?}", other),
        }
    }

    /// Phase 2A #2: Sell-side orphan + positive edge → Adopt (same decision,
    /// edge sign ≠ direction; edge is a per-symbol strategy metric).
    /// Phase 2A #2：Sell 孤兒 + 正邊際 → Adopt（邊際是 per-symbol 指標，非方向訊號）。
    #[test]
    fn stage_b2_positive_edge_adopts_short() {
        let pos = make_pos("BTCUSDT", "Sell", 0.01, 100.0, 120.0, 5.0);
        let json = r#"{
            "_meta": {"grand_mean_bps": 0.0},
            "bb_reversion::BTCUSDT": {"shrunk_bps": 4.2, "n": 100}
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
            OrphanDecision::Adopt {
                stage,
                triggering_strategy,
                ..
            } => {
                assert_eq!(stage, OrphanStage::AdoptPositiveEdge);
                assert_eq!(triggering_strategy, "bb_reversion");
            }
            other => panic!("expected Adopt(AdoptPositiveEdge), got {:?}", other),
        }
    }

    /// Phase 2A #3: Multiple strategies populated but NONE with positive edge
    /// AND position is losing → falls through to SoftConservative (not Adopt,
    /// not lock-profit). Proves B2 is strictly-greater-than-zero gated.
    /// Phase 2A #3：多策略都無正邊際且虧損 → 落到 SoftConservative
    /// （非 Adopt 也非 lock-profit）。驗證 B2 嚴格 > 0。
    #[test]
    fn stage_b2_no_positive_edge_losing_falls_through() {
        let pos = make_pos("BTCUSDT", "Buy", 0.01, 100.0, 80.0, -3.0);
        let json = r#"{
            "_meta": {"grand_mean_bps": 0.0},
            "ma_crossover::BTCUSDT": {"shrunk_bps": -2.5, "n": 50},
            "bb_reversion::BTCUSDT": {"shrunk_bps": 0.0, "n": 30}
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
            OrphanDecision::Close { stage, .. } => assert_eq!(stage, OrphanStage::SoftConservative),
            other => panic!("expected SoftConservative, got {:?}", other),
        }
    }

    /// Phase 2A #4: Multiple positive-edge strategies → first found (per
    /// `KNOWN_STRATEGY_NAMES` order) wins. Guarantees deterministic
    /// triggering_strategy selection so downstream attribution is stable.
    /// Phase 2A #4：多策略皆正邊際 → 按 KNOWN_STRATEGY_NAMES 順序取第一個，
    /// 確保 triggering_strategy 選擇具有決定性。
    #[test]
    fn stage_b2_first_positive_edge_wins() {
        let pos = make_pos("BTCUSDT", "Buy", 0.01, 100.0, 80.0, 0.0);
        let json = r#"{
            "_meta": {"grand_mean_bps": 0.0},
            "bb_reversion::BTCUSDT": {"shrunk_bps": 7.0, "n": 100},
            "ma_crossover::BTCUSDT": {"shrunk_bps": 3.0, "n": 50},
            "grid_trading::BTCUSDT": {"shrunk_bps": 5.0, "n": 40}
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
            OrphanDecision::Adopt {
                triggering_strategy,
                ..
            } => {
                // KNOWN_STRATEGY_NAMES = [ma_crossover, bb_reversion, bb_breakout,
                // grid_trading, funding_arb]; `ma_crossover` wins even though
                // `bb_reversion` has the larger edge.
                assert_eq!(triggering_strategy, "ma_crossover");
            }
            other => panic!("expected Adopt, got {:?}", other),
        }
    }

    /// Phase 2A #5: Stage A (liq distance) MUST fire even when B2 would adopt
    /// — safety checks strictly precede adopt-path decisions.
    /// Phase 2A #5：Stage A（liq 距離）即使 B2 本會 Adopt 也必須優先觸發。
    #[test]
    fn stage_a_precedence_over_b2_adopt() {
        // liq within 5% of mark → A1 hits; positive edge would otherwise adopt.
        // liq 距 mark 5% → A1 觸發；否則正邊際會 Adopt。
        let pos = make_pos("BTCUSDT", "Buy", 0.01, 100.0, 95.0, 5.0);
        let json = r#"{
            "_meta": {"grand_mean_bps": 0.0},
            "ma_crossover::BTCUSDT": {"shrunk_bps": 10.0, "n": 200}
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
            OrphanDecision::Close { stage, .. } => {
                assert_eq!(stage, OrphanStage::HardSafetyLiqClose)
            }
            other => panic!("expected HardSafetyLiqClose, got {:?}", other),
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
            OrphanDecision::Close { stage, .. } => {
                assert_eq!(stage, OrphanStage::HardSafetyLiqClose)
            }
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
        assert!(!check_and_stamp_dedup(
            &mut state,
            key,
            t0 + ORPHAN_CLOSE_DEDUP_MS - 1
        ));
        // After window — allowed again.
        assert!(check_and_stamp_dedup(
            &mut state,
            key,
            t0 + ORPHAN_CLOSE_DEDUP_MS + 1
        ));
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
