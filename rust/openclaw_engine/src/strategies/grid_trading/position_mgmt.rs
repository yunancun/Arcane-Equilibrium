//! Grid Trading position management — inventory lifecycle + trend-adaptive cooldown.
//! Grid Trading 持倉管理 — 庫存生命週期 + 趨勢自適應冷卻。
//!
//! MODULE_NOTE (EN): Split out of `strategies/grid_trading.rs` by GRID-TRADING-MOD-SPLIT-1
//!   (2026-04-23) to honour CLAUDE.md §九's 1200-line hard cap (pre-split 1729 lines).
//!   Contains per-symbol position bookkeeping used by the `Strategy` trait
//!   callbacks: external-close inventory reset (risk-stop path), strategy-emitted
//!   Close confirm / skip rollback (FIX-C preserves `last_trade_ms` so the 30s
//!   reject backoff stays active), RC-04 rejection rollback + M-2 per-symbol
//!   backoff arming, and the G-SR-1 A3 trend-adjusted cooldown computation
//!   (ADX + Hurst → 1x..6x multiplier). All logic / signatures / field
//!   mutations preserved byte-identical to pre-split.
//! MODULE_NOTE (中)：GRID-TRADING-MOD-SPLIT-1（2026-04-23）由
//!   `strategies/grid_trading.rs` 拆出以遵守 CLAUDE.md §九 1200 行硬上限
//!   （拆前 1729 行）。本檔包含 `Strategy` trait callback 使用的逐幣種倉位
//!   記帳：外部平倉（風控止損路徑）的 net_inventory 重設、策略發出 Close
//!   的 confirm / skip 回滾（FIX-C 保留 `last_trade_ms` 使 30s reject 退避
//!   仍生效）、RC-04 拒絕回滾 + M-2 逐幣種退避設定，以及 G-SR-1 A3 趨勢調整
//!   冷卻計算（ADX + Hurst → 1x..6x 倍率）。所有邏輯 / 簽名 / 欄位變更
//!   與拆前逐字節相同。

use openclaw_core::indicators::IndicatorSnapshot;
use tracing::{info, warn};

use super::GridTrading;
use crate::intent_processor::OrderIntent;
use crate::strategies::maker_rejection::MakerRejectionCategory;

impl GridTrading {
    /// G-SR-1 A3: Compute trend-adjusted cooldown for a symbol.
    /// In trending markets (high ADX + high Hurst), cooldown scales up 1x→6x
    /// to reduce grid frequency and limit inventory drift losses.
    /// G-SR-1 A3：計算趨勢調整後的冷卻時間。
    /// 趨勢市場（高 ADX + 高 Hurst）中，冷卻從 1x 增至 6x，降低網格頻率。
    pub(super) fn compute_trend_adjusted_cooldown(&self, snap: Option<&IndicatorSnapshot>) -> u64 {
        let Some(ind) = snap else {
            return self.cooldown_ms;
        };

        let adx_val = ind.adx.as_ref().map(|a| a.adx).unwrap_or(0.0);
        let hurst_val = ind.hurst.as_ref().map(|h| h.hurst).unwrap_or(0.5);

        // ADX factor: adx_low→adx_high maps to 0→1
        let adx_range = self.adx_high_threshold - self.adx_low_threshold;
        let adx_factor = if adx_range > 0.0 {
            ((adx_val - self.adx_low_threshold) / adx_range).clamp(0.0, 1.0)
        } else {
            0.0
        };

        // Hurst factor: 0.50→0.75 maps to 0→1
        let hurst_factor = ((hurst_val - 0.50) / 0.25).clamp(0.0, 1.0);

        // Blend 60/40 (ADX reacts faster than Hurst) / 混合 60/40（ADX 反應快於 Hurst）
        let trend_score = 0.6 * adx_factor + 0.4 * hurst_factor;

        // Multiplier range: 1x to (1 + max_cooldown_boost)x / 倍率範圍：1x 到 (1+max_cooldown_boost)x
        let multiplier = 1.0 + (trend_score * self.max_cooldown_boost);

        (self.cooldown_ms as f64 * multiplier) as u64
    }

    /// Record a confirmed grid close and arm a no-new-entry cooldown if the
    /// symbol is churning. Close/risk reduction paths remain enabled.
    /// 記錄已確認 grid 平倉；若短窗內反覆平倉，對該 symbol 暫停新入場。
    /// 平倉 / 降風險路徑不受影響。
    pub(super) fn record_churn_close_impl(&mut self, symbol: &str) {
        if !self.churn_breaker_enabled {
            return;
        }
        let close_ts = self.last_trade_ms.get(symbol).copied().unwrap_or(0);
        if close_ts == 0 {
            return;
        }
        let window_start = close_ts.saturating_sub(self.churn_breaker_window_ms);
        let close_times = self
            .churn_breaker_close_times
            .entry(symbol.to_string())
            .or_default();
        close_times.retain(|&ts| ts >= window_start);
        close_times.push(close_ts);

        if close_times.len() >= self.churn_breaker_close_count {
            let until = close_ts.saturating_add(self.churn_breaker_cooldown_ms);
            self.churn_breaker_until_ms
                .insert(symbol.to_string(), until);
            close_times.clear();
            warn!(
                strategy = "grid_trading",
                %symbol,
                close_ts,
                cooldown_until_ms = until,
                window_ms = self.churn_breaker_window_ms,
                close_count = self.churn_breaker_close_count,
                "grid churn breaker armed: suppressing new entries \
                 / grid churn breaker 已觸發：暫停新入場"
            );
        }
    }

    /// Reset per-symbol net_inventory on external close (risk-stop) to prevent desync.
    /// 外部平倉（風控止損）時重設該幣種 net_inventory，防止與 paper_state 脫鉤。
    pub(super) fn on_external_close_impl(&mut self, symbol: &str) {
        let inv = self.net_inventory.get(symbol).copied().unwrap_or(0.0);
        if inv != 0.0 {
            info!(strategy = "grid_trading", %symbol, prev_inventory = %inv,
                  "external close: resetting net_inventory / 外部平倉：重設淨庫存");
            self.net_inventory.insert(symbol.to_string(), 0.0);
        }
    }

    /// Pipeline confirmed a strategy-emitted Close was executed — adjust per-symbol inventory.
    /// 管線確認策略平倉已執行 — 調整該幣種庫存。
    pub(super) fn on_close_confirmed_impl(&mut self, symbol: &str) {
        let prev_inv = self.prev_inventory.get(symbol).copied().unwrap_or(0.0);
        let new_inventory = {
            let cur_inv = self.net_inventory.entry(symbol.to_string()).or_insert(0.0);
            if prev_inv < 0.0 {
                *cur_inv += self.qty_per_grid;
            } else if prev_inv > 0.0 {
                *cur_inv -= self.qty_per_grid;
            }
            *cur_inv
        };
        self.record_churn_close_impl(symbol);
        info!(strategy = "grid_trading", %symbol, new_inventory = %new_inventory,
              "close confirmed: inventory adjusted / 平倉確認：庫存已調整");
    }

    /// Pipeline skipped a strategy-emitted Close (no position found) — roll back cross state.
    /// FIX-C: Do NOT roll back last_trade_ms. The emit timestamp is kept as-is so the
    /// existing 30s cooldown (REJECT_BACKOFF_MS) stays active and prevents tight-loop
    /// re-emission on the next tick. Previously, rolling back last_trade_ms removed the
    /// cooldown entirely, causing grid to re-emit the same Close intent every single tick
    /// (observed: hundreds of `close_skipped:no_position_grid_close_short` per second during CB).
    /// 管線跳過策略平倉（未找到倉位）— 回滾交叉狀態。
    /// FIX-C：不回滾 last_trade_ms。保留發送時間戳使現有 30s 冷卻繼續有效，防止下一 tick 立即重發。
    /// 舊行為：回滾 last_trade_ms → 冷卻失效 → 每 tick 重發 Close（CB 期間每秒數百條 close_skipped）。
    pub(super) fn on_close_skipped_impl(&mut self, symbol: &str) {
        if let Some(prev) = self.prev_cross_idx.get(symbol) {
            match prev {
                Some(idx) => {
                    self.last_cross_idx.insert(symbol.to_string(), *idx);
                }
                None => {
                    self.last_cross_idx.remove(symbol);
                }
            }
        }
        // NOTE: last_trade_ms intentionally NOT rolled back here (FIX-C).
        // last_trade_ms 此處刻意不回滾（FIX-C）。
        info!(strategy = "grid_trading", %symbol, "close skipped: cross state rolled back, trade_ms preserved / 平倉跳過：交叉狀態已回滾，trade_ms 保留");
    }

    /// RC-04: Revert per-symbol net_inventory, last_cross_idx, last_trade_ms on rejection.
    /// M-2: Also arm a per-symbol rejection backoff using the emit timestamp captured
    /// in `last_trade_ms` BEFORE the rollback overwrites it. This breaks tight retry
    /// loops on persistent guardian/cost_gate rejections without losing state coherence.
    /// RC-04：拒絕時回滾該幣種的 net_inventory、last_cross_idx、last_trade_ms。
    /// M-2：同時使用回滾前 `last_trade_ms` 中捕獲的發送時間戳設定該幣種拒絕退避。
    /// 在不破壞狀態一致性的前提下打破持續性 guardian/cost_gate 拒絕的緊湊重試迴圈。
    pub(super) fn on_rejection_impl(&mut self, intent: &OrderIntent, _reason: &str) {
        let sym = &intent.symbol;

        // M-2: Capture emit timestamp before rollback overwrites it.
        // M-2：在回滾覆蓋之前捕獲發送時間戳。
        // BB-MF-3 (2026-05-16)：governance pipeline rejection 屬 entry-side
        // 路徑（per_strategy_new_entry_rejection 只觸發於 entry intent），
        // 寫入 entry cooldown map，不影響同 symbol 的 close emission。
        if let Some(&emit_ts) = self.last_trade_ms.get(sym) {
            if emit_ts > 0 {
                self.reject_cooldown_entry_until_ms
                    .insert(sym.to_string(), emit_ts + self.reject_backoff_ms);
            }
        }

        if let Some(prev) = self.prev_cross_idx.get(sym) {
            match prev {
                Some(idx) => {
                    self.last_cross_idx.insert(sym.to_string(), *idx);
                }
                None => {
                    self.last_cross_idx.remove(sym);
                }
            }
        }
        if let Some(&inv) = self.prev_inventory.get(sym) {
            self.net_inventory.insert(sym.to_string(), inv);
        }
        if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
            if ts == 0 {
                self.last_trade_ms.remove(sym);
            } else {
                self.last_trade_ms.insert(sym.to_string(), ts);
            }
        }
    }

    /// EDGE-P2-3 Phase 1B-3 (FIX-G7-09C-PHASE2-WIRE-1B3): exchange rejected
    /// our PostOnly maker **entry** — arm a per-symbol entry cooldown.
    /// BB-MF-3 (2026-05-16)：寫入 `reject_cooldown_entry_until_ms`，僅阻擋
    /// `signal.rs` 的 Open emission；同 symbol 的 Close emission 由獨立的
    /// `reject_cooldown_close_until_ms` 控制（pre-Phase 2a Demo prereq）。
    /// 預期接線：本 callback 仍由「PostOnly maker entry」路徑觸發；close
    /// path 啟用 maker-first 後（Phase 1b 主軸）改透過 `arm_close_cooldown`
    /// 寫入 close map，不重用本路徑。category 目前僅紀錄供鑑識，未來可對
    /// `TooManyPending` 給更長 multiplier。Saturating add 防 i64 溢出。
    pub(super) fn on_post_only_rejected_impl(
        &mut self,
        symbol: &str,
        ts_ms: i64,
        category: &MakerRejectionCategory,
    ) {
        // Saturating add against i64 overflow; cooldown_ms always > 0.
        // Saturating add 防 i64 溢出。
        let cooldown_until_i64 = ts_ms.saturating_add(self.reject_cooldown_ms as i64);
        // Cast to u64 for storage; values < 0 (impossible here) fall to 0
        // — entry path 後續即略過 cooldown 分支。
        let cooldown_until_ms = cooldown_until_i64.max(0) as u64;
        self.reject_cooldown_entry_until_ms
            .insert(symbol.to_string(), cooldown_until_ms);
        warn!(
            strategy = "grid_trading",
            %symbol,
            ts_ms,
            cooldown_ms = self.reject_cooldown_ms,
            cooldown_until_ms,
            category = %category.label(),
            side = "entry",
            "post-only entry rejected by exchange — armed entry reject cooldown \
             / 交易所拒絕 PostOnly entry — 已設 entry 冷卻"
        );
    }

    /// EDGE-P2-3 Phase 1b BB-MF-3 (2026-05-16) — close-side maker rejection
    /// cooldown 寫入 helper。對應 spec v1.2 §6.1 dispatch table：
    ///   - `MakerRejectionCategory::PostOnlyCross` → no-op（spec §5.3 Race C：
    ///     價已過則直接 market，不進 close cooldown）
    ///   - `MakerRejectionCategory::TooManyPending` → 5min 固定（spec §5.4
    ///     dynamic backoff per-symbol exp + global cascade 屬獨立工作項，
    ///     本 prereq 不實作）
    ///   - 其他類別（FokCancel / SelfCancel / Other） → 1min default
    /// 寫入 `reject_cooldown_close_until_ms`，下游 close path 的 maker-first
    /// gate 在 Phase 1b 主軸 IMPL 後生效（cooldown 期內走 market fallback）。
    /// **本 prereq commit 不接線生產 dispatcher**（commands.rs 仍 hard-coded
    /// market），由單元測試驗證 helper 行為與 entry/close 隔離不變式。
    /// Saturating add 防 i64 溢出。
    pub(super) fn arm_close_cooldown_impl(
        &mut self,
        symbol: &str,
        ts_ms: i64,
        category: &MakerRejectionCategory,
    ) {
        // 路由規則：依 category 決定 cooldown_ms（None = 不進 close cooldown）。
        let cooldown_ms: Option<u64> = match category {
            // spec §5.3 Race C：PostOnlyCross close 走 market，不 arm cooldown。
            MakerRejectionCategory::PostOnlyCross => None,
            // spec §6.1 + PM Wave 2b 任務：TooManyPending close → 5min 固定。
            MakerRejectionCategory::TooManyPending => {
                Some(super::CLOSE_REJECT_COOLDOWN_TOO_MANY_PENDING_MS)
            }
            // 其他 reject 類別走 1min default（per spec §6.1 表「其他 reject → 1min」）。
            MakerRejectionCategory::FokCancel
            | MakerRejectionCategory::SelfCancel
            | MakerRejectionCategory::Other(_) => Some(super::CLOSE_REJECT_COOLDOWN_DEFAULT_MS),
        };

        let Some(cooldown_ms) = cooldown_ms else {
            // PostOnlyCross close：不 arm cooldown，僅紀錄供 forensics。
            warn!(
                strategy = "grid_trading",
                %symbol,
                ts_ms,
                category = %category.label(),
                side = "close",
                "close postonly_cross — bypass cooldown, fall back to market \
                 / close 路徑 PostOnly 拒絕 — 跳過 cooldown，走 market"
            );
            return;
        };

        // Saturating add against i64 overflow / Saturating add 防 i64 溢出。
        let cooldown_until_i64 = ts_ms.saturating_add(cooldown_ms as i64);
        let cooldown_until_ms = cooldown_until_i64.max(0) as u64;
        self.reject_cooldown_close_until_ms
            .insert(symbol.to_string(), cooldown_until_ms);
        warn!(
            strategy = "grid_trading",
            %symbol,
            ts_ms,
            cooldown_ms,
            cooldown_until_ms,
            category = %category.label(),
            side = "close",
            "close maker rejected by exchange — armed close reject cooldown \
             / 交易所拒絕 close maker — 已設 close 冷卻"
        );
    }
}
