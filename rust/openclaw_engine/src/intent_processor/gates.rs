//! Cost gate implementations — profile-aware EV filtering.
//! 成本門控實現 — 按 GovernanceProfile 分層 EV 過濾。

use super::*;

/// P1-09 測試固定時鐘（epoch 秒，2026-05-29T00:00:00Z 附近）。測試 fixture 的
/// `_meta.updated_at` 相對此值構造 fresh / stale 場景，避免依賴 wallclock。
#[cfg(test)]
pub(super) const TEST_NOW_SECS: i64 = 1_780_000_000;

impl IntentProcessor {
    /// PH5-WIRE-1: Paper/demo mode cost gate helper.
    /// Positive JS estimate → check EV vs fee (block if below).
    /// Negative JS estimate → exploration mode (allow + log; need data to improve estimates).
    /// No estimate (cold-start) → ATR×conf×0.2 fallback.
    /// Returns Some(rejected) on block, None on pass.
    /// PH5-WIRE-1：Paper/demo 模式成本門。
    /// 正估計 → EV 與 fee 比較；負估計 → 探索模式（允許+記錄）；無估計 → ATR×0.2 回退。
    pub(super) fn cost_gate_paper(
        &self,
        strategy: &str,
        symbol: &str,
        _atr: f64,
        _conf: f64,
        _qty: f64,
        _price: f64,
        fee_rate: f64,
        slippage: f64,
    ) -> Option<IntentResult> {
        let slippage_cfg = &self.risk_config.slippage;
        // Round-trip cost in bps: (fee + slippage) × 2 legs × 10000
        // 來回成本 bps：(手續費 + 滑點) × 2 腿 × 10000
        let fee_bps = 2.0 * (fee_rate + slippage) * 10_000.0;

        match self.edge_estimates.get_cell(strategy, symbol) {
            Some(cell) if cell.shrunk_bps > 0.0 => {
                // Positive JS estimate: use it as EV signal with win_rate weighting.
                // G7-07: floor + safety multiplier now read from
                // `risk.slippage.cost_gate_{win_rate_floor, safety_multiplier}`.
                // 正 JS 估計：作為 EV 信號，加入 win_rate 加權。
                // G7-07：floor 與 safety multiplier 改讀 risk.slippage.* TOML。
                let wr = cell
                    .win_rate
                    .clamp(slippage_cfg.cost_gate_win_rate_floor, 1.0);
                let threshold_bps = fee_bps / wr * slippage_cfg.cost_gate_safety_multiplier;
                if cell.shrunk_bps < threshold_bps {
                    return Some(IntentResult::rejected(
                        RejectionCode::CostGateJsPaper {
                            edge_bps: cell.shrunk_bps,
                            threshold_bps,
                            fee_bps,
                            win_rate: cell.win_rate,
                            slippage_bps: slippage * 10_000.0,
                        }
                        .format(),
                    ));
                }
                tracing::debug!(
                    strategy,
                    symbol,
                    shrunk_edge_bps = cell.shrunk_bps,
                    win_rate = cell.win_rate,
                    n_trades = cell.n_trades,
                    "cost_gate(JS): positive edge — allowed / 正 edge 允許通過"
                );
                None
            }
            Some(cell) => {
                // Negative JS estimate: exploration mode — allow to accumulate data.
                // Paper pipeline now reads its own edge_estimates_paper.json (isolated from
                // demo/live), so paper exploration noise no longer degrades production estimates.
                // 負 JS 估計：探索模式——允許以積累數據。
                // Paper 管線現在讀取獨立的 edge_estimates_paper.json，
                // paper 探索噪音不再影響生產估計。
                tracing::info!(
                    strategy,
                    symbol,
                    estimated_edge_bps = cell.shrunk_bps,
                    win_rate = cell.win_rate,
                    n_trades = cell.n_trades,
                    "cost_gate(JS): negative estimate — exploration mode / 負估計探索模式"
                );
                None
            }
            None => {
                // Cold start: no JS estimate — exploration mode for paper, ATR gate for exchange.
                // Paper/demo mode needs to accumulate trades to build JS estimates; blocking here
                // creates a dead-loop: no trades → no data → no estimates → no trades.
                // 冷啟動：無 JS 估計 — paper 模式用探索模式放行，交易所模式用 ATR 門控。
                // Paper/demo 需要積累交易以建立 JS 估計；攔截會造成死循環。
                tracing::info!(strategy, symbol,
                    "cost_gate(cold-start): no JS estimate — exploration mode (paper) / 無 JS 估計探索模式");
                None
            }
        }
    }

    /// 3E-2a: Demo mode cost gate — moderate strictness (between exploration and strict).
    /// EDGE-DIAG-2 (2026-04-28): low-sample cells (n_trades < cost_gate_min_n_trades_for_block,
    /// default 30) bypass the JS estimate entirely and route to exploration mode — the
    /// estimate is noise-dominated and blocking on it creates a dead-loop where strategies
    /// cannot accumulate fills to escape the negative-edge bucket. Statistically robust cells
    /// (n >= min_n) keep the original behavior: positive → threshold check; negative → block;
    /// cold-start (no cell) → allow with warning. Live path stays strict per
    /// CLAUDE.md §四 operator policy: demo loose, live strict.
    /// 3E-2a：Demo 模式成本門——中等嚴格。
    /// EDGE-DIAG-2（2026-04-28）：低樣本（n_trades < cost_gate_min_n_trades_for_block，
    /// 預設 30）跳過 JS 估計直接走探索模式——估計值噪音主導，據此阻擋會造成死循環，
    /// 策略無法累積 fills 逃脫負 edge 桶。統計穩健（n ≥ min_n）保持原行為：
    /// 正 → 門檻檢查；負 → 阻擋；冷啟動（無格子） → 放行並警告。Live 路徑仍嚴格
    /// （CLAUDE.md §四 operator 政策：demo 放寬 / live 收緊）。
    #[cfg(test)]
    pub(super) fn cost_gate_moderate(
        &self,
        strategy: &str,
        symbol: &str,
        fee_rate: f64,
        volume_24h: f64,
    ) -> Option<ExchangeGateResult> {
        let slippage = lookup_slippage(&self.risk_config.slippage, volume_24h);
        // 測試 wrapper：注入固定 now（與 TEST_NOW_SECS fixture 對齊）。
        self.cost_gate_moderate_with_slippage(strategy, symbol, fee_rate, slippage, TEST_NOW_SECS)
    }

    pub(super) fn cost_gate_moderate_with_slippage(
        &self,
        strategy: &str,
        symbol: &str,
        fee_rate: f64,
        slippage: f64,
        now_secs: i64,
    ) -> Option<ExchangeGateResult> {
        let slippage_cfg = &self.risk_config.slippage;
        let fee_bps = 2.0 * (fee_rate + slippage) * 10_000.0;
        let min_n = slippage_cfg.cost_gate_min_n_trades_for_block;
        match self.edge_estimates.get_cell(strategy, symbol) {
            // EDGE-DIAG-2 補:即使 low-sample,當 shrunk_bps 落在
            // crypto 結構性 noise band 以下(< -15 bps),不放行;
            // 避免 cell 在 noise band 內累損直到跨 min_n。
            // cutoff 由 MIT sensitivity sweep 拍板(2026-05-23):
            //   - cross-validation 50% 命中率顯示 [-15, 0) 是 noise band
            //   - deep tail < -15 才方向可靠
            //   - 1B funding_arb 框架僅 LABUSDT outlier 被影響
            Some(cell) if cell.n_trades < min_n && cell.shrunk_bps < -15.0 => {
                // Track1 demo explore-gate（branch A）：若 allocator 指示此 arm 仍在探索期
                // AND 探索額度未滿 → 翻 reject 為探索放行（return None = pass）。
                // 為什麼安全：放行的 qty 是已過 Guardian(Gate2)/Kelly(Gate2.5)/P1 cap(Gate2.6)/
                // 准入(Gate2.7) 的 final_qty（cost gate 是最後一道），explore 只翻 Gate3 此一道，
                // 結構上不可能繞過上游風控。fail-closed：缺欄→false/0→不進此分支→維持現行 block。
                if cell.explore_eligible && cell.explore_remaining > 0 {
                    tracing::info!(
                        strategy,
                        symbol,
                        estimated_edge_bps = cell.shrunk_bps,
                        n_trades = cell.n_trades,
                        explore_remaining = cell.explore_remaining,
                        "cost_gate(JS-demo): EXPLORE allow deep-neg low-sample / 探索放行深負低樣本"
                    );
                    return None;
                }
                // E2 review 2026-05-23 對齊:tracing field key 改用 `estimated_edge_bps`
                // 與既有 4 處(paper L73 / demo L159 / live L73 / live L157)baseline 一致;
                // audit log grep 不再分裂兩種 key。`cutoff_bps` 顯式 f64 避免 type mismatch。
                tracing::info!(
                    strategy,
                    symbol,
                    estimated_edge_bps = cell.shrunk_bps,
                    n_trades = cell.n_trades,
                    cutoff_bps = -15.0_f64,
                    "cost_gate(JS-demo): low sample but deep-negative — block / 低樣本深負阻擋"
                );
                Some(ExchangeGateResult::rejected(
                    RejectionCode::CostGateJsDemoNegative {
                        estimated_bps: cell.shrunk_bps,
                    }
                    .format(),
                ))
            }
            Some(cell) if cell.n_trades < min_n => {
                // EDGE-DIAG-2: low-sample cell — treat as noise; route to exploration mode.
                // EDGE-DIAG-2：低樣本 cell — 視為噪音；路由到探索模式。
                tracing::info!(
                    strategy,
                    symbol,
                    estimated_edge_bps = cell.shrunk_bps,
                    win_rate = cell.win_rate,
                    n_trades = cell.n_trades,
                    min_n_for_block = min_n,
                    "cost_gate(JS-demo): low sample — exploration mode / 低樣本探索模式"
                );
                None
            }
            Some(cell) if cell.shrunk_bps > 0.0 => {
                // P1-09 demo 非對稱：正 edge 若 stale / 非 runtime-derived / 未驗證，
                // 路由到探索模式（放行 + log），NOT reject。理由：demo 是學習資料源
                // （memory feedback_demo_loose_live_strict_policy），對 unvalidated-positive
                // 採 fail-close 會重現 Phase 5 99.98% reject 死循環。live 同情況改為拒絕。
                let ttl = slippage_cfg.edge_estimate_ttl_secs;
                let fresh = self.edge_estimates.is_fresh(now_secs, ttl);
                if !fresh || !cell.from_runtime_field || !cell.validation_passed {
                    tracing::info!(
                        strategy,
                        symbol,
                        estimated_edge_bps = cell.shrunk_bps,
                        fresh,
                        has_runtime = cell.from_runtime_field,
                        validated = cell.validation_passed,
                        "cost_gate(JS-demo): positive edge unproven — exploration mode / 正 edge 未驗證探索模式"
                    );
                    return None;
                }
                // Positive JS estimate: same threshold as live (win-rate weighted)
                // G7-07: floor + safety multiplier from `risk.slippage.*`.
                // 正 JS 估計：與 live 相同門檻（勝率加權）。G7-07：改讀 TOML。
                let wr = cell
                    .win_rate
                    .clamp(slippage_cfg.cost_gate_win_rate_floor, 1.0);
                let threshold_bps = fee_bps / wr * slippage_cfg.cost_gate_safety_multiplier;
                if cell.shrunk_bps < threshold_bps {
                    return Some(ExchangeGateResult::rejected(
                        RejectionCode::CostGateJsDemoThreshold {
                            edge_bps: cell.shrunk_bps,
                            threshold_bps,
                            fee_bps,
                            win_rate: cell.win_rate,
                        }
                        .format(),
                    ));
                }
                None // pass
            }
            Some(cell) => {
                // Track1 demo explore-gate（branch B）：robust-negative（n≥min_n 的負）通常該死。
                // 但若 allocator 仍指示 explore_eligible（例如 regime 轉折後 forgetting_gamma
                // 衰減舊 regime 的負統計，arm 被縮回探索期）AND remaining>0 → 探索放行。
                // 為什麼開 branch B：死 flat 主體是 n≥min_n 的負 arm；只開 branch A 它們會永久死，
                // 撞 first-detection deadlock。regime 非平穩處理在 allocator 端，gate 只信任信號。
                // fail-closed 與隔離同 branch A：缺欄→不放行；只 demo gate 讀 explore 欄。
                if cell.explore_eligible && cell.explore_remaining > 0 {
                    tracing::info!(
                        strategy,
                        symbol,
                        estimated_edge_bps = cell.shrunk_bps,
                        n_trades = cell.n_trades,
                        explore_remaining = cell.explore_remaining,
                        "cost_gate(JS-demo): EXPLORE allow robust-neg / 探索放行穩健負(regime-driven)"
                    );
                    return None;
                }
                // Statistically robust (n >= min_n) negative JS estimate → block.
                // 統計穩健（n ≥ min_n）的負 JS 估計 → 阻擋。
                Some(ExchangeGateResult::rejected(
                    RejectionCode::CostGateJsDemoNegative {
                        estimated_bps: cell.shrunk_bps,
                    }
                    .format(),
                ))
            }
            None => {
                // Cold start: allow with warning (unlike live which blocks)
                // Demo needs to accumulate trades — blocking creates dead-loop like paper.
                // 冷啟動：放行並警告（不同於 live 阻擋）。Demo 需累積交易數據。
                tracing::info!(strategy, symbol,
                    "cost_gate(demo-cold-start): no JS estimate — allowing for data accumulation / 無 JS 估計放行以累積數據");
                None
            }
        }
    }

    /// PH5-WIRE-1: Live mode cost gate — strictly requires positive JS estimate.
    /// Negative or missing estimate → fail-closed (root principle #5: survival > profit).
    /// Returns Some(rejected) on block, None on pass.
    /// PH5-WIRE-1：Live 模式成本門——嚴格要求正 JS 估計。
    /// 負/無估計 → 失敗關閉（根原則 #5：生存 > 利潤）。
    #[cfg(test)]
    pub(super) fn cost_gate_live(
        &self,
        strategy: &str,
        symbol: &str,
        fee_rate: f64,
        volume_24h: f64,
    ) -> Option<ExchangeGateResult> {
        let slippage = lookup_slippage(&self.risk_config.slippage, volume_24h);
        // 測試 wrapper：注入固定 now（與 TEST_NOW_SECS fixture 對齊）。
        self.cost_gate_live_with_slippage(strategy, symbol, fee_rate, slippage, TEST_NOW_SECS)
    }

    pub(super) fn cost_gate_live_with_slippage(
        &self,
        strategy: &str,
        symbol: &str,
        fee_rate: f64,
        slippage: f64,
        now_secs: i64,
    ) -> Option<ExchangeGateResult> {
        let slippage_cfg = &self.risk_config.slippage;
        // Round-trip cost in bps including slippage
        // 包含滑點的來回成本 bps
        let fee_bps = 2.0 * (fee_rate + slippage) * 10_000.0;
        match self.edge_estimates.get_cell(strategy, symbol) {
            Some(cell) if cell.shrunk_bps > 0.0 => {
                // P1-09 生產新鮮度門：正 edge 僅在 fresh + runtime-derived + validated
                // 三者全真時才允許進入門檻比較。任一不成立 → live fail-closed 拒絕
                // （根原則 #5/#6：陳舊 / 舊格式 / 未驗證的正 edge 不可授權 live）。
                // `now_secs` 由 caller 注入，TTL 讀 config 而非字面量。
                let ttl = slippage_cfg.edge_estimate_ttl_secs;
                let fresh = self.edge_estimates.is_fresh(now_secs, ttl);
                if !fresh || !cell.from_runtime_field || !cell.validation_passed {
                    let age_secs = self
                        .edge_estimates
                        .updated_at()
                        .map(|u| now_secs.saturating_sub(u));
                    return Some(ExchangeGateResult::rejected(
                        RejectionCode::CostGateJsLiveStaleOrUnvalidated {
                            age_secs,
                            ttl_secs: ttl,
                            has_runtime: cell.from_runtime_field,
                            validated: cell.validation_passed,
                        }
                        .format(),
                    ));
                }
                // Win-rate weighted threshold (aligned with Python cost_gate.py)
                // G7-07: floor + safety multiplier from `risk.slippage.*`.
                // 勝率加權門檻（對齊 Python cost_gate.py）。G7-07：改讀 TOML。
                let wr = cell
                    .win_rate
                    .clamp(slippage_cfg.cost_gate_win_rate_floor, 1.0);
                let threshold_bps = fee_bps / wr * slippage_cfg.cost_gate_safety_multiplier;
                if cell.shrunk_bps < threshold_bps {
                    return Some(ExchangeGateResult::rejected(
                        RejectionCode::CostGateJsLiveThreshold {
                            edge_bps: cell.shrunk_bps,
                            threshold_bps,
                            fee_bps,
                            win_rate: cell.win_rate,
                        }
                        .format(),
                    ));
                }
                None // pass
            }
            Some(cell) => Some(ExchangeGateResult::rejected(
                RejectionCode::CostGateJsLiveNegative {
                    estimated_bps: cell.shrunk_bps,
                }
                .format(),
            )),
            None => Some(ExchangeGateResult::rejected(
                RejectionCode::CostGateJsLiveColdStart.format(),
            )),
        }
    }

    /// PNL-5: Cost-gate k multiplier scaled by notional size, reading
    /// k_small / k_medium / k_base from RiskManagerConfig (Session 12 cleanup).
    /// Reserved for exchange-mode cost gate (Live pipeline).
    /// PNL-5：成本門 k 倍率隨 notional 規模調整，三檔 k 從 config 讀取。
    /// 為交易所模式成本門（Live 管線）保留。
    #[allow(dead_code)]
    pub(super) fn cost_gate_k(&self, notional: f64) -> f64 {
        if notional < 50.0 {
            self.risk_config.cost_gate.k_small
        } else if notional < 200.0 {
            self.risk_config.cost_gate.k_medium
        } else {
            self.risk_config.cost_gate.k_base
        }
    }
}
