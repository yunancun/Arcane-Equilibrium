// MODULE_NOTE
// 模塊用途：M4 Pattern Miner Stage 1 共用 struct / enum 定義。
//   PatternDraft = Rust 產出的 hypothesis 候選；Python 端拿來組 INSERT learning.hypotheses
//   的 6 attribute 欄位（per W1-B spec §4）。其他 struct 為 algorithm 中間結果。
//
// 硬邊界：本檔只放型別，沒有業務邏輯；
//   PatternDraft.status 只允許 'preregistered' / 'exploratory' / 'draft'（不可 auto promote
//   past 'preregistered'，per 16 原則 #7 + W1-B spec §0 I-5）。

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// Forward-return 觀察窗口長度（分鐘）。
///
/// W1-B spec §2.1.1 定義 5 個 forward window：
///   τ ∈ {1, 5, 15, 60, 240} minutes。
/// 為什麼 5 個：對應 1m/5m/15m/1h/4h timeframe — Bonferroni K_total = K_hyp × 5。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ForwardWindow {
    OneMinute = 1,
    FiveMinutes = 5,
    FifteenMinutes = 15,
    OneHour = 60,
    FourHours = 240,
}

impl ForwardWindow {
    /// 所有 forward window 順序列表 — Bonferroni K_hyp × 5 的 5 來源。
    pub const ALL: [ForwardWindow; 5] = [
        ForwardWindow::OneMinute,
        ForwardWindow::FiveMinutes,
        ForwardWindow::FifteenMinutes,
        ForwardWindow::OneHour,
        ForwardWindow::FourHours,
    ];

    /// 轉成 minute 整數，方便 slice indexing。
    pub fn as_minutes(self) -> usize {
        self as usize
    }
}

/// Event type — event-window analysis 三類事件。
///
/// per W1-B spec §2.2.1 Sprint 2 IMPL 3 種：
///   - FundingFlip: funding rate sign change + |rate| > 0.01%
///   - LiquidationCascade: cascade_size > 5M USD 5min window
///   - LargeFundingSpike: |funding_rate| > 0.1%
///   - FOMC / TokenUnlock 為 Sprint 3+ defer。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum EventType {
    FundingFlip,
    LiquidationCascade,
    LargeFundingSpike,
}

impl EventType {
    pub fn as_str(self) -> &'static str {
        match self {
            EventType::FundingFlip => "funding_flip",
            EventType::LiquidationCascade => "liquidation_cascade",
            EventType::LargeFundingSpike => "large_funding_spike",
        }
    }
}

/// Statistical algorithm 結果（cross-correlation / event-window 共通容器）。
///
/// 對應 Python 端要寫入 learning.hypotheses 6 attribute 字段的中間表示：
///   - n_observations -> m4_attribute_n
///   - raw_p_value -> bonferroni_corrected_p（Python 端用 K_TOTAL 比較）
///   - cohens_d -> m4_attribute_effect_size
///   - subperiod_pass -> m4_attribute_subperiod_pass
///   - graveyard_flag -> m4_attribute_graveyard_flag
///   - replicability_score 由 Python 端用 sub-period + cross-asset 計
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StatisticalResult {
    /// 觀察樣本數。N >= 30 才能進 'preregistered'，否則強制 'exploratory'。
    pub n_observations: usize,
    /// 原始 p-value（K_TOTAL Bonferroni 比較在 application 端 with K=2500）。
    pub raw_p_value: f64,
    /// Cohen's d effect size。
    pub cohens_d: f64,
    /// 前後 50/50 split Mann-Whitney U 通過？event-window 場景設 None。
    pub subperiod_pass: Option<bool>,
    /// Harvey-Liu-Zhu graveyard fuzzy match 命中？warning only 不阻 promote。
    pub graveyard_flag: bool,
    /// 觀察樣本是否含 leak（per W1-B spec §4.3 leakage scan 自驗）。fail-closed default。
    pub leakage_scan_pass: bool,
}

impl StatisticalResult {
    /// 安全建構：強制 N 與 p-value boundary。
    pub fn new(n: usize, p: f64, d: f64) -> Self {
        Self {
            n_observations: n,
            raw_p_value: p.clamp(0.0, 1.0),
            cohens_d: d,
            subperiod_pass: None,
            graveyard_flag: false,
            leakage_scan_pass: false, // fail-closed default per 根原則 #6
        }
    }
}

/// Event-window analysis 完整結果（含 pre/post window forward return）。
///
/// per W1-B spec §2.2 + §3 6 attribute 對 event-window 場景特化：
///   - n_events < 30 強制 'exploratory'
///   - 'subperiod_pass' = None（per W1-B Open Q4：event-window 不適用 sub-period split）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EventWindowResult {
    pub event_type: EventType,
    pub n_events: usize,
    pub pre_window_mean_bps: f64,
    pub post_window_mean_bps: f64,
    /// effect = mean(post) - mean(pre)
    pub effect_bps: f64,
    /// p-value (Welch's t-test or Mann-Whitney U)。
    pub raw_p_value: f64,
    /// Cohen's d。
    pub cohens_d: f64,
}

/// Event-window sample-gate verdict — per W1-B spec §2.2.3 + §3.2。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EventWindowVerdict {
    /// N >= 30，可考慮 'preregistered'（仍須 Bonferroni + Cohen's d 過 gate）。
    PreregisteredCandidate,
    /// N < 30，強制 'exploratory' + event_rate_constrained flag。
    Exploratory,
}

impl EventWindowVerdict {
    pub fn as_str(self) -> &'static str {
        match self {
            EventWindowVerdict::PreregisteredCandidate => "preregistered_candidate",
            EventWindowVerdict::Exploratory => "exploratory",
        }
    }
}

/// PatternDraft — Rust miner 產出、Python writeback 消費的最小資料載體。
///
/// 對應 V100 base + V103 EXTEND 6 column 的子集（Decision Lease backref 與
/// cowork_review_status 由 Python orchestrator 補）。
///
/// 不變量：
///   - status ∈ {"draft", "exploratory", "preregistered"}；M4 寫入只用前三個
///   - status = "live" / "promoted" / "rejected" 不能由 Rust miner 自動寫入
///     （per 16 原則 #7 + AMD-2026-05-21-01 protected scope (a)）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PatternDraft {
    /// 策略名（grid / ma / bb_breakout / bb_reversion / funding_arb 等）。
    pub strategy_name: String,
    /// Symbol — 25 universe 之一。
    pub symbol: String,
    /// Timeframe — 1m/5m/15m/1h/4h。
    pub timeframe: String,
    /// Feature 名（per W1-B spec §2.1.3 baseline 25 個）。
    pub feature_name: String,
    /// Forward window — 5 個之一。
    pub forward_window: ForwardWindow,
    /// 統計結果（cross-correlation / event-window 共用容器）。
    pub statistical_result: StatisticalResult,
    /// Event 類型（None 表示 cross-correlation 來源；Some 表示 event-window）。
    pub event_type: Option<EventType>,
    /// 待 Python 端決定的 status — Rust miner 只標 candidate verdict。
    /// 不變量：值 ∈ {"draft", "exploratory", "preregistered"}。
    pub status_candidate: String,
    /// 為什麼此 candidate（debug + audit），例：「N=80 cohens_d=0.45 raw_p=1e-7」。
    pub rationale: String,
    /// Rust miner 完成時間 — Python 端用做 INSERT created_at 對齊。
    pub generated_at: DateTime<Utc>,
}

impl PatternDraft {
    /// 安全建構：強制 status_candidate ∈ 白名單。
    /// 為什麼 fail-loud：避免 Python 端拿到 status="live"/"promoted" 之類非法值。
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        strategy_name: String,
        symbol: String,
        timeframe: String,
        feature_name: String,
        forward_window: ForwardWindow,
        statistical_result: StatisticalResult,
        event_type: Option<EventType>,
        status_candidate: String,
        rationale: String,
    ) -> Result<Self, String> {
        // 不變量：status_candidate 必 ∈ {"draft", "exploratory", "preregistered"}。
        // 為什麼 fail-loud：Rust miner 不能自動 promote past "preregistered"
        // （per AMD-2026-05-21-01 protected scope (a) + 16 原則 #7 學習 ≠ live）。
        match status_candidate.as_str() {
            "draft" | "exploratory" | "preregistered" => {}
            other => {
                return Err(format!(
                    "PatternDraft.status_candidate 非法值 '{}'：M4 miner 只能寫 draft/exploratory/preregistered",
                    other
                ));
            }
        }
        Ok(Self {
            strategy_name,
            symbol,
            timeframe,
            feature_name,
            forward_window,
            statistical_result,
            event_type,
            status_candidate,
            rationale,
            generated_at: Utc::now(),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn forward_window_all_has_5_entries() {
        // I-3 Bonferroni K_total = K_hyp × 5 forward window；ALL.len() == 5 為硬不變量。
        assert_eq!(ForwardWindow::ALL.len(), 5);
    }

    #[test]
    fn pattern_draft_rejects_live_status() {
        // 不變量 verify：M4 不能自動寫 "live" / "promoted" / "rejected"。
        let r = PatternDraft::new(
            "grid".into(),
            "BTCUSDT".into(),
            "5m".into(),
            "sma20_ratio".into(),
            ForwardWindow::FiveMinutes,
            StatisticalResult::new(50, 1e-6, 0.5),
            None,
            "live".into(),
            "test".into(),
        );
        assert!(r.is_err(), "M4 miner 不能寫 status='live'");
        let r2 = PatternDraft::new(
            "grid".into(),
            "BTCUSDT".into(),
            "5m".into(),
            "sma20_ratio".into(),
            ForwardWindow::FiveMinutes,
            StatisticalResult::new(50, 1e-6, 0.5),
            None,
            "promoted".into(),
            "test".into(),
        );
        assert!(r2.is_err(), "M4 miner 不能寫 status='promoted'");
    }

    #[test]
    fn pattern_draft_accepts_legitimate_status() {
        for status in ["draft", "exploratory", "preregistered"] {
            let r = PatternDraft::new(
                "grid".into(),
                "BTCUSDT".into(),
                "5m".into(),
                "sma20_ratio".into(),
                ForwardWindow::FiveMinutes,
                StatisticalResult::new(50, 1e-6, 0.5),
                None,
                status.into(),
                "test".into(),
            );
            assert!(r.is_ok(), "合法 status '{}' 應通過", status);
        }
    }

    #[test]
    fn statistical_result_p_value_clamped() {
        // 邊界：p > 1 或 p < 0 都應 clamp 到 [0,1]。
        let r = StatisticalResult::new(10, 1.5, 0.3);
        assert!(r.raw_p_value <= 1.0);
        let r2 = StatisticalResult::new(10, -0.1, 0.3);
        assert!(r2.raw_p_value >= 0.0);
    }

    #[test]
    fn statistical_result_leakage_default_fail_closed() {
        // 不變量：leakage_scan_pass DEFAULT FALSE（per V103 EXTEND + 根原則 #6）。
        let r = StatisticalResult::new(10, 0.05, 0.3);
        assert_eq!(r.leakage_scan_pass, false);
    }
}
