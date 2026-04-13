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
        volume_24h: f64,
    ) -> Option<IntentResult> {
        let fee_rate = self.fee_rate(symbol);
        let slippage = lookup_slippage(volume_24h);
        // Round-trip cost in bps: (fee + slippage) × 2 legs × 10000
        // 來回成本 bps：(手續費 + 滑點) × 2 腿 × 10000
        let fee_bps = 2.0 * (fee_rate + slippage) * 10_000.0;

        match self.edge_estimates.get_cell(strategy, symbol) {
            Some(cell) if cell.shrunk_bps > 0.0 => {
                // Positive JS estimate: use it as EV signal with win_rate weighting.
                // 正 JS 估計：作為 EV 信號，加入 win_rate 加權。
                // Effective threshold: fee_bps / max(0.3, win_rate) × 1.3 (30% safety margin)
                // Mirrors Python: min_move_pct = c_round / max(0.3, win_rate) × 1.3
                let wr = cell.win_rate.clamp(0.3, 1.0);
                let threshold_bps = fee_bps / wr * 1.3;
                if cell.shrunk_bps < threshold_bps {
                    return Some(IntentResult {
                        submitted: false,
                        rejected_reason: Some(format!(
                            "cost_gate(JS): edge={:.2}bps < threshold={:.2}bps \
                             (fee={:.2}bps, wr={:.2}, slip={:.1}bps)",
                            cell.shrunk_bps, threshold_bps, fee_bps, cell.win_rate,
                            slippage * 10_000.0,
                        )),
                        fill: None,
                        verdict_info: None,
                    });
                }
                tracing::debug!(strategy, symbol, shrunk_edge_bps = cell.shrunk_bps,
                    win_rate = cell.win_rate, n_trades = cell.n_trades,
                    "cost_gate(JS): positive edge — allowed / 正 edge 允許通過");
                None
            }
            Some(cell) => {
                // Negative JS estimate: exploration mode — allow to accumulate data.
                // Paper pipeline now reads its own edge_estimates_paper.json (isolated from
                // demo/live), so paper exploration noise no longer degrades production estimates.
                // 負 JS 估計：探索模式——允許以積累數據。
                // Paper 管線現在讀取獨立的 edge_estimates_paper.json，
                // paper 探索噪音不再影響生產估計。
                tracing::info!(strategy, symbol, estimated_edge_bps = cell.shrunk_bps,
                    win_rate = cell.win_rate, n_trades = cell.n_trades,
                    "cost_gate(JS): negative estimate — exploration mode / 負估計探索模式");
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
    /// Positive JS estimate → apply threshold; negative → block; cold-start → allow with warning.
    /// 3E-2a：Demo 模式成本門——中等嚴格（介於探索和嚴格之間）。
    /// 正 JS 估計 → 應用門檻；負 → 阻擋；冷啟動 → 放行並警告。
    pub(super) fn cost_gate_moderate(
        &self,
        strategy: &str,
        symbol: &str,
        fee_rate: f64,
        volume_24h: f64,
    ) -> Option<ExchangeGateResult> {
        let slippage = lookup_slippage(volume_24h);
        let fee_bps = 2.0 * (fee_rate + slippage) * 10_000.0;
        match self.edge_estimates.get_cell(strategy, symbol) {
            Some(cell) if cell.shrunk_bps > 0.0 => {
                // Positive JS estimate: same threshold as live (win-rate weighted)
                // 正 JS 估計：與 live 相同門檻（勝率加權）
                let wr = cell.win_rate.clamp(0.3, 1.0);
                let threshold_bps = fee_bps / wr * 1.3;
                if cell.shrunk_bps < threshold_bps {
                    return Some(ExchangeGateResult {
                        approved: false,
                        rejected_reason: Some(format!(
                            "cost_gate(JS-demo): edge={:.2}bps < threshold={:.2}bps \
                             (fee={:.2}bps, wr={:.2})",
                            cell.shrunk_bps, threshold_bps, fee_bps, cell.win_rate,
                        )),
                        approved_qty: 0.0,
                        verdict_info: None,
                    });
                }
                None // pass
            }
            Some(cell) => {
                // Negative JS estimate: block (unlike paper exploration which allows)
                // 負 JS 估計：阻擋（不同於 paper 探索模式允許）
                Some(ExchangeGateResult {
                    approved: false,
                    rejected_reason: Some(format!(
                        "cost_gate(JS-demo): estimated={:.2}bps < 0 — blocked / 負估計阻擋",
                        cell.shrunk_bps,
                    )),
                    approved_qty: 0.0,
                    verdict_info: None,
                })
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
    pub(super) fn cost_gate_live(
        &self,
        strategy: &str,
        symbol: &str,
        fee_rate: f64,
        volume_24h: f64,
    ) -> Option<ExchangeGateResult> {
        let slippage = lookup_slippage(volume_24h);
        // Round-trip cost in bps including slippage
        // 包含滑點的來回成本 bps
        let fee_bps = 2.0 * (fee_rate + slippage) * 10_000.0;
        match self.edge_estimates.get_cell(strategy, symbol) {
            Some(cell) if cell.shrunk_bps > 0.0 => {
                // Win-rate weighted threshold (aligned with Python cost_gate.py)
                // 勝率加權門檻（對齊 Python cost_gate.py）
                let wr = cell.win_rate.clamp(0.3, 1.0);
                let threshold_bps = fee_bps / wr * 1.3;
                if cell.shrunk_bps < threshold_bps {
                    return Some(ExchangeGateResult {
                        approved: false,
                        rejected_reason: Some(format!(
                            "cost_gate(JS-live): edge={:.2}bps < threshold={:.2}bps \
                             (fee={:.2}bps, wr={:.2})",
                            cell.shrunk_bps, threshold_bps, fee_bps, cell.win_rate,
                        )),
                        approved_qty: 0.0,
                        verdict_info: None,
                    });
                }
                None // pass
            }
            Some(cell) => Some(ExchangeGateResult {
                approved: false,
                rejected_reason: Some(format!(
                    "cost_gate(JS-live): estimated={:.2}bps < 0 — fail-closed / 負估計失敗關閉",
                    cell.shrunk_bps,
                )),
                approved_qty: 0.0,
                verdict_info: None,
            }),
            None => Some(ExchangeGateResult {
                approved: false,
                rejected_reason: Some(
                    "cost_gate(JS-live): no edge estimate — fail-closed (cold-start) / 無估計失敗關閉".into(),
                ),
                approved_qty: 0.0,
                verdict_info: None,
            }),
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
