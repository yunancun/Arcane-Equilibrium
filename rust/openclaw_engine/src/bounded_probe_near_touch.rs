//! Bounded Demo probe near-touch placement Adapter.
//!
//! This Module is pure placement math for the future Cost Gate learning
//! authority path. It stays free of plan reads, ledger writes, Bybit calls,
//! Cost Gate mutation, and probe/order authority grants.
//!
//! 這個 Module 只封裝未來 bounded probe 的近觸碰 post-only 報價數學；
//! 它不接 runtime、交易所或授權開關，避免把 source readiness 誤判成已可下單。

pub const DEFAULT_MAX_FRESH_BBO_AGE_MS: u64 = 1_000;
pub const DEFAULT_MAX_INITIAL_PASSIVE_GAP_BPS: f64 = 75.0;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct BboSnapshot {
    pub best_bid: f64,
    pub best_ask: f64,
    pub tick_size: f64,
    pub observed_at_ms: u64,
}

impl BboSnapshot {
    fn validate(&self) -> Result<(), BoundedProbePlacementSkipReason> {
        if self.observed_at_ms == 0 {
            return Err(BoundedProbePlacementSkipReason::MissingFreshBbo);
        }
        if !self.best_bid.is_finite()
            || !self.best_ask.is_finite()
            || !self.tick_size.is_finite()
            || self.best_bid <= 0.0
            || self.best_ask <= 0.0
            || self.tick_size <= 0.0
            || self.best_bid > self.best_ask
        {
            return Err(BoundedProbePlacementSkipReason::InvalidBbo);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct BoundedProbeNearTouchConfig {
    pub max_fresh_bbo_age_ms: u64,
    pub max_initial_passive_gap_bps: f64,
}

impl BoundedProbeNearTouchConfig {
    pub fn validate(&self) -> Result<(), BoundedProbePlacementSkipReason> {
        if !(1..=60_000).contains(&self.max_fresh_bbo_age_ms) {
            return Err(BoundedProbePlacementSkipReason::InvalidConfig);
        }
        if !self.max_initial_passive_gap_bps.is_finite()
            || !(0.0..=10_000.0).contains(&self.max_initial_passive_gap_bps)
        {
            return Err(BoundedProbePlacementSkipReason::InvalidConfig);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct BoundedProbePlacementRequest {
    pub side_cell_key: String,
    pub is_buy: bool,
    pub now_ms: u64,
    pub bbo: BboSnapshot,
    pub config: BoundedProbeNearTouchConfig,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BoundedProbeOptionalBboPlacementRequest {
    pub side_cell_key: String,
    pub is_buy: bool,
    pub now_ms: u64,
    pub best_bid: Option<f64>,
    pub best_ask: Option<f64>,
    pub tick_size: Option<f64>,
    pub observed_at_ms: Option<u64>,
    pub config: BoundedProbeNearTouchConfig,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BoundedProbePlacementSkipReason {
    InvalidConfig,
    InvalidBbo,
    MissingFreshBbo,
    StaleBbo,
    GapTooWide,
}

impl BoundedProbePlacementSkipReason {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::InvalidConfig => "invalid_config",
            Self::InvalidBbo => "invalid_bbo",
            Self::MissingFreshBbo => "missing_fresh_bbo",
            Self::StaleBbo => "stale_bbo",
            Self::GapTooWide => "gap_too_wide",
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum BoundedProbePlacementDecision {
    Submit(BoundedProbeAttemptPlacement),
    Skip(BoundedProbeTouchabilityBlock),
}

#[derive(Debug, Clone, PartialEq)]
pub struct BoundedProbeAttemptPlacement {
    pub record_type: &'static str,
    pub side_cell_key: String,
    pub limit_price: f64,
    pub touch_gap_bps: f64,
    pub reference_price: f64,
    pub bbo_age_ms: u64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BoundedProbeTouchabilityBlock {
    pub record_type: &'static str,
    pub side_cell_key: String,
    pub reason: BoundedProbePlacementSkipReason,
    pub touch_gap_bps: Option<f64>,
    pub bbo_age_ms: Option<u64>,
}

impl BoundedProbeTouchabilityBlock {
    fn new(
        side_cell_key: &str,
        reason: BoundedProbePlacementSkipReason,
        touch_gap_bps: Option<f64>,
        bbo_age_ms: Option<u64>,
    ) -> Self {
        Self {
            record_type: "bounded_probe_touchability_block",
            side_cell_key: side_cell_key.to_string(),
            reason,
            touch_gap_bps,
            bbo_age_ms,
        }
    }
}

pub fn post_only_near_touch_or_skip(
    request: &BoundedProbePlacementRequest,
) -> BoundedProbePlacementDecision {
    if let Err(reason) = request.config.validate() {
        return BoundedProbePlacementDecision::Skip(BoundedProbeTouchabilityBlock::new(
            &request.side_cell_key,
            reason,
            None,
            None,
        ));
    }
    if let Err(reason) = request.bbo.validate() {
        return BoundedProbePlacementDecision::Skip(BoundedProbeTouchabilityBlock::new(
            &request.side_cell_key,
            reason,
            None,
            None,
        ));
    }
    if request.now_ms == 0 {
        return BoundedProbePlacementDecision::Skip(BoundedProbeTouchabilityBlock::new(
            &request.side_cell_key,
            BoundedProbePlacementSkipReason::MissingFreshBbo,
            None,
            None,
        ));
    }
    if request.bbo.observed_at_ms > request.now_ms {
        return BoundedProbePlacementDecision::Skip(BoundedProbeTouchabilityBlock::new(
            &request.side_cell_key,
            BoundedProbePlacementSkipReason::MissingFreshBbo,
            None,
            None,
        ));
    }
    let bbo_age_ms = request.now_ms.saturating_sub(request.bbo.observed_at_ms);
    if bbo_age_ms > request.config.max_fresh_bbo_age_ms {
        return BoundedProbePlacementDecision::Skip(BoundedProbeTouchabilityBlock::new(
            &request.side_cell_key,
            BoundedProbePlacementSkipReason::StaleBbo,
            None,
            Some(bbo_age_ms),
        ));
    }

    let (limit_price, reference_price) = if request.is_buy {
        (
            request
                .bbo
                .best_bid
                .min(request.bbo.best_ask - request.bbo.tick_size),
            request.bbo.best_ask,
        )
    } else {
        (
            request
                .bbo
                .best_ask
                .max(request.bbo.best_bid + request.bbo.tick_size),
            request.bbo.best_bid,
        )
    };
    if !limit_price.is_finite() || limit_price <= 0.0 {
        return BoundedProbePlacementDecision::Skip(BoundedProbeTouchabilityBlock::new(
            &request.side_cell_key,
            BoundedProbePlacementSkipReason::InvalidBbo,
            None,
            Some(bbo_age_ms),
        ));
    }
    let touch_gap_bps = ((reference_price - limit_price).abs() / reference_price) * 10_000.0;

    if touch_gap_bps > request.config.max_initial_passive_gap_bps {
        return BoundedProbePlacementDecision::Skip(BoundedProbeTouchabilityBlock::new(
            &request.side_cell_key,
            BoundedProbePlacementSkipReason::GapTooWide,
            Some(touch_gap_bps),
            Some(bbo_age_ms),
        ));
    }

    BoundedProbePlacementDecision::Submit(BoundedProbeAttemptPlacement {
        record_type: "bounded_probe_attempt",
        side_cell_key: request.side_cell_key.clone(),
        limit_price,
        touch_gap_bps,
        reference_price,
        bbo_age_ms,
    })
}

pub fn post_only_near_touch_from_optional_bbo_or_skip(
    request: &BoundedProbeOptionalBboPlacementRequest,
) -> BoundedProbePlacementDecision {
    let (Some(best_bid), Some(best_ask), Some(tick_size), Some(observed_at_ms)) = (
        request.best_bid,
        request.best_ask,
        request.tick_size,
        request.observed_at_ms,
    ) else {
        return BoundedProbePlacementDecision::Skip(BoundedProbeTouchabilityBlock::new(
            &request.side_cell_key,
            BoundedProbePlacementSkipReason::MissingFreshBbo,
            None,
            None,
        ));
    };

    post_only_near_touch_or_skip(&BoundedProbePlacementRequest {
        side_cell_key: request.side_cell_key.clone(),
        is_buy: request.is_buy,
        now_ms: request.now_ms,
        bbo: BboSnapshot {
            best_bid,
            best_ask,
            tick_size,
            observed_at_ms,
        },
        config: request.config,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cfg() -> BoundedProbeNearTouchConfig {
        BoundedProbeNearTouchConfig {
            max_fresh_bbo_age_ms: DEFAULT_MAX_FRESH_BBO_AGE_MS,
            max_initial_passive_gap_bps: DEFAULT_MAX_INITIAL_PASSIVE_GAP_BPS,
        }
    }

    fn bbo() -> BboSnapshot {
        BboSnapshot {
            best_bid: 100.0,
            best_ask: 100.2,
            tick_size: 0.1,
            observed_at_ms: 10_000,
        }
    }

    fn request(is_buy: bool) -> BoundedProbePlacementRequest {
        BoundedProbePlacementRequest {
            side_cell_key: "ma_crossover|BTCUSDT|Sell".to_string(),
            is_buy,
            now_ms: 10_500,
            bbo: bbo(),
            config: cfg(),
        }
    }

    #[test]
    fn buy_uses_maker_side_near_touch_limit() {
        let decision = post_only_near_touch_or_skip(&request(true));
        let BoundedProbePlacementDecision::Submit(attempt) = decision else {
            panic!("expected submit");
        };
        assert_eq!(attempt.record_type, "bounded_probe_attempt");
        assert_eq!(attempt.limit_price, 100.0);
        assert!((attempt.touch_gap_bps - 19.960_079_84).abs() < 1e-6);
        assert_eq!(attempt.bbo_age_ms, 500);
    }

    #[test]
    fn sell_uses_maker_side_near_touch_limit() {
        let decision = post_only_near_touch_or_skip(&request(false));
        let BoundedProbePlacementDecision::Submit(attempt) = decision else {
            panic!("expected submit");
        };
        assert_eq!(attempt.record_type, "bounded_probe_attempt");
        assert_eq!(attempt.limit_price, 100.2);
        assert!((attempt.touch_gap_bps - 20.0).abs() < 1e-6);
    }

    #[test]
    fn stale_bbo_skips_with_touchability_block() {
        let mut req = request(true);
        req.now_ms = 12_000;
        let decision = post_only_near_touch_or_skip(&req);
        let BoundedProbePlacementDecision::Skip(block) = decision else {
            panic!("expected skip");
        };
        assert_eq!(block.record_type, "bounded_probe_touchability_block");
        assert_eq!(block.reason, BoundedProbePlacementSkipReason::StaleBbo);
        assert_eq!(block.bbo_age_ms, Some(2_000));
    }

    #[test]
    fn future_bbo_skips_closed() {
        let mut req = request(true);
        req.bbo.observed_at_ms = 11_000;
        let decision = post_only_near_touch_or_skip(&req);
        let BoundedProbePlacementDecision::Skip(block) = decision else {
            panic!("expected skip");
        };
        assert_eq!(
            block.reason,
            BoundedProbePlacementSkipReason::MissingFreshBbo
        );
        assert_eq!(block.bbo_age_ms, None);
    }

    #[test]
    fn wide_gap_skips_with_touch_gap_bps() {
        let mut req = request(true);
        req.config.max_initial_passive_gap_bps = 5.0;
        let decision = post_only_near_touch_or_skip(&req);
        let BoundedProbePlacementDecision::Skip(block) = decision else {
            panic!("expected skip");
        };
        assert_eq!(block.reason, BoundedProbePlacementSkipReason::GapTooWide);
        assert!(block.touch_gap_bps.unwrap() > 5.0);
    }

    #[test]
    fn non_positive_near_touch_limit_fails_closed() {
        let mut req = request(true);
        req.bbo.best_bid = 0.1;
        req.bbo.best_ask = 0.1;
        req.bbo.tick_size = 0.1;
        let decision = post_only_near_touch_or_skip(&req);
        let BoundedProbePlacementDecision::Skip(block) = decision else {
            panic!("expected skip");
        };
        assert_eq!(block.reason, BoundedProbePlacementSkipReason::InvalidBbo);
        assert_eq!(block.bbo_age_ms, Some(500));
    }

    #[test]
    fn crossed_or_invalid_bbo_fails_closed() {
        let mut req = request(true);
        req.bbo.best_bid = 101.0;
        req.bbo.best_ask = 100.0;
        let decision = post_only_near_touch_or_skip(&req);
        let BoundedProbePlacementDecision::Skip(block) = decision else {
            panic!("expected skip");
        };
        assert_eq!(block.reason, BoundedProbePlacementSkipReason::InvalidBbo);
    }

    #[test]
    fn optional_bbo_missing_quote_records_touchability_block() {
        let decision = post_only_near_touch_from_optional_bbo_or_skip(
            &BoundedProbeOptionalBboPlacementRequest {
                side_cell_key: "ma_crossover|BTCUSDT|Sell".to_string(),
                is_buy: false,
                now_ms: 10_500,
                best_bid: Some(100.0),
                best_ask: None,
                tick_size: Some(0.1),
                observed_at_ms: Some(10_500),
                config: cfg(),
            },
        );
        let BoundedProbePlacementDecision::Skip(block) = decision else {
            panic!("expected skip");
        };
        assert_eq!(block.record_type, "bounded_probe_touchability_block");
        assert_eq!(
            block.reason,
            BoundedProbePlacementSkipReason::MissingFreshBbo
        );
    }

    #[test]
    fn optional_bbo_complete_routes_to_near_touch_math() {
        let decision = post_only_near_touch_from_optional_bbo_or_skip(
            &BoundedProbeOptionalBboPlacementRequest {
                side_cell_key: "ma_crossover|BTCUSDT|Sell".to_string(),
                is_buy: false,
                now_ms: 10_500,
                best_bid: Some(100.0),
                best_ask: Some(100.2),
                tick_size: Some(0.1),
                observed_at_ms: Some(10_000),
                config: cfg(),
            },
        );
        let BoundedProbePlacementDecision::Submit(attempt) = decision else {
            panic!("expected submit");
        };
        assert_eq!(attempt.record_type, "bounded_probe_attempt");
        assert_eq!(attempt.limit_price, 100.2);
        assert_eq!(attempt.bbo_age_ms, 500);
    }
}
