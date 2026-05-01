//! Scanner-side strategy policy sync.
//! scanner 側策略政策同步。
//!
//! MODULE_NOTE (EN): Bridges RiskConfig's per-strategy symbol policy into the
//! scanner's route eligibility layer. Scanner selection is shared across
//! paper/demo/live, so a route is removed from scanner best-route contention
//! only when every target RiskConfig would reject that strategy-symbol fresh
//! entry. The per-engine dispatch path still pre-gates with its own current
//! RiskConfig snapshot before any DB intent/risk verdict is written.
//!
//! MODULE_NOTE (中): 將 RiskConfig 的 per-strategy symbol policy 接入 scanner
//! route eligibility。scanner selection 由 paper/demo/live 共用，因此只有當
//! 所有目標 RiskConfig 都會拒絕某 strategy-symbol 新開倉時，才把該 route 從
//! scanner best-route 競爭中移除。逐 engine dispatch 仍會用自身最新
//! RiskConfig 在寫入 intent/risk verdict 前做 pre-gate。

use crate::config::{per_strategy_new_entry_rejection, ConfigStore, RiskConfig};
use crate::scanner::types::StrategyRouteJudgment;
use std::collections::BTreeMap;
use std::sync::Arc;

/// RiskConfig stores used by ScannerRunner to build a fresh policy each scan.
/// ScannerRunner 每輪 scan 用於生成當前策略政策的 RiskConfig stores。
#[derive(Clone)]
pub struct ScannerStrategyPolicyStores {
    paper: Arc<ConfigStore<RiskConfig>>,
    demo: Arc<ConfigStore<RiskConfig>>,
    live: Arc<ConfigStore<RiskConfig>>,
}

impl ScannerStrategyPolicyStores {
    pub fn new(
        paper: Arc<ConfigStore<RiskConfig>>,
        demo: Arc<ConfigStore<RiskConfig>>,
        live: Arc<ConfigStore<RiskConfig>>,
    ) -> Self {
        Self { paper, demo, live }
    }

    pub fn load_policy(&self) -> ScannerStrategyPolicy {
        let paper = self.paper.load();
        let demo = self.demo.load();
        let live = self.live.load();
        ScannerStrategyPolicy::from_risk_configs([
            ("paper", paper.as_ref()),
            ("demo", demo.as_ref()),
            ("live", live.as_ref()),
        ])
    }
}

/// Snapshot of per-strategy policy at one scanner cycle.
/// 單輪 scanner 週期中的 per-strategy policy 快照。
#[derive(Debug, Clone, Default)]
pub struct ScannerStrategyPolicy {
    targets: Vec<TargetPolicy>,
}

#[derive(Debug, Clone)]
struct TargetPolicy {
    mode: &'static str,
    risk_config: RiskConfig,
}

impl ScannerStrategyPolicy {
    pub fn from_risk_configs<'a>(
        configs: impl IntoIterator<Item = (&'static str, &'a RiskConfig)>,
    ) -> Self {
        Self {
            targets: configs
                .into_iter()
                .map(|(mode, risk_config)| TargetPolicy {
                    mode,
                    risk_config: risk_config.clone(),
                })
                .collect(),
        }
    }

    /// Scanner-level rejection: only reject when all target modes reject.
    /// scanner 層拒絕：只有所有目標模式都拒絕時才拒。
    pub fn route_rejection(&self, strategy: &str, symbol: &str) -> Option<String> {
        if self.targets.is_empty() {
            return None;
        }

        let mut rejects = Vec::new();
        for target in &self.targets {
            match per_strategy_new_entry_rejection(&target.risk_config, strategy, symbol) {
                Some(reason) => rejects.push(format!("{}:{reason}", target.mode)),
                None => return None,
            }
        }

        Some(format!(
            "risk_policy_all_targets_blocked:{}",
            rejects.join("|")
        ))
    }
}

/// Apply strategy policy to scanner route judgments.
/// 將策略政策套用到 scanner route judgments。
pub(crate) fn apply_strategy_policy(
    symbol: &str,
    judgments: &mut BTreeMap<String, StrategyRouteJudgment>,
    policy: &ScannerStrategyPolicy,
) {
    for (strategy, judgment) in judgments.iter_mut() {
        if let Some(reason) = policy.route_rejection(strategy, symbol) {
            judgment.final_score = 0.0;
            judgment.market_status = "policy_blocked".to_string();
            judgment.route_mode = "risk_policy_gate".to_string();
            judgment.route_reason = reason;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::StrategyOverride;
    use crate::edge_estimates::EdgeEstimates;
    use crate::market_data_client::types::TickerInfo;
    use crate::scanner::config::{EdgeRoutingConfig, HardFilters, MarketJudgmentConfig};
    use crate::scanner::scorer::score_ticker_with_policy;
    use crate::scanner::types::StrategyCategory;

    fn risk_with_blocks(blocks: &[(&str, &str)]) -> RiskConfig {
        let mut cfg = RiskConfig::default();
        for (strategy, symbol) in blocks {
            cfg.per_strategy.insert(
                (*strategy).to_string(),
                StrategyOverride {
                    blocked_symbols: Some(vec![(*symbol).to_string()]),
                    ..StrategyOverride::default()
                },
            );
        }
        cfg
    }

    fn risk_with_block(strategy: &str, symbol: &str) -> RiskConfig {
        risk_with_blocks(&[(strategy, symbol)])
    }

    fn make_ticker(symbol: &str) -> TickerInfo {
        TickerInfo {
            symbol: symbol.to_string(),
            last_price: 100.0,
            bid1_price: 99.99,
            ask1_price: 100.01,
            volume_24h: 0.0,
            turnover_24h: 120_000_000.0,
            high_price_24h: 106.0,
            low_price_24h: 100.0,
            prev_price_24h: 95.0,
            open_interest: 0.0,
            funding_rate: 0.0,
            next_funding_time: String::new(),
            price_change_24h_pct: 0.05,
        }
    }

    #[test]
    fn policy_blocks_only_when_all_targets_reject() {
        let paper = risk_with_block("ma_crossover", "NAORISUSDT");
        let demo = risk_with_block("ma_crossover", "NAORISUSDT");
        let live = risk_with_block("ma_crossover", "NAORISUSDT");
        let policy = ScannerStrategyPolicy::from_risk_configs([
            ("paper", &paper),
            ("demo", &demo),
            ("live", &live),
        ]);

        let reason = policy
            .route_rejection("ma_crossover", "NAORISUSDT")
            .expect("all targets blocked");
        assert!(reason.contains("risk_policy_all_targets_blocked"));
        assert!(reason.contains("demo:NAORISUSDT blocked"));
    }

    #[test]
    fn policy_allows_when_any_target_allows() {
        let paper = risk_with_block("ma_crossover", "NAORISUSDT");
        let demo = RiskConfig::default();
        let live = risk_with_block("ma_crossover", "NAORISUSDT");
        let policy = ScannerStrategyPolicy::from_risk_configs([
            ("paper", &paper),
            ("demo", &demo),
            ("live", &live),
        ]);

        assert!(policy
            .route_rejection("ma_crossover", "NAORISUSDT")
            .is_none());
    }

    #[test]
    fn scoring_skips_policy_blocked_best_route() {
        let paper = risk_with_block("ma_crossover", "NAORISUSDT");
        let demo = risk_with_block("ma_crossover", "NAORISUSDT");
        let live = risk_with_block("ma_crossover", "NAORISUSDT");
        let policy = ScannerStrategyPolicy::from_risk_configs([
            ("paper", &paper),
            ("demo", &demo),
            ("live", &live),
        ]);

        let scored = score_ticker_with_policy(
            &make_ticker("NAORISUSDT"),
            2.0,
            &EdgeEstimates::empty(),
            &HardFilters::default(),
            &EdgeRoutingConfig::default(),
            &MarketJudgmentConfig::default(),
            &policy,
        )
        .expect("non-policy routes remain eligible");

        assert_ne!(scored.best_strategy, StrategyCategory::MaCrossover);
        assert_eq!(
            scored.strategy_judgments["ma_crossover"].route_mode,
            "risk_policy_gate"
        );
    }

    #[test]
    fn scoring_drops_symbol_when_all_selectable_routes_policy_blocked() {
        let blocks = [
            ("ma_crossover", "NAORISUSDT"),
            ("grid_trading", "NAORISUSDT"),
            ("bb_reversion", "NAORISUSDT"),
            ("bb_breakout", "NAORISUSDT"),
            ("funding_arb", "NAORISUSDT"),
        ];
        let paper = risk_with_blocks(&blocks);
        let demo = risk_with_blocks(&blocks);
        let live = risk_with_blocks(&blocks);
        let policy = ScannerStrategyPolicy::from_risk_configs([
            ("paper", &paper),
            ("demo", &demo),
            ("live", &live),
        ]);

        let scored = score_ticker_with_policy(
            &make_ticker("NAORISUSDT"),
            2.0,
            &EdgeEstimates::empty(),
            &HardFilters::default(),
            &EdgeRoutingConfig::default(),
            &MarketJudgmentConfig::default(),
            &policy,
        );

        assert!(scored.is_none());
    }
}
