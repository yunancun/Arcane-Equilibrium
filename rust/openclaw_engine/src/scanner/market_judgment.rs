//! Scanner market-regime judgement — per-strategy route compatibility.
//! Scanner 行情結構判斷 — 分策略路由相容性。
//!
//! MODULE_NOTE (EN): Keeps regime gating separate from the base scorer so
//! scanner scoring remains focused on deterministic fitness and correlation
//! selection. The outputs are audit metadata used by demo/live_demo new-entry
//! gates; close/reduce paths do not consume this module.
//! MODULE_NOTE (中): 將行情 regime gate 從基礎 scorer 拆出，讓 scorer 專注
//! 確定性適配分與相關性選擇。輸出是 demo/live_demo 新開倉 gate 使用的審計
//! metadata；close/reduce 路徑不消費本模組。

use crate::edge_estimates::EdgeEstimates;
use crate::scanner::config::{EdgeRoutingConfig, MarketJudgmentConfig};
use crate::scanner::scorer::{apply_edge_bonus_for_strategy, FitnessScores, MarketConditions};
use crate::scanner::types::StrategyRouteJudgment;
use std::collections::BTreeMap;

/// Classify a compact market regime label for scanner audit trails.
/// 將市場條件歸類為精簡 regime label，供 scanner 審計鏈使用。
pub(crate) fn classify_market_regime(mc: &MarketConditions) -> &'static str {
    if mc.shock_score >= 0.55 {
        "one_way_shock"
    } else if mc.trend_score >= 0.55 {
        "trending"
    } else if mc.range_score >= 0.35 {
        "range_bound"
    } else if mc.range_pct < 3.0 {
        "quiet"
    } else {
        "mixed"
    }
}

/// Return a strategy-specific market block reason, or None when compatible.
/// 返回分策略行情阻擋原因；行情相容時返回 None。
fn market_block_reason(
    strategy: &str,
    mc: &MarketConditions,
    cfg: &MarketJudgmentConfig,
) -> Option<String> {
    if !cfg.enabled {
        return None;
    }
    match strategy {
        "grid_trading" => {
            if mc.range_pct < cfg.grid_min_range_pct {
                Some(format!(
                    "grid_range_too_small:range={:.2}<min{:.2}",
                    mc.range_pct, cfg.grid_min_range_pct
                ))
            } else if mc.dir_pct > cfg.grid_max_dir_pct
                || mc.de > cfg.grid_max_directional_efficiency
                || mc.trend_score > cfg.grid_max_trend_score
            {
                Some(format!(
                    "grid_trend_mismatch:trend={:.2} de={:.2} dir={:.2}% range={:.2}%",
                    mc.trend_score, mc.de, mc.dir_pct, mc.range_pct
                ))
            } else {
                None
            }
        }
        "ma_crossover" => {
            if mc.trend_score < cfg.trend_min_trend_score || mc.dir_pct < cfg.trend_min_dir_pct {
                Some(format!(
                    "ma_no_clean_trend:trend={:.2}<min{:.2} dir={:.2}%<min{:.2}%",
                    mc.trend_score, cfg.trend_min_trend_score, mc.dir_pct, cfg.trend_min_dir_pct
                ))
            } else {
                None
            }
        }
        "bb_reversion" => {
            if mc.range_pct < cfg.reversion_min_range_pct {
                Some(format!(
                    "reversion_range_too_small:range={:.2}<min{:.2}",
                    mc.range_pct, cfg.reversion_min_range_pct
                ))
            } else if mc.trend_score > cfg.reversion_max_trend_score {
                Some(format!(
                    "reversion_trend_dominant:trend={:.2}>max{:.2} de={:.2}",
                    mc.trend_score, cfg.reversion_max_trend_score, mc.de
                ))
            } else {
                None
            }
        }
        "bb_breakout" => {
            if mc.trend_score < cfg.breakout_min_trend_score
                || mc.dir_pct < cfg.breakout_min_dir_pct
            {
                Some(format!(
                    "breakout_no_expansion:trend={:.2}<min{:.2} dir={:.2}%<min{:.2}%",
                    mc.trend_score,
                    cfg.breakout_min_trend_score,
                    mc.dir_pct,
                    cfg.breakout_min_dir_pct
                ))
            } else {
                None
            }
        }
        // Funding arb uses the momentum thresholds as a soft caution in
        // `funding_momentum_caution_reason`, not a hard market block. The
        // observed 2026-05-01 BIOUSDT case showed that high spot momentum can
        // still carry positive demo edge once funding / basis logic fires.
        // funding arb 的 momentum 門檻改由 `funding_momentum_caution_reason`
        // 做軟性降分，不作硬阻擋。2026-05-01 BIOUSDT 反例顯示高動量下
        // funding / basis 邏輯仍可能有正 demo edge。
        "funding_arb" => None,
        _ => None,
    }
}

/// Return a funding-specific soft caution reason; never hard-blocks entries.
/// 返回 funding 專用軟性警示原因；絕不硬阻擋新開倉。
fn funding_momentum_caution_reason(
    strategy: &str,
    mc: &MarketConditions,
    cfg: &MarketJudgmentConfig,
) -> Option<String> {
    if strategy != "funding_arb" || !cfg.enabled {
        return None;
    }
    if mc.dir_pct > cfg.funding_max_dir_pct || mc.trend_score > cfg.funding_max_trend_score {
        Some(format!(
            "funding_momentum_caution:trend={:.2} dir={:.2}% funding={:.2}bps",
            mc.trend_score, mc.dir_pct, mc.signed_fr_bps
        ))
    } else {
        None
    }
}

/// Return the base scanner fitness for one explicit strategy.
/// 返回指定策略的 scanner 基礎適配分。
fn strategy_fitness(strategy: &str, fitness: &FitnessScores, _mc: &MarketConditions) -> f64 {
    match strategy {
        "ma_crossover" => fitness.f_ma,
        "grid_trading" => fitness.f_grid,
        "bb_reversion" => fitness.f_bbrv,
        "bb_breakout" => fitness.f_bkout,
        "funding_arb" => fitness.f_funding_arb,
        _ => 0.0,
    }
}

/// Build per-strategy route judgments for one scanner candidate.
/// 為單一 scanner 候選生成分策略路由判斷。
pub(crate) fn build_strategy_judgments(
    fitness: &FitnessScores,
    mc: &MarketConditions,
    symbol: &str,
    estimates: &EdgeEstimates,
    edge_cfg: &EdgeRoutingConfig,
    market_cfg: &MarketJudgmentConfig,
) -> BTreeMap<String, StrategyRouteJudgment> {
    let mut out = BTreeMap::new();
    for strategy in [
        "ma_crossover",
        "grid_trading",
        "bb_reversion",
        "bb_breakout",
        "funding_arb",
    ] {
        let raw = strategy_fitness(strategy, fitness, mc);
        let mut edge = apply_edge_bonus_for_strategy(raw, strategy, symbol, estimates, edge_cfg);

        let immature_negative = market_cfg.enabled
            && edge.n >= market_cfg.immature_negative_min_trades
            && edge.n < edge_cfg.robust_negative_min_trades
            && edge
                .edge_bps
                .map(|bps| bps < market_cfg.immature_negative_bps_threshold)
                .unwrap_or(false);
        if let Some(reason) = market_block_reason(strategy, mc, market_cfg) {
            edge.final_score = edge.final_score.min(market_cfg.gate_score_cap);
            edge.market_status = "blocked".to_string();
            edge.route_mode = "market_gate".to_string();
            edge.route_reason = reason;
        } else if immature_negative {
            edge.final_score = edge.final_score.min(market_cfg.immature_negative_score_cap);
            edge.market_status = "edge_watch".to_string();
            edge.route_mode = "exploration".to_string();
            edge.route_reason = format!(
                "immature_negative_watch:n={} bps={:.2}",
                edge.n,
                edge.edge_bps.unwrap_or(0.0)
            );
        } else if let Some(reason) = funding_momentum_caution_reason(strategy, mc, market_cfg) {
            edge.final_score = edge.final_score.min(market_cfg.gate_score_cap);
            edge.market_status = "momentum_caution".to_string();
            edge.route_reason = reason;
        } else if market_cfg.enabled {
            edge.market_status = "compatible".to_string();
            if edge.route_reason == "edge_unexplored" {
                edge.route_reason = format!(
                    "market_compatible:regime={} phase={} trend={:.2} range={:.2}",
                    classify_market_regime(mc),
                    mc.trend_phase,
                    mc.trend_score,
                    mc.range_score
                );
            }
        } else {
            edge.market_status = "disabled".to_string();
            if edge.route_reason == "edge_unexplored" {
                edge.route_reason = "market_judgment_disabled".to_string();
            }
        }

        out.insert(
            strategy.to_string(),
            StrategyRouteJudgment {
                strategy: strategy.to_string(),
                fitness_score: raw,
                final_score: edge.final_score,
                edge_bps: edge.edge_bps,
                edge_bonus: edge.bonus,
                edge_n: edge.n,
                edge_status: edge.edge_status,
                route_mode: edge.route_mode,
                market_status: edge.market_status,
                route_reason: edge.route_reason,
            },
        );
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::edge_estimates::EdgeEstimates;
    use crate::scanner::config::{EdgeRoutingConfig, MarketJudgmentConfig};
    use crate::scanner::scorer::{compute_fitness, MarketConditions};

    fn make_mc(dir_pct: f64, range_pct: f64, de: f64, fr_bps: f64) -> MarketConditions {
        let signed_dir_pct = dir_pct;
        let dir_pct = dir_pct.abs();
        let signed_fr_bps = fr_bps;
        let fr_bps = fr_bps.abs();
        let range_position = if signed_dir_pct > 0.0 {
            0.75
        } else if signed_dir_pct < 0.0 {
            0.25
        } else {
            0.5
        };
        let close_alignment = if signed_dir_pct > 0.0 {
            range_position
        } else if signed_dir_pct < 0.0 {
            1.0 - range_position
        } else {
            0.5
        };
        let dir_norm = (dir_pct / 6.0).clamp(0.0, 1.0);
        let range_norm = (range_pct / 12.0).clamp(0.0, 1.0);
        let range_mid_score = (1.0 - (range_position - 0.5_f64).abs() * 2.0).clamp(0.0, 1.0);
        let trend_score = (0.45 * de + 0.35 * dir_norm + 0.20 * close_alignment).clamp(0.0, 1.0);
        let range_score =
            ((0.70 * (1.0 - de) + 0.30 * range_mid_score) * range_norm).clamp(0.0, 1.0);
        let shock_score =
            (de * (dir_pct / 8.0).clamp(0.0, 1.0) * (0.5 + 0.5 * close_alignment)).clamp(0.0, 1.0);
        let crowding_score =
            (((fr_bps - 8.0) / 20.0).clamp(0.0, 1.0) * (0.5 + 0.5 * trend_score)).clamp(0.0, 1.0);
        let reversal_risk_score =
            (trend_score * (1.0 - close_alignment) * (dir_pct / 4.0).clamp(0.0, 1.0))
                .clamp(0.0, 1.0);
        let trend_phase = if shock_score >= 0.55 && crowding_score >= 0.45 {
            "crowded_shock"
        } else if shock_score >= 0.55 {
            "one_way_shock"
        } else if reversal_risk_score >= 0.30 {
            "failed_trend"
        } else if trend_score >= 0.60 {
            "clean_trend"
        } else if range_score >= 0.35 {
            "range_bound"
        } else if range_pct < 3.0 {
            "quiet"
        } else {
            "mixed"
        }
        .to_string();
        MarketConditions {
            signed_dir_pct,
            dir_pct,
            range_pct,
            de,
            fr_bps,
            signed_fr_bps,
            trend_score,
            range_score,
            shock_score,
            close_alignment,
            range_position,
            crowding_score,
            reversal_risk_score,
            trend_phase,
            turnover_24h: 60_000_000.0,
        }
    }

    #[test]
    fn test_market_judgment_blocks_grid_in_one_way_trend() {
        let mc = make_mc(4.2, 8.0, 0.72, 5.0);
        let fitness = compute_fitness(&mc);
        let judgments = build_strategy_judgments(
            &fitness,
            &mc,
            "BIOUSDT",
            &EdgeEstimates::empty(),
            &EdgeRoutingConfig::default(),
            &MarketJudgmentConfig::default(),
        );
        let grid = judgments.get("grid_trading").expect("grid judgment");
        assert_eq!(grid.market_status, "blocked");
        assert_eq!(grid.route_mode, "market_gate");
        assert!(
            grid.route_reason.contains("grid_trend_mismatch"),
            "{}",
            grid.route_reason
        );
    }

    #[test]
    fn test_market_judgment_watches_immature_negative_edge_without_hard_block() {
        let estimates = EdgeEstimates::load_from_str(
            r#"{"grid_trading::BIOUSDT":{"shrunk_bps":-6.0,"n":16,"std_bps":20.0}}"#,
        )
        .expect("edge estimates");
        let mc = make_mc(1.2, 7.0, 0.20, 5.0);
        let fitness = compute_fitness(&mc);
        let judgments = build_strategy_judgments(
            &fitness,
            &mc,
            "BIOUSDT",
            &estimates,
            &EdgeRoutingConfig::default(),
            &MarketJudgmentConfig::default(),
        );
        let grid = judgments.get("grid_trading").expect("grid judgment");
        assert_eq!(grid.market_status, "edge_watch");
        assert_eq!(grid.route_mode, "exploration");
        assert!(
            grid.route_reason.contains("immature_negative_watch"),
            "{}",
            grid.route_reason
        );
    }

    #[test]
    fn test_immature_negative_does_not_override_market_hard_gate() {
        let estimates = EdgeEstimates::load_from_str(
            r#"{"grid_trading::BIOUSDT":{"shrunk_bps":-6.0,"n":16,"std_bps":20.0}}"#,
        )
        .expect("edge estimates");
        let mc = make_mc(8.2, 9.0, 0.82, 5.0);
        let fitness = compute_fitness(&mc);
        let judgments = build_strategy_judgments(
            &fitness,
            &mc,
            "BIOUSDT",
            &estimates,
            &EdgeRoutingConfig::default(),
            &MarketJudgmentConfig::default(),
        );
        let grid = judgments.get("grid_trading").expect("grid judgment");
        assert_eq!(grid.market_status, "blocked");
        assert_eq!(grid.route_mode, "market_gate");
        assert!(
            grid.route_reason.contains("grid_trend_mismatch"),
            "{}",
            grid.route_reason
        );
    }

    #[test]
    fn test_funding_momentum_caution_does_not_hard_block_demo_learning() {
        let mc = make_mc(26.0, 30.0, 0.90, -1.0);
        let fitness = compute_fitness(&mc);
        let judgments = build_strategy_judgments(
            &fitness,
            &mc,
            "BIOUSDT",
            &EdgeEstimates::empty(),
            &EdgeRoutingConfig::default(),
            &MarketJudgmentConfig::default(),
        );
        let funding = judgments.get("funding_arb").expect("funding judgment");
        assert_eq!(funding.market_status, "momentum_caution");
        assert_ne!(funding.route_mode, "market_gate");
        assert!(
            funding.route_reason.contains("funding_momentum_caution"),
            "{}",
            funding.route_reason
        );
    }
}
