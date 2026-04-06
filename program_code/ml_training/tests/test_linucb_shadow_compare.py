"""Unit tests for LinUCB shadow compare (Phase 4 task 4-06).
LinUCB 影子比較測試。
"""

from __future__ import annotations

import random

from ml_training.linucb_shadow_compare import (
    ShadowCompareConfig,
    ShadowCompareResult,
    decide,
)


def _cfg(min_decisions=10, sigma=2.0):
    return ShadowCompareConfig(
        champion_version="v1_15",
        challenger_version="v2_25",
        window_days=14,
        rollback_threshold_sigma=sigma,
        min_decisions=min_decisions,
    )


def test_shadow_compare_promote_when_v2_clearly_better():
    """Challenger mean clearly above champion by many σ → PROMOTE.
    挑戰者顯著優於冠軍 → PROMOTE。
    """
    random.seed(1)
    champion = [random.gauss(0.0, 0.1) for _ in range(500)]
    challenger = [random.gauss(0.5, 0.1) for _ in range(500)]
    res = decide(champion, challenger, _cfg())
    assert isinstance(res, ShadowCompareResult)
    assert res.decision == "PROMOTE"
    assert res.delta > 0
    assert res.n_decisions_compared == 500


def test_shadow_compare_keep_champion_when_v2_below_threshold():
    """Challenger mean clearly below champion → KEEP_CHAMPION with z < -2.
    挑戰者顯著更差 → KEEP_CHAMPION 且 z < -2。
    """
    random.seed(2)
    champion = [random.gauss(0.5, 0.1) for _ in range(500)]
    challenger = [random.gauss(0.0, 0.1) for _ in range(500)]
    res = decide(champion, challenger, _cfg())
    assert res.decision == "KEEP_CHAMPION"
    assert res.delta < 0
    # z < -2 → eligible for rollback
    assert (res.delta / res.delta_sigma) < -2.0


def test_shadow_compare_insufficient_data_below_min_decisions():
    """Too few samples → INSUFFICIENT_DATA, regardless of sign.
    樣本不足 → INSUFFICIENT_DATA。
    """
    random.seed(3)
    champion = [0.1, 0.2, 0.3]
    challenger = [0.5, 0.6, 0.7]
    res = decide(champion, challenger, _cfg(min_decisions=100))
    assert res.decision == "INSUFFICIENT_DATA"
    assert res.n_decisions_compared == 3
