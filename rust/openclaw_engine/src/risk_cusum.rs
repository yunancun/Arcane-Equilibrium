//! Strategy edge-decay CUSUM evaluator (G7-04 Phase B).
//! 策略 edge 衰減 CUSUM 評估器（G7-04 Phase B）。
//!
//! MODULE_NOTE (EN): `RiskConfig.cusum` landed as schema-only in G7-04 Phase A.
//! This module is the first runtime-consumable implementation: a pure,
//! side-effect-free one-sided downside CUSUM over realized per-trade net bps.
//! It does not mutate strategy state, risk config, DB rows, or live behaviour.
//! Callers decide what to do with an alarm. Defaults stay dormant because
//! `CusumConfig.enabled=false` in all shipped TOML files.
//!
//! MODULE_NOTE (中): G7-04 Phase A 已落 `RiskConfig.cusum` schema；本模組提供
//! 第一個可被 runtime 消費的純函式實作：對 realized per-trade net bps 做單側
//! 下行 CUSUM。模組本身不改策略狀態、不寫 DB、不改 live 行為；alarm 後續由
//! caller 決定處置。現有 TOML 預設 `enabled=false`，因此部署後保持 dormant。

use crate::config::risk_config::CusumConfig;

/// Output of one downside-CUSUM evaluation.
/// 單次 downside-CUSUM 評估輸出。
#[derive(Debug, Clone, PartialEq)]
pub struct CusumEvaluation {
    pub enabled: bool,
    pub observations: usize,
    pub mean_bps: f64,
    pub sigma_bps: f64,
    pub score_bps: f64,
    pub threshold_bps: f64,
    pub alarm: bool,
    pub reason: String,
}

impl CusumEvaluation {
    fn disabled() -> Self {
        Self {
            enabled: false,
            observations: 0,
            mean_bps: 0.0,
            sigma_bps: 0.0,
            score_bps: 0.0,
            threshold_bps: 0.0,
            alarm: false,
            reason: "cusum_disabled".to_string(),
        }
    }
}

/// Evaluate one-sided downside CUSUM over realized net bps.
///
/// Formula:
/// `S_t = max(0, S_{t-1} - (x_t - target_return_bps) - slack_k * sigma)`.
/// Alarm when `S_t > threshold_h * sigma`.
///
/// Non-finite observations are ignored. If the finite sample count is below
/// `min_observations`, or sample sigma is degenerate, this returns no alarm.
/// 評估單側下行 CUSUM；非有限樣本會忽略。樣本不足或 sigma 退化時不告警。
pub fn evaluate_downside_cusum(net_bps: &[f64], cfg: &CusumConfig) -> CusumEvaluation {
    if !cfg.enabled {
        return CusumEvaluation::disabled();
    }

    let values: Vec<f64> = net_bps.iter().copied().filter(|v| v.is_finite()).collect();
    let observations = values.len();
    if observations < cfg.min_observations as usize {
        return CusumEvaluation {
            enabled: true,
            observations,
            mean_bps: mean(&values),
            sigma_bps: 0.0,
            score_bps: 0.0,
            threshold_bps: 0.0,
            alarm: false,
            reason: format!(
                "insufficient_observations:{observations}<{}",
                cfg.min_observations
            ),
        };
    }

    let mean_bps = mean(&values);
    let sigma_bps = sample_sigma(&values, mean_bps);
    if sigma_bps <= f64::EPSILON {
        return CusumEvaluation {
            enabled: true,
            observations,
            mean_bps,
            sigma_bps,
            score_bps: 0.0,
            threshold_bps: 0.0,
            alarm: false,
            reason: "degenerate_sigma".to_string(),
        };
    }

    let mut score = 0.0_f64;
    let deadband = cfg.slack_k * sigma_bps;
    for x in values {
        let downside = -(x - cfg.target_return_bps) - deadband;
        score = (score + downside).max(0.0);
    }
    let threshold = cfg.threshold_h * sigma_bps;
    let alarm = score > threshold;
    CusumEvaluation {
        enabled: true,
        observations,
        mean_bps,
        sigma_bps,
        score_bps: score,
        threshold_bps: threshold,
        alarm,
        reason: if alarm {
            "downside_cusum_alarm".to_string()
        } else {
            "within_control_band".to_string()
        },
    }
}

fn mean(values: &[f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    values.iter().sum::<f64>() / values.len() as f64
}

fn sample_sigma(values: &[f64], mean: f64) -> f64 {
    if values.len() < 2 {
        return 0.0;
    }
    let var = values
        .iter()
        .map(|v| {
            let d = *v - mean;
            d * d
        })
        .sum::<f64>()
        / (values.len() as f64 - 1.0);
    var.sqrt()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cfg_on() -> CusumConfig {
        CusumConfig {
            enabled: true,
            slack_k: 0.5,
            threshold_h: 4.0,
            min_observations: 5,
            target_return_bps: 0.0,
        }
    }

    #[test]
    fn disabled_config_is_dormant() {
        let eval = evaluate_downside_cusum(&[-50.0; 20], &CusumConfig::default());
        assert!(!eval.enabled);
        assert!(!eval.alarm);
        assert_eq!(eval.reason, "cusum_disabled");
    }

    #[test]
    fn insufficient_observations_do_not_alarm() {
        let eval = evaluate_downside_cusum(&[-20.0, -25.0, -30.0], &cfg_on());
        assert!(eval.enabled);
        assert!(!eval.alarm);
        assert_eq!(eval.observations, 3);
        assert!(eval.reason.contains("insufficient_observations"));
    }

    #[test]
    fn non_finite_values_are_ignored() {
        let eval = evaluate_downside_cusum(
            &[-10.0, f64::NAN, -12.0, f64::INFINITY, -8.0, -9.0, -11.0],
            &cfg_on(),
        );
        assert_eq!(eval.observations, 5);
        assert!(eval.enabled);
    }

    #[test]
    fn positive_or_flat_edge_stays_inside_band() {
        let values = [4.0, 5.0, 3.5, 4.5, 5.5, 4.2, 4.8, 5.1];
        let eval = evaluate_downside_cusum(&values, &cfg_on());
        assert!(!eval.alarm);
        assert_eq!(eval.reason, "within_control_band");
        assert_eq!(eval.score_bps, 0.0);
    }

    #[test]
    fn sustained_negative_edge_alarms() {
        let values = [-2.0, -5.0, -8.0, -10.0, -12.0, -15.0, -18.0, -21.0, -24.0];
        let eval = evaluate_downside_cusum(&values, &cfg_on());
        assert!(eval.alarm, "eval={eval:?}");
        assert!(eval.score_bps > eval.threshold_bps);
        assert_eq!(eval.reason, "downside_cusum_alarm");
    }

    #[test]
    fn degenerate_sigma_does_not_auto_alarm() {
        let eval = evaluate_downside_cusum(&[-10.0, -10.0, -10.0, -10.0, -10.0], &cfg_on());
        assert!(!eval.alarm);
        assert_eq!(eval.reason, "degenerate_sigma");
    }
}
