"""
MODULE_NOTE
模塊用途：M4 Stage 1 6 attribute enforcement gate（per W1-B spec §3）。

6 attribute pass conditions：
   1. N (n_observations) >= 30
   2. Bonferroni-corrected p < ALPHA_CORRECTED (2e-5)
   3. Cohen's d ∈ [0.2, 3.0)
   4. sub-period stability: TRUE (None 在 event-window 場景下允許)
   5. graveyard flag: 不阻 promotion（warning only）
   6. cluster silhouette: skip Sprint 2（Stage 2 才啟）

returns 'preregistered' / 'exploratory'（不直接寫 'draft' — 'draft' 是 INSERT
base state；本函式決定後續 transition target）。

不變量：
   - 不能 promote past 'preregistered'（per AMD-2026-05-21-01 protected scope (a)
     + W1-B spec §0 I-5）
   - graveyard_flag 不參與 pass criterion — warning only
"""
from __future__ import annotations

from helper_scripts.m4.algorithms.bonferroni import is_significant_after_correction
from helper_scripts.m4.algorithms.effect_size import passes_cohens_d_gate


def determine_hypothesis_status(
    n: int,
    raw_p: float,
    cohens_d: float | None,
    subperiod_pass: bool | None,
    graveyard_flag: bool,
    silhouette: float | None = None,
) -> str:
    """決定 hypothesis 的 transition status target。

    Returns: 'preregistered' / 'exploratory'

    Pass all 條件（per W1-B spec §3.2）：
       - N >= 30
       - Bonferroni 校正後顯著（raw_p < 2e-5）
       - 0.2 <= |Cohen's d| < 3.0
       - subperiod_pass is True 或 is None（event-window 場景）
       - silhouette is None 或 >= 0.5（Sprint 2 skip）
       - graveyard_flag 不阻

    不變量：本函式只回 'preregistered' / 'exploratory'；不能回 'live' / 'promoted'
       （per 16 原則 #7 + AMD-2026-05-21-01 protected scope (a)）。
    """
    # 不變量 I-4：N < 30 強制 'exploratory'。
    if n < 30:
        return "exploratory"
    # 不變量 I-3：Bonferroni K=2500 校正比較。
    if not is_significant_after_correction(raw_p):
        return "exploratory"
    # Cohen's d gate（0.2 <= |d| < 3.0）。
    if not passes_cohens_d_gate(cohens_d):
        return "exploratory"
    # Sub-period stability：True 或 None（event-window）通過；False 不通過。
    if subperiod_pass is False:
        return "exploratory"
    # Silhouette：None 或 >= 0.5（Sprint 2 skip → None 通過）。
    if silhouette is not None and silhouette < 0.5:
        return "exploratory"
    # graveyard_flag 不參與 pass criterion — warning only。

    return "preregistered"


def is_promotable(status_candidate: str) -> bool:
    """判斷 status_candidate 是否可由 M4 miner 自動寫入。

    不變量：只有 'draft' / 'exploratory' / 'preregistered' 三狀態可由 M4 自動寫入；
    'live' / 'promoted' / 'rejected' 必經 operator manual Console click
    （per AMD-2026-05-21-01 protected scope (a)）。
    """
    return status_candidate in ("draft", "exploratory", "preregistered")
