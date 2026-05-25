// MODULE_NOTE
// 模塊用途：M4 Stage 1 Bonferroni multiple comparisons correction（per W1-B I-3）。
//   提供 K_TOTAL 常數 + α_corrected + p-value 校正 + is_significant_after_correction。
//
// 不變量 I-3：
//   - BONFERRONI_K_TOTAL = 2500 — hard-coded（per W1-B spec §0 + §2.1.4）
//     K_hyp = 500（baseline）× 5 forward window = 2500
//   - ALPHA_CORRECTED = 0.05 / 2500 = 2e-5
//
// 為什麼 hard-coded 不放 config：
//   - 5 對抗式 grep（W1-B spec §9.2 Review-2）要 grep `K_TOTAL` 或 `BONFERRONI_K`
//     hit ≥ 1，hard-code 確保 grep 必命中
//   - K_hyp = 500 是 PA Sprint 2 baseline empirical 估計；Sprint 3 若需 adjust
//     需 PA + MIT + QC 三角仲裁（per W1-B Open Q1），non-trivial 決策，不應靜默
//     config 改動

/// Bonferroni K_total — hypothesis count × forward window count。
///
/// 不變量：K_total = K_hyp × 5 forward window = 2500。
/// 為什麼 hard-coded：5 對抗 grep（W1-B spec §9.2）要強制可發現性 + Sprint 3 改動
/// 必經三角仲裁（per W1-B Open Q1）。
pub const BONFERRONI_K_TOTAL: usize = 2500;

/// Bonferroni-corrected α — 0.05 / K_TOTAL = 2e-5。
pub const ALPHA_CORRECTED: f64 = 0.05 / BONFERRONI_K_TOTAL as f64;

/// 把 raw p-value 套用 Bonferroni correction。
///
/// 公式：p_corrected = min(1.0, p_raw × K_TOTAL)
///
/// 為什麼 min(1.0, ...)：Bonferroni 後 p 可能 > 1（無意義），upper clamp 至 1.0。
pub fn correct_p_value(raw_p: f64) -> f64 {
    (raw_p * BONFERRONI_K_TOTAL as f64).min(1.0)
}

/// 是否在 Bonferroni correction 後仍顯著？
///
/// 不變量：判斷必用 `raw_p < ALPHA_CORRECTED`（等價 `correct_p_value(raw_p) < 0.05`）；
/// 不允許用 `raw_p < 0.05` 或 `raw_p < 0.01` 不經 K_TOTAL 比較（per W1-B spec §9.2
/// Review-2 grep）。
///
/// 為什麼 raw_p 比較 ALPHA_CORRECTED 而非 correct(raw_p) 比較 0.05：兩者數學
/// 等價，但前者一行就過 grep `K_TOTAL`，後者要在 callsite 寫 `correct_p_value(...)`，
/// 對 grep tooling 比較友善。
pub fn is_significant_after_correction(raw_p: f64) -> bool {
    // Bonferroni K=2500 — 不可改為 0.05 / 100 或其他 K（per W1-B spec §0 I-3）。
    raw_p < ALPHA_CORRECTED
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn k_total_is_2500() {
        // 5 對抗 grep（W1-B spec §9.2 Review-2）必命中此常數。
        assert_eq!(BONFERRONI_K_TOTAL, 2500);
    }

    #[test]
    fn alpha_corrected_is_2e_minus_5() {
        assert!((ALPHA_CORRECTED - 2e-5).abs() < 1e-10);
    }

    #[test]
    fn correct_p_value_basic() {
        // raw 0.001 × 2500 = 2.5 → clamp 1.0
        assert_eq!(correct_p_value(0.001), 1.0);
        // raw 1e-6 × 2500 = 0.0025
        assert!((correct_p_value(1e-6) - 0.0025).abs() < 1e-10);
        // raw 0 → 0
        assert_eq!(correct_p_value(0.0), 0.0);
    }

    #[test]
    fn is_significant_strict_threshold() {
        // ALPHA_CORRECTED = 2e-5 = 0.00002。
        // raw 1e-5 = 0.00001 < 0.00002 → 顯著。
        assert!(is_significant_after_correction(1e-5));
        // raw 1e-4 = 0.0001 > 0.00002 → 不顯著。
        assert!(!is_significant_after_correction(1e-4));
        // raw 0.05 → 絕對不顯著。
        assert!(!is_significant_after_correction(0.05));
        // raw 1e-6 << 2e-5 → 顯著。
        assert!(is_significant_after_correction(1e-6));
    }

    #[test]
    fn is_significant_boundary() {
        // raw 剛好等於 ALPHA_CORRECTED → 不顯著（strict less than）
        assert!(!is_significant_after_correction(ALPHA_CORRECTED));
        // raw 略小於 → 顯著
        assert!(is_significant_after_correction(ALPHA_CORRECTED - 1e-10));
    }

    #[test]
    fn correct_p_value_zero_and_one() {
        assert_eq!(correct_p_value(0.0), 0.0);
        assert_eq!(correct_p_value(1.0), 1.0);
        // raw 0.5 × 2500 = 1250 → clamp 1.0
        assert_eq!(correct_p_value(0.5), 1.0);
    }
}
