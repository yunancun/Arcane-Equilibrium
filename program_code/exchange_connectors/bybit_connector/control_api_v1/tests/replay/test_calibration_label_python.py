"""REF-20 Sprint C R6 W6 R6-T9 — calibration_label Python port unit test。

模組目的：
    驗 Python `replay/calibration_label.py::derive_execution_confidence`
    在 QC spec §1.1 5 strategy fixture 下回傳預期 label。byte-equal Rust
    `replay/calibration_label.rs::derive_execution_confidence` 的 5
    reproducibility test（commit `c2cd317f` W5 R6-T8）。

5 case fixtures（與 Rust W5 fixture 同形）：
  1. test_python_grid_1162_yields_calibrated — n=1162 + stable fee → calibrated。
  2. test_python_ma_635_yields_limited_or_calibrated — n=635 + bimodal →
     limited 或 calibrated（QC §1.1 容許邊界）。
  3. test_python_funding_99_not_calibrated — n=99 → 必非 calibrated。
  4. test_python_bb_reversion_7_yields_none — n=7 < 30 → none。
  5. test_python_empty_fills_yields_none — n=0 → none。

這 5 case 鏡像 Rust W5 reproducibility test 的 fixture（同 deterministic
pattern：等距 age 線性插值 + Stable/Bimodal fee 模式）。Python 端不必再
驗 reproducibility（純函數已是字節 deterministic），主要驗 label 與 Rust
端 5 case 對齊（cross-language byte-equal at label level）。

CLAUDE.md §七 雙語注釋強制：default 中文（2026-05-05 governance change）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from program_code.exchange_connectors.bybit_connector.control_api_v1.replay.calibration_label import (  # noqa: E501
    CalibrationResult,
    ExecutionConfidence,
    FillRecord,
    derive_execution_confidence,
)


# 所有 test 共用的參考時鐘 — 固定、確定性（鏡 Rust W5）。
_REFERENCE_NOW = datetime(2026, 5, 5, 12, 0, 0, tzinfo=timezone.utc)


def _build_stable_fee_fixture(
    n: int,
    last_age_days: float,
    oldest_age_days: float,
    fee_rate: float,
    entry: float,
    exit_offset: float,
) -> list[FillRecord]:
    """構造穩定 fee 全等 fill fixture（鏡 Rust W5 Stable pattern）。

    age 線性插值於 [oldest, last] 端點：
      age_i = oldest + (last - oldest) * i / (n-1)
    fee_rate 全 fill 同。
    """
    fills: list[FillRecord] = []
    if n == 0:
        return fills
    if n == 1:
        age = last_age_days
        fills.append(
            FillRecord(
                fee_rate=fee_rate,
                entry_price=entry,
                exit_price=entry + exit_offset,
                is_long=True,
                filled_at=_REFERENCE_NOW - timedelta(days=age),
            )
        )
        return fills
    for i in range(n):
        age = oldest_age_days + (last_age_days - oldest_age_days) * i / (n - 1)
        fills.append(
            FillRecord(
                fee_rate=fee_rate,
                entry_price=entry,
                exit_price=entry + exit_offset,
                is_long=True,
                filled_at=_REFERENCE_NOW - timedelta(days=age),
            )
        )
    return fills


def _build_bimodal_fixture(
    n: int,
    last_age_days: float,
    oldest_age_days: float,
    fee_maker: float,
    fee_taker: float,
    entry: float,
    exit_offset: float,
) -> list[FillRecord]:
    """構造 bimodal maker/taker fee fixture（鏡 Rust W5 Bimodal pattern）。

    偶數 idx 用 maker；奇數 idx 用 taker。age 等距插值同 Stable。
    """
    fills: list[FillRecord] = []
    if n == 0:
        return fills
    for i in range(n):
        age = (
            oldest_age_days + (last_age_days - oldest_age_days) * i / max(n - 1, 1)
        )
        fee = fee_maker if i % 2 == 0 else fee_taker
        fills.append(
            FillRecord(
                fee_rate=fee,
                entry_price=entry,
                exit_price=entry + exit_offset,
                is_long=True,
                filled_at=_REFERENCE_NOW - timedelta(days=age),
            )
        )
    return fills


def test_python_grid_1162_yields_calibrated() -> None:
    """grid_trading n=1162 + stable maker fee 2 bps → calibrated。

    QC §1.1 預期：calibrated（n ≥ 200 + age ≤ 7d + MAD < 3 bps + IQR < 8 bps）。
    """
    fills = _build_stable_fee_fixture(
        n=1162,
        last_age_days=0.0,
        oldest_age_days=6.0,
        fee_rate=0.0002,  # 2 bps stable
        entry=100.0,
        exit_offset=1.0,
    )
    result = derive_execution_confidence(fills, _REFERENCE_NOW)
    assert isinstance(result, CalibrationResult)
    assert result.label == ExecutionConfidence.CALIBRATED
    assert result.sample_count == 1162
    assert result.fee_bps_mad < 3.0, "MAD must be < 3 bps for calibrated"
    assert result.ttl == timedelta(days=7)
    # p5 ≤ p50 ≤ p95 不變式。
    assert result.net_bps_p5 <= result.net_bps_p50
    assert result.net_bps_p50 <= result.net_bps_p95


def test_python_ma_635_yields_limited_or_calibrated() -> None:
    """ma_crossover n=635 + bimodal maker(2) / taker(5.5) bps → limited 或 calibrated。

    QC §1.1 預期：bimodal 拉開 MAD 可能 > 3 bps → limited；若 fixture 走 spec 容許
    上限仍 calibrated（容差範圍）。
    """
    fills = _build_bimodal_fixture(
        n=635,
        last_age_days=2.0,
        oldest_age_days=6.5,
        fee_maker=0.0002,
        fee_taker=0.00055,
        entry=100.0,
        exit_offset=1.0,
    )
    result = derive_execution_confidence(fills, _REFERENCE_NOW)
    assert result.label != ExecutionConfidence.NONE, (
        f"ma_crossover n={result.sample_count} freshness OK 應為 limited 或 calibrated；"
        f"實際 = {result.label.value}"
    )
    assert result.sample_count == 635


def test_python_funding_99_not_calibrated() -> None:
    """funding_arb n=99 < 200 → 必非 calibrated（QC §1.1 強制）。

    n<200 即使 freshness OK + MAD OK 也不能進 calibrated。
    """
    fills = _build_stable_fee_fixture(
        n=99,
        last_age_days=1.0,
        oldest_age_days=5.0,
        fee_rate=0.0002,
        entry=100.0,
        exit_offset=1.0,
    )
    result = derive_execution_confidence(fills, _REFERENCE_NOW)
    assert result.label != ExecutionConfidence.CALIBRATED, (
        f"funding_arb n={result.sample_count} < 200 必非 calibrated"
    )
    assert result.sample_count == 99


def test_python_bb_reversion_7_yields_none() -> None:
    """bb_reversion n=7 < 30 → none（QC §1.1 強制）。"""
    fills = _build_stable_fee_fixture(
        n=7,
        last_age_days=1.0,
        oldest_age_days=3.0,
        fee_rate=0.0002,
        entry=100.0,
        exit_offset=1.0,
    )
    result = derive_execution_confidence(fills, _REFERENCE_NOW)
    assert result.label == ExecutionConfidence.NONE
    assert result.sample_count == 7
    assert result.ttl == timedelta(0)


def test_python_empty_fills_yields_none() -> None:
    """空 fills list → none + sample_count=0 + last_fill_age_ms=-1。"""
    result = derive_execution_confidence([], _REFERENCE_NOW)
    assert result.label == ExecutionConfidence.NONE
    assert result.sample_count == 0
    assert result.last_fill_age_ms == -1
    assert result.ttl == timedelta(0)


def test_python_stale_fills_yields_none() -> None:
    """all fills > 14d old → none（freshness 短路）。

    額外 boundary case 證 freshness>14d 短路（鏡 Rust W3 module test
    `test_freshness_boundary_15d_returns_none`）。
    """
    fills = _build_stable_fee_fixture(
        n=300,
        last_age_days=15.0,  # 15d > 14d cutoff
        oldest_age_days=20.0,
        fee_rate=0.0002,
        entry=100.0,
        exit_offset=1.0,
    )
    result = derive_execution_confidence(fills, _REFERENCE_NOW)
    assert result.label == ExecutionConfidence.NONE
    assert result.sample_count == 300


def test_python_label_str_value_matches_v049_enum() -> None:
    """ExecutionConfidence.value 字串對齊 V049 CHECK enum。

    驗 `result.label.value` 直接餵 `update_execution_confidence` helper 不需
    額外映射（V049_EXECUTION_CONFIDENCE_ALLOWED = {'none','limited','calibrated'}）。
    """
    assert ExecutionConfidence.NONE.value == "none"
    assert ExecutionConfidence.LIMITED.value == "limited"
    assert ExecutionConfidence.CALIBRATED.value == "calibrated"


def test_python_nan_fee_rate_filtered_out() -> None:
    """NaN fee_rate row 應被 Step 1 過濾（鏡 Rust W3 `test_nan_fee_rate_filtered`）。"""
    fills = [
        FillRecord(
            fee_rate=0.0002,
            entry_price=100.0,
            exit_price=101.0,
            is_long=True,
            filled_at=_REFERENCE_NOW - timedelta(days=1),
        ),
        FillRecord(
            fee_rate=float("nan"),  # 應被過濾
            entry_price=100.0,
            exit_price=101.0,
            is_long=True,
            filled_at=_REFERENCE_NOW - timedelta(days=2),
        ),
        FillRecord(
            fee_rate=0.0002,
            entry_price=100.0,
            exit_price=101.0,
            is_long=True,
            filled_at=_REFERENCE_NOW - timedelta(days=3),
        ),
    ]
    result = derive_execution_confidence(fills, _REFERENCE_NOW)
    assert result.sample_count == 2  # 3 row → 1 過濾後 2


def test_python_ci_n_lt_30_uses_normal_extension() -> None:
    """n=10 → CI 走 normal-extension fallback（median ± 1.645×1.4826×MAD）。"""
    fills = _build_stable_fee_fixture(
        n=10,
        last_age_days=1.0,
        oldest_age_days=2.0,
        fee_rate=0.0002,
        entry=100.0,
        exit_offset=1.0,
    )
    result = derive_execution_confidence(fills, _REFERENCE_NOW)
    # n=10 → label=None（n<30）；但 CI 仍計算（鏡 Rust）。
    assert result.label == ExecutionConfidence.NONE
    # 全 fill fee 同 → MAD=0 → half_width=0 → CI=(med, med, med) collapse。
    # 不檢查精確值；驗有限即可（不為 NaN）。
    import math
    assert math.isfinite(result.net_bps_p5)
    assert math.isfinite(result.net_bps_p50)
    assert math.isfinite(result.net_bps_p95)
    assert result.net_bps_p5 == result.net_bps_p50 == result.net_bps_p95


def test_python_short_direction_inverts_gross_bps() -> None:
    """is_long=False → direction=-1 → gross_bps 反號。

    驗 caller 傳入 short side 時 net_bps_after_fee 計算反向（鏡 Rust 同義 test）。
    """
    # exit > entry + is_long=True → gross_bps 正；exit > entry + is_long=False →
    # gross_bps 負。對 calibration label 不影響（label 走 fee_bps_mad 主信號），
    # 但對 net_bps_p* 應反映方向差。
    fills_long = [
        FillRecord(
            fee_rate=0.0002,
            entry_price=100.0,
            exit_price=110.0,
            is_long=True,
            filled_at=_REFERENCE_NOW - timedelta(days=1),
        )
    ]
    fills_short = [
        FillRecord(
            fee_rate=0.0002,
            entry_price=100.0,
            exit_price=110.0,
            is_long=False,
            filled_at=_REFERENCE_NOW - timedelta(days=1),
        )
    ]
    r_long = derive_execution_confidence(fills_long, _REFERENCE_NOW)
    r_short = derive_execution_confidence(fills_short, _REFERENCE_NOW)
    # n=1 < 30 → CI=(med, med, med) — long 為正 net；short 為負 net。
    assert r_long.net_bps_p50 > 0
    assert r_short.net_bps_p50 < 0
    # label 不變（兩者都 None，n<30）。
    assert r_long.label == ExecutionConfidence.NONE
    assert r_short.label == ExecutionConfidence.NONE


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
