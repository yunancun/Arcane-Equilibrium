"""Unit tests for REF-20 P3a-Q2 embargo_validator.

REF-20 P3a-Q2 embargo_validator 的單元測試。

Test invocation / 測試呼叫:
    pytest srv/program_code/exchange_connectors/bybit_connector/\
control_api_v1/replay/tests/test_embargo_validator.py -v

References / 參考:
- docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md §8.1
- docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 R20-P3a-Q2
- sql/migrations/V041__replay_oos_embargo_enforcement.sql (SQL sibling)
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Path resolution / 路徑解析
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
# tests / replay / control_api_v1
_CONTROL_API_ROOT = _THIS_FILE.parents[2]
if str(_CONTROL_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_CONTROL_API_ROOT))


# ---------------------------------------------------------------------------
# Import target / 匯入目標
# ---------------------------------------------------------------------------
from replay.embargo_validator import (  # type: ignore[import-not-found]  # noqa: E402
    EmbargoCheckResult,
    HALF_LIFE_MULTIPLIER,
    MIN_EMBARGO_DAYS_FLOOR,
    check_embargo,
    compute_min_embargo_days,
    validate_embargo,
)


# ---------------------------------------------------------------------------
# 1. validate_embargo() pass case / 通過 case
# ---------------------------------------------------------------------------
def test_validate_embargo_passes_when_above_floor_and_2x_half_life() -> None:
    """V3 §8.1 invariant satisfied: embargo >= max(7, ceil(2 × half_life)).

    V3 §8.1 不變量滿足。
    """
    # half_life=3 → max(7, ceil(6)) = 7. embargo=7 should pass.
    # half_life=3 → max(7, ceil(6)) = 7。embargo=7 通過。
    assert validate_embargo(3.0, 7) is True
    # half_life=5 → max(7, ceil(10)) = 10. embargo=10 exact match should pass.
    # half_life=5 → max(7, ceil(10)) = 10。embargo=10 等值通過。
    assert validate_embargo(5.0, 10) is True
    # half_life=7.5 → max(7, ceil(15)) = 15. embargo=15 should pass.
    # half_life=7.5 → max(7, ceil(15)) = 15。embargo=15 通過。
    assert validate_embargo(7.5, 15) is True
    # Embargo well above the bound also passes.
    # embargo 遠超下限也通過。
    assert validate_embargo(5.0, 30) is True


# ---------------------------------------------------------------------------
# 2. validate_embargo() fail case / 失敗 case
# ---------------------------------------------------------------------------
def test_validate_embargo_fails_when_below_floor_or_below_2x_half_life() -> None:
    """V3 §8.1 invariant violated: rejection.

    V3 §8.1 不變量違反：拒絕。
    """
    # 7-day floor binding case: half_life=3 needs embargo >= 7.
    # 7-day floor 邊界 case：half_life=3 需 embargo >= 7。
    assert validate_embargo(3.0, 6) is False
    # 2x half-life binding: half_life=5 needs embargo >= 10; 9 fails.
    # 2x half-life 邊界：half_life=5 需 embargo >= 10；9 失敗。
    assert validate_embargo(5.0, 9) is False
    # CEIL semantics: half_life=5.6 → ceil(11.2) = 12; 11 fails.
    # CEIL 語意：half_life=5.6 → ceil(11.2) = 12；11 失敗。
    assert validate_embargo(5.6, 11) is False
    # Default fallback (None → 14d) needs embargo >= 28.
    # 預設 fallback（None → 14d）需 embargo >= 28。
    assert validate_embargo(None, 27) is False


# ---------------------------------------------------------------------------
# 3. check_embargo() returns structured result with bilingual reasons.
# 3. check_embargo() 回結構化結果含雙語原因。
# ---------------------------------------------------------------------------
def test_check_embargo_returns_bilingual_reason_on_fail() -> None:
    """``check_embargo`` returns ``EmbargoCheckResult`` with bilingual reasons.

    ``check_embargo`` 回 ``EmbargoCheckResult`` 含雙語 reason。
    """
    result = check_embargo(5.6, 11)
    assert isinstance(result, EmbargoCheckResult)
    assert result.ok is False
    assert result.proposed_embargo_days == 11
    # ceil(2 × 5.6) = ceil(11.2) = 12; max(7, 12) = 12.
    assert result.min_required_days == 12
    assert result.half_life_days == 5.6
    # Reason strings must be non-empty in both languages.
    # reason 字串中英都不能空。
    assert result.reason_zh != ""
    assert result.reason_en != ""
    # Chinese reason must reference 天 (day) and §8.1.
    # 中文 reason 必引「天」與「§8.1」。
    assert "天" in result.reason_zh
    assert "§8.1" in result.reason_zh
    # English reason must reference "embargo" and "minimum".
    # 英文 reason 必引 "embargo" 與 "minimum"。
    assert "embargo" in result.reason_en.lower()
    assert "minimum" in result.reason_en.lower()


def test_check_embargo_returns_empty_reason_on_pass() -> None:
    """``check_embargo`` ok=True returns empty bilingual reason strings.

    ``check_embargo`` ok=True 時 reason 字串應為空。
    """
    result = check_embargo(5.0, 10)
    assert result.ok is True
    assert result.proposed_embargo_days == 10
    assert result.min_required_days == 10
    assert result.half_life_days == 5.0
    assert result.reason_zh == ""
    assert result.reason_en == ""


# ---------------------------------------------------------------------------
# 4. SQL alignment / 與 V041 CHECK 對齊
# ---------------------------------------------------------------------------
def test_python_validator_aligns_with_v041_check_expression() -> None:
    """``compute_min_embargo_days`` matches V041 ``GREATEST(7, CEIL(2.0 × h))``.

    ``compute_min_embargo_days`` 與 V041 ``GREATEST(7, CEIL(2.0 × h))`` 對齊。
    """
    # Direct cross-language replication.
    # 直接跨語言重現 SQL 表達式。
    def _sql_min(half_life: float) -> int:
        # PG: GREATEST(7, CEIL(2.0 * half_life_days)::INTEGER)
        return max(7, int(math.ceil(2.0 * float(half_life))))

    representative = [
        (0.0, 7),
        (3.0, 7),    # 6 < 7 → floor binds
        (3.5, 7),    # 7 == 7 → floor binds
        (4.0, 8),    # 8 > 7 → 2x half-life binds
        (5.0, 10),
        (5.6, 12),   # ceil(11.2) = 12
        (7.5, 15),
        (10.0, 20),
        (14.0, 28),  # default-fallback case
        (100.0, 200),
    ]
    for half_life, expected_min in representative:
        py_min = compute_min_embargo_days(half_life)
        sql_min = _sql_min(half_life)
        assert py_min == sql_min == expected_min, (
            f"Mismatch at half_life={half_life}: "
            f"py={py_min} sql={sql_min} expected={expected_min}"
        )

    # NULL fallback — Python None → 14d default;
    # SQL NULL CHECK passes (uses CHECK ... OR half_life_days IS NULL).
    # NULL fallback — Python None → 14d 預設；
    # SQL NULL CHECK 通過（用 CHECK ... OR half_life_days IS NULL）。
    assert compute_min_embargo_days(None) == 28


# ---------------------------------------------------------------------------
# Bonus: error handling / 額外：錯誤處理
# ---------------------------------------------------------------------------
def test_compute_min_embargo_days_rejects_nan_and_negative() -> None:
    """NaN / negative half-life raises ValueError.

    NaN / 負 half-life raise ValueError。
    """
    with pytest.raises(ValueError, match="NaN"):
        compute_min_embargo_days(float("nan"))
    with pytest.raises(ValueError, match="negative"):
        compute_min_embargo_days(-1.0)


def test_validate_embargo_rejects_non_integer_proposed() -> None:
    """Non-integer ``proposed_embargo_days`` raises ValueError.

    非整數 ``proposed_embargo_days`` raise ValueError。
    """
    with pytest.raises(ValueError, match="must be int"):
        validate_embargo(5.0, 10.5)  # type: ignore[arg-type]


def test_constants_match_v3_spec() -> None:
    """``MIN_EMBARGO_DAYS_FLOOR`` and ``HALF_LIFE_MULTIPLIER`` match V3 §8.1.

    常數 ``MIN_EMBARGO_DAYS_FLOOR`` 與 ``HALF_LIFE_MULTIPLIER`` 對齊 V3 §8.1。
    """
    assert MIN_EMBARGO_DAYS_FLOOR == 7
    assert HALF_LIFE_MULTIPLIER == 2.0
