//! Paper maker-order statistics & KPI gate — EDGE-P2-3 Phase 1B-5.
//! 紙盤 maker 掛單統計 & KPI gate — EDGE-P2-3 Phase 1B-5。
//!
//! MODULE_NOTE (EN): Accumulates submit / fill-full / fill-partial / timeout
//!   counters for PostOnly resting orders on the Paper path, plus the running
//!   sum of `net_edge_bps` (bias-guard #4 adverse-selection metric). Offers a
//!   tri-state `MakerKpiStatus` gate the router consults before enqueuing so a
//!   symbol whose maker path is chronically unfilled or bleeding to adverse
//!   selection silently falls back to market execution instead of letting
//!   intents rot in the queue.
//!
//!   The statistics live on `PaperState` (one `MakerStats` per engine) — the
//!   exchange path tracks maker fills via WS and has its own observability, so
//!   there is no need to hoist this module above `paper_state`. Thresholds are
//!   hard-coded defaults now; a ConfigStore-backed override is a 1B-5 FUP.
//!
//! MODULE_NOTE (中): 累計紙盤 PostOnly 掛單的 submit / fill-full / fill-partial /
//!   timeout 計數器，以及 `net_edge_bps`（bias 保護 #4 adverse-selection）的
//!   running sum。Router 在 enqueue 前透過 `MakerKpiStatus` 三態 gate 檢查：
//!   若某 symbol 的 maker 路徑長期不成交或被 adverse-selection 侵蝕，靜默
//!   fallback 到市價成交，避免 intent 卡隊列。
//!
//!   統計資料掛在 `PaperState`（一引擎一份）—— 交易所路徑的 maker 成交走 WS
//!   + 自有 observability，不需把這模組升到 paper_state 之上。門檻暫時寫死；
//!   ConfigStore 動態覆寫列為 1B-5 FUP。

use std::collections::HashMap;

/// Per-scope counters (aggregate or per-symbol).
/// per-scope 計數器（總體或 per-symbol）。
///
/// `filled_full` / `filled_partial` are tracked separately so a future KPI can
/// distinguish "we cross the book" (full) vs "we sit at touch and coin-flip"
/// (partial) — the latter has inherently worse fill-rate predictability.
///
/// `sum_net_edge_bps` is a running sum across *all* fills whose
/// `mid_price_at_submit > 0.0`. Fills lacking a valid submit-mid (e.g. first
/// tick before any mid is available) still bump the fill counter but are
/// excluded from the edge sum so bootstrap ticks cannot poison the mean.
#[derive(Debug, Clone, Default)]
pub struct MakerStatsCounters {
    /// Total resting orders enqueued on this scope.
    /// 本 scope 累計進入 resting 隊列的掛單數。
    pub submitted: u64,
    /// Orders that filled via true cross (tick price crossed the limit).
    /// 經真實穿越（tick 價越過限價）成交的掛單數。
    pub filled_full: u64,
    /// Orders that filled via touch + deterministic coin-flip (1B-4.2 50%).
    /// 碰觸 + 確定性硬幣（1B-4.2 50%）成交的掛單數。
    pub filled_partial: u64,
    /// Orders drained by deadline without any fill.
    /// 到期未成交、被 sweep 清出隊列的掛單數。
    pub timedout: u64,
    /// Running sum of signed net edge in bps across valid fills.
    /// 有效成交的 net edge（bps）累加和。
    pub sum_net_edge_bps: f64,
    /// Number of intents that skipped enqueue because the KPI gate reported
    /// `Degraded` — they silently fell back to market fill. Accumulated by
    /// caller (router) on gate rejection, not by the sweep path.
    /// KPI gate 回 `Degraded` 而被跳過 enqueue 的 intent 數（改走 market）。
    /// 由 router 在 gate 拒絕時累加，不由 sweep 路徑觸發。
    pub degraded_fallbacks: u64,
}

impl MakerStatsCounters {
    /// Total filled = full cross + partial (coin-flip). Used as edge-mean denom.
    /// 全部成交 = 真實穿越 + 碰觸硬幣。
    pub fn filled_total(&self) -> u64 {
        self.filled_full + self.filled_partial
    }

    /// Fill rate = filled / (filled + timedout). `None` when denom is zero so
    /// callers can distinguish "no samples" from "all timeouts".
    /// 成交率 = filled / (filled + timedout)。分母為 0 時回 None 以便區分
    /// 「無樣本」與「全超時」。
    pub fn fill_rate(&self) -> Option<f64> {
        let denom = self.filled_total() + self.timedout;
        if denom == 0 {
            None
        } else {
            Some(self.filled_total() as f64 / denom as f64)
        }
    }

    /// Mean `net_edge_bps` across filled orders with valid submit mid.
    /// `None` when there are zero valid samples.
    /// 平均 net_edge_bps（以 filled_total 為分母）。無樣本回 None。
    pub fn avg_net_edge_bps(&self) -> Option<f64> {
        let n = self.filled_total();
        if n == 0 {
            None
        } else {
            Some(self.sum_net_edge_bps / n as f64)
        }
    }

    /// Samples used for KPI gate freshness check = filled + timedout.
    /// Excludes `submitted`-only counts so a symbol with many in-flight
    /// resting orders but zero terminal events still reads as Cold.
    /// KPI gate 採用的樣本數 = filled + timedout。尚在隊列的 submitted
    /// 不計入，避免「很多掛單、零終局事件」被誤判為有效樣本。
    pub fn terminal_samples(&self) -> u64 {
        self.filled_total() + self.timedout
    }

    /// Evaluate KPI gate. Order of checks (first match wins):
    ///   1. terminal_samples < min_samples → Cold (warmup, allow enqueue)
    ///   2. fill_rate < min_fill_rate       → Degraded("fill_rate_below_threshold")
    ///   3. avg_net_edge_bps < min_edge_bps → Degraded("net_edge_below_threshold")
    ///   4. otherwise                       → Healthy
    /// 先判樣本數 → 再判成交率 → 再判平均 edge → 其餘為 Healthy。
    pub fn kpi_status(&self, cfg: &MakerKpiConfig) -> MakerKpiStatus {
        if self.terminal_samples() < cfg.min_samples {
            return MakerKpiStatus::Cold;
        }
        if let Some(rate) = self.fill_rate() {
            if rate < cfg.min_fill_rate {
                return MakerKpiStatus::Degraded {
                    reason: "fill_rate_below_threshold",
                };
            }
        }
        if let Some(edge) = self.avg_net_edge_bps() {
            if edge < cfg.min_avg_net_edge_bps {
                return MakerKpiStatus::Degraded {
                    reason: "net_edge_below_threshold",
                };
            }
        }
        MakerKpiStatus::Healthy
    }
}

/// Top-level container: aggregate + per-symbol split.
/// 頂層容器：aggregate + per-symbol 拆分。
#[derive(Debug, Clone, Default)]
pub struct MakerStats {
    pub aggregate: MakerStatsCounters,
    pub per_symbol: HashMap<String, MakerStatsCounters>,
}

impl MakerStats {
    fn entry(&mut self, symbol: &str) -> &mut MakerStatsCounters {
        self.per_symbol
            .entry(symbol.to_string())
            .or_insert_with(MakerStatsCounters::default)
    }

    /// Record enqueue — bumps `submitted` on both aggregate and per-symbol.
    /// 記錄入隊 — aggregate 與 per-symbol 的 submitted 各 +1。
    pub fn record_submit(&mut self, symbol: &str) {
        self.aggregate.submitted += 1;
        self.entry(symbol).submitted += 1;
    }

    /// Record terminal fill event. `true_cross=true` → `filled_full`, else
    /// `filled_partial`. When `mid_price_at_submit > 0.0`, computes
    /// `net_edge_bps` (signed by side) minus fee bps and adds to sum on both
    /// aggregate and per-symbol scope. When submit-mid is 0 or fill-price is
    /// 0, counter is bumped but the edge sum is untouched (bootstrap safety).
    /// 記錄終局成交。`true_cross=true` 進 filled_full，否則 filled_partial。
    /// submit-mid > 0 時計算 `net_edge_bps`（含方向符號 − fee bps），並加到
    /// aggregate 與 per-symbol 的 sum。submit-mid 為 0 或成交價 0 → 只計數
    /// 不進 sum（bootstrap 保護）。
    #[allow(clippy::too_many_arguments)]
    pub fn record_fill(
        &mut self,
        symbol: &str,
        is_long: bool,
        mid_price_at_submit: f64,
        mid_price_at_fill: f64,
        qty: f64,
        fill_price: f64,
        fee: f64,
        true_cross: bool,
    ) {
        if true_cross {
            self.aggregate.filled_full += 1;
            self.entry(symbol).filled_full += 1;
        } else {
            self.aggregate.filled_partial += 1;
            self.entry(symbol).filled_partial += 1;
        }
        if let Some(net_bps) =
            compute_net_edge_bps(is_long, mid_price_at_submit, mid_price_at_fill, qty, fill_price, fee)
        {
            self.aggregate.sum_net_edge_bps += net_bps;
            self.entry(symbol).sum_net_edge_bps += net_bps;
        }
    }

    /// Record timeout — bumps `timedout` on both aggregate and per-symbol.
    /// 記錄超時 — aggregate 與 per-symbol 的 timedout 各 +1。
    pub fn record_timeout(&mut self, symbol: &str) {
        self.aggregate.timedout += 1;
        self.entry(symbol).timedout += 1;
    }

    /// Record a router-level degraded fallback (KPI gate rejected enqueue).
    /// 記錄 router 端的 Degraded fallback（KPI gate 拒絕 enqueue）。
    pub fn record_degraded_fallback(&mut self, symbol: &str) {
        self.aggregate.degraded_fallbacks += 1;
        self.entry(symbol).degraded_fallbacks += 1;
    }

    /// Resolve effective KPI status for `symbol`. Uses per-symbol counters
    /// when they have enough terminal samples; otherwise falls back to
    /// aggregate so cross-symbol experience can rescue a cold single symbol.
    /// 解析某 symbol 的有效 KPI 狀態。per-symbol 終局樣本足夠時以 per-symbol
    /// 判定；不足則 fallback 到 aggregate，讓單一 symbol 的冷啟動借用其他
    /// symbol 的經驗。
    pub fn status_for(&self, symbol: &str, cfg: &MakerKpiConfig) -> MakerKpiStatus {
        if let Some(per) = self.per_symbol.get(symbol) {
            if per.terminal_samples() >= cfg.min_samples {
                return per.kpi_status(cfg);
            }
        }
        self.aggregate.kpi_status(cfg)
    }
}

/// KPI gate configuration. Conservative defaults chosen so the gate stays
/// *inactive* until enough data accumulates, then bites only on clearly bad
/// behaviour (fill rate <15% or avg edge <-5 bps).
/// KPI gate 設定。預設保守：樣本不足時閒置，累積後只針對明確劣化（fill<15%
/// 或平均 edge<-5 bps）介入。
#[derive(Debug, Clone)]
pub struct MakerKpiConfig {
    /// Terminal samples required before the gate evaluates fill_rate / edge.
    /// gate 開始評估前的最少終局樣本數。
    pub min_samples: u64,
    /// Fill rate floor (filled / (filled + timedout)). Below → Degraded.
    /// 成交率下限。低於此值 → Degraded。
    pub min_fill_rate: f64,
    /// Mean net edge floor in bps. Below → Degraded.
    /// 平均 net edge 下限（bps）。低於此值 → Degraded。
    pub min_avg_net_edge_bps: f64,
}

impl Default for MakerKpiConfig {
    fn default() -> Self {
        Self {
            min_samples: 20,
            min_fill_rate: 0.15,
            min_avg_net_edge_bps: -5.0,
        }
    }
}

/// Tri-state gate result. `Cold` means "insufficient samples, allow enqueue"
/// — treated as pass at call sites. `Degraded` is a hard stop that routes the
/// intent to market execution.
/// 三態 gate 結果。Cold=樣本不足，允許 enqueue；Degraded=強制 fallback 市價。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MakerKpiStatus {
    Cold,
    Healthy,
    Degraded { reason: &'static str },
}

impl MakerKpiStatus {
    /// True when the gate explicitly wants the caller to bypass enqueue.
    /// gate 明確要求 caller 跳過 enqueue 時為 true。
    pub fn is_degraded(&self) -> bool {
        matches!(self, MakerKpiStatus::Degraded { .. })
    }
}

/// Compute `net_edge_bps` for a single filled maker order.
///
/// Formula:
///   side_sign     = +1.0 long / -1.0 short
///   price_edge_bps = side_sign * (mid_fill - mid_submit) / mid_submit * 10_000
///   fee_bps        = fee / (qty * fill_price) * 10_000   (always ≥ 0)
///   net_edge_bps   = price_edge_bps - fee_bps
///
/// Returns `None` when the inputs cannot produce a meaningful metric:
///   * `mid_price_at_submit <= 0.0` (unknown at enqueue)
///   * `qty <= 0.0` or `fill_price <= 0.0` (can't normalise fee to bps)
/// The caller counts the fill regardless; the sum merely skips these cases
/// so bootstrap ticks can't poison the mean.
///
/// 公式：
///   side_sign     = 多 +1 / 空 −1
///   price_edge_bps = side_sign × (mid_fill − mid_submit) / mid_submit × 1e4
///   fee_bps        = fee / (qty × fill_price) × 1e4（恆 ≥ 0）
///   net_edge_bps   = price_edge_bps − fee_bps
///
/// 下列情況回 None（只計數、不進 sum）：submit-mid ≤ 0、qty ≤ 0、成交價 ≤ 0。
pub fn compute_net_edge_bps(
    is_long: bool,
    mid_price_at_submit: f64,
    mid_price_at_fill: f64,
    qty: f64,
    fill_price: f64,
    fee: f64,
) -> Option<f64> {
    if mid_price_at_submit <= 0.0 || qty <= 0.0 || fill_price <= 0.0 {
        return None;
    }
    let side_sign = if is_long { 1.0 } else { -1.0 };
    let price_edge_bps =
        side_sign * (mid_price_at_fill - mid_price_at_submit) / mid_price_at_submit * 10_000.0;
    let fee_bps = fee / (qty * fill_price) * 10_000.0;
    Some(price_edge_bps - fee_bps)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cfg_default() -> MakerKpiConfig {
        MakerKpiConfig::default()
    }

    // ────────────────────────────────────────────────────────────────
    // compute_net_edge_bps / net_edge 公式
    // ────────────────────────────────────────────────────────────────

    #[test]
    fn net_edge_long_favorable_price_move() {
        // Long: submit mid 100 → fill mid 101 → +100 bps before fee.
        // Fee = 0.02 bps of notional. Net ≈ 100 - 0.02 (tiny) - actual.
        // qty=1, fill_price=100, fee=0.001 → fee_bps = 0.001/(1*100)*1e4 = 0.1
        let v = compute_net_edge_bps(true, 100.0, 101.0, 1.0, 100.0, 0.001).unwrap();
        assert!((v - (100.0 - 0.1)).abs() < 1e-9, "got {v}");
    }

    #[test]
    fn net_edge_long_adverse_move() {
        // Long: submit mid 100 → fill mid 99 → -100 bps price edge.
        let v = compute_net_edge_bps(true, 100.0, 99.0, 1.0, 100.0, 0.0).unwrap();
        assert!((v - (-100.0)).abs() < 1e-9, "got {v}");
    }

    #[test]
    fn net_edge_short_favorable_is_price_down() {
        // Short: favorable = mid dropped after submit.
        // side_sign=-1; (99-100)/100*1e4 = -100; signed = +100 (favorable).
        let v = compute_net_edge_bps(false, 100.0, 99.0, 1.0, 100.0, 0.0).unwrap();
        assert!((v - 100.0).abs() < 1e-9, "got {v}");
    }

    #[test]
    fn net_edge_short_adverse_is_price_up() {
        let v = compute_net_edge_bps(false, 100.0, 101.0, 1.0, 100.0, 0.0).unwrap();
        assert!((v - (-100.0)).abs() < 1e-9, "got {v}");
    }

    #[test]
    fn net_edge_returns_none_when_submit_mid_zero() {
        assert!(compute_net_edge_bps(true, 0.0, 100.0, 1.0, 100.0, 0.0).is_none());
    }

    #[test]
    fn net_edge_returns_none_when_qty_zero() {
        assert!(compute_net_edge_bps(true, 100.0, 100.0, 0.0, 100.0, 0.0).is_none());
    }

    #[test]
    fn net_edge_returns_none_when_fill_price_zero() {
        assert!(compute_net_edge_bps(true, 100.0, 100.0, 1.0, 0.0, 0.0).is_none());
    }

    // ────────────────────────────────────────────────────────────────
    // MakerStatsCounters: fill_rate / avg / kpi_status
    // ────────────────────────────────────────────────────────────────

    #[test]
    fn fill_rate_zero_denom_returns_none() {
        let c = MakerStatsCounters::default();
        assert!(c.fill_rate().is_none());
    }

    #[test]
    fn fill_rate_with_samples() {
        let mut c = MakerStatsCounters::default();
        c.filled_full = 3;
        c.filled_partial = 1;
        c.timedout = 6;
        // 4 / (4 + 6) = 0.4
        assert!((c.fill_rate().unwrap() - 0.4).abs() < 1e-9);
    }

    #[test]
    fn avg_net_edge_zero_fills_returns_none() {
        let c = MakerStatsCounters::default();
        assert!(c.avg_net_edge_bps().is_none());
    }

    #[test]
    fn avg_net_edge_mean() {
        let mut c = MakerStatsCounters::default();
        c.filled_full = 2;
        c.sum_net_edge_bps = 10.0; // mean = 5.0
        assert!((c.avg_net_edge_bps().unwrap() - 5.0).abs() < 1e-9);
    }

    #[test]
    fn kpi_status_cold_when_samples_below_min() {
        let mut c = MakerStatsCounters::default();
        c.filled_full = 5;
        c.timedout = 5;
        let cfg = cfg_default(); // min_samples = 20
        assert_eq!(c.kpi_status(&cfg), MakerKpiStatus::Cold);
    }

    #[test]
    fn kpi_status_healthy_when_above_thresholds() {
        let mut c = MakerStatsCounters::default();
        c.filled_full = 18;
        c.timedout = 2;
        c.sum_net_edge_bps = 18.0; // mean = +1.0 bps
        let cfg = cfg_default();
        assert_eq!(c.kpi_status(&cfg), MakerKpiStatus::Healthy);
    }

    #[test]
    fn kpi_status_degraded_low_fill_rate() {
        let mut c = MakerStatsCounters::default();
        c.filled_full = 2; // fill_rate = 2/20 = 0.1 (< 0.15)
        c.timedout = 18;
        c.sum_net_edge_bps = 0.0;
        let cfg = cfg_default();
        match c.kpi_status(&cfg) {
            MakerKpiStatus::Degraded { reason } => {
                assert_eq!(reason, "fill_rate_below_threshold")
            }
            other => panic!("expected Degraded fill_rate, got {:?}", other),
        }
    }

    #[test]
    fn kpi_status_degraded_low_edge() {
        let mut c = MakerStatsCounters::default();
        c.filled_full = 18; // fill_rate = 18/20 = 0.9
        c.timedout = 2;
        c.sum_net_edge_bps = -200.0; // mean = -11.1 bps (< -5)
        let cfg = cfg_default();
        match c.kpi_status(&cfg) {
            MakerKpiStatus::Degraded { reason } => {
                assert_eq!(reason, "net_edge_below_threshold")
            }
            other => panic!("expected Degraded edge, got {:?}", other),
        }
    }

    #[test]
    fn kpi_status_fill_rate_beats_edge_when_both_bad() {
        // Both fill_rate and edge below thresholds → fill_rate reason wins
        // (checked first). Stable reason ordering keeps downstream histograms
        // single-bucketed.
        let mut c = MakerStatsCounters::default();
        c.filled_full = 2; // rate 0.1
        c.timedout = 18;
        c.sum_net_edge_bps = -200.0; // mean very negative
        let cfg = cfg_default();
        match c.kpi_status(&cfg) {
            MakerKpiStatus::Degraded { reason } => {
                assert_eq!(reason, "fill_rate_below_threshold")
            }
            other => panic!("expected Degraded fill_rate precedence, got {:?}", other),
        }
    }

    // ────────────────────────────────────────────────────────────────
    // MakerStats: aggregate & per-symbol wiring
    // ────────────────────────────────────────────────────────────────

    #[test]
    fn record_submit_updates_both_scopes() {
        let mut s = MakerStats::default();
        s.record_submit("BTCUSDT");
        s.record_submit("ETHUSDT");
        s.record_submit("BTCUSDT");
        assert_eq!(s.aggregate.submitted, 3);
        assert_eq!(s.per_symbol.get("BTCUSDT").unwrap().submitted, 2);
        assert_eq!(s.per_symbol.get("ETHUSDT").unwrap().submitted, 1);
    }

    #[test]
    fn record_fill_full_vs_partial_counters() {
        let mut s = MakerStats::default();
        // true_cross=true → filled_full
        s.record_fill("BTCUSDT", true, 100.0, 100.0, 1.0, 100.0, 0.0, true);
        // true_cross=false → filled_partial
        s.record_fill("BTCUSDT", true, 100.0, 100.0, 1.0, 100.0, 0.0, false);
        assert_eq!(s.aggregate.filled_full, 1);
        assert_eq!(s.aggregate.filled_partial, 1);
        assert_eq!(s.per_symbol.get("BTCUSDT").unwrap().filled_full, 1);
        assert_eq!(s.per_symbol.get("BTCUSDT").unwrap().filled_partial, 1);
    }

    #[test]
    fn record_fill_adds_to_sum_only_when_submit_mid_valid() {
        let mut s = MakerStats::default();
        // Valid submit mid → sum += net_edge_bps (= 0 in this case since
        // mid_fill == mid_submit and fee = 0).
        s.record_fill("BTCUSDT", true, 100.0, 100.0, 1.0, 100.0, 0.0, true);
        assert_eq!(s.aggregate.sum_net_edge_bps, 0.0);
        assert_eq!(s.aggregate.filled_full, 1);

        // Unknown submit mid (0.0) → count the fill but skip sum.
        s.record_fill("BTCUSDT", true, 0.0, 100.0, 1.0, 100.0, 0.0, true);
        assert_eq!(s.aggregate.filled_full, 2);
        assert_eq!(s.aggregate.sum_net_edge_bps, 0.0, "bootstrap tick must not poison sum");
    }

    #[test]
    fn record_fill_accumulates_signed_edge() {
        let mut s = MakerStats::default();
        // Long favorable: mid 100 → 101 = +100 bps, fee=0 → net=+100
        s.record_fill("BTCUSDT", true, 100.0, 101.0, 1.0, 101.0, 0.0, true);
        // Short favorable: mid 100 → 99 = +100 bps (signed), fee=0 → net=+100
        s.record_fill("BTCUSDT", false, 100.0, 99.0, 1.0, 99.0, 0.0, true);
        assert!((s.aggregate.sum_net_edge_bps - 200.0).abs() < 1e-6);
        // Per-symbol should mirror aggregate (only 1 symbol active).
        let per = s.per_symbol.get("BTCUSDT").unwrap();
        assert!((per.sum_net_edge_bps - 200.0).abs() < 1e-6);
    }

    #[test]
    fn record_timeout_updates_both_scopes() {
        let mut s = MakerStats::default();
        s.record_timeout("BTCUSDT");
        s.record_timeout("ETHUSDT");
        assert_eq!(s.aggregate.timedout, 2);
        assert_eq!(s.per_symbol.get("BTCUSDT").unwrap().timedout, 1);
        assert_eq!(s.per_symbol.get("ETHUSDT").unwrap().timedout, 1);
    }

    #[test]
    fn record_degraded_fallback_bumps_counter() {
        let mut s = MakerStats::default();
        s.record_degraded_fallback("BTCUSDT");
        s.record_degraded_fallback("BTCUSDT");
        assert_eq!(s.aggregate.degraded_fallbacks, 2);
        assert_eq!(s.per_symbol.get("BTCUSDT").unwrap().degraded_fallbacks, 2);
    }

    // ────────────────────────────────────────────────────────────────
    // MakerStats::status_for — per-symbol with aggregate fallback
    // ────────────────────────────────────────────────────────────────

    #[test]
    fn status_for_unknown_symbol_uses_aggregate() {
        let mut s = MakerStats::default();
        // Build healthy aggregate on a different symbol.
        for _ in 0..18 {
            s.record_fill("BTCUSDT", true, 100.0, 100.0, 1.0, 100.0, 0.0, true);
        }
        for _ in 0..2 {
            s.record_timeout("BTCUSDT");
        }
        // Unknown symbol → no per-symbol entry → aggregate path.
        let cfg = cfg_default();
        assert_eq!(s.status_for("NEWCOIN", &cfg), MakerKpiStatus::Healthy);
    }

    #[test]
    fn status_for_per_symbol_takes_over_when_enough_samples() {
        let mut s = MakerStats::default();
        // Aggregate mixes two symbols into Healthy, but BTCUSDT alone is bad.
        // BTCUSDT: 2 fills / 18 timeouts → fill_rate 0.1 (Degraded)
        for _ in 0..2 {
            s.record_fill("BTCUSDT", true, 100.0, 100.0, 1.0, 100.0, 0.0, true);
        }
        for _ in 0..18 {
            s.record_timeout("BTCUSDT");
        }
        // ETHUSDT: 30 fills / 0 timeouts → fill_rate 1.0 (Healthy)
        for _ in 0..30 {
            s.record_fill("ETHUSDT", true, 100.0, 100.0, 1.0, 100.0, 0.0, true);
        }
        let cfg = cfg_default();
        // BTCUSDT has 20 terminal samples → its own counters decide → Degraded.
        match s.status_for("BTCUSDT", &cfg) {
            MakerKpiStatus::Degraded { reason } => {
                assert_eq!(reason, "fill_rate_below_threshold")
            }
            other => panic!("expected BTCUSDT Degraded, got {:?}", other),
        }
        // ETHUSDT: Healthy from its own counters.
        assert_eq!(s.status_for("ETHUSDT", &cfg), MakerKpiStatus::Healthy);
    }

    #[test]
    fn status_for_cold_symbol_falls_back_to_aggregate() {
        let mut s = MakerStats::default();
        // Aggregate healthy via ETHUSDT (20 fills, 0 timeouts).
        for _ in 0..20 {
            s.record_fill("ETHUSDT", true, 100.0, 100.0, 1.0, 100.0, 0.0, true);
        }
        // BTCUSDT only has 1 timeout → terminal_samples=1 < 20 → fallback.
        s.record_timeout("BTCUSDT");
        let cfg = cfg_default();
        assert_eq!(s.status_for("BTCUSDT", &cfg), MakerKpiStatus::Healthy);
    }

    #[test]
    fn is_degraded_matches_only_degraded_variant() {
        assert!(!MakerKpiStatus::Cold.is_degraded());
        assert!(!MakerKpiStatus::Healthy.is_degraded());
        assert!(MakerKpiStatus::Degraded { reason: "x" }.is_degraded());
    }
}
