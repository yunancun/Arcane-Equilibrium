"""W-AUDIT-8c Liquidation Cluster Reaction Stage 0R helpers.

模塊用途：read-only Stage 0R 數學工具，計算 liquidation cluster reaction
strategy 候選的 promotion-floor 評估指標。鏡像 W-AUDIT-8b funding_skew 模塊
結構（zero precedent breakage），加入 8b RED_FINAL 提取的三大改進：
  1. cluster-aware n_eff（per MIT SHOULD-3 forward-applicable mandate）。
  2. single-symbol concentration cap（per 8b INJUSDT 87% 集中度教訓）。
  3. per-tier × per-direction 4-value verdict（PASS-BOTH/LONG/SHORT/RED，
     per BB STRUCTURAL 2026-05-18 long-liq skew real-microstructure 結論）。

主要類函數：CandidateCell / compute_stage0r / compute_stage0r_sweep。
依賴：純 stdlib（math/random/statistics/dataclasses/collections/datetime）。
硬邊界：純 math layer；無 DB / 無 file IO / 無 live state 修改。
"""
