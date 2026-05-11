//! Grid Trading signal engine — per-tick cross detection + entry/close dispatch.
//! Grid Trading 信號引擎 — 每 tick 穿越偵測 + 入場/平倉派發。
//!
//! MODULE_NOTE (EN): Split out of `strategies/grid_trading.rs` by GRID-TRADING-MOD-SPLIT-1
//!   (2026-04-23) to honour CLAUDE.md §九's 1200-line hard cap (pre-split 1729 lines).
//!   Contains the main `on_tick_impl` dispatch: OU price-history append,
//!   lazy per-symbol grid init (template-bounds or adaptive ±10%), periodic
//!   health check + rebalance, OU spacing refresh cadence, EDGE-P1-1 trending
//!   hard-stop (ADX > 30 or Hurst regime = trending), M-2 per-symbol reject
//!   backoff, A3 trend-adjusted cooldown, nearest-level cross detection,
//!   RC-04 pre-mutation state snapshot, dynamic confidence scaling, EDGE-P2-3
//!   Phase 1a PostOnly vs Market entry resolution, and the BUY/SELL dispatch
//!   that emits `StrategyAction::Open` on a fresh cross or `StrategyAction::Close`
//!   when net_inventory would flip. All logic / signatures / ordering of
//!   mutations preserved byte-identical to pre-split.
//! MODULE_NOTE (中)：GRID-TRADING-MOD-SPLIT-1（2026-04-23）由
//!   `strategies/grid_trading.rs` 拆出以遵守 CLAUDE.md §九 1200 行硬上限
//!   （拆前 1729 行）。本檔包含主要的 `on_tick_impl` 派發：OU 價格歷史追加、
//!   逐幣種延遲初始化網格（模板邊界或自適應 ±10%）、週期健康檢查 + 再平衡、
//!   OU 間距刷新節奏、EDGE-P1-1 趨勢硬停（ADX > 30 或 Hurst regime = trending）、
//!   M-2 逐幣種拒絕退避、A3 趨勢調整冷卻、最近層級穿越偵測、RC-04 變更前
//!   狀態快照、動態信心縮放、EDGE-P2-3 Phase 1a PostOnly vs Market 入場決策，
//!   以及在新鮮穿越時發送 `StrategyAction::Open` 或在 net_inventory 會翻轉
//!   時發送 `StrategyAction::Close` 的 BUY/SELL 派發。所有邏輯 / 簽名 /
//!   變更順序與拆前逐字節相同。

use super::{compute_grid_confidence, GridHealth, GridTrading};
use crate::intent_processor::OrderIntent;
use crate::order_manager::TimeInForce;
use crate::strategies::common::{compute_post_only_price, MakerPriceInputs};
use crate::strategies::{grid_helpers, Strategy, StrategyAction};
use crate::tick_pipeline::TickContext;
use tracing::debug;

impl GridTrading {
    fn resolve_entry_order(
        &self,
        ctx: &TickContext<'_>,
        is_long: bool,
    ) -> Option<(String, Option<f64>, Option<TimeInForce>, Option<u64>)> {
        if !self.use_maker_entry {
            return Some(("market".to_string(), None, None, None));
        }
        let maker_inputs = MakerPriceInputs {
            last_price: ctx.price,
            best_bid: ctx.best_bid,
            best_ask: ctx.best_ask,
            tick_size: ctx.tick_size,
        };
        let price = compute_post_only_price(
            is_long,
            maker_inputs,
            self.maker_price_offset_bps,
            self.maker_price_buffer_ticks,
            "grid_trading",
            ctx.symbol,
        )?;
        Some((
            "limit".to_string(),
            Some(price),
            Some(TimeInForce::PostOnly),
            Some(self.maker_limit_timeout_ms),
        ))
    }

    pub(super) fn on_tick_impl(&mut self, ctx: &TickContext<'_>) -> Vec<StrategyAction> {
        let sym = ctx.symbol;

        // Per-symbol price history for OU model
        let history = self.price_history.entry(sym.to_string()).or_default();
        history.push(ctx.price);
        let ou_lookback = self.ou_lookback;
        if history.len() > ou_lookback * 2 {
            history.drain(0..ou_lookback);
        }

        // Auto-initialize per-symbol grid on first tick.
        // If template_bounds is set (from new(lower, upper)), use those bounds;
        // otherwise use adaptive ±10% of current price.
        // 每幣種首次 tick 初始化網格。有 template_bounds 用模板邊界，否則自適應 ±10%。
        if !self.grid_levels.contains_key(sym) && ctx.price > 0.0 {
            let (lower, upper) = match self.template_bounds {
                Some((lo, hi)) => (lo, hi),
                None => (
                    ctx.price * (1.0 - self.adaptive_range_pct),
                    ctx.price * (1.0 + self.adaptive_range_pct),
                ),
            };
            self.grid_levels.insert(
                sym.to_string(),
                grid_helpers::build_levels(lower, upper, self.grid_count, &self.spacing_mode),
            );
        }

        // Per-symbol health check every health_check_interval ticks.
        // 每幣種每 health_check_interval 個 tick 執行健康檢查。
        let ticks = self
            .ticks_since_health_check
            .entry(sym.to_string())
            .or_insert(0);
        *ticks += 1;
        if *ticks >= self.health_check_interval {
            *ticks = 0;
            let health = self.check_health(sym, ctx.price);
            if health == GridHealth::NeedsRebalance {
                self.rebalance(sym, ctx.price);
            }
        }

        // Periodically update per-symbol grid spacing via OU model
        // 定期通過 OU 模型更新該幣種網格間距
        let hist_len = self.price_history.get(sym).map(|h| h.len()).unwrap_or(0);
        // QC-H9: ou_update_interval configurable (was hardcoded 50)
        if hist_len > 0 && self.ou_update_interval > 0 && hist_len % self.ou_update_interval == 0 {
            self.update_ou_spacing(sym);
        }

        // EDGE-P1-1: Trending hard stop — suppress new grid entries in strong trends.
        // ADX > 30 or Hurst regime = "trending" → grid is structurally disadvantaged,
        // return empty (existing positions exit via normal risk/stop path).
        // EDGE-P1-1：趨勢硬停 — 強趨勢中暫停 grid 新開倉。
        // ADX > 30 或 Hurst regime = "trending" → grid 結構性不利，返回空。
        if let Some(ind) = ctx.indicators {
            let adx_val = ind.adx.as_ref().map(|a| a.adx).unwrap_or(0.0);
            let is_trending_regime = ind
                .hurst
                .as_ref()
                .map(|h| h.regime.as_str() == "trending")
                .unwrap_or(false);
            if adx_val > 30.0 || is_trending_regime {
                return vec![];
            }
        }

        // M-2: Honor per-symbol rejection backoff before any cross detection.
        // M-2：在任何 cross 偵測前遵守該幣種的拒絕退避。
        if let Some(&until) = self.reject_cooldown_until_ms.get(sym) {
            if ctx.timestamp_ms < until {
                return vec![];
            }
        }

        let last_ms = self.last_trade_ms.get(sym).copied().unwrap_or(0);
        // A3: Trend-adaptive cooldown — scales 1x→6x in trending markets.
        // A3：趨勢自適應冷卻 — 趨勢市場中 1x→6x 縮放。
        let effective_cooldown = self.compute_trend_adjusted_cooldown(ctx.indicators);
        if last_ms > 0 && ctx.timestamp_ms < last_ms + effective_cooldown {
            return vec![];
        }

        let idx = self.nearest_grid_idx(sym, ctx.price);
        if self.last_cross_idx.get(sym) == Some(&idx) {
            return vec![];
        }

        let prev_idx = self.last_cross_idx.get(sym).copied().unwrap_or(idx);
        let cur_inventory = self.net_inventory.get(sym).copied().unwrap_or(0.0);
        let is_down_cross = idx < prev_idx;
        let is_up_cross = idx > prev_idx;
        let would_open =
            (is_down_cross && cur_inventory >= 0.0) || (is_up_cross && cur_inventory <= 0.0);

        // OPTION-A-LITE-E1D (2026-05-11)：cross-strategy paper_state holding 防 race。
        // grid_trading 的 net_inventory 是 grid-level 累積（-2/-1/0/+1/+2 layered qty），
        // 必須保留本地累積（PA §7 BLOCKER #2：paper_state 不含 grid-level 資訊）。
        // 但若 paper_state 已有非 grid 來源（ma_crossover / bb_reversion / bb_breakout 等）
        // 開的倉位，grid 的 would_open 路徑會誤觸發新入場，導致 cross-strategy
        // mass scalp 混合（如 strategy=grid_trading + exit_reason=bb_mean_revert）。
        // 解法：在 entry path 偵測非 grid owner 倉位即 skip new entry；接受的合法 owner
        // 為 "grid_trading"（自己）/ "bybit_sync"（boot 後 sync）/ "orphan_adopted"
        // （PA §7 #5 watch：視為未知 owner，下次 fill 自然 re-attribute）。
        // 不動 net_inventory / on_external_close / on_fill 等任何 read/write 路徑。
        let cross_strategy_holds = ctx
            .position_state
            .filter(|p| {
                let owner = p.owner_strategy.as_str();
                owner != "grid_trading" && owner != "bybit_sync" && owner != "orphan_adopted"
            })
            .is_some();
        if would_open && cross_strategy_holds {
            // SAFETY 不變量：unwrap 安全 — cross_strategy_holds=true 蘊含
            // ctx.position_state.is_some() 為真（filter 對 None 永遠回 None）。
            let owner = ctx
                .position_state
                .map(|p| p.owner_strategy.as_str())
                .unwrap_or("unknown");
            debug!(
                strategy = "grid_trading",
                symbol = sym,
                owner = owner,
                "skip grid new entry: cross-strategy paper_state position holds \
                 / grid 新開倉跳過：cross-strategy paper_state 已持倉"
            );
            return vec![];
        }

        if would_open && self.blocked_symbols.contains(sym) {
            debug!(
                strategy = "grid_trading",
                symbol = sym,
                "grid new entry skipped: symbol in blocked_symbols / grid 新開倉跳過：symbol 在 blocked_symbols"
            );
            return vec![];
        }
        if would_open && self.churn_breaker_enabled {
            if let Some(until) = self.churn_breaker_until_ms.get(sym).copied() {
                if ctx.timestamp_ms < until {
                    debug!(
                        strategy = "grid_trading",
                        symbol = sym,
                        cooldown_until_ms = until,
                        "grid new entry skipped: churn breaker active \
                         / grid 新開倉跳過：churn breaker 生效"
                    );
                    return vec![];
                }
                self.churn_breaker_until_ms.remove(sym);
            }
        }
        let entry_order = if would_open {
            let is_long = is_down_cross;
            self.resolve_entry_order(ctx, is_long)
        } else {
            None
        };
        if would_open && entry_order.is_none() {
            return vec![];
        }

        // RC-04: Snapshot per-symbol state before any mutation for rejection rollback.
        // RC-04：在任何變更前快照該幣種狀態，供拒絕回滾使用。
        self.prev_cross_idx
            .insert(sym.to_string(), self.last_cross_idx.get(sym).copied());
        self.prev_inventory.insert(sym.to_string(), cur_inventory);
        self.prev_last_trade_ms.insert(sym.to_string(), last_ms);

        self.last_cross_idx.insert(sym.to_string(), idx);

        let mut intents = Vec::new();

        // Dynamic confidence: grid thrives in ranging + narrow BB, suffers in trending.
        // 動態信心：grid 在 ranging + 窄 BB 中表現好，trending 中表現差。
        // CONF-D: apply per-strategy scale.
        let conf = crate::tick_pipeline::on_tick_helpers::clamp_confidence(
            compute_grid_confidence(ctx.indicators) * self.conf_scale,
        );

        if idx < prev_idx {
            // Price crossed down → buy. If net_inventory < 0 (short), this closes short → Close.
            // Otherwise it's a new long → Open.
            // 價格下穿 → 買入。若 net_inventory < 0（空倉），為平空 → Close；否則新多 → Open。
            if cur_inventory < 0.0 {
                intents.push(StrategyAction::Close {
                    symbol: ctx.symbol.to_string(),
                    confidence: conf,
                    reason: "grid_close_short".into(),
                });
            } else {
                let (order_type, limit_price, time_in_force, maker_timeout_ms) =
                    entry_order.expect("entry_order precomputed for grid buy open");
                let intent = OrderIntent {
                    symbol: ctx.symbol.to_string(),
                    is_long: true,
                    qty: self.qty_per_grid,
                    confidence: conf,
                    strategy: self.name().into(),
                    order_type,
                    limit_price,
                    // Grid has no confluence/persistence; builder fills 0.0.
                    // Grid 無 confluence/persistence；builder 填 0。
                    confluence_score: None,
                    persistence_elapsed_ms: None,
                    time_in_force,
                    maker_timeout_ms,
                };
                intents.push(StrategyAction::Open(intent));
                *self.net_inventory.entry(sym.to_string()).or_insert(0.0) += self.qty_per_grid;
            }
            self.last_trade_ms.insert(sym.to_string(), ctx.timestamp_ms);
        } else if idx > prev_idx {
            // Price crossed up → sell. If net_inventory > 0 (long), this closes long → Close.
            // Otherwise it's a new short → Open.
            // 價格上穿 → 賣出。若 net_inventory > 0（多倉），為平多 → Close；否則新空 → Open。
            if cur_inventory > 0.0 {
                intents.push(StrategyAction::Close {
                    symbol: ctx.symbol.to_string(),
                    confidence: conf,
                    reason: "grid_close_long".into(),
                });
            } else {
                let (order_type, limit_price, time_in_force, maker_timeout_ms) =
                    entry_order.expect("entry_order precomputed for grid sell open");
                let intent = OrderIntent {
                    symbol: ctx.symbol.to_string(),
                    is_long: false,
                    qty: self.qty_per_grid,
                    confidence: conf,
                    strategy: self.name().into(),
                    order_type,
                    limit_price,
                    // Grid has no confluence/persistence; builder fills 0.0.
                    // Grid 無 confluence/persistence；builder 填 0。
                    confluence_score: None,
                    persistence_elapsed_ms: None,
                    time_in_force,
                    maker_timeout_ms,
                };
                intents.push(StrategyAction::Open(intent));
                *self.net_inventory.entry(sym.to_string()).or_insert(0.0) -= self.qty_per_grid;
            }
            self.last_trade_ms.insert(sym.to_string(), ctx.timestamp_ms);
        }

        intents
    }
}
