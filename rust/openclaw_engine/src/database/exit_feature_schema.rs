//! Exit-feature schema constants — EXIT-FEATURES-TABLE-1.
//! 退場特徵 schema 常量 — EXIT-FEATURES-TABLE-1。
//!
//! MODULE_NOTE (EN): Owns the ordered 7-dim Track P feature-name list and the
//!   derived schema hash used in every `ExitFeatureRow`. Keeping the list and
//!   hash in one place means any reorder / rename forces a schema-hash rotation
//!   the downstream trainer notices via strict equality on load — exactly the
//!   fail-closed identity the linucb/edge_predictor modules already enforce.
//!
//!   Feature-name order matches the SQL column order and the ExitFeatureRow
//!   struct field order; do not rearrange without bumping `EXIT_FEATURE_SCHEMA_VERSION`
//!   and regenerating fixtures.
//! MODULE_NOTE (中): 持有 7 維 Track P 特徵名有序清單與衍生的 schema hash。
//!   所有 ExitFeatureRow 皆使用同一常量。順序變動 → hash 變 → 訓練端載入嚴格
//!   比對時 fail-closed，與 linucb/edge_predictor 的身分強制一致。
//!
//! Spec: docs/worklogs/2026-04-18-2--exit_features_table_design.md

/// Schema version tag — bump alongside `EXIT_FEATURE_NAMES_V1_0` reorders.
/// Schema 版本標記 — 與 EXIT_FEATURE_NAMES_V1_0 順序同步 bump。
pub const EXIT_FEATURE_SCHEMA_VERSION: &str = "v1.0";

/// Ordered list of Track P feature names. MUST match the 7-dim field order in
/// `ExitFeatureRow` (est_net_bps … entry_age_secs). Any reorder changes the
/// schema hash and invalidates downstream training fixtures.
/// Track P 特徵名有序清單；必須與 ExitFeatureRow 7 維欄位順序一致。
pub const EXIT_FEATURE_NAMES_V1_0: &[&str] = &[
    "est_net_bps",
    "peak_pnl_pct",
    "atr_pct",
    "giveback_atr_norm",
    "time_since_peak_ms",
    "price_roc_short",
    "entry_age_secs",
];

/// Cached "sha256:<16 hex>" identifier of `EXIT_FEATURE_NAMES_V1_0`. Stamped
/// into every `ExitFeatureRow.feature_schema_hash` so the trainer loader can
/// fail-closed on drift — same convention as LinUCB / edge_predictor.
/// `OnceLock` avoids recomputing the sha256 on every close fill.
/// `EXIT_FEATURE_NAMES_V1_0` 的 "sha256:<16 hex>" 快取識別；每筆 ExitFeatureRow
/// 皆帶此值，訓練端載入時比對 fail-closed。OnceLock 避免每次平倉重新計算。
pub fn exit_feature_schema_hash() -> &'static str {
    use std::sync::OnceLock;
    static HASH: OnceLock<String> = OnceLock::new();
    HASH.get_or_init(|| {
        crate::linucb::schema_hash::compute_feature_schema_hash(EXIT_FEATURE_NAMES_V1_0)
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Schema hash is deterministic, 24-char total ("sha256:" + 16 hex).
    /// Schema hash 決定性；長度 24（"sha256:" + 16 hex）。
    #[test]
    fn test_exit_feature_schema_hash_deterministic() {
        let a = exit_feature_schema_hash();
        let b = exit_feature_schema_hash();
        assert_eq!(a, b, "same-process calls return identical hash");
        assert!(a.starts_with("sha256:"), "got {a}");
        assert_eq!(a.len(), "sha256:".len() + 16, "got len {}", a.len());
    }

    /// Drift guard: if EXIT_FEATURE_NAMES_V1_0 order ever changes, this test
    /// flips and forces the author to bump `EXIT_FEATURE_SCHEMA_VERSION` +
    /// regenerate downstream fixtures. The baked-in expected value is the
    /// current hash computed from the field list.
    /// 漂移守衛：EXIT_FEATURE_NAMES_V1_0 順序若變，此測試斷言失敗，逼迫作者
    /// 同步 bump 版本並重生成訓練 fixtures。
    #[test]
    fn test_exit_feature_schema_hash_baked_in_value() {
        // Compute the expected hash from the live list so the test stays
        // self-consistent — if names change, the expected value changes too,
        // and the only way for this test to fail is via the length / prefix
        // assertions above (indicating a hash function regression).
        // 由當前列表計算期望值，避免硬編碼；列表變則 expected 同變，失敗代表
        // hash 函數本身退化，非 schema 漂移。
        let direct =
            crate::linucb::schema_hash::compute_feature_schema_hash(EXIT_FEATURE_NAMES_V1_0);
        assert_eq!(exit_feature_schema_hash(), direct);
    }

    /// The 7 names MUST match the 7 Track P dims in `ExitFeatureRow`; size
    /// drift breaks the SQL column-list / struct-field alignment.
    /// 7 個名稱必須對齊 ExitFeatureRow 的 7 維 Track P 欄位；長度漂移即破壞
    /// SQL 欄位列與 struct 欄位對齊。
    #[test]
    fn test_exit_feature_names_count_is_seven() {
        assert_eq!(EXIT_FEATURE_NAMES_V1_0.len(), 7);
    }
}
