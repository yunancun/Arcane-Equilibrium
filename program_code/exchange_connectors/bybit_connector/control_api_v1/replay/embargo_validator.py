"""REF-20 P3a-Q2 OOS Embargo Validator — Python sibling of V041 CHECK.

REF-20 P3a-Q2 OOS Embargo 校驗器 — V041 CHECK 的 Python 鏡像。

MODULE_NOTE (EN):
    Pure-function validator that mirrors the V041
    `chk_embargo_days` CHECK constraint at the API surface, so manifest
    submissions whose embargo violates V3 §8.1 are rejected with a
    400 + reason_code BEFORE the SQL constraint sees them. The DB
    constraint is the last line of defence; this validator is the first.

    Invariant / 不變量:
        proposed_embargo_days >= max(7, ceil(2 × half_life_days))

    Why ceil(2 × half_life) / 為什麼 ceil:
        embargo_days is INTEGER (V3 §8.1) but half_life_days is
        DOUBLE PRECISION. For half-life 5.6, 2 × 5.6 = 11.2, and
        we round UP because the invariant is "at least 2 half-lives";
        rounding down would let a 11-day embargo through when the math
        says 11.2 days are needed. The V041 SQL CHECK uses
        ``GREATEST(7, CEIL(2.0 * half_life_days)::INTEGER)`` for the
        same reason — Python ``math.ceil`` and PostgreSQL ``CEIL`` agree
        on integer mathematics.

    Cross-language consistency / 跨語言一致性:
        For any (half_life_days, proposed_embargo_days) pair, this
        function and the V041 CHECK constraint MUST agree on accept /
        reject. Test
        ``tests/migrations/test_v041_oos_embargo.py::
        test_v041_check_aligns_with_python_validator``
        verifies edge cases (5.0 half-life vs 10-day embargo;
        7.5 half-life vs 15-day embargo; 5.6 vs 12-day reject case).

    Wave 5 P3a-Q2 scope (this commit):
      - ``validate_embargo(half_life_days, proposed_embargo_days) -> bool``
      - ``compute_min_embargo_days(half_life_days) -> int`` helper
      - ``EmbargoCheckResult`` dataclass for replay_routes adoption.
      - 4 unit tests covering pass / fail / boundary / NULL half-life.

    NOT in this scope:
      - replay_routes.py call-site wiring (Wave 5+ separate task; this
        module is import-ready but not yet hooked into manifest POST).
      - Half-life estimation pipeline (Wave 5 P3a-Q1 sibling task).
      - DB INSERT / UPDATE of experiments.embargo_days (P2b runner owns).

MODULE_NOTE (中):
    純函式校驗器，鏡像 V041 `chk_embargo_days` CHECK 約束在 API 表面。
    違反 V3 §8.1 的 manifest 在進到 SQL 前先以 400 + reason_code 拒絕。
    DB 約束是最後一道防線；本 validator 是第一道。

    不變量：proposed_embargo_days >= max(7, ceil(2 × half_life_days))

    Wave 5 P3a-Q2 範圍：
      - ``validate_embargo(...)`` 純函式
      - ``compute_min_embargo_days(...)`` helper
      - ``EmbargoCheckResult`` dataclass
      - 4 unit test：pass / fail / boundary / NULL half-life

    不在範圍：
      - replay_routes.py call-site wiring（後續任務）
      - 半衰期估計管線（P3a-Q1 sibling）
      - experiments.embargo_days 的 DB INSERT / UPDATE（P2b runner）

SPEC:
  - REF-20 V3 §8.1 (Sample, Freshness, Embargo)
  - REF-20 V3 §3 G12 (quant patches)
  - REF-20 V3 §12 acceptance #16 (execution_calibration_power)
Workplan:
  docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 R20-P3a-Q2
SQL sibling:
  sql/migrations/V041__replay_oos_embargo_enforcement.sql
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# V3 §8.1 lower bounds / V3 §8.1 下限常數
# ─────────────────────────────────────────────────────────────────────────────

# V3 §8.1 minimum embargo regardless of half-life: 7 days.
# V3 §8.1 不論 half-life 多少，embargo 最少 7 天。
MIN_EMBARGO_DAYS_FLOOR: int = 7

# V3 §8.1 multiplier on half-life: 2 × half_life_days.
# V3 §8.1 半衰期倍數係數。
HALF_LIFE_MULTIPLIER: float = 2.0


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass / 結果 dataclass
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EmbargoCheckResult:
    """Result of embargo validation.

    Embargo 校驗結果。

    Attributes:
        ok: True if proposed embargo satisfies V3 §8.1 invariant.
        proposed_embargo_days: The candidate embargo (input echo).
        min_required_days: ``max(7, ceil(2 × half_life))`` lower bound.
        half_life_days: Input half-life (echo for audit / log).
        reason_zh: Chinese reason if not ok; empty string if ok.
        reason_en: English reason if not ok; empty string if ok.
    """

    ok: bool
    proposed_embargo_days: int
    min_required_days: int
    half_life_days: Optional[float]
    reason_zh: str
    reason_en: str


# ─────────────────────────────────────────────────────────────────────────────
# Public API / 公開 API
# ─────────────────────────────────────────────────────────────────────────────


def compute_min_embargo_days(half_life_days: Optional[float]) -> int:
    """Return ``max(7, ceil(2 × half_life_days))`` lower bound.

    回傳 ``max(7, ceil(2 × half_life_days))`` 下限。

    Args:
        half_life_days: PnL/Sharpe decay half-life in days. ``None``
            indicates unmeasured half-life — V3 §8.1 prescribes a
            conservative 14-day default which yields min embargo
            ``max(7, 2 × 14) = 28`` days.

    Returns:
        Integer minimum embargo days. Always >= 7.

    Raises:
        ValueError: if half_life_days is negative or NaN.

    不變量 / Invariant:
        Result equals PostgreSQL
        ``GREATEST(7, CEIL(2.0 * half_life_days)::INTEGER)``
        for the same input (cross-language consistency with V041 CHECK).
    """
    # V3 §8.1 NULL fallback: assume conservative 14d half-life.
    # V3 §8.1 NULL 後備：取保守的 14 天 half-life。
    if half_life_days is None:
        half_life_days = 14.0

    # Guard against NaN / negative — these would never be a legitimate
    # half-life and indicate upstream pipeline bug.
    # 防 NaN / 負值 — 不會是合法 half-life，表示上游管線 bug。
    if math.isnan(half_life_days):
        raise ValueError(
            "half_life_days is NaN; check upstream half-life estimation pipeline "
            "(P3a-Q1 half_life_estimator)"
        )
    if half_life_days < 0:
        raise ValueError(
            f"half_life_days={half_life_days} is negative; V3 §8.1 requires "
            "non-negative decay half-life"
        )

    # CEIL(2 × half_life_days) matches PG CEIL(2.0 * half_life_days)::INTEGER.
    # CEIL(2 × half_life_days) 對齊 PG CEIL(2.0 * half_life_days)::INTEGER。
    multiplied = HALF_LIFE_MULTIPLIER * float(half_life_days)
    ceiled = int(math.ceil(multiplied))
    return max(MIN_EMBARGO_DAYS_FLOOR, ceiled)


def validate_embargo(
    half_life_days: Optional[float],
    proposed_embargo_days: int,
) -> bool:
    """Return True iff proposed embargo satisfies V3 §8.1 invariant.

    回傳 True 若提議 embargo 符合 V3 §8.1 不變量。

    Args:
        half_life_days: Half-life in days; ``None`` triggers
            conservative 14-day fallback.
        proposed_embargo_days: Candidate embargo (integer days).

    Returns:
        True if ``proposed_embargo_days >= max(7, ceil(2 × half_life))``.
        False otherwise.

    Raises:
        ValueError: on NaN / negative half-life or non-integer
            proposed_embargo_days.
    """
    if not isinstance(proposed_embargo_days, int):
        raise ValueError(
            f"proposed_embargo_days must be int (V3 §8.1 contract); "
            f"got {type(proposed_embargo_days).__name__}"
        )

    min_required = compute_min_embargo_days(half_life_days)
    return proposed_embargo_days >= min_required


def check_embargo(
    half_life_days: Optional[float],
    proposed_embargo_days: int,
) -> EmbargoCheckResult:
    """Return a structured ``EmbargoCheckResult`` for replay_routes adoption.

    回傳結構化 ``EmbargoCheckResult`` 供 replay_routes 採用。

    Args:
        half_life_days: Half-life in days; ``None`` → 14d fallback.
        proposed_embargo_days: Candidate embargo.

    Returns:
        ``EmbargoCheckResult`` with ``ok`` / ``min_required_days`` and
        bilingual reason strings (empty when ``ok=True``).

    Raises:
        ValueError: as per :func:`compute_min_embargo_days`.
    """
    min_required = compute_min_embargo_days(half_life_days)
    ok = proposed_embargo_days >= min_required

    if ok:
        reason_zh = ""
        reason_en = ""
    else:
        reason_zh = (
            f"OOS embargo {proposed_embargo_days} 天 < "
            f"V3 §8.1 下限 {min_required} 天 "
            f"(half_life={half_life_days if half_life_days is not None else '14 (default)'})"
        )
        reason_en = (
            f"OOS embargo {proposed_embargo_days}d < "
            f"V3 §8.1 minimum {min_required}d "
            f"(half_life={half_life_days if half_life_days is not None else '14 (default)'})"
        )

    return EmbargoCheckResult(
        ok=ok,
        proposed_embargo_days=proposed_embargo_days,
        min_required_days=min_required,
        half_life_days=half_life_days,
        reason_zh=reason_zh,
        reason_en=reason_en,
    )


__all__ = [
    "EmbargoCheckResult",
    "MIN_EMBARGO_DAYS_FLOOR",
    "HALF_LIFE_MULTIPLIER",
    "compute_min_embargo_days",
    "validate_embargo",
    "check_embargo",
]
