"""
Tests for regime_controller (REF-20 Wave 5 RGM-Q1).
regime_controller 測試（REF-20 Wave 5 RGM-Q1）。

Coverage / 覆蓋:
1. 0 fills → warming_up + remaining=500. / 0 fills → warming_up + 缺 500。
2. 250 fills → warming_up + remaining=250. / 250 fills → warming_up + 缺 250。
3. 499 fills → still warming_up (1 fill shy). / 499 fills 仍 warming_up（差 1 fill）。
4. 500 fills → ready + remaining=0. / 500 fills → ready + 缺 0。

Bonus / 額外:
- Boundary semantics ≥ 500 (501 also ready).
- get_cell_status composite mirrors warmup result 1:1 (Q1 design).
- Invalid cell_key / fills_count raises ValueError.
- Constructor override / non-positive threshold rejected.

Test invocation / 測試呼叫:
    pytest srv/program_code/learning_engine/tests/test_regime_controller.py -v

References / 參考:
- docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md §8.4 #1
- docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 R20-RGM-Q1
"""

from __future__ import annotations

import pytest

from program_code.learning_engine.regime_controller import (
    CellRegimeStatus,
    RegimeController,
    WARMUP_FILLS_THRESHOLD,
    WarmupStatus,
)


# ---------------------------------------------------------------------------
# Fixtures / 共享測試夾具
# ---------------------------------------------------------------------------


@pytest.fixture
def controller() -> RegimeController:
    """Default-threshold controller (V3 §8.4 #1 production threshold).

    預設閾值 controller（V3 §8.4 #1 production 閾值）。
    """
    return RegimeController()


CELL_KEY = "grid_trading::BTCUSDT::long"


# ---------------------------------------------------------------------------
# 1. 0 fills → warming_up + remaining=500
# ---------------------------------------------------------------------------
def test_check_warmup_returns_warming_up_at_zero_fills(
    controller: RegimeController,
) -> None:
    """0 fills → ready=False, remaining=500.

    0 fills → ready=False, 缺 500。
    """
    status = controller.check_warmup(CELL_KEY, 0)
    assert isinstance(status, WarmupStatus)
    assert status.ready is False
    assert status.fills_count == 0
    assert status.threshold == 500
    assert status.remaining == 500
    assert status.status == "warming_up"
    assert status.cell_key == CELL_KEY
    # Bilingual reasons populated.
    # 雙語 reason 已填。
    assert "暖機中" in status.reason_zh
    assert "warming up" in status.reason_en
    # Reason references threshold + cell key.
    # reason 包含閾值與 cell key。
    assert "500" in status.reason_zh
    assert CELL_KEY in status.reason_en


# ---------------------------------------------------------------------------
# 2. 250 fills → warming_up + remaining=250
# ---------------------------------------------------------------------------
def test_check_warmup_returns_warming_up_at_250_fills(
    controller: RegimeController,
) -> None:
    """250 fills → ready=False, remaining=250.

    250 fills → ready=False, 缺 250。
    """
    status = controller.check_warmup(CELL_KEY, 250)
    assert status.ready is False
    assert status.fills_count == 250
    assert status.remaining == 250
    assert status.status == "warming_up"
    assert "250" in status.reason_zh


# ---------------------------------------------------------------------------
# 3. 499 fills → still warming_up (1 fill shy)
# 3. 499 fills → 仍 warming_up（差 1 fill）
# ---------------------------------------------------------------------------
def test_check_warmup_still_warming_at_499_fills(
    controller: RegimeController,
) -> None:
    """499 fills → ready=False, remaining=1 (boundary just below threshold).

    499 fills → ready=False, 缺 1（閾值下臨界）。
    """
    status = controller.check_warmup(CELL_KEY, 499)
    assert status.ready is False
    assert status.fills_count == 499
    assert status.remaining == 1
    assert status.status == "warming_up"


# ---------------------------------------------------------------------------
# 4. 500 fills → ready
# ---------------------------------------------------------------------------
def test_check_warmup_ready_at_500_fills(
    controller: RegimeController,
) -> None:
    """500 fills → ready=True, remaining=0 (boundary equal to threshold).

    500 fills → ready=True, 缺 0（閾值等值臨界）。
    """
    status = controller.check_warmup(CELL_KEY, 500)
    assert status.ready is True
    assert status.fills_count == 500
    assert status.remaining == 0
    assert status.status == "ready"
    # Reasons empty when ready.
    # ready 時 reason 應空。
    assert status.reason_zh == ""
    assert status.reason_en == ""


# ---------------------------------------------------------------------------
# Bonus: ready boundary > 500 / ready 邊界 > 500
# ---------------------------------------------------------------------------
def test_check_warmup_ready_above_threshold(
    controller: RegimeController,
) -> None:
    """501+ fills also ready; remaining stays 0 (clamped not negative).

    501+ fills 也 ready；remaining 維持 0（不會變負）。
    """
    status = controller.check_warmup(CELL_KEY, 501)
    assert status.ready is True
    assert status.remaining == 0

    status_large = controller.check_warmup(CELL_KEY, 9999)
    assert status_large.ready is True
    assert status_large.remaining == 0


# ---------------------------------------------------------------------------
# Bonus: get_cell_status composite (Q1 — 1:1 with warmup)
# 額外：get_cell_status 複合（Q1 — 與 warmup 1:1）
# ---------------------------------------------------------------------------
def test_get_cell_status_mirrors_warmup_result(
    controller: RegimeController,
) -> None:
    """``get_cell_status`` composite_status mirrors warmup result (Q1 design).

    ``get_cell_status`` 的 composite_status 鏡像 warmup 結果（Q1 設計）。
    """
    # Below threshold.
    status_low = controller.get_cell_status(CELL_KEY, 100)
    assert isinstance(status_low, CellRegimeStatus)
    assert status_low.composite_status == "warming_up"
    assert status_low.warmup.ready is False
    assert status_low.warmup.remaining == 400
    assert status_low.cell_key == CELL_KEY
    assert status_low.extra_payload == {}  # default empty

    # At threshold.
    status_ready = controller.get_cell_status(CELL_KEY, 500)
    assert status_ready.composite_status == "ready"
    assert status_ready.warmup.ready is True
    assert "ready" in status_ready.reason_en
    assert "ready" in status_ready.reason_zh.lower() or "完成" in status_ready.reason_zh


def test_get_cell_status_extra_payload_passthrough(
    controller: RegimeController,
) -> None:
    """``extra_payload`` ctor arg passes through to result (Q2/Q3/Q4 forward-compat hook).

    ``extra_payload`` 透傳到結果（Q2/Q3/Q4 向前相容掛鉤）。
    """
    payload = {"cusum_z_score": 1.5, "kupiec_n": 220}
    status = controller.get_cell_status(CELL_KEY, 500, extra_payload=payload)
    assert status.extra_payload == payload
    # Defensive copy: mutating caller dict must not mutate result.
    # 防禦性 copy：caller 改 dict 不改結果。
    payload["cusum_z_score"] = 99.9
    assert status.extra_payload["cusum_z_score"] == 1.5


# ---------------------------------------------------------------------------
# Constants / 常數
# ---------------------------------------------------------------------------
def test_warmup_threshold_constant_matches_v3_spec() -> None:
    """Module constant ``WARMUP_FILLS_THRESHOLD`` matches V3 §8.4 #1.

    模組常數 ``WARMUP_FILLS_THRESHOLD`` 對齊 V3 §8.4 #1。
    """
    assert WARMUP_FILLS_THRESHOLD == 500


def test_default_constructor_uses_v3_spec_threshold() -> None:
    """Default constructor uses V3 §8.4 #1 threshold (500).

    預設 ctor 用 V3 §8.4 #1 閾值（500）。
    """
    ctrl = RegimeController()
    assert ctrl.warmup_threshold == 500


def test_constructor_override_for_hermetic_test() -> None:
    """Hermetic test override allowed; production caller MUST use default.

    Hermetic test 可覆寫；production caller 必用預設。
    """
    ctrl = RegimeController(warmup_threshold=10)
    assert ctrl.warmup_threshold == 10
    status = ctrl.check_warmup(CELL_KEY, 10)
    assert status.ready is True


# ---------------------------------------------------------------------------
# Error handling / 錯誤處理
# ---------------------------------------------------------------------------
def test_check_warmup_rejects_empty_cell_key(
    controller: RegimeController,
) -> None:
    """Empty cell_key raises ValueError.

    空 cell_key raise ValueError。
    """
    with pytest.raises(ValueError, match="non-empty string"):
        controller.check_warmup("", 100)
    with pytest.raises(ValueError, match="non-empty string"):
        controller.check_warmup("   ", 100)  # whitespace-only


def test_check_warmup_rejects_negative_fills(
    controller: RegimeController,
) -> None:
    """Negative fills_count raises ValueError.

    負 fills_count raise ValueError。
    """
    with pytest.raises(ValueError, match="non-negative"):
        controller.check_warmup(CELL_KEY, -1)


def test_check_warmup_rejects_non_integer_fills(
    controller: RegimeController,
) -> None:
    """Non-integer fills_count raises ValueError.

    非整數 fills_count raise ValueError。
    """
    with pytest.raises(ValueError, match="must be int"):
        controller.check_warmup(CELL_KEY, 100.5)  # type: ignore[arg-type]


def test_constructor_rejects_non_positive_threshold() -> None:
    """Non-positive warmup_threshold raises ValueError.

    非正 warmup_threshold raise ValueError。
    """
    with pytest.raises(ValueError, match="must be positive"):
        RegimeController(warmup_threshold=0)
    with pytest.raises(ValueError, match="must be positive"):
        RegimeController(warmup_threshold=-100)


def test_constructor_rejects_non_integer_threshold() -> None:
    """Non-integer warmup_threshold raises ValueError.

    非整數 warmup_threshold raise ValueError。
    """
    with pytest.raises(ValueError, match="must be int"):
        RegimeController(warmup_threshold=500.0)  # type: ignore[arg-type]
