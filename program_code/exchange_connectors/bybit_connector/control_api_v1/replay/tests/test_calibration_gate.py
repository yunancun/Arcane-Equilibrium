"""Unit tests for REF-20 P3a-Q6 CalibrationGate.

REF-20 P3a-Q6 CalibrationGate 的單元測試。

Test invocation / 測試呼叫:
    pytest srv/program_code/exchange_connectors/bybit_connector/\
control_api_v1/replay/tests/test_calibration_gate.py -v

References / 參考:
- docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md §8.1
- docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 R20-P3a-Q6
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Path resolution / 路徑解析
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
_CONTROL_API_ROOT = _THIS_FILE.parents[2]
if str(_CONTROL_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_CONTROL_API_ROOT))


# ---------------------------------------------------------------------------
# Import target / 匯入目標
# ---------------------------------------------------------------------------
from replay.calibration_gate import (  # type: ignore[import-not-found]  # noqa: E402
    CalibrationGate,
    FRESHNESS_MAX_HOURS,
    FreshnessCheck,
    HandoffVerdict,
    PowerCheck,
    SAMPLE_POWER_MIN_N,
)


# ---------------------------------------------------------------------------
# Fixtures / 共享測試夾具
# ---------------------------------------------------------------------------
@pytest.fixture
def gate() -> CalibrationGate:
    """Default-threshold gate (V3 §8.1 production thresholds).

    預設閾值 gate（V3 §8.1 production 閾值）。
    """
    return CalibrationGate()


@pytest.fixture
def now_utc() -> datetime:
    """Fixed UTC reference time for deterministic age computation.

    固定 UTC 參考時間，讓年齡計算確定可重現。
    """
    return datetime(2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# 1. handoff_ok: fresh + powered → ok
# 1. handoff_ok：鮮度 + 功效都過 → ok
# ---------------------------------------------------------------------------
def test_gate_handoff_ok_when_fresh_and_powered(
    gate: CalibrationGate, now_utc: datetime
) -> None:
    """Fresh calibration (24h ago) + n=250 → verdict=handoff_ok.

    鮮度新鮮（24h 前）+ n=250 → verdict=handoff_ok。
    """
    # 24h ago, well within 72h threshold.
    # 24h 前，遠在 72h 閾值內。
    cal_ts = now_utc - timedelta(hours=24)
    manifest = {
        "calibration_ts": cal_ts,
        "n_fills": 250,
    }
    verdict = gate.gate_handoff(manifest, now=now_utc)
    assert isinstance(verdict, HandoffVerdict)
    assert verdict.verdict == "handoff_ok"
    assert verdict.freshness_check.status == "ok"
    assert verdict.power_check.status == "ok"
    assert verdict.reason_zh == "校準鮮度與樣本功效均符合 V3 §8.1 不變量"
    assert "satisfy V3 §8.1" in verdict.reason_en


# ---------------------------------------------------------------------------
# 2. stale_calibration: too old → reject
# 2. stale_calibration：過期 → 拒絕
# ---------------------------------------------------------------------------
def test_gate_handoff_rejects_stale_calibration(
    gate: CalibrationGate, now_utc: datetime
) -> None:
    """Calibration age 80h > 72h → verdict=stale_calibration.

    校準年齡 80h > 72h → verdict=stale_calibration。
    """
    cal_ts = now_utc - timedelta(hours=80)
    manifest = {
        "calibration_ts": cal_ts,
        "n_fills": 250,  # power passes
    }
    verdict = gate.gate_handoff(manifest, now=now_utc)
    assert verdict.verdict == "stale_calibration"
    assert verdict.freshness_check.status == "stale"
    assert verdict.power_check.status == "ok"
    # Bilingual reason surfaces the failing dimension.
    # 雙語 reason 顯露失敗維度。
    assert "校準鮮度過期" in verdict.reason_zh
    assert "calibration stale" in verdict.reason_en
    # Age must be reported.
    # 年齡要回報。
    assert abs(verdict.freshness_check.age_hours - 80.0) < 1e-4


# ---------------------------------------------------------------------------
# 3. insufficient_power: n < 200 → reject
# 3. insufficient_power：n < 200 → 拒絕
# ---------------------------------------------------------------------------
def test_gate_handoff_rejects_insufficient_power(
    gate: CalibrationGate, now_utc: datetime
) -> None:
    """Fresh calibration + n=150 → verdict=insufficient_power.

    鮮度新鮮 + n=150 → verdict=insufficient_power。
    """
    cal_ts = now_utc - timedelta(hours=12)
    manifest = {
        "calibration_ts": cal_ts,
        "n_fills": 150,
    }
    verdict = gate.gate_handoff(manifest, now=now_utc)
    assert verdict.verdict == "insufficient_power"
    assert verdict.freshness_check.status == "ok"
    assert verdict.power_check.status == "insufficient"
    # Deficit reported.
    # 缺額要回報。
    assert verdict.power_check.deficit == 50  # 200 - 150
    assert "樣本功效不足" in verdict.reason_zh
    assert "insufficient sample power" in verdict.reason_en


# ---------------------------------------------------------------------------
# 4. both_fail: stale AND underpowered → composite reason
# 4. both_fail：又過期又功效不足 → 複合 reason
# ---------------------------------------------------------------------------
def test_gate_handoff_both_fail_composite_reason(
    gate: CalibrationGate, now_utc: datetime
) -> None:
    """Stale calibration + n=100 → verdict=both_fail with composite reason.

    校準過期 + n=100 → verdict=both_fail 含複合 reason。
    """
    cal_ts = now_utc - timedelta(hours=100)  # 100h > 72h threshold
    manifest = {
        "calibration_ts": cal_ts,
        "n_fills": 100,  # 100 < 200 threshold
    }
    verdict = gate.gate_handoff(manifest, now=now_utc)
    assert verdict.verdict == "both_fail"
    assert verdict.freshness_check.status == "stale"
    assert verdict.power_check.status == "insufficient"
    # Composite reason must mention BOTH dimensions.
    # 複合 reason 必同時提到兩個維度。
    assert "校準鮮度過期" in verdict.reason_zh
    assert "樣本功效不足" in verdict.reason_zh
    assert "calibration stale" in verdict.reason_en
    assert "insufficient sample power" in verdict.reason_en


# ---------------------------------------------------------------------------
# Bonus: per-method tests + edge cases / 每方法 + 邊界 case
# ---------------------------------------------------------------------------
def test_check_freshness_boundary_72h_exact_passes(
    gate: CalibrationGate, now_utc: datetime
) -> None:
    """Boundary: age = 72h exact → status='ok' (≤ semantic).

    邊界：年齡 = 72h 恰好 → status='ok'（≤ 語意）。
    """
    cal_ts = now_utc - timedelta(hours=72)
    result = gate.check_freshness(cal_ts, now=now_utc)
    assert result.status == "ok"
    assert abs(result.age_hours - 72.0) < 1e-4


def test_check_sample_power_boundary_200_exact_passes(
    gate: CalibrationGate,
) -> None:
    """Boundary: n = 200 exact → status='ok' (≥ semantic).

    邊界：n = 200 恰好 → status='ok'（≥ 語意）。
    """
    result = gate.check_sample_power(200)
    assert result.status == "ok"
    assert result.deficit == 0


def test_check_freshness_rejects_naive_datetime(
    gate: CalibrationGate, now_utc: datetime
) -> None:
    """Naive (no tzinfo) datetime raises ValueError.

    無 tzinfo 的 datetime raise ValueError。
    """
    naive_ts = datetime(2026, 5, 3, 8, 0, 0)  # no tzinfo
    with pytest.raises(ValueError, match="timezone-aware"):
        gate.check_freshness(naive_ts, now=now_utc)


def test_check_sample_power_rejects_negative_n(gate: CalibrationGate) -> None:
    """Negative n raises ValueError.

    負 n raise ValueError。
    """
    with pytest.raises(ValueError, match="non-negative"):
        gate.check_sample_power(-1)


def test_gate_handoff_rejects_missing_manifest_fields(
    gate: CalibrationGate, now_utc: datetime
) -> None:
    """Manifest missing required fields raises KeyError.

    Manifest 缺必要欄位 raise KeyError。
    """
    with pytest.raises(KeyError, match="calibration_ts"):
        gate.gate_handoff({"n_fills": 250}, now=now_utc)
    with pytest.raises(KeyError, match="n_fills"):
        gate.gate_handoff(
            {"calibration_ts": now_utc - timedelta(hours=24)},
            now=now_utc,
        )


def test_gate_constants_match_v3_spec() -> None:
    """Module-level constants reflect V3 §8.1 production thresholds.

    模組級常數對齊 V3 §8.1 production 閾值。
    """
    assert FRESHNESS_MAX_HOURS == 72.0
    assert SAMPLE_POWER_MIN_N == 200


def test_gate_init_rejects_non_positive_overrides() -> None:
    """Constructor rejects non-positive threshold overrides.

    Constructor 拒絕非正閾值覆寫。
    """
    with pytest.raises(ValueError, match="freshness_max_hours"):
        CalibrationGate(freshness_max_hours=0)
    with pytest.raises(ValueError, match="sample_power_min_n"):
        CalibrationGate(sample_power_min_n=0)
