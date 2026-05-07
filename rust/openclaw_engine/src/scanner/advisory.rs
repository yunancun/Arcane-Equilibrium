//! Scanner advisory event builders.
//! scanner advisory 事件構建器。
//!
//! MODULE_NOTE (EN): Pure conversion helpers only. This module emits scanner
//!   evidence such as `OpportunityDecay`; it must not dispatch orders or
//!   convert scanner ranking changes into close/reduce actions.
//! MODULE_NOTE (中): 僅純轉換 helper。本模組 emit scanner evidence，例如
//!   `OpportunityDecay`；不得派單，也不得把 scanner 排名變化直接轉為
//!   平倉/減倉動作。

use crate::scanner::types::{
    OpportunityDecay, OpportunityDecayReason, ScanResult, ScannerAuthorityMode, ScoredSymbol,
};
use std::collections::{HashMap, HashSet};

/// Build advisory decay events by comparing the previous scanner view with the
/// current selected top set.
/// 比較上一輪 scanner view 與本輪 selected top set，構建 advisory decay 事件。
pub(crate) fn build_opportunity_decays(
    previous_scan: Option<&ScanResult>,
    selected: &[ScoredSymbol],
    scan_id: &str,
    now_ms: u64,
    open_positions: &HashSet<String>,
    added: &[String],
    removed: &[String],
    pinned_symbols: &[String],
    authority_mode: ScannerAuthorityMode,
) -> Vec<OpportunityDecay> {
    let Some(previous_scan) = previous_scan else {
        return Vec::new();
    };

    let pinned: HashSet<&str> = pinned_symbols.iter().map(String::as_str).collect();
    let removed_set: HashSet<&str> = removed.iter().map(String::as_str).collect();
    let selected_symbols: Vec<String> = selected.iter().map(|c| c.symbol.clone()).collect();
    let previous_ranked = ranked_candidates(&previous_scan.candidates);
    let current_ranked = ranked_candidates(selected);
    let current_by_symbol: HashMap<&str, (u32, &ScoredSymbol)> = current_ranked
        .iter()
        .map(|(rank, candidate)| (candidate.symbol.as_str(), (*rank, *candidate)))
        .collect();

    let mut decays = Vec::new();
    for (previous_rank, previous_candidate) in previous_ranked {
        let symbol = previous_candidate.symbol.as_str();
        if pinned.contains(symbol) {
            continue;
        }

        let current = current_by_symbol.get(symbol).copied();
        let reason = match current {
            Some((_, current_candidate))
                if current_candidate.final_score < previous_candidate.final_score =>
            {
                OpportunityDecayReason::ScoreWeakened
            }
            Some(_) => continue,
            None if removed_set.contains(symbol) && !added.is_empty() => {
                OpportunityDecayReason::Displaced
            }
            None => OpportunityDecayReason::ExitedTopSet,
        };

        let has_open_position = open_positions.contains(symbol);
        let (current_rank, current_score) = current
            .map(|(rank, candidate)| (Some(rank), Some(candidate.final_score)))
            .unwrap_or((None, None));
        let strategy = previous_candidate
            .best_strategy
            .as_estimate_key()
            .to_string();

        decays.push(OpportunityDecay {
            schema_version: "1.0".to_string(),
            decay_id: format!("oppdecay:{scan_id}:{symbol}:{}", reason.as_str()),
            candidate_id: Some(format!(
                "oppcand:{}:{}:{}",
                previous_scan.scan_id, previous_candidate.symbol, strategy
            )),
            scan_id: scan_id.to_string(),
            decay_ts_ms: now_ms,
            symbol: previous_candidate.symbol.clone(),
            strategy: Some(strategy),
            authority_mode,
            reason,
            previous_score: Some(previous_candidate.final_score),
            current_score,
            previous_rank: Some(previous_rank),
            current_rank,
            has_open_position,
            position_review_required: has_open_position,
            auto_close_allowed: false,
            evidence: serde_json::json!({
                "source": "scanner_advisory_decay",
                "previous_scan_id": previous_scan.scan_id,
                "selected_symbols": selected_symbols,
                "replacement_symbols": added,
                "removed_this_cycle": removed_set.contains(symbol),
                "review_only": has_open_position,
                "position_review_input": has_open_position,
                "close_dispatch_allowed": false,
            }),
        });
    }

    decays
}

fn ranked_candidates(candidates: &[ScoredSymbol]) -> Vec<(u32, &ScoredSymbol)> {
    let mut ranked: Vec<&ScoredSymbol> = candidates.iter().collect();
    ranked.sort_by(|a, b| b.final_score.total_cmp(&a.final_score));
    ranked
        .into_iter()
        .enumerate()
        .map(|(idx, candidate)| ((idx + 1) as u32, candidate))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scanner::types::{StrategyCategory, StrategyRouteJudgment};
    use std::collections::BTreeMap;

    fn make_scored(symbol: &str, score: f64) -> ScoredSymbol {
        let mut strategy_judgments = BTreeMap::new();
        strategy_judgments.insert(
            "grid_trading".to_string(),
            StrategyRouteJudgment {
                strategy: "grid_trading".to_string(),
                fitness_score: score - 5.0,
                final_score: score,
                edge_bps: None,
                edge_bonus: 5.0,
                edge_n: 0,
                edge_status: "unexplored".to_string(),
                route_mode: "exploration".to_string(),
                market_status: "compatible".to_string(),
                route_reason: "test".to_string(),
                opportunity: None,
            },
        );
        ScoredSymbol {
            symbol: symbol.to_string(),
            final_score: score,
            raw_score: score - 5.0,
            best_strategy: StrategyCategory::GridTrading,
            f_ma: 0.0,
            f_grid: score - 5.0,
            f_bbrv: 0.0,
            f_bkout: 0.0,
            f_funding_arb: 0.0,
            de: 0.2,
            dir_pct: 2.0,
            range_pct: 8.0,
            fr_bps: 5.0,
            signed_dir_pct: 2.0,
            trend_score: 0.25,
            range_score: 0.5,
            shock_score: 0.05,
            close_alignment: 0.60,
            range_position: 0.60,
            crowding_score: 0.0,
            reversal_risk_score: 0.0,
            market_regime: "range_bound".to_string(),
            trend_phase: "range_bound".to_string(),
            turnover_24h: 60_000_000.0,
            edge_bonus: 5.0,
            edge_n: 0,
            edge_bps: None,
            edge_status: "unexplored".to_string(),
            route_mode: "exploration".to_string(),
            market_status: "compatible".to_string(),
            route_reason: "test".to_string(),
            strategy_judgments,
            beta_proxy: Some(0.5),
            sector: "other".to_string(),
        }
    }

    fn make_scan(scan_id: &str, candidates: Vec<ScoredSymbol>) -> ScanResult {
        ScanResult {
            scan_ts_ms: 1_000,
            scan_id: scan_id.to_string(),
            active_symbols: candidates.iter().map(|c| c.symbol.clone()).collect(),
            added: Vec::new(),
            removed: Vec::new(),
            candidates,
            opportunity_decays: Vec::new(),
            rejected_count: 0,
            scan_duration_ms: 1,
        }
    }

    #[test]
    fn emits_score_weakened_when_selected_score_drops() {
        let previous = make_scan("scan-prev", vec![make_scored("SOLUSDT", 80.0)]);
        let selected = vec![make_scored("SOLUSDT", 70.0)];

        let decays = build_opportunity_decays(
            Some(&previous),
            &selected,
            "scan-now",
            2_000,
            &HashSet::new(),
            &[],
            &[],
            &[],
            ScannerAuthorityMode::LegacyGate,
        );

        assert_eq!(decays.len(), 1);
        let decay = &decays[0];
        assert_eq!(decay.reason, OpportunityDecayReason::ScoreWeakened);
        assert_eq!(decay.previous_score, Some(80.0));
        assert_eq!(decay.current_score, Some(70.0));
        assert_eq!(decay.previous_rank, Some(1));
        assert_eq!(decay.current_rank, Some(1));
        assert!(!decay.position_review_required);
        assert!(!decay.auto_close_allowed);
    }

    #[test]
    fn open_position_exit_requests_review_without_auto_close() {
        let previous = make_scan("scan-prev", vec![make_scored("SOLUSDT", 80.0)]);
        let selected = vec![make_scored("ADAUSDT", 75.0)];
        let mut open_positions = HashSet::new();
        open_positions.insert("SOLUSDT".to_string());

        let decays = build_opportunity_decays(
            Some(&previous),
            &selected,
            "scan-now",
            2_000,
            &open_positions,
            &[],
            &[],
            &[],
            ScannerAuthorityMode::LegacyGate,
        );

        assert_eq!(decays.len(), 1);
        let decay = &decays[0];
        assert_eq!(decay.reason, OpportunityDecayReason::ExitedTopSet);
        assert!(decay.has_open_position);
        assert!(decay.position_review_required);
        assert!(!decay.auto_close_allowed);
        assert_eq!(decay.current_rank, None);
    }

    #[test]
    fn scanner_removal_of_open_position_is_review_input_not_close_signal() {
        let previous = make_scan("scan-prev", vec![make_scored("SOLUSDT", 80.0)]);
        let selected = Vec::new();
        let mut open_positions = HashSet::new();
        open_positions.insert("SOLUSDT".to_string());

        let decays = build_opportunity_decays(
            Some(&previous),
            &selected,
            "scan-now",
            2_000,
            &open_positions,
            &[],
            &[],
            &[],
            ScannerAuthorityMode::AdvisoryShadow,
        );

        assert_eq!(decays.len(), 1);
        let decay = &decays[0];
        assert_eq!(decay.authority_mode, ScannerAuthorityMode::AdvisoryShadow);
        assert_eq!(decay.reason, OpportunityDecayReason::ExitedTopSet);
        assert!(decay.has_open_position);
        assert!(decay.position_review_required);
        assert!(!decay.auto_close_allowed);
        assert_eq!(decay.evidence["position_review_input"], true);
        assert_eq!(decay.evidence["close_dispatch_allowed"], false);
    }

    #[test]
    fn removed_symbol_with_replacement_is_displaced() {
        let previous = make_scan("scan-prev", vec![make_scored("SOLUSDT", 80.0)]);
        let selected = vec![make_scored("ADAUSDT", 95.0)];
        let added = vec!["ADAUSDT".to_string()];
        let removed = vec!["SOLUSDT".to_string()];

        let decays = build_opportunity_decays(
            Some(&previous),
            &selected,
            "scan-now",
            2_000,
            &HashSet::new(),
            &added,
            &removed,
            &[],
            ScannerAuthorityMode::LegacyGate,
        );

        assert_eq!(decays.len(), 1);
        let decay = &decays[0];
        assert_eq!(decay.reason, OpportunityDecayReason::Displaced);
        assert_eq!(decay.evidence["replacement_symbols"][0], "ADAUSDT");
        assert_eq!(decay.evidence["removed_this_cycle"], true);
        assert!(!decay.auto_close_allowed);
    }

    #[test]
    fn pinned_symbols_do_not_emit_top_set_decay() {
        let previous = make_scan("scan-prev", vec![make_scored("BTCUSDT", 80.0)]);

        let decays = build_opportunity_decays(
            Some(&previous),
            &[],
            "scan-now",
            2_000,
            &HashSet::new(),
            &[],
            &[],
            &["BTCUSDT".to_string()],
            ScannerAuthorityMode::LegacyGate,
        );

        assert!(decays.is_empty());
    }
}
