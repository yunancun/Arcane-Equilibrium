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
    ///
    /// Sprint N+1 W2 sub-task 2（per spec v1.2 §5.1.1）：宣告 `CrossAsset` tag
    /// 表示本策略消費 BtcLeadLagPanel（**paper-only shadow log，不影響 strategy
    /// decision**；fence Layer 1 由 step_4_5_dispatch 構造 surface 階段控制，
    /// demo / live_demo / live → surface.btc_lead_lag = None → 本策略 on_tick
    /// 內 `if let Some(panel) = surface.btc_lead_lag` 即 skip）。
    fn declared_alpha_sources(&self) -> &[AlphaSourceTag] {
        const TAGS: &[AlphaSourceTag] = &[AlphaSourceTag::Ta1m, AlphaSourceTag::CrossAsset];
        TAGS
    }

    /// P0 Option A-Lite (2026-05-11)：拒絕時的 cooldown rollback only。
    ///
    /// 改造前 W7-3 Option B + RC-04 行為：position 與 cooldown 雙 rollback +
    /// reason 字串解析 duplicate_position 1-tick 防衛。
    /// 改造後：positions 不再本地維護（`ctx.position_state` 為 SSoT）。
    /// 移除清單：
    /// - self.positions.insert/remove 全部移除（field 已消失）
    /// - prev_position rollback 移除（rollback 對象消失）
    /// - W7-3 Option B reason 解析移除（owner_strategy gate 已涵蓋）
    /// - cooldown rollback 保留（與 positions 解耦的獨立狀態，
    ///   prev_last_trade_ms 沿用「0 = 未見」哨兵語意）
    ///
    /// 詳：PA report `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_option_a_position_state_ssot_refactor.md` §4.1
    fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
        let sym = &intent.symbol;

        // Cooldown rollback：reject 時還原該幣種的 last_trade_ms 至 mutation 前狀態。
        // 變更前 last_ms == 0（未見）→ 清除；非 0 → 回寫原值。
        if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
            if ts == 0 {
                self.cooldown.clear(sym);
            } else {
                self.cooldown.record_signal(sym, ts);
            }
        }
    }

    /// P0 Option A-Lite (2026-05-11)：外部平倉時清理 signal-time persistence。
    /// 改造前：`self.positions.remove(symbol)` + `persistence` 清理。
    /// 改造後：positions 已不存在（field 移除）；persistence / exit_persistence
    /// 仍需清理 — signal-time state 與 position lifecycle 強耦合，無 SSoT 替代。
    fn on_external_close(&mut self, symbol: &str) {
        self.persistence.clear(symbol);
        self.exit_persistence.clear(symbol);
    }

    // P0 Option A-Lite (2026-05-11)：on_fill 化為 trait default no-op。
    // 改造前 W7-5 part 1：strategy.on_fill 同步 self.positions = intent.is_long。
    // 改造後：paper_state.apply_fill 是 SSoT 寫入點（callsite
    // `step_4_5_dispatch.rs:1026`）；strategy 端無需 mirror。下個 tick 走
    // ctx.position_state（`paper_state.get_position(symbol)`）讀。
    // fn on_fill 不再 override，使用 Strategy trait default no-op。

    // P0 Option A-Lite (2026-05-11)：import_positions 化為 trait default no-op。
    // 改造前 W7-5 part 2：bootstrap 從 paper_state 重建 self.positions。
    // 改造後：self.positions 已不存在；bootstrap 後第一個 tick 自然從
    // ctx.position_state 讀。cold-start desync 風險改由 on_tick 內
    // owner_strategy gate 涵蓋（任何 cross-strategy 倉位持有都 skip entry，
    // 不再撞 router gate 1.5 形成 hot loop）。
    // fn import_positions 不再 override，使用 Strategy trait default no-op。

    fn on_tick(
        &mut self,
        ctx: &TickContext<'_>,
        surface: &AlphaSurface<'_>,
    ) -> Vec<StrategyAction> {
        // Sprint N+1 W2 sub-task 2：BtcLeadLagPanel paper-only shadow log。
        // 在任何 strategy logic 之前 evaluate（per spec §5.1.2 + §6 Layer 3）。
        // - paper-only fence Layer 1：surface.btc_lead_lag 在 demo/live_demo/live
        //   永遠 None（fence 由 step_4_5_dispatch engine_mode gate 主防線控制）
        // - 本端 `if let Some(panel) = ...` 為 redundant safety guard
        // - shadow log emit 後 **不**改 actions / **不**改 strategy state；
        //   下游 7d 後跑離線 SQL 對齊真實 fill 算 counterfactual edge
        if let Some(panel) = surface.btc_lead_lag {
            let _shadow = crate::strategies::cross_asset::evaluate_shadow_signal(
                self.name(),
                ctx,
                panel,
            );
            // _shadow 純評估快照，丟棄不影響後續 strategy decision。
        }

        let ind = match ctx.indicators {
            Some(i) => i,
            None => return vec![],
        };
        // 為 on_rejection cooldown rollback 快照變更前 last_ms（未見時哨兵 0）。
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

        // 為 on_rejection cooldown rollback 快照變更前 last_ms（未見時沿用哨兵 0）。
        // P0 Option A-Lite (2026-05-11)：prev_position snapshot 移除；prev_last_trade_ms 保留。
        self.prev_last_trade_ms
            .insert(ctx.symbol.to_string(), last_ms);

        // ── P0 Option A-Lite (2026-05-11)：position state SSoT 改造 ──
        // 改造前：`match self.positions.get(ctx.symbol).copied()` 走本地 state。
        // 改造後：以 `ctx.position_state` filter 出 self-owned position 做為 SSoT；
        // owner_strategy != self.name() 視為 cross-strategy 持倉 → skip entry。
        //
        // - `owns = Some(is_long)`：self-owned 倉位 → exit 分支
        // - `owns = None` + `ctx.position_state.is_some()`：cross-strategy 持倉 → skip
        // - `owns = None` + `ctx.position_state.is_none()`：無倉 → entry 分支
        //
        // 詳：PA report `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_option_a_position_state_ssot_refactor.md` §3.2
        let owns: Option<bool> = ctx
            .position_state
            .filter(|p| p.owner_strategy == self.name())
            .map(|p| p.is_long);

        match owns {
            None if ctx.position_state.is_some() => {
                // Cross-strategy 持倉（owner_strategy != "ma_crossover"，
                // 可能是 grid_trading / bb_breakout / bb_reversion / bybit_sync / orphan_adopted
                // 等任一）→ 主動 backoff，不發 entry 也不嘗試 exit（exit 由 owner strategy
                // 負責）。symbol 真釋放（close）後下個 tick 自動恢復 entry path。
                tracing::debug!(
                    target: "ma_crossover",
                    symbol = %ctx.symbol,
                    "skip entry: cross-strategy paper_state position holds (P0 Option A-Lite owner gate)"
                );
                return vec![];
            }
            None => {
                // 無倉位 → entry path。RC-01 regime filter + RC-02 higher-TF confirmation 套用。
                if !self.regime_allows_entry(ctx) {
                    return vec![];
                }

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
                // R3-9：最小名義值守衛
                if qty * ctx.price < self.min_notional_usd {
                    return vec![];
                }

                let regime = ind.hurst.as_ref().map(|h| h.regime.as_str());
                let entry_conf = self.compute_entry_confidence(adx, regime);
                // R3-2：復用 confidence 欄位存放匯流分數。
                let conf_with_score = match score {
                    Some(s) if s > 0.0 => s / 65.0, // normalize to [0,1]
                    _ => entry_conf,
                };

                if let Some(is_long) = signal {
                    if !self.higher_tf_allows_entry(ctx.symbol, is_long) {
                        return vec![];
                    }
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
                        // P0 Option A-Lite (2026-05-11)：self.positions.insert 移除
                        // — paper_state.apply_fill 是 SSoT 寫入點。cooldown 仍需 record。
                        self.cooldown.record_signal(ctx.symbol, ctx.timestamp_ms);
                    }
                }
            }
            Some(is_long) => {
                // Exit path — RC-01/RC-02 filters do NOT apply to exits.
                // KAMA crosses back through SMA20 = trend reversal (Kaufman).
                // 出場路徑 — KAMA 回穿 SMA20 = 趨勢反轉。出場不套用入場過濾器。
                //
                // A1：反向交叉不再單 tick 出場，以 KAMA ER 縮放的持續性窗口過濾假反轉。
                let reverse_signal: Option<bool> = if is_long && fast < slow {
                    Some(false) // bearish reverse for long position
                } else if !is_long && fast > slow {
                    Some(true) // bullish reverse for short position
                } else {
                    None // aligned with position, no reverse signal
                };

                // ER 縮放的出場持續性窗口；無 KAMA 時退回 ER=0.5 避免冷啟動 pin 在入場門檻。
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
                    // P0 Option A-Lite (2026-05-11)：self.positions.remove 移除
                    // — paper_state.apply_fill 平倉路徑會清 paper_state position。
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
