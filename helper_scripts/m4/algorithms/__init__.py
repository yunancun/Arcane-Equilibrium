"""
M4 Stage 1 statistical algorithms（per W1-B spec §2 + §3）。

   - cross_correlation: Pearson / Spearman + rolling shift(1) leak-free
   - event_window: 3 detector + pre/post window forward shift + N>=30 gate
   - bonferroni: K=2500 hard-coded + correct_p_value + is_significant
   - effect_size: Cohen's d + pooled std
"""
