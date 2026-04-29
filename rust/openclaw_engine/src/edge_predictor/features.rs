//! Feature vector v1 — 17 dimensions per spec §3.2.
//! Feature 向量 v1 — 17 維，按規格 §3.2。
//!
//! MODULE_NOTE (EN): `FeatureVectorV1` is the canonical Copy struct fed into
//!   the edge predictor. Per spec §3.2 it carries 17 features across Regime
//!   (5), Basis/Microstructure (3), Strategy (3), Position (3), Time (3).
//!   `all_in_range()` enforces invariant #12: any NaN/Inf/out-of-range value
//!   trips fail-closed fallback to the shrinkage gate. `schema_hash()` and
//!   `definition_hash()` are const-table values; Stage 2 (ML-MIT) computes
//!   them and stores in model metadata for mismatch detection.
//! MODULE_NOTE (中): `FeatureVectorV1` 是餵給預測器的 Copy 結構。依規格 §3.2 攜
//!   17 個 features。`all_in_range()` 強制 invariant #12：任何 NaN/Inf/超界值
//!   → fail-closed 回退到 shrinkage gate。hash 在 Stage 2 ML-MIT 寫入 model
//!   metadata，供不匹配檢測。
//!
//! Spec: docs/references/2026-04-15--edge_predictor_spec.md v1.4 §3.2

/// 17-dim feature vector for edge predictor inference.
/// 17 維 feature 向量，供邊緣預測器推理。
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct FeatureVectorV1 {
    // ===== Regime (5) =====
    /// ADX 1h — trend strength. Range [0, 100].
    pub adx_1h: f32,
    /// Bollinger Band width % (5m). Range [0, 50].
    pub bb_width_pct: f32,
    /// ATR as % of price (5m). Range [0, 20].
    pub atr_pct: f32,
    /// Funding rate (decimal, not bps). Range [-0.01, 0.01].
    pub funding_rate: f32,
    /// 1h realized vol % (stddev of 1m log returns × sqrt(60) × 100). Range [0, 20].
    pub realized_vol_1h: f32,

    // ===== Basis / Microstructure (3) =====
    /// (index - last) / mid × 10000. Range [-500, 500].
    pub basis_bps: f32,
    /// Orderbook L5 imbalance (bid_vol - ask_vol) / (bid_vol + ask_vol). Range [-1, 1].
    pub orderbook_imbalance_top5: f32,
    /// (ask - bid) / mid × 10000. Range [0, 1000].
    pub spread_bps: f32,

    // ===== Strategy (3) =====
    /// Confluence score (0-65 sum across 4 components). Range [0, 65].
    pub confluence_score: f32,
    /// Persistence elapsed milliseconds since signal onset. Range [0, 3_600_000].
    pub persistence_elapsed_ms: f32,
    /// Order side: +1 long, -1 short.
    pub side: i8,

    // ===== Position (3) =====
    /// Intended notional / paper_balance as %. Range [0, 100].
    pub notional_pct_of_bal: f32,
    /// Total concurrent positions at decision time. Range [0, 100].
    pub concurrent_positions: u8,
    /// Positions in same direction (long-vs-short grouping). Range [0, 100].
    pub same_direction_cnt: u8,

    // ===== Time (3) =====
    /// sin(2π × hour_utc / 24). Range [-1, 1].
    pub tod_sin: f32,
    /// cos(2π × hour_utc / 24). Range [-1, 1].
    pub tod_cos: f32,
    /// 1 iff now in last 15min of 8h Bybit funding settlement window.
    pub is_funding_settlement_window: u8,
}

/// Canonical feature name order for v1 — MUST match `to_array()` index order.
/// v1 特徵名稱規範順序 — 必須與 `to_array()` 索引順序一致。
///
/// Changing this list (rename/reorder/add/remove) invalidates
/// `feature_schema_hash()` and breaks train/serve parity. Python mirror:
/// `program_code/ml_training/parquet_etl.py::EDGE_P3_FEATURE_NAMES`.
/// 變更此列表即改動 `feature_schema_hash()`，Python 端鏡像需同步。
pub const FEATURE_NAMES_V1: &[&str; FeatureVectorV1::DIM] = &[
    "adx_1h",
    "bb_width_pct",
    "atr_pct",
    "funding_rate",
    "realized_vol_1h",
    "basis_bps",
    "orderbook_imbalance_top5",
    "spread_bps",
    "confluence_score",
    "persistence_elapsed_ms",
    "side",
    "notional_pct_of_bal",
    "concurrent_positions",
    "same_direction_cnt",
    "tod_sin",
    "tod_cos",
    "is_funding_settlement_window",
];

/// Canonical feature definitions for v1 — formulas/windows/ranges, same order
/// as `FEATURE_NAMES_V1`. Name-only schema hash catches reorder/rename drift;
/// this definition hash catches formula/window drift under stable names.
/// v1 特徵定義規範 — 公式/窗口/range，順序與 `FEATURE_NAMES_V1` 一致。
pub const FEATURE_DEFINITIONS_V1: &[&str; FeatureVectorV1::DIM] = &[
    "adx_1h=ADX trend strength on 1h klines; range[0,100]",
    "bb_width_pct=Bollinger Band width percent on 5m klines; range[0,50]",
    "atr_pct=ATR14 as percent of price on 5m klines; range[0,20]",
    "funding_rate=Bybit funding rate decimal; range[-0.01,0.01]",
    "realized_vol_1h=1h realized vol percent from 1m log returns sqrt(60)*100; range[0,20]",
    "basis_bps=(index_price-last_price)/mid_price*10000; range[-500,500]",
    "orderbook_imbalance_top5=(bid_l5_qty-ask_l5_qty)/(bid_l5_qty+ask_l5_qty); range[-1,1]",
    "spread_bps=(ask_price-bid_price)/mid_price*10000; range[0,1000]",
    "confluence_score=sum of local strategy confluence components; range[0,65]",
    "persistence_elapsed_ms=milliseconds since signal onset; range[0,3600000]",
    "side=order side encoded long=1 short=-1; range{-1,1}",
    "notional_pct_of_bal=intended_notional/paper_balance*100; range[0,100]",
    "concurrent_positions=open position count at decision time; range[0,100]",
    "same_direction_cnt=open positions sharing side at decision time; range[0,100]",
    "tod_sin=sin(2*pi*utc_hour/24); range[-1,1]",
    "tod_cos=cos(2*pi*utc_hour/24); range[-1,1]",
    "is_funding_settlement_window=1 iff within last 15m of 8h funding window; range{0,1}",
];

/// Schema version tag stored alongside every `learning.decision_features` row.
/// 存入 `learning.decision_features` 每列的 schema 版本標記。
pub const FEATURE_SCHEMA_VERSION: &str = "v1";

/// Stable identity for feature schema — sha256 over newline-joined names.
/// Computed once and cached; safe to call on hot paths.
/// 特徵 schema 穩定身分 — sha256 換行串接名稱。單次計算後快取，熱路徑可安全調用。
pub fn feature_schema_hash() -> &'static str {
    static HASH: std::sync::OnceLock<String> = std::sync::OnceLock::new();
    HASH.get_or_init(|| crate::linucb::schema_hash::compute_feature_schema_hash(FEATURE_NAMES_V1))
        .as_str()
}

/// Stable identity for feature definitions — sha256 over newline-joined
/// formula/window/range definitions. Safe to call on hot paths.
/// 特徵定義穩定身分 — sha256 換行串接公式/窗口/range。
pub fn feature_definition_hash() -> &'static str {
    static HASH: std::sync::OnceLock<String> = std::sync::OnceLock::new();
    HASH.get_or_init(|| {
        crate::linucb::schema_hash::compute_feature_schema_hash(FEATURE_DEFINITIONS_V1)
    })
    .as_str()
}

impl FeatureVectorV1 {
    /// Number of features in this version (17). Used for ONNX tensor shape assertion.
    /// 本版本 feature 總數（17），供 ONNX tensor shape 斷言。
    pub const DIM: usize = 17;

    /// Invariant #12 sanity — every field is finite and in declared range.
    /// Returns false on any NaN / Inf / out-of-range. Caller fails closed on false.
    /// 斷言每個欄位 finite 且在聲明 range 內。NaN/Inf/超界 → false → fail-closed。
    pub fn all_in_range(&self) -> bool {
        let f = self;
        let checks = [
            in_range(f.adx_1h, 0.0, 100.0),
            in_range(f.bb_width_pct, 0.0, 50.0),
            in_range(f.atr_pct, 0.0, 20.0),
            in_range(f.funding_rate, -0.01, 0.01),
            in_range(f.realized_vol_1h, 0.0, 20.0),
            in_range(f.basis_bps, -500.0, 500.0),
            in_range(f.orderbook_imbalance_top5, -1.0, 1.0),
            in_range(f.spread_bps, 0.0, 1000.0),
            in_range(f.confluence_score, 0.0, 65.0),
            in_range(f.persistence_elapsed_ms, 0.0, 3_600_000.0),
            (f.side == 1 || f.side == -1),
            in_range(f.notional_pct_of_bal, 0.0, 100.0),
            // u8 fields — only upper bound matters; underflow impossible.
            f.concurrent_positions <= 100,
            f.same_direction_cnt <= 100,
            in_range(f.tod_sin, -1.0, 1.0),
            in_range(f.tod_cos, -1.0, 1.0),
            (f.is_funding_settlement_window == 0 || f.is_funding_settlement_window == 1),
        ];
        checks.iter().all(|&ok| ok)
    }

    /// Convert to flat `[f32; 17]` for ONNX tensor ingestion.
    /// Order MUST match the schema hash canonical ordering (§3.3).
    /// 扁平化為 `[f32; 17]` 供 ONNX tensor。順序必須與 schema hash 一致。
    pub fn to_array(&self) -> [f32; Self::DIM] {
        [
            self.adx_1h,
            self.bb_width_pct,
            self.atr_pct,
            self.funding_rate,
            self.realized_vol_1h,
            self.basis_bps,
            self.orderbook_imbalance_top5,
            self.spread_bps,
            self.confluence_score,
            self.persistence_elapsed_ms,
            self.side as f32,
            self.notional_pct_of_bal,
            self.concurrent_positions as f32,
            self.same_direction_cnt as f32,
            self.tod_sin,
            self.tod_cos,
            self.is_funding_settlement_window as f32,
        ]
    }

    /// Serialize to a compact JSONB-compatible JSON string for
    /// `PipelineCommand::EmitShadowFill` payloads. Field order matches the
    /// declared struct order (stable, alphabetical is not required by Postgres
    /// JSONB). Shadow-fill consumers join on `context_id`, so the keys are for
    /// operator debugging, not query predicates.
    /// 序列化為 `EmitShadowFill` 載荷用 JSON 字串；JSONB 欄位順序不需 alphabetical。
    pub fn to_jsonb(&self) -> String {
        format!(
            concat!(
                r#"{{"adx_1h":{adx},"bb_width_pct":{bw},"atr_pct":{atr},"#,
                r#""funding_rate":{fr},"realized_vol_1h":{rv},"basis_bps":{bs},"#,
                r#""orderbook_imbalance_top5":{ob},"spread_bps":{sp},"#,
                r#""confluence_score":{cs},"persistence_elapsed_ms":{pe},"#,
                r#""side":{sd},"notional_pct_of_bal":{np},"#,
                r#""concurrent_positions":{cp},"same_direction_cnt":{sdc},"#,
                r#""tod_sin":{ts},"tod_cos":{tc},"#,
                r#""is_funding_settlement_window":{fw}}}"#,
            ),
            adx = json_f32(self.adx_1h),
            bw = json_f32(self.bb_width_pct),
            atr = json_f32(self.atr_pct),
            fr = json_f32(self.funding_rate),
            rv = json_f32(self.realized_vol_1h),
            bs = json_f32(self.basis_bps),
            ob = json_f32(self.orderbook_imbalance_top5),
            sp = json_f32(self.spread_bps),
            cs = json_f32(self.confluence_score),
            pe = json_f32(self.persistence_elapsed_ms),
            sd = self.side,
            np = json_f32(self.notional_pct_of_bal),
            cp = self.concurrent_positions,
            sdc = self.same_direction_cnt,
            ts = json_f32(self.tod_sin),
            tc = json_f32(self.tod_cos),
            fw = self.is_funding_settlement_window,
        )
    }

    /// Zero-default vector for tests / placeholders. `side = 1` (longs by default).
    /// 測試/占位用零值，`side = 1`（默認 long）。
    pub fn zeroed() -> Self {
        Self {
            adx_1h: 0.0,
            bb_width_pct: 0.0,
            atr_pct: 0.0,
            funding_rate: 0.0,
            realized_vol_1h: 0.0,
            basis_bps: 0.0,
            orderbook_imbalance_top5: 0.0,
            spread_bps: 0.0,
            confluence_score: 0.0,
            persistence_elapsed_ms: 0.0,
            side: 1,
            notional_pct_of_bal: 0.0,
            concurrent_positions: 0,
            same_direction_cnt: 0,
            tod_sin: 0.0,
            tod_cos: 0.0,
            is_funding_settlement_window: 0,
        }
    }
}

#[inline]
fn in_range(v: f32, lo: f32, hi: f32) -> bool {
    v.is_finite() && v >= lo && v <= hi
}

/// JSON-safe f32 serializer — NaN/Inf become `null`, matching `serde_json` policy.
/// Keeps `to_jsonb()` free of serde dependency while staying parse-safe downstream.
/// JSON 安全 f32：NaN/Inf 寫 `null`，與 serde_json 一致。
#[inline]
fn json_f32(v: f32) -> String {
    if v.is_finite() {
        format!("{}", v)
    } else {
        "null".into()
    }
}

// ============================================================
// Tests
// ============================================================
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_dim_is_17() {
        assert_eq!(FeatureVectorV1::DIM, 17);
    }

    #[test]
    fn test_zeroed_passes_range_check() {
        assert!(FeatureVectorV1::zeroed().all_in_range());
    }

    #[test]
    fn test_nan_fails_range_check() {
        let mut f = FeatureVectorV1::zeroed();
        f.adx_1h = f32::NAN;
        assert!(!f.all_in_range());
    }

    #[test]
    fn test_infinity_fails_range_check() {
        let mut f = FeatureVectorV1::zeroed();
        f.atr_pct = f32::INFINITY;
        assert!(!f.all_in_range());
    }

    #[test]
    fn test_out_of_range_each_regime_field() {
        let baseline = FeatureVectorV1::zeroed();
        let mut f = baseline;
        f.adx_1h = 200.0;
        assert!(!f.all_in_range());
        f = baseline;
        f.bb_width_pct = 60.0;
        assert!(!f.all_in_range());
        f = baseline;
        f.atr_pct = 25.0;
        assert!(!f.all_in_range());
        f = baseline;
        f.funding_rate = 0.02;
        assert!(!f.all_in_range());
        f = baseline;
        f.realized_vol_1h = 30.0;
        assert!(!f.all_in_range());
    }

    #[test]
    fn test_out_of_range_basis_microstructure() {
        let baseline = FeatureVectorV1::zeroed();
        let mut f = baseline;
        f.basis_bps = 600.0;
        assert!(!f.all_in_range());
        f = baseline;
        f.orderbook_imbalance_top5 = 1.5;
        assert!(!f.all_in_range());
        f = baseline;
        f.spread_bps = 2000.0;
        assert!(!f.all_in_range());
    }

    #[test]
    fn test_side_must_be_plus_minus_one() {
        let mut f = FeatureVectorV1::zeroed();
        f.side = 0;
        assert!(!f.all_in_range());
        f.side = 2;
        assert!(!f.all_in_range());
        f.side = -1;
        assert!(f.all_in_range());
        f.side = 1;
        assert!(f.all_in_range());
    }

    #[test]
    fn test_u8_fields_upper_bound() {
        let mut f = FeatureVectorV1::zeroed();
        f.concurrent_positions = 101;
        assert!(!f.all_in_range());
        f = FeatureVectorV1::zeroed();
        f.same_direction_cnt = 101;
        assert!(!f.all_in_range());
    }

    #[test]
    fn test_funding_window_flag_must_be_binary() {
        let mut f = FeatureVectorV1::zeroed();
        f.is_funding_settlement_window = 2;
        assert!(!f.all_in_range());
        f.is_funding_settlement_window = 0;
        assert!(f.all_in_range());
        f.is_funding_settlement_window = 1;
        assert!(f.all_in_range());
    }

    #[test]
    fn test_to_array_preserves_declared_order() {
        let mut f = FeatureVectorV1::zeroed();
        f.adx_1h = 1.0;
        f.bb_width_pct = 2.0;
        f.atr_pct = 3.0;
        f.funding_rate = 0.004;
        let arr = f.to_array();
        assert_eq!(arr.len(), FeatureVectorV1::DIM);
        assert_eq!(arr[0], 1.0);
        assert_eq!(arr[1], 2.0);
        assert_eq!(arr[2], 3.0);
        assert!((arr[3] - 0.004).abs() < 1e-6);
    }

    #[test]
    fn test_to_array_side_conversion() {
        let mut f = FeatureVectorV1::zeroed();
        f.side = -1;
        let arr = f.to_array();
        assert_eq!(arr[10], -1.0);
    }

    #[test]
    fn test_to_jsonb_roundtrips_via_serde_json() {
        // to_jsonb is hand-rolled; verify output is valid JSON and keys line up.
        // to_jsonb 手寫實作，驗證為合法 JSON 且 key 齊全。
        let f = FeatureVectorV1 {
            adx_1h: 25.0,
            bb_width_pct: 3.5,
            atr_pct: 1.2,
            funding_rate: 0.0003,
            realized_vol_1h: 1.8,
            basis_bps: 4.5,
            orderbook_imbalance_top5: 0.12,
            spread_bps: 1.5,
            confluence_score: 42.0,
            persistence_elapsed_ms: 125_000.0,
            side: -1,
            notional_pct_of_bal: 3.0,
            concurrent_positions: 4,
            same_direction_cnt: 2,
            tod_sin: 0.707,
            tod_cos: 0.707,
            is_funding_settlement_window: 1,
        };
        let s = f.to_jsonb();
        let v: serde_json::Value = serde_json::from_str(&s).expect("valid JSON");
        assert_eq!(v["adx_1h"], 25.0);
        assert_eq!(v["side"], -1);
        assert_eq!(v["concurrent_positions"], 4);
        assert_eq!(v["same_direction_cnt"], 2);
        assert_eq!(v["is_funding_settlement_window"], 1);
        assert_eq!(v["persistence_elapsed_ms"], 125_000.0);
        // 17 distinct fields; no silent omission.
        assert_eq!(v.as_object().unwrap().len(), 17);
    }

    #[test]
    fn test_to_jsonb_emits_null_for_nan_infinity() {
        // JSON has no NaN/Inf literals; emit null so downstream JSONB parsers
        // see a valid document rather than fail.
        // JSON 無 NaN/Inf 字面；寫 null 避免下游解析失敗。
        let mut f = FeatureVectorV1::zeroed();
        f.adx_1h = f32::NAN;
        f.spread_bps = f32::INFINITY;
        let s = f.to_jsonb();
        let v: serde_json::Value = serde_json::from_str(&s).expect("valid JSON");
        assert!(v["adx_1h"].is_null());
        assert!(v["spread_bps"].is_null());
    }

    #[test]
    fn test_feature_names_v1_length_matches_dim() {
        assert_eq!(FEATURE_NAMES_V1.len(), FeatureVectorV1::DIM);
    }

    #[test]
    fn test_feature_names_v1_head_and_tail_anchored() {
        // Schema-hash frozen anchors; any accidental reorder trips this.
        // schema_hash 凍結錨點；意外重排會在此斷言失敗。
        assert_eq!(FEATURE_NAMES_V1[0], "adx_1h");
        assert_eq!(FEATURE_NAMES_V1[10], "side");
        assert_eq!(FEATURE_NAMES_V1[16], "is_funding_settlement_window");
    }

    #[test]
    fn test_feature_schema_hash_is_deterministic_and_cached() {
        let a = feature_schema_hash();
        let b = feature_schema_hash();
        assert_eq!(a, b);
        assert!(a.starts_with("sha256:"));
        assert_eq!(a.len(), "sha256:".len() + 16);
    }

    #[test]
    fn test_feature_schema_hash_matches_direct_compute() {
        let direct = crate::linucb::schema_hash::compute_feature_schema_hash(FEATURE_NAMES_V1);
        assert_eq!(feature_schema_hash(), direct);
    }

    #[test]
    fn test_feature_definition_hash_is_distinct_from_name_schema_hash() {
        assert_eq!(FEATURE_DEFINITIONS_V1.len(), FeatureVectorV1::DIM);
        assert_ne!(feature_definition_hash(), feature_schema_hash());
        assert!(feature_definition_hash().starts_with("sha256:"));
        assert_eq!(feature_definition_hash().len(), "sha256:".len() + 16);
    }

    #[test]
    fn test_feature_schema_version_is_v1() {
        assert_eq!(FEATURE_SCHEMA_VERSION, "v1");
    }

    #[test]
    fn test_typical_decision_vector_passes() {
        let f = FeatureVectorV1 {
            adx_1h: 25.0,
            bb_width_pct: 3.5,
            atr_pct: 1.2,
            funding_rate: 0.0003,
            realized_vol_1h: 1.8,
            basis_bps: 4.5,
            orderbook_imbalance_top5: 0.12,
            spread_bps: 1.5,
            confluence_score: 42.0,
            persistence_elapsed_ms: 125_000.0,
            side: 1,
            notional_pct_of_bal: 3.0,
            concurrent_positions: 4,
            same_direction_cnt: 2,
            tod_sin: 0.707,
            tod_cos: 0.707,
            is_funding_settlement_window: 0,
        };
        assert!(f.all_in_range());
    }
}
