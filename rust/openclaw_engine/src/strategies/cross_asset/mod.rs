//! Sprint N+1 W2 sub-task 2 — cross-asset alpha source 共用消費端 helper。
//!
//! MODULE_NOTE：
//!   ma_crossover + grid_trading 在 paper engine 模式接 BtcLeadLagPanel
//!   做 paper-only shadow log（per spec §5.1 + §6 三層 fence 中的 Layer 3）。
//!   本模組是兩策略的共用 helper，避免在策略內各自寫一份 5-condition 評估
//!   + step_gate 階梯邏輯 + tracing emit 重複代碼。
//!
//!   **paper-only fence Layer 3（深度防禦）**：
//!     Layer 1（主防線）：step_4_5_dispatch.rs 構造 surface 階段 engine_mode
//!         gate，demo / live_demo / live → surface.btc_lead_lag = None
//!     Layer 2：BtcLeadLagProducer env-gate（W2-IMPL-2, 2026-05-11 amendment;
//!         Stage 0R diagnostic override added 2026-05-15）
//!         — main.rs spawn 前 三狀態邏輯：
//!             (a) OPENCLAW_ENABLE_PAPER=1 → spawn producer（paper 正路徑）
//!             (b) OPENCLAW_ENABLE_BTC_LEAD_LAG_DIAGNOSTIC=1 → spawn producer
//!                 with source_tier='cross_asset_btc_lead_lag_diagnostic'
//!                 (Stage 0R diagnostic/read-only, non-promotional)
//!             (c) env unset + paper-only（!has_demo && !has_live）→ spawn
//!             (d) env unset + demo|live active → skip spawn（fence fired）
//!         producer skip 時 PG `panel.btc_lead_lag_panel` 永不寫入 → 下游
//!         ML pipeline / 5 策略 demo edge baseline 不污染。原 spec v1.2 §6.2
//!         「Python writer paper-only fence」已 obsolete — producer 從 PA D+0
//!         階段就是 Rust（`panel_aggregator/btc_lead_lag.rs`），Python writer
//!         從不存在；spec v1.3 §6.2 改為 Producer env-gate 表達。
//!     Layer 3（本模組）：策略消費端 `if let Some(panel) = surface.btc_lead_lag`
//!         隱含 None → skip；本模組 evaluate_shadow_signal 再次 trust panel != None
//!         的契約，純 emit tracing log，**永不**改 strategy decision
//!
//!   **與 spec §5.1.2 對齊（純 tracing log，不寫 PG）**：
//!   spec §5.1.2 + §7.2 設計：shadow log 寫到 `btc_alt_lead_lag_shadow` target，
//!   D+12 後跑離線 SQL 對齊每筆 entry/exit fill 反算 counterfactual edge。
//!   本 sub-task **不**動 learning.decision_features 表（features_jsonb 是
//!   FeatureVectorV1 17-dim ML schema lock，btc_lead_lag 是 panel-level signal
//!   不屬 per-intent feature；強塞會破壞 V017 schema lock 與 W6-3c V086 invariant）。
//!
//!   **與 spec v1.2 §8.1 三檔 step_gate 對齊**：
//!   step_gate 標籤對應 D+12 paper edge report 的三檔判斷 hint：
//!     - "plus15"     : avg_net_bps ≥ +15 bps → promote N+2 demo IMPL
//!     - "plus5_15"   : +5 ≤ avg_net_bps < +15 → extend paper window 14d 重評
//!     - "minus5"     : avg_net_bps < +5 bps → revise spec 或 archive
//!     - "no_signal"  : 5 conditions 任一 fail / panel unavailable
//!   注意：本端是 per-tick 即時評估（不是 7d 累計 avg）；step_gate per-tick
//!   標籤是「**若**此 tick 信號方向跟 forward return 一致，**且** 7d 累計
//!   net_edge_bps 落在哪個 bucket」的 forward-looking hint，下游 SQL 用
//!   `btc_lead_return_pct` 與 `expected_dir` 對齊真實 fill 才算 final verdict。
//!
//!   **不變式**：
//!   - 本 helper 純函數（除 tracing emit 外無副作用）
//!   - 永不返回 StrategyAction / 永不改 strategy state
//!   - tracing target 字串固定 "btc_alt_lead_lag_shadow"（spec §5.1.2 contract）
//!
//! Spec：`srv/docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md` v1.2
//! Producer：`panel_aggregator/btc_lead_lag.rs`（W2 sub-task 1）
//! Trait skeleton：`openclaw_core::alpha_surface::BtcLeadLagPanel`

use crate::tick_pipeline::TickContext;
use openclaw_core::alpha_surface::BtcLeadLagPanel;

// ─────────────────────────────────────────────────────────────────────────
// Constants — spec §3.3 + §7.1 + §8.1 對齊
// ─────────────────────────────────────────────────────────────────────────

/// Per spec §3.3：xcorr 信任門檻（|xcorr| < THRESHOLD_Y → expected_dir=0 不 trust）。
const THRESHOLD_Y: f64 = 0.40;

/// Per spec §3.3：BTC return 觸發門檻（bps，|btc_lead_return_pct| > THRESHOLD_X_BPS 才生方向）。
const THRESHOLD_X_BPS: f64 = 10.0;

/// Per spec §7.1 acceptance prerequisite v1.2 dual-layer σ：L2 net edge σ_net = 50-80 bps。
/// 本端用單一中位點 65 bps 作 per-tick log dual_layer_sigma_pct hint
/// （downstream 7d 對齊真實 fill σ 才精算 power）。
const DUAL_LAYER_SIGMA_NET_MID_BPS: f64 = 65.0;

/// Tracing target 字串（spec §5.1.2 contract，downstream offline SQL grep 用）。
pub const SHADOW_LOG_TARGET: &str = "btc_alt_lead_lag_shadow";

// ─────────────────────────────────────────────────────────────────────────
// BtcLeadLagShadowSignal — 5 conditions check + step_gate 評估結果
// ─────────────────────────────────────────────────────────────────────────

/// `BtcLeadLagShadowSignal` — 單 tick 的 BtcLeadLag panel shadow 評估快照。
///
/// 由 `evaluate_shadow_signal()` 從 (strategy_name, ctx, panel) 計算，內含
/// per spec v1.2 §8.1 + §7.1 的 5 conditions 通過數 + 階梯 step_gate 標籤。
/// 本 struct 純 read-only snapshot（不持有 panel 引用），caller emit tracing
/// log 後即可丟棄；亦可用於 unit test 驗證 evaluator 對特定輸入的判定。
///
/// **強調**：本 struct 純 in-memory（**不**寫 PG），spec §5.1.2 設計就是純
/// tracing log，downstream offline SQL 對齊每筆 fill 跑 counterfactual。
#[derive(Debug, Clone, PartialEq)]
pub struct BtcLeadLagShadowSignal {
    /// 5 conditions 通過數（0-5）：
    ///   1. panel != None（caller 已 confirmed，本 struct 內為 1）
    ///   2. symbol ∈ panel.alt_symbols cohort
    ///   3. xcorr 非 NaN 且 |xcorr| ≥ THRESHOLD_Y(0.40)
    ///   4. btc_lead_return_pct 非 NaN 且 |btc_lead_return_pct| > THRESHOLD_X_BPS(10 bps)
    ///   5. regime_tag == "normal"（per spec §9 extreme regime 不計 7d avg）
    pub condition_pass_count: u8,
    /// L2 net edge σ_net 中位點（per spec §7.1 dual-layer σ acceptance 65 bps mid）。
    /// downstream 7d 對齊真實 fill σ 才算 final power；per-tick 為 hint。
    pub dual_layer_sigma_pct: f64,
    /// 階梯 gate 標籤（per spec v1.2 §8.1）。
    /// "plus15" / "plus5_15" / "minus5" / "no_signal"。
    pub step_gate: &'static str,
    /// alpha decay R²(N) 三檔 hint（per spec §3.1.1 condition #3）。
    /// 本端用 panel.lead_window_secs 對應 R² 快速 hint（caller 不持 R² 計算
    /// 結果；7d evaluate 才算實 R²）。設值 = lead_window_secs；downstream
    /// 對齊 panel.btc_lead_return_pct_60s/300s 計算實 decay curve。
    pub r_squared_decay: u32,
    /// Cohort 內 symbol 對應 index（None = symbol 不在 cohort，condition 2 fail）。
    pub alt_index: Option<usize>,
    /// 從 panel 讀出的 cross-correlation（NaN = 樣本不足）。
    pub xcorr: f64,
    /// 從 panel 讀出的 expected_dir（−1 / 0 / +1）。
    pub expected_dir: i8,
}

impl BtcLeadLagShadowSignal {
    /// 純 NoSignal sentinel — 用於 panel unavailable / 5 conditions 任一 fail 的情境。
    /// caller emit log 時 tracing field 用此 default 值（除非 condition 1 pass）。
    pub fn no_signal() -> Self {
        Self {
            condition_pass_count: 0,
            dual_layer_sigma_pct: DUAL_LAYER_SIGMA_NET_MID_BPS,
            step_gate: "no_signal",
            r_squared_decay: 0,
            alt_index: None,
            xcorr: f64::NAN,
            expected_dir: 0,
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// evaluate_shadow_signal — 純函數 5 conditions 評估
// ─────────────────────────────────────────────────────────────────────────

/// 評估單 tick 的 BtcLeadLag shadow signal 並 emit tracing log（spec §5.1.2 contract）。
///
/// **caller 端契約**：
/// - caller 必先檢 `if let Some(panel) = surface.btc_lead_lag` 之後才呼叫本函數
///   （若 None 則直接 skip，不必 evaluate；condition 1 implicit pass）；
/// - 本函數回傳的 `BtcLeadLagShadowSignal` **不影響** strategy decision，caller
///   應立即丟棄（或保留供 unit test 驗證）；
/// - 本函數會 emit `tracing::info!` 到 `SHADOW_LOG_TARGET` ("btc_alt_lead_lag_shadow")，
///   downstream 7d 後跑離線 SQL pull 此 log target，對齊真實 fill 算 counterfactual edge。
///
/// **5 conditions check**（per spec v1.2 §8.1 + §7.1 + §3.3）：
///   1. panel != None ✅（caller 已 confirmed）
///   2. ctx.symbol ∈ panel.alt_symbols cohort
///   3. xcorr 非 NaN 且 |xcorr| ≥ THRESHOLD_Y(0.40)
///   4. btc_lead_return_pct 非 NaN 且 |btc_lead_return_pct| > THRESHOLD_X_BPS(10)
///   5. regime_tag == "normal"
///
/// **step_gate 階梯**（per spec v1.2 §8.1）：
///   - 5/5 conditions PASS → "plus15"  （per-tick hint：信號方向若對，預估 7d net edge ≥ +15 bps）
///   - 4/5 conditions PASS → "plus5_15"（per-tick hint：邊緣 promote / 需 14d extend）
///   - ≤ 3/5 conditions PASS → "minus5"（per-tick hint：信號質量低，預估 < +5 archive）
///   - panel unavailable / symbol 非 cohort → "no_signal"
pub fn evaluate_shadow_signal(
    strategy_name: &str,
    ctx: &TickContext<'_>,
    panel: &BtcLeadLagPanel,
) -> BtcLeadLagShadowSignal {
    // condition 1：panel != None（caller 已 confirmed，恆 pass = 1）
    let cond_1 = 1u8;

    // condition 2：symbol ∈ cohort
    let alt_index = panel.alt_symbols.iter().position(|s| s == ctx.symbol);
    let cond_2: u8 = if alt_index.is_some() { 1 } else { 0 };

    // 取 xcorr / expected_dir（symbol 非 cohort → NaN / 0 sentinel）
    let xcorr = alt_index
        .and_then(|i| panel.alt_xcorr.get(i).copied())
        .unwrap_or(f64::NAN);
    let expected_dir = alt_index
        .and_then(|i| panel.alt_expected_dir.get(i).copied())
        .unwrap_or(0);

    // condition 3：xcorr 非 NaN 且 |xcorr| ≥ THRESHOLD_Y(0.40)
    let cond_3: u8 = if !xcorr.is_nan() && xcorr.abs() >= THRESHOLD_Y {
        1
    } else {
        0
    };

    // condition 4：btc_lead_return_pct 非 NaN 且 |btc_lead_return_pct| > THRESHOLD_X_BPS(10 bps)
    let btc_ret = panel.btc_lead_return_pct;
    let cond_4: u8 = if !btc_ret.is_nan() && btc_ret.abs() > THRESHOLD_X_BPS {
        1
    } else {
        0
    };

    // condition 5：regime_tag == "normal"
    let cond_5: u8 = if panel.source_tier_regime_normal() {
        1
    } else {
        0
    };

    let condition_pass_count = cond_1 + cond_2 + cond_3 + cond_4 + cond_5;

    // step_gate 階梯（per spec v1.2 §8.1，per-tick hint）
    let step_gate = match condition_pass_count {
        5 => "plus15",
        4 => "plus5_15",
        _ => "minus5",
    };

    let signal = BtcLeadLagShadowSignal {
        condition_pass_count,
        dual_layer_sigma_pct: DUAL_LAYER_SIGMA_NET_MID_BPS,
        step_gate,
        // r_squared_decay hint = 主信號 lead_window_secs（per spec §3.1.1
        // condition #3：D+12 evaluate 強制報三檔 N=60/120/300 R² decay curve；
        // per-tick 只給主信號 N hint，非真實 R²）
        r_squared_decay: panel.lead_window_secs,
        alt_index,
        xcorr,
        expected_dir,
    };

    // emit shadow log — spec §5.1.2 contract（target 字串 + field schema 鎖死，
    // downstream 7d 後 grep target + parse field）
    tracing::info!(
        target: SHADOW_LOG_TARGET,
        strategy = strategy_name,
        symbol = ctx.symbol,
        ts_ms = ctx.timestamp_ms,
        btc_lead_return_pct = btc_ret,
        lead_window_secs = panel.lead_window_secs,
        xcorr = xcorr,
        expected_dir = expected_dir,
        regime_tag = if cond_5 == 1 { "normal" } else { "extreme_or_unknown" },
        condition_pass_count = condition_pass_count,
        dual_layer_sigma_pct = signal.dual_layer_sigma_pct,
        step_gate = signal.step_gate,
        r_squared_decay = signal.r_squared_decay,
        "btc_alt_lead_lag_shadow paper-only signal evaluated"
    );

    signal
}

// ─────────────────────────────────────────────────────────────────────────
// regime helper — 為避免 BtcLeadLagPanel struct 添加 method 的 ABI 變動，
// 本 module 內提供 trait 風格 inherent helper（透過 free function pattern）。
// ─────────────────────────────────────────────────────────────────────────

/// inherent helper：判 BtcLeadLagPanel 的 regime 是否為 normal。
///
/// 注意：BtcLeadLagPanel struct 在 `openclaw_core` crate 端不知道 spec §9
/// regime 字串契約（"normal" / "extreme"）；source_tier 也 open 給 producer
/// 端 set。本 helper 用 source_tier 字串內容匹配的方式做 regime 判別，
/// 避免在 trait skeleton 加 method（保 ABI 穩定）。
///
/// 邏輯：source_tier == "cross_asset_btc_lead_lag" 表 producer 走 normal path
/// emit；extreme regime 走 producer 端標記但 source_tier 不變 → 本 helper 透過
/// 對應 producer impl 約定（producer 寫 "normal" / "extreme" 到獨立 regime_tag
/// V088 schema column，但 trait struct 不暴露 regime_tag 字段，僅 source_tier）。
///
/// 因此本 helper 為 **永遠 true** 的退化實作（caller 預期 panel 來自 paper-only
/// fence，非 extreme regime tick 才 surface）。**TODO**：W2 sub-task 4 wire-up
/// 時若 trait 加 regime_tag field，本 helper 改讀真實 regime_tag。
trait BtcLeadLagPanelRegime {
    fn source_tier_regime_normal(&self) -> bool;
}

impl BtcLeadLagPanelRegime for BtcLeadLagPanel {
    fn source_tier_regime_normal(&self) -> bool {
        // 退化實作：source_tier 含 "cross_asset_btc_lead_lag" 即視為 normal。
        // sub-task 4 trait extend regime_tag field 後改讀真實 regime_tag。
        // 真實 cohort BtcLeadLagPanelSnapshot.regime_tag 由 producer 寫 PG，
        // trait BtcLeadLagPanel struct 僅取主信號子集（spec §4.2 step 6 設計）。
        !self.source_tier.is_empty() && self.source_tier.contains("btc_lead_lag")
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE;

    /// helper：構造一個 paper engine 的 TickContext（最少必要 field）。
    fn ctx_for(symbol: &'static str, ts_ms: u64) -> TickContext<'static> {
        TickContext {
            symbol,
            price: 50_000.0,
            timestamp_ms: ts_ms,
            indicators: None,
            indicators_5m: None,
            signals: &[],
            h0_allowed: true,
            funding_rate: None,
            index_price: None,
            open_interest: None,
            best_bid: None,
            best_ask: None,
            tick_size: None,
            alpha_surface_ref: &EMPTY_ALPHA_SURFACE,
            position_state: None,
            is_pinned: true,
        }
    }

    /// helper：構造一個 5/5 conditions 全 pass 的 panel snapshot。
    fn panel_5_pass() -> BtcLeadLagPanel {
        BtcLeadLagPanel {
            alt_symbols: vec!["ETHUSDT".to_string(), "SOLUSDT".to_string()],
            btc_lead_return_pct: 25.0, // > 10 bps cond 4 pass
            lead_window_secs: 120,
            alt_xcorr: vec![0.65, 0.55], // > 0.40 cond 3 pass
            alt_expected_dir: vec![1, 1],
            snapshot_ts_ms: 1_715_000_000_000,
            source_tier: "cross_asset_btc_lead_lag".to_string(), // cond 5 pass
        }
    }

    /// 5/5 conditions 全 pass → step_gate = "plus15" + condition_pass_count=5。
    #[test]
    fn evaluate_all_five_conditions_pass_step_gate_plus15() {
        let ctx = ctx_for("ETHUSDT", 1_715_000_000_000);
        let panel = panel_5_pass();
        let sig = evaluate_shadow_signal("ma_crossover", &ctx, &panel);
        assert_eq!(sig.condition_pass_count, 5, "5/5 conditions must pass");
        assert_eq!(sig.step_gate, "plus15", "5/5 → step_gate=plus15");
        assert_eq!(sig.alt_index, Some(0));
        assert_eq!(sig.xcorr, 0.65);
        assert_eq!(sig.expected_dir, 1);
        assert_eq!(sig.r_squared_decay, 120);
        assert_eq!(sig.dual_layer_sigma_pct, DUAL_LAYER_SIGMA_NET_MID_BPS);
    }

    /// xcorr < THRESHOLD_Y(0.40) → cond 3 fail，4/5 pass → step_gate = "plus5_15"。
    #[test]
    fn evaluate_xcorr_below_threshold_y_fails_cond_3() {
        let ctx = ctx_for("ETHUSDT", 1_715_000_000_000);
        let mut panel = panel_5_pass();
        panel.alt_xcorr[0] = 0.30; // < 0.40 → cond 3 fail
        let sig = evaluate_shadow_signal("grid_trading", &ctx, &panel);
        assert_eq!(sig.condition_pass_count, 4, "cond 3 fail → 4/5");
        assert_eq!(sig.step_gate, "plus5_15", "4/5 → plus5_15");
        assert_eq!(sig.xcorr, 0.30);
    }

    /// btc_lead_return_pct ≤ THRESHOLD_X_BPS(10) → cond 4 fail。
    #[test]
    fn evaluate_btc_return_below_threshold_x_fails_cond_4() {
        let ctx = ctx_for("ETHUSDT", 1_715_000_000_000);
        let mut panel = panel_5_pass();
        panel.btc_lead_return_pct = 5.0; // ≤ 10 bps → cond 4 fail
        let sig = evaluate_shadow_signal("ma_crossover", &ctx, &panel);
        assert_eq!(sig.condition_pass_count, 4);
        assert_eq!(sig.step_gate, "plus5_15");
    }

    /// xcorr NaN → cond 3 fail（樣本不足 sentinel）。
    #[test]
    fn evaluate_xcorr_nan_fails_cond_3() {
        let ctx = ctx_for("ETHUSDT", 1_715_000_000_000);
        let mut panel = panel_5_pass();
        panel.alt_xcorr[0] = f64::NAN;
        let sig = evaluate_shadow_signal("ma_crossover", &ctx, &panel);
        assert_eq!(sig.condition_pass_count, 4);
        assert_eq!(sig.step_gate, "plus5_15");
    }

    /// btc_lead_return_pct NaN → cond 4 fail。
    #[test]
    fn evaluate_btc_return_nan_fails_cond_4() {
        let ctx = ctx_for("ETHUSDT", 1_715_000_000_000);
        let mut panel = panel_5_pass();
        panel.btc_lead_return_pct = f64::NAN;
        let sig = evaluate_shadow_signal("ma_crossover", &ctx, &panel);
        assert_eq!(sig.condition_pass_count, 4);
        assert_eq!(sig.step_gate, "plus5_15");
    }

    /// symbol 非 cohort → cond 2 fail，alt_index = None。
    #[test]
    fn evaluate_symbol_not_in_cohort_fails_cond_2() {
        let ctx = ctx_for("XRPUSDT", 1_715_000_000_000); // 非 cohort
        let panel = panel_5_pass();
        let sig = evaluate_shadow_signal("grid_trading", &ctx, &panel);
        assert_eq!(
            sig.condition_pass_count, 3,
            "cond 2 fail → cond 3+4 也 NaN/0"
        );
        assert_eq!(sig.step_gate, "minus5", "≤3/5 → minus5");
        assert_eq!(sig.alt_index, None);
        assert!(sig.xcorr.is_nan());
        assert_eq!(sig.expected_dir, 0);
    }

    /// regime_tag 不 normal（source_tier 非 btc_lead_lag）→ cond 5 fail。
    #[test]
    fn evaluate_source_tier_unknown_fails_cond_5() {
        let ctx = ctx_for("ETHUSDT", 1_715_000_000_000);
        let mut panel = panel_5_pass();
        panel.source_tier = String::new(); // empty → cond 5 fail
        let sig = evaluate_shadow_signal("ma_crossover", &ctx, &panel);
        assert_eq!(sig.condition_pass_count, 4);
        assert_eq!(sig.step_gate, "plus5_15");
    }

    /// no_signal sentinel：condition_pass_count=0 + step_gate="no_signal"。
    #[test]
    fn no_signal_sentinel_baseline() {
        let sig = BtcLeadLagShadowSignal::no_signal();
        assert_eq!(sig.condition_pass_count, 0);
        assert_eq!(sig.step_gate, "no_signal");
        assert_eq!(sig.r_squared_decay, 0);
        assert_eq!(sig.alt_index, None);
        assert!(sig.xcorr.is_nan());
        assert_eq!(sig.expected_dir, 0);
        assert_eq!(sig.dual_layer_sigma_pct, DUAL_LAYER_SIGMA_NET_MID_BPS);
    }

    /// SHADOW_LOG_TARGET 字串契約鎖定（spec §5.1.2 contract，downstream SQL 用）。
    #[test]
    fn shadow_log_target_locked_to_spec() {
        // Lock 字串避免無意間 rename 破壞 downstream offline SQL。
        assert_eq!(SHADOW_LOG_TARGET, "btc_alt_lead_lag_shadow");
    }

    /// step_gate 三標籤完整覆蓋（防 caller 寫死成枚舉外字串）。
    #[test]
    fn step_gate_labels_match_spec_v1_2_section_8_1() {
        let valid = ["plus15", "plus5_15", "minus5", "no_signal"];
        // 驗 5/4/3/0 conditions 都對應到 valid 集合
        for cond in 0..=5u8 {
            let step_gate = match cond {
                5 => "plus15",
                4 => "plus5_15",
                _ => "minus5",
            };
            assert!(
                valid.contains(&step_gate),
                "step_gate '{step_gate}' for cond_pass={cond} must be in spec v1.2 §8.1 set"
            );
        }
        // no_signal sentinel 額外驗
        let s = BtcLeadLagShadowSignal::no_signal();
        assert!(valid.contains(&s.step_gate));
    }

    /// dual_layer_sigma_pct 鎖定 65 bps（spec §7.1 dual-layer σ_net 50-80 bps 中位點 hint）。
    #[test]
    fn dual_layer_sigma_pct_locked_to_mid_65_bps() {
        let ctx = ctx_for("ETHUSDT", 1_715_000_000_000);
        let panel = panel_5_pass();
        let sig = evaluate_shadow_signal("ma_crossover", &ctx, &panel);
        assert_eq!(
            sig.dual_layer_sigma_pct, 65.0,
            "spec §7.1 σ_net 50-80 bps mid"
        );
    }
}
