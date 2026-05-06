//! Scanner opportunity evaluation — shadow-only current opportunity math.
//! scanner 機會評估 — shadow-only 當前機會數學。
//!
//! MODULE_NOTE (EN): Pure functions only. This module does not reject orders
//!   and does not mutate scanner route scores; it emits auditable fields that
//!   downstream admission/replay layers can compare against realized outcomes.
//! MODULE_NOTE (中): 僅純函數。本模組不拒單、不改 scanner route score；只輸出
//!   可審計欄位，供下游 admission/replay 與實現結果對照。

use crate::edge_estimates::CellEstimate;
use crate::edge_predictor::gate::estimate_round_trip_cost_bps;
use crate::market_data_client::types::TickerInfo;
use crate::scanner::config::OpportunityConfig;
use crate::scanner::scorer::MarketConditions;
use crate::scanner::types::{OpportunityComponents, OpportunityDecision, StrategyRouteJudgment};

/// Cost prior supplied by runtime fee/calibration sources.
/// Runtime fee / calibration 來源提供的成本先驗。
#[derive(Debug, Clone, Copy)]
pub(crate) struct OpportunityCostPrior {
    pub one_way_fee_bps: f64,
    pub slippage_buffer_bps: f64,
    pub source: &'static str,
}

fn finite_some(value: f64) -> Option<f64> {
    if value.is_finite() {
        Some(value)
    } else {
        None
    }
}

fn spread_bps(ticker: &TickerInfo) -> f64 {
    let mid = (ticker.bid1_price + ticker.ask1_price) / 2.0;
    if mid <= 0.0 {
        return 0.0;
    }
    ((ticker.ask1_price - ticker.bid1_price).max(0.0) / mid * 10_000.0).max(0.0)
}

fn bps_to_rate(bps: f64) -> f64 {
    bps / 10_000.0
}

fn config_cost_prior(cfg: &OpportunityConfig) -> OpportunityCostPrior {
    OpportunityCostPrior {
        one_way_fee_bps: cfg.one_way_fee_bps,
        slippage_buffer_bps: cfg.slippage_buffer_bps,
        source: "scanner_config_static",
    }
}

fn round_trip_fee_slippage_cost_bps(prior: OpportunityCostPrior) -> f64 {
    estimate_round_trip_cost_bps(
        bps_to_rate(prior.one_way_fee_bps),
        bps_to_rate(prior.slippage_buffer_bps),
    )
}

fn data_quality_score(mc: &MarketConditions, spread_bps: f64, cfg: &OpportunityConfig) -> f64 {
    let spread_score = (1.0 - spread_bps / cfg.spread_quality_reference_bps).clamp(0.0, 1.0);
    let turnover_score = if mc.turnover_24h >= 100_000_000.0 {
        1.0
    } else if mc.turnover_24h >= 50_000_000.0 {
        0.8
    } else {
        0.5
    };
    let regime_score =
        (1.0 - 0.35 * mc.shock_score - 0.20 * mc.crowding_score - 0.20 * mc.reversal_risk_score)
            .clamp(0.0, 1.0);
    (0.45 * spread_score + 0.35 * turnover_score + 0.20 * regime_score).clamp(0.0, 1.0)
}

fn historical_lcb_bps(cell: &CellEstimate, cfg: &OpportunityConfig) -> Option<f64> {
    if cfg.historical_lcb_z <= 0.0 || cell.n_trades == 0 {
        return None;
    }
    let sample_std = if cell.std_bps.is_finite() && cell.std_bps > 0.0 {
        cell.std_bps
    } else {
        cfg.historical_min_std_bps
    };
    let std = sample_std.max(cfg.historical_min_std_bps);
    finite_some(cell.shrunk_bps - cfg.historical_lcb_z * std / (cell.n_trades as f64).sqrt())
}

fn calibration_weight(cell: Option<&CellEstimate>, cfg: &OpportunityConfig) -> f64 {
    let Some(cell) = cell else {
        return 0.0;
    };
    let sample_weight =
        (cell.n_trades as f64 / f64::from(cfg.min_calibration_trades)).clamp(0.0, 1.0);
    let validation_weight = if cell.validation_passed || cell.shrunk_bps <= 0.0 {
        1.0
    } else {
        0.5
    };
    (sample_weight * validation_weight).clamp(0.0, 1.0)
}

fn admission_hint(
    judgment: &StrategyRouteJudgment,
    lcb_bps: Option<f64>,
    calibration_weight: f64,
    cfg: &OpportunityConfig,
) -> &'static str {
    if !cfg.enabled {
        return "shadow_disabled";
    }
    match judgment.route_mode.as_str() {
        "risk_policy_gate" => return "tradability_block",
        "market_gate" => return "opportunity_weak",
        "exploration_only" => {
            if matches!(
                judgment.edge_status.as_str(),
                "robust_negative" | "posterior_negative"
            ) {
                return "calibration_block";
            }
            return "exploration_candidate";
        }
        _ => {}
    }
    match lcb_bps {
        Some(v) if v > 0.0 && calibration_weight >= 1.0 => "opportunity_positive",
        Some(v) if v > 0.0 => "exploration_candidate",
        Some(_) => "opportunity_weak",
        None => "shadow_only",
    }
}

/// Evaluate the current scanner opportunity for one strategy-symbol route.
/// 評估單個 strategy-symbol route 的當前 scanner opportunity。
pub(crate) fn evaluate_opportunity(
    strategy: &str,
    judgment: &StrategyRouteJudgment,
    mc: &MarketConditions,
    ticker: &TickerInfo,
    cell: Option<&CellEstimate>,
    cfg: &OpportunityConfig,
    cost_prior: Option<OpportunityCostPrior>,
) -> OpportunityDecision {
    let spread = spread_bps(ticker);
    let cost_prior = cost_prior.unwrap_or_else(|| config_cost_prior(cfg));
    let expected_execution_cost_bps = round_trip_fee_slippage_cost_bps(cost_prior) + spread;
    let cost_uncertainty_bps = cfg.cost_uncertainty_bps + 0.5 * spread;
    let quality = data_quality_score(mc, spread, cfg);

    let gross_current_opportunity_bps =
        (judgment.fitness_score.max(0.0) * cfg.fitness_gross_bps_per_score).max(0.0);

    let historical_edge_bps = cell.map(|c| c.shrunk_bps);
    let historical_edge_n = cell
        .map(|c| c.n_trades.min(u64::from(u32::MAX)) as u32)
        .unwrap_or(0);
    let historical_edge_lcb = cell.and_then(|c| historical_lcb_bps(c, cfg));
    let hist_weight = calibration_weight(cell, cfg);

    let mut uncertainty_buffer_bps = cfg.base_uncertainty_bps
        + 5.0 * mc.shock_score
        + 3.0 * mc.crowding_score
        + 3.0 * mc.reversal_risk_score
        + (1.0 - quality) * 5.0;

    if let Some(lcb) = historical_edge_lcb {
        if lcb < 0.0 {
            uncertainty_buffer_bps += (-lcb) * hist_weight * cfg.historical_negative_penalty_weight;
        } else if lcb > expected_execution_cost_bps {
            uncertainty_buffer_bps = (uncertainty_buffer_bps
                - cfg.positive_history_uncertainty_discount_bps * hist_weight)
                .max(0.0);
        }
    }

    let current_q10_bps = gross_current_opportunity_bps - uncertainty_buffer_bps;
    let cost_q90_bps = expected_execution_cost_bps + cost_uncertainty_bps;
    let opportunity_lcb_bps = if cfg.enabled {
        finite_some(current_q10_bps - cost_q90_bps)
    } else {
        None
    };
    let score = opportunity_lcb_bps
        .map(|lcb| (50.0 + lcb * cfg.opportunity_score_bps_multiplier).clamp(0.0, 100.0))
        .unwrap_or(0.0);
    let hint = admission_hint(judgment, opportunity_lcb_bps, hist_weight, cfg).to_string();
    let canary_block_new_entry = cfg.canary_block_new_entries
        && matches!(
            hint.as_str(),
            "opportunity_weak" | "calibration_block" | "tradability_block"
        )
        && opportunity_lcb_bps.map_or(true, |v| v <= 0.0);
    let reason = format!(
        "{hint}:strategy={strategy} fitness={:.2} gross={:.2} cost_q90={:.2} lcb={} cost_model=edge_predictor_round_trip+spread cost_source={} route_mode={} edge_status={} canary_block={}",
        judgment.fitness_score,
        gross_current_opportunity_bps,
        cost_q90_bps,
        opportunity_lcb_bps
            .map(|v| format!("{v:.2}"))
            .unwrap_or_else(|| "none".to_string()),
        cost_prior.source,
        judgment.route_mode,
        judgment.edge_status,
        canary_block_new_entry,
    );

    OpportunityDecision {
        opportunity_score: score,
        opportunity_lcb_bps,
        admission_hint: hint,
        canary_block_new_entry,
        reason,
        components: OpportunityComponents {
            market_structure_score: judgment.fitness_score,
            strategy_fitness_score: judgment.fitness_score,
            gross_current_opportunity_bps: finite_some(gross_current_opportunity_bps),
            expected_execution_cost_bps: finite_some(expected_execution_cost_bps),
            cost_source: cost_prior.source.to_string(),
            cost_uncertainty_bps: finite_some(cost_uncertainty_bps),
            uncertainty_buffer_bps: finite_some(uncertainty_buffer_bps),
            historical_edge_bps,
            historical_edge_n,
            historical_edge_lcb_bps: historical_edge_lcb,
            data_quality_score: quality,
            calibration_weight: hist_weight,
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scanner::config::OpportunityConfig;

    fn make_ticker() -> TickerInfo {
        TickerInfo {
            symbol: "BTCUSDT".to_string(),
            last_price: 100.0,
            bid1_price: 99.99,
            ask1_price: 100.01,
            volume_24h: 0.0,
            turnover_24h: 120_000_000.0,
            high_price_24h: 106.0,
            low_price_24h: 96.0,
            prev_price_24h: 98.0,
            open_interest: 0.0,
            funding_rate: 0.0,
            next_funding_time: String::new(),
            price_change_24h_pct: 0.03,
        }
    }

    fn make_mc() -> MarketConditions {
        crate::scanner::scorer::compute_market_conditions(&make_ticker())
    }

    fn make_judgment(fitness_score: f64) -> StrategyRouteJudgment {
        StrategyRouteJudgment {
            strategy: "ma_crossover".to_string(),
            fitness_score,
            final_score: fitness_score,
            edge_bps: None,
            edge_bonus: 0.0,
            edge_n: 0,
            edge_status: "unexplored".to_string(),
            route_mode: "exploration".to_string(),
            market_status: "compatible".to_string(),
            route_reason: "test".to_string(),
            opportunity: None,
        }
    }

    #[test]
    fn test_high_fitness_can_emit_positive_or_exploration_opportunity() {
        let decision = evaluate_opportunity(
            "ma_crossover",
            &make_judgment(95.0),
            &make_mc(),
            &make_ticker(),
            None,
            &OpportunityConfig::default(),
            None,
        );
        assert!(decision.opportunity_lcb_bps.unwrap() > 0.0);
        assert_eq!(decision.admission_hint, "exploration_candidate");
        assert!(decision.components.expected_execution_cost_bps.unwrap() > 0.0);
    }

    #[test]
    fn test_cost_model_reuses_edge_predictor_round_trip_definition() {
        let cfg = OpportunityConfig::default();
        let decision = evaluate_opportunity(
            "ma_crossover",
            &make_judgment(95.0),
            &make_mc(),
            &make_ticker(),
            None,
            &cfg,
            None,
        );
        let shared_round_trip = estimate_round_trip_cost_bps(
            bps_to_rate(cfg.one_way_fee_bps),
            bps_to_rate(cfg.slippage_buffer_bps),
        );
        let expected = shared_round_trip + spread_bps(&make_ticker());
        let actual = decision.components.expected_execution_cost_bps.unwrap();
        assert!((actual - expected).abs() < 1e-9);
        assert!(decision
            .reason
            .contains("cost_model=edge_predictor_round_trip+spread"));
        assert_eq!(
            decision.components.cost_source,
            "scanner_config_static".to_string()
        );
    }

    #[test]
    fn test_cost_model_accepts_runtime_fee_prior() {
        let cfg = OpportunityConfig::default();
        let prior = OpportunityCostPrior {
            one_way_fee_bps: 5.5,
            slippage_buffer_bps: 1.0,
            source: "account_manager_taker_fee",
        };
        let decision = evaluate_opportunity(
            "ma_crossover",
            &make_judgment(95.0),
            &make_mc(),
            &make_ticker(),
            None,
            &cfg,
            Some(prior),
        );
        let expected = estimate_round_trip_cost_bps(bps_to_rate(5.5), bps_to_rate(1.0))
            + spread_bps(&make_ticker());
        let actual = decision.components.expected_execution_cost_bps.unwrap();
        assert!((actual - expected).abs() < 1e-9);
        assert_eq!(decision.components.cost_source, "account_manager_taker_fee");
        assert!(decision
            .reason
            .contains("cost_source=account_manager_taker_fee"));
    }

    #[test]
    fn test_canary_block_new_entry_when_enabled_for_nonpositive_lcb() {
        let cfg = OpportunityConfig {
            canary_block_new_entries: true,
            ..OpportunityConfig::default()
        };
        let decision = evaluate_opportunity(
            "ma_crossover",
            &make_judgment(20.0),
            &make_mc(),
            &make_ticker(),
            None,
            &cfg,
            None,
        );
        assert!(decision.opportunity_lcb_bps.unwrap() <= 0.0);
        assert_eq!(decision.admission_hint, "opportunity_weak");
        assert!(decision.canary_block_new_entry);
        assert!(decision.reason.contains("canary_block=true"));
    }

    #[test]
    fn test_risk_policy_gate_maps_to_tradability_block_without_changing_route() {
        let mut judgment = make_judgment(95.0);
        judgment.route_mode = "risk_policy_gate".to_string();
        let decision = evaluate_opportunity(
            "ma_crossover",
            &judgment,
            &make_mc(),
            &make_ticker(),
            None,
            &OpportunityConfig::default(),
            None,
        );
        assert_eq!(decision.admission_hint, "tradability_block");
        assert_eq!(judgment.route_mode, "risk_policy_gate");
    }

    #[test]
    fn test_mature_negative_history_penalizes_uncertainty() {
        let cfg = OpportunityConfig::default();
        let cell = CellEstimate {
            shrunk_bps: -20.0,
            win_rate: 0.3,
            n_trades: 60,
            std_bps: 20.0,
            validation_passed: true,
            validation_reason: "test".to_string(),
        };
        let decision = evaluate_opportunity(
            "ma_crossover",
            &make_judgment(95.0),
            &make_mc(),
            &make_ticker(),
            Some(&cell),
            &cfg,
            None,
        );
        assert!(decision.components.historical_edge_lcb_bps.unwrap() < 0.0);
        assert!(decision.components.calibration_weight > 0.9);
        assert!(decision.components.uncertainty_buffer_bps.unwrap() > cfg.base_uncertainty_bps);
    }
}
