//! Phase 2 — demo→live 策略參數促升的 EDGE-ANCHORED criteria gate（純函數）。
//!
//! MODULE_NOTE (中):
//!   模塊用途：對「某策略的一次 demo→live 參數促升」做量化可辯護的 fail-closed
//!     判定。判定**不靠 demo realized PnL**（多頭/趨勢 regime 下的正 PnL 是
//!     down-beta 副產品，非 alpha — 承 project_2026_06_15_demo_loss_rootcause_grid_trend），
//!     而是 anchor 在既有 battle-tested 顯著性防線上：
//!       1. 每 (strategy, symbol) cell 的 `validation_passed` walk-forward OOS 鏈
//!          （James-Stein producer，內含 DSR≥0.90 Bonferroni-deflated / PSR≥0.95 /
//!          OOS-n — `edge_estimate_validation.py`）；
//!       2. live cost wall（`cost_gate_live_with_slippage` 同算式：
//!          `shrunk_bps >= fee_bps/clamp(win_rate) × safety_multiplier`）；
//!       再疊 canary Stage 3→4 可移植的 soak / wall-clock / boundary 風控 metric。
//!   主要型別/函數：`PromotionCriteriaInput`、`ActiveCellEdge`、`PromotionVerdict`
//!     enum（`Eligible` / `Pending(reason)` / `Reject(reason)`）、純函數
//!     `evaluate_promotion_criteria`（10-step 短路 fail-closed 判定，§2.4.E）。
//!   依賴：純 Rust + std。**零 IO**——所有 metric（含 per-cell edge 數據、live
//!     cost model 參數）由 caller 預先 query/snapshot 後以 struct 傳入，鏡像
//!     canary `is_promote_eligible(stage, metrics)` 簽名。
//!   硬邊界：
//!     1. fail-closed：方向模糊 param / boundary 越界 = **Reject**（永不因等待轉
//!        Eligible）；樣本/soak/coverage 不足 = **Pending**（等更多證據）。
//!     2. edge coverage 是 **binding gate**——即使 soak/fills/wall-clock 全過，
//!        沒有 OOS-validated 清 live 成本牆的正 edge（weighted-coverage<floor）
//!        仍 Pending。0 validated cell（今天的真實狀態）→ 任何策略一律 Pending，
//!        這是 DESIRED 行為（root #5/#6/#12）。
//!     3. 結構上**不讀** demo PnL（無 `realized_pnl` 欄）、不讀
//!        `explore_eligible`/`explore_remaining`（explore-grace cell 無法冒充
//!        live-qualified），且額外要求 `validation_reason == "passed"`。
//!     4. drawdown bound 用 **LIVE** envelope（12%/7%）量測 demo 軌跡，非 demo
//!        自己的寬鬆 envelope（25%/15%）——由 caller 把越界次數編進
//!        `demo_boundary_violation_count`（§2.4.D）。

use serde::{Deserialize, Serialize};

// ---------------------------------------------------------------------------
// 閾值常數（PA 初擬，QC MANDATORY 復核釘死 — §2.4「待 QC 釘死」6 項）。
// 全部標 PROVISIONAL；改值不改判定邏輯結構。
// ---------------------------------------------------------------------------

/// weighted-coverage 下界（PROVISIONAL，QC 釘）。
/// 為什麼 0.6：majority 比例，單 cell cherry-pick 結構上撐不起 25-sym 策略。
pub const COVERAGE_FLOOR: f64 = 0.6;

/// qualified cell 絕對下界（PROVISIONAL，QC 釘）。
/// 為什麼還要絕對下界：防單一高 n_trades cell 把 weighted-coverage 撐過 floor；
/// caller 另以 `max(MIN_QUALIFIED_CELLS, ceil(active/2))` 取較嚴者（見判定邏輯）。
pub const MIN_QUALIFIED_CELLS: usize = 2;

/// per-cell OOS 樣本下界（PROVISIONAL，對齊 edge_estimate_validation.min_oos_n=30；
/// QC 可上調至 runtime 60）。
pub const MIN_CELL_N_TRADES: u64 = 30;

/// demo soak wall-clock 下界（鏡像 canary STAGE3_WALL_CLOCK_MS = 21d）。
pub const SOAK_WALL_CLOCK_MS: i64 = 21 * 24 * 60 * 60 * 1000;

/// 自上次 param 變動以來的穩定窗（鏡像 canary sample_floor 72h）。
/// 為什麼用 wall-clock 而非「N 輪 loop」：loop 頻率變動不影響 72h 物理時間。
pub const STABLE_SINCE_CHANGE_MS: i64 = 72 * 60 * 60 * 1000;

/// soak 窗內可歸因 demo fills 下界（鏡像 canary STAGE2_ENTRY_FILLS_MIN = 30）。
pub const MIN_ATTRIBUTABLE_FILLS: i64 = 30;

/// attribution_chain_ok additional gate floor（鏡像 canary
/// STAGE3_ATTRIBUTION_RATIO_FLOOR = 0.7）。
pub const ATTRIBUTION_CHAIN_FLOOR: f64 = 0.7;

// ---------------------------------------------------------------------------
// §2.4.F v1 DIRECTION BOUND — unambiguous「tighten = 更保守 = 交易更少」單調語意
// 的 param allowlist（PROVISIONAL，QC MANDATORY 釘死最終名單）。
//
// 為什麼要 allowlist：25-sym live blast radius 下，方向倒置的促升風險高；v1 只放
// 行方向語意單調的旋鈕（↑=更難進場/間隔更長），其餘 param 一律 Reject 直到 QC
// 建立 direction×param consistency map（Phase 2.1）。
//
// allowlist 名稱與 strategy param_ranges 的 `name` 對齊（親查 strategies/*/params.rs：
// cooldown_ms / min_events / funding_threshold / adx_threshold / *_threshold_usd 皆實在）。
// ---------------------------------------------------------------------------

/// v1 PROVISIONAL allowlist：方向單調保守的 param key。
/// 注意：以「前綴/精確」兩種匹配（見 `is_direction_allowed`）——`min_*` 與
/// `*_threshold_usd` 是前綴族；其餘為精確 key。
pub const DIRECTION_ALLOWLIST_EXACT: &[&str] = &[
    "cooldown_ms",
    "reject_cooldown_ms",
    "churn_breaker_cooldown_ms",
    "funding_threshold",
    "adx_threshold",
];

/// allowlist 前綴族（單調保守的樣本/事件/門檻下界）。
/// `min_*`：要求更多證據才進場（↑=更保守）；
/// `*_threshold_usd`：要求更強信號才進場（↑=更保守）。
pub const DIRECTION_ALLOWLIST_PREFIX: &[&str] = &["min_"];
pub const DIRECTION_ALLOWLIST_SUFFIX: &[&str] = &["_threshold_usd"];

/// 判定單一 param key 是否方向語意明確（在 v1 allowlist 內）。
///
/// 為什麼 fail-closed：不在 allowlist 的 param（weight_* / take_profit_pct /
/// max_hold_ms / *_ratio / sizing 等）方向可反轉有效信號，v1 一律拒，直到 QC map。
fn is_direction_allowed(name: &str) -> bool {
    if DIRECTION_ALLOWLIST_EXACT.contains(&name) {
        return true;
    }
    if DIRECTION_ALLOWLIST_PREFIX
        .iter()
        .any(|p| name.starts_with(p))
    {
        return true;
    }
    if DIRECTION_ALLOWLIST_SUFFIX.iter().any(|s| name.ends_with(s)) {
        return true;
    }
    false
}

// ---------------------------------------------------------------------------
// 輸入 struct — caller（IPC handler / route）預先 query 後填入。
// ---------------------------------------------------------------------------

/// 單一 active symbol 的 live edge cell 快照（§2.4.B per-cell 8 條檢查的輸入）。
///
/// 注意：`is_fresh` 不在此（freshness 是 snapshot 級單一 `_meta.updated_at`，對全
/// snapshot 一個 bool，由 `PromotionCriteriaInput.edge_estimates_fresh` 統一帶入；
/// 鏡像 edge_estimates.rs is_fresh 語意）。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ActiveCellEdge {
    pub symbol: String,
    /// get_cell 是否存在（None → 該 symbol unqualified）。
    pub present: bool,
    pub validation_passed: bool,
    /// 必須 == "passed"（拒 explore-grace / insufficient_* / *_below_threshold）。
    pub validation_reason: String,
    /// runtime-derived bps（非 legacy shrunk_bps 回退，P1-09）。
    pub from_runtime_field: bool,
    pub shrunk_bps: f64,
    pub win_rate: f64,
    pub n_trades: u64,
}

/// 促升 criteria 判定的完整輸入快照（§2.4.E）。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PromotionCriteriaInput {
    // ── §2.4.B edge coverage（per active-symbol cell）──
    /// 每 active symbol 一筆（caller 從 live EdgeEstimates snapshot + active-symbol
    /// 解析後填；空 → Reject("no_active_symbols")）。
    pub active_cells: Vec<ActiveCellEdge>,

    // ── §2.4.C/D canary 可移植 soak / 風控 metric ──
    pub demo_soak_wall_clock_ms: i64,
    pub ms_since_last_param_change: i64,
    pub attributable_demo_fills: i64,
    /// §2.4.D：以 LIVE envelope（12%/7%）量測 demo 軌跡的越界次數（caller 算）。
    pub demo_boundary_violation_count: i64,
    /// additional where-available：None → Pending（不 fail，等下次），非 binding。
    pub attribution_chain_ok_ratio: Option<f64>,

    // ── live cost model 參數（reuse risk_config_live.toml slippage.*）──
    /// 來回 taker+滑點成本 bps：`2×(fee_rate + slippage)×10000`（caller 用 live
    /// fee_rate + lookup_slippage 算好，鏡像 cost_gate_live_with_slippage:299）。
    pub fee_bps_round_trip: f64,
    /// `slippage.cost_gate_safety_multiplier`（live SSOT）。
    pub cost_gate_safety_multiplier: f64,
    /// `slippage.cost_gate_win_rate_floor`（live SSOT，win_rate clamp 下界）。
    pub cost_gate_win_rate_floor: f64,
    /// snapshot 級 is_fresh(now, edge_ttl)，caller 對 live snapshot 算一次。
    pub edge_estimates_fresh: bool,

    // ── §2.4.F direction bound ──
    /// 本次 promote 相對 pre-promotion 真正改動的 param key（route 算 diff 傳入）。
    pub tuned_param_names: Vec<String>,
}

// ---------------------------------------------------------------------------
// 輸出 enum — 鏡像 canary PromoteVerdict。
// ---------------------------------------------------------------------------

/// 促升 criteria 判定結果。reason 為穩定短 token（GUI surface + audit row 用）。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum PromotionVerdict {
    /// 全部 binding + additional 條件 PASS → 可促升（仍須 operator + 5-gate + token）。
    Eligible,
    /// 證據不足（樣本/soak/coverage/freshness/attribution 未達）→ 等更多證據。
    Pending { reason: String },
    /// 硬拒（方向模糊 / boundary 越界 / 無 active symbol）→ 永不因等待轉 Eligible。
    Reject { reason: String },
}

impl PromotionVerdict {
    /// 穩定短標籤（audit row / GUI / healthcheck 用，不含可變細節）。
    pub fn tag(&self) -> &'static str {
        match self {
            PromotionVerdict::Eligible => "eligible",
            PromotionVerdict::Pending { .. } => "pending",
            PromotionVerdict::Reject { .. } => "reject",
        }
    }

    /// 人讀 reason（Eligible 無 reason → 空字串）。
    pub fn reason(&self) -> &str {
        match self {
            PromotionVerdict::Eligible => "",
            PromotionVerdict::Pending { reason } | PromotionVerdict::Reject { reason } => reason,
        }
    }
}

// ---------------------------------------------------------------------------
// per-cell live cost wall — reuse cost_gate_live_with_slippage 算式（不另造成本模型）。
// ---------------------------------------------------------------------------

/// 單一 cell 是否清 live cost wall（degradation haircut）。
///
/// 鏡像 `intent_processor::gates::cost_gate_live_with_slippage`：
///   `threshold_bps = fee_bps / clamp(win_rate, floor, 1.0) × safety_multiplier`
///   通過條件 `shrunk_bps >= threshold_bps`。
///
/// 為什麼 reuse 而非自定義：QC 要的是「demo→live degradation haircut，shrunk_bps
/// 須清 LIVE 成本牆（taker fee + 保守滑點 + win-rate 加權）」，這正是 live
/// cost_gate 已釘的算式；自造成本模型會與 live gate drift。
fn clears_live_cost_wall(
    shrunk_bps: f64,
    win_rate: f64,
    fee_bps_round_trip: f64,
    safety_multiplier: f64,
    win_rate_floor: f64,
) -> bool {
    let wr = win_rate.clamp(win_rate_floor, 1.0);
    // 防呆：wr 經 clamp 後 ∈ [floor, 1]，floor 預設 > 0（live SSOT），不會除零。
    if wr <= 0.0 {
        return false;
    }
    let threshold_bps = fee_bps_round_trip / wr * safety_multiplier;
    shrunk_bps >= threshold_bps
}

/// 單一 cell 是否 qualified（§2.4.B per-cell 8 條全真）。
///
/// 8 條：present + validation_passed + validation_reason=="passed" +
///       snapshot fresh + from_runtime_field + shrunk_bps>0 + n_trades>=floor +
///       清 live cost wall。
fn cell_qualified(cell: &ActiveCellEdge, input: &PromotionCriteriaInput) -> bool {
    cell.present
        && cell.validation_passed
        && cell.validation_reason == "passed"
        && input.edge_estimates_fresh
        && cell.from_runtime_field
        && cell.shrunk_bps > 0.0
        && cell.n_trades >= MIN_CELL_N_TRADES
        && clears_live_cost_wall(
            cell.shrunk_bps,
            cell.win_rate,
            input.fee_bps_round_trip,
            input.cost_gate_safety_multiplier,
            input.cost_gate_win_rate_floor,
        )
}

// ---------------------------------------------------------------------------
// 核心純函數 — 10-step 短路 fail-closed 判定（§2.4.E）。
// ---------------------------------------------------------------------------

/// 對一次促升的完整 metric 快照評估 EDGE-ANCHORED criteria。
///
/// 為什麼 fail-closed + 短路：方向模糊 param / boundary 越界是 **Reject**（硬拒，
/// 永不因等待轉 Eligible）；其餘樣本/soak/coverage 不足是 **Pending**（等更多
/// 證據）。edge coverage 是 **binding gate**——沒有 OOS-validated 清 live 成本牆
/// 的正 edge 就沒有可促升的 alpha（root #5/#6/#12）。
pub fn evaluate_promotion_criteria(input: &PromotionCriteriaInput) -> PromotionVerdict {
    // Step 1 — direction bound（§2.4.F）：任一 param 不在 allowlist → Reject。
    for name in &input.tuned_param_names {
        if !is_direction_allowed(name) {
            return PromotionVerdict::Reject {
                reason: format!("param_direction_ambiguous: {name}"),
            };
        }
    }

    // Step 2 — active-symbol 空：無 live blast radius 即無促升意義 → Reject。
    if input.active_cells.is_empty() {
        return PromotionVerdict::Reject {
            reason: "no_active_symbols".to_string(),
        };
    }

    // Step 3 — boundary（§2.4.D）：demo 曾突破 LIVE drawdown envelope → 硬拒（root #5）。
    if input.demo_boundary_violation_count > 0 {
        return PromotionVerdict::Reject {
            reason: "demo_breached_live_drawdown_envelope".to_string(),
        };
    }

    // Step 4 — snapshot freshness：陳舊 edge 快照不可作促升證據 → Pending。
    if !input.edge_estimates_fresh {
        return PromotionVerdict::Pending {
            reason: "edge_snapshot_stale".to_string(),
        };
    }

    // Step 5 — attributable fills：樣本充足性閘（鏡像 canary Stage2 entry fills）。
    if input.attributable_demo_fills < MIN_ATTRIBUTABLE_FILLS {
        return PromotionVerdict::Pending {
            reason: format!(
                "insufficient_attributable_fills: {}<{}",
                input.attributable_demo_fills, MIN_ATTRIBUTABLE_FILLS
            ),
        };
    }

    // Step 6 — wall-clock soak（鏡像 canary Stage3 21d）。
    if input.demo_soak_wall_clock_ms < SOAK_WALL_CLOCK_MS {
        return PromotionVerdict::Pending {
            reason: format!(
                "soak_below_21d: {}ms<{}ms",
                input.demo_soak_wall_clock_ms, SOAK_WALL_CLOCK_MS
            ),
        };
    }

    // Step 7 — since-change：param 須穩定 ≥72h（鏡像 canary sample_floor）。
    if input.ms_since_last_param_change < STABLE_SINCE_CHANGE_MS {
        return PromotionVerdict::Pending {
            reason: format!(
                "param_changed_within_72h: {}ms<{}ms",
                input.ms_since_last_param_change, STABLE_SINCE_CHANGE_MS
            ),
        };
    }

    // Step 8 — edge coverage（BINDING，§2.4.B）：per-cell 8 條 + weighted coverage。
    //   weighted-coverage = Σ n_trades(qualified) / Σ n_trades(all active)；
    //   qualified_count = per-cell 全過者數。
    //   絕對下界取 max(MIN_QUALIFIED_CELLS, ceil(active/2))（防單高-n_trades cell
    //   撐起整個 coverage）。
    let active_count = input.active_cells.len();
    let mut qualified_count: usize = 0;
    let mut sum_n_all: u128 = 0;
    let mut sum_n_qualified: u128 = 0;
    for cell in &input.active_cells {
        sum_n_all += cell.n_trades as u128;
        if cell_qualified(cell, input) {
            qualified_count += 1;
            sum_n_qualified += cell.n_trades as u128;
        }
    }
    // weighted coverage：分母為 0（全 cell n_trades=0）時 coverage=0（fail-closed）。
    let coverage = if sum_n_all == 0 {
        0.0
    } else {
        sum_n_qualified as f64 / sum_n_all as f64
    };
    // ceil(active/2) without float：(active + 1) / 2。
    let min_qualified_required = MIN_QUALIFIED_CELLS.max(active_count.div_ceil(2));
    if coverage < COVERAGE_FLOOR || qualified_count < min_qualified_required {
        return PromotionVerdict::Pending {
            reason: format!(
                "edge_coverage_below_floor: q={}/{} cov={:.4} (need q>={} cov>={})",
                qualified_count, active_count, coverage, min_qualified_required, COVERAGE_FLOOR
            ),
        };
    }

    // Step 9 — attribution（additional where-available，非 binding）：
    //   None → Pending（不 fail，等 [55] healthcheck 算出）；< floor → Pending。
    match input.attribution_chain_ok_ratio {
        None => {
            return PromotionVerdict::Pending {
                reason: "attribution_not_computed".to_string(),
            };
        }
        Some(r) if r < ATTRIBUTION_CHAIN_FLOOR => {
            return PromotionVerdict::Pending {
                reason: format!(
                    "attribution_chain_below_floor: {r:.4}<{ATTRIBUTION_CHAIN_FLOOR}"
                ),
            };
        }
        Some(_) => {}
    }

    // Step 10 — 全過 → Eligible（仍須 operator + 5-gate + token；criteria 只是業務前提）。
    PromotionVerdict::Eligible
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 建一個「全部 8 條 per-cell 全過」的 qualified cell（high n_trades，清成本牆）。
    fn good_cell(symbol: &str, n_trades: u64) -> ActiveCellEdge {
        ActiveCellEdge {
            symbol: symbol.to_string(),
            present: true,
            validation_passed: true,
            validation_reason: "passed".to_string(),
            from_runtime_field: true,
            // shrunk_bps 遠大於 cost wall：fee_bps=8 / wr=0.6 × 1.5 = 20 bps；給 50。
            shrunk_bps: 50.0,
            win_rate: 0.6,
            n_trades,
        }
    }

    /// 一個全條件達成的 base input（caller 可逐欄覆寫做 mutation 測試）。
    fn good_input(cells: Vec<ActiveCellEdge>) -> PromotionCriteriaInput {
        PromotionCriteriaInput {
            active_cells: cells,
            demo_soak_wall_clock_ms: SOAK_WALL_CLOCK_MS + 1,
            ms_since_last_param_change: STABLE_SINCE_CHANGE_MS + 1,
            attributable_demo_fills: MIN_ATTRIBUTABLE_FILLS + 5,
            demo_boundary_violation_count: 0,
            attribution_chain_ok_ratio: Some(0.9),
            // fee_bps=8 → cost wall = 8/0.6×1.5 = 20bps；good_cell shrunk_bps=50 清過。
            fee_bps_round_trip: 8.0,
            cost_gate_safety_multiplier: 1.5,
            cost_gate_win_rate_floor: 0.2,
            edge_estimates_fresh: true,
            // cooldown_ms 在 v1 allowlist 內。
            tuned_param_names: vec!["cooldown_ms".to_string()],
        }
    }

    // ── 現實狀態：0-validated-cell → 非 Eligible（DESIRED fail-closed）──

    #[test]
    fn zero_validated_cells_is_pending_not_eligible() {
        // 鏡像今天真實狀態：cell present 但 validation_passed=false。
        let cells = vec![
            ActiveCellEdge {
                symbol: "BTCUSDT".to_string(),
                present: true,
                validation_passed: false,
                validation_reason: "insufficient_total_samples".to_string(),
                from_runtime_field: true,
                shrunk_bps: 50.0,
                win_rate: 0.6,
                n_trades: 120,
            },
            ActiveCellEdge {
                symbol: "ETHUSDT".to_string(),
                present: true,
                validation_passed: false,
                validation_reason: "dsr_below_threshold".to_string(),
                from_runtime_field: true,
                shrunk_bps: 40.0,
                win_rate: 0.55,
                n_trades: 100,
            },
        ];
        let v = evaluate_promotion_criteria(&good_input(cells));
        assert_ne!(v, PromotionVerdict::Eligible);
        assert_eq!(v.tag(), "pending");
        assert!(v.reason().starts_with("edge_coverage_below_floor"));
    }

    #[test]
    fn empty_active_cells_is_reject() {
        let v = evaluate_promotion_criteria(&good_input(vec![]));
        assert_eq!(
            v,
            PromotionVerdict::Reject {
                reason: "no_active_symbols".to_string()
            }
        );
    }

    // ── all-validated-fresh-positive-n>=30-majority → Eligible ──

    #[test]
    fn all_validated_majority_is_eligible() {
        let cells = vec![
            good_cell("BTCUSDT", 120),
            good_cell("ETHUSDT", 100),
            good_cell("SOLUSDT", 80),
        ];
        let v = evaluate_promotion_criteria(&good_input(cells));
        assert_eq!(v, PromotionVerdict::Eligible);
    }

    // ── explore-grace validation_reason → 不 Eligible（拒冒充）──

    #[test]
    fn explore_grace_reason_is_not_eligible() {
        // validation_passed=true 但 reason 非 "passed"（explore-gate overlay 不寫
        // validation_reason="passed"；模擬探索期 cell 試圖冒充）。
        let mut cells = vec![good_cell("BTCUSDT", 120), good_cell("ETHUSDT", 100)];
        for c in &mut cells {
            c.validation_reason = "explore_grace".to_string();
        }
        let v = evaluate_promotion_criteria(&good_input(cells));
        assert_ne!(v, PromotionVerdict::Eligible);
        // 兩 cell 皆 unqualified（reason!="passed"）→ coverage=0 → Pending。
        assert_eq!(v.tag(), "pending");
        assert!(v.reason().starts_with("edge_coverage_below_floor"));
    }

    // ── denylisted direction param → Reject（step 1 短路，先於其他閘）──

    #[test]
    fn denylisted_direction_param_is_reject() {
        let mut input = good_input(vec![good_cell("BTCUSDT", 120), good_cell("ETHUSDT", 100)]);
        input.tuned_param_names = vec!["weight_adx".to_string()];
        let v = evaluate_promotion_criteria(&input);
        assert_eq!(v.tag(), "reject");
        assert_eq!(v.reason(), "param_direction_ambiguous: weight_adx");
    }

    #[test]
    fn take_profit_and_ratio_params_are_denylisted() {
        for bad in &["take_profit_pct", "max_hold_ms", "entry_basis_ratio", "size_multiplier"] {
            let mut input = good_input(vec![good_cell("BTCUSDT", 120), good_cell("ETHUSDT", 100)]);
            input.tuned_param_names = vec![bad.to_string()];
            let v = evaluate_promotion_criteria(&input);
            assert_eq!(v.tag(), "reject", "param {bad} must Reject");
        }
    }

    #[test]
    fn allowlisted_direction_params_pass_step1() {
        // 確認 allowlist 全族（exact + min_ prefix + _threshold_usd suffix）不被 step1 拒。
        for ok in &[
            "cooldown_ms",
            "reject_cooldown_ms",
            "funding_threshold",
            "adx_threshold",
            "min_events",
            "default_threshold_usd",
            "btc_threshold_usd",
            "eth_threshold_usd",
        ] {
            let mut input = good_input(vec![good_cell("BTCUSDT", 120), good_cell("ETHUSDT", 100)]);
            input.tuned_param_names = vec![ok.to_string()];
            let v = evaluate_promotion_criteria(&input);
            assert_eq!(v, PromotionVerdict::Eligible, "param {ok} should pass");
        }
    }

    // ── live-cost-wall fail → 該 cell unqualified → coverage 不足 → Pending ──

    #[test]
    fn live_cost_wall_fail_blocks_promotion() {
        // shrunk_bps=5 < cost wall 20bps（fee 8 / wr 0.6 × 1.5）→ 不清成本牆。
        let mut cells = vec![good_cell("BTCUSDT", 120), good_cell("ETHUSDT", 100)];
        for c in &mut cells {
            c.shrunk_bps = 5.0;
        }
        let v = evaluate_promotion_criteria(&good_input(cells));
        assert_ne!(v, PromotionVerdict::Eligible);
        assert_eq!(v.tag(), "pending");
        assert!(v.reason().starts_with("edge_coverage_below_floor"));
    }

    // ── boundary breach → Reject（先於 coverage）──

    #[test]
    fn demo_breached_live_envelope_is_reject() {
        let mut input = good_input(vec![good_cell("BTCUSDT", 120), good_cell("ETHUSDT", 100)]);
        input.demo_boundary_violation_count = 1;
        let v = evaluate_promotion_criteria(&input);
        assert_eq!(
            v,
            PromotionVerdict::Reject {
                reason: "demo_breached_live_drawdown_envelope".to_string()
            }
        );
    }

    // ── soak / fills / since-change / freshness Pending 分支 ──

    #[test]
    fn stale_snapshot_is_pending() {
        let mut input = good_input(vec![good_cell("BTCUSDT", 120), good_cell("ETHUSDT", 100)]);
        input.edge_estimates_fresh = false;
        let v = evaluate_promotion_criteria(&input);
        assert_eq!(v.tag(), "pending");
        assert_eq!(v.reason(), "edge_snapshot_stale");
    }

    #[test]
    fn insufficient_fills_is_pending() {
        let mut input = good_input(vec![good_cell("BTCUSDT", 120), good_cell("ETHUSDT", 100)]);
        input.attributable_demo_fills = MIN_ATTRIBUTABLE_FILLS - 1;
        let v = evaluate_promotion_criteria(&input);
        assert_eq!(v.tag(), "pending");
        assert!(v.reason().starts_with("insufficient_attributable_fills"));
    }

    #[test]
    fn soak_below_21d_is_pending() {
        let mut input = good_input(vec![good_cell("BTCUSDT", 120), good_cell("ETHUSDT", 100)]);
        input.demo_soak_wall_clock_ms = SOAK_WALL_CLOCK_MS - 1;
        let v = evaluate_promotion_criteria(&input);
        assert_eq!(v.tag(), "pending");
        assert!(v.reason().starts_with("soak_below_21d"));
    }

    #[test]
    fn param_changed_within_72h_is_pending() {
        let mut input = good_input(vec![good_cell("BTCUSDT", 120), good_cell("ETHUSDT", 100)]);
        input.ms_since_last_param_change = STABLE_SINCE_CHANGE_MS - 1;
        let v = evaluate_promotion_criteria(&input);
        assert_eq!(v.tag(), "pending");
        assert!(v.reason().starts_with("param_changed_within_72h"));
    }

    // ── attribution additional gate ──

    #[test]
    fn attribution_none_is_pending() {
        let mut input = good_input(vec![good_cell("BTCUSDT", 120), good_cell("ETHUSDT", 100)]);
        input.attribution_chain_ok_ratio = None;
        let v = evaluate_promotion_criteria(&input);
        assert_eq!(v.tag(), "pending");
        assert_eq!(v.reason(), "attribution_not_computed");
    }

    #[test]
    fn attribution_below_floor_is_pending() {
        let mut input = good_input(vec![good_cell("BTCUSDT", 120), good_cell("ETHUSDT", 100)]);
        input.attribution_chain_ok_ratio = Some(0.5);
        let v = evaluate_promotion_criteria(&input);
        assert_eq!(v.tag(), "pending");
        assert!(v.reason().starts_with("attribution_chain_below_floor"));
    }

    // ── MUTATION-BITE: coverage check（單 cell cherry-pick 不能過）──

    #[test]
    fn single_cherry_picked_cell_cannot_pass_majority() {
        // 4 active cell，只有 1 個 qualified（high n_trades），其餘 3 個 unqualified。
        // weighted-coverage 看似可被高 n_trades 撐高，但 qualified_count=1 <
        // ceil(4/2)=2 的絕對下界 → 必 Pending（mutation-bite：移除絕對下界這條會誤過）。
        let qualified = good_cell("BTCUSDT", 100_000); // 巨大 n_trades 試圖撐 coverage
        let mut bad1 = good_cell("ETHUSDT", 30);
        bad1.validation_passed = false;
        bad1.validation_reason = "psr_below_threshold".to_string();
        let mut bad2 = good_cell("SOLUSDT", 30);
        bad2.validation_passed = false;
        bad2.validation_reason = "dsr_below_threshold".to_string();
        let mut bad3 = good_cell("XRPUSDT", 30);
        bad3.validation_passed = false;
        bad3.validation_reason = "insufficient_total_samples".to_string();
        let cells = vec![qualified, bad1, bad2, bad3];
        let v = evaluate_promotion_criteria(&good_input(cells));
        assert_eq!(v.tag(), "pending");
        // weighted coverage 應 >= floor（巨 n_trades），但 qualified_count=1<2 → Pending。
        assert!(v.reason().starts_with("edge_coverage_below_floor"));
        assert!(v.reason().contains("q=1/4"));
    }

    #[test]
    fn n_trades_below_floor_unqualifies_cell() {
        // n_trades=29 < MIN_CELL_N_TRADES(30) → 該 cell unqualified。
        let mut cells = vec![good_cell("BTCUSDT", 29), good_cell("ETHUSDT", 29)];
        for c in &mut cells {
            c.n_trades = MIN_CELL_N_TRADES - 1;
        }
        let v = evaluate_promotion_criteria(&good_input(cells));
        assert_ne!(v, PromotionVerdict::Eligible);
        assert_eq!(v.tag(), "pending");
        assert!(v.reason().starts_with("edge_coverage_below_floor"));
    }

    #[test]
    fn from_runtime_field_false_unqualifies_cell() {
        let mut cells = vec![good_cell("BTCUSDT", 120), good_cell("ETHUSDT", 100)];
        for c in &mut cells {
            c.from_runtime_field = false;
        }
        let v = evaluate_promotion_criteria(&good_input(cells));
        assert_ne!(v, PromotionVerdict::Eligible);
        assert_eq!(v.tag(), "pending");
    }

    // ── MUTATION-BITE: cost-wall 算式（明確驗 threshold 邊界）──

    #[test]
    fn cost_wall_boundary_is_inclusive() {
        // fee_bps=8, wr=0.6 (>floor 0.2), mult=1.5 → threshold = 8/0.6×1.5 = 20.0。
        // shrunk_bps 恰 == 20.0 → 應通過（>=，inclusive）。
        assert!(clears_live_cost_wall(20.0, 0.6, 8.0, 1.5, 0.2));
        // 19.99 → 不通過。
        assert!(!clears_live_cost_wall(19.99, 0.6, 8.0, 1.5, 0.2));
    }

    #[test]
    fn cost_wall_uses_win_rate_floor_clamp() {
        // win_rate=0.05 被 clamp 到 floor 0.2 → threshold = 8/0.2×1.5 = 60.0。
        // 若沒 clamp（用 0.05）→ threshold = 8/0.05×1.5 = 240 → 50 不過；
        // clamp 後 threshold=60 → 50 仍不過。給 shrunk=70 驗 clamp 生效（>60 過）。
        assert!(clears_live_cost_wall(70.0, 0.05, 8.0, 1.5, 0.2));
        assert!(!clears_live_cost_wall(50.0, 0.05, 8.0, 1.5, 0.2));
    }

    #[test]
    fn verdict_tag_and_reason_stable() {
        assert_eq!(PromotionVerdict::Eligible.tag(), "eligible");
        assert_eq!(PromotionVerdict::Eligible.reason(), "");
        let p = PromotionVerdict::Pending {
            reason: "x".to_string(),
        };
        assert_eq!(p.tag(), "pending");
        assert_eq!(p.reason(), "x");
    }
}
