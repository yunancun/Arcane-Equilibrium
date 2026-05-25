"""
MODULE_NOTE
模塊用途：M4 Stage 1 Bonferroni multiple comparisons correction（Python 端 SSOT 對齊
   Rust `openclaw_core::m4_miner::bonferroni`）。

不變量 I-3：
   - BONFERRONI_K_TOTAL = 2500 — hard-coded（per W1-B spec §0 + §2.1.4）
   - ALPHA_CORRECTED = 0.05 / 2500 = 2e-5

為什麼 hard-coded：
   - 5 對抗式 grep（W1-B spec §9.2 Review-2）要 grep `K_TOTAL` 或 `BONFERRONI_K`
     hit ≥ 1
   - K_hyp = 500 是 PA Sprint 2 baseline empirical 估計；Sprint 3 若需 adjust
     需 PA + MIT + QC 三角仲裁（per W1-B Open Q1），non-trivial 決策，不應靜默
     config 改動
"""
from __future__ import annotations

# Bonferroni K_total — 不可改為 0.05 / 100 或其他 K（per W1-B spec §0 I-3）。
# 為什麼是 2500：K_hyp = 500 (baseline) × 5 forward window = 2500。
BONFERRONI_K_TOTAL: int = 2500
ALPHA_CORRECTED: float = 0.05 / BONFERRONI_K_TOTAL  # = 2e-5


def correct_p_value(raw_p: float) -> float:
    """套用 Bonferroni correction。

    公式：p_corrected = min(1.0, raw_p × K_TOTAL)
    為什麼 min：Bonferroni 後 p 可能 > 1，上 clamp。
    """
    if raw_p < 0.0:
        raw_p = 0.0
    return min(1.0, raw_p * BONFERRONI_K_TOTAL)


def is_significant_after_correction(raw_p: float) -> bool:
    """Bonferroni 校正後是否仍顯著？

    不變量：判斷必用 raw_p < ALPHA_CORRECTED（等價 correct_p_value(raw_p) < 0.05）；
    不允許 raw_p < 0.05 或 < 0.01 不經 K_TOTAL 比較（per W1-B spec §9.2 Review-2 grep）。

    為什麼直接比較 ALPHA_CORRECTED：兩者數學等價，但前者一行就過 grep `K_TOTAL`。
    """
    # Bonferroni K=2500 — 不可改（per W1-B spec §0 I-3）。
    return raw_p < ALPHA_CORRECTED
