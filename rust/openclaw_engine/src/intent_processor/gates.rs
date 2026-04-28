//! Cost gate implementations — profile-aware EV filtering.
//! 成本門控實現 — 按 GovernanceProfile 分層 EV 過濾。

use super::*;

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
        self.cost_gate_moderate_with_slippage(strategy, symbol, fee_rate, slippage)
    }

    pub(super) fn cost_gate_moderate_with_slippage(
        &self,
        strategy: &str,
        symbol: &str,
        fee_rate: f64,
        slippage: f64,
    ) -> Option<ExchangeGateResult> {
        let slippage_cfg = &self.risk_config.slippage;
        let fee_bps = 2.0 * (fee_rate + slippage) * 10_000.0;
        let min_n = slippage_cfg.cost_gate_min_n_trades_for_block;
        match self.edge_estimates.get_cell(strategy, symbol) {
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
        self.cost_gate_live_with_slippage(strategy, symbol, fee_rate, slippage)
    }

    pub(super) fn cost_gate_live_with_slippage(
        &self,
        strategy: &str,
        symbol: &str,
        fee_rate: f64,
        slippage: f64,
    ) -> Option<ExchangeGateResult> {
        let slippage_cfg = &self.risk_config.slippage;
        // Round-trip cost in bps including slippage
        // 包含滑點的來回成本 bps
        let fee_bps = 2.0 * (fee_rate + slippage) * 10_000.0;
        match self.edge_estimates.get_cell(strategy, symbol) {
            Some(cell) if cell.shrunk_bps > 0.0 => {
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
