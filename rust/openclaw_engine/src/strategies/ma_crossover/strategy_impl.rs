//! MaCrossover — `Strategy` trait impl (on_tick + lifecycle hooks).
//! MaCrossover — `Strategy` trait 實作（on_tick + 生命週期鉤子）。
//!
//! MODULE_NOTE (EN): Split out of `strategies/ma_crossover.rs` by E5-P2-4c
//!   (2026-04-23) to honour CLAUDE.md §九 1200-line hard cap. Contains the
//!   `impl Strategy for MaCrossover` block: `on_tick` main 4-step loop
//!   (ADX gate → crossover signal → persistence → confluence), `on_rejection`
//!   (RC-04 rollback), `on_external_close`, and the JSON param adapters
//!   (`update_params_json` / `get_params_json` / `param_ranges_json`) plus
//!   `conf_scale` / `set_conf_scale`.
//! MODULE_NOTE (中)：E5-P2-4c（2026-04-23）由 `strategies/ma_crossover.rs` 拆出，
//!   依 §九 1200 行硬上限。本檔含 `impl Strategy for MaCrossover`：`on_tick` 主 4
//!   步流程（ADX 門 → 交叉信號 → 持續性 → 匯流）、`on_rejection`（RC-04 回滾）、
//!   `on_external_close`，以及 JSON 參數適配器（`update_params_json` /
//!   `get_params_json` / `param_ranges_json`）加 `conf_scale` / `set_conf_scale`。

use crate::intent_processor::OrderIntent;
use crate::strategies::{Strategy, StrategyAction, StrategyParams};
use crate::tick_pipeline::TickContext;
use openclaw_core::alpha_surface::{AlphaSourceTag, AlphaSurface};

use super::{confluence, MaCrossover, MaCrossoverParams};

impl Strategy for MaCrossover {
    fn name(&self) -> &str {
        "ma_crossover"
    }
    fn is_active(&self) -> bool {
        self.active
    }
    fn set_active(&mut self, active: bool) {
        self.active = active;
    }

    /// W-AUDIT-8a Phase A spec §3 Phase A Deliverable #3：
    /// `ma_crossover`：`[Ta1m]`（純 1m kline TA + ADX + persistence）。
    fn declared_alpha_sources(&self) -> &[AlphaSourceTag] {
        const TAGS: &[AlphaSourceTag] = &[AlphaSourceTag::Ta1m];
        TAGS
    }

    /// RC-04 + W7-3 Option B：拒絕時的 1-tick 防衛（cross-strategy desync hot loop 修復）。
    ///
    /// 原 RC-04 行為：回滾該幣種的 position 與 last_trade_ms 至 mutation 前狀態。
    ///
    /// W7-3 Option B 補丁（PA audit `2026-05-10--p1_ma_crossover_duplicate_intent_audit.md`
    /// §6 Option B）：當 reason 是 router gate 1.5 `duplicate_position` 時，
    /// 解析「已存在的方向」並把 self.positions 同步成該方向，**不**走 prev_position
    /// rollback。這樣下一 tick 進入 `Some(is_long)` exit 分支而非 None entry 分支，
    /// 立即終結 INXUSDT 11:34 那種 5 分鐘 2319 次 reject 的 hot loop。
    ///
    /// cooldown 不 rollback 也是設計：reject 觸發時 entry 已寫過 last_trade_ms，
    /// 保留它讓下個 tick 必走 cooldown gate，多一層 hot loop 防護。
    /// （治本是 W-AUDIT-8a Option A — strategy 端查 paper_state；此補丁僅應急。）
    fn on_rejection(&mut self, intent: &OrderIntent, reason: &str) {
        let sym = &intent.symbol;

        // W7-3 Option B：duplicate_position 識別 + 立即 sync self.positions。
        // reason 字串契約見 rejection_coding.rs:147-152 —
        // 格式 "duplicate_position: {symbol} already {LONG|SHORT} {qty}"。
        if reason.contains("duplicate_position") {
            let existing_is_long = if reason.contains("already LONG") {
                Some(true)
            } else if reason.contains("already SHORT") {
                Some(false)
            } else {
                None
            };

            if let Some(is_long) = existing_is_long {
                // 同步 paper_state 真實方向；下個 tick 進 exit 分支不再撞 gate 1.5。
                self.positions.insert(sym.clone(), is_long);
                // **不** rollback cooldown：保留 entry tick 寫入的 last_trade_ms，
                // 配合 cooldown gate 多擋一輪。
                tracing::debug!(
                    symbol = %sym,
                    existing_is_long,
                    "ma_crossover.on_rejection: duplicate_position 1-tick defense — \
                     synced self.positions to paper_state direction (W7-3 Option B)"
                );
                return;
            }
            // reason 含 duplicate_position 但無 already LONG/SHORT 子串 → 字串契約破裂，
            // fallback 走原 RC-04 rollback 並標 warn 提醒 contract drift。
            tracing::warn!(
                symbol = %sym,
                reason = %reason,
                "ma_crossover.on_rejection: duplicate_position reason missing \
                 'already LONG/SHORT' marker; falling back to RC-04 rollback"
            );
        }

        // 原 RC-04 rollback：non-duplicate_position rejection 走此路徑。
        if let Some(prev) = self.prev_position.get(sym) {
            match prev {
                Some(b) => {
                    self.positions.insert(sym.clone(), *b);
                }
                None => {
                    self.positions.remove(sym);
                }
            }
        }
        if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
            if ts == 0 {
                // 哨兵 0 → 變更前為未見；清除以還原。
                self.cooldown.clear(sym);
            } else {
                self.cooldown.record_signal(sym, ts);
            }
        }
    }

    /// Reset internal position for the closed symbol (risk-stop).
    /// 外部平倉（風控止損）時重設該幣種的內部倉位狀態。
    fn on_external_close(&mut self, symbol: &str) {
        self.positions.remove(symbol);
        self.persistence.clear(symbol);
        self.exit_persistence.clear(symbol);
    }

    fn on_tick(
        &mut self,
        ctx: &TickContext<'_>,
        _surface: &AlphaSurface<'_>,
    ) -> Vec<StrategyAction> {
        let ind = match ctx.indicators {
            Some(i) => i,
            None => return vec![],
        };
        // Snapshot pre-mutation last_ms for RC-04 (sentinel 0 when unseen, as before).
        // 為 RC-04 快照變更前的 last_ms（未見時沿用哨兵 0）。
        let last_ms = self.cooldown.last_ms(ctx.symbol).unwrap_or(0);
        // A2: trend-adaptive cooldown — extends cooldown in strong-trend markets
        // to prevent re-entering into a continuing trend that just closed us out.
        // E1-P0-2: Delegated to shared `TrendCooldown`; we push the effective
        // duration in each tick so semantics match `ts < last_ms + effective`
        // exactly (unseen symbol still → cooled via TrendCooldown's None branch).
        // A2：趨勢自適應冷卻；E1-P0-2 委派給 TrendCooldown，語意完全一致。
        let effective_cooldown = self.compute_trend_adjusted_cooldown(ctx.indicators);
        self.cooldown.set_duration(effective_cooldown);
        if !self.cooldown.is_cooled_down(ctx.symbol, ctx.timestamp_ms) {
            return vec![];
        }

        // ADX trend-strength gate (existing).
        // ADX 趨勢強度門檻（原有）。
        let adx = ind.adx.as_ref().map(|a| a.adx).unwrap_or(0.0);
        if adx < self.adx_threshold {
            return vec![];
        }

        // RC-02: Update per-symbol higher-TF proxy from sma_50 (every tick for EMA warmup).
        // RC-02: 從 sma_50 更新該幣種的較高時間框架替代指標（每個 tick 更新以暖機 EMA）。
        if let Some(sma_50) = ind.sma_50 {
            self.update_higher_tf(ctx.symbol, sma_50);
        }

        let fast = match ind.kama.as_ref() {
            Some(k) => k.kama,
            None => {
                // QC-#2: Log KAMA fallback — strategy silently degrades to SMA vs SMA (never crosses).
                // QC-#2：記錄 KAMA 退化 — 策略靜默退化為 SMA vs SMA（永不交叉）。
                tracing::debug!(
                    symbol = %ctx.symbol,
                    "KAMA unavailable, falling back to SMA(20) / KAMA 不可用，退化為 SMA(20)"
                );
                ind.sma_20.unwrap_or(0.0)
            }
        };
        let slow = ind.sma_20.unwrap_or(0.0);
        if fast == 0.0 || slow == 0.0 {
            return vec![];
        }

        let mut intents = Vec::new();

        // RC-04: Snapshot per-symbol state before any mutation for rejection rollback.
        // RC-04：在任何變更前快照該幣種狀態，供拒絕回滾使用。
        self.prev_position.insert(
            ctx.symbol.to_string(),
            self.positions.get(ctx.symbol).copied(),
        );
        self.prev_last_trade_ms
            .insert(ctx.symbol.to_string(), last_ms);

        match self.positions.get(ctx.symbol).copied() {
            None => {
                // Entry path — apply RC-01 regime filter + RC-02 higher-TF confirmation.
                // 入場路徑 — 套用 RC-01 狀態過濾 + RC-02 較高時間框架確認。
                if !self.regime_allows_entry(ctx) {
                    return vec![];
                }

                // G-SR-1 A1: Determine signal direction for persistence check.
                // G-SR-1 A1：確定信號方向供持續性檢查。
                let signal: Option<bool> = if fast > slow {
                    Some(true)
                } else if fast < slow {
                    Some(false)
                } else {
                    None
                };
                if signal.is_some()
                    && !self.trend_snr_allows_entry(fast, slow, ctx.price, ctx.indicators)
                {
                    self.persistence.clear(ctx.symbol);
                    return vec![];
                }

                // A1: Time-based persistence filter — signal must hold ≥ min_persistence_ms.
                // A1：基於時間的持續性過濾 — 信號必須持續 ≥ min_persistence_ms。
                if !self.persistence.check(
                    ctx.symbol,
                    signal,
                    ctx.timestamp_ms,
                    self.min_persistence_ms,
                    false, // not a close signal / 非平倉信號
                ) {
                    return vec![];
                }

                // A2: Confluence scoring — primary signal is mandatory gate.
                // A2：匯流評分 — 主信號是強制門控。
                let score = confluence::compute_score(
                    &self.confluence_config,
                    signal.is_some(),
                    ind.adx.as_ref().map(|a| a.adx),
                    ind.hurst
                        .as_ref()
                        .map(|h| h.regime.as_str())
                        .unwrap_or("uncertain"),
                    ind.volume_ratio,
                    ind.rsi_14,
                    signal.unwrap_or(true),
                );
                let qty_pct = confluence::score_to_qty_pct(score, &self.confluence_config);
                if qty_pct <= 0.0 {
                    return vec![];
                }
                let qty = self.default_qty * qty_pct;
                // R3-9: Min notional guard / 最小名義值守衛
                if qty * ctx.price < self.min_notional_usd {
                    return vec![];
                }

                let regime = ind.hurst.as_ref().map(|h| h.regime.as_str());
                let entry_conf = self.compute_entry_confidence(adx, regime);
                // R3-2: Reuse confidence field for confluence score.
                // R3-2：復用 confidence 欄位存放匯流分數。
                let conf_with_score = match score {
                    Some(s) if s > 0.0 => s / 65.0, // normalize to [0,1]
                    _ => entry_conf,
                };

                if let Some(is_long) = signal {
                    if !self.higher_tf_allows_entry(ctx.symbol, is_long) {
                        return vec![];
                    }
                    // EDGE-P3-1 A6: snapshot confluence + persistence elapsed at
                    // decision time so predictor sees the same numbers the gate
                    // used. Clamp score to f32 for feature vector.
                    // EDGE-P3-1 A6：抓取決策時的 confluence/persistence 供預測器。
                    let confluence_score = score.map(|s| s as f32);
                    let persistence_elapsed_ms =
                        self.persistence.elapsed_ms(ctx.symbol, ctx.timestamp_ms);
                    let maybe_intent = self.make_intent_with_qty(
                        ctx,
                        is_long,
                        conf_with_score,
                        qty,
                        confluence_score,
                        persistence_elapsed_ms,
                    );
                    if let Some(intent) = maybe_intent {
                        intents.push(StrategyAction::Open(intent));
                        self.positions.insert(ctx.symbol.to_string(), is_long);
                        self.cooldown.record_signal(ctx.symbol, ctx.timestamp_ms);
                    }
                }
            }
            Some(is_long) => {
                // Exit path — RC-01/RC-02 filters do NOT apply to exits.
                // KAMA crosses back through SMA20 = trend reversal (Kaufman).
                // Exit urgency > entry selectivity: no ADX/regime/higher-TF filter on exit.
                // 出場路徑 — KAMA 回穿 SMA20 = 趨勢反轉。出場不套用入場過濾器。
                //
                // A1: instead of firing Close on the first reverse tick, require
                // the reverse signal to persist for `min_persistence_ms × (1 − ER)`.
                // Choppy markets (ER→0) demand confirmation; clean trends (ER→1)
                // exit nearly instantly. Hard stop / trailing / fast_track paths
                // operate independently and remain unaffected.
                // A1：反向交叉不再單 tick 出場，以 KAMA ER 縮放的持續性窗口過濾假反轉。
                let reverse_signal: Option<bool> = if is_long && fast < slow {
                    Some(false) // bearish reverse for long position
                } else if !is_long && fast > slow {
                    Some(true) // bullish reverse for short position
                } else {
                    None // aligned with position, no reverse signal
                };

                // ER-scaled exit persistence window. KAMA-less snapshots fall
                // back to ER=0.5 (mid) rather than 0 to avoid pinning exit at
                // the entry-level threshold on cold starts.
                // ER 縮放的出場持續性窗口；無 KAMA 時退回 ER=0.5。
                let er = ind.kama.as_ref().map(|k| k.efficiency_ratio).unwrap_or(0.5);
                let exit_persistence_ms = self.compute_exit_persistence_ms(er);

                let persisted = self.exit_persistence.check(
                    ctx.symbol,
                    reverse_signal,
                    ctx.timestamp_ms,
                    exit_persistence_ms,
                    false, // not a close-exempt path — we WANT persistence
                );

                if persisted && reverse_signal.is_some() {
                    let exit_conf = self.compute_exit_confidence(adx);
                    intents.push(StrategyAction::Close {
                        symbol: ctx.symbol.to_string(),
                        confidence: exit_conf,
                        reason: "ma_reverse_cross".into(),
                    });
                    self.positions.remove(ctx.symbol);
                    self.cooldown.record_signal(ctx.symbol, ctx.timestamp_ms);
                    self.exit_persistence.clear(ctx.symbol);
                }
            }
        }
        intents
    }

    fn update_params_json(&mut self, json: &str) -> Result<(), String> {
        let params: MaCrossoverParams = serde_json::from_str(json).map_err(|e| e.to_string())?;
        self.update_params(params)
    }

    fn get_params_json(&self) -> String {
        serde_json::to_string(&self.get_params()).unwrap_or_default()
    }

    fn param_ranges_json(&self) -> String {
        serde_json::to_string(&MaCrossoverParams::param_ranges()).unwrap_or_default()
    }

    fn conf_scale(&self) -> f64 {
        self.conf_scale
    }

    fn set_conf_scale(&mut self, scale: f64) {
        self.conf_scale = scale.clamp(0.0, 2.0);
    }
}
